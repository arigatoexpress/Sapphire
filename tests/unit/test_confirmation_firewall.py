"""Tests for lib/core/confirmation_firewall.py — action classification + budget tracking.

Run: /usr/local/bin/python3 -m pytest tests/unit/test_confirmation_firewall.py -v
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import lib.core.confirmation_firewall as fw_module  # type: ignore
from lib.core.confirmation_firewall import (  # type: ignore
    DAILY_AUTO_LIMIT,
    ActionRisk,
    ConfirmationFirewall,
    _load_daily_spend,
    _record_spend,
    _try_consume_daily_budget,
    classify_action,
)


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Redirect all state paths to tmp_path and disable Redis."""
    state = tmp_path / ".sapphire"
    state.mkdir()
    monkeypatch.setattr(fw_module, "SAPPHIRE_STATE", state)
    monkeypatch.setattr(fw_module, "PENDING_DIR", state / "pending_confirmations")
    monkeypatch.setattr(fw_module, "LIMITS_FILE", state / "financial_limits.json")
    monkeypatch.setenv("SAPPHIRE_NO_REDIS", "1")
    return state


class TestClassifyAction:
    def test_cat_is_read(self):
        assert classify_action("cat /var/log/system.log") == ActionRisk.READ_ONLY

    def test_health_check_is_read(self):
        assert classify_action("health check services") == ActionRisk.READ_ONLY

    def test_curl_get_is_read(self):
        assert classify_action("curl GET http://localhost:8080/health") == ActionRisk.READ_ONLY

    def test_status_is_read(self):
        assert classify_action("status sapphire services") == ActionRisk.READ_ONLY

    def test_rm_rf_is_destructive(self):
        assert classify_action("rm -rf /tmp/data") == ActionRisk.DESTRUCTIVE

    def test_launchctl_bootout_is_destructive(self):
        assert classify_action("launchctl bootout system/com.sapphire") == ActionRisk.DESTRUCTIVE

    def test_pkill_is_destructive(self):
        assert classify_action("pkill -f python3") == ActionRisk.DESTRUCTIVE

    def test_drop_table_is_destructive(self):
        assert classify_action("drop table signals") == ActionRisk.DESTRUCTIVE

    def test_trade_is_financial(self):
        assert classify_action("trade BTC on hyperliquid") == ActionRisk.FINANCIAL

    def test_go_long_is_financial(self):
        assert classify_action("go long on ETH") == ActionRisk.FINANCIAL

    def test_stop_loss_is_financial(self):
        assert classify_action("set stop-loss at 63000") == ActionRisk.FINANCIAL

    def test_place_position_is_financial(self):
        assert classify_action("place position SOL 1x long") == ActionRisk.FINANCIAL

    def test_withdraw_is_financial(self):
        assert classify_action("withdraw funds from account") == ActionRisk.FINANCIAL

    def test_write_log_is_self_modify(self):
        assert classify_action("write log entry for today") == ActionRisk.SELF_MODIFY

    def test_append_log_is_self_modify(self):
        assert classify_action("echo done >> /var/log/app.log") == ActionRisk.SELF_MODIFY

    def test_memory_write_is_self_modify(self):
        assert classify_action("memory write note about BTC") == ActionRisk.SELF_MODIFY

    def test_git_push_is_external(self):
        assert classify_action("git push origin main") == ActionRisk.EXTERNAL_SEND

    def test_post_tweet_is_external(self):
        assert classify_action("post tweet about market") == ActionRisk.EXTERNAL_SEND

    def test_send_message_is_external(self):
        assert classify_action("send message to team") == ActionRisk.EXTERNAL_SEND

    def test_deploy_is_external(self):
        assert classify_action("deploy service to production") == ActionRisk.EXTERNAL_SEND

    def test_restart_is_system(self):
        assert classify_action("restart inference-proxy service") == ActionRisk.SYSTEM_MODIFY

    def test_pip_install_is_system(self):
        assert classify_action("pip install requests") == ActionRisk.SYSTEM_MODIFY

    def test_git_commit_is_system(self):
        assert classify_action("git commit -m fix") == ActionRisk.SYSTEM_MODIFY

    def test_config_write_is_system(self):
        assert classify_action("config write new settings") == ActionRisk.SYSTEM_MODIFY

    def test_destructive_beats_financial(self):
        assert classify_action("rm -rf data and close position") == ActionRisk.DESTRUCTIVE

    def test_financial_beats_external(self):
        assert classify_action("send $500 via transfer") == ActionRisk.FINANCIAL

    def test_unknown_defaults_to_read_only(self):
        assert classify_action("frob the quux") == ActionRisk.READ_ONLY

    def test_target_included_in_classification(self):
        result = classify_action("launchctl kickstart", target="system/com.sapphire")
        assert result == ActionRisk.SYSTEM_MODIFY


