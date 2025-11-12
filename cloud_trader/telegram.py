"""Telegram notification service."""
from __future__ import annotations
import logging
import re
from typing import Optional
from telegram import Bot
from .config import Settings

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id

    async def send_message(self, text: str, parse_mode: str = 'MarkdownV2') -> None:
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode=parse_mode)
        except Exception as exc:
            logger.error(f"Failed to send Telegram message with parse_mode={parse_mode}: {exc}")
            if parse_mode:
                try:
                    await self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode=None)
                    return
                except Exception as fallback_exc:
                    logger.error(f"Fallback Telegram send failed: {fallback_exc}")

    async def send_trade_notification(self, **kwargs):
        """Send concise trade notifications only."""
        side = kwargs.get('side', 'N/A').upper()
        symbol = kwargs.get('symbol', 'N/A')
        price = kwargs.get('price', 0.0)
        notional = kwargs.get('notional', 0.0)
        pnl = kwargs.get('pnl')
        take_profit = kwargs.get('take_profit', 0.0)
        stop_loss = kwargs.get('stop_loss', 0.0)

        # Escape for MarkdownV2
        symbol_md = self._escape_markdown(symbol)

        action_emoji = '🚀' if side == 'BUY' else '📉'

        # Ultra-concise trade message
        message = f"{action_emoji} *{side} {symbol_md}* | `${price:.2f}` | `${notional:.0f}`"

        # Add TP/SL if available
        if take_profit > 0 or stop_loss > 0:
            targets = []
            if take_profit > 0:
                targets.append(f"TP: ${take_profit:.2f}")
            if stop_loss > 0:
                targets.append(f"SL: ${stop_loss:.2f}")
            if targets:
                message += f" | {' | '.join(targets)}"

        # Add P&L for closes
        if pnl is not None:
            pnl_emoji = "💚" if pnl > 0 else "💔" if pnl < 0 else "⚪"
            message += f" | {pnl_emoji} ${pnl:.2f}"

        await self.send_message(message)

    async def send_market_observation(self, **kwargs):
        """Disabled - too noisy for trade-focused notifications."""
        return  # Skip all market observations to reduce noise

    async def send_mcp_notification(self, **kwargs):
        """Disabled - too noisy for trade-focused notifications."""
        return  # Skip all MCP notifications to reduce noise

    def _escape_markdown(self, text: str) -> str:
        """Helper to escape characters for Telegram's MarkdownV2."""
        escape_chars = '_*[]()~`>#+-=|{}.!'
        return ''.join(f'\\{char}' if char in escape_chars else char for char in str(text))

async def create_telegram_service(settings: Settings) -> Optional[TelegramService]:
    if settings.telegram_bot_token and settings.telegram_chat_id:
        return TelegramService(settings.telegram_bot_token, settings.telegram_chat_id)
    return None
