"""Regression tests for backtest constructor compatibility and short sweeps."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.analytics import run_strategies
from lib.analytics import strategies as strategies_mod
from lib.analytics.backtest import BacktestConfig, Backtester
from lib.analytics.backtest_engine import _synthetic_bars


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


def test_run_strategies_days_7_still_writes_artifact(tmp_path, monkeypatch):
    out_dir = tmp_path / "data" / "backtests" / "strategies"
    monkeypatch.setattr(run_strategies, "load_yfinance_ohlcv", lambda symbol, days: _synthetic_bars(symbol, days))
    monkeypatch.setattr(run_strategies, "_ROOT", tmp_path)
    monkeypatch.setattr(strategies_mod, "RESULTS_DIR", out_dir)

    best = run_strategies.run(days=7, bankroll=10_000.0)

    assert best
    assert any(out_dir.glob("strategy_sweep_*.json"))
