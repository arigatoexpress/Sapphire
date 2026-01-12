import asyncio
import logging
import os
import signal
import sys

import uvloop
from src.ai.gemini_guard import GeminiGuard
from src.execution.dispatcher import dispatcher
from src.feeds.market_data import MarketDataAggregator
from src.strategy.engine import AlphaStrategyEngine

# Add shared library to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from error_classifier import ErrorCategory, ErrorSeverity, classify_error
from health import start_health_server
from smart_notifications import notification_manager

# Install uvloop as the default event loop policy
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# Configure high-performance logging
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")


class AlphaEngine:
    def __init__(self):
        self.running = False
        self.market_data = MarketDataAggregator()
        self.strategy = AlphaStrategyEngine(self.market_data)

        # Telegram Bot for Notifications & Commands
        from telegram_bot import TelegramPlatformBot

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        logger.info(f"Alpha Hub: TELEGRAM_BOT_TOKEN is {'set' if token else 'NOT SET'}")
        self.telegram = TelegramPlatformBot(
            bot_token=token, chat_id=chat_id, command_callback=self._handle_telegram_command
        )
        # Initialize Gemini Guard
        self.ai = GeminiGuard(telegram_bot=self.telegram)

    async def _handle_telegram_command(
        self, platform: str, symbol: str, action: str, quantity: float
    ):
        """Callback for Telegram @mentions to trigger manual overrides."""
        logger.warning(f"🚨 TELEGRAM OVERRIDE: {platform} {action} {quantity} {symbol}")

        # intercept AI commands
        if platform.lower() == "alpha" and action.lower() in ("recap", "analyze", "report"):
            await self.telegram.send_message("🧠 **Processing AI Request...**", priority="medium")
            analysis_type = "full" if action.lower() == "report" else "recap"
            await self.ai.force_analyze(analysis_type)
            return

        # Dispatch command via ExecutionDispatcher
        await dispatcher.send_command(
            platform,
            {
                "action": action,
                "symbol": symbol,
                "quantity": quantity,
                "source": "telegram_override",
            },
        )

    async def start(self):
        logger.info("🚀 Sapphire Alpha Engine Starting (uvloop enabled)")
        self.running = True

        # Start Health Server (Cloud Run)
        await start_health_server()

        # 1. Start Telegram FIRST for immediate status
        logger.info("📡 Initializing Telegram Notification Task...")
        asyncio.create_task(
            self.telegram.send_message("💎 Sapphire Alpha Hub Online & Listening", priority="high")
        )
        asyncio.create_task(self.telegram.start_listener())

        # 2. Start Pub/Sub Listener for Trade Results
        asyncio.create_task(self._listen_for_trades())

        # 3. Start Gemini Guard
        asyncio.create_task(self.ai.start())

        # 4. Start Feeds, Strategy, Dispatcher
        await dispatcher.start()
        await self.market_data.start()
        await self.strategy.start()

        # Keep-alive loop
        while self.running:
            await asyncio.sleep(1)

    async def _listen_for_trades(self):
        """Listen for trade execution results from all bots."""
        from pubsub.client import subscribe

        logger.info("👂 Initializing Pub/Sub 'trade-executed' listener...")

        async def handle_trade(message_data: dict):
            try:
                # Log to AI for Recaps
                self.ai.log_trade(message_data)

                # Format notification
                platform = message_data.get("platform", "Unknown")
                symbol = message_data.get("symbol", "N/A")
                success = message_data.get("success", False)
                side = message_data.get("side", "N/A")
                qty = message_data.get("filled_quantity", 0)

                if success:
                    msg = f"✅ TRADE EXECUTED: {platform} | {side} {qty} {symbol}"
                    # Use LOW priority to batch execution updates
                    await self.telegram.send_message(msg, priority="low")
                else:
                    err = message_data.get("error_message", "Unknown")

                    # Classify the error
                    category, severity = classify_error(err)

                    # Check if we should notify
                    should_notify = notification_manager.should_notify(err, category, severity)

                    if should_notify:
                        msg = f"❌ TRADE FAILED: {platform} | {side} {symbol} | Error: {err}"

                        # Use appropriate priority based on severity
                        priority = "high" if severity >= ErrorSeverity.ERROR else "medium"
                        await self.telegram.send_message(msg, priority=priority)
                        logger.warning(msg)
                    else:
                        # Log but don't spam Telegram
                        logger.info(
                            f"⚠️ Expected/deduplicated failure: {platform} | {side} {symbol} | {err}"
                        )
            except Exception as e:
                logger.error(f"Error in trade result handler: {e}")

        await subscribe("trade-executed", handle_trade)

    async def stop(self):
        logger.info("🛑 Stopping Alpha Engine...")
        self.running = False
        await self.market_data.stop()
        await self.strategy.stop()
        await dispatcher.stop()
        await self.ai.stop()  # Stop AI loop


async def main():
    engine = AlphaEngine()

    def handle_sig(sig, frame):
        asyncio.create_task(engine.stop())

    signal.signal(signal.SIGTERM, handle_sig)
    signal.signal(signal.SIGINT, handle_sig)

    await engine.start()


if __name__ == "__main__":
    asyncio.run(main())
