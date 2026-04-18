"""Sapphire on-chain intelligence module.

Provides adapters for free on-chain data sources (DeFiLlama, Hyperliquid,
CoinGecko) and an aggregator that synthesizes them into a single market regime.
"""

from .intelligence import (
    ChainIntelligence,
    FundingSnapshot,
    MarketOverview,
    MarketRegime,
    OISnapshot,
    StablecoinFlows,
    TVLTrend,
)
from .sources import (
    CoinGeckoClient,
    DefiLlamaClient,
    HyperliquidClient,
)

__all__ = [
    "DefiLlamaClient",
    "HyperliquidClient",
    "CoinGeckoClient",
    "ChainIntelligence",
    "MarketOverview",
    "FundingSnapshot",
    "OISnapshot",
    "TVLTrend",
    "StablecoinFlows",
    "MarketRegime",
]
