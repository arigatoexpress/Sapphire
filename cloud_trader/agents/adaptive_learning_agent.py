"""
V2.3 Adaptive Learning Agent - Self-Improving Autonomous Trader

Instead of hardcoded strategies (VPIN, Momentum, etc.), agents:
1. Learn optimal trading patterns through experience
2. Evolve their own strategies based on what works
3. Adapt to their platform's unique characteristics
4. Continuously improve through episodic memory

Each platform trader (Drift, Hyperliquid, Aster, Symphony, Lighter) develops
its own trading methodology organically through trial, error, and success.
"""

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class TradeExperience:
    """Record of a single trade experience for learning."""
    timestamp: float
    symbol: str
    platform: str
    side: str  # BUY/SELL
    entry_price: float
    exit_price: Optional[float] = None
    pnl: float = 0.0
    duration_seconds: float = 0.0

    # Market conditions at entry
    volatility: float = 0.0
    trend_strength: float = 0.0
    volume_level: float = 0.0

    # Agent decision factors
    confidence: float = 0.0
    leverage_used: float = 1.0

    # Outcome
    profitable: bool = False
    closed: bool = False

    # What worked / didn't work
    learned_pattern: Optional[str] = None


@dataclass
class StrategyPattern:
    """A discovered trading pattern that works."""
    pattern_id: str
    description: str
    success_rate: float = 0.0
    avg_pnl: float = 0.0
    times_used: int = 0

    # Conditions when this pattern works best
    optimal_volatility_range: tuple = (0.0, 1.0)
    optimal_trend_strength: float = 0.5
    preferred_symbols: List[str] = field(default_factory=list)

    # Evolution tracking
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)
    last_success: float = 0.0


