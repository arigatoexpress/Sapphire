#!/usr/bin/env python3
"""Sapphire Narrative Evaluation daemon.

Scores elapsed narrative thesis horizons against local outcome rows and writes
idempotent artifacts under ``data/narrative_evaluation/<date>/scores.jsonl``.
No live market calls, LLM calls, Telegram sends, or trading-path writes occur.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.core.provenance import write_envelope_sidecar  # noqa: E402
from lib.narrative_evaluation import (  # noqa: E402
    DEFAULT_HORIZONS_HOURS,
    aggregate_scores,
    calibration_report,
    diagnostics_report,
    score_thesis,
    summary_report,
)

DEFAULT_NARRATIVE_ROOT = REPO_ROOT / "data" / "narratives"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "narrative_evaluation"
DEFAULT_OUTCOME_PATHS = (
    REPO_ROOT / "data" / "narrative_evaluation" / "outcomes.jsonl",
    REPO_ROOT / "data" / "signals",
    REPO_ROOT / "data" / "performance" / "signals.jsonl",
)
GENERATOR = "services.narrative_evaluation.run"
VERSION = "0.1.0"
DEFAULT_POLL_INTERVAL_SECONDS = 60 * 60


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _date_str(now: datetime | None = None) -> str:
    return (now or _utc_now()).strftime("%Y-%m-%d")


def _read_jsonl(path: Path, *, limit: int | None = None) -> list[dict[str, Any]]:
    if not path.exists() or not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    if limit is not None:
        lines = lines[-max(1, int(limit)) :]
    rows: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _jsonl_paths(root_or_file: Path, *, date: str | None = None) -> list[Path]:
    if root_or_file.is_file():
        return [root_or_file]
    if not root_or_file.exists():
        return []
    if date:
        dated = root_or_file / date
        if dated.is_dir():
            return sorted(dated.glob("*.jsonl"))
        dated_file = root_or_file / f"{date}.jsonl"
        if dated_file.exists():
            return [dated_file]
    return sorted(root_or_file.glob("**/*.jsonl"))


def load_narratives(
    *,
    narrative_root: Path = DEFAULT_NARRATIVE_ROOT,
    date: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    paths = _jsonl_paths(narrative_root, date=date)
    rows: list[dict[str, Any]] = []
    for path in paths:
        if path.name != "theses.jsonl":
            continue
        rows.extend(_read_jsonl(path, limit=limit))
    return rows[-limit:] if limit else rows


def load_outcomes(paths: Sequence[Path] = DEFAULT_OUTCOME_PATHS, *, date: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for root in paths:
        for path in _jsonl_paths(root, date=date):
            rows.extend(_read_jsonl(path))
    return rows


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _actual_value(row: dict[str, Any]) -> float | None:
    for key in ("actual_return_pct", "return_pct", "pnl_pct", "move_pct"):
        try:
            if row.get(key) is not None:
                return float(row[key])
        except (TypeError, ValueError):
            return None
    if row.get("entry_price") and row.get("exit_price"):
        try:
            entry = float(row["entry_price"])
            exit_p = float(row["exit_price"])
            side = str(row.get("side") or row.get("direction") or "long").lower()
            move = ((exit_p - entry) / entry) * 100.0
            return -move if side in {"short", "sell", "bearish"} else move
        except (TypeError, ValueError, ZeroDivisionError):
            return None
    return None


def _outcome_ts(row: dict[str, Any]) -> datetime | None:
    return _parse_ts(row.get("observed_at") or row.get("timestamp") or row.get("closed_at") or row.get("generated_at"))


def _find_outcome(
    thesis_row: dict[str, Any],
    outcomes: Sequence[dict[str, Any]],
    *,
    horizon_hours: int,
) -> dict[str, Any] | None:
    thesis = thesis_row.get("thesis") if isinstance(thesis_row.get("thesis"), dict) else thesis_row
    symbol = str(thesis.get("symbol") or thesis_row.get("symbol") or "").upper()
    timeframe = str(thesis.get("timeframe") or thesis_row.get("timeframe") or "").lower()
    generated = _parse_ts(thesis.get("generated_at") or thesis_row.get("generated_at"))
    if generated is None:
        return None
    due = generated.timestamp() + int(horizon_hours) * 3600
    candidates: list[tuple[float, dict[str, Any]]] = []
    for row in outcomes:
        if symbol and str(row.get("symbol") or "").upper() != symbol:
            continue
        row_tf = str(row.get("timeframe") or timeframe).lower()
        if timeframe and row_tf != timeframe:
            continue
        if _actual_value(row) is None:
            continue
        observed = _outcome_ts(row)
        if observed is None:
            continue
        lag = observed.timestamp() - due
        if lag >= 0:
            candidates.append((lag, row))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item[0])[0][1]


def _scores_path(output_root: Path, *, now: datetime | None = None) -> Path:
    return output_root / _date_str(now) / "scores.jsonl"


def load_scores(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    date: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in _jsonl_paths(output_root, date=date):
        if path.name == "scores.jsonl":
            rows.extend(_read_jsonl(path))
    return rows[-max(1, int(limit)) :]


def _write_scores(rows: Sequence[dict[str, Any]], *, output_root: Path, now: datetime | None) -> Path | None:
    if not rows:
        return None
    path = _scores_path(output_root, now=now)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    write_envelope_sidecar(
        path,
        generator=GENERATOR,
        source_paths=(),
        ttl_seconds=30 * 86_400,
        metadata={"version": VERSION, "rows_appended": len(rows)},
    )
    return path


def run_once(
    *,
    narrative_root: Path = DEFAULT_NARRATIVE_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    outcome_paths: Sequence[Path] = DEFAULT_OUTCOME_PATHS,
    horizons_hours: Sequence[int] = DEFAULT_HORIZONS_HOURS,
    date: str | None = None,
    now: datetime | None = None,
    narratives: Sequence[dict[str, Any]] | None = None,
    outcomes: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    now = now or _utc_now()
    thesis_rows = list(narratives) if narratives is not None else load_narratives(narrative_root=narrative_root, date=date)
    actual_rows = list(outcomes) if outcomes is not None else load_outcomes(outcome_paths, date=date)
    existing = {row.get("score_id") for row in load_scores(output_root=output_root, limit=5000)}
    new_rows: list[dict[str, Any]] = []
    skipped_existing = 0
    for thesis in thesis_rows:
        for horizon in sorted({int(h) for h in horizons_hours}):
            outcome = _find_outcome(thesis, actual_rows, horizon_hours=horizon)
            score = score_thesis(thesis, outcome, horizon_hours=horizon, scored_at=now).to_dict()
            if score["score_id"] in existing:
                skipped_existing += 1
                continue
            existing.add(score["score_id"])
            new_rows.append(score)
    output_path = _write_scores(new_rows, output_root=output_root, now=now)
    return {
        "ok": True,
        "generator": GENERATOR,
        "version": VERSION,
        "narratives_seen": len(thesis_rows),
        "outcomes_seen": len(actual_rows),
        "scores_written": len(new_rows),
        "skipped_existing": skipped_existing,
        "output_path": str(output_path) if output_path else None,
        "horizons_hours": sorted({int(h) for h in horizons_hours}),
        "dry_run": True,
    }


def status(*, output_root: Path = DEFAULT_OUTPUT_ROOT) -> dict[str, Any]:
    scores = load_scores(output_root=output_root, limit=5000)
    return {
        "ok": True,
        "generator": GENERATOR,
        "version": VERSION,
        "output_root": str(output_root),
        "score_rows": len(scores),
        "default_horizons_hours": list(DEFAULT_HORIZONS_HOURS),
        "default_poll_interval_seconds": DEFAULT_POLL_INTERVAL_SECONDS,
        "dry_run": True,
    }


def summary(*, output_root: Path = DEFAULT_OUTPUT_ROOT, date: str | None = None, limit: int = 1000) -> dict[str, Any]:
    return summary_report(load_scores(output_root=output_root, date=date, limit=limit))


def aggregates(
    *,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    group_by: str = "symbol",
    date: str | None = None,
    limit: int = 1000,
) -> dict[str, Any]:
    return aggregate_scores(load_scores(output_root=output_root, date=date, limit=limit), group_by=group_by)


def diagnostics(*, output_root: Path = DEFAULT_OUTPUT_ROOT, date: str | None = None, limit: int = 1000) -> dict[str, Any]:
    return diagnostics_report(load_scores(output_root=output_root, date=date, limit=limit))


def calibration(*, output_root: Path = DEFAULT_OUTPUT_ROOT, date: str | None = None, limit: int = 1000) -> dict[str, Any]:
    return calibration_report(load_scores(output_root=output_root, date=date, limit=limit))


def daemon(
    *,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
    max_iterations: int | None = None,
    sleep: Any = time.sleep,
    **kwargs: Any,
) -> dict[str, Any]:
    iterations = 0
    while True:
        run_once(**kwargs)
        iterations += 1
        if max_iterations is not None and iterations >= max_iterations:
            break
        sleep(poll_interval_seconds)
    return {"ok": True, "iterations": iterations}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    once = sub.add_parser("run-once")
    once.add_argument("--date")
    once.add_argument("--horizon", action="append", dest="horizons", type=int)
    daemon_p = sub.add_parser("daemon")
    daemon_p.add_argument("--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS)
    daemon_p.add_argument("--max-iterations", type=int, default=None)
    sub.add_parser("status")
    sub.add_parser("summary")
    agg = sub.add_parser("aggregates")
    agg.add_argument("--group-by", default="symbol")
    sub.add_parser("diagnostics")
    sub.add_parser("calibration")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "run-once":
        result = run_once(date=args.date, horizons_hours=tuple(args.horizons or DEFAULT_HORIZONS_HOURS))
    elif args.action == "daemon":
        result = daemon(
            poll_interval_seconds=args.poll_interval_seconds,
            max_iterations=args.max_iterations,
        )
    elif args.action == "status":
        result = status()
    elif args.action == "summary":
        result = summary()
    elif args.action == "aggregates":
        result = aggregates(group_by=args.group_by)
    elif args.action == "diagnostics":
        result = diagnostics()
    elif args.action == "calibration":
        result = calibration()
    else:
        result = {"ok": False, "error": f"unknown action {args.action}"}
    json.dump(result, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
