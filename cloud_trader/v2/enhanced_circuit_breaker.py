"""
Enhanced Circuit Breaker with Multi-Platform Support
=====================================================
Production-grade circuit breaker for Hyperliquid, Drift, and other platforms.

Platforms:
- ASTER: CEX (Primary spot/margin)
- DRIFT: Solana DeFi Perps
- HYPERLIQUID: EVM DeFi Perps (REINSTATED)
- SYMPHONY: Monad Treasury Operations

Author: Sapphire V2 Architecture Team
Version: 2.2.0
"""

from __future__ import annotations

import asyncio
import functools
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Generic, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class Platform(Enum):
    """Trading platforms - Hyperliquid is ACTIVE."""
    ASTER = "aster"
    DRIFT = "drift"
    HYPERLIQUID = "hyperliquid"  # REINSTATED as active
    SYMPHONY = "symphony"


@dataclass
class CircuitMetrics:
    """Circuit breaker metrics."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    last_state_change: Optional[datetime] = None
    
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    
    time_in_open: timedelta = field(default_factory=lambda: timedelta())
    recovery_attempts: int = 0
    
    @property
    def success_rate(self) -> float:
        if self.total_calls == 0:
            return 1.0
        return self.successful_calls / self.total_calls
    
    def to_dict(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "successful": self.successful_calls,
            "failed": self.failed_calls,
            "rejected": self.rejected_calls,
            "success_rate": round(self.success_rate, 3),
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "last_failure": self.last_failure_time.isoformat() if self.last_failure_time else None,
            "last_success": self.last_success_time.isoformat() if self.last_success_time else None,
            "recovery_attempts": self.recovery_attempts,
        }


@dataclass
class CircuitConfig:
    """Circuit breaker configuration."""
    failure_threshold: int = 5
    success_threshold: int = 3
    recovery_timeout: timedelta = field(default_factory=lambda: timedelta(seconds=60))
    half_open_max_calls: int = 3
    calls_in_half_open: int = 1
    platform: Optional[Platform] = None


class CircuitOpenError(Exception):
    """Raised when circuit is open."""
    
    def __init__(self, platform: str, state: CircuitState, recovery_time: Optional[datetime] = None):
        self.platform = platform
        self.state = state
        self.recovery_time = recovery_time
        
        message = f"🔴 Circuit OPEN for {platform}"
        if recovery_time:
            wait = (recovery_time - datetime.utcnow()).total_seconds()
            message += f" | Recovery in {wait:.0f}s"
        super().__init__(message)


class CircuitBreaker(Generic[T]):
    """Circuit breaker for platform protection."""
    
    def __init__(self, name: str, config: Optional[CircuitConfig] = None):
        self.name = name
        self.config = config or CircuitConfig()
        
        self._state = CircuitState.CLOSED
        self._metrics = CircuitMetrics()
        self._opened_at: Optional[datetime] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
        
        logger.debug(f"🔧 [Circuit:{name}] Initialized")
    
    @property
    def state(self) -> CircuitState:
        return self._state
    
    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED
    
    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN
    
    @property
    def metrics(self) -> CircuitMetrics:
        return self._metrics
    
    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function through circuit breaker."""
        await self._before_call()
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure(e)
            raise
    
    async def _before_call(self) -> None:
        async with self._lock:
            self._metrics.total_calls += 1
            
            if self._state == CircuitState.CLOSED:
                return
            
            if self._state == CircuitState.OPEN:
                if self._opened_at and datetime.utcnow() >= self._opened_at + self.config.recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
                    logger.info(f"⚡ [Circuit:{self.name}] OPEN → HALF_OPEN")
                else:
                    self._metrics.rejected_calls += 1
                    recovery = self._opened_at + self.config.recovery_timeout if self._opened_at else None
                    raise CircuitOpenError(self.name, self._state, recovery)
            
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.config.half_open_max_calls:
                    self._metrics.rejected_calls += 1
                    raise CircuitOpenError(self.name, self._state)
                self._half_open_calls += 1
                self._metrics.recovery_attempts += 1
    
    async def _on_success(self) -> None:
        async with self._lock:
            self._metrics.successful_calls += 1
            self._metrics.last_success_time = datetime.utcnow()
            self._metrics.consecutive_successes += 1
            self._metrics.consecutive_failures = 0
            
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls -= 1
                if self._metrics.consecutive_successes >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    logger.info(f"✅ [Circuit:{self.name}] HALF_OPEN → CLOSED | Recovered!")
    
    async def _on_failure(self, error: Exception) -> None:
        async with self._lock:
            self._metrics.failed_calls += 1
            self._metrics.last_failure_time = datetime.utcnow()
            self._metrics.consecutive_failures += 1
            self._metrics.consecutive_successes = 0
            
            logger.warning(f"⚠️ [Circuit:{self.name}] Failure #{self._metrics.consecutive_failures}: {error}")
            
            if self._state == CircuitState.CLOSED:
                if self._metrics.consecutive_failures >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
                    logger.error(f"🔴 [Circuit:{self.name}] CLOSED → OPEN | Threshold reached")
            
            elif self._state == CircuitState.HALF_OPEN:
                self._half_open_calls -= 1
                self._transition_to(CircuitState.OPEN)
                logger.warning(f"🔴 [Circuit:{self.name}] HALF_OPEN → OPEN | Probe failed")
    
    def _transition_to(self, new_state: CircuitState) -> None:
        self._state = new_state
        self._metrics.last_state_change = datetime.utcnow()
        
        if new_state == CircuitState.OPEN:
            self._opened_at = datetime.utcnow()
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
        elif new_state == CircuitState.CLOSED:
            if self._opened_at:
                self._metrics.time_in_open += datetime.utcnow() - self._opened_at
            self._opened_at = None
            self._metrics.consecutive_failures = 0
    
    def reset(self) -> None:
        """Manual reset to CLOSED."""
        logger.info(f"🔄 [Circuit:{self.name}] Manual reset")
        self._transition_to(CircuitState.CLOSED)
        self._metrics.consecutive_failures = 0
        self._metrics.consecutive_successes = 0
    
    def get_status(self) -> dict:
        return {
            "name": self.name,
            "state": self._state.value,
            "metrics": self._metrics.to_dict(),
        }


