"""Research notes orchestration helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.analytics import backtest_results, strategy_performance
from lib.core.provenance import sidecar_path
from lib.research_notes.composer import compose_research_note
from lib.research_notes.model import ResearchNote
from lib.research_notes.renderer import render_pdf

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "research_notes"


def _date() -> str:
    return datetime.now(UTC).date().isoformat()


def _output_path(output_root: Path, as_of_date: str, strategy_slug: str) -> Path:
    return output_root / as_of_date / strategy_slug / "research-note.pdf"


def compose_note(
    *,
    backtest_summary_data: dict[str, Any] | None = None,
    leaderboard_data: dict[str, Any] | None = None,
    performance_data: dict[str, Any] | None = None,
    timeseries_data: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    strategy_slug: str | None = None,
    as_of_date: str | None = None,
    generated_at: str | None = None,
) -> ResearchNote:
    """Compose a note from provided data or the latest local artifacts."""
    backtest_summary_data = (
        backtest_summary_data if backtest_summary_data is not None else backtest_results.summary()
    )
    leaderboard_data = (
        leaderboard_data if leaderboard_data is not None else backtest_results.leaderboard()
    )
    performance_data = (
        performance_data if performance_data is not None else strategy_performance.report()
    )
    timeseries_data = (
        timeseries_data if timeseries_data is not None else strategy_performance.timeseries()
    )
    return compose_research_note(
        backtest_summary=backtest_summary_data,
        leaderboard=leaderboard_data,
        performance=performance_data,
        timeseries=timeseries_data,
        context=context,
        strategy_slug=strategy_slug,
        as_of_date=as_of_date,
        generated_at=generated_at,
        source_paths=_discover_source_paths(backtest_summary_data, leaderboard_data),
    )


def render_note(
    note: ResearchNote,
    *,
    timeseries_data: dict[str, Any] | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    """Render a note to its canonical output path."""
    path = _output_path(output_root, note.as_of_date, note.strategy_slug)
    return render_pdf(
        note,
        path,
        timeseries=timeseries_data or {},
        source_paths=tuple(note.sources),
    )


def build_note(
    *,
    context: dict[str, Any] | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    as_of_date: str | None = None,
    strategy_slug: str | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timeseries = strategy_performance.timeseries()
    note = compose_note(
        context=context,
        timeseries_data=timeseries,
        as_of_date=as_of_date,
        strategy_slug=strategy_slug,
        generated_at=generated_at,
    )
    pdf = render_note(note, timeseries_data=timeseries, output_root=output_root)
    json_path = pdf.with_suffix(".json")
    json_path.write_text(json.dumps(note.to_dict(), indent=2, sort_keys=True) + "\n")
    return {
        "ok": True,
        "note": note.to_dict(),
        "pdf_path": str(pdf),
        "json_path": str(json_path),
        "envelope_path": str(sidecar_path(pdf)),
    }


def _discover_source_paths(
    backtest_summary_data: dict[str, Any],
    leaderboard_data: dict[str, Any],
) -> list[Path]:
    names = {
        backtest_summary_data.get("source_file"),
        leaderboard_data.get("source_file"),
    }
    paths: list[Path] = []
    for name in names:
        if not name:
            continue
        path = backtest_results.BACKTESTS_DIR / str(name)
        if path.exists():
            paths.append(path)
    return paths


def _iter_notes(output_root: Path = DEFAULT_OUTPUT_ROOT) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not output_root.exists():
        return rows
    for pdf in sorted(output_root.glob("*/*/research-note.pdf")):
        env = sidecar_path(pdf)
        rows.append(
            {
                "pdf_path": str(pdf),
                "envelope_path": str(env) if env.exists() else None,
                "date": pdf.parent.parent.name,
                "strategy_slug": pdf.parent.name,
                "bytes": pdf.stat().st_size,
            }
        )
    return rows


def latest_note(*, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    rows = _iter_notes(output_root)
    return {"ok": bool(rows), "latest": rows[-1] if rows else None, "count": len(rows)}


def aggregate_summary(*, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    rows = _iter_notes(output_root)
    by_date: dict[str, int] = {}
    by_strategy: dict[str, int] = {}
    for row in rows:
        by_date[row["date"]] = by_date.get(row["date"], 0) + 1
        by_strategy[row["strategy_slug"]] = by_strategy.get(row["strategy_slug"], 0) + 1
    return {
        "ok": True,
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "note_count": len(rows),
        "by_date": by_date,
        "by_strategy": by_strategy,
        "latest": rows[-1] if rows else None,
    }


def completed_sweeps() -> list[dict[str, Any]]:
    """Enumerate completed local sweep artifacts."""
    root = backtest_results.BACKTESTS_DIR
    if not root.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(root.glob("strategy_sweep_*.json")):
        out.append(
            {
                "path": str(path),
                "name": path.name,
                "bytes": path.stat().st_size,
                "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                .replace(microsecond=0)
                .isoformat(),
            }
        )
    return out
