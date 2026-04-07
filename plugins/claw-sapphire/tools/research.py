#!/usr/bin/env python3
"""Sapphire Autonomous Trading Research Agent.

Runs nightly to:
1. Pull price data from OpenBB (BTC, ETH, SOL, HYPE)
2. Read indicator levels from TradingView (if connected)
3. Analyze with Nemotron Cascade-2 (31.6B, free)
4. Generate predictions with confidence scores
5. Compare yesterday's predictions to actual results
6. Track accuracy over time
7. Send morning Telegram briefing

All inference is FREE via local Nemotron on GPU.

Usage:
    python3 research.py                    # Full nightly run
    python3 research.py --briefing         # Just send the morning briefing
    python3 research.py --score            # Score yesterday's predictions
    python3 research.py --history          # Show prediction accuracy history
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from nemotron import MODELS, generate

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
RESEARCH_PATH = SAPPHIRE_DIR / "data" / "trading_research.jsonl"
PREDICTIONS_PATH = SAPPHIRE_DIR / "data" / "trading_predictions.jsonl"
EVENTS_PATH = SAPPHIRE_DIR / "data" / "system_events.jsonl"
OPENBB_BASE = "http://127.0.0.1:6900/api/v1"

SYMBOLS = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "SOL": "SOL-USD",
}


@dataclass
class MarketSnapshot:
    """Point-in-time market data for analysis."""

    timestamp: str
    prices: dict  # symbol → {price, change_24h, change_7d, volume}
    macro: dict  # key indicators
    tv_data: dict  # TradingView indicator data (if available)


@dataclass
class Prediction:
    """A trading prediction with confidence."""

    timestamp: str
    symbol: str
    direction: str  # "bullish" | "bearish" | "neutral"
    confidence: float  # 0.0 - 1.0
    target_price: float
    timeframe: str  # "24h" | "7d"
    reasoning: str
    actual_price: float | None = None  # filled in when scored
    correct: bool | None = None  # filled in when scored


def _openbb_get(path: str, params: dict) -> dict:
    """GET from OpenBB REST API."""
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{OPENBB_BASE}{path}?{qs}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}


def _tv_cmd(args: list[str]) -> dict:
    """Run tv CLI command."""
    try:
        r = subprocess.run(["tv"] + args, capture_output=True, text=True, timeout=10)
        if r.stdout.strip():
            return json.loads(r.stdout)
        return {"error": r.stderr.strip() or "no output"}
    except json.JSONDecodeError:
        return {"raw": r.stdout.strip()}
    except Exception as e:
        return {"error": str(e)}


def collect_market_data() -> MarketSnapshot:
    """Collect comprehensive market data from all sources."""
    prices = {}

    # Crypto prices from OpenBB
    for label, symbol in SYMBOLS.items():
        data = _openbb_get("/crypto/price/historical", {
            "symbol": symbol, "provider": "yfinance",
            "start_date": (datetime.now(UTC) - timedelta(days=8)).strftime("%Y-%m-%d"),
        })
        results = data.get("results", [])
        if results:
            latest = results[-1]
            week_ago = results[0] if len(results) >= 7 else results[0]
            day_ago = results[-2] if len(results) >= 2 else latest
            price = latest.get("close", 0)
            prices[label] = {
                "price": round(price, 2),
                "change_24h": round((price - day_ago.get("close", price)) / max(day_ago.get("close", 1), 0.01) * 100, 2),
                "change_7d": round((price - week_ago.get("close", price)) / max(week_ago.get("close", 1), 0.01) * 100, 2),
                "volume": latest.get("volume", 0),
                "high_7d": max(r.get("high", 0) for r in results),
                "low_7d": min(r.get("low", float("inf")) for r in results),
            }

    # Macro data
    macro = {}
    for series, label in [("DGS10", "us_10y_yield"), ("VIXCLS", "vix")]:
        data = _openbb_get("/economy/fred_series", {
            "symbol": series, "provider": "fred",
            "start_date": (datetime.now(UTC) - timedelta(days=5)).strftime("%Y-%m-%d"),
        })
        results = data.get("results", [])
        if results:
            macro[label] = results[-1].get("value", 0)

    # TradingView data (if connected)
    tv_data = {}
    tv_status = _tv_cmd(["status"])
    if tv_status.get("cdp_connected"):
        tv_quote = _tv_cmd(["quote"])
        if tv_quote.get("success"):
            tv_data["chart_symbol"] = tv_quote.get("symbol", "")
            tv_data["chart_price"] = tv_quote.get("last", 0)
        tv_values = _tv_cmd(["values"])
        if tv_values.get("success"):
            tv_data["indicators"] = tv_values.get("values", {})

    return MarketSnapshot(
        timestamp=datetime.now(UTC).isoformat(),
        prices=prices,
        macro=macro,
        tv_data=tv_data,
    )


def analyze_with_nemotron(snapshot: MarketSnapshot) -> list[Prediction]:
    """Send market data to Nemotron Cascade-2 for analysis."""
    # Build the analysis prompt
    price_summary = "\n".join(
        f"  {sym}: ${d['price']:,.2f} (24h: {d['change_24h']:+.1f}%, 7d: {d['change_7d']:+.1f}%, vol: {d['volume']:,.0f})"
        for sym, d in snapshot.prices.items()
    )

    macro_summary = "\n".join(f"  {k}: {v}" for k, v in snapshot.macro.items()) or "  (unavailable)"

    tv_summary = ""
    if snapshot.tv_data.get("chart_symbol"):
        tv_summary = f"\nTradingView: {snapshot.tv_data['chart_symbol']} @ ${snapshot.tv_data.get('chart_price', 0):,.2f}"
        if snapshot.tv_data.get("indicators"):
            tv_summary += f"\nIndicators: {json.dumps(snapshot.tv_data['indicators'])[:500]}"

    prompt = f"""You are a quantitative crypto analyst. Analyze this market data and make predictions.

