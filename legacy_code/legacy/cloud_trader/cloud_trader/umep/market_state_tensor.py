"""
UMEP - Universal Market Encoding Protocol

Market State Tensor: A hierarchical, composable encoding that captures
market meaning in an AI-friendly format.

This is a novel contribution to the ACTS trading system.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class MarketRegime(Enum):
    """High-level market regime classification."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    BREAKOUT = "breakout"
    BREAKDOWN = "breakdown"


class RiskAppetite(Enum):
    """Market-wide risk sentiment."""

    RISK_ON = "risk_on"
    RISK_OFF = "risk_off"
    NEUTRAL = "neutral"


class TrendStrength(Enum):
    """Trend strength classification."""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"


class LiquidityLevel(Enum):
    """Order book liquidity depth."""

    DEEP = "deep"
    NORMAL = "normal"
    THIN = "thin"


@dataclass
class MacroContext:
    """Layer 1: Macro market context."""

    regime: MarketRegime = MarketRegime.RANGING
    risk_appetite: RiskAppetite = RiskAppetite.NEUTRAL
    correlation_clusters: Dict[str, float] = field(default_factory=dict)
    dominant_sector: Optional[str] = None
    btc_dominance_trend: Optional[str] = None  # "rising", "falling", "stable"
    funding_rates_aggregate: float = 0.0  # Average across majors

    def to_text(self) -> str:
        """Compress to LLM-friendly text."""
        parts = [
            f"Regime: {self.regime.value}",
            f"Risk: {self.risk_appetite.value}",
        ]
        if self.btc_dominance_trend:
            parts.append(f"BTC.D: {self.btc_dominance_trend}")
        if self.funding_rates_aggregate != 0:
            sign = "+" if self.funding_rates_aggregate > 0 else ""
            parts.append(f"Funding: {sign}{self.funding_rates_aggregate:.4f}")
        return " | ".join(parts)


@dataclass
class AssetState:
    """Layer 2: Individual asset state."""

    symbol: str

    # Price action
    price: float = 0.0
    change_24h: float = 0.0  # Percentage
    change_7d: float = 0.0

    # Momentum (-1 to 1, negative = bearish)
    momentum_1h: float = 0.0
    momentum_4h: float = 0.0
    momentum_1d: float = 0.0

    # Volatility (percentile 0-100)
    volatility_percentile: float = 50.0
    atr_percent: float = 0.0  # ATR as % of price

    # Trend
    trend_strength: TrendStrength = TrendStrength.NONE
    trend_direction: str = "neutral"  # "up", "down", "neutral"

    # Key levels (as % distance from current price)
    nearest_support_pct: float = 0.0
    nearest_resistance_pct: float = 0.0

    # Volume
    volume_ratio: float = 1.0  # Current vs 20-day average

    def to_text(self) -> str:
        """Compress to LLM-friendly text."""
        trend = f"{self.trend_direction} ({self.trend_strength.value})"

        return (
            f"{self.symbol}: ${self.price:.2f} ({self.change_24h:+.1f}%) | "
            f"Trend: {trend} | "
            f"Mom[1h/4h/1d]: {self.momentum_1h:.2f}/{self.momentum_4h:.2f}/{self.momentum_1d:.2f} | "
            f"Vol: P{self.volatility_percentile:.0f} | "
            f"S:{self.nearest_support_pct:.1f}% R:{self.nearest_resistance_pct:.1f}%"
        )


@dataclass
class Microstructure:
    """Layer 3: Order book and trade flow microstructure."""

    symbol: str

    # Order flow
    order_flow_imbalance: float = 0.0  # -1 (all sells) to 1 (all buys)
    taker_buy_ratio: float = 0.5  # % of volume from taker buys

    # Liquidity
    liquidity_level: LiquidityLevel = LiquidityLevel.NORMAL
    spread_bps: float = 0.0  # Spread in basis points

    # Recent activity
    large_order_flow: str = "neutral"  # "heavy_buying", "heavy_selling", "neutral"

    def to_text(self) -> str:
        """Compress to LLM-friendly text."""
        flow_emoji = (
            "🟢"
            if self.order_flow_imbalance > 0.2
            else ("🔴" if self.order_flow_imbalance < -0.2 else "⚪")
        )
        return (
            f"μStruct[{self.symbol}]: {flow_emoji} Flow: {self.order_flow_imbalance:+.2f} | "
            f"Liq: {self.liquidity_level.value} | "
            f"Spread: {self.spread_bps:.1f}bps"
        )


