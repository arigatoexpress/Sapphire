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

        # Check if we should participate in communication
        if not await self._should_participate_in_communication():
            logger.debug("Freqtrade skipping insight sharing due to participation threshold")
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
            # Query coordinator for recent global signals
            response = await self.mcp_client._client.get("/global-signals")
            if response.status_code == 200:
                signals_data = response.json()
                return self._analyze_global_signals(signals_data.get("signals", []))
            else:
                return []
        except Exception as e:
            logger.error(f"Failed to learn from global signals: {e}")
            return []

    async def get_role_guidance(self) -> Dict[str, Any]:
        """Get role guidance from portfolio orchestrator."""
        if not self.mcp_client:
            return {"guidance": "MCP not available"}

        try:
            response = await self.mcp_client._client.get(f"/agent/freqtrade-hft/guidance")
            if response.status_code == 200:
                return response.json()
            else:
                return {"guidance": "Guidance not available"}
        except Exception as e:
            logger.error(f"Failed to get role guidance: {e}")
            return {"guidance": "Error retrieving guidance"}

    async def validate_trade_intent(self, trade_details: Dict[str, Any]) -> bool:
        """Validate trade against portfolio constraints."""
        if not self.mcp_client:
            return True  # Allow trade if MCP unavailable

        try:
            response = await self.mcp_client._client.post(
                "/validate-trade/freqtrade-hft",
                json=trade_details
            )
            if response.status_code == 200:
                result = response.json()
                return result.get("trade_valid", True)
            else:
                return True  # Allow trade if validation fails
        except Exception as e:
            logger.error(f"Failed to validate trade: {e}")
            return True  # Allow trade on error

    def _analyze_global_signals(self, signals: list) -> list:
        """Analyze global signals for Freqtrade insights."""
        insights = []

        if not signals:
            return insights

        # Group by symbol
        symbol_signals = {}
        for signal in signals:
            symbol = signal.get("symbol", "unknown")
            if symbol not in symbol_signals:
                symbol_signals[symbol] = []
            symbol_signals[symbol].append(signal)

        # Analyze each symbol
        for symbol, sym_signals in symbol_signals.items():
            # Look for consensus patterns
            buy_signals = [s for s in sym_signals if s.get("side") == "buy"]
            sell_signals = [s for s in sym_signals if s.get("side") == "sell"]

            total_signals = len(sym_signals)
            buy_ratio = len(buy_signals) / total_signals if total_signals > 0 else 0

            if buy_ratio > 0.7:
                insights.append(f"Strong bullish consensus on {symbol} ({buy_ratio:.1%})")
            elif buy_ratio < 0.3:
                insights.append(f"Strong bearish consensus on {symbol} ({1-buy_ratio:.1%})")
            else:
                insights.append(f"Mixed signals on {symbol}, monitor closely")

            # Check for high conviction signals
            high_conf_signals = [s for s in sym_signals if s.get("confidence", 0) > 0.8]
            if high_conf_signals:
                insights.append(f"High conviction signals detected on {symbol}")

        return insights

    async def _should_participate_in_communication(self) -> bool:
        """Check if Freqtrade should participate in communication based on activity levels."""
        if not self.mcp_client:
            return False

        try:
            # Check with coordinator if we should participate
            response = await self.mcp_client._client.get("/agent/freqtrade-hft/participation-check")
            if response.status_code == 200:
                result = response.json()
                return result.get("should_participate", True)
            else:
                return True  # Default to participating if check fails
        except Exception as e:
            logger.debug(f"Participation check failed, defaulting to participate: {e}")
            return True

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
