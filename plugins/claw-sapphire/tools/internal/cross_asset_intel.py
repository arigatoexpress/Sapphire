#!/usr/bin/env python3
"""Sapphire Cross-Asset Intel plugin tool.

Stdin-JSON actions:

- ``matrix``: return a selected rolling correlation matrix.
- ``regime``: return the deterministic current regime label.
- ``breakdowns``: return active correlation breakdown events.
- ``lead-lag``: return strongest lead/lag pairs.
- ``status``: return caps and cache/live-gate posture without fetching data.
"""

from __future__ import annotations

import json
import os
import sys
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

from lib.cross_asset.correlation_matrix import (  # noqa: E402
    DEFAULT_METHODS,
    DEFAULT_WINDOWS,
    MAX_ASSETS_HARD,
    MAX_WINDOW_DAYS,
    MIN_OBSERVATIONS_PER_WINDOW,
)
from lib.cross_asset.sources import CACHE_ROOT, DEFAULT_ASSET_MAP, LIVE_ENV  # noqa: E402
from services.cross_asset.run import VERSION, build_snapshot  # noqa: E402

VALID_ACTIONS = ("matrix", "regime", "breakdowns", "lead-lag", "status")
DEFAULT_WINDOW = "7d"
DEFAULT_METHOD = "pearson"


def _coerce_assets(raw: Any) -> list[str] | None:
    if raw in (None, "", []):
        return None
    if isinstance(raw, str):
        assets = [item.strip().upper() for item in raw.split(",") if item.strip()]
    elif isinstance(raw, list):
        assets = [str(item).strip().upper() for item in raw if str(item).strip()]
    else:
        raise ValueError("assets must be a comma-separated string or list")
    if len(assets) > MAX_ASSETS_HARD:
        raise ValueError(f"asset count exceeds MAX_ASSETS_HARD={MAX_ASSETS_HARD}")
    return list(dict.fromkeys(assets))


def _snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    live = bool(payload.get("live"))
    return build_snapshot(assets=_coerce_assets(payload.get("assets")), live=live)


def matrix_action(payload: dict[str, Any]) -> dict[str, Any]:
    snap = _snapshot(payload)
    window = str(payload.get("window") or DEFAULT_WINDOW)
    method = str(payload.get("method") or DEFAULT_METHOD).lower()
    windows = snap.get("matrix", {}).get("windows", {})
    selected = (windows.get(window) or {}).get(method)
    if selected is None and windows:
        first_window = next(iter(windows))
        first_methods = windows[first_window]
        first_method = method if method in first_methods else next(iter(first_methods))
        selected = first_methods[first_method]
        window = first_window
        method = first_method
    return {
        "ok": selected is not None,
        "action": "matrix",
        "version": VERSION,
        "mode": snap.get("mode"),
        "window": window,
        "method": method,
        "matrix": selected,
        "breakdown_count": len(snap.get("breakdowns") or []),
        "generated_at": snap.get("generated_at"),
        "provenance": snap.get("provenance"),
    }


def regime_action(payload: dict[str, Any]) -> dict[str, Any]:
    snap = _snapshot(payload)
    return {
        "ok": True,
        "action": "regime",
        "version": VERSION,
        "mode": snap.get("mode"),
        "regime": snap.get("regime"),
        "generated_at": snap.get("generated_at"),
        "provenance": snap.get("provenance"),
    }


def breakdowns_action(payload: dict[str, Any]) -> dict[str, Any]:
    snap = _snapshot(payload)
    limit = int(payload.get("limit") or 25)
    return {
        "ok": True,
        "action": "breakdowns",
        "version": VERSION,
        "mode": snap.get("mode"),
        "breakdowns": (snap.get("breakdowns") or [])[: max(0, limit)],
        "generated_at": snap.get("generated_at"),
        "provenance": snap.get("provenance"),
    }


def lead_lag_action(payload: dict[str, Any]) -> dict[str, Any]:
    snap = _snapshot(payload)
    limit = int(payload.get("limit") or 12)
    return {
        "ok": True,
        "action": "lead-lag",
        "version": VERSION,
        "mode": snap.get("mode"),
        "lead_lag": (snap.get("lead_lag") or [])[: max(0, limit)],
        "generated_at": snap.get("generated_at"),
        "provenance": snap.get("provenance"),
    }


def status_action() -> dict[str, Any]:
    return {
        "ok": True,
        "action": "status",
        "version": VERSION,
        "valid_actions": list(VALID_ACTIONS),
        "live_env": os.environ.get(LIVE_ENV, "") == "1",
        "cache_root": str(CACHE_ROOT),
        "default_assets": sorted(DEFAULT_ASSET_MAP),
        "caps": {
            "max_assets_hard": MAX_ASSETS_HARD,
            "max_window_days": MAX_WINDOW_DAYS,
            "min_observations_per_window": MIN_OBSERVATIONS_PER_WINDOW,
            "default_windows": dict(DEFAULT_WINDOWS),
            "methods": list(DEFAULT_METHODS),
        },
    }


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "status").strip().lower().replace("_", "-")
    try:
        if action == "matrix":
            return matrix_action(payload)
        if action == "regime":
            return regime_action(payload)
        if action == "breakdowns":
            return breakdowns_action(payload)
        if action in {"lead-lag", "leadlag"}:
            return lead_lag_action(payload)
        if action == "status":
            return status_action()
        return {"error": f"unknown action '{action}'", "valid_actions": list(VALID_ACTIONS)}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}", "valid_actions": list(VALID_ACTIONS)}


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
    json.dump(response, stream_out, indent=2, sort_keys=True)
    return 1 if response.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
