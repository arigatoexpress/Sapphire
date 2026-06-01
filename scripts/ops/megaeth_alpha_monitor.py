#!/usr/bin/env python3
"""MegaETH live alpha monitor — one-shot snapshot for the 3h routine.

Writes data/megaeth/alpha_log.jsonl on the monitoring/megaeth-alpha-log
branch and data/megaeth/alerts.jsonl + opens a PR on threshold breaches.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import sys
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

sys.path.insert(0, ".")

RPC_URL = "https://mainnet.megaeth.com/rpc"
EXPECTED_CHAIN_ID = 0x10E6  # 4326

# ── alert thresholds ─────────────────────────────────────────────────────────
USDM_ALERT_SEVERITIES = {"BREAK_100BP", "CRISIS_500BP", "CIRCUIT_BREAKER"}
AAVE_UTILIZATION_ALERT = 0.95   # 95%
GMX_FUNDING_APR_ALERT = 2.00    # 200% abs


def _to_json(obj: Any) -> Any:
    """Recursively convert dataclasses / Decimals to JSON-safe primitives."""
    if isinstance(obj, Decimal):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_json(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json(x) for x in obj]
    # Enum
    if hasattr(obj, "value") and hasattr(obj, "name"):
        return obj.name
    return obj


async def _rpc(method: str, params: list[Any] | None = None) -> Any:
    import httpx
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.post(RPC_URL, json=payload)
        r.raise_for_status()
        body = r.json()
    if "error" in body:
        raise RuntimeError(f"RPC error: {body['error']}")
    return body["result"]


async def run_snapshot() -> dict[str, Any]:
    ts = datetime.now(timezone.utc).isoformat()
    snapshot: dict[str, Any] = {"ts": ts}

    # ── chain liveness ───────────────────────────────────────────────────────
    try:
        raw_chain = await _rpc("eth_chainId")
        chain_id = int(raw_chain, 16) if isinstance(raw_chain, str) else int(raw_chain)
        raw_block = await _rpc("eth_blockNumber")
        block_number = int(raw_block, 16) if isinstance(raw_block, str) else int(raw_block)
        snapshot["chain_id"] = chain_id
        snapshot["block_number"] = block_number
    except Exception as exc:
        snapshot["chain_id"] = None
        snapshot["block_number"] = None
        snapshot["rpc_error"] = str(exc)
        snapshot["mode"] = "rpc_failure"
        return snapshot

    # ── try full library path ────────────────────────────────────────────────
    has_lib = False
    try:
        from lib.chains.megaeth.protocols import MegaETHProtocols
        # Adapter: the protocol library expects a client whose _call matches
        # the MegaETHClient._call signature.  We create a thin async adapter
        # around our raw httpx helper so we don't need the internal module
        # import (which fails due to claw-sapphire's package structure).
        class _ClientAdapter:
            async def _call(self, method: str, params: list[Any] | None = None) -> Any:
                return await _rpc(method, params)

        client = _ClientAdapter()
        protocols = MegaETHProtocols(client)
        has_lib = True
    except ImportError:
        has_lib = False

    snapshot["mode"] = "full" if has_lib else "fallback"

    if not has_lib:
        return snapshot

    # ── lend (Aave V3) ───────────────────────────────────────────────────────
    try:
        lend = await protocols.lend_overview()
        snapshot["lend"] = _to_json(lend)
    except Exception as exc:
        snapshot["lend"] = {"error": str(exc), "traceback": traceback.format_exc()}

    # ── stable (USDM peg) ────────────────────────────────────────────────────
    try:
        stable = await protocols.stable_health()
        snapshot["stable"] = _to_json(stable)
    except Exception as exc:
        snapshot["stable"] = {"error": str(exc)}

    # ── perps (GMX V2) ───────────────────────────────────────────────────────
    try:
        perps = await protocols.perps_overview()  # type: ignore[attr-defined]
        snapshot["perps"] = _to_json(perps)
    except AttributeError:
        snapshot["perps"] = {"note": "perps_overview not in Wave A facade"}
    except Exception as exc:
        snapshot["perps"] = {"error": str(exc)}

    return snapshot


def compute_alerts(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    # ── chain liveness alert ─────────────────────────────────────────────────
    chain_id = snapshot.get("chain_id")
    if chain_id is None or snapshot.get("mode") == "rpc_failure":
        alerts.append({
            "type": "chain_rpc_failure",
            "severity": "CRITICAL",
            "detail": snapshot.get("rpc_error", "unknown"),
        })
    elif chain_id != EXPECTED_CHAIN_ID:
        alerts.append({
            "type": "chain_id_mismatch",
            "severity": "CRITICAL",
            "expected": hex(EXPECTED_CHAIN_ID),
            "actual": hex(chain_id),
        })

    # ── USDM peg alert ───────────────────────────────────────────────────────
    stable = snapshot.get("stable", {})
    if isinstance(stable, dict) and "error" not in stable:
        severity = stable.get("severity")
        if severity in USDM_ALERT_SEVERITIES:
            peg = stable.get("peg_snapshot", {})
            alerts.append({
                "type": "usdm_depeg",
                "severity": severity,
                "divergence_bps": peg.get("max_divergence_bps") if isinstance(peg, dict) else None,
                "block_reason": stable.get("block_reason"),
            })

    # ── Aave utilization alert ───────────────────────────────────────────────
    lend = snapshot.get("lend", {})
    if isinstance(lend, dict) and "error" not in lend:
        for r in lend.get("reserves", []):
            if not isinstance(r, dict):
                continue
            util = r.get("utilization_rate") or r.get("utilizationRate")
            if util is None:
                # compute from raw totals
                supplied = r.get("total_supplied") or r.get("totalSupply") or 0
                borrowed = r.get("total_borrowed") or r.get("totalBorrow") or 0
                if supplied:
                    util = borrowed / supplied
            if util is not None and float(util) > AAVE_UTILIZATION_ALERT:
                alerts.append({
                    "type": "aave_utilization_critical",
                    "severity": "HIGH",
                    "symbol": r.get("symbol"),
                    "utilization_pct": round(float(util) * 100, 2),
                })

    # ── GMX funding rate alert (Aave-priced markets only) ────────────────────
    perps = snapshot.get("perps", {})
    if isinstance(perps, dict) and "error" not in perps and "note" not in perps:
        for market in perps.get("markets", []):
            if not isinstance(market, dict):
                continue
            # Skip unpriced markets (BTC + synthetics have no Aave oracle price)
            if market.get("oracle_source") != "aave":
                continue
            funding_apr = market.get("funding_rate_apr") or market.get("fundingRateApr") or 0
            if abs(float(funding_apr)) > GMX_FUNDING_APR_ALERT:
                alerts.append({
                    "type": "gmx_funding_extreme",
                    "severity": "HIGH",
                    "market": market.get("symbol") or market.get("market"),
                    "funding_rate_apr": round(float(funding_apr) * 100, 2),
                })

    return alerts


def _load_last_snapshot() -> dict[str, Any] | None:
    log_path = "data/megaeth/alpha_log.jsonl"
    if not os.path.exists(log_path):
        return None
    try:
        with open(log_path) as f:
            lines = [l.strip() for l in f if l.strip()]
        if not lines:
            return None
        return json.loads(lines[-1])
    except Exception:
        return None


def check_block_staleness(snapshot: dict[str, Any], last: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Flag if block_number hasn't moved vs prior snapshot (>30 min stale)."""
    if last is None:
        return []
    cur_block = snapshot.get("block_number")
    last_block = last.get("block_number")
    if cur_block is None or last_block is None:
        return []
    try:
        last_ts = datetime.fromisoformat(last["ts"])
        cur_ts = datetime.fromisoformat(snapshot["ts"])
        delta_min = (cur_ts - last_ts).total_seconds() / 60
    except Exception:
        return []
    if cur_block == last_block and delta_min > 30:
        return [{
            "type": "chain_block_stale",
            "severity": "CRITICAL",
            "block_number": cur_block,
            "stale_minutes": round(delta_min, 1),
        }]
    return []


