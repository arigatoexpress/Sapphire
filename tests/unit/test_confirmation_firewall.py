"""Tests for lib/core/confirmation_firewall.py — action classification + budget tracking.

Run: /usr/local/bin/python3 -m pytest tests/unit/test_confirmation_firewall.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import lib.core.confirmation_firewall as fw_module  # type: ignore
from lib.core.confirmation_firewall import (  # type: ignore
    DAILY_AUTO_LIMIT,
    ActionRisk,
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
