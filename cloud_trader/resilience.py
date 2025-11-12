"""Resilience and Self-Healing System

Implements circuit breakers, health checks, automatic recovery,
and fault tolerance for high-reliability trading operations.
"""

import asyncio
import time
import threading
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Any, Callable, Optional, Awaitable
from dataclasses import dataclass
from contextlib import asynccontextmanager

from .logging_config import get_trading_logger


class CircuitBreakerState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"         # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5  # Failures before opening
    recovery_timeout: int = 60  # Seconds before trying recovery
    success_threshold: int = 3  # Successes needed to close
    timeout: float = 10.0      # Request timeout


@dataclass
class HealthCheck:
    """Health check configuration."""
    name: str
    check_function: Callable[[], Awaitable[bool]]
    interval: int = 30  # Seconds
    timeout: float = 5.0
    max_failures: int = 3


class CircuitBreaker:
    """Circuit breaker for external service calls."""

    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.logger = get_trading_logger("circuit-breaker")

    async def call(self, func: Callable[[], Awaitable[Any]]) -> Any:
        """Execute function with circuit breaker protection."""
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_recovery():
                self.state = CircuitBreakerState.HALF_OPEN
                self.logger.info(f"Circuit breaker {self.name} entering HALF_OPEN state")
            else:
                raise Exception(f"Circuit breaker {self.name} is OPEN")

        try:
            # Execute with timeout
            result = await asyncio.wait_for(func(), timeout=self.config.timeout)
            self._record_success()
            return result

        except Exception as e:
            self._record_failure()
            raise e

    def _record_success(self):
        """Record successful call."""
        self.failure_count = 0

        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.success_count = 0
                self.logger.info(f"Circuit breaker {self.name} CLOSED after successful recovery")

    def _record_failure(self):
        """Record failed call."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()

        if self.failure_count >= self.config.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            self.logger.warning(f"Circuit breaker {self.name} OPENED after {self.failure_count} failures")

    def _should_attempt_recovery(self) -> bool:
        """Check if we should attempt recovery."""
        if self.last_failure_time is None:
            return True

        elapsed = (datetime.now() - self.last_failure_time).total_seconds()
        return elapsed >= self.config.recovery_timeout

    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
        }


class HealthChecker:
    """Health checker for services and dependencies."""

    def __init__(self):
        self.logger = get_trading_logger("health-checker")
        self.checks: Dict[str, HealthCheck] = {}
        self.results: Dict[str, Dict[str, Any]] = {}
        self._shutdown_event = threading.Event()

        # Start health check monitoring
        self._start_monitoring()

    def add_check(self, check: HealthCheck):
        """Add a health check."""
        self.checks[check.name] = check
        self.logger.info(f"Added health check: {check.name}")

    async def run_check(self, check: HealthCheck) -> Dict[str, Any]:
        """Run a single health check."""
        start_time = time.time()

        try:
            result = await asyncio.wait_for(check.check_function(), timeout=check.timeout)
            duration = time.time() - start_time

            status = {
                "name": check.name,
                "status": "healthy" if result else "unhealthy",
                "duration": duration,
                "timestamp": datetime.now().isoformat(),
                "consecutive_failures": 0
            }

        except Exception as e:
            duration = time.time() - start_time
            consecutive_failures = self.results.get(check.name, {}).get("consecutive_failures", 0) + 1

            status = {
                "name": check.name,
                "status": "unhealthy",
                "error": str(e),
                "duration": duration,
                "timestamp": datetime.now().isoformat(),
                "consecutive_failures": consecutive_failures
            }

            if consecutive_failures >= check.max_failures:
                self.logger.error(f"Health check {check.name} failed {consecutive_failures} times", {
                    "check": check.name,
                    "error": str(e),
                    "consecutive_failures": consecutive_failures
                })

        self.results[check.name] = status
        return status

    async def run_all_checks(self) -> Dict[str, Any]:
        """Run all health checks."""
        tasks = [self.run_check(check) for check in self.checks.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        summary = {
            "timestamp": datetime.now().isoformat(),
            "total_checks": len(self.checks),
            "healthy": 0,
            "unhealthy": 0,
            "results": {}
        }

        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"Health check error: {result}")
                continue

            summary["results"][result["name"]] = result
            if result["status"] == "healthy":
                summary["healthy"] += 1
            else:
                summary["unhealthy"] += 1

        overall_status = "healthy" if summary["unhealthy"] == 0 else "degraded" if summary["healthy"] > 0 else "unhealthy"
        summary["overall_status"] = overall_status

        return summary

    def _start_monitoring(self):
        """Start background health monitoring."""
        def monitor():
            while not self._shutdown_event.is_set():
                try:
                    # Run checks every 30 seconds
                    asyncio.run(self.run_all_checks())
                except Exception as e:
                    self.logger.error(f"Health monitoring error: {e}")

                time.sleep(30)

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()

    def get_status(self) -> Dict[str, Any]:
        """Get current health status."""
        return {
            "checks": list(self.results.values()),
            "summary": self._calculate_summary()
        }

    def _calculate_summary(self) -> Dict[str, Any]:
        """Calculate health summary."""
        total = len(self.results)
        healthy = sum(1 for r in self.results.values() if r["status"] == "healthy")

        return {
            "total": total,
            "healthy": healthy,
            "unhealthy": total - healthy,
            "health_percentage": (healthy / total * 100) if total > 0 else 0
        }


class AutoRecovery:
    """Automatic recovery system for failed services."""

    def __init__(self):
        self.logger = get_trading_logger("auto-recovery")
        self.recovery_actions: Dict[str, Callable[[], Awaitable[None]]] = {}
        self.recovery_intervals: Dict[str, int] = {}
        self.last_recovery_attempts: Dict[str, datetime] = {}
        self._shutdown_event = threading.Event()

        # Start recovery monitoring
        self._start_recovery_monitor()

    def register_recovery_action(self, service_name: str, action: Callable[[], Awaitable[None]], interval_minutes: int = 5):
        """Register a recovery action for a service."""
        self.recovery_actions[service_name] = action
        self.recovery_intervals[service_name] = interval_minutes
        self.logger.info(f"Registered recovery action for {service_name}")

    async def trigger_recovery(self, service_name: str, reason: str):
        """Trigger recovery for a service."""
        if service_name not in self.recovery_actions:
            self.logger.warning(f"No recovery action registered for {service_name}")
            return

        # Check if we've attempted recovery recently
        last_attempt = self.last_recovery_attempts.get(service_name)
        if last_attempt:
            elapsed = (datetime.now() - last_attempt).total_seconds() / 60  # minutes
            if elapsed < self.recovery_intervals[service_name]:
                self.logger.debug(f"Recovery for {service_name} attempted {elapsed:.1f} minutes ago, skipping")
                return

        self.logger.info(f"Attempting recovery for {service_name}: {reason}")

        try:
            await self.recovery_actions[service_name]()
            self.last_recovery_attempts[service_name] = datetime.now()
            self.logger.info(f"Recovery successful for {service_name}")

        except Exception as e:
            self.logger.error(f"Recovery failed for {service_name}: {e}")

    def _start_recovery_monitor(self):
        """Start background recovery monitoring."""
        def monitor():
            while not self._shutdown_event.is_set():
                try:
                    # Check for recovery needs every minute
                    asyncio.run(self._check_recovery_needs())
                except Exception as e:
                    self.logger.error(f"Recovery monitoring error: {e}")

                time.sleep(60)

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()

    async def _check_recovery_needs(self):
        """Check if any services need recovery."""
        # This would integrate with health checker to trigger recoveries
        # For now, it's a placeholder for future implementation
        pass


class ResilienceManager:
    """Central resilience management system."""

    def __init__(self):
        self.logger = get_trading_logger("resilience-manager")
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.health_checker = HealthChecker()
        self.auto_recovery = AutoRecovery()

        # Register default health checks
        self._register_default_health_checks()

    def get_circuit_breaker(self, name: str) -> CircuitBreaker:
        """Get or create circuit breaker."""
        if name not in self.circuit_breakers:
            self.circuit_breakers[name] = CircuitBreaker(name)
        return self.circuit_breakers[name]

    def _register_default_health_checks(self):
        """Register default health checks."""
        # MCP Coordinator health check
        async def check_mcp_coordinator():
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get("http://mcp-coordinator.trading.svc.cluster.local:8081/healthz")
                    return response.status_code == 200
            except:
                return False

        self.health_checker.add_check(HealthCheck(
            name="mcp_coordinator",
            check_function=check_mcp_coordinator,
            interval=30
        ))

        # Database connectivity check
        async def check_bigquery():
            try:
                from .bigquery_exporter import BigQueryExporter
                exporter = BigQueryExporter()
                # Simple connectivity test
                return exporter.client is not None
            except:
                return False

        self.health_checker.add_check(HealthCheck(
            name="bigquery_connectivity",
            check_function=check_bigquery,
            interval=60
        ))

    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status."""
        circuit_breakers_status = {
            name: cb.get_status() for name, cb in self.circuit_breakers.items()
        }

        return {
            "timestamp": datetime.now().isoformat(),
            "circuit_breakers": circuit_breakers_status,
            "health": self.health_checker.get_status(),
            "recovery_actions": list(self.auto_recovery.recovery_actions.keys())
        }

    async def graceful_shutdown(self):
        """Perform graceful shutdown."""
        self.logger.info("Initiating graceful shutdown...")

        # Close circuit breakers
        for cb in self.circuit_breakers.values():
            # Any cleanup needed
            pass

        # Stop health monitoring
        # Note: Health checker runs in daemon thread, will stop automatically

        self.logger.info("Graceful shutdown completed")


# Global resilience manager instance
_resilience_manager = None


def get_resilience_manager() -> ResilienceManager:
    """Get or create global resilience manager instance."""
    global _resilience_manager
    if _resilience_manager is None:
        _resilience_manager = ResilienceManager()
    return _resilience_manager


# Circuit breaker decorator
def circuit_breaker(name: str):
    """Decorator to apply circuit breaker to functions."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            manager = get_resilience_manager()
            cb = manager.get_circuit_breaker(name)
            return await cb.call(lambda: func(*args, **kwargs))
        return wrapper
    return decorator


# Health check decorator
def health_check(name: str, interval: int = 30, timeout: float = 5.0):
    """Decorator to register function as health check."""
    def decorator(func):
        manager = get_resilience_manager()
        check = HealthCheck(
            name=name,
            check_function=func,
            interval=interval,
            timeout=timeout
        )
        manager.health_checker.add_check(check)
        return func
    return decorator
