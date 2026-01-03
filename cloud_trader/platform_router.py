"""Platform Router - Modular Multi-Chain Execution

Routes trades to the correct platform using the Adapter Pattern.
Enables adding new platforms without modifying core trading logic.

Design Principles:
1. Platform Abstraction: Each platform has a standardized adapter
2. Dependency Injection: Clients injected, not hardcoded
3. Composability: New platforms = new adapter class
4. Testability: Mock adapters for testing
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .resilience import with_retry, with_timeout

logger = logging.getLogger(__name__)


@dataclass
class ExecutionMetrics:
    """Metrics for platform router execution."""

    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    total_latency_ms: float = 0.0
    last_execution_time: Optional[float] = None

    @property
    def success_rate(self) -> float:
        """Calculate success rate (0-1)."""
        if self.total_executions == 0:
            return 0.0
        return self.successful_executions / self.total_executions

    @property
    def avg_latency_ms(self) -> float:
        """Calculate average execution latency in milliseconds."""
        if self.total_executions == 0:
            return 0.0
        return self.total_latency_ms / self.total_executions

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "total_executions": self.total_executions,
            "successful_executions": self.successful_executions,
            "failed_executions": self.failed_executions,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "last_execution_time": self.last_execution_time,
        }


@dataclass
class ExecutionHistoryItem:
    """Single execution history entry."""

    timestamp: float
    platform: str
    symbol: str
    side: str
    quantity: float
    success: bool
    latency_ms: float
    error_message: Optional[str] = None
    order_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "timestamp": self.timestamp,
            "platform": self.platform,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "error_message": self.error_message,
            "order_id": self.order_id,
        }


@dataclass
class PlatformHealth:
    """Health status for a platform adapter."""

    platform: str
    is_healthy: bool
    last_check: float
    error_message: Optional[str] = None
    consecutive_failures: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "platform": self.platform,
            "is_healthy": self.is_healthy,
            "last_check": self.last_check,
            "error_message": self.error_message,
            "consecutive_failures": self.consecutive_failures,
            "status": "healthy" if self.is_healthy else "unhealthy",
        }


@dataclass
class CircuitBreaker:
    """Circuit breaker for platform resilience.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Platform unhealthy, requests rejected immediately
    - HALF_OPEN: Testing if platform recovered
    """

    failure_threshold: int = 3  # Failures before opening
    recovery_timeout: float = 30.0  # Seconds before trying half-open
    half_open_max_calls: int = 1  # Calls to test in half-open state

    # State tracking
    state: str = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    last_failure_time: Optional[float] = None
    half_open_calls: int = 0

    def should_allow_request(self) -> bool:
        """Check if request should be allowed through."""
        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            # Check if recovery timeout has passed
            if (
                self.last_failure_time
                and (time.time() - self.last_failure_time) >= self.recovery_timeout
            ):
                self.state = "HALF_OPEN"
                self.half_open_calls = 0
                return True
            return False

        if self.state == "HALF_OPEN":
            # Allow limited calls to test recovery
            return self.half_open_calls < self.half_open_max_calls

        return False

    def record_success(self) -> None:
        """Record successful execution."""
        if self.state == "HALF_OPEN":
            self.half_open_calls += 1
            # Recovered - close the circuit
            self.state = "CLOSED"
            self.last_failure_time = None

    def record_failure(self, consecutive_failures: int) -> None:
        """Record failed execution."""
        self.last_failure_time = time.time()

        if self.state == "HALF_OPEN":
            # Failed during recovery test - reopen
            self.state = "OPEN"
        elif consecutive_failures >= self.failure_threshold:
            # Hit threshold - open the circuit
            self.state = "OPEN"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API responses."""
        return {
            "state": self.state,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "last_failure_time": self.last_failure_time,
            "is_open": self.state == "OPEN",
        }


@dataclass
class TradeResult:
    """Standardized trade result across all platforms."""

    success: bool
    order_id: Optional[str]
    filled_quantity: float
    avg_price: float
    platform: str
    metadata: Dict[str, Any]


class PlatformAdapter(ABC):
    """Abstract base class for platform-specific execution."""

    @abstractmethod
    async def execute_trade(self, symbol: str, side: str, quantity: float, **kwargs) -> TradeResult:
        """Execute a trade on this platform."""
        pass

    @abstractmethod
    async def get_balance(self) -> Dict[str, float]:
        """Get account balances."""
        pass


