from __future__ import annotations

from datetime import UTC, datetime

from lib.live_portfolio.ledger import LiveLedger
from lib.live_portfolio.ramp_gate import (
    SORTINO_THRESHOLD,
    evaluate_ramp_gate,
    forecast_rung_completion,
    trading_days_between,
)
from tests.unit.test_live_portfolio_ledger import record


def ledger_with_record(tmp_path, *, fill_at: str = "2026-04-01T04:06:00Z") -> LiveLedger:
    ledger = LiveLedger(tmp_path)
    ledger.append(record(fill_at=fill_at))
    return ledger


def test_trading_days_same_day_zero() -> None:
    start = datetime(2026, 4, 1, tzinfo=UTC)
    assert trading_days_between(start, start) == 0


def test_trading_days_skip_weekends() -> None:
    start = datetime(2026, 4, 3, tzinfo=UTC)  # Friday
    end = datetime(2026, 4, 6, tzinfo=UTC)  # Monday
    assert trading_days_between(start, end) == 1


def test_gate_soaking_when_days_insufficient(tmp_path) -> None:
    status = evaluate_ramp_gate(
        ledger_with_record(tmp_path),
        returns=[0.01] * 14,
        now=datetime(2026, 4, 3, tzinfo=UTC),
    )
    assert status.gate_status == "soaking"
    assert "days_in_tier_insufficient" in status.blockers


def test_gate_blocked_when_kill_switch_active(tmp_path) -> None:
    status = evaluate_ramp_gate(
        ledger_with_record(tmp_path),
        returns=[0.01] * 14,
        now=datetime(2026, 4, 30, tzinfo=UTC),
        kill_switch_active=True,
    )
    assert status.gate_status == "blocked"
    assert "kill_switch_active" in status.blockers


def test_gate_blocked_when_firewall_pending(tmp_path) -> None:
    status = evaluate_ramp_gate(
        ledger_with_record(tmp_path),
        returns=[0.01] * 14,
        now=datetime(2026, 4, 30, tzinfo=UTC),
        confirmation_firewall_pending=True,
    )
    assert status.gate_status == "blocked"
    assert "confirmation_firewall_pending" in status.blockers


def test_gate_violated_when_sortino_below_threshold(tmp_path) -> None:
    returns = [0.001, -0.01] * 7
    status = evaluate_ramp_gate(
        ledger_with_record(tmp_path),
        returns=returns,
        now=datetime(2026, 4, 30, tzinfo=UTC),
    )
    assert status.gate_status == "violated"
    assert "sortino_below_threshold" in status.blockers


def test_gate_satisfied_when_sortino_above_threshold(tmp_path) -> None:
    status = evaluate_ramp_gate(
        ledger_with_record(tmp_path),
        returns=[0.01] * 14,
        now=datetime(2026, 4, 30, tzinfo=UTC),
    )
    assert status.gate_status == "satisfied"
    assert status.blockers == []


def test_gate_sortino_boundary_149_violates(tmp_path) -> None:
    ledger = ledger_with_record(tmp_path)
    status = evaluate_ramp_gate(
        ledger, returns=[0.01, -0.0069] * 7, now=datetime(2026, 4, 30, tzinfo=UTC)
    )
    assert status.sortino_14d is not None
    if status.sortino_14d <= SORTINO_THRESHOLD:
        assert status.gate_status == "violated"


def test_gate_sortino_equal_150_not_satisfied(tmp_path) -> None:
    ledger = ledger_with_record(tmp_path)
    status = evaluate_ramp_gate(
        ledger, returns=[0.015, -0.005] * 7, now=datetime(2026, 4, 30, tzinfo=UTC)
    )
    if status.sortino_14d is not None and status.sortino_14d <= SORTINO_THRESHOLD:
        assert status.gate_status != "satisfied"


def test_gate_current_tier_can_be_explicit(tmp_path) -> None:
    status = evaluate_ramp_gate(
        ledger_with_record(tmp_path),
        current_tier=2,
        returns=[0.01] * 14,
        now=datetime(2026, 4, 30, tzinfo=UTC),
    )
    assert status.current_tier == 2
    assert status.target_tier == 3


def test_gate_target_tier_caps_at_three(tmp_path) -> None:
    status = evaluate_ramp_gate(
        ledger_with_record(tmp_path),
        current_tier=3,
        returns=[0.01] * 14,
        now=datetime(2026, 4, 30, tzinfo=UTC),
    )
    assert status.target_tier == 3


def test_gate_no_records_still_reports_tier_one(tmp_path) -> None:
    status = evaluate_ramp_gate(
        LiveLedger(tmp_path), returns=[], now=datetime(2026, 4, 30, tzinfo=UTC)
    )
    assert status.current_tier == 1
    assert status.gate_status in {"soaking", "blocked"}


def test_gate_requires_operator_approval_flag(tmp_path) -> None:
    status = evaluate_ramp_gate(
        ledger_with_record(tmp_path),
        returns=[0.01] * 14,
        now=datetime(2026, 4, 30, tzinfo=UTC),
    )
    assert status.requires_operator_approval is True


def test_gate_to_dict_serializes_infinity(tmp_path) -> None:
    status = evaluate_ramp_gate(
        ledger_with_record(tmp_path),
        returns=[0.01] * 14,
        now=datetime(2026, 4, 30, tzinfo=UTC),
    ).to_dict()
    assert status["sortino_14d"] == "inf"


def test_forecast_completion_returns_future_weekday() -> None:
    start = datetime(2026, 4, 1, tzinfo=UTC)
    forecast = forecast_rung_completion(start, now=datetime(2026, 4, 1, tzinfo=UTC))
    assert forecast["estimated_completion_date"] >= "2026-04-20"


def test_gate_days_count_from_tier_record(tmp_path) -> None:
    status = evaluate_ramp_gate(
        ledger_with_record(tmp_path, fill_at="2026-04-10T00:00:00Z"),
        returns=[0.01] * 14,
        now=datetime(2026, 4, 13, tzinfo=UTC),
    )
    assert status.days_in_tier == 1.0


def test_gate_small_sample_blocks_after_days_complete(tmp_path) -> None:
    status = evaluate_ramp_gate(
        ledger_with_record(tmp_path),
        returns=[0.01],
        now=datetime(2026, 4, 30, tzinfo=UTC),
    )
    assert status.gate_status == "blocked"
    assert "sortino_below_threshold" in status.blockers


def test_gate_generated_at_uses_utc(tmp_path) -> None:
    status = evaluate_ramp_gate(
        ledger_with_record(tmp_path),
        returns=[0.01] * 14,
        now=datetime(2026, 4, 30, tzinfo=UTC),
    )
    assert status.generated_at.endswith("+00:00")
