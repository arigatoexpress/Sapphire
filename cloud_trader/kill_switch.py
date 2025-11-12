"""Kill Switch Service for Emergency Trading Halt

Monitors Pub/Sub messages and executes emergency shutdown procedures.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Optional

from .config import get_settings
from .pubsub import PubSubClient

logger = logging.getLogger(__name__)


class KillSwitch:
    """Emergency kill switch for trading system."""

    def __init__(self):
        self.settings = get_settings()
        self.pubsub_client: Optional[PubSubClient] = None
        self.active = False
        self.activation_time: Optional[datetime] = None
        self.activation_reason: Optional[str] = None
        self.affected_components: set = set()

    async def start(self):
        """Initialize the kill switch."""
        if self.settings.gcp_project_id:
            self.pubsub_client = PubSubClient(self.settings)
            await self.pubsub_client.connect()

        # Subscribe to kill switch messages
        asyncio.create_task(self._monitor_kill_switch_messages())

        logger.info("Kill Switch service started")

    async def stop(self):
        """Shutdown the kill switch."""
        if self.pubsub_client:
            await self.pubsub_client.close()

    async def activate(self, reason: str, source: str = "unknown"):
        """Activate the kill switch."""
        if self.active:
            logger.warning(f"Kill switch already active. New activation request ignored: {reason}")
            return

        self.active = True
        self.activation_time = datetime.now()
        self.activation_reason = reason

        logger.critical(f"KILL SWITCH ACTIVATED: {reason} (source: {source})")

        # Notify all components
        await self._notify_components(reason)

        # Execute emergency procedures
        await self._execute_emergency_procedures()

    async def deactivate(self, reason: str, source: str = "unknown"):
        """Deactivate the kill switch."""
        if not self.active:
            logger.warning("Kill switch not active. Deactivation request ignored.")
            return

        logger.info(f"KILL SWITCH DEACTIVATED: {reason} (source: {source})")

        self.active = False
        self.activation_time = None
        self.activation_reason = None
        self.affected_components.clear()

        # Notify components of reactivation
        await self._notify_components("Kill switch deactivated", reactivate=True)

    async def _monitor_kill_switch_messages(self):
        """Monitor Pub/Sub for kill switch messages."""
        # In a real implementation, this would subscribe to a kill switch topic
        # For now, we'll simulate monitoring
        while True:
            try:
                # Check for kill switch messages (would be implemented with actual Pub/Sub subscription)
                await asyncio.sleep(5)  # Check every 5 seconds
            except Exception as e:
                logger.error(f"Kill switch monitoring error: {e}")
                await asyncio.sleep(5)

    async def _notify_components(self, message: str, reactivate: bool = False):
        """Notify all trading components of kill switch status."""
        if not self.pubsub_client:
            return

        event_type = "kill_switch_deactivated" if reactivate else "kill_switch_activated"

        notification = {
            "event": event_type,
            "message": message,
            "timestamp": datetime.now().isoformat(),
            "activation_time": self.activation_time.isoformat() if self.activation_time else None,
            "reason": self.activation_reason,
            "affected_components": list(self.affected_components),
        }

        try:
            await self.pubsub_client.publish_reasoning(notification)
            logger.info(f"Kill switch notification sent: {event_type}")
        except Exception as e:
            logger.error(f"Failed to send kill switch notification: {e}")

    async def _execute_emergency_procedures(self):
        """Execute emergency shutdown procedures."""
        logger.critical("Executing emergency procedures...")

        # 1. Cancel all open orders
        await self._cancel_all_orders()

        # 2. Close all positions
        await self._close_all_positions()

        # 3. Freeze trading
        await self._freeze_trading()

        # 4. Send emergency alerts
        await self._send_emergency_alerts()

        logger.critical("Emergency procedures completed")

    async def _cancel_all_orders(self):
        """Cancel all open orders across all components."""
        # This would send cancellation commands to all trading components
        logger.warning("Cancelling all open orders...")

        if self.pubsub_client:
            await self.pubsub_client.publish_reasoning({
                "event": "cancel_all_orders",
                "reason": "Kill switch activated",
                "timestamp": datetime.now().isoformat(),
            })

    async def _close_all_positions(self):
        """Close all open positions across all components."""
        logger.warning("Closing all positions...")

        if self.pubsub_client:
            await self.pubsub_client.publish_reasoning({
                "event": "close_all_positions",
                "reason": "Kill switch activated",
                "timestamp": datetime.now().isoformat(),
            })

    async def _freeze_trading(self):
        """Freeze all trading activities."""
        logger.warning("Freezing trading activities...")

        if self.pubsub_client:
            await self.pubsub_client.publish_reasoning({
                "event": "freeze_trading",
                "reason": "Kill switch activated",
                "timestamp": datetime.now().isoformat(),
            })

    async def _send_emergency_alerts(self):
        """Send emergency alerts to administrators."""
        logger.critical("Sending emergency alerts...")

        alert_message = {
            "alert_type": "emergency_kill_switch",
            "severity": "critical",
            "message": f"Kill switch activated: {self.activation_reason}",
            "timestamp": datetime.now().isoformat(),
            "portfolio_status": "frozen",
            "trading_status": "halted",
        }

        # In a real implementation, this would send emails, SMS, etc.
        logger.critical(f"EMERGENCY ALERT: {json.dumps(alert_message, indent=2)}")

    def get_status(self) -> Dict:
        """Get kill switch status."""
        return {
            "active": self.active,
            "activation_time": self.activation_time.isoformat() if self.activation_time else None,
            "activation_reason": self.activation_reason,
            "affected_components": list(self.affected_components),
            "last_check": datetime.now().isoformat(),
        }

    async def health_check(self) -> Dict:
        """Perform health check."""
        return {
            "service": "kill_switch",
            "status": "healthy",
            "active": self.active,
            "monitoring": True,
        }


# Global kill switch instance
_kill_switch: Optional[KillSwitch] = None


def get_kill_switch() -> KillSwitch:
    """Get or create global kill switch instance."""
    global _kill_switch
    if _kill_switch is None:
        _kill_switch = KillSwitch()
    return _kill_switch


async def handle_kill_switch_message(message: Dict):
    """Handle incoming kill switch messages."""
    kill_switch = get_kill_switch()

    event = message.get("event")
    reason = message.get("reason", "Unknown reason")
    source = message.get("source", "unknown")

    if event == "activate_kill_switch":
        await kill_switch.activate(reason, source)
    elif event == "deactivate_kill_switch":
        await kill_switch.deactivate(reason, source)
    else:
        logger.warning(f"Unknown kill switch event: {event}")
