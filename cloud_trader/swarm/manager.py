"""
Swarm Intelligence Module.
Manages peer awareness, global exposure, and collaborative decision making.
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class AgentContext:
    id: str
    role: str
    current_sentiment: str  # BULLISH, BEARISH, NEUTRAL
    active_positions: List[str]  # Symbols
    last_win: float
    performance_score: float


@dataclass
class SwarmState:
    agents: Dict[str, AgentContext] = field(default_factory=dict)
    global_exposure: Dict[str, float] = field(default_factory=dict)  # Symbol -> Net Quantity
    last_update: float = 0.0


class SwarmManager:
    def __init__(self):
        self.state = SwarmState()

    def update_agent_state(
        self,
        agent_id: str,
        role: str,
        sentiment: str,
        positions: List[str],
        last_win: float,
        score: float,
    ):
        """Update an individual agent's state in the swarm."""
        self.state.agents[agent_id] = AgentContext(
            id=agent_id,
            role=role,
            current_sentiment=sentiment,
            active_positions=positions,
            last_win=last_win,
            performance_score=score,
        )
        self.state.last_update = time.time()
        self._recalc_global_exposure()

    def _recalc_global_exposure(self):
        """Aggregate exposure across all agents (simulated for now based on reported positions)."""
        # In a real system, we'd sum up actual quantities.
        # Here we just track "Sentiment Exposure" count.
        exposure = {}
        for agent in self.state.agents.values():
            for symbol in agent.active_positions:
                exposure[symbol] = exposure.get(symbol, 0) + (
                    1 if agent.current_sentiment == "BULLISH" else -1
                )
        self.state.global_exposure = exposure

    def get_swarm_context(self, requesting_agent_id: str, symbol: str) -> str:
        """Generate a context string for an agent about the swarm's stance on a symbol."""

        # 1. Peer Sentiment
        bulls = [
            a.id
            for a in self.state.agents.values()
            if a.current_sentiment == "BULLISH" and a.id != requesting_agent_id
        ]
        bears = [
            a.id
            for a in self.state.agents.values()
            if a.current_sentiment == "BEARISH" and a.id != requesting_agent_id
        ]

        sentiment_str = "Neutral"
        if len(bulls) > len(bears):
            sentiment_str = f"Bullish ({len(bulls)} peers including {bulls[:2]})"
        elif len(bears) > len(bulls):
            sentiment_str = f"Bearish ({len(bears)} peers including {bears[:2]})"

        # 2. Expert Opinion (Find highest performing agent)
        best_agent = max(
            self.state.agents.values(), key=lambda a: a.performance_score, default=None
        )
        expert_str = ""
        if best_agent and best_agent.id != requesting_agent_id:
            expert_str = f"Top performer '{best_agent.id}' is {best_agent.current_sentiment}."

        # 3. Exposure
        net_exp = self.state.global_exposure.get(symbol, 0)
        exposure_str = (
            "High Long Exposure"
            if net_exp > 2
            else "High Short Exposure" if net_exp < -2 else "Balanced Exposure"
        )

        return f"""
Swarm Intelligence Report:
- Overall Sentiment: {sentiment_str}
- {expert_str}
- Account Risk: {exposure_str}
- Directive: Align with swarm for trend, or fade if exposure is extreme (contrarian).
"""
