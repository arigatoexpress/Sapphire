"""Walk-forward backtest engine.

Pure orchestrator over the existing strategy + backtest infrastructure. Given a
``Strategy`` class (any subclass from ``lib.analytics.strategies``), a parameter
grid, an OHLCV bar list, and optional aux/regime data, it produces a sequence of
non-overlapping (train, test) windows and reports per-window out-of-sample
metrics. Selection on each window is done by best-Sortino on the train slice;
the chosen parameters are then frozen and evaluated on the immediately
following test slice. The returned ``WalkforwardResult`` is JSON-serializable
and additionally carries the per-window concatenated test-period returns,
which downstream modules (``regime_decomp``, ``deflated_sharpe``) consume.

Determinism: given identical inputs the engine is fully deterministic. It does
not call live data, the network, the file system, or any randomness primitive.
The grid is enumerated in a stable order; ties on Sortino fall back to Sharpe,
then to total_return_pct, then to lexicographic ``(rsi_period, sl_pct, tp_pct,
composite_threshold)``.

Window-advance policy (default): ``advance_by_test_window``. The next train
slice starts at the previous test_end; the next test slice immediately follows.
This produces a chain of non-overlapping test slices that, concatenated end to
end, cover the full bar series minus the warm-up. Override via
``WalkforwardConfig.advance_bars`` to set a fixed integer step (rolling), or by
passing ``mode="rolling_overlap"`` for stride-based overlapping windows.

The engine never mutates ``strategies``/``backtest``/``backtest_engine``/
``deflated_sharpe``/``risk_engine`` — it only instantiates and reads from them.
"""

from __future__ import annotations

import itertools
import logging
import math
import statistics
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

from lib.analytics.backtest_engine import (
    Bar as EngineBar,
)
from lib.analytics.backtest_engine import (
    max_drawdown_pct,
    sharpe_ratio,
    sortino_ratio,
)
from lib.analytics.strategies import (
    PARAM_GRID as DEFAULT_PARAM_GRID,
)
from lib.analytics.strategies import (
    BacktestEngine,
    Strategy,
    StrategyParams,
)

log = logging.getLogger(__name__)


__all__ = [
    "ParameterGrid",
    "WalkforwardConfig",
    "WalkforwardResult",
    "WalkforwardWindow",
    "WindowMetrics",
    "run_walkforward",
    "walkforward_windows",
]


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


# A parameter grid is a mapping of StrategyParams field name -> list of values.
# We accept either dict or Mapping; the engine itertools.products values to form
# combos. The default mirrors strategies.PARAM_GRID (rsi_period × sl_pct × tp_pct).
ParameterGrid = Mapping[str, list[Any]]


@dataclass
class WalkforwardConfig:
    """Configuration for a single walk-forward run.

    Args:
        train_bars:    Number of bars in each training window. Must be ≥ 60.
        test_bars:     Number of bars in each test window. Must be ≥ 20.
        advance_bars:  Step between successive train_start values. Defaults to
                       ``test_bars`` (no overlap between test slices). Setting
                       this to a value < ``test_bars`` is allowed and produces
                       overlapping test slices ("rolling_overlap" mode).
        purge_bars:    Bars purged at the train→test boundary to prevent label
                       leakage (CPCV-style). Default 0.
        embargo_bars:  Bars embargoed on the train side immediately following a
                       prior test slice in overlapping mode. Default 0.
        selection_metric: One of ``sortino``, ``sharpe``, ``calmar``,
                       ``profit_factor``, ``total_return``. Used to pick the
                       best param combo on each train slice.
        bankroll:      Initial capital for the inner ``BacktestEngine``.
        symbol:        Symbol label propagated to ``BacktestEngine.run``.
        min_train_trades: A train fit with fewer than this many trades is
                       treated as ``-inf`` for selection (avoids picking a
                       lucky-but-stale combo).
    """

    train_bars: int = 90
    test_bars: int = 30
    advance_bars: int | None = None
    purge_bars: int = 0
    embargo_bars: int = 0
    selection_metric: str = "sortino"
    bankroll: float = 10_000.0
    symbol: str = "?"
    min_train_trades: int = 1

    def effective_advance(self) -> int:
        """Resolve advance_bars defaulting to test_bars (no-overlap chain)."""
        return int(self.advance_bars if self.advance_bars is not None else self.test_bars)

    def validate(self) -> None:
        if self.train_bars < 60:
            raise ValueError(f"train_bars must be ≥ 60 (got {self.train_bars})")
        if self.test_bars < 20:
            raise ValueError(f"test_bars must be ≥ 20 (got {self.test_bars})")
        if self.effective_advance() < 1:
            raise ValueError(f"advance_bars must be ≥ 1 (got {self.advance_bars})")
        if self.purge_bars < 0 or self.embargo_bars < 0:
            raise ValueError("purge_bars / embargo_bars must be ≥ 0")
        valid_metrics = {"sortino", "sharpe", "calmar", "profit_factor", "total_return"}
        if self.selection_metric not in valid_metrics:
            raise ValueError(
                f"selection_metric must be one of {sorted(valid_metrics)} "
                f"(got {self.selection_metric!r})"
            )


