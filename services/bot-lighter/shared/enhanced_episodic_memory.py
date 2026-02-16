"""
Enhanced Episodic Memory Bank v2.0 - Memory That Actually Learns

Major enhancements over v1:
1. MarketSnapshot: Captures rich market context at episode start/end
2. Auto-regime detection: Infers regime from market data
3. Multi-faceted lessons: Tactical, strategic, psychological insights
4. Causal chains: Tracks what led to what
5. Temporal patterns: Time-of-day and day-of-week correlations
6. Counter-factual analysis: "What if we had done X instead?"
7. Confidence scoring: How reliable are past lessons?
"""

import asyncio
import hashlib
import json
import logging
import math
import os
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import google.generativeai as genai

logger = logging.getLogger(__name__)


# ============ MARKET SNAPSHOT ============


@dataclass
class MarketSnapshot:
    """
    Rich market context at a specific moment.
    Captures price, volume, volatility, and sentiment indicators.
    """

    timestamp: datetime

    # Price data
    prices: Dict[str, float] = field(default_factory=dict)  # symbol -> price

    # Volume (24h)
    volumes: Dict[str, float] = field(default_factory=dict)  # symbol -> volume

    # Volatility (realized, 1h)
    volatility: Dict[str, float] = field(default_factory=dict)  # symbol -> vol

    # Order book imbalance (-1 to 1)
    order_book_imbalance: Dict[str, float] = field(default_factory=dict)

    # Funding rates (for perps)
    funding_rates: Dict[str, float] = field(default_factory=dict)

    # Open interest
    open_interest: Dict[str, float] = field(default_factory=dict)

    # Correlation matrix (key = "SYM1:SYM2")
    correlations: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "prices": self.prices,
            "volumes": self.volumes,
            "volatility": self.volatility,
            "order_book_imbalance": self.order_book_imbalance,
            "funding_rates": self.funding_rates,
            "open_interest": self.open_interest,
            "correlations": self.correlations,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketSnapshot":
        return cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            prices=data.get("prices", {}),
            volumes=data.get("volumes", {}),
            volatility=data.get("volatility", {}),
            order_book_imbalance=data.get("order_book_imbalance", {}),
            funding_rates=data.get("funding_rates", {}),
            open_interest=data.get("open_interest", {}),
            correlations=data.get("correlations", {}),
        )

    def get_regime_indicators(self) -> Dict[str, float]:
        """Extract numerical indicators for regime classification."""
        avg_volatility = statistics.mean(self.volatility.values()) if self.volatility else 0
        avg_imbalance = (
            statistics.mean(self.order_book_imbalance.values()) if self.order_book_imbalance else 0
        )
        avg_funding = statistics.mean(self.funding_rates.values()) if self.funding_rates else 0

        return {
            "avg_volatility": avg_volatility,
            "avg_imbalance": avg_imbalance,
            "avg_funding": avg_funding,
            "high_volatility": avg_volatility > 0.03,
            "bullish_pressure": avg_imbalance > 0.1,
            "bearish_pressure": avg_imbalance < -0.1,
        }


# ============ REGIME AUTO-DETECTION ============