class PlatformCircuitManager:
    """Manages circuit breakers for all platforms including Hyperliquid."""
    
    # Platform configurations - Hyperliquid is now ACTIVE
    PLATFORM_CONFIGS = {
        Platform.ASTER: CircuitConfig(
            failure_threshold=5,
            success_threshold=3,
            recovery_timeout=timedelta(seconds=60),
        ),
        Platform.DRIFT: CircuitConfig(
            failure_threshold=3,
            success_threshold=2,
            recovery_timeout=timedelta(seconds=30),
        ),
        Platform.HYPERLIQUID: CircuitConfig(
            failure_threshold=3,  # Same as Drift - both are active DeFi platforms
            success_threshold=2,
            recovery_timeout=timedelta(seconds=30),
        ),
        Platform.SYMPHONY: CircuitConfig(
            failure_threshold=5,
            success_threshold=3,
            recovery_timeout=timedelta(seconds=45),
        ),
    }
    
    # Failover chains - Hyperliquid and Drift can failover to each other
    FAILOVER_CHAIN = {
        Platform.ASTER: [Platform.DRIFT, Platform.HYPERLIQUID],
        Platform.DRIFT: [Platform.HYPERLIQUID, Platform.ASTER],  # Drift -> Hyperliquid -> Aster
        Platform.HYPERLIQUID: [Platform.DRIFT, Platform.ASTER],  # Hyperliquid -> Drift -> Aster
        Platform.SYMPHONY: [Platform.DRIFT, Platform.HYPERLIQUID],
    }
    
    def __init__(self, custom_configs: Optional[dict[Platform, CircuitConfig]] = None):
        self._circuits: dict[Platform, CircuitBreaker] = {}
        self._custom_configs = custom_configs or {}
        
        for platform in Platform:
            config = self._custom_configs.get(platform) or self.PLATFORM_CONFIGS.get(platform)
            self._circuits[platform] = CircuitBreaker(platform.value, config)
        
        logger.info(
            f"🔧 [CircuitManager] Initialized | "
            f"Platforms: {[p.value for p in Platform]} | "
            f"Hyperliquid: ACTIVE ✅"
        )
    
    def get_circuit(self, platform: Platform) -> CircuitBreaker:
        return self._circuits[platform]
    
    async def execute(
        self,
        platform: Platform,
        func: Callable[..., T],
        *args,
        enable_failover: bool = True,
        **kwargs,
    ) -> T:
        """Execute with automatic failover."""
        circuit = self._circuits[platform]
        
        try:
            return await circuit.call(func, *args, **kwargs)
        except CircuitOpenError:
            logger.warning(f"⚠️ [CircuitManager] {platform.value} circuit open")
            
            if not enable_failover:
                raise
            
            for failover in self.FAILOVER_CHAIN.get(platform, []):
                failover_circuit = self._circuits[failover]
                if failover_circuit.is_open:
                    continue
                
                try:
                    logger.info(f"🔄 [CircuitManager] Failover: {platform.value} → {failover.value}")
                    kwargs["_failover_from"] = platform.value
                    return await failover_circuit.call(func, *args, **kwargs)
                except (CircuitOpenError, Exception):
                    continue
            
            logger.error(f"❌ [CircuitManager] All failovers exhausted for {platform.value}")
            raise
    
    def get_all_status(self) -> dict[str, dict]:
        return {p.value: c.get_status() for p, c in self._circuits.items()}
    
    def get_healthy_platforms(self) -> list[Platform]:
        return [p for p, c in self._circuits.items() if c.is_closed]
    
    def reset_all(self) -> None:
        for circuit in self._circuits.values():
            circuit.reset()
    
    def log_status(self) -> None:
        emojis = {"closed": "✅", "open": "🔴", "half_open": "🟡"}
        lines = [
            f"    {p.value}: {emojis[c.state.value]} {c.state.value} ({c.metrics.success_rate:.0%})"
            for p, c in self._circuits.items()
        ]
        logger.info(f"📊 [CircuitManager] Status:\n" + "\n".join(lines))


