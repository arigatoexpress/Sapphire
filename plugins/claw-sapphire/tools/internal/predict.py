#!/usr/bin/env python3
"""Sapphire Prediction Engine — TA-grounded price predictions.

Uses real technical analysis (RSI, MACD, Bollinger, MA, ATR) from OpenBB
to generate predictions. No hallucinated numbers — every value is computed.

Actions:
    predict  — Generate new predictions for BTC, ETH, SOL
    score    — Score pending predictions against live prices
    history  — Show prediction history and accuracy

Usage:
    echo '{"action":"predict"}' | python3 predict.py
    echo '{"action":"score"}' | python3 predict.py
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import tempfile
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
PREDICTIONS_FILE = SAPPHIRE_DIR / "data" / "trading_predictions.jsonl"


def _get_coingecko_prices() -> dict:
    """Get current prices from CoinGecko."""
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd&include_24hr_change=true"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        return {
            "BTC": data["bitcoin"]["usd"],
            "ETH": data["ethereum"]["usd"],
            "SOL": data["solana"]["usd"],
        }
    except Exception:
        return {}


def action_predict() -> dict:
    """Generate TA-grounded predictions."""
    from technical_analysis import analyze_all

    profiles = analyze_all()
    predictions = []
    now = datetime.now(UTC).isoformat()

    for sym, profile in profiles.items():
        if profile is None:
            continue

        # ─── Multi-factor confidence scoring ───
        # Each factor contributes independently. Direction comes from consensus.
        bull_score = 0.0
        bear_score = 0.0
        factors = []

        # 1. MA trend (strongest directional signal)
        if profile.ma_trend == "bullish":
            bull_score += 2.0
            factors.append("MA↑")
        elif profile.ma_trend == "bearish":
            bear_score += 2.0
            factors.append("MA↓")

        # 2. RSI (contrarian near extremes, confirming in middle)
        if profile.rsi_14 < 30:
            bull_score += 1.5  # Oversold bounce
            factors.append(f"RSI{profile.rsi_14:.0f}↑")
        elif profile.rsi_14 < 45:
            bear_score += 0.5  # Weak
            factors.append(f"RSI{profile.rsi_14:.0f}")
        elif profile.rsi_14 < 55:
            pass  # Neutral
        elif profile.rsi_14 < 70:
            bull_score += 0.5  # Mildly bullish momentum
            factors.append(f"RSI{profile.rsi_14:.0f}")
        else:
            bear_score += 1.0  # Overbought, likely pullback
            factors.append(f"RSI{profile.rsi_14:.0f}↓")

        # 3. MACD cross
        if profile.macd_cross == "bullish_cross":
            bull_score += 1.5
            factors.append("MACD↑")
        elif profile.macd_cross == "bearish_cross":
            bear_score += 1.5
            factors.append("MACD↓")

        # 4. Bollinger position
        if profile.bb_position == "below_lower":
            bull_score += 1.0
            factors.append("BB<low")
        elif profile.bb_position == "above_upper":
            bear_score += 1.0
            factors.append("BB>high")

        # 5. Volume confirmation (amplifies existing signal)
        if profile.volume_ratio > 1.5:
            if bull_score > bear_score:
                bull_score += 0.5
            elif bear_score > bull_score:
                bear_score += 0.5
            factors.append("Vol↑")
        elif profile.volume_ratio < 0.5:
            # Low volume = weak conviction, dampen both
            bull_score *= 0.8
            bear_score *= 0.8
            factors.append("Vol↓")

        # 6. 7-day momentum
        if profile.change_7d_pct > 5:
            bull_score += 0.5
        elif profile.change_7d_pct < -5:
            bear_score += 0.5

        # ─── Direction decision ───
        net = bull_score - bear_score
        if net > 1.5:
            direction = "bullish"
        elif net < -1.5:
            direction = "bearish"
        else:
            direction = "neutral"

        # ─── Confidence: based on how strong the consensus is ───
        total_score = bull_score + bear_score
        dominance = max(bull_score, bear_score) / total_score if total_score > 0 else 0.5
        conf = round(min(0.90, 0.40 + dominance * 0.4 + abs(net) * 0.05), 2)

        # ─── Target: entry ± 0.5 ATR (conservative) ───
        atr_move = profile.atr_14
        if direction == "bullish":
            target = profile.price + atr_move * 0.5
        elif direction == "bearish":
            target = profile.price - atr_move * 0.5
        else:
            target = profile.price

        pred = {
            "timestamp": now,
            "symbol": sym,
            "direction": direction,
            "confidence": round(conf, 2),
            "target_price": round(target, 2),
            "entry_price": profile.price,
            "timeframe": "24h",
            # TA indicators used
            "rsi": profile.rsi_14,
            "macd_cross": profile.macd_cross,
            "ma_trend": profile.ma_trend,
            "bb_position": profile.bb_position,
            "volume_signal": profile.volume_signal,
            "volatility": profile.volatility_regime,
            "signals_bullish": profile.signal_count_bullish,
            "signals_bearish": profile.signal_count_bearish,
            "net_signal": profile.net_signal,
            "reasoning": (
                f"{direction} (net={net:+.1f}): {' '.join(factors)}. "
                f"Bull={bull_score:.1f} Bear={bear_score:.1f}. "
                f"RSI {profile.rsi_14:.0f}, MA {profile.ma_trend}, BB {profile.bb_position}."
            ),
            "actual_price": None,
            "correct": None,
        }
        predictions.append(pred)

    # Append to predictions file
    with open(PREDICTIONS_FILE, "a") as f:
        for p in predictions:
            f.write(json.dumps(p) + "\n")

    return {
        "success": True,
        "predictions": len(predictions),
        "summary": [
            f"{p['symbol']} {p['direction']} → ${p['target_price']:,.0f} (conf {p['confidence']:.0%}, {p['net_signal']})"
            for p in predictions
        ],
    }


_TIMEFRAME_SECONDS = {
    "1h": 3600, "2h": 7200, "4h": 14400, "6h": 21600,
    "12h": 43200, "24h": 86400, "1d": 86400,
    "3d": 259200, "7d": 604800, "1w": 604800,
}


def _timeframe_elapsed(pred: dict, now: datetime) -> bool:
    """True once `pred["timestamp"] + pred["timeframe"]` is in the past."""
    tf = str(pred.get("timeframe", "24h"))
    window = _TIMEFRAME_SECONDS.get(tf, 86400)
    raw_ts = pred.get("timestamp")
    if not raw_ts:
        return False
    try:
        created = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
    except ValueError:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return now - created >= timedelta(seconds=window)


def _atomic_write_lines(path: Path, lines: list[str]) -> None:
    """Write lines to path atomically via a same-directory temp file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines))
            if lines:
                f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def action_score() -> dict:
    """Score predictions whose timeframe has elapsed against live prices.

    Previously this scored every un-scored prediction the moment it saw one —
    which turned a "24h forecast" into a "does the current price beat entry
    right now" coin-flip and invalidated every published accuracy number.
    """
    prices = _get_coingecko_prices()
    if not prices:
        return {"error": "Could not fetch live prices"}

    if not PREDICTIONS_FILE.exists():
        return {"success": True, "newly_scored": 0, "total_scored": 0, "correct": 0, "accuracy": "N/A"}

    now = datetime.now(UTC)
    updated: list[str] = []
    scored_count = 0
    correct_count = 0
    pending_within_window = 0

    for line in PREDICTIONS_FILE.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            p = json.loads(line)
        except json.JSONDecodeError:
            continue

        if p.get("correct") is None and p.get("symbol") in prices:
            if not _timeframe_elapsed(p, now):
                pending_within_window += 1
            else:
                current = prices[p["symbol"]]
                entry = p.get("entry_price") or p["target_price"]
                if entry and p["direction"] == "bullish":
                    p["correct"] = bool(current > entry)
                elif entry and p["direction"] == "bearish":
                    p["correct"] = bool(current < entry)
                elif entry:
                    p["correct"] = abs((current - entry) / entry * 100) < 3
                p["actual_price"] = current
                p["scored_at"] = now.isoformat()
                scored_count += 1

        if p.get("correct") is True:
            correct_count += 1

        updated.append(json.dumps(p))

    _atomic_write_lines(PREDICTIONS_FILE, updated)

    total_scored = sum(
        1 for line in updated if json.loads(line).get("correct") is not None
    )

    return {
        "success": True,
        "newly_scored": scored_count,
        "total_scored": total_scored,
        "correct": correct_count,
        "pending_within_window": pending_within_window,
        "accuracy": f"{correct_count / total_scored * 100:.0f}%" if total_scored else "N/A",
    }


