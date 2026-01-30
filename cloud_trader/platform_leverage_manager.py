"""
Platform-Specific Intelligent Leverage Manager

Dynamically calculates optimal leverage based on:
- Platform and asset-specific limits
- Signal confidence and strength
- Market volatility
- Market regime (trending, ranging, volatile, calm)
- Portfolio leverage constraints

Platform Leverage Limits:
- Drift (Solana Perps): BTC/ETH 10x, SOL 20x, Altcoins 5x
- Hyperliquid (L1 Perps): BTC/ETH 50x, Altcoins 25x
- Aster (CEX-style): BTC 125x, ETH 100x, Altcoins 75x
- Symphony (Monad/Base): Uniform 1.1-25x range
- Jupiter (Spot DEX): No leverage (1x)
- Lighter (L2 DEX): No leverage (1x)
"""

import logging
import math
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional, List

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    """Market regime classifications"""
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    CALM = "calm"


@dataclass
class LeverageRecommendation:
    """Leverage recommendation with reasoning"""
    platform: str
    symbol: str
    recommended_leverage: float
    max_leverage: float  # Platform/asset limit
    confidence: float
    volatility: float
    regime: MarketRegime
    portfolio_leverage: float
    reasoning: str
    adjustments: Dict[str, float]  # Track each adjustment factor


