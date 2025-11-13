"""Portfolio Orchestrator for Agent Role Management and Coordination

Defines agent roles, manages portfolio-level risk, and coordinates
agent collaboration while maintaining individual trading freedom.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    MOMENTUM_TRADER = "momentum_trader"
    MEAN_REVERSION_TRADER = "mean_reversion_trader"
    SENTIMENT_ANALYST = "sentiment_analyst"
    VOLATILITY_SPECIALIST = "volatility_specialist"
    TECHNICAL_ANALYST = "technical_analyst"
    MARKET_MAKER = "market_maker"
    RISK_MANAGER = "risk_manager"
    PORTFOLIO_OPTIMIZER = "portfolio_optimizer"


class PortfolioGoal(str, Enum):
    MAXIMUM_PROFIT = "maximum_profit"
    CONSISTENT_RETURNS = "consistent_returns"
    RISK_ADJUSTED_RETURNS = "risk_adjusted_returns"
    VOLATILITY_HARVESTING = "volatility_harvesting"
    MARKET_NEUTRAL = "market_neutral"


class AgentPersonality:
    """Defines an agent's role, expertise, and communication preferences."""

    def __init__(self, agent_id: str, role: AgentRole):
        self.agent_id = agent_id
        self.role = role
        self.expertise = self._get_expertise_for_role(role)
        self.portfolio_contribution = self._get_contribution_for_role(role)
        self.communication_style = self._get_communication_style(role)
        self.collaboration_partners = self._get_collaboration_partners(role)
        self.risk_tolerance = self._get_risk_tolerance(role)
        self.time_horizon = self._get_time_horizon(role)
        self.preferred_assets = self._get_preferred_assets(role)

    def _get_expertise_for_role(self, role: AgentRole) -> List[str]:
        """Get expertise areas for each role."""
        expertise_map = {
            AgentRole.MOMENTUM_TRADER: ["trend_analysis", "breakout_detection", "momentum_indicators"],
            AgentRole.MEAN_REVERSION_TRADER: ["support_resistance", "overbought_oversold", "statistical_arbitrage"],
            AgentRole.SENTIMENT_ANALYST: ["news_analysis", "social_sentiment", "market_psychology"],
            AgentRole.VOLATILITY_SPECIALIST: ["volatility_forecasting", "options_strategies", "tail_risk_management"],
            AgentRole.TECHNICAL_ANALYST: ["pattern_recognition", "indicator_analysis", "quantitative_modeling"],
            AgentRole.MARKET_MAKER: ["liquidity_provision", "spread_management", "order_flow_analysis"],
            AgentRole.RISK_MANAGER: ["position_sizing", "correlation_analysis", "stress_testing"],
            AgentRole.PORTFOLIO_OPTIMIZER: ["asset_allocation", "risk_parity", "performance_attribution"]
        }
        return expertise_map.get(role, [])

    def _get_contribution_for_role(self, role: AgentRole) -> str:
        """Get portfolio contribution description."""
        contribution_map = {
            AgentRole.MOMENTUM_TRADER: "Captures trending moves with high conviction",
            AgentRole.MEAN_REVERSION_TRADER: "Profits from price corrections and range trading",
            AgentRole.SENTIMENT_ANALYST: "Provides fundamental context and market sentiment",
            AgentRole.VOLATILITY_SPECIALIST: "Manages tail risk and harvests volatility premiums",
            AgentRole.TECHNICAL_ANALYST: "Generates quantitative signals across timeframes",
            AgentRole.MARKET_MAKER: "Provides liquidity and reduces slippage costs",
            AgentRole.RISK_MANAGER: "Ensures portfolio stability and risk control",
            AgentRole.PORTFOLIO_OPTIMIZER: "Optimizes asset allocation and performance"
        }
        return contribution_map.get(role, "Contributes to portfolio diversification")

    def _get_communication_style(self, role: AgentRole) -> str:
        """Get communication style for each role."""
        style_map = {
            AgentRole.MOMENTUM_TRADER: "Direct and conviction-driven",
            AgentRole.MEAN_REVERSION_TRADER: "Analytical and patient",
            AgentRole.SENTIMENT_ANALYST: "Context-rich and narrative-driven",
            AgentRole.VOLATILITY_SPECIALIST: "Quantitative and probabilistic",
            AgentRole.TECHNICAL_ANALYST: "Data-driven and systematic",
            AgentRole.MARKET_MAKER: "Practical and execution-focused",
            AgentRole.RISK_MANAGER: "Conservative and cautionary",
            AgentRole.PORTFOLIO_OPTIMIZER: "Strategic and holistic"
        }
        return style_map.get(role, "Collaborative and informative")

    def _get_collaboration_partners(self, role: AgentRole) -> List[AgentRole]:
        """Get preferred collaboration partners."""
        partners_map = {
            AgentRole.MOMENTUM_TRADER: [AgentRole.TECHNICAL_ANALYST, AgentRole.SENTIMENT_ANALYST],
            AgentRole.MEAN_REVERSION_TRADER: [AgentRole.VOLATILITY_SPECIALIST, AgentRole.TECHNICAL_ANALYST],
            AgentRole.SENTIMENT_ANALYST: [AgentRole.MOMENTUM_TRADER, AgentRole.RISK_MANAGER],
            AgentRole.VOLATILITY_SPECIALIST: [AgentRole.MEAN_REVERSION_TRADER, AgentRole.RISK_MANAGER],
            AgentRole.TECHNICAL_ANALYST: [AgentRole.MOMENTUM_TRADER, AgentRole.MEAN_REVERSION_TRADER],
            AgentRole.MARKET_MAKER: [AgentRole.TECHNICAL_ANALYST, AgentRole.PORTFOLIO_OPTIMIZER],
            AgentRole.RISK_MANAGER: [AgentRole.VOLATILITY_SPECIALIST, AgentRole.PORTFOLIO_OPTIMIZER],
            AgentRole.PORTFOLIO_OPTIMIZER: [AgentRole.RISK_MANAGER, AgentRole.TECHNICAL_ANALYST]
        }
        return partners_map.get(role, [])

    def _get_risk_tolerance(self, role: AgentRole) -> str:
        """Get risk tolerance level."""
        tolerance_map = {
            AgentRole.MOMENTUM_TRADER: "high",
            AgentRole.MEAN_REVERSION_TRADER: "medium",
            AgentRole.SENTIMENT_ANALYST: "medium",
            AgentRole.VOLATILITY_SPECIALIST: "high",
            AgentRole.TECHNICAL_ANALYST: "medium",
            AgentRole.MARKET_MAKER: "low",
            AgentRole.RISK_MANAGER: "low",
            AgentRole.PORTFOLIO_OPTIMIZER: "medium"
        }
        return tolerance_map.get(role, "medium")

    def _get_time_horizon(self, role: AgentRole) -> str:
        """Get preferred time horizon."""
        horizon_map = {
            AgentRole.MOMENTUM_TRADER: "short_term",
            AgentRole.MEAN_REVERSION_TRADER: "short_term",
            AgentRole.SENTIMENT_ANALYST: "medium_term",
            AgentRole.VOLATILITY_SPECIALIST: "medium_term",
            AgentRole.TECHNICAL_ANALYST: "multi_timeframe",
            AgentRole.MARKET_MAKER: "ultra_short_term",
            AgentRole.RISK_MANAGER: "continuous",
            AgentRole.PORTFOLIO_OPTIMIZER: "long_term"
        }
        return horizon_map.get(role, "short_term")

    def _get_preferred_assets(self, role: AgentRole) -> List[str]:
        """Get preferred assets for each role - all roles can trade any symbols."""
        # All agents can trade any available symbols
        return ["all"]


