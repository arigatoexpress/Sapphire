#!/usr/bin/env python3
"""Sapphire Trading Research Agent v2 — Grounded in Real Data.

v1 hallucinated prices and indicators. v2 fixes this:
- ALL numbers come from OpenBB via technical_analysis.py (pure math)
- LLM only interprets patterns and generates narrative
- Predictions use actual price ± ATR (not imagined numbers)
- TradingView indicator readings integrated when available
- Every prediction scored against actual outcomes

Usage:
    python3 research.py                    # Full nightly run
    python3 research.py --briefing         # Morning briefing only
    python3 research.py --score            # Score yesterday's predictions
    python3 research.py --history          # Accuracy history
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from nemotron import MODELS, generate
from technical_analysis import TechnicalProfile, analyze_all

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
RESEARCH_PATH = SAPPHIRE_DIR / "data" / "trading_research.jsonl"
PREDICTIONS_PATH = SAPPHIRE_DIR / "data" / "trading_predictions.jsonl"
EVENTS_PATH = SAPPHIRE_DIR / "data" / "system_events.jsonl"
OPENBB_BASE = "http://127.0.0.1:6900/api/v1"


def _tv_cmd(args: list[str]) -> dict:
    """Run tv CLI command."""
    try:
        r = subprocess.run(["tv"] + args, capture_output=True, text=True, timeout=10)
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except Exception:
        return {}


def collect_tv_data() -> dict:
    """Read live TradingView indicator values if connected."""
    status = _tv_cmd(["status"])
    if not status.get("cdp_connected"):
        return {"connected": False}

    tv = {"connected": True, "symbol": status.get("chart_symbol", "")}
    quote = _tv_cmd(["quote"])
    if quote.get("success"):
        tv["price"] = quote.get("last", 0)

    values = _tv_cmd(["values"])
    if values.get("success"):
        tv["indicators"] = values.get("values", {})

    lines = _tv_cmd(["data", "lines"])
    if lines.get("success"):
        tv["levels"] = lines.get("lines", [])[:10]

    return tv


def generate_predictions(profiles: dict[str, TechnicalProfile], tv_data: dict) -> list[dict]:
    """Use LLM to interpret real technical data — NOT to generate numbers.

    The LLM receives:
    - Exact prices, RSI, MACD, MA, BB values (calculated, not hallucinated)
    - TradingView indicator readings (if connected)
    - Net signal counts

    The LLM outputs:
    - Direction interpretation
    - Confidence (how many signals agree)
    - Narrative reasoning

    Target price is CALCULATED: price ± (ATR * confidence_factor), NOT from LLM.
    """
    predictions = []

    for symbol, p in profiles.items():
        # Calculate target price mathematically
        # Bullish: price + ATR * factor. Bearish: price - ATR * factor.
        conf_factor = abs(p.signal_count_bullish - p.signal_count_bearish) / 8
        confidence = min(0.95, max(0.3, 0.5 + conf_factor * 0.3))

        if p.net_signal in ("strong_bullish", "bullish"):
            direction = "bullish"
            target = round(p.price + p.atr_14 * (0.5 + conf_factor), 2)
        elif p.net_signal in ("strong_bearish", "bearish"):
            direction = "bearish"
            target = round(p.price - p.atr_14 * (0.5 + conf_factor), 2)
        else:
            direction = "neutral"
            target = p.price

        predictions.append(
            {
                "timestamp": p.timestamp,
                "symbol": symbol,
                "direction": direction,
                "confidence": round(confidence, 2),
                "target_price": target,
                "entry_price": p.price,
                "timeframe": "24h",
                "signals_bullish": p.signal_count_bullish,
                "signals_bearish": p.signal_count_bearish,
                "rsi": p.rsi_14,
                "macd_cross": p.macd_cross,
                "ma_trend": p.ma_trend,
                "bb_position": p.bb_position,
                "volume_signal": p.volume_signal,
                "volatility": p.volatility_regime,
                "reasoning": "",  # Will be filled by LLM
                "actual_price": None,
                "correct": None,
            }
        )

    # Use LLM ONLY for narrative reasoning (not numbers)
    if predictions:
        summary_lines = []
        for pred in predictions:
            p = profiles[pred["symbol"]]
            summary_lines.append(
                f"{pred['symbol']}: ${p.price:,.2f} | RSI={p.rsi_14:.0f} ({p.rsi_zone}) | "
                f"MACD={p.macd_cross} | MA={p.ma_trend} | BB={p.bb_position} | "
                f"Vol={p.volume_signal} ({p.volume_ratio:.1f}x) | "
                f"Signals: {p.signal_count_bullish}↑ {p.signal_count_bearish}↓ → {p.net_signal}"
            )

        tv_context = ""
        if tv_data.get("connected") and tv_data.get("indicators"):
            tv_context = f"\nTradingView indicators on {tv_data['symbol']}: {json.dumps(tv_data['indicators'])[:300]}"

        prompt = f"""You are a crypto analyst. Here is today's REAL technical data (all numbers are calculated, not estimated):

{chr(10).join(summary_lines)}
{tv_context}

