#!/usr/bin/env python3
"""Sapphire macro intelligence stdin-JSON tool.

Actions:

* ``recent`` — read recent ``data/macro/<date>/events.jsonl`` rows.
* ``calendar`` — read or synthesize the forward macro calendar.
* ``next-event-for-asset`` — return the next calendar event affecting an asset.
* ``pull-once`` — one macro-intel tick. Defaults to dry-run unless ``live`` is
  requested and ``SAPPHIRE_MACRO_INTEL_LIVE=1`` is set.
* ``status`` — cache/counter summary.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_repo_module(qualname: str, relpath: str):
    if qualname in sys.modules:
        existing = sys.modules[qualname]
        existing_file = getattr(existing, "__file__", "") or ""
        if str(REPO_ROOT) in existing_file:
            return existing
    import types as _types

    parts = qualname.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[:i])
        if parent not in sys.modules or not hasattr(sys.modules[parent], "__path__"):
            mod = _types.ModuleType(parent)
            mod.__path__ = [str(REPO_ROOT / Path(*parts[:i]))]  # type: ignore[attr-defined]
            sys.modules[parent] = mod

    target = REPO_ROOT / relpath
    spec = importlib.util.spec_from_file_location(qualname, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {qualname} from {target}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualname] = module
    spec.loader.exec_module(module)
    if len(parts) > 1:
        setattr(sys.modules[".".join(parts[:-1])], parts[-1], module)
    return module


_load_repo_module("lib.macro.sources", "lib/macro/sources.py")
_load_repo_module("lib.macro.classifier", "lib/macro/classifier.py")
_load_repo_module("lib.macro.calendar", "lib/macro/calendar.py")
_load_repo_module("lib.macro", "lib/macro/__init__.py")
svc = _load_repo_module("services.macro_intel.run", "services/macro_intel/run.py")

from lib.macro.calendar import build_calendar, calendar_from_dicts  # noqa: E402
from lib.macro.sources import MAX_FORWARD_CALENDAR_DAYS  # noqa: E402

DEFAULT_OUTPUT_ROOT = REPO_ROOT / "data" / "macro"
VERSION = "0.1.0"
GENERATOR = "plugins.claw_sapphire.macro_intel"


def _date_key(value: str | None = None) -> str:
    if value:
        return value
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _jsonl_path(kind: str, date_value: str | None = None) -> Path:
    filename = "calendar.jsonl" if kind == "calendar" else "events.jsonl"
    return DEFAULT_OUTPUT_ROOT / _date_key(date_value) / filename


def _read_jsonl(path: Path, *, limit: int = 100) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        row.pop("provenance", None)
        rows.append(row)
    return rows[-max(1, min(limit, 500)) :]


def recent_action(*, date: str | None = None, limit: int = 20) -> dict[str, Any]:
    path = _jsonl_path("events", date)
    rows = _read_jsonl(path, limit=limit)
    return {
        "ok": bool(rows),
        "date": _date_key(date),
        "path": str(path),
        "count": len(rows),
        "events": rows,
        "reason": None if rows else "no macro events file",
    }


def _fallback_calendar_rows() -> list[dict[str, Any]]:
    return build_calendar((), include_static=True, max_forward_days=MAX_FORWARD_CALENDAR_DAYS).to_dicts()


def calendar_action(*, date: str | None = None, hours: float | None = None) -> dict[str, Any]:
    path = _jsonl_path("calendar", date)
    rows = _read_jsonl(path, limit=500)
    if not rows:
        rows = _fallback_calendar_rows()
    if hours is not None:
        cal = calendar_from_dicts(rows)
        rows = [event.to_dict() for event in cal.in_next_hours(hours)]
    return {
        "ok": True,
        "date": _date_key(date),
        "path": str(path),
        "count": len(rows),
        "calendar": rows,
    }


def next_event_for_asset_action(*, asset: str, date: str | None = None) -> dict[str, Any]:
    if not asset or not str(asset).strip():
        return {"ok": False, "error": "asset is required"}
    rows = calendar_action(date=date)["calendar"]
    event = calendar_from_dicts(rows).next_event_for_asset(str(asset).strip())
    return {
        "ok": event is not None,
        "asset": str(asset).strip().upper(),
        "event": event.to_dict() if event else None,
        "reason": None if event else "no matching event in forward calendar",
    }


def _live_requested(payload: dict[str, Any]) -> bool:
    return bool(payload.get("live")) and os.environ.get("SAPPHIRE_MACRO_INTEL_LIVE") == "1"


def pull_once_action(payload: dict[str, Any]) -> dict[str, Any]:
    result = svc.run_once(
        since_hours=float(payload.get("since_hours") or 24.0),
        live=_live_requested(payload),
        publish=bool(payload.get("publish")),
        output_root=DEFAULT_OUTPUT_ROOT,
    )
    result.setdefault("metadata", {})["tool_generator"] = GENERATOR
    result["metadata"]["tool_version"] = VERSION
    return result


def status_action() -> dict[str, Any]:
    snap = svc.status(output_root=DEFAULT_OUTPUT_ROOT)
    snap.update(
        {
            "tool_version": VERSION,
            "tool_generator": GENERATOR,
            "live_request_requires_env": "SAPPHIRE_MACRO_INTEL_LIVE=1",
        }
    )
    return snap


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "recent").strip().lower()
    if action == "recent":
        return recent_action(
            date=payload.get("date"),
            limit=int(payload.get("limit") or 20),
        )
    if action == "calendar":
        hours = payload.get("hours")
        return calendar_action(
            date=payload.get("date"),
            hours=float(hours) if hours is not None else None,
        )
    if action == "next-event-for-asset":
        return next_event_for_asset_action(asset=str(payload.get("asset") or ""), date=payload.get("date"))
    if action == "pull-once":
        return pull_once_action(payload)
    if action == "status":
        return status_action()
    return {
        "ok": False,
        "error": f"unknown action '{action}'",
        "valid_actions": ["recent", "calendar", "next-event-for-asset", "pull-once", "status"],
    }


def main(stream_in: Any = sys.stdin, stream_out: Any = sys.stdout) -> int:
    raw = stream_in.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        json.dump({"ok": False, "error": f"invalid JSON: {exc}"}, stream_out)
        return 2
    if not isinstance(payload, dict):
        json.dump({"ok": False, "error": "stdin payload must be a JSON object"}, stream_out)
        return 2
    response = handle(payload)
    json.dump(response, stream_out, indent=2, sort_keys=True, default=str)
    return 0 if response.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
