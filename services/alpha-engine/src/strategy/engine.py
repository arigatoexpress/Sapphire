import asyncio
import time

from loguru import logger
from src.feeds.market_data import MarketDataAggregator


class AlphaStrategyEngine:
    def __init__(self, market_data: MarketDataAggregator):
        self.market_data = market_data
        self.running = False
        self.min_spread_pct = 0.001  # 0.1%
        self.last_execution_time = 0

    async def start(self):
        self.running = True
        asyncio.create_task(self._arb_loop())
        logger.info("🧠 Alpha Strategy Engine Started")

    async def stop(self):
        self.running = False

    async def _arb_loop(self):
        """Core HFT Loop."""
        while self.running:
            try:
                drift_price = self.market_data.get_price("DRIFT", "SOL")
                hl_price = self.market_data.get_price("HYPERLIQUID", "SOL")

                if drift_price > 0 and hl_price > 0:
                    spread = abs(drift_price - hl_price)
                    spread_pct = spread / min(drift_price, hl_price)

                    if spread_pct > self.min_spread_pct:
                        now = time.time()
                        if now - self.last_execution_time > 5.0:  # 5s cooldown for now (debug mode)
                            logger.info(
                                f"⚡ ARB OPPORTUNITY: Drift={drift_price} HL={hl_price} Spread={spread_pct:.4f}"
                            )

                            # Phase 2.2: Dispatch Execution
                            from src.execution.dispatcher import dispatcher

                            cmd = {
                                "type": "ARB_EXECUTE",
                                "side": "BUY" if drift_price < hl_price else "SELL",
                                "symbol": "SOL",
                                "spread": spread_pct,
                            }
                            # Example: Send to Drift
                            await dispatcher.send_command("DRIFT", cmd)
                            self.last_execution_time = now

                # Slower pace for Cloud Run stability (500ms)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Strategy Loop Error: {e}")
                await asyncio.sleep(1)
