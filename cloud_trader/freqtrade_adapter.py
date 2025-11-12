"""Freqtrade MCP Adapter

Integrates Freqtrade with the MCP coordinator for unified autonomous trading.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Optional

from .config import get_settings
from .mcp import (
    MCPClient,
    MCPHFTSignalPayload,
    MCPMarketDataPayload,
    MCPOrderExecutionPayload,
    MCRiskUpdatePayload,
    MCPStrategyAdjustmentPayload,
    MCPMessageType,
)
from .pubsub import PubSubClient

logger = logging.getLogger(__name__)


class FreqtradeMCPAdapter:
    """Adapter for Freqtrade to communicate with MCP coordinator."""

    def __init__(self):
        self.settings = get_settings()
        self.mcp_client: Optional[MCPClient] = None
        self.pubsub_client: Optional[PubSubClient] = None
        self.component_id = "freqtrade-hft-bot"
        self._running = False

    async def start(self):
        """Initialize the adapter."""
        # Initialize MCP client
        if self.settings.mcp_url:
            self.mcp_client = MCPClient(
                base_url=self.settings.mcp_url,
                session_id=self.settings.mcp_session_id,
            )
            await self.mcp_client.ensure_session()

        # Initialize Pub/Sub client
        if self.settings.gcp_project_id:
            self.pubsub_client = PubSubClient(self.settings)
            await self.pubsub_client.connect()

        # Register with MCP coordinator
        await self._register_with_coordinator()

        self._running = True
        logger.info("Freqtrade MCP adapter started")

    async def stop(self):
        """Shutdown the adapter."""
        self._running = False
        if self.mcp_client:
            await self.mcp_client.close()
        if self.pubsub_client:
            await self.pubsub_client.close()

    async def _register_with_coordinator(self):
        """Register this component with the MCP coordinator."""
        if not self.mcp_client:
            return

        try:
            await self.mcp_client.publish({
                "message_type": "register",
                "component_id": self.component_id,
                "component_type": "freqtrade",
                "capabilities": ["signal_generation", "order_execution", "risk_management"],
            })
        except Exception as e:
            logger.error(f"Failed to register with MCP coordinator: {e}")

    async def publish_signal(self, signal: Dict[str, Any]):
        """Publish a trading signal to the MCP coordinator."""
        if not self.mcp_client:
            return

        try:
            payload = MCPHFTSignalPayload(
                symbol=signal["symbol"],
                side=signal["side"],
                confidence=signal.get("confidence", 0.5),
                notional=signal.get("notional", 0.0),
                price=signal.get("price"),
                rationale=signal.get("rationale", ""),
                source="freqtrade",
                strategy=signal.get("strategy", "default"),
                indicators=signal.get("indicators"),
            )

            await self.mcp_client.publish({
                "message_type": MCPMessageType.HFT_SIGNAL,
                "payload": payload.model_dump(),
                "timestamp": asyncio.get_event_loop().time(),
            })

            # Also publish via Pub/Sub for broader distribution
            if self.pubsub_client:
                await self.pubsub_client.publish_hft_signal({
                    "component": "freqtrade",
                    "signal": payload.model_dump(),
                })

        except Exception as e:
            logger.error(f"Failed to publish signal: {e}")

    async def publish_market_data(self, data: Dict[str, Any]):
        """Publish market data update."""
        if not self.mcp_client:
            return

        try:
            payload = MCPMarketDataPayload(
                symbol=data["symbol"],
                price=data["price"],
                volume=data["volume"],
                bid_price=data.get("bid_price"),
                ask_price=data.get("ask_price"),
                timestamp=data.get("timestamp", str(asyncio.get_event_loop().time())),
                source="freqtrade",
            )

            await self.mcp_client.publish({
                "message_type": MCPMessageType.MARKET_DATA,
                "payload": payload.model_dump(),
            })

        except Exception as e:
            logger.error(f"Failed to publish market data: {e}")

    async def publish_order_execution(self, execution: Dict[str, Any]):
        """Publish order execution notification."""
        if not self.mcp_client:
            return

        try:
            payload = MCPOrderExecutionPayload(
                symbol=execution["symbol"],
                side=execution["side"],
                quantity=execution["quantity"],
                price=execution["price"],
                order_id=execution["order_id"],
                timestamp=execution.get("timestamp", str(asyncio.get_event_loop().time())),
                status=execution.get("status", "filled"),
                source="freqtrade",
                fees=execution.get("fees"),
            )

            await self.mcp_client.publish({
                "message_type": MCPMessageType.ORDER_EXECUTION,
                "payload": payload.model_dump(),
            })

            # Also publish via Pub/Sub
            if self.pubsub_client:
                await self.pubsub_client.publish_order_execution({
                    "component": "freqtrade",
                    "execution": payload.model_dump(),
                })

        except Exception as e:
            logger.error(f"Failed to publish order execution: {e}")

    async def publish_risk_update(self, risk_data: Dict[str, Any]):
        """Publish risk management update."""
        if not self.mcp_client:
            return

        try:
            payload = MCRiskUpdatePayload(
                symbol=risk_data.get("symbol"),
                portfolio_risk=risk_data["portfolio_risk"],
                position_risk=risk_data.get("position_risk"),
                drawdown=risk_data["drawdown"],
                leverage=risk_data["leverage"],
                alerts=risk_data.get("alerts"),
                timestamp=risk_data.get("timestamp", str(asyncio.get_event_loop().time())),
            )

            await self.mcp_client.publish({
                "message_type": MCPMessageType.RISK_UPDATE,
                "payload": payload.model_dump(),
            })

        except Exception as e:
            logger.error(f"Failed to publish risk update: {e}")

    async def publish_strategy_adjustment(self, adjustment: Dict[str, Any]):
        """Publish strategy parameter adjustment."""
        if not self.mcp_client:
            return

        try:
            payload = MCPStrategyAdjustmentPayload(
                strategy_name=adjustment["strategy_name"],
                parameter=adjustment["parameter"],
                old_value=adjustment["old_value"],
                new_value=adjustment["new_value"],
                reason=adjustment["reason"],
                source="freqtrade",
                timestamp=adjustment.get("timestamp", str(asyncio.get_event_loop().time())),
            )

            await self.mcp_client.publish({
                "message_type": MCPMessageType.STRATEGY_ADJUSTMENT,
                "payload": payload.model_dump(),
            })

        except Exception as e:
            logger.error(f"Failed to publish strategy adjustment: {e}")

    async def consume_collaboration_signals(self) -> list:
        """Consume collaboration signals and discussions from other agents."""
        if not self.mcp_client:
            return []

        try:
            # Check for discussion invitations and agent communications
            discussions = await self._check_pending_discussions()
            questions = await self._check_pending_questions()
            insights = await self._check_pending_insights()

            return {
                "discussions": discussions,
                "questions": questions,
                "insights": insights
            }
        except Exception as e:
            logger.error(f"Failed to consume collaboration signals: {e}")
            return {"discussions": [], "questions": [], "insights": []}

    async def ask_agent_question(self, target_agent: str, question: str, context: Dict[str, Any] = None):
        """Ask a question to another agent."""
        if not self.mcp_client:
            return

        try:
            question_payload = {
                "asking_agent": "freqtrade",
                "target_agent": target_agent,
                "question": question,
                "context": context or {},
                "timestamp": asyncio.get_event_loop().time()
            }

            # Ask via MCP coordinator
            response = await self.mcp_client.publish({
                "message_type": "ask_question",
                "question": question_payload
            })

            logger.info(f"Freqtrade asked {target_agent}: {question}")
            return response

        except Exception as e:
            logger.error(f"Failed to ask question: {e}")

    async def share_strategy_insight(self, symbol: str, insight: str, confidence: float = None):
        """Share a trading insight with other agents."""
        if not self.mcp_client:
            return

        try:
            insight_payload = {
                "agent": "freqtrade",
                "symbol": symbol,
                "insight": insight,
                "confidence": confidence,
                "strategy_type": "technical_analysis",
                "timestamp": asyncio.get_event_loop().time()
            }

            await self.mcp_client.publish({
                "message_type": "share_insight",
                "insight": insight_payload
            })

            logger.info(f"Freqtrade shared insight about {symbol}: {insight}")

        except Exception as e:
            logger.error(f"Failed to share insight: {e}")

    async def share_trade_thesis(self, symbol: str, thesis: str, entry_point: float = None,
                                take_profit: float = None, stop_loss: float = None,
                                risk_reward_ratio: float = None, timeframe: str = "5m",
                                conviction_level: str = "medium"):
        """Share detailed trade thesis with all agents."""
        if not self.mcp_client:
            return

        try:
            thesis_payload = {
                "agent": "freqtrade",
                "symbol": symbol,
                "thesis": thesis,
                "entry_point": entry_point,
                "take_profit": take_profit,
                "stop_loss": stop_loss,
                "risk_reward_ratio": risk_reward_ratio,
                "timeframe": timeframe,
                "conviction_level": conviction_level,
                "market_context": {
                    "strategy": "technical_analysis",
                    "indicators_used": ["rsi", "bbands", "atr", "volume"],
                    "market_regime": "volatile"
                },
                "timestamp": asyncio.get_event_loop().time()
            }

            await self.mcp_client.publish({
                "message_type": "share_thesis",
                "thesis": thesis_payload
            })

            logger.info(f"Freqtrade shared thesis about {symbol}: {thesis[:100]}...")

        except Exception as e:
            logger.error(f"Failed to share thesis: {e}")

    async def engage_strategy_discussion(self, topic: str, content: str,
                                        target_agent: str = None, discussion_type: str = "question"):
        """Engage in strategy discussion with other agents."""
        if not self.mcp_client:
            return

        try:
            discussion_payload = {
                "from_agent": "freqtrade",
                "to_agent": target_agent,
                "topic": topic,
                "content": content,
                "context": {
                    "expertise": "technical_analysis",
                    "timeframes": ["5m", "15m", "1h"],
                    "strategies": ["mean_reversion", "momentum", "breakout"]
                },
                "discussion_type": discussion_type,
                "timestamp": asyncio.get_event_loop().time()
            }

            await self.mcp_client.publish({
                "message_type": "strategy_discussion",
                "discussion": discussion_payload
            })

            logger.info(f"Freqtrade started discussion: {topic}")

        except Exception as e:
            logger.error(f"Failed to engage in discussion: {e}")

    async def learn_from_global_signals(self) -> list:
        """Learn from global signals shared by all agents."""
        if not self.mcp_client:
            return []

        try:
            # This would query the coordinator for recent global signals
            # For now, return insights that can be learned
            return [
                "Global signal analysis: Multiple agents showing BTC momentum",
                "Cross-asset correlation: ETH following BTC pattern",
                "Risk aggregation: High conviction across multiple agents on BTC"
            ]
        except Exception as e:
            logger.error(f"Failed to learn from global signals: {e}")
            return []

    async def _check_pending_discussions(self) -> list:
        """Check for pending discussion invitations."""
        # This would poll the coordinator for discussions
        # For now, return empty list
        return []

    async def _check_pending_questions(self) -> list:
        """Check for questions directed at Freqtrade."""
        # This would poll the coordinator for questions
        # For now, return empty list
        return []

    async def _check_pending_insights(self) -> list:
        """Check for insights shared by other agents."""
        # This would poll the coordinator for insights
        # For now, return empty list
        return []

    async def health_check(self) -> Dict[str, Any]:
        """Perform health check."""
        return {
            "component": "freqtrade",
            "status": "healthy" if self._running else "stopped",
            "mcp_connected": self.mcp_client is not None,
            "pubsub_connected": self.pubsub_client is not None and self.pubsub_client.is_connected(),
        }


# Global adapter instance
_freqtrade_adapter: Optional[FreqtradeMCPAdapter] = None


def get_freqtrade_adapter() -> FreqtradeMCPAdapter:
    """Get or create global Freqtrade adapter instance."""
    global _freqtrade_adapter
    if _freqtrade_adapter is None:
        _freqtrade_adapter = FreqtradeMCPAdapter()
    return _freqtrade_adapter
