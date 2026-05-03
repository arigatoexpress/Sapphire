#!/usr/bin/env python3
"""Sapphire Narrative Synthesis daemon.

Reads correlated signals from ``data/correlated_signals/<date>/signals.jsonl``,
generates deterministic dry-run narratives by default, gates publication with
the synthesis rubric, and writes publishable theses to
``data/narratives/<date>/theses.jsonl``. Event-bus publication is gated by
``SAPPHIRE_NARRATIVE_LIVE_BUS=1`` so local tests and operator dry-runs do not
touch Redis unless explicitly enabled.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.core.provenance import write_envelope_sidecar  # noqa: E402
from lib.intelligence import enrich_signal_for_narrative  # noqa: E402
from lib.synthesis import (  # noqa: E402
    MIN_RUBRIC_SCORE_TO_PUBLISH,
    score_narrative,
    synthesize_thesis,
)

DEFAULT_CORRELATOR_ROOT = REPO_ROOT / "data" / "correlated_signals"
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "narratives"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "sapphire" / "narrative_synthesis_service"
GENERATOR = "services.synthesis.run"
VERSION = "0.1.0"
DEFAULT_POLL_INTERVAL_SECONDS = 30 * 60
DEFAULT_EDGE_DELTA = 0.10


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _date_str(now: datetime | None = None) -> str:
    return (now or _utc_now()).strftime("%Y-%m-%d")


def _input_path(root: Path, *, date: str | None = None, now: datetime | None = None) -> Path:
    return root / (date or _date_str(now)) / "signals.jsonl"


def _output_path(root: Path, *, date: str | None = None, now: datetime | None = None) -> Path:
    return root / (date or _date_str(now)) / "theses.jsonl"


def _state_path(cache_dir: Path) -> Path:
    return cache_dir / "last_edges.json"


def _load_state(cache_dir: Path) -> dict[str, float]:
    path = _state_path(cache_dir)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in raw.items():
        try:
            out[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def _save_state(cache_dir: Path, state: dict[str, float]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    _state_path(cache_dir).write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def _pair_key(signal: dict[str, Any]) -> str:
    return f"{str(signal.get('symbol') or '').upper()}:{str(signal.get('timeframe') or '').lower()}"


def _edge(signal: dict[str, Any]) -> float:
    try:
        return float(signal.get("edge_score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def latest_signal_rows(
    *,
    input_root: Path = DEFAULT_CORRELATOR_ROOT,
    date: str | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Return the latest row per ``(symbol, timeframe)`` for a date."""
    rows = _read_jsonl(_input_path(input_root, date=date, now=now))
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _pair_key(row)
        if not key.strip(":"):
            continue
        latest[key] = row
    return list(latest.values())


