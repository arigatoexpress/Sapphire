"""
Order Lifecycle Management
Aggressively manages orders to prevent stale/lingering limit orders.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .experiment_tracker import get_experiment_tracker
from .logger import get_logger

logger = get_logger(__name__)


class OrderManager:
    """
    Manages active orders with strict timeouts and price deviation checks.
    """

    def __init__(self, exchange_client: Any):
        self.exchange = exchange_client
        self.max_order_age = 30.0  # seconds
        self.cancel_threshold_pct = 0.002  # 0.2% price move
        self.tracker = get_experiment_tracker()

    async def check_and_cancel_stale_orders(
        self, active_orders: List[Dict], current_prices: Dict[str, float]
    ):
        """
        Check active orders and cancel those that violate age or price policies.
        """
        cancel_tasks = []

        for order in active_orders:
            should_cancel = False
            reason = ""

            # Check age
            # Assuming order structure has 'timestamp' or 'created_at' in ms or datetime
            # Adjust based on actual exchange format. Here assuming 'timestamp' in ms
            order_time = order.get("timestamp", 0) / 1000.0
            age = time.time() - order_time

            if age > self.max_order_age:
                should_cancel = True
                reason = f"max_age ({age:.1f}s > {self.max_order_age}s)"

            # Check price deviation if not already triggered
            if not should_cancel:
                symbol = order.get("symbol")
                price = order.get("price")  # Limit price
                side = order.get("side")
                current_price = current_prices.get(symbol)

                if price and current_price:
                    price = float(price)
                    deviation = abs(current_price - price) / price

                    # Logic: if price moves AWAY from our limit, we might never get filled and it's drifting.
                    # Or if market moves drastically against us?
                    # The requirement: "Cancel if current_price moves > 0.2% away from limit price"
                    if deviation > self.cancel_threshold_pct:
                        should_cancel = True
                        reason = (
                            f"price_deviation ({deviation:.2%} > {self.cancel_threshold_pct:.1%})"
                        )

            if should_cancel:
                logger.warning(
                    f"🚫 Canceling order {order.get('id')} ({order.get('symbol')}): {reason}"
                )

                # Track this event
                self.tracker.track_metric(
                    "order_auto_cancel",
                    1,
                    {"order_id": order.get("id"), "reason": reason, "age": age},
                )

                cancel_tasks.append(
                    self.exchange.cancel_order(order.get("symbol"), order.get("id"))
                )

        if cancel_tasks:
            results = await asyncio.gather(*cancel_tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    logger.error(f"Failed to cancel order: {res}")

    async def execute_market_stop(self, symbol: str, side: str, amount: float, params: Dict = None):
        """
        Execute a MARKET order for stop-loss purposes.
        Priority: Speed and Certainty.
        """
        try:
            start_time = time.time()
            order = await self.exchange.create_market_order(
                symbol=symbol, side=side, amount=amount, params=params or {"reduceOnly": True}
            )
            duration = (time.time() - start_time) * 1000

            self.tracker.track_metric(
                "stop_loss_execution_ms", duration, {"symbol": symbol, "type": "market"}
            )

            logger.info(f"⚡️ Executed MARKET stop for {symbol}: {duration:.1f}ms")
            return order
        except Exception as e:
            logger.error(f"CRITICAL: Failed to execute market stop for {symbol}: {e}")
            self.tracker.track_metric("stop_loss_failure", 1, {"symbol": symbol, "error": str(e)})
            raise e
