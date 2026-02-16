"""
Adaptive TP/SL Calculator - Dynamic Risk Management

Uses trade history, volatility (ATR), and market conditions to set
optimal take-profit and stop-loss levels for each trade.

Key Features:
- ATR-based volatility scaling (wider stops in volatile markets)
- Symbol-specific tuning (learns from historical win rates)
- Win-rate adjusted R:R (high win rate = tighter TP, lower = wider)
- Trailing stop management with breakeven activation
- Confidence-based sizing multiplier
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class AdaptiveTPSL:
    """Container for calculated TP/SL values."""

    tp_pct: float  # Take Profit percentage (e.g., 0.03 = 3%)
    sl_pct: float  # Stop Loss percentage
    tp_price: float  # Actual TP price
    sl_price: float  # Actual SL price
    trailing_activation_pct: float  # When to activate trailing stop
    trailing_distance_pct: float  # Trailing stop distance
    reasoning: str  # Explanation for transparency


class AdaptiveTPSLCalculator:
    """
    Calculates dynamic TP/SL based on multiple factors.

    Philosophy:
    - "Maximum money" = maximize expected value per trade
    - E[V] = (Win Rate × Avg Win) - (Loss Rate × Avg Loss)
    - We optimize both: increasing wins via smart entry AND reducing losses via adaptive stops
    """

    # Base settings (will be modified by conditions)
    BASE_TP_PCT = 0.025  # 2.5% base TP
    BASE_SL_PCT = 0.015  # 1.5% base SL (1.67R minimum)

    # ATR scaling bounds
    MIN_TP_PCT = 0.015  # Never less than 1.5% TP
    MAX_TP_PCT = 0.08  # Never more than 8% TP
    MIN_SL_PCT = 0.008  # Never less than 0.8% SL
    MAX_SL_PCT = 0.04  # Never more than 4% SL

    # Trailing stop settings
    TRAILING_ACTIVATION_DEFAULT = 0.02  # Activate after 2% profit
    TRAILING_DISTANCE_DEFAULT = 0.012  # Trail at 1.2%

    def __init__(self, performance_tracker=None, feature_pipeline=None):
        """
        Initialize with optional dependencies.

        Args:
            performance_tracker: PerformanceTracker instance for trade history
            feature_pipeline: FeaturePipeline for ATR/volatility data
        """
        self.performance_tracker = performance_tracker
        self.feature_pipeline = feature_pipeline

        # Cache for ATR values (refreshed periodically)
        self._atr_cache: Dict[str, float] = {}
        self._atr_cache_time: Dict[str, float] = {}

    async def calculate(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        agent_id: str = None,
        consensus_confidence: float = 0.7,
        market_analysis: Dict[str, Any] = None,
    ) -> AdaptiveTPSL:
        """
        Calculate optimal TP/SL for a trade.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: "BUY" or "SELL"
            entry_price: Entry price of the trade
            agent_id: Optional agent ID for history lookup
            consensus_confidence: Swarm confidence (0-1)
            market_analysis: Pre-fetched analysis dict (optional, avoids extra API call)

        Returns:
            AdaptiveTPSL with calculated values
        """
        reasons = []

        # 1. START WITH BASE VALUES
        tp_pct = self.BASE_TP_PCT
        sl_pct = self.BASE_SL_PCT

        # 2. VOLATILITY ADJUSTMENT (ATR-based)
        atr_multiplier = 1.0
        try:
            if market_analysis and "atr" in market_analysis:
                atr = market_analysis["atr"]
            elif self.feature_pipeline:
                analysis = await self.feature_pipeline.get_market_analysis(symbol)
                atr = analysis.get("atr", 0)
            else:
                atr = 0

            if atr > 0 and entry_price > 0:
                atr_pct = atr / entry_price

                # ATR reference: 1% is "normal", scale from there
                if atr_pct > 0.02:  # High volatility (>2% ATR)
                    atr_multiplier = 1.5
                    reasons.append(f"High Vol (ATR {atr_pct:.1%})")
                elif atr_pct > 0.01:  # Normal volatility
                    atr_multiplier = 1.0 + (atr_pct - 0.01) * 25  # Scale 1.0 to 1.25
                    reasons.append(f"Normal Vol (ATR {atr_pct:.1%})")
                else:  # Low volatility (<1% ATR)
                    atr_multiplier = 0.8
                    reasons.append(f"Low Vol (ATR {atr_pct:.1%})")
        except Exception as e:
            logger.warning(f"ATR calculation failed for {symbol}: {e}")
            reasons.append("ATR unavailable")

        # Apply ATR scaling
        tp_pct *= atr_multiplier
        sl_pct *= atr_multiplier

        # 3. SYMBOL-SPECIFIC WIN RATE ADJUSTMENT
        win_rate = 0.5  # Default neutral
        try:
            if self.performance_tracker and agent_id:
                win_rate = self.performance_tracker.get_symbol_win_rate(agent_id, symbol)
                total_trades = 0
                stats = self.performance_tracker.get_symbol_stats(agent_id, symbol)
                if stats:
                    total_trades = stats.get("wins", 0) + stats.get("losses", 0)

                if total_trades >= 5:  # Only adjust if we have enough data
                    if win_rate > 0.65:  # High win rate
                        # Tighter TP (take profits faster), slightly looser SL
                        tp_pct *= 0.85  # 15% reduction
                        sl_pct *= 1.1  # 10% increase
                        reasons.append(f"High WR ({win_rate:.0%}): Tighter TP")
                    elif win_rate < 0.45:  # Low win rate
                        # Wider TP (let winners run), tighter SL
                        tp_pct *= 1.2  # 20% increase
                        sl_pct *= 0.85  # 15% reduction
                        reasons.append(f"Low WR ({win_rate:.0%}): Wider TP, Tight SL")
                    else:
                        reasons.append(f"WR: {win_rate:.0%} (balanced)")
                else:
                    reasons.append(f"History: {total_trades} trades (learning)")
        except Exception as e:
            logger.warning(f"Win rate lookup failed for {symbol}: {e}")

        # 4. CONFIDENCE ADJUSTMENT
        if consensus_confidence >= 0.85:
            # Very high confidence = can be more aggressive
            tp_pct *= 1.15  # Target higher
            reasons.append(f"High Conf ({consensus_confidence:.0%}): Aggressive TP")
        elif consensus_confidence < 0.65:
            # Lower confidence = be more conservative
            sl_pct *= 0.9  # Tighter stop
            tp_pct *= 0.9  # Don't reach as far
            reasons.append(f"Low Conf ({consensus_confidence:.0%}): Conservative")

        # 5. MARKET REGIME ADJUSTMENT
        if market_analysis:
            trend = market_analysis.get("trend", "NEUTRAL")
            rsi = market_analysis.get("rsi", 50)

            # Trend-aligned trades get more room
            if (side == "BUY" and trend == "BULLISH") or (side == "SELL" and trend == "BEARISH"):
                tp_pct *= 1.1  # 10% more room for aligned trades
                reasons.append("Trend Aligned")
            elif (side == "BUY" and trend == "BEARISH") or (side == "SELL" and trend == "BULLISH"):
                sl_pct *= 0.85  # Tighter stop for counter-trend
                reasons.append("⚠️ Counter-Trend")

            # RSI extremes
            if (side == "BUY" and rsi < 30) or (side == "SELL" and rsi > 70):
                tp_pct *= 1.2  # Oversold/overbought = potential for bigger move
                reasons.append(f"RSI Extreme ({rsi:.0f})")

        # 6. ENFORCE BOUNDS
        tp_pct = max(self.MIN_TP_PCT, min(self.MAX_TP_PCT, tp_pct))
        sl_pct = max(self.MIN_SL_PCT, min(self.MAX_SL_PCT, sl_pct))

        # Ensure minimum R:R of 1.5 (never risk more than potential gain / 1.5)
        min_rr = 1.5
        if tp_pct / sl_pct < min_rr:
            sl_pct = tp_pct / min_rr
            reasons.append(f"R:R enforced (≥{min_rr:.1f})")

        # 7. CALCULATE ACTUAL PRICES
        if side == "BUY":
            tp_price = entry_price * (1 + tp_pct)
            sl_price = entry_price * (1 - sl_pct)
        else:  # SELL
            tp_price = entry_price * (1 - tp_pct)
            sl_price = entry_price * (1 + sl_pct)

        # 8. TRAILING STOP SETTINGS
        # Activate trailing when position is in enough profit
        trailing_activation = self.TRAILING_ACTIVATION_DEFAULT
        trailing_distance = self.TRAILING_DISTANCE_DEFAULT

        # Adjust based on volatility
        if atr_multiplier > 1.2:
            trailing_activation *= 1.3  # Wait longer in volatile markets
            trailing_distance *= 1.3  # Wider trail

        # Adjust based on win rate (high win rate = trail tighter)
        if win_rate > 0.6:
            trailing_distance *= 0.85  # Tighter trail for consistent winners

        # Build reasoning string
        rr_ratio = tp_pct / sl_pct if sl_pct > 0 else 0
        reasoning = f"TP: {tp_pct:.1%} | SL: {sl_pct:.1%} | R:R: {rr_ratio:.1f}. "
        reasoning += " | ".join(reasons) if reasons else "Default settings"

        logger.info(f"📊 Adaptive TP/SL for {symbol} {side}: {reasoning}")

        return AdaptiveTPSL(
            tp_pct=tp_pct,
            sl_pct=sl_pct,
            tp_price=tp_price,
            sl_price=sl_price,
            trailing_activation_pct=trailing_activation,
            trailing_distance_pct=trailing_distance,
            reasoning=reasoning,
        )

    def adjust_for_trailing(
        self,
        current_pnl_pct: float,
        current_sl_pct: float,
        entry_price: float,
        high_water_mark: float,
        side: str,
        trailing_activation: float,
        trailing_distance: float,
    ) -> Tuple[float, str]:
        """
        Calculate new SL based on trailing stop logic.

        Args:
            current_pnl_pct: Current PnL percentage
            current_sl_pct: Current SL percentage from entry
            entry_price: Original entry price
            high_water_mark: Highest profit seen
            side: "BUY" or "SELL"
            trailing_activation: When to activate trailing (e.g., 0.02)
            trailing_distance: Trail distance (e.g., 0.012)

        Returns:
            Tuple of (new_sl_price, update_reason) - None if no update needed
        """
        # Only trail if we've passed activation threshold
        if current_pnl_pct < trailing_activation:
            return None, None

        if side == "BUY":
            # New SL is high_water_mark minus trailing distance
            new_sl_price = high_water_mark * (1 - trailing_distance)

            # Only update if new SL is higher than current
            current_sl_price = entry_price * (1 - current_sl_pct)
            if new_sl_price > current_sl_price:
                locked_profit = (new_sl_price - entry_price) / entry_price
                return new_sl_price, f"🔒 Trailing: Locked {locked_profit:.1%} profit"
        else:  # SELL
            # New SL is low_water_mark plus trailing distance
            new_sl_price = high_water_mark * (
                1 + trailing_distance
            )  # high_water_mark is actually low for shorts

            current_sl_price = entry_price * (1 + current_sl_pct)
            if new_sl_price < current_sl_price:
                locked_profit = (entry_price - new_sl_price) / entry_price
                return new_sl_price, f"🔒 Trailing: Locked {locked_profit:.1%} profit"

        return None, None


# Global instance (lazy-loaded)
_adaptive_calculator: Optional[AdaptiveTPSLCalculator] = None


def get_adaptive_tpsl_calculator(
    performance_tracker=None,
    feature_pipeline=None,
) -> AdaptiveTPSLCalculator:
    """Get or create the global AdaptiveTPSLCalculator instance."""
    global _adaptive_calculator
    if _adaptive_calculator is None:
        _adaptive_calculator = AdaptiveTPSLCalculator(
            performance_tracker=performance_tracker,
            feature_pipeline=feature_pipeline,
        )
    return _adaptive_calculator
