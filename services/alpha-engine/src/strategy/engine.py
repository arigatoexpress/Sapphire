import asyncio
import os
import time

from loguru import logger
from src.feeds.market_data import MarketDataAggregator


class AlphaStrategyEngine:
    def __init__(self, market_data: MarketDataAggregator):
        self.market_data = market_data
        self.running = False
        self.min_spread_pct = 0.001  # 0.1%
        self.last_execution_time = 0
        self.internal_arb_execution_enabled = (
            os.getenv("INTERNAL_ARB_EXECUTION_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self.internal_arb_quantity = max(
            0.0,
            float(os.getenv("INTERNAL_ARB_EXECUTION_QUANTITY", "0.02")),
        )

    async def start(self):
        self.running = True
        asyncio.create_task(self._arb_loop())
        logger.info(
            "🧠 Alpha Strategy Engine Started | internal_arb_execution_enabled={} qty={}",
            self.internal_arb_execution_enabled,
            self.internal_arb_quantity,
        )

    async def stop(self):
        self.running = False

    async def _arb_loop(self):
        """Core HFT Loop."""
        while self.running:
            try:
                aster_price = self.market_data.get_price("ASTER", "SOL")
                lighter_price = self.market_data.get_price("LIGHTER", "SOL")

                if aster_price > 0 and lighter_price > 0:
                    spread = abs(aster_price - lighter_price)
                    spread_pct = spread / min(aster_price, lighter_price)

                    if spread_pct > self.min_spread_pct:
                        now = time.time()
                        if now - self.last_execution_time > 5.0:  # 5s cooldown for now (debug mode)
                            logger.info(
                                f"⚡ ARB OPPORTUNITY: Aster={aster_price} Lighter={lighter_price} Spread={spread_pct:.4f}"
                            )

                            if self.internal_arb_execution_enabled:
                                from src.execution.dispatcher import dispatcher

                                cmd = {
                                    "type": "ARB_EXECUTE",
                                    "side": "BUY" if aster_price < lighter_price else "SELL",
                                    "symbol": "SOL",
                                    "quantity": self.internal_arb_quantity,
                                    "spread": spread_pct,
                                    "source": "alpha_internal_arb",
                                }
                                await dispatcher.send_command("ASTER", cmd)
                            else:
                                logger.info(
                                    "Internal ARB execution disabled; opportunity observed only."
                                )
                            self.last_execution_time = now

                # Slower pace for Cloud Run stability (500ms)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Strategy Loop Error: {e}")
                await asyncio.sleep(1)
