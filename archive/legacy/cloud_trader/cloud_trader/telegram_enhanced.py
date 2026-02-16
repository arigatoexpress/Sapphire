"""
Enhanced Telegram Notifications for Sapphire V2
Rich formatting, real-time updates, and comprehensive trade notifications
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional, Any
import aiohttp
from loguru import logger


class NotificationType(Enum):
    """Notification categories"""
    SYSTEM = "🖥️"
    TRADE_SIGNAL = "📊"
    TRADE_EXECUTED = "✅"
    TRADE_FAILED = "❌"
    POSITION_UPDATE = "📈"
    RISK_ALERT = "⚠️"
    AI_ANALYSIS = "🤖"
    PROFIT = "💰"
    LOSS = "📉"
    CRITICAL = "🚨"


class TelegramEnhanced:
    """
    Enhanced Telegram notification system for Sapphire V2

    Features:
    - Rich formatting with emojis and markdown
    - Trade execution summaries
    - AI analysis updates
    - Position tracking
    - P&L reporting
    - System health alerts
    """

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.session: Optional[aiohttp.ClientSession] = None

        logger.info("✅ Enhanced Telegram notifications initialized")

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10)
            )
        return self.session

    async def send(
        self,
        text: str,
        notification_type: NotificationType = NotificationType.SYSTEM,
        disable_preview: bool = True
    ):
        """Send enhanced notification"""
        try:
            # Add type emoji prefix
            formatted_text = f"{notification_type.value} {text}"

            session = await self._get_session()
            url = f"{self.base_url}/sendMessage"

            payload = {
                "chat_id": self.chat_id,
                "text": formatted_text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": disable_preview
            }

            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.warning(f"Telegram notification failed: {resp.status}")
                    # Retry without markdown if parse error
                    if resp.status == 400:
                        payload.pop("parse_mode")
                        await session.post(url, json=payload)
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")

    async def notify_system_start(self, service_name: str, features: List[str]):
        """Notify system startup with features"""
        features_text = "\n".join([f"  ✓ {feature}" for feature in features])

        message = f"""
*🚀 Sapphire V2 Started*

*Service:* `{service_name}`
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

*Active Features:*
{features_text}

Ready to trade! 📈
"""
        await self.send(message, NotificationType.SYSTEM)

    async def notify_ai_initialized(self, model: str, agents: List[str]):
        """Notify AI model initialization"""
        agents_text = "\n".join([f"  • {agent}" for agent in agents])

        message = f"""
*🤖 AI System Initialized*

*Model:* `{model}`
*Agents Active:* {len(agents)}

{agents_text}

AI-driven trading enabled ⚡
"""
        await self.send(message, NotificationType.AI_ANALYSIS)

    async def notify_trade_signal(
        self,
        symbol: str,
        side: str,
        platform: str,
        confidence: float,
        reasoning: str,
        price: Optional[Decimal] = None
    ):
        """Notify new trade signal"""

        side_emoji = "🟢" if side.upper() == "BUY" else "🔴"
        confidence_bar = "█" * int(confidence * 10)

        price_text = f"*Price:* ${price:.4f}" if price else ""

        message = f"""
*{side_emoji} Trade Signal Generated*

*Symbol:* `{symbol}`
*Side:* *{side.upper()}*
*Platform:* {platform}
*Confidence:* {confidence_bar} {confidence*100:.1f}%
{price_text}

*AI Reasoning:*
_{reasoning[:200]}_...

Executing trade...
"""
        await self.send(message, NotificationType.TRADE_SIGNAL)

    async def notify_trade_executed(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        price: Decimal,
        platform: str,
        latency_ms: int,
        trade_id: str
    ):
        """Notify successful trade execution"""

        side_emoji = "🟢" if side.upper() == "BUY" else "🔴"
        total_value = quantity * price

        message = f"""
*{side_emoji} Trade Executed*

*Symbol:* `{symbol}`
*Side:* *{side.upper()}*
*Quantity:* {quantity:.6f}
*Price:* ${price:.4f}
*Total:* ${total_value:.2f}
*Platform:* {platform}
*Latency:* {latency_ms}ms

*Trade ID:* `{trade_id[:12]}...`

✅ Execution successful
"""
        await self.send(message, NotificationType.TRADE_EXECUTED)

    async def notify_trade_failed(
        self,
        symbol: str,
        side: str,
        platform: str,
        error: str
    ):
        """Notify failed trade"""

        message = f"""
*❌ Trade Failed*

*Symbol:* `{symbol}`
*Side:* *{side.upper()}*
*Platform:* {platform}

*Error:* _{error[:150]}_

Investigating...
"""
        await self.send(message, NotificationType.TRADE_FAILED)

    async def notify_position_opened(
        self,
        symbol: str,
        side: str,
        size: Decimal,
        entry_price: Decimal,
        leverage: Optional[int] = None,
        stop_loss: Optional[Decimal] = None,
        take_profit: Optional[Decimal] = None
    ):
        """Notify position opened (for perpetuals)"""

        side_emoji = "📈" if side.lower() == "long" else "📉"
        leverage_text = f"{leverage}x leverage" if leverage else "Spot"

        notional_value = size * entry_price * (leverage or 1)

        sl_text = f"*Stop Loss:* ${stop_loss:.4f}" if stop_loss else ""
        tp_text = f"*Take Profit:* ${take_profit:.4f}" if take_profit else ""

        message = f"""
