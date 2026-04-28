from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

risk_kernel = importlib.import_module("lib.core.risk_kernel")

decision = {
    "decision_id": "demo-btc-order-001",
    "action": "open_order",
    "symbol": "BTC-USD",
    "side": "long",
    "price": 65_000.0,
    "notional_usd": 1_300.0,
    "proposed_position_pct": 1.3,
    "equity": 100_000.0,
    "atr": 1_700.0,
    "confidence": 0.72,
    "risk_metrics": {
        "daily_loss_pct": 0.8,
        "intraday_drawdown_pct": 1.2,
        "kill_switch_active": False,
    },
}

verdict = risk_kernel.RiskKernelV1().evaluate(decision)
print(json.dumps(verdict.to_dict(), indent=2, sort_keys=True))