@dataclass
class WalkforwardWindow:
    """A single (train, test) slice with absolute bar indices."""

    window_idx: int
    train_start: int
    train_end: int  # exclusive
    test_start: int
    test_end: int  # exclusive

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass
class WindowMetrics:
    """Per-window OOS metrics + the chosen training parameters."""

    window_idx: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    chosen_params: dict[str, Any]
    train_metric: float  # value of the selection metric on the train slice
    train_trades: int
    test_sortino: float
    test_sharpe: float
    test_calmar: float
    test_profit_factor: float
    test_win_rate: float
    test_total_return_pct: float
    test_max_drawdown_pct: float
    test_trades: int
    # Per-bar pseudo-returns on the test slice — used by regime_decomp +
    # deflated_sharpe. Computed from equity-curve diffs on the test bars.
    test_returns: list[float] = field(default_factory=list)
    # First / last test-bar timestamps (ISO date string) — used by regime_decomp
    # to align labels.
    test_start_ts: str = ""
    test_end_ts: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_idx": self.window_idx,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "chosen_params": self.chosen_params,
            "train_metric": self.train_metric,
            "train_trades": self.train_trades,
            "test_sortino": self.test_sortino,
            "test_sharpe": self.test_sharpe,
            "test_calmar": self.test_calmar,
            "test_profit_factor": self.test_profit_factor,
            "test_win_rate": self.test_win_rate,
            "test_total_return_pct": self.test_total_return_pct,
            "test_max_drawdown_pct": self.test_max_drawdown_pct,
            "test_trades": self.test_trades,
            "test_returns": list(self.test_returns),
            "test_start_ts": self.test_start_ts,
            "test_end_ts": self.test_end_ts,
        }