For each symbol, write ONE sentence explaining the key pattern you see. Focus on:
- What the MACD cross means in context
- Whether RSI confirms or contradicts the MA trend
- What the volume tells us
- Any divergences between indicators

Format: SYMBOL: your one sentence.
Example: BTC: Bullish MACD cross with neutral RSI and above-average volume suggests momentum building for a breakout above the 20-day MA."""

        result = generate(
            prompt, model=MODELS.get("analyze", "llama3.2:3b"), timeout=60, max_tokens=300
        )
        if not result.success:
            result = generate(prompt, model="llama3.2:3b", timeout=30, max_tokens=300)

        if result.success:
            for pred in predictions:
                sym = pred["symbol"]
                for line in result.response.splitlines():
                    if line.strip().startswith(f"{sym}:"):
                        pred["reasoning"] = line.strip()[len(sym) + 1 :].strip()[:200]
                        break
                if not pred["reasoning"]:
                    pred["reasoning"] = (
                        f"{pred['direction'].capitalize()} — {pred['signals_bullish']}↑ vs {pred['signals_bearish']}↓ signals"
                    )

    return predictions


def score_predictions() -> dict:
    """Score yesterday's predictions against actual prices."""
    import urllib.request

    if not PREDICTIONS_PATH.exists():
        return {"scored": 0, "message": "No predictions to score"}

    lines = PREDICTIONS_PATH.read_text(encoding="utf-8").strip().splitlines()
    scored = 0
    correct = 0
    updated_lines = []

    for line in lines:
        pred = json.loads(line)

        if pred.get("correct") is not None:
            updated_lines.append(line)
            if pred["correct"]:
                correct += 1
            scored += 1
            continue

        pred_time = datetime.fromisoformat(pred["timestamp"])
        if datetime.now(UTC) - pred_time < timedelta(hours=20):
            updated_lines.append(line)
            continue

        # Fetch actual price
        sym_map = {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD"}
        yf = sym_map.get(pred["symbol"])
        if not yf:
            updated_lines.append(line)
            continue

        try:
            url = f"{OPENBB_BASE}/crypto/price/historical?symbol={yf}&provider=yfinance&start_date={(datetime.now(UTC) - timedelta(days=2)).strftime('%Y-%m-%d')}"
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read())
            results = data.get("results", [])
            if not results:
                updated_lines.append(line)
                continue

            actual = results[-1].get("close", 0)
            pred["actual_price"] = round(actual, 2)
            entry = pred.get("entry_price", pred.get("target_price", actual))

            # Score: was direction correct?
            actual_move = actual - entry
            if pred["direction"] == "bullish":
                pred["correct"] = actual_move > 0
            elif pred["direction"] == "bearish":
                pred["correct"] = actual_move < 0
            else:
                pred["correct"] = abs(actual_move / max(entry, 1)) < 0.02  # Within 2%

            scored += 1
            if pred["correct"]:
                correct += 1
        except Exception:
            pass

        updated_lines.append(json.dumps(pred))

    PREDICTIONS_PATH.write_text("\n".join(updated_lines) + "\n")

    return {
        "scored": scored,
        "correct": correct,
        "accuracy": round(correct / scored * 100, 1) if scored > 0 else 0,
    }


def get_accuracy_history() -> dict:
    """Overall accuracy stats."""
    if not PREDICTIONS_PATH.exists():
        return {"total": 0, "scored": 0, "correct": 0, "accuracy": 0}

    lines = PREDICTIONS_PATH.read_text(encoding="utf-8").strip().splitlines()
    preds = [json.loads(l) for l in lines]
    scored = [p for p in preds if p.get("correct") is not None]
    correct = sum(1 for p in scored if p["correct"])

    by_symbol = {}
    for p in scored:
        sym = p["symbol"]
        if sym not in by_symbol:
            by_symbol[sym] = {"scored": 0, "correct": 0}
        by_symbol[sym]["scored"] += 1
        if p["correct"]:
            by_symbol[sym]["correct"] += 1

    return {
        "total_predictions": len(preds),
        "scored": len(scored),
        "correct": correct,
        "accuracy": round(correct / len(scored) * 100, 1) if scored else 0,
        "by_symbol": {
            k: {**v, "accuracy": round(v["correct"] / v["scored"] * 100, 1)}
            for k, v in by_symbol.items()
        },
    }


