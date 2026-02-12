import asyncio
import json
import time
from typing import Dict, Optional

import websockets
from loguru import logger


class MarketDataAggregator:
    def __init__(self):
        self.prices: Dict[str, Dict[str, float]] = {
            "ASTER": {"SOL": 0.0},
            "LIGHTER": {"SOL": 0.0},
        }
        self.running = False

    async def start(self):
        self.running = True
        # Start WS connections in background
        asyncio.create_task(self._aster_feed())
        asyncio.create_task(self._hl_feed())

    async def stop(self):
        self.running = False

    def get_price(self, venue: str, symbol: str) -> float:
        return self.prices.get(venue, {}).get(symbol, 0.0)

    async def _aster_feed(self):
        """Simulated Aster WS Feed (Replace with actual Aster WS protocol)."""
        # Note: In production, connect to wss://dlob.aster.trade/ws
        url = "wss://dlob.aster.trade/ws"
        logger.info("🌊 Connecting to Aster Feed...")
        while self.running:
            try:
                # For MVP demo, we will simulate or use a public feed if accessible without auth
                # Here we Stub for stability until we implement full Aster protocol
                self.prices["ASTER"]["SOL"] = 150.0  # Placeholder
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Aster WS Error: {e}")
                await asyncio.sleep(1)

    async def _hl_feed(self):
        """Lighter WS Feed."""
        url = "wss://api.lighter.xyz/ws"
        logger.info("💧 Connecting to Lighter Feed...")
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
                                self.prices["LIGHTER"]["SOL"] = price
            except Exception as e:
                logger.error(f"Lighter WS Error: {e}")
                await asyncio.sleep(1)
