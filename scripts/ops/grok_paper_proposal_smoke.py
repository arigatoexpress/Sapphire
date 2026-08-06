#!/usr/bin/env python3
"""Smoke free-reign gate against a fixed paper proposal suite (no network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from lib.grok.free_reign_gate import GateRequest, gate_order  # noqa: E402

SUITE = [
    GateRequest("SONNY", "buy", "rh_l2", "l2_token", 5.0),
    GateRequest("IBIT", "buy", "rh_agentic", "equity", 20.0),
    GateRequest("ETH", "buy", "rh_l2", "l2_token", 50.0),
    GateRequest("AXTI", "buy", "rh_agentic", "option", 35.0, is_defined_risk_option=True),
    GateRequest("NVDA", "sell", "rh_agentic", "equity", 5.0),
    GateRequest("X", "buy", "moss", "l2_token", 1.0, moss_grant_hours_left=-5),
    GateRequest("ETH", "buy", "paper", "l2_token", 100.0),
]


def main() -> int:
    rows = []
    for req in SUITE:
        r = gate_order(req)
        rows.append(
            {
                "symbol": req.symbol,
                "side": req.side,
                "rail": req.rail,
                "allowed": r.allowed,
                "code": r.code,
                "reason": r.reason,
            }
        )
    print(json.dumps({"count": len(rows), "results": rows}, indent=2))
    # sanity: dens blocked, axti allowed, paper allowed
    by = {(x["symbol"], x["side"], x["rail"]): x for x in rows}
    assert by[("SONNY", "buy", "rh_l2")]["allowed"] is False
    assert by[("AXTI", "buy", "rh_agentic")]["allowed"] is True
    assert by[("ETH", "buy", "paper")]["allowed"] is True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