async def main() -> None:
    print(f"[megaeth-monitor] starting snapshot at {datetime.now(timezone.utc).isoformat()}")

    last_snapshot = _load_last_snapshot()
    snapshot = await run_snapshot()

    alerts = compute_alerts(snapshot)
    stale_alerts = check_block_staleness(snapshot, last_snapshot)
    alerts.extend(stale_alerts)

    snapshot["alerts"] = alerts

    # Write snapshot to temp file for git ingestion
    os.makedirs("data/megaeth", exist_ok=True)
    snapshot_line = json.dumps(snapshot, default=str)
    with open("/tmp/megaeth_snapshot.json", "w") as f:
        json.dump(snapshot, f, default=str, indent=2)

    # Print report
    mode = snapshot.get("mode", "unknown")
    block = snapshot.get("block_number", "N/A")
    cid = hex(snapshot["chain_id"]) if snapshot.get("chain_id") else "N/A"

    print(f"\n--- MegaETH Alpha Snapshot ---")
    print(f"  ts:          {snapshot['ts']}")
    print(f"  mode:        {mode}")
    print(f"  chain_id:    {cid}  block: {block}")

    lend = snapshot.get("lend", {})
    if isinstance(lend, dict) and "error" not in lend:
        tvl = lend.get("total_supplied_usd") or 0
        borrow = lend.get("total_borrowed_usd") or 0
        reserves = lend.get("reserve_count", "?")
        print(f"  lend:        TVL=${tvl:,.0f}  Borrowed=${borrow:,.0f}  ({reserves} reserves)")
    elif isinstance(lend, dict) and "error" in lend:
        print(f"  lend:        ERROR - {lend['error'][:80]}")

    stable = snapshot.get("stable", {})
    if isinstance(stable, dict) and "error" not in stable:
        sev = stable.get("severity", "?")
        supply = stable.get("circulating_supply") or 0
        print(f"  stable:      USDM peg={sev}  supply={supply:,.0f}")
    elif isinstance(stable, dict) and "error" in stable:
        print(f"  stable:      ERROR - {stable['error'][:80]}")

    perps = snapshot.get("perps", {})
    if isinstance(perps, dict):
        if "note" in perps:
            print(f"  perps:       {perps['note']}")
        elif "error" in perps:
            print(f"  perps:       ERROR - {perps['error'][:80]}")
        else:
            mkts = len(perps.get("markets", []))
            print(f"  perps:       {mkts} markets")

    if alerts:
        print(f"\n  ALERTS ({len(alerts)}):")
        for a in alerts:
            print(f"    [{a['severity']}] {a['type']}: {json.dumps({k: v for k, v in a.items() if k not in ('type','severity')})}")
    else:
        print(f"  ALERTS:      NONE")

    # Write result for shell consumption
    with open("/tmp/megaeth_alerts.json", "w") as f:
        json.dump(alerts, f, default=str)

    print("\n[megaeth-monitor] snapshot complete.")


if __name__ == "__main__":
    asyncio.run(main())
