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
import uuid
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from .config import get_settings
from .mcp import MCPMessageType, MCPProposalPayload, MCPResponsePayload
from .portfolio_orchestrator import get_portfolio_orchestrator
from .pubsub import PubSubClient
from .logging_config import get_trading_logger, correlation_context, log_performance
from .data_collector import get_data_collector, collect_market_data, collect_trading_decision, collect_trade_execution
from .resilience import get_resilience_manager, circuit_breaker, health_check

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

        # Initialize core systems
        self.portfolio_orchestrator = get_portfolio_orchestrator()
        self.data_collector = get_data_collector()
        self.resilience_manager = get_resilience_manager()
        self.logger = get_trading_logger("mcp-coordinator")

        # Communication management
        self.agent_activity_levels: Dict[str, Dict[str, Any]] = {}
        self.communication_throttles: Dict[str, datetime] = {}
        self.participation_thresholds: Dict[str, float] = {}

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
        @log_performance("receive_signal")
        async def receive_signal(signal: TradingSignal, request: Request = None):
            """Receive trading signal from a component."""
            # Generate correlation ID for tracing
            correlation_id = request.headers.get("X-Correlation-ID") if request else str(uuid.uuid4())
            self.logger.set_correlation_id(correlation_id)

            # Track trading activity for participation management
            agent_id = self._get_agent_id_from_source(signal.source)
            self._update_agent_activity(agent_id, "trading")

            # Collect trading decision data
            decision_data = {
                "timestamp": signal.timestamp.isoformat(),
                "agent_id": agent_id,
                "symbol": signal.symbol,
                "decision": signal.side,
                "confidence": signal.confidence,
                "strategy": getattr(signal, 'strategy', 'unknown'),
                "indicators": getattr(signal, 'indicators', {}),
                "market_context": getattr(signal, 'market_context', {}),
                "reasoning": signal.rationale,
                "position_size": getattr(signal, 'position_size', 1.0),
                "risk_parameters": getattr(signal, 'risk_parameters', {}),
                "correlation_id": correlation_id,
            }
            collect_trading_decision(decision_data)

            # Log the trading signal
            self.logger.log_trade_signal({
                "symbol": signal.symbol,
                "side": signal.side,
                "confidence": signal.confidence,
                "notional": signal.notional,
                "price": signal.price,
                "source": agent_id,
                "rationale": signal.rationale,
                "correlation_id": correlation_id,
            })

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

        @self.app.get("/portfolio-status")
        async def get_portfolio_status():
            """Get comprehensive portfolio status from orchestrator."""
            return self.portfolio_orchestrator.get_portfolio_status()

        @self.app.get("/agent-roles")
        async def get_agent_roles():
            """Get agent roles and responsibilities."""
            return {
                agent_id: {
                    "role": personality.role.value,
                    "expertise": personality.expertise,
                    "contribution": personality.portfolio_contribution,
                    "communication_style": personality.communication_style,
                    "collaboration_partners": [p.value for p in personality.collaboration_partners],
                    "risk_tolerance": personality.risk_tolerance,
                    "time_horizon": personality.time_horizon,
                    "preferred_assets": personality.preferred_assets,
                    "allocated_capital": self.portfolio_orchestrator.agent_allocations.get(agent_id, 0)
                }
                for agent_id, personality in self.portfolio_orchestrator.agent_personalities.items()
            }

        @self.app.get("/agent/{agent_id}/guidance")
        async def get_agent_guidance(agent_id: str):
            """Get personalized guidance for an agent."""
            guidance = self.portfolio_orchestrator.get_agent_guidance(agent_id)
            return guidance

        @self.app.get("/agent/{agent_id}/participation-check")
        async def check_agent_participation(agent_id: str):
            """Check if agent should participate in communication."""
            should_participate = self.should_agent_participate(agent_id, "communication")
            return {"should_participate": should_participate}

        @self.app.post("/validate-trade/{agent_id}")
        async def validate_agent_trade(agent_id: str, trade_details: Dict[str, Any]):
            """Validate a trade against portfolio constraints."""
            is_valid = self.portfolio_orchestrator.validate_agent_trade(agent_id, trade_details)
            return {
                "agent_id": agent_id,
                "trade_valid": is_valid,
                "validation_details": "Trade validated against portfolio constraints" if is_valid else "Trade exceeds portfolio limits"
            }

        @self.app.post("/portfolio-goal")
        async def set_portfolio_goal(goal: Dict[str, str]):
            """Set portfolio optimization goal."""
            from .portfolio_orchestrator import PortfolioGoal
            goal_enum = PortfolioGoal(goal["goal"])
            self.portfolio_orchestrator.portfolio_goal = goal_enum
            return {"status": "goal_updated", "new_goal": goal_enum.value}

        @self.app.get("/agent-activity")
        async def get_agent_activity():
            """Get current agent activity levels."""
            return {
                agent_id: {
                    "activity_score": data["activity_score"],
                    "communication_count": data["communication_count"],
                    "trading_count": data["trading_count"],
                    "last_activity": data["last_activity"].isoformat(),
                    "participation_threshold": self.participation_thresholds.get(agent_id, 0.5)
                }
                for agent_id, data in self.agent_activity_levels.items()
            }

        @self.app.post("/set-participation-threshold/{agent_id}")
        async def set_agent_participation_threshold(agent_id: str, threshold: Dict[str, float]):
            """Set participation threshold for an agent."""
            self.set_participation_threshold(agent_id, threshold["threshold"])
            return {"status": "threshold_set", "agent_id": agent_id, "threshold": threshold["threshold"]}

        @self.app.get("/system-status")
        async def get_system_status():
            """Get comprehensive system status."""
            return self.resilience_manager.get_system_status()

        @self.app.get("/health-metrics")
        async def get_health_metrics():
            """Get health metrics for monitoring."""
            return {
                "portfolio": self.portfolio_orchestrator.get_portfolio_status(),
                "data_collection": {
                    "market_data_collected": len(self.data_collector.market_data_buffer),
                    "decisions_collected": len(self.data_collector.trading_decisions_buffer),
                    "executions_collected": len(self.data_collector.trade_executions_buffer),
                },
                "communication": {
                    "active_agents": len(self.agent_activity_levels),
                    "throttled_agents": len(self.communication_throttles),
                },
                "timestamp": datetime.now().isoformat(),
            }

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
        # Only send to agents that should participate and aren't throttled
        for component_id in self.registered_components.keys():
            if self.should_agent_participate(component_id, "communication"):
                await self._notify_component(component_id, {
                    "message_type": "global_signal_broadcast",
                    "signal": global_signal,
                    "timestamp": datetime.now()
                })
                self.update_communication_throttle(component_id)

        logger.info(f"Global signal broadcast: {signal.source} trading {signal.symbol} {signal.side}")

    def should_agent_participate(self, agent_id: str, activity_type: str = "communication") -> bool:
        """Determine if agent should participate based on activity levels and thresholds."""
        # Update activity levels
        self._update_agent_activity(agent_id, activity_type)

        # Check participation threshold
        threshold = self.participation_thresholds.get(agent_id, 0.5)  # Default 50% participation

        # Get agent's activity level compared to others
        agent_activity = self._get_agent_activity_level(agent_id)
        average_activity = self._get_average_activity_level()

        # Agents participate less if they're much more active than average
        if agent_activity > average_activity * 2:
            participation_chance = max(0.1, threshold * 0.5)  # Reduce participation
        elif agent_activity < average_activity * 0.5:
            participation_chance = min(0.9, threshold * 1.5)  # Increase participation
        else:
            participation_chance = threshold

        # Random chance based on participation threshold
        import random
        return random.random() < participation_chance

    def is_agent_throttled(self, agent_id: str, throttle_seconds: int = 30) -> bool:
        """Check if agent is currently throttled from communication."""
        last_communication = self.communication_throttles.get(agent_id)
        if not last_communication:
            return False

        time_since_last = (datetime.now() - last_communication).total_seconds()
        return time_since_last < throttle_seconds

    def update_communication_throttle(self, agent_id: str):
        """Update agent's communication throttle timestamp."""
        self.communication_throttles[agent_id] = datetime.now()

    def _update_agent_activity(self, agent_id: str, activity_type: str):
        """Update agent's activity level tracking."""
        if agent_id not in self.agent_activity_levels:
            self.agent_activity_levels[agent_id] = {
                "communication_count": 0,
                "trading_count": 0,
                "last_activity": datetime.now(),
                "activity_score": 0.0
            }

        activity_data = self.agent_activity_levels[agent_id]
        activity_data["last_activity"] = datetime.now()

        if activity_type == "communication":
            activity_data["communication_count"] += 1
        elif activity_type == "trading":
            activity_data["trading_count"] += 1

        # Calculate activity score (trades are weighted more heavily)
        activity_data["activity_score"] = (
            activity_data["communication_count"] * 0.3 +
            activity_data["trading_count"] * 0.7
        )

    def _get_agent_activity_level(self, agent_id: str) -> float:
        """Get agent's activity level score."""
        if agent_id not in self.agent_activity_levels:
            return 0.0
        return self.agent_activity_levels[agent_id]["activity_score"]

    def _get_average_activity_level(self) -> float:
        """Get average activity level across all agents."""
        if not self.agent_activity_levels:
            return 1.0

        total_activity = sum(data["activity_score"] for data in self.agent_activity_levels.values())
        return total_activity / len(self.agent_activity_levels)

    def set_participation_threshold(self, agent_id: str, threshold: float):
        """Set participation threshold for an agent (0.0 to 1.0)."""
        self.participation_thresholds[agent_id] = max(0.0, min(1.0, threshold))

    def _get_agent_id_from_source(self, source) -> str:
        """Get agent ID from signal source."""
        # Map signal sources to agent IDs
        source_mapping = {
            "trend-momentum": "trend-momentum-agent",
            "strategy-optimization": "strategy-optimization-agent",
            "financial-sentiment": "financial-sentiment-agent",
            "market-prediction": "market-prediction-agent",
            "volume-microstructure": "volume-microstructure-agent",
            "freqtrade": "freqtrade",
            "hummingbot": "hummingbot",
            "vpin": "vpin-hft",
        }
        return source_mapping.get(source.value, source.value)

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

        # Broadcast thesis to all agents (with participation filtering)
        for component_id in self.registered_components.keys():
            if self.should_agent_participate(component_id, "communication"):
                await self._notify_component(component_id, {
                    "message_type": "trade_thesis_shared",
                    "thesis": thesis_data,
                    "timestamp": datetime.now()
                })
                self.update_communication_throttle(component_id)

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

        # Route to specific agent or broadcast (with participation filtering)
        if discussion_data["to_agent"]:
            component_id = self._get_component_id_for_agent(discussion_data["to_agent"])
            if component_id and self.should_agent_participate(component_id, "communication"):
                await self._notify_component(component_id, {
                    "message_type": "strategy_discussion",
                    "discussion": discussion_data,
                    "timestamp": datetime.now()
                })
                self.update_communication_throttle(component_id)
        else:
            # Broadcast to all agents (with participation filtering)
            for component_id in self.registered_components.keys():
                if component_id != self._get_component_id_for_agent(discussion_data["from_agent"]):
                    if self.should_agent_participate(component_id, "communication"):
                        await self._notify_component(component_id, {
                            "message_type": "strategy_discussion_broadcast",
                            "discussion": discussion_data,
                            "timestamp": datetime.now()
                        })
                        self.update_communication_throttle(component_id)

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