@dataclass
class WalkforwardResult:
    """Outcome of one walk-forward run for one strategy class on one symbol."""

    strategy_cls: str
    symbol: str
    config: dict[str, Any]
    n_windows: int
    n_bars: int
    grid_size: int
    windows: list[WindowMetrics] = field(default_factory=list)

    # Aggregates across windows that produced ≥1 test trade.
    mean_test_sortino: float = 0.0
    median_test_sortino: float = 0.0
    std_test_sortino: float = 0.0
    mean_test_sharpe: float = 0.0
    mean_test_calmar: float = 0.0
    mean_test_total_return_pct: float = 0.0
    mean_test_win_rate: float = 0.0
    mean_test_profit_factor: float = 0.0
    aggregate_test_max_drawdown_pct: float = 0.0
    n_active_windows: int = 0  # windows with ≥1 trade
    # Coefficient of variation on test Sortino — high CV = unstable, likely overfit.
    test_sortino_cv: float = 0.0

    # Concatenated per-bar returns across test slices (in chronological order).
    # Used by regime_decomp + deflated_sharpe wrapper.
    concatenated_test_returns: list[float] = field(default_factory=list)
    concatenated_test_timestamps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_cls": self.strategy_cls,
            "symbol": self.symbol,
            "config": self.config,
            "n_windows": self.n_windows,
            "n_bars": self.n_bars,
            "grid_size": self.grid_size,
            "n_active_windows": self.n_active_windows,
            "mean_test_sortino": self.mean_test_sortino,
            "median_test_sortino": self.median_test_sortino,
            "std_test_sortino": self.std_test_sortino,
            "mean_test_sharpe": self.mean_test_sharpe,
            "mean_test_calmar": self.mean_test_calmar,
            "mean_test_total_return_pct": self.mean_test_total_return_pct,
            "mean_test_win_rate": self.mean_test_win_rate,
            "mean_test_profit_factor": self.mean_test_profit_factor,
            "aggregate_test_max_drawdown_pct": self.aggregate_test_max_drawdown_pct,
            "test_sortino_cv": self.test_sortino_cv,
            "windows": [w.to_dict() for w in self.windows],
            "concatenated_test_returns": list(self.concatenated_test_returns),
            "concatenated_test_timestamps": list(self.concatenated_test_timestamps),
        }


# ---------------------------------------------------------------------------
# Helpers — pure
# ---------------------------------------------------------------------------


def _bar_ts(bar: Any) -> str:
    """Return an ISO date string for a bar of any common shape."""
    if isinstance(bar, dict):
        ts = bar.get("date") or bar.get("ts") or ""
        if isinstance(ts, datetime):
            return ts.date().isoformat()
        return str(ts)[:10]
    ts = getattr(bar, "ts", None) or getattr(bar, "date", None)
    if isinstance(ts, datetime):
        return ts.date().isoformat()
    return str(ts)[:10] if ts is not None else ""


def _bar_close(bar: Any) -> float:
    if isinstance(bar, dict):
        return float(bar.get("close") or bar.get("Close") or 0.0)
    return float(getattr(bar, "close", 0.0))


def _equity_to_returns(equity_curve: list[tuple[str, float]]) -> list[float]:
    """Bar-to-bar returns from an equity curve."""
    out: list[float] = []
    for i in range(1, len(equity_curve)):
        prev = equity_curve[i - 1][1]
        curr = equity_curve[i][1]
        if prev > 0:
            out.append((curr - prev) / prev)
    return out


def _grid_combos(grid: ParameterGrid) -> list[dict[str, Any]]:
    """Stable enumeration of grid combos as dicts."""
    if not grid:
        return [{}]
    keys = list(grid.keys())
    vals = [list(grid[k]) for k in keys]
    return [dict(zip(keys, combo, strict=False)) for combo in itertools.product(*vals)]


def _select_metric_value(report: Any, metric: str) -> float:
    """Map metric name → numeric value from a strategies.BacktestEngine report."""
    if metric == "sortino":
        v = report.sortino
    elif metric == "sharpe":
        v = report.sharpe
    elif metric == "calmar":
        v = report.calmar
    elif metric == "profit_factor":
        v = report.profit_factor
    elif metric == "total_return":
        v = report.total_return_pct
    else:  # pragma: no cover — config.validate() blocks this
        v = report.sortino
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return float("-inf")
    return float(v)


def _params_sort_key(combo: dict[str, Any]) -> tuple:
    """Deterministic tie-break key for grid combos."""
    return (
        combo.get("rsi_period", 0),
        combo.get("sl_pct", 0.0),
        combo.get("tp_pct", 0.0),
        combo.get("composite_threshold", 0.0),
    )


def _build_params(combo: dict[str, Any], base: StrategyParams | None = None) -> StrategyParams:
    """Build a StrategyParams from a grid combo dict, falling back to defaults."""
    base = base or StrategyParams()
    kwargs: dict[str, Any] = {f.name: getattr(base, f.name) for f in _params_fields()}
    for k, v in combo.items():
        if k in kwargs:
            kwargs[k] = v
    return StrategyParams(**kwargs)


