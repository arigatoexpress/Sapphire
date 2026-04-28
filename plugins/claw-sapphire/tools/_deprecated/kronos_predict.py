#!/usr/bin/env python3
"""Sapphire Kronos Predictor — foundation model for financial candlestick forecasting.

Uses the Kronos model (AAAI 2026) to predict future OHLCV candles from historical data.
Kronos is pre-trained on 45+ exchanges and tokenizes candlestick data into discrete tokens.

Actions:
    forecast  — Predict next N candles for a symbol
    compare   — Compare Kronos forecast vs our TA-based prediction

Usage:
    echo '{"action":"forecast","symbol":"BTC","horizon":24}' | python3 kronos_predict.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
KRONOS_DIR = Path.home() / "Code" / "Kronos"
OPENBB_BASE = "http://127.0.0.1:6900/api/v1"

SYMBOLS = {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD"}


def _fetch_ohlcv(symbol: str, days: int = 60) -> list[dict]:
    """Fetch OHLCV from OpenBB."""
    yf_symbol = SYMBOLS.get(symbol, f"{symbol}-USD")
    from datetime import timedelta

    start = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
    url = f"{OPENBB_BASE}/crypto/price/historical?symbol={yf_symbol}&provider=yfinance&start_date={start}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            data = json.loads(r.read())
        return data.get("results", [])
    except Exception:
        return []


def action_forecast(symbol: str = "BTC", horizon: int = 24) -> dict:
    """Predict next N candles using Kronos foundation model."""
    try:
        sys.path.insert(0, str(KRONOS_DIR))
        import pandas as pd
        from model import Kronos, KronosPredictor, KronosTokenizer

        # Load model (use mini for speed on CPU)
        tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-2k")
        model = Kronos.from_pretrained("NeoQuasar/Kronos-mini")

        device = "cpu"  # Use CPU on Mac, GPU on Windows
        predictor = KronosPredictor(model, tokenizer, device=device, max_context=512)

        # Fetch historical OHLCV
        raw = _fetch_ohlcv(symbol, days=30)
        if not raw:
            return {"error": f"No OHLCV data for {symbol}"}

        df = pd.DataFrame(raw)
        df["date"] = pd.to_datetime(df["date"])

        # Kronos expects: open, high, low, close, volume, amount
        ohlcv = df[["open", "high", "low", "close", "volume"]].tail(400).copy()
        ohlcv["amount"] = ohlcv["volume"] * ohlcv["close"]  # Approximate amount

        # Timestamps for Kronos
        dates = df["date"].tail(400 + min(horizon, 120))
        x_timestamp = dates.iloc[: len(ohlcv)]
        y_timestamp = dates.iloc[len(ohlcv) : len(ohlcv) + min(horizon, 120)]

        # If we don't have enough future timestamps, generate them
        if len(y_timestamp) < min(horizon, 120):
            from datetime import timedelta

            last_date = x_timestamp.iloc[-1]
            freq = (
                x_timestamp.iloc[-1] - x_timestamp.iloc[-2]
                if len(x_timestamp) > 1
                else timedelta(days=1)
            )
            y_dates = [last_date + freq * (i + 1) for i in range(min(horizon, 120))]
            y_timestamp = pd.Series(y_dates)

        # Run prediction
        pred_df = predictor.predict(
            ohlcv, x_timestamp=x_timestamp, y_timestamp=y_timestamp, pred_len=min(horizon, 120)
        )

        # Extract predictions
        predictions = []
        for _, row in pred_df.iterrows():
            predictions.append(
                {
                    "open": round(float(row["open"]), 2),
                    "high": round(float(row["high"]), 2),
                    "low": round(float(row["low"]), 2),
                    "close": round(float(row["close"]), 2),
                    "volume": round(float(row.get("volume", 0)), 0),
                }
            )

        current_price = float(ohlcv.iloc[-1]["close"])
        predicted_close = predictions[-1]["close"] if predictions else current_price
        direction = "bullish" if predicted_close > current_price else "bearish"
        change_pct = (predicted_close - current_price) / current_price * 100

        return {
            "success": True,
            "symbol": symbol,
            "model": "Kronos-mini (4.1M params)",
            "current_price": current_price,
            "predicted_close": predicted_close,
            "direction": direction,
            "change_pct": round(change_pct, 2),
            "horizon": len(predictions),
            "predictions": predictions[:5],  # First 5 candles
        }

    except ImportError as e:
        return {
            "error": f"Kronos not available: {e}. Run: pip install torch einops huggingface_hub safetensors"
        }
    except Exception as e:
        return {"error": str(e)[:200]}


def action_compare(symbol: str = "BTC") -> dict:
    """Compare Kronos forecast vs TA-based prediction."""
    # Get Kronos forecast
    kronos = action_forecast(symbol, horizon=24)

    # Get our TA prediction
    ta_result = {"direction": "unknown", "confidence": 0}
    try:
        sys.path.insert(0, str(SAPPHIRE_DIR / "plugins" / "claw-sapphire" / "lib"))
        from technical_analysis import analyze

        profile = analyze(symbol)
        if profile:
            ta_result = {
                "direction": profile.net_signal,
                "confidence": 0.5
                + abs(profile.signal_count_bullish - profile.signal_count_bearish) * 0.05,
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


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {"action": "forecast", "symbol": "BTC"}
    action = params.get("action", "forecast")

    if action == "forecast":
        result = action_forecast(params.get("symbol", "BTC"), params.get("horizon", 24))
    elif action == "compare":
        result = action_compare(params.get("symbol", "BTC"))
    else:
        result = {"error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
