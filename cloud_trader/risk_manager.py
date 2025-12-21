"""Risk Management Service for HFT Trading System

Provides real-time risk monitoring, position management, and emergency controls.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

from .config import get_settings
from .logger import get_logger
from .metrics import PORTFOLIO_DRAWDOWN, PORTFOLIO_LEVERAGE, POSITION_SIZE, RISK_LIMITS_BREACHED
from .pubsub import PubSubClient

logger = get_logger(__name__)


class RiskManager:
    """Centralized risk management for the trading system."""

    def __init__(self):
        self.settings = get_settings()
        self.pubsub_client: Optional[PubSubClient] = None

        # Risk state
        self.portfolio_value = 10000.0  # Starting value
        self.peak_portfolio_value = 10000.0
        self.current_drawdown = 0.0
        self.daily_start_value = 10000.0
        self.daily_pnl = 0.0

        # Position tracking
        self.positions: Dict[str, Dict] = {}  # symbol -> position data
        self.total_exposure = 0.0
        self.leverage_ratio = 0.0

        # Risk limits
        self.max_drawdown = 0.15  # 15%
        self.max_daily_loss = 0.05  # 5%
        self.max_position_size_pct = 0.02  # 2%
        self.max_leverage = 10.0

        # Circuit breakers
        self.trading_paused = False
        self.kill_switch_activated = False
        self.last_kill_switch_time = None

        # Alert thresholds
        self.drawdown_warning_threshold = 0.05  # 5%
        self.drawdown_critical_threshold = 0.10  # 10%

        # Monitoring
        self.monitoring_active = True
        self.check_interval = 10  # seconds

    async def start(self):
        """Initialize the risk manager."""
        if self.settings.gcp_project_id:
            self.pubsub_client = PubSubClient(self.settings)
            await self.pubsub_client.connect()

        # Start monitoring loop
        asyncio.create_task(self._monitoring_loop())

        # Subscribe to risk-related messages
        await self._subscribe_to_updates()

        logger.info("Risk Manager started")

    async def stop(self):
        """Shutdown the risk manager."""
        self.monitoring_active = False
        if self.pubsub_client:
            await self.pubsub_client.close()

    async def _subscribe_to_updates(self):
        """Subscribe to position and trade updates."""
        if not self.pubsub_client:
            return

        # In a real implementation, this would set up subscriptions
        # For now, we'll poll via health checks
        pass

    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self.monitoring_active:
            try:
                await self._check_risk_limits()
                await self._update_metrics()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Risk monitoring error: {e}")
                await asyncio.sleep(self.check_interval)

    async def _check_risk_limits(self):
        """Check all risk limits and trigger actions if needed."""
        # Update drawdown
        self.current_drawdown = (
            self.peak_portfolio_value - self.portfolio_value
        ) / self.peak_portfolio_value

        # Check drawdown limits
        if self.current_drawdown > self.drawdown_critical_threshold:
            await self._trigger_emergency_stop("Critical drawdown exceeded")
        elif self.current_drawdown > self.drawdown_warning_threshold:
            await self._send_alert(
                "High drawdown warning", f"Drawdown: {self.current_drawdown:.2%}"
            )

        # Check daily loss limit
        daily_loss_pct = (self.daily_start_value - self.portfolio_value) / self.daily_start_value
        if daily_loss_pct > self.max_daily_loss:
            await self._pause_trading("Daily loss limit exceeded")

        # Check leverage limit
        if self.leverage_ratio > self.max_leverage:
            await self._reduce_leverage("Leverage limit exceeded")

        # Check position sizes
        for symbol, position in self.positions.items():
            position_value = abs(position.get("notional", 0))
            position_pct = position_value / self.portfolio_value

            if position_pct > self.max_position_size_pct:
                await self._reduce_position(symbol, "Position size limit exceeded")

    async def _trigger_emergency_stop(self, reason: str):
        """Trigger emergency stop of all trading."""
        if self.kill_switch_activated:
            return  # Already activated

        self.kill_switch_activated = True
        self.last_kill_switch_time = datetime.now()

        logger.critical(f"EMERGENCY STOP ACTIVATED: {reason}")

        # Publish kill switch message
        if self.pubsub_client:
            await self.pubsub_client.publish_reasoning(
                {
                    "event": "kill_switch_activated",
                    "reason": reason,
                    "timestamp": datetime.now().isoformat(),
                    "portfolio_value": self.portfolio_value,
                    "drawdown": self.current_drawdown,
                }
            )

        # Send critical alert
        await self._send_alert("EMERGENCY STOP", f"Trading halted: {reason}")

        RISK_LIMITS_BREACHED.labels(limit_type="emergency_stop").inc()

    async def _pause_trading(self, reason: str):
        """Pause trading activities."""
        if self.trading_paused:
            return

        self.trading_paused = True
        logger.warning(f"Trading paused: {reason}")

        if self.pubsub_client:
            await self.pubsub_client.publish_reasoning(
                {
                    "event": "trading_paused",
                    "reason": reason,
                    "timestamp": datetime.now().isoformat(),
                }
            )

        RISK_LIMITS_BREACHED.labels(limit_type="trading_paused").inc()

    async def _reduce_leverage(self, reason: str):
        """Reduce portfolio leverage."""
        logger.warning(f"Reducing leverage: {reason}")

        if self.pubsub_client:
            await self.pubsub_client.publish_reasoning(
                {
                    "event": "leverage_reduction",
                    "reason": reason,
                    "current_leverage": self.leverage_ratio,
                    "target_leverage": self.max_leverage * 0.8,  # Reduce to 80% of max
                    "timestamp": datetime.now().isoformat(),
                }
            )

    async def _reduce_position(self, symbol: str, reason: str):
        """Reduce position size for a symbol."""
        logger.warning(f"Reducing position for {symbol}: {reason}")

        if self.pubsub_client:
            await self.pubsub_client.publish_reasoning(
                {
                    "event": "position_reduction",
                    "symbol": symbol,
                    "reason": reason,
                    "current_size_pct": self.positions[symbol].get("notional", 0)
                    / self.portfolio_value,
                    "target_size_pct": self.max_position_size_pct * 0.8,
                    "timestamp": datetime.now().isoformat(),
                }
            )

    async def _send_alert(self, title: str, message: str):
        """Send risk alert."""
        logger.warning(f"ALERT: {title} - {message}")

        if self.pubsub_client:
            await self.pubsub_client.publish_reasoning(
                {
                    "event": "risk_alert",
                    "title": title,
                    "message": message,
                    "severity": "warning" if "warning" in title.lower() else "critical",
                    "timestamp": datetime.now().isoformat(),
                }
            )

    async def update_portfolio_value(self, new_value: float):
        """Update portfolio value and recalculate risk metrics."""
        old_value = self.portfolio_value
        self.portfolio_value = new_value

        # Update peak value
        if new_value > self.peak_portfolio_value:
            self.peak_portfolio_value = new_value

        # Update daily P&L
        self.daily_pnl = new_value - self.daily_start_value

        # Recalculate exposure and leverage
        await self._recalculate_exposure()

        logger.info(
            f"Portfolio value updated: ${old_value:.2f} → ${new_value:.2f} (P&L: ${self.daily_pnl:.2f})"
        )

    async def update_position(self, symbol: str, position_data: Dict):
        """Update position information."""
        self.positions[symbol] = position_data
        await self._recalculate_exposure()

    async def remove_position(self, symbol: str):
        """Remove a closed position."""
        if symbol in self.positions:
            del self.positions[symbol]
            await self._recalculate_exposure()

    async def _recalculate_exposure(self):
        """Recalculate total exposure and leverage."""
        total_exposure = sum(abs(pos.get("notional", 0)) for pos in self.positions.values())
        self.total_exposure = total_exposure
        self.leverage_ratio = (
            total_exposure / self.portfolio_value if self.portfolio_value > 0 else 0
        )

    def get_risk_status(self) -> Dict:
        """Get current risk status."""
        return {
            "portfolio_value": self.portfolio_value,
            "peak_value": self.peak_portfolio_value,
            "current_drawdown": self.current_drawdown,
            "daily_pnl": self.daily_pnl,
            "leverage_ratio": self.leverage_ratio,
            "total_exposure": self.total_exposure,
            "trading_paused": self.trading_paused,
            "kill_switch_active": self.kill_switch_activated,
            "positions_count": len(self.positions),
            "last_update": datetime.now().isoformat(),
        }

    def reset_daily_values(self):
        """Reset daily tracking values (call at market open)."""
        self.daily_start_value = self.portfolio_value
        self.daily_pnl = 0.0
        logger.info("Daily risk values reset")

    async def _update_metrics(self):
        """Update Prometheus metrics."""
        try:
            PORTFOLIO_DRAWDOWN.set(self.current_drawdown)
            PORTFOLIO_LEVERAGE.set(self.leverage_ratio)

            # Update position sizes
            for symbol, position in self.positions.items():
                POSITION_SIZE.labels(symbol=symbol).set(position.get("notional", 0))

        except Exception as e:
            logger.error(f"Failed to update metrics: {e}")

    async def health_check(self) -> Dict:
        """Perform health check."""
        return {
            "service": "risk_manager",
            "status": "healthy",
            "monitoring_active": self.monitoring_active,
            "kill_switch_active": self.kill_switch_activated,
            "trading_paused": self.trading_paused,
            "current_drawdown": f"{self.current_drawdown:.2%}",
            "leverage_ratio": f"{self.leverage_ratio:.2f}",
        }


# Global risk manager instance
_risk_manager: Optional[RiskManager] = None


def get_risk_manager() -> RiskManager:
    """Get or create global risk manager instance."""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager()
    return _risk_manager
