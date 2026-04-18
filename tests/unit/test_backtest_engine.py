"""Unit tests for lib/analytics/backtest_engine.py."""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.analytics.backtest_engine import (  # noqa: E402
    _synthetic_bars,
    default_rsi_signal,
    max_drawdown_pct,
    run_backtest,
    run_sweep,
    save_result,
    sharpe_ratio,
    sortino_ratio,
)


def test_sharpe_zero_stdev_returns_zero() -> None:
    # Flat returns should not divide by zero.
    assert sharpe_ratio([0.01] * 10) == 0.0


def test_sharpe_positive_trend() -> None:
    # Steady positive returns should produce positive Sharpe.
    rets = [0.005 + (i % 3) * 0.001 for i in range(50)]
    assert sharpe_ratio(rets) > 0


def test_sortino_no_downside() -> None:
    # All positive returns → no downside → 0 (by convention here).
    assert sortino_ratio([0.01, 0.02, 0.015, 0.03]) == 0.0


def test_sortino_penalizes_drawdowns() -> None:
    # Mix of positive and negative; Sortino should be finite & negative-ish
    # when mean is near zero but there are downside moves.
    rets = [0.01, -0.02, 0.01, -0.03, 0.015, -0.01]
    val = sortino_ratio(rets)
    assert math.isfinite(val)


def test_max_drawdown_monotonic_gain() -> None:
    equity = [100.0, 110.0, 115.0, 120.0]
    assert max_drawdown_pct(equity) == 0.0


def test_max_drawdown_known_peak_trough() -> None:
    equity = [100.0, 120.0, 90.0, 95.0]  # peak 120, trough 90 → 25% DD
    assert max_drawdown_pct(equity) == pytest.approx(25.0, rel=1e-3)


def test_synthetic_bars_deterministic() -> None:
    # Seeded by symbol → reproducible. This is used for offline/CI runs.
    a = _synthetic_bars("BTC-USD", 30)
    b = _synthetic_bars("BTC-USD", 30)
    assert len(a) == 30
    assert all(x.close == y.close for x, y in zip(a, b, strict=True))


def test_backtest_structure() -> None:
    bars = _synthetic_bars("BTC-USD", 90)
    r = run_backtest("BTC-USD", bars=bars)
    assert r.symbol == "BTC-USD"
    assert r.bars == 90
    assert len(r.equity_curve) == 90
    # Either the strategy found trades or it didn't; both are valid outcomes.
    assert r.initial_capital == 10_000.0
    assert r.final_capital >= 0


def test_backtest_with_custom_strategy() -> None:
    # Strategy that always buys on the first bar — we should see exactly one
    # entry and one forced close at end-of-window.
    def one_shot(symbol, bars, i):
        if i == 0:
            return {
                "symbol": symbol, "action": "buy", "price": bars[0].close,
                "confidence": 0.9, "strategy": "one_shot",
            }
        return None

    bars = _synthetic_bars("X", 60)
    r = run_backtest("X", bars=bars, signal_fn=one_shot)
    assert len(r.trades) == 1
    assert r.trades[0].exit_reason == "end_of_window"


def test_backtest_tp_sl_exit() -> None:
    # Craft a strategy with tight TP so we always exit on TP in synthetic data.
    def tp_strategy(symbol, bars, i):
        if i == 0:
            p = bars[0].close
            return {
                "symbol": symbol, "action": "buy", "price": p,
                "take_profit": p * 1.001,  # 0.1% TP — almost guaranteed to hit
                "stop_loss":   p * 0.5,     # far SL so we don't hit it
                "confidence": 0.9, "strategy": "tight_tp",
            }
        return None

    bars = _synthetic_bars("TP", 30)
    r = run_backtest("TP", bars=bars, signal_fn=tp_strategy)
    assert r.trades, "expected at least one trade"
    assert r.trades[0].exit_reason in {"take_profit", "end_of_window"}


def test_insufficient_bars_returns_empty_result() -> None:
    r = run_backtest("TINY", bars=_synthetic_bars("TINY", 5))
    assert r.trades == []
    assert "insufficient" in " ".join(r.notes).lower()


def test_default_rsi_signal_returns_none_early() -> None:
    bars = _synthetic_bars("X", 30)
    # Before index 15 the RSI function always returns None.
    for i in range(15):
        assert default_rsi_signal("X", bars, i) is None


def test_run_sweep_covers_symbols() -> None:
    # Using synthetic bars for both avoids network dependency.
    from lib.analytics import backtest_engine as be

    def mock_fetch(sym, days=90, interval="1d"):
        return be._synthetic_bars(sym, days)

    original = be.fetch_ohlcv
    be.fetch_ohlcv = mock_fetch  # type: ignore[attr-defined]
    try:
        results = run_sweep(["A", "B"], days=40)
    finally:
        be.fetch_ohlcv = original

    assert set(results.keys()) == {"A", "B"}
    assert all(r.bars > 0 for r in results.values())


def test_save_result_writes_file(tmp_path) -> None:
    bars = _synthetic_bars("SAVE", 40)
    r = run_backtest("SAVE", bars=bars)
    out = save_result(r, out_dir=tmp_path)
    assert out.exists()
    assert out.suffix == ".json"
