"""DataStore - Unified Data Access Layer

Provides a single interface for agents to query ANY market data:
- Technical indicators
- Sentiment data
- On-chain metrics
- Order flow
- Macro data

Design: Provider pattern + caching
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class TTLCache:
    """Simple TTL cache for data."""

    def __init__(self, ttl: int = 60):
        self.ttl = ttl
        self.cache: Dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            value, expiry = self.cache[key]
            if time.time() < expiry:
                return value
            else:
                del self.cache[key]
        return None

    def set(self, key: str, value: Any):
        self.cache[key] = (value, time.time() + self.ttl)


class DataProvider(ABC):
    """Base class for data providers."""

    @abstractmethod
    async def fetch(self, indicator: str, symbol: str, **params) -> Any:
        """Fetch specific indicator for symbol."""
        pass

    @abstractmethod
    def supports(self, indicator: str) -> bool:
        """Check if this provider supports the indicator."""
        pass


class TechnicalIndicatorProvider(DataProvider):
    """Provides technical analysis indicators."""

    def __init__(self, feature_pipeline):
        self.feature_pipeline = feature_pipeline
        self.supported_indicators = {
            "rsi",
            "macd",
            "ema",
            "sma",
            "atr",
            "bollinger_bands",
            "stochastic",
            "cci",
            "adx",
            "obv",
            "volume",
            "wyckoff",
            "fib_levels",
            "vsop",
            "price",
            "volatility_state",
        }

    def supports(self, indicator: str) -> bool:
        return indicator in self.supported_indicators

    async def fetch(self, indicator: str, symbol: str, **params) -> Any:
        """Fetch technical indicator."""
        # Get full market analysis from feature pipeline
        analysis = await self.feature_pipeline.get_market_analysis(symbol)

        if not analysis:
            return None

        # Extract specific indicator
        if indicator == "rsi":
            return analysis.get("rsi", 50.0)

        elif indicator == "macd":
            return {
                "macd": analysis.get("macd_val", 0.0),  # Updated key to avoid confusion
                "signal": analysis.get("macd_signal", 0.0),
                "histogram": analysis.get("macd_hist", 0.0),
                "trend": analysis.get("trend", "NEUTRAL"),
            }

        elif indicator == "volume":
            return analysis.get("volume", 0.0)

        elif indicator in ["ema", "sma"]:
            period = params.get("period", 20)
            return analysis.get(f"ema_{period}", analysis.get("price", 0.0))

        elif indicator == "atr":
            return analysis.get("atr", 0.0)

        elif indicator == "bollinger_bands":
            return {
                "upper": analysis.get("bb_upper", 0.0),
                "mid": analysis.get("bb_mid", 0.0),
                "lower": analysis.get("bb_lower", 0.0),
                "bandwidth": (analysis.get("bb_upper", 0) - analysis.get("bb_lower", 0))
                / analysis.get("bb_mid", 1.0),
            }

        elif indicator == "stochastic":
            return {"k": analysis.get("stoch_k", 0.0), "d": analysis.get("stoch_d", 0.0)}

        elif indicator == "cci":
            return analysis.get("cci", 0.0)

        elif indicator == "adx":
            return analysis.get("adx", 0.0)

        elif indicator == "obv":
            return analysis.get("obv", 0.0)

        elif indicator == "wyckoff":
            return analysis.get("wyckoff_phase", "NEUTRAL")

        elif indicator == "fib_levels":
            return {"0.5": analysis.get("fib_0_5", 0.0), "0.618": analysis.get("fib_0_618", 0.0)}

        elif indicator == "vsop":
            return analysis.get("vsop", 50.0)

        elif indicator == "price":
            return analysis.get("price", 0.0)

        elif indicator == "volatility_state":
            return analysis.get("volatility_state", "LOW")

        # Default: return None if not implemented
        return None


class OrderFlowProvider(DataProvider):
    """Provides order flow and market microstructure data."""

    def __init__(self, feature_pipeline):
        self.feature_pipeline = feature_pipeline
        self.supported_indicators = {"bid_pressure", "spread", "order_book_depth"}

    def supports(self, indicator: str) -> bool:
        return indicator in self.supported_indicators

    async def fetch(self, indicator: str, symbol: str, **params) -> Any:
        analysis = await self.feature_pipeline.get_market_analysis(symbol)

        if not analysis:
            return None

        if indicator == "bid_pressure":
            return analysis.get("bid_pressure", 0.5)

        elif indicator == "spread":
            return analysis.get("spread_pct", 0.0)

        elif indicator == "order_book_depth":
            # TODO: Implement actual order book analysis
            return {"bids": 0.0, "asks": 0.0}

        return None


class SentimentProvider(DataProvider):
    """Provides sentiment data (future: integrate APIs)."""

    def __init__(self):
        self.supported_indicators = {"social_sentiment", "news_sentiment", "fear_greed_index"}

    def supports(self, indicator: str) -> bool:
        return indicator in self.supported_indicators

    async def fetch(self, indicator: str, symbol: str, **params) -> Any:
        """
        Fetch sentiment data.

        TODO: Integrate with real APIs:
        - Twitter/X API for social sentiment
        - News API for news sentiment
        - Alternative.me for Fear & Greed Index
        """
        # Placeholder: return neutral sentiment
        if indicator == "social_sentiment":
            return 0.5  # Neutral (0.0 = very bearish, 1.0 = very bullish)

        elif indicator == "news_sentiment":
            return 0.5

        elif indicator == "fear_greed_index":
            return 50.0  # Neutral (0-100 scale)

        return None


class MacroDataProvider(DataProvider):
    """Provides macro market data."""

    def __init__(self):
        self.supported_indicators = {"btc_dominance", "market_cap", "total_volume"}

    def supports(self, indicator: str) -> bool:
        return indicator in self.supported_indicators

    async def fetch(self, indicator: str, symbol: str, **params) -> Any:
        """
        Fetch macro data.

        TODO: Integrate with CoinGecko/CoinMarketCap APIs
        """
        # Placeholder
        if indicator == "btc_dominance":
            return 50.0  # %

        elif indicator == "market_cap":
            return 1000000000.0  # Total market cap

        elif indicator == "total_volume":
            return 50000000.0  # 24h volume

        return None


class DataStore:
    """
    Unified data access layer.

    Agents use this to query any indicator they want.
    """

    def __init__(self, feature_pipeline):
        # Initialize providers
        self.providers = [
            TechnicalIndicatorProvider(feature_pipeline),
            OrderFlowProvider(feature_pipeline),
            SentimentProvider(),
            MacroDataProvider(),
        ]

        # Cache with 60s TTL
        self.cache = TTLCache(ttl=60)

        # Track what indicators are being used
        self.usage_stats = defaultdict(int)

    async def get(self, indicator: str, symbol: str, **params) -> Any:
        """
        Get any indicator for any symbol.

        Examples:
            await ds.get("rsi", "BTC-USDC", period=14)
            await ds.get("bid_pressure", "ETH-USDC")
            await ds.get("social_sentiment", "MON")

        Returns:
            Indicator value or None if not available
        """
        # Build cache key
        cache_key = f"{indicator}:{symbol}:{params}"

        # Check cache
        cached = self.cache.get(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit: {indicator} for {symbol}")
            return cached

        # Find provider
        provider = self._find_provider(indicator)
        if not provider:
            logger.warning(f"No provider for indicator: {indicator}")
            return None

        # Fetch data
        try:
            result = await provider.fetch(indicator, symbol, **params)

            # Cache result
            if result is not None:
                self.cache.set(cache_key, result)

            # Track usage
            self.usage_stats[indicator] += 1

            return result

        except Exception as e:
            logger.error(f"Error fetching {indicator} for {symbol}: {e}")
            return None

    def _find_provider(self, indicator: str) -> Optional[DataProvider]:
        """Find provider that supports the indicator."""
        for provider in self.providers:
            if provider.supports(indicator):
                return provider
        return None

    def get_available_indicators(self) -> list[str]:
        """Get list of all available indicators."""
        indicators = set()
        for provider in self.providers:
            if hasattr(provider, "supported_indicators"):
                indicators.update(provider.supported_indicators)
        return sorted(indicators)

    def get_usage_stats(self) -> Dict[str, int]:
        """Get indicator usage statistics."""
        return dict(self.usage_stats)


# Optimized BigQuery Streaming Integration
async def get_bigquery_streamer():
    """Get the optimized BigQuery streamer instance for production."""
    try:
        from .optimized_bigquery import get_optimized_bigquery_streamer

        return await get_optimized_bigquery_streamer()
    except Exception as e:
        logger.error(f"Failed to load BigQuery streamer: {e}")
        return None


async def close_bigquery_streamer():
    """Close the optimized BigQuery streamer."""
    try:
        from .optimized_bigquery import close_optimized_bigquery_streamer

        await close_optimized_bigquery_streamer()
    except Exception:
        pass


async def get_cache():
    return None


async def get_storage():
    return None


async def get_feature_store():
    return None


async def close_cache():
    pass


async def close_storage():
    pass