def changed_signals(
    signals: Iterable[dict[str, Any]],
    *,
    state: dict[str, float],
    min_edge_delta: float = DEFAULT_EDGE_DELTA,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for signal in signals:
        key = _pair_key(signal)
        edge = _edge(signal)
        previous = state.get(key)
        if previous is None or abs(edge - previous) > min_edge_delta:
            selected.append(signal)
    return selected


def _write_jsonl(
    rows: Sequence[dict[str, Any]], *, output_root: Path, now: datetime | None
) -> Path:
    path = _output_path(output_root, now=now)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    write_envelope_sidecar(
        path,
        generator=GENERATOR,
        source_paths=(),
        ttl_seconds=14 * 86_400,
        metadata={"version": VERSION, "rows_appended": len(rows)},
    )
    return path


def _publish_events(rows: Sequence[dict[str, Any]]) -> int:
    if os.environ.get("SAPPHIRE_NARRATIVE_LIVE_BUS", "").strip() != "1":
        return 0
    try:
        from lib.core.event_bus import get_bus
    except ImportError:  # pragma: no cover
        return 0
    try:
        bus = get_bus(source="narrative-synthesis")
    except Exception:  # noqa: BLE001
        return 0
    published = 0
    for row in rows:
        try:
            bus.publish("narrative.thesis.generated", row, source="narrative-synthesis")
            published += 1
        except Exception:  # noqa: BLE001
            continue
    return published


def run_once(
    *,
    input_root: Path = DEFAULT_CORRELATOR_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    min_edge_delta: float = DEFAULT_EDGE_DELTA,
    mode: str = "dry-run",
    publish: bool = True,
    now: datetime | None = None,
    signals: Sequence[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Single synthesis tick."""
    state = _load_state(cache_dir)
    source_rows = (
        list(signals) if signals is not None else latest_signal_rows(input_root=input_root, now=now)
    )
    selected = changed_signals(source_rows, state=state, min_edge_delta=min_edge_delta)
    publishable: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for signal in selected:
        enriched_signal = enrich_signal_for_narrative(signal, generated_at=now)
        thesis = synthesize_thesis(enriched_signal, mode=mode, now=now)
        rubric = score_narrative(thesis, signal=enriched_signal)
        row = {
            "symbol": thesis.symbol,
            "timeframe": thesis.timeframe,
            "generated_at": thesis.generated_at,
            "mode_actual": thesis.mode_actual,
            "thesis": thesis.to_dict(),
            "rubric": rubric.to_dict(),
            "source_signal": {
                "edge_score": enriched_signal.get("edge_score"),
                "consensus": enriched_signal.get("consensus"),
                "generated_at": enriched_signal.get("generated_at"),
                "tranche4_context": enriched_signal.get("tranche4_context"),
            },
            "service": {"generator": GENERATOR, "version": VERSION},
        }
        if rubric.overall >= MIN_RUBRIC_SCORE_TO_PUBLISH:
            publishable.append(row)
            state[_pair_key(signal)] = _edge(signal)
        else:
            dropped.append(row)

    output_path: Path | None = None
    if publishable:
        output_path = _write_jsonl(publishable, output_root=output_root, now=now)
    published = _publish_events(publishable) if publish else 0
    _save_state(cache_dir, state)
    return {
        "ok": True,
        "signals_seen": len(source_rows),
        "signals_changed": len(selected),
        "published_rows": len(publishable),
        "dropped_rows": len(dropped),
        "event_bus_published": published,
        "output_path": str(output_path) if output_path else None,
        "min_edge_delta": min_edge_delta,
        "min_rubric_score_to_publish": MIN_RUBRIC_SCORE_TO_PUBLISH,
        "live_bus": os.environ.get("SAPPHIRE_NARRATIVE_LIVE_BUS") == "1",
    }


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
    return {"iterations": iterations}


def status(*, cache_dir: Path = DEFAULT_CACHE_DIR) -> dict[str, Any]:
    state = _load_state(cache_dir)
    return {
        "cache_dir": str(cache_dir),
        "tracked_pairs": len(state),
        "live_bus": os.environ.get("SAPPHIRE_NARRATIVE_LIVE_BUS") == "1",
        "default_poll_interval_seconds": DEFAULT_POLL_INTERVAL_SECONDS,
        "default_edge_delta": DEFAULT_EDGE_DELTA,
        "min_rubric_score_to_publish": MIN_RUBRIC_SCORE_TO_PUBLISH,
        "generator": GENERATOR,
        "version": VERSION,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    once = sub.add_parser("run-once", help="single dry-run tick")
    once.add_argument("--mode", default="dry-run", choices=["dry-run", "live"])
    once.add_argument("--min-edge-delta", type=float, default=DEFAULT_EDGE_DELTA)
    daemon_p = sub.add_parser("daemon", help="continuous poll loop")
    daemon_p.add_argument("--mode", default="dry-run", choices=["dry-run", "live"])
    daemon_p.add_argument(
        "--poll-interval-seconds", type=float, default=DEFAULT_POLL_INTERVAL_SECONDS
    )
    daemon_p.add_argument("--max-iterations", type=int, default=None)
    sub.add_parser("status", help="read-only service status")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.action == "run-once":
        result = run_once(mode=args.mode, min_edge_delta=args.min_edge_delta)
    elif args.action == "daemon":
        result = daemon(
            poll_interval_seconds=args.poll_interval_seconds,
            max_iterations=args.max_iterations,
            mode=args.mode,
        )
    elif args.action == "status":
        result = status()
    else:  # pragma: no cover - argparse enforces choices
        result = {"ok": False, "error": f"unknown action {args.action}"}
    json.dump(result, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