class PlatformLeverageManager:
    """
    Intelligent leverage management for multi-platform trading.

    Formula:
    optimal_leverage = base_leverage × confidence × volatility_adj × regime_adj × portfolio_adj

    where:
      base_leverage = platform/asset limit (e.g., Aster BTC: 125x)
      confidence = signal confidence (0.3-1.0)
      volatility_adj = 1.0 - (volatility - 1%) × 8  (higher vol → lower leverage)
      regime_adj = {TRENDING: 1.0, VOLATILE: 0.6, CALM: 1.2, RANGING: 0.8}
      portfolio_adj = {portfolio_leverage < 5: 1.0, 5-10: 0.7, >10: 0.5}
    """

    # Platform and asset-specific leverage limits
    PLATFORM_LIMITS = {
        "drift": {
            "btc": 10,
            "eth": 10,
            "sol": 20,
            "default": 5,  # Altcoins
        },
        "hyperliquid": {
            "btc": 50,
            "eth": 50,
            "default": 25,  # Altcoins
        },
        "aster": {
            "btc": 125,
            "eth": 100,
            "default": 75,  # Altcoins
        },
        "symphony": {
            "default": 25,
            "min": 1.1,
        },
        "jupiter": {
            "default": 1,  # Spot only
        },
        "lighter": {
            "default": 1,  # Spot only
        },
    }

    # Regime-based leverage multipliers
    REGIME_MULTIPLIERS = {
        MarketRegime.TRENDING_UP: 1.0,
        MarketRegime.TRENDING_DOWN: 1.0,
        MarketRegime.RANGING: 0.8,
        MarketRegime.VOLATILE: 0.6,
        MarketRegime.CALM: 1.2,
    }

    def __init__(self):
        """Initialize platform leverage manager"""
        logger.info(f"📊 PlatformLeverageManager initialized with {len(self.PLATFORM_LIMITS)} platforms")

    def get_max_leverage(self, platform: str, symbol: str) -> float:
        """
        Get maximum leverage allowed for platform and asset.

        Args:
            platform: Platform name (drift, hyperliquid, aster, etc.)
            symbol: Trading symbol (BTC-PERP, SOL-PERP, etc.)

        Returns:
            Maximum leverage for the platform/asset combination
        """
        platform_lower = platform.lower()

        if platform_lower not in self.PLATFORM_LIMITS:
            logger.warning(f"Unknown platform: {platform}, defaulting to 1x leverage")
            return 1.0

        platform_config = self.PLATFORM_LIMITS[platform_lower]

        # Extract base asset from symbol (e.g., BTC-PERP -> btc, SOL-USDC -> sol)
        base_asset = symbol.split('-')[0].lower()

        # Check if asset has specific limit
        if base_asset in platform_config:
            max_lev = platform_config[base_asset]
        else:
            max_lev = platform_config.get("default", 1.0)

        logger.debug(f"Max leverage for {platform}/{symbol}: {max_lev}x")
        return max_lev

    def calculate_volatility_adjustment(self, volatility: float, base_leverage: float) -> float:
        """
        Calculate volatility adjustment factor.

        Higher volatility → lower leverage to maintain consistent risk.

        Formula: 1.0 - (volatility - 1%) × 8

        Examples:
        - 1% volatility (baseline): 1.0x (no adjustment)
        - 2% volatility: 0.92x (8% reduction)
        - 5% volatility: 0.68x (32% reduction)
        - 10% volatility: 0.28x (72% reduction)

        Args:
            volatility: Recent volatility (e.g., 0.02 for 2%)
            base_leverage: Base leverage before adjustment

        Returns:
            Volatility adjustment multiplier (0.2-1.0)
        """
        baseline_vol = 0.01  # 1% baseline volatility
        vol_impact = 8.0  # Sensitivity factor

        adjustment = 1.0 - (volatility - baseline_vol) * vol_impact

        # Clamp between 0.2 and 1.0
        adjustment = max(0.2, min(1.0, adjustment))

        return adjustment

    def calculate_regime_adjustment(self, regime: MarketRegime) -> float:
        """
        Calculate market regime adjustment factor.

        - TRENDING: 1.0x (full leverage in trends)
        - CALM: 1.2x (boost leverage in calm markets)
        - RANGING: 0.8x (reduce leverage in choppy markets)
        - VOLATILE: 0.6x (significantly reduce in volatile markets)

        Args:
            regime: Current market regime

        Returns:
            Regime adjustment multiplier
        """
        return self.REGIME_MULTIPLIERS.get(regime, 1.0)

    def calculate_portfolio_adjustment(self, portfolio_leverage: float) -> float:
        """
        Calculate portfolio-level leverage adjustment.

        Reduce individual position leverage when portfolio is already leveraged.

        - Portfolio leverage < 5x: 1.0x (no adjustment)
        - Portfolio leverage 5-10x: 0.7x (30% reduction)
        - Portfolio leverage > 10x: 0.5x (50% reduction)

        Args:
            portfolio_leverage: Current aggregate portfolio leverage

        Returns:
            Portfolio adjustment multiplier
        """
        if portfolio_leverage < 5.0:
            return 1.0
        elif portfolio_leverage < 10.0:
            return 0.7
        else:
            return 0.5

    def calculate_confidence_adjustment(self, confidence: float) -> float:
        """
        Calculate confidence-based adjustment.

        Linearly scales leverage with signal confidence.

        Args:
            confidence: Signal confidence (0.0-1.0)

        Returns:
            Confidence multiplier (clamped to 0.3-1.0)
        """
        # Clamp confidence to reasonable range
        confidence = max(0.3, min(1.0, confidence))
        return confidence

    def get_optimal_leverage(
        self,
        platform: str,
        symbol: str,
        confidence: float,
        signal_strength: float = 1.0,
        volatility: float = 0.05,
        regime: MarketRegime = MarketRegime.CALM,
        portfolio_leverage: float = 0.0,
    ) -> LeverageRecommendation:
        """
        Calculate optimal leverage for a trade.

        Args:
            platform: Platform name
            symbol: Trading symbol
            confidence: Signal confidence (0-1)
            signal_strength: Signal strength multiplier (0-1, default 1.0)
            volatility: Recent volatility (e.g., 0.05 for 5%)
            regime: Current market regime
            portfolio_leverage: Current portfolio aggregate leverage

        Returns:
            LeverageRecommendation with optimal leverage and reasoning
        """
        # Get platform/asset max leverage
        max_leverage = self.get_max_leverage(platform, symbol)

        # Calculate adjustment factors
        confidence_adj = self.calculate_confidence_adjustment(confidence)
        volatility_adj = self.calculate_volatility_adjustment(volatility, max_leverage)
        regime_adj = self.calculate_regime_adjustment(regime)
        portfolio_adj = self.calculate_portfolio_adjustment(portfolio_leverage)

        # Calculate optimal leverage
        optimal_leverage = (
            max_leverage
            * confidence_adj
            * volatility_adj
            * regime_adj
            * portfolio_adj
            * signal_strength
        )

        # Ensure we don't exceed platform limits
        optimal_leverage = max(1.0, min(optimal_leverage, max_leverage))

        # Build reasoning
        adjustments = {
            "confidence": confidence_adj,
            "volatility": volatility_adj,
            "regime": regime_adj,
            "portfolio": portfolio_adj,
            "signal_strength": signal_strength,
        }

        reasoning_parts = [
            f"Base: {max_leverage}x ({platform}/{symbol})",
            f"Confidence: {confidence:.2f} → {confidence_adj:.2f}x",
            f"Volatility: {volatility:.1%} → {volatility_adj:.2f}x",
            f"Regime: {regime.value} → {regime_adj:.2f}x",
            f"Portfolio: {portfolio_leverage:.1f}x → {portfolio_adj:.2f}x",
        ]

        if signal_strength != 1.0:
            reasoning_parts.append(f"Signal: {signal_strength:.2f}x")

        reasoning = " | ".join(reasoning_parts)
        reasoning += f" | Final: {optimal_leverage:.1f}x"

        logger.info(
            f"🎯 Leverage for {platform}/{symbol}: {optimal_leverage:.1f}x "
            f"(max: {max_leverage}x, conf: {confidence:.2f})"
        )

        return LeverageRecommendation(
            platform=platform,
            symbol=symbol,
            recommended_leverage=optimal_leverage,
            max_leverage=max_leverage,
            confidence=confidence,
            volatility=volatility,
            regime=regime,
            portfolio_leverage=portfolio_leverage,
            reasoning=reasoning,
            adjustments=adjustments,
        )

    def validate_leverage(
        self,
        platform: str,
        symbol: str,
        requested_leverage: float
    ) -> tuple[bool, Optional[str]]:
        """
        Validate if requested leverage is within platform limits.

        Args:
            platform: Platform name
            symbol: Trading symbol
            requested_leverage: Requested leverage amount

        Returns:
            (is_valid, error_message) tuple
        """
        max_leverage = self.get_max_leverage(platform, symbol)

        if requested_leverage > max_leverage:
            error = (
                f"Requested leverage {requested_leverage:.1f}x exceeds "
                f"{platform}/{symbol} limit of {max_leverage:.1f}x"
            )
            return False, error

        if requested_leverage < 1.0:
            error = f"Leverage must be >= 1.0x (requested: {requested_leverage:.1f}x)"
            return False, error

        return True, None

    def get_platform_info(self, platform: str) -> Dict:
        """Get platform leverage configuration"""
        return {
            "platform": platform,
            "limits": self.PLATFORM_LIMITS.get(platform.lower(), {}),
            "supported": platform.lower() in self.PLATFORM_LIMITS,
        }

    def get_all_platforms(self) -> List[str]:
        """Get list of all supported platforms"""
        return list(self.PLATFORM_LIMITS.keys())
