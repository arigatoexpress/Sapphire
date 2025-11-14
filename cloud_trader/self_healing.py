"""
Self-healing mechanisms for automatic system recovery.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable, Awaitable
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class HealthCheck:
    """Represents a health check for a system component."""
    name: str
    check_func: Callable[[], Awaitable[bool]]
    interval: float = 30.0  # seconds
    timeout: float = 10.0  # seconds
    max_failures: int = 3
    recovery_func: Optional[Callable[[], Awaitable[bool]]] = None

    # Runtime state
    failures: int = 0
    last_check: Optional[float] = None
    last_failure: Optional[float] = None
    last_success: Optional[float] = None
    healthy: bool = True

@dataclass
class SelfHealingConfig:
    """Configuration for self-healing behavior."""
    health_check_interval: float = 30.0
    recovery_cooldown: float = 300.0  # 5 minutes between recovery attempts
    max_recovery_attempts: int = 5
    enable_auto_recovery: bool = True
    alert_on_failures: bool = True

class SelfHealingManager:
    """Manages self-healing operations for the trading system."""

    def __init__(self, config: Optional[SelfHealingConfig] = None):
        self.config = config or SelfHealingConfig()
        self.health_checks: Dict[str, HealthCheck] = {}
        self.recovery_history: List[Dict[str, Any]] = []
        self.monitoring_active = False
        self._monitoring_task: Optional[asyncio.Task] = None

    def register_health_check(self, check: HealthCheck):
        """Register a health check."""
        self.health_checks[check.name] = check
        logger.info(f"Registered health check: {check.name}")

    async def perform_health_check(self, check: HealthCheck) -> bool:
        """Perform a single health check."""
        try:
            # Run the health check with timeout
            result = await asyncio.wait_for(check.check_func(), timeout=check.timeout)
            check.last_check = time.time()

            if result:
                check.healthy = True
                check.failures = 0
                check.last_success = time.time()
                return True
            else:
                check.healthy = False
                check.failures += 1
                check.last_failure = time.time()
                return False

        except asyncio.TimeoutError:
            logger.warning(f"Health check {check.name} timed out")
            check.healthy = False
            check.failures += 1
            check.last_failure = time.time()
            return False
        except Exception as e:
            logger.error(f"Health check {check.name} failed with exception: {e}")
            check.healthy = False
            check.failures += 1
            check.last_failure = time.time()
            return False

    async def attempt_recovery(self, check: HealthCheck) -> bool:
        """Attempt to recover a failed component."""
        if not check.recovery_func:
            logger.warning(f"No recovery function for {check.name}")
            return False

        # Check cooldown period
        if check.last_failure and time.time() - check.last_failure < self.config.recovery_cooldown:
            logger.debug(f"Recovery for {check.name} still in cooldown")
            return False

        logger.info(f"Attempting recovery for {check.name}")

        try:
            success = await asyncio.wait_for(check.recovery_func(), timeout=60.0)

            # Record recovery attempt
            self.recovery_history.append({
                'timestamp': datetime.now(),
                'component': check.name,
                'success': success,
                'failures_before_recovery': check.failures
            })

            if success:
                logger.info(f"Successfully recovered {check.name}")
                check.failures = 0
                check.healthy = True
                return True
            else:
                logger.warning(f"Recovery failed for {check.name}")
                return False

        except Exception as e:
            logger.error(f"Recovery attempt failed for {check.name}: {e}")
            return False

    async def check_and_recover(self, check: HealthCheck):
        """Check health and attempt recovery if needed."""
        healthy = await self.perform_health_check(check)

        if not healthy:
            logger.warning(f"Health check failed for {check.name} (failures: {check.failures}/{check.max_failures})")

            # Check if we should attempt recovery
            if (self.config.enable_auto_recovery and
                check.failures >= check.max_failures and
                check.recovery_func):

                success = await self.attempt_recovery(check)
                if success:
                    # Reset failure count on successful recovery
                    check.failures = 0

            # Alert if configured
            if self.config.alert_on_failures and check.failures >= check.max_failures:
                await self._send_health_alert(check)

    async def _send_health_alert(self, check: HealthCheck):
        """Send alert for persistent health check failures."""
        try:
            # Import here to avoid circular imports
            from .enhanced_telegram import NotificationPriority

            alert_message = (
                f"🚨 HEALTH ALERT: {check.name}\n"
                f"Status: FAILING\n"
                f"Failures: {check.failures}\n"
                f"Last Success: {datetime.fromtimestamp(check.last_success) if check.last_success else 'Never'}\n"
                f"Last Failure: {datetime.fromtimestamp(check.last_failure) if check.last_failure else 'Never'}"
            )

            # Try to send telegram alert (will fail gracefully if not configured)
            try:
                from .enhanced_telegram import create_enhanced_telegram_service
                telegram = await create_enhanced_telegram_service(None)  # Will use environment config
                if telegram:
                    await telegram.send_message(alert_message, priority=NotificationPriority.CRITICAL)
            except Exception:
                pass  # Telegram not configured or failed

        except Exception as e:
            logger.error(f"Failed to send health alert: {e}")

    async def health_monitoring_loop(self):
        """Main health monitoring loop."""
        logger.info("Starting self-healing health monitoring")

        while self.monitoring_active:
            try:
                # Run all health checks concurrently
                tasks = [
                    self.check_and_recover(check)
                    for check in self.health_checks.values()
                ]

                await asyncio.gather(*tasks, return_exceptions=True)

                # Wait for next check cycle
                await asyncio.sleep(self.config.health_check_interval)

            except Exception as e:
                logger.error(f"Error in health monitoring loop: {e}")
                await asyncio.sleep(5)  # Brief pause before retrying

    def start_monitoring(self):
        """Start the health monitoring system."""
        if self.monitoring_active:
            logger.warning("Health monitoring already active")
            return

        self.monitoring_active = True
        try:
            # Try to get running event loop
            loop = asyncio.get_running_loop()
            self._monitoring_task = asyncio.create_task(self.health_monitoring_loop())
            logger.info("Self-healing health monitoring started")
        except RuntimeError:
            # No event loop running, schedule for later
            logger.warning("No event loop available, self-healing monitoring will start when loop is available")
            self.monitoring_active = False

    def stop_monitoring(self):
        """Stop the health monitoring system."""
        self.monitoring_active = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
        logger.info("Self-healing health monitoring stopped")

    async def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status of all components."""
        status = {
            'timestamp': datetime.now(),
            'overall_healthy': all(check.healthy for check in self.health_checks.values()),
            'components': {},
            'recovery_history': self.recovery_history[-10:]  # Last 10 recovery attempts
        }

        for name, check in self.health_checks.items():
            status['components'][name] = {
                'healthy': check.healthy,
                'failures': check.failures,
                'last_check': datetime.fromtimestamp(check.last_check) if check.last_check else None,
                'last_success': datetime.fromtimestamp(check.last_success) if check.last_success else None,
                'last_failure': datetime.fromtimestamp(check.last_failure) if check.last_failure else None,
            }

        return status