def action_history() -> dict:
    """Show prediction history and accuracy."""
    if not PREDICTIONS_FILE.exists():
        return {"predictions": [], "accuracy": "N/A"}

    preds = [json.loads(l) for l in PREDICTIONS_FILE.read_text().strip().split("\n")]
    scored = [p for p in preds if p.get("correct") is not None]
    correct = sum(1 for p in scored if p["correct"])

    # Group by symbol
    by_symbol = {}
    for p in scored:
        sym = p["symbol"]
        by_symbol.setdefault(sym, {"correct": 0, "total": 0})
        by_symbol[sym]["total"] += 1
        if p["correct"]:
            by_symbol[sym]["correct"] += 1

    return {
        "total_predictions": len(preds),
        "scored": len(scored),
        "correct": correct,
        "accuracy": f"{correct / len(scored) * 100:.0f}%" if scored else "N/A",
        "by_symbol": {
            sym: f"{d['correct']}/{d['total']} = {d['correct']/d['total']*100:.0f}%"
            for sym, d in by_symbol.items()
        },
        "pending": len(preds) - len(scored),
    }


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {"action": "predict"}
    action = params.get("action", "predict")

    if action == "predict":
        result = action_predict()
    elif action == "score":
        result = action_score()
    elif action == "history":
        result = action_history()
    else:
        result = {"error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
