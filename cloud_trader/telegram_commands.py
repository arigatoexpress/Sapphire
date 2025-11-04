"""Interactive Telegram command handlers for trading bot."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

logger = logging.getLogger(__name__)


class TelegramCommandHandler:
    """Handler for interactive Telegram commands."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        trading_service: Any,  # TradingService type
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.trading_service = trading_service
        self.application: Optional[Application] = None
        self._task: Optional[asyncio.Task[None]] = None

    async def start(self) -> None:
        """Start the Telegram command handler."""
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram bot token or chat ID not configured, skipping command handler")
            return

        try:
            self.application = Application.builder().token(self.bot_token).build()

            # Register command handlers
            self.application.add_handler(CommandHandler("start", self._start_command))
            self.application.add_handler(CommandHandler("status", self._status_command))
            self.application.add_handler(CommandHandler("portfolio", self._portfolio_command))
            self.application.add_handler(CommandHandler("positions", self._positions_command))
            self.application.add_handler(CommandHandler("performance", self._performance_command))
            self.application.add_handler(CommandHandler("risk", self._risk_command))
            self.application.add_handler(CommandHandler("help", self._help_command))

            # Initialize and start polling
            await self.application.initialize()
            await self.application.start()
            self._task = asyncio.create_task(self._poll_updates())
            logger.info("Telegram command handler started")
        except Exception as exc:
            logger.error(f"Failed to start Telegram command handler: {exc}")

    async def stop(self) -> None:
        """Stop the Telegram command handler."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self.application:
            await self.application.stop()
            await self.application.shutdown()

    async def _poll_updates(self) -> None:
        """Poll for Telegram updates."""
        if not self.application:
            return

        try:
            await self.application.updater.start_polling(
                allowed_updates=["message"],
                drop_pending_updates=True,
            )
        except Exception as exc:
            logger.error(f"Error polling Telegram updates: {exc}")

    async def _start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        if str(update.effective_chat.id) != self.chat_id:
            await update.message.reply_text("❌ Unauthorized access")
            return

        message = """
🤖 <b>Sapphire AI Trading Bot</b>

Welcome! I'm your autonomous trading assistant.

<b>Available Commands:</b>
/status - System health and trading status
/portfolio - Current portfolio balance and exposure
/positions - Open positions and P&L
/performance - Trading performance metrics
/risk - Risk management status
/help - Show this help message

Trading is running 24/7 autonomously. I'll notify you of all trades and important events!
"""
        await update.message.reply_text(message, parse_mode="HTML")

    async def _status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /status command."""
        if str(update.effective_chat.id) != self.chat_id:
            await update.message.reply_text("❌ Unauthorized access")
            return

        try:
            health = self.trading_service.health()
            status_emoji = "🟢" if health.running else "🔴"
            trading_mode = "📄 Paper Trading" if health.paper_trading else "💰 Live Trading"

            message = f"""
{status_emoji} <b>System Status</b>

<b>Status:</b> {"Running" if health.running else "Stopped"}
<b>Mode:</b> {trading_mode}
<b>Last Error:</b> {health.last_error or "None"}

<i>System is operating autonomously</i>
"""
            await update.message.reply_text(message, parse_mode="HTML")
        except Exception as exc:
            await update.message.reply_text(f"❌ Error fetching status: {exc}")

    async def _portfolio_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /portfolio command."""
        if str(update.effective_chat.id) != self.chat_id:
            await update.message.reply_text("❌ Unauthorized access")
            return

        try:
            portfolio = self.trading_service._portfolio
            total_exposure = portfolio.total_exposure
            balance = portfolio.balance
            leverage = total_exposure / balance if balance > 0 else 0.0

            message = f"""
💰 <b>Portfolio</b>

<b>Balance:</b> ${balance:,.2f}
<b>Total Exposure:</b> ${total_exposure:,.2f}
<b>Leverage:</b> {leverage:.2f}x
<b>Open Positions:</b> {len(portfolio.positions)}

