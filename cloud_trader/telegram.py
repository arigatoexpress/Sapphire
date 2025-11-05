"""Telegram notification service."""
from __future__ import annotations
import logging
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
        side = kwargs.get('side', 'N/A').upper()
        symbol = kwargs.get('symbol', 'N/A')
        price = kwargs.get('price', 0.0)
        quantity = kwargs.get('quantity', 0.0)
        notional = kwargs.get('notional', 0.0)
        reason = kwargs.get('decision_reason', 'N/A')
        model = kwargs.get('model_used', 'N/A')
        confidence = kwargs.get('confidence', 0.0) * 100
        pnl = kwargs.get('pnl') # Can be None
        portfolio_balance = kwargs.get('portfolio_balance', 0.0)
        risk_percentage = kwargs.get('risk_percentage', 0.0)

        # Escape special characters for MarkdownV2
        symbol_md = self._escape_markdown(symbol)
        reason_md = self._escape_markdown(reason)
        model_md = self._escape_markdown(model)

        action_emoji = '📈' if side == 'BUY' else '📉'
        
        message = (
            f"{action_emoji} *New Trade: {side} {symbol_md}*\n\n"
            f"*Execution Details:*\n"
            f"• Price: `${price:,.4f}`\n"
            f"• Quantity: `{quantity:,.6f}`\n"
            f"• Notional: `${notional:,.2f}`\n\n"
            f"*AI Signal Context:*\n"
            f"• Model: `{model_md}`\n"
            f"• Confidence: `{confidence:.1f}%`\n"
            f"• Rationale: _{reason_md}_\n\n"
            f"*Portfolio Impact:*\n"
            f"• Risk Allocation: `{risk_percentage:.2f}%` of portfolio\n"
            f"• Post Trade Balance Estimated: `${portfolio_balance:,.2f}`"
        )

        if pnl is not None:
            message += f"\n• Realized PnL: `${pnl:,.2f}`"

        await self.send_message(message)

    async def send_mcp_notification(self, **kwargs):
        message_type = self._escape_markdown(kwargs.get('message_type', 'N/A').upper())
        session_id = self._escape_markdown(kwargs.get('session_id', 'N/A'))
        sender_id = self._escape_markdown(kwargs.get('sender_id', 'N/A'))
        content = self._escape_markdown(kwargs.get('content', 'N/A'))
        
        message = (
            f"🤖 *MCP Event: {message_type}*\n"
            f"• Session: `{session_id}`\n"
            f"• Sender: `{sender_id}`\n"
            f"• Content: _{content}_"
        )
        await self.send_message(message)

    def _escape_markdown(self, text: str) -> str:
        """Helper to escape characters for Telegram's MarkdownV2."""
        escape_chars = '_*[]()~`>#+-=|{}.!'
        return ''.join(f'\\{char}' if char in escape_chars else char for char in str(text))

async def create_telegram_service(settings: Settings) -> Optional[TelegramService]:
    if settings.telegram_bot_token and settings.telegram_chat_id:
        return TelegramService(settings.telegram_bot_token, settings.telegram_chat_id)
    return None
