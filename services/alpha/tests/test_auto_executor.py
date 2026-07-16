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
        telegram_api_class=FakeTelegramAPI,
        readiness_fn=fake_readiness_fn,
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────


class FakeTelegramAPI(ae.TelegramAPI):
    """In-memory Telegram API stub that records sent confirmation requests."""

    sent: list[ae.SignalRecord] = []
    callbacks: list[dict] = []

    def __init__(self, token: str = "", chat_id: str = "", timeout_seconds: float = 1.0) -> None:
        super().__init__(token=token, chat_id=chat_id, timeout_seconds=timeout_seconds)

    def send_confirmation_request(self, signal: ae.SignalRecord) -> dict:
        self.sent.append(signal)
        return {"ok": True, "result": {"message_id": 1}}

    def get_callback_updates(self, offset: int = 0) -> list[dict]:
        return list(self.callbacks)

    def answer_callback_query(self, callback_query_id: str) -> None:
        pass

    @classmethod
    def reset(cls) -> None:
        cls.sent.clear()
        cls.callbacks.clear()


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


def test_confirmation_request_sent_for_pending_signal(tmp_dirs, config, fake_signal_record):
    FakeTelegramAPI.reset()
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)

    ae.run_once(config)

    assert len(FakeTelegramAPI.sent) == 1
    assert FakeTelegramAPI.sent[0].pipeline_id == "abc12345"


def test_approval_record_triggers_paper_execution(tmp_dirs, config, fake_signal_record):
    FakeTelegramAPI.reset()
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)

    # Simulate an approval callback
    FakeTelegramAPI.callbacks.append(
        {
            "update_id": 1,
            "callback_query": {
                "id": "cb1",
                "data": "ae:abc12345:approve",
            },
        }
    )

    ae.run_once(config)

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


def test_rejection_record_skips_execution(tmp_dirs, config, fake_signal_record):
    FakeTelegramAPI.reset()
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)

    FakeTelegramAPI.callbacks.append(
        {
            "update_id": 2,
            "callback_query": {
                "id": "cb2",
                "data": "ae:abc12345:reject",
            },
        }
    )

    ae.run_once(config)

    signal_lines = load_jsonl(
        tmp_dirs["signals_dir"] / f"{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"
    )
    decisions = [r for r in signal_lines if r.get("record_type") == "executor_decision"]
    assert len(decisions) == 1
    assert decisions[0]["decision"] == "REJECTED"

    audit = load_jsonl(config.audit_log)
    assert audit == []


def test_notional_cap_blocks_execution(tmp_dirs, config, fake_signal_record):
    FakeTelegramAPI.reset()
    fake_signal_record["position_usd"] = 100.0
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)

    FakeTelegramAPI.callbacks.append(
        {
            "update_id": 3,
            "callback_query": {
                "id": "cb3",
                "data": "ae:abc12345:approve",
            },
        }
    )

    ae.run_once(config)

    audit = load_jsonl(config.audit_log)
    assert len(audit) == 1
    assert audit[0]["verdict"] == "BLOCKED"
    assert any("notional_cap_exceeded" in b for b in audit[0]["blockers"])


def test_live_mode_requires_env_var(tmp_dirs, config, fake_signal_record, monkeypatch):
    FakeTelegramAPI.reset()
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)
    FakeTelegramAPI.callbacks.append(
        {
            "update_id": 4,
            "callback_query": {
                "id": "cb4",
                "data": "ae:abc12345:approve",
            },
        }
    )

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
    tmp_dirs, config, fake_signal_record, monkeypatch
):
    FakeTelegramAPI.reset()
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)
    FakeTelegramAPI.callbacks.append(
        {
            "update_id": 5,
            "callback_query": {
                "id": "cb5",
                "data": "ae:abc12345:approve",
            },
        }
    )

    config.live = True
    config.confirm_token = "AUTO_EXECUTOR_LIVE_BUY_BTC-USD_5.00"
    monkeypatch.setenv(ae.AUTO_EXECUTOR_LIVE_ENV, "1")

    fake_submit = MagicMock(return_value={
        "client_order_id": "live-order-1",
        "submit_response": {"id": "rh-order-1", "state": "queued"},
    })
    config.robinhood_submit_fn = fake_submit

    ae.run_once(config)

    fake_submit.assert_called_once()
    audit = load_jsonl(config.audit_log)
    assert len(audit) == 1
    assert audit[0]["verdict"] == "SUBMITTED"
    assert audit[0]["paper_mode"] is False
    assert audit[0]["real_order_submitted"] is True


def test_daily_loss_limit_blocks_execution(tmp_dirs, config, fake_signal_record):
    FakeTelegramAPI.reset()
    # Seed daily loss at the limit
    tmp_dirs["daily_loss"].write_text(json.dumps({"date": str(__import__("datetime").date.today()), "loss_usd": 25.0}))
    write_signal(tmp_dirs["signals_dir"], fake_signal_record)
    FakeTelegramAPI.callbacks.append(
        {
            "update_id": 6,
            "callback_query": {
                "id": "cb6",
                "data": "ae:abc12345:approve",
            },
        }
    )

    ae.run_once(config)

    audit = load_jsonl(config.audit_log)
    assert len(audit) == 1
    assert audit[0]["verdict"] == "BLOCKED"
    assert any("daily_loss_limit_reached" in b for b in audit[0]["blockers"])
