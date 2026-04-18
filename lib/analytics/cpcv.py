"""Combinatorial Purged Cross-Validation (CPCV) for time-series backtesting.

Prevents overfitting in parameter sweeps by generating all C(N, k) train/test
splits with purging (removes train observations whose label window overlaps with
the test period) and embargoing (removes observations immediately after each
test set to prevent leakage from delayed market reactions).

Reference: López de Prado, "Advances in Financial Machine Learning", Ch. 12.
"""

from __future__ import annotations

import logging
import math
import statistics
from collections.abc import Generator
from dataclasses import dataclass, field
from itertools import combinations
from typing import TYPE_CHECKING, Any

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from lib.analytics.backtest_engine import Bar, SignalFn, Trade


# ── Data structures ────────────────────────────────────────────────────────────


@dataclass
class CPCVSplitMetrics:
    split_idx: int
    test_groups: tuple[int, ...]
    n_test_bars: int
    n_train_bars: int
    n_trades: int
    sharpe: float
    sortino: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float


@dataclass
class CPCVResult:
    symbol: str
    n_groups: int
    n_test_groups: int
    n_splits: int
    splits: list[CPCVSplitMetrics] = field(default_factory=list)

    # Aggregated OOS statistics across all splits
    mean_sharpe: float = 0.0
    std_sharpe: float = 0.0
    min_sharpe: float = 0.0
    mean_sortino: float = 0.0
    std_sortino: float = 0.0
    min_sortino: float = 0.0
    mean_max_drawdown: float = 0.0
    mean_win_rate: float = 0.0
    mean_profit_factor: float = 0.0
    # Coefficient of variation of Sharpe: std / |mean|. Higher → more overfitting risk.
    sharpe_cv: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "n_groups": self.n_groups,
            "n_test_groups": self.n_test_groups,
            "n_splits": self.n_splits,
            "mean_sharpe": self.mean_sharpe,
            "std_sharpe": self.std_sharpe,
            "min_sharpe": self.min_sharpe,
            "mean_sortino": self.mean_sortino,
            "std_sortino": self.std_sortino,
            "min_sortino": self.min_sortino,
            "mean_max_drawdown": self.mean_max_drawdown,
            "mean_win_rate": self.mean_win_rate,
            "mean_profit_factor": self.mean_profit_factor,
            "sharpe_cv": self.sharpe_cv,
            "splits": [
                {
                    "split_idx": s.split_idx,
                    "test_groups": list(s.test_groups),
                    "n_test_bars": s.n_test_bars,
                    "n_train_bars": s.n_train_bars,
                    "n_trades": s.n_trades,
                    "sharpe": s.sharpe,
                    "sortino": s.sortino,
                    "max_drawdown_pct": s.max_drawdown_pct,
                    "win_rate": s.win_rate,
                    "profit_factor": s.profit_factor,
                }
                for s in self.splits
            ],
        }


# ── Split generation ───────────────────────────────────────────────────────────


def _group_bounds(n_samples: int, n_groups: int) -> list[tuple[int, int]]:
    """Return (start, end) index pairs for each group. Last group absorbs remainder."""
    group_size = n_samples // n_groups
    bounds: list[tuple[int, int]] = []
    for g in range(n_groups):
        start = g * group_size
        end = (g + 1) * group_size if g < n_groups - 1 else n_samples
        bounds.append((start, end))
    return bounds


