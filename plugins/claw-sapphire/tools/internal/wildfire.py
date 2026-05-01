#!/usr/bin/env python3
"""Wildfire-watch signal ingester for Sapphire.

Bridges the wildfire-watch drone fleet (~/Code/wildfire-watch) to the Sapphire
intelligence mesh. Validates incoming wildfire_signal payloads against the
v1 schema, appends them to data/wildfire_signals.jsonl, and emits an
event_bus event for downstream consumers (dashboard SSE, Telegram alerts via
hermes-agent, weekly content engine).

Read-only-query actions are also exposed (`list`, `stats`) so the dashboard
and operator console can surface recent signals without re-running the
ingestion path.

Usage (stdin JSON):
    echo '{"action":"ingest","signal":{...}}' | python3 wildfire.py
    echo '{"action":"list","limit":10,"min_risk":50}' | python3 wildfire.py
    echo '{"action":"stats","since_hours":24}' | python3 wildfire.py

Schema source of truth:
    ~/Code/wildfire-watch/sapphire_integration/wildfire_signal_schema.json

Design constraints:
- Stateless. All persistent state lives in data/wildfire_signals.jsonl.
- Idempotent on signal_id (re-ingesting the same UUID is a no-op).
- Inert when wildfire-watch repo is absent: validation falls back to a
  minimal in-process schema so the tool still works for tests.
- Never sends Telegram directly. recommended_action="notify_fire_dept"
  surfaces in stats and the event_bus event; the operator-supervised
  hermes skill (sapphire/wildfire-alert) is what actually pages.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
SIGNALS_PATH = SAPPHIRE_DIR / "data" / "wildfire_signals.jsonl"
EVENTS_PATH = SAPPHIRE_DIR / "data" / "events" / "bus.jsonl"
WILDFIRE_REPO = Path.home() / "Code" / "wildfire-watch"
SCHEMA_PATH = WILDFIRE_REPO / "sapphire_integration" / "wildfire_signal_schema.json"

SCHEMA_VERSION = "1.0.0"
SIGNAL_TYPES = {"smoke", "fire", "thermal_anomaly", "wildlife", "anomaly", "system_event"}
RECOMMENDED_ACTIONS = {
    "log_only",
    "notify_operator",
    "notify_fire_dept",
    "loiter_and_capture",
    "rtl",
}


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _ensure_dirs() -> None:
    SIGNALS_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_signals() -> list[dict[str, Any]]:
    if not SIGNALS_PATH.exists():
        return []
    rows: list[dict[str, Any]] = []
    with SIGNALS_PATH.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _validate(signal: dict[str, Any]) -> tuple[bool, str | None]:
    """Minimal in-process validation of the v1 wildfire_signal schema.

    Doesn't pull jsonschema as a dep — Sapphire keeps test deps lean. Mirrors
    the `required` list and the constrained enums from the canonical schema
    at WILDFIRE_REPO/sapphire_integration/wildfire_signal_schema.json.
    """

    if not isinstance(signal, dict):
        return False, "signal must be an object"

    required = [
        "signal_id",
        "drone_id",
        "zone_id",
        "timestamp",
        "coords",
        "signal_type",
        "confidence",
        "evidence",
        "risk_score",
        "recommended_action",
        "schema_version",
    ]
    for key in required:
        if key not in signal:
            return False, f"missing required field: {key}"

    if signal.get("schema_version") != SCHEMA_VERSION:
        return False, f"schema_version must be {SCHEMA_VERSION}"

    sid = signal.get("signal_id", "")
    try:
        uuid.UUID(str(sid))
    except (ValueError, TypeError):
        return False, f"signal_id must be a valid UUID: {sid!r}"

    drone_id = str(signal.get("drone_id", ""))
    if not drone_id.startswith("wfw-") or len(drone_id) > 20:
        return False, f"drone_id must match ^wfw-[a-z0-9]{{4,16}}$ : {drone_id!r}"

    if signal.get("signal_type") not in SIGNAL_TYPES:
        return False, f"signal_type must be one of {sorted(SIGNAL_TYPES)}"

    if signal.get("recommended_action") not in RECOMMENDED_ACTIONS:
        return False, f"recommended_action must be one of {sorted(RECOMMENDED_ACTIONS)}"

    confidence = signal.get("confidence")
    if not isinstance(confidence, int | float) or not 0 <= confidence <= 1:
        return False, "confidence must be a number in [0, 1]"

    risk_score = signal.get("risk_score")
    if not isinstance(risk_score, int | float) or not 0 <= risk_score <= 100:
        return False, "risk_score must be a number in [0, 100]"

    coords = signal.get("coords") or {}
    if not isinstance(coords, dict):
        return False, "coords must be an object"
    for axis in ("lat", "lon", "alt_agl_m"):
        if axis not in coords:
            return False, f"coords.{axis} is required"
    lat, lon = coords.get("lat"), coords.get("lon")
    if not (isinstance(lat, int | float) and -90 <= lat <= 90):
        return False, "coords.lat must be in [-90, 90]"
    if not (isinstance(lon, int | float) and -180 <= lon <= 180):
        return False, "coords.lon must be in [-180, 180]"

    evidence = signal.get("evidence") or {}
    if not isinstance(evidence, dict):
        return False, "evidence must be an object"
    frame_uris = evidence.get("frame_uris")
    if not isinstance(frame_uris, list) or not frame_uris:
        return False, "evidence.frame_uris must be a non-empty array"

    return True, None


def _emit_event(signal: dict[str, Any]) -> None:
    """Append an event_bus envelope so dashboard SSE + content engine see it.

    Mirrors the `data/events/bus.jsonl` JSONL fallback pattern that the
    primary Redis Streams bus degrades to. Never raises.
    """

    try:
        envelope = {
            "ts": _utcnow_iso(),
            "type": "wildfire.signal.detected",
            "tags": {
                "service": "wildfire-watch",
                "device": signal.get("drone_id"),
                "zone": signal.get("zone_id"),
                "signal_type": signal.get("signal_type"),
                "priority": _priority_for(signal),
            },
            "signal": {
                "signal_id": signal.get("signal_id"),
                "risk_score": signal.get("risk_score"),
                "confidence": signal.get("confidence"),
                "recommended_action": signal.get("recommended_action"),
                "coords": signal.get("coords"),
            },
        }
        _ensure_dirs()
        with EVENTS_PATH.open("a") as fh:
            fh.write(json.dumps(envelope, separators=(",", ":")) + "\n")
    except OSError:
        pass


def _priority_for(signal: dict[str, Any]) -> str:
    risk = signal.get("risk_score") or 0
    action = signal.get("recommended_action") or "log_only"
    if action == "notify_fire_dept" or risk >= 80:
        return "critical"
    if action in ("loiter_and_capture", "notify_operator") or risk >= 50:
        return "high"
    if signal.get("signal_type") in ("fire", "smoke", "thermal_anomaly"):
        return "elevated"
    return "info"


def _action_ingest(payload: dict[str, Any]) -> dict[str, Any]:
    signal = payload.get("signal")
    if not isinstance(signal, dict):
        return {"ok": False, "error": "payload.signal must be an object"}

    ok, err = _validate(signal)
    if not ok:
        return {"ok": False, "error": err}

    sid = signal["signal_id"]
    existing = {row.get("signal_id") for row in _load_signals()}
    if sid in existing:
        return {"ok": True, "signal_id": sid, "duplicate": True}

    _ensure_dirs()
    with SIGNALS_PATH.open("a") as fh:
        fh.write(json.dumps(signal, separators=(",", ":")) + "\n")

    _emit_event(signal)

    return {
        "ok": True,
        "signal_id": sid,
        "duplicate": False,
        "priority": _priority_for(signal),
        "persisted_to": str(SIGNALS_PATH),
    }


def _action_list(payload: dict[str, Any]) -> dict[str, Any]:
    rows = _load_signals()
    zone = payload.get("zone_id")
    min_risk = payload.get("min_risk")
    signal_type = payload.get("signal_type")
    since_hours = payload.get("since_hours")
    limit = int(payload.get("limit") or 50)

    filtered = []
    cutoff: datetime | None = None
    if since_hours is not None:
        cutoff = datetime.now(UTC) - timedelta(hours=float(since_hours))
    for row in rows:
        if zone and row.get("zone_id") != zone:
            continue
        if signal_type and row.get("signal_type") != signal_type:
            continue
        if min_risk is not None and (row.get("risk_score") or 0) < float(min_risk):
            continue
        if cutoff is not None:
            ts = row.get("timestamp")
            try:
                ts_dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=UTC)
            if ts_dt < cutoff:
                continue
        filtered.append(row)

    filtered.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    return {"ok": True, "count": len(filtered), "signals": filtered[:limit]}


def _action_stats(payload: dict[str, Any]) -> dict[str, Any]:
    rows = _load_signals()
    since_hours = payload.get("since_hours")
    if since_hours is not None:
        cutoff = datetime.now(UTC) - timedelta(hours=float(since_hours))
        windowed = []
        for row in rows:
            try:
                ts_dt = datetime.fromisoformat(str(row.get("timestamp")).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                continue
            if ts_dt.tzinfo is None:
                ts_dt = ts_dt.replace(tzinfo=UTC)
            if ts_dt >= cutoff:
                windowed.append(row)
        rows = windowed

    by_zone: dict[str, int] = {}
    by_type: dict[str, int] = {}
    by_action: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    max_risk = 0.0
    for row in rows:
        by_zone[row.get("zone_id", "unknown")] = by_zone.get(row.get("zone_id", "unknown"), 0) + 1
        by_type[row.get("signal_type", "unknown")] = by_type.get(row.get("signal_type", "unknown"), 0) + 1
        by_action[row.get("recommended_action", "unknown")] = (
            by_action.get(row.get("recommended_action", "unknown"), 0) + 1
        )
        prio = _priority_for(row)
        by_priority[prio] = by_priority.get(prio, 0) + 1
        max_risk = max(max_risk, float(row.get("risk_score") or 0))

    return {
        "ok": True,
        "total": len(rows),
        "by_zone": by_zone,
        "by_signal_type": by_type,
        "by_recommended_action": by_action,
        "by_priority": by_priority,
        "max_risk_score": max_risk,
        "as_of": _utcnow_iso(),
    }


def _action_schema_info(_: dict[str, Any]) -> dict[str, Any]:
    info: dict[str, Any] = {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "schema_path": str(SCHEMA_PATH),
        "schema_present": SCHEMA_PATH.exists(),
        "signal_types": sorted(SIGNAL_TYPES),
        "recommended_actions": sorted(RECOMMENDED_ACTIONS),
        "signals_path": str(SIGNALS_PATH),
        "events_path": str(EVENTS_PATH),
    }
    return info


_ACTIONS = {
    "ingest": _action_ingest,
    "list": _action_list,
    "stats": _action_stats,
    "schema_info": _action_schema_info,
}


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = (payload or {}).get("action") or "schema_info"
    handler = _ACTIONS.get(action)
    if handler is None:
        return {
            "ok": False,
            "error": f"unknown action: {action}",
            "available_actions": sorted(_ACTIONS),
        }
    return handler(payload or {})


def main() -> None:
    raw = sys.stdin.read().strip()
    payload = json.loads(raw) if raw else {}
    result = handle(payload)
    print(json.dumps(result, indent=2 if "--pretty" in sys.argv else None))


if __name__ == "__main__":
    main()
