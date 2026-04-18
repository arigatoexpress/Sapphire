#!/usr/bin/env python3
"""Sapphire Macro Data — FRED API integration (free Bloomberg replacement).

Provides real-time access to Federal Reserve Economic Data:
GDP, CPI, unemployment, interest rates, treasury yields, S&P 500, and more.

Actions:
    dashboard  — Key macro indicators at a glance
    series     — Fetch any FRED series by ID
    rates      — Interest rates overview (Fed funds, treasuries)
    housing    — Housing market data (starts, permits, prices)

Usage:
    echo '{"action":"dashboard"}' | python3 macro_data.py
    echo '{"action":"series","id":"GDP"}' | python3 macro_data.py
    echo '{"action":"housing"}' | python3 macro_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SECRETS_DIR = Path.home() / ".config" / "sapphire-secrets"
FRED_KEY_PATH = SECRETS_DIR / "fred_api_key"


def _get_fred():
    from fredapi import Fred
    key = FRED_KEY_PATH.read_text().strip() if FRED_KEY_PATH.exists() else None
    if not key:
        raise RuntimeError("No FRED API key. Save to ~/.config/sapphire-secrets/fred_api_key")
    return Fred(api_key=key)


def _latest(series_id: str, fred=None) -> dict:
    """Get latest value + metadata for a FRED series."""
    if fred is None:
        fred = _get_fred()
    try:
        s = fred.get_series(series_id)
        s = s.dropna()
        if s.empty:
            return {"id": series_id, "value": None, "error": "No data"}
        return {
            "id": series_id,
            "value": round(float(s.iloc[-1]), 2),
            "date": s.index[-1].strftime("%Y-%m-%d"),
        }
    except Exception as e:
        return {"id": series_id, "error": str(e)[:100]}


def action_dashboard() -> dict:
    """Key macro indicators at a glance."""
    fred = _get_fred()

    indicators = {
        "GDP (Billions)": "GDP",
        "Fed Funds Rate %": "FEDFUNDS",
        "CPI Index": "CPIAUCSL",
        "Core CPI YoY %": "CPILFESL",
        "Unemployment %": "UNRATE",
        "10Y Treasury %": "DGS10",
        "2Y Treasury %": "DGS2",
        "30Y Mortgage %": "MORTGAGE30US",
        "S&P 500": "SP500",
        "VIX": "VIXCLS",
        "M2 Money Supply (T)": "M2SL",
        "Initial Jobless Claims": "ICSA",
    }

    results = {}
    for label, series_id in indicators.items():
        data = _latest(series_id, fred)
        results[label] = {"value": data.get("value"), "date": data.get("date"), "series": series_id}

    return {"success": True, "indicators": results, "source": "FRED (Federal Reserve)"}


def action_rates() -> dict:
    """Interest rates overview."""
    fred = _get_fred()
    rates = {}
    for label, sid in [
        ("Fed Funds", "FEDFUNDS"), ("3M Treasury", "DTB3"), ("2Y Treasury", "DGS2"),
        ("5Y Treasury", "DGS5"), ("10Y Treasury", "DGS10"), ("30Y Treasury", "DGS30"),
        ("30Y Mortgage", "MORTGAGE30US"), ("Prime Rate", "DPRIME"),
    ]:
        data = _latest(sid, fred)
        rates[label] = f"{data.get('value')}%" if data.get("value") is not None else "N/A"
    return {"success": True, "rates": rates}


def action_housing() -> dict:
    """Housing market data (relevant to THO)."""
    fred = _get_fred()
    metrics = {}
    for label, sid in [
        ("Housing Starts (K)", "HOUST"), ("Building Permits (K)", "PERMIT"),
        ("New Home Sales (K)", "HSN1F"), ("Existing Home Sales (M)", "EXHOSLUSM495S"),
        ("Median Home Price", "MSPUS"), ("30Y Mortgage %", "MORTGAGE30US"),
        ("Case-Shiller Index", "CSUSHPINSA"),
    ]:
        data = _latest(sid, fred)
        metrics[label] = {"value": data.get("value"), "date": data.get("date")}
    return {"success": True, "housing": metrics, "note": "Key housing indicators for Texas Home Outlet market analysis"}


def action_series(series_id: str, periods: int = 12) -> dict:
    """Fetch any FRED series."""
    fred = _get_fred()
    try:
        s = fred.get_series(series_id).dropna().tail(periods)
        info = fred.get_series_info(series_id)
        return {
            "success": True,
            "series": series_id,
            "title": info.get("title", series_id),
            "frequency": info.get("frequency", "?"),
            "units": info.get("units", "?"),
            "data": [{"date": idx.strftime("%Y-%m-%d"), "value": round(float(v), 4)} for idx, v in s.items()],
        }
    except Exception as e:
        return {"error": str(e)[:200]}


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {"action": "dashboard"}
    action = params.get("action", "dashboard")

    if action == "dashboard":
        result = action_dashboard()
    elif action == "rates":
        result = action_rates()
    elif action == "housing":
        result = action_housing()
    elif action == "series":
        result = action_series(params.get("id", "GDP"), params.get("periods", 12))
    else:
        result = {"error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
