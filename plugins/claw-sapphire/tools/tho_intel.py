#!/usr/bin/env python3
"""Sapphire THO Market Intelligence — housing market insights for Texas Home Outlet.

Combines FRED housing data + Regional Intel permits + customer analytics
to provide actionable market intelligence for the THO business.

Actions:
    market     — Housing market overview (rates, starts, prices, permits)
    buyers     — Buyer readiness indicators (affordability, demand signals)
    report     — Full market intelligence report

Usage:
    echo '{"action":"market"}' | python3 tho_intel.py
    echo '{"action":"buyers"}' | python3 tho_intel.py
"""

from __future__ import annotations

import json
import ssl
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
TOOLS_DIR = SAPPHIRE_DIR / "plugins" / "claw-sapphire" / "tools"


def _run_tool(name: str, params: dict) -> dict:
    try:
        r = subprocess.run(
            [sys.executable, str(TOOLS_DIR / f"{name}.py")],
            input=json.dumps(params), capture_output=True, text=True, timeout=30,
        )
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except Exception:
        return {}


def action_market() -> dict:
    """Housing market overview combining FRED + Regional Intel."""
    # FRED housing data
    housing = _run_tool("macro_data", {"action": "housing"})
    rates = _run_tool("macro_data", {"action": "rates"})

    # Regional Intel permits
    permits = []
    try:
        url = "http://127.0.0.1:8787/api/intel/snapshot?region=houston_tx"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        permits = data.get("permits", [])
    except Exception:
        pass

    # THO customer stats
    tho_stats = {}
    try:
        import certifi
        ctx = ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        ctx = ssl.create_default_context()
    try:
        token_resp = urllib.request.urlopen(urllib.request.Request(
            "https://project-go-forward-691674245427.us-central1.run.app/api/admin/verify",
            data=json.dumps({"pin": "4832"}).encode(),
            headers={"Content-Type": "application/json"},
        ), timeout=10, context=ctx)
        token = json.loads(token_resp.read()).get("token", "")
        if token:
            stats_resp = urllib.request.urlopen(urllib.request.Request(
                "https://project-go-forward-691674245427.us-central1.run.app/api/analytics/customers",
                headers={"X-Admin-Token": token},
            ), timeout=10, context=ctx)
            tho_stats = json.loads(stats_resp.read())
    except Exception:
        pass

    # Analyze
    mortgage_rate = None
    for label, info in (housing.get("housing", {}) or {}).items():
        if "Mortgage" in label:
            mortgage_rate = info.get("value")

    analysis = {
        "mortgage_rate": mortgage_rate,
        "affordability": "challenging" if mortgage_rate and mortgage_rate > 6.5 else "moderate" if mortgage_rate and mortgage_rate > 5.5 else "favorable",
        "houston_permits": len(permits),
        "new_subdivisions": sum(1 for p in permits if "subdivision" in str(p).lower()),
        "tho_customers": tho_stats.get("total", 0),
        "tho_conversion": tho_stats.get("conversion_rate", 0),
        "tho_recent_leads": len(tho_stats.get("recent_leads", [])),
    }

    # Market sentiment
    if mortgage_rate and mortgage_rate < 6:
        analysis["market_sentiment"] = "bullish — rates dropping, demand should increase"
    elif mortgage_rate and mortgage_rate > 7:
        analysis["market_sentiment"] = "bearish — high rates suppressing demand"
    else:
        analysis["market_sentiment"] = "neutral — rates stable, steady demand"

    return {
        "success": True,
        "housing": housing.get("housing", {}),
        "rates": rates.get("rates", {}),
        "permits": {"total": len(permits), "subdivisions": analysis["new_subdivisions"]},
        "tho": {"customers": analysis["tho_customers"], "conversion": analysis["tho_conversion"], "recent_leads": analysis["tho_recent_leads"]},
        "analysis": analysis,
    }


def action_buyers() -> dict:
    """Buyer readiness indicators."""
    market = action_market()
    a = market.get("analysis", {})

    indicators = []

    # Mortgage affordability
    rate = a.get("mortgage_rate")
    if rate:
        if rate < 5.5:
            indicators.append({"indicator": "Mortgage Rate", "signal": "strong_buy", "detail": f"{rate:.1f}% — very affordable"})
        elif rate < 6.5:
            indicators.append({"indicator": "Mortgage Rate", "signal": "neutral", "detail": f"{rate:.1f}% — moderate"})
        else:
            indicators.append({"indicator": "Mortgage Rate", "signal": "headwind", "detail": f"{rate:.1f}% — challenging for buyers"})

    # Permit activity (more permits = more demand)
    permits = a.get("houston_permits", 0)
    if permits > 50:
        indicators.append({"indicator": "Houston Permits", "signal": "strong_demand", "detail": f"{permits} active permits"})
    elif permits > 20:
        indicators.append({"indicator": "Houston Permits", "signal": "moderate", "detail": f"{permits} permits"})

    # THO pipeline health
    conv = a.get("tho_conversion", 0)
    if conv > 60:
        indicators.append({"indicator": "THO Conversion", "signal": "healthy", "detail": f"{conv}% enrolled"})
    elif conv > 40:
        indicators.append({"indicator": "THO Conversion", "signal": "moderate", "detail": f"{conv}%"})

    return {"success": True, "indicators": indicators, "market_sentiment": a.get("market_sentiment", "unknown")}


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {"action": "market"}
    action = params.get("action", "market")

    if action == "market":
        result = action_market()
    elif action == "buyers":
        result = action_buyers()
    elif action == "report":
        market = action_market()
        buyers = action_buyers()
        result = {"market": market, "buyers": buyers}
    else:
        result = {"error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