class MarketRegime(str, Enum):
    """Market regime classifications."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    RANGING = "ranging"
    BREAKOUT = "breakout"
    MEAN_REVERSION = "mean_reversion"
    UNKNOWN = "unknown"


def auto_detect_regime(
    snapshot: MarketSnapshot,
    price_change_1h: Dict[str, float] = None,
    price_change_24h: Dict[str, float] = None,
) -> Tuple[MarketRegime, float]:
    """
    Automatically detect market regime from snapshot data.

    Returns (regime, confidence).
    """
    indicators = snapshot.get_regime_indicators()

    # Default confidence
    confidence = 0.5

    # High volatility regime
    if indicators["high_volatility"]:
        if indicators["avg_imbalance"] > 0.15:
            return MarketRegime.BREAKOUT, 0.8
        elif indicators["avg_imbalance"] < -0.15:
            return MarketRegime.HIGH_VOLATILITY, 0.7
        return MarketRegime.HIGH_VOLATILITY, 0.6

    # Trending detection using price changes
    if price_change_1h:
        avg_1h_change = statistics.mean(price_change_1h.values())

        if avg_1h_change > 2.0:  # >2% avg 1h gain
            return MarketRegime.TRENDING_UP, 0.75
        elif avg_1h_change < -2.0:
            return MarketRegime.TRENDING_DOWN, 0.75

    # Order book pressure
    if indicators["bullish_pressure"]:
        return MarketRegime.TRENDING_UP, 0.6
    elif indicators["bearish_pressure"]:
        return MarketRegime.TRENDING_DOWN, 0.6

    # Low volatility / ranging
    if not indicators["high_volatility"]:
        if abs(indicators["avg_imbalance"]) < 0.05:
            return MarketRegime.RANGING, 0.65
        return MarketRegime.LOW_VOLATILITY, 0.55

    return MarketRegime.UNKNOWN, 0.3


# ============ CAUSAL CHAIN ============


@dataclass
class CausalEvent:
    """A single event in a causal chain."""

    timestamp: datetime
    event_type: str  # "market", "action", "outcome"
    description: str
    data: Dict[str, Any] = field(default_factory=dict)

    # Links to other events
    caused_by: Optional[str] = None  # ID of preceding event
    led_to: Optional[str] = None  # ID of resulting event

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type,
            "description": self.description,
            "data": self.data,
            "caused_by": self.caused_by,
            "led_to": self.led_to,
        }


@dataclass
class CausalChain:
    """A chain of causally-linked events."""

    chain_id: str
    events: List[CausalEvent] = field(default_factory=list)

    def add_event(
        self,
        event_type: str,
        description: str,
        data: Dict = None,
    ) -> CausalEvent:
        """Add an event to the chain."""
        event = CausalEvent(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            description=description,
            data=data or {},
        )

        # Link to previous event
        if self.events:
            prev_id = f"{self.chain_id}-{len(self.events)-1}"
            event.caused_by = prev_id
            self.events[-1].led_to = f"{self.chain_id}-{len(self.events)}"

        self.events.append(event)
        return event

    def get_narrative(self) -> str:
        """Generate a narrative from the causal chain."""
        if not self.events:
            return "No events recorded."

        parts = []
        for i, event in enumerate(self.events):
            prefix = "→ " if i > 0 else ""
            parts.append(f"{prefix}[{event.event_type}] {event.description}")

        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "events": [e.to_dict() for e in self.events],
        }


# ============ MULTI-FACETED LESSONS ============


@dataclass
class MultiFacetedLesson:
    """
    Lessons extracted from multiple perspectives.

    Not just "what to do next time" but:
    - Tactical: Specific actions that worked/failed
    - Strategic: Higher-level patterns
    - Psychological: Mental state insights
    - Counter-factual: What could have been done differently
    """

    tactical: Optional[str] = None  # "Close 50% at first resistance"
    strategic: Optional[str] = None  # "In uptrends, trail stops rather than fixed TP"
    psychological: Optional[str] = None  # "Overconfidence after 3 wins led to oversizing"
    counter_factual: Optional[str] = None  # "Had we waited 5 min, entry would be 2% better"
    confidence: float = 0.5  # How reliable is this lesson?

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tactical": self.tactical,
            "strategic": self.strategic,
            "psychological": self.psychological,
            "counter_factual": self.counter_factual,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultiFacetedLesson":
        return cls(
            tactical=data.get("tactical"),
            strategic=data.get("strategic"),
            psychological=data.get("psychological"),
            counter_factual=data.get("counter_factual"),
            confidence=data.get("confidence", 0.5),
        )

    def get_summary(self) -> str:
        parts = []
        if self.tactical:
            parts.append(f"📌 Tactical: {self.tactical}")
        if self.strategic:
            parts.append(f"🎯 Strategic: {self.strategic}")
        if self.psychological:
            parts.append(f"🧠 Psychological: {self.psychological}")
        if self.counter_factual:
            parts.append(f"🔄 Counter-factual: {self.counter_factual}")
        return "\n".join(parts) if parts else "No lessons extracted."


# ============ TEMPORAL PATTERNS ============


@dataclass
class TemporalPattern:
    """Patterns based on time (hour, day, etc)."""

    hour_of_day: int  # 0-23 UTC
    day_of_week: int  # 0=Monday, 6=Sunday

    # Outcomes at this time
    trades_taken: int = 0
    wins: int = 0
    losses: int = 0
    total_pnl: float = 0.0
    avg_volatility: float = 0.0

    @property
    def win_rate(self) -> float:
        if self.trades_taken == 0:
            return 0.0
        return self.wins / self.trades_taken

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hour_of_day": self.hour_of_day,
            "day_of_week": self.day_of_week,
            "trades_taken": self.trades_taken,
            "wins": self.wins,
            "losses": self.losses,
            "total_pnl": self.total_pnl,
            "avg_volatility": self.avg_volatility,
        }


# ============ ENHANCED EPISODE ============


@dataclass
class EnhancedEpisode:
    """
    Enhanced episode with rich context, causal chains, and multi-faceted lessons.
    """

    episode_id: str
    name: str

    # Time bounds
    start_time: datetime
    end_time: Optional[datetime] = None

    # Rich market context
    start_snapshot: Optional[MarketSnapshot] = None
    end_snapshot: Optional[MarketSnapshot] = None

    # Auto-detected regime (with confidence)
    regime: MarketRegime = MarketRegime.UNKNOWN
    regime_confidence: float = 0.5

    # Symbols and assets involved
    symbols_involved: List[str] = field(default_factory=list)

    # Causal chain of events
    causal_chain: CausalChain = field(default_factory=lambda: CausalChain(""))

    # Trades with richer context
    trades: List[Dict[str, Any]] = field(default_factory=list)

    # Outcomes
    total_pnl: float = 0.0
    win_rate: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0

    # Multi-faceted lessons
    lessons: Optional[MultiFacetedLesson] = None

    # Tags for categorization
    tags: List[str] = field(default_factory=list)

    # Temporal context
    hour_of_day: int = 0
    day_of_week: int = 0

    # Embedding for semantic similarity
    embedding: Optional[List[float]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "start_snapshot": self.start_snapshot.to_dict() if self.start_snapshot else None,
            "end_snapshot": self.end_snapshot.to_dict() if self.end_snapshot else None,
            "regime": self.regime.value,
            "regime_confidence": self.regime_confidence,
            "symbols_involved": self.symbols_involved,
            "causal_chain": self.causal_chain.to_dict() if self.causal_chain else None,
            "trades": self.trades,
            "total_pnl": self.total_pnl,
            "win_rate": self.win_rate,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "lessons": self.lessons.to_dict() if self.lessons else None,
            "tags": self.tags,
            "hour_of_day": self.hour_of_day,
            "day_of_week": self.day_of_week,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnhancedEpisode":
        ep = cls(
            episode_id=data["episode_id"],
            name=data["name"],
            start_time=datetime.fromisoformat(data["start_time"]),
            end_time=datetime.fromisoformat(data["end_time"]) if data.get("end_time") else None,
            regime=MarketRegime(data.get("regime", "unknown")),
            regime_confidence=data.get("regime_confidence", 0.5),
            symbols_involved=data.get("symbols_involved", []),
            trades=data.get("trades", []),
            total_pnl=data.get("total_pnl", 0.0),
            win_rate=data.get("win_rate", 0.0),
            max_drawdown_pct=data.get("max_drawdown_pct", 0.0),
            sharpe_ratio=data.get("sharpe_ratio", 0.0),
            tags=data.get("tags", []),
            hour_of_day=data.get("hour_of_day", 0),
            day_of_week=data.get("day_of_week", 0),
        )

        if data.get("start_snapshot"):
            ep.start_snapshot = MarketSnapshot.from_dict(data["start_snapshot"])
        if data.get("end_snapshot"):
            ep.end_snapshot = MarketSnapshot.from_dict(data["end_snapshot"])
        if data.get("lessons"):
            ep.lessons = MultiFacetedLesson.from_dict(data["lessons"])

        return ep

    def get_summary(self) -> str:
        """Generate rich summary."""
        duration = (self.end_time - self.start_time).total_seconds() / 3600 if self.end_time else 0
        lesson_summary = self.lessons.get_summary() if self.lessons else "No lessons"

        return f"""📅 Episode: {self.name}
