import asyncio
import math
from typing import Any, Dict, List

class VpinHFTAgent:
    def __init__(self, exchange_client: Any, pubsub_topic: str, risk_manager_queue: asyncio.Queue):
        self.exchange_client = exchange_client
        self.pubsub_topic = pubsub_topic
        self.risk_manager_queue = risk_manager_queue
        self.vpin_threshold = 0.4  # Dynamic threshold, can be adjusted

    def calculate_vpin(self, tick_data_batch: List[Dict[str, Any]]) -> float:
        """
        Calculates the Volume-Weighted VPIN.
        """
        if len(tick_data_batch) < 10:
            return 0.0

        total_price_volume = 0.0
        total_volume_for_vwap = 0.0
        for tick in tick_data_batch:
            price = tick.get('price')
            volume = tick.get('volume', 0.0)
            if price is not None and volume > 0:
                total_price_volume += price * volume
                total_volume_for_vwap += volume
        
        if total_volume_for_vwap == 0:
            return 0.0
            
        vwap = total_price_volume / total_volume_for_vwap

        buy_volume = 0.0
        sell_volume = 0.0
        total_volume = 0.0

        for tick in tick_data_batch:
            price = tick.get('price')
            volume = tick.get('volume', 0.0)
            
            if price is None:
                continue

            total_volume += volume

            if price > vwap:
                buy_volume += volume
            elif price < vwap:
                sell_volume += volume
            else:
                # Price is exactly VWAP, split the volume
                buy_volume += volume / 2
                sell_volume += volume / 2

        if total_volume == 0:
            return 0.0

        volume_imbalance = abs(buy_volume - sell_volume)
        vpin = (volume_imbalance / total_volume) * math.sqrt(len(tick_data_batch))

        return min(vpin, 1.0)

    async def execute_trade(self, vpin_signal: float, symbol: str):
        """
        Executes a trade if the VPIN signal crosses a threshold.
        """
        if vpin_signal > self.vpin_threshold:
            # Execute aggressive 30x leverage trade
            # This is a placeholder for the actual trade execution logic.
            # In a real implementation, you would use the exchange_client to place an order.
            print(f"VPIN signal {vpin_signal:.4f} crossed threshold for {symbol}. Executing 30x leverage trade.")

            # Post non-blocking message to RiskManager via Pub/Sub or queue
            position_details = {
                "symbol": symbol,
                "side": "BUY",  # Or SELL, depending on the strategy
                "notional": 1000, # Example notional
                "leverage": 30,
                "vpin_signal": vpin_signal,
                "source": "vpin-hft"
            }
            await self.risk_manager_queue.put(position_details)
            print(f"Sent position details to RiskManager for {symbol}.")
