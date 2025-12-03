"""Simplified Enhanced Telegram Service for Hyperliquid Trader."""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder

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
    notional: float
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None
    pnl: Optional[float] = None
    confidence: Optional[float] = None
    ai_analysis: Optional[str] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class EnhancedTelegramService:
    """Simplified Telegram notification service for Hyperliquid."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id
        self.application = ApplicationBuilder().token(bot_token).build()
        self.daily_stats = {"trades": 0, "volume": 0.0, "pnl": 0.0}
        self.last_summary_time = time.time()

    async def start(self):
        """Start the bot (notification only mode)."""
        logger.info("Starting Hyperliquid Telegram Bot...")
        try:
            await self.application.initialize()
            await self.application.start()
            await self.send_startup_notification()
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")

    async def send_startup_notification(self):
        """Send startup notification (Silent/Low Priority)."""
        message = (
            "🚀 *Hyperliquid Trader Online*\n"
            "📊 Daily Summary Mode Active"
        )
        # Send silently
        await self.send_message(message, priority=NotificationPriority.LOW)

    async def send_trade_notification(
        self,
        trade: Optional[TradeNotification] = None,
        priority: NotificationPriority = NotificationPriority.LOW,
        **kwargs,
    ):
        """Record trade for summary, suppress immediate notification."""
        if trade is None and kwargs:
            trade = TradeNotification(
                symbol=kwargs.get("symbol", "N/A"),
                side=kwargs.get("side", "HOLD"),
                price=kwargs.get("price", 0.0),
                quantity=kwargs.get("quantity", 0.0),
                notional=kwargs.get("notional", 0.0),
                pnl=kwargs.get("pnl"),
            )

        if trade is None:
            return

        # Update stats
        self.daily_stats["trades"] += 1
        self.daily_stats["volume"] += trade.notional
        if trade.pnl:
            self.daily_stats["pnl"] += trade.pnl

        # ONLY send immediate notification for Profit Sweeps or High Priority
        if priority in [NotificationPriority.HIGH, NotificationPriority.CRITICAL]:
             action_emoji = "🔵" if trade.side.upper() == "BUY" else "🔴"
             symbol_md = trade.symbol.replace("-", "\\-").replace(".", "\\.")
             
             message = (
                f"{action_emoji} **HYPERLIQUID {trade.side.upper()} {symbol_md}**\n"
                f"💰 Price: `${trade.price:.4f}`\n"
                f"💵 Value: `${trade.notional:.2f}`"
             )
             if trade.pnl:
                 message += f"\n✅ P&L: `${trade.pnl:.2f}`"
                 
             await self.send_message(message, priority=priority)

    async def send_daily_summary(self):
        """Send a data-rich daily summary."""
        trades_count = self.daily_stats["trades"]
        volume = self.daily_stats["volume"]
        pnl = self.daily_stats["pnl"]
        
        if trades_count == 0:
            return

        message = (
            "📊 **Daily Trading Summary**\n\n"
            f"🔢 Total Trades: `{trades_count}`\n"
            f"💸 Total Volume: `${volume:,.2f}`\n"
            f"💰 Estimated P&L: `${pnl:,.2f}`\n\n"
            "🤖 *AI Performance: Optimized*"
        )
        
        await self.send_message(message, priority=NotificationPriority.HIGH)
        
        # Reset stats
        self.daily_stats = {"trades": 0, "volume": 0.0, "pnl": 0.0}

    async def send_message(
        self,
        text: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        reply_markup: InlineKeyboardMarkup = None,
        parse_mode: str = ParseMode.MARKDOWN,
    ) -> None:
        """Send message with priority handling."""
        try:
            priority_prefix = {
                NotificationPriority.LOW: "📝",
                NotificationPriority.MEDIUM: "📢",
                NotificationPriority.HIGH: "🚨",
                NotificationPriority.CRITICAL: "🚨🚨",
            }.get(priority, "📢")

            full_message = f"{priority_prefix} {text}"

            await self.bot.send_message(
                chat_id=self.chat_id,
                text=full_message,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
