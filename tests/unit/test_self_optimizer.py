"""Unit tests for lib/analytics/self_optimizer.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.analytics import backtest_engine as be  # noqa: E402
from lib.analytics.self_optimizer import (  # noqa: E402
    ParamCell,
    load_recent_proposals,
    optimize_symbol,
    run_sweep,
    save_proposal,
)


@pytest.fixture(autouse=True)
def _use_synthetic(monkeypatch) -> None:
    """Force the backtester to use synthetic bars — no network."""
    monkeypatch.setattr(
        be, "fetch_ohlcv",
        lambda sym, days=90, interval="1d": be._synthetic_bars(sym, days),
    )


def test_optimize_symbol_returns_proposal() -> None:
    p = optimize_symbol("X", days=60)
    assert p.symbol == "X"
    assert p.recommended["score_min"] in (0.0, 40.0, 55.0, 70.0)
    assert p.recommended["position_size_pct"] in (0.05, 0.10, 0.15)
    assert "sharpe" in p.recommended_metrics
    assert len(p.grid_results) == 12  # 4 × 3 grid


def test_optimize_respects_current() -> None:
    current = ParamCell(score_min=70.0, position_size_pct=0.05)
    p = optimize_symbol("Y", days=60, current=current)
    assert p.current["score_min"] == 70.0
    assert p.current["position_size_pct"] == 0.05


def test_proposal_delta_fields_exist() -> None:
    p = optimize_symbol("Z", days=60)
    assert "sharpe" in p.delta
    assert "return_pct" in p.delta
    assert "drawdown_pct" in p.delta


def test_save_and_load_proposals(tmp_path) -> None:
    file = tmp_path / "proposals.jsonl"
    p1 = optimize_symbol("A", days=50)
    p2 = optimize_symbol("B", days=50)
    save_proposal(p1, path=file)
    save_proposal(p2, path=file)

    loaded = load_recent_proposals(path=file)
    assert len(loaded) == 2
    # Newest first
    assert loaded[0]["symbol"] == "B"
    assert loaded[1]["symbol"] == "A"


def test_run_sweep_persist_toggle(tmp_path) -> None:
    file = tmp_path / "proposals.jsonl"
    proposals = run_sweep(["X", "Y"], days=50, persist=True, path=file)
    assert len(proposals) == 2
    assert file.exists()
    # Dry run doesn't write.
    file2 = tmp_path / "proposals2.jsonl"
    run_sweep(["X"], days=50, persist=False, path=file2)
    assert not file2.exists()
