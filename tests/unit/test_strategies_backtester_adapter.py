"""Regression tests for the strategies BacktestEngine compatibility adapter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from lib.analytics.backtest import Decision
from lib.analytics.backtest_engine import Bar
from lib.analytics.strategies import BacktestEngine, Strategy, StrategyParams


def test_backtest_engine_default_kwargs_build_backtest_config():
    engine = BacktestEngine()

    assert engine.bankroll == 10_000.0
    assert engine.fee_bps == 5.0
    assert engine.backtest_config.initial_capital == 10_000.0
    assert engine.backtest_config.fee_bps == 5.0


def test_backtest_engine_custom_kwargs_build_backtest_config():
    engine = BacktestEngine(bankroll=25_000, fee_bps=12.5)

    assert engine.bankroll == 25_000.0
    assert engine.fee_bps == 12.5
    assert engine.backtest_config.initial_capital == 25_000.0
    assert engine.backtest_config.fee_bps == 12.5


class _OneShotLong(Strategy):
    @property
    def name(self) -> str:
        return "OneShotLong"

    def on_bar(self, window, aux):  # noqa: ARG002
        if len(window) != 21:
            return None
        return Decision(direction="long", size=0.5, stop_pct=0.50, tp_pct=0.05)


def _rising_bars(n: int = 30, start: float = 100.0) -> list[Bar]:
    bars: list[Bar] = []
    base_ts = datetime(2026, 3, 1, tzinfo=UTC)
    price = start
    for i in range(n):
        nxt = price * 1.01
        bars.append(
            Bar(
                ts=base_ts + timedelta(days=i),
                open=price,
                high=nxt * 1.001,
                low=price * 0.999,
                close=nxt,
                volume=1_000_000,
            )
        )
        price = nxt
    return bars


def test_backtest_engine_run_backtest_uses_adapter_initial_capital():
    engine = BacktestEngine(bankroll=12_000, fee_bps=7.5)
    strategy = _OneShotLong(StrategyParams(rsi_period=7, sl_pct=0.50, tp_pct=0.05))

    report = engine.run(_rising_bars(), strategy, symbol="RISE", aux_data={})

    assert report.total_trades == 1
    assert report.win_rate == 1.0
    assert report.report["initial_capital"] == 12_000.0
    assert report.report["final_capital"] > 12_000.0


# ── _align_aux edge-case regression tests ─────────────────────────────
#
# backtest-weekly loads aux series (funding rates, macro data, etc.) from
# heterogeneous providers. Some return None, some return empty lists, some
# return dicts without the expected date key. The pipeline runs unattended
# once a week; a single AttributeError or KeyError here silently blocks the
# weekly artifact refresh (data/backtests/strategies/strategy_sweep_*.json)
# without ever surfacing in a Telegram alert.


def test_align_aux_handles_none_value_without_crash():
    """An aux series set to None (upstream fetch returned nothing) → []."""
    engine = BacktestEngine()
    main_bars = [{"date": "2026-07-01", "close": 100.0}]
    aligned = engine._align_aux(main_bars, {"btc_funding": None})
    assert aligned == {"btc_funding": []}


def test_align_aux_handles_empty_aux_series():
    """Empty aux list → aligned empty; never raises IndexError on aux[0]."""
    engine = BacktestEngine()
    main_bars = [{"date": "2026-07-01", "close": 100.0}]
    aligned = engine._align_aux(main_bars, {"funding": []})
    assert aligned == {"funding": []}


def test_align_aux_handles_mixed_bar_shapes():
    """Main bars may be dicts (yfinance) or Bar dataclasses. Both must work."""
    engine = BacktestEngine()
    aux_bar = {"date": "2026-07-01", "value": 0.01}
    aligned = engine._align_aux(
        [{"date": "2026-07-01", "close": 100.0}, {"date": "2026-07-02", "close": 101.0}],
        {"funding": [aux_bar]},
    )
    # Forward-fill: 07-02 has no explicit aux bar, so it reuses 07-01's.
    assert len(aligned["funding"]) == 2
    assert aligned["funding"][0] == aux_bar
    assert aligned["funding"][1] == aux_bar


def test_align_aux_handles_main_bar_without_date_key():
    """A main bar missing date (Bar dataclass without ts) must not KeyError."""
    engine = BacktestEngine()
    aux_bar = {"date": "2026-07-01", "value": 0.01}
    aligned = engine._align_aux(
        [{"close": 100.0}],  # no date/ts
        {"funding": [aux_bar]},
    )
    # Falls back to last-known aux row rather than crashing.
    assert aligned["funding"] == [aux_bar]