# Global self-healing manager instance
_healing_manager: Optional[SelfHealingManager] = None

def get_self_healing_manager() -> SelfHealingManager:
    """Get the global self-healing manager instance."""
    global _healing_manager
    if _healing_manager is None:
        _healing_manager = SelfHealingManager()
    return _healing_manager

# Convenience functions for common recovery operations
async def recover_database_connection() -> bool:
    """Attempt to recover database connection."""
    try:
        # Import here to avoid circular imports
        from . import get_storage, close_storage

        # Close existing connection
        await close_storage()

        # Try to create new connection
        storage = await get_storage()
        if storage:
            logger.info("Database connection recovered")
            return True
        else:
            logger.error("Failed to create new database connection")
            return False

    except Exception as e:
        logger.error(f"Database recovery failed: {e}")
        return False

async def recover_redis_connection() -> bool:
    """Attempt to recover Redis connection."""
    try:
        # Import here to avoid circular imports
        from . import get_cache, close_cache

        # Close existing connection
        await close_cache()

        # Try to create new connection
        cache = await get_cache()
        if cache:
            logger.info("Redis connection recovered")
            return True
        else:
            logger.error("Failed to create new Redis connection")
            return False

    except Exception as e:
        logger.error(f"Redis recovery failed: {e}")
        return False

async def recover_vertex_ai_connection() -> bool:
    """Attempt to recover Vertex AI connection."""
    try:
        # Import here to avoid circular imports
        from .vertex_ai_client import get_vertex_client

        # Try to create new client
        client = await get_vertex_client()
        if client:
            logger.info("Vertex AI connection recovered")
            return True
        else:
            logger.error("Failed to create new Vertex AI client")
            return False

    except Exception as e:
        logger.error(f"Vertex AI recovery failed: {e}")
        return False
