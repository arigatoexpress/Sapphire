
import asyncio
import logging
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .eliza_agent import AgentConfig, ElizaAgent, ModelProvider, Thesis

logger = logging.getLogger(__name__)

# Lazy import for RL agent
_rl_agent = None

def _get_rl_agent():
    global _rl_agent
    if _rl_agent is None:
        try:
            from ..rl.rl_agent import RLTradingAgent
            _rl_agent = RLTradingAgent()
        except Exception as e:
            logger.warning(f"RL agent not available: {e}")
    return _rl_agent


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
    - Weighted voting based on agent performance (Sigmoid)
    - Conflict resolution
    - Automated Debrief Cycles
    """

    def __init__(self, monitoring: Optional[Any] = None):
        self.agents: Dict[str, ElizaAgent] = {}
        self.monitoring = monitoring
        self.rl_weight = 0.3  # Weight for RL agent in consensus
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
                confidence_threshold=0.50,  # Lowered from 0.7
            ),
            AgentConfig(
                agent_id="sentiment-sage",
                name="Sentiment Sage",
                personality="contrarian",
                specialization="sentiment",
                primary_model=ModelProvider.GEMINI,
                confidence_threshold=0.45,  # Lowered from 0.65
            ),
            AgentConfig(
                agent_id="risk-guardian",
                name="Risk Guardian",
                personality="conservative",
                specialization="hybrid",
                primary_model=ModelProvider.GEMINI,
                confidence_threshold=0.55,  # Lowered from 0.75
            ),
            AgentConfig(
                agent_id="degen-hunter",
                name="Degen Hunter",
                personality="aggressive",
                specialization="orderflow",
                primary_model=ModelProvider.GEMINI,
                confidence_threshold=0.40,  # Lowered from 0.6 - aggressive scout
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

        # Get RL agent prediction and add as weighted vote
        rl_signal = await self._get_rl_prediction(symbol, market_data)

        # Calculate weighted votes
        return self._calculate_consensus(symbol, valid_theses, rl_signal)

    async def _get_rl_prediction(self, symbol: str, market_data: Optional[Dict]) -> Optional[Dict]:
        """Get prediction from RL agent."""
        rl_agent = _get_rl_agent()
        if not rl_agent:
            return None

        try:
            # Build observation from market data
            import numpy as np
            if market_data and 'prices' in market_data:
                prices = market_data['prices'][-30:]
                obs = np.array(prices, dtype=np.float32)
                # Pad if needed
                if len(obs) < 63:  # Env observation size
                    obs = np.pad(obs, (0, 63 - len(obs)))
            else:
                obs = np.zeros(63, dtype=np.float32)

            action = rl_agent.predict(obs)
            signal = rl_agent.action_to_signal(action)
            
            return {
                "signal": signal,
                "confidence": 0.7,  # RL confidence (can be trained)
                "source": "rl_ppo"
            }
        except Exception as e:
            logger.warning(f"RL prediction failed: {e}")
            return None

    def _calculate_consensus(self, symbol: str, theses: List[Thesis], rl_signal: Optional[Dict] = None) -> ConsensusResult:
        """Calculate consensus from multiple agent theses using Sigmoid weighting."""
        signal_scores = {"BUY": 0.0, "SELL": 0.0, "HOLD": 0.0}
        agent_votes = []

        # Sigmoid parameters - RELAXED for more trading activity
        k = 3  # Reduced from 5 - gentler sigmoid curve
        threshold = 0.35  # Lowered from 0.5 - more signals pass

        for thesis in theses:
            agent = self.agents.get(thesis.agent_id)
            win_rate = agent.get_win_rate() if agent else 0.5
            
            # Sigmoid Weighting: 1 / (1 + exp(-k * (confidence * win_rate - threshold)))
            # This pushes weights towards 0 or 1 based on performance x confidence
            try:
                x = thesis.confidence * win_rate
                weight = 1 / (1 + math.exp(-k * (x - threshold)))
            except OverflowError:
                weight = 0.0 if (thesis.confidence * win_rate) < threshold else 1.0

            signal_scores[thesis.signal] += weight

            agent_votes.append(
                {
                    "agent_id": thesis.agent_id,
                    "agent_name": agent.name if agent else "Unknown",
                    "signal": thesis.signal,
                    "confidence": thesis.confidence,
                    "weight": weight,
                    "reasoning": thesis.reasoning,
                }
            )

        # Add RL agent vote
        if rl_signal:
            rl_weight = self.rl_weight
            signal_scores[rl_signal["signal"]] += rl_weight
            agent_votes.append({
                "agent_id": "rl-ppo",
                "agent_name": "RL PPO Agent",
                "signal": rl_signal["signal"],
                "confidence": rl_signal["confidence"],
                "weight": rl_weight,
                "reasoning": "PPO model prediction",
            })

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

        # Consensus confidence (weighted average of confidence of supporters)
        supporters = [v for v in agent_votes if v["signal"] == winning_signal]
        if supporters:
            avg_conf = sum(v["confidence"] for v in supporters) / len(supporters)
        else:
            avg_conf = 0.0

        # Build reasoning
        reasoning = (
            f"{len(supporters)}/{len(theses)} agents agree (Score: {winning_score:.2f}): "
            + "; ".join(v["reasoning"][:50] for v in supporters)[:200]
        )

        result = ConsensusResult(
            symbol=symbol,
            signal=winning_signal,
            confidence=avg_conf,
            reasoning=reasoning,
            agent_votes=agent_votes,
            agreement_level=agreement,
        )
        
        # Log consensus for debugging zero-trade issues
        logger.info(
            f"🎯 Consensus for {symbol}: {winning_signal} "
            f"(conf={avg_conf:.2f}, agree={agreement:.2f}, score={winning_score:.2f})"
        )
        
        return result

    async def learn_from_trade(self, symbol: str, signal: str, pnl_pct: float):
        """Update all agents and run debrief cycle."""
        
        # 1. Debrief: Generate a lesson from the trade
        lesson = "N/A"
        try:
            # Use Quant Alpha (or first available) to generate a critique
            critique_agent = self.agents.get("quant-alpha") or next(iter(self.agents.values()))
            if critique_agent:
                prompt = f"""
                Analyze this trade outcome for {symbol}.
                Signal: {signal}
                PnL: {pnl_pct:.2%}
                
                Provide a concise, 1-sentence strategic lesson to improve future decisions.
                Format: "LESSON: [Your lesson here]"
                """
                response = await critique_agent.models.query(
                    prompt=prompt, 
                    primary=critique_agent.config.primary_model
                )
                text = response.get("text", "")
                if "LESSON:" in text:
                    lesson = text.split("LESSON:")[1].strip()
                elif text:
                    lesson = text.strip()
                    
        except Exception as e:
            logger.warning(f"Debrief failed: {e}")

        # 2. Update agents with the lesson
        for agent in self.agents.values():
            # Create a dummy thesis for learning
            thesis = Thesis(
                symbol=symbol,
                signal=signal,
                confidence=0.5,
                reasoning=f"Trace outcome. Lesson: {lesson}",
                agent_id=agent.id,
            )
            # We inject the lesson into the memory via the thesis reasoning or a separate field
            # ElizaAgent.learn_from_trade calls memory.store which saves the thesis reasoning and a hardcoded "lesson".
            # I should hack ElizaAgent's learn_from_trade or pass it here.
            # ElizaAgent.learn_from_trade logic: 
            # lesson = "Successful strategy" if pnl_pct > 0 else "Review entry criteria"
            # It ignores the passed thesis reasoning for the 'lesson' field in memory, but stores 'reasoning'.
            # I'll rely on the 'reasoning' field of the thesis which now contains the lesson.
            
            await agent.learn_from_trade(thesis, pnl_pct)

    def get_agent_stats(self) -> List[Dict]:
        """Get statistics for all agents."""
        return [agent.get_stats() for agent in self.agents.values()]

    async def stop(self):
        """Stop all agents."""
        logger.info("🎭 AgentOrchestrator stopped")


