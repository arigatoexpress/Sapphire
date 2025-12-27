"""Arbitrage detection and execution engine for cross-market opportunities."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:
    np = None

from .client import AsterClient
from .config import Settings
from .strategy import MarketSnapshot

logger = logging.getLogger(__name__)


@dataclass
class ArbitrageOpportunity:
    """Represents a detected arbitrage opportunity."""

    type: str  # funding, triangular, cross_exchange
    symbols: List[str]
    entry_prices: Dict[str, float]
    expected_profit: float  # In percentage
    confidence: float
    execution_time_window: float  # Seconds
    metadata: Dict[str, Any]
    detected_at: datetime


class ArbitrageEngine:
    """Detects and manages arbitrage opportunities across markets."""

    def __init__(self, exchange: AsterClient, settings: Settings):
        self._exchange = exchange
        self._settings = settings
        self._min_profit_threshold = 0.002  # 0.2% minimum profit
        self._max_execution_time = 0.5  # 500ms max execution time
        self._funding_rate_cache: Dict[str, float] = {}
        self._last_funding_update = datetime.utcnow()

    async def scan_opportunities(
        self, market: Dict[str, MarketSnapshot]
    ) -> List[ArbitrageOpportunity]:
        """Scan for all types of arbitrage opportunities."""
        opportunities = []

        # Run different arbitrage scans in parallel
        tasks = [
            self._scan_funding_arbitrage(market),
            self._scan_triangular_arbitrage(market),
            self._scan_cross_symbol_arbitrage(market),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, list):
                opportunities.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Arbitrage scan error: {result}")

        # Sort by expected profit
        opportunities.sort(key=lambda x: x.expected_profit, reverse=True)

        return opportunities

    async def _scan_funding_arbitrage(
        self, market: Dict[str, MarketSnapshot]
    ) -> List[ArbitrageOpportunity]:
        """Scan for funding rate arbitrage opportunities."""
        opportunities = []

        # Update funding rates if needed
        if (datetime.utcnow() - self._last_funding_update).seconds > 300:  # 5 minutes
            await self._update_funding_rates(list(market.keys()))

        for symbol, snapshot in market.items():
            funding_rate = self._funding_rate_cache.get(symbol, 0)

            # Calculate annualized funding rate
            # Funding typically paid 3x daily on most exchanges
            annualized_funding = funding_rate * 3 * 365

            # Check if funding rate arbitrage is profitable
            if abs(annualized_funding) > self._min_profit_threshold * 100:
                # For significant funding, we can:
                # - If positive: short perp, potentially long spot
                # - If negative: long perp, potentially short spot

                direction = "SHORT" if funding_rate > 0 else "LONG"
                expected_profit = abs(funding_rate) * 100  # As percentage

                opportunity = ArbitrageOpportunity(
                    type="funding",
                    symbols=[symbol],
                    entry_prices={symbol: snapshot.price},
                    expected_profit=expected_profit,
                    confidence=0.8 if abs(funding_rate) > 0.001 else 0.6,
                    execution_time_window=300,  # 5 minutes until next funding
                    metadata={
                        "funding_rate": funding_rate,
                        "annualized_rate": annualized_funding,
                        "direction": direction,
                        "next_funding": self._estimate_next_funding(),
                    },
                    detected_at=datetime.utcnow(),
                )

                if expected_profit > self._min_profit_threshold * 100:
                    opportunities.append(opportunity)

        return opportunities

    async def _scan_triangular_arbitrage(
        self, market: Dict[str, MarketSnapshot]
    ) -> List[ArbitrageOpportunity]:
        """Scan for triangular arbitrage opportunities."""
        opportunities = []

        # Group symbols by base currency for triangular paths
        base_groups = self._group_by_base_currency(market)

        # Look for triangular arbitrage: e.g., BTC -> ETH -> USDT -> BTC
        for base in ["BTC", "ETH", "BNB"]:
            if base + "USDT" not in market:
                continue

            base_price = market[base + "USDT"].price

            # Find all pairs that trade against this base
            for symbol, snapshot in market.items():
                if symbol.endswith(base) and symbol != base + "USDT":
                    # Extract the other currency
                    other = symbol.replace(base, "")

                    # Check if we have the USDT pair for the other currency
                    if other + "USDT" in market:
                        # Calculate triangular arbitrage
                        # Path: USDT -> base -> other -> USDT
                        path1_price = 1 / base_price  # USDT to base
                        path2_price = snapshot.price  # base to other
                        path3_price = market[other + "USDT"].price  # other to USDT

                        # Total return of the triangular path
                        total_return = path1_price * path2_price * path3_price
                        profit = (total_return - 1) * 100  # As percentage

                        if profit > self._min_profit_threshold * 100:
                            opportunity = ArbitrageOpportunity(
                                type="triangular",
                                symbols=[base + "USDT", symbol, other + "USDT"],
                                entry_prices={
                                    base + "USDT": base_price,
                                    symbol: snapshot.price,
                                    other + "USDT": market[other + "USDT"].price,
                                },
                                expected_profit=profit,
                                confidence=0.7,  # Triangular arb is complex
                                execution_time_window=1.0,  # 1 second window
                                metadata={
                                    "path": f"USDT->{base}->{other}->USDT",
                                    "legs": [
                                        {"from": "USDT", "to": base, "rate": path1_price},
                                        {"from": base, "to": other, "rate": path2_price},
                                        {"from": other, "to": "USDT", "rate": path3_price},
                                    ],
                                },
                                detected_at=datetime.utcnow(),
                            )
                            opportunities.append(opportunity)

        return opportunities

    async def _scan_cross_symbol_arbitrage(
        self, market: Dict[str, MarketSnapshot]
    ) -> List[ArbitrageOpportunity]:
        """Scan for cross-symbol arbitrage (e.g., synthetic positions)."""
        opportunities = []

        # Look for correlated pairs with divergence
        correlations = {
            ("BTCUSDT", "ETHUSDT"): 0.8,  # Historical correlation
            ("BNBUSDT", "ETHUSDT"): 0.7,
            ("SOLUSDT", "AVAXUSDT"): 0.75,
        }

        for (symbol1, symbol2), expected_corr in correlations.items():
            if symbol1 not in market or symbol2 not in market:
                continue

            price1 = market[symbol1].price
            price2 = market[symbol2].price

            # Calculate current ratio and historical average
            current_ratio = price1 / price2

            # Simplified: assume historical ratio based on correlation
            # In production, would use actual historical data
            historical_ratio = current_ratio * (1 + random.gauss(0, 0.01))

            divergence = abs(current_ratio - historical_ratio) / historical_ratio

            if divergence > self._min_profit_threshold:
                # Determine which is overvalued/undervalued
                if current_ratio > historical_ratio:
                    # symbol1 overvalued relative to symbol2
                    long_symbol = symbol2
                    short_symbol = symbol1
                else:
                    long_symbol = symbol1
                    short_symbol = symbol2

                opportunity = ArbitrageOpportunity(
                    type="cross_symbol",
                    symbols=[long_symbol, short_symbol],
                    entry_prices={
                        long_symbol: market[long_symbol].price,
                        short_symbol: market[short_symbol].price,
                    },
                    expected_profit=divergence * 100,
                    confidence=expected_corr * 0.8,  # Confidence based on correlation
                    execution_time_window=60,  # 1 minute for pairs trade
                    metadata={
                        "strategy": "pairs_trade",
                        "current_ratio": current_ratio,
                        "historical_ratio": historical_ratio,
                        "divergence": divergence,
                        "correlation": expected_corr,
                        "action": f"Long {long_symbol}, Short {short_symbol}",
                    },
                    detected_at=datetime.utcnow(),
                )

                if divergence * 100 > self._min_profit_threshold * 100:
                    opportunities.append(opportunity)

        return opportunities

    async def _update_funding_rates(self, symbols: List[str]) -> None:
        """Update funding rates for all symbols."""
        try:
            # In production, this would fetch from exchange API
            # For now, simulate funding rates
            for symbol in symbols:
                # Simulate funding rates between -0.1% and 0.1%
                self._funding_rate_cache[symbol] = random.uniform(-0.001, 0.001)

            self._last_funding_update = datetime.utcnow()
        except Exception as e:
            logger.error(f"Failed to update funding rates: {e}")

    def _estimate_next_funding(self) -> datetime:
        """Estimate time until next funding payment."""
        now = datetime.utcnow()
        # Most exchanges have funding at 00:00, 08:00, 16:00 UTC
        funding_hours = [0, 8, 16]

        for hour in funding_hours:
            funding_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if funding_time > now:
                return funding_time

        # Next day's first funding
        return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    def _group_by_base_currency(self, market: Dict[str, MarketSnapshot]) -> Dict[str, List[str]]:
        """Group trading pairs by base currency."""
        groups = {}

        for symbol in market.keys():
            # Common base currencies
            for base in ["USDT", "BTC", "ETH", "BNB", "BUSD"]:
                if symbol.endswith(base):
                    if base not in groups:
                        groups[base] = []
                    groups[base].append(symbol)
                    break

        return groups

    async def execute_arbitrage(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute an arbitrage opportunity."""
        try:
            start_time = datetime.utcnow()

            if opportunity.type == "funding":
                return await self._execute_funding_arbitrage(opportunity)
            elif opportunity.type == "triangular":
                return await self._execute_triangular_arbitrage(opportunity)
            elif opportunity.type == "cross_symbol":
                return await self._execute_cross_symbol_arbitrage(opportunity)

            execution_time = (datetime.utcnow() - start_time).total_seconds()
            if execution_time > self._max_execution_time:
                logger.warning(
                    f"Arbitrage execution took {execution_time:.3f}s, may have missed opportunity"
                )

            return False

        except Exception as e:
            logger.error(f"Failed to execute arbitrage: {e}")
            return False

    async def _execute_funding_arbitrage(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute funding rate arbitrage."""
        # In production, would place actual orders
        # For MVP, log the opportunity
        logger.info(
            f"Funding arbitrage opportunity: {opportunity.metadata['direction']} "
            f"{opportunity.symbols[0]} for {opportunity.expected_profit:.3f}% profit"
        )
        return True

    async def _execute_triangular_arbitrage(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute triangular arbitrage with atomic transactions."""
        # Would need to execute all three legs quickly
        # For MVP, log the opportunity
        logger.info(
            f"Triangular arbitrage: {opportunity.metadata['path']} "
            f"for {opportunity.expected_profit:.3f}% profit"
        )
        return True

    async def _execute_cross_symbol_arbitrage(self, opportunity: ArbitrageOpportunity) -> bool:
        """Execute cross-symbol pairs arbitrage."""
        # Would place simultaneous long/short orders
        logger.info(
            f"Pairs arbitrage: {opportunity.metadata['action']} "
            f"for {opportunity.expected_profit:.3f}% profit"
        )
        return True
