"""Tests for ConfirmationFirewall — classification + approval logic.

Run: /usr/local/bin/python3 -m pytest tests/unit/test_confirmation_firewall.py -v
"""

from __future__ import annotations

import json

# Import module under test
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lib" / "core"))
from confirmation_firewall import (
    ActionRisk,
    ConfirmationFirewall,
    _approve_pending,
    _deny_pending,
    _load_daily_spend,
    _poll_pending,
    _record_spend,
    _write_pending,
    classify_action,
)

# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Redirect all state dirs to tmp_path so tests don't touch real ~/.sapphire."""
    monkeypatch.setattr("confirmation_firewall.SAPPHIRE_STATE", tmp_path)
    monkeypatch.setattr("confirmation_firewall.PENDING_DIR", tmp_path / "pending")
    monkeypatch.setattr("confirmation_firewall.LIMITS_FILE", tmp_path / "limits.json")
    monkeypatch.setenv("SAPPHIRE_NO_REDIS", "1")
    yield tmp_path


@pytest.fixture
def fw():
    return ConfirmationFirewall()


# ─── Classification Tests ─────────────────────────────────────────────────────

class TestClassification:
    def test_read_only_commands(self):
        assert classify_action("cat /var/log/syslog") == ActionRisk.READ_ONLY
        assert classify_action("ls -la ~/.hermes/") == ActionRisk.READ_ONLY
        assert classify_action("health check endpoint") == ActionRisk.READ_ONLY
        assert classify_action("get model list") == ActionRisk.READ_ONLY
        assert classify_action("status check") == ActionRisk.READ_ONLY

    def test_self_modify_commands(self):
        assert classify_action("write log entry") == ActionRisk.SELF_MODIFY
        assert classify_action("append log") == ActionRisk.SELF_MODIFY
        assert classify_action("send self message") == ActionRisk.SELF_MODIFY

    def test_system_modify_commands(self):
        assert classify_action("restart hermes") == ActionRisk.SYSTEM_MODIFY
        assert classify_action("launchctl kickstart inference-proxy") == ActionRisk.SYSTEM_MODIFY
        assert classify_action("config set PI_RARI2_ENABLED=1") == ActionRisk.SYSTEM_MODIFY
        assert classify_action("pip install requests") == ActionRisk.SYSTEM_MODIFY
        assert classify_action("chmod +x script.sh") == ActionRisk.SYSTEM_MODIFY

    def test_external_send_commands(self):
        assert classify_action("send message to alice") == ActionRisk.EXTERNAL_SEND
        assert classify_action("git push origin main") == ActionRisk.EXTERNAL_SEND
        assert classify_action("deploy to production") == ActionRisk.EXTERNAL_SEND

    def test_financial_commands(self):
        assert classify_action("buy 0.1 ETH") == ActionRisk.FINANCIAL
        assert classify_action("place order sell BTC") == ActionRisk.FINANCIAL
        assert classify_action("transfer $500") == ActionRisk.FINANCIAL
        assert classify_action("swap USDC for ETH") == ActionRisk.FINANCIAL

    def test_destructive_commands(self):
        assert classify_action("rm -rf /tmp/data") == ActionRisk.DESTRUCTIVE
        assert classify_action("launchctl bootout gui/501/com.sapphire.proxy") == ActionRisk.DESTRUCTIVE
        assert classify_action("kill -9 12345") == ActionRisk.DESTRUCTIVE
        assert classify_action("pkill ollama") == ActionRisk.DESTRUCTIVE

    def test_destructive_beats_financial(self):
        """Destructive patterns take priority over financial."""
        assert classify_action("delete all trade history") == ActionRisk.DESTRUCTIVE

    def test_target_included_in_matching(self):
        assert classify_action("service stop", target="ollama") == ActionRisk.SYSTEM_MODIFY
        assert classify_action("systemctl stop", target="ollama") == ActionRisk.SYSTEM_MODIFY

    def test_unknown_defaults_to_read_only(self):
        assert classify_action("frobulate the widget") == ActionRisk.READ_ONLY


# ─── Auto-Approval Tests ──────────────────────────────────────────────────────

class TestAutoApproval:
    def test_read_only_auto_approved(self, fw):
        approved = fw.request_confirmation("cat file.txt", ActionRisk.READ_ONLY)
        assert approved is True

    def test_self_modify_auto_approved(self, fw):
        approved = fw.request_confirmation("append log entry", ActionRisk.SELF_MODIFY)
        assert approved is True

    def test_system_modify_requires_confirmation(self, fw):
        """Without Telegram and with instant timeout, should deny."""
        # Use tiny poll_interval + instantly deny the confirmation
        mock_send = MagicMock(return_value=False)

        def instant_deny(*_, **__):
            # deny immediately via pending file
            pass

        # Override poll to immediately return "denied"
        with patch("confirmation_firewall._poll_pending", return_value="denied"):
            approved = fw.request_confirmation(
                "restart proxy", ActionRisk.SYSTEM_MODIFY, "restart inference proxy",
                _send_fn=mock_send, poll_interval=0.01,
            )
        assert approved is False
        mock_send.assert_called_once()

    def test_system_modify_approved_when_confirmed(self, fw, tmp_path):
        mock_send = MagicMock(return_value=True)
        responses = ["pending", "pending", "approved"]
        response_iter = iter(responses)

        with patch("confirmation_firewall._poll_pending", side_effect=lambda _: next(response_iter)):
            with patch("time.sleep"):
                approved = fw.request_confirmation(
                    "restart proxy", ActionRisk.SYSTEM_MODIFY, "restart inference proxy",
                    _send_fn=mock_send, poll_interval=0.01,
                )
        assert approved is True


