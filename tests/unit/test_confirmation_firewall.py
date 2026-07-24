"""Tests for lib/core/confirmation_firewall.py — action classification + budget tracking.

Run: /usr/local/bin/python3 -m pytest tests/unit/test_confirmation_firewall.py -v
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Unix only (fcntl)")

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
    handle_confirmation_reply,
    parse_confirmation_reply,
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
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

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

        record = json.loads(path.read_text(encoding="utf-8"))
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
        record = json.loads(path.read_text(encoding="utf-8"))
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

        assert (
            fw_module._send_confirmation_request(
                "ABC123",
                "post token=sample-token to webhook",
                ActionRisk.EXTERNAL_SEND,
                "token=sample-details-token bearer sample-bearer",
            )
            is True
        )

        text = captured["payload"]["text"]
        assert "sample-token" not in text
        assert "sample-details-token" not in text
        assert "sample-bearer" not in text
        assert "token=<redacted>" in text


class TestConfirmationReplyHandler:
    def _records(self, path: Path) -> list[dict]:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def test_parse_confirmation_reply_accepts_bare_commands(self):
        assert parse_confirmation_reply("CONFIRM ab12cd34") == ("approve", "AB12CD34")
        assert parse_confirmation_reply("/approve AB12CD34") == ("approve", "AB12CD34")
        assert parse_confirmation_reply("deny ab12cd34") == ("deny", "AB12CD34")
        assert parse_confirmation_reply("cancel ab12cd34") == ("deny", "AB12CD34")

    def test_parse_confirmation_reply_ignores_conversation(self):
        assert parse_confirmation_reply("please confirm this later") is None
        assert parse_confirmation_reply("CONFIRM") is None
        assert parse_confirmation_reply("CONFIRM ABC123") is None
        assert parse_confirmation_reply("CONFIRM ABC12345 and do it") is None

    def test_handle_confirmation_reply_approves_pending_code(self, tmp_path):
        audit_path = tmp_path / "audit.jsonl"
        fw = ConfirmationFirewall(audit_path=audit_path)
        path = fw_module._write_pending(
            "ABC12345",
            "paper trade SOL",
            ActionRisk.FINANCIAL,
            "paper-only unit test",
        )

        result = handle_confirmation_reply("CONFIRM abc12345", firewall=fw)

        assert result == {
            "matched": True,
            "action": "approve",
            "code": "ABC12345",
            "ok": True,
            "status": "approved",
        }
        assert json.loads(path.read_text(encoding="utf-8"))["status"] == "approved"
        records = self._records(audit_path)
        assert records[-1]["event_type"] == "confirmation.pending_approved"
        assert records[-1]["status"] == "approved"

    def test_handle_confirmation_reply_denies_pending_code(self, tmp_path):
        audit_path = tmp_path / "audit.jsonl"
        fw = ConfirmationFirewall(audit_path=audit_path)
        path = fw_module._write_pending(
            "ABC12345",
            "paper trade SOL",
            ActionRisk.FINANCIAL,
            "paper-only unit test",
        )

        result = handle_confirmation_reply("DENY abc12345", firewall=fw)

        assert result == {
            "matched": True,
            "action": "deny",
            "code": "ABC12345",
            "ok": True,
            "status": "denied",
        }
        assert json.loads(path.read_text(encoding="utf-8"))["status"] == "denied"
        records = self._records(audit_path)
        assert records[-1]["event_type"] == "confirmation.pending_denied"
        assert records[-1]["status"] == "denied"

    def test_handle_confirmation_reply_reports_missing_code(self, tmp_path):
        audit_path = tmp_path / "audit.jsonl"
        fw = ConfirmationFirewall(audit_path=audit_path)

        result = handle_confirmation_reply("CONFIRM abc12345", firewall=fw)

        assert result == {
            "matched": True,
            "action": "approve",
            "code": "ABC12345",
            "ok": False,
            "status": "not_found_or_expired",
        }
        records = self._records(audit_path)
        assert records[-1]["event_type"] == "confirmation.pending_approved"
        assert records[-1]["status"] == "not_found_or_expired"

    def test_handle_confirmation_reply_ignores_non_reply(self, tmp_path):
        fw = ConfirmationFirewall(audit_path=tmp_path / "audit.jsonl")

        assert handle_confirmation_reply("hello there", firewall=fw) is None


# ---------------------------------------------------------------------------
# Branch coverage additions — 2-phase commit cycle, timeout, destructive
# delay, env-driven overrides, and edge-case state file handling.
# ---------------------------------------------------------------------------


class TestTwoPhaseCommitCycle:
    """The firewall runs a prepare/commit cycle on every gated action.

    prepare:   _write_pending writes the pending JSON
    commit:    approve_pending rewrites status="approved"
    abort:     deny_pending rewrites status="denied"
    timeout:   _poll_pending observes expires<now and unlinks the file
    """

    def test_prepare_then_commit_keeps_record_until_polled(self, tmp_path):
        fw = ConfirmationFirewall(audit_path=tmp_path / "audit.jsonl")
        path = fw_module._write_pending(
            "PREPCOMM",
            "paper trade SOL",
            ActionRisk.FINANCIAL,
            "paper-only unit test",
        )

        assert path.exists()
        assert fw.approve_pending("PREPCOMM") is True
        # commit phase records "approved" — file still on disk until poll consumes it.
        assert json.loads(path.read_text(encoding="utf-8"))["status"] == "approved"
        assert fw_module._poll_pending("PREPCOMM") == "approved"
        assert not path.exists()

    def test_prepare_then_abort_marks_denied_and_clears_on_poll(self, tmp_path):
        fw = ConfirmationFirewall(audit_path=tmp_path / "audit.jsonl")
        path = fw_module._write_pending(
            "PREPABRT",
            "paper trade SOL",
            ActionRisk.FINANCIAL,
            "paper-only unit test",
        )

        assert fw.deny_pending("PREPABRT") is True
        assert json.loads(path.read_text(encoding="utf-8"))["status"] == "denied"
        assert fw_module._poll_pending("PREPABRT") == "denied"
        assert not path.exists()

    def test_prepare_without_commit_times_out(self, tmp_path):
        fw_module._write_pending(
            "TIMEDOUT",
            "paper trade SOL",
            ActionRisk.FINANCIAL,
            "paper-only unit test",
        )
        path = fw_module.PENDING_DIR / "TIMEDOUT.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        record["expires"] = time.time() - 1
        path.write_text(json.dumps(record))

        # Poll past the expiry → returns "denied" by design (fail-closed).
        assert fw_module._poll_pending("TIMEDOUT") == "denied"
        assert not path.exists()

    def test_double_prepare_for_distinct_codes_keeps_both(self):
        fw_module._write_pending("FIRST123", "paper trade BTC", ActionRisk.FINANCIAL, "")
        fw_module._write_pending("SCND4567", "paper trade ETH", ActionRisk.FINANCIAL, "")

        fw = ConfirmationFirewall(audit_path=False)
        codes = {p["code"] for p in fw.list_pending()}
        assert codes == {"FIRST123", "SCND4567"}

    def test_approve_pending_rejects_already_committed_record(self):
        fw_module._write_pending("DBLCOMMT", "trade", ActionRisk.FINANCIAL, "")
        fw = ConfirmationFirewall(audit_path=False)

        assert fw.approve_pending("DBLCOMMT") is True
        # second approve must fail closed — the record is now in a non-pending state.
        assert fw.approve_pending("DBLCOMMT") is False

    def test_deny_pending_rejects_already_committed_record(self):
        fw_module._write_pending("DBLDENY1", "trade", ActionRisk.FINANCIAL, "")
        fw = ConfirmationFirewall(audit_path=False)

        assert fw.approve_pending("DBLDENY1") is True
        # cannot deny something already approved — fail closed.
        assert fw.deny_pending("DBLDENY1") is False

    def test_approve_unknown_code_returns_false(self):
        fw = ConfirmationFirewall(audit_path=False)
        assert fw.approve_pending("NOPENOPE") is False
        assert fw.deny_pending("NOPENOPE") is False

    def test_approve_pending_on_expired_record_fails_closed(self):
        path = fw_module._write_pending("EXPIRED1", "trade", ActionRisk.FINANCIAL, "")
        record = json.loads(path.read_text(encoding="utf-8"))
        record["expires"] = time.time() - 1
        path.write_text(json.dumps(record))

        fw = ConfirmationFirewall(audit_path=False)
        # The expired record must NOT be approved; it is also unlinked so a
        # later replay cannot revive it.
        assert fw.approve_pending("EXPIRED1") is False
        assert not path.exists()


class TestPendingCleanup:
    def test_cleanup_expired_pending_removes_only_stale(self, monkeypatch):
        live = fw_module._write_pending("LIVE1234", "trade", ActionRisk.FINANCIAL, "")
        stale = fw_module._write_pending("STAL1234", "trade", ActionRisk.FINANCIAL, "")
        record = json.loads(stale.read_text(encoding="utf-8"))
        record["expires"] = time.time() - 100
        stale.write_text(json.dumps(record))

        removed = fw_module._cleanup_expired_pending()
        assert removed == 1
        assert live.exists()
        assert not stale.exists()

    def test_cleanup_handles_missing_directory(self, isolated_state):
        # Force the directory away.
        import shutil

        shutil.rmtree(fw_module.PENDING_DIR, ignore_errors=True)
        assert fw_module._cleanup_expired_pending() == 0

    def test_cleanup_skips_corrupt_records(self, monkeypatch):
        fw_module.PENDING_DIR.mkdir(parents=True, exist_ok=True)
        bad = fw_module.PENDING_DIR / "BADJSON1.json"
        bad.write_text("{not json")
        # Must not raise on malformed JSON.
        assert fw_module._cleanup_expired_pending() == 0
        assert bad.exists()  # untouched (no expiry to evaluate)


class TestEnvOverrides:
    def test_live_financial_override_promotes_to_paper_path(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SAPPHIRE_FIREWALL_ALLOW_LIVE_FINANCIAL_AUTO_APPROVAL", "1")
        audit = tmp_path / "audit.jsonl"
        fw = ConfirmationFirewall(audit_path=audit)

        approved = fw.request_confirmation(
            "buy SOL on mainnet",
            ActionRisk.FINANCIAL,
            amount=10.0,
            details="live exchange order",
        )
        assert approved is True
        records = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
        assert records[0]["event_type"] == "confirmation.financial_auto_approved"

    def test_invalid_daily_limit_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("SAPPHIRE_FIREWALL_DAILY_AUTO_LIMIT", "not-a-number")
        assert fw_module._current_daily_auto_limit() == DAILY_AUTO_LIMIT

    def test_blank_daily_limit_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("SAPPHIRE_FIREWALL_DAILY_AUTO_LIMIT", "")
        assert fw_module._current_daily_auto_limit() == DAILY_AUTO_LIMIT

    def test_negative_daily_limit_env_clamped_to_zero(self, monkeypatch):
        monkeypatch.setenv("SAPPHIRE_FIREWALL_DAILY_AUTO_LIMIT", "-50")
        # max(0.0, float(-50)) → 0.0
        assert fw_module._current_daily_auto_limit() == 0.0

    def test_paper_financial_keywords_trigger_auto_path(self):
        # Each paper/sandbox/dry-run keyword should classify as auto-eligible.
        for action in [
            "paper trade ETH",
            "dry-run buy BTC",
            "simulate sell SOL",
            "sandbox trade USD",
            "backtest order BTC",
            "testnet swap ETH",
        ]:
            assert fw_module._is_paper_or_dry_run_financial(action) is True

    def test_audit_path_resolves_from_env(self, monkeypatch, tmp_path):
        env_target = tmp_path / "env-firewall.jsonl"
        monkeypatch.setenv("SAPPHIRE_CONFIRMATION_FIREWALL_AUDIT_LOG", str(env_target))
        fw = ConfirmationFirewall()  # no explicit path
        fw.request_confirmation(
            "health check",
            ActionRisk.READ_ONLY,
            details="all good",
        )
        assert env_target.exists()


class TestRequestConfirmationFlow:
    def test_timeout_returns_false_and_audits_timed_out(self, tmp_path, monkeypatch):
        audit = tmp_path / "audit.jsonl"
        fw = ConfirmationFirewall(audit_path=audit)

        # Drive the deadline past now() so the loop body never executes.
        monkeypatch.setattr(fw_module, "CONFIRMATION_TIMEOUT", 0)
        approved = fw.request_confirmation(
            "post tweet about market",
            ActionRisk.EXTERNAL_SEND,
            details="external send action",
            poll_interval=0,
            _send_fn=lambda *a, **k: True,
            _sleep_fn=lambda _seconds: None,
        )
        assert approved is False
        events = [json.loads(line)["event_type"] for line in audit.read_text(encoding="utf-8").splitlines()]
        assert events[-1] == "confirmation.timed_out"

    def test_destructive_approval_enforces_post_approval_delay(self, tmp_path, monkeypatch):
        audit = tmp_path / "audit.jsonl"
        fw = ConfirmationFirewall(audit_path=audit)
        sleeps: list[float] = []

        def approve_immediately(code, *_args):
            assert fw.approve_pending(code) is True
            return True

        approved = fw.request_confirmation(
            "rm -rf /tmp/data",
            ActionRisk.DESTRUCTIVE,
            details="destructive cleanup",
            poll_interval=0,
            _send_fn=approve_immediately,
            _sleep_fn=lambda seconds: sleeps.append(seconds),
        )
        assert approved is True
        # The poll sleep (0) plus the destructive delay (DESTRUCTIVE_DELAY) must both occur.
        assert fw_module.DESTRUCTIVE_DELAY in sleeps

    def test_denied_request_returns_false_and_audits(self, tmp_path):
        audit = tmp_path / "audit.jsonl"
        fw = ConfirmationFirewall(audit_path=audit)

        def deny_immediately(code, *_args):
            assert fw.deny_pending(code) is True
            return True

        approved = fw.request_confirmation(
            "git push origin main",
            ActionRisk.EXTERNAL_SEND,
            details="external publish",
            poll_interval=0,
            _send_fn=deny_immediately,
            _sleep_fn=lambda _seconds: None,
        )
        assert approved is False
        events = [json.loads(line)["event_type"] for line in audit.read_text(encoding="utf-8").splitlines()]
        assert events[-1] == "confirmation.denied"

    def test_self_modify_auto_approves_without_confirmation(self, tmp_path):
        audit = tmp_path / "audit.jsonl"
        fw = ConfirmationFirewall(audit_path=audit)

        # _send_fn must NOT fire for SELF_MODIFY — fail loudly if it does.
        def fail_send(*_args, **_kwargs):
            raise AssertionError("SELF_MODIFY should auto-approve without sending")

        approved = fw.request_confirmation(
            "write log entry today",
            ActionRisk.SELF_MODIFY,
            details="self-only",
            _send_fn=fail_send,
            _sleep_fn=lambda _seconds: None,
        )
        assert approved is True
        events = [json.loads(line)["event_type"] for line in audit.read_text(encoding="utf-8").splitlines()]
        assert events == ["confirmation.auto_approved"]


class TestAutoApproveHelper:
    def test_auto_approve_passes_safe_actions(self):
        fw = ConfirmationFirewall(audit_path=False)
        assert fw.auto_approve("cat /var/log/system.log") is True
        assert fw.auto_approve("write log note", target="self") is True

    def test_auto_approve_rejects_high_risk_actions(self):
        fw = ConfirmationFirewall(audit_path=False)
        assert fw.auto_approve("rm -rf /tmp/x") is False
        assert fw.auto_approve("buy BTC at market") is False
        assert fw.auto_approve("git push origin main") is False


class TestPendingFileEdgeCases:
    def test_poll_pending_returns_none_on_corrupt_file(self):
        fw_module.PENDING_DIR.mkdir(parents=True, exist_ok=True)
        path = fw_module.PENDING_DIR / "CORRUPT1.json"
        path.write_text("{partial")
        # Per the doc string in _poll_pending: corrupt reads return None,
        # never silently deny — so the action keeps polling.
        assert fw_module._poll_pending("CORRUPT1") is None

    def test_poll_pending_returns_none_for_unknown_code(self):
        assert fw_module._poll_pending("MISSING9") is None

    def test_list_pending_skips_corrupt_files(self):
        fw_module.PENDING_DIR.mkdir(parents=True, exist_ok=True)
        good = fw_module._write_pending("GOODONE1", "paper trade SOL", ActionRisk.FINANCIAL, "")
        bad = fw_module.PENDING_DIR / "BADJSON1.json"
        bad.write_text("{")
        fw = ConfirmationFirewall(audit_path=False)

        codes = [p["code"] for p in fw.list_pending()]
        assert "GOODONE1" in codes
        # Corrupt file is ignored, not crash-loaded.
        assert good.exists()
