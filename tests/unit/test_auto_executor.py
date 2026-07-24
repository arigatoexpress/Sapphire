"""Tests for services/alpha/auto_executor.py — exactly-once execution + single-instance lock."""

import json
import os
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.alpha.auto_executor import (  # noqa: E402
    ExecutorConfig,
    SignalRecord,
    _acquire_single_instance_lock,
    _already_executed_ids,
    _paper_trading_enabled,
    _release_single_instance_lock,
    run_once,
)


def _signal(pipeline_id: str = "sig-1") -> SignalRecord:
    return SignalRecord(
        pipeline_id=pipeline_id,
        timestamp="2026-07-16T00:00:00Z",
        symbol="BTC-USD",
        action="buy",
        direction="long",
        strategy="test",
        price=100000.0,
        confidence=0.9,
        score=0.8,
        routing="confirmation_required",
        position_usd=5.0,
        position_pct=1.0,
        kernel_ok=True,
        kernel_reason="ok",
        confirmation_code="ABCD1234",
    )


def _config(tmp_path: Path) -> ExecutorConfig:
    return ExecutorConfig(
        signals_dir=tmp_path / "signals",
        audit_log=tmp_path / "audit.jsonl",
        killswitch_path=tmp_path / "pause",
        daily_loss_file=tmp_path / "loss.json",
    )


class TestAlreadyExecutedIds:
    def test_missing_log_is_empty(self, tmp_path):
        assert _already_executed_ids(tmp_path / "nope.jsonl") == set()

    def test_terminal_verdicts_collected(self, tmp_path):
        log_file = tmp_path / "audit.jsonl"
        rows = [
            {"pipeline_id": "a", "verdict": "PAPER_EXECUTED"},
            {"pipeline_id": "b", "verdict": "SUBMITTED"},
            {"pipeline_id": "c", "verdict": "BLOCKED"},
            {"pipeline_id": "d", "verdict": "BLOCKED_TOKEN_MISMATCH"},
        ]
        log_file.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        assert _already_executed_ids(log_file) == {"a", "b"}

    def test_garbage_lines_skipped(self, tmp_path):
        log_file = tmp_path / "audit.jsonl"
        log_file.write_text('not json\n{"pipeline_id": "a", "verdict": "PAPER_EXECUTED"}\n\n')
        assert _already_executed_ids(log_file) == {"a"}


class TestRunOnceExactlyOnce:
    def _run_pass(self, config, signal):
        with (
            mock.patch(
                "services.alpha.auto_executor._find_confirmation_required_signals",
                return_value=[signal],
            ),
            mock.patch(
                "services.alpha.auto_executor._executor_decisions_for_day",
                return_value={signal.pipeline_id: "APPROVED"},
            ),
            mock.patch(
                "services.alpha.auto_executor._poll_firewall_decisions",
                side_effect=lambda signals, d, decisions: decisions,
            ),
            mock.patch(
                "services.alpha.auto_executor._run_preflight_checks",
                return_value=(True, []),
            ),
        ):
            run_once(config)

    def test_approved_signal_executes_once_across_passes(self, tmp_path):
        config = _config(tmp_path)
        signal = _signal()
        for _ in range(3):
            self._run_pass(config, signal)
        rows = [json.loads(line) for line in config.audit_log.read_text(encoding="utf-8").splitlines()]
        executed = [r for r in rows if r["verdict"] == "PAPER_EXECUTED"]
        assert len(executed) == 1

    def test_killswitch_blocks_everything(self, tmp_path):
        config = _config(tmp_path)
        config.killswitch_path.write_text("paused")
        self._run_pass(config, _signal())
        assert not config.audit_log.exists()


class TestSingleInstanceLock:
    def test_acquire_and_release(self, tmp_path):
        lock = tmp_path / "exec.lock"
        assert _acquire_single_instance_lock(lock) is True
        assert lock.read_text(encoding="utf-8") == str(os.getpid())
        _release_single_instance_lock(lock)
        assert not lock.exists()

    def test_second_acquire_fails_while_holder_alive(self, tmp_path):
        lock = tmp_path / "exec.lock"
        assert _acquire_single_instance_lock(lock) is True
        # Same-pid holder is alive, so a second claim must lose.
        assert _acquire_single_instance_lock(lock) is False
        _release_single_instance_lock(lock)

    def test_stale_lock_from_dead_pid_is_reclaimed(self, tmp_path):
        lock = tmp_path / "exec.lock"
        lock.write_text("999999999")  # certainly-dead pid on macOS/Linux
        assert _acquire_single_instance_lock(lock) is True
        _release_single_instance_lock(lock)

    def test_release_does_not_remove_foreign_lock(self, tmp_path):
        lock = tmp_path / "exec.lock"
        lock.write_text("12345")
        _release_single_instance_lock(lock)
        assert lock.exists()


class TestPaperTradingDefault:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("", True),
            ("1", True),
            ("true", True),
            ("0", False),
            ("false", False),
            ("off", False),
        ],
    )
    def test_default_on_unless_explicitly_disabled(self, value, expected, monkeypatch):
        monkeypatch.setenv("PAPER_TRADING", value)
        assert _paper_trading_enabled() is expected
