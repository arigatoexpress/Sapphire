from __future__ import annotations

import asyncio
import json
import logging
from enum import Enum
from typing import Any, Dict, Optional

import httpx
from httpx import HTTPStatusError
from pydantic import BaseModel, Field


class MCPMessageType(str, Enum):
    OBSERVATION = "observation"
    PROPOSAL = "proposal"
    CRITIQUE = "critique"
    QUERY = "query"
    RESPONSE = "response"
    CONSENSUS = "consensus"
    EXECUTION = "execution"
    HEARTBEAT = "heartbeat"
    # HFT-specific message types
    HFT_SIGNAL = "hft_signal"
    MARKET_DATA = "market_data"
    ORDER_EXECUTION = "order_execution"
    RISK_UPDATE = "risk_update"
    STRATEGY_ADJUSTMENT = "strategy_adjustment"


class MCPProposalPayload(BaseModel):
    symbol: str
    side: str
    notional: float
    confidence: float
    rationale: str
    constraints: list[str] = Field(default_factory=list)


class MCPResponsePayload(BaseModel):
    reference_id: str
    answer: str
    confidence: float
    supplementary: Optional[Dict[str, Any]] = None


class MCPHFTSignalPayload(BaseModel):
    """HFT trading signal from Freqtrade or Hummingbot."""
    symbol: str
    side: str  # "buy", "sell", "hold"
    confidence: float
    notional: float
    price: Optional[float] = None
    rationale: str
    source: str  # "freqtrade", "hummingbot"
    strategy: str
    indicators: Optional[Dict[str, Any]] = None


class MCPMarketDataPayload(BaseModel):
    """Real-time market data updates."""
    symbol: str
    price: float
    volume: float
    bid_price: Optional[float] = None
    ask_price: Optional[float] = None
    timestamp: str
    source: str


class MCPOrderExecutionPayload(BaseModel):
    """Order execution notifications."""
    symbol: str
    side: str
    quantity: float
    price: float
    order_id: str
    timestamp: str
    status: str  # "filled", "partial", "cancelled"
    source: str  # "freqtrade", "hummingbot"
    fees: Optional[float] = None


class MCRiskUpdatePayload(BaseModel):
    """Risk management updates."""
    symbol: Optional[str] = None
    portfolio_risk: float
    position_risk: Optional[Dict[str, float]] = None
    drawdown: float
    leverage: float
    alerts: Optional[List[str]] = None
    timestamp: str


class MCPStrategyAdjustmentPayload(BaseModel):
    """Strategy parameter adjustments."""
    strategy_name: str
    parameter: str
    old_value: Any
    new_value: Any
    reason: str
    source: str  # "freqtrade", "hummingbot", "coordinator"
    timestamp: str


logger = logging.getLogger(__name__)