🕐 Duration: {duration:.1f}h ({self.start_time.strftime('%a %H:%M')} UTC)
📊 Regime: {self.regime.value} (confidence: {self.regime_confidence:.0%})
💰 PnL: ${self.total_pnl:+,.2f} | Win Rate: {self.win_rate:.0%} | Sharpe: {self.sharpe_ratio:.2f}
🏷️ Tags: {', '.join(self.tags) if self.tags else 'None'}

LESSONS:
{lesson_summary}"""


# ============ ENHANCED MEMORY BANK ============


class EnhancedMemoryBank:
    """
    Enhanced episodic memory with auto-detection, causal chains, and multi-faceted lessons.
    """

    def __init__(self, storage_path: Optional[str] = None):
        self.episodes: Dict[str, EnhancedEpisode] = {}
        self.storage_path = storage_path or "/tmp/sapphire_enhanced_memory.json"
        self.current_episode: Optional[EnhancedEpisode] = None

        # Temporal pattern tracking
        self.temporal_patterns: Dict[Tuple[int, int], TemporalPattern] = {}

        # AI for lesson extraction
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel("gemini-2.0-flash")
        else:
            self.model = None

        self._load()

    def _load(self):
        """Load enhanced episodes from storage."""
        try:
            if os.path.exists(self.storage_path):
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    for ep_data in data.get("episodes", []):
                        ep = EnhancedEpisode.from_dict(ep_data)
                        self.episodes[ep.episode_id] = ep
                logger.info(f"📚 Loaded {len(self.episodes)} enhanced episodes")
        except Exception as e:
            logger.warning(f"Could not load enhanced memory: {e}")

    def _save(self):
        """Persist enhanced episodes."""
        try:
            data = {
                "episodes": [ep.to_dict() for ep in self.episodes.values()],
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "version": "2.0",
            }
            with open(self.storage_path, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save enhanced memory: {e}")

    def start_episode(
        self,
        name: str,
        snapshot: MarketSnapshot,
        symbols: List[str] = None,
        price_change_1h: Dict[str, float] = None,
        price_change_24h: Dict[str, float] = None,
    ) -> EnhancedEpisode:
        """Start a new episode with auto-detected regime."""
        now = datetime.now(timezone.utc)
        episode_id = f"ep-{now.strftime('%Y%m%d-%H%M%S')}"

        # Auto-detect regime
        regime, confidence = auto_detect_regime(snapshot, price_change_1h, price_change_24h)

        self.current_episode = EnhancedEpisode(
            episode_id=episode_id,
            name=name,
            start_time=now,
            start_snapshot=snapshot,
            regime=regime,
            regime_confidence=confidence,
            symbols_involved=symbols or [],
            hour_of_day=now.hour,
            day_of_week=now.weekday(),
            causal_chain=CausalChain(episode_id),
        )

        # Record start event in causal chain
        self.current_episode.causal_chain.add_event(
            "market",
            f"Episode started: {regime.value} regime detected ({confidence:.0%} confidence)",
            {"regime": regime.value, "confidence": confidence},
        )

        logger.info(f"📝 Started enhanced episode: {name} | Regime: {regime.value}")
        return self.current_episode

    def record_market_event(self, description: str, data: Dict = None) -> None:
        """Record a market event in the causal chain."""
        if self.current_episode:
            self.current_episode.causal_chain.add_event("market", description, data)

    def record_action(self, description: str, data: Dict = None) -> None:
        """Record an action (trade decision) in the causal chain."""
        if self.current_episode:
            self.current_episode.causal_chain.add_event("action", description, data)

    def record_outcome(self, description: str, data: Dict = None) -> None:
        """Record an outcome in the causal chain."""
        if self.current_episode:
            self.current_episode.causal_chain.add_event("outcome", description, data)

    def record_trade(self, trade_data: Dict[str, Any]) -> None:
        """Record a trade with causal chain entry."""
        if not self.current_episode:
            return

        self.current_episode.trades.append(trade_data)

        # Add to causal chain
        side = trade_data.get("side", "UNKNOWN")
        symbol = trade_data.get("symbol", "UNKNOWN")
        price = trade_data.get("price", 0)

        self.current_episode.causal_chain.add_event(
            "action",
            f"Executed {side} {symbol} @ ${price:.2f}",
            trade_data,
        )

    def end_episode(
        self,
        end_snapshot: MarketSnapshot = None,
    ) -> Optional[EnhancedEpisode]:
        """End the current episode with rich outcome calculation."""
        if not self.current_episode:
            return None

        ep = self.current_episode
        ep.end_time = datetime.now(timezone.utc)
        ep.end_snapshot = end_snapshot

        # Calculate outcomes
        if ep.trades:
            pnls = [t.get("pnl", 0) for t in ep.trades]
            wins = sum(1 for p in pnls if p > 0)

            ep.win_rate = wins / len(ep.trades)
            ep.total_pnl = sum(pnls)

            # Calculate Sharpe (simplified)
            if len(pnls) > 1 and statistics.stdev(pnls) > 0:
                ep.sharpe_ratio = statistics.mean(pnls) / statistics.stdev(pnls)

            # Max drawdown
            cumulative = 0
            peak = 0
            max_dd = 0
            for pnl in pnls:
                cumulative += pnl
                peak = max(peak, cumulative)
                drawdown = (peak - cumulative) / peak if peak > 0 else 0
                max_dd = max(max_dd, drawdown)
            ep.max_drawdown_pct = max_dd * 100

        # Record end event
        ep.causal_chain.add_event(
            "outcome",
            f"Episode ended: PnL ${ep.total_pnl:+,.2f}, Win rate {ep.win_rate:.0%}",
            {"pnl": ep.total_pnl, "win_rate": ep.win_rate},
        )

        # Update temporal patterns
        self._update_temporal_patterns(ep)

        # Store and save
        self.episodes[ep.episode_id] = ep
        self.current_episode = None
        self._save()

        logger.info(f"📚 Enhanced episode ended: {ep.name} | PnL: ${ep.total_pnl:+,.2f}")
        return ep

    def _update_temporal_patterns(self, ep: EnhancedEpisode) -> None:
        """Update temporal pattern statistics."""
        key = (ep.hour_of_day, ep.day_of_week)

        if key not in self.temporal_patterns:
            self.temporal_patterns[key] = TemporalPattern(
                hour_of_day=ep.hour_of_day,
                day_of_week=ep.day_of_week,
            )

        pattern = self.temporal_patterns[key]
        pattern.trades_taken += len(ep.trades)
        pattern.wins += int(ep.win_rate * len(ep.trades))
        pattern.losses += int((1 - ep.win_rate) * len(ep.trades))
        pattern.total_pnl += ep.total_pnl

    async def extract_multi_faceted_lessons(self, episode: EnhancedEpisode) -> MultiFacetedLesson:
        """Extract lessons from multiple perspectives using Gemini."""
        if not self.model:
            return MultiFacetedLesson(
                tactical="[Mock] Consider tighter stops in volatile conditions",
                confidence=0.3,
            )

        prompt = f"""Analyze this trading episode from multiple perspectives:

