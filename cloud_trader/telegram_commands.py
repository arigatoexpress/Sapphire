"""Telegram bot command handler for admin interaction."""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

if TYPE_CHECKING:
    from .service import TradingService

logger = logging.getLogger(__name__)

class TelegramCommandHandler:
    def __init__(self, bot_token: str, chat_id: str, trading_service: 'TradingService'):
        self.application = ApplicationBuilder().token(bot_token).build()
        self.chat_id = chat_id
        self.trading_service = trading_service
        self._add_handlers()

    def _add_handlers(self):
        self.application.add_handler(CommandHandler("status", self.status))
        self.application.add_handler(CommandHandler("start_trading", self.start_trading))
        self.application.add_handler(CommandHandler("stop_trading", self.stop_trading))
        self.application.add_handler(CommandHandler("portfolio", self.portfolio))
        self.application.add_handler(CommandHandler("kill_switch", self.kill_switch))
        self.application.add_handler(CommandHandler("safeguards", self.safeguards))

    async def start(self):
        logger.info("Starting Telegram command handler...")
        self.application.run_async()

    async def _restricted(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        if str(update.effective_chat.id) != self.chat_id:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="You are not authorized.")
            return True
        return False

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await self._restricted(update, context): return
        health = self.trading_service.health()
        status_msg = f"Trading Bot Status:\n- Running: {health.running}\n- Paper Trading: {health.paper_trading}\n- Last Error: {health.last_error or 'None'}"
        await context.bot.send_message(chat_id=self.chat_id, text=status_msg)

    async def start_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await self._restricted(update, context): return
        await self.trading_service.start()
        await context.bot.send_message(chat_id=self.chat_id, text="Trading service started.")

    async def stop_trading(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await self._restricted(update, context): return
        await self.trading_service.stop()
        await context.bot.send_message(chat_id=self.chat_id, text="Trading service stopped.")

    async def portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await self._restricted(update, context): return
        portfolio_data = await self.trading_service.dashboard_snapshot()
        portfolio_msg = f"Portfolio:\n- Balance: ${portfolio_data['portfolio']['balance']}\n- Exposure: ${portfolio_data['portfolio']['total_exposure']}"
        await context.bot.send_message(chat_id=self.chat_id, text=portfolio_msg)
    
    async def kill_switch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await self._restricted(update, context): return
        
        # Parse command arguments
        args = context.args
        if not args:
            usage = "Usage: /kill_switch [activate|deactivate|status] [reason]"
            await context.bot.send_message(chat_id=self.chat_id, text=usage)
            return
        
        action = args[0].lower()
        reason = " ".join(args[1:]) if len(args) > 1 else ""
        
        # Import handle_kill_switch_command
        from .safeguards import handle_kill_switch_command
        result = await handle_kill_switch_command(self.trading_service._safeguards, action, reason)
        
        await context.bot.send_message(chat_id=self.chat_id, text=result, parse_mode='Markdown')
    
    async def safeguards(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if await self._restricted(update, context): return
        
        status = self.trading_service._safeguards.get_status()
        
        # Format status message
        msg = "🛡 **Safeguards Status**\n\n"
        
        # Kill switch
        kill_switch = status['kill_switch']
        msg += f"**Kill Switch**: {'🚨 ACTIVE' if kill_switch['active'] else '✅ Inactive'}\n"
        if kill_switch['active']:
            msg += f"Reason: {kill_switch['reason']}\n"
        msg += "\n"
        
        # Circuit breakers
        msg += "**Circuit Breakers**:\n"
        for name, breaker in status['circuit_breakers'].items():
            emoji = '🟢' if breaker['state'] == 'CLOSED' else '🔴' if breaker['state'] == 'OPEN' else '🟡'
            msg += f"  {emoji} {name}: {breaker['state']} (failures: {breaker['failures']})\n"
        msg += "\n"
        
        # Heat metrics
        heat = status['heat_metrics']
        msg += "**Risk Metrics**:\n"
        msg += f"  Exposure: {heat['exposure']}%\n"
        msg += f"  Positions: {heat['positions']}\n"
        msg += f"  Daily Loss: {heat['daily_loss']}\n"
        msg += f"  Max Drawdown: {heat['max_drawdown']}\n"
        msg += "\n"
        
        # Limits
        limits = status['limits']
        msg += "**Limits**:\n"
        msg += f"  Max Exposure: {limits['max_exposure']}\n"
        msg += f"  Max Positions: {limits['max_positions']}\n"
        msg += f"  Max Drawdown: {limits['max_drawdown']}\n"
        msg += f"  Daily Loss Limit: {limits['daily_loss_limit']}\n"
        msg += f"  Order Rate: {limits['current_order_rate']}/{limits['orders_per_minute']}/min\n"
        
        await context.bot.send_message(chat_id=self.chat_id, text=msg, parse_mode='Markdown')

