#!/usr/bin/env python3
"""Sapphire Intelligence Digest — unified morning report.

Synthesizes ALL data sources into one actionable brief:
- Technical analysis (RSI, MACD, MA, BB)
- Quant analysis (S/R levels, trend strength, correlations)
- Research predictions + accuracy history
- Factory health (repos, tests, QA)
- System mesh status (devices, services)

Usage:
    python3 digest.py              # Generate and send full digest
    python3 digest.py --json       # Output raw JSON
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

SAPPHIRE_DIR = Path.home() / "Code" / "Sapphire"
PREDICTIONS_PATH = SAPPHIRE_DIR / "data" / "trading_predictions.jsonl"
QA_REPORT_PATH = SAPPHIRE_DIR / "data" / "frontend_qa_report.json"
EVENTS_PATH = SAPPHIRE_DIR / "data" / "system_events.jsonl"


def collect_market_intelligence() -> dict:
    """Collect technical + quant analysis."""
    try:
        from technical_analysis import analyze_all
        from quant_analysis import analyze_full, correlation_matrix

        technical = analyze_all()
        quant = {sym: analyze_full(sym) for sym in technical}
        correlations = correlation_matrix()

        return {
            "technical": {sym: {"price": p.price, "net_signal": p.net_signal, "rsi": p.rsi_14,
                                 "macd_cross": p.macd_cross, "ma_trend": p.ma_trend}
                          for sym, p in technical.items()},
            "quant": {sym: {"trend_strength": q.trend_strength, "trend_direction": q.trend_direction,
                            "nearest_support": q.nearest_support, "nearest_resistance": q.nearest_resistance,
                            "risk_reward": q.risk_reward}
                      for sym, q in quant.items() if q},
            "correlations": [{"pair": f"{c.asset_a}/{c.asset_b}", "corr": c.correlation, "interp": c.interpretation}
                             for c in correlations],
        }
    except Exception as e:
        return {"error": str(e)}


def collect_prediction_accuracy() -> dict:
    """Get prediction accuracy history."""
    if not PREDICTIONS_PATH.exists():
        return {"total": 0, "accuracy": 0}

    preds = [json.loads(l) for l in PREDICTIONS_PATH.read_text().strip().splitlines() if l.strip()]
    scored = [p for p in preds if p.get("correct") is not None]
    correct = sum(1 for p in scored if p["correct"])

    recent = preds[-3:] if preds else []

    return {
        "total": len(preds),
        "scored": len(scored),
        "correct": correct,
        "accuracy": round(correct / len(scored) * 100, 1) if scored else 0,
        "recent": [{"symbol": p["symbol"], "direction": p["direction"],
                     "confidence": p.get("confidence", 0), "correct": p.get("correct")}
                    for p in recent],
    }


def collect_system_health() -> dict:
    """Check system health."""
    import subprocess

    def check(url: str) -> str:
        try:
            r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url],
                               capture_output=True, text=True, timeout=5)
            return r.stdout.strip()
        except Exception:
            return "000"

    services = {
        "control-plane": check("http://127.0.0.1:8082/"),
        "dashboard": check("http://127.0.0.1:8080/health"),
        "openbb": check("http://127.0.0.1:6900/api/v1/equity/price/quote?symbol=AAPL&provider=yfinance"),
        "regional-intel": check("http://127.0.0.1:8060/"),
    }

    return {
        "services": services,
        "services_up": sum(1 for v in services.values() if v == "200"),
        "services_total": len(services),
    }


def collect_factory_health() -> dict:
    """Get factory state."""
    if QA_REPORT_PATH.exists():
        report = json.loads(QA_REPORT_PATH.read_text())
        scores = {name: fe.get("ux_score", 0) for name, fe in report.get("frontends", {}).items()}
        return {"frontend_scores": scores, "avg_score": round(sum(scores.values()) / max(len(scores), 1), 1)}
    return {}


def generate_digest() -> str:
    """Generate the full intelligence digest."""
    lines = [f"📋 *Sapphire Intelligence Digest*",
             f"_{datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}_\n"]

    # Market Intelligence
    market = collect_market_intelligence()
    if "technical" in market:
        lines.append("*📊 Market Analysis*")
        for sym, data in market["technical"].items():
            icon = "🟢" if "bullish" in data["net_signal"] else "🔴" if "bearish" in data["net_signal"] else "⚪"
            lines.append(f"  {icon} {sym} ${data['price']:,.2f} | {data['net_signal'].upper()} | RSI {data['rsi']:.0f} | MACD {data['macd_cross']}")

        if "quant" in market:
            lines.append("\n*🎯 Key Levels*")
            for sym, q in market["quant"].items():
                lines.append(f"  {sym}: S=${q['nearest_support']:,.2f} R=${q['nearest_resistance']:,.2f} R:R={q['risk_reward']:.1f}")

            # Best setup
            best = max(market["quant"].items(), key=lambda x: x[1]["risk_reward"])
            if best[1]["risk_reward"] > 1.0:
                lines.append(f"\n  💡 *Best setup: {best[0]}* — R:R {best[1]['risk_reward']:.1f} (more room up than down)")

        if market.get("correlations"):
            corr_strs = []
            for c in market["correlations"]:
                corr_strs.append(f"{c['pair']} {c['corr']:+.2f}")
            lines.append(f"\n*🔗 Correlations*: {', '.join(corr_strs)}")

    # Predictions
    preds = collect_prediction_accuracy()
    if preds["total"] > 0:
        lines.append(f"\n*🧠 Predictions*")
        lines.append(f"  Lifetime: {preds['correct']}/{preds['scored']} ({preds['accuracy']}%)")
        if preds["recent"]:
            for p in preds["recent"]:
                icon = "✅" if p["correct"] else "❌" if p["correct"] is False else "⏳"
                lines.append(f"  {icon} {p['symbol']} {p['direction']} ({p['confidence']:.0%})")

    # System Health
    health = collect_system_health()
    lines.append(f"\n*🖥️ System*: {health['services_up']}/{health['services_total']} services up")

    # Factory
    factory = collect_factory_health()
    if factory.get("frontend_scores"):
        lines.append(f"*🏭 Frontend Avg*: {factory['avg_score']}/10")

    lines.append(f"\n_Generated by Sapphire OS — all data calculated, never hallucinated_")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.json:
        data = {
            "market": collect_market_intelligence(),
            "predictions": collect_prediction_accuracy(),
            "system": collect_system_health(),
            "factory": collect_factory_health(),
        }
        print(json.dumps(data, indent=2, default=str))
    else:
        digest = generate_digest()
        print(digest)
        # Also send to Telegram
        try:
            sys.path.insert(0, str(Path(__file__).parent))
            from notify import send_telegram_message
            result = send_telegram_message(digest, priority="p1")
            print(f"\n{'Sent to Telegram ✅' if result.get('ok') else 'Telegram send failed'}")
        except Exception as e:
            print(f"\nTelegram error: {e}")