class SymphonyAdapter(PlatformAdapter):
    """Adapter for Symphony (Monad/Base) execution."""

    def __init__(self, symphony_client, agents_config):
        self.client = symphony_client
        self.agents = agents_config

    @with_retry(
        max_attempts=3,
        base_delay=0.5,
        max_delay=10.0,
        retryable_exceptions=(ConnectionError, TimeoutError, Exception),
    )
    @with_timeout(30.0)
    async def execute_trade(self, symbol: str, side: str, quantity: float, **kwargs) -> TradeResult:
        """
        Route to appropriate Symphony agent (MILF for swaps, Degen for perps).
        Includes automatic retry with exponential backoff on failures.
        """
        try:
            # Determine if swap or perp
            is_swap = symbol in ["MON-USDC", "CHOG-USDC", "DAC-USDC"]

            # Clean symbol
            token = symbol.split("-")[0]

            if is_swap:
                # Use MILF for swaps
                agent_id = self.agents["MILF"]["id"]
                token_in = "USDC" if side == "BUY" else token
                token_out = token if side == "BUY" else "USDC"

                result = await self.client.execute_swap(
                    token_in=token_in,
                    token_out=token_out,
                    weight=5.0,  # 5% of balance
                    agent_id=agent_id,
                )
            else:
                # Use Degen for perps
                agent_id = self.agents["DEGEN"]["id"]
                action = "LONG" if side == "BUY" else "SHORT"

                result = await self.client.open_perpetual_position(
                    symbol=token, action=action, weight=5.0, leverage=2.0, agent_id=agent_id
                )

            # Standardize response
            if result and result.get("successful", 0) > 0:
                return TradeResult(
                    success=True,
                    order_id=result.get("batchId"),
                    filled_quantity=quantity,
                    avg_price=0.0,  # Symphony doesn't return fill price
                    platform="symphony",
                    metadata=result,
                )
            else:
                return TradeResult(
                    success=False,
                    order_id=None,
                    filled_quantity=0.0,
                    avg_price=0.0,
                    platform="symphony",
                    metadata=result or {},
                )

        except Exception as e:
            logger.error(f"Symphony execution error: {e}")
            return TradeResult(
                success=False,
                order_id=None,
                filled_quantity=0.0,
                avg_price=0.0,
                platform="symphony",
                metadata={"error": str(e)},
            )

    async def get_balance(self) -> Dict[str, float]:
        """Get Symphony balances."""
        # TODO: Implement when Symphony API supports it
        return {"USDC": 0.0}


class AsterAdapter(PlatformAdapter):
    """Adapter for Aster DEX execution."""

    def __init__(self, aster_client):
        self.client = aster_client

    @with_retry(
        max_attempts=3,
        base_delay=0.5,
        max_delay=10.0,
        retryable_exceptions=(ConnectionError, TimeoutError, Exception),
    )
    @with_timeout(30.0)
    async def execute_trade(self, symbol: str, side: str, quantity: float, **kwargs) -> TradeResult:
        """Execute market order on Aster with automatic retry."""
        try:
            from .enums import OrderType

            order = await self.client.place_order(
                symbol=symbol, side=side, order_type=OrderType.MARKET, quantity=quantity
            )

            return TradeResult(
                success=True,
                order_id=order.get("orderId"),
                filled_quantity=float(order.get("executedQty", 0)),
                avg_price=float(order.get("avgPrice", 0)),
                platform="aster",
                metadata=order,
            )

        except Exception as e:
            logger.error(f"Aster execution error: {e}")
            return TradeResult(
                success=False,
                order_id=None,
                filled_quantity=0.0,
                avg_price=0.0,
                platform="aster",
                metadata={"error": str(e)},
            )

    async def get_balance(self) -> Dict[str, float]:
        """Get Aster balances."""
        try:
            info = await self.client.get_account_info_v2()
            balances = {}
            for asset in info:
                balances[asset["asset"]] = float(asset["balance"])
            return balances
        except:
            return {}