def cpcv_splits(
    n_samples: int,
    n_groups: int = 6,
    n_test_groups: int = 2,
    purge_pct: float = 0.01,
    embargo_pct: float = 0.02,
) -> Generator[tuple[list[int], list[int]], None, None]:
    """Yield (train_indices, test_indices) for all C(n_groups, n_test_groups) splits.

    Purging removes train samples within ``purge_window`` bars of each test group's
    start. Embargoing removes train samples within ``embargo_window`` bars after each
    test group's end, preventing leakage from delayed market reactions.

    Args:
        n_samples: Total number of observations.
        n_groups: Number of data groups (folds). Default 6.
        n_test_groups: Number of groups combined as the test set. Default 2.
        purge_pct: Fraction of n_samples purged before each test boundary.
        embargo_pct: Fraction of n_samples embargoed after each test boundary.

    Yields:
        (train_indices, test_indices) — both sorted, non-overlapping.
    """
    if n_test_groups >= n_groups:
        raise ValueError(f"n_test_groups ({n_test_groups}) must be < n_groups ({n_groups})")
    if n_samples < n_groups:
        raise ValueError(f"n_samples ({n_samples}) must be >= n_groups ({n_groups})")

    purge_window = max(1, int(n_samples * purge_pct))
    embargo_window = max(1, int(n_samples * embargo_pct))
    bounds = _group_bounds(n_samples, n_groups)

    for test_combo in combinations(range(n_groups), n_test_groups):
        test_set: set[int] = set()
        for g in test_combo:
            s, e = bounds[g]
            test_set.update(range(s, e))

        train_set: set[int] = set(range(n_samples)) - test_set

        for g in test_combo:
            t_start, t_end = bounds[g]
            # Purge: remove train samples adjacent to test group start
            for j in range(max(0, t_start - purge_window), t_start):
                train_set.discard(j)
            # Embargo: remove train samples immediately after test group end
            for j in range(t_end, min(n_samples, t_end + embargo_window)):
                train_set.discard(j)

        yield sorted(train_set), sorted(list(test_set))


# ── Per-split metric computation ───────────────────────────────────────────────


def _trade_metrics(
    trades: list[Trade],
    initial_capital: float = 10_000.0,
) -> dict[str, float]:
    """Compute Sharpe, Sortino, max-DD, win rate, profit factor from a trade list."""
    from lib.analytics.backtest_engine import max_drawdown_pct, sharpe_ratio, sortino_ratio

    if not trades:
        return {
            "sharpe": 0.0, "sortino": 0.0, "max_drawdown_pct": 0.0,
            "win_rate": 0.0, "profit_factor": 0.0, "n_trades": 0.0,
        }

    capital = initial_capital
    equity: list[float] = [capital]
    for t in trades:
        capital += t.pnl_usd
        equity.append(max(0.01, capital))

    returns = [(equity[i] - equity[i - 1]) / equity[i - 1] for i in range(1, len(equity))]
    wins = [t for t in trades if t.pnl_usd > 0]
    losses = [t for t in trades if t.pnl_usd < 0]
    total_wins = sum(t.pnl_usd for t in wins)
    total_losses = abs(sum(t.pnl_usd for t in losses))

    return {
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "max_drawdown_pct": max_drawdown_pct(equity),
        "win_rate": len(wins) / len(trades) * 100,
        "profit_factor": (total_wins / total_losses) if total_losses > 0 else 999.0,
        "n_trades": float(len(trades)),
    }


# ── CPCV backtest runner ───────────────────────────────────────────────────────