# ─── Financial Limit Tests ────────────────────────────────────────────────────

class TestFinancialLimits:
    def test_under_daily_limit_auto_approved(self, fw, tmp_path):
        # Start with $0 spent
        approved = fw.request_confirmation(
            "buy ETH", ActionRisk.FINANCIAL, "buy 0.01 ETH", amount=50.0,
        )
        assert approved is True

    def test_spend_tracked(self, fw, tmp_path):
        fw.request_confirmation("buy ETH", ActionRisk.FINANCIAL, "buy", amount=30.0)
        fw.request_confirmation("buy BTC", ActionRisk.FINANCIAL, "buy", amount=40.0)
        spent = _load_daily_spend()
        assert spent == pytest.approx(70.0)

    def test_over_daily_limit_requires_confirmation(self, fw):
        _record_spend(90.0)  # pre-spend $90
        mock_send = MagicMock(return_value=False)
        with patch("confirmation_firewall._poll_pending", return_value="denied"):
            approved = fw.request_confirmation(
                "buy ETH", ActionRisk.FINANCIAL, "buy 0.1 ETH", amount=50.0,
                _send_fn=mock_send, poll_interval=0.01,
            )
        assert approved is False
        mock_send.assert_called_once()

    def test_exactly_at_limit_still_approved(self, fw):
        _record_spend(50.0)
        approved = fw.request_confirmation(
            "buy", ActionRisk.FINANCIAL, "buy", amount=50.0,
        )
        assert approved is True


# ─── Destructive Delay Tests ──────────────────────────────────────────────────

class TestDestructiveDelay:
    def test_destructive_enforces_30s_delay(self, fw):
        mock_send = MagicMock(return_value=True)
        slept = []

        def fake_sleep(n):
            slept.append(n)

        with patch("confirmation_firewall._poll_pending", return_value="approved"):
            approved = fw.request_confirmation(
                "rm -rf /tmp/test", ActionRisk.DESTRUCTIVE, "delete temp data",
                _send_fn=mock_send, poll_interval=0.01, _sleep_fn=fake_sleep,
            )
        assert approved is True
        # The 30s delay must appear in slept calls
        assert any(n >= 30 for n in slept), f"No 30s delay found in sleep calls: {slept}"

    def test_destructive_denied_no_delay(self, fw):
        mock_send = MagicMock(return_value=True)
        slept = []

        with patch("confirmation_firewall._poll_pending", return_value="denied"):
            approved = fw.request_confirmation(
                "rm -rf /tmp/test", ActionRisk.DESTRUCTIVE, "delete data",
                _send_fn=mock_send, poll_interval=0.01, _sleep_fn=lambda n: slept.append(n),
            )
        assert approved is False
        assert not any(n >= 30 for n in slept)


# ─── Pending Store Tests ──────────────────────────────────────────────────────

class TestPendingStore:
    def test_write_and_approve(self, tmp_path, monkeypatch):
        monkeypatch.setattr("confirmation_firewall.PENDING_DIR", tmp_path)
        code = "TESTCODE"
        _write_pending(code, "restart", ActionRisk.SYSTEM_MODIFY, "details")
        assert (tmp_path / f"{code}.json").exists()
        result = _approve_pending(code)
        assert result is True
        # File is cleaned up on next poll
        status = _poll_pending(code)
        assert status == "approved"

    def test_write_and_deny(self, tmp_path, monkeypatch):
        monkeypatch.setattr("confirmation_firewall.PENDING_DIR", tmp_path)
        code = "DENYCODE"
        _write_pending(code, "rm -rf", ActionRisk.DESTRUCTIVE, "bad action")
        _deny_pending(code)
        status = _poll_pending(code)
        assert status == "denied"

    def test_expired_returns_denied(self, tmp_path, monkeypatch):
        monkeypatch.setattr("confirmation_firewall.PENDING_DIR", tmp_path)
        code = "EXPCODE"
        _write_pending(code, "action", ActionRisk.SYSTEM_MODIFY, "detail")
        # Manually expire
        path = tmp_path / f"{code}.json"
        data = json.loads(path.read_text())
        data["expires"] = time.time() - 1
        path.write_text(json.dumps(data))
        status = _poll_pending(code)
        assert status == "denied"
        assert not path.exists()

    def test_list_pending(self, fw, tmp_path, monkeypatch):
        monkeypatch.setattr("confirmation_firewall.PENDING_DIR", tmp_path)
        _write_pending("AAA", "action 1", ActionRisk.SYSTEM_MODIFY, "d1")
        _write_pending("BBB", "action 2", ActionRisk.EXTERNAL_SEND, "d2")
        pending = fw.list_pending()
        assert len(pending) == 2
        codes = {p["code"] for p in pending}
        assert codes == {"AAA", "BBB"}


# ─── Auto-Approve Shortcut ────────────────────────────────────────────────────

class TestAutoApproveShortcut:
    def test_safe_actions_pass(self, fw):
        assert fw.auto_approve("cat log.txt") is True
        assert fw.auto_approve("append log") is True

    def test_risky_actions_fail(self, fw):
        assert fw.auto_approve("restart service") is False
        assert fw.auto_approve("rm -rf data") is False
        assert fw.auto_approve("buy ETH") is False
