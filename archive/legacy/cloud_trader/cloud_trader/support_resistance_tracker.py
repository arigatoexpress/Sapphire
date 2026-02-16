"""
Support/Resistance Tracker - Smart Re-entry System

Tracks key price levels (support and resistance) for intelligent re-entry
after taking profits or being stopped out with trailing stops.

Algorithm:
1. Find pivot points (local highs/lows) in historical candles
2. Cluster nearby pivots into zones (±0.5% price range)
3. Score zones by touch count, volume, and persistence
4. Track levels over time

Re-entry Rules:
1. Only re-enter after TP or trailing stop (NOT after SL)
2. Price must be within 0.3% of key level
3. Level must be strong (strength > 0.6, touch count ≥ 3)
4. At least 5 minutes since last exit
5. Require confirmation: volume spike (1.5x average) or reversal pattern

Benefits:
- High-probability re-entry at tested levels
- Avoid random re-entries (systematic approach)
- Learn from historical price action
- Tighter stops on re-entries (50% of normal)
"""

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PivotPoint:
    """A historical pivot point (local high or low)"""
    price: float
    timestamp: float
    pivot_type: str  # "high" or "low"
    volume: float = 0.0
    significance: float = 0.0  # How significant this pivot is


@dataclass
class SupportResistanceLevel:
    """A support or resistance zone"""
    price: float  # Center price of the zone
    level_type: str  # "support" or "resistance"
    touch_count: int  # Number of times price touched this level
    first_seen: float  # Timestamp of first touch
    last_seen: float  # Timestamp of last touch
    avg_volume: float  # Average volume at this level
    strength: float  # Overall strength score (0-1)
    touches: List[PivotPoint] = field(default_factory=list)


@dataclass
class ReentryOpportunity:
    """A potential re-entry opportunity at a key level"""
    symbol: str
    level: SupportResistanceLevel
    current_price: float
    distance_to_level_pct: float
    level_strength: float
    has_volume_confirmation: bool
    has_pattern_confirmation: bool
    time_since_exit_seconds: float
    recommended_stop_loss: float
    confidence: float
    reasoning: str


