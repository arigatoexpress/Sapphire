"""Hyperliquid trading bot — subscribes to Sapphire signals and executes on Hyperliquid.

Signal flow:
    services/alpha → pubsub topic 'trading-signals' → this bot → Hyperliquid API

Supported pairs (Hyperliquid has 150+ assets):
    BTC, ETH, SOL, HYPE, ZEC and any asset in the Hyperliquid universe
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

# Load .env from service directory
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)
except ImportError:
    pass

# Add shared lib to path (monorepo structure)
sys.path.insert(0, str(Path(__file__).parents[3] / "lib" / "core" / "src"))

from sapphire_core.logging_config import setup_logging

from .client import HyperliquidClient

logger = logging.getLogger(__name__)

PRIVATE_KEY = os.getenv("HYPERLIQUID_PRIVATE_KEY", "").strip()
TESTNET = os.getenv("HYPERLIQUID_TESTNET", "false").lower() == "true"
DEFAULT_SIZE_USD = float(os.getenv("HYPERLIQUID_SIZE_USD", "100"))


class HyperliquidBot:
    """Sapphire signal executor for Hyperliquid."""

    def __init__(self) -> None:
        if not PRIVATE_KEY:
            raise ValueError("HYPERLIQUID_PRIVATE_KEY not set")
        self._client = HyperliquidClient(PRIVATE_KEY, testnet=TESTNET)
        self.running = False

    async def start(self) -> None:
        self.running = True
        logger.info("HyperliquidBot starting (testnet=%s)", TESTNET)
        async with self._client:
            state = await self._client.get_user_state()
            margin = state.get("marginSummary", {})
            logger.info(
                "Account: address=%s equity=%s",
                self._client.address,
                margin.get("accountValue", "?"),
            )
            await self._run_loop()

    async def _run_loop(self) -> None:
        """Main loop — polls for signals from control-plane or pubsub."""
        # TODO: subscribe to sapphire pubsub 'trading-signals' topic
        # and route signals to self._execute()
        while self.running:
            await asyncio.sleep(5)

    async def execute(self, signal: dict) -> dict:
        """Execute a trading signal.

        Args:
            signal: {symbol, action: 'buy'|'sell'|'close', size_usd, confidence}

        Returns:
            Hyperliquid order response.
        """
        symbol = signal.get("symbol", "BTC").upper()
        action = signal.get("action", "").lower()
        size_usd = float(signal.get("size_usd", DEFAULT_SIZE_USD))

        if action == "close":
            logger.info("Closing position: %s", symbol)
            return await self._client.close_position(symbol)

        mids = await self._client.get_all_mids()
        price = float(mids.get(symbol, 0))
        if not price:
            return {"status": "error", "error": f"No price for {symbol}"}

        size = size_usd / price
        is_buy = action == "buy"
        logger.info("Placing %s %s size=%.6f @ ~%.2f", action, symbol, size, price)
        return await self._client.market_order(symbol, is_buy, size)

    def stop(self) -> None:
        self.running = False


async def main() -> None:
    setup_logging()
    bot = HyperliquidBot()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, bot.stop)

    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