*{side_emoji} Position Opened*

*Symbol:* `{symbol}`
*Side:* *{side.upper()}*
*Size:* {size:.6f}
*Entry:* ${entry_price:.4f}
*{leverage_text}*
*Notional:* ${notional_value:.2f}

{sl_text}
{tp_text}

Position active 🎯
"""
        await self.send(message, NotificationType.POSITION_UPDATE)

    async def notify_position_closed(
        self,
        symbol: str,
        side: str,
        pnl: Decimal,
        pnl_percentage: float,
        exit_price: Decimal,
        hold_time_hours: float
    ):
        """Notify position closed with P&L"""

        pnl_emoji = "💰" if pnl > 0 else "📉"
        result_text = "PROFIT" if pnl > 0 else "LOSS"

        message = f"""
*{pnl_emoji} Position Closed - {result_text}*

*Symbol:* `{symbol}`
*P&L:* ${pnl:.2f} ({pnl_percentage:+.2f}%)
*Exit Price:* ${exit_price:.4f}
*Hold Time:* {hold_time_hours:.1f}h

{"🎉 Well done!" if pnl > 0 else "📊 Learn and improve"}
"""

        notification_type = NotificationType.PROFIT if pnl > 0 else NotificationType.LOSS
        await self.send(message, notification_type)

    async def notify_daily_summary(
        self,
        total_trades: int,
        winning_trades: int,
        total_pnl: Decimal,
        best_trade: Dict[str, Any],
        worst_trade: Dict[str, Any]
    ):
        """Send daily trading summary"""

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        pnl_emoji = "💰" if total_pnl > 0 else "📉"

        message = f"""
*📊 Daily Trading Summary*

*Date:* {datetime.now().strftime('%Y-%m-%d')}

*Trades:* {total_trades}
*Win Rate:* {win_rate:.1f}%
*Total P&L:* {pnl_emoji} ${total_pnl:+.2f}

*Best Trade:*
  `{best_trade.get('symbol')}` - ${best_trade.get('pnl', 0):+.2f}

*Worst Trade:*
  `{worst_trade.get('symbol')}` - ${worst_trade.get('pnl', 0):+.2f}

{"🎉 Profitable day!" if total_pnl > 0 else "📈 Tomorrow is a new day"}
"""
        await self.send(message, NotificationType.SYSTEM)

    async def notify_risk_alert(
        self,
        alert_type: str,
        symbol: str,
        details: str,
        severity: str = "HIGH"
    ):
        """Send risk management alert"""

        severity_emoji = "🚨" if severity == "CRITICAL" else "⚠️"

        message = f"""
*{severity_emoji} Risk Alert - {severity}*

*Type:* {alert_type}
*Symbol:* `{symbol}`

*Details:*
_{details}_

Action required! 🛑
"""

        notification_type = NotificationType.CRITICAL if severity == "CRITICAL" else NotificationType.RISK_ALERT
        await self.send(message, notification_type)

    async def notify_system_health(
        self,
        services_healthy: int,
        total_services: int,
        ai_status: str,
        issues: List[str]
    ):
        """Send system health update"""

        health_percentage = (services_healthy / total_services * 100)
        health_emoji = "✅" if health_percentage == 100 else "⚠️" if health_percentage >= 80 else "❌"

        issues_text = "\n".join([f"  • {issue}" for issue in issues]) if issues else "  None"

        message = f"""
*{health_emoji} System Health Check*

*Services:* {services_healthy}/{total_services} healthy ({health_percentage:.0f}%)
*AI Status:* {ai_status}

*Issues:*
{issues_text}

{f"System operational ✅" if not issues else "Investigating... 🔍"}
"""
        await self.send(message, NotificationType.SYSTEM)

    async def notify_deployment_complete(
        self,
        build_id: str,
        services_updated: List[str],
        new_features: List[str]
    ):
        """Notify deployment completion"""

        services_text = "\n".join([f"  ✓ {service}" for service in services_updated])
        features_text = "\n".join([f"  🆕 {feature}" for feature in new_features])

        message = f"""
*🚀 Deployment Complete*

*Build ID:* `{build_id[:12]}...`
*Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}

*Services Updated:*
{services_text}

*New Features:*
{features_text}

System ready! 🎯
"""
        await self.send(message, NotificationType.SYSTEM)

    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def send_deployment_notification(
    bot_token: str,
    chat_id: str,
    build_id: str,
    services: List[str],
    features: List[str]
):
    """Quick helper to send deployment notification"""
    notifier = TelegramEnhanced(bot_token, chat_id)
    await notifier.notify_deployment_complete(build_id, services, features)
    await notifier.close()


async def send_health_check(
    bot_token: str,
    chat_id: str,
    services_healthy: int,
    total_services: int,
    ai_status: str = "Operational",
    issues: Optional[List[str]] = None
):
    """Quick helper to send health check notification"""
    notifier = TelegramEnhanced(bot_token, chat_id)
    await notifier.notify_system_health(
        services_healthy,
        total_services,
        ai_status,
        issues or []
    )
    await notifier.close()
