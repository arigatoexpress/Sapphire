"""
Unit tests — HardRiskKernel.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../services/shared"))

from risk_kernel import HardRiskKernel


class TestHardRiskKernel:
    def test_no_block_when_within_limits(self):
        rk = HardRiskKernel(
            enabled=True,
            hold_seconds=120,
            max_daily_loss_pct=5.0,
            max_intraday_drawdown_pct=5.0,
        )
        event = rk.ingest_equity_snapshot({"equity_estimate": 100.0}, now_ts=1000.0)
        assert event is None
        event = rk.ingest_equity_snapshot({"equity_estimate": 98.0}, now_ts=1010.0)
        assert event is None
        ok, reason = rk.can_open_entry(now_ts=1011.0)
        assert ok is True
        assert reason == ""

    def test_daily_loss_pct_triggers_block(self):
        rk = HardRiskKernel(
            enabled=True,
            hold_seconds=90,
            max_daily_loss_pct=2.0,
            max_intraday_drawdown_pct=10.0,
        )
        assert rk.ingest_equity_snapshot({"equity_estimate": 100.0}, now_ts=2000.0) is None
        event = rk.ingest_equity_snapshot({"equity_estimate": 97.8}, now_ts=2010.0)
        assert event is not None
        assert "daily_loss_pct" in event.reason
        ok, reason = rk.can_open_entry(now_ts=2015.0)
        assert ok is False
        assert "risk_kernel_hold" in reason

    def test_hold_expires_and_reopens_entries(self):
        rk = HardRiskKernel(enabled=True, hold_seconds=30, max_daily_loss_pct=1.0)
        rk.ingest_equity_snapshot({"equity_estimate": 100.0}, now_ts=3000.0)
        rk.ingest_equity_snapshot({"equity_estimate": 98.5}, now_ts=3005.0)
        ok, _ = rk.can_open_entry(now_ts=3010.0)
        assert ok is False
        ok, reason = rk.can_open_entry(now_ts=3070.0)
        assert ok is True
        assert reason == ""

    def test_consecutive_hard_fails_trigger(self):
        rk = HardRiskKernel(
            enabled=True,
            hold_seconds=120,
            max_consecutive_hard_fails=3,
            max_daily_loss_pct=0.0,
            max_intraday_drawdown_pct=0.0,
        )
        assert rk.record_execution_outcome(outcome="hard_failed", now_ts=4000.0) is None
        assert rk.record_execution_outcome(outcome="hard_failed", now_ts=4010.0) is None
        event = rk.record_execution_outcome(outcome="hard_failed", now_ts=4020.0)
        assert event is not None
        assert "consecutive_hard_fails" in event.reason

    def test_consecutive_loss_events_trigger(self):
        rk = HardRiskKernel(
            enabled=True,
            hold_seconds=120,
            max_consecutive_loss_events=2,
            max_daily_loss_pct=0.0,
            max_intraday_drawdown_pct=0.0,
            loss_event_min_delta_usd=0.10,
        )
        rk.record_execution_outcome(outcome="filled_success", equity_estimate=100.0, now_ts=5000.0)
        assert (
            rk.record_execution_outcome(
                outcome="filled_success",
                equity_estimate=99.7,
                now_ts=5010.0,
            )
            is None
        )
        event = rk.record_execution_outcome(
            outcome="filled_success",
            equity_estimate=99.4,
            now_ts=5020.0,
        )
        assert event is not None
        assert "consecutive_loss_events" in event.reason

    def test_day_rollover_resets_streaks(self):
        rk = HardRiskKernel(enabled=True, max_consecutive_hard_fails=2)
        rk.record_execution_outcome(outcome="hard_failed", now_ts=6000.0)
        rk.record_execution_outcome(outcome="hard_failed", now_ts=6010.0)
        status_before = rk.status(now_ts=6011.0)
        assert status_before["consecutive_hard_fails"] >= 2
        # Force day rollover
        rk.current_day = "1970-01-01"
        rk.record_execution_outcome(outcome="accepted_no_fill", now_ts=6012.0)
        status_after = rk.status(now_ts=6013.0)
        assert status_after["consecutive_hard_fails"] == 0