<i>Portfolio updated in real-time</i>
"""
            await update.message.reply_text(message, parse_mode="HTML")
        except Exception as exc:
            await update.message.reply_text(f"❌ Error fetching portfolio: {exc}")

    async def _positions_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /positions command."""
        if str(update.effective_chat.id) != self.chat_id:
            await update.message.reply_text("❌ Unauthorized access")
            return

        try:
            portfolio = self.trading_service._portfolio
            positions = portfolio.positions

            if not positions:
                await update.message.reply_text("📊 <b>No Open Positions</b>\n\nAll positions are closed.", parse_mode="HTML")
                return

            message = "📊 <b>Open Positions</b>\n\n"
            total_pnl = 0.0

            for symbol, position in positions.items():
                pnl = position.pnl if hasattr(position, "pnl") else 0.0
                total_pnl += pnl
                pnl_emoji = "🟢" if pnl >= 0 else "🔴"
                message += f"{pnl_emoji} <b>{symbol}</b>\n"
                message += f"   P&L: ${pnl:,.2f}\n"
                if hasattr(position, "notional"):
                    message += f"   Size: ${position.notional:,.2f}\n"
                message += "\n"

            message += f"<b>Total P&L:</b> ${total_pnl:,.2f}"
            await update.message.reply_text(message, parse_mode="HTML")
        except Exception as exc:
            await update.message.reply_text(f"❌ Error fetching positions: {exc}")

    async def _performance_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /performance command."""
        if str(update.effective_chat.id) != self.chat_id:
            await update.message.reply_text("❌ Unauthorized access")
            return

        try:
            agents = self.trading_service._agent_states
            if not agents:
                await update.message.reply_text("📈 <b>Performance</b>\n\nNo agent data available yet.", parse_mode="HTML")
                return

            message = "📈 <b>Trading Performance</b>\n\n"
            total_trades = 0
            total_pnl = 0.0

            for agent_id, state in agents.items():
                total_trades += state.total_trades
                total_pnl += state.total_pnl
                status_emoji = "🟢" if state.status == "active" else "🟡" if state.status == "monitoring" else "⚪"
                message += f"{status_emoji} <b>{state.name}</b>\n"
                message += f"   Trades: {state.total_trades}\n"
                message += f"   P&L: ${state.total_pnl:,.2f}\n"
                message += f"   Win Rate: {state.win_rate * 100:.1f}%\n\n"

            message += f"<b>Total Trades:</b> {total_trades}\n"
            message += f"<b>Total P&L:</b> ${total_pnl:,.2f}"
            await update.message.reply_text(message, parse_mode="HTML")
        except Exception as exc:
            await update.message.reply_text(f"❌ Error fetching performance: {exc}")

    async def _risk_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /risk command."""
        if str(update.effective_chat.id) != self.chat_id:
            await update.message.reply_text("❌ Unauthorized access")
            return

        try:
            portfolio = self.trading_service._portfolio
            risk_manager = self.trading_service._risk
            settings = self.trading_service._settings

            max_exposure = settings.max_total_exposure
            current_exposure = portfolio.total_exposure
            exposure_pct = (current_exposure / portfolio.balance * 100) if portfolio.balance > 0 else 0.0

            risk_emoji = "🟢" if exposure_pct < 80 else "🟡" if exposure_pct < 95 else "🔴"

            message = f"""
⚠️ <b>Risk Management</b>

{risk_emoji} <b>Exposure:</b> ${current_exposure:,.2f} / ${max_exposure:,.2f}
<b>Exposure %:</b> {exposure_pct:.1f}%
<b>Max Positions:</b> {settings.max_concurrent_positions}
<b>Current Positions:</b> {len(portfolio.positions)}

<i>Risk limits are enforced automatically</i>
"""
            await update.message.reply_text(message, parse_mode="HTML")
        except Exception as exc:
            await update.message.reply_text(f"❌ Error fetching risk info: {exc}")

    async def _help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /help command."""
        if str(update.effective_chat.id) != self.chat_id:
            await update.message.reply_text("❌ Unauthorized access")
            return

        message = """
📖 <b>Command Help</b>

<b>Available Commands:</b>

/start - Start the bot and see welcome message
/status - Check system health and trading status
/portfolio - View current portfolio balance and exposure
/positions - List all open positions with P&L
/performance - View trading performance by agent
/risk - Check risk management status and limits
/help - Show this help message

<i>All commands are rate-limited for security</i>
"""
        await update.message.reply_text(message, parse_mode="HTML")