class PortfolioOrchestrator:
    """Orchestrates portfolio-level coordination and agent role management."""

    def __init__(self):
        self.portfolio_goal = PortfolioGoal.MAXIMUM_PROFIT
        self.agent_personalities: Dict[str, AgentPersonality] = {}
        self.portfolio_value = 10000.0
        self.portfolio_risk_limit = 0.15  # 15% max drawdown
        self.agent_allocations: Dict[str, float] = {}
        self.collaboration_topics: List[Dict] = []

        # Initialize agent personalities
        self._initialize_agent_personalities()

    def _initialize_agent_personalities(self):
        """Initialize agent personalities based on registered agents."""
        # This would be called when agents register with the system
        # For now, we'll define the standard agent set
        standard_agents = {
            "trend-momentum-agent": AgentRole.MOMENTUM_TRADER,
            "strategy-optimization-agent": AgentRole.STRATEGY_OPTIMIZER,
            "financial-sentiment-agent": AgentRole.SENTIMENT_ANALYST,
            "market-prediction-agent": AgentRole.MARKET_PREDICTOR,
            "volume-microstructure-agent": AgentRole.VOLUME_ANALYST,
            "vpin-hft": AgentRole.VOLATILITY_SPECIALIST,
            "freqtrade": AgentRole.TECHNICAL_ANALYST,
            "hummingbot": AgentRole.MARKET_MAKER,
        }

        for agent_id, role in standard_agents.items():
            self.agent_personalities[agent_id] = AgentPersonality(agent_id, role)

        # Allocate portfolio based on roles
        self._allocate_portfolio_based_on_roles()

    def _allocate_portfolio_based_on_roles(self):
        """Allocate portfolio capital based on agent roles and risk tolerance."""
        total_allocation = 0
        base_allocation = self.portfolio_value * 0.8  # 80% for active trading

        # Risk-weighted allocations
        risk_weights = {
            "high": 0.15,    # 15% for high-risk agents
            "medium": 0.10,  # 10% for medium-risk agents
            "low": 0.05      # 5% for low-risk agents
        }

        for agent_id, personality in self.agent_personalities.items():
            risk_weight = risk_weights.get(personality.risk_tolerance, 0.10)
            allocation = base_allocation * risk_weight
            self.agent_allocations[agent_id] = allocation
            total_allocation += allocation

        # Allocate remaining capital to portfolio optimizer
        remaining = base_allocation - total_allocation
        if "portfolio_optimizer" in self.agent_allocations:
            self.agent_allocations["portfolio_optimizer"] += remaining
        else:
            # Distribute remaining capital equally
            equal_share = remaining / len(self.agent_allocations)
            for agent_id in self.agent_allocations:
                self.agent_allocations[agent_id] += equal_share

    async def coordinate_agent_collaboration(self, agent_id: str, topic: str, context: Dict = None):
        """Coordinate collaboration based on agent roles and expertise."""
        if agent_id not in self.agent_personalities:
            return

        personality = self.agent_personalities[agent_id]
        relevant_partners = personality.collaboration_partners

        # Create collaboration context
        collaboration_context = {
            "initiating_agent": agent_id,
            "agent_role": personality.role.value,
            "topic": topic,
            "expertise_area": personality.expertise,
            "relevant_partners": [partner.value for partner in relevant_partners],
            "portfolio_goal": self.portfolio_goal.value,
            "context": context or {},
            "timestamp": datetime.now().isoformat()
        }

        self.collaboration_topics.append(collaboration_context)

        # This would broadcast to relevant agents via MCP
        await self._broadcast_collaboration_opportunity(collaboration_context)

        logger.info(f"Coordinated collaboration: {agent_id} ({personality.role.value}) on topic: {topic}")

    async def _broadcast_collaboration_opportunity(self, collaboration_context: Dict):
        """Broadcast collaboration opportunity to relevant agents."""
        # This would use the MCP coordinator to broadcast
        # For now, just log the collaboration opportunity
        logger.info(f"Broadcasting collaboration: {collaboration_context}")

    def validate_agent_trade(self, agent_id: str, trade_details: Dict) -> bool:
        """Validate trade against portfolio constraints and agent role."""
        if agent_id not in self.agent_personalities:
            return False

        personality = self.agent_personalities[agent_id]

        # Check asset preferences
        symbol = trade_details.get("symbol", "")
        if personality.preferred_assets != ["all"] and symbol not in personality.preferred_assets:
            # Allow but log preference mismatch
            logger.debug(f"{agent_id} trading {symbol} outside preferred assets {personality.preferred_assets}")

        # Check position size against allocation
        notional = trade_details.get("notional", 0)
        allocated_capital = self.agent_allocations.get(agent_id, 0)
        max_position = allocated_capital * 0.05  # Max 5% of agent allocation

        if notional > max_position:
            logger.warning(f"{agent_id} position size ${notional} exceeds limit ${max_position}")
            return False

        # Check leverage against role risk tolerance
        leverage = trade_details.get("leverage", 1.0)
        max_leverage_by_risk = {
            "high": 10.0,
            "medium": 5.0,
            "low": 2.0
        }

        max_leverage = max_leverage_by_risk.get(personality.risk_tolerance, 5.0)
        if leverage > max_leverage:
            logger.warning(f"{agent_id} leverage {leverage}x exceeds role limit {max_leverage}x")
            return False

        return True

    def get_portfolio_status(self) -> Dict:
        """Get comprehensive portfolio status."""
        return {
            "portfolio_value": self.portfolio_value,
            "portfolio_goal": self.portfolio_goal.value,
            "risk_limit": self.portfolio_risk_limit,
            "agent_allocations": self.agent_allocations,
            "agent_roles": {
                agent_id: personality.role.value
                for agent_id, personality in self.agent_personalities.items()
            },
            "active_collaborations": len(self.collaboration_topics),
            "timestamp": datetime.now().isoformat()
        }

    def update_portfolio_value(self, new_value: float):
        """Update portfolio value and recalculate allocations."""
        self.portfolio_value = new_value
        self._allocate_portfolio_based_on_roles()

    async def optimize_portfolio_allocation(self):
        """Optimize portfolio allocation based on agent performance."""
        # This would analyze agent performance and reallocate capital
        # For now, maintain current allocations
        pass

    def get_agent_guidance(self, agent_id: str) -> Dict:
        """Get guidance for an agent based on their role and portfolio context."""
        if agent_id not in self.agent_personalities:
            return {"guidance": "Agent not recognized"}

        personality = self.agent_personalities[agent_id]

        return {
            "role": personality.role.value,
            "expertise": personality.expertise,
            "risk_tolerance": personality.risk_tolerance,
            "time_horizon": personality.time_horizon,
            "allocated_capital": self.agent_allocations.get(agent_id, 0),
            "preferred_assets": personality.preferred_assets,
            "portfolio_goal": self.portfolio_goal.value,
            "collaboration_partners": [p.value for p in personality.collaboration_partners],
            "guidance": self._generate_role_guidance(personality)
        }

    def _generate_role_guidance(self, personality: AgentPersonality) -> str:
        """Generate role-specific guidance."""
        base_guidance = f"As a {personality.role.value.replace('_', ' ')}, focus on {', '.join(personality.expertise)}. "

        if personality.risk_tolerance == "high":
            base_guidance += "You have high risk tolerance - pursue high-conviction opportunities. "
        elif personality.risk_tolerance == "medium":
            base_guidance += "Maintain balanced risk-reward approach. "
        else:
            base_guidance += "Prioritize capital preservation and steady returns. "

        base_guidance += f"Collaborate with {', '.join([p.value for p in personality.collaboration_partners])} for optimal results."

        return base_guidance


# Global orchestrator instance
_portfolio_orchestrator: Optional[PortfolioOrchestrator] = None


def get_portfolio_orchestrator() -> PortfolioOrchestrator:
    """Get or create global portfolio orchestrator instance."""
    global _portfolio_orchestrator
    if _portfolio_orchestrator is None:
        _portfolio_orchestrator = PortfolioOrchestrator()
    return _portfolio_orchestrator
