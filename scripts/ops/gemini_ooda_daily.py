#!/usr/bin/env python3
"""Daily dry-run Gemini OODA packet writer.

This wrapper is intentionally no-spend: it calls the Gemini OODA tool in
``mode=dry-run`` and explicitly clears the live-mode environment flag before
invoking the tool. The generated packet is written under ``data/.autonomy``
with a provenance sidecar and a paste-safe delta event.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.core.provenance import write_envelope_sidecar
from lib.core.routine_pause import abort_if_paused
from lib.intel.sovereign_thesis import DEFAULT_CONFIG_PATH, build_sovereign_thesis_report

OUT_DIR = REPO_ROOT / "data" / ".autonomy" / "gemini-ooda"
EVENTS_PATH = REPO_ROOT / "data" / "system_events.jsonl"
TOOL_PATH = REPO_ROOT / "plugins" / "claw-sapphire" / "tools" / "gemini_ooda.py"
RUNBOOK_PATH = REPO_ROOT / "docs" / "ops" / "gemini-ooda-daily-runbook.md"
DEFAULT_TOPIC = "Sapphire daily thesis OODA snapshot"
MAX_DIFF_VALUE_CHARS = 180
MAX_CONTEXT_CHARS = 1_500


@dataclass(frozen=True)
class DailyRunResult:
    """Paths and payload emitted by one daily dry-run."""

    packet_path: Path
    envelope_path: Path
    event: dict[str, Any]
    packet: dict[str, Any]


def now_utc() -> datetime:
    return datetime.now(UTC)


def date_key(now: datetime | None = None) -> str:
    return (now or now_utc()).astimezone(UTC).date().isoformat()


def truncate_value(value: Any, limit: int = MAX_DIFF_VALUE_CHARS) -> str:
    text = json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


def repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _flatten(value: Any, *, prefix: str = "") -> dict[str, Any]:
    if isinstance(value, dict):
        flattened: dict[str, Any] = {}
        for key, child in sorted(value.items()):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.update(_flatten(child, prefix=child_prefix))
        return flattened
    return {prefix: value}


def diff_packets(today: dict[str, Any], yesterday: dict[str, Any] | None) -> dict[str, Any]:
    """Return a paste-safe key-level diff between two OODA packet payloads."""
    if not yesterday:
        return {
            "available": False,
            "reason": "no_previous_packet",
            "added": [],
            "removed": [],
            "mutated": [],
        }

    current = _flatten(
        {
            "topic": today.get("topic"),
            "tool_response": today.get("tool_response"),
            "context_summary": today.get("context_summary"),
        }
    )
    previous = _flatten(
        {
            "topic": yesterday.get("topic"),
            "tool_response": yesterday.get("tool_response"),
            "context_summary": yesterday.get("context_summary"),
        }
    )
    current_keys = set(current)
    previous_keys = set(previous)
    mutated = [
        {
            "key": key,
            "before": truncate_value(previous[key]),
            "after": truncate_value(current[key]),
        }
        for key in sorted(current_keys & previous_keys)
        if current[key] != previous[key]
    ]
    return {
        "available": True,
        "added": sorted(current_keys - previous_keys),
        "removed": sorted(previous_keys - current_keys),
        "mutated": mutated,
    }


def _previous_packet_path(out_dir: Path, day: str) -> Path | None:
    candidates = sorted(path for path in out_dir.glob("*.json") if path.stem < day)
    return candidates[-1] if candidates else None


def load_previous_packet(out_dir: Path, day: str) -> dict[str, Any] | None:
    previous = _previous_packet_path(out_dir, day)
    if previous is None:
        return None
    try:
        return json.loads(previous.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def build_thesis_context() -> tuple[str, dict[str, Any]]:
    """Build a paste-safe summary from the current sovereign-thesis snapshot."""
    thesis = build_sovereign_thesis_report()
    assets = thesis.get("assets") or []
    ranked = sorted(
        [row for row in assets if row.get("relative_score") is not None],
        key=lambda row: float(row.get("relative_score") or 0),
        reverse=True,
    )[:5]
    summary = ", ".join(
        f"{row.get('symbol', '?')} score={row.get('relative_score', 0)} fit={row.get('fit', '?')}"
        for row in ranked
    )
    totals = thesis.get("totals") or {}
    context = (
        "Sovereign-thesis daily snapshot. "
        f"Top assets: {summary or 'none available'}. "
        f"Assets={totals.get('assets', 0)}, lenses={totals.get('lenses', 0)}, "
        f"evidence_coverage_pct={totals.get('evidence_coverage_pct', 0)}, "
        "mode=research_intel_only, no positions, no orders, no Telegram sends."
    )
    context_summary = {
        "config_path": thesis.get("config_path"),
        "generated_at": thesis.get("generated_at"),
        "mode": thesis.get("mode"),
        "top_assets": [
            {
                "symbol": row.get("symbol"),
                "fit": row.get("fit"),
                "relative_score": row.get("relative_score"),
            }
            for row in ranked
        ],
        "totals": {
            "assets": totals.get("assets", 0),
            "lenses": totals.get("lenses", 0),
            "evidence_coverage_pct": totals.get("evidence_coverage_pct", 0),
            "evidence_wired_pct": totals.get("evidence_wired_pct", 0),
            "invalidation_watches": totals.get("invalidation_watches", 0),
        },
    }
    return context[:MAX_CONTEXT_CHARS], context_summary


def run_tool(
    *,
    topic: str,
    context: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    payload = {
        "action": "synthesize",
        "topic": topic,
        "context": context,
        "mode": "dry-run",
        "model": "gemini-2.5-flash",
        "max_output_tokens": 512,
        "ttl_seconds": 86400,
    }
    env = dict(os.environ)
    env["SAPPHIRE_GEMINI_LIVE"] = "0"
    completed = runner(
        [sys.executable, str(TOOL_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=60,
        env=env,
    )
    if completed.returncode != 0:
        return {
            "error": "gemini_ooda_tool_failed",
            "returncode": completed.returncode,
            "stderr": truncate_value(completed.stderr, 500),
        }
    try:
        parsed = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:
        return {
            "error": "gemini_ooda_tool_output_invalid_json",
            "detail": str(exc),
            "stdout": truncate_value(completed.stdout, 500),
        }
    return parsed


def write_packet(
    packet: dict[str, Any],
    *,
    out_dir: Path = OUT_DIR,
    day: str,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    packet_path = out_dir / f"{day}.json"
    packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    envelope_path = write_envelope_sidecar(
        packet_path,
        generator="scripts.ops.gemini_ooda_daily",
        model="gemini-2.5-flash",
        source_paths=(TOOL_PATH, DEFAULT_CONFIG_PATH, RUNBOOK_PATH),
        ttl_seconds=86400,
        metadata={"date": day, "mode": "daily-dry-run"},
    )
    return packet_path, envelope_path


def append_delta_event(
    *,
    diff: dict[str, Any],
    packet_path: Path,
    events_path: Path = EVENTS_PATH,
    generated_at: str,
) -> dict[str, Any]:
    added = len(diff.get("added") or [])
    removed = len(diff.get("removed") or [])
    mutated = len(diff.get("mutated") or [])
    event = {
        "timestamp": generated_at,
        "type": "gemini_ooda_daily",
        "service": "scripts.ops.gemini_ooda_daily",
        "priority": "p3",
        "message": (
            "Gemini OODA daily dry-run packet written "
            f"added={added} removed={removed} mutated={mutated}"
        ),
        "tags": [
            "project:sapphire",
            "agent:launchagent",
            "priority:p3",
            "type:gemini_ooda_daily",
            "service:gemini-ooda",
        ],
        "data": {
            "packet_path": repo_relative(packet_path),
            "diff_available": bool(diff.get("available")),
            "added": added,
            "removed": removed,
            "mutated": mutated,
        },
    }
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
    return event


def run_daily(
    *,
    day: str | None = None,
    out_dir: Path = OUT_DIR,
    events_path: Path = EVENTS_PATH,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> DailyRunResult:
    run_day = day or date_key()
    generated_at = now_utc().replace(microsecond=0).isoformat()
    context, context_summary = build_thesis_context()
    tool_response = run_tool(topic=DEFAULT_TOPIC, context=context, runner=runner)
    previous_packet = load_previous_packet(out_dir, run_day)
    packet = {
        "schema_version": 1,
        "date": run_day,
        "generated_at": generated_at,
        "mode": "daily-dry-run",
        "topic": DEFAULT_TOPIC,
        "safety": {
            "live_requested": False,
            "live_trading_enabled": False,
            "telegram_sends_enabled": False,
            "writes_by_default": True,
            "guards": [
                "gemini_ooda_mode_dry_run",
                "sapphire_gemini_live_env_forced_zero",
                "paste_safe_context_only",
            ],
        },
        "context_summary": context_summary,
        "tool_response": tool_response,
    }
    packet["diff_against_previous"] = diff_packets(packet, previous_packet)
    packet_path, envelope_path = write_packet(packet, out_dir=out_dir, day=run_day)
    event = append_delta_event(
        diff=packet["diff_against_previous"],
        packet_path=packet_path,
        events_path=events_path,
        generated_at=generated_at,
    )
    return DailyRunResult(
        packet_path=packet_path,
        envelope_path=envelope_path,
        event=event,
        packet=packet,
    )


def main(argv: list[str] | None = None) -> int:
    abort_if_paused("gemini-ooda-daily")
    parser = argparse.ArgumentParser(description="Write the daily dry-run Gemini OODA packet")
    parser.add_argument("--date", default=None, help="Override YYYY-MM-DD output date")
    parser.add_argument("--out-dir", default=str(OUT_DIR), help="Output directory")
    parser.add_argument("--events-path", default=str(EVENTS_PATH), help="system_events JSONL path")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print the run summary")
    args = parser.parse_args(argv)

    result = run_daily(
        day=args.date,
        out_dir=Path(args.out_dir),
        events_path=Path(args.events_path),
    )
    summary = {
        "ok": True,
        "packet_path": str(result.packet_path),
        "envelope_path": str(result.envelope_path),
        "event_type": result.event.get("type"),
        "diff": result.packet.get("diff_against_previous"),
    }
    print(json.dumps(summary, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
