#!/usr/bin/env python3
"""Sapphire Trading Brain — unified decision engine combining all signal sources.

Aggregates signals from multiple independent systems:
1. Technical Analysis (RSI, MACD, Bollinger, MA, ATR, volume)
2. Multi-factor ensemble signal generator (6-factor agreement gate)
3. Kronos foundation model (candlestick prediction)
4. FRED macro environment (rates, VIX, GDP)
5. Paper trading track record (win rate, Sortino)

Produces a single GO/WAIT/EXIT decision with confidence and reasoning.

Usage:
    echo '{"action":"decide","symbol":"BTC"}' | python3 trading_brain.py
    echo '{"action":"dashboard"}' | python3 trading_brain.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
TOOLS_DIR = SAPPHIRE_DIR / "plugins" / "claw-sapphire" / "tools"
LIB_DIR = SAPPHIRE_DIR / "plugins" / "claw-sapphire" / "lib"
sys.path.insert(0, str(LIB_DIR))


def _run_tool(tool_name: str, params: dict) -> dict:
    """Run a Sapphire plugin tool and return parsed JSON."""
    tool_path = TOOLS_DIR / f"{tool_name}.py"
    env = {**__import__("os").environ, "PYTHONPATH": str(LIB_DIR)}
    try:
        r = subprocess.run(
            [sys.executable, str(tool_path)],
            input=json.dumps(params), capture_output=True, text=True,
            timeout=30, env=env,
        )
        return json.loads(r.stdout) if r.stdout.strip() else {"error": r.stderr[:200]}
    except Exception as e:
        return {"error": str(e)[:100]}


def _canonical_market_symbol(symbol: str) -> str:
    """Map short crypto tickers to the canonical symbols used by predict_kronos."""
    cleaned = (symbol or "").strip().upper()
    aliases = {
        "BTC": "BTC-USD",
        "ETH": "ETH-USD",
        "SOL": "SOL-USD",
    }
    return aliases.get(cleaned, cleaned if "-" in cleaned else f"{cleaned}-USD")


def _get_macro_sentiment() -> dict:
    """Get macro environment sentiment from FRED data."""
    macro = _run_tool("macro_data", {"action": "dashboard"})
    if "error" in macro:
        return {"sentiment": "neutral", "score": 0, "reason": "macro unavailable"}

    indicators = macro.get("indicators", {})
    score = 0
    reasons = []

    # VIX — fear gauge
    vix = indicators.get("VIX", {}).get("value")
    if vix:
        if vix < 15:
            score += 2
            reasons.append(f"VIX low ({vix:.0f})")
        elif vix > 25:
            score -= 2
            reasons.append(f"VIX high ({vix:.0f})")
        elif vix > 20:
            score -= 1
            reasons.append(f"VIX elevated ({vix:.0f})")

    # Fed Funds Rate — higher = tighter = bearish for risk
    ffr = indicators.get("Fed Funds Rate %", {}).get("value")
    if ffr:
        if ffr > 5:
            score -= 1
            reasons.append(f"Fed tight ({ffr:.1f}%)")
        elif ffr < 3:
            score += 1
            reasons.append(f"Fed easy ({ffr:.1f}%)")

    # 10Y-2Y spread (yield curve)
    t10 = indicators.get("10Y Treasury %", {}).get("value")
    t2 = indicators.get("2Y Treasury %", {}).get("value")
    if t10 and t2:
        spread = t10 - t2
        if spread < 0:
            score -= 2
            reasons.append(f"Inverted curve ({spread:+.2f}%)")
        elif spread > 0.5:
            score += 1
            reasons.append(f"Healthy curve ({spread:+.2f}%)")

    sentiment = "bullish" if score > 1 else "bearish" if score < -1 else "neutral"
    return {"sentiment": sentiment, "score": score, "reasons": reasons}


def _get_paper_track_record() -> dict:
    """Get paper trading performance as a confidence modifier."""
    metrics = _run_tool("paper_trader", {"action": "metrics"})
    if "error" in metrics or metrics.get("total_trades", 0) == 0:
        return {"modifier": 0, "reason": "no track record"}

    win_rate_str = metrics.get("win_rate", "0%")
    try:
        win_rate = float(win_rate_str.replace("%", "")) / 100
    except ValueError:
        win_rate = 0.5

    # Good track record boosts confidence, bad dampens it
    if win_rate > 0.65:
        return {"modifier": 0.1, "reason": f"strong track ({win_rate:.0%} win rate)"}
    elif win_rate < 0.35:
        return {"modifier": -0.15, "reason": f"weak track ({win_rate:.0%} win rate)"}
    return {"modifier": 0, "reason": f"mixed track ({win_rate:.0%})"}


def action_decide(symbol: str = "BTC") -> dict:
    """Produce a unified GO/WAIT/EXIT decision for a symbol."""
    now = datetime.now(UTC)
    votes = []  # (direction, weight, source, detail)

    # ─── Source 1: Technical Analysis ───
    try:
        from technical_analysis import analyze
        profile = analyze(symbol)
        if profile:
            ta_dir = "bullish" if profile.net_signal in ("bullish", "strong_bullish") else \
                     "bearish" if profile.net_signal in ("bearish", "strong_bearish") else "neutral"
            ta_weight = 0.3  # 30% weight
            votes.append((ta_dir, ta_weight, "TA",
                          f"{profile.net_signal} RSI={profile.rsi_14:.0f} MA={profile.ma_trend}"))
    except Exception as e:
        votes.append(("neutral", 0.1, "TA", f"unavailable: {e}"))

    # ─── Source 2: Signal Generator (multi-factor ensemble) ───
    signals = _run_tool("signal_generator", {"action": "scan", "symbols": [symbol]})
    if signals.get("signals", 0) > 0:
        sig = signals["details"][0]
        sig_dir = "bullish" if sig["action"] == "BUY" else "bearish"
        votes.append((sig_dir, 0.25, "Ensemble", sig["reason"]))
    else:
        votes.append(("neutral", 0.15, "Ensemble", "no consensus"))

    # ─── Source 3: Kronos Foundation Model ───
    kronos = _run_tool(
        "predict_kronos",
        {"action": "predict", "symbol": _canonical_market_symbol(symbol), "predict_bars": 24, "interval": "1h"},
    )
    if "error" not in kronos:
        k_dir = kronos.get("direction", "neutral")
        current_price = float(kronos.get("current_price", 0) or 0)
        predictions = kronos.get("predictions", [])
        predicted_close = float(predictions[-1]["close"]) if predictions else current_price
        change_pct = ((predicted_close - current_price) / current_price * 100) if current_price else 0.0
        k_conf = min(abs(change_pct) / 5, 1.0)  # Normalize to 0-1
        votes.append((k_dir, 0.25 * k_conf, "Kronos", f"{change_pct:+.1f}% predicted"))
    else:
        votes.append(("neutral", 0.05, "Kronos", kronos.get("error", "unavailable")[:50]))

    # ─── Source 4: Macro Environment ───
    macro = _get_macro_sentiment()
    macro_weight = 0.10
    votes.append((macro["sentiment"], macro_weight, "Macro", " | ".join(macro.get("reasons", [])[:2]) or "neutral"))

    # ─── Source 5: Track Record Modifier ───
    track = _get_paper_track_record()

    # ─── Aggregate Votes ───
    bull_weight = sum(w for d, w, _, _ in votes if d == "bullish")
    bear_weight = sum(w for d, w, _, _ in votes if d == "bearish")
    neutral_weight = sum(w for d, w, _, _ in votes if d == "neutral")
    total_weight = bull_weight + bear_weight + neutral_weight

    if total_weight == 0:
        total_weight = 1

    bull_pct = bull_weight / total_weight
    bear_pct = bear_weight / total_weight

    # Decision logic
    if bull_pct > 0.55:
        decision = "GO_LONG"
        confidence = min(0.95, bull_pct + track["modifier"])
        direction = "bullish"
    elif bear_pct > 0.55:
        decision = "GO_SHORT"
        confidence = min(0.95, bear_pct + track["modifier"])
        direction = "bearish"
    elif bull_pct > 0.40 and bear_pct < 0.30:
        decision = "LEAN_LONG"
        confidence = bull_pct * 0.8 + track["modifier"]
        direction = "bullish"
    elif bear_pct > 0.40 and bull_pct < 0.30:
        decision = "LEAN_SHORT"
        confidence = bear_pct * 0.8 + track["modifier"]
        direction = "bearish"
    else:
        decision = "WAIT"
        confidence = max(bull_pct, bear_pct)
        direction = "neutral"

    confidence = round(max(0.1, min(0.95, confidence)), 2)

    result = {
        "symbol": symbol,
        "decision": decision,
        "direction": direction,
        "confidence": confidence,
        "timestamp": now.isoformat(),
        "votes": [
            {"source": src, "direction": d, "weight": round(w, 3), "detail": det}
            for d, w, src, det in votes
        ],
        "aggregation": {
            "bullish": round(bull_pct * 100, 1),
            "bearish": round(bear_pct * 100, 1),
            "neutral": round(neutral_weight / total_weight * 100, 1),
        },
        "track_record": track,
    }

    # Persist decision for accuracy tracking
    try:
        sys.path.insert(0, str(SAPPHIRE_DIR))
        from lib.analytics.brain_accuracy import record_decision
        record_decision(result)
    except Exception as e:
        sys.stderr.write(f"brain_accuracy record failed: {e}\n")

    return result


def action_dashboard() -> dict:
    """Get decisions for all tracked symbols."""
    results = {}
    for symbol in ["BTC", "ETH", "SOL"]:
        results[symbol] = action_decide(symbol)
    return {"success": True, "decisions": results, "timestamp": datetime.now(UTC).isoformat()}


def main():
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {"action": "dashboard"}
    action = params.get("action", "dashboard")

    if action == "decide":
        result = action_decide(params.get("symbol", "BTC"))
    elif action == "dashboard":
        result = action_dashboard()
    else:
        result = {"error": f"Unknown action: {action}"}

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
