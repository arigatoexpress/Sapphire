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

import json
import sys
import urllib.request
from dataclasses import asdict
from datetime import datetime, timezone
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
    now = datetime.now(timezone.utc).isoformat()

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
        if total_score > 0:
            dominance = max(bull_score, bear_score) / total_score
        else:
            dominance = 0.5
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


def action_score() -> dict:
    """Score pending predictions against live prices."""
    prices = _get_coingecko_prices()
    if not prices:
        return {"error": "Could not fetch live prices"}

    lines = PREDICTIONS_FILE.read_text().strip().split("\n")
    updated = []
    scored_count = 0
    correct_count = 0

    for line in lines:
        p = json.loads(line)

        # Only score unscored predictions
        if p.get("correct") is None and p["symbol"] in prices:
            current = prices[p["symbol"]]
            entry = p.get("entry_price") or p["target_price"]

            if p["direction"] == "bullish":
                p["correct"] = current > entry
            elif p["direction"] == "bearish":
                p["correct"] = current < entry
            else:
                p["correct"] = abs((current - entry) / entry * 100) < 3

            p["actual_price"] = current
            scored_count += 1

        if p.get("correct") is not None:
            if p["correct"]:
                correct_count += 1

        updated.append(json.dumps(p))

    # Write back
    PREDICTIONS_FILE.write_text("\n".join(updated) + "\n")

    total_scored = sum(1 for l in updated if json.loads(l).get("correct") is not None)

    return {
        "success": True,
        "newly_scored": scored_count,
        "total_scored": total_scored,
        "correct": correct_count,
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
