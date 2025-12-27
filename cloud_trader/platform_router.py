"""Platform Router - Modular Multi-Chain Execution

Routes trades to the correct platform using the Adapter Pattern.
Enables adding new platforms without modifying core trading logic.

Design Principles:
1. Platform Abstraction: Each platform has a standardized adapter
2. Dependency Injection: Clients injected, not hardcoded
3. Composability: New platforms = new adapter class
4. Testability: Mock adapters for testing
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """Standardized trade result across all platforms."""

    success: bool
    order_id: Optional[str]
    filled_quantity: float
    avg_price: float
    platform: str
    metadata: Dict[str, Any]


class PlatformAdapter(ABC):
    """Abstract base class for platform-specific execution."""

    @abstractmethod
    async def execute_trade(self, symbol: str, side: str, quantity: float, **kwargs) -> TradeResult:
        """Execute a trade on this platform."""
        pass

    @abstractmethod
    async def get_balance(self) -> Dict[str, float]:
        """Get account balances."""
        pass


class SymphonyAdapter(PlatformAdapter):
    """Adapter for Symphony (Monad/Base) execution."""

    def __init__(self, symphony_client, agents_config):
        self.client = symphony_client
        self.agents = agents_config

    async def execute_trade(self, symbol: str, side: str, quantity: float, **kwargs) -> TradeResult:
        """
        Route to appropriate Symphony agent (MILF for swaps, Degen for perps).
        """
        try:
            # Determine if swap or perp
            is_swap = symbol in ["MON-USDC", "CHOG-USDC", "DAC-USDC"]

            # Clean symbol
            token = symbol.split("-")[0]

            if is_swap:
                # Use MILF for swaps
                agent_id = self.agents["MILF"]["id"]
                token_in = "USDC" if side == "BUY" else token
                token_out = token if side == "BUY" else "USDC"

                result = await self.client.execute_swap(
                    token_in=token_in,
                    token_out=token_out,
                    weight=5.0,  # 5% of balance
                    agent_id=agent_id,
                )
            else:
                # Use Degen for perps
                agent_id = self.agents["DEGEN"]["id"]
                action = "LONG" if side == "BUY" else "SHORT"

                result = await self.client.open_perpetual_position(
                    symbol=token, action=action, weight=5.0, leverage=2.0, agent_id=agent_id
                )

            # Standardize response
            if result and result.get("successful", 0) > 0:
                return TradeResult(
                    success=True,
                    order_id=result.get("batchId"),
                    filled_quantity=quantity,
                    avg_price=0.0,  # Symphony doesn't return fill price
                    platform="symphony",
                    metadata=result,
                )
            else:
                return TradeResult(
                    success=False,
                    order_id=None,
                    filled_quantity=0.0,
                    avg_price=0.0,
                    platform="symphony",
                    metadata=result or {},
                )

        except Exception as e:
            logger.error(f"Symphony execution error: {e}")
            return TradeResult(
                success=False,
                order_id=None,
                filled_quantity=0.0,
                avg_price=0.0,
                platform="symphony",
                metadata={"error": str(e)},
            )

    async def get_balance(self) -> Dict[str, float]:
        """Get Symphony balances."""
        # TODO: Implement when Symphony API supports it
        return {"USDC": 0.0}


class AsterAdapter(PlatformAdapter):
    """Adapter for Aster DEX execution."""

    def __init__(self, aster_client):
        self.client = aster_client

    async def execute_trade(self, symbol: str, side: str, quantity: float, **kwargs) -> TradeResult:
        """Execute market order on Aster."""
        try:
            from ..enums import OrderType

            order = await self.client.place_order(
                symbol=symbol, side=side, order_type=OrderType.MARKET, quantity=quantity
            )

            return TradeResult(
                success=True,
                order_id=order.get("orderId"),
                filled_quantity=float(order.get("executedQty", 0)),
                avg_price=float(order.get("avgPrice", 0)),
                platform="aster",
                metadata=order,
            )

        except Exception as e:
            logger.error(f"Aster execution error: {e}")
            return TradeResult(
                success=False,
                order_id=None,
                filled_quantity=0.0,
                avg_price=0.0,
                platform="aster",
                metadata={"error": str(e)},
            )

    async def get_balance(self) -> Dict[str, float]:
        """Get Aster balances."""
        try:
            info = await self.client.get_account_info_v2()
            balances = {}
            for asset in info:
                balances[asset["asset"]] = float(asset["balance"])
            return balances
        except:
            return {}


class PlatformRouter:
    """
    Routes trades to appropriate platform adapter.

    Design: Strategy Pattern + Dependency Injection
    - Adapters are injected at init
    - Router selects adapter based on symbol/platform hint
    - Easy to add new platforms by creating new adapter
    """

    def __init__(self, adapters: Dict[str, PlatformAdapter]):
        self.adapters = adapters

    async def execute(self, symbol: str, side: str, quantity: float, platform: str) -> TradeResult:
        """
        Execute trade on specified platform.

        Args:
            symbol: Trading pair (e.g., "BTC-USDC")
            side: "BUY" or "SELL"
            quantity: Amount to trade
            platform: "symphony" or "aster"

        Returns:
            TradeResult with execution details
        """
        adapter = self.adapters.get(platform)

        if not adapter:
            logger.error(f"No adapter found for platform: {platform}")
            return TradeResult(
                success=False,
                order_id=None,
                filled_quantity=0.0,
                avg_price=0.0,
                platform=platform,
                metadata={"error": f"Unknown platform: {platform}"},
            )

        logger.info(f"Routing {side} {quantity} {symbol} to {platform}")
        result = await adapter.execute_trade(symbol, side, quantity)

        if result.success:
            logger.info(f"✅ Trade executed on {platform}: {result.order_id}")
        else:
            logger.error(f"❌ Trade failed on {platform}: {result.metadata}")

        return result

    async def get_all_balances(self) -> Dict[str, Dict[str, float]]:
        """Get balances from all platforms."""
        balances = {}
        for platform_name, adapter in self.adapters.items():
            balances[platform_name] = await adapter.get_balance()
        return balances

    def add_platform(self, name: str, adapter: PlatformAdapter):
        """Add a new platform adapter dynamically."""
        self.adapters[name] = adapter
        logger.info(f"Added platform: {name}")