class SupportResistanceTracker:
    """
    Tracks support and resistance levels for smart re-entry decisions.

    Maintains historical pivot points and clusters them into
    actionable support/resistance zones.
    """

    # Configuration
    CLUSTER_DISTANCE_PCT = 0.005  # 0.5% price range for clustering
    MIN_TOUCHES_FOR_LEVEL = 3  # Minimum touches to be considered a level
    MIN_LEVEL_STRENGTH = 0.6  # Minimum strength for re-entry (0-1)
    REENTRY_DISTANCE_PCT = 0.003  # Price within 0.3% of level
    MIN_TIME_SINCE_EXIT_SECONDS = 300  # 5 minutes
    VOLUME_SPIKE_MULTIPLIER = 1.5  # 1.5x average volume for confirmation
    MAX_LEVELS_PER_SYMBOL = 10  # Track top 10 levels per symbol

    def __init__(self):
        """Initialize support/resistance tracker"""
        # symbol -> list of pivot points
        self.pivot_points: Dict[str, List[PivotPoint]] = defaultdict(list)

        # symbol -> list of S/R levels
        self.sr_levels: Dict[str, List[SupportResistanceLevel]] = defaultdict(list)

        # symbol -> last exit info
        self.last_exits: Dict[str, Dict] = {}

        # Statistics
        self.reentry_opportunities_found = 0
        self.successful_reentries = 0

        logger.info("📍 SupportResistanceTracker initialized")

    def add_candle(
        self,
        symbol: str,
        high: float,
        low: float,
        close: float,
        volume: float,
        timestamp: float
    ):
        """
        Add a price candle and detect pivot points

        Args:
            symbol: Trading symbol
            high: Candle high price
            low: Candle low price
            close: Candle close price
            volume: Candle volume
            timestamp: Candle timestamp
        """
        # Check if this candle forms a pivot point
        # In production, you'd compare with previous/next candles
        # For now, we'll use a simplified approach

        # Add high as potential resistance pivot
        high_pivot = PivotPoint(
            price=high,
            timestamp=timestamp,
            pivot_type="high",
            volume=volume,
            significance=self._calculate_pivot_significance(symbol, high, "high")
        )

        # Add low as potential support pivot
        low_pivot = PivotPoint(
            price=low,
            timestamp=timestamp,
            pivot_type="low",
            volume=volume,
            significance=self._calculate_pivot_significance(symbol, low, "low")
        )

        self.pivot_points[symbol].extend([high_pivot, low_pivot])

        # Keep only recent pivots (last 1000)
        if len(self.pivot_points[symbol]) > 1000:
            self.pivot_points[symbol] = self.pivot_points[symbol][-1000:]

        # Periodically refresh S/R levels
        if len(self.pivot_points[symbol]) % 100 == 0:
            self.refresh_levels(symbol)

    def _calculate_pivot_significance(
        self,
        symbol: str,
        price: float,
        pivot_type: str
    ) -> float:
        """
        Calculate how significant a pivot point is

        Factors:
        - Distance from recent price action
        - Volume at pivot
        - Historical touches

        Returns:
            Significance score (0-1)
        """
        # Simplified significance calculation
        # In production, compare with recent price range, volume, etc.
        return 0.5  # Default medium significance

    def refresh_levels(self, symbol: str):
        """
        Refresh support/resistance levels for a symbol

        Clusters pivot points into zones and scores them
        """
        if symbol not in self.pivot_points or not self.pivot_points[symbol]:
            return

        pivots = self.pivot_points[symbol]

        # Cluster pivots into levels
        levels = self._cluster_pivots(pivots)

        # Score each level
        scored_levels = []
        for level in levels:
            strength = self._calculate_level_strength(level)
            level.strength = strength
            scored_levels.append(level)

        # Sort by strength and keep top N
        scored_levels.sort(key=lambda x: x.strength, reverse=True)
        self.sr_levels[symbol] = scored_levels[:self.MAX_LEVELS_PER_SYMBOL]

        logger.debug(
            f"Refreshed S/R levels for {symbol}: {len(self.sr_levels[symbol])} levels found"
        )

    def _cluster_pivots(
        self,
        pivots: List[PivotPoint]
    ) -> List[SupportResistanceLevel]:
        """
        Cluster nearby pivot points into S/R levels

        Uses price proximity clustering (±0.5% range)
        """
        if not pivots:
            return []

        # Sort pivots by price
        sorted_pivots = sorted(pivots, key=lambda p: p.price)

        clusters = []
        current_cluster = [sorted_pivots[0]]

        for pivot in sorted_pivots[1:]:
            last_price = current_cluster[-1].price
            price_diff_pct = abs(pivot.price - last_price) / last_price

            if price_diff_pct <= self.CLUSTER_DISTANCE_PCT:
                # Same cluster
                current_cluster.append(pivot)
            else:
                # New cluster - save previous and start new
                if len(current_cluster) >= self.MIN_TOUCHES_FOR_LEVEL:
                    clusters.append(self._create_level_from_cluster(current_cluster))
                current_cluster = [pivot]

        # Don't forget the last cluster
        if len(current_cluster) >= self.MIN_TOUCHES_FOR_LEVEL:
            clusters.append(self._create_level_from_cluster(current_cluster))

        return clusters

    def _create_level_from_cluster(
        self,
        cluster: List[PivotPoint]
    ) -> SupportResistanceLevel:
        """Create a S/R level from a cluster of pivots"""
        # Average price of cluster
        avg_price = sum(p.price for p in cluster) / len(cluster)

        # Determine level type (support or resistance)
        high_count = sum(1 for p in cluster if p.pivot_type == "high")
        low_count = len(cluster) - high_count
        level_type = "resistance" if high_count > low_count else "support"

        # Average volume
        avg_volume = sum(p.volume for p in cluster) / len(cluster)

        # Time span
        timestamps = [p.timestamp for p in cluster]
        first_seen = min(timestamps)
        last_seen = max(timestamps)

        return SupportResistanceLevel(
            price=avg_price,
            level_type=level_type,
            touch_count=len(cluster),
            first_seen=first_seen,
            last_seen=last_seen,
            avg_volume=avg_volume,
            strength=0.0,  # Will be calculated separately
            touches=cluster
        )

    def _calculate_level_strength(
        self,
        level: SupportResistanceLevel
    ) -> float:
        """
        Calculate strength score for a S/R level

        Factors:
        1. Touch count (more touches = stronger)
        2. Volume (higher volume = stronger)
        3. Persistence over time (longer-lasting = stronger)
        4. Recent activity (recently touched = more relevant)

        Returns:
            Strength score (0-1)
        """
        # 1. Touch count score (0-1)
        touch_score = min(level.touch_count / 10.0, 1.0)  # Cap at 10 touches

        # 2. Volume score (normalized, simplified)
        volume_score = 0.5  # Default (would compare with average volume in production)

        # 3. Persistence score (how long the level has existed)
        age_seconds = level.last_seen - level.first_seen
        age_days = age_seconds / 86400
        persistence_score = min(age_days / 30.0, 1.0)  # Cap at 30 days

        # 4. Recency score (when was it last touched)
        time_since_touch = time.time() - level.last_seen
        days_since = time_since_touch / 86400
        if days_since < 1:
            recency_score = 1.0
        elif days_since < 7:
            recency_score = 0.8
        elif days_since < 30:
            recency_score = 0.5
        else:
            recency_score = 0.2

        # Weighted average
        strength = (
            touch_score * 0.3 +
            volume_score * 0.2 +
            persistence_score * 0.2 +
            recency_score * 0.3
        )

        return strength

    def record_exit(
        self,
        symbol: str,
        exit_price: float,
        exit_type: str,  # "take_profit", "trailing_stop", "stop_loss"
        timestamp: Optional[float] = None
    ):
        """
        Record position exit for re-entry tracking

        Args:
            symbol: Trading symbol
            exit_price: Exit price
            exit_type: Type of exit (TP, trailing stop, SL)
            timestamp: Exit timestamp (defaults to now)
        """
        if timestamp is None:
            timestamp = time.time()

        self.last_exits[symbol] = {
            "exit_price": exit_price,
            "exit_type": exit_type,
            "timestamp": timestamp,
        }

        logger.info(f"📤 Recorded exit: {symbol} @ {exit_price:.4f} ({exit_type})")

    def should_reenter_at_level(
        self,
        symbol: str,
        current_price: float,
        side: str,  # "LONG" or "SHORT"
        current_volume: float = 0.0,
        avg_volume: float = 1.0,
        has_reversal_pattern: bool = False
    ) -> Optional[ReentryOpportunity]:
        """
        Check if current price is near a strong S/R level for re-entry

        Re-entry rules:
        1. Only after TP or trailing stop (NOT after SL)
        2. Price within 0.3% of level
        3. Level strength > 0.6
        4. Touch count ≥ 3
        5. At least 5 minutes since exit
        6. Volume spike (1.5x) or reversal pattern

        Args:
            symbol: Trading symbol
            current_price: Current market price
            side: Desired position side
            current_volume: Current volume
            avg_volume: Average volume for comparison
            has_reversal_pattern: Whether a reversal pattern is detected

        Returns:
            ReentryOpportunity if conditions met, None otherwise
        """
        # Check if we have recent exit data
        if symbol not in self.last_exits:
            return None

        last_exit = self.last_exits[symbol]

        # Rule 1: Only re-enter after TP or trailing stop (NOT after SL)
        if last_exit["exit_type"] == "stop_loss":
            return None

        # Rule 5: At least 5 minutes since exit
        time_since_exit = time.time() - last_exit["timestamp"]
        if time_since_exit < self.MIN_TIME_SINCE_EXIT_SECONDS:
            return None

        # Check if we have levels for this symbol
        if symbol not in self.sr_levels or not self.sr_levels[symbol]:
            return None

        # Find nearby strong levels
        for level in self.sr_levels[symbol]:
            distance_pct = abs(current_price - level.price) / current_price

            # Rule 2: Price within 0.3% of level
            if distance_pct > self.REENTRY_DISTANCE_PCT:
                continue

            # Rule 3: Level strength > 0.6
            if level.strength < self.MIN_LEVEL_STRENGTH:
                continue

            # Rule 4: Touch count ≥ 3
            if level.touch_count < self.MIN_TOUCHES_FOR_LEVEL:
                continue

            # Check if level type matches side
            # For LONG: want to enter at support
            # For SHORT: want to enter at resistance
            if side.upper() == "LONG" and level.level_type != "support":
                continue
            if side.upper() == "SHORT" and level.level_type != "resistance":
                continue

            # Rule 6: Volume spike or reversal pattern
            volume_spike = (current_volume / avg_volume) >= self.VOLUME_SPIKE_MULTIPLIER if avg_volume > 0 else False
            has_confirmation = volume_spike or has_reversal_pattern

            if not has_confirmation:
                continue

            # Calculate recommended stop loss (tighter for re-entries)
            # Use 50% of level distance as SL
            sl_distance = abs(current_price - level.price) * 0.5
            if side.upper() == "LONG":
                recommended_sl = level.price - sl_distance
            else:
                recommended_sl = level.price + sl_distance

            # Calculate confidence
            confidence = (
                level.strength * 0.4 +
                (1.0 - distance_pct / self.REENTRY_DISTANCE_PCT) * 0.3 +
                (1.0 if volume_spike else 0.0) * 0.2 +
                (1.0 if has_reversal_pattern else 0.0) * 0.1
            )

            reasoning = (
                f"Re-entry at {level.level_type} | Level: {level.price:.4f} | "
                f"Strength: {level.strength:.2f} | Touches: {level.touch_count} | "
                f"Distance: {distance_pct:.2%} | "
                f"Confirmation: {'Volume spike' if volume_spike else 'Reversal pattern'} | "
                f"Time since exit: {time_since_exit / 60:.1f}min"
            )

            opportunity = ReentryOpportunity(
                symbol=symbol,
                level=level,
                current_price=current_price,
                distance_to_level_pct=distance_pct,
                level_strength=level.strength,
                has_volume_confirmation=volume_spike,
                has_pattern_confirmation=has_reversal_pattern,
                time_since_exit_seconds=time_since_exit,
                recommended_stop_loss=recommended_sl,
                confidence=confidence,
                reasoning=reasoning
            )

            self.reentry_opportunities_found += 1

            logger.info(f"🎯 Re-entry opportunity: {reasoning}")

            return opportunity

        return None

    def get_levels(self, symbol: str) -> List[SupportResistanceLevel]:
        """Get all tracked S/R levels for a symbol"""
        return self.sr_levels.get(symbol, [])

    def get_strong_levels(
        self,
        symbol: str,
        min_strength: float = 0.7
    ) -> List[SupportResistanceLevel]:
        """Get strong S/R levels above threshold"""
        levels = self.get_levels(symbol)
        return [l for l in levels if l.strength >= min_strength]

    def get_stats(self) -> Dict:
        """Get tracker statistics"""
        total_symbols = len(self.sr_levels)
        total_levels = sum(len(levels) for levels in self.sr_levels.values())

        return {
            "tracked_symbols": total_symbols,
            "total_levels": total_levels,
            "reentry_opportunities_found": self.reentry_opportunities_found,
            "successful_reentries": self.successful_reentries,
            "reentry_success_rate": (
                self.successful_reentries / max(1, self.reentry_opportunities_found)
            ),
        }
