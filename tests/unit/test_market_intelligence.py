from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from lib.intel import market_intelligence as market


def test_intel_package_does_not_eagerly_import_market_intelligence():
    repo_root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": str(repo_root)}
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import lib.intel; "
                "raise SystemExit(1 if 'lib.intel.market_intelligence' in sys.modules else 0)"
            ),
        ],
        env=env,
        check=False,
    )
    assert proc.returncode == 0


def test_collect_uses_previous_hyperliquid_feeds_when_source_unavailable(monkeypatch):
    previous = {
        "liquidation": {
            "timestamp": "2026-04-24T00:00:00+00:00",
            "bands": [{"coin": "BTC", "flag": "neutral"}],
            "alerts": [],
        },
        "order_flow": {
            "timestamp": "2026-04-24T00:00:00+00:00",
            "velocities": [{"coin": "BTC", "signal": "neutral"}],
            "crowding_alerts": [],
        },
    }

    monkeypatch.setattr(market, "_load_raw_snapshot", lambda: previous)
    monkeypatch.setattr(market, "_fetch_stablecoins", lambda _prev: {"signal": "neutral"})
    monkeypatch.setattr(market, "_fetch_econ_calendar", lambda: {"events": []})
    monkeypatch.setattr(market, "_fetch_political", lambda: {"signals": []})

    def unavailable(_self):
        raise market.SourceError("offline")

    monkeypatch.setattr(market.HyperliquidClient, "meta_and_asset_ctxs", unavailable)

    snap = market.MarketIntelligence().collect()

    assert snap.liquidation == previous["liquidation"]
    assert snap.order_flow == previous["order_flow"]
    assert "using previous snapshot" in snap.errors["liquidation"]
    assert "using previous snapshot" in snap.errors["order_flow"]
