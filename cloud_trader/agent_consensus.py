"""Advanced agent consensus voting system for multi-agent decision making."""

from __future__ import annotations

import asyncio
import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .market_regime import MarketRegime, RegimeMetrics
from .time_sync import get_timestamp_us

logger = logging.getLogger(__name__)


class ConsensusMethod(Enum):
    """Methods for reaching consensus among agents."""

    MAJORITY_VOTE = "majority_vote"
    WEIGHTED_VOTE = "weighted_vote"
    BAYESIAN_FUSION = "bayesian_fusion"
    DELPHI_METHOD = "delphi_method"
    ADAPTIVE_WEIGHTING = "adaptive_weighting"


class SignalType(Enum):
    """Types of trading signals that can be voted on."""

    ENTRY_LONG = "entry_long"
    ENTRY_SHORT = "entry_short"
    EXIT_LONG = "exit_long"
    EXIT_SHORT = "exit_short"
    HOLD = "hold"
    RISK_ADJUSTMENT = "risk_adjustment"


@dataclass
class AgentSignal:
    """Individual agent signal with confidence and metadata."""

    agent_id: str
    signal_type: SignalType
    confidence: float  # 0-1
    strength: float  # Signal strength/intensity
    symbol: str
    timestamp_us: int
    reasoning: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "agent_id": self.agent_id,
            "signal_type": self.signal_type.value,
            "confidence": self.confidence,
            "strength": self.strength,
            "symbol": self.symbol,
            "timestamp_us": self.timestamp_us,
            "reasoning": self.reasoning,
            "metadata": self.metadata or {},
        }


@dataclass
class ConsensusResult:
    """Result of consensus voting among agents."""

    winning_signal: Optional[SignalType]
    consensus_confidence: float  # 0-1
    agreement_level: float  # 0-1 (unanimity level)
    participation_rate: float  # 0-1 (agents that voted)
    total_votes: int
    method_used: ConsensusMethod
    symbol: str
    timestamp_us: int
    agent_votes: Dict[str, AgentSignal]
    reasoning: str

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "winning_signal": self.winning_signal.value if self.winning_signal else None,
            "consensus_confidence": self.consensus_confidence,
            "agreement_level": self.agreement_level,
            "participation_rate": self.participation_rate,
            "total_votes": self.total_votes,
            "method_used": self.method_used.value,
            "symbol": self.symbol,
            "timestamp_us": self.timestamp_us,
            "agent_votes": {aid: signal.to_dict() for aid, signal in self.agent_votes.items()},
            "reasoning": self.reasoning,
        }


@dataclass
class AgentPerformance:
    """Performance metrics for individual agents."""

    agent_id: str
    win_rate: float
    avg_return: float
    sharpe_ratio: float
    max_drawdown: float
    total_trades: int
    confidence_accuracy: float  # How well confidence predicts outcomes
    regime_performance: Dict[MarketRegime, float]  # Performance by regime
    last_updated: int

    def calculate_weight(self, base_weight: float = 1.0) -> float:
        """Calculate dynamic weight based on performance metrics."""
        # Weight based on multiple factors
        win_weight = min(2.0, self.win_rate * 1.5 + 0.5)  # 0.5 to 2.0
        return_weight = min(2.0, max(0.1, self.avg_return * 10 + 1.0))  # 0.1 to 2.0
        risk_weight = min(2.0, max(0.1, (1.0 - self.max_drawdown) * 1.5))  # 0.1 to 2.0

        # Combine weights with base weight
        combined_weight = (win_weight * 0.4 + return_weight * 0.4 + risk_weight * 0.2) * base_weight

        return max(0.1, min(3.0, combined_weight))  # Clamp between 0.1 and 3.0


