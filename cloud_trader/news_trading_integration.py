"""
Integration layer: Connects Telegram news monitoring to autonomous trading agents
"""

import logging
import asyncio
from typing import List, Optional, Dict
import os

from cloud_trader.telegram_news_monitor import TelegramNewsMonitor, NewsMessage, create_news_monitor
from cloud_trader.news_intelligence_agent import NewsIntelligenceAgent, NewsInsight

logger = logging.getLogger(__name__)


class NewsTradingIntegration:
    """
    Connects Telegram news monitoring with autonomous trading agents

    Flow:
    1. TelegramNewsMonitor receives messages from alpha/news groups
    2. NewsIntelligenceAgent analyzes with AI to extract trading insights
    3. Insights are forwarded to trading orchestrator for action
    """

    def __init__(
        self,
        monitored_chat_ids: Optional[List[int]] = None,
        trading_callback: Optional[callable] = None,
    ):
        """
        Initialize news trading integration

        Args:
            monitored_chat_ids: List of Telegram chat IDs to monitor
            trading_callback: Callback function that receives NewsInsight objects
                             for forwarding to trading agents
        """
        # Initialize components
        self.news_monitor = create_news_monitor(monitored_chat_ids)
        self.intelligence_agent = NewsIntelligenceAgent()

        # Connect news monitor -> intelligence agent
        self.news_monitor.add_handler(self._on_news_message)

        # Store trading callback
        self.trading_callback = trading_callback
        if trading_callback:
            self.intelligence_agent.add_insight_callback(trading_callback)

        self.running = False

        logger.info("🔗 NewsTradingIntegration initialized")

    async def _on_news_message(self, news: NewsMessage) -> None:
        """
        Internal handler: receives raw news and sends to intelligence agent

        Args:
            news: Raw NewsMessage from Telegram
        """
        logger.debug(f"📥 Received news from {news.chat_name}: {news.text[:100]}...")

        # Process through AI intelligence
        await self.intelligence_agent.process_news(news)

    async def start(self) -> None:
        """Start news monitoring and intelligence processing"""
        if self.running:
            logger.warning("⚠️ NewsTradingIntegration already running")
            return

        logger.info("🚀 Starting NewsTradingIntegration...")

        # Initialize Gemini model
        self.intelligence_agent.initialize_model()

        # Start Telegram monitor
        await self.news_monitor.start()

        self.running = True
        logger.info("✅ NewsTradingIntegration started and monitoring news")

    async def stop(self) -> None:
        """Stop news monitoring"""
        logger.info("🛑 Stopping NewsTradingIntegration...")
        self.running = False

        await self.news_monitor.stop()

        logger.info("✅ NewsTradingIntegration stopped")

    def add_monitored_chat(self, chat_id: int) -> None:
        """Add a Telegram chat to monitoring"""
        self.news_monitor.add_monitored_chat(chat_id)

    def remove_monitored_chat(self, chat_id: int) -> None:
        """Remove a Telegram chat from monitoring"""
        self.news_monitor.remove_monitored_chat(chat_id)

    def add_trading_callback(self, callback: callable) -> None:
        """
        Add additional callback for trading insights

        Args:
            callback: Function that receives NewsInsight objects
        """
        self.intelligence_agent.add_insight_callback(callback)

    async def get_monitored_chats(self) -> List[dict]:
        """Get information about monitored chats"""
        return await self.news_monitor.get_monitored_chats_info()

    async def list_available_chats(self, limit: int = 50) -> List[dict]:
        """List available chats for configuration"""
        return await self.news_monitor.list_available_chats(limit)

    def get_stats(self) -> Dict:
        """Get statistics about news processing"""
        return {
            "running": self.running,
            "intelligence": self.intelligence_agent.get_stats(),
            "monitored_chats": len(self.news_monitor.monitored_chats) if self.news_monitor.monitored_chats else "ALL",
        }


# Helper function to create from environment
def create_news_trading_integration(
    trading_callback: Optional[callable] = None,
) -> NewsTradingIntegration:
    """
    Factory function to create NewsTradingIntegration from environment variables

    Environment variables:
    - NEWS_MONITOR_CHAT_IDS: Comma-separated list of Telegram chat IDs

    Args:
        trading_callback: Callback for trading insights

    Returns:
        Configured NewsTradingIntegration instance
    """
    # Parse chat IDs from environment
    chat_ids_str = os.getenv("NEWS_MONITOR_CHAT_IDS", "")
    monitored_chats = None

    if chat_ids_str:
        try:
            monitored_chats = [int(id.strip()) for id in chat_ids_str.split(",") if id.strip()]
            logger.info(f"📡 Configured to monitor {len(monitored_chats)} chats from environment")
        except ValueError as e:
            logger.error(f"❌ Invalid NEWS_MONITOR_CHAT_IDS format: {e}")

    return NewsTradingIntegration(
        monitored_chat_ids=monitored_chats,
        trading_callback=trading_callback,
    )