{episode.get_summary()}

CAUSAL CHAIN:
{episode.causal_chain.get_narrative()}

TRADES:
{json.dumps(episode.trades[:5], indent=2)}

Extract lessons from FOUR perspectives. Be specific and actionable:

1. TACTICAL (specific execution): What specific entry/exit/sizing could have been better?
2. STRATEGIC (pattern-level): What broader pattern or strategy insight emerges?
3. PSYCHOLOGICAL (mental state): Any biases, emotions, or decision-making issues?
4. COUNTER-FACTUAL (alternative): What would have happened with a different approach?

Format as JSON:
{{
  "tactical": "...",
  "strategic": "...",
  "psychological": "...",
  "counter_factual": "...",
  "confidence": 0.0-1.0
}}"""

        try:
            response = await asyncio.to_thread(
                lambda: self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        max_output_tokens=512,
                        temperature=0.5,
                    ),
                )
            )

            # Parse JSON from response
            text = response.text
            # Extract JSON from possible markdown code block
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]

            data = json.loads(text.strip())

            lessons = MultiFacetedLesson(
                tactical=data.get("tactical"),
                strategic=data.get("strategic"),
                psychological=data.get("psychological"),
                counter_factual=data.get("counter_factual"),
                confidence=float(data.get("confidence", 0.7)),
            )

            episode.lessons = lessons
            self._save()

            logger.info(f"📖 Multi-faceted lessons extracted for {episode.name}")
            return lessons

        except Exception as e:
            logger.error(f"Lesson extraction failed: {e}")
            return MultiFacetedLesson(tactical=f"Error: {e}", confidence=0.1)

    def find_similar_episodes(
        self,
        regime: MarketRegime = None,
        symbols: List[str] = None,
        hour_of_day: int = None,
        min_confidence: float = 0.0,
        limit: int = 5,
    ) -> List[EnhancedEpisode]:
        """Find similar episodes with multiple matching criteria."""
        scored = []

        for ep in self.episodes.values():
            score = 0

            # Regime match (weighted by confidence)
            if regime and ep.regime == regime:
                score += 3 * ep.regime_confidence

            # Symbol overlap
            if symbols:
                overlap = len(set(ep.symbols_involved) & set(symbols))
                score += overlap * 2

            # Time of day similarity (±2 hours)
            if hour_of_day is not None:
                hour_diff = abs(ep.hour_of_day - hour_of_day)
                if hour_diff <= 2:
                    score += 1 - (hour_diff / 2) * 0.5

            # Has lessons
            if ep.lessons and ep.lessons.confidence >= min_confidence:
                score += 1

            if score > 0:
                scored.append((score, ep))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:limit]]

    def get_temporal_insights(self) -> Dict[str, Any]:
        """Get insights about best/worst times to trade."""
        if not self.temporal_patterns:
            return {"message": "Not enough data yet"}

        # Best hour
        best_hour = max(
            self.temporal_patterns.values(),
            key=lambda p: p.total_pnl,
            default=None,
        )

        # Worst hour
        worst_hour = min(
            self.temporal_patterns.values(),
            key=lambda p: p.total_pnl,
            default=None,
        )

        # Best day
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_pnls = {}
        for p in self.temporal_patterns.values():
            day_pnls[p.day_of_week] = day_pnls.get(p.day_of_week, 0) + p.total_pnl

        best_day = max(day_pnls.items(), key=lambda x: x[1], default=(0, 0))

        return {
            "best_hour": best_hour.hour_of_day if best_hour else None,
            "best_hour_pnl": best_hour.total_pnl if best_hour else 0,
            "worst_hour": worst_hour.hour_of_day if worst_hour else None,
            "worst_hour_pnl": worst_hour.total_pnl if worst_hour else 0,
            "best_day": days[best_day[0]] if best_day else None,
            "best_day_pnl": best_day[1] if best_day else 0,
        }

    async def recall_for_decision(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        context: str = "",
    ) -> str:
        """Generate context-aware advice from memory."""
        # Auto-detect current regime
        regime, _ = auto_detect_regime(snapshot)

        # Find similar past episodes
        similar = self.find_similar_episodes(
            regime=regime,
            symbols=[symbol],
            hour_of_day=datetime.now(timezone.utc).hour,
            min_confidence=0.5,
            limit=3,
        )

        if not similar:
            return "No relevant past experiences found."

        # Compile lessons
        lessons = []
        for ep in similar:
            if ep.lessons:
                lessons.append(f"**{ep.name}** ({ep.regime.value}):")
                lessons.append(ep.lessons.get_summary())
                lessons.append("")

        if not lessons:
            return "Similar episodes found, but no lessons extracted yet."

        # Get temporal insight
        temporal = self.get_temporal_insights()
        current_hour = datetime.now(timezone.utc).hour
        temporal_warning = ""
        if temporal.get("worst_hour") == current_hour:
            temporal_warning = (
                f"\n⚠️ WARNING: {current_hour}:00 UTC is historically your worst trading hour!"
            )

        # Synthesize with AI if available
        if self.model:
            synthesis_prompt = f"""Given these lessons from past similar situations:

