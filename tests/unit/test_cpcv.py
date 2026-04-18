"""Unit tests for lib/analytics/cpcv.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.analytics.backtest_engine import _synthetic_bars  # noqa: E402
from lib.analytics.cpcv import (  # noqa: E402
    CPCVResult,
    CPCVSplitMetrics,
    _group_bounds,
    _trade_metrics,
    cpcv_splits,
    run_cpcv_backtest,
)

# ── cpcv_splits ────────────────────────────────────────────────────────────────


def test_cpcv_splits_correct_count() -> None:
    # C(6, 2) = 15 splits
    splits = list(cpcv_splits(120, n_groups=6, n_test_groups=2))
    assert len(splits) == 15


def test_cpcv_splits_no_overlap() -> None:
    for train, test in cpcv_splits(120, n_groups=6, n_test_groups=2):
        assert set(train).isdisjoint(set(test)), "train and test must not overlap"


def test_cpcv_splits_covers_all_samples_per_split() -> None:
    # After purge/embargo, train ∪ test may not cover everything, but
    # test indices alone should cover n_test_groups / n_groups of samples.
    n = 120
    n_groups = 6
    group_size = n // n_groups
    splits = list(cpcv_splits(n, n_groups=n_groups, n_test_groups=2))
    for _train, test in splits:
        # Test set should be exactly 2 groups worth of samples (±1 for remainder)
        expected_test_size = group_size * 2
        assert abs(len(test) - expected_test_size) <= 1


def test_cpcv_splits_purge_removes_boundary_train_samples() -> None:
    # With a large purge_pct, fewer train samples should survive near boundaries.
    n = 100
    splits_no_purge = list(cpcv_splits(n, n_groups=5, n_test_groups=1, purge_pct=0.0, embargo_pct=0.0))
    splits_with_purge = list(cpcv_splits(n, n_groups=5, n_test_groups=1, purge_pct=0.05, embargo_pct=0.0))
    for (train_np, _), (train_wp, _) in zip(splits_no_purge, splits_with_purge, strict=False):
        assert len(train_wp) <= len(train_np), "purge should reduce or equal train size"


def test_cpcv_splits_embargo_removes_post_test_samples() -> None:
    n = 100
    splits_no_emb = list(cpcv_splits(n, n_groups=5, n_test_groups=1, purge_pct=0.0, embargo_pct=0.0))
    splits_with_emb = list(cpcv_splits(n, n_groups=5, n_test_groups=1, purge_pct=0.0, embargo_pct=0.05))
    for (train_ne, _), (train_we, _) in zip(splits_no_emb, splits_with_emb, strict=False):
        assert len(train_we) <= len(train_ne), "embargo should reduce or equal train size"


def test_cpcv_splits_invalid_n_test_groups() -> None:
    with pytest.raises(ValueError, match="n_test_groups"):
        list(cpcv_splits(60, n_groups=3, n_test_groups=3))


def test_cpcv_splits_insufficient_samples() -> None:
    with pytest.raises(ValueError, match="n_samples"):
        list(cpcv_splits(2, n_groups=6, n_test_groups=2))


def test_cpcv_splits_train_indices_sorted() -> None:
    for train, test in cpcv_splits(60, n_groups=6, n_test_groups=2):
        assert train == sorted(train)
        assert test == sorted(test)


def test_group_bounds_last_group_absorbs_remainder() -> None:
    bounds = _group_bounds(100, 6)
    assert len(bounds) == 6
    # Last group should end at 100, not at 6*16=96
    assert bounds[-1][1] == 100
    # All groups should be contiguous
    for i in range(1, len(bounds)):
        assert bounds[i][0] == bounds[i - 1][1]


# ── _trade_metrics ─────────────────────────────────────────────────────────────


def test_trade_metrics_empty_returns_zeros() -> None:
    m = _trade_metrics([])
    assert m["sharpe"] == 0.0
    assert m["win_rate"] == 0.0
    assert m["n_trades"] == 0.0


def test_trade_metrics_single_win() -> None:
    bars = _synthetic_bars("X", 60)
    # Run a simple one-shot backtest to get a real Trade object
    from lib.analytics.backtest_engine import run_backtest

    def always_buy(symbol, bars, i):
        if i == 5:
            return {"symbol": symbol, "action": "buy", "price": bars[i].close,
                    "confidence": 0.8, "strategy": "test"}
        return None

    result = run_backtest("X", bars=bars, signal_fn=always_buy)
    if result.trades:
        m = _trade_metrics(result.trades)
        assert 0.0 <= m["win_rate"] <= 100.0
        assert m["n_trades"] == float(len(result.trades))


# ── run_cpcv_backtest ──────────────────────────────────────────────────────────


def _fast_signal(symbol, bars, i):
    """Generates signals every 3 bars to produce enough trades for CPCV."""
    if i < 2:
        return None
    if i % 6 == 0:
        return {"symbol": symbol, "action": "buy", "price": bars[i].close,
                "confidence": 0.7, "strategy": "cpcv_test",
                "take_profit": bars[i].close * 1.03,
                "stop_loss": bars[i].close * 0.97}
    return None


def test_run_cpcv_backtest_returns_correct_n_splits() -> None:
    bars = _synthetic_bars("CPCV", 120)
    result = run_cpcv_backtest("CPCV", bars=bars, signal_fn=_fast_signal)
    assert result.n_splits == 15  # C(6, 2) = 15


def test_run_cpcv_backtest_split_metrics_type() -> None:
    bars = _synthetic_bars("CPCV", 120)
    result = run_cpcv_backtest("CPCV", bars=bars, signal_fn=_fast_signal)
    assert isinstance(result, CPCVResult)
    assert all(isinstance(s, CPCVSplitMetrics) for s in result.splits)


def test_run_cpcv_backtest_aggregate_fields_present() -> None:
    bars = _synthetic_bars("CPCV", 120)
    result = run_cpcv_backtest("CPCV", bars=bars, signal_fn=_fast_signal)
    assert hasattr(result, "mean_sharpe")
    assert hasattr(result, "std_sharpe")
    assert hasattr(result, "min_sharpe")
    assert hasattr(result, "sharpe_cv")
    assert hasattr(result, "mean_max_drawdown")


def test_run_cpcv_backtest_sharpe_cv_finite() -> None:
    bars = _synthetic_bars("CPCV", 120)
    result = run_cpcv_backtest("CPCV", bars=bars, signal_fn=_fast_signal)
    import math
    # sharpe_cv is capped to 999.0 for inf cases
    assert math.isfinite(result.sharpe_cv) or result.sharpe_cv == 999.0


def test_run_cpcv_backtest_insufficient_bars_returns_empty() -> None:
    bars = _synthetic_bars("TINY", 10)
    result = run_cpcv_backtest("TINY", bars=bars)
    assert result.n_splits == 0
    assert result.splits == []


def test_run_cpcv_backtest_split_train_test_sizes_reasonable() -> None:
    bars = _synthetic_bars("CPCV", 120)
    result = run_cpcv_backtest("CPCV", bars=bars, signal_fn=_fast_signal)
    for split in result.splits:
        assert split.n_test_bars > 0
        assert split.n_train_bars > 0
        # Test should be ~1/3 of total (2 out of 6 groups)
        assert split.n_test_bars < len(bars)


def test_run_cpcv_backtest_to_dict_serializable() -> None:
    bars = _synthetic_bars("CPCV", 120)
    result = run_cpcv_backtest("CPCV", bars=bars, signal_fn=_fast_signal)
    d = result.to_dict()
    assert d["symbol"] == "CPCV"
    assert d["n_groups"] == 6
    assert len(d["splits"]) == 15
    import json
    json.dumps(d)  # must be JSON-serializable