CURRENT PRICES (as of {snapshot.timestamp[:10]}):
{price_summary}

MACRO:
{macro_summary}
{tv_summary}

For EACH of BTC, ETH, and SOL, provide:
1. Direction: bullish, bearish, or neutral
2. Confidence: 0.0 to 1.0
3. 24-hour price target
4. Key reasoning (1-2 sentences)

Respond in STRICT JSON format:
[
  {{"symbol": "BTC", "direction": "bullish|bearish|neutral", "confidence": 0.85, "target_price": 69000, "reasoning": "..."}},
  {{"symbol": "ETH", "direction": "...", "confidence": ..., "target_price": ..., "reasoning": "..."}},
  {{"symbol": "SOL", "direction": "...", "confidence": ..., "target_price": ..., "reasoning": "..."}}
]

ONLY output the JSON array. No other text."""

    # Try cascade-2 (GPU), fall back to llama3.2:3b (local, fast)
    result = generate(prompt, model=MODELS["analyze"], timeout=120, max_tokens=1024)
    if not result.success:
        result = generate(prompt, model="llama3.2:3b", timeout=60, max_tokens=512)

    if not result.success:
        return []

    # Parse predictions from Nemotron response
    predictions = []
    try:
        start = result.response.find("[")
        end = result.response.rfind("]") + 1
        if start >= 0 and end > start:
            raw = json.loads(result.response[start:end])
            for p in raw:
                predictions.append(Prediction(
                    timestamp=snapshot.timestamp,
                    symbol=p.get("symbol", "?"),
                    direction=p.get("direction", "neutral"),
                    confidence=min(1.0, max(0.0, float(p.get("confidence", 0.5)))),
                    target_price=float(p.get("target_price", 0)),
                    timeframe="24h",
                    reasoning=p.get("reasoning", "")[:200],
                ))
    except (json.JSONDecodeError, KeyError, ValueError):
        pass

    return predictions


def score_predictions() -> dict:
    """Score yesterday's predictions against actual prices."""
    if not PREDICTIONS_PATH.exists():
        return {"scored": 0, "message": "No predictions to score"}

    lines = PREDICTIONS_PATH.read_text().strip().splitlines()
    if not lines:
        return {"scored": 0}

    scored = 0
    correct = 0
    updated_lines = []

    for line in lines:
        pred = json.loads(line)

        # Skip already scored
        if pred.get("correct") is not None:
            updated_lines.append(line)
            continue

        # Check if old enough to score (24h+)
        pred_time = datetime.fromisoformat(pred["timestamp"])
        if datetime.now(UTC) - pred_time < timedelta(hours=20):
            updated_lines.append(line)
            continue

        # Get current price
        symbol_map = {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD"}
        yf_symbol = symbol_map.get(pred["symbol"])
        if not yf_symbol:
            updated_lines.append(line)
            continue

        data = _openbb_get("/crypto/price/historical", {
            "symbol": yf_symbol, "provider": "yfinance",
            "start_date": (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%d"),
        })
        results = data.get("results", [])
        if not results:
            updated_lines.append(line)
            continue

        actual_price = results[-1].get("close", 0)
        pred["actual_price"] = round(actual_price, 2)

        # Score: direction correct?
        pred_time_price = pred.get("target_price", 0)
        if pred["direction"] == "bullish":
            pred["correct"] = actual_price > pred_time_price * 0.98  # within 2% counts
        elif pred["direction"] == "bearish":
            pred["correct"] = actual_price < pred_time_price * 1.02
        else:
            pred["correct"] = abs(actual_price - pred_time_price) / max(pred_time_price, 1) < 0.03

        scored += 1
        if pred["correct"]:
            correct += 1

        updated_lines.append(json.dumps(pred))

    # Write back
    PREDICTIONS_PATH.write_text("\n".join(updated_lines) + "\n")

    return {
        "scored": scored,
        "correct": correct,
        "accuracy": round(correct / scored * 100, 1) if scored > 0 else 0,
    }


def get_accuracy_history() -> dict:
    """Calculate overall prediction accuracy."""
    if not PREDICTIONS_PATH.exists():
        return {"total": 0, "scored": 0, "correct": 0, "accuracy": 0}

    lines = PREDICTIONS_PATH.read_text().strip().splitlines()
    total = len(lines)
    scored_preds = [json.loads(l) for l in lines if json.loads(l).get("correct") is not None]
    correct = sum(1 for p in scored_preds if p["correct"])

    by_symbol = {}
    for p in scored_preds:
        sym = p["symbol"]
        if sym not in by_symbol:
            by_symbol[sym] = {"scored": 0, "correct": 0}
        by_symbol[sym]["scored"] += 1
        if p["correct"]:
            by_symbol[sym]["correct"] += 1

    return {
        "total_predictions": total,
        "scored": len(scored_preds),
        "correct": correct,
        "accuracy": round(correct / len(scored_preds) * 100, 1) if scored_preds else 0,
        "by_symbol": {k: {**v, "accuracy": round(v["correct"] / v["scored"] * 100, 1) if v["scored"] else 0} for k, v in by_symbol.items()},
    }


def generate_briefing(snapshot: MarketSnapshot, predictions: list[Prediction], scores: dict) -> str:
    """Generate Telegram morning briefing."""
    lines = ["🌅 *Sapphire Morning Research Brief*\n"]

    # Prices
    lines.append("*Market Prices:*")
    for sym, d in snapshot.prices.items():
        arrow = "📈" if d["change_24h"] > 0 else "📉" if d["change_24h"] < 0 else "➡️"
        lines.append(f"  {arrow} {sym}: ${d['price']:,.2f} ({d['change_24h']:+.1f}% 24h, {d['change_7d']:+.1f}% 7d)")

    # Macro
    if snapshot.macro:
        lines.append("\n*Macro:*")
        if "us_10y_yield" in snapshot.macro:
            lines.append(f"  US 10Y: {snapshot.macro['us_10y_yield']}%")
        if "vix" in snapshot.macro:
            lines.append(f"  VIX: {snapshot.macro['vix']}")

    # Predictions
    if predictions:
        lines.append("\n*AI Predictions (24h):*")
        for p in predictions:
            icon = "🟢" if p.direction == "bullish" else "🔴" if p.direction == "bearish" else "⚪"
            conf_bar = "█" * int(p.confidence * 5) + "░" * (5 - int(p.confidence * 5))
            lines.append(f"  {icon} {p.symbol} → {p.direction.upper()} ({conf_bar} {p.confidence:.0%})")
            lines.append(f"     Target: ${p.target_price:,.2f}")
            lines.append(f"     _{p.reasoning}_")

    # Accuracy
    if scores.get("scored", 0) > 0:
        lines.append(f"\n*Yesterday's Accuracy:* {scores['correct']}/{scores['scored']} ({scores['accuracy']}%)")

    history = get_accuracy_history()
    if history["scored"] > 0:
        lines.append(f"*Lifetime:* {history['correct']}/{history['scored']} ({history['accuracy']}%)")
        for sym, stats in history.get("by_symbol", {}).items():
            lines.append(f"  {sym}: {stats['accuracy']}% ({stats['correct']}/{stats['scored']})")

    lines.append(f"\n_Powered by Nemotron Cascade-2 (31.6B) on RTX 5070 Ti — FREE inference_")

    return "\n".join(lines)


def run_nightly() -> dict:
    """Full nightly research run."""
    print("🌙 Sapphire Trading Research Agent — Nightly Run")
    print(f"   {datetime.now(UTC).isoformat()}\n")

    # Step 1: Collect data
    print("📊 Collecting market data...")
    snapshot = collect_market_data()
    print(f"   Prices: {list(snapshot.prices.keys())}")
    print(f"   Macro: {list(snapshot.macro.keys())}")
    print(f"   TV: {'connected' if snapshot.tv_data else 'not connected'}")

    # Save snapshot
    RESEARCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESEARCH_PATH, "a") as f:
        f.write(json.dumps({"type": "snapshot", **asdict(snapshot)}) + "\n")

    # Step 2: Score yesterday's predictions
    print("\n📈 Scoring yesterday's predictions...")
    scores = score_predictions()
    print(f"   Scored: {scores.get('scored', 0)}, Correct: {scores.get('correct', 0)}")

    # Step 3: Analyze with Nemotron
    print("\n🧠 Analyzing with Nemotron Cascade-2 (31.6B)...")
    predictions = analyze_with_nemotron(snapshot)
    print(f"   Generated {len(predictions)} predictions")
    for p in predictions:
        print(f"   {p.symbol}: {p.direction} ({p.confidence:.0%}) → ${p.target_price:,.2f}")

    # Save predictions
    for p in predictions:
        with open(PREDICTIONS_PATH, "a") as f:
            f.write(json.dumps(asdict(p)) + "\n")

    # Step 4: Generate briefing
    print("\n📱 Generating Telegram briefing...")
    briefing = generate_briefing(snapshot, predictions, scores)

    # Send via Telegram
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from notify import send_telegram_message
        result = send_telegram_message(briefing, priority="p1")
        sent = result.get("ok", False)
        print(f"   Telegram: {'sent ✅' if sent else 'failed ❌'}")
    except Exception as e:
        print(f"   Telegram error: {e}")
        sent = False

    # Log event
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": "research.nightly",
        "message": f"Nightly research: {len(predictions)} predictions, {scores.get('scored', 0)} scored ({scores.get('accuracy', 0)}%)",
        "tags": ["agent:research", "type:trading", "device:mac"],
        "data": {
            "predictions": len(predictions),
            "scored": scores.get("scored", 0),
            "accuracy": scores.get("accuracy", 0),
            "briefing_sent": sent,
        },
    }
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVENTS_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")

    print(f"\n{'='*50}")
    print(f"  DONE — {len(predictions)} predictions logged")
    print(f"{'='*50}")

    return {
        "predictions": len(predictions),
        "scored": scores.get("scored", 0),
        "accuracy": scores.get("accuracy", 0),
        "briefing_sent": sent,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Sapphire Trading Research Agent")
    parser.add_argument("--briefing", action="store_true", help="Send morning briefing only")
    parser.add_argument("--score", action="store_true", help="Score yesterday's predictions")
    parser.add_argument("--history", action="store_true", help="Show accuracy history")
    args = parser.parse_args()

    if args.score:
        print(json.dumps(score_predictions(), indent=2))
    elif args.history:
        print(json.dumps(get_accuracy_history(), indent=2))
    elif args.briefing:
        snapshot = collect_market_data()
        scores = score_predictions()
        predictions = []
        if PREDICTIONS_PATH.exists():
            lines = PREDICTIONS_PATH.read_text().strip().splitlines()[-3:]
            predictions = [Prediction(**json.loads(l)) for l in lines if "direction" in l]
        briefing = generate_briefing(snapshot, predictions, scores)
        from notify import send_telegram_message
        send_telegram_message(briefing, priority="p1")
        print("Briefing sent ✅")
    else:
        run_nightly()
