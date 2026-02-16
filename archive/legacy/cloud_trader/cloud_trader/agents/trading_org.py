"""
Sapphire V2 Trading Organization
Multi-agent organizational structure inspired by ElizaOS the-org.

Each agent has a specialized role in the trading organization:
- Alpha (Chief Analyst): Market analysis and opportunity identification
- Risk (Risk Officer): Portfolio protection and position sizing
- Executor (Execution Specialist): Trade execution and optimization
- Strategist (Strategy Director): High-level strategy and adaptation
- Sentinel (Market Sentinel): Real-time monitoring and alerts
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .eliza_agent import AgentConfig, ElizaAgent, ModelProvider, Thesis

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Specialized roles in the trading organization."""

    CHIEF_ANALYST = "alpha"  # Market analysis, opportunity identification
    RISK_OFFICER = "risk"  # Risk management, position sizing
    EXECUTOR = "executor"  # Trade execution, timing
    STRATEGIST = "strategist"  # Strategy direction, adaptation
    SENTINEL = "sentinel"  # Monitoring, alerts


@dataclass
class TeamDecision:
    """Collaborative decision from the trading organization."""

    symbol: str
    action: str  # TRADE, HOLD, CLOSE, ALERT
    signal: str  # BUY, SELL, HOLD
    confidence: float
    position_size: float
    reasoning: str
    approvals: Dict[str, bool] = field(default_factory=dict)
    vetoes: List[str] = field(default_factory=list)
    timestamp: float = 0.0

    def is_approved(self) -> bool:
        """Check if decision has required approvals and no vetoes."""
        # Risk Officer can veto any trade
        if AgentRole.RISK_OFFICER.value in self.vetoes:
            return False
        # Need at least analyst and one other approval
        required = [AgentRole.CHIEF_ANALYST.value]
        return all(self.approvals.get(r, False) for r in required)