class TestDailySpend:
    def test_initial_spend_is_zero(self):
        assert _load_daily_spend() == pytest.approx(0.0)

    def test_record_spend_accumulates(self):
        _record_spend(25.0)
        _record_spend(30.0)
        assert _load_daily_spend() == pytest.approx(55.0)

    def test_spend_resets_on_new_day(self):
        fw_module.LIMITS_FILE.write_text(json.dumps({"date": "2020-01-01", "spent": 99.0}))
        assert _load_daily_spend() == pytest.approx(0.0)

    def test_record_handles_corrupt_file(self):
        fw_module.LIMITS_FILE.write_text("not json")
        _record_spend(10.0)
        assert _load_daily_spend() == pytest.approx(10.0)


class TestTryConsumeBudget:
    def test_first_spend_approved(self):
        approved, total = _try_consume_daily_budget(50.0, DAILY_AUTO_LIMIT)
        assert approved is True
        assert total == pytest.approx(50.0)

    def test_spend_at_limit_denied(self):
        _record_spend(DAILY_AUTO_LIMIT)
        approved, _ = _try_consume_daily_budget(0.01, DAILY_AUTO_LIMIT)
        assert approved is False

    def test_spend_under_limit_approved(self):
        _record_spend(50.0)
        approved, total = _try_consume_daily_budget(40.0, DAILY_AUTO_LIMIT)
        assert approved is True
        assert total == pytest.approx(90.0)

    def test_spend_over_limit_denied(self):
        _record_spend(80.0)
        approved, _ = _try_consume_daily_budget(30.0, DAILY_AUTO_LIMIT)
        assert approved is False

    def test_denied_does_not_record(self):
        _record_spend(DAILY_AUTO_LIMIT)
        _try_consume_daily_budget(10.0, DAILY_AUTO_LIMIT)
        assert _load_daily_spend() == pytest.approx(DAILY_AUTO_LIMIT)