def generate_briefing(
    profiles: dict[str, TechnicalProfile], predictions: list[dict], scores: dict, tv_data: dict
) -> str:
    """Generate Telegram morning briefing with REAL data."""
    lines = ["🌅 *Sapphire Research Brief*\n"]

    for sym, p in profiles.items():
        arrow = "📈" if p.change_24h_pct > 0 else "📉" if p.change_24h_pct < 0 else "➡️"
        signal_icon = (
            "🟢" if "bullish" in p.net_signal else "🔴" if "bearish" in p.net_signal else "⚪"
        )
        lines.append(f"{arrow} *{sym}*: ${p.price:,.2f} ({p.change_24h_pct:+.1f}%)")
        lines.append(
            f"   {signal_icon} {p.net_signal.upper()} ({p.signal_count_bullish}↑ {p.signal_count_bearish}↓)"
        )
        lines.append(f"   RSI: {p.rsi_14:.0f} | MACD: {p.macd_cross} | Vol: {p.volume_signal}")

    if tv_data.get("connected"):
        lines.append(f"\n📊 TV: {tv_data.get('symbol', '?')} @ ${tv_data.get('price', 0):,.2f}")

    if predictions:
        lines.append("\n*Predictions (24h):*")
        for pred in predictions:
            icon = (
                "🟢"
                if pred["direction"] == "bullish"
                else "🔴"
                if pred["direction"] == "bearish"
                else "⚪"
            )
            conf = int(pred["confidence"] * 100)
            lines.append(
                f"  {icon} {pred['symbol']}: {pred['direction']} ({conf}%) → ${pred['target_price']:,.2f}"
            )
            if pred.get("reasoning"):
                lines.append(f"     _{pred['reasoning'][:100]}_")

    if scores.get("scored", 0) > 0:
        lines.append(
            f"\n*Yesterday:* {scores['correct']}/{scores['scored']} correct ({scores['accuracy']}%)"
        )

    history = get_accuracy_history()
    if history["scored"] > 0:
        lines.append(
            f"*Lifetime:* {history['correct']}/{history['scored']} ({history['accuracy']}%)"
        )

    lines.append("\n_Math: RSI/MACD/BB/MA calculated from OHLCV. LLM: narrative only._")

    return "\n".join(lines)


def run_nightly() -> dict:
    """Full nightly research run."""
    print("🌙 Sapphire Research Agent v2 — Grounded in Real Data")
    print(f"   {datetime.now(UTC).isoformat()}\n")

    # Step 1: Technical analysis (PURE MATH)
    print("📊 Running technical analysis...")
    profiles = analyze_all()
    for sym, p in profiles.items():
        print(
            f"   {sym}: ${p.price:,.2f} | {p.net_signal} | RSI={p.rsi_14:.0f} | MACD={p.macd_cross}"
        )

    # Step 2: TradingView data (if connected)
    print("\n📈 Reading TradingView...")
    tv_data = collect_tv_data()
    print(
        f"   {'Connected: ' + tv_data.get('symbol', '') if tv_data.get('connected') else 'Not connected'}"
    )

    # Step 3: Score yesterday
    print("\n📊 Scoring yesterday's predictions...")
    scores = score_predictions()
    print(f"   Scored: {scores.get('scored', 0)}, Correct: {scores.get('correct', 0)}")

    # Step 4: Generate predictions (math + LLM narrative)
    print("\n🧠 Generating predictions...")
    predictions = generate_predictions(profiles, tv_data)
    for pred in predictions:
        print(
            f"   {pred['symbol']}: {pred['direction']} ({pred['confidence']:.0%}) → ${pred['target_price']:,.2f}"
        )
        print(f"     {pred.get('reasoning', '')[:80]}")

    # Save
    RESEARCH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESEARCH_PATH, "a") as f:
        snapshot = {"type": "analysis", "timestamp": datetime.now(UTC).isoformat()}
        for sym, p in profiles.items():
            snapshot[sym] = asdict(p)
        f.write(json.dumps(snapshot) + "\n")

    for pred in predictions:
        with open(PREDICTIONS_PATH, "a") as f:
            f.write(json.dumps(pred) + "\n")

    # Step 5: Briefing
    print("\n📱 Sending Telegram briefing...")
    briefing = generate_briefing(profiles, predictions, scores, tv_data)
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from notify import send_telegram_message

        result = send_telegram_message(briefing, priority="p1")
        sent = result.get("ok", False)
    except Exception as e:
        sent = False
        print(f"   Telegram error: {e}")
    print(f"   {'Sent ✅' if sent else 'Failed ❌'}")

    # Log event
    event = {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": "research.nightly",
        "message": f"Research v2: {len(predictions)} predictions ({scores.get('accuracy', 0)}% yesterday)",
        "tags": ["agent:research", "type:trading", "device:mac"],
        "data": {"predictions": len(predictions), "accuracy": scores.get("accuracy", 0)},
    }
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVENTS_PATH, "a") as f:
        f.write(json.dumps(event) + "\n")

    print(f"\n{'=' * 50}")
    print(f"  DONE — {len(predictions)} grounded predictions")
    print(f"{'=' * 50}")

    return {"predictions": len(predictions), "scores": scores, "sent": sent}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--briefing", action="store_true")
    parser.add_argument("--score", action="store_true")
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()

    if args.score:
        print(json.dumps(score_predictions(), indent=2))
    elif args.history:
        print(json.dumps(get_accuracy_history(), indent=2))
    elif args.briefing:
        profiles = analyze_all()
        tv = collect_tv_data()
        scores = score_predictions()
        preds = generate_predictions(profiles, tv)
        briefing = generate_briefing(profiles, preds, scores, tv)
        from notify import send_telegram_message

        send_telegram_message(briefing, priority="p1")
    else:
        run_nightly()
