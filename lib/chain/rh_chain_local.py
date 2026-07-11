"""Read-only loader for the local Robinhood Chain mission-control state.

Reads JSON snapshots produced by the Mac-side rh-chain poller and orderflow
collector in ``~/ops-state/rh-chain/``.  No network calls; no signing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

RH_CHAIN_STATE_DIR = Path.home() / "ops-state" / "rh-chain"
VISUALIZER_URL = "http://127.0.0.1:8146/"
_MAX_FILE_BYTES = 8 * 1024 * 1024


def _load_json_file(name: str) -> dict[str, Any]:
    """Load a single JSON state file, returning an empty dict on any failure."""
    path = RH_CHAIN_STATE_DIR / name
    try:
        if not path.exists():
            return {}
        size = path.stat().st_size
        if size > _MAX_FILE_BYTES:
            log.warning("%s is %.2f MB; skipping oversized local state", name, size / (1024 * 1024))
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        log.warning("failed to load %s: %s", name, exc)
        return {}


def _network_summary(raw: dict[str, Any]) -> dict[str, Any]:
    """Summarize the per-network section of rh-chain-state.json."""
    nets = raw.get("networks") or {}
    out: dict[str, Any] = {}
    for name, net in nets.items():
        if not isinstance(net, dict):
            continue
        tokens = net.get("tokens") or []
        stock_tokens = net.get("stock_tokens") or []
        wallet = net.get("wallet") or {}
        out[name] = {
            "chain_id": net.get("chain_id"),
            "chain": net.get("chain"),
            "latest_block": net.get("latest_block"),
            "gas_gwei": net.get("gas_gwei"),
            "block_time_s": net.get("block_time_s"),
            "rpc_ok": net.get("rpc_ok"),
            "token_count": len(tokens) if isinstance(tokens, list) else 0,
            "stock_token_count": len(stock_tokens) if isinstance(stock_tokens, list) else 0,
            "wallet_funded": wallet.get("funded") if isinstance(wallet, dict) else None,
            "wallet_balance_eth": wallet.get("balance_eth") if isinstance(wallet, dict) else None,
        }
    return out


def _ai_summary(raw: dict[str, Any]) -> dict[str, Any]:
    """Summarize the AI trading-system section of rh-chain-state.json."""
    ai = raw.get("ai") or {}
    adv = ai.get("advisory") or {}
    gpu = ai.get("gpu_node") or {}
    return {
        "banner": ai.get("banner"),
        "advisory_date": adv.get("date"),
        "advisory_row_count": len(adv.get("rows") or []),
        "advisory_stale": adv.get("stale"),
        "advisory_age_h": adv.get("age_h"),
        "forecaster": adv.get("forecaster"),
        "gpu_status": gpu.get("status") if isinstance(gpu, dict) else None,
        "gpu_services": gpu.get("services") if isinstance(gpu, dict) else None,
    }


def _feed_summary(raw: dict[str, Any]) -> dict[str, Any]:
    """Summarize the sequencer-feed section of rh-chain-state.json."""
    feed = raw.get("feed") or {}
    return {
        "connected": feed.get("connected") if isinstance(feed, dict) else None,
        "msgs_per_min": feed.get("msgs_per_min") if isinstance(feed, dict) else None,
        "feed_lag_s": feed.get("feed_lag_s") if isinstance(feed, dict) else None,
        "last_seq": feed.get("last_seq") if isinstance(feed, dict) else None,
    }


def build_local_state_summary() -> dict[str, Any]:
    """Return a dashboard-ready summary of the local RH Chain stack.

    The payload is intentionally compact: it exposes block/gas/network health,
    the AI advisory snapshot, feed health, and memes-state metadata without
    shipping the full token lists on every page load.
    """
    chain_state = _load_json_file("rh-chain-state.json")
    memes_state = _load_json_file("memes-state.json")
    feed_state = _load_json_file("rh-feed-state.json")

    updated = chain_state.get("updated")
    if isinstance(memes_state.get("updated"), int):
        updated = max(updated or 0, memes_state["updated"])

    tokens = memes_state.get("tokens") or []
    tape = memes_state.get("tape") or []
    alerts = memes_state.get("alerts") or []
    ideas = memes_state.get("ideas") or []

    return {
        "ok": bool(chain_state),
        "mode": "local_state_summary",
        "visualizer_url": VISUALIZER_URL,
        "updated": updated,
        "networks": _network_summary(chain_state),
        "ai": _ai_summary(chain_state),
        "feed": _feed_summary(chain_state) if chain_state else feed_state,
        "memes": {
            "head_block": memes_state.get("head_block"),
            "token_count": len(tokens) if isinstance(tokens, list) else 0,
            "tape_count": len(tape) if isinstance(tape, list) else 0,
            "alert_count": len(alerts) if isinstance(alerts, list) else 0,
            "idea_count": len(ideas) if isinstance(ideas, list) else 0,
            "backfill_done": memes_state.get("backfill_done"),
            "weth_usd": memes_state.get("weth_usd"),
        },
        "event_count": len(chain_state.get("event_log") or []),
    }


def load_memes_state() -> dict[str, Any]:
    """Return the full memes-state.json (or an empty dict if absent)."""
    return _load_json_file("memes-state.json")


def load_feed_state() -> dict[str, Any]:
    """Return the full rh-feed-state.json (or an empty dict if absent)."""
    return _load_json_file("rh-feed-state.json")