def _params_fields() -> list[Any]:
    from dataclasses import fields

    return list(fields(StrategyParams))


# ---------------------------------------------------------------------------
# Window enumeration — deterministic, stride-aware
# ---------------------------------------------------------------------------


def walkforward_windows(
    n_bars: int,
    config: WalkforwardConfig,
) -> list[WalkforwardWindow]:
    """Return the list of (train, test) windows for ``n_bars`` under ``config``.

    Pure / side-effect-free. The first window starts at index 0; each window's
    train slice is ``[train_start, train_end)``. After purge_bars are removed
    from the *end* of the train slice, the test slice is
    ``[test_start, test_end)`` where ``test_start = train_end + purge_bars``.

    Successive windows advance ``train_start`` by ``effective_advance()``.
    Embargo_bars are subtracted from the front of subsequent train slices to
    prevent leakage from the prior test slice. Windows that would overflow
    n_bars (``test_end > n_bars``) are dropped.
    """
    config.validate()
    if n_bars < config.train_bars + config.test_bars + config.purge_bars:
        return []

    advance = config.effective_advance()
    out: list[WalkforwardWindow] = []
    idx = 0
    train_start = 0
    while True:
        # Embargo: trim the front of the train slice if a previous test slice
        # ended within embargo_bars of train_start (only matters when overlap).
        emb_start = train_start
        if out and config.embargo_bars > 0:
            prev_test_end = out[-1].test_end
            emb_start = max(train_start, prev_test_end + config.embargo_bars)

        train_end = emb_start + config.train_bars
        test_start = train_end + config.purge_bars
        test_end = test_start + config.test_bars

        if test_end > n_bars:
            break
        if train_end - emb_start < config.train_bars:
            break  # embargo pushed us into infeasibility

        out.append(
            WalkforwardWindow(
                window_idx=idx,
                train_start=emb_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
            )
        )
        idx += 1
        train_start += advance

    return out


# ---------------------------------------------------------------------------
# Per-window evaluation — pure (consumes injected BacktestEngine instance)
# ---------------------------------------------------------------------------


def _slice_bars(bars: list[Any], start: int, end: int) -> list[Any]:
    """Return bars[start:end]; tolerant to dict-shaped bars."""
    return list(bars[start:end])


def _slice_aux(aux: Mapping[str, list[Any]] | None, start: int, end: int) -> dict[str, list[Any]]:
    """Slice each aux series the same way; preserve missing keys as []."""
    if not aux:
        return {}
    return {k: list(v[start:end]) for k, v in aux.items()}


def _evaluate_combo(
    *,
    strategy_cls: type[Strategy],
    combo: dict[str, Any],
    bars: list[Any],
    aux: Mapping[str, list[Any]] | None,
    bankroll: float,
    symbol: str,
) -> Any:
    """Run a single backtest for one (combo, slice). Returns the BacktestEngine
    SimpleNamespace report (sortino / sharpe / calmar / total_return_pct / etc).
    """
    params = _build_params(combo)
    engine = BacktestEngine(bankroll=bankroll)
    strat = strategy_cls(params)
    return engine.run(bars, strat, symbol, dict(aux or {}))


def _select_train_combo(
    *,
    strategy_cls: type[Strategy],
    grid: list[dict[str, Any]],
    train_bars: list[Any],
    aux: Mapping[str, list[Any]] | None,
    config: WalkforwardConfig,
) -> tuple[dict[str, Any], float, int, Any]:
    """Pick the best combo on the train slice. Returns (combo, metric, trades, report)."""
    best_combo: dict[str, Any] | None = None
    best_value = float("-inf")
    best_trades = 0
    best_report: Any = None

    for combo in grid:
        report = _evaluate_combo(
            strategy_cls=strategy_cls,
            combo=combo,
            bars=train_bars,
            aux=aux,
            bankroll=config.bankroll,
            symbol=config.symbol,
        )
        if report.total_trades < config.min_train_trades:
            value = float("-inf")
        else:
            value = _select_metric_value(report, config.selection_metric)

        if best_combo is None or _is_better(
            value, report, best_value, best_report, config.selection_metric
        ):
            best_combo = combo
            best_value = value
            best_trades = report.total_trades
            best_report = report
        elif (
            value == best_value
            and (report.total_trades, _params_sort_key(combo))
            < (best_trades, _params_sort_key(best_combo))
        ):
            # Lexicographic tie-break to keep the result deterministic.
            best_combo = combo
            best_value = value
            best_trades = report.total_trades
            best_report = report

    assert best_combo is not None  # grid is always non-empty
    return best_combo, best_value, best_trades, best_report


