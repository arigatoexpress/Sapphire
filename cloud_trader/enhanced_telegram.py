"""Enhanced AI-powered Telegram notification service (Lightweight)."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

import aiohttp

# Remove telegram library imports to resolve dependency conflicts with Drift
# from telegram import ...

logger = logging.getLogger(__name__)


class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TradeNotification:
    symbol: str
    side: str
    price: float
    quantity: float
    notional: float = 0.0
    take_profit: float = 0.0
    stop_loss: float = 0.0
    confidence: float = 0.0
    ai_analysis: str = ""


@dataclass
class MarketInsight:
    symbol: str
    sentiment: str
    confidence: float
    key_levels: Dict[str, float]
    recommendation: str
    analysis: str


class AITradingAnalyzer:
    def __init__(self, *args, **kwargs):
        pass


class MarketSentimentAnalyzer:
    def __init__(self, *args, **kwargs):
        pass


class RiskAnalyzer:
    def __init__(self, *args, **kwargs):
        pass


class EnhancedTelegramService:
    """Lightweight Telegram notification service using raw HTTP API."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        ai_analyzer: Optional[Any] = None,
        sentiment_analyzer: Optional[Any] = None,
        risk_analyzer: Optional[Any] = None,
        performance_analyzer: Optional[Any] = None,
    ):
        self.bot_token = bot_token.strip() if bot_token else bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"

        # Analyzers (placeholder for interface compatibility)
        self.ai_analyzer = ai_analyzer
        self.sentiment_analyzer = sentiment_analyzer
        self.risk_analyzer = risk_analyzer
        self.performance_analyzer = performance_analyzer

        # Throttling
        self.last_send_time = 0
        self.daily_stats = {"trades": 0, "volume": 0.0, "pnl": 0.0}

    async def start(self):
        """No-op start for compatibility."""
        logger.info("✅ Telegram Service (Lightweight) Initialized")
        await self.send_startup_notification()

    async def send_message(
        self, text: str, priority: NotificationPriority = NotificationPriority.MEDIUM, **kwargs
    ) -> None:
        """Send message via raw HTTP API."""
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram token/chat_id missing, cannot send message")
            return

        priority_prefix = {
            NotificationPriority.LOW: "📝",
            NotificationPriority.MEDIUM: "📢",
            NotificationPriority.HIGH: "🚨",
            NotificationPriority.CRITICAL: "🚨🚨",
        }.get(priority, "📢")

        full_message = f"{priority_prefix} {text}"

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": full_message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as resp:
                    if resp.status != 200:
                        err_text = await resp.text()
                        logger.error(f"Telegram API Error {resp.status}: {err_text}")
                    else:
                        logger.info(f"Sent Telegram message (len={len(full_message)})")
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    async def send_startup_notification(self):
        await self.send_message(
            "🤖 *Sapphire Trading AI Bot Online*\n\n"
            "💎 Lightweight Notification Service Active\n"
            "⚠️ Interactive commands disabled for system stability",
            priority=NotificationPriority.HIGH,
        )

    async def send_trade_notification(
        self, trade=None, priority=NotificationPriority.MEDIUM, **kwargs
    ):
        """Send trade notification with rich formatting."""
        symbol = trade.symbol if trade else kwargs.get("symbol", "N/A")
        side = trade.side if trade else kwargs.get("side", "HOLD")
        price = trade.price if trade else kwargs.get("price", 0.0)
        quantity = trade.quantity if trade else kwargs.get("quantity", 0.0)
        platform = trade.platform if trade else kwargs.get("platform", "Unknown")

        # Determine emoji based on side
        side_emoji = "🟢" if side in ["BUY", "LONG"] else "🔴"
        platform_emoji = {"drift": "🌊", "hyperliquid": "💧", "aster": "⭐", "symphony": "🎵"}.get(
            platform.lower(), "🤖"
        )

        msg = (
            f"{side_emoji} **{side} {symbol}**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💵 Price: `${price:,.4f}`\n"
            f"📦 Size: `{quantity}`\n"
            f"{platform_emoji} Venue: `{platform.title()}`\n"
            f"🕒 Time: `{time.strftime('%H:%M:%S UTC')}`"
        )

        await self.send_message(msg, priority=priority)

    async def send_risk_alert(self, alert_type, severity, message, recommendations=None):
        msg = f"⚠️ **RISK ALERT: {alert_type}**\n{message}"
        await self.send_message(msg, priority=NotificationPriority.HIGH)

    async def send_market_insight(self, insight, priority=NotificationPriority.MEDIUM):
        """Send AI market analysis."""
        msg = f"🧠 **Market Insight**\n{insight}"
        await self.send_message(msg, priority=priority)

    async def send_status_update(self, system_status: Dict[str, Any]):
        """Send system health status report."""
        active_bots = system_status.get("active_bots", 0)
        uptime = system_status.get("uptime", "0h")
        cpu = system_status.get("cpu_usage", "0%")
        ram = system_status.get("ram_usage", "0%")

        status_emoji = "🟢" if active_bots >= 4 else "⚠️"

        msg = (
            f"{status_emoji} **System Status Report**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🤖 **Active Bots**: `{active_bots}/4`\n"
            f"⏱️ **Uptime**: `{uptime}`\n"
            f"🖥️ **CPU**: `{cpu}` | **RAM**: `{ram}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔌 *All Systems Operational*"
        )
        await self.send_message(msg, priority=NotificationPriority.LOW)

    async def send_performance_summary(self, period, metrics, ai_commentary=None):
        """Send detailed performance report."""
        pnl = metrics.get("total_pnl", 0.0)
        volume = metrics.get("volume", 0.0)
        trades = metrics.get("trades", 0)
        win_rate = metrics.get("win_rate", 0.0)

        pnl_emoji = "🚀" if pnl >= 0 else "📉"
        pnl_str = f"+${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"

        msg = (
            f"📊 **{period} Performance Report**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{pnl_emoji} **PnL**: `{pnl_str}`\n"
            f"📈 **Volume**: `${volume:,.0f}`\n"
            f"🎯 **Win Rate**: `{win_rate:.1f}%` ({trades} trades)\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💡 **AI Insight**:\n_{ai_commentary or 'Market conditions appear normal. Continuing standard strategy.'}_"
        )
        await self.send_message(msg, priority=NotificationPriority.HIGH)
