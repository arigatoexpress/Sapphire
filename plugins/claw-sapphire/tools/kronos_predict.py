#!/usr/bin/env python3
"""Legacy compatibility wrapper for the canonical Kronos predictor.

`predict_kronos.py` is the canonical tool. This file remains on disk so older
scheduled tasks, skills, and direct subprocess calls keep working while the repo
converges on one Kronos interface.

Supported legacy actions:
    forecast  — Adapted to `predict_kronos.action_predict`
    compare   — Legacy compare view using canonical Kronos + TA profile
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
TOOLS_DIR = SAPPHIRE_DIR / "plugins" / "claw-sapphire" / "tools"
LIB_DIR = SAPPHIRE_DIR / "plugins" / "claw-sapphire" / "lib"

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))
if str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

import predict_kronos


def _normalize_symbol(symbol: str) -> str:
    """Map legacy short symbols to canonical market symbols."""
    cleaned = (symbol or "BTC").strip().upper()
    aliases = {
        "BTC": "BTC-USD",
        "ETH": "ETH-USD",
        "SOL": "SOL-USD",
    }
    return aliases.get(cleaned, cleaned if "-" in cleaned else f"{cleaned}-USD")


def action_forecast(symbol: str = "BTC", horizon: int = 24) -> dict:
    """Compatibility layer for the old `forecast` action."""
    canonical_symbol = _normalize_symbol(symbol)
    result = predict_kronos.action_predict(
        symbol=canonical_symbol,
        lookback_bars=200,
        predict_bars=horizon,
        interval="1h",
    )

    if "error" in result:
        return {"error": result["error"]}

    predictions = result.get("predictions", [])
    predicted_close = float(predictions[-1]["close"]) if predictions else float(result["current_price"])
    current_price = float(result["current_price"])
    change_pct = ((predicted_close - current_price) / current_price * 100) if current_price else 0.0

    return {
        "success": True,
        "symbol": symbol,
        "canonical_symbol": canonical_symbol,
        "model": result.get("model", "Kronos-base"),
        "current_price": round(current_price, 6),
        "predicted_close": round(predicted_close, 6),
        "direction": result.get("direction", "neutral"),
        "change_pct": round(change_pct, 2),
        "horizon": len(predictions),
        "predictions": predictions[:5],
    }


def action_compare(symbol: str = "BTC") -> dict:
    """Compare canonical Kronos output with the TA profile used elsewhere."""
    kronos = action_forecast(symbol, horizon=24)

    ta_result = {"direction": "unknown", "confidence": 0.0}
    try:
        from technical_analysis import analyze

        profile = analyze(symbol)
        if profile:
            ta_result = {
                "direction": profile.net_signal,
                "confidence": 0.5 + abs(profile.signal_count_bullish - profile.signal_count_bearish) * 0.05,
                "rsi": profile.rsi_14,
                "ma_trend": profile.ma_trend,
            }
    except Exception:
        pass

    return {
        "symbol": symbol,
        "kronos": {
            "direction": kronos.get("direction"),
            "change_pct": kronos.get("change_pct"),
            "model": kronos.get("model"),
        },
        "ta": ta_result,
        "agreement": kronos.get("direction") == ta_result.get("direction"),
    }


def main() -> None:
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {"action": "forecast", "symbol": "BTC"}
    action = params.get("action", "forecast")

    if action == "forecast":
        result = action_forecast(params.get("symbol", "BTC"), int(params.get("horizon", 24)))
    elif action == "compare":
        result = action_compare(params.get("symbol", "BTC"))
    else:
        result = {
            "error": (
                f"Unknown action: {action}. This legacy wrapper supports "
                "forecast and compare. Use predict_kronos.py for canonical actions."
            )
        }

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
