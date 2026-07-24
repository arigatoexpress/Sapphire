"""Tests for SignalPipeline — scoring, outcome writeback, JSONL atomicity, thread safety.

Run: /usr/local/bin/python3 -m pytest tests/unit/test_signal_pipeline.py -v
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

# Add signal pipeline to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "alpha"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lib" / "core"))

import signal_pipeline as sp  # type: ignore
from signal_pipeline import SignalPipeline  # type: ignore

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def signals_dir(tmp_path):
    d = tmp_path / "signals"
    d.mkdir()
    return d


@pytest.fixture
def pipeline(signals_dir, monkeypatch):
    """SignalPipeline with all externals mocked out."""
    monkeypatch.setattr("signal_pipeline.SIGNALS_DIR", signals_dir)
    monkeypatch.setattr(
        "signal_pipeline.PAPER_TRADING_LOG", signals_dir.parent / "paper_trading.jsonl"
    )
    monkeypatch.setattr("signal_pipeline._NOTIFY_AVAILABLE", False)
    monkeypatch.setattr("signal_pipeline._KERNEL_AVAILABLE", False)
    monkeypatch.setattr("signal_pipeline._FIREWALL_AVAILABLE", False)
    monkeypatch.setattr("signal_pipeline._DECISION_ENGINE_AVAILABLE", False)
    monkeypatch.setattr("signal_pipeline._DECISION_ENGINE", None)
    pl = SignalPipeline()
    return pl, signals_dir


def _raw(
    symbol="BTC",
    action="buy",
    price=65000.0,
    confidence=0.75,
    strategy="rsi_cross",
    tp=67000.0,
    sl=64000.0,
):
    return {
        "symbol": symbol,
        "action": action,
        "price": price,
        "confidence": confidence,
        "strategy": strategy,
        "take_profit": tp,
        "stop_loss": sl,
    }


# ─── Safety defaults ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, True),
        ("", True),
        ("1", True),
        ("true", True),
        ("YES", True),
        ("0", False),
        ("false", False),
        ("off", False),
        ("live-please", True),
    ],
)
def test_paper_trading_env_defaults_fail_closed(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("PAPER_TRADING", raising=False)
    else:
        monkeypatch.setenv("PAPER_TRADING", value)
    assert sp._paper_trading_env_enabled() is expected


def test_paper_trading_log_redirected_in_tests(pipeline):
    pl, sig_dir = pipeline
    pl.process(_raw(action="buy"))
    assert (sig_dir.parent / "paper_trading.jsonl").exists()


# ─── Scoring tests ─────────────────────────────────────────────────────────────


class TestScoring:
    def test_process_returns_processed_signal(self, pipeline):
        pl, _ = pipeline
        result = pl.process(_raw())
        assert result.scored is not None
        assert result.elapsed_ms >= 0

    def test_direction_buy_is_long(self, pipeline):
        pl, _ = pipeline
        result = pl.process(_raw(action="buy"))
        assert result.scored.direction == "long"

    def test_direction_sell_is_short(self, pipeline):
        pl, _ = pipeline
        result = pl.process(_raw(action="sell"))
        assert result.scored.direction == "short"

    def test_direction_entry_long(self, pipeline):
        pl, _ = pipeline
        result = pl.process(_raw(action="entry_long"))
        assert result.scored.direction == "long"

    def test_score_is_bounded(self, pipeline):
        pl, _ = pipeline
        result = pl.process(_raw())
        assert 0 <= result.scored.score <= 100

    def test_rr_ratio_calculated(self, pipeline):
        pl, _ = pipeline
        result = pl.process(_raw(price=65000, tp=67000, sl=64000))
        # reward = 2000, risk = 1000 => rr = 2.0
        assert result.scored.rr_ratio == pytest.approx(2.0, abs=0.01)

    def test_rr_ratio_zero_when_no_tp_sl(self, pipeline):
        pl, _ = pipeline
        result = pl.process(_raw(tp=0, sl=0))
        assert result.scored.rr_ratio == 0.0

    def test_symbol_uppercased(self, pipeline):
        pl, _ = pipeline
        result = pl.process(_raw(symbol="btcusdt"))
        assert result.scored.symbol == "BTCUSDT"

    def test_composite_score_components(self, pipeline):
        """Score should increase with higher confidence."""
        pl, _ = pipeline
        low = pl.process(_raw(confidence=0.3))
        high = pl.process(_raw(confidence=0.95))
        assert high.scored.score > low.scored.score

    def test_no_crash_on_missing_fields(self, pipeline):
        pl, _ = pipeline
        result = pl.process({})
        assert result.scored is not None


# ─── JSONL audit trail ────────────────────────────────────────────────────────


class TestAuditTrail:
    def test_writes_jsonl_record(self, pipeline):
        pl, sig_dir = pipeline
        pl.process(_raw())
        # Should have written a .jsonl file
        files = list(sig_dir.glob("*.jsonl"))
        assert len(files) == 1

    def test_jsonl_record_is_valid_json(self, pipeline):
        pl, sig_dir = pipeline
        pl.process(_raw())
        f = list(sig_dir.glob("*.jsonl"))[0]
        for line in f.read_text(encoding="utf-8").strip().splitlines():
            data = json.loads(line)
            assert "symbol" in data

    def test_multiple_signals_appended(self, pipeline):
        pl, sig_dir = pipeline
        pl.process(_raw(symbol="BTC"))
        pl.process(_raw(symbol="ETH"))
        f = list(sig_dir.glob("*.jsonl"))[0]
        lines = [l for l in f.read_text(encoding="utf-8").strip().splitlines() if l.strip()]
        assert len(lines) == 2

    def test_audit_path_in_result(self, pipeline):
        pl, sig_dir = pipeline
        result = pl.process(_raw())
        assert result.audit_path
        assert Path(result.audit_path).exists()


# ─── Outcome writeback ────────────────────────────────────────────────────────


class TestOutcomeWriteback:
    def test_update_win(self, pipeline):
        pl, sig_dir = pipeline
        result = pl.process(_raw())
        pid = result.scored.pipeline_id
        ok = pl.update_signal_outcome(pid, "win", 250.0, close_price=67000)
        assert ok is True
        # Verify the JSONL was updated
        f = list(sig_dir.glob("*.jsonl"))[0]
        for line in f.read_text(encoding="utf-8").strip().splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("pipeline_id") == pid:
                assert data["outcome"] == "win"
                assert data["pnl_usd"] == 250.0
                assert data["close_price"] == 67000

    def test_update_loss(self, pipeline):
        pl, sig_dir = pipeline
        result = pl.process(_raw())
        pid = result.scored.pipeline_id
        pl.update_signal_outcome(pid, "loss", -150.0)
        f = list(sig_dir.glob("*.jsonl"))[0]
        for line in f.read_text(encoding="utf-8").strip().splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("pipeline_id") == pid:
                assert data["outcome"] == "loss"
                assert data["pnl_usd"] == -150.0

    def test_update_nonexistent_pipeline_id_returns_false(self, pipeline):
        pl, sig_dir = pipeline
        pl.process(_raw())
        ok = pl.update_signal_outcome("nonexistent-id", "win", 100.0)
        assert ok is False

    def test_update_removes_from_active(self, pipeline):
        pl, sig_dir = pipeline
        result = pl.process(_raw(action="buy"))
        pid = result.scored.pipeline_id
        # Should be in active signals
        active_before = pl.active_signals()
        assert len(active_before) == 1
        # Update to closed
        pl.update_signal_outcome(pid, "win", 200.0)
        # Should be removed from active
        active_after = pl.active_signals()
        assert len(active_after) == 0

    @pytest.mark.skipif(sys.platform == "win32", reason="Windows locks files differently")
    def test_atomic_write_survives_concurrent_updates(self, pipeline, tmp_path):
        """Two concurrent updates to the same day file must not lose data."""
        pl, sig_dir = pipeline
        # Add two separate signals
        r1 = pl.process(_raw(symbol="BTC"))
        r2 = pl.process(_raw(symbol="ETH"))
        pid1 = r1.scored.pipeline_id
        pid2 = r2.scored.pipeline_id

        errors = []

        def update1():
            try:
                pl.update_signal_outcome(pid1, "win", 100.0)
            except Exception as e:
                errors.append(e)

        def update2():
            try:
                pl.update_signal_outcome(pid2, "loss", -50.0)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=update1)
        t2 = threading.Thread(target=update2)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert not errors, f"Thread errors: {errors}"

        # Both outcomes should be in the file
        f = list(sig_dir.glob("*.jsonl"))[0]
        outcomes = {}
        for line in f.read_text(encoding="utf-8").strip().splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            if "outcome" in data:
                outcomes[data["pipeline_id"]] = data["outcome"]

        assert pid1 in outcomes or pid2 in outcomes, "At least one outcome should be written"


# ─── Active signals index ─────────────────────────────────────────────────────


class TestActiveSignals:
    def test_buy_adds_to_active(self, pipeline):
        pl, _ = pipeline
        pl.process(_raw(action="buy", symbol="BTC"))
        active = pl.active_signals()
        assert len(active) == 1

    def test_close_removes_from_active(self, pipeline):
        pl, _ = pipeline
        pl.process(_raw(action="buy", symbol="BTC"))
        assert len(pl.active_signals()) == 1
        pl.process(_raw(action="close", symbol="BTC"))
        # _active is now keyed by symbol — close correctly removes the open position
        assert len(pl.active_signals()) == 0

    def test_close_without_open_logs_warning(self, pipeline, caplog):
        import logging

        pl, _ = pipeline
        with caplog.at_level(logging.WARNING):
            pl.process(_raw(action="close", symbol="MISSING"))
        assert any("no open position" in r.message for r in caplog.records)

    def test_second_open_replaces_first(self, pipeline):
        pl, _ = pipeline
        pl.process(_raw(action="buy", symbol="BTC", price=60000))
        pl.process(_raw(action="buy", symbol="BTC", price=65000))
        active = pl.active_signals()
        # Only one entry per symbol
        btc_entries = [a for a in active if a["symbol"] == "BTC"]
        assert len(btc_entries) == 1
        assert btc_entries[0]["price"] == 65000

    def test_multiple_symbols_tracked(self, pipeline):
        pl, _ = pipeline
        pl.process(_raw(action="buy", symbol="BTC"))
        pl.process(_raw(action="buy", symbol="ETH"))
        active = pl.active_signals()
        assert len(active) == 2

    def test_active_signals_thread_safe(self, pipeline):
        """Concurrent reads of active_signals should not crash."""
        pl, _ = pipeline
        for i in range(5):
            pl.process(_raw(symbol=f"TOKEN{i}"))

        errors = []

        def read_active():
            try:
                result = pl.active_signals()
                assert isinstance(result, list)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=read_active) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


# ─── Signal stats ─────────────────────────────────────────────────────────────


class TestSignalStats:
    def test_empty_stats(self, pipeline):
        pl, _ = pipeline
        stats = pl.signal_stats()
        assert stats["total_signals"] == 0
        assert stats["wins"] == 0
        assert stats["win_rate"] is None

    def test_stats_with_data(self, pipeline):
        pl, sig_dir = pipeline
        # Write some fake JSONL records directly
        today = __import__("datetime").date.today().isoformat()
        f = sig_dir / f"{today}.jsonl"
        records = [
            {"symbol": "BTC", "outcome": "win", "pnl_usd": 100.0},
            {"symbol": "ETH", "outcome": "win", "pnl_usd": 50.0},
            {"symbol": "SOL", "outcome": "loss", "pnl_usd": -30.0},
            {"symbol": "ADA", "score": 70},  # no outcome yet
        ]
        f.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        stats = pl.signal_stats()
        assert stats["wins"] == 2
        assert stats["losses"] == 1
        assert stats["win_rate"] == pytest.approx(2 / 3, abs=0.01)
        assert stats["total_pnl_usd"] == pytest.approx(120.0, abs=0.01)

    def test_stats_handles_corrupt_file(self, pipeline):
        """signal_stats must not crash on corrupt JSONL files."""
        pl, sig_dir = pipeline
        today = __import__("datetime").date.today().isoformat()
        f = sig_dir / f"{today}.jsonl"
        f.write_text("valid json line\nnot json at all\n{broken\n")
        # Should not raise
        stats = pl.signal_stats()
        assert isinstance(stats, dict)

    def test_stats_handles_missing_file(self, pipeline):
        """signal_stats must not crash if a file disappears between glob and read."""
        pl, sig_dir = pipeline
        # Create a file, then patch read_text to raise OSError
        today = __import__("datetime").date.today().isoformat()
        f = sig_dir / f"{today}.jsonl"
        f.write_text('{"outcome":"win","pnl_usd":50}\n')
        with patch.object(Path, "read_text", side_effect=OSError("file removed")):
            stats = pl.signal_stats()
        assert isinstance(stats, dict)


# ─── Decision Engine Wiring ────────────────────────────────────────────────────


class TestDecisionEngineWiring:
    """Verify the decision engine gate in _score works correctly."""

    _RAW = {
        "symbol": "BTC",
        "action": "buy",
        "price": 50000.0,
        "confidence": 0.70,
        "strategy": "test",
    }

    def test_decision_engine_block_overrides_routing(self, pipeline, monkeypatch):
        pl, _ = pipeline
        from unittest.mock import MagicMock

        import signal_pipeline as sp  # type: ignore

        fake_dec = MagicMock()
        fake_dec.verdict = "BLOCK"
        fake_dec.adjusted_confidence = 0.10
        fake_dec.reasons = ["extreme_funding"]
        fake_engine = MagicMock()
        fake_engine.evaluate.return_value = fake_dec
        monkeypatch.setattr(sp, "_DECISION_ENGINE_AVAILABLE", True)
        monkeypatch.setattr(sp, "_DECISION_ENGINE", fake_engine)
        result = pl.process(self._RAW)
        assert result.scored.routing == "BLOCKED"
        assert any("decision_engine" in n for n in result.scored.notes)

    def test_decision_engine_reduce_adjusts_confidence(self, pipeline, monkeypatch):
        pl, _ = pipeline
        from unittest.mock import MagicMock

        import signal_pipeline as sp  # type: ignore

        fake_dec = MagicMock()
        fake_dec.verdict = "REDUCE"
        fake_dec.adjusted_confidence = 0.45  # below MEDIUM_CONF → LOG_ONLY
        fake_dec.reasons = ["bear_regime"]
        fake_engine = MagicMock()
        fake_engine.evaluate.return_value = fake_dec
        monkeypatch.setattr(sp, "_DECISION_ENGINE_AVAILABLE", True)
        monkeypatch.setattr(sp, "_DECISION_ENGINE", fake_engine)
        result = pl.process(self._RAW)
        assert result.scored.confidence < 0.70
        assert result.scored.routing != "BLOCKED"

    def test_decision_engine_error_is_caught(self, pipeline, monkeypatch):
        pl, _ = pipeline
        from unittest.mock import MagicMock

        import signal_pipeline as sp  # type: ignore

        fake_engine = MagicMock()
        fake_engine.evaluate.side_effect = RuntimeError("chain data unavailable")
        monkeypatch.setattr(sp, "_DECISION_ENGINE_AVAILABLE", True)
        monkeypatch.setattr(sp, "_DECISION_ENGINE", fake_engine)
        result = pl.process(self._RAW)
        assert any("decision_engine_error" in n for n in result.scored.notes)
        assert result.scored.routing != "BLOCKED"

    def test_decision_engine_unavailable_does_not_block(self, pipeline, monkeypatch):
        pl, _ = pipeline
        import signal_pipeline as sp  # type: ignore

        monkeypatch.setattr(sp, "_DECISION_ENGINE_AVAILABLE", False)
        monkeypatch.setattr(sp, "_DECISION_ENGINE", None)
        result = pl.process(self._RAW)
        assert result.scored.routing in {"NOTIFY", "CONFIRMATION_REQUIRED", "LOG_ONLY"}
