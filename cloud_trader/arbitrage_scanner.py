"""Cross-Platform Arbitrage Scanner

Detects price discrepancies across Aster, Hyperliquid, and Drift.
Enables risk-free profit opportunities when spreads exceed thresholds.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ArbitrageOpportunity:
    """Detected arbitrage opportunity."""

    symbol: str
    buy_platform: str
    sell_platform: str
    buy_price: float
    sell_price: float
    spread_pct: float  # Percentage spread
    estimated_profit_pct: float  # Net profit after fees
    timestamp: float

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "buy_platform": self.buy_platform,
            "sell_platform": self.sell_platform,
            "buy_price": self.buy_price,
            "sell_price": self.sell_price,
            "spread_pct": self.spread_pct,
            "estimated_profit_pct": self.estimated_profit_pct,
            "timestamp": self.timestamp,
        }


class ArbitrageScanner:
    """
    Scans for cross-platform arbitrage opportunities.

    Strategy:
    1. Fetch prices for overlapping symbols across platforms
    2. Identify spreads exceeding threshold (default 0.5%)
    3. Account for estimated fees to calculate net profit
    4. Return actionable opportunities sorted by profit
    """

    # Estimated taker fees per platform
    PLATFORM_FEES = {
        "drift": 0.0001,  # 0.01% (Taker)
        "aster": 0.001,  # 0.1%
        "symphony": 0.001,  # 0.1%
    }

    # Min spread required (after fees) to consider opportunity
    MIN_PROFIT_THRESHOLD = 0.003  # 0.3%

    def __init__(
        self,
        aster_client=None,
        hl_client=None,
        drift_client=None,
    ):
        self.aster_client = aster_client
        self.hl_client = hl_client
        self.drift_client = drift_client

        # Overlapping symbols that exist on multiple platforms
        # Format: (unified_symbol, {platform: platform_symbol})
        self.cross_listed_symbols = {
            "BTC": {
                "aster": "BTCUSDC",
                "hyperliquid": "BTC-USDC",
            },
            "ETH": {
                "aster": "ETHUSDC",
                "hyperliquid": "ETH-USDC",
                "symphony": "ETH-USDC",
            },
            "SOL": {
                "aster": "SOLUSDC",
                "hyperliquid": "SOL-USDC",
                "drift": "SOL-USD",
            },
        }

    async def scan(self) -> List[ArbitrageOpportunity]:
        """
        Scan all cross-listed symbols for arbitrage opportunities.

        Returns:
            List of opportunities sorted by estimated profit (descending)
        """
        import time

        opportunities = []

        for unified_symbol, platform_symbols in self.cross_listed_symbols.items():
            try:
                # Fetch prices from all platforms
                prices = await self._fetch_prices(platform_symbols)

                if len(prices) < 2:
                    continue  # Need at least 2 prices to compare

                # Find best buy and sell prices
                buy_platform, buy_price = min(prices.items(), key=lambda x: x[1])
                sell_platform, sell_price = max(prices.items(), key=lambda x: x[1])

                if buy_platform == sell_platform:
                    continue  # Same platform, no arb

                # Calculate spread
                spread_pct = (sell_price - buy_price) / buy_price

                # Calculate net profit after fees
                total_fees = self.PLATFORM_FEES.get(buy_platform, 0.001) + self.PLATFORM_FEES.get(
                    sell_platform, 0.001
                )
                estimated_profit_pct = spread_pct - total_fees

                if estimated_profit_pct >= self.MIN_PROFIT_THRESHOLD:
                    opp = ArbitrageOpportunity(
                        symbol=unified_symbol,
                        buy_platform=buy_platform,
                        sell_platform=sell_platform,
                        buy_price=buy_price,
                        sell_price=sell_price,
                        spread_pct=spread_pct,
                        estimated_profit_pct=estimated_profit_pct,
                        timestamp=time.time(),
                    )
                    opportunities.append(opp)
                    logger.info(
                        f"💰 [ARB] {unified_symbol}: Buy {buy_platform} @ {buy_price:.2f}, "
                        f"Sell {sell_platform} @ {sell_price:.2f} = {estimated_profit_pct:.2%} profit"
                    )

            except Exception as e:
                logger.debug(f"Arbitrage scan error for {unified_symbol}: {e}")

        # Sort by profit descending
        opportunities.sort(key=lambda x: x.estimated_profit_pct, reverse=True)
        return opportunities

    async def _fetch_prices(self, platform_symbols: Dict[str, str]) -> Dict[str, float]:
        """Fetch prices from all available platforms for a symbol."""
        prices = {}

        tasks = []
        platforms = []

        for platform, symbol in platform_symbols.items():
            if platform == "aster" and self.aster_client:
                tasks.append(self._get_aster_price(symbol))
                platforms.append("aster")
            elif platform == "drift" and self.drift_client:
                tasks.append(self._get_drift_price(symbol))
                platforms.append("drift")

        if not tasks:
            return prices

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for platform, price in zip(platforms, results):
            if isinstance(price, (int, float)) and price > 0:
                prices[platform] = price

        return prices

    async def _get_aster_price(self, symbol: str) -> float:
        """Get price from Aster."""
        try:
            ticker = await self.aster_client.get_market_price(symbol)
            return float(ticker) if ticker else 0.0
        except Exception:
            return 0.0

    async def _get_hl_price(self, symbol: str) -> float:
        """Get price from Hyperliquid."""
        try:
            # Extract base from symbol (e.g., "BTC-USDC" -> "BTC")
            base = symbol.split("-")[0]
            ticker = await self.hl_client.get_ticker(base)
            return float(ticker.get("markPx", 0)) if ticker else 0.0
        except Exception:
            return 0.0

    async def _get_drift_price(self, symbol: str) -> float:
        """Get price from Drift."""
        try:
            price = await self.drift_client.get_token_price(symbol)
            return float(price) if price else 0.0
        except Exception:
            return 0.0


# Global instance
_arb_scanner: Optional[ArbitrageScanner] = None


def get_arbitrage_scanner() -> Optional[ArbitrageScanner]:
    """Get global arbitrage scanner instance."""
    global _arb_scanner
    return _arb_scanner


def init_arbitrage_scanner(
    aster_client=None, hl_client=None, drift_client=None
) -> ArbitrageScanner:
    """Initialize the global arbitrage scanner."""
    global _arb_scanner
    _arb_scanner = ArbitrageScanner(
        aster_client=aster_client,
        hl_client=hl_client,
        drift_client=drift_client,
    )
    logger.info("✅ ArbitrageScanner initialized")
    return _arb_scanner
