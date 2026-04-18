#!/usr/bin/env python3
"""Sapphire Kronos Predictor — Foundation model candlestick forecasting.

Wraps NeoQuasar/Kronos-base (102M params) for OHLCV sequence prediction.
Fetches live data from OpenBB REST API or yfinance fallback.

Actions (stdin JSON):
    predict  — Forecast next N bars for a symbol
    batch    — Forecast multiple symbols at once
    status   — Check model load status + last run info

Usage:
    echo '{"action":"predict","symbol":"BTC-USD","lookback_bars":200,"predict_bars":24,"interval":"1h"}' | python3 predict_kronos.py
    echo '{"action":"batch","symbols":["BTC-USD","ETH-USD","SPY"],"predict_bars":12}' | python3 predict_kronos.py
    echo '{"action":"status"}' | python3 predict_kronos.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ── Paths ─────────────────────────────────────────────────────────────────────
KRONOS_ROOT = Path.home() / "Code" / "Kronos"
KRONOS_MODELS = KRONOS_ROOT / ".models"
SAPPHIRE_ROOT = Path.home() / "Code" / "Sapphire"
INTEL_DIR = SAPPHIRE_ROOT / "data" / "intelligence"
OPENBB_URL = "http://localhost:6900"

# Add Kronos to path for model imports
if str(KRONOS_ROOT) not in sys.path:
    sys.path.insert(0, str(KRONOS_ROOT))

# ── Model cache (module-level singleton) ──────────────────────────────────────
_predictor = None
_model_loaded_at: float | None = None


def _load_predictor(verbose: bool = False) -> Any:
    """Load Kronos model + tokenizer, cache in module-level singleton."""
    global _predictor, _model_loaded_at

    if _predictor is not None:
        return _predictor

    t0 = time.time()
    try:
        from model import Kronos, KronosTokenizer, KronosPredictor  # type: ignore

        if verbose:
            print("Loading KronosTokenizer...", file=sys.stderr)
        tokenizer = KronosTokenizer.from_pretrained(
            "NeoQuasar/Kronos-Tokenizer-base",
            cache_dir=str(KRONOS_MODELS),
        )

        if verbose:
            print("Loading Kronos-base model...", file=sys.stderr)
        model = Kronos.from_pretrained(
            "NeoQuasar/Kronos-base",
            cache_dir=str(KRONOS_MODELS),
        )

        _predictor = KronosPredictor(model, tokenizer, max_context=512)
        _model_loaded_at = time.time()

        if verbose:
            print(f"Model ready in {time.time()-t0:.1f}s", file=sys.stderr)

        return _predictor

    except ImportError as e:
        raise RuntimeError(f"Kronos model code not found at {KRONOS_ROOT}: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to load Kronos model: {e}")


# ── Data fetching ─────────────────────────────────────────────────────────────

def _fetch_openbb(symbol: str, interval: str, bars: int) -> "pd.DataFrame | None":
    """Try to fetch OHLCV from OpenBB REST API."""
    try:
        import requests
        import pandas as pd

        # Determine date range
        interval_minutes = {
            "1m": 1, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "4h": 240, "1d": 1440,
        }.get(interval, 60)

        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(minutes=interval_minutes * (bars + 20))

        start_str = start_dt.strftime("%Y-%m-%d")
        end_str = end_dt.strftime("%Y-%m-%d")

        # Try crypto endpoint first
        is_crypto = any(c in symbol.upper() for c in ["-USD", "USDT", "BTC", "ETH", "SOL"])
        if is_crypto:
            url = f"{OPENBB_URL}/api/v1/crypto/price/historical"
        else:
            url = f"{OPENBB_URL}/api/v1/equity/price/historical"

        params = {
            "symbol": symbol,
            "provider": "yfinance",
            "start_date": start_str,
            "end_date": end_str,
            "interval": interval,
        }

        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return None

        data = resp.json()
        results = data.get("results", [])
        if not results:
            return None

        df = pd.DataFrame(results)
        # Normalize column names
        col_map = {}
        for col in df.columns:
            cl = col.lower()
            if cl in ("open", "high", "low", "close", "volume", "date", "datetime", "timestamp"):
                col_map[col] = cl
        df = df.rename(columns=col_map)

        # Ensure timestamp column
        if "date" in df.columns and "datetime" not in df.columns:
            df["datetime"] = pd.to_datetime(df["date"])
        elif "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"])

        df = df.sort_values("datetime").reset_index(drop=True)

        # Keep only what we need
        needed = ["open", "high", "low", "close", "volume", "datetime"]
        df = df[[c for c in needed if c in df.columns]]

        return df.tail(bars)

    except Exception:
        return None


def _fetch_yfinance(symbol: str, interval: str, bars: int) -> "pd.DataFrame":
    """Fetch OHLCV from yfinance directly."""
    import yfinance as yf
    import pandas as pd

    # Map interval to yfinance period
    interval_to_period = {
        "1m": "7d", "5m": "60d", "15m": "60d", "30m": "60d",
        "1h": "60d", "4h": "60d", "1d": "2y",
    }
    period = interval_to_period.get(interval, "60d")

    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)

    if df.empty:
        raise ValueError(f"No data returned for {symbol} at {interval}")

    df = df.reset_index()
    # Normalize columns
    df.columns = [c.lower() for c in df.columns]

    # Timestamp column
    if "datetime" in df.columns:
        pass
    elif "date" in df.columns:
        df["datetime"] = pd.to_datetime(df["date"])

    df = df.sort_values("datetime").reset_index(drop=True)
    needed = ["open", "high", "low", "close", "volume", "datetime"]
    df = df[[c for c in needed if c in df.columns]]

    return df.tail(bars)


def _get_ohlcv(symbol: str, interval: str, bars: int) -> "pd.DataFrame":
    """Fetch OHLCV — OpenBB first, yfinance fallback."""
    df = _fetch_openbb(symbol, interval, bars)
    if df is not None and len(df) >= 20:
        return df
    return _fetch_yfinance(symbol, interval, bars)


# ── Prediction logic ──────────────────────────────────────────────────────────

def _make_timestamps(last_ts: "pd.Timestamp", interval: str, n: int) -> "pd.Series":
    """Generate future timestamps for prediction horizon."""
    import pandas as pd

    interval_map = {
        "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
        "1h": "1h", "4h": "4h", "1d": "1D",
    }
    freq = interval_map.get(interval, "1h")
    future = pd.date_range(start=last_ts, periods=n + 1, freq=freq)[1:]
    return pd.Series(future)


def _direction_from_pred(current_close: float, pred_df: "pd.DataFrame") -> tuple[str, float]:
    """Compute direction and confidence from prediction DataFrame."""
    if "close" not in pred_df.columns or len(pred_df) == 0:
        return "neutral", 0.5

    final_close = float(pred_df["close"].iloc[-1])
    pct_change = (final_close - current_close) / current_close

    if pct_change > 0.015:
        direction = "bullish"
        confidence = min(0.95, 0.5 + abs(pct_change) * 15)
    elif pct_change < -0.015:
        direction = "bearish"
        confidence = min(0.95, 0.5 + abs(pct_change) * 15)
    else:
        direction = "neutral"
        confidence = 0.5 - abs(pct_change) * 10

    return direction, round(max(0.1, confidence), 3)


def action_predict(
    symbol: str = "BTC-USD",
    lookback_bars: int = 200,
    predict_bars: int = 24,
    interval: str = "1h",
    temperature: float = 1.0,
    top_p: float = 0.9,
    sample_count: int = 1,
) -> dict:
    """Run Kronos prediction for a single symbol."""
    import pandas as pd

    t0 = time.time()

    # Cap lookback at model max context
    lookback_bars = min(lookback_bars, 500)

    # Fetch data
    try:
        df = _get_ohlcv(symbol, interval, lookback_bars)
    except Exception as e:
        return {"error": f"Data fetch failed for {symbol}: {e}"}

    if len(df) < 20:
        return {"error": f"Insufficient data: only {len(df)} bars for {symbol}"}

    current_close = float(df["close"].iloc[-1])
    current_price = current_close

    # Prepare inputs for Kronos
    feature_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    x_df = df[feature_cols].copy()
    x_timestamp = df["datetime"] if "datetime" in df.columns else pd.Series(range(len(df)))

    last_ts = x_timestamp.iloc[-1]
    y_timestamp = _make_timestamps(last_ts, interval, predict_bars)

    # Load model
    try:
        predictor = _load_predictor(verbose=True)
    except RuntimeError as e:
        return {"error": str(e)}

    # Run prediction
    try:
        pred_df = predictor.predict(
            df=x_df,
            x_timestamp=x_timestamp,
            y_timestamp=y_timestamp,
            pred_len=predict_bars,
            T=temperature,
            top_p=top_p,
            sample_count=sample_count,
            verbose=False,
        )
    except Exception as e:
        return {"error": f"Kronos prediction failed: {e}"}

    direction, confidence = _direction_from_pred(current_close, pred_df)

    # Build predictions list
    predictions = []
    for i, (ts, row) in enumerate(zip(y_timestamp, pred_df.itertuples())):
        entry: dict = {
            "bar": i + 1,
            "timestamp": str(ts),
        }
        for col in ["open", "high", "low", "close"]:
            if hasattr(row, col):
                entry[col] = round(float(getattr(row, col)), 6)
        # Volume can go negative from Kronos inverse-normalization — clamp
        if hasattr(row, "volume"):
            entry["volume"] = max(0.0, round(float(row.volume), 2))
        predictions.append(entry)

    # Last N historical bars for chart overlay
    history = []
    hist_slice = df.tail(50)
    for row in hist_slice.itertuples():
        entry = {"timestamp": str(row.datetime) if hasattr(row, "datetime") else ""}
        for col in ["open", "high", "low", "close", "volume"]:
            if hasattr(row, col):
                entry[col] = round(float(getattr(row, col)), 6)
        history.append(entry)

    elapsed = round(time.time() - t0, 2)

    return {
        "symbol": symbol,
        "interval": interval,
        "lookback_used": len(df),
        "predict_bars": predict_bars,
        "current_price": round(current_price, 6),
        "direction": direction,
        "confidence": confidence,
        "predictions": predictions,
        "history": history,
        "model": "Kronos-base",
        "elapsed_s": elapsed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def action_batch(
    symbols: list[str] | None = None,
    lookback_bars: int = 200,
    predict_bars: int = 24,
    interval: str = "1h",
) -> dict:
    """Run Kronos predictions for multiple symbols."""
    if symbols is None:
        symbols = ["BTC-USD", "ETH-USD", "SOL-USD"]

    results = {}
    for sym in symbols:
        results[sym] = action_predict(
            symbol=sym,
            lookback_bars=lookback_bars,
            predict_bars=predict_bars,
            interval=interval,
        )

    # Aggregate summary
    directions = {s: r.get("direction", "unknown") for s, r in results.items() if "error" not in r}
    bull = sum(1 for d in directions.values() if d == "bullish")
    bear = sum(1 for d in directions.values() if d == "bearish")
    market_bias = "bullish" if bull > bear else ("bearish" if bear > bull else "neutral")

    return {
        "symbols": results,
        "market_bias": market_bias,
        "bullish_count": bull,
        "bearish_count": bear,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def action_status() -> dict:
    """Check model status and last prediction info."""
    model_dir = KRONOS_MODELS
    models_present = []

    if model_dir.exists():
        for d in model_dir.iterdir():
            if d.is_dir() and "Kronos" in d.name:
                models_present.append(d.name)

    return {
        "model_loaded": _predictor is not None,
        "model_loaded_at": (
            datetime.fromtimestamp(_model_loaded_at, tz=timezone.utc).isoformat()
            if _model_loaded_at else None
        ),
        "models_cached": models_present,
        "kronos_root": str(KRONOS_ROOT),
        "kronos_root_exists": KRONOS_ROOT.exists(),
        "models_dir": str(model_dir),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _save_intelligence_snapshot(result: dict, symbol: str) -> None:
    """Write prediction result to data/intelligence/YYYY-MM-DD/predictions.json."""
    try:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        out_dir = INTEL_DIR / today
        out_dir.mkdir(parents=True, exist_ok=True)

        pred_file = out_dir / "predictions.json"
        if pred_file.exists():
            existing = json.loads(pred_file.read_text())
        else:
            existing = {"generated_at": datetime.now(timezone.utc).isoformat(), "predictions": {}}

        existing["predictions"][symbol] = result
        existing["updated_at"] = datetime.now(timezone.utc).isoformat()
        pred_file.write_text(json.dumps(existing, indent=2))
    except Exception:
        pass


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    raw = sys.stdin.read().strip()
    if not raw:
        inp: dict = {}
    else:
        try:
            inp = json.loads(raw)
        except json.JSONDecodeError as e:
            print(json.dumps({"error": f"Invalid JSON: {e}"}))
            return

    action = inp.get("action", "predict")

    if action == "status":
        print(json.dumps(action_status(), indent=2))

    elif action == "predict":
        result = action_predict(
            symbol=inp.get("symbol", "BTC-USD"),
            lookback_bars=int(inp.get("lookback_bars", 200)),
            predict_bars=int(inp.get("predict_bars", 24)),
            interval=inp.get("interval", "1h"),
            temperature=float(inp.get("temperature", 1.0)),
            top_p=float(inp.get("top_p", 0.9)),
            sample_count=int(inp.get("sample_count", 1)),
        )
        symbol = inp.get("symbol", "BTC-USD")
        if "error" not in result:
            _save_intelligence_snapshot(result, symbol)
        print(json.dumps(result, indent=2))

    elif action == "batch":
        result = action_batch(
            symbols=inp.get("symbols"),
            lookback_bars=int(inp.get("lookback_bars", 200)),
            predict_bars=int(inp.get("predict_bars", 24)),
            interval=inp.get("interval", "1h"),
        )
        # Save each symbol
        for sym, r in result.get("symbols", {}).items():
            if "error" not in r:
                _save_intelligence_snapshot(r, sym)
        print(json.dumps(result, indent=2))

    else:
        print(json.dumps({"error": f"Unknown action: {action}. Use: predict, batch, status"}))


if __name__ == "__main__":
    main()
