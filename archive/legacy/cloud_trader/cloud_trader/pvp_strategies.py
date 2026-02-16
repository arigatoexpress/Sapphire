"""
PvP Adversarial Trading Strategies

This module contains strategies designed to counter retail trading patterns
and capitalize on market maker behavior. The philosophy is:

1. When retail expects X, market makers often do Y
2. Wait for capitulation before entering
3. Trade WITH smart money, not against it
4. Use dynamic leverage based on confidence and volatility
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MarketPhase(Enum):
    """Current market phase for counter-trading."""

    ACCUMULATION = "accumulation"  # Smart money buying
    MARKUP = "markup"  # Trend up
    DISTRIBUTION = "distribution"  # Smart money selling
    MARKDOWN = "markdown"  # Trend down
    CAPITULATION = "capitulation"  # Retail panic


@dataclass
class RetailSignal:
    """A signal that retail traders would typically act on."""

    symbol: str
    retail_direction: str  # What retail would do
    counter_direction: str  # What WE should do
    confidence: float
    reason: str
    wait_for_capitulation: bool = True


class CounterRetailStrategy:
    """
    Counter-retail trading strategy.

    Core insight: Market makers know where retail stops are and where
    retail will enter (obvious TA signals). They hunt these positions.

    Our approach:
    1. Identify obvious retail setups (RSI oversold, support bounce, etc.)
    2. WAIT - don't enter with retail
    3. When retail gets stopped out (capitulation), THEN enter
    """

    def __init__(self):
        self._retail_traps: Dict[str, Dict] = {}
        self._capitulation_signals: Dict[str, float] = {}

    async def apply_crowd_sentiment_weighting(
        self, symbol: str, base_signal: str, base_confidence: float  # "LONG" or "SHORT"
    ) -> float:
        """
        Apply crowd sentiment weighting to boost or fade signal confidence.

        Logic:
        - If crowd agrees with signal (60%+ votes) → +20% confidence boost
        - If crowd is extreme (90%+ bullish) and we're shorting → +30% confidence (fade the crowd)
        - Minimum 10 votes required for weighting

        Returns:
            Adjusted confidence
        """
        try:
            from .voting_service import get_voting_service

            voting_service = get_voting_service()
            crowd = await voting_service.get_crowd_sentiment(symbol)

            vote_count = crowd.get("vote_count", 0)

            # Require minimum votes
            if vote_count < 10:
                return base_confidence

            bullish_pct = crowd.get("bullish_pct", 0)
            bearish_pct = crowd.get("bearish_pct", 0)

            # Crowd agrees with our signal
            if base_signal == "LONG" and bullish_pct > 0.6:
                logger.info(
                    f"📊 Crowd sentiment boost: {symbol} {bullish_pct:.0%} bullish, signal LONG → +20% confidence"
                )
                return base_confidence * 1.2
            elif base_signal == "SHORT" and bearish_pct > 0.6:
                logger.info(
                    f"📊 Crowd sentiment boost: {symbol} {bearish_pct:.0%} bearish, signal SHORT → +20% confidence"
                )
                return base_confidence * 1.2

            # Contrarian: crowd is extreme, we fade
            elif base_signal == "SHORT" and bullish_pct > 0.9:
                logger.info(
                    f"📊 Fade the crowd: {symbol} {bullish_pct:.0%} bullish, signal SHORT → +30% confidence"
                )
                return base_confidence * 1.3
            elif base_signal == "LONG" and bearish_pct > 0.9:
                logger.info(
                    f"📊 Fade the crowd: {symbol} {bearish_pct:.0%} bearish, signal LONG → +30% confidence"
                )
                return base_confidence * 1.3

            # No strong crowd signal
            return base_confidence

        except Exception as e:
            logger.error(f"Failed to apply crowd sentiment: {e}")
            return base_confidence

    def analyze_retail_trap(
        self,
        symbol: str,
        rsi: Optional[float],
        price_change_24h: float,
        range_position: float,  # 0 = at low, 1 = at high
        volume_ratio: float = 1.0,  # Current vol / avg vol
    ) -> Optional[RetailSignal]:
        """
        Identify potential retail traps.

        Retail traders love:
        - RSI < 30 = "oversold, time to buy!"
        - RSI > 70 = "overbought, time to sell!"
        - Price at support = "bounce incoming!"
        - Price at resistance = "rejection incoming!"

        But market makers KNOW this. They push price to these levels
        to trigger retail entries, then reverse.
        """
        if rsi is None:
            return None

        # ═══════════════════════════════════════════════════════════════
        # TRAP 1: RSI Oversold Trap
        # Retail sees RSI < 30 and buys. MMs push it even lower.
        # ═══════════════════════════════════════════════════════════════
        if 25 < rsi < 35:  # Classic "oversold" zone
            # This is where retail buys blindly
            # We wait for RSI < 20 (true capitulation)
            return RetailSignal(
                symbol=symbol,
                retail_direction="LONG",
                counter_direction="WAIT_FOR_CAPITULATION",  # Don't trade yet
                confidence=0.6,
                reason=f"RSI {rsi:.0f} - Retail buying zone. Wait for RSI < 20 capitulation.",
                wait_for_capitulation=True,
            )

        # ═══════════════════════════════════════════════════════════════
        # TRAP 2: RSI Overbought Trap
        # Retail sees RSI > 70 and shorts. But strong trends stay overbought.
        # ═══════════════════════════════════════════════════════════════
        if 65 < rsi < 75:
            return RetailSignal(
                symbol=symbol,
                retail_direction="SHORT",
                counter_direction="WAIT_FOR_CAPITULATION",
                confidence=0.6,
                reason=f"RSI {rsi:.0f} - Retail shorting zone. Wait for RSI > 85 capitulation.",
                wait_for_capitulation=True,
            )

        # ═══════════════════════════════════════════════════════════════
        # CAPITULATION DETECTED: True entry signals
        # ═══════════════════════════════════════════════════════════════
        if rsi < 20:
            # TRUE capitulation - retail is being liquidated
            # NOW we buy
            return RetailSignal(
                symbol=symbol,
                retail_direction="CAPITULATING_LONG",
                counter_direction="LONG",  # We buy here
                confidence=0.85,
                reason=f"RSI {rsi:.0f} - CAPITULATION! Retail longs liquidated. Enter LONG.",
                wait_for_capitulation=False,
            )

        if rsi > 85:
            # TRUE mania - shorts are being liquidated
            # But be careful - could be genuine breakout
            # Only short if price is also at resistance
            if range_position > 0.9:
                return RetailSignal(
                    symbol=symbol,
                    retail_direction="CAPITULATING_SHORT",
                    counter_direction="SHORT",  # We short here
                    confidence=0.80,
                    reason=f"RSI {rsi:.0f} at resistance - MANIA! Shorts liquidated. Enter SHORT.",
                    wait_for_capitulation=False,
                )

        # ═══════════════════════════════════════════════════════════════
        # TRAP 3: Support/Resistance Fakeout
        # ═══════════════════════════════════════════════════════════════
        if range_position < 0.1 and price_change_24h < -5:
            # Price crashed to support with momentum
            # Retail expects bounce - MMs might push through
            return RetailSignal(
                symbol=symbol,
                retail_direction="LONG",
                counter_direction="WAIT",
                confidence=0.5,
                reason="At support after crash - retail expects bounce. Wait for confirmation.",
                wait_for_capitulation=True,
            )

        return None

    def get_capitulation_bonus(self, rsi: Optional[float]) -> float:
        """
        Get confidence bonus for capitulation signals.

        The more extreme the RSI, the higher the bonus.
        """
        if rsi is None:
            return 1.0

        if rsi < 15:
            return 1.30  # 30% bonus for extreme oversold
        elif rsi < 20:
            return 1.20  # 20% bonus
        elif rsi > 90:
            return 1.25  # 25% bonus for extreme overbought
        elif rsi > 85:
            return 1.15  # 15% bonus

        return 1.0


class DynamicLeverageCalculator:
    """
    Dynamic leverage based on confidence, volatility, and win rate.

    Philosophy (CONSERVATIVE):
    - High confidence + low volatility = max 10x leverage
    - Medium confidence = standard 5-7x leverage
    - Low confidence or high volatility = min 3x leverage

    SAFETY FIRST: Max leverage capped at 10x to prevent catastrophic losses.
    """

    def __init__(
        self,
        min_leverage: float = 3.0,
        standard_leverage: float = 5.0,
        max_leverage: float = 10.0,  # SAFETY: Hard cap at 10x
    ):
        self.min_leverage = min_leverage
        self.standard_leverage = standard_leverage
        self.max_leverage = max_leverage
        self._win_rates: Dict[str, float] = {}  # Per-symbol win rates

    def calculate_leverage(
        self,
        confidence: float,
        atr_pct: float,  # ATR as % of price (volatility)
        win_rate: float = 0.5,
        is_reentry: bool = False,
        is_capitulation: bool = False,
    ) -> float:
        """
        Calculate optimal leverage for a trade.

        Args:
            confidence: Trade confidence 0-1
            atr_pct: ATR as percentage of price (e.g., 0.02 = 2%)
            win_rate: Historical win rate 0-1
            is_reentry: True if this is a re-entry at better price
            is_capitulation: True if this is a capitulation signal

        Returns:
            Optimal leverage (3x to 10x) - CAPPED FOR SAFETY
        """
        # Base leverage from confidence
        # High confidence (0.85+) = use max leverage
        # Medium confidence (0.7-0.85) = standard leverage
        # Low confidence (<0.7) = min leverage
        if confidence >= 0.90:
            base_lev = self.max_leverage  # 10x
        elif confidence >= 0.85:
            base_lev = self.max_leverage * 0.8  # 8x
        elif confidence >= 0.80:
            base_lev = self.standard_leverage * 1.4  # 7x
        elif confidence >= 0.75:
            base_lev = self.standard_leverage  # 5x
        elif confidence >= 0.70:
            base_lev = self.standard_leverage * 0.8  # 4x
        else:
            base_lev = self.min_leverage  # 3x

        # Volatility adjustment
        # High ATR = reduce leverage (more volatile = more risk)
        # 2% ATR is "normal", adjust from there
        volatility_factor = 0.02 / max(atr_pct, 0.005)
        volatility_factor = max(0.5, min(1.5, volatility_factor))

        # Win rate adjustment
        # Good win rate = can afford more leverage
        if win_rate > 0.6:
            win_factor = 1.2
        elif win_rate > 0.5:
            win_factor = 1.0
        else:
            win_factor = 0.7

        # Re-entry bonus (capped to not exceed max leverage)
        reentry_factor = 1.1 if is_reentry else 1.0  # Reduced from 1.3

        # Capitulation bonus (capped to not exceed max leverage)
        capitulation_factor = 1.15 if is_capitulation else 1.0  # Reduced from 1.4

        # Calculate final leverage
        leverage = base_lev * volatility_factor * win_factor * reentry_factor * capitulation_factor

        # Clamp to limits
        leverage = max(self.min_leverage, min(self.max_leverage, leverage))

        return round(leverage, 1)

    def update_win_rate(self, symbol: str, won: bool):
        """Update win rate for a symbol after a trade closes."""
        current = self._win_rates.get(symbol, 0.5)
        # Exponential moving average with alpha=0.1
        self._win_rates[symbol] = current * 0.9 + (1.0 if won else 0.0) * 0.1


# Global instances
_counter_retail: Optional[CounterRetailStrategy] = None
_dynamic_leverage: Optional[DynamicLeverageCalculator] = None


def get_counter_retail_strategy() -> CounterRetailStrategy:
    """Get or create the global counter-retail strategy."""
    global _counter_retail
    if _counter_retail is None:
        _counter_retail = CounterRetailStrategy()
    return _counter_retail


def get_dynamic_leverage_calculator() -> DynamicLeverageCalculator:
    """Get or create the global dynamic leverage calculator."""
    global _dynamic_leverage
    if _dynamic_leverage is None:
        _dynamic_leverage = DynamicLeverageCalculator(
            min_leverage=3.0,  # Safer minimum
            standard_leverage=5.0,  # Conservative standard
            max_leverage=10.0,  # HARD CAP at 10x for safety
        )
    return _dynamic_leverage