@dataclass
class MarketStateTensor:
    """
    Complete market state encoding.

    This is the core primitive of UMEP - a hierarchical, composable
    representation of market state that can be:
    1. Compressed to text for LLM consumption
    2. Serialized for storage/transmission
    3. Used for similarity matching in episodic memory
    """

    timestamp: datetime = field(default_factory=datetime.now)

    # Layer 1: Macro
    macro: MacroContext = field(default_factory=MacroContext)

    # Layer 2: Asset states (symbol -> AssetState)
    assets: Dict[str, AssetState] = field(default_factory=dict)

    # Layer 3: Microstructure (symbol -> Microstructure)
    microstructure: Dict[str, Microstructure] = field(default_factory=dict)

    # Layer 4: Semantic summary (LLM-generated)
    semantic_summary: str = ""

    # Metadata
    encoding_version: str = "1.0.0"
    source: str = "acts"

    def to_text(self, include_micro: bool = False, max_assets: int = 5) -> str:
        """
        Compress the entire market state to LLM-friendly text.

        This is the key innovation - converting complex market data
        into a format that fits in an LLM context window while
        preserving semantic meaning.
        """
        lines = []

        # Timestamp
        lines.append(f"📅 {self.timestamp.strftime('%Y-%m-%d %H:%M UTC')}")

        # Macro context
        lines.append(f"🌍 {self.macro.to_text()}")

        # Asset states (top N)
        if self.assets:
            lines.append("📊 Assets:")
            for i, (symbol, state) in enumerate(self.assets.items()):
                if i >= max_assets:
                    lines.append(f"   ... and {len(self.assets) - max_assets} more")
                    break
                lines.append(f"   {state.to_text()}")

        # Microstructure (optional)
        if include_micro and self.microstructure:
            lines.append("🔬 Microstructure:")
            for symbol, micro in list(self.microstructure.items())[:max_assets]:
                lines.append(f"   {micro.to_text()}")

        # Semantic summary
        if self.semantic_summary:
            lines.append(f"📝 Summary: {self.semantic_summary}")

        return "\n".join(lines)

    def to_embedding_text(self) -> str:
        """
        Generate text optimized for embedding/similarity search.
        Focus on features that matter for decision-making.
        """
        parts = []

        # Macro
        parts.append(f"regime:{self.macro.regime.value}")
        parts.append(f"risk:{self.macro.risk_appetite.value}")

        # Assets (sorted by relevance)
        for symbol, state in sorted(
            self.assets.items(), key=lambda x: abs(x[1].momentum_1h), reverse=True
        )[:3]:
            parts.append(
                f"{symbol}:trend_{state.trend_direction}_"
                f"mom_{state.momentum_1h:.1f}_"
                f"vol_p{state.volatility_percentile:.0f}"
            )

        return " ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for storage."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "encoding_version": self.encoding_version,
            "source": self.source,
            "macro": {
                "regime": self.macro.regime.value,
                "risk_appetite": self.macro.risk_appetite.value,
                "correlation_clusters": self.macro.correlation_clusters,
                "btc_dominance_trend": self.macro.btc_dominance_trend,
                "funding_rates_aggregate": self.macro.funding_rates_aggregate,
            },
            "assets": {
                symbol: {
                    "price": state.price,
                    "change_24h": state.change_24h,
                    "momentum_1h": state.momentum_1h,
                    "momentum_4h": state.momentum_4h,
                    "momentum_1d": state.momentum_1d,
                    "volatility_percentile": state.volatility_percentile,
                    "trend_strength": state.trend_strength.value,
                    "trend_direction": state.trend_direction,
                }
                for symbol, state in self.assets.items()
            },
            "semantic_summary": self.semantic_summary,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MarketStateTensor":
        """Deserialize from dictionary."""
        mst = cls(
            timestamp=datetime.fromisoformat(data["timestamp"]),
            encoding_version=data.get("encoding_version", "1.0.0"),
            source=data.get("source", "unknown"),
            semantic_summary=data.get("semantic_summary", ""),
        )

        # Reconstruct macro
        macro_data = data.get("macro", {})
        mst.macro = MacroContext(
            regime=MarketRegime(macro_data.get("regime", "ranging")),
            risk_appetite=RiskAppetite(macro_data.get("risk_appetite", "neutral")),
            correlation_clusters=macro_data.get("correlation_clusters", {}),
            btc_dominance_trend=macro_data.get("btc_dominance_trend"),
            funding_rates_aggregate=macro_data.get("funding_rates_aggregate", 0.0),
        )

        # Reconstruct assets
        for symbol, asset_data in data.get("assets", {}).items():
            mst.assets[symbol] = AssetState(
                symbol=symbol,
                price=asset_data.get("price", 0),
                change_24h=asset_data.get("change_24h", 0),
                momentum_1h=asset_data.get("momentum_1h", 0),
                momentum_4h=asset_data.get("momentum_4h", 0),
                momentum_1d=asset_data.get("momentum_1d", 0),
                volatility_percentile=asset_data.get("volatility_percentile", 50),
                trend_strength=TrendStrength(asset_data.get("trend_strength", "none")),
                trend_direction=asset_data.get("trend_direction", "neutral"),
            )

        return mst

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, json_str: str) -> "MarketStateTensor":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))


# Factory function for creating MST from market data
def create_market_state_tensor(
    prices: Dict[str, float],
    changes_24h: Dict[str, float],
    regime: str = "ranging",
    risk: str = "neutral",
    semantic_summary: str = "",
) -> MarketStateTensor:
    """
    Factory function to create a MarketStateTensor from basic market data.
    For full encoding, use the dedicated encoder classes.
    """
    mst = MarketStateTensor(
        macro=MacroContext(
            regime=MarketRegime(regime),
            risk_appetite=RiskAppetite(risk),
        ),
        semantic_summary=semantic_summary,
    )

    for symbol, price in prices.items():
        mst.assets[symbol] = AssetState(
            symbol=symbol,
            price=price,
            change_24h=changes_24h.get(symbol, 0.0),
        )

    return mst
