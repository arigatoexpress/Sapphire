#!/usr/bin/env python3
"""Brain → Sapphire bridge.

Reads the quant-perps ``brain.advisory`` output (``~/ops-state/advisory/advisory-latest.json``)
and exposes it in a Sapphire-native shape so the dashboard and trading brain can consume
crypto-proxy equity signals (MSTR / IBIT / TSLA / SPY) alongside native crypto decisions.

The bridge is intentionally read-only and advisory-only:
- ``publish`` defaults to dry-run and only prints what would be sent on-chain.
- No private keys are read; no orders are placed.

Usage:
    echo '{"action":"read"}'   | python3 brain_advisory_bridge.py
    echo '{"action":"dashboard"}' | python3 brain_advisory_bridge.py
    echo '{"action":"decide","symbol":"BTC"}' | python3 brain_advisory_bridge.py
    echo '{"action":"publish","live":false}' | python3 brain_advisory_bridge.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ADVISORY_PATH = Path(
    os.environ.get("BRAIN_ADVISORY_JSON", "~/ops-state/advisory/advisory-latest.json")
).expanduser()

# Map Sapphire-native crypto symbols to the crypto-proxy equity symbols in the
# advisory cluster. Currently only BTC has a liquid proxy (IBIT); ETH/SOL have
# none in this cluster and will receive a neutral "no advisory row" vote.
PROXY_MAP: dict[str, str] = {
    "BTC": "IBIT",
}

# Invert for advisory -> native lookups.
_ADVISORY_TO_NATIVE: dict[str, list[str]] = {}
for _native, _proxy in PROXY_MAP.items():
    _ADVISORY_TO_NATIVE.setdefault(_proxy, []).append(_native)

ADVISORY_STALE_SECONDS = int(os.environ.get("BRAIN_ADVISORY_STALE_SECONDS", "86400"))


def _load_advisory() -> dict[str, Any]:
    if not ADVISORY_PATH.exists():
        return {
            "error": f"advisory file not found: {ADVISORY_PATH}",
            "rows": [],
        }
    try:
        with ADVISORY_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        return {"error": f"advisory JSON invalid: {exc}", "rows": []}
    except OSError as exc:
        return {"error": f"advisory read failed: {exc}", "rows": []}


def _advisory_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    return [r for r in rows if isinstance(r, dict)]


def _row_for_symbol(rows: list[dict[str, Any]], symbol: str) -> dict[str, Any] | None:
    sym = symbol.upper()
    for row in rows:
        if str(row.get("symbol", "")).upper() == sym:
            return row
    return None


def _is_stale(payload: dict[str, Any]) -> bool:
    ts = payload.get("generated_ts")
    if not isinstance(ts, int | float):
        return True
    return (datetime.now(UTC).timestamp() - ts) > ADVISORY_STALE_SECONDS


def _advisory_to_decision(
    row: dict[str, Any] | None, symbol: str = "", proxy_symbol: str = ""
) -> dict[str, Any]:
    """Translate an advisory row into Sapphire trading-brain vocabulary."""
    if row is None:
        return {
            "signal": "WAIT",
            "direction": "neutral",
            "confidence": 0.0,
            "source": "BrainAdvisory",
            "detail": "no advisory row",
        }

    signal = str(row.get("signal", "FLAT")).upper()
    score = row.get("score")
    close = row.get("close")
    forecast = row.get("forecast") or {}
    regime = row.get("regime", "unknown")

    if signal == "LONG":
        decision = "GO_LONG"
        direction = "bullish"
        confidence = (
            min(0.95, max(0.5, (score + 0.5) / 1.5)) if isinstance(score, int | float) else 0.6
        )
    elif signal == "SHORT":
        decision = "GO_SHORT"
        direction = "bearish"
        confidence = (
            min(0.95, max(0.5, (abs(score) + 0.5) / 1.5)) if isinstance(score, int | float) else 0.6
        )
    else:
        decision = "WAIT"
        direction = "neutral"
        confidence = 0.2

    detail = f"advisory {signal}"
    if proxy_symbol and proxy_symbol != symbol:
        detail += f" via {proxy_symbol}"
    detail += f" | regime={regime}"
    if isinstance(close, int | float):
        detail += f" | close={close:.2f}"
    if isinstance(forecast.get("point"), int | float) and isinstance(close, int | float):
        pct = (forecast["point"] - close) / close * 100 if close else 0.0
        detail += f" | forecast={pct:+.1f}%"

    return {
        "signal": decision,
        "direction": direction,
        "confidence": round(confidence, 2),
        "source": "BrainAdvisory",
        "detail": detail,
        "advisory": row,
    }


def action_read() -> dict[str, Any]:
    """Return the advisory payload with bridge metadata."""
    payload = _load_advisory()
    rows = _advisory_rows(payload)
    return {
        "success": "error" not in payload,
        "advisory_path": str(ADVISORY_PATH),
        "exists": ADVISORY_PATH.exists(),
        "stale": _is_stale(payload),
        "stale_threshold_seconds": ADVISORY_STALE_SECONDS,
        "row_count": len(rows),
        "banner": payload.get("banner"),
        "date": payload.get("date"),
        "forecaster": payload.get("forecaster"),
        "error": payload.get("error"),
        "rows": rows,
    }


def action_decide(symbol: str) -> dict[str, Any]:
    """Return a Sapphire-style decision for a native or proxy symbol."""
    payload = _load_advisory()
    rows = _advisory_rows(payload)
    proxy = PROXY_MAP.get((symbol or "").upper())

    if proxy:
        row = _row_for_symbol(rows, proxy)
        decision = _advisory_to_decision(row, symbol=symbol, proxy_symbol=proxy)
        decision["symbol"] = symbol.upper()
        decision["proxy_symbol"] = proxy
    else:
        row = _row_for_symbol(rows, symbol)
        decision = _advisory_to_decision(row, symbol=symbol)
        decision["symbol"] = symbol.upper()

    decision["advisory_stale"] = _is_stale(payload)
    decision["advisory_path"] = str(ADVISORY_PATH)
    decision["timestamp"] = datetime.now(UTC).isoformat()
    return decision


def action_dashboard() -> dict[str, Any]:
    """Return decisions for every advisory row plus native crypto proxies."""
    payload = _load_advisory()
    rows = _advisory_rows(payload)
    decisions: dict[str, dict[str, Any]] = {}

    # Native crypto decisions via proxies.
    for native in PROXY_MAP:
        decisions[native] = action_decide(native)

    # Direct advisory symbols (avoid duplicates).
    seen = {d.get("proxy_symbol") for d in decisions.values()}
    for row in rows:
        sym = str(row.get("symbol", "")).upper()
        if not sym or sym in seen:
            continue
        decisions[sym] = action_decide(sym)

    return {
        "success": "error" not in payload,
        "advisory_path": str(ADVISORY_PATH),
        "stale": _is_stale(payload),
        "decisions": decisions,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def action_publish(live: bool = False) -> dict[str, Any]:
    """Translate advisory LONG rows into RH Chain signal payloads.

    Default is dry-run. When ``live`` is false the function returns the list of
    signals that *would* be published but never touches web3 or private keys.
    """
    payload = _load_advisory()
    rows = _advisory_rows(payload)
    signals: list[dict[str, Any]] = []

    for row in rows:
        if row.get("is_reference"):
            continue
        signal = str(row.get("signal", "FLAT")).upper()
        if signal not in ("LONG", "SHORT"):
            continue
        direction = "long" if signal == "LONG" else "short"
        score = row.get("score")
        confidence = (
            min(0.95, max(0.5, (score + 0.5) / 1.5)) if isinstance(score, int | float) else 0.6
        )

        signals.append(
            {
                "strategy": "brain_advisory",
                "symbol": str(row.get("symbol", "")).upper(),
                "direction": direction,
                "confidence": round(confidence, 4),
                "proof_hash": None,
                "live": live,
            }
        )

    result = {
        "success": "error" not in payload,
        "mode": "live" if live else "dry-run",
        "count": len(signals),
        "signals": signals,
        "advisory_path": str(ADVISORY_PATH),
        "stale": _is_stale(payload),
        "note": "dry-run: no transaction signed or sent"
        if not live
        else "live: caller must supply private key",
    }
    if not live:
        result["next_step"] = "set live=true and configure RH private key to publish on-chain"
    return result


def main() -> None:
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {"action": "dashboard"}
    action = params.get("action", "dashboard")

    if action == "read":
        result = action_read()
    elif action == "decide":
        result = action_decide(params.get("symbol", "BTC"))
    elif action == "dashboard":
        result = action_dashboard()
    elif action == "publish":
        result = action_publish(live=_boolish(params.get("live")))
    else:
        result = {"error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2, default=str))


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    main()
