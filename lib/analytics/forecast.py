"""Forecast aggregator — Kronos + TA scanner consensus.

Reads two prediction streams and reconciles them into a single dashboard view:

  data/intelligence/YYYY-MM-DD/predictions.json
    Kronos 24-bar forward projections (OHLCV per bar) with overall direction
    and confidence. Symbols: BTC-USD, ETH-USD, SOL-USD, SPY, TSLA.

  data/trading_predictions.jsonl
    TA-scanner predictions (RSI/MACD/BB/MA) with direction + target_price.

Output per symbol:
  kronos:  {direction, confidence, current_price, target_high, target_low, horizon_hours}
  ta:      {direction, confidence, target_price, timeframe, signals_bullish/bearish}
  consensus: AGREE_BULL | AGREE_BEAR | CONTRADICT | KRONOS_ONLY | TA_ONLY | NEITHER
  edge:    combined expected-value score for ranking on the dashboard.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
INTELLIGENCE_DIR = ROOT / "data" / "intelligence"
TRADING_PREDICTIONS = ROOT / "data" / "trading_predictions.jsonl"

TA_PREDICTION_STALE_HOURS = 36  # older TA predictions are considered stale


def _latest_kronos_file() -> Path | None:
    if not INTELLIGENCE_DIR.exists():
        return None
    candidates = sorted(
        p for p in INTELLIGENCE_DIR.iterdir() if p.is_dir() and (p / "predictions.json").exists()
    )
    return (candidates[-1] / "predictions.json") if candidates else None


def _load_kronos() -> dict[str, Any]:
    f = _latest_kronos_file()
    if f is None:
        return {"generated_at": None, "predictions": {}, "source_file": None}
    try:
        raw = f.read_text()
    except OSError:
        return {"generated_at": None, "predictions": {}, "source_file": None}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"generated_at": None, "predictions": {}, "source_file": None}
    try:
        data["source_file"] = str(f.relative_to(ROOT))
    except ValueError:
        data["source_file"] = str(f)
    return data


def _kronos_per_symbol(kronos: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Condense Kronos OHLCV projections into compact per-symbol dicts."""
    out: dict[str, dict[str, Any]] = {}
    preds = kronos.get("predictions") or {}
    for symbol, p in preds.items():
        bars = p.get("predictions") or []
        if not bars:
            continue
        highs = [b.get("high") or b.get("close") or 0 for b in bars]
        lows = [b.get("low") or b.get("close") or 0 for b in bars]
        closes = [b.get("close") or 0 for b in bars]
        final_close = closes[-1] if closes else None
        current = p.get("current_price")
        target_high = max(highs) if highs else None
        target_low = min(lows) if lows else None
        out[symbol] = {
            "direction": p.get("direction"),
            "confidence": p.get("confidence"),
            "current_price": current,
            "final_close": final_close,
            "target_high": target_high,
            "target_low": target_low,
            "horizon_hours": p.get("predict_bars"),
            "interval": p.get("interval"),
            "projected_change_pct": (
                round((final_close - current) / current * 100, 3)
                if (final_close and current) else None
            ),
        }
    return out


def _load_ta_latest_per_symbol() -> dict[str, dict[str, Any]]:
    """Return the most recent non-stale TA prediction per symbol."""
    if not TRADING_PREDICTIONS.exists():
        return {}
    try:
        raw = TRADING_PREDICTIONS.read_text()
    except OSError:
        return {}

    cutoff = datetime.now(UTC) - timedelta(hours=TA_PREDICTION_STALE_HOURS)
    by_symbol: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts_str = r.get("timestamp")
        if not ts_str:
            continue
        try:
            ts = datetime.fromisoformat(ts_str)
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        if ts < cutoff:
            continue
        symbol = r.get("symbol")
        if not symbol:
            continue
        existing = by_symbol.get(symbol)
        if existing is None or ts > existing[0]:
            by_symbol[symbol] = (ts, r)

    return {
        sym: {
            "direction": r.get("direction"),
            "confidence": r.get("confidence"),
            "target_price": r.get("target_price"),
            "entry_price": r.get("entry_price"),
            "timeframe": r.get("timeframe"),
            "signals_bullish": r.get("signals_bullish"),
            "signals_bearish": r.get("signals_bearish"),
            "net_signal": r.get("net_signal"),
            "timestamp": r.get("timestamp"),
            "rsi": r.get("rsi"),
            "ma_trend": r.get("ma_trend"),
        }
        for sym, (_, r) in by_symbol.items()
    }


