"""Enhanced AI-powered Telegram notification service with Interactive Commands."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import aiohttp

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
    """Enhanced Telegram notification service with interactive commands using raw HTTP API."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        ai_analyzer: Optional[Any] = None,
        sentiment_analyzer: Optional[Any] = None,
        risk_analyzer: Optional[Any] = None,
        performance_analyzer: Optional[Any] = None,
        command_callback: Optional[Callable[[str, str, str, float], Any]] = None,
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

        # Command listener
        self.command_callback = command_callback
        self.last_update_id = 0
        self.running = False
        self._listener_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start Telegram service with interactive command listener."""
        import os

        logger.info("✅ Telegram Service (Enhanced with Interactive Commands) Initialized")
        # Send startup notification in background (don't block initialization)
        asyncio.create_task(self.send_startup_notification())

        # Only start listener if explicitly enabled (prevents conflicts in multi-instance deployments)
        enable_listener = os.getenv("ENABLE_TELEGRAM_LISTENER", "false").lower() == "true"

        if not enable_listener:
            logger.info("ℹ️ Telegram command listener disabled via ENABLE_TELEGRAM_LISTENER=false (notification-only mode)")
            return

        # Start command listener if bot token is available
        if self.bot_token and self.chat_id:
            self.running = True
            self._listener_task = asyncio.create_task(self._command_listener())
            logger.info("📡 Telegram Command Listener Started")
        else:
            logger.warning("⚠️ Telegram command listener disabled (missing token or chat_id)")

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
            "🚨 🤖 *Sapphire Trading AI Bot Online* 💎\n\n"
            "✅ Enhanced Notification Service Active\n"
            "🎮 Interactive Commands: **ENABLED**\n\n"
            "*Available Commands:*\n"
            "`@aster status` - Check Aster positions\n"
            "`@jupiter status` - Check Jupiter routes\n"
            "`@aster status` - Check Aster HFT positions\n"
            "`@lighter status` - Check Lighter\n"
            "`@aster status` - Check Aster agents\n"
            "`@all status` - Check all platforms\n\n"
            "*Manual Trading:*\n"
            "`@[platform] buy [amount] [symbol]`\n"
            "`@[platform] sell [amount] [symbol]`\n"
            "`@[platform] close [amount] [symbol]`\n\n"
            "Example: `@aster buy 0.5 sol`",
            priority=NotificationPriority.HIGH,
        )

    async def send_trade_notification(
        self, trade=None, priority=NotificationPriority.MEDIUM, **kwargs
    ):
        """
        Send comprehensive trade notification with all execution details.

        Supports both entry and exit trades with full position information.
        """
        # Check if trade is an object with attributes or a dict
        if trade and hasattr(trade, 'symbol'):
            # Trade is an object with attributes
            symbol = getattr(trade, 'symbol', 'N/A')
            side = getattr(trade, 'side', 'HOLD')
            price = getattr(trade, 'price', 0.0)
            quantity = getattr(trade, 'quantity', 0.0)
            platform = getattr(trade, 'platform', 'Unknown')
            leverage = getattr(trade, 'leverage', 1)
            entry_price = getattr(trade, 'entry_price', 0.0)
            take_profit = getattr(trade, 'take_profit', 0.0)
            stop_loss = getattr(trade, 'stop_loss', 0.0)
            pnl = getattr(trade, 'pnl', 0.0)
            is_closing = getattr(trade, 'is_closing', False)
            thesis = getattr(trade, 'thesis', '')
        else:
            # Trade is None or a dict, use kwargs
            symbol = kwargs.get("symbol", "N/A")
            side = kwargs.get("side", "HOLD")
            price = kwargs.get("price", 0.0)
            quantity = kwargs.get("quantity", 0.0)
            platform = kwargs.get("platform", "Unknown")
            leverage = kwargs.get("leverage", 1)
            entry_price = kwargs.get("entry_price", 0.0)
            take_profit = kwargs.get("take_profit", kwargs.get("tp_price", 0.0))
            stop_loss = kwargs.get("stop_loss", kwargs.get("sl_price", 0.0))
            pnl = kwargs.get("pnl", 0.0)
            is_closing = kwargs.get("is_closing", False)
            thesis = kwargs.get("thesis", kwargs.get("status", ""))

        # Validate critical fields - log warning if 0
        if price == 0.0:
            logger.warning(f"⚠️ Trade notification for {symbol} received with price=0.0")
        if quantity == 0.0:
            logger.warning(f"⚠️ Trade notification for {symbol} received with quantity=0.0")

        # Calculate notional value
        notional = price * quantity if price > 0 and quantity > 0 else 0.0

        # Determine emoji based on side and trade type
        if is_closing:
            side_emoji = "🏁" if pnl >= 0 else "💔"
            action_text = f"CLOSED {side}"
        else:
            side_emoji = "🟢" if side in ["BUY", "LONG"] else "🔴"
            action_text = f"{side}"

        platform_emoji = {
            "aster": "🌊",
            "lighter": "💧",
            "aster": "⭐",
            "aster": "🎵",
            "lighter": "⚡",
            "jupiter": "🪐"
        }.get(str(platform).lower(), "🤖")

        # Build the message based on trade type
        if is_closing:
            # Exit/Close trade notification
            pnl_emoji = "💰" if pnl >= 0 else "📉"
            pnl_str = f"+${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"

            msg = (
                f"{side_emoji} **POSITION CLOSED: {symbol}**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 **Exit Price**: `${price:,.4f}`\n"
                f"📦 **Size**: `{quantity:,.4f}`\n"
                f"💰 **Value**: `${notional:,.2f}`\n"
            )

            if entry_price > 0:
                pct_change = ((price - entry_price) / entry_price) * 100
                pct_emoji = "📈" if pct_change >= 0 else "📉"
                msg += f"📍 **Entry**: `${entry_price:,.4f}`\n"
                msg += f"{pct_emoji} **Move**: `{pct_change:+.2f}%`\n"

            msg += (
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{pnl_emoji} **Realized PnL**: `{pnl_str}`\n"
                f"{platform_emoji} **Venue**: `{str(platform).title()}`\n"
                f"🕒 **Time**: `{time.strftime('%H:%M:%S UTC')}`"
            )
        else:
            # Entry trade notification
            # Get verified position data from kwargs
            account_equity = kwargs.get("account_equity")
            liquidation_price = kwargs.get("liquidation_price")
            position_size = kwargs.get("position_size")
            actual_usd_value = kwargs.get("actual_usd_value")
            notional_value = kwargs.get("notional_value")

            msg = (
                f"{side_emoji} **{action_text} {symbol}**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"💵 **Entry Price**: `${price:,.4f}`\n"
                f"📦 **Position Size**: `{quantity:,.4f}`\n"
            )

            # Show both notional and actual USD value if leverage is used
            if actual_usd_value and notional_value and leverage and leverage > 1:
                msg += f"💰 **Notional Value**: `${notional_value:,.2f}`\n"
                msg += f"💵 **USD at Risk**: `${actual_usd_value:,.2f}`\n"
                msg += f"⚙️ **Leverage**: `{leverage}x`\n"
            else:
                msg += f"💰 **Value**: `${notional:,.2f}`\n"
                if leverage and leverage > 1:
                    msg += f"⚙️ **Leverage**: `{leverage}x`\n"

            # Add account info if available
            if account_equity:
                msg += f"━━━━━━━━━━━━━━━━━━\n"
                msg += f"💼 **Account Equity**: `${account_equity:,.2f}`\n"
                if liquidation_price and liquidation_price > 0:
                    msg += f"⚠️ **Liquidation**: `${liquidation_price:,.2f}`\n"

            # Add TP/SL if set
            if take_profit > 0 or stop_loss > 0:
                msg += f"━━━━━━━━━━━━━━━━━━\n"
                if take_profit > 0:
                    tp_pct = ((take_profit - price) / price) * 100 if price > 0 else 0
                    msg += f"🎯 **Take Profit**: `${take_profit:,.2f}` ({tp_pct:+.1f}%)\n"
                if stop_loss > 0:
                    sl_pct = ((stop_loss - price) / price) * 100 if price > 0 else 0
                    msg += f"🛡️ **Stop Loss**: `${stop_loss:,.2f}` ({sl_pct:+.1f}%)\n"

            msg += (
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{platform_emoji} **Venue**: `{str(platform).title()}`\n"
                f"🕒 **Time**: `{time.strftime('%H:%M:%S UTC')}`"
            )

            # Add thesis/reasoning if available
            if thesis:
                msg += f"\n💡 _{thesis[:100]}{'...' if len(thesis) > 100 else ''}_"

        await self.send_message(msg, priority=priority)

        # Update daily stats
        self.daily_stats["trades"] += 1
        self.daily_stats["volume"] += notional
        if is_closing:
            self.daily_stats["pnl"] += pnl

    async def send_jupiter_swap_notification(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        input_amount: float,
        output_amount: float,
        tx_signature: str,
        latency_ms: int = 0,
        priority: NotificationPriority = NotificationPriority.HIGH,
    ):
        """Send detailed Jupiter swap notification with blockchain verification."""
        side_emoji = "🟢" if side == "BUY" else "🔴"

        # Calculate value
        notional = price * quantity if price > 0 else 0

        # Format transaction signature
        tx_short = f"{tx_signature[:8]}...{tx_signature[-8:]}" if len(tx_signature) > 16 else tx_signature

        msg = (
            f"{side_emoji} **JUPITER SWAP EXECUTED**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🪐 **Pair**: `{symbol}`\n"
            f"📊 **Action**: `{side}`\n"
            f"💵 **Price**: `${price:,.6f}`\n"
            f"📦 **Quantity**: `{quantity:.6f}`\n"
            f"💰 **Value**: `${notional:.2f}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📥 **Input**: `{input_amount:.6f}`\n"
            f"📤 **Output**: `{output_amount:.6f}`\n"
            f"⚡ **Latency**: `{latency_ms}ms`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔗 **Tx**: `{tx_short}`\n"
            f"🔍 [View on Solscan](https://solscan.io/tx/{tx_signature})\n"
            f"🕒 **Time**: `{time.strftime('%H:%M:%S UTC')}`"
        )

        await self.send_message(msg, priority=priority)

    async def send_position_pnl_update(
        self,
        positions: List[Dict[str, Any]],
        total_unrealized_pnl: float = 0.0,
        total_realized_pnl: float = 0.0,
        priority: NotificationPriority = NotificationPriority.LOW,
    ):
        """
        Send real-time PnL update for all open positions.

        Args:
            positions: List of position dicts with symbol, side, entry_price, current_price, pnl_pct, etc.
            total_unrealized_pnl: Total unrealized P&L across all positions
            total_realized_pnl: Total realized P&L (session)
        """
        if not positions:
            return

        total_emoji = "📈" if total_unrealized_pnl >= 0 else "📉"
        total_pnl_str = f"+${total_unrealized_pnl:,.2f}" if total_unrealized_pnl >= 0 else f"-${abs(total_unrealized_pnl):,.2f}"

        msg = (
            f"{total_emoji} **PORTFOLIO UPDATE**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )

        for pos in positions[:5]:  # Limit to top 5 positions
            symbol = pos.get("symbol", "???")
            side = pos.get("side", "???")
            entry = pos.get("entry_price", 0)
            current = pos.get("current_price", 0)
            pnl_pct = pos.get("pnl_pct", 0)
            trailing_active = pos.get("trailing_stop_active", False)

            # Position emoji
            pos_emoji = "🟢" if side in ["BUY", "LONG"] else "🔴"
            pnl_emoji = "📈" if pnl_pct >= 0 else "📉"
            trail_indicator = "🛡️" if trailing_active else ""

            msg += (
                f"{pos_emoji} **{symbol}** {trail_indicator}\n"
                f"   Entry: `${entry:,.2f}` → `${current:,.2f}`\n"
                f"   {pnl_emoji} PnL: `{pnl_pct:+.2f}%`\n"
            )

        msg += (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💼 **Total Unrealized**: `{total_pnl_str}`\n"
        )

        if total_realized_pnl != 0:
            realized_emoji = "💰" if total_realized_pnl >= 0 else "💸"
            realized_str = f"+${total_realized_pnl:,.2f}" if total_realized_pnl >= 0 else f"-${abs(total_realized_pnl):,.2f}"
            msg += f"{realized_emoji} **Session Realized**: `{realized_str}`\n"

        msg += f"🕒 `{time.strftime('%H:%M:%S UTC')}`"

        await self.send_message(msg, priority=priority)

    async def send_trailing_stop_alert(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        current_price: float,
        stop_price: float,
        highest_price: float,
        pnl_pct: float,
        priority: NotificationPriority = NotificationPriority.HIGH,
    ):
        """Send alert when trailing stop is triggered."""
        side_emoji = "🟢" if side in ["BUY", "LONG"] else "🔴"
        pnl_emoji = "💰" if pnl_pct >= 0 else "💔"

        msg = (
            f"🛑 **TRAILING STOP TRIGGERED**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{side_emoji} **{symbol}** ({side})\n"
            f"📍 **Entry**: `${entry_price:,.4f}`\n"
            f"🏔️ **Peak**: `${highest_price:,.4f}`\n"
            f"🛑 **Stop**: `${stop_price:,.4f}`\n"
            f"📊 **Exit**: `${current_price:,.4f}`\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{pnl_emoji} **Locked PnL**: `{pnl_pct:+.2f}%`\n"
            f"🕒 `{time.strftime('%H:%M:%S UTC')}`"
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

    async def stop(self):
        """Stop the Telegram service and command listener."""
        self.running = False
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        logger.info("📡 Telegram service stopped")

    async def _command_listener(self):
        """Listen for interactive commands via Telegram long polling."""
        logger.info("📡 Starting Telegram command listener...")

        while self.running:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {"offset": self.last_update_id + 1, "timeout": 30}

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=35)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("ok"):
                                for update in data.get("result", []):
                                    self.last_update_id = update["update_id"]
                                    await self._process_command(update)
                        elif resp.status == 409:
                            # Conflict - another instance is polling
                            import random
                            jitter = random.uniform(5, 30)
                            logger.warning(f"Telegram conflict (another instance listening), retrying in {jitter:.1f}s...")
                            await asyncio.sleep(jitter)
                        else:
                            logger.error(f"Telegram listener error: {resp.status}")
                            await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Telegram listener crashed: {e}")
                await asyncio.sleep(10)

    async def _process_command(self, update: Dict[str, Any]):
        """Process incoming Telegram command."""
        message = update.get("message", {})
        text = message.get("text", "")
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Security: Only respond to messages from authorized chat
        if self.chat_id and chat_id != self.chat_id:
            return

        # Pattern 1: @platform action quantity symbol (e.g., @lighter buy 0.1 sol)
        cmd_match = re.search(r"@(\w+)\s+(buy|sell|close)\s+([\d.]+)\s+(\w+)", text.lower())

        # Pattern 2: Status commands (e.g., @aster status, @all status)
        status_match = re.search(r"@(\w+)\s+(status|positions|health)", text.lower())

        if status_match:
            platform = status_match.group(1)
            action = status_match.group(2).upper()

            await self.send_message(
                f"⚡ **Status Request**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **Platform**: `{platform.upper()}`\n"
                f"📝 **Command**: `{action}`\n"
                f"⏳ **Processing**...",
                priority=NotificationPriority.MEDIUM,
            )

            if self.command_callback:
                try:
                    await self.command_callback(platform, "STATUS", action, 0.0)
                except Exception as e:
                    await self.send_message(f"❌ Error executing status command: {e}", priority=NotificationPriority.HIGH)
            else:
                logger.warning("No command callback registered for status commands")

        elif cmd_match:
            platform = cmd_match.group(1)
            action = cmd_match.group(2).upper()
            quantity = float(cmd_match.group(3))
            symbol = cmd_match.group(4).upper()

            # Special case for "all"
            platforms = ["aster", "lighter", "aster", "aster", "jupiter"] if platform == "all" else [platform]

            await self.send_message(
                f"⚡ **MANUAL OVERRIDE DETECTED**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **Platform**: `{platform.upper()}`\n"
                f"📝 **Action**: `{action} {quantity} {symbol}`\n"
                f"⏳ **Verification**: Dispatching to execution layer...",
                priority=NotificationPriority.HIGH,
            )

            if self.command_callback:
                for p in platforms:
                    try:
                        await self.command_callback(p, symbol, action, quantity)
                    except Exception as e:
                        await self.send_message(
                            f"❌ Error dispatching to {p}: {e}",
                            priority=NotificationPriority.HIGH
                        )
            else:
                logger.warning("No command callback registered for Telegram commands")