def _is_better(value: float, report: Any, best_value: float, best_report: Any, metric: str) -> bool:
    """Strict `>` on the selection metric, with ``-inf`` semantics for invalid."""
    if best_report is None:
        return True
    if value > best_value:
        return True
    if value < best_value:
        return False
    # tied — prefer the report with more trades
    return report.total_trades > getattr(best_report, "total_trades", 0)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def run_walkforward(
    strategy_cls: type[Strategy],
    bars: list[Any],
    *,
    grid: ParameterGrid | None = None,
    aux: Mapping[str, list[Any]] | None = None,
    config: WalkforwardConfig | None = None,
) -> WalkforwardResult:
    """Run walk-forward backtest over ``bars`` for one strategy class.

    The function never modifies upstream modules. It instantiates ``strategy_cls``
    once per (window, combo) pair on the train slice, picks the best combo by
    ``config.selection_metric``, and then evaluates that frozen combo on the
    test slice. Per-window OOS metrics are returned along with the chosen
    parameters and the per-bar test-slice returns.

    Args:
        strategy_cls: Subclass of ``lib.analytics.strategies.Strategy``.
        bars:         Pre-fetched OHLCV bars (the engine never touches the network).
        grid:         Parameter grid mapping (defaults to strategies.PARAM_GRID).
        aux:          Auxiliary series (e.g., {"btc": btc_bars, "spy": spy_bars}).
        config:       WalkforwardConfig; defaults are 90/30/30 train/test/advance.

    Returns:
        ``WalkforwardResult`` with per-window metrics and aggregates.
    """
    cfg = config or WalkforwardConfig()
    cfg.validate()

    grid_dict: ParameterGrid = grid if grid is not None else DEFAULT_PARAM_GRID
    grid_list = _grid_combos(grid_dict)
    if not grid_list:
        grid_list = [{}]
    n_bars = len(bars)
    windows = walkforward_windows(n_bars, cfg)

    result = WalkforwardResult(
        strategy_cls=strategy_cls.__name__,
        symbol=cfg.symbol,
        config={
            "train_bars": cfg.train_bars,
            "test_bars": cfg.test_bars,
            "advance_bars": cfg.effective_advance(),
            "purge_bars": cfg.purge_bars,
            "embargo_bars": cfg.embargo_bars,
            "selection_metric": cfg.selection_metric,
            "bankroll": cfg.bankroll,
            "min_train_trades": cfg.min_train_trades,
        },
        n_windows=len(windows),
        n_bars=n_bars,
        grid_size=len(grid_list),
    )

    if not windows:
        return result

    for w in windows:
        train_slice = _slice_bars(bars, w.train_start, w.train_end)
        test_slice = _slice_bars(bars, w.test_start, w.test_end)
        # The aux series must include bars covering BOTH train and test windows
        # so that strategies that look back through aux do not lose history.
        # We slice from 0 → train_end for train selection and from 0 → test_end
        # for the post-selection eval so aux mirrors the price series the engine
        # would otherwise see in a full-bar run.
        train_aux = _slice_aux(aux, 0, w.train_end)

        combo, train_metric, train_trades, _ = _select_train_combo(
            strategy_cls=strategy_cls,
            grid=grid_list,
            train_bars=train_slice,
            aux=train_aux,
            config=cfg,
        )

        # Evaluate the chosen combo on the test slice. To give the strategy
        # access to history it has already "seen", we pass bars[0:test_end]
        # and trim the equity curve to just the test region. This keeps the
        # signal generator's lookback intact while metric computation is
        # restricted to test-period bars.
        full_to_test = _slice_bars(bars, 0, w.test_end)
        test_aux_full = _slice_aux(aux, 0, w.test_end)
        full_report = _evaluate_combo(
            strategy_cls=strategy_cls,
            combo=combo,
            bars=full_to_test,
            aux=test_aux_full,
            bankroll=cfg.bankroll,
            symbol=cfg.symbol,
        )

        test_metrics = _isolate_test_metrics(
            full_report,
            test_start_idx=w.test_start,
            test_end_idx=w.test_end,
            initial_capital=cfg.bankroll,
        )

        wm = WindowMetrics(
            window_idx=w.window_idx,
            train_start=w.train_start,
            train_end=w.train_end,
            test_start=w.test_start,
            test_end=w.test_end,
            chosen_params=dict(combo),
            train_metric=train_metric,
            train_trades=int(train_trades),
            test_sortino=test_metrics["sortino"],
            test_sharpe=test_metrics["sharpe"],
            test_calmar=test_metrics["calmar"],
            test_profit_factor=test_metrics["profit_factor"],
            test_win_rate=test_metrics["win_rate"],
            test_total_return_pct=test_metrics["total_return_pct"],
            test_max_drawdown_pct=test_metrics["max_drawdown_pct"],
            test_trades=int(test_metrics["trades"]),
            test_returns=test_metrics["returns"],
            test_start_ts=_bar_ts(test_slice[0]) if test_slice else "",
            test_end_ts=_bar_ts(test_slice[-1]) if test_slice else "",
        )
        result.windows.append(wm)
        result.concatenated_test_returns.extend(wm.test_returns)
        # Use the test slice timestamps trimmed to len(test_returns); equity
        # has len(returns) + 1 entries, returns are the diffs starting at
        # bar[1] of the test window.
        slice_ts = [_bar_ts(b) for b in test_slice[1 : 1 + len(wm.test_returns)]]
        result.concatenated_test_timestamps.extend(slice_ts)

    _aggregate(result)
    return result


