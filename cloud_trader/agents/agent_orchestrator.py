"""
Sapphire V2 Agent Orchestrator
Manages multiple ElizaAgents and produces consensus decisions.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .eliza_agent import AgentConfig, ElizaAgent, ModelProvider, Thesis

logger = logging.getLogger(__name__)


@dataclass
class ConsensusResult:
    """Result of multi-agent consensus."""

    symbol: str
    signal: str  # BUY, SELL, HOLD
    confidence: float
    reasoning: str
    agent_votes: List[Dict]
    agreement_level: float  # 0.0-1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "signal": self.signal,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "agent_votes": self.agent_votes,
            "agreement_level": self.agreement_level,
        }


class AgentOrchestrator:
    """
    Manages a swarm of ElizaAgents and produces consensus decisions.

    Features:
    - Multiple specialized agents with different personalities
    - Weighted voting based on agent performance
    - Conflict resolution
    """

    def __init__(self, monitoring: Optional[Any] = None):
        self.agents: Dict[str, ElizaAgent] = {}
        self.monitoring = monitoring
        self._initialize_default_agents()
        logger.info(f"🎭 AgentOrchestrator initialized with {len(self.agents)} agents")

    def _initialize_default_agents(self):
        """Create the default agent roster."""
        default_agents = [
            AgentConfig(
                agent_id="quant-alpha",
                name="Quant Alpha",
                personality="analytical",
                specialization="technical",
                primary_model=ModelProvider.GEMINI,
                confidence_threshold=0.7,
            ),
            AgentConfig(
                agent_id="sentiment-sage",
                name="Sentiment Sage",
                personality="contrarian",
                specialization="sentiment",
                primary_model=ModelProvider.GEMINI,
                confidence_threshold=0.65,
            ),
            AgentConfig(
                agent_id="risk-guardian",
                name="Risk Guardian",
                personality="conservative",
                specialization="hybrid",
                primary_model=ModelProvider.GEMINI,
                confidence_threshold=0.75,
            ),
            AgentConfig(
                agent_id="degen-hunter",
                name="Degen Hunter",
                personality="aggressive",
                specialization="orderflow",
                primary_model=ModelProvider.GEMINI,
                confidence_threshold=0.6,
            ),
        ]

        for config in default_agents:
            self.agents[config.agent_id] = ElizaAgent(config)
            if self.monitoring:
                self.monitoring.register_agent(config.agent_id, config.name)

    async def get_consensus(
        self, symbol: str, context: str = "entry", market_data: Optional[Dict] = None
    ) -> Optional[ConsensusResult]:
        """
        Get consensus decision from all agents.

        Args:
            symbol: Trading pair to analyze
            context: "entry" or "exit_check"
            market_data: Optional market data to share with agents
        """
        if not self.agents:
            return None

        # Gather all agent analyses concurrently
        tasks = []
        for agent in self.agents.values():
            tasks.append(agent.analyze(symbol, market_data))

        theses = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out errors
        valid_theses: List[Thesis] = []
        for thesis in theses:
            if isinstance(thesis, Thesis):
                valid_theses.append(thesis)
            elif isinstance(thesis, Exception):
                logger.warning(f"Agent analysis failed: {thesis}")

        if not valid_theses:
            return None

        # Calculate weighted votes
        return self._calculate_consensus(symbol, valid_theses)

    def _calculate_consensus(self, symbol: str, theses: List[Thesis]) -> ConsensusResult:
        """Calculate consensus from multiple agent theses."""
        # Vote counts weighted by confidence and agent performance
        signal_scores = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0}
        agent_votes = []

        for thesis in theses:
            agent = self.agents.get(thesis.agent_id)
            win_rate = agent.get_win_rate() if agent else 0.5

            # Weight = confidence * (0.5 + 0.5 * win_rate)
            # This gives experienced agents more influence
            weight = thesis.confidence * (0.5 + 0.5 * win_rate)
            signal_scores[thesis.signal] += weight

            agent_votes.append(
                {
                    "agent_id": thesis.agent_id,
                    "agent_name": agent.name if agent else "Unknown",
                    "signal": thesis.signal,
                    "confidence": thesis.confidence,
                    "reasoning": thesis.reasoning,
                }
            )

        # Determine winning signal
        total_score = sum(signal_scores.values())
        if total_score == 0:
            return ConsensusResult(
                symbol=symbol,
                signal="HOLD",
                confidence=0.0,
                reasoning="No valid agent votes",
                agent_votes=agent_votes,
                agreement_level=0.0,
            )

        winning_signal = max(signal_scores.keys(), key=lambda s: signal_scores[s])
        winning_score = signal_scores[winning_signal]

        # Calculate agreement level
        agreement = winning_score / total_score

        # Consensus confidence
        consensus_confidence = winning_score / len(theses) if theses else 0

        # Build reasoning
        supporters = [v["agent_name"] for v in agent_votes if v["signal"] == winning_signal]
        reasoning = (
            f"{len(supporters)}/{len(theses)} agents agree: "
            + "; ".join(v["reasoning"][:50] for v in agent_votes if v["signal"] == winning_signal)[
                :200
            ]
        )

        return ConsensusResult(
            symbol=symbol,
            signal=winning_signal,
            confidence=consensus_confidence,
            reasoning=reasoning,
            agent_votes=agent_votes,
            agreement_level=agreement,
        )

    async def learn_from_trade(self, symbol: str, signal: str, pnl_pct: float):
        """Update all agents that participated in a trade."""
        for agent in self.agents.values():
            # Create a dummy thesis for learning
            thesis = Thesis(
                symbol=symbol,
                signal=signal,
                confidence=0.5,
                reasoning="Trade outcome feedback",
                agent_id=agent.id,
            )
            await agent.learn_from_trade(thesis, pnl_pct)

    def get_agent_stats(self) -> List[Dict]:
        """Get statistics for all agents."""
        return [agent.get_stats() for agent in self.agents.values()]

    async def stop(self):
        """Stop all agents."""
        logger.info("🎭 AgentOrchestrator stopped")