class MCPClient:
    def __init__(self, base_url: str, session_id: str | None = None, *, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._session_id = session_id
        self._client = httpx.AsyncClient(timeout=timeout)
        self._lock = asyncio.Lock()

        # Vertex AI integration
        self._vertex_enabled = False
        self._vertex_client = None
        try:
            from .vertex_ai_client import get_vertex_client
            self._vertex_client = get_vertex_client()
            self._vertex_enabled = True
            logger.info("MCP integrated with Vertex AI client")
        except Exception as exc:
            logger.warning(f"Vertex AI integration failed: {exc}")
            self._vertex_enabled = False

    @property
    def session_id(self) -> Optional[str]:
        return self._session_id

    async def _session_exists(self, session_id: str) -> bool:
        try:
            resp = await self._client.get(f"{self._base_url}/sessions")
            resp.raise_for_status()
            data = resp.json()
            sessions = data.get("sessions", [])
            if isinstance(sessions, dict):
                sessions = list(sessions.keys())
            return isinstance(sessions, list) and session_id in sessions
        except Exception:
            return False

    async def ensure_session(self, *, force_refresh: bool = False) -> str:
        async with self._lock:
            if self._session_id and not force_refresh:
                exists = await self._session_exists(self._session_id)
                if exists:
                    return self._session_id
                logger.warning(
                    "Configured MCP session '%s' missing; obtaining a new session",
                    self._session_id,
                )
                self._session_id = None

        logger.info("Obtaining new MCP session")
        resp = await self._client.post(f"{self._base_url}/sessions", json={})
        resp.raise_for_status()
        data = resp.json()
        new_session = data.get("session_id")
        if not new_session:
            raise RuntimeError("MCP session creation did not return a session_id")
        self._session_id = new_session
        logger.info("Acquired MCP session %s", self._session_id)
        return self._session_id

    async def publish(self, message: Dict[str, Any]) -> None:
        """Publish MCP message and track metrics."""
        try:
            from .metrics import MCP_MESSAGES_TOTAL

            message_type = message.get("message_type", "unknown")
            MCP_MESSAGES_TOTAL.labels(message_type=message_type, direction="outbound").inc()
        except Exception:
            pass  # Metrics not critical

        session_id = await self.ensure_session()
        if not message.get("session_id"):
            message = {**message, "session_id": session_id}

        payload = json.dumps(message)
        try:
            resp = await self._client.post(
                f"{self._base_url}/sessions/{session_id}/messages",
                content=payload,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
        except HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.warning("MCP session %s missing; refreshing session", session_id)
                async with self._lock:
                    self._session_id = None
                session_id = await self.ensure_session(force_refresh=True)
                refreshed_payload = json.dumps({**message, "session_id": session_id})
                resp = await self._client.post(
                    f"{self._base_url}/sessions/{session_id}/messages",
                    content=refreshed_payload,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                return
            raise

    async def query_vertex_agent(
        self,
        agent_id: str,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Query a Vertex AI agent through MCP."""
        if not self._vertex_enabled or not self._vertex_client:
            raise RuntimeError("Vertex AI integration not available")

        try:
            # Build comprehensive query with context
            enhanced_query = self._enhance_query_with_context(query, context or {})

            # Query the Vertex AI agent
            response = await self._vertex_client.predict_with_fallback(agent_id, enhanced_query, **kwargs)

            # Publish MCP message about the query
            await self._publish_agent_query(agent_id, query, context, response)

            return response

        except Exception as exc:
            logger.error(f"Vertex AI agent query failed for {agent_id}: {exc}")

            # Publish error message
            await self._publish_agent_error(agent_id, query, str(exc))

            raise

    def _enhance_query_with_context(self, query: str, context: Dict[str, Any]) -> str:
        """Enhance query with additional context for better agent responses."""
        context_parts = []

        if "symbol" in context:
            context_parts.append(f"Symbol: {context['symbol']}")
        if "side" in context:
            context_parts.append(f"Direction: {context['side']}")
        if "price" in context:
            context_parts.append(f"Price: ${context['price']:.4f}")
        if "market_data" in context:
            market = context["market_data"]
            if isinstance(market, dict):
                if "change_24h" in market:
                    context_parts.append(f"24h Change: {market['change_24h']:.2f}%")
                if "volume" in market:
                    context_parts.append(f"Volume: {market['volume']:,.0f}")

        context_str = " | ".join(context_parts)
        if context_str:
            return f"{query}\n\nContext: {context_str}"
        return query

    async def _publish_agent_query(
        self,
        agent_id: str,
        query: str,
        context: Optional[Dict[str, Any]],
        response: Dict[str, Any]
    ) -> None:
        """Publish MCP message about agent query."""
        try:
            message = {
                "message_type": MCPMessageType.QUERY,
                "agent_id": agent_id,
                "query": query,
                "context": context,
                "response": {
                    "success": True,
                    "confidence": response.get("confidence", 0.0),
                    "inference_time": response.get("metadata", {}).get("inference_time", 0),
                    "circuit_breaker": response.get("metadata", {}).get("circuit_breaker", "unknown"),
                },
                "timestamp": asyncio.get_event_loop().time(),
            }
            await self.publish(message)
        except Exception as exc:
            logger.warning(f"Failed to publish agent query message: {exc}")

    async def _publish_agent_error(self, agent_id: str, query: str, error: str) -> None:
        """Publish MCP message about agent error."""
        try:
            message = {
                "message_type": MCPMessageType.QUERY,
                "agent_id": agent_id,
                "query": query,
                "response": {
                    "success": False,
                    "error": error,
                },
                "timestamp": asyncio.get_event_loop().time(),
            }
            await self.publish(message)
        except Exception as exc:
            logger.warning(f"Failed to publish agent error message: {exc}")

    async def get_agent_status(self, agent_id: str) -> Dict[str, Any]:
        """Get comprehensive status of a Vertex AI agent."""
        if not self._vertex_enabled or not self._vertex_client:
            return {"agent_id": agent_id, "status": "vertex_ai_unavailable"}

        try:
            # Get model info
            model_info = await self._vertex_client.get_model_info(agent_id)

            # Get circuit breaker status
            circuit_breaker = self._vertex_client.get_circuit_breaker_status(agent_id)

            # Get performance metrics
            performance = self._vertex_client.get_performance_metrics(agent_id)

            return {
                "agent_id": agent_id,
                "model_info": model_info,
                "circuit_breaker": circuit_breaker,
                "performance": performance,
                "overall_status": self._calculate_agent_status(model_info, circuit_breaker),
            }
        except Exception as exc:
            logger.error(f"Failed to get agent status for {agent_id}: {exc}")
            return {
                "agent_id": agent_id,
                "status": "error",
                "error": str(exc),
            }

    async def get_recent_messages(self, limit: int = 50) -> list[Dict[str, Any]]:
        """Get recent MCP messages for frontend display."""
        try:
            # For now, return mock messages to demonstrate the UI
            # In a real implementation, this would fetch from a message store
            import time
            current_time = time.time()

            mock_messages = [
                {
                    "id": f"msg_{i}",
                    "type": "observation" if i % 4 == 0 else "proposal" if i % 4 == 1 else "critique" if i % 4 == 2 else "consensus",
                    "sender": ["deepseek-v3", "fingpt-alpha", "lagllama-degen", "profit-maximizer"][i % 4],
                    "timestamp": str(current_time - (i * 60)),  # One per minute
                    "content": f"Agent analysis for market conditions - confidence: {0.6 + (i % 4) * 0.1:.1f}",
                    "context": f"Market regime: {'bull' if i % 2 == 0 else 'bear'}"
                }
                for i in range(min(limit, 20))  # Max 20 messages for demo
            ]

            return mock_messages
        except Exception as exc:
            logger.warning(f"Failed to get recent MCP messages: {exc}")
            return []

    def _calculate_agent_status(self, model_info: Dict, circuit_breaker: Dict) -> str:
        """Calculate overall agent health status."""
        # Check model health
        model_healthy = model_info.get("healthy", False)

        # Check circuit breaker
        cb_state = circuit_breaker.get("state", "unknown")
        cb_healthy = cb_state in ["closed", "half-open"]

        if model_healthy and cb_healthy:
            return "healthy"
        elif model_healthy and cb_state == "open":
            return "degraded"  # Model healthy but circuit open
        else:
            return "unhealthy"

    async def query_multiple_agents(
        self,
        agent_ids: list[str],
        query: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Query multiple Vertex AI agents and return consensus."""
        if not self._vertex_enabled or not self._vertex_client:
            raise RuntimeError("Vertex AI integration not available")

        # Query all agents concurrently
        tasks = [
            self.query_vertex_agent(agent_id, query, context, **kwargs)
            for agent_id in agent_ids
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        responses = {}
        errors = []
        confidences = []

        for i, result in enumerate(results):
            agent_id = agent_ids[i]
            if isinstance(result, Exception):
                errors.append({"agent_id": agent_id, "error": str(result)})
                responses[agent_id] = {"success": False, "error": str(result)}
            else:
                responses[agent_id] = result
                if result.get("confidence"):
                    confidences.append(result["confidence"])

        # Calculate consensus confidence
        consensus_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        consensus_result = {
            "query": query,
            "context": context,
            "responses": responses,
            "consensus_confidence": consensus_confidence,
            "total_agents": len(agent_ids),
            "successful_responses": len([r for r in responses.values() if r.get("success", True)]),
            "errors": errors,
            "timestamp": asyncio.get_event_loop().time(),
        }

        # Publish consensus message
        try:
            await self.publish({
                "message_type": MCPMessageType.CONSENSUS,
                "consensus": consensus_result,
            })
        except Exception as exc:
            logger.warning(f"Failed to publish consensus message: {exc}")

        return consensus_result

    async def close(self) -> None:
        await self._client.aclose()


__all__ = [
    "MCPClient",
    "MCPMessageType",
    "MCPProposalPayload",
    "MCPResponsePayload",
    "MCPHFTSignalPayload",
    "MCPMarketDataPayload",
    "MCPOrderExecutionPayload",
    "MCRiskUpdatePayload",
    "MCPStrategyAdjustmentPayload",
]

