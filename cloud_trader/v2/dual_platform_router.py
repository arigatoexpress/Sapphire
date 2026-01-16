"""
Dual Platform Router - Hyperliquid & Drift
==========================================
Smart routing between Hyperliquid and Drift perpetual platforms.

Routing Strategy:
- Each platform has its own symbol set
- Routing based on symbol, liquidity, and configuration
- Independent circuit breakers per platform
- Automatic failover between platforms

Symbol Allocation (Configurable):
- Hyperliquid Primary: BTC, ETH, ARB, OP, MATIC, AVAX, LINK, DOGE
- Drift Primary: SOL, JTO, PYTH, BONK, WIF, JUP, RNDR, HNT

Author: Sapphire V2 Architecture Team
Version: 2.2.0
"""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from .enhanced_circuit_breaker import (
    CircuitBreaker,
    CircuitConfig,
    CircuitOpenError,
    CircuitState,
    Platform,
)

# Configure logging
logger = logging.getLogger(__name__)


class RoutingStrategy(Enum):
    """Platform routing strategies."""
    SYMBOL_BASED = "symbol_based"      # Route based on symbol assignment
    LIQUIDITY_BASED = "liquidity"      # Route to deepest liquidity
    COST_BASED = "cost"                # Route to lowest fees
    ROUND_ROBIN = "round_robin"        # Alternate between platforms
    PRIMARY_FAILOVER = "failover"      # Use primary, failover on error
    SPLIT = "split"                    # Split order across platforms


@dataclass
class RoutingConfig:
    """Configuration for dual-platform routing."""
    
    # Primary platform assignments by symbol
    hyperliquid_symbols: list[str] = field(default_factory=lambda: [
        "BTC-PERP", "BTC",
        "ETH-PERP", "ETH", 
        "ARB-PERP", "ARB",
        "OP-PERP", "OP",
        "MATIC-PERP", "MATIC",
        "AVAX-PERP", "AVAX",
        "LINK-PERP", "LINK",
        "DOGE-PERP", "DOGE",
        "UNI-PERP", "UNI",
        "AAVE-PERP", "AAVE",
    ])
    
    drift_symbols: list[str] = field(default_factory=lambda: [
        "SOL-PERP", "SOL",
        "JTO-PERP", "JTO",
        "PYTH-PERP", "PYTH",
        "BONK-PERP", "BONK",
        "WIF-PERP", "WIF",
        "JUP-PERP", "JUP",
        "RNDR-PERP", "RNDR",
        "HNT-PERP", "HNT",
        "MEME-PERP", "MEME",
        "PEPE-PERP", "PEPE",
    ])
    
    # Default routing strategy
    default_strategy: RoutingStrategy = RoutingStrategy.SYMBOL_BASED
    
    # Failover settings
    enable_failover: bool = True
    failover_delay_ms: int = 100
    
    # Game theory obfuscation
    enable_jitter: bool = True
    jitter_min_ms: int = 50
    jitter_max_ms: int = 500
    
    enable_fuzzing: bool = True
    fuzz_percent: float = 0.02  # 2% quantity fuzzing
    
    # Circuit breaker settings
    hyperliquid_failure_threshold: int = 3
    hyperliquid_recovery_seconds: int = 30
    drift_failure_threshold: int = 3
    drift_recovery_seconds: int = 30


@dataclass
class RoutingDecision:
    """Result of routing decision."""
    primary_platform: Platform
    fallback_platform: Optional[Platform]
    symbol: str
    reason: str
    jitter_ms: int = 0
    fuzz_factor: float = 1.0
    
    def to_dict(self) -> dict:
        return {
            "primary": self.primary_platform.value,
            "fallback": self.fallback_platform.value if self.fallback_platform else None,
            "symbol": self.symbol,
            "reason": self.reason,
            "jitter_ms": self.jitter_ms,
            "fuzz_factor": round(self.fuzz_factor, 4),
        }


