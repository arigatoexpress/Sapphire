"""
Market Scanner Service - Signal Generator

Scans markets across all platforms for trading opportunities and
publishes signals for bots to execute. This is the brain of the system.
"""

import asyncio
import logging
import os
import random
import signal
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add shared library to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "shared"))

from pubsub import get_pubsub_client, publish
from utils import ServiceConfig, setup_logging, utc_now

from models import SignalType, TradeSide, TradeSignal

logger = logging.getLogger(__name__)

SERVICE_NAME = "market-scanner"


class MarketScanner:
    """
    Market Scanner - Generates trading signals for all platforms.

    Strategies:
    - Cross-platform arbitrage detection
    - Momentum & trend following
    - Mean reversion
    - Funding rate arbitrage
    """

    def __init__(self):
        self.running = False
        self._shutdown_event = asyncio.Event()

        # Platform-specific price feeds
        self.price_feeds: Dict[str, Dict[str, float]] = {}

        # Signal generation config
        self.min_confidence = float(os.getenv("MIN_CONFIDENCE", "0.65"))
        self.scan_interval_ms = int(os.getenv("SCAN_INTERVAL_MS", "5000"))

        # Watchlist
        self.symbols = [
            "ETH-USDC",
            "BTC-USDC",
            "SOL-USDC",
            "JUP-USDC",
            "BONK-USDC",
            "DEGEN-USDC",
            "MON-USDC",
            "CHOG-USDC",
        ]

        # Funding rates (from HL, Drift)
        self.funding_rates: Dict[str, Dict[str, float]] = {}

        # Performance tracking
        self.signals_generated = 0
        self.signals_by_type: Dict[str, int] = {}

    async def initialize(self):
        """Initialize the scanner."""
        logger.info(f"🚀 Initializing {SERVICE_NAME}...")

        try:
            pubsub = get_pubsub_client()
            await pubsub.initialize()
            logger.info(f"✅ {SERVICE_NAME} initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            return False

    async def start(self):
        """Start the scanner loops."""
        if not await self.initialize():
            return

        self.running = True
        logger.info(f"🎯 {SERVICE_NAME} is now running")

        try:
            await asyncio.gather(
                self._momentum_scanner_loop(),
                self._arbitrage_scanner_loop(),
                self._funding_scanner_loop(),
            )
        except asyncio.CancelledError:
            pass
        finally:
            self.running = False

    async def stop(self):
        """Stop the scanner."""
        logger.info(f"🛑 Stopping {SERVICE_NAME}...")
        self.running = False
        self._shutdown_event.set()

    async def _momentum_scanner_loop(self):
        """Scan for momentum-based opportunities."""
        while self.running:
            try:
                for symbol in self.symbols:
                    signal = await self._analyze_momentum(symbol)
                    if signal:
                        await self._publish_signal(signal)

            except Exception as e:
                logger.error(f"Momentum scanner error: {e}")

            await asyncio.sleep(self.scan_interval_ms / 1000)

    async def _arbitrage_scanner_loop(self):
        """Scan for cross-platform arbitrage opportunities."""
        while self.running:
            try:
                opportunities = await self._detect_arbitrage()
                for opp in opportunities:
                    await self._publish_signal(opp)

            except Exception as e:
                logger.error(f"Arbitrage scanner error: {e}")

            await asyncio.sleep(10)  # Check every 10 seconds

    async def _funding_scanner_loop(self):
        """Scan for funding rate arbitrage."""
        while self.running:
            try:
                signals = await self._analyze_funding_rates()
                for signal in signals:
                    await self._publish_signal(signal)

            except Exception as e:
                logger.error(f"Funding scanner error: {e}")

            await asyncio.sleep(60)  # Check every minute

    async def _analyze_momentum(self, symbol: str) -> Optional[TradeSignal]:
        """
        Analyze momentum for a symbol.
        Returns a signal if a strong opportunity is detected.
        """
        try:
            # Placeholder - in production, fetch real price data
            # This would use TA indicators: RSI, MACD, Bollinger Bands

            # Simulated momentum detection
            momentum_score = random.uniform(-1, 1)  # Replace with real analysis

            if abs(momentum_score) > 0.7:  # Strong momentum
                confidence = min(abs(momentum_score), 0.95)

                if confidence >= self.min_confidence:
                    side = TradeSide.LONG if momentum_score > 0 else TradeSide.SHORT

                    # Determine target platforms based on symbol
                    platforms = self._get_platforms_for_symbol(symbol)

                    return TradeSignal(
                        signal_id=f"momentum-{symbol}-{datetime.now().timestamp()}",
                        symbol=symbol,
                        side=side,
                        signal_type=SignalType.ENTRY,
                        confidence=confidence,
                        source="market-scanner:momentum",
                        target_platforms=platforms,
                        metadata={
                            "strategy": "momentum",
                            "momentum_score": momentum_score,
                        },
                    )

        except Exception as e:
            logger.error(f"Momentum analysis error for {symbol}: {e}")

        return None

    async def _detect_arbitrage(self) -> List[TradeSignal]:
        """
        Detect cross-platform arbitrage opportunities.
        """
        signals = []

        try:
            # Example: Check for price differences between platforms
            # In production, this would fetch real prices from each platform

            for symbol in ["ETH-USDC", "BTC-USDC", "SOL-USDC"]:
                # Simulated price differences
                hl_price = 3000 + random.uniform(-50, 50)
                drift_price = 3000 + random.uniform(-50, 50)

                spread_pct = abs(hl_price - drift_price) / min(hl_price, drift_price)

                # If spread > 0.2% (profitable after fees)
                if spread_pct > 0.002:
                    # Buy on cheaper, sell on more expensive
                    if hl_price < drift_price:
                        buy_platform = "hyperliquid"
                        sell_platform = "drift"
                    else:
                        buy_platform = "drift"
                        sell_platform = "hyperliquid"

                    # Create paired signals
                    signals.append(
                        TradeSignal(
                            signal_id=f"arb-{symbol}-buy-{datetime.now().timestamp()}",
                            symbol=symbol,
                            side=TradeSide.LONG,
                            signal_type=SignalType.ENTRY,
                            confidence=0.85,
                            source="market-scanner:arbitrage",
                            target_platforms=[buy_platform],
                            metadata={
                                "strategy": "arbitrage",
                                "spread_pct": spread_pct,
                                "paired_platform": sell_platform,
                            },
                        )
                    )

        except Exception as e:
            logger.error(f"Arbitrage detection error: {e}")

        return signals

    async def _analyze_funding_rates(self) -> List[TradeSignal]:
        """
        Analyze funding rates for cash-and-carry opportunities.
        """
        signals = []

        try:
            # In production, fetch real funding rates from HL and Drift
            # If funding is very positive -> short perps, long spot
            # If funding is very negative -> long perps, short spot (if available)

            for symbol in ["ETH-USDC", "BTC-USDC"]:
                # Simulated funding rate (-0.1% to 0.1% per 8h)
                funding_rate = random.uniform(-0.001, 0.001)

                # Very high positive funding = good for shorting
                if funding_rate > 0.0005:
                    signals.append(
                        TradeSignal(
                            signal_id=f"funding-{symbol}-{datetime.now().timestamp()}",
                            symbol=symbol,
                            side=TradeSide.SHORT,
                            signal_type=SignalType.ENTRY,
                            confidence=0.70,
                            source="market-scanner:funding",
                            target_platforms=["hyperliquid", "drift"],
                            metadata={
                                "strategy": "funding_arbitrage",
                                "funding_rate": funding_rate,
                                "expected_return_8h": funding_rate * 100,
                            },
                        )
                    )

        except Exception as e:
            logger.error(f"Funding analysis error: {e}")

        return signals

    def _get_platforms_for_symbol(self, symbol: str) -> List[str]:
        """Determine which platforms support a symbol."""
        # Map symbols to supported platforms
        symbol_platforms = {
            # Solana ecosystem -> Drift
            "SOL-USDC": ["drift", "hyperliquid"],
            "JUP-USDC": ["drift"],
            "PYTH-USDC": ["drift"],
            "BONK-USDC": ["drift", "hyperliquid"],
            # Monad/Base -> Symphony
            "MON-USDC": ["symphony"],
            "CHOG-USDC": ["symphony"],
            "DEGEN-USDC": ["symphony"],
            # Major pairs -> All platforms
            "ETH-USDC": ["symphony", "drift", "hyperliquid", "aster"],
            "BTC-USDC": ["symphony", "drift", "hyperliquid", "aster"],
        }

        return symbol_platforms.get(symbol, ["symphony", "aster"])

    async def _publish_signal(self, signal: TradeSignal):
        """Publish a trading signal to Pub/Sub."""
        try:
            await publish("trading-signals", signal)

            self.signals_generated += 1
            strategy = signal.metadata.get("strategy", "unknown")
            self.signals_by_type[strategy] = self.signals_by_type.get(strategy, 0) + 1

            logger.info(
                f"📤 Published signal: {signal.side.value} {signal.symbol} "
                f"(conf={signal.confidence:.2f}, platforms={signal.target_platforms})"
            )

        except Exception as e:
            logger.error(f"Failed to publish signal: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get scanner status."""
        return {
            "service": SERVICE_NAME,
            "running": self.running,
            "signals_generated": self.signals_generated,
            "signals_by_type": self.signals_by_type,
            "symbols_watched": len(self.symbols),
            "min_confidence": self.min_confidence,
        }


async def main():
    """Main entry point with health server for Cloud Run."""
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))

    logger.info("=" * 50)
    logger.info(f"🔍 MARKET SCANNER SERVICE")
    logger.info(f"📅 {datetime.now().isoformat()}")
    logger.info("=" * 50)

    scanner = MarketScanner()

    def handle_shutdown(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(scanner.stop())

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Run with health server for Cloud Run compatibility
    from utils.health_server import run_with_health_server

    await run_with_health_server(SERVICE_NAME, scanner.start, scanner.get_status)


if __name__ == "__main__":
    asyncio.run(main())
