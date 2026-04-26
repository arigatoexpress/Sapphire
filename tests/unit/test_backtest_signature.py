"""Regression tests for backtest constructor compatibility and short sweeps."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.analytics import run_strategies
from lib.analytics import strategies as strategies_mod
from lib.analytics.backtest import BacktestConfig, Backtester, Decision
from lib.analytics.backtest_engine import _synthetic_bars
from lib.analytics.strategies import BacktestEngine, Strategy, StrategyParams


def _wave_bars(n: int = 150, start: float = 100.0) -> list[dict]:
    bars = []
    price = start
    for i in range(n):
        drift = 1.2 if (i // 20) % 2 == 0 else -1.0
        price = max(10.0, price + drift + (0.4 if i % 3 == 0 else -0.2))
        bars.append({
            "date": f"2026-02-{(i % 28) + 1:02d}",
            "open": price * 0.999,
            "high": price * 1.01,
            "low": price * 0.99,
            "close": price,
            "volume": 1_000_000,
        })
    return bars


def test_backtester_accepts_legacy_bankroll_fee_bps_signature(monkeypatch):
    bars = _wave_bars()
    monkeypatch.setattr("lib.analytics.backtest._load_ohlcv", lambda *_args, **_kwargs: bars)

    cfg = BacktestConfig(symbols=("SYN",), period_days=90, initial_capital=10_000.0)
    no_fee = Backtester(cfg).run_symbol("SYN", with_regime=False)

    legacy = Backtester(10_000.0, 5.0)
    with_fee = legacy.run_symbol("SYN", with_regime=False)

    assert legacy.cfg.initial_capital == 10_000.0
    assert legacy.cfg.fee_bps == 5.0
    assert with_fee.symbol == "SYN"
    assert with_fee.trade_count > 0
    assert with_fee.final_equity < no_fee.final_equity


class _OneShotLong(Strategy):
    """Test strategy: enter long on the first eligible bar with TP=+5%, SL=-50%.

    Pairs with `_rising_bars` so the TP is guaranteed to fire on bar 22, giving
    a deterministic single-trade result for unit-contract assertions.
    """

    @property
    def name(self) -> str:
        return "OneShotLong"

    def on_bar(self, window, aux):  # noqa: ARG002
        if len(window) != 21:  # fire exactly once at index 20
            return None
        return Decision(direction="long", size=0.5, stop_pct=0.50, tp_pct=0.05)


def _rising_bars(n: int = 30, start: float = 100.0) -> list:
    """Linearly rising bars (+1% per bar) so a long TP at +5% always hits."""
    from datetime import UTC, datetime, timedelta

    from lib.analytics.backtest_engine import Bar

    bars = []
    base_ts = datetime(2026, 3, 1, tzinfo=UTC)
    price = start
    for i in range(n):
        nxt = price * 1.01
        bars.append(Bar(
            ts=base_ts + timedelta(days=i),
            open=price, high=nxt * 1.001, low=price * 0.999,
            close=nxt, volume=1_000_000,
        ))
        price = nxt
    return bars


def test_backtest_engine_run_returns_fraction_units():
    """Pin the unit contract: BacktestEngine.run() must return win_rate /
    total_return_pct / max_drawdown_pct as fractions (0–1), not percents
    (0–100). The dashboard, format_table, and historical SweepResult JSON all
    consume fractions; emitting percents inflates leaderboard rows by 100×.

    Regression for the Apr-21 unit-mismatch where BacktestResult percents
    flowed through SimpleNamespace verbatim.
    """
    bars = _rising_bars(n=30)
    strat = _OneShotLong(StrategyParams(rsi_period=7, sl_pct=0.50, tp_pct=0.05))
    engine = BacktestEngine(bankroll=10_000.0)

    report = engine.run(bars, strat, symbol="RISE", aux_data={})

    # Exactly one trade, hitting TP at +5% on a 50%-of-bankroll position.
    assert report.total_trades == 1, f"expected 1 trade, got {report.total_trades}"
    # win_rate must be a fraction in [0, 1] — never percent.
    assert report.win_rate == 1.0, (
        f"win_rate must be fraction (1.0 = 100%), got {report.win_rate}; "
        "percent-scale leak from BacktestResult re-introduced?"
    )
    # total_return_pct must also be a fraction. Worst-case sanity: a 5% TP on
    # a 50% position can't lift bankroll by more than 5%, so the fraction must
    # be < 0.10. A percent-scale value would be ~2.5 (i.e. 250% by mistake).
    assert 0.0 < report.total_return_pct < 0.10, (
        f"total_return_pct must be fraction (~0.025 expected), got "
        f"{report.total_return_pct}; percent-scale leak?"
    )
    # max_drawdown_pct: same fraction contract. Rising bars → essentially zero
    # drawdown, but cap at 1.0 to catch percent-scale leaks.
    assert 0.0 <= report.max_drawdown_pct < 1.0, (
        f"max_drawdown_pct must be fraction, got {report.max_drawdown_pct}"
    )


def test_run_strategies_days_7_still_writes_artifact(tmp_path, monkeypatch):
    out_dir = tmp_path / "data" / "backtests" / "strategies"
    monkeypatch.setattr(run_strategies, "load_yfinance_ohlcv", lambda symbol, days: _synthetic_bars(symbol, days))
    monkeypatch.setattr(run_strategies, "_ROOT", tmp_path)
    monkeypatch.setattr(strategies_mod, "RESULTS_DIR", out_dir)
    monkeypatch.setenv("GITHUB_SHA", "abc123")
    monkeypatch.setenv("GITHUB_RUN_ID", "456")

    best = run_strategies.run(days=7, bankroll=10_000.0)

    assert best
    sweep_path = next(out_dir.glob("strategy_sweep_*.json"))
    best_path = next(out_dir.glob("best_per_symbol_*.json"))
    sweep = json.loads(sweep_path.read_text())
    best_payload = json.loads(best_path.read_text())

    for payload in (sweep, best_payload):
        metadata = payload["metadata"]
        assert metadata["source"]["generator"] == "lib.analytics.run_strategies"
        assert metadata["source"]["git_sha"] == "abc123"
        assert metadata["source"]["github_run_id"] == "456"
        assert metadata["config"]["days"] == 7
        assert metadata["config"]["bankroll"] == 10_000.0
        assert set(metadata["bar_fingerprints"]) == set(run_strategies.SYMBOLS)
        assert metadata["bar_fingerprints"]["BTC-USD"]["bars"] == 7
        assert len(metadata["bar_fingerprints"]["BTC-USD"]["sha256"]) == 64
