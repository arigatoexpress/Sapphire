"""Unit tests for lib/analytics/walkforward/engine.py.

All tests use synthetic deterministic OHLCV — no live data, no fixtures from
disk. The bar fixture has a regime mix that forces strategies through both
risk-on and risk-off regions so walk-forward selection actually picks
different params on different windows.
"""

from __future__ import annotations

import math
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.analytics.backtest_engine import Bar  # noqa: E402
from lib.analytics.strategies import (  # noqa: E402
    PARAM_GRID,
    CorrelationBreakout,
    FundingRateContrarian,
    MultiTFMomentum,
    RegimeAwareRSI,
    SapphireComposite,
    StrategyParams,
)
from lib.analytics.walkforward.engine import (  # noqa: E402
    Bar as ReExportedBar,
)
from lib.analytics.walkforward.engine import (  # noqa: E402
    ParameterGrid,
    WalkforwardConfig,
    WalkforwardResult,
    WalkforwardWindow,
    WindowMetrics,
    _build_params,
    _equity_to_returns,
    _grid_combos,
    _params_sort_key,
    _select_metric_value,
    run_walkforward,
    walkforward_windows,
    window_test_indices,
    windows_summary,
)

# ── Synthetic bar fixtures ─────────────────────────────────────────────────


def _make_bars(n: int, *, seed: int = 7, regime_change_at: int = 0) -> list[Bar]:
    """Deterministic OHLCV with optional mid-window regime flip."""
    bars: list[Bar] = []
    base = datetime(2025, 1, 1, tzinfo=UTC)
    price = 100.0 + (seed % 17)
    for i in range(n):
        d1 = math.sin(i / 7.0 + seed / 13.0) * 1.4
        d2 = math.cos(i / 21.0 + seed / 5.0) * 0.7
        regime_drift = -1.5 if regime_change_at and i >= regime_change_at else 0.0
        delta = (d1 + d2 + regime_drift) / 100.0
        price = max(5.0, price * (1.0 + delta))
        bars.append(
            Bar(
                ts=base + timedelta(days=i),
                open=price * 0.997,
                high=price * 1.013,
                low=price * 0.987,
                close=price,
                volume=1_000_000.0 + (i % 5) * 50_000,
            )
        )
    return bars


@pytest.fixture
def bars_250() -> list[Bar]:
    return _make_bars(250, seed=11, regime_change_at=120)


@pytest.fixture
def bars_500() -> list[Bar]:
    return _make_bars(500, seed=23, regime_change_at=250)


# ── walkforward_windows — pure window enumeration ──────────────────────────


def test_windows_count_no_overlap_default() -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    windows = walkforward_windows(200, cfg)
    # First window: train [0,60), test [60,80). Advance by 20.
    # Last test_end ≤ 200 → train_start ≤ 120. So train_starts ∈ {0,20,..,120}.
    assert len(windows) == 7
    for w in windows:
        assert w.train_end - w.train_start == 60
        assert w.test_end - w.test_start == 20
        assert w.test_start == w.train_end  # no purge
        assert w.test_end <= 200


def test_windows_no_overlap_between_test_slices() -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    windows = walkforward_windows(300, cfg)
    test_ranges = [(w.test_start, w.test_end) for w in windows]
    # Default advance == test_bars → all test slices contiguous, no overlap.
    for (s1, e1), (s2, e2) in zip(test_ranges, test_ranges[1:], strict=False):
        assert s2 == e1, f"expected contiguous test slices, got [{s1},{e1}) → [{s2},{e2})"


def test_windows_explicit_advance_creates_gap_or_overlap() -> None:
    # advance > test_bars → gaps between test slices
    cfg_gap = WalkforwardConfig(train_bars=60, test_bars=20, advance_bars=40)
    windows = walkforward_windows(300, cfg_gap)
    assert windows[1].train_start - windows[0].train_start == 40
    assert windows[1].test_start > windows[0].test_end


def test_windows_advance_smaller_than_test_overlaps() -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=30, advance_bars=10)
    windows = walkforward_windows(200, cfg)
    # Test slices should overlap by 20 bars
    assert windows[1].test_start < windows[0].test_end


def test_windows_zero_when_n_bars_too_small() -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    assert walkforward_windows(50, cfg) == []
    assert walkforward_windows(79, cfg) == []  # train + test - 1


