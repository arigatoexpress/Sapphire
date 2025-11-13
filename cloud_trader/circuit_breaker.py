"""
Circuit breaker implementation for resilient external service calls.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional, Union
from functools import wraps

logger = logging.getLogger(__name__)

class CircuitBreakerState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing if service recovered

@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior."""
    failure_threshold: int = 5  # Failures before opening
    recovery_timeout: float = 60.0  # Seconds before attempting recovery
    expected_exception: tuple = (Exception,)  # Exceptions to count as failures
    success_threshold: int = 3  # Successes needed to close circuit
    timeout: float = 30.0  # Request timeout
    name: str = "default"

@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker monitoring."""
    total_requests: int = 0
    total_failures: int = 0
    total_successes: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None

class CircuitBreaker:
    """Circuit breaker implementation with async support."""

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitBreakerState.CLOSED
        self.metrics = CircuitBreakerMetrics()
        self._lock = asyncio.Lock()
        self.logger = logging.getLogger(f"{__name__}.{config.name}")

    async def _should_attempt_call(self) -> bool:
        """Determine if a call should be attempted."""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            if time.time() - (self.metrics.last_failure_time or 0) > self.config.recovery_timeout:
                async with self._lock:
                    self.state = CircuitBreakerState.HALF_OPEN
                    self.metrics.consecutive_successes = 0
                self.logger.info(f"Circuit breaker {self.config.name} entering HALF_OPEN state")
                return True
            return False
        elif self.state == CircuitBreakerState.HALF_OPEN:
            return True
        return False

    async def _record_success(self):
        """Record a successful call."""
        async with self._lock:
            self.metrics.total_requests += 1
            self.metrics.total_successes += 1
            self.metrics.consecutive_successes += 1
            self.metrics.consecutive_failures = 0
            self.metrics.last_success_time = time.time()

            if self.state == CircuitBreakerState.HALF_OPEN:
                if self.metrics.consecutive_successes >= self.config.success_threshold:
                    self.state = CircuitBreakerState.CLOSED
                    self.logger.info(f"Circuit breaker {self.config.name} CLOSED after {self.metrics.consecutive_successes} successes")

    async def _record_failure(self, exception: Exception):
        """Record a failed call."""
        async with self._lock:
            self.metrics.total_requests += 1
            self.metrics.total_failures += 1
            self.metrics.consecutive_failures += 1
            self.metrics.consecutive_successes = 0
            self.metrics.last_failure_time = time.time()

            if self.state == CircuitBreakerState.CLOSED:
                if self.metrics.consecutive_failures >= self.config.failure_threshold:
                    self.state = CircuitBreakerState.OPEN
                    self.logger.warning(f"Circuit breaker {self.config.name} OPENED after {self.metrics.consecutive_failures} failures")
            elif self.state == CircuitBreakerState.HALF_OPEN:
                self.state = CircuitBreakerState.OPEN
                self.logger.warning(f"Circuit breaker {self.config.name} re-OPENED during HALF_OPEN state")

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function with circuit breaker protection."""
        if not await self._should_attempt_call():
            raise CircuitBreakerOpenException(f"Circuit breaker {self.config.name} is OPEN")

        try:
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(*args, **kwargs), timeout=self.config.timeout)
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: func(*args, **kwargs)
                )

            await self._record_success()
            return result

        except self.config.expected_exception as e:
            await self._record_failure(e)
            raise
        except asyncio.TimeoutError as e:
            await self._record_failure(e)
            raise CircuitBreakerTimeoutException(f"Call to {self.config.name} timed out") from e

    def __call__(self, func: Callable) -> Callable:
        """Decorator usage."""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await self.call(func, *args, **kwargs)
        return wrapper

class CircuitBreakerOpenException(Exception):
    """Exception raised when circuit breaker is open."""
    pass

class CircuitBreakerTimeoutException(Exception):
    """Exception raised when circuit breaker call times out."""
    pass

# Global circuit breaker registry
_circuit_breakers: Dict[str, CircuitBreaker] = {}

def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """Get or create a circuit breaker instance."""
    if name not in _circuit_breakers:
        if config is None:
            config = CircuitBreakerConfig(name=name)
        _circuit_breakers[name] = CircuitBreaker(config)

    return _circuit_breakers[name]

# Pre-configured circuit breakers for common services
VERTEX_AI_BREAKER = get_circuit_breaker("vertex_ai", CircuitBreakerConfig(
    name="vertex_ai",
    failure_threshold=3,
    recovery_timeout=30.0,
    timeout=60.0
))

EXCHANGE_API_BREAKER = get_circuit_breaker("exchange_api", CircuitBreakerConfig(
    name="exchange_api",
    failure_threshold=5,
    recovery_timeout=60.0,
    timeout=10.0
))

REDIS_BREAKER = get_circuit_breaker("redis", CircuitBreakerConfig(
    name="redis",
    failure_threshold=3,
    recovery_timeout=15.0,
    timeout=5.0
))

DATABASE_BREAKER = get_circuit_breaker("database", CircuitBreakerConfig(
    name="database",
    failure_threshold=3,
    recovery_timeout=30.0,
    timeout=15.0
))

TELEGRAM_BREAKER = get_circuit_breaker("telegram", CircuitBreakerConfig(
    name="telegram",
    failure_threshold=5,
    recovery_timeout=300.0,  # 5 minutes
    timeout=10.0
))

def circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None):
    """Decorator to apply circuit breaker to a function."""
    breaker = get_circuit_breaker(name, config)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await breaker.call(func, *args, **kwargs)
        return wrapper
    return decorator