"""Self-optimization loop — nightly sweep over strategy params using the backtester.

Walks a small grid of (score_min, position_size_pct) combinations for each
symbol and picks the Pareto-dominant one by Sharpe (tiebreak: min drawdown).
Writes proposals to ``data/optimization/proposals.jsonl`` — the human/operator
accepts or rejects before anything is applied.

NEVER writes back into env/config itself. Proposals are passive recommendations.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from lib.analytics.backtest_engine import (
        BacktestResult,
        default_rsi_signal,
        fetch_ohlcv,
        run_backtest,
    )
except ImportError:
    from backtest_engine import (  # type: ignore
        BacktestResult,
        default_rsi_signal,
        fetch_ohlcv,
        run_backtest,
    )

log = logging.getLogger(__name__)

PROPOSALS_FILE = Path.home() / "Code" / "Sapphire" / "data" / "optimization" / "proposals.jsonl"


@dataclass
class ParamCell:
    score_min: float
    position_size_pct: float


@dataclass
class Proposal:
    symbol: str
    generated_at: str
    window_days: int
    current: dict[str, Any]
    recommended: dict[str, Any]
    recommended_metrics: dict[str, Any]
    delta: dict[str, float]
    grid_results: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _grid() -> list[ParamCell]:
    score_mins = [0.0, 40.0, 55.0, 70.0]
    size_pcts = [0.05, 0.10, 0.15]
    return [ParamCell(s, p) for s, p in itertools.product(score_mins, size_pcts)]


def optimize_symbol(
    symbol: str,
    days: int = 90,
    current: ParamCell | None = None,
) -> Proposal:
    """Run the backtest grid and return a proposal. Does NOT apply the change."""
    current = current or ParamCell(score_min=0.0, position_size_pct=0.10)
    bars = fetch_ohlcv(symbol, days=days)

    results: list[tuple[ParamCell, BacktestResult]] = []
    for cell in _grid():
        r = run_backtest(
            symbol,
            bars=bars,
            days=days,
            signal_fn=default_rsi_signal,
            position_size_pct=cell.position_size_pct,
            score_min=cell.score_min,
        )
        results.append((cell, r))

    base_r = run_backtest(
        symbol,
        bars=bars,
        days=days,
        signal_fn=default_rsi_signal,
        position_size_pct=current.position_size_pct,
        score_min=current.score_min,
    )

    # Rank: Sharpe desc, then min max-drawdown
    ranked = sorted(
        results,
        key=lambda rr: (rr[1].sharpe, -rr[1].max_drawdown_pct, rr[1].win_rate),
        reverse=True,
    )
    best_cell, best_r = ranked[0]

    notes: list[str] = []
    if best_r.sharpe <= base_r.sharpe and best_r.total_return_pct <= base_r.total_return_pct:
        notes.append("no_improvement_over_current")
    if best_r.bars < 20:
        notes.append("insufficient_bars")
    if len(best_r.trades) < 3:
        notes.append("low_trade_count")

    return Proposal(
        symbol=symbol,
        generated_at=datetime.now(UTC).isoformat(),
        window_days=days,
        current={
            "score_min": current.score_min,
            "position_size_pct": current.position_size_pct,
            "metrics": {
                "sharpe": base_r.sharpe,
                "sortino": base_r.sortino,
                "total_return_pct": base_r.total_return_pct,
                "max_drawdown_pct": base_r.max_drawdown_pct,
                "win_rate": base_r.win_rate,
                "trades": len(base_r.trades),
            },
        },
        recommended={
            "score_min": best_cell.score_min,
            "position_size_pct": best_cell.position_size_pct,
        },
        recommended_metrics={
            "sharpe": best_r.sharpe,
            "sortino": best_r.sortino,
            "total_return_pct": best_r.total_return_pct,
            "max_drawdown_pct": best_r.max_drawdown_pct,
            "win_rate": best_r.win_rate,
            "trades": len(best_r.trades),
        },
        delta={
            "sharpe": round(best_r.sharpe - base_r.sharpe, 3),
            "return_pct": round(best_r.total_return_pct - base_r.total_return_pct, 3),
            "drawdown_pct": round(best_r.max_drawdown_pct - base_r.max_drawdown_pct, 3),
        },
        grid_results=[
            {
                "score_min": c.score_min,
                "position_size_pct": c.position_size_pct,
                "sharpe": r.sharpe,
                "return_pct": r.total_return_pct,
                "dd_pct": r.max_drawdown_pct,
                "trades": len(r.trades),
            }
            for c, r in results
        ],
        notes=notes,
    )


def save_proposal(proposal: Proposal, path: Path | None = None) -> Path:
    path = path or PROPOSALS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(asdict(proposal), default=str) + "\n")
    return path


def run_sweep(
    symbols: list[str],
    days: int = 90,
    persist: bool = True,
    path: Path | None = None,
) -> list[Proposal]:
    """Optimize a list of symbols and optionally persist proposals."""
    out: list[Proposal] = []
    for sym in symbols:
        try:
            p = optimize_symbol(sym, days=days)
        except Exception as e:
            log.warning("optimize %s failed: %s", sym, e)
            continue
        out.append(p)
        if persist:
            try:
                save_proposal(p, path=path)
            except Exception as e:
                log.warning("persist proposal for %s failed: %s", sym, e)
    return out


def load_recent_proposals(limit: int = 20, path: Path | None = None) -> list[dict]:
    path = path or PROPOSALS_FILE
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()[-limit:]
    out: list[dict] = []
    for line in lines:
        with contextlib.suppress(json.JSONDecodeError):
            out.append(json.loads(line))
    return list(reversed(out))


__all__ = [
    "ParamCell",
    "Proposal",
    "optimize_symbol",
    "save_proposal",
    "run_sweep",
    "load_recent_proposals",
]


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", default="BTC-USD,ETH-USD,SOL-USD")
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    proposals = run_sweep(
        args.symbols.split(","),
        days=args.days,
        persist=not args.dry_run,
    )
    for p in proposals:
        print(f"\n{p.symbol}:")
        print(f"  current:     {p.current['metrics']}")
        print(f"  recommended: {p.recommended} → {p.recommended_metrics}")
        print(f"  delta:       {p.delta}")
        if p.notes:
            print(f"  notes:       {', '.join(p.notes)}")
