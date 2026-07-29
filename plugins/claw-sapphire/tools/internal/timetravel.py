#!/usr/bin/env python3
"""Sapphire Time-Travel + Replay plugin tool.

Stdin-JSON actions:

- ``snapshot``: ``{"action": "snapshot", "at": "<ISO8601 UTC>", "scope": [...]}``
  → ``SystemSnapshot`` dict for the requested timestamp.
- ``replay``: ``{"action": "replay", "at": "<ISO8601 UTC>"}``
  → :class:`ReplayResult` for the snapshot at that timestamp.
- ``diff``: ``{"action": "diff", "at": "<ISO8601 UTC>"}``
  → :class:`DiffResult` comparing actual-at-T vs replay-at-T.
- ``index-status``: ``{"action": "index-status"}``
  → cached index summary, no rebuild.
- ``status``: ``{"action": "status"}`` — alias for ``index-status``.

All actions are read-only over ``data/`` and never publish events,
trigger trades, or send Telegram messages. The tool is the agent-facing
surface for ``lib.timetravel``.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _evict_plugin_lib_shadow() -> None:
    import types

    repo_lib = REPO_ROOT / "lib"
    lib_mod = sys.modules.get("lib")
    lib_file = str(getattr(lib_mod, "__file__", "") or "")
    if "plugins/claw-sapphire/lib" in lib_file:
        for name in list(sys.modules):
            if name == "lib" or name.startswith("lib."):
                sys.modules.pop(name, None)
        lib_mod = None
    if lib_mod is None or not hasattr(lib_mod, "__path__"):
        mod = types.ModuleType("lib")
        mod.__path__ = [str(repo_lib)]  # type: ignore[attr-defined]
        sys.modules["lib"] = mod
        return
    paths = [path for path in list(lib_mod.__path__) if path != str(repo_lib)]  # type: ignore[attr-defined]
    lib_mod.__path__ = [str(repo_lib), *paths]  # type: ignore[attr-defined]


_evict_plugin_lib_shadow()

from lib.timetravel import (  # noqa: E402
    DEFAULT_SCOPE,
    INDEX_PATH,
    SCOPE_TO_ROOT,
    diff_actual_vs_replay,
    index_status,
    replay,
    take_snapshot,
)

VERSION = "0.1.0"
GENERATOR = "plugins.claw-sapphire.tools.timetravel"
VALID_ACTIONS = ("snapshot", "replay", "diff", "index-status", "status")
DEFAULT_MAX_ROWS_PER_SCOPE = 500


def _coerce_at(payload: dict[str, Any]) -> datetime:
    raw = payload.get("at") or payload.get("timestamp")
    if not raw:
        raise ValueError("'at' is required for this action (ISO-8601 UTC)")
    s = str(raw).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        ts = datetime.fromisoformat(s)
    except ValueError as exc:
        raise ValueError(f"invalid ISO-8601 timestamp: {raw}") from exc
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return ts.astimezone(UTC)


def _coerce_scope(payload: dict[str, Any]) -> tuple[str, ...]:
    raw = payload.get("scope")
    if raw in (None, "", []):
        return DEFAULT_SCOPE
    if isinstance(raw, str):
        scopes = [s.strip() for s in raw.split(",") if s.strip()]
    elif isinstance(raw, list | tuple):
        scopes = [str(s).strip() for s in raw if str(s).strip()]
    else:
        raise ValueError("'scope' must be a comma-separated string or list")
    invalid = [s for s in scopes if s not in SCOPE_TO_ROOT]
    if invalid:
        raise ValueError(f"unknown scope(s) {invalid}; valid: {sorted(SCOPE_TO_ROOT)}")
    return tuple(scopes)


def _truncate_rows(snapshot_dict: dict[str, Any], cap: int) -> dict[str, Any]:
    """Cap the row count per scope when serializing for stdin/stdout JSON."""
    if cap is None or cap <= 0:
        return snapshot_dict
    entries = snapshot_dict.get("entries") or {}
    truncated = {}
    for name, entry in entries.items():
        rows = list(entry.get("rows") or [])
        if len(rows) > cap:
            entry = dict(entry)
            entry["rows"] = rows[-cap:]
            entry["truncated"] = True
            entry["truncated_to"] = cap
        truncated[name] = entry
    snapshot_dict["entries"] = truncated
    return snapshot_dict


def snapshot_action(payload: dict[str, Any]) -> dict[str, Any]:
    at = _coerce_at(payload)
    scope = _coerce_scope(payload)
    cache_path = Path(payload.get("cache_path") or INDEX_PATH).expanduser()
    rebuild = bool(payload.get("rebuild_index"))
    snap = take_snapshot(at, scope=scope, cache_path=cache_path, rebuild_index=rebuild)
    cap = int(payload.get("max_rows_per_scope") or DEFAULT_MAX_ROWS_PER_SCOPE)
    return {
        "ok": True,
        "action": "snapshot",
        "version": VERSION,
        "at": snap.at,
        "scope": list(snap.scope),
        "snapshot": _truncate_rows(snap.to_dict(), cap),
    }


def replay_action(payload: dict[str, Any]) -> dict[str, Any]:
    at = _coerce_at(payload)
    scope = _coerce_scope(payload)
    cache_path = Path(payload.get("cache_path") or INDEX_PATH).expanduser()
    snap = take_snapshot(at, scope=scope, cache_path=cache_path)
    result = replay(snap)
    return {
        "ok": True,
        "action": "replay",
        "version": VERSION,
        "at": result.at,
        "result": result.to_dict(),
    }


def diff_action(payload: dict[str, Any]) -> dict[str, Any]:
    at = _coerce_at(payload)
    scope = _coerce_scope(payload)
    cache_path = Path(payload.get("cache_path") or INDEX_PATH).expanduser()
    snap = take_snapshot(at, scope=scope, cache_path=cache_path)
    replay_result = replay(snap)
    diff = diff_actual_vs_replay(snap, replay_result)
    return {
        "ok": True,
        "action": "diff",
        "version": VERSION,
        "at": diff.at,
        "summary": dict(diff.summary),
        "diff": diff.to_dict(),
    }


def index_status_action(payload: dict[str, Any]) -> dict[str, Any]:
    cache_path = Path(payload.get("cache_path") or INDEX_PATH).expanduser()
    return {
        "ok": True,
        "action": "index-status",
        "version": VERSION,
        "status": index_status(cache_path=cache_path),
        "valid_actions": list(VALID_ACTIONS),
        "scopes": sorted(SCOPE_TO_ROOT),
    }


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "index-status").strip().lower().replace("_", "-")
    try:
        if action == "snapshot":
            return snapshot_action(payload)
        if action == "replay":
            return replay_action(payload)
        if action == "diff":
            return diff_action(payload)
        if action in {"index-status", "status"}:
            return index_status_action(payload)
        return {
            "error": f"unknown action '{action}'",
            "valid_actions": list(VALID_ACTIONS),
        }
    except ValueError as exc:
        return {"error": str(exc), "valid_actions": list(VALID_ACTIONS)}
    except Exception as exc:  # noqa: BLE001 - return clean JSON, don't crash.
        return {
            "error": f"{type(exc).__name__}: {exc}",
            "valid_actions": list(VALID_ACTIONS),
        }


def main(stream_in: Any = sys.stdin, stream_out: Any = sys.stdout) -> int:
    raw = stream_in.read() or "{}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        json.dump({"error": f"invalid JSON: {exc}"}, stream_out)
        return 2
    if not isinstance(payload, dict):
        json.dump({"error": "stdin payload must be a JSON object"}, stream_out)
        return 2
    response = handle(payload)
    json.dump(response, stream_out, default=str, indent=2, sort_keys=True)
    return 1 if response.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