class AdaptiveLearningAgent:
    """
    Self-improving trader that discovers its own strategies.

    V2.3 Philosophy:
    - NO hardcoded strategies (no VPIN, Momentum, etc.)
    - Agent learns what works on its specific platform
    - Builds repertoire of successful patterns
    - Evolves strategy based on continuous feedback
    - Platform-specific optimization through experience

    Learning Process:
    1. Try different approaches (exploration)
    2. Record what works (experience memory)
    3. Identify successful patterns
    4. Exploit winning strategies
    5. Continuously adapt and improve
    """

    def __init__(
        self,
        agent_id: str,
        platform: str,
        max_experiences: int = 500
    ):
        self.agent_id = agent_id
        self.platform = platform.lower()
        self.max_experiences = max_experiences

        # Experience memory
        self.experiences: deque = deque(maxlen=max_experiences)

        # Discovered patterns (agent's learned strategies)
        self.discovered_patterns: Dict[str, StrategyPattern] = {}

        # Performance tracking
        self.total_trades = 0
        self.profitable_trades = 0
        self.total_pnl = 0.0

        # Exploration vs Exploitation balance
        self.exploration_rate = 0.3  # 30% try new things, 70% use what works

        # Learning metrics
        self.learning_stats = {
            "patterns_discovered": 0,
            "successful_patterns": 0,
            "avg_pattern_success_rate": 0.0,
            "strategy_evolution_count": 0
        }

        logger.info(
            f"🧠 [LEARNING] {agent_id} initialized for {platform} "
            f"- Will discover optimal strategies through experience"
        )

    def record_trade_experience(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: Optional[float],
        pnl: float,
        duration_seconds: float,
        confidence: float,
        volatility: float = 0.0,
        trend_strength: float = 0.0,
        volume_level: float = 0.0,
        leverage_used: float = 1.0
    ):
        """Record a trade experience for learning."""

        profitable = pnl > 0

        experience = TradeExperience(
            timestamp=time.time(),
            symbol=symbol,
            platform=self.platform,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl=pnl,
            duration_seconds=duration_seconds,
            volatility=volatility,
            trend_strength=trend_strength,
            volume_level=volume_level,
            confidence=confidence,
            leverage_used=leverage_used,
            profitable=profitable,
            closed=exit_price is not None
        )

        self.experiences.append(experience)
        self.total_trades += 1
        if profitable:
            self.profitable_trades += 1
        self.total_pnl += pnl

        # Analyze and learn from experience
        if experience.closed:
            self._learn_from_experience(experience)

        logger.debug(
            f"📝 [LEARNING] {self.agent_id} recorded experience: "
            f"{symbol} {side} PnL: ${pnl:.2f} ({'✅' if profitable else '❌'})"
        )

    def _learn_from_experience(self, experience: TradeExperience):
        """
        Analyze experience and discover/update patterns.

        This is where the magic happens - agent figures out what works!
        """

        # Look for similar past experiences
        similar = self._find_similar_experiences(experience)

        if len(similar) >= 3:  # Need at least 3 similar trades to identify pattern
            # Calculate success rate of this type of trade
            profitable_count = sum(1 for exp in similar if exp.profitable)
            success_rate = profitable_count / len(similar)
            avg_pnl = sum(exp.pnl for exp in similar) / len(similar)

            # If this type of trade works well, create/update a pattern
            if success_rate >= 0.60 and avg_pnl > 0:
                pattern_id = self._generate_pattern_id(experience)

                if pattern_id in self.discovered_patterns:
                    # Update existing pattern
                    pattern = self.discovered_patterns[pattern_id]
                    pattern.success_rate = success_rate
                    pattern.avg_pnl = avg_pnl
                    pattern.times_used += 1
                    pattern.last_used = time.time()
                    if experience.profitable:
                        pattern.last_success = time.time()
                else:
                    # Discover new winning pattern!
                    pattern = StrategyPattern(
                        pattern_id=pattern_id,
                        description=self._describe_pattern(experience, similar),
                        success_rate=success_rate,
                        avg_pnl=avg_pnl,
                        times_used=len(similar),
                        optimal_volatility_range=(
                            min(e.volatility for e in similar),
                            max(e.volatility for e in similar)
                        ),
                        optimal_trend_strength=sum(e.trend_strength for e in similar) / len(similar),
                        preferred_symbols=list(set(e.symbol for e in similar))
                    )
                    self.discovered_patterns[pattern_id] = pattern
                    self.learning_stats["patterns_discovered"] += 1

                    logger.info(
                        f"✨ [LEARNING] {self.agent_id} discovered new pattern: "
                        f"{pattern.description} (success_rate: {success_rate:.1%}, "
                        f"avg_pnl: ${avg_pnl:.2f})"
                    )

    def _find_similar_experiences(
        self,
        experience: TradeExperience,
        similarity_threshold: float = 0.7
    ) -> List[TradeExperience]:
        """Find similar past experiences based on market conditions."""

        similar = []

        for past_exp in self.experiences:
            if not past_exp.closed:
                continue

            # Calculate similarity score
            similarity = 0.0
            factors = 0

            # Same symbol?
            if past_exp.symbol == experience.symbol:
                similarity += 0.4
            factors += 1

            # Similar volatility?
            vol_diff = abs(past_exp.volatility - experience.volatility)
            if vol_diff < 0.2:
                similarity += 0.3
            factors += 1

            # Similar trend strength?
            trend_diff = abs(past_exp.trend_strength - experience.trend_strength)
            if trend_diff < 0.3:
                similarity += 0.3
            factors += 1

            # Normalize similarity
            if factors > 0:
                similarity = similarity / factors

            if similarity >= similarity_threshold:
                similar.append(past_exp)

        return similar

    def _generate_pattern_id(self, experience: TradeExperience) -> str:
        """Generate unique ID for a pattern type."""

        # Categorize volatility
        vol_cat = "low" if experience.volatility < 0.3 else ("high" if experience.volatility > 0.7 else "med")

        # Categorize trend
        trend_cat = "strong" if abs(experience.trend_strength) > 0.6 else "weak"

        return f"{experience.symbol}_{vol_cat}vol_{trend_cat}trend"

    def _describe_pattern(
        self,
        experience: TradeExperience,
        similar: List[TradeExperience]
    ) -> str:
        """Generate human-readable description of discovered pattern."""

        avg_vol = sum(e.volatility for e in similar) / len(similar)
        avg_trend = sum(e.trend_strength for e in similar) / len(similar)

        vol_desc = "low volatility" if avg_vol < 0.3 else ("high volatility" if avg_vol > 0.7 else "moderate volatility")
        trend_desc = "strong trend" if abs(avg_trend) > 0.6 else "ranging market"

        return f"{experience.symbol} trades in {vol_desc} {trend_desc} conditions"

    def should_explore(self) -> bool:
        """Decide whether to explore new strategies or exploit known winners."""
        import random
        return random.random() < self.exploration_rate

    def get_best_pattern_for_conditions(
        self,
        symbol: str,
        volatility: float,
        trend_strength: float
    ) -> Optional[StrategyPattern]:
        """Get the best known pattern for current market conditions."""

        if not self.discovered_patterns:
            return None  # No patterns learned yet, must explore

        # Filter patterns that match current conditions
        matching = []
        for pattern in self.discovered_patterns.values():
            # Check if symbol matches or is in preferred list
            if symbol in pattern.preferred_symbols or not pattern.preferred_symbols:
                # Check if volatility in range
                if pattern.optimal_volatility_range[0] <= volatility <= pattern.optimal_volatility_range[1]:
                    # Check if trend strength is similar
                    if abs(pattern.optimal_trend_strength - trend_strength) < 0.3:
                        matching.append(pattern)

        if not matching:
            return None

        # Return pattern with best success rate and recent usage
        return max(matching, key=lambda p: p.success_rate * 0.7 + (0.3 if time.time() - p.last_success < 3600 else 0))

    def get_learning_summary(self) -> dict:
        """Get summary of agent's learning progress."""

        win_rate = self.profitable_trades / self.total_trades if self.total_trades > 0 else 0.0

        successful_patterns = [p for p in self.discovered_patterns.values() if p.success_rate >= 0.60]
        avg_pattern_success = (
            sum(p.success_rate for p in successful_patterns) / len(successful_patterns)
            if successful_patterns else 0.0
        )

        return {
            "agent_id": self.agent_id,
            "platform": self.platform,
            "total_trades": self.total_trades,
            "win_rate": win_rate,
            "total_pnl": self.total_pnl,
            "patterns_discovered": len(self.discovered_patterns),
            "successful_patterns": len(successful_patterns),
            "avg_pattern_success_rate": avg_pattern_success,
            "exploration_rate": self.exploration_rate,
            "is_learning": self.total_trades < 100,  # Still in heavy learning phase
            "patterns": [
                {
                    "id": p.pattern_id,
                    "description": p.description,
                    "success_rate": p.success_rate,
                    "avg_pnl": p.avg_pnl,
                    "times_used": p.times_used
                }
                for p in sorted(
                    self.discovered_patterns.values(),
                    key=lambda x: x.success_rate,
                    reverse=True
                )[:5]  # Top 5 patterns
            ]
        }


def get_adaptive_agent(agent_id: str, platform: str) -> AdaptiveLearningAgent:
    """Get or create adaptive learning agent for a platform."""
    _agents = {}

    key = f"{agent_id}_{platform}"
    if key not in _agents:
        _agents[key] = AdaptiveLearningAgent(agent_id, platform)

    return _agents[key]
