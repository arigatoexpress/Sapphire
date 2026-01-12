import asyncio
import json
import time
from typing import Dict, Optional

import websockets
from loguru import logger


class MarketDataAggregator:
    def __init__(self):
        self.prices: Dict[str, Dict[str, float]] = {
            "DRIFT": {"SOL": 0.0},
            "HYPERLIQUID": {"SOL": 0.0},
        }
        self.running = False

    async def start(self):
        self.running = True
        # Start WS connections in background
        asyncio.create_task(self._drift_feed())
        asyncio.create_task(self._hl_feed())

    async def stop(self):
        self.running = False

    def get_price(self, venue: str, symbol: str) -> float:
        return self.prices.get(venue, {}).get(symbol, 0.0)

    async def _drift_feed(self):
        """Simulated Drift WS Feed (Replace with actual Drift WS protocol)."""
        # Note: In production, connect to wss://dlob.drift.trade/ws
        url = "wss://dlob.drift.trade/ws"
        logger.info("🌊 Connecting to Drift Feed...")
        while self.running:
            try:
                # For MVP demo, we will simulate or use a public feed if accessible without auth
                # Here we Stub for stability until we implement full Drift protocol
                self.prices["DRIFT"]["SOL"] = 150.0  # Placeholder
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Drift WS Error: {e}")
                await asyncio.sleep(1)

    async def _hl_feed(self):
        """Hyperliquid WS Feed."""
        url = "wss://api.hyperliquid.xyz/ws"
        logger.info("💧 Connecting to Hyperliquid Feed...")
        while self.running:
            try:
                async with websockets.connect(url) as ws:
                    # Subscribe to SOL metadata/ticker
                    sub_msg = {"method": "subscribe", "subscription": {"type": "allMids"}}
                    await ws.send(json.dumps(sub_msg))

                    while self.running:
                        msg = await ws.recv()
                        data = json.loads(msg)

                        if data.get("channel") == "allMids":
                            mids = data.get("data", {}).get("mids", {})
                            if "SOL" in mids:
                                price = float(mids["SOL"])
                                self.prices["HYPERLIQUID"]["SOL"] = price
            except Exception as e:
                logger.error(f"Hyperliquid WS Error: {e}")
                await asyncio.sleep(1)
