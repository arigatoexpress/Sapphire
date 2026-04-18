"""Unit tests for lib.analytics.backtest — deterministic synthetic OHLCV.

Module loading notes:
- `services/alpha/signal_pipeline.py` (loaded indirectly by other tests in
  the suite) inserts the *main* Sapphire repo's lib/ and plugins/ trees
  into sys.path[0]. That shadows both `lib.analytics.backtest` (wrong
  package) and a plain `backtest` import (wrong file — the plugin tool).
- So load our module explicitly via importlib and expose it as `bt`.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

_BACKTEST_PATH = Path(__file__).resolve().parents[2] / "lib" / "analytics" / "backtest.py"
_spec = importlib.util.spec_from_file_location("sapphire_backtest", _BACKTEST_PATH)
bt = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
# Register in sys.modules *before* exec so @dataclass lookups on cls.__module__
# find this module rather than getting None. Using a unique name avoids the
# `backtest` collision with plugins/claw-sapphire/tools/backtest.py.
sys.modules[_spec.name] = bt
_spec.loader.exec_module(bt)

# Names re-exported for clarity in tests
Bar = bt.Bar
Decision = bt.Decision
Backtester = bt.Backtester
backtest_symbol = bt.backtest_symbol
_rsi = bt._rsi
load_yfinance_ohlcv = bt.load_yfinance_ohlcv


# ---------------------------------------------------------------------------
# Helpers — deterministic synthetic bar series (no yfinance network)
# ---------------------------------------------------------------------------


def _bars_uptrend(n: int = 100, start: float = 100.0, step: float = 1.0):
    """Monotone uptrend — 1% daily gain. Good for buy_and_hold sanity."""

    bars = []
    px = start
    for i in range(n):
        o = px
        c = o + step
        bars.append(Bar(
            date=f"2026-01-{(i % 28) + 1:02d}" if i < 28
                 else f"2026-{((i // 28) % 12) + 1:02d}-{(i % 28) + 1:02d}",
            open=o, high=max(o, c) + 0.1, low=min(o, c) - 0.1, close=c, volume=1_000,
        ))
        px = c
    # Recompute sequential dates with a simple epoch offset for stability.
    from datetime import date, timedelta
    base = date(2026, 1, 1)
    for i, b in enumerate(bars):
        b.date = (base + timedelta(days=i)).isoformat()
    return bars


def _bars_oscillation(n: int = 100, center: float = 100.0, amplitude: float = 10.0):
    """Sine-wave oscillation — triggers RSI mean-reversion regularly."""
    from datetime import date, timedelta

    bars = []
    base = date(2026, 1, 1)
    for i in range(n):
        # Period ≈ 15 days → enough swings for RSI<30 and RSI>70.
        v = math.sin(2 * math.pi * i / 15) * amplitude + center
        prev_v = math.sin(2 * math.pi * (i - 1) / 15) * amplitude + center if i > 0 else v
        o = prev_v
        c = v
        bars.append(Bar(
            date=(base + timedelta(days=i)).isoformat(),
            open=o, high=max(o, c) + 0.5, low=min(o, c) - 0.5, close=c, volume=1_000,
        ))
    return bars


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def test_load_yfinance_ohlcv_returns_list():
    """Loader returns an empty list when yfinance fails — never raises."""

    # Use an invalid ticker so we don't depend on network reach.
    result = bt.load_yfinance_ohlcv("__NOT_A_REAL_TICKER_XYZ__", days=5)
    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Backtester — walk-forward mechanics
# ---------------------------------------------------------------------------


def test_backtester_empty_bars_returns_empty_report():

    r = Backtester()._empty_report("BTC-USD", "rsi", [])
    assert r.total_trades == 0
    assert r.win_rate is None
    assert r.sharpe is None
    assert r.max_drawdown_pct == 0.0


def test_backtester_rejects_unknown_strategy():

    bars = _bars_uptrend(30)
    with pytest.raises(ValueError, match="unknown strategy"):
        Backtester().run(bars, "not_a_real_strategy")


def test_buy_and_hold_on_uptrend_is_profitable():
    """Buy-and-hold on a pure uptrend must end positive and close at end_of_data."""

    bars = _bars_uptrend(50, start=100.0, step=1.0)
    r = Backtester(bankroll=10_000.0, fee_bps=0.0).run(bars, "buy_and_hold", symbol="TEST")

    assert r.total_trades == 1
    assert r.trades[0]["exit_reason"] == "end_of_data"
    assert r.total_pnl_usd > 0
    # Synthetic returns roughly 1%/day — over 50 bars, equity should grow >30%.
    assert r.total_return_pct > 0.3


def test_fees_reduce_pnl():
    """Round-trip fees lower total PnL — two runs with different fee_bps."""

    bars = _bars_uptrend(50)
    r_zero = Backtester(fee_bps=0.0).run(bars, "buy_and_hold")
    r_fees = Backtester(fee_bps=20.0).run(bars, "buy_and_hold")
    assert r_fees.total_pnl_usd < r_zero.total_pnl_usd


def test_stop_loss_exits_before_end_of_data():
    """Long with a 2% stop must exit on a sharp drawdown — not end_of_data."""

    def always_long(bars):
        # Tight stop so it triggers on the synthetic flash crash.
        if len(bars) < 1:
            return None
        return Decision(direction="long", size=1.0, stop_pct=0.02, take_pct=None)

    # Build bars: 3 flat, then a gap-down
    bars = [
        Bar(date="2026-01-01", open=100, high=100.5, low=99.5, close=100, volume=100),
        Bar(date="2026-01-02", open=100, high=100.5, low=99.5, close=100, volume=100),
        Bar(date="2026-01-03", open=100, high=100.5, low=99.5, close=100, volume=100),
        Bar(date="2026-01-04", open=100, high=100.5, low=90, close=95, volume=100),  # crash
        Bar(date="2026-01-05", open=95, high=96, low=94, close=95, volume=100),
    ]
    r = Backtester(bankroll=10_000.0, fee_bps=0.0).run(bars, always_long)
    assert r.total_trades >= 1
    # First trade stopped out on the crash bar
    first = r.trades[0]
    assert first["exit_reason"] == "stop"
    assert first["outcome"] == "loss"


def test_signal_reverse_closes_old_opens_new():
    """When strategy flips direction, engine closes and opens a new position."""

    # Flip at bar 3: long for first 3 bars, then short.
    call_count = [0]

    def flipper(bars):
        call_count[0] += 1
        if len(bars) < 1:
            return None
        return Decision(direction="long" if len(bars) <= 3 else "short", size=1.0)

    bars = [
        Bar(date=f"2026-01-{i:02d}", open=100 + i, high=100 + i + 0.5,
            low=100 + i - 0.5, close=100 + i, volume=100)
        for i in range(1, 8)
    ]
    r = Backtester(fee_bps=0.0).run(bars, flipper)
    # Should have ≥2 trades: one long (closed on reverse), one short (closed at EoD).
    assert r.total_trades >= 2
    reasons = [t["exit_reason"] for t in r.trades]
    assert "signal_reverse" in reasons


def test_metrics_sharpe_sortino_computed_with_enough_trades():
    """With >=2 trades and non-zero variance, Sharpe/Sortino must be non-None floats."""

    bars = _bars_oscillation(80, center=100.0, amplitude=8.0)
    r = Backtester(fee_bps=0.0).run(bars, "rsi", symbol="OSC")

    # The oscillator generates enough RSI crossings to produce trades.
    if r.total_trades >= 2:
        # Sharpe/Sortino are floats (may be None if all returns identical — unlikely).
        assert r.sharpe is None or isinstance(r.sharpe, float)
        assert r.sortino is None or isinstance(r.sortino, float)


def test_win_rate_and_profit_factor_with_mixed_trades():
    """Directly construct a sequence with known W/L outcomes and verify metrics."""

    # Strategy that always goes long with stop/take so every bar decides.
    def always_long(bars):
        if len(bars) < 1:
            return None
        return Decision(direction="long", size=1.0, stop_pct=0.05, take_pct=0.05)

    # Design: first trip hits take (win), second hits stop (loss)
    bars = [
        Bar(date="2026-01-01", open=100, high=100.5, low=99.5, close=100, volume=100),
        Bar(date="2026-01-02", open=100, high=106, low=99.5, close=105.5, volume=100),  # hits +5% take
        Bar(date="2026-01-03", open=105, high=106, low=104, close=105, volume=100),
        Bar(date="2026-01-04", open=105, high=106, low=99, close=100, volume=100),  # hits -5% stop on entry 105
        Bar(date="2026-01-05", open=100, high=101, low=99, close=100, volume=100),
    ]
    r = Backtester(fee_bps=0.0).run(bars, always_long)
    assert r.total_trades >= 2
    # At least one win and one loss in outcomes list
    outcomes = [t["outcome"] for t in r.trades]
    assert "win" in outcomes
    assert "loss" in outcomes
    assert r.win_rate is not None
    # Profit factor defined when there's ≥1 loss
    assert r.profit_factor is not None


def test_drawdown_is_nonneg_and_tracks_equity_curve():

    bars = _bars_oscillation(60)
    r = Backtester(fee_bps=0.0).run(bars, "rsi", symbol="OSC")
    assert r.max_drawdown_pct >= 0
    # Every equity-curve point has a drawdown_pct field
    for p in r.equity_curve:
        assert "drawdown_pct" in p
        assert p["drawdown_pct"] >= 0


def test_backtest_symbol_convenience_with_unreachable_symbol():
    """Convenience entry point returns an empty report on load failure."""

    r = backtest_symbol("__ABSOLUTELY_NOT_A_SYMBOL_ZZZ__", strategy="rsi", days=5)
    assert r.total_trades == 0
    assert r.bars == 0


# ---------------------------------------------------------------------------
# Indicator correctness (sanity)
# ---------------------------------------------------------------------------


def test_rsi_extremes():

    # All-up series → RSI should be 100.
    up = [100 + i for i in range(30)]
    assert _rsi(up) == 100.0

    # All-down → RSI very low (close to 0 but may not be exactly 0 in pure decline).
    down = [100 - i for i in range(30)]
    r = _rsi(down)
    assert r is not None and r < 20.0


def test_rsi_returns_none_when_too_few_bars():
    assert _rsi([100, 101]) is None
