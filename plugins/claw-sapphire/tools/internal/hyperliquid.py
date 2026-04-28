#!/usr/bin/env python3
"""Dry-run/status tool for Sapphire's Hyperliquid public-feed signals."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
SERVICE_SRC = ROOT / "services" / "hyperliquid" / "src"
for path in (ROOT, SERVICE_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from hyperliquid_bot.public_feed import (  # noqa: E402
    HyperliquidPublicFeedSubscriber,
    JsonlSignalStore,
    load_symbol_config,
    status_payload,
)

VALID_ACTIONS = ("status", "latest", "subscribe-test")


def handle(payload: dict[str, Any]) -> dict[str, Any]:
    """Handle a plugin payload without making network calls."""
    action = str(payload.get("action") or "status").strip().lower().replace("_", "-")
    if action == "status":
        return status_payload()
    if action == "latest":
        limit = int(payload.get("limit") or 10)
        return {"signals": JsonlSignalStore().latest(limit=limit), "limit": limit}
    if action == "subscribe-test":
        config = load_symbol_config()
        return HyperliquidPublicFeedSubscriber(config.symbols).subscribe_test()
    return {"error": f"unknown action '{action}'", "valid_actions": list(VALID_ACTIONS)}


def run(action: str = "status", **kwargs: Any) -> str:
    """Tool entry point used by direct imports and simple plugin callers."""
    return json.dumps(handle({"action": action, **kwargs}), indent=2, sort_keys=True)


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
