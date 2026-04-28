"""Tests for the `output_dir` override in `lib.analytics.strategies.save_results`."""

from __future__ import annotations

import json
from pathlib import Path

from lib.analytics.backtest import BacktestResult
from lib.analytics.strategies import RESULTS_DIR, SweepResult, save_results


def _empty_result() -> SweepResult:
    report = BacktestResult(
        symbol="TEST",
        regime_enhancement=False,
        period_days=30,
        bar_count=0,
        trade_count=0,
        final_equity=10_000.0,
        total_return_pct=0.0,
        sharpe=0.0,
        sortino=0.0,
        max_drawdown_pct=0.0,
        win_rate=0.0,
        profit_factor=0.0,
        avg_win=0.0,
        avg_loss=0.0,
        avg_score=0.0,
    )
    return SweepResult(
        strategy_cls="Noop",
        strategy_name="Noop",
        symbol="TEST",
        rsi_period=14,
        sl_pct=0.02,
        tp_pct=0.03,
        sortino=0.0,
        sharpe=0.0,
        total_return_pct=0.0,
        win_rate=0.0,
        profit_factor=0.0,
        max_drawdown_pct=0.0,
        calmar=0.0,
        total_trades=0,
        report=report,
    )


def test_save_results_uses_default_results_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("lib.analytics.strategies.RESULTS_DIR", tmp_path / "default")
    path = save_results([_empty_result()], metadata={"test": True})
    assert path.parent == tmp_path / "default"
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["metadata"] == {"test": True}
    assert payload["total_backtests"] == 1


def test_save_results_honours_explicit_output_dir(tmp_path):
    target = tmp_path / "explicit-out"
    path = save_results([_empty_result()], output_dir=target)
    assert path.parent == target
    assert path.exists()
    assert target.is_dir()


def test_save_results_creates_nested_output_dir(tmp_path):
    target = tmp_path / "nested" / "level2" / "out"
    assert not target.exists()
    path = save_results([_empty_result()], output_dir=target)
    assert path.parent == target
    assert target.is_dir()


def test_save_results_default_dir_is_under_data_backtests_strategies():
    # Sanity: the canonical default still resolves under data/backtests/strategies.
    assert RESULTS_DIR.name == "strategies"
    assert RESULTS_DIR.parent.name == "backtests"
    assert RESULTS_DIR.parent.parent.name == "data"
    assert isinstance(RESULTS_DIR, Path)
