"""
Safety Switch & Health Monitoring
"Dead Man's Switch" logic to ensure system integrity.
"""

import logging
import time
from typing import Awaitable, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class SafetySwitch:
    """
    Monitors system health and triggers emergency actions if checks fail.
    """

    def __init__(
        self,
        max_heartbeat_delay: float = 30.0,
        emergency_callback: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        """
        Args:
            max_heartbeat_delay: Max seconds between heartbeats before triggering safety
            emergency_callback: Async function to call when safety triggers (e.g. close positions)
        """
        self.max_heartbeat_delay = max_heartbeat_delay
        self.emergency_callback = emergency_callback

        self._heartbeats: Dict[str, float] = {}
        self._triggered = False

    def heartbeat(self, service_name: str):
        """Register a heartbeat from a critical service."""
        self._heartbeats[service_name] = time.time()
        # If we recovered, maybe untrigger? For now, manual reset might be safer.

    def check_health(self) -> bool:
        """
        Check if all registered services are healthy.
        Returns False if any service has timed out.
        """
        now = time.time()
        for service, last_beat in self._heartbeats.items():
            if now - last_beat > self.max_heartbeat_delay:
                logger.critical(
                    f"🚨 HEALTH CHECK FAILED: {service} last heartbeat {now - last_beat:.1f}s ago"
                )
                return False
        return True

    async def monitor(self):
        """
        Run monitoring loop (call this periodically).
        """
        if self._triggered:
            return

        if not self.check_health():
            logger.critical("🚨 SAFETY SWITCH TRIGGERED! INITIATING EMERGENCY PROCEDURES")
            self._triggered = True
            if self.emergency_callback:
                try:
                    await self.emergency_callback()
                    logger.info("✅ Emergency callback executed successfully")
                except Exception as e:
                    logger.error(f"❌ Failed to execute emergency callback: {e}")

    def reset(self):
        """Reset the safety switch (use with caution)."""
        self._triggered = False
        self._heartbeats.clear()
        logger.info("Safety switch reset")


# Global instance
_safety_switch: Optional[SafetySwitch] = None


def get_safety_switch() -> SafetySwitch:
    global _safety_switch
    if _safety_switch is None:
        _safety_switch = SafetySwitch()
    return _safety_switch
