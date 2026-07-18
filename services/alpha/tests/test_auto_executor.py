"""Dry-run tests for the autonomous trading executor.

Run:
    python3 -m pytest services/alpha/tests/test_auto_executor.py -q
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Add modules under test to path
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "lib" / "core"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "scripts" / "ops"))

import auto_executor as ae  # type: ignore

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_dirs(tmp_path):
    signals_dir = tmp_path / "signals"
    signals_dir.mkdir()
    audit_log = tmp_path / "auto_executor_orders.jsonl"
    killswitch = tmp_path / "autonomous_trading_pause"
    daily_loss = tmp_path / "daily_loss.json"
    return {
        "signals_dir": signals_dir,
        "audit_log": audit_log,
        "killswitch": killswitch,
        "daily_loss": daily_loss,
    }


@pytest.fixture
def fake_signal_record():
    return {
        "pipeline_id": "abc12345",
        "timestamp": datetime.now(UTC).isoformat(),
        "symbol": "BTC",
        "action": "buy",
        "direction": "long",
        "strategy": "test",
        "price": 65000.0,
        "confidence": 0.85,
        "score": 82.0,
        "routing": "CONFIRMATION_REQUIRED",
        "position_usd": 5.0,
        "position_pct": 0.05,
        "kernel_ok": True,
        "kernel_reason": "",
        "take_profit": 67000.0,
        "stop_loss": 64000.0,
        "rr_ratio": 2.0,
        "confirmation_code": "A1B2C3D4",
    }


@pytest.fixture
def config(tmp_dirs):
    return ae.ExecutorConfig(
        live=False,
        confirm_token="",
        max_notional_usd=10.0,
        daily_loss_limit_usd=20.0,
        poll_interval_seconds=1,
        signals_dir=tmp_dirs["signals_dir"],
        audit_log=tmp_dirs["audit_log"],
        killswitch_path=tmp_dirs["killswitch"],
        daily_loss_file=tmp_dirs["daily_loss"],
        readiness_fn=fake_readiness_fn,
    )


@pytest.fixture
def poll_pending(monkeypatch):
    """Monkey-patch confirmation_firewall._poll_pending for deterministic tests."""
    calls: list[str] = []
    return_values: dict[str, str | None] = {}

    def _fake_poll(code: str) -> str | None:
        calls.append(code)
        return return_values.get(code)

    monkeypatch.setattr(ae, "_poll_pending", _fake_poll)
    monkeypatch.setattr(ae, "_POLL_PENDING_AVAILABLE", True)
    return calls, return_values


# ─── Helpers ──────────────────────────────────────────────────────────────────


def fake_readiness_fn(*, symbol, action, notional_usd, live_read_only, max_spread_bps):
    return {"verdict": "READY_FOR_MANUAL_CONFIRMATION"}


def write_signal(signals_dir: Path, record: dict) -> None:
    path = signals_dir / f"{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


# ─── Unit tests ───────────────────────────────────────────────────────────────


def test_paper_trading_defaults_enabled(monkeypatch):
    monkeypatch.delenv(ae.PAPER_TRADING_ENV, raising=False)
    assert ae._paper_trading_enabled() is True


def test_paper_trading_disabled_explicitly(monkeypatch):
    monkeypatch.setenv(ae.PAPER_TRADING_ENV, "0")
    assert ae._paper_trading_enabled() is False


def test_killswitch_blocks_execution(tmp_dirs, config, fake_signal_record):
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)
    tmp_dirs["killswitch"].touch()

    ae.run_once(config)

    audit = load_jsonl(config.audit_log)
    assert audit == []


def test_no_confirmation_code_skips_signal(tmp_dirs, config, fake_signal_record, poll_pending):
    calls, _ = poll_pending
    fake_signal_record.pop("confirmation_code", None)
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)

    ae.run_once(config)

    assert calls == []
    audit = load_jsonl(config.audit_log)
    assert audit == []


def test_approval_poll_triggers_paper_execution(tmp_dirs, config, fake_signal_record, poll_pending):
    calls, return_values = poll_pending
    return_values["A1B2C3D4"] = "approved"
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)

    ae.run_once(config)

    assert "A1B2C3D4" in calls

    # Signal audit should contain an APPROVED decision
    signal_lines = load_jsonl(
        tmp_dirs["signals_dir"] / f"{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"
    )
    decisions = [r for r in signal_lines if r.get("record_type") == "executor_decision"]
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "APPROVED"
    assert decisions[0]["pipeline_id"] == "abc12345"

    # Executor audit should contain a paper execution
    audit = load_jsonl(config.audit_log)
    assert len(audit) == 1
    assert audit[0]["verdict"] == "PAPER_EXECUTED"
    assert audit[0]["paper_mode"] is True
    assert audit[0]["real_order_submitted"] is False
    assert audit[0]["order_body"]["symbol"] == "BTC-USD"


def test_rejection_poll_skips_execution(tmp_dirs, config, fake_signal_record, poll_pending):
    calls, return_values = poll_pending
    return_values["A1B2C3D4"] = "denied"
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)

    ae.run_once(config)

    assert "A1B2C3D4" in calls

    signal_lines = load_jsonl(
        tmp_dirs["signals_dir"] / f"{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"
    )
    decisions = [r for r in signal_lines if r.get("record_type") == "executor_decision"]
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "REJECTED"

    audit = load_jsonl(config.audit_log)
    assert audit == []


def test_notional_cap_blocks_execution(tmp_dirs, config, fake_signal_record, poll_pending):
    _, return_values = poll_pending
    return_values["A1B2C3D4"] = "approved"
    fake_signal_record["position_usd"] = 100.0
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)

    ae.run_once(config)

    audit = load_jsonl(config.audit_log)
    assert len(audit) == 1
    assert audit[0]["verdict"] == "BLOCKED"
    assert any("notional_cap_exceeded" in b for b in audit[0]["blockers"])


def test_live_mode_requires_env_var(
    tmp_dirs, config, fake_signal_record, monkeypatch, poll_pending
):
    _, return_values = poll_pending
    return_values["A1B2C3D4"] = "approved"
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)

    config.live = True
    config.confirm_token = "AUTO_EXECUTOR_LIVE_BUY_BTC-USD_5.00"
    monkeypatch.delenv(ae.AUTO_EXECUTOR_LIVE_ENV, raising=False)

    rc = ae.main(["--live", "--confirm-token", config.confirm_token, "--one-shot"])
    assert rc == 1


def test_live_mode_requires_confirm_token(tmp_dirs, monkeypatch):
    monkeypatch.setenv(ae.AUTO_EXECUTOR_LIVE_ENV, "1")
    rc = ae.main(["--live", "--one-shot"])
    assert rc == 1


def test_live_mode_with_valid_token_uses_robinhood_submit(
    tmp_dirs, config, fake_signal_record, monkeypatch, poll_pending
):
    _, return_values = poll_pending
    return_values["A1B2C3D4"] = "approved"
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)

    config.live = True
    config.confirm_token = "AUTO_EXECUTOR_LIVE_BUY_BTC-USD_5.00"
    monkeypatch.setenv(ae.AUTO_EXECUTOR_LIVE_ENV, "1")

    fake_submit = MagicMock(
        return_value={
            "client_order_id": "live-order-1",
            "submit_response": {"id": "rh-order-1", "state": "queued"},
        }
    )
    config.robinhood_submit_fn = fake_submit

    ae.run_once(config)

    fake_submit.assert_called_once()
    audit = load_jsonl(config.audit_log)
    assert len(audit) == 1
    assert audit[0]["verdict"] == "SUBMITTED"
    assert audit[0]["paper_mode"] is False
    assert audit[0]["real_order_submitted"] is True


def test_daily_loss_limit_blocks_execution(tmp_dirs, config, fake_signal_record, poll_pending):
    _, return_values = poll_pending
    return_values["A1B2C3D4"] = "approved"
    # Seed daily loss at the limit
    tmp_dirs["daily_loss"].write_text(
        json.dumps({"date": str(__import__("datetime").date.today()), "loss_usd": 25.0})
    )
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)

    ae.run_once(config)

    audit = load_jsonl(config.audit_log)
    assert len(audit) == 1
    assert audit[0]["verdict"] == "BLOCKED"
    assert any("daily_loss_limit_reached" in b for b in audit[0]["blockers"])


# ─── Duplicate-fill regression (the "913x" bug class) ────────────────────────
# An approved signal must execute exactly once no matter how many executor
# passes see it. The audit log is the durable consume ledger; if that dedup
# ever regresses, repeated run_once passes re-fill the same approval
# (observed 2026-07: 913 duplicate paper fills from one approval).


def test_approved_signal_executes_exactly_once_across_repeated_passes(
    tmp_dirs, config, fake_signal_record, poll_pending
):
    _, return_values = poll_pending
    return_values["A1B2C3D4"] = "approved"
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)

    for _ in range(50):  # many polling passes over the same approved signal
        ae.run_once(config)

    audit = load_jsonl(config.audit_log)
    fills = [r for r in audit if r["verdict"] == "PAPER_EXECUTED"]
    assert len(fills) == 1, f"duplicate fills: {len(fills)} (913x bug class)"


def test_dedup_survives_fresh_process_state(
    tmp_dirs, config, fake_signal_record, poll_pending
):
    """Dedup must come from the on-disk audit ledger, not in-memory state —
    a restarted executor (new process) must not re-fill a consumed approval."""
    _, return_values = poll_pending
    return_values["A1B2C3D4"] = "approved"
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)

    ae.run_once(config)
    # Simulate a process restart: re-read everything from disk only.
    executed = ae._already_executed_ids(config.audit_log)
    assert "abc12345" in executed
    ae.run_once(config)

    audit = load_jsonl(config.audit_log)
    fills = [r for r in audit if r["verdict"] == "PAPER_EXECUTED"]
    assert len(fills) == 1
