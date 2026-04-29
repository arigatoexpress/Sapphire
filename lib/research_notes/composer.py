"""Research note composition from local backtest, sweep, and context data."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.core.provenance import sha256_canonical
from lib.research_notes.model import ResearchNote

VERSION = "0.1.0"
GENERATOR = "lib.research_notes.composer"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "research-note"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct(value: Any) -> str:
    number = _float(value)
    if abs(number) <= 1:
        number *= 100
    return f"{number:.1f}%"


def _money(value: Any) -> str:
    return f"${_float(value):,.0f}"


def _best_row(backtest_summary: dict[str, Any], leaderboard: dict[str, Any]) -> dict[str, Any]:
    rows = leaderboard.get("rows") or []
    if rows:
        return dict(rows[0])
    best = backtest_summary.get("best_per_symbol") or []
    if best:
        return dict(best[0])
    return {}


def _source_names(paths: list[str | Path] | tuple[str | Path, ...]) -> list[str]:
    return [str(path) for path in paths if str(path)]


def compose_research_note(
    *,
    backtest_summary: dict[str, Any],
    leaderboard: dict[str, Any],
    performance: dict[str, Any],
    timeseries: dict[str, Any],
    context: dict[str, Any] | None = None,
    strategy_slug: str | None = None,
    as_of_date: str | None = None,
    generated_at: str | None = None,
    source_paths: list[str | Path] | tuple[str | Path, ...] = (),
) -> ResearchNote:
    """Compose a buyer-readable research note without external calls."""
    context = dict(context or {})
    generated = generated_at or _now()
    date = as_of_date or generated[:10]
    best = _best_row(backtest_summary, leaderboard)
    strategy_name = str(
        best.get("strategy_name")
        or best.get("strategy_cls")
        or context.get("strategy_name")
        or "Sapphire Composite"
    )
    slug = strategy_slug or _slug(strategy_name)
    symbol = str(best.get("symbol") or context.get("symbol") or "multi-asset")
    metric_name = str(leaderboard.get("metric") or "sortino")
    metric_value = best.get(metric_name)
    overall = performance.get("overall") or {}
    trade_count = performance.get("trade_count") or overall.get("trades") or 0
    total_return = best.get("total_return_pct")
    win_rate = best.get("win_rate") if best else overall.get("win_rate")
    total_pnl = overall.get("total_pnl_usd")
    drawdown = best.get("max_drawdown_pct") or (timeseries.get("max_drawdown") or {}).get("pct")
    note_id = f"{date}/{slug}"

    thesis = (
        f"{strategy_name} is ready for research-note packaging because the latest local sweep "
        f"identifies {symbol} as the clearest candidate, ranked by {metric_name}="
        f"{metric_value if metric_value is not None else 'n/a'}. The live trading conclusion is "
        "intentionally absent: this memo is an auditable research artifact for evaluating whether "
        "the strategy evidence is coherent enough for operator review."
    )
    counter = (
        "The counter-thesis is that a sweep leader can be overfit, stale, or supported by too few "
        "closed trades. A buyer should treat this as evidence of process maturity, not proof that "
        "future market returns will resemble the historical sample."
    )
    key_metrics = {
        "strategy": strategy_name,
        "symbol": symbol,
        "rank_metric": metric_name,
        "rank_metric_value": metric_value,
        "total_return_pct": total_return,
        "win_rate": win_rate,
        "total_pnl_usd": total_pnl,
        "trade_count": trade_count,
        "max_drawdown_pct": drawdown,
        "source_file": backtest_summary.get("source_file") or leaderboard.get("source_file"),
    }
    evidence = [
        f"Backtest coverage: {backtest_summary.get('total_backtests', 0)} local strategy evaluations.",
        f"Leaderboard filter retained {leaderboard.get('filtered_rows', 0)} rows from {leaderboard.get('total_rows', 0)} candidates.",
        f"Observed performance stream contains {trade_count} closed trades and {_money(total_pnl)} total PnL.",
        f"Top row reports total_return={_pct(total_return)} and win_rate={_pct(win_rate)}.",
    ]
    if context.get("market_regime"):
        evidence.append(f"Context regime tag: {context['market_regime']}.")
    invalidators = [
        "Invalidate the note if the next completed sweep changes the top strategy or symbol.",
        "Invalidate if the retained leaderboard row count falls below the configured minimum-trade filter.",
        "Invalidate if realized closed-trade performance diverges from the sweep direction over the next review window.",
        "Invalidate if source artifacts are missing a provenance envelope or cannot be reproduced locally.",
    ]
    next_steps = [
        "Compare the next sweep against this note before changing any operator-facing recommendation.",
        "Attach this PDF and its envelope to the diligence packet only with the research-only caveat intact.",
        "Keep execution, sizing, Telegram delivery, and customer data out of this pipeline.",
    ]
    caveat = (
        "Research-only artifact. This note does not place trades, size positions, send Telegram "
        "messages, include customer data, or authorize live execution."
    )
    chart_specs = [
        {
            "kind": "equity_curve",
            "title": "Equity Curve",
            "description": "Closed-trade equity path from local paper/performance data.",
        }
    ]
    payload_for_hash = {
        "backtest_summary": backtest_summary,
        "leaderboard": leaderboard,
        "performance": performance,
        "timeseries": timeseries,
        "context": context,
    }
    provenance = {
        "generator": GENERATOR,
        "version": VERSION,
        "generated_at": generated,
        "input_hash": sha256_canonical(payload_for_hash),
        "source_paths": _source_names(source_paths),
        "mode": "offline",
    }
    return ResearchNote(
        note_id=note_id,
        as_of_date=date,
        strategy_slug=slug,
        strategy_name=strategy_name,
        title=f"{strategy_name} Research Note",
        subtitle=f"{date} | {symbol} | local sweep and paper-performance evidence",
        thesis=thesis,
        counter_thesis=counter,
        key_metrics=key_metrics,
        backtest_summary=backtest_summary,
        performance_summary=performance,
        context=context,
        chart_specs=chart_specs,
        evidence=evidence,
        invalidators=invalidators,
        next_steps=next_steps,
        caveat=caveat,
        sources=_source_names(source_paths),
        generated_at=generated,
        provenance=provenance,
    )
