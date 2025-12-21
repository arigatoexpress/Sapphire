"""
Symphony Mock Client for Testing Activation Flow.
This simulates the Symphony API until the real API is available.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SymphonyMockClient:
    """
    Mock Symphony client for testing the MIT activation flow.
    Simulates real Symphony behavior with local state tracking.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("SYMPHONY_API_KEY")

        # Mock state (in production this would be Symphony's database)
        self._trades_count = 0
        self._activated = False
        self._balance = 250.0  # User's funded amount
        self._positions = []

    async def close(self):
        """Close the HTTP client."""
        pass

    async def get_account_info(self) -> Dict[str, Any]:
        """Get Symphony smart account information (MOCK)."""
        return {
            "address": "0xMOCK1234567890abcdef",
            "balance": {"USDC": self._balance},
            "is_activated": self._activated,
            "trades_count": self._trades_count,
            "activation_threshold": 5,
            "name": "Sapphire MIT Agent",
        }

    async def get_balance(self) -> Dict[str, float]:
        """Get account balance (MOCK)."""
        return {"USDC": self._balance}

    async def open_perpetual_position(
        self,
        symbol: str,
        side: str,
        size: float,
        leverage: int = 1,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Open a perpetual futures position (MOCK)."""

        # Increment trade count
        self._trades_count += 1

        # Check activation
        if self._trades_count >= 5:
            self._activated = True
            logger.info("🎉 MIT Fund Activated! 5 trades completed.")

        # Mock position
        position = {
            "position_id": f"mock_pos_{int(time.time())}_{self._trades_count}",
            "symbol": symbol,
            "side": side,
            "entry_price": 42000.0 if "BTC" in symbol else 2500.0,
            "size": size,
            "leverage": leverage,
            "status": "open",
            "timestamp": time.time(),
        }

        self._positions.append(position)

        logger.info(
            f"✅ Mock Perpetual Opened: {symbol} {side} ${size} @{leverage}x "
            f"(Trade {self._trades_count}/5)"
        )

        return position

    async def execute_spot_trade(
        self, symbol: str, side: str, quantity: float, order_type: str = "market"
    ) -> Dict[str, Any]:
        """Execute a spot trade (MOCK)."""

        # Increment trade count
        self._trades_count += 1

        # Check activation
        if self._trades_count >= 5:
            self._activated = True
            logger.info("🎉 MIT Fund Activated! 5 trades completed.")

        # Mock order
        order = {
            "order_id": f"mock_order_{int(time.time())}_{self._trades_count}",
            "symbol": symbol,
            "side": side,
            "executed_price": 42000.0 if "BTC" in symbol else 2500.0,
            "quantity": quantity,
            "order_type": order_type,
            "status": "filled",
            "timestamp": time.time(),
        }

        logger.info(
            f"✅ Mock Spot Trade: {side} {quantity} {symbol} " f"(Trade {self._trades_count}/5)"
        )

        return order

    async def get_perpetual_positions(self) -> List[Dict[str, Any]]:
        """Get all open perpetual positions (MOCK)."""
        return self._positions

    async def close_perpetual_position(self, position_id: str) -> Dict[str, Any]:
        """Close a perpetual position (MOCK)."""
        # Remove from positions
        self._positions = [p for p in self._positions if p["position_id"] != position_id]

        return {
            "position_id": position_id,
            "status": "closed",
            "pnl": 5.50,  # Mock profit
            "timestamp": time.time(),
        }

    @property
    def is_activated(self) -> bool:
        """Check if the agentic fund is activated."""
        return self._activated or self._trades_count >= 5

    @property
    def activation_progress(self) -> Dict[str, Any]:
        """Get activation progress."""
        current = min(self._trades_count, 5)
        return {
            "current": current,
            "required": 5,
            "percentage": (current / 5.0) * 100,
            "activated": self.is_activated,
        }


# Global singleton for session persistence
_mock_client: Optional[SymphonyMockClient] = None


def get_symphony_mock_client(api_key: Optional[str] = None) -> SymphonyMockClient:
    """Get or create mock Symphony client singleton."""
    global _mock_client
    if _mock_client is None:
        _mock_client = SymphonyMockClient(api_key=api_key)
    return _mock_client