def _isolate_test_metrics(
    full_report: Any,
    *,
    test_start_idx: int,
    test_end_idx: int,
    initial_capital: float,
) -> dict[str, Any]:
    """Reduce a full-bar BacktestEngine report into a test-slice metric set.

    The inner engine (``strategies.BacktestEngine.run``) returns a SimpleNamespace
    with .report (a dict from BacktestResult.to_dict()) carrying trades and
    equity_curve. We:
      1. Slice the equity curve to the test region by index.
      2. Compute returns / sharpe / sortino / max_dd over that slice only.
      3. Filter trades whose entry_ts falls inside [test_start, test_end).
    """
    report_dict = full_report.report if isinstance(full_report.report, dict) else {}
    equity_curve = report_dict.get("equity_curve") or []
    trades = report_dict.get("trades") or []

    # Equity curve has one entry per bar in the original full slice. We take
    # entries [test_start_idx .. test_end_idx-1] inclusive.
    test_curve = list(equity_curve[test_start_idx:test_end_idx])
    if len(test_curve) < 2:
        return _zero_metrics()

    eq_values = [float(v[1]) if isinstance(v, list | tuple) else float(v) for v in test_curve]
    returns = [
        (eq_values[i] - eq_values[i - 1]) / eq_values[i - 1]
        for i in range(1, len(eq_values))
        if eq_values[i - 1] > 0
    ]
    sharpe = sharpe_ratio(returns)
    sortino = sortino_ratio(returns)
    dd = max_drawdown_pct(eq_values)

    # Filter trades whose entry_ts falls in the test slice. Trade entry_ts is
    # an ISO datetime string from backtest_engine._close.
    test_trades = []
    # Build a date set for the test region using equity_curve dates.
    test_dates = {row[0] if isinstance(row, list | tuple) else "" for row in test_curve}
    for t in trades:
        entry = t.get("entry_ts") or t.get("entry_date") or ""
        date_part = str(entry)[:10]
        if date_part in test_dates:
            test_trades.append(t)

    pnl = [float(t.get("pnl_usd", t.get("pnl", 0.0))) for t in test_trades]
    wins = [v for v in pnl if v > 0]
    losses = [v for v in pnl if v < 0]
    win_rate = (len(wins) / len(pnl)) if pnl else 0.0
    total_pnl = sum(pnl)
    total_wins = sum(wins)
    total_losses = abs(sum(losses))
    profit_factor = (total_wins / total_losses) if total_losses > 0 else 0.0
    if total_losses == 0 and total_wins > 0:
        profit_factor = 999.0
    total_return_pct = (total_pnl / initial_capital) if initial_capital > 0 else 0.0
    calmar = (total_return_pct * 100.0) / dd if dd > 0 else 0.0

    return {
        "sortino": float(sortino),
        "sharpe": float(sharpe),
        "calmar": float(calmar),
        "profit_factor": float(min(profit_factor, 999.0)),
        "win_rate": float(win_rate),
        "total_return_pct": float(total_return_pct),
        "max_drawdown_pct": float(dd / 100.0),  # to fraction (mirror BacktestEngine projection)
        "trades": len(test_trades),
        "returns": returns,
    }