class PlatformRouter:
    """
    Routes trades to appropriate platform adapter with comprehensive observability.

    Design: Strategy Pattern + Dependency Injection + World-Class Observability
    - Adapters are injected at init
    - Router selects adapter based on symbol/platform hint
    - Easy to add new platforms by creating new adapter
    - Tracks execution metrics, health status, and history for monitoring
    """

    def __init__(self, adapters: Dict[str, PlatformAdapter], history_size: int = 100):
        self.adapters = adapters

        # Observability infrastructure
        self._metrics: Dict[str, ExecutionMetrics] = {
            platform: ExecutionMetrics() for platform in adapters.keys()
        }
        self._health: Dict[str, PlatformHealth] = {
            platform: PlatformHealth(platform=platform, is_healthy=True, last_check=time.time())
            for platform in adapters.keys()
        }
        self._execution_history: deque = deque(maxlen=history_size)

        # Circuit breakers for resilience
        self._circuit_breakers: Dict[str, CircuitBreaker] = {
            platform: CircuitBreaker() for platform in adapters.keys()
        }

        logger.info(
            f"✅ PlatformRouter initialized with {len(adapters)} adapters: {list(adapters.keys())}"
        )

    async def execute(self, symbol: str, side: str, quantity: float, platform: str) -> TradeResult:
        return await self._execute_routed_trade(symbol, side, quantity, platform)

    async def _execute_routed_trade(
        self, symbol: str, side: str, quantity: float, platform: str
    ) -> TradeResult:
        """
        Execute trade on specified platform with comprehensive observability.

        Args:
            symbol: Trading pair (e.g., "BTC-USDC")
            side: "BUY" or "SELL"
            quantity: Amount to trade
            platform: "symphony" or "aster"

        Returns:
            TradeResult with execution details
        """
        start_time = time.time()

        # Check circuit breaker first
        circuit_breaker = self._circuit_breakers.get(platform)
        if circuit_breaker and not circuit_breaker.should_allow_request():
            error_msg = f"Circuit breaker OPEN for platform: {platform}. Rejecting request."
            logger.warning(f"⚡ {error_msg}")

            self._record_execution(
                platform=platform,
                symbol=symbol,
                side=side,
                quantity=quantity,
                success=False,
                latency_ms=0.0,
                error_message=error_msg,
            )

            return TradeResult(
                success=False,
                order_id=None,
                filled_quantity=0.0,
                avg_price=0.0,
                platform=platform,
                metadata={"error": error_msg, "circuit_breaker": "OPEN"},
            )

        adapter = self.adapters.get(platform)

        if not adapter:
            error_msg = f"No adapter found for platform: {platform}"
            logger.error(f"❌ {error_msg}")

            # Record failed execution
            self._record_execution(
                platform=platform,
                symbol=symbol,
                side=side,
                quantity=quantity,
                success=False,
                latency_ms=0.0,
                error_message=error_msg,
            )

            return TradeResult(
                success=False,
                order_id=None,
                filled_quantity=0.0,
                avg_price=0.0,
                platform=platform,
                metadata={"error": error_msg},
            )

        logger.info(f"🚀 Routing {side} {quantity} {symbol} to {platform}")

        try:
            result = await adapter.execute_trade(symbol, side, quantity)

            # Calculate latency
            latency_ms = (time.time() - start_time) * 1000

            # Record execution metrics
            self._record_execution(
                platform=platform,
                symbol=symbol,
                side=side,
                quantity=quantity,
                success=result.success,
                latency_ms=latency_ms,
                error_message=result.metadata.get("error") if not result.success else None,
                order_id=result.order_id,
            )

            # Update health status
            self._update_health(
                platform, result.success, None if result.success else result.metadata.get("error")
            )

            if result.success:
                logger.info(
                    f"✅ Trade executed on {platform}: {result.order_id} (latency: {latency_ms:.2f}ms)"
                )
            else:
                logger.error(
                    f"❌ Trade failed on {platform}: {result.metadata} (latency: {latency_ms:.2f}ms)"
                )

            return result

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_msg = str(e)

            logger.exception(f"💥 Exception during trade execution on {platform}: {e}")

            # Record failed execution
            self._record_execution(
                platform=platform,
                symbol=symbol,
                side=side,
                quantity=quantity,
                success=False,
                latency_ms=latency_ms,
                error_message=error_msg,
            )

            # Update health status
            self._update_health(platform, False, error_msg)

            return TradeResult(
                success=False,
                order_id=None,
                filled_quantity=0.0,
                avg_price=0.0,
                platform=platform,
                metadata={"error": error_msg, "exception_type": type(e).__name__},
            )

    def _record_execution(
        self,
        platform: str,
        symbol: str,
        side: str,
        quantity: float,
        success: bool,
        latency_ms: float,
        error_message: Optional[str] = None,
        order_id: Optional[str] = None,
    ) -> None:
        """Record execution metrics and history."""
        # Update metrics
        if platform in self._metrics:
            metrics = self._metrics[platform]
            metrics.total_executions += 1
            if success:
                metrics.successful_executions += 1
            else:
                metrics.failed_executions += 1
            metrics.total_latency_ms += latency_ms
            metrics.last_execution_time = time.time()

        # Add to history
        history_item = ExecutionHistoryItem(
            timestamp=time.time(),
            platform=platform,
            symbol=symbol,
            side=side,
            quantity=quantity,
            success=success,
            latency_ms=latency_ms,
            error_message=error_message,
            order_id=order_id,
        )
        self._execution_history.append(history_item)

    def _update_health(self, platform: str, success: bool, error_message: Optional[str]) -> None:
        """Update platform health status and circuit breaker."""
        if platform not in self._health:
            return

        health = self._health[platform]
        health.last_check = time.time()

        # Update circuit breaker
        circuit_breaker = self._circuit_breakers.get(platform)

        if success:
            health.is_healthy = True
            health.consecutive_failures = 0
            health.error_message = None
            if circuit_breaker:
                circuit_breaker.record_success()
        else:
            health.consecutive_failures += 1
            health.error_message = error_message
            if circuit_breaker:
                circuit_breaker.record_failure(health.consecutive_failures)

            # Mark unhealthy after 3 consecutive failures
            if health.consecutive_failures >= 3:
                health.is_healthy = False
                logger.warning(
                    f"⚠️ Platform {platform} marked UNHEALTHY after {health.consecutive_failures} failures"
                )

        # Broadcast status update to WebSocket subscribers
        self._broadcast_status_update(platform)

    def _broadcast_status_update(self, platform: str) -> None:
        """Broadcast platform status to WebSocket subscribers."""
        try:
            from .websocket_manager import broadcast_platform_router_status

            status_data = {
                "platform": platform,
                "health": self._health[platform].to_dict() if platform in self._health else None,
                "metrics": self._metrics[platform].to_dict() if platform in self._metrics else None,
                "circuit_breaker": (
                    self._circuit_breakers[platform].to_dict()
                    if platform in self._circuit_breakers
                    else None
                ),
            }

            # Schedule async broadcast (non-blocking)
            asyncio.create_task(broadcast_platform_router_status(status_data))
        except Exception as e:
            logger.debug(f"WebSocket broadcast skipped: {e}")

    async def get_all_balances(self) -> Dict[str, Dict[str, float]]:
        """Get balances from all platforms."""
        balances = {}
        for platform_name, adapter in self.adapters.items():
            try:
                balances[platform_name] = await adapter.get_balance()
            except Exception as e:
                logger.error(f"Failed to get balance from {platform_name}: {e}")
                balances[platform_name] = {}
        return balances

    def add_platform(self, name: str, adapter: PlatformAdapter):
        """Add a new platform adapter dynamically."""
        self.adapters[name] = adapter
        self._metrics[name] = ExecutionMetrics()
        self._health[name] = PlatformHealth(platform=name, is_healthy=True, last_check=time.time())
        logger.info(f"✅ Added platform: {name}")

    # === Observability API Methods ===

    def get_metrics(self, platform: Optional[str] = None) -> Dict[str, Any]:
        """Get execution metrics for all platforms or a specific platform."""
        if platform:
            if platform not in self._metrics:
                return {}
            return {platform: self._metrics[platform].to_dict()}

        return {name: metrics.to_dict() for name, metrics in self._metrics.items()}

    def get_health_status(self, platform: Optional[str] = None) -> Dict[str, Any]:
        """Get health status for all platforms or a specific platform."""
        if platform:
            if platform not in self._health:
                return {}
            return self._health[platform].to_dict()

        return {
            "platforms": {name: health.to_dict() for name, health in self._health.items()},
            "overall_healthy": all(h.is_healthy for h in self._health.values()),
            "total_platforms": len(self._health),
            "healthy_platforms": sum(1 for h in self._health.values() if h.is_healthy),
        }

    def get_execution_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get recent execution history."""
        history = list(self._execution_history)
        if limit:
            history = history[-limit:]
        return [item.to_dict() for item in history]

    def get_status_summary(self) -> Dict[str, Any]:
        """Get comprehensive status summary for monitoring dashboards."""
        total_executions = sum(m.total_executions for m in self._metrics.values())
        total_successful = sum(m.successful_executions for m in self._metrics.values())
        total_failed = sum(m.failed_executions for m in self._metrics.values())

        return {
            "adapters": list(self.adapters.keys()),
            "health": self.get_health_status(),
            "metrics": {
                "total_executions": total_executions,
                "successful_executions": total_successful,
                "failed_executions": total_failed,
                "overall_success_rate": (
                    total_successful / total_executions if total_executions > 0 else 0.0
                ),
                "by_platform": self.get_metrics(),
            },
            "recent_executions": len(self._execution_history),
            "timestamp": time.time(),
        }