def test_windows_purge_pushes_test_start_forward() -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=20, purge_bars=5)
    windows = walkforward_windows(200, cfg)
    for w in windows:
        assert w.test_start == w.train_end + 5


def test_windows_validate_rejects_short_train() -> None:
    with pytest.raises(ValueError, match="train_bars must be ≥ 60"):
        WalkforwardConfig(train_bars=30, test_bars=20).validate()


def test_windows_validate_rejects_short_test() -> None:
    with pytest.raises(ValueError, match="test_bars must be ≥ 20"):
        WalkforwardConfig(train_bars=60, test_bars=10).validate()


def test_windows_validate_rejects_unknown_metric() -> None:
    with pytest.raises(ValueError, match="selection_metric"):
        WalkforwardConfig(train_bars=60, test_bars=20, selection_metric="meh").validate()


def test_windows_summary_jsonable() -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    summary = windows_summary(walkforward_windows(200, cfg))
    assert isinstance(summary, list)
    assert all(isinstance(s, dict) and "window_idx" in s for s in summary)


def test_window_test_indices_correct() -> None:
    w = WalkforwardWindow(window_idx=0, train_start=0, train_end=60, test_start=60, test_end=80)
    assert window_test_indices(w) == list(range(60, 80))


# ── grid enumeration ───────────────────────────────────────────────────────


def test_grid_combos_returns_cartesian_product() -> None:
    grid = {"a": [1, 2], "b": [3, 4, 5]}
    combos = _grid_combos(grid)
    assert len(combos) == 6
    assert {(c["a"], c["b"]) for c in combos} == {(1, 3), (1, 4), (1, 5), (2, 3), (2, 4), (2, 5)}


def test_grid_combos_empty_grid_yields_one_empty_combo() -> None:
    assert _grid_combos({}) == [{}]


def test_grid_combos_default_param_grid_size_27() -> None:
    # PARAM_GRID has 3 keys × 3 values = 27 combos
    combos = _grid_combos(PARAM_GRID)
    assert len(combos) == 27


def test_params_sort_key_is_deterministic() -> None:
    a = {"rsi_period": 7, "sl_pct": 0.02, "tp_pct": 0.05}
    b = {"rsi_period": 14, "sl_pct": 0.02, "tp_pct": 0.05}
    assert _params_sort_key(a) < _params_sort_key(b)


def test_build_params_overrides_defaults_only() -> None:
    p = _build_params({"rsi_period": 7, "sl_pct": 0.02, "tp_pct": 0.05})
    assert p.rsi_period == 7
    assert p.sl_pct == 0.02
    # untouched fields keep defaults
    assert p.regime_period == StrategyParams().regime_period


# ── _select_metric_value ───────────────────────────────────────────────────


class _FakeReport:
    def __init__(self, **kw: float) -> None:
        for k, v in kw.items():
            setattr(self, k, v)


def test_select_metric_value_translates_metric_name() -> None:
    rep = _FakeReport(sortino=1.5, sharpe=0.9, calmar=2.1, profit_factor=3.0, total_return_pct=0.4)
    assert _select_metric_value(rep, "sortino") == pytest.approx(1.5)
    assert _select_metric_value(rep, "sharpe") == pytest.approx(0.9)
    assert _select_metric_value(rep, "calmar") == pytest.approx(2.1)
    assert _select_metric_value(rep, "profit_factor") == pytest.approx(3.0)
    assert _select_metric_value(rep, "total_return") == pytest.approx(0.4)


def test_select_metric_value_handles_none_or_nan() -> None:
    rep = _FakeReport(
        sortino=None, sharpe=float("nan"), calmar=1, profit_factor=1, total_return_pct=0
    )
    assert _select_metric_value(rep, "sortino") == float("-inf")
    assert _select_metric_value(rep, "sharpe") == float("-inf")


# ── _equity_to_returns ─────────────────────────────────────────────────────


def test_equity_to_returns_simple() -> None:
    equity = [("a", 100.0), ("b", 110.0), ("c", 105.0)]
    rets = _equity_to_returns(equity)
    assert rets == pytest.approx([0.1, -0.045454545454545456])


def test_equity_to_returns_skips_zero_prev() -> None:
    equity = [("a", 100.0), ("b", 0.0), ("c", 50.0)]
    rets = _equity_to_returns(equity)
    # second step has prev=0 → skipped
    assert len(rets) == 1


