#!/usr/bin/env python3
"""Sapphire Hyperliquid counter-party intelligence tool."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _load_repo_lib_module(qualname: str, relpath: str):
    import importlib.util
    import types as _types

    existing = sys.modules.get(qualname)
    existing_file = getattr(existing, "__file__", "") if existing else ""
    if existing is not None and str(REPO_ROOT) in existing_file:
        return existing
    target = REPO_ROOT / relpath
    spec = importlib.util.spec_from_file_location(qualname, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot resolve Sapphire module {qualname} at {target}")
    parts = qualname.split(".")
    for i in range(1, len(parts)):
        parent = ".".join(parts[:i])
        if parent not in sys.modules or not hasattr(sys.modules[parent], "__path__"):
            mod = _types.ModuleType(parent)
            mod.__path__ = [str(REPO_ROOT / Path(*parts[:i]))]  # type: ignore[attr-defined]
            sys.modules[parent] = mod
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualname] = module
    spec.loader.exec_module(module)
    if len(parts) > 1:
        setattr(sys.modules[".".join(parts[:-1])], parts[-1], module)
    return module


_load_repo_lib_module("lib.counterparty.tracker", "lib/counterparty/tracker.py")
_load_repo_lib_module("lib.counterparty.signal_generator", "lib/counterparty/signal_generator.py")
_load_repo_lib_module("lib.counterparty.sources", "lib/counterparty/sources.py")
_counterparty_pkg = _load_repo_lib_module("lib.counterparty", "lib/counterparty/__init__.py")

HyperliquidCounterpartyClient = _counterparty_pkg.HyperliquidCounterpartyClient
generate_signals = _counterparty_pkg.generate_signals
rank_traders = _counterparty_pkg.rank_traders
track_position_changes = _counterparty_pkg.track_position_changes

VALID_ACTIONS = ("leaderboard", "position-changes", "smart-money-consensus", "status")
VERSION = "0.1.0"


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    action = str(payload.get("action") or "status").strip().lower()
    client = HyperliquidCounterpartyClient()
    if action == "status":
        return {**client.status(), "version": VERSION}
    if action == "leaderboard":
        top_n = int(payload.get("top_n") or 50)
        return {"ok": True, "traders": [t.to_dict() for t in client.leaderboard(top_n=top_n)], "version": VERSION}
    if action == "position-changes":
        changes = track_position_changes(payload.get("previous") or [], payload.get("current") or [])
        return {"ok": True, "position_changes": [c.to_dict() for c in changes], "version": VERSION}
    if action == "smart-money-consensus":
        signals = generate_signals(payload.get("position_changes") or [])
        return {"ok": True, "signals": [s.to_dict() for s in signals], "version": VERSION}
    return {"error": f"unknown action '{action}'", "valid_actions": list(VALID_ACTIONS)}


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
    json.dump(response, stream_out, indent=2, sort_keys=True, default=str)
    return 1 if response.get("error") else 0


if __name__ == "__main__":
    raise SystemExit(main())
