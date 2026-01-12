"""
Executor Agent - Platform-Specific Trade Execution with Cognitive Reasoning

This module provides ExecutorAgent classes that wrap existing platform bots
(Drift, Aster, Hyperliquid) with cognitive mesh integration.

Each executor:
- Receives consensus decisions from the mesh
- Validates execution feasibility
- Executes trades on the platform
- Reports results with reasoning back to the mesh
"""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from .cognitive_agent import CognitiveAgent, MarketContext
from .cognitive_mesh import (
    AgentRole,
    CognitiveMesh,
    CognitiveMessage,
    MessageType,
    get_cognitive_mesh,
)

logger = logging.getLogger(__name__)


@dataclass
class ExecutionRequest:
    """Request to execute a trade on a specific platform."""

    symbol: str
    side: str  # BUY, SELL, LONG, SHORT
    quantity: float
    order_type: str = "MARKET"  # MARKET, LIMIT
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

    # Cognitive context
    consensus_id: Optional[str] = None
    reasoning: Optional[str] = None


@dataclass
class ExecutionReport:
    """Report of execution result."""

    success: bool
    trade_id: Optional[str] = None
    filled_quantity: float = 0.0
    avg_price: float = 0.0
    platform: str = ""
    execution_time_ms: float = 0.0
    error_message: Optional[str] = None

    # Cognitive reflection
    reflection: Optional[str] = None


class ExecutorAgent(CognitiveAgent, ABC):
    """
    Base class for platform-specific executor agents.

    Executors are the "legs" of the swarm - they receive consensus decisions
    and execute trades on their respective platforms.
    """

    def __init__(
        self,
        agent_id: str,
        platform: str,
        model_name: str = "gemini-2.0-flash",
    ):
        super().__init__(agent_id, AgentRole.EXECUTOR, model_name)
        self.platform = platform
        self.execution_count = 0
        self.success_count = 0

    def get_capabilities(self) -> List[str]:
        return [
            f"execute_{self.platform}",
            "order_placement",
            "position_management",
        ]

    def get_system_prompt(self) -> str:
        return f"""You are EXECUTOR-{self.platform.upper()}, a trade execution specialist.

Your role is to:
1. Validate execution requests before placing orders
2. Report execution results with relevant context
3. Identify any issues that might affect trade quality

You speak concisely about execution details:
- Fill quality (slippage, partial fills)
- Platform conditions (funding rate, liquidity)
- Risk factors specific to {self.platform}

Format your execution report as:
STATUS: [SUCCESS/FAILED/PARTIAL]
FILL_ANALYSIS: [Quality of execution]
PLATFORM_CONDITIONS: [Any relevant state]
RECOMMENDATION: [Post-trade suggestion]"""

    async def analyze(self, context: MarketContext) -> CognitiveMessage:
        """Executor's analysis focuses on execution feasibility."""
        prompt = f"""Analyze execution feasibility for {context.symbol} on {self.platform}:

{context.to_prompt()}

Focus on liquidity, slippage risk, and platform-specific factors."""

        reasoning = await self.reason(prompt)

        return await self.broadcast(
            message_type=MessageType.VALIDATION,
            reasoning=reasoning,
            symbol=context.symbol,
            confidence=0.8,  # Executors typically have high confidence on feasibility
        )

    @abstractmethod
    async def execute(self, request: ExecutionRequest) -> ExecutionReport:
        """Execute a trade on the platform. Implemented by subclasses."""
        pass

    async def execute_with_reasoning(
        self,
        request: ExecutionRequest,
    ) -> ExecutionReport:
        """
        Execute a trade and generate cognitive reflection on the result.

        This is the main entry point for cognitive execution.
        """
        # Pre-execution reasoning
        pre_prompt = f"""You are about to execute: {request.side} {request.quantity} {request.symbol}
Consensus reasoning: {request.reasoning or 'No reasoning provided'}

Any concerns before execution?"""

        pre_analysis = await self.reason(pre_prompt, max_tokens=128)

        # Execute
        start_time = datetime.now()
        report = await self.execute(request)
        report.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000

        self.execution_count += 1
        if report.success:
            self.success_count += 1

        # Post-execution reflection
        post_prompt = f"""Trade executed:
- Symbol: {request.symbol}
- Side: {request.side}
- Quantity: {request.quantity}
- Result: {"SUCCESS" if report.success else "FAILED"}
- Fill Price: {report.avg_price}
- Execution Time: {report.execution_time_ms:.0f}ms
{"- Error: " + report.error_message if report.error_message else ""}

Reflect on this execution and provide recommendations."""

        report.reflection = await self.reason(post_prompt, max_tokens=256)

        # Broadcast result to mesh
        await self.broadcast(
            message_type=MessageType.EXECUTION,
            reasoning=report.reflection,
            symbol=request.symbol,
            suggested_action="FILLED" if report.success else "FAILED",
            confidence=1.0 if report.success else 0.0,
            metadata={
                "trade_id": report.trade_id,
                "avg_price": report.avg_price,
                "filled_quantity": report.filled_quantity,
                "consensus_id": request.consensus_id,
            },
        )

        return report