@dataclass
class ExecutionResult:
    """Result of trade execution."""
    success: bool
    platform: Platform
    order_id: Optional[str] = None
    symbol: str = ""
    side: str = ""
    quantity: float = 0.0
    price: float = 0.0
    filled_quantity: float = 0.0
    fees: float = 0.0
    latency_ms: float = 0.0
    failover_used: bool = False
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "platform": self.platform.value,
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "filled_quantity": self.filled_quantity,
            "price": self.price,
            "fees": self.fees,
            "latency_ms": round(self.latency_ms, 2),
            "failover_used": self.failover_used,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


class DualPlatformRouter:
    """
    Routes trades between Hyperliquid and Drift platforms.
    
    Features:
    - Symbol-based routing with configurable assignments
    - Independent circuit breakers per platform
    - Automatic failover between platforms
    - Game theory obfuscation (jitter, fuzzing)
    - Execution metrics tracking
    
    Usage:
        router = DualPlatformRouter(
            hyperliquid_client=hl_client,
            drift_client=drift_client,
        )
        await router.initialize()
        
        # Execute trade - router decides platform
        result = await router.execute(
            symbol="BTC-PERP",
            side="BUY",
            quantity=0.01,
        )
    """
    
    def __init__(
        self,
        hyperliquid_client: Any,
        drift_client: Any,
        config: Optional[RoutingConfig] = None,
    ):
        """
        Initialize dual-platform router.
        
        Args:
            hyperliquid_client: Initialized Hyperliquid client
            drift_client: Initialized Drift client
            config: Optional routing configuration
        """
        self._hl_client = hyperliquid_client
        self._drift_client = drift_client
        self.config = config or RoutingConfig()
        
        # Circuit breakers
        self._hl_breaker = CircuitBreaker(
            "hyperliquid",
            CircuitConfig(
                failure_threshold=self.config.hyperliquid_failure_threshold,
                recovery_timeout=asyncio.timedelta(seconds=self.config.hyperliquid_recovery_seconds),
            )
        )
        self._drift_breaker = CircuitBreaker(
            "drift", 
            CircuitConfig(
                failure_threshold=self.config.drift_failure_threshold,
                recovery_timeout=asyncio.timedelta(seconds=self.config.drift_recovery_seconds),
            )
        )
        
        # Metrics
        self._executions: list[ExecutionResult] = []
        self._hl_executions = 0
        self._drift_executions = 0
        self._failovers = 0
        self._round_robin_index = 0
        
        # State
        self._initialized = False
        
    @property
    def is_initialized(self) -> bool:
        return self._initialized
    
    async def initialize(self) -> bool:
        """Initialize router and verify platform connectivity."""
        logger.info("🔀 [Router] Initializing Dual-Platform Router...")
        
        # Verify Hyperliquid
        hl_ok = False
        if self._hl_client:
            try:
                if hasattr(self._hl_client, 'is_initialized'):
                    hl_ok = self._hl_client.is_initialized
                else:
                    hl_ok = True
                logger.info(f"  {'✅' if hl_ok else '❌'} Hyperliquid: {'Ready' if hl_ok else 'Not Ready'}")
            except Exception as e:
                logger.warning(f"  ❌ Hyperliquid: {e}")
        
        # Verify Drift
        drift_ok = False
        if self._drift_client:
            try:
                if hasattr(self._drift_client, 'is_initialized'):
                    drift_ok = self._drift_client.is_initialized
                else:
                    drift_ok = True
                logger.info(f"  {'✅' if drift_ok else '❌'} Drift: {'Ready' if drift_ok else 'Not Ready'}")
            except Exception as e:
                logger.warning(f"  ❌ Drift: {e}")
        
        self._initialized = hl_ok or drift_ok
        
        if self._initialized:
            logger.info(
                f"✅ [Router] Initialized | "
                f"Hyperliquid: {'✅' if hl_ok else '❌'} | "
                f"Drift: {'✅' if drift_ok else '❌'}"
            )
        else:
            logger.error("❌ [Router] Failed - no platforms available")
        
        return self._initialized
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Normalize symbol format."""
        return symbol.upper().replace("_", "-")
    
    def _get_primary_platform(self, symbol: str) -> Platform:
        """Determine primary platform for a symbol."""
        normalized = self._normalize_symbol(symbol)
        base = normalized.replace("-PERP", "").replace("-USDC", "")
        
        # Check Hyperliquid symbols
        for hl_sym in self.config.hyperliquid_symbols:
            if base in hl_sym or hl_sym in normalized:
                return Platform.HYPERLIQUID
        
        # Check Drift symbols  
        for drift_sym in self.config.drift_symbols:
            if base in drift_sym or drift_sym in normalized:
                return Platform.DRIFT
        
        # Default to Hyperliquid for unknown symbols
        return Platform.HYPERLIQUID
    
    def _get_failover_platform(self, primary: Platform) -> Platform:
        """Get failover platform."""
        if primary == Platform.HYPERLIQUID:
            return Platform.DRIFT
        return Platform.HYPERLIQUID
    
    def _apply_jitter(self) -> int:
        """Calculate jitter delay in milliseconds."""
        if not self.config.enable_jitter:
            return 0
        return random.randint(self.config.jitter_min_ms, self.config.jitter_max_ms)
    
    def _apply_fuzz(self, quantity: float) -> float:
        """Apply quantity fuzzing."""
        if not self.config.enable_fuzzing:
            return quantity
        
        fuzz = 1.0 + random.uniform(-self.config.fuzz_percent, self.config.fuzz_percent)
        return quantity * fuzz
    
    def decide_route(
        self,
        symbol: str,
        strategy: Optional[RoutingStrategy] = None,
    ) -> RoutingDecision:
        """
        Decide which platform to route to.
        
        Args:
            symbol: Trading symbol
            strategy: Optional override strategy
            
        Returns:
            Routing decision
        """
        strategy = strategy or self.config.default_strategy
        normalized = self._normalize_symbol(symbol)
        
        primary = self._get_primary_platform(normalized)
        fallback = self._get_failover_platform(primary) if self.config.enable_failover else None
        
        # Check circuit breakers
        primary_breaker = self._hl_breaker if primary == Platform.HYPERLIQUID else self._drift_breaker
        
        if primary_breaker.is_open:
            # Primary is down, use fallback
            if fallback:
                fallback_breaker = self._hl_breaker if fallback == Platform.HYPERLIQUID else self._drift_breaker
                if not fallback_breaker.is_open:
                    logger.info(
                        f"🔄 [Router] Primary {primary.value} circuit open, "
                        f"routing to {fallback.value}"
                    )
                    primary, fallback = fallback, primary
        
        reason = f"{strategy.value}: {normalized} -> {primary.value}"
        
        return RoutingDecision(
            primary_platform=primary,
            fallback_platform=fallback,
            symbol=normalized,
            reason=reason,
            jitter_ms=self._apply_jitter(),
            fuzz_factor=1.0 + random.uniform(-self.config.fuzz_percent, self.config.fuzz_percent) if self.config.enable_fuzzing else 1.0,
        )
    
    async def execute(
        self,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        strategy: Optional[RoutingStrategy] = None,
        reduce_only: bool = False,
    ) -> ExecutionResult:
        """
        Execute trade through the appropriate platform.
        
        Args:
            symbol: Trading symbol
            side: "BUY" or "SELL"
            quantity: Order quantity
            order_type: "MARKET" or "LIMIT"
            price: Limit price (for LIMIT orders)
            strategy: Optional routing strategy override
            reduce_only: Only reduce position
            
        Returns:
            Execution result
        """
        if not self._initialized:
            await self.initialize()
        
        start_time = datetime.utcnow()
        
        # Get routing decision
        decision = self.decide_route(symbol, strategy)
        
        # Apply jitter
        if decision.jitter_ms > 0:
            await asyncio.sleep(decision.jitter_ms / 1000)
        
        # Apply fuzzing
        fuzzed_quantity = quantity * decision.fuzz_factor
        
        logger.info(
            f"🔀 [Router] Executing | "
            f"Symbol: {decision.symbol} | "
            f"Platform: {decision.primary_platform.value} | "
            f"Side: {side} | "
            f"Qty: {quantity:.6f} (fuzzed: {fuzzed_quantity:.6f})"
        )
        
        # Try primary platform
        result = await self._execute_on_platform(
            platform=decision.primary_platform,
            symbol=decision.symbol,
            side=side,
            quantity=fuzzed_quantity,
            order_type=order_type,
            price=price,
            reduce_only=reduce_only,
        )
        
        # If failed and failover enabled, try fallback
        if not result.success and decision.fallback_platform and self.config.enable_failover:
            logger.warning(
                f"⚠️ [Router] Primary failed, trying failover to {decision.fallback_platform.value}"
            )
            
            await asyncio.sleep(self.config.failover_delay_ms / 1000)
            
            result = await self._execute_on_platform(
                platform=decision.fallback_platform,
                symbol=decision.symbol,
                side=side,
                quantity=fuzzed_quantity,
                order_type=order_type,
                price=price,
                reduce_only=reduce_only,
            )
            
            if result.success:
                result.failover_used = True
                self._failovers += 1
        
        # Calculate latency
        result.latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Track metrics
        self._executions.append(result)
        if result.platform == Platform.HYPERLIQUID:
            self._hl_executions += 1
        else:
            self._drift_executions += 1
        
        return result
    
    async def _execute_on_platform(
        self,
        platform: Platform,
        symbol: str,
        side: str,
        quantity: float,
        order_type: str,
        price: Optional[float],
        reduce_only: bool,
    ) -> ExecutionResult:
        """Execute on a specific platform."""
        breaker = self._hl_breaker if platform == Platform.HYPERLIQUID else self._drift_breaker
        client = self._hl_client if platform == Platform.HYPERLIQUID else self._drift_client
        
        if client is None:
            return ExecutionResult(
                success=False,
                platform=platform,
                symbol=symbol,
                side=side,
                quantity=quantity,
                error=f"{platform.value} client not configured",
            )
        
        try:
            # Execute through circuit breaker
            order = await breaker.call(
                client.place_order,
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                price=price,
                reduce_only=reduce_only,
            )
            
            return ExecutionResult(
                success=True,
                platform=platform,
                order_id=getattr(order, 'order_id', str(order)),
                symbol=symbol,
                side=side,
                quantity=quantity,
                filled_quantity=getattr(order, 'filled_quantity', quantity),
                price=getattr(order, 'price', price or 0),
            )
            
        except CircuitOpenError as e:
            logger.warning(f"🔴 [Router] Circuit open for {platform.value}")
            return ExecutionResult(
                success=False,
                platform=platform,
                symbol=symbol,
                side=side,
                quantity=quantity,
                error=str(e),
            )
            
        except Exception as e:
            logger.error(f"❌ [Router] Execution failed on {platform.value}: {e}")
            return ExecutionResult(
                success=False,
                platform=platform,
                symbol=symbol,
                side=side,
                quantity=quantity,
                error=str(e),
            )
    
    async def get_positions(self, platform: Optional[Platform] = None) -> dict:
        """Get positions from one or both platforms."""
        positions = {}
        
        if platform is None or platform == Platform.HYPERLIQUID:
            if self._hl_client and hasattr(self._hl_client, 'get_positions'):
                try:
                    hl_positions = await self._hl_client.get_positions()
                    positions["hyperliquid"] = [p.to_dict() if hasattr(p, 'to_dict') else p for p in hl_positions]
                except Exception as e:
                    logger.error(f"❌ [Router] Failed to get Hyperliquid positions: {e}")
                    positions["hyperliquid"] = []
        
        if platform is None or platform == Platform.DRIFT:
            if self._drift_client and hasattr(self._drift_client, 'get_positions'):
                try:
                    drift_positions = await self._drift_client.get_positions()
                    positions["drift"] = [p.to_dict() if hasattr(p, 'to_dict') else p for p in drift_positions]
                except Exception as e:
                    logger.error(f"❌ [Router] Failed to get Drift positions: {e}")
                    positions["drift"] = []
        
        return positions
    
    def get_circuit_status(self) -> dict:
        """Get circuit breaker status for both platforms."""
        return {
            "hyperliquid": {
                "state": self._hl_breaker.state.value,
                "is_closed": self._hl_breaker.is_closed,
                "metrics": self._hl_breaker.metrics.to_dict(),
            },
            "drift": {
                "state": self._drift_breaker.state.value,
                "is_closed": self._drift_breaker.is_closed,
                "metrics": self._drift_breaker.metrics.to_dict(),
            },
        }
    
    def get_routing_stats(self) -> dict:
        """Get routing statistics."""
        total = self._hl_executions + self._drift_executions
        
        return {
            "total_executions": total,
            "hyperliquid_executions": self._hl_executions,
            "drift_executions": self._drift_executions,
            "hyperliquid_percent": round(self._hl_executions / total * 100, 1) if total > 0 else 0,
            "drift_percent": round(self._drift_executions / total * 100, 1) if total > 0 else 0,
            "failovers": self._failovers,
            "failover_rate": round(self._failovers / total * 100, 2) if total > 0 else 0,
            "circuits": self.get_circuit_status(),
        }
    
    def get_symbol_routing(self) -> dict:
        """Get symbol to platform mapping."""
        routing = {}
        
        for sym in self.config.hyperliquid_symbols:
            base = sym.replace("-PERP", "")
            routing[base] = "hyperliquid"
        
        for sym in self.config.drift_symbols:
            base = sym.replace("-PERP", "")
            routing[base] = "drift"
        
        return routing
    
    def get_status(self) -> dict:
        """Get comprehensive router status."""
        return {
            "initialized": self._initialized,
            "config": {
                "default_strategy": self.config.default_strategy.value,
                "enable_failover": self.config.enable_failover,
                "enable_jitter": self.config.enable_jitter,
                "enable_fuzzing": self.config.enable_fuzzing,
            },
            "platforms": {
                "hyperliquid": {
                    "connected": self._hl_client is not None,
                    "symbols": len(self.config.hyperliquid_symbols),
                    "circuit": self._hl_breaker.state.value,
                },
                "drift": {
                    "connected": self._drift_client is not None,
                    "symbols": len(self.config.drift_symbols),
                    "circuit": self._drift_breaker.state.value,
                },
            },
            "stats": self.get_routing_stats(),
        }


# Factory function
async def create_dual_router(
    hyperliquid_client: Any,
    drift_client: Any,
    config: Optional[RoutingConfig] = None,
) -> DualPlatformRouter:
    """
    Create and initialize a dual-platform router.
    
    Args:
        hyperliquid_client: Hyperliquid client
        drift_client: Drift client
        config: Optional routing configuration
        
    Returns:
        Initialized router
    """
    router = DualPlatformRouter(
        hyperliquid_client=hyperliquid_client,
        drift_client=drift_client,
        config=config,
    )
    await router.initialize()
    return router


if __name__ == "__main__":
    async def demo():
        print("🔀 Dual Platform Router Demo\n")
        
        # Create router without real clients for demo
        router = DualPlatformRouter(
            hyperliquid_client=None,
            drift_client=None,
        )
        
        # Test routing decisions
        test_symbols = ["BTC-PERP", "ETH-PERP", "SOL-PERP", "BONK-PERP", "ARB-PERP"]
        
        print("Symbol Routing Decisions:")
        for sym in test_symbols:
            decision = router.decide_route(sym)
            print(f"  {sym}: {decision.primary_platform.value} (fallback: {decision.fallback_platform.value if decision.fallback_platform else 'none'})")
        
        print(f"\nSymbol Mapping: {router.get_symbol_routing()}")
        print(f"\nRouter Status: {router.get_status()}")
    
    asyncio.run(demo())