# ── run_walkforward — end-to-end ──────────────────────────────────────────


def test_run_walkforward_basic_shape(bars_250: list[Bar]) -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=20, advance_bars=20)
    result = run_walkforward(RegimeAwareRSI, bars_250, config=cfg)
    assert isinstance(result, WalkforwardResult)
    assert result.strategy_cls == "RegimeAwareRSI"
    assert result.n_bars == 250
    assert result.n_windows > 0
    for w in result.windows:
        assert isinstance(w, WindowMetrics)
        assert w.train_end - w.train_start == 60
        assert w.test_end - w.test_start == 20


def test_run_walkforward_chosen_params_subset_of_grid(bars_250: list[Bar]) -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    result = run_walkforward(RegimeAwareRSI, bars_250, config=cfg)
    valid_rsi = set(PARAM_GRID["rsi_period"])
    valid_sl = set(PARAM_GRID["sl_pct"])
    valid_tp = set(PARAM_GRID["tp_pct"])
    for w in result.windows:
        assert w.chosen_params["rsi_period"] in valid_rsi
        assert w.chosen_params["sl_pct"] in valid_sl
        assert w.chosen_params["tp_pct"] in valid_tp


def test_run_walkforward_concatenated_returns_aligned_with_timestamps(bars_250: list[Bar]) -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    result = run_walkforward(RegimeAwareRSI, bars_250, config=cfg)
    assert len(result.concatenated_test_returns) == len(result.concatenated_test_timestamps)


def test_run_walkforward_aggregates_only_active_windows(bars_250: list[Bar]) -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    result = run_walkforward(RegimeAwareRSI, bars_250, config=cfg)
    # n_active_windows ≤ n_windows; aggregates exist
    assert 0 <= result.n_active_windows <= result.n_windows
    assert isinstance(result.mean_test_sortino, float)


def test_run_walkforward_to_dict_jsonable(bars_250: list[Bar]) -> None:
    import json

    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    result = run_walkforward(RegimeAwareRSI, bars_250, config=cfg)
    d = result.to_dict()
    blob = json.dumps(d, default=str)
    assert "RegimeAwareRSI" in blob
    assert "windows" in d
    assert "concatenated_test_returns" in d


def test_run_walkforward_empty_when_too_few_bars() -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    result = run_walkforward(RegimeAwareRSI, _make_bars(50), config=cfg)
    assert result.n_windows == 0
    assert result.windows == []


def test_run_walkforward_custom_grid_drives_selection(bars_250: list[Bar]) -> None:
    grid: ParameterGrid = {
        "rsi_period": [7],
        "sl_pct": [0.02, 0.05],
        "tp_pct": [0.10],
    }
    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    result = run_walkforward(RegimeAwareRSI, bars_250, grid=grid, config=cfg)
    assert result.grid_size == 2
    for w in result.windows:
        assert w.chosen_params["rsi_period"] == 7
        assert w.chosen_params["sl_pct"] in (0.02, 0.05)
        assert w.chosen_params["tp_pct"] == 0.10


def test_run_walkforward_with_aux_data(bars_500: list[Bar]) -> None:
    """CorrelationBreakout requires aux['spy']."""
    spy = _make_bars(500, seed=99, regime_change_at=300)
    btc = _make_bars(500, seed=77)
    cfg = WalkforwardConfig(train_bars=90, test_bars=30, advance_bars=30, symbol="BTC-USD")
    result = run_walkforward(
        CorrelationBreakout,
        bars_500,
        aux={"spy": spy, "btc": btc},
        config=cfg,
    )
    assert result.strategy_cls == "CorrelationBreakout"
    assert result.n_windows > 0


def test_run_walkforward_all_strategy_classes_runnable(bars_500: list[Bar]) -> None:
    aux = {"spy": _make_bars(500, seed=55), "btc": _make_bars(500, seed=44)}
    cfg = WalkforwardConfig(train_bars=90, test_bars=30, advance_bars=30)
    for cls in (
        RegimeAwareRSI,
        FundingRateContrarian,
        CorrelationBreakout,
        MultiTFMomentum,
        SapphireComposite,
    ):
        result = run_walkforward(cls, bars_500, aux=aux, config=cfg)
        assert result.strategy_cls == cls.__name__
        assert result.n_windows > 0


