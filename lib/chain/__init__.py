"""Sapphire on-chain intelligence module.

Provides adapters for free on-chain data sources (DeFiLlama, Hyperliquid,
CoinGecko) and an aggregator that synthesizes them into a single market regime.
"""

from .sources import (
    DefiLlamaClient,
    HyperliquidClient,
    CoinGeckoClient,
)
from .intelligence import (
    ChainIntelligence,
    MarketOverview,
    FundingSnapshot,
    OISnapshot,
    TVLTrend,
    StablecoinFlows,
    MarketRegime,
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