class TradingOrganization:
    """
    Organizational structure for coordinated multi-agent trading.

    Inspired by the-org pattern:
    - Each agent has a specialized role
    - Decisions require coordination and approval
    - Risk Officer has veto power
    - Sentinel provides real-time oversight
    """

    def __init__(self, model_router=None, memory_manager=None):
        self.agents: Dict[AgentRole, ElizaAgent] = {}
        self._initialize_organization(model_router, memory_manager)

        logger.info("🏛️ TradingOrganization initialized with specialized agents")

    def _initialize_organization(self, model_router, memory_manager):
        """Initialize all specialized agents."""

        # Alpha - Chief Analyst
        self.agents[AgentRole.CHIEF_ANALYST] = ElizaAgent(
            AgentConfig(
                agent_id="org-alpha",
                name="Alpha",
                personality="analytical",
                specialization="technical",
                primary_model=ModelProvider.GEMINI,
                confidence_threshold=0.6,
            ),
            model_router=model_router,
            memory_manager=memory_manager,
        )

        # Risk - Risk Officer
        self.agents[AgentRole.RISK_OFFICER] = ElizaAgent(
            AgentConfig(
                agent_id="org-risk",
                name="Risk",
                personality="conservative",
                specialization="hybrid",
                primary_model=ModelProvider.GEMINI,
                confidence_threshold=0.75,  # Higher threshold for risk
            )
        )

        # Executor - Execution Specialist
        self.agents[AgentRole.EXECUTOR] = ElizaAgent(
            AgentConfig(
                agent_id="org-executor",
                name="Executor",
                personality="aggressive",
                specialization="orderflow",
                primary_model=ModelProvider.GEMINI,
                confidence_threshold=0.55,
            )
        )

        # Strategist - Strategy Director
        self.agents[AgentRole.STRATEGIST] = ElizaAgent(
            AgentConfig(
                agent_id="org-strategist",
                name="Strategist",
                personality="analytical",
                specialization="hybrid",
                primary_model=ModelProvider.GEMINI,
                confidence_threshold=0.7,
            )
        )

        # Sentinel - Market Sentinel
        self.agents[AgentRole.SENTINEL] = ElizaAgent(
            AgentConfig(
                agent_id="org-sentinel",
                name="Sentinel",
                personality="contrarian",
                specialization="sentiment",
                primary_model=ModelProvider.GEMINI,
                confidence_threshold=0.5,
            )
        )

    async def make_trade_decision(
        self, symbol: str, market_data: Optional[Dict] = None
    ) -> TeamDecision:
        """
        Coordinate a trade decision across the organization.

        Flow:
        1. Alpha analyzes opportunity
        2. Risk evaluates exposure
        3. Strategist validates alignment
        4. Executor determines timing
        5. Sentinel checks for warnings
        """
        import time

        # Step 1: Chief Analyst evaluates opportunity
        alpha = self.agents[AgentRole.CHIEF_ANALYST]
        alpha_thesis = await alpha.analyze(symbol, market_data)

        if alpha_thesis.signal == "HOLD" or alpha_thesis.confidence < 0.5:
            return TeamDecision(
                symbol=symbol,
                action="HOLD",
                signal="HOLD",
                confidence=alpha_thesis.confidence,
                position_size=0.0,
                reasoning="Alpha: No actionable opportunity",
                timestamp=time.time(),
            )

        # Step 2: Risk Officer evaluates
        risk = self.agents[AgentRole.RISK_OFFICER]
        risk_thesis = await risk.analyze(
            symbol,
            {
                **(market_data or {}),
                "proposed_signal": alpha_thesis.signal,
                "analyst_confidence": alpha_thesis.confidence,
            },
        )

        # Risk can veto
        vetoes = []
        if risk_thesis.signal == "HOLD" and risk_thesis.confidence > 0.7:
            vetoes.append(AgentRole.RISK_OFFICER.value)

        # Step 3: Calculate position size based on risk assessment
        base_size = 100.0  # Base position size in USD
        risk_multiplier = 1.0 - (0.5 * (1 - risk_thesis.confidence))
        position_size = base_size * risk_multiplier * alpha_thesis.confidence

        # Step 4: Executor checks timing
        executor = self.agents[AgentRole.EXECUTOR]
        exec_thesis = await executor.analyze(
            symbol, {**(market_data or {}), "proposed_signal": alpha_thesis.signal}
        )

        # Step 5: Sentinel safety check
        sentinel = self.agents[AgentRole.SENTINEL]
        sentinel_thesis = await sentinel.analyze(symbol, market_data)

        # Sentinel warning can reduce confidence
        final_confidence = alpha_thesis.confidence
        if sentinel_thesis.signal != alpha_thesis.signal and sentinel_thesis.confidence > 0.6:
            final_confidence *= 0.8  # Reduce confidence on disagreement

        # Build approvals
        approvals = {
            AgentRole.CHIEF_ANALYST.value: alpha_thesis.confidence
            >= alpha.config.confidence_threshold,
            AgentRole.RISK_OFFICER.value: risk_thesis.signal != "HOLD"
            or risk_thesis.confidence < 0.7,
            AgentRole.EXECUTOR.value: exec_thesis.confidence >= 0.5,
            AgentRole.STRATEGIST.value: True,  # Strategist approves by default for now
        }

        # Combine reasoning
        reasoning = (
            f"Alpha: {alpha_thesis.reasoning[:50]}... | Risk: {risk_thesis.reasoning[:30]}..."
        )

        decision = TeamDecision(
            symbol=symbol,
            action="TRADE" if not vetoes else "HOLD",
            signal=alpha_thesis.signal,
            confidence=final_confidence,
            position_size=position_size if not vetoes else 0.0,
            reasoning=reasoning,
            approvals=approvals,
            vetoes=vetoes,
            timestamp=time.time(),
        )

        logger.info(
            f"🏛️ [ORG] {symbol}: {decision.action} {decision.signal} "
            f"(conf: {decision.confidence:.2f}, size: ${decision.position_size:.0f}, "
            f"vetoes: {vetoes})"
        )

        return decision

    async def get_market_sentiment(self, symbols: List[str]) -> Dict[str, Any]:
        """Get Sentinel's market sentiment overview."""
        sentinel = self.agents[AgentRole.SENTINEL]

        results = {}
        for symbol in symbols:
            thesis = await sentinel.analyze(symbol)
            results[symbol] = {
                "sentiment": thesis.signal,
                "confidence": thesis.confidence,
                "reasoning": thesis.reasoning,
            }

        return results

    def get_org_stats(self) -> Dict[str, Any]:
        """Get organization statistics."""
        return {role.value: agent.get_stats() for role, agent in self.agents.items()}
