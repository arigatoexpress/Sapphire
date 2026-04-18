"""Unit tests — lib.analytics.backtest."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lib.analytics.backtest import (
    BacktestConfig,
    Backtester,
    Trade,
    _apply_enhancement,
    _atr,
    _classify_regime,
    _generate_signals,
    _metrics,
    _score_signal,
    _simulate,
    _sma,
)


def _synthetic_bars(n: int = 120, start: float = 100.0, trend: float = 0.5) -> list[dict]:
    """Deterministic uptrending bars with ±1% noise — no network."""
    bars = []
    price = start
    for i in range(n):
        price += trend + (0.5 if i % 3 == 0 else -0.3)
        high = price * 1.01
        low = price * 0.99
        bars.append({
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "open": price * 0.999,
            "high": high,
            "low":  low,
            "close": price,
            "volume": 1_000_000,
        })
    return bars


class TestSMA:
    def test_sma_basic(self):
        out = _sma([1, 2, 3, 4, 5], 3)
        assert out[:2] == [None, None]
        assert out[2] == pytest.approx(2.0)
        assert out[3] == pytest.approx(3.0)
        assert out[4] == pytest.approx(4.0)

    def test_sma_insufficient_data(self):
        assert _sma([1, 2], 5) == [None, None]

    def test_sma_window_zero(self):
        # Guard: window <= 0 returns all Nones without raising.
        assert _sma([1, 2, 3], 0) == [None, None, None]


class TestATR:
    def test_atr_produces_positive_values(self):
        bars = _synthetic_bars(40)
        atr = _atr(bars, 14)
        assert atr[:13] == [None] * 13
        assert atr[13] is not None
        assert atr[13] > 0
        for v in atr[14:]:
            assert v > 0


class TestRegimeClassifier:
    def test_trend_up_detection(self):
        # Strong monotonic uptrend → TREND_UP
        closes = [100 + i for i in range(60)]
        regime, score = _classify_regime(closes, 59)
        assert regime == "TREND_UP"
        assert score > 0

    def test_trend_down_detection(self):
        closes = [200 - i for i in range(60)]
        regime, score = _classify_regime(closes, 59)
        assert regime == "TREND_DOWN"
        assert score < 0

    def test_range_for_flat_series(self):
        closes = [100.0] * 60
        regime, _ = _classify_regime(closes, 59)
        assert regime == "RANGE"

    def test_unknown_when_insufficient_history(self):
        regime, score = _classify_regime([100] * 20, 19)
        assert regime == "UNKNOWN"
        assert score == 0.0


class TestEnhancement:
    def test_aligned_boosts_confidence(self):
        adj, flags = _apply_enhancement("long", 0.50, "TREND_UP", 0.5)
        assert adj > 0.50
        assert any("aligned" in f for f in flags)

    def test_opposed_cuts_confidence(self):
        adj, flags = _apply_enhancement("short", 0.60, "TREND_UP", 0.5)
        assert adj < 0.60
        assert any("opposed" in f for f in flags)

    def test_volatile_reduces_confidence(self):
        adj, flags = _apply_enhancement("long", 0.70, "VOLATILE", 0.0)
        assert adj < 0.70
        assert flags == ["regime_volatile"]

    def test_range_is_neutral(self):
        adj, flags = _apply_enhancement("long", 0.60, "RANGE", 0.0)
        assert adj == 0.60
        assert flags == []

    def test_confidence_clamped(self):
        adj, _ = _apply_enhancement("long", 0.95, "TREND_UP", 1.0)
        assert 0.0 <= adj <= 1.0


class TestScoring:
    def test_score_mirrors_pipeline_formula(self):
        # confidence .75 × 40 + 25 (kernel) + 1.67×7 rr + 15 pos = 30 + 25 + 11.69 + 15 ≈ 81.7
        score = _score_signal(0.75, 1.67, 0.10, kernel_ok=True)
        assert 80.0 <= score <= 82.5

    def test_kernel_blocked_reduces_score(self):
        ok = _score_signal(0.75, 1.67, 0.10, kernel_ok=True)
        blocked = _score_signal(0.75, 1.67, 0.10, kernel_ok=False)
        assert blocked == ok - 25

    def test_score_in_range(self):
        # Out-of-range confidence must not produce > 100 composite.
        assert _score_signal(2.0, 5.0, 0.5) <= 100
        assert _score_signal(-1.0, 0.0, 0.0) >= 0


class TestSignalGeneration:
    def test_signals_have_required_fields(self):
        bars = _synthetic_bars(120)
        cfg = BacktestConfig(sma_fast=5, sma_slow=20)
        signals = _generate_signals(bars, cfg)
        for s in signals:
            assert {"idx", "date", "price", "direction", "confidence", "atr"} <= s.keys()
            assert s["direction"] in {"long", "short"}
            assert 0.0 <= s["confidence"] <= 1.0


class TestSimulation:
    def test_simulate_returns_trades_and_curve(self):
        bars = _synthetic_bars(150)
        cfg = BacktestConfig(sma_fast=5, sma_slow=20)
        signals = _generate_signals(bars, cfg)
        for s in signals:
            s["symbol"] = "SYN"
        trades, curve = _simulate(bars, signals, cfg, with_regime=False)
        assert len(curve) == len(bars)
        # Equity curve is monotone between trades — never NaN
        for v in curve:
            assert math.isfinite(v)
            assert v > 0
        # All closed trades have valid fields
        for t in trades:
            assert isinstance(t, Trade)
            assert t.exit_reason in {"tp", "sl", "cross", "eod"}
            assert t.bars_held >= 0

    def test_regime_changes_trade_count(self):
        """WITH-regime filtering can skip low-confidence entries → trade count ≠ without."""
        bars = _synthetic_bars(150, trend=-0.3)  # downtrend
        cfg = BacktestConfig(sma_fast=5, sma_slow=20, medium_conf_threshold=0.4)
        signals = _generate_signals(bars, cfg)
        for s in signals:
            s["symbol"] = "SYN"
        t_off, _ = _simulate(bars, signals, cfg, with_regime=False)
        t_on, _  = _simulate(bars, signals, cfg, with_regime=True)
        # Same signal input; regime filter may reduce entries.
        assert len(t_on) <= len(t_off)


class TestMetrics:
    def test_metrics_empty_trades(self):
        m = _metrics([100_000, 100_000], [], 100_000)
        assert m["win_rate"] == 0.0
        assert m["profit_factor"] == 0.0
        assert m["max_drawdown"] == 0.0

    def test_metrics_winning_sequence(self):
        curve = [100_000, 101_000, 102_000, 103_000]
        trades = [
            Trade("X", "long", "d1", 100, "d2", 110, 10.0, 10.0, 1, 80, 0.7, "TREND_UP", "tp"),
            Trade("X", "long", "d3", 100, "d4", 105,  5.0,  5.0, 1, 70, 0.6, "TREND_UP", "tp"),
        ]
        m = _metrics(curve, trades, 100_000)
        assert m["win_rate"] == 1.0
        assert m["profit_factor"] == 999.0  # no losses → infinity sentinel
        assert m["sharpe"] > 0

    def test_drawdown_from_decline(self):
        curve = [100_000, 110_000, 90_000]
        m = _metrics(curve, [], 100_000)
        # peak 110k → trough 90k = ~18.18% drawdown
        assert 0.17 < m["max_drawdown"] < 0.19


class TestBacktester:
    def test_run_symbol_synthetic_via_monkeypatch(self, monkeypatch):
        """End-to-end run with a stubbed loader — no network."""
        bars = _synthetic_bars(120)

        def fake_load(symbol, days):
            return bars

        monkeypatch.setattr("lib.analytics.backtest._load_ohlcv", fake_load)
        cfg = BacktestConfig(symbols=("SYN",), period_days=90, sma_fast=5, sma_slow=20)
        bt = Backtester(cfg)
        result = bt.run_symbol("SYN", with_regime=False)
        assert result.symbol == "SYN"
        assert result.bar_count == 120
        assert result.trade_count >= 0
        assert math.isfinite(result.sharpe)
        assert math.isfinite(result.sortino)
        assert 0 <= result.win_rate <= 1
        assert result.max_drawdown_pct >= 0

    def test_run_comparison_produces_delta(self, monkeypatch):
        bars = _synthetic_bars(150)

        def fake_load(symbol, days):
            return bars

        monkeypatch.setattr("lib.analytics.backtest._load_ohlcv", fake_load)
        cfg = BacktestConfig(symbols=("SYN",), period_days=90, sma_fast=5, sma_slow=20)
        bt = Backtester(cfg)
        results = bt.run_comparison(["SYN"])
        assert "with_regime" in results and "without_regime" in results
        assert "delta" in results
        assert "SYN" in results["delta"]
        d = results["delta"]["SYN"]
        assert "sharpe" in d and "total_return_pct" in d

    def test_save_writes_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "lib.analytics.backtest._load_ohlcv",
            lambda *_args, **_kw: _synthetic_bars(120),
        )
        cfg = BacktestConfig(symbols=("SYN",), period_days=90, output_dir=tmp_path)
        bt = Backtester(cfg)
        results = bt.run_comparison(["SYN"])
        path = bt.save(results)
        assert path.exists()
        assert (tmp_path / "latest.json").exists()


class TestErrors:
    def test_load_raises_when_yfinance_returns_empty(self, monkeypatch):
        import lib.analytics.backtest as bt_mod

        class _EmptyYF:
            @staticmethod
            def download(*_args, **_kwargs):
                class _DF:
                    empty = True
                return _DF()

        monkeypatch.setitem(sys.modules, "yfinance", _EmptyYF)
        with pytest.raises(RuntimeError, match="no data"):
            bt_mod._load_ohlcv("FAKE", 90)