# Global manager
_global_manager: Optional[PlatformCircuitManager] = None


def get_circuit_manager() -> PlatformCircuitManager:
    global _global_manager
    if _global_manager is None:
        _global_manager = PlatformCircuitManager()
    return _global_manager


def configure_circuit_manager(configs: Optional[dict[Platform, CircuitConfig]] = None) -> PlatformCircuitManager:
    global _global_manager
    _global_manager = PlatformCircuitManager(configs)
    return _global_manager


def circuit_protected(platform: Platform, enable_failover: bool = True):
    """Decorator for circuit-protected functions."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            manager = get_circuit_manager()
            return await manager.execute(platform, func, *args, enable_failover=enable_failover, **kwargs)
        return wrapper
    return decorator


if __name__ == "__main__":
    async def demo():
        print("🔌 Circuit Breaker Demo (Hyperliquid ACTIVE)\n")
        
        manager = PlatformCircuitManager()
        
        print("Platform Status:")
        for platform in Platform:
            circuit = manager.get_circuit(platform)
            print(f"  {platform.value}: {circuit.state.value}")
        
        print(f"\nHealthy platforms: {[p.value for p in manager.get_healthy_platforms()]}")
        print(f"\nFailover chains:")
        for p, chain in manager.FAILOVER_CHAIN.items():
            print(f"  {p.value} → {[f.value for f in chain]}")
    
    asyncio.run(demo())