{chr(10).join(lessons)}

Current situation:
- Symbol: {symbol}
- Regime: {regime.value}
- Context: {context}
{temporal_warning}

Provide ONE synthesized recommendation (2-3 sentences) that combines these lessons."""

            try:
                response = await asyncio.to_thread(
                    lambda: self.model.generate_content(
                        synthesis_prompt,
                        generation_config=genai.types.GenerationConfig(
                            max_output_tokens=256,
                            temperature=0.4,
                        ),
                    )
                )
                return response.text.strip() + temporal_warning
            except Exception as e:
                pass

        return "\n".join(lessons) + temporal_warning

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics."""
        total_pnl = sum(ep.total_pnl for ep in self.episodes.values())
        total_trades = sum(len(ep.trades) for ep in self.episodes.values())

        regime_dist = {}
        for ep in self.episodes.values():
            regime_dist[ep.regime.value] = regime_dist.get(ep.regime.value, 0) + 1

        lessons_with_all = sum(
            1
            for ep in self.episodes.values()
            if ep.lessons
            and all(
                [
                    ep.lessons.tactical,
                    ep.lessons.strategic,
                    ep.lessons.psychological,
                ]
            )
        )

        return {
            "total_episodes": len(self.episodes),
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "regime_distribution": regime_dist,
            "episodes_with_full_lessons": lessons_with_all,
            "temporal_insights": self.get_temporal_insights(),
        }


