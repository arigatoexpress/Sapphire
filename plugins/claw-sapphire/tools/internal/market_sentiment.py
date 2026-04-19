#!/usr/bin/env python3
"""Sapphire Market Sentiment — Fear&Greed + funding + decorrelation + regime.

Feeds into the morning brief as Section 7.

Reads a stdin JSON command:
    {"action": "report"}           # full report (default)
    {"action": "regime"}           # regime snapshot + shift status only
    {"action": "funding"}          # funding rates only
    {"action": "decorrelation"}    # decorrelation events only

Example:
    echo '{"action":"report"}' | python3 market_sentiment.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

ROOT = Path.home() / "Code" / "Sapphire"
sys.path.insert(0, str(ROOT))


def _regime_snapshot() -> dict:
    from lib.chain.intelligence import ChainIntelligence
    return ChainIntelligence().snapshot()


def _funding_only() -> dict:
    from lib.chain.intelligence import _fetch_binance_funding
    btc = _fetch_binance_funding("BTCUSDT")
    eth = _fetch_binance_funding("ETHUSDT")
    sol = _fetch_binance_funding("SOLUSDT")
    return {
        "btc_funding_rate_pct_8h": btc,
        "eth_funding_rate_pct_8h": eth,
        "sol_funding_rate_pct_8h": sol,
        "interpretation": _interpret_funding(btc, eth, sol),
    }


def _interpret_funding(btc: float | None, eth: float | None, sol: float | None) -> str:
    vals = [v for v in (btc, eth, sol) if v is not None]
    if not vals:
        return "funding data unavailable"
    avg = sum(vals) / len(vals)
    if avg > 0.03:
        return f"crowded longs (avg {avg:+.3f}% / 8h) — squeeze risk"
    if avg > 0.01:
        return f"mild long bias (avg {avg:+.3f}% / 8h)"
    if avg < -0.01:
        return f"crowded shorts (avg {avg:+.3f}% / 8h) — squeeze risk"
    return f"balanced (avg {avg:+.3f}% / 8h)"


def _decorrelation_only() -> dict:
    try:
        from lib.analytics.correlation import CorrelationEngine
    except ImportError as exc:
        return {"error": f"correlation engine unavailable: {exc}"}
    try:
        eng = CorrelationEngine()
        report = eng.report(window_days=30)
    except Exception as exc:  # noqa: BLE001 — yfinance can raise many types
        return {"error": f"decorrelation report failed: {type(exc).__name__}: {exc}"}
    events = [
        {
            "pair": f"{e.pair[0]}↔{e.pair[1]}",
            "current": e.current,
            "baseline": e.baseline,
            "severity": e.severity,
            "note": e.note,
        }
        for e in report.decorrelation_events
    ]
    return {
        "window_days": report.matrix.window_days,
        "sample_count": report.matrix.sample_count,
        "decorrelation_events": events,
        "event_count": len(events),
    }


def _full_report() -> dict:
    regime = _regime_snapshot()
    funding = _funding_only()
    decor = _decorrelation_only()

    c = regime.get("classification", {})
    lines = []
    lines.append(f"*Regime*: {c.get('regime', 'UNKNOWN')} (score {c.get('score', 0):+.2f}, "
                 f"{c.get('inputs_ok', 0)}/{c.get('inputs_total', 0)} inputs)")
    if regime.get("fear_greed") is not None:
        lines.append(f"*Fear & Greed*: {regime['fear_greed']} ({regime.get('fear_greed_label')})")
    lines.append(f"*Funding 8h*: BTC={funding.get('btc_funding_rate_pct_8h')} "
                 f"ETH={funding.get('eth_funding_rate_pct_8h')} "
                 f"SOL={funding.get('sol_funding_rate_pct_8h')} — "
                 f"{funding.get('interpretation', '')}")

    if isinstance(decor.get("decorrelation_events"), list) and decor["decorrelation_events"]:
        top = decor["decorrelation_events"][:3]
        lines.append(f"*Decorrelation* ({decor['event_count']} events):")
        for e in top:
            lines.append(f"  • [{e['severity']}] {e['note']}")
    elif "error" in decor:
        lines.append(f"*Decorrelation*: unavailable — {decor['error']}")
    else:
        lines.append(f"*Decorrelation*: none above threshold ({decor.get('sample_count', 0)} samples)")

    if regime.get("regime_shift"):
        shift = regime["regime_shift"]
        lines.append(f"🚨 *Regime shift*: {shift['from']} → {shift['to']} "
                     f"(score {shift['from_score']:+.2f} → {shift['to_score']:+.2f})")

    return {
        "summary_markdown": "\n".join(lines),
        "regime": regime,
        "funding": funding,
        "decorrelation": decor,
    }


def main() -> None:
    raw = sys.stdin.read().strip()
    params = json.loads(raw) if raw else {"action": "report"}
    action = params.get("action", "report")
    if action == "regime":
        print(json.dumps(_regime_snapshot(), indent=2, default=str))
    elif action == "funding":
        print(json.dumps(_funding_only(), indent=2, default=str))
    elif action == "decorrelation":
        print(json.dumps(_decorrelation_only(), indent=2, default=str))
    elif action == "report":
        print(json.dumps(_full_report(), indent=2, default=str))
    else:
        print(json.dumps({"error": f"unknown action: {action}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