def _zero_metrics() -> dict[str, Any]:
    return {
        "sortino": 0.0,
        "sharpe": 0.0,
        "calmar": 0.0,
        "profit_factor": 0.0,
        "win_rate": 0.0,
        "total_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "trades": 0,
        "returns": [],
    }


def _aggregate(result: WalkforwardResult) -> None:
    """Compute aggregates across all populated windows."""
    if not result.windows:
        return

    active = [w for w in result.windows if w.test_trades > 0] or list(result.windows)
    sortinos = [w.test_sortino for w in active]
    sharpes = [w.test_sharpe for w in active]
    calmars = [w.test_calmar for w in active]
    pfs = [w.test_profit_factor for w in active]
    wrs = [w.test_win_rate for w in active]
    rets = [w.test_total_return_pct for w in active]
    dds = [w.test_max_drawdown_pct for w in active]

    result.n_active_windows = len(active)
    result.mean_test_sortino = round(statistics.fmean(sortinos), 4)
    result.median_test_sortino = round(statistics.median(sortinos), 4)
    result.std_test_sortino = round(
        statistics.pstdev(sortinos) if len(sortinos) > 1 else 0.0, 4
    )
    result.mean_test_sharpe = round(statistics.fmean(sharpes), 4)
    result.mean_test_calmar = round(statistics.fmean(calmars), 4)
    result.mean_test_total_return_pct = round(statistics.fmean(rets), 6)
    result.mean_test_win_rate = round(statistics.fmean(wrs), 4)
    result.mean_test_profit_factor = round(min(statistics.fmean(pfs), 999.0), 4)
    result.aggregate_test_max_drawdown_pct = round(max(dds), 6)

    raw_cv = (result.std_test_sortino / abs(result.mean_test_sortino)) if result.mean_test_sortino != 0 else float("inf")
    result.test_sortino_cv = (
        round(raw_cv, 4) if math.isfinite(raw_cv) else 999.0
    )


# ---------------------------------------------------------------------------
# Re-exports for callers that want to construct a synthetic Bar
# ---------------------------------------------------------------------------

# These let callers (services/walkforward/build.py, tests) import Bar from this
# module without re-importing backtest_engine. Read-only re-export.
Bar = EngineBar


# ---------------------------------------------------------------------------
# Convenience: enumerate bar indices for a window (used by regime_decomp)
# ---------------------------------------------------------------------------


def window_test_indices(window: WalkforwardWindow) -> list[int]:
    """Return the absolute bar indices belonging to the test slice."""
    return list(range(window.test_start, window.test_end))


def windows_summary(windows: Iterable[WalkforwardWindow]) -> list[dict[str, int]]:
    """Stable JSON-serializable summary of a window list."""
    return [w.to_dict() for w in windows]
