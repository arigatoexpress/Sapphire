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
        pnl = kwargs.get('pnl')
        portfolio_balance = kwargs.get('portfolio_balance', 0.0)
        risk_percentage = kwargs.get('risk_percentage', 0.0)
        take_profit = kwargs.get('take_profit', 0.0)
        stop_loss = kwargs.get('stop_loss', 0.0)
        market_context = kwargs.get('market_context', {})
        trade_thesis = kwargs.get('trade_thesis', '')
        risk_reward_ratio = kwargs.get('risk_reward_ratio', 0.0)

        # Escape special characters for MarkdownV2
        symbol_md = self._escape_markdown(symbol)
        reason_md = self._escape_markdown(reason)
        model_md = self._escape_markdown(model)
        thesis_md = self._escape_markdown(trade_thesis)

        action_emoji = '🚀' if side == 'BUY' else '📉'

        # Market observations
        market_obs = ""
        if market_context:
            change_24h = market_context.get('change_24h', 0)
            volume = market_context.get('volume', 0)
            atr = market_context.get('atr')

            trend = "📈 Bullish" if change_24h > 0 else "📉 Bearish" if change_24h < 0 else "➡️ Sideways"
            market_obs = (
                f"• Market Trend: {trend} ({change_24h:+.2f}% 24h)\n"
                f"• Volume: `${volume:,.0f}`\n"
            )
            if atr:
                market_obs += f"• Volatility (ATR): `${atr:.4f}`\n"

        # Trading thesis and reasoning
        thesis_section = ""
        if trade_thesis:
            thesis_section = f"*🎯 Trading Thesis:*\n_{thesis_md}_\n\n"

        # Risk/Reward analysis
        rr_section = ""
        if risk_reward_ratio > 0:
            rr_section = f"• Risk\\-Reward Ratio: `{risk_reward_ratio:.1f}:1`\n"

        # Targets
        targets_section = ""
        if take_profit > 0 or stop_loss > 0:
            targets_section = f"*🎯 Position Targets:*\n"
            if take_profit > 0:
                profit_pct = ((take_profit - price) / price) * 100 if side == 'BUY' else ((price - take_profit) / price) * 100
                targets_section += f"• Take Profit: `${take_profit:,.4f}` ({profit_pct:+.1f}%)\n"
            if stop_loss > 0:
                loss_pct = ((price - stop_loss) / price) * 100 if side == 'BUY' else ((stop_loss - price) / price) * 100
                targets_section += f"• Stop Loss: `${stop_loss:,.4f}` ({loss_pct:+.1f}%)\n"

        message = (
            f"{action_emoji} *TRADE EXECUTED: {side} {symbol_md}*\n\n"
            f"*📊 Market Observations:*\n"
            f"{market_obs}\n"
            f"*🧠 AI Analysis:*\n"
            f"• Model: `{model_md}`\n"
            f"• Confidence: `{confidence:.1f}%`\n"
            f"• Signal: _{reason_md}_\n"
            f"{rr_section}\n"
            f"{thesis_section}"
            f"*💰 Execution Details:*\n"
            f"• Entry Price: `${price:,.4f}`\n"
            f"• Position Size: `{quantity:,.6f}` contracts\n"
            f"• Notional Value: `${notional:,.2f}`\n\n"
            f"{targets_section}"
            f"*📊 Portfolio Impact:*\n"
            f"• Risk Allocation: `{risk_percentage:.2f}%` of portfolio\n"
            f"• Post\\-Trade Balance: `${portfolio_balance:,.2f}`\n"
        )

        if pnl is not None:
            pnl_emoji = "💚" if pnl > 0 else "💔" if pnl < 0 else "⚪"
            message += f"• Realized P&L: {pnl_emoji} `${pnl:,.2f}`"

        await self.send_message(message)

    async def send_market_observation(self, **kwargs):
        """Send periodic market observations and portfolio analysis."""
        portfolio_balance = kwargs.get('portfolio_balance', 0.0)
        active_positions = kwargs.get('active_positions', [])
        total_pnl = kwargs.get('total_pnl', 0.0)
        market_summary = kwargs.get('market_summary', {})
        trading_activity = kwargs.get('trading_activity', {})

        # Portfolio overview
        portfolio_md = self._escape_markdown(f"${portfolio_balance:,.2f}")
        pnl_md = self._escape_markdown(f"${total_pnl:,.2f}")
        pnl_emoji = "💚" if total_pnl > 0 else "💔" if total_pnl < 0 else "⚪"

        message = (
            f"📊 *PORTFOLIO STATUS UPDATE*\n\n"
            f"*💰 Portfolio Balance:* `{portfolio_md}`\n"
            f"*📈 Total P&L:* {pnl_emoji} `{pnl_md}`\n"
            f"*📊 Active Positions:* `{len(active_positions)}`\n\n"
        )

        # Market summary
        if market_summary:
            message += f"*🌍 Market Overview:*\n"
            for symbol, data in market_summary.items():
                if isinstance(data, dict):
                    change = data.get('change_24h', 0)
                    volume = data.get('volume', 0)
                    trend_emoji = "📈" if change > 0 else "📉" if change < 0 else "➡️"
                    message += f"• {symbol}: {trend_emoji} {change:+.1f}% | Vol: {volume:,.0f}\n"
            message += "\n"

        # Trading activity
        if trading_activity:
            trades_today = trading_activity.get('trades_today', 0)
            win_rate = trading_activity.get('win_rate', 0)
            avg_return = trading_activity.get('avg_return', 0)

            message += (
                f"*⚡ Trading Activity:*\n"
                f"• Trades Today: `{trades_today}`\n"
                f"• Win Rate: `{win_rate:.1f}%`\n"
                f"• Avg Return/Trade: `{avg_return:+.2f}%`\n\n"
            )

        # Active positions summary
        if active_positions:
            message += f"*🎯 Active Positions:*\n"
            for pos in active_positions[:3]:  # Show top 3
                symbol = pos.get('symbol', 'UNK')
                side = pos.get('side', 'UNK')
                notional = pos.get('notional', 0)
                pnl = pos.get('pnl', 0)

                side_emoji = "📈" if side.upper() == 'BUY' else "📉"
                pnl_emoji = "💚" if pnl > 0 else "💔" if pnl < 0 else "⚪"

                message += f"• {symbol}: {side_emoji} `${notional:,.0f}` | {pnl_emoji} `${pnl:,.2f}`\n"

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
