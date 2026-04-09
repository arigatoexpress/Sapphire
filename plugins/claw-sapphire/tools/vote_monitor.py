#!/usr/bin/env python3
"""Sapphire Vote Monitor Bridge — connects ve Vote Monitor to the trading pipeline.

Bridges the regional-intel-workbench vote escrow monitoring system into
Sapphire for autonomous strategy tracking across:
- Blackhole (veBLACK on Avalanche)
- Supernova (veNOVA on Ethereum)
- Full Sail (veSAIL on Sui)

Actions:
    snapshot  — Fetch live pool data from all protocols
    strategy  — Get allocation recommendations (conservative/aggressive)
    digest    — Human-readable strategy digest
    perf      — Replay evaluator: strategy quality metrics

Usage (stdin JSON):
    echo '{"action":"snapshot"}' | python3 vote_monitor.py
    echo '{"action":"strategy","profile":"aggressive"}' | python3 vote_monitor.py
    echo '{"action":"digest","blackhole":15000,"supernova":8000,"fullsail":50000}' | python3 vote_monitor.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
VOTE_DATA_DIR = SAPPHIRE_DIR / "data" / "vote_monitor"
VOTE_DATA_DIR.mkdir(parents=True, exist_ok=True)

RIW_DIR = Path.home() / "Code" / "regional-intel-workbench"
VE_API_BASE = "http://127.0.0.1:8787"

# Default vote balances (configurable per action)
DEFAULT_BALANCES = {
    "blackhole": 15000,
    "supernova": 8000,
    "fullsail": 50000,
}


def _call_api(endpoint: str, params: dict = None) -> dict | None:
    """Call the ve vote monitor API."""
    import urllib.request
    import urllib.parse

    url = f"{VE_API_BASE}{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        return {"error": str(e)}


def _call_cli(args: list[str]) -> str | None:
    """Call the ve vote monitor CLI."""
    try:
        result = subprocess.run(
            ["uv", "run", "python", "-m", "app.cli"] + args,
            capture_output=True, text=True, timeout=30,
            cwd=str(RIW_DIR),
        )
        return result.stdout if result.returncode == 0 else result.stderr
    except Exception as e:
        return f"CLI error: {e}"


def action_snapshot() -> dict:
    """Fetch live pool data from all protocols."""
    data = _call_api("/api/snapshot")
    if data and "error" not in data:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        (VOTE_DATA_DIR / f"snapshot_{ts}.json").write_text(json.dumps(data, indent=2))
        return {
            "success": True,
            "protocols": list(data.keys()) if isinstance(data, dict) else [],
            "saved_to": str(VOTE_DATA_DIR / f"snapshot_{ts}.json"),
        }
    # Fallback: try CLI
    output = _call_cli(["snapshot"])
    return {"success": output is not None, "output": (output or "")[:2000], "method": "cli"}


def action_strategy(profile: str = "conservative", **balances) -> dict:
    """Get allocation recommendations."""
    params = {
        "blackhole": balances.get("blackhole", DEFAULT_BALANCES["blackhole"]),
        "supernova": balances.get("supernova", DEFAULT_BALANCES["supernova"]),
        "fullsail": balances.get("fullsail", DEFAULT_BALANCES["fullsail"]),
        "profile": profile,
    }
    data = _call_api("/api/strategy", params)
    if data and "error" not in data:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        (VOTE_DATA_DIR / f"strategy_{profile}_{ts}.json").write_text(json.dumps(data, indent=2))
        return {"success": True, "strategy": data, "profile": profile}
    return {"success": False, "error": data.get("error", "Unknown") if data else "API unreachable"}


def action_digest(profile: str = "conservative", **balances) -> dict:
    """Get a human-readable strategy digest."""
    params = {
        "blackhole": balances.get("blackhole", DEFAULT_BALANCES["blackhole"]),
        "supernova": balances.get("supernova", DEFAULT_BALANCES["supernova"]),
        "fullsail": balances.get("fullsail", DEFAULT_BALANCES["fullsail"]),
        "profile": profile,
        "format": "text",
    }
    data = _call_api("/api/digest", params)
    if data and "error" not in data:
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = VOTE_DATA_DIR / f"digest_{profile}_{ts}.md"
        text = data.get("text", data.get("digest", json.dumps(data, indent=2)))
        path.write_text(text if isinstance(text, str) else json.dumps(text, indent=2))
        return {"success": True, "profile": profile, "saved_to": str(path), "preview": str(text)[:1000]}
    return {"success": False, "error": data.get("error", "Unknown") if data else "API unreachable"}


def action_performance(profile: str = "conservative", **balances) -> dict:
    """Get strategy replay evaluator results."""
    params = {
        "blackhole": balances.get("blackhole", DEFAULT_BALANCES["blackhole"]),
        "supernova": balances.get("supernova", DEFAULT_BALANCES["supernova"]),
        "fullsail": balances.get("fullsail", DEFAULT_BALANCES["fullsail"]),
        "profile": profile,
    }
    data = _call_api("/api/performance", params)
    if data and "error" not in data:
        return {"success": True, "performance": data, "profile": profile}
    return {"success": False, "error": data.get("error", "Unknown") if data else "API unreachable"}


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        raw = '{"action": "snapshot"}'

    try:
        params = json.loads(raw)
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}))
        return

    action = params.get("action", "snapshot")
    profile = params.get("profile", "conservative")
    balances = {k: params.get(k, DEFAULT_BALANCES.get(k)) for k in ["blackhole", "supernova", "fullsail"]}

    if action == "snapshot":
        result = action_snapshot()
    elif action == "strategy":
        result = action_strategy(profile=profile, **balances)
    elif action == "digest":
        result = action_digest(profile=profile, **balances)
    elif action == "perf":
        result = action_performance(profile=profile, **balances)
    else:
        result = {"error": f"Unknown action: {action}. Use: snapshot, strategy, digest, perf"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
