#!/usr/bin/env python3
"""Dry-run/live-gated tool for Sapphire on-chain intelligence 0.2.0."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT = ROOT / "plugins" / "claw-sapphire"
if str(ROOT) in sys.path:
    sys.path.remove(str(ROOT))
sys.path.insert(0, str(ROOT))
for path in list(sys.path):
    try:
        if Path(path).resolve() == PLUGIN_ROOT:
            sys.path.remove(path)
    except OSError:
        continue
loaded_lib = sys.modules.get("lib")
if loaded_lib is not None and str(PLUGIN_ROOT) in str(getattr(loaded_lib, "__file__", "")):
    sys.modules.pop("lib", None)

from services.onchain_intel.service import (  # noqa: E402
    build_status,
    collect_snapshot,
    write_snapshot,
)

VALID_ACTIONS = ("status", "providers", "snapshot", "write-snapshot")


def _parse_assets(payload: dict[str, Any]) -> list[str] | None:
    raw = payload.get("assets")
    if raw is None:
        return None
    if isinstance(raw, str):
        values = raw.split(",")
    elif isinstance(raw, list):
        values = raw
    else:
        return None
    assets = [str(value).strip().upper() for value in values if str(value).strip()]
    return assets or None


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    """Handle a plugin payload without enabling live calls by itself."""

    action = str(payload.get("action") or "status").strip().lower().replace("_", "-")
    if action == "providers":
        return {"providers": build_status()["providers"]}
    if action == "status":
        return build_status()
    if action in {"snapshot", "write-snapshot"}:
        snapshot = collect_snapshot(
            assets=_parse_assets(payload),
            backfill_days=payload.get("backfill_days"),
        )
        if action == "write-snapshot" or bool(payload.get("write")):
            snapshot["paths"] = write_snapshot(snapshot)
        return snapshot
    return {"error": f"unknown action '{action}'", "valid_actions": list(VALID_ACTIONS)}


def run(action: str = "status", **kwargs: Any) -> str:
    return json.dumps(handle({"action": action, **kwargs}), indent=2, sort_keys=True, default=str)


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