_BULL_TERMS = {"bullish", "long", "up", "buy"}
_BEAR_TERMS = {"bearish", "short", "down", "sell"}


def _direction_class(direction: str | None) -> str:
    if not direction:
        return "NEUTRAL"
    d = direction.lower()
    if d in _BULL_TERMS:
        return "BULL"
    if d in _BEAR_TERMS:
        return "BEAR"
    return "NEUTRAL"


def _consensus(kronos: dict[str, Any] | None, ta: dict[str, Any] | None) -> str:
    if kronos and ta:
        k = _direction_class(kronos.get("direction"))
        t = _direction_class(ta.get("direction"))
        if k == "BULL" and t == "BULL":
            return "AGREE_BULL"
        if k == "BEAR" and t == "BEAR":
            return "AGREE_BEAR"
        if k == "NEUTRAL" or t == "NEUTRAL":
            return "PARTIAL"
        return "CONTRADICT"
    if kronos:
        return "KRONOS_ONLY"
    if ta:
        return "TA_ONLY"
    return "NEITHER"


def _edge_score(kronos: dict[str, Any] | None, ta: dict[str, Any] | None, consensus: str) -> float:
    """Simple blended expected-value proxy for dashboard ranking.

    Range roughly [-1, +1]. Positive = net bullish, negative = net bearish.
    """
    score = 0.0
    if kronos:
        k_dir = _direction_class(kronos.get("direction"))
        k_conf = float(kronos.get("confidence") or 0.0)
        if k_dir == "BULL":
            score += k_conf
        elif k_dir == "BEAR":
            score -= k_conf
    if ta:
        t_dir = _direction_class(ta.get("direction"))
        t_conf = float(ta.get("confidence") or 0.0)
        if t_dir == "BULL":
            score += t_conf
        elif t_dir == "BEAR":
            score -= t_conf
    # Scale: max would be 2.0 (both BULL at conf 1), clamp to [-1, 1]
    scaled = score / 2.0
    # Reward agreement, penalize contradiction
    if consensus in {"AGREE_BULL", "AGREE_BEAR"}:
        scaled *= 1.1
    elif consensus == "CONTRADICT":
        scaled *= 0.4
    return round(max(-1.0, min(1.0, scaled)), 4)


_SYMBOL_ALIASES = {
    "BTC-USD": "BTC",
    "ETH-USD": "ETH",
    "SOL-USD": "SOL",
    "BTC": "BTC",
    "ETH": "ETH",
    "SOL": "SOL",
}


def forecast() -> dict[str, Any]:
    """Combined Kronos + TA forecast per symbol, with consensus and edge score."""
    kronos_data = _load_kronos()
    kronos_per_symbol = _kronos_per_symbol(kronos_data)
    ta_per_symbol = _load_ta_latest_per_symbol()

    # Canonicalize keys — BTC-USD (Kronos) and BTC (TA) refer to the same asset.
    merged: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"kronos": None, "ta": None, "kronos_symbol": None, "ta_symbol": None}
    )
    for k_sym, k in kronos_per_symbol.items():
        canonical = _SYMBOL_ALIASES.get(k_sym, k_sym)
        merged[canonical]["kronos"] = k
        merged[canonical]["kronos_symbol"] = k_sym
    for t_sym, t in ta_per_symbol.items():
        canonical = _SYMBOL_ALIASES.get(t_sym, t_sym)
        merged[canonical]["ta"] = t
        merged[canonical]["ta_symbol"] = t_sym

    rows: list[dict[str, Any]] = []
    for canonical, parts in merged.items():
        consensus = _consensus(parts["kronos"], parts["ta"])
        edge = _edge_score(parts["kronos"], parts["ta"], consensus)
        rows.append({
            "symbol": canonical,
            "kronos_symbol": parts["kronos_symbol"],
            "ta_symbol": parts["ta_symbol"],
            "kronos": parts["kronos"],
            "ta": parts["ta"],
            "consensus": consensus,
            "edge_score": edge,
        })

    rows.sort(key=lambda r: abs(r["edge_score"]), reverse=True)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "kronos_stamp": kronos_data.get("generated_at"),
        "kronos_source": kronos_data.get("source_file"),
        "rows": rows,
        "symbols": [r["symbol"] for r in rows],
    }


if __name__ == "__main__":
    import sys
    json.dump(forecast(), sys.stdout, indent=2, default=str)
    print()