def run_cpcv_backtest(
    symbol: str,
    bars: list[Bar] | None = None,
    days: int = 90,
    signal_fn: SignalFn | None = None,
    initial_capital: float = 10_000.0,
    position_size_pct: float = 0.10,
    n_groups: int = 6,
    n_test_groups: int = 2,
    purge_pct: float = 0.01,
    embargo_pct: float = 0.02,
) -> CPCVResult:
    """Run a CPCV-validated backtest returning OOS metric distributions.

    Runs a single full backtest on all bars, then for each of the
    C(n_groups, n_test_groups) splits, filters trades whose entry falls in the
    test period and computes OOS metrics independently. The distribution of
    Sharpe/Sortino across splits quantifies overfitting risk: a high
    ``sharpe_cv`` (coefficient of variation) indicates the strategy is fragile
    and likely overfit to specific market conditions.

    Args:
        symbol: Ticker symbol.
        bars: Pre-fetched bar list. Fetched via yfinance if None.
        days: History window used when bars is None.
        signal_fn: Signal generator. Defaults to default_rsi_signal.
        initial_capital: Starting capital for metric computation.
        position_size_pct: Fraction of capital per trade.
        n_groups: N in C(N, k). Default 6 → C(6,2)=15 splits.
        n_test_groups: k in C(N, k). Default 2.
        purge_pct: Fraction of samples purged before each test boundary.
        embargo_pct: Fraction of samples embargoed after each test boundary.

    Returns:
        CPCVResult with per-split metrics and aggregate OOS statistics.
    """
    from lib.analytics.backtest_engine import (
        default_rsi_signal,
        fetch_ohlcv,
        run_backtest,
    )

    if bars is None:
        bars = fetch_ohlcv(symbol, days=days)

    if signal_fn is None:
        signal_fn = default_rsi_signal

    n_bars = len(bars)
    min_bars = n_groups * 4
    if n_bars < min_bars:
        log.warning(
            "CPCV: only %d bars for %d groups (need %d) — returning empty result",
            n_bars, n_groups, min_bars,
        )
        return CPCVResult(
            symbol=symbol, n_groups=n_groups, n_test_groups=n_test_groups, n_splits=0,
        )

    # Single full backtest — trades contain entry timestamps we'll filter by split
    full_result = run_backtest(
        symbol, bars=bars, signal_fn=signal_fn,
        initial_capital=initial_capital,
        position_size_pct=position_size_pct,
    )

    # Map ISO date string → bar index for O(1) trade-to-split assignment
    date_to_idx: dict[str, int] = {
        bar.ts.isoformat()[:10]: i for i, bar in enumerate(bars)
    }

    bounds = _group_bounds(n_bars, n_groups)
    purge_window = max(1, int(n_bars * purge_pct))
    embargo_window = max(1, int(n_bars * embargo_pct))

    split_results: list[CPCVSplitMetrics] = []

    for split_idx, test_combo in enumerate(combinations(range(n_groups), n_test_groups)):
        test_set: set[int] = set()
        for g in test_combo:
            s, e = bounds[g]
            test_set.update(range(s, e))

        train_set: set[int] = set(range(n_bars)) - test_set
        for g in test_combo:
            t_start, t_end = bounds[g]
            for j in range(max(0, t_start - purge_window), t_start):
                train_set.discard(j)
            for j in range(t_end, min(n_bars, t_end + embargo_window)):
                train_set.discard(j)

        # Filter trades whose entry bar falls in this test period
        test_trades = [
            t for t in full_result.trades
            if date_to_idx.get(str(t.entry_ts)[:10]) in test_set
        ]

        m = _trade_metrics(test_trades, initial_capital)
        split_results.append(CPCVSplitMetrics(
            split_idx=split_idx,
            test_groups=test_combo,
            n_test_bars=len(test_set),
            n_train_bars=len(train_set),
            n_trades=int(m["n_trades"]),
            sharpe=round(m["sharpe"], 3),
            sortino=round(m["sortino"], 3),
            max_drawdown_pct=round(m["max_drawdown_pct"], 3),
            win_rate=round(m["win_rate"], 2),
            profit_factor=round(min(m["profit_factor"], 999.0), 3),
        ))

    # Aggregate across splits that had at least one trade
    active = [s for s in split_results if s.n_trades > 0] or split_results
    sharpes = [s.sharpe for s in active] or [0.0]
    sortinos = [s.sortino for s in active] or [0.0]
    dds = [s.max_drawdown_pct for s in active] or [0.0]
    wrs = [s.win_rate for s in active] or [0.0]
    pfs = [s.profit_factor for s in active] or [0.0]

    mean_sharpe = statistics.fmean(sharpes)
    std_sharpe = statistics.pstdev(sharpes) if len(sharpes) > 1 else 0.0
    raw_cv = (std_sharpe / abs(mean_sharpe)) if mean_sharpe != 0 else float("inf")
    sharpe_cv = round(raw_cv, 3) if math.isfinite(raw_cv) else 999.0

    return CPCVResult(
        symbol=symbol,
        n_groups=n_groups,
        n_test_groups=n_test_groups,
        n_splits=len(split_results),
        splits=split_results,
        mean_sharpe=round(mean_sharpe, 3),
        std_sharpe=round(std_sharpe, 3),
        min_sharpe=round(min(sharpes), 3),
        mean_sortino=round(statistics.fmean(sortinos), 3),
        std_sortino=round(statistics.pstdev(sortinos) if len(sortinos) > 1 else 0.0, 3),
        min_sortino=round(min(sortinos), 3),
        mean_max_drawdown=round(statistics.fmean(dds), 3),
        mean_win_rate=round(statistics.fmean(wrs), 2),
        mean_profit_factor=round(min(statistics.fmean(pfs), 999.0), 3),
        sharpe_cv=sharpe_cv,
    )


__all__ = [
    "CPCVResult",
    "CPCVSplitMetrics",
    "cpcv_splits",
    "run_cpcv_backtest",
]