class AsterExecutorAgent(ExecutorAgent):
    """
    Executor agent for Aster DEX.

    Wraps the existing AsterBot to provide cognitive execution.
    """

    def __init__(self, agent_id: str = "aster-executor"):
        super().__init__(agent_id, "aster")
        self.aster_client = None

    async def initialize_client(self):
        """Initialize the Aster client."""
        try:
            from aster_client import AsterClient

            api_key = os.getenv("ASTER_API_KEY")
            api_secret = os.getenv("ASTER_API_SECRET")
            passphrase = os.getenv("ASTER_PASSPHRASE")

            if not api_key or not api_secret:
                logger.warning("Aster credentials not configured")
                return False

            self.aster_client = AsterClient(
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase,
            )
            await self.aster_client.initialize()
            logger.info("🌟 Aster Executor initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Aster client: {e}")
            return False

    async def execute(self, request: ExecutionRequest) -> ExecutionReport:
        """Execute trade on Aster."""
        if not self.aster_client:
            return ExecutionReport(
                success=False,
                platform="aster",
                error_message="Aster client not initialized",
            )

        try:
            # Prepare order params
            side = "BUY" if request.side.upper() in ["BUY", "LONG"] else "SELL"

            # Place market order
            result = await self.aster_client.place_order(
                symbol=request.symbol,
                side=side,
                quantity=request.quantity,
                order_type=request.order_type,
                price=request.limit_price,
            )

            return ExecutionReport(
                success=True,
                trade_id=result.get("order_id"),
                filled_quantity=float(result.get("filled_qty", request.quantity)),
                avg_price=float(result.get("avg_price", 0)),
                platform="aster",
            )

        except Exception as e:
            logger.error(f"Aster execution failed: {e}")
            return ExecutionReport(
                success=False,
                platform="aster",
                error_message=str(e),
            )


class DriftExecutorAgent(ExecutorAgent):
    """
    Executor agent for Drift Protocol (Solana).

    Wraps the existing DriftBot for cognitive execution.
    """

    def __init__(self, agent_id: str = "drift-executor"):
        super().__init__(agent_id, "drift")
        self.drift_client = None

    async def initialize_client(self):
        """Initialize the Drift SDK client."""
        try:
            from driftpy.account_subscription_config import AccountSubscriptionConfig
            from driftpy.drift_client import DriftClient
            from solana.rpc.async_api import AsyncClient
            from solders.keypair import Keypair

            rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
            private_key = os.getenv("SOLANA_PRIVATE_KEY")

            if not private_key:
                logger.warning("Solana private key not configured")
                return False

            connection = AsyncClient(rpc_url)

            if "[" in private_key:
                import json

                raw_key = json.loads(private_key)
                keypair = Keypair.from_bytes(bytes(raw_key))
            else:
                keypair = Keypair.from_base58_string(private_key)

            self.drift_client = DriftClient(
                connection,
                keypair,
                env="mainnet",
                account_subscription=AccountSubscriptionConfig("websocket"),
            )
            await self.drift_client.subscribe()

            logger.info("🌀 Drift Executor initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Drift client: {e}")
            return False

    async def execute(self, request: ExecutionRequest) -> ExecutionReport:
        """Execute trade on Drift."""
        if not self.drift_client:
            return ExecutionReport(
                success=False,
                platform="drift",
                error_message="Drift client not initialized",
            )

        try:
            from driftpy.types import MarketType, OrderParams, OrderType, PositionDirection

            # Symbol to market index mapping
            symbol_map = {"SOL": 0, "BTC": 1, "ETH": 2, "JUP": 8}
            market_index = symbol_map.get(request.symbol.replace("-PERP", "").upper())

            if market_index is None:
                return ExecutionReport(
                    success=False,
                    platform="drift",
                    error_message=f"Unknown market: {request.symbol}",
                )

            direction = (
                PositionDirection.Long()
                if request.side.upper() in ["BUY", "LONG"]
                else PositionDirection.Short()
            )

            order_params = OrderParams(
                order_type=OrderType.Market(),
                market_type=MarketType.Perp(),
                market_index=market_index,
                base_asset_amount=int(request.quantity * 1e9),
                direction=direction,
            )

            tx_sig = await self.drift_client.place_perp_order(order_params)

            # Wait for confirmation (Solana is fast)
            # Note: In production, this would use confirm_transaction

            return ExecutionReport(
                success=True,
                trade_id=str(tx_sig),
                filled_quantity=request.quantity,
                avg_price=0.0,  # Would need oracle price
                platform="drift",
            )

        except Exception as e:
            logger.error(f"Drift execution failed: {e}")
            return ExecutionReport(
                success=False,
                platform="drift",
                error_message=str(e),
            )


