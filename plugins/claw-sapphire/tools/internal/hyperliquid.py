#!/usr/bin/env python3
"""Dry-run/status tool for Sapphire's Hyperliquid public-feed signals.

Also exposes ``live-status`` for the trading executor — reports killswitch
state, trading-enabled flag, today's daily-loss tally, and recent trade-log
entries without touching the network or wallet keys.
"""

from __future__ import annotations

import json
import os
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
from hyperliquid_bot.risk import (  # noqa: E402
    HyperliquidLivePolicy,
    killswitch_active,
)

VALID_ACTIONS = ("status", "latest", "subscribe-test", "live-status")


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
    if action == "live-status":
        return _live_status_payload(int(payload.get("limit") or 5))
    return {"error": f"unknown action '{action}'", "valid_actions": list(VALID_ACTIONS)}


def _live_status_payload(limit: int) -> dict[str, Any]:
    policy = HyperliquidLivePolicy()
    trade_log = ROOT / policy.trade_log_path
    daily_pnl = ROOT / policy.daily_pnl_path
    return {
        "trading_enabled": os.getenv("HYPERLIQUID_TRADING_ENABLED", "0").strip().lower()
        in ("1", "true", "yes"),
        "testnet_default": os.getenv("HYPERLIQUID_TESTNET", "true").strip().lower()
        not in ("0", "false", "no", "off"),
        "signing_verified": policy.signing_verified,
        "killswitch_active": killswitch_active(policy),
        "killswitch_path": str(Path(policy.killswitch_path).expanduser()),
        "policy": policy.to_dict(),
        "daily_pnl": _read_json(daily_pnl),
        "recent_trades": _tail_jsonl(trade_log, limit),
    }


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _tail_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
    if not path.exists() or limit <= 0:
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return rows


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
