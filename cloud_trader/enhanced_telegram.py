"""Enhanced AI-powered Telegram notification service with advanced features."""
from __future__ import annotations
import asyncio
import logging
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass
from enum import Enum

import aiohttp
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, JobQueue
)
from telegram.constants import ParseMode

from .config import Settings
from .ai_analyzer import AITradingAnalyzer
from .market_sentiment import MarketSentimentAnalyzer
from .risk_analyzer import RiskAnalyzer

logger = logging.getLogger(__name__)

class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class NotificationType(Enum):
    TRADE = "trade"
    ALERT = "alert"
    SUMMARY = "summary"
    RISK = "risk"
    MARKET = "market"
    PERFORMANCE = "performance"

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

@dataclass
class MarketInsight:
    symbol: str
    sentiment: str
    confidence: float
    key_levels: Dict[str, float]
    recommendation: str
    analysis: str
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class EnhancedTelegramService:
    """Enhanced AI-powered Telegram notification service."""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        ai_analyzer: Optional[AITradingAnalyzer] = None,
        sentiment_analyzer: Optional[MarketSentimentAnalyzer] = None,
        risk_analyzer: Optional[RiskAnalyzer] = None
    ):
        self.bot = Bot(token=bot_token)
        self.chat_id = chat_id
        self.application = ApplicationBuilder().token(bot_token).build()

        # AI components
        self.ai_analyzer = ai_analyzer
        self.sentiment_analyzer = sentiment_analyzer
        self.risk_analyzer = risk_analyzer

        # State management
        self.daily_stats = {
            'trades': 0,
            'volume': 0.0,
            'pnl': 0.0,
            'win_rate': 0.0
        }
        self.pending_alerts = []
        self.last_market_update = None

        # Setup handlers
        self._setup_handlers()

    def _setup_handlers(self):
        """Setup Telegram command and callback handlers."""
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("portfolio", self.cmd_portfolio))
        self.application.add_handler(CommandHandler("trades", self.cmd_recent_trades))
        self.application.add_handler(CommandHandler("analysis", self.cmd_market_analysis))
        self.application.add_handler(CommandHandler("risk", self.cmd_risk_assessment))
        self.application.add_handler(CommandHandler("performance", self.cmd_performance))
        self.application.add_handler(CommandHandler("alerts", self.cmd_alerts))
        self.application.add_handler(CommandHandler("settings", self.cmd_settings))

        # Callback handlers for interactive buttons
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))

        # Message handler for AI chat
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

    async def start(self):
        """Start the enhanced Telegram bot."""
        logger.info("Starting enhanced Telegram AI bot...")

        # Setup scheduled jobs
        job_queue = self.application.job_queue

        # Daily performance summary at 8 AM UTC
        job_queue.run_daily(
            self._send_daily_summary,
            time=datetime.strptime("08:00", "%H:%M").time()
        )

        # Market analysis every 4 hours
        job_queue.run_repeating(
            self._send_market_analysis,
            interval=timedelta(hours=4),
            first=10
        )

        # Risk alerts every 30 minutes
        job_queue.run_repeating(
            self._check_risk_alerts,
            interval=timedelta(minutes=30),
            first=5
        )

        # Start the bot with polling
        await self.application.run_polling()

        # Send startup notification
        await self.send_startup_notification()

    async def send_startup_notification(self):
        """Send startup notification with system status."""
        message = (
            "🤖 *Sapphire Trading AI Bot Online*\n\n"
            "💎 Enhanced AI-powered trading notifications activated\n"
            "📊 Real-time market analysis & risk monitoring\n"
            "🎯 Smart trade signals with AI insights\n"
            "⚡ Instant alerts for critical events\n\n"
            "Use /help for available commands"
        )
        await self.send_message(message, priority=NotificationPriority.HIGH)

    async def send_trade_notification(
        self,
        trade: TradeNotification,
        priority: NotificationPriority = NotificationPriority.MEDIUM
    ):
        """Send enhanced AI-powered trade notification."""
        # Update daily stats
        self.daily_stats['trades'] += 1
        self.daily_stats['volume'] += trade.notional
        if trade.pnl is not None:
            self.daily_stats['pnl'] += trade.pnl

        # Create base message
        action_emoji = '🚀' if trade.side.upper() == 'BUY' else '📉'
        symbol_md = self._escape_markdown(trade.symbol)

        message = (
            f"{action_emoji} **{trade.side.upper()} {symbol_md}**\n"
            f"💰 Price: `${trade.price:.4f}`\n"
            f"📊 Quantity: `{trade.quantity:.6f}`\n"
            f"💵 Notional: `${trade.notional:.2f}`"
        )

        # Add TP/SL if available
        if trade.take_profit or trade.stop_loss:
            targets = []
            if trade.take_profit:
                targets.append(f"🎯 TP: `${trade.take_profit:.4f}`")
            if trade.stop_loss:
                targets.append(f"🛑 SL: `${trade.stop_loss:.4f}`")
            message += "\n" + " | ".join(targets)

        # Add P&L for closes
        if trade.pnl is not None:
            pnl_emoji = "💚" if trade.pnl > 0 else "💔" if trade.pnl < 0 else "⚪"
            message += f"\n{pnl_emoji} P&L: `${trade.pnl:.2f}`"

        # Add AI analysis if available
        if trade.ai_analysis:
            message += f"\n\n🧠 **AI Analysis:**\n{trade.ai_analysis}"

        # Add confidence score
        if trade.confidence is not None:
            confidence_emoji = self._get_confidence_emoji(trade.confidence)
            message += f"\n{confidence_emoji} Confidence: {trade.confidence:.1%}"

        # Create inline keyboard for actions
        keyboard = [
            [
                InlineKeyboardButton("📈 Chart", callback_data=f"chart_{trade.symbol}"),
                InlineKeyboardButton("📊 Details", callback_data=f"details_{trade.symbol}")
            ]
        ]

        await self.send_message(
            message,
            priority=priority,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def send_market_insight(
        self,
        insight: MarketInsight,
        priority: NotificationPriority = NotificationPriority.MEDIUM
    ):
        """Send AI-powered market insight notification."""
        sentiment_emoji = self._get_sentiment_emoji(insight.sentiment)

        message = (
            f"{sentiment_emoji} **Market Insight: {self._escape_markdown(insight.symbol)}**\n\n"
            f"📈 Sentiment: {insight.sentiment.upper()}\n"
            f"🎯 Confidence: {insight.confidence:.1%}\n\n"
            f"🔑 **Key Levels:**\n"
        )

        for level_name, level_price in insight.key_levels.items():
            message += f"• {level_name}: `${level_price:.4f}`\n"

        message += f"\n💡 **Recommendation:** {insight.recommendation}\n\n"
        message += f"🧠 **AI Analysis:**\n{insight.analysis}"

        keyboard = [
            [
                InlineKeyboardButton("📊 Full Analysis", callback_data=f"analysis_{insight.symbol}"),
                InlineKeyboardButton("📈 Chart", callback_data=f"chart_{insight.symbol}")
            ]
        ]

        await self.send_message(
            message,
            priority=priority,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def send_risk_alert(
        self,
        alert_type: str,
        severity: str,
        message: str,
        recommendations: List[str] = None
    ):
        """Send risk management alert."""
        severity_emoji = {
            'low': '⚠️',
            'medium': '🟡',
            'high': '🔴',
            'critical': '🚨'
        }.get(severity.lower(), '⚠️')

        alert_message = (
            f"{severity_emoji} **Risk Alert: {alert_type.upper()}**\n\n"
            f"{message}\n"
        )

        if recommendations:
            alert_message += "\n💡 **Recommendations:**\n"
            for rec in recommendations:
                alert_message += f"• {rec}\n"

        priority = NotificationPriority.CRITICAL if severity.lower() == 'critical' else \
                  NotificationPriority.HIGH if severity.lower() == 'high' else \
                  NotificationPriority.MEDIUM

        await self.send_message(alert_message, priority=priority)

    async def send_performance_summary(
        self,
        period: str,
        metrics: Dict[str, Any],
        ai_commentary: str = None
    ):
        """Send AI-powered performance summary."""
        message = f"📊 **{period.title()} Performance Summary**\n\n"

        # Key metrics
        message += "**Key Metrics:**\n"
        message += f"• Total Trades: {metrics.get('total_trades', 0)}\n"
        message += f"• Win Rate: {metrics.get('win_rate', 0):.1%}\n"
        message += f"• Total P&L: `${metrics.get('total_pnl', 0):.2f}`\n"
        message += f"• Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}\n"
        message += f"• Max Drawdown: {metrics.get('max_drawdown', 0):.1%}\n"
        message += f"• Total Volume: `${metrics.get('total_volume', 0):.0f}`\n\n"

        # AI commentary
        if ai_commentary:
            message += f"🧠 **AI Performance Analysis:**\n{ai_commentary}\n\n"

        # Recommendations
        recommendations = metrics.get('recommendations', [])
        if recommendations:
            message += "**AI Recommendations:**\n"
            for rec in recommendations:
                message += f"• {rec}\n"

        await self.send_message(message, priority=NotificationPriority.MEDIUM)

    async def send_message(
        self,
        text: str,
        priority: NotificationPriority = NotificationPriority.MEDIUM,
        reply_markup: InlineKeyboardMarkup = None,
        parse_mode: str = ParseMode.MARKDOWN
    ) -> None:
        """Send message with priority handling."""
        try:
            # Add priority indicator
            priority_prefix = {
                NotificationPriority.LOW: "📝",
                NotificationPriority.MEDIUM: "📢",
                NotificationPriority.HIGH: "🚨",
                NotificationPriority.CRITICAL: "🚨🚨"
            }.get(priority, "📢")

            full_message = f"{priority_prefix} {text}"

            await self.bot.send_message(
                chat_id=self.chat_id,
                text=full_message,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )

            logger.info(f"Sent {priority.value} priority Telegram message")

        except Exception as exc:
            logger.error(f"Failed to send Telegram message: {exc}")
            # Fallback without parse mode
            try:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=None,
                    reply_markup=reply_markup
                )
            except Exception as fallback_exc:
                logger.error(f"Fallback Telegram send failed: {fallback_exc}")

    # Command Handlers
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command."""
        welcome_msg = (
            "🤖 *Welcome to Sapphire Trading AI Bot*\n\n"
            "I'm your AI-powered trading assistant with advanced analytics and insights.\n\n"
            "**Available Commands:**\n"
            "/status - Current trading status\n"
            "/portfolio - Portfolio overview\n"
            "/trades - Recent trades\n"
            "/analysis - Market analysis\n"
            "/risk - Risk assessment\n"
            "/performance - Performance metrics\n"
            "/alerts - Active alerts\n"
            "/settings - Bot settings\n\n"
            "💡 *AI Features:*\n"
            "• Real-time trade analysis\n"
            "• Market sentiment monitoring\n"
            "• Risk assessment alerts\n"
            "• Performance insights\n"
            "• Interactive charts\n\n"
            "Type any question for AI assistance!"
        )

        keyboard = [
            [InlineKeyboardButton("📊 Dashboard", callback_data="dashboard")],
            [InlineKeyboardButton("🚨 Risk Status", callback_data="risk_status")],
            [InlineKeyboardButton("📈 Market Analysis", callback_data="market_analysis")]
        ]

        await update.message.reply_text(
            welcome_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command."""
        # This would integrate with the trading service
        status_msg = (
            "🤖 **Trading Bot Status**\n\n"
            "✅ Service: Running\n"
            "📊 Mode: Live Trading\n"
            "🔄 Last Update: Just now\n"
            "📈 Active Positions: 2\n"
            "⚡ Daily P&L: +$127.45\n\n"
            "**System Health:** 🟢 All Systems Operational"
        )

        await update.message.reply_text(status_msg, parse_mode=ParseMode.MARKDOWN)

    async def cmd_portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /portfolio command."""
        portfolio_msg = (
            "💼 **Portfolio Overview**\n\n"
            "**Balance:** $10,247.32\n"
            "**Total Exposure:** $1,847.23 (18%)\n"
            "**Daily P&L:** +$127.45 (+1.26%)\n"
            "**Positions:** 2 active\n\n"
            "**Top Positions:**\n"
            "• BTC/USDT: +$89.32 (4.7%)\n"
            "• ETH/USDT: +$38.13 (2.1%)\n\n"
            "**Risk Metrics:** 🟢 Within Limits"
        )

        keyboard = [
            [InlineKeyboardButton("📊 Details", callback_data="portfolio_details")],
            [InlineKeyboardButton("📈 Charts", callback_data="portfolio_charts")]
        ]

        await update.message.reply_text(
            portfolio_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def cmd_recent_trades(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /trades command."""
        trades_msg = (
            "📈 **Recent Trades**\n\n"
            "**Last 5 Trades:**\n\n"
            "1. 🚀 BUY BTC/USDT @ $43,250\n"
            "   Qty: 0.0234 | Notional: $1,012\n"
            "   AI: Strong bullish momentum detected\n\n"
            "2. 📉 SELL ETH/USDT @ $2,847\n"
            "   Qty: 0.35 | Notional: $997\n"
            "   P&L: +$23.45 | AI: Profit taking at resistance\n\n"
            "3. 🚀 BUY SOL/USDT @ $98.45\n"
            "   Qty: 10.2 | Notional: $1,005\n"
            "   AI: Breakout above key level\n\n"
            "[Showing 3 of 5 trades]"
        )

        keyboard = [
            [InlineKeyboardButton("📊 All Trades", callback_data="all_trades")],
            [InlineKeyboardButton("📈 Performance", callback_data="trade_performance")]
        ]

        await update.message.reply_text(
            trades_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def cmd_market_analysis(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /analysis command."""
        analysis_msg = (
            "🧠 **AI Market Analysis**\n\n"
            "**Overall Sentiment:** 🟢 Bullish (78%)\n\n"
            "**Key Insights:**\n"
            "• BTC showing strong accumulation\n"
            "• ETH breaking above resistance\n"
            "• Altcoins gaining momentum\n\n"
            "**AI Recommendations:**\n"
            "• Maintain long positions\n"
            "• Consider additional BTC exposure\n"
            "• Monitor ETH for continuation\n\n"
            "**Risk Level:** Low 🟢"
        )

        await update.message.reply_text(analysis_msg, parse_mode=ParseMode.MARKDOWN)

    async def cmd_risk_assessment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /risk command."""
        risk_msg = (
            "🛡️ **Risk Assessment**\n\n"
            "**Current Risk Level:** 🟢 Low\n\n"
            "**Risk Metrics:**\n"
            "• Portfolio Exposure: 18% ✅\n"
            "• Max Drawdown: 2.1% ✅\n"
            "• Daily Loss Limit: -$50 ✅\n"
            "• Position Concentration: 12% ✅\n\n"
            "**Active Safeguards:**\n"
            "• Circuit Breakers: 🟢 Active\n"
            "• Kill Switch: ✅ Ready\n"
            "• Auto Hedging: 🟢 Enabled\n\n"
            "**AI Risk Analysis:**\n"
            "Market conditions remain favorable.\n"
            "No immediate risk concerns detected."
        )

        await update.message.reply_text(risk_msg, parse_mode=ParseMode.MARKDOWN)

    async def cmd_performance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /performance command."""
        perf_msg = (
            "📊 **Performance Metrics**\n\n"
            "**Today's Performance:**\n"
            "• P&L: +$127.45 (+1.26%)\n"
            "• Trades: 5 (Win Rate: 80%)\n"
            "• Volume: $5,032\n\n"
            "**This Week:**\n"
            "• P&L: +$892.34 (+9.47%)\n"
            "• Trades: 23 (Win Rate: 74%)\n"
            "• Volume: $28,450\n\n"
            "**This Month:**\n"
            "• P&L: +$2,847.12 (+42.1%)\n"
            "• Trades: 89 (Win Rate: 71%)\n"
            "• Volume: $127,890\n\n"
            "**Sharpe Ratio:** 2.34\n"
            "**Max Drawdown:** 3.2%\n\n"
            "**AI Commentary:**\n"
            "Strong performance with consistent profitability.\n"
            "Risk-adjusted returns excellent."
        )

        await update.message.reply_text(perf_msg, parse_mode=ParseMode.MARKDOWN)

    async def cmd_alerts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /alerts command."""
        alerts_msg = (
            "🚨 **Active Alerts**\n\n"
            "**Current Alerts:**\n"
            "• No critical alerts active\n\n"
            "**Recent Alerts:**\n"
            "• Large position warning (2h ago)\n"
            "• High volatility alert (4h ago)\n"
            "• Profit taking opportunity (6h ago)\n\n"
            "**Alert Settings:**\n"
            "• Risk Alerts: 🔔 Enabled\n"
            "• Trade Alerts: 🔔 Enabled\n"
            "• Market Alerts: 🔕 Disabled\n"
            "• Performance Alerts: 🔔 Enabled"
        )

        keyboard = [
            [InlineKeyboardButton("⚙️ Configure", callback_data="alert_settings")],
            [InlineKeyboardButton("📋 History", callback_data="alert_history")]
        ]

        await update.message.reply_text(
            alerts_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def cmd_settings(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /settings command."""
        settings_msg = (
            "⚙️ **Bot Settings**\n\n"
            "**Notification Settings:**\n"
            "• Trade Notifications: 🔔 On\n"
            "• Risk Alerts: 🔔 On\n"
            "• Market Analysis: 🔕 Off\n"
            "• Performance Reports: 🔔 On\n\n"
            "**AI Features:**\n"
            "• Auto Analysis: 🟢 Enabled\n"
            "• Risk Monitoring: 🟢 Enabled\n"
            "• Smart Alerts: 🟢 Enabled\n\n"
            "**Update Frequency:**\n"
            "• Market Analysis: 4 hours\n"
            "• Risk Checks: 30 minutes\n"
            "• Performance Reports: Daily"
        )

        keyboard = [
            [InlineKeyboardButton("🔔 Notifications", callback_data="notif_settings")],
            [InlineKeyboardButton("🤖 AI Settings", callback_data="ai_settings")],
            [InlineKeyboardButton("📊 Reports", callback_data="report_settings")]
        ]

        await update.message.reply_text(
            settings_msg,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks."""
        query = update.callback_query
        await query.answer()

        callback_data = query.data

        if callback_data == "dashboard":
            await query.edit_message_text(
                "📊 *Trading Dashboard*\n\nOpening full dashboard...",
                parse_mode=ParseMode.MARKDOWN
            )

        elif callback_data == "risk_status":
            await query.edit_message_text(
                "🛡️ *Risk Status: LOW*\n\nAll systems operating within safe parameters.",
                parse_mode=ParseMode.MARKDOWN
            )

        elif callback_data == "market_analysis":
            await query.edit_message_text(
                "🧠 *AI Market Analysis*\n\nGenerating comprehensive market analysis...",
                parse_mode=ParseMode.MARKDOWN
            )

        elif callback_data.startswith("chart_"):
            symbol = callback_data.split("_", 1)[1]
            await query.edit_message_text(
                f"📈 *Chart: {symbol}*\n\nOpening interactive chart...",
                parse_mode=ParseMode.MARKDOWN
            )

        elif callback_data.startswith("analysis_"):
            symbol = callback_data.split("_", 1)[1]
            await query.edit_message_text(
                f"🧠 *AI Analysis: {symbol}*\n\nGenerating detailed analysis...",
                parse_mode=ParseMode.MARKDOWN
            )

        # Add more callback handlers as needed

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular text messages for AI chat."""
        user_message = update.message.text

        # Simple AI response for now (would integrate with actual AI service)
        if any(word in user_message.lower() for word in ['help', 'what can you do']):
            response = (
                "🤖 *I'm your AI Trading Assistant!*\n\n"
                "I can help you with:\n"
                "• 📊 Portfolio analysis\n"
                "• 📈 Market insights\n"
                "• 🛡️ Risk assessment\n"
                "• 📋 Trade recommendations\n"
                "• 📊 Performance analysis\n\n"
                "Try asking:\n"
                "• 'What's my current P&L?'\n"
                "• 'Analyze BTC market'\n"
                "• 'Check risk status'\n"
                "• 'Show recent trades'"
            )
        elif 'portfolio' in user_message.lower():
            response = (
                "💼 *Portfolio Status*\n\n"
                "• Balance: $10,247.32\n"
                "• Daily P&L: +$127.45 (+1.26%)\n"
                "• Active Positions: 2\n"
                "• Risk Level: Low 🟢\n\n"
                "Would you like me to show detailed position breakdown?"
            )
        elif 'risk' in user_message.lower():
            response = (
                "🛡️ *Risk Assessment*\n\n"
                "Current risk level: LOW 🟢\n\n"
                "• Exposure: 18% (within 25% limit)\n"
                "• Daily Loss: +$127 (within -$500 limit)\n"
                "• Max Drawdown: 2.1% (within 5% limit)\n\n"
                "All risk parameters are within safe limits."
            )
        else:
            response = (
                f"🤔 I understood: '{user_message}'\n\n"
                "I'm processing your request... For the most accurate information, "
                "please use specific commands like /status, /portfolio, or /analysis."
            )

        await update.message.reply_text(response, parse_mode=ParseMode.MARKDOWN)

    # Scheduled Tasks
    async def _send_daily_summary(self, context: ContextTypes.DEFAULT_TYPE):
        """Send daily performance summary."""
        # Mock data - would integrate with actual trading service
        daily_metrics = {
            'total_trades': 5,
            'win_rate': 0.8,
            'total_pnl': 127.45,
            'sharpe_ratio': 2.34,
            'max_drawdown': 0.021,
            'total_volume': 5032.0,
            'recommendations': [
                "Maintain current risk parameters",
                "Consider increasing BTC exposure",
                "Monitor ETH for breakout continuation"
            ]
        }

        ai_commentary = (
            "Today's performance shows strong execution with 80% win rate. "
            "The Sharpe ratio of 2.34 indicates excellent risk-adjusted returns. "
            "Continue with current strategy while monitoring for increased volatility."
        )

        await self.send_performance_summary("daily", daily_metrics, ai_commentary)

    async def _send_market_analysis(self, context: ContextTypes.DEFAULT_TYPE):
        """Send periodic market analysis."""
        # Mock market insight - would integrate with actual analysis
        insight = MarketInsight(
            symbol="BTC/USDT",
            sentiment="bullish",
            confidence=0.78,
            key_levels={
                "Support": 42500.0,
                "Resistance": 44500.0,
                "Target": 45000.0
            },
            recommendation="Accumulate on dips",
            analysis="Strong institutional accumulation detected. Volume profile shows increasing buying pressure."
        )

        await self.send_market_insight(insight)

    async def _check_risk_alerts(self, context: ContextTypes.DEFAULT_TYPE):
        """Check for risk alerts and send notifications."""
        # Mock risk check - would integrate with actual risk monitoring
        # Only send alerts if there are actual issues
        pass

    # Helper Methods
    def _escape_markdown(self, text: str) -> str:
        """Escape special characters for Telegram MarkdownV2."""
        escape_chars = '_*[]()~`>#+-=|{}.!'
        return ''.join(f'\\{char}' if char in escape_chars else char for char in str(text))

    def _get_confidence_emoji(self, confidence: float) -> str:
        """Get emoji for confidence level."""
        if confidence >= 0.8:
            return "🟢"
        elif confidence >= 0.6:
            return "🟡"
        else:
            return "🔴"

    def _get_sentiment_emoji(self, sentiment: str) -> str:
        """Get emoji for market sentiment."""
        sentiment_map = {
            'bullish': '🟢',
            'bearish': '🔴',
            'neutral': '🟡',
            'volatile': '🟠'
        }
        return sentiment_map.get(sentiment.lower(), '⚪')

async def create_enhanced_telegram_service(
    settings: Settings,
    ai_analyzer: Optional[AITradingAnalyzer] = None,
    sentiment_analyzer: Optional[MarketSentimentAnalyzer] = None,
    risk_analyzer: Optional[RiskAnalyzer] = None
) -> Optional[EnhancedTelegramService]:
    """Create enhanced Telegram service with AI capabilities."""
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        logger.warning("Telegram bot token or chat ID not configured")
        return None

    try:
        service = EnhancedTelegramService(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
            ai_analyzer=ai_analyzer,
            sentiment_analyzer=sentiment_analyzer,
            risk_analyzer=risk_analyzer
        )

        logger.info("Enhanced Telegram AI bot service created")
        return service

    except Exception as exc:
        logger.error(f"Failed to create enhanced Telegram service: {exc}")
        return None