class HyperliquidExecutorAgent(ExecutorAgent):
    """
    Executor agent for Hyperliquid.

    Wraps the existing HyperliquidClient for cognitive execution.
    """

    def __init__(self, agent_id: str = "hl-executor"):
        super().__init__(agent_id, "hyperliquid")
        self.hl_client = None

    async def initialize_client(self):
        """Initialize the Hyperliquid client."""
        try:
            from hyperliquid.api import API

            private_key = os.getenv("HYPERLIQUID_PRIVATE_KEY")

            if not private_key:
                logger.warning("Hyperliquid private key not configured")
                return False

            self.hl_client = API(private_key, testnet=False)
            logger.info("⚡ Hyperliquid Executor initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Hyperliquid client: {e}")
            return False

    async def execute(self, request: ExecutionRequest) -> ExecutionReport:
        """Execute trade on Hyperliquid."""
        if not self.hl_client:
            return ExecutionReport(
                success=False,
                platform="hyperliquid",
                error_message="Hyperliquid client not initialized",
            )

        try:
            is_buy = request.side.upper() in ["BUY", "LONG"]

            # Place market order
            result = await asyncio.to_thread(
                self.hl_client.order,
                request.symbol,
                is_buy,
                request.quantity,
                request.limit_price or 0,
                {"limit": {"tif": "Ioc"}} if not request.limit_price else None,
            )

            status = result.get("status", {})

            if status.get("filled", {}).get("totalSz", 0) > 0:
                return ExecutionReport(
                    success=True,
                    trade_id=str(
                        result.get("response", {})
                        .get("data", {})
                        .get("statuses", [{}])[0]
                        .get("resting", {})
                        .get("oid")
                    ),
                    filled_quantity=float(status.get("filled", {}).get("totalSz", 0)),
                    avg_price=float(status.get("filled", {}).get("avgPx", 0)),
                    platform="hyperliquid",
                )
            else:
                return ExecutionReport(
                    success=False,
                    platform="hyperliquid",
                    error_message="Order not filled",
                )

        except Exception as e:
            logger.error(f"Hyperliquid execution failed: {e}")
            return ExecutionReport(
                success=False,
                platform="hyperliquid",
                error_message=str(e),
            )


# Factory function to create all executor agents
async def create_executor_swarm() -> Dict[str, ExecutorAgent]:
    """Create and initialize all executor agents."""
    executors = {
        "aster": AsterExecutorAgent(),
        "drift": DriftExecutorAgent(),
        "hyperliquid": HyperliquidExecutorAgent(),
    }

    mesh = get_cognitive_mesh()

    for name, executor in executors.items():
        await executor.connect(mesh)
        success = await executor.initialize_client()
        if success:
            logger.info(f"✅ {name.upper()} executor ready")
        else:
            logger.warning(f"⚠️ {name.upper()} executor offline (credentials missing)")

    return executors
