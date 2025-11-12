"""MCP Coordinator for HFT Integration

Coordinates communication between LLM agents, Freqtrade, and Hummingbot
for unified autonomous trading decisions.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from .config import get_settings
from .mcp import MCPMessageType, MCPProposalPayload, MCPResponsePayload
from .pubsub import PubSubClient

logger = logging.getLogger(__name__)


class ComponentType(str, Enum):
    LLM_AGENT = "llm_agent"
    FREQTRADE = "freqtrade"
    HUMMINGBOT = "hummingbot"
    DASHBOARD = "dashboard"


class TradingSignal(BaseModel):
    symbol: str
    side: str  # "buy" or "sell"
    confidence: float
    notional: float
    rationale: str
    source: ComponentType
    timestamp: datetime


class MarketData(BaseModel):
    symbol: str
    price: float
    volume: float
    timestamp: datetime


class CoordinatorMessage(BaseModel):
    message_type: str
    component_id: str
    component_type: ComponentType
    payload: Dict[str, Any]
    timestamp: datetime


class MCPCoordinator:
    """Coordinates all trading components via MCP protocol."""

    def __init__(self):
        self.settings = get_settings()
        self.pubsub_client = None
        self.app = FastAPI(title="MCP Coordinator", version="1.0.0")

        # Component registry
        self.registered_components: Dict[str, ComponentType] = {}
        self.component_health: Dict[str, datetime] = {}

        # Trading state
        self.active_signals: Dict[str, List[TradingSignal]] = defaultdict(list)
        self.market_data: Dict[str, MarketData] = {}
        self.consensus_decisions: List[Dict[str, Any]] = []

        # Setup routes
        self._setup_routes()

        # Health monitoring
        self.health_check_interval = 30  # seconds
        self.max_health_age = timedelta(minutes=5)

    async def start(self):
        """Initialize the coordinator."""
        # Initialize Pub/Sub client
        if self.settings.gcp_project_id:
            self.pubsub_client = PubSubClient(self.settings)
            await self.pubsub_client.connect()

        # Start health monitoring
        asyncio.create_task(self._health_monitor())

        logger.info("MCP Coordinator started")

    async def stop(self):
        """Shutdown the coordinator."""
        if self.pubsub_client:
            await self.pubsub_client.close()

    def _setup_routes(self):
        """Setup FastAPI routes."""

        @self.app.get("/healthz")
        async def health_check():
            """Health check endpoint."""
            unhealthy_components = []
            now = datetime.now()

            for component_id, last_seen in self.component_health.items():
                if now - last_seen > self.max_health_age:
                    unhealthy_components.append(component_id)

            if unhealthy_components:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "degraded",
                        "unhealthy_components": unhealthy_components
                    }
                )

            return {"status": "healthy", "components": len(self.registered_components)}

        @self.app.post("/register")
        async def register_component(message: CoordinatorMessage):
            """Register a component with the coordinator."""
            component_id = message.component_id
            component_type = message.component_type

            self.registered_components[component_id] = component_type
            self.component_health[component_id] = datetime.now()

            logger.info(f"Registered {component_type} component: {component_id}")
            return {"status": "registered", "component_id": component_id}

        @self.app.post("/signal")
        async def receive_signal(signal: TradingSignal):
            """Receive trading signal from a component."""
            # Store signal
            self.active_signals[signal.symbol].append(signal)

            # Publish to Pub/Sub if available
            if self.pubsub_client:
                await self.pubsub_client.publish_reasoning({
                    "component": signal.source.value,
                    "signal": signal.model_dump(),
                    "action": "signal_received"
                })

            # Broadcast signal globally for cross-agent learning
            await self._broadcast_signal_globally(signal)

            # Check for collaboration opportunities (both same-symbol and cross-symbol)
            await self._check_collaboration_opportunities(signal.symbol)

            return {"status": "received", "signal_id": f"{signal.source}_{signal.timestamp.isoformat()}"}

        @self.app.post("/market-data")
        async def receive_market_data(data: MarketData):
            """Receive market data update."""
            self.market_data[data.symbol] = data

            # Forward to components that need real-time data
            await self._broadcast_market_data(data)

            return {"status": "received"}

        @self.app.get("/consensus/{symbol}")
        async def get_consensus(symbol: str):
            """Get consensus decision for a symbol."""
            consensus = await self._calculate_consensus(symbol)
            return {"symbol": symbol, "consensus": consensus}

        @self.app.post("/ask-question")
        async def ask_question(question: Dict[str, Any]):
            """Allow agents to ask questions to other agents."""
            await self.receive_agent_question(question)
            return {"status": "question_routed"}

        @self.app.post("/share-insight")
        async def share_insight(insight: Dict[str, Any]):
            """Allow agents to share insights with other agents."""
            await self.receive_agent_insight(insight)
            return {"status": "insight_shared"}

        @self.app.post("/share-thesis")
        async def share_thesis(thesis: Dict[str, Any]):
            """Allow agents to share detailed trade theses."""
            await self.receive_trade_thesis(thesis)
            return {"status": "thesis_shared"}

        @self.app.post("/strategy-discussion")
        async def strategy_discussion(discussion: Dict[str, Any]):
            """Allow agents to engage in strategy discussions."""
            await self.receive_strategy_discussion(discussion)
            return {"status": "discussion_routed"}

        @self.app.get("/agent-theses/{symbol}")
        async def get_agent_theses(symbol: str):
            """Get all theses shared for a symbol."""
            theses = getattr(self, 'agent_theses', {}).get(symbol, [])
            return {"symbol": symbol, "theses": theses}

        @self.app.get("/global-signals")
        async def get_global_signals():
            """Get recent global signals from all agents."""
            all_signals = []
            for symbol_signals in self.active_signals.values():
                for signal in symbol_signals[-10:]:  # Last 10 signals per symbol
                    all_signals.append({
                        "symbol": signal.symbol,
                        "source": signal.source,
                        "side": signal.side,
                        "confidence": signal.confidence,
                        "timestamp": signal.timestamp.isoformat()
                    })
            # Sort by timestamp, most recent first
            all_signals.sort(key=lambda x: x["timestamp"], reverse=True)
            return {"signals": all_signals[:50]}  # Return most recent 50

        @self.app.get("/discussions/{symbol}")
        async def get_symbol_discussions(symbol: str):
            """Get recent discussions for a symbol."""
            # This would be implemented to return recent discussions
            return {"symbol": symbol, "discussions": []}

        @self.app.get("/status")
        async def get_status():
            """Get overall system status."""
            return {
                "components": {
                    cid: {
                        "type": ctype.value,
                        "healthy": datetime.now() - self.component_health.get(cid, datetime.min) < self.max_health_age
                    }
                    for cid, ctype in self.registered_components.items()
                },
                "active_signals": {symbol: len(signals) for symbol, signals in self.active_signals.items()},
                "market_data": list(self.market_data.keys()),
                "consensus_count": len(self.consensus_decisions)
            }

    async def _check_collaboration_opportunities(self, symbol: str):
        """Check for collaboration opportunities and facilitate communication."""
        signals = self.active_signals[symbol]

        # Share information when multiple agents are active on the same symbol
        if len(signals) >= 2:
            await self._facilitate_agent_discussion(symbol, signals)

    async def _facilitate_agent_discussion(self, symbol: str, signals: list):
        """Facilitate collaborative discussion between agents."""
        # Create discussion context
        discussion = {
            "symbol": symbol,
            "active_agents": [s.source for s in signals],
            "signal_summary": [
                {
                    "agent": s.source,
                    "side": s.side,
                    "confidence": s.confidence,
                    "strategy": getattr(s, 'strategy', 'unknown'),
                    "notional": s.notional
                }
                for s in signals
            ],
            "timestamp": datetime.now(),
            "discussion_id": f"disc_{symbol}_{int(datetime.now().timestamp())}"
        }

        # Publish discussion opportunity
        if self.pubsub_client:
            await self.pubsub_client.publish_reasoning({
                "event": "agent_discussion",
                "discussion": discussion,
                "action": "collaboration_opportunity"
            })

        # Allow agents to respond and ask questions
        await self._broadcast_discussion_to_agents(discussion)

        logger.info(f"Agent discussion initiated for {symbol} with {len(signals)} participants")

    async def _broadcast_signal_globally(self, signal: TradingSignal):
        """Broadcast trading signal globally to all agents for cross-learning."""
        global_signal = {
            "event": "global_trade_signal",
            "signal": {
                "symbol": signal.symbol,
                "side": signal.side,
                "confidence": signal.confidence,
                "notional": signal.notional,
                "price": signal.price,
                "rationale": signal.rationale,
                "source_agent": signal.source,
                "strategy": getattr(signal, 'strategy', 'unknown'),
                "indicators": getattr(signal, 'indicators', {}),
                "risk_parameters": getattr(signal, 'risk_parameters', {}),
                "timestamp": signal.timestamp.isoformat(),
            },
            "action": "global_signal_broadcast"
        }

        # Broadcast to all registered agents for learning opportunities
        for component_id in self.registered_components.keys():
            await self._notify_component(component_id, {
                "message_type": "global_signal_broadcast",
                "signal": global_signal,
                "timestamp": datetime.now()
            })

        logger.info(f"Global signal broadcast: {signal.source} trading {signal.symbol} {signal.side}")

    async def receive_trade_thesis(self, thesis: Dict[str, Any]):
        """Receive detailed trade thesis from an agent."""
        thesis_data = {
            "agent": thesis["agent"],
            "symbol": thesis["symbol"],
            "thesis": thesis["thesis"],
            "entry_point": thesis.get("entry_point"),
            "take_profit": thesis.get("take_profit"),
            "stop_loss": thesis.get("stop_loss"),
            "risk_reward_ratio": thesis.get("risk_reward_ratio"),
            "timeframe": thesis.get("timeframe"),
            "conviction_level": thesis.get("conviction_level"),
            "market_context": thesis.get("market_context", {}),
            "timestamp": thesis.get("timestamp", datetime.now().isoformat())
        }

        # Store thesis for cross-agent learning
        if not hasattr(self, 'agent_theses'):
            self.agent_theses = {}
        if thesis["symbol"] not in self.agent_theses:
            self.agent_theses[thesis["symbol"]] = []
        self.agent_theses[thesis["symbol"]].append(thesis_data)

        # Broadcast thesis to all agents
        for component_id in self.registered_components.keys():
            await self._notify_component(component_id, {
                "message_type": "trade_thesis_shared",
                "thesis": thesis_data,
                "timestamp": datetime.now()
            })

        # Publish to BigQuery for analysis
        if hasattr(self, 'bigquery_exporter') and self.bigquery_exporter:
            await self.bigquery_exporter.export_trade_thesis(thesis_data)

        logger.info(f"Trade thesis received from {thesis['agent']} on {thesis['symbol']}")

    async def receive_strategy_discussion(self, discussion: Dict[str, Any]):
        """Receive strategy discussion or question from an agent."""
        discussion_data = {
            "from_agent": discussion["from_agent"],
            "to_agent": discussion.get("to_agent"),  # None for broadcast
            "topic": discussion["topic"],
            "content": discussion["content"],
            "context": discussion.get("context", {}),
            "discussion_type": discussion.get("discussion_type", "question"),  # question, insight, strategy
            "timestamp": discussion.get("timestamp", datetime.now().isoformat())
        }

        # Route to specific agent or broadcast
        if discussion_data["to_agent"]:
            component_id = self._get_component_id_for_agent(discussion_data["to_agent"])
            if component_id:
                await self._notify_component(component_id, {
                    "message_type": "strategy_discussion",
                    "discussion": discussion_data,
                    "timestamp": datetime.now()
                })
        else:
            # Broadcast to all agents
            for component_id in self.registered_components.keys():
                if component_id != self._get_component_id_for_agent(discussion_data["from_agent"]):
                    await self._notify_component(component_id, {
                        "message_type": "strategy_discussion_broadcast",
                        "discussion": discussion_data,
                        "timestamp": datetime.now()
                    })

        logger.info(f"Strategy discussion: {discussion_data['from_agent']} → {discussion_data['to_agent'] or 'ALL'}: {discussion_data['topic']}")

    async def _broadcast_discussion_to_agents(self, discussion: Dict[str, Any]):
        """Broadcast discussion opportunity to all participating agents."""
        for agent_type in discussion["active_agents"]:
            component_id = self._get_component_id_for_agent(agent_type)
            if component_id:
                await self._notify_component(component_id, {
                    "message_type": "discussion_invitation",
                    "discussion": discussion,
                    "timestamp": datetime.now()
                })

    def _get_component_id_for_agent(self, agent_type: str) -> Optional[str]:
        """Get component ID for an agent type."""
        for component_id, component_type in self.registered_components.items():
            if agent_type.lower() in component_id.lower():
                return component_id
        return None

    async def receive_agent_question(self, question: Dict[str, Any]):
        """Receive a question from an agent and route it appropriately."""
        target_agent = question.get("target_agent")
        asking_agent = question.get("asking_agent")
        question_content = question.get("question")

        # Route question to target agent or broadcast to all
        if target_agent:
            component_id = self._get_component_id_for_agent(target_agent)
            if component_id:
                await self._notify_component(component_id, {
                    "message_type": "agent_question",
                    "question": question,
                    "timestamp": datetime.now()
                })
        else:
            # Broadcast question to all agents
            for component_id in self.registered_components.keys():
                await self._notify_component(component_id, {
                    "message_type": "agent_question_broadcast",
                    "question": question,
                    "timestamp": datetime.now()
                })

        logger.info(f"Agent {asking_agent} asked: {question_content}")

    async def receive_agent_insight(self, insight: Dict[str, Any]):
        """Receive an insight from an agent and share with others."""
        symbol = insight.get("symbol")
        agent = insight.get("agent")
        insight_content = insight.get("insight")

        # Share insight with other agents working on the same symbol
        signals = self.active_signals.get(symbol, [])
        for signal in signals:
            if signal.source != agent:  # Don't send back to sender
                component_id = self._get_component_id_for_agent(signal.source)
                if component_id:
                    await self._notify_component(component_id, {
                        "message_type": "agent_insight",
                        "insight": insight,
                        "timestamp": datetime.now()
                    })

        logger.info(f"Agent {agent} shared insight about {symbol}: {insight_content}")

    async def _execute_consensus(self, consensus: Dict[str, Any]):
        """Execute a consensus trading decision."""
        # Forward to execution components (Freqtrade, Hummingbot)
        execution_payload = {
            "message_type": MCPMessageType.EXECUTION,
            "consensus": consensus,
            "timestamp": datetime.now()
        }

        # Send to all registered components for execution
        for component_id, component_type in self.registered_components.items():
            if component_type in [ComponentType.FREQTRADE, ComponentType.HUMMINGBOT]:
                await self._notify_component(component_id, execution_payload)

    async def _broadcast_market_data(self, data: MarketData):
        """Broadcast market data to components that need it."""
        payload = {
            "message_type": "market_data",
            "data": data.model_dump(),
            "timestamp": datetime.now()
        }

        for component_id in self.registered_components:
            await self._notify_component(component_id, payload)

    async def _notify_component(self, component_id: str, payload: Dict[str, Any]):
        """Notify a component via HTTP or other mechanism."""
        # This would be implemented based on how components expose their APIs
        # For now, use Pub/Sub as the communication mechanism
        if self.pubsub_client:
            await self.pubsub_client.publish_reasoning({
                "target_component": component_id,
                "payload": payload
            })

    async def _calculate_consensus(self, symbol: str) -> Dict[str, Any]:
        """Calculate current consensus for a symbol."""
        signals = self.active_signals[symbol]
        if not signals:
            return {"status": "no_signals"}

        buy_confidence = sum(s.confidence for s in signals if s.side == "buy")
        sell_confidence = sum(s.confidence for s in signals if s.side == "sell")

        total_confidence = buy_confidence + sell_confidence
        if total_confidence == 0:
            return {"status": "neutral"}

        buy_ratio = buy_confidence / total_confidence
        sell_ratio = sell_confidence / total_confidence

        if buy_ratio > 0.6:
            return {"decision": "buy", "confidence": buy_ratio, "signal_count": len(signals)}
        elif sell_ratio > 0.6:
            return {"decision": "sell", "confidence": sell_ratio, "signal_count": len(signals)}
        else:
            return {"decision": "hold", "confidence": max(buy_ratio, sell_ratio), "signal_count": len(signals)}

    async def _health_monitor(self):
        """Monitor component health."""
        while True:
            try:
                # Check for stale components
                now = datetime.now()
                stale_components = []

                for component_id, last_seen in self.component_health.items():
                    if now - last_seen > self.max_health_age:
                        stale_components.append(component_id)

                for component_id in stale_components:
                    logger.warning(f"Component {component_id} appears unhealthy")
                    # Could send alerts or attempt recovery here

                await asyncio.sleep(self.health_check_interval)

            except Exception as e:
                logger.error(f"Health monitoring error: {e}")
                await asyncio.sleep(self.health_check_interval)


# Global coordinator instance
_coordinator: Optional[MCPCoordinator] = None


def get_coordinator() -> MCPCoordinator:
    """Get or create global coordinator instance."""
    global _coordinator
    if _coordinator is None:
        _coordinator = MCPCoordinator()
    return _coordinator


if __name__ == "__main__":
    import uvicorn

    coordinator = get_coordinator()

    @coordinator.app.on_event("startup")
    async def startup_event():
        await coordinator.start()

    @coordinator.app.on_event("shutdown")
    async def shutdown_event():
        await coordinator.stop()

    uvicorn.run(coordinator.app, host="0.0.0.0", port=8081)