def test_run_walkforward_window_test_returns_match_test_window_length(bars_250: list[Bar]) -> None:
    """Per-window returns should have at most test_bars - 1 entries
    (the equity curve over test_bars produces test_bars - 1 returns)."""
    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    result = run_walkforward(RegimeAwareRSI, bars_250, config=cfg)
    for w in result.windows:
        assert len(w.test_returns) <= cfg.test_bars - 1


def test_run_walkforward_purge_skips_bars_between_train_and_test() -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=20, purge_bars=5)
    bars = _make_bars(200, seed=3)
    result = run_walkforward(RegimeAwareRSI, bars, config=cfg)
    for w in result.windows:
        assert w.test_start - w.train_end == 5


def test_run_walkforward_selection_metric_override(bars_250: list[Bar]) -> None:
    cfg_sortino = WalkforwardConfig(train_bars=60, test_bars=20, selection_metric="sortino")
    cfg_sharpe = WalkforwardConfig(train_bars=60, test_bars=20, selection_metric="sharpe")
    r1 = run_walkforward(RegimeAwareRSI, bars_250, config=cfg_sortino)
    r2 = run_walkforward(RegimeAwareRSI, bars_250, config=cfg_sharpe)
    assert r1.config["selection_metric"] == "sortino"
    assert r2.config["selection_metric"] == "sharpe"


def test_run_walkforward_deterministic_repeatable(bars_250: list[Bar]) -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    a = run_walkforward(RegimeAwareRSI, bars_250, config=cfg)
    b = run_walkforward(RegimeAwareRSI, bars_250, config=cfg)
    assert a.to_dict() == b.to_dict()


def test_run_walkforward_advance_explicit_no_overlap_chain(bars_500: list[Bar]) -> None:
    cfg = WalkforwardConfig(train_bars=90, test_bars=30, advance_bars=30)
    result = run_walkforward(RegimeAwareRSI, bars_500, config=cfg)
    test_starts = [w.test_start for w in result.windows]
    test_ends = [w.test_end for w in result.windows]
    for i in range(1, len(test_starts)):
        assert test_starts[i] == test_ends[i - 1]


def test_run_walkforward_min_train_trades_blocks_underfit(bars_250: list[Bar]) -> None:
    """Setting min_train_trades very high forces -inf metric → first valid combo wins."""
    cfg = WalkforwardConfig(train_bars=60, test_bars=20, min_train_trades=10_000)
    result = run_walkforward(RegimeAwareRSI, bars_250, config=cfg)
    # Even with no combos meeting the trade floor, the engine still picks one.
    assert result.n_windows > 0
    for w in result.windows:
        assert w.train_metric == float("-inf") or w.train_trades >= 10_000


def test_run_walkforward_record_window_timestamps(bars_250: list[Bar]) -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    result = run_walkforward(RegimeAwareRSI, bars_250, config=cfg)
    for w in result.windows:
        # ISO date strings, length 10
        assert len(w.test_start_ts) == 10
        assert len(w.test_end_ts) == 10
        assert w.test_start_ts <= w.test_end_ts


def test_run_walkforward_grid_size_recorded(bars_250: list[Bar]) -> None:
    grid: ParameterGrid = {"rsi_period": [7, 14], "sl_pct": [0.05], "tp_pct": [0.10]}
    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    result = run_walkforward(RegimeAwareRSI, bars_250, grid=grid, config=cfg)
    assert result.grid_size == 2


def test_walkforward_window_dataclass_to_dict_keys() -> None:
    w = WalkforwardWindow(window_idx=2, train_start=10, train_end=70, test_start=70, test_end=90)
    d = w.to_dict()
    assert set(d.keys()) == {"window_idx", "train_start", "train_end", "test_start", "test_end"}


def test_run_walkforward_handles_zero_window_aggregates_safely() -> None:
    cfg = WalkforwardConfig(train_bars=60, test_bars=20)
    result = run_walkforward(RegimeAwareRSI, _make_bars(70), config=cfg)
    # No windows produced — aggregates remain at 0
    assert result.mean_test_sortino == 0.0
    assert result.test_sortino_cv == 0.0


def test_re_exported_bar_is_engine_bar() -> None:
    """Ensure the re-export from engine.Bar is the real backtest_engine.Bar
    so callers can do `from lib.analytics.walkforward.engine import Bar`."""
    assert ReExportedBar is Bar
