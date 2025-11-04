"""Telegram notification service for trading alerts."""

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

from .circuit_breaker import AsyncCircuitBreaker, CircuitBreakerError
from .metrics import CIRCUIT_BREAKER_STATE, CIRCUIT_BREAKER_FAILURES

logger = logging.getLogger(__name__)

# Circuit breaker state mapping
_STATE_MAP = {"closed": 0, "open": 1, "half_open": 2}


def _update_circuit_breaker_metrics(breaker: AsyncCircuitBreaker, service_name: str) -> None:
    """Update Prometheus metrics for circuit breaker state."""
    state_name = breaker.current_state
    state_value = _STATE_MAP.get(state_name, 0)
    CIRCUIT_BREAKER_STATE.labels(service=service_name).set(state_value)


# Circuit breaker for Telegram API calls
# Fails open after 5 failures, resets after 60 seconds
_telegram_circuit_breaker = AsyncCircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="TelegramAPI",
)


class TelegramService:
    """Service for sending formatted trade notifications via Telegram."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self.client = httpx.AsyncClient(timeout=30.0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send a message to the configured Telegram chat.

        Args:
            message: The message content
            parse_mode: Message formatting (HTML, Markdown, etc.)

        Returns:
            bool: True if message sent successfully
        """
        async def _execute_send():
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }

            response = await self.client.post(url, json=payload)
            response.raise_for_status()

            result = response.json()
            if result.get("ok"):
                logger.info(f"✅ Telegram message sent successfully")
                return True
            else:
                error_msg = result.get('description', 'Unknown error')
                logger.error(f"❌ Telegram API error: {error_msg}")
                raise RuntimeError(f"Telegram API error: {error_msg}")

        try:
            # Update metrics before checking state
            _update_circuit_breaker_metrics(_telegram_circuit_breaker, "telegram")

            # Check circuit breaker state
            if _telegram_circuit_breaker.current_state == "open":
                logger.warning("Telegram API circuit breaker is OPEN, failing fast")
                return False

            # Call through circuit breaker
            result = await _telegram_circuit_breaker.call(_execute_send)
            # Update metrics after call
            _update_circuit_breaker_metrics(_telegram_circuit_breaker, "telegram")
            return result
        except CircuitBreakerError as e:
            logger.error(f"Telegram circuit breaker error: {e}")
            _update_circuit_breaker_metrics(_telegram_circuit_breaker, "telegram")
            CIRCUIT_BREAKER_FAILURES.labels(service="telegram").inc()
            return False
        except Exception as exc:
            logger.error(f"❌ Failed to send Telegram message: {exc}")
            _update_circuit_breaker_metrics(_telegram_circuit_breaker, "telegram")
            CIRCUIT_BREAKER_FAILURES.labels(service="telegram").inc()
            return False

    async def send_trade_notification(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        notional: float,
        decision_reason: str,
        model_used: str = "unknown",
        confidence: float = 0.0,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None,
        portfolio_balance: Optional[float] = None,
        risk_percentage: Optional[float] = None,
    ) -> bool:
        """Send a detailed trade notification.

        Args:
            symbol: Trading pair (e.g., "BTCUSDT")
            side: "BUY" or "SELL"
            price: Entry price
            quantity: Quantity traded
            notional: Notional value
            decision_reason: Why this trade was made
            model_used: AI model that made the decision
            confidence: Confidence score (0-1)
            take_profit: Take profit price
            stop_loss: Stop loss price
            portfolio_balance: Current portfolio balance
            risk_percentage: Risk as % of portfolio

        Returns:
            bool: True if notification sent successfully
        """
        try:
            # Format side with emoji
            side_emoji = "🟢" if side.upper() == "BUY" else "🔴"
            side_text = f"{side_emoji} <b>{side.upper()}</b>"

            # Format numbers
            price_fmt = f"${price:,.4f}"
            quantity_fmt = f"{quantity:,.6f}"
            notional_fmt = f"${notional:,.2f}"
            confidence_pct = f"{confidence:.1%}" if confidence > 0 else "N/A"

            # Build message
            message = f"""
🚀 <b>TRADE EXECUTED</b> 🚀

<b>Symbol:</b> {symbol}
<b>Action:</b> {side_text}
<b>Entry Price:</b> {price_fmt}
<b>Quantity:</b> {quantity_fmt}
<b>Notional Value:</b> {notional_fmt}

📊 <b>Trade Details</b>
<b>Model:</b> {model_used}
<b>Confidence:</b> {confidence_pct}
"""

            if portfolio_balance:
                balance_fmt = f"${portfolio_balance:,.2f}"
                message += f"<b>Portfolio Balance:</b> {balance_fmt}\n"

            if risk_percentage:
                risk_fmt = f"{risk_percentage:.2f}%"
                message += f"<b>Risk Exposure:</b> {risk_fmt}\n"

            if take_profit:
                tp_fmt = f"${take_profit:,.4f}"
                message += f"<b>Take Profit:</b> {tp_fmt}\n"

            if stop_loss:
                sl_fmt = f"${stop_loss:,.4f}"
                message += f"<b>Stop Loss:</b> {sl_fmt}\n"

            # Add decision reasoning
            if decision_reason:
                message += f"\n🧠 <b>Decision Logic</b>\n{decision_reason}"

            # Add timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
            message += f"\n\n⏰ <i>Executed at: {timestamp}</i>"

            return await self.send_message(message.strip())

        except Exception as exc:
            logger.error(f"❌ Failed to format trade notification: {exc}")
            return False

    async def send_portfolio_update(
        self,
        balance: float,
        total_exposure: float,
        positions_count: int,
        pnl_24h: Optional[float] = None,
        win_rate: Optional[float] = None,
    ) -> bool:
        """Send a portfolio status update.

        Args:
            balance: Current portfolio balance
            total_exposure: Total exposure across positions
            positions_count: Number of active positions
            pnl_24h: 24h P&L if available
            win_rate: Win rate if available

        Returns:
            bool: True if notification sent successfully
        """
        try:
            balance_fmt = f"${balance:,.2f}"
            exposure_fmt = f"${total_exposure:,.2f}"

            message = f"""
📊 <b>PORTFOLIO UPDATE</b>

<b>Balance:</b> {balance_fmt}
<b>Total Exposure:</b> {exposure_fmt}
<b>Active Positions:</b> {positions_count}
"""

            if pnl_24h is not None:
                pnl_emoji = "📈" if pnl_24h >= 0 else "📉"
                pnl_fmt = f"${pnl_24h:+,.2f}"
                message += f"<b>24h P&L:</b> {pnl_emoji} {pnl_fmt}\n"

            if win_rate is not None:
                win_fmt = f"{win_rate:.1%}"
                message += f"<b>Win Rate:</b> {win_fmt}\n"

            # Add timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
            message += f"\n⏰ <i>Updated at: {timestamp}</i>"

            return await self.send_message(message.strip())

        except Exception as exc:
            logger.error(f"❌ Failed to format portfolio update: {exc}")
            return False

    async def send_alert(
        self,
        alert_type: str,
        message: str,
        severity: str = "info"
    ) -> bool:
        """Send an alert notification.

        Args:
            alert_type: Type of alert (e.g., "ERROR", "WARNING", "INFO")
            message: Alert message
            severity: Alert severity level

        Returns:
            bool: True if notification sent successfully
        """
        try:
            # Format severity with emoji
            severity_emoji = {
                "error": "🚨",
                "warning": "⚠️",
                "success": "✅",
                "info": "ℹ️"
            }.get(severity.lower(), "📢")

            formatted_message = f"""
{severity_emoji} <b>{alert_type.upper()} ALERT</b>

{message}
"""

            # Add timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
            formatted_message += f"\n⏰ <i>{timestamp}</i>"

            return await self.send_message(formatted_message.strip())

        except Exception as exc:
            logger.error(f"❌ Failed to send alert: {exc}")
            return False

    async def send_mcp_notification(
        self,
        session_id: str,
        sender_id: str,
        message_type: str,
        content: str,
        context: Optional[str] = None
    ) -> bool:
        """Send MCP (Multi-Agent Collaboration Protocol) notifications.

        Args:
            session_id: MCP session identifier
            sender_id: Agent that sent the message
            message_type: Type of MCP message (proposal, critique, consensus, etc.)
            content: Message content
            context: Additional context information

        Returns:
            bool: True if notification sent successfully
        """
        try:
            # Format message type with emoji
            type_emoji = {
                "proposal": "💡",
                "critique": "🔍",
                "consensus": "🤝",
                "query": "❓",
                "response": "💬",
                "execution": "⚡",
                "observation": "👁️",
                "heartbeat": "💓"
            }.get(message_type.lower(), "🤖")

            formatted_message = f"""
{type_emoji} <b>MCP {message_type.upper()}</b> {type_emoji}

<b>Agent:</b> {sender_id}
<b>Session:</b> {session_id[:8]}...

{content}
"""

            if context:
                formatted_message += f"\n📋 <b>Context:</b> {context}"

            # Add timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
            formatted_message += f"\n⏰ <i>{timestamp}</i>"

            return await self.send_message(formatted_message.strip())

        except Exception as exc:
            logger.error(f"❌ Failed to send MCP notification: {exc}")
            return False

    async def send_agent_status_update(
        self,
        agent_id: str,
        status: str,
        model: str,
        active_positions: int,
        total_pnl: float,
        win_rate: Optional[float] = None,
        last_trade_time: Optional[str] = None
    ) -> bool:
        """Send agent status update notifications.

        Args:
            agent_id: Agent identifier
            status: Current status (active, idle, error, etc.)
            model: AI model being used
            active_positions: Number of active positions
            total_pnl: Total profit/loss
            win_rate: Win rate percentage
            last_trade_time: When the last trade occurred

        Returns:
            bool: True if notification sent successfully
        """
        try:
            # Format status with emoji
            status_emoji = {
                "active": "🟢",
                "idle": "⚪",
                "monitoring": "🟡",
                "error": "🔴",
                "stopped": "⚫"
            }.get(status.lower(), "⚪")

            pnl_emoji = "📈" if total_pnl >= 0 else "📉"
            pnl_fmt = f"${total_pnl:+,.2f}"

            formatted_message = f"""
{status_emoji} <b>AGENT STATUS UPDATE</b>

<b>Agent:</b> {agent_id}
<b>Model:</b> {model}
<b>Status:</b> {status.upper()}
<b>Active Positions:</b> {active_positions}
<b>Total P&L:</b> {pnl_emoji} {pnl_fmt}
"""

            if win_rate is not None:
                formatted_message += f"<b>Win Rate:</b> {win_rate:.1%}\n"

            if last_trade_time:
                formatted_message += f"<b>Last Trade:</b> {last_trade_time}\n"

            # Add timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
            formatted_message += f"\n⏰ <i>Updated at: {timestamp}</i>"

            return await self.send_message(formatted_message.strip())

        except Exception as exc:
            logger.error(f"❌ Failed to send agent status update: {exc}")
            return False

    async def send_system_status_report(
        self,
        uptime_seconds: int,
        total_trades: int,
        active_agents: int,
        total_portfolio_value: float,
        daily_pnl: Optional[float] = None,
        system_health: str = "healthy"
    ) -> bool:
        """Send comprehensive system status report.

        Args:
            uptime_seconds: System uptime in seconds
            total_trades: Total number of trades executed
            active_agents: Number of active AI agents
            total_portfolio_value: Current portfolio value
            daily_pnl: Daily profit/loss
            system_health: Overall system health status

        Returns:
            bool: True if notification sent successfully
        """
        try:
            # Format uptime
            hours = uptime_seconds // 3600
            minutes = (uptime_seconds % 3600) // 60
            uptime_fmt = f"{hours}h {minutes}m"

            # Format portfolio value
            portfolio_fmt = f"${total_portfolio_value:,.2f}"

            # Format daily P&L
            if daily_pnl is not None:
                pnl_emoji = "📈" if daily_pnl >= 0 else "📉"
                daily_pnl_fmt = f"${daily_pnl:+,.2f}"
            else:
                pnl_emoji = "🤷"
                daily_pnl_fmt = "N/A"

            # Format system health
            health_emoji = {
                "healthy": "🟢",
                "warning": "🟡",
                "critical": "🔴",
                "offline": "⚫"
            }.get(system_health.lower(), "⚪")

            formatted_message = f"""
{health_emoji} <b>SYSTEM STATUS REPORT</b> {health_emoji}

<b>Uptime:</b> {uptime_fmt}
<b>Total Trades:</b> {total_trades:,}
<b>Active Agents:</b> {active_agents}
<b>Portfolio Value:</b> {portfolio_fmt}
<b>Daily P&L:</b> {pnl_emoji} {daily_pnl_fmt}
<b>System Health:</b> {system_health.upper()}
"""

            # Add performance metrics
            if total_trades > 0:
                avg_trade_size = total_portfolio_value / max(total_trades, 1)
                formatted_message += f"<b>Avg Trade Size:</b> ${avg_trade_size:.2f}\n"

            # Add timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
            formatted_message += f"\n⏰ <i>Report generated at: {timestamp}</i>"

            return await self.send_message(formatted_message.strip())

        except Exception as exc:
            logger.error(f"❌ Failed to send system status report: {exc}")
            return False

    async def send_market_alert(
        self,
        symbol: str,
        alert_type: str,
        message: str,
        current_price: Optional[float] = None,
        price_change_24h: Optional[float] = None,
        volume_24h: Optional[float] = None
    ) -> bool:
        """Send market-related alerts and opportunities.

        Args:
            symbol: Trading pair symbol
            alert_type: Type of market alert (breakout, dip, high_volume, etc.)
            message: Alert description
            current_price: Current market price
            price_change_24h: 24h price change percentage
            volume_24h: 24h trading volume

        Returns:
            bool: True if notification sent successfully
        """
        try:
            # Format alert type with emoji
            alert_emoji = {
                "breakout": "🚀",
                "dip": "📉",
                "high_volume": "📊",
                "volatility": "⚡",
                "opportunity": "💎",
                "warning": "⚠️"
            }.get(alert_type.lower(), "📢")

            formatted_message = f"""
{alert_emoji} <b>MARKET ALERT: {alert_type.upper()}</b>

<b>Symbol:</b> {symbol}

{message}
"""

            if current_price is not None:
                formatted_message += f"<b>Current Price:</b> ${current_price:,.4f}\n"

            if price_change_24h is not None:
                change_emoji = "📈" if price_change_24h >= 0 else "📉"
                change_fmt = f"{price_change_24h:+.2f}%"
                formatted_message += f"<b>24h Change:</b> {change_emoji} {change_fmt}\n"

            if volume_24h is not None:
                volume_fmt = f"${volume_24h:,.0f}"
                formatted_message += f"<b>24h Volume:</b> {volume_fmt}\n"

            # Add timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
            formatted_message += f"\n⏰ <i>Alert at: {timestamp}</i>"

            return await self.send_message(formatted_message.strip())

        except Exception as exc:
            logger.error(f"❌ Failed to send market alert: {exc}")
            return False

    async def send_risk_alert(
        self,
        risk_type: str,
        severity: str,
        message: str,
        current_exposure: Optional[float] = None,
        max_exposure: Optional[float] = None,
        portfolio_value: Optional[float] = None,
        recommendations: Optional[list] = None
    ) -> bool:
        """Send risk management alerts.

        Args:
            risk_type: Type of risk (exposure, drawdown, concentration, etc.)
            severity: Risk severity (low, medium, high, critical)
            message: Risk description
            current_exposure: Current exposure amount
            max_exposure: Maximum allowed exposure
            portfolio_value: Current portfolio value
            recommendations: List of risk mitigation recommendations

        Returns:
            bool: True if notification sent successfully
        """
        try:
            # Format severity with emoji and color
            severity_config = {
                "low": {"emoji": "🟢", "level": "LOW"},
                "medium": {"emoji": "🟡", "level": "MEDIUM"},
                "high": {"emoji": "🟠", "level": "HIGH"},
                "critical": {"emoji": "🔴", "level": "CRITICAL"}
            }.get(severity.lower(), {"emoji": "⚪", "level": severity.upper()})

            formatted_message = f"""
{severity_config['emoji']} <b>RISK ALERT: {risk_type.upper()}</b>

<b>Severity:</b> {severity_config['level']}

{message}
"""

            if current_exposure is not None and max_exposure is not None:
                exposure_pct = (current_exposure / max_exposure) * 100
                formatted_message += f"<b>Current Exposure:</b> ${current_exposure:,.2f} ({exposure_pct:.1f}% of limit)\n"
                formatted_message += f"<b>Max Exposure:</b> ${max_exposure:,.2f}\n"

            if portfolio_value is not None:
                formatted_message += f"<b>Portfolio Value:</b> ${portfolio_value:,.2f}\n"

            if recommendations:
                formatted_message += "\n<b>Recommendations:</b>\n"
                for rec in recommendations[:3]:  # Limit to 3 recommendations
                    formatted_message += f"• {rec}\n"

            # Add timestamp
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
            formatted_message += f"\n⏰ <i>Risk alert at: {timestamp}</i>"

            return await self.send_message(formatted_message.strip())

        except Exception as exc:
            logger.error(f"❌ Failed to send risk alert: {exc}")
            return False


async def create_telegram_service(settings) -> Optional[TelegramService]:
    """Create a Telegram service if credentials are configured.

    Args:
        settings: Application settings object

    Returns:
        TelegramService instance or None if not configured
    """
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.info("Telegram notifications not configured - skipping")
        return None

    try:
        service = TelegramService(settings.telegram_bot_token, settings.telegram_chat_id)

        # Test the connection with a simple message
        test_message = "🤖 <b>Sapphire AI Trading Bot</b>\n\n✅ Bot initialized and ready for trade notifications!"
        success = await service.send_message(test_message)

        if success:
            logger.info("✅ Telegram service initialized successfully")
            return service
        else:
            logger.error("❌ Failed to send test message to Telegram")
            return None

    except Exception as exc:
        logger.error(f"❌ Failed to initialize Telegram service: {exc}")
        return None