# Global instance
_enhanced_memory: Optional[EnhancedMemoryBank] = None


def get_enhanced_memory() -> EnhancedMemoryBank:
    """Get or create the enhanced memory instance."""
    global _enhanced_memory
    if _enhanced_memory is None:
        _enhanced_memory = EnhancedMemoryBank()
    return _enhanced_memory


async def demo_enhanced_memory():
    """Demo the enhanced episodic memory."""
    memory = get_enhanced_memory()

    # Create a snapshot
    snapshot = MarketSnapshot(
        timestamp=datetime.now(timezone.utc),
        prices={"SOL": 145.00, "BTC": 48000.00},
        volumes={"SOL": 800_000_000, "BTC": 35_000_000_000},
        volatility={"SOL": 0.045, "BTC": 0.025},
        order_book_imbalance={"SOL": 0.22, "BTC": 0.08},
        funding_rates={"SOL": 0.0015, "BTC": 0.0008},
    )

    # Start episode
    print("📝 Starting enhanced episode...")
    ep = memory.start_episode(
        name="SOL Breakout Test",
        snapshot=snapshot,
        symbols=["SOL"],
        price_change_1h={"SOL": 3.5, "BTC": 0.8},
    )
    print(f"  Regime auto-detected: {ep.regime.value} ({ep.regime_confidence:.0%})")

    # Record events
    memory.record_market_event("Volume spike 3x normal")
    memory.record_action("Decided to enter long based on breakout")

    # Record trade
    memory.record_trade(
        {
            "symbol": "SOL",
            "side": "BUY",
            "price": 145.50,
            "quantity": 5,
            "pnl": 125.00,
        }
    )

    memory.record_outcome("Price hit first target at 148")

    # End episode
    end_snapshot = MarketSnapshot(
        timestamp=datetime.now(timezone.utc),
        prices={"SOL": 148.50, "BTC": 48100.00},
        volumes={"SOL": 1_200_000_000, "BTC": 36_000_000_000},
        volatility={"SOL": 0.055, "BTC": 0.028},
        order_book_imbalance={"SOL": 0.15, "BTC": 0.05},
        funding_rates={"SOL": 0.0025, "BTC": 0.0010},
    )

    ep = memory.end_episode(end_snapshot)
    print(f"\n📊 Episode Summary:\n{ep.get_summary()}")

    # Extract multi-faceted lessons
    print("\n📖 Extracting multi-faceted lessons...")
    lessons = await memory.extract_multi_faceted_lessons(ep)
    print(lessons.get_summary())

    # Show causal chain
    print(f"\n🔗 Causal Chain:\n{ep.causal_chain.get_narrative()}")

    # Get stats
    print(f"\n📈 Memory Stats: {json.dumps(memory.get_stats(), indent=2)}")


if __name__ == "__main__":
    asyncio.run(demo_enhanced_memory())