class AgentConsensusEngine:
    """
    Advanced multi-agent consensus voting system.
    Aggregates signals from multiple AI agents with adaptive weighting and conflict resolution.
    """

    def __init__(self):
        # Agent registry and performance tracking
        self.agent_registry: Dict[str, Dict[str, Any]] = {}
        self.agent_performance: Dict[str, AgentPerformance] = {}
        self.agent_weights: Dict[str, float] = defaultdict(lambda: 1.0)

        # Consensus history and learning
        self.consensus_history: List[ConsensusResult] = []
        self.signal_outcomes: Dict[str, List[Tuple[ConsensusResult, float]]] = defaultdict(list)

        # Voting parameters
        self.min_participation_rate = 0.6  # Require 60% agent participation
        self.min_consensus_threshold = 0.7  # Require 70% agreement for strong signal
        self.adaptive_learning_rate = 0.1

        # Regime-specific adjustments
        self.regime_weights = {
            MarketRegime.TRENDING_UP: {"momentum_agents": 1.3, "mean_reversion": 0.7},
            MarketRegime.TRENDING_DOWN: {"momentum_agents": 1.3, "mean_reversion": 0.7},
            MarketRegime.RANGING: {"momentum_agents": 0.7, "mean_reversion": 1.3},
            MarketRegime.VOLATILE: {"high_confidence_only": True, "reduce_participation": True},
            MarketRegime.CALM: {"all_agents_equal": True},
        }

        # Signal type compatibility and conflict resolution
        self.signal_conflicts = self._initialize_signal_conflicts()

        # Pending signals for the next voting round
        self.pending_signals: Dict[str, List[AgentSignal]] = defaultdict(list)

    def _initialize_signal_conflicts(self) -> Dict[Tuple[SignalType, SignalType], float]:
        """Initialize signal conflict matrix."""
        conflicts = {}

        # Entry conflicts
        conflicts[(SignalType.ENTRY_LONG, SignalType.ENTRY_SHORT)] = 1.0  # Complete conflict
        conflicts[(SignalType.EXIT_LONG, SignalType.ENTRY_LONG)] = 0.8  # Strong conflict
        conflicts[(SignalType.EXIT_SHORT, SignalType.ENTRY_SHORT)] = 0.8  # Strong conflict

        # Make symmetric
        for (sig1, sig2), conflict in list(conflicts.items()):
            conflicts[(sig2, sig1)] = conflict

        return conflicts

    def register_agent(
        self, agent_id: str, agent_type: str, specialization: str, base_weight: float = 1.0
    ) -> None:
        """Register an agent in the consensus system."""
        self.agent_registry[agent_id] = {
            "type": agent_type,
            "specialization": specialization,
            "base_weight": base_weight,
            "registered_at": get_timestamp_us(),
        }

        # Initialize performance tracking
        self.agent_performance[agent_id] = AgentPerformance(
            agent_id=agent_id,
            win_rate=0.5,  # Start neutral
            avg_return=0.0,
            sharpe_ratio=1.0,
            max_drawdown=0.1,
            total_trades=0,
            confidence_accuracy=0.5,
            regime_performance={regime: 0.5 for regime in MarketRegime},
            last_updated=get_timestamp_us(),
        )

        logger.info(f"Registered agent {agent_id} ({agent_type}: {specialization})")

    def submit_signal(self, signal: AgentSignal) -> None:
        """Submit a signal from an agent for consensus consideration."""
        print(f"🔔 SUBMIT_SIGNAL: {signal.agent_id} → {signal.symbol} {signal.signal_type.value} ({signal.confidence:.2f})")
        
        # Validate agent is registered
        if signal.agent_id not in self.agent_registry:
            print(f"❌ REJECTED: Agent {signal.agent_id} not registered! Registry has: {list(self.agent_registry.keys())}")
            logger.warning(f"Received signal from unregistered agent: {signal.agent_id}")
            return

        # Store signal with timestamp
        signal.timestamp_us = signal.timestamp_us or get_timestamp_us()

        # Add to pending aggregation
        self.pending_signals[signal.symbol].append(signal)
        
        print(f"✅ SIGNAL ADDED: {signal.symbol} now has {len(self.pending_signals[signal.symbol])} pending signals")

        # Signal will be processed in consensus voting
        logger.debug(
            f"Received signal from {signal.agent_id}: {signal.signal_type.value} "
            f"({signal.confidence:.2f}) for {signal.symbol}"
        )

    async def conduct_consensus_vote(
        self, symbol: str, regime: Optional[RegimeMetrics] = None, max_wait_time: int = 1000000
    ) -> Optional[ConsensusResult]:
        """
        Conduct a consensus vote among all registered agents using PENDING signals.
        """
        start_time = get_timestamp_us()

        # 1. Retrieve and consume signals for this symbol
        agent_signals = self.pending_signals.pop(symbol, [])

        if not agent_signals:
            return None

        # Apply regime-specific filtering and weighting
        filtered_signals, weights = self._apply_regime_filtering(agent_signals, regime)

        # Conduct consensus voting
        consensus_result = self._conduct_voting(filtered_signals, weights, symbol)

        # Store result for learning
        self.consensus_history.append(consensus_result)
        if len(self.consensus_history) > 1000:
            self.consensus_history = self.consensus_history[-1000:]

        return consensus_result

    # MOCK METHODS REMOVED

    def _apply_regime_filtering(
        self, signals: List[AgentSignal], regime: Optional[RegimeMetrics]
    ) -> Tuple[List[AgentSignal], Dict[str, float]]:
        """Apply regime-specific filtering and weighting to signals."""

        filtered_signals = signals.copy()
        weights = {}

        for signal in filtered_signals:
            base_weight = self.agent_weights[signal.agent_id]

            # Apply regime adjustments
            if regime:
                regime_adjustments = self.regime_weights.get(regime.regime, {})

                # Reduce weight for conflicting strategies in certain regimes
                agent_info = self.agent_registry[signal.agent_id]
                agent_type = agent_info["specialization"]

                if regime.regime == MarketRegime.VOLATILE and regime_adjustments.get(
                    "high_confidence_only"
                ):
                    # In volatile markets, only consider high-confidence signals
                    if signal.confidence < 0.7:
                        filtered_signals.remove(signal)
                        continue

                if regime.regime == MarketRegime.VOLATILE and regime_adjustments.get(
                    "reduce_participation"
                ):
                    # Reduce participation in volatile markets
                    base_weight *= 0.8

                # Apply specialization-based adjustments
                for key, multiplier in regime_adjustments.items():
                    if key in agent_type or agent_type in key:
                        base_weight *= multiplier

            # Apply performance-based weighting
            if signal.agent_id in self.agent_performance:
                performance_weight = self.agent_performance[signal.agent_id].calculate_weight(
                    base_weight
                )
                weights[signal.agent_id] = performance_weight
            else:
                weights[signal.agent_id] = base_weight

        return filtered_signals, weights

    def _conduct_voting(
        self, signals: List[AgentSignal], weights: Dict[str, float], symbol: str
    ) -> ConsensusResult:
        """Conduct the actual consensus voting using the specified method."""

        if not signals:
            return ConsensusResult(
                winning_signal=None,
                consensus_confidence=0.0,
                agreement_level=0.0,
                participation_rate=0.0,
                total_votes=0,
                method_used=ConsensusMethod.WEIGHTED_VOTE,
                symbol=symbol,
                timestamp_us=get_timestamp_us(),
                agent_votes={},
                reasoning="No signals received",
            )

        # Group signals by type
        signal_groups: Dict[SignalType, List[Tuple[AgentSignal, float]]] = defaultdict(list)

        for signal in signals:
            weight = weights.get(signal.agent_id, 1.0)
            signal_groups[signal.signal_type].append((signal, weight))

        # Calculate weighted scores for each signal type
        signal_scores = {}
        total_weight = sum(weights.values())

        for signal_type, signal_list in signal_groups.items():
            weighted_confidence = sum(signal.confidence * weight for signal, weight in signal_list)
            weighted_strength = sum(signal.strength * weight for signal, weight in signal_list)
            total_type_weight = sum(weight for _, weight in signal_list)

            # Normalize by participation
            participation_factor = total_type_weight / total_weight if total_weight > 0 else 0

            signal_scores[signal_type] = {
                "weighted_confidence": (
                    weighted_confidence / total_type_weight if total_type_weight > 0 else 0
                ),
                "weighted_strength": (
                    weighted_strength / total_type_weight if total_type_weight > 0 else 0
                ),
                "participation": participation_factor,
                "votes": len(signal_list),
            }

        # Find winning signal
        if not signal_scores:
            winning_signal = None
            max_score = 0
        else:
            # Score = confidence * strength * participation
            signal_rankings = {}
            for signal_type, scores in signal_scores.items():
                score = (
                    scores["weighted_confidence"]
                    * scores["weighted_strength"]
                    * scores["participation"]
                )
                signal_rankings[signal_type] = score

            winning_signal = max(signal_rankings, key=signal_rankings.get)
            max_score = signal_rankings[winning_signal]

        # Calculate agreement level (concentration of votes on winning signal)
        if signal_scores and winning_signal:
            winning_participation = signal_scores[winning_signal]["participation"]
            total_participation = sum(scores["participation"] for scores in signal_scores.values())
            agreement_level = (
                winning_participation / total_participation if total_participation > 0 else 0
            )
        else:
            agreement_level = 0

        # Calculate participation rate
        expected_agents = len(self.agent_registry)
        actual_agents = len(signals)
        participation_rate = actual_agents / expected_agents if expected_agents > 0 else 0

        # Build agent votes dict
        agent_votes = {signal.agent_id: signal for signal in signals}

        # Generate reasoning
        reasoning = self._generate_consensus_reasoning(
            winning_signal, max_score, agreement_level, participation_rate, signal_scores
        )

        return ConsensusResult(
            winning_signal=winning_signal,
            consensus_confidence=min(1.0, max_score),
            agreement_level=agreement_level,
            participation_rate=participation_rate,
            total_votes=len(signals),
            method_used=ConsensusMethod.WEIGHTED_VOTE,
            symbol=symbol,
            timestamp_us=get_timestamp_us(),
            agent_votes=agent_votes,
            reasoning=reasoning,
        )

    def _generate_consensus_reasoning(
        self,
        winning_signal: Optional[SignalType],
        max_score: float,
        agreement_level: float,
        participation_rate: float,
        signal_scores: Dict,
    ) -> str:
        """Generate human-readable reasoning for consensus result."""

        if not winning_signal:
            return "No consensus reached - insufficient signals or participation"

        reasons = [f"Winning signal: {winning_signal.value}"]

        if max_score > 0.8:
            reasons.append("Strong consensus with high confidence")
        elif max_score > 0.6:
            reasons.append("Moderate consensus achieved")
        else:
            reasons.append("Weak consensus - low confidence")

        if agreement_level > 0.8:
            reasons.append("High agreement among participating agents")
        elif agreement_level > 0.6:
            reasons.append("Moderate agreement level")
        else:
            reasons.append("Low agreement - potential conflicts")

        if participation_rate < self.min_participation_rate:
            reasons.append(f"Low participation rate ({participation_rate:.1%})")

        # Add signal breakdown
        signal_breakdown = []
        for signal_type, scores in signal_scores.items():
            signal_breakdown.append(f"{signal_type.value}: {scores['votes']} votes")

        if signal_breakdown:
            reasons.append(f"Signal breakdown: {', '.join(signal_breakdown)}")

        return "; ".join(reasons)

    def update_performance_feedback(
        self,
        consensus_result: ConsensusResult,
        actual_outcome: float,
        regime: Optional[MarketRegime],
    ) -> None:
        """
        Update agent performance based on consensus outcome.
        actual_outcome: realized P&L or signal accuracy (positive = good outcome)
        """

        # Store outcome for learning
        outcome_key = f"{consensus_result.symbol}_{consensus_result.timestamp_us}"
        self.signal_outcomes[outcome_key].append((consensus_result, actual_outcome))

        # Update individual agent performance
        for agent_id, signal in consensus_result.agent_votes.items():
            if agent_id not in self.agent_performance:
                continue

            perf = self.agent_performance[agent_id]

            # Update win rate based on signal alignment with outcome
            signal_correct = self._evaluate_signal_correctness(
                signal, consensus_result.winning_signal, actual_outcome
            )

            # Exponential moving average for win rate
            alpha = self.adaptive_learning_rate
            perf.win_rate = alpha * (1.0 if signal_correct else 0.0) + (1 - alpha) * perf.win_rate

            # Update returns
            signal_contribution = signal.confidence * signal.strength
            perf.avg_return = (
                alpha * (actual_outcome * signal_contribution) + (1 - alpha) * perf.avg_return
            )

            # Update regime-specific performance
            if regime:
                regime_correct = 1.0 if signal_correct else 0.0
                perf.regime_performance[regime] = (
                    alpha * regime_correct + (1 - alpha) * perf.regime_performance[regime]
                )

            # Update confidence accuracy
            confidence_alignment = abs(signal.confidence - (1.0 if signal_correct else 0.0))
            perf.confidence_accuracy = (
                alpha * (1.0 - confidence_alignment) + (1 - alpha) * perf.confidence_accuracy
            )

            perf.total_trades += 1
            perf.last_updated = get_timestamp_us()

        # Update agent weights based on new performance
        self._update_agent_weights()

    def _evaluate_signal_correctness(
        self, signal: AgentSignal, winning_signal: Optional[SignalType], actual_outcome: float
    ) -> bool:
        """Evaluate if an agent's signal was correct based on outcome."""

        if winning_signal is None:
            return False

        # Simple correctness evaluation (can be made more sophisticated)
        signal_aligned = signal.signal_type == winning_signal

        # Weight by confidence and outcome
        confidence_factor = signal.confidence
        outcome_factor = 1.0 if actual_outcome > 0 else -1.0

        return signal_aligned and (confidence_factor * outcome_factor > 0)

    def _update_agent_weights(self) -> None:
        """Update agent weights based on recent performance."""
        for agent_id, perf in self.agent_performance.items():
            if perf.total_trades >= 10:  # Require minimum trades for reliable weights
                base_weight = self.agent_registry[agent_id]["base_weight"]
                performance_weight = perf.calculate_weight(base_weight)
                self.agent_weights[agent_id] = performance_weight

    def get_consensus_stats(self) -> Dict[str, Any]:
        """Get comprehensive consensus system statistics."""

        if not self.consensus_history:
            return {"total_consensus_events": 0}

        recent_results = (
            self.consensus_history[-100:]
            if len(self.consensus_history) >= 100
            else self.consensus_history
        )

        # Calculate success rates and metrics
        winning_signals = [r for r in recent_results if r.winning_signal is not None]
        success_rate = len(winning_signals) / len(recent_results) if recent_results else 0

        avg_confidence = (
            statistics.mean(r.consensus_confidence for r in recent_results) if recent_results else 0
        )
        avg_agreement = (
            statistics.mean(r.agreement_level for r in recent_results) if recent_results else 0
        )
        avg_participation = (
            statistics.mean(r.participation_rate for r in recent_results) if recent_results else 0
        )

        # Signal type distribution
        signal_distribution = {}
        for result in recent_results:
            if result.winning_signal:
                signal_type = result.winning_signal.value
                signal_distribution[signal_type] = signal_distribution.get(signal_type, 0) + 1

        # Agent performance summary
        agent_summary = {}
        for agent_id, perf in self.agent_performance.items():
            agent_summary[agent_id] = {
                "win_rate": perf.win_rate,
                "total_trades": perf.total_trades,
                "current_weight": self.agent_weights[agent_id],
            }

        return {
            "total_consensus_events": len(self.consensus_history),
            "success_rate": success_rate,
            "avg_confidence": avg_confidence,
            "avg_agreement": avg_agreement,
            "avg_participation": avg_participation,
            "signal_distribution": signal_distribution,
            "agent_performance": agent_summary,
            "active_agents": len(self.agent_registry),
        }


# Global consensus engine instance
_consensus_engine: Optional[AgentConsensusEngine] = None


async def get_agent_consensus_engine() -> AgentConsensusEngine:
    """Get global agent consensus engine instance."""
    global _consensus_engine
    if _consensus_engine is None:
        _consensus_engine = AgentConsensusEngine()
    return _consensus_engine