class TestConfirmationAudit:
    def _records(self, path: Path) -> list[dict]:
        return [json.loads(line) for line in path.read_text().splitlines()]

    def test_low_risk_auto_approval_is_audited(self, tmp_path):
        audit_path = tmp_path / "audit.jsonl"
        fw = ConfirmationFirewall(audit_path=audit_path)

        approved = fw.request_confirmation(
            "health check services",
            ActionRisk.READ_ONLY,
            details="safe local read",
        )

        assert approved is True
        records = self._records(audit_path)
        assert records[0]["event_type"] == "confirmation.auto_approved"
        assert records[0]["risk"] == "read_only"
        assert records[0]["details_len"] == len("safe local read")

    def test_audit_path_can_be_disabled(self, tmp_path):
        fw = ConfirmationFirewall(audit_path=False)

        assert fw.request_confirmation("cat status", ActionRisk.READ_ONLY) is True
        assert list(tmp_path.rglob("*.jsonl")) == []

    def test_financial_auto_approval_is_audited(self, tmp_path):
        audit_path = tmp_path / "audit.jsonl"
        fw = ConfirmationFirewall(audit_path=audit_path)

        approved = fw.request_confirmation(
            "paper trade SOL",
            ActionRisk.FINANCIAL,
            amount=25.0,
            details="paper-only sizing note",
        )

        assert approved is True
        record = self._records(audit_path)[0]
        assert record["event_type"] == "confirmation.financial_auto_approved"
        assert record["daily_total"] == pytest.approx(25.0)
        assert record["daily_limit"] == pytest.approx(DAILY_AUTO_LIMIT)

    def test_live_financial_under_limit_requires_explicit_confirmation(self, tmp_path):
        audit_path = tmp_path / "audit.jsonl"
        fw = ConfirmationFirewall(audit_path=audit_path)

        def approve_immediately(code, *_args):
            assert fw.approve_pending(code) is True
            return True

        approved = fw.request_confirmation(
            "buy SOL on mainnet",
            ActionRisk.FINANCIAL,
            amount=25.0,
            details="live exchange order",
            poll_interval=0,
            _send_fn=approve_immediately,
            _sleep_fn=lambda _seconds: None,
        )

        assert approved is True
        records = self._records(audit_path)
        assert records[0]["event_type"] == "confirmation.financial_auto_approval_unavailable"
        assert records[0]["reason"] == "requires_paper_or_dry_run"
        assert [r["event_type"] for r in records] == [
            "confirmation.financial_auto_approval_unavailable",
            "confirmation.pending_created",
            "confirmation.pending_approved",
            "confirmation.approved",
        ]
        assert _load_daily_spend() == pytest.approx(25.0)

    def test_financial_auto_limit_can_be_disabled(self, tmp_path, monkeypatch):
        audit_path = tmp_path / "audit.jsonl"
        monkeypatch.setenv("SAPPHIRE_FIREWALL_DAILY_AUTO_LIMIT", "0")
        fw = ConfirmationFirewall(audit_path=audit_path)

        def approve_immediately(code, *_args):
            assert fw.approve_pending(code) is True
            return True

        approved = fw.request_confirmation(
            "paper trade SOL",
            ActionRisk.FINANCIAL,
            amount=25.0,
            details="paper-only sizing note",
            poll_interval=0,
            _send_fn=approve_immediately,
            _sleep_fn=lambda _seconds: None,
        )

        assert approved is True
        event_types = [r["event_type"] for r in self._records(audit_path)]
        assert event_types == [
            "confirmation.financial_auto_approval_unavailable",
            "confirmation.pending_created",
            "confirmation.pending_approved",
            "confirmation.approved",
        ]
        assert _load_daily_spend() == pytest.approx(25.0)

    def test_audit_redacts_secret_like_action_text(self, tmp_path):
        audit_path = tmp_path / "audit.jsonl"
        fw = ConfirmationFirewall(audit_path=audit_path)

        fw.request_confirmation(
            "send token=abc123 to webhook",
            ActionRisk.READ_ONLY,
        )

        record = self._records(audit_path)[0]
        assert "abc123" not in record["action"]
        assert "token=<redacted>" in record["action"]

    def test_pending_record_redacts_secret_like_fields(self):
        path = fw_module._write_pending(
            "ABC123",
            "post token=sample-token to webhook",
            ActionRisk.EXTERNAL_SEND,
            "token=sample-details-token bearer sample-bearer",
        )

        record = json.loads(path.read_text())
        serialized = json.dumps(record)
        assert "sample-token" not in serialized
        assert "sample-details-token" not in serialized
        assert "sample-bearer" not in serialized
        assert "token=<redacted>" in record["action"]
        assert "token=<redacted>" in record["details"]

    def test_list_pending_prunes_expired_records(self):
        path = fw_module._write_pending(
            "ABC123",
            "paper trade SOL",
            ActionRisk.FINANCIAL,
            "paper-only unit test",
        )
        record = json.loads(path.read_text())
        record["expires"] = time.time() - 1
        path.write_text(json.dumps(record))

        fw = ConfirmationFirewall(audit_path=False)

        assert fw.list_pending() == []
        assert not path.exists()

    def test_telegram_confirmation_payload_redacts_secret_like_fields(self, monkeypatch):
        import urllib.request

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "123")
        captured = {}

        class _Response:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        def fake_urlopen(req, *_, **__):
            captured["payload"] = json.loads(req.data.decode())
            return _Response()

        monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

        assert fw_module._send_confirmation_request(
            "ABC123",
            "post token=sample-token to webhook",
            ActionRisk.EXTERNAL_SEND,
            "token=sample-details-token bearer sample-bearer",
        ) is True

        text = captured["payload"]["text"]
        assert "sample-token" not in text
        assert "sample-details-token" not in text
        assert "sample-bearer" not in text
        assert "token=<redacted>" in text
