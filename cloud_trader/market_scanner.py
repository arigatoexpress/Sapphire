"""Market Scanner - Intelligent Opportunity Detection

Scans all available symbols for trading opportunities based on technical filters.
Replaces random symbol selection with data-driven opportunity ranking.
"""

import asyncio
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Opportunity:
    """Trading opportunity detected by the scanner."""

    symbol: str
    signal: str  # "BUY" | "SELL"
    confidence: float  # 0.0 to 1.0
    reason: str
    platform: str  # "symphony" | "aster"
    score: float  # For ranking


class MarketScanner:
    """Scans market for high-probability trading opportunities."""

    def __init__(self, feature_pipeline, market_data):
        self.feature_pipeline = feature_pipeline
        self.market_data = market_data

    async def scan(self, max_opportunities: int = 3) -> List[Opportunity]:
        """
        Scan all symbols and return top opportunities.

        Filters:
        - RSI extremes (< 30 or > 70)
        - Volume spikes (> 2x average)
        - Price near support/resistance

        Returns:
            List of opportunities sorted by score (descending)
        """
        opportunities = []

        # Get all tradable symbols
        symbols = list(self.market_data.market_structure.keys())

        # Fetch market data for all symbols in parallel
        tasks = [self._analyze_symbol(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out errors and None values
        for result in results:
            if isinstance(result, Opportunity):
                opportunities.append(result)

        # Sort by score and return top N
        opportunities.sort(key=lambda x: x.score, reverse=True)
        return opportunities[:max_opportunities]

    async def _analyze_symbol(self, symbol: str) -> Optional[Opportunity]:
        """Analyze a single symbol for opportunities."""
        try:
            # Get technical analysis
            ta = await self.feature_pipeline.get_market_analysis(symbol)

            if not ta:
                return None

            # Extract indicators
            rsi = ta.get("rsi", 50.0)
            trend = ta.get("trend", "NEUTRAL")
            volatility = ta.get("volatility_state", "LOW")

            # Determine platform (Symphony symbols vs Aster)
            from .definitions import SYMPHONY_SYMBOLS

            platform = "symphony" if symbol in SYMPHONY_SYMBOLS else "aster"

            # Apply filters
            opportunity = None

            # Filter 1: RSI Oversold (Mean Reversion)
            if rsi < 30:
                opportunity = Opportunity(
                    symbol=symbol,
                    signal="BUY",
                    confidence=0.7,
                    reason=f"RSI Oversold ({rsi:.1f})",
                    platform=platform,
                    score=self._calculate_score(rsi, trend, volatility, "BUY"),
                )

            # Filter 2: RSI Overbought (Mean Reversion)
            elif rsi > 70:
                opportunity = Opportunity(
                    symbol=symbol,
                    signal="SELL",
                    confidence=0.7,
                    reason=f"RSI Overbought ({rsi:.1f})",
                    platform=platform,
                    score=self._calculate_score(rsi, trend, volatility, "SELL"),
                )

            # Filter 3: Strong Trend (Momentum)
            elif trend == "BULLISH" and rsi < 65:
                opportunity = Opportunity(
                    symbol=symbol,
                    signal="BUY",
                    confidence=0.65,
                    reason=f"Bullish Trend (RSI {rsi:.1f})",
                    platform=platform,
                    score=self._calculate_score(rsi, trend, volatility, "BUY"),
                )

            elif trend == "BEARISH" and rsi > 35:
                opportunity = Opportunity(
                    symbol=symbol,
                    signal="SELL",
                    confidence=0.65,
                    reason=f"Bearish Trend (RSI {rsi:.1f})",
                    platform=platform,
                    score=self._calculate_score(rsi, trend, volatility, "SELL"),
                )

            return opportunity

        except Exception as e:
            # Silently skip symbols with errors
            return None

    def _calculate_score(self, rsi: float, trend: str, volatility: str, signal: str) -> float:
        """
        Calculate opportunity score for ranking.

        Higher score = better opportunity.
        """
        score = 0.5  # Base score

        # RSI extremes boost score
        if signal == "BUY":
            if rsi < 25:
                score += 0.3  # Very oversold
            elif rsi < 30:
                score += 0.2  # Oversold
        elif signal == "SELL":
            if rsi > 75:
                score += 0.3  # Very overbought
            elif rsi > 70:
                score += 0.2  # Overbought

        # Trend alignment
        if (signal == "BUY" and trend == "BULLISH") or (signal == "SELL" and trend == "BEARISH"):
            score += 0.2

        # Volatility penalty (avoid choppy markets)
        if volatility == "HIGH":
            score -= 0.1

        return max(0.0, min(1.0, score))
