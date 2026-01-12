"""
Platform Router - Universal Execution Layer for Sapphire.
Handles intelligent routing between Aster, Drift, Hyperliquid, and Symphony.

Optimizes for:
1. Low latency (Fastest execution path)
2. Fees (Cheapest platform for the asset)
3. Liquidity (Deepest order books)
4. Resilience (Failover to secondary platforms)
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional

from .ai_error_recovery import recover_from_error
from .definitions import DRIFT_SYMBOLS, HYPERLIQUID_SYMBOLS, SYMPHONY_SYMBOLS
from .logger import get_logger

logger = get_logger(__name__)


class PlatformType(Enum):
    ASTER = "aster"
    DRIFT = "drift"
    HYPERLIQUID = "hyperliquid"
    SYMPHONY = "symphony"


class ExecutionResult:
    """Standardized result for any platform execution."""

    def __init__(
        self,
        success: bool,
        platform: PlatformType,
        symbol: str,
        side: str,
        quantity: float,
        price: float = 0.0,
        tx_sig: Optional[str] = None,
        error: Optional[str] = None,
        latency_ms: int = 0,
        raw_response: Optional[Dict] = None,
    ):
        self.success = success
        self.platform = platform
        self.symbol = symbol
        self.side = side
        self.quantity = quantity
        self.price = price
        self.tx_sig = tx_sig
        self.error = error
        self.latency_ms = latency_ms
        self.raw_response = raw_response
        self.timestamp = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "platform": self.platform.value,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": self.quantity,
            "price": self.price,
            "tx_sig": self.tx_sig,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
        }


class PlatformRouter:
    """
    Orchestrates trade execution across multiple liquidity venues.
    Part of the Sapphire "Quant Lab" architecture.
    """

    def __init__(self, service):
        self.service = service
        self.history: List[ExecutionResult] = []
        self.stats = {
            p.value: {"trades": 0, "wins": 0, "errors": 0, "avg_latency": 0.0} for p in PlatformType
        }

        # Initialize circuit breakers for each platform
        from .circuit_breaker import CircuitBreakerConfig, get_circuit_breaker

        self.circuit_breakers = {
            PlatformType.ASTER: get_circuit_breaker(
                "aster",
                CircuitBreakerConfig(
                    name="aster", failure_threshold=5, recovery_timeout=60.0, timeout=10.0
                ),
            ),
            PlatformType.DRIFT: get_circuit_breaker(
                "drift",
                CircuitBreakerConfig(
                    name="drift", failure_threshold=5, recovery_timeout=60.0, timeout=15.0
                ),
            ),
            PlatformType.SYMPHONY: get_circuit_breaker(
                "symphony",
                CircuitBreakerConfig(
                    name="symphony", failure_threshold=5, recovery_timeout=60.0, timeout=10.0
                ),
            ),
            PlatformType.HYPERLIQUID: get_circuit_breaker(
                "hyperliquid",
                CircuitBreakerConfig(
                    name="hyperliquid", failure_threshold=5, recovery_timeout=60.0, timeout=10.0
                ),
            ),
        }

        logger.info("✅ PlatformRouter initialized with circuit breakers for resilient execution.")

    def _determine_platform(self, agent: Any, symbol: str) -> PlatformType:
        """
        Intelligently select the best platform for the given trade.

        Priority:
        1. Agent preference (system field)
        2. Asset exclusivity (DRIFT_SYMBOLS, HYPERLIQUID_SYMBOLS, SYMPHONY_SYMBOLS)
        3. Default to Aster (Main liquidity pool)
        """
        # Strategy 1: Agent Explicit System Preference
        if hasattr(agent, "system") and agent.system:
            if agent.system.lower() == "drift" and symbol in DRIFT_SYMBOLS:
                return PlatformType.DRIFT
            if agent.system.lower() == "hyperliquid" and symbol in HYPERLIQUID_SYMBOLS:
                return PlatformType.HYPERLIQUID
            if agent.system.lower() == "symphony" and symbol in SYMPHONY_SYMBOLS:
                return PlatformType.SYMPHONY

        # Strategy 2: Asset-Platform Mapping
        if symbol in DRIFT_SYMBOLS:
            return PlatformType.DRIFT
        if symbol in HYPERLIQUID_SYMBOLS:
            return PlatformType.HYPERLIQUID
        if symbol in SYMPHONY_SYMBOLS:
            return PlatformType.SYMPHONY

        # Strategy 3: Default to Aster
        return PlatformType.ASTER

    def _get_fallback_platform(
        self, failed_platform: PlatformType, symbol: str
    ) -> Optional[PlatformType]:
        """
        Determine the best fallback platform when the primary platform fails.

        Fallback hierarchy:
        1. Aster (always available, highest liquidity)
        2. Drift (Solana perps)
        3. Symphony (if symbol supported)
        """
        # If Aster failed, try Drift
        if failed_platform == PlatformType.ASTER:
            if symbol in DRIFT_SYMBOLS:
                return PlatformType.DRIFT
            if symbol in SYMPHONY_SYMBOLS:
                return PlatformType.SYMPHONY
            return None

        # If Drift/Symphony/HL failed, fallback to Aster
        return PlatformType.ASTER

    async def execute_trade(
        self,
        agent: Any,
        symbol: str,
        side: str,
        quantity: float,
        thesis: str,
        is_closing: bool = False,
        attempt: int = 1,
    ) -> ExecutionResult:
        """
        Main execution entry point. Handles routing, execution, and error recovery.
        """
        start_time = time.time()
        platform = self._determine_platform(agent, symbol)

        logger.info(
            f"🚀 [ROUTER] {side} {symbol} ({quantity}) -> {platform.value} | Attempt {attempt}"
        )

        # --- GAME THEORY: EXECUTION OBFUSCATION ---
        # 1. Jitter: Add random delay to avoid HFT detection
        import random

        jitter = random.uniform(0.1, 1.5)
        logger.debug(f"🎲 [ROUTER] Applying {jitter:.2f}s jitter for {agent.name}")
        await asyncio.sleep(jitter)

        # 2. Fuzzing: Slightly adjust quantity to avoid round-number patterns
        quantity_fuzz = random.uniform(0.98, 1.02)  # +/- 2%
        final_quantity = quantity * quantity_fuzz

        # Standardize formatting via PositionManager
        formatted_quantity = await self.service.position_manager._round_quantity(
            symbol, final_quantity
        )

        try:
            # Circuit breaker protection for platform execution
            breaker = self.circuit_breakers.get(platform)

            # Attempt execution with circuit breaker
            try:
                if platform == PlatformType.DRIFT:
                    result = await breaker.call(
                        self._execute_drift, symbol, side, formatted_quantity
                    )
                elif platform == PlatformType.HYPERLIQUID:
                    result = await breaker.call(
                        self._execute_hyperliquid, symbol, side, formatted_quantity
                    )
                elif platform == PlatformType.SYMPHONY:
                    result = await breaker.call(
                        self._execute_symphony, agent, symbol, side, formatted_quantity, is_closing
                    )
                else:
                    result = await breaker.call(
                        self._execute_aster, symbol, side, formatted_quantity
                    )

            except Exception as breaker_exc:
                # Circuit breaker is OPEN or call failed - attempt failover
                logger.warning(f"⚠️ [ROUTER] {platform.value} unavailable: {breaker_exc}")

                # Attempt failover to alternative platform
                fallback_platform = self._get_fallback_platform(platform, symbol)
                if fallback_platform and fallback_platform != platform:
                    logger.info(f"🔄 [ROUTER] Failing over to {fallback_platform.value}")
                    fallback_breaker = self.circuit_breakers.get(fallback_platform)

                    if fallback_platform == PlatformType.DRIFT:
                        result = await fallback_breaker.call(
                            self._execute_drift, symbol, side, formatted_quantity
                        )
                    elif fallback_platform == PlatformType.SYMPHONY:
                        result = await fallback_breaker.call(
                            self._execute_symphony,
                            agent,
                            symbol,
                            side,
                            formatted_quantity,
                            is_closing,
                        )
                    else:
                        result = await fallback_breaker.call(
                            self._execute_aster, symbol, side, formatted_quantity
                        )
                else:
                    # No fallback available
                    raise breaker_exc

            latency_ms = int((time.time() - start_time) * 1000)
            result.latency_ms = latency_ms

            # Log to internal history
            self._record_result(result)

            if result.success:
                logger.info(f"✅ [ROUTER] SUCCESS on {platform.value}: {symbol} {side}")
                return result
            else:
                # Execution failed at platform level - trigger AI Error Recovery
                return await self._handle_failure(
                    result, agent, symbol, side, quantity, thesis, is_closing, attempt
                )

        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_result = ExecutionResult(
                success=False,
                platform=platform,
                symbol=symbol,
                side=side,
                quantity=quantity,
                error=str(e),
                latency_ms=latency_ms,
            )
            return await self._handle_failure(
                error_result, agent, symbol, side, quantity, thesis, is_closing, attempt
            )

    async def _execute_drift(self, symbol: str, side: str, quantity: float) -> ExecutionResult:
        """Execute on Drift Protocol (Solana)."""
        if not self.service.drift or not self.service.drift.is_initialized:
            return ExecutionResult(
                False, PlatformType.DRIFT, symbol, side, quantity, error="Drift not initialized"
            )

        try:
            res = await self.service.drift.place_perp_order(
                symbol=symbol, side=side, amount=quantity, order_type="market"
            )
            success = bool(res and res.get("tx_sig"))
            return ExecutionResult(
                success=success,
                platform=PlatformType.DRIFT,
                symbol=symbol,
                side=side,
                quantity=quantity,
                tx_sig=res.get("tx_sig") if success else None,
                error=None if success else str(res),
                raw_response=res,
            )
        except Exception as e:
            return ExecutionResult(False, PlatformType.DRIFT, symbol, side, quantity, error=str(e))

    async def _execute_hyperliquid(
        self, symbol: str, side: str, quantity: float
    ) -> ExecutionResult:
        """Execute on Hyperliquid L1."""
        if not self.service.hl_client or not self.service.hl_client.is_initialized:
            return ExecutionResult(
                False,
                PlatformType.HYPERLIQUID,
                symbol,
                side,
                quantity,
                error="Hyperliquid not initialized",
            )

        try:
            # Parse coin
            coin = symbol.split("-")[0] if "-" in symbol else symbol
            is_buy = side.upper() == "BUY"

            res = await self.service.hl_client.place_order(
                coin=coin, is_buy=is_buy, sz=quantity, order_type={"market": {}}
            )
            success = bool(res and res.get("status") == "ok")
            return ExecutionResult(
                success=success,
                platform=PlatformType.HYPERLIQUID,
                symbol=symbol,
                side=side,
                quantity=quantity,
                tx_sig=(
                    str(
                        res.get("response", {})
                        .get("data", {})
                        .get("statuses", [{}])[0]
                        .get("resting", "n/a")
                    )
                    if success
                    else None
                ),
                error=None if success else str(res),
                raw_response=res,
            )
        except Exception as e:
            return ExecutionResult(
                False, PlatformType.HYPERLIQUID, symbol, side, quantity, error=str(e)
            )

    async def _execute_symphony(
        self, agent: Any, symbol: str, side: str, quantity: float, is_closing: bool
    ) -> ExecutionResult:
        """Execute on Symphony (Monad/Base)."""
        if not self.service.symphony or not self.service.symphony.client:
            return ExecutionResult(
                False,
                PlatformType.SYMPHONY,
                symbol,
                side,
                quantity,
                error="Symphony not initialized",
            )

        try:
            # Symphony uses weight/action for perps
            action = "LONG" if side.upper() == "BUY" else "SHORT"
            if is_closing:
                # Should ideally close by batchId, but for router we might need a more generic 'close'
                # If we don't have batchId, we might have to open opposite or fetch positions
                positions = await self.service.symphony.get_perpetual_positions()
                target = next((p for p in positions if p.get("symbol") == symbol), None)
                if target and target.get("batchId"):
                    res = await self.service.symphony.close_perpetual_position(target["batchId"])
                else:
                    return ExecutionResult(
                        False,
                        PlatformType.SYMPHONY,
                        symbol,
                        side,
                        quantity,
                        error="No open position found to close",
                    )
            else:
                # Open with 10% weight as default if not specified
                res = await self.service.symphony.open_perpetual_position(
                    symbol=symbol.split("-")[0],
                    action=action,
                    weight=10.0,
                    leverage=1.1,
                    agent_id=agent.id,
                )

            success = bool(res and (res.get("successful", 0) > 0 or res.get("status") == "ok"))
            return ExecutionResult(
                success=success,
                platform=PlatformType.SYMPHONY,
                symbol=symbol,
                side=side,
                quantity=quantity,
                tx_sig=res.get("batchId") if success else None,
                error=None if success else str(res),
                raw_response=res,
            )
        except Exception as e:
            return ExecutionResult(
                False, PlatformType.SYMPHONY, symbol, side, quantity, error=str(e)
            )

    async def _execute_aster(self, symbol: str, side: str, quantity: float) -> ExecutionResult:
        """Execute on Aster (Main Liquidity)."""
        try:
            from .enums import OrderType

            aster_symbol = self.service._normalize_for_aster(symbol)

            # CRITICAL FIX: Use place_order instead of create_order
            # CRITICAL FIX: Use OrderType.MARKET enum
            res = await self.service._exchange_client.place_order(
                symbol=aster_symbol, side=side, order_type=OrderType.MARKET, quantity=quantity
            )

            # CRITICAL CHECK: Verify FILL
            # Aster/Binance API returns 'status': 'FILLED' for immediate market fills
            status = res.get("status", "UNKNOWN")
            is_filled = status == "FILLED"
            success = bool(res and res.get("orderId") and is_filled)

            # Use avgPrice for market orders as 'price' is usually 0
            avg_price = float(res.get("avgPrice", res.get("price", 0.0)))

            if not success and status != "FILLED":
                logger.warning(f"⚠️ Order placed but NOT FILLED. Status: {status}, Response: {res}")

            return ExecutionResult(
                success=success,
                platform=PlatformType.ASTER,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=avg_price,
                tx_sig=str(res.get("orderId")) if res.get("orderId") else None,
                error=None if success else f"Order Status: {status} (Expected FILLED)",
                raw_response=res,
            )
        except Exception as e:
            return ExecutionResult(False, PlatformType.ASTER, symbol, side, quantity, error=str(e))

    async def _handle_failure(
        self,
        result: ExecutionResult,
        agent: Any,
        symbol: str,
        side: str,
        quantity: float,
        thesis: str,
        is_closing: bool,
        attempt: int,
    ) -> ExecutionResult:
        """Consult AI Error Recovery and potentially retry."""
        if attempt >= 3:
            logger.error(f"❌ Max retries reached for {symbol} {side} on {result.platform.value}")
            return result

        # 1. Consult Recovery Agent
        context = {
            "platform": result.platform.value,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "attempt": attempt,
            "agent_id": agent.id,
        }

        recovery = await recover_from_error(result.error or "Unknown platform error", context)

        if recovery.recoverable and recovery.action == "retry":
            logger.info(f"🔄 AI RECOVERY: {recovery.reason}. Retrying...")

            # Apply corrections if any
            new_quantity = recovery.corrections.get("quantity", quantity)
            new_symbol = recovery.corrections.get("symbol", symbol)

            # Wait if suggested
            delay_ms = recovery.corrections.get("delay_ms", 500)
            await asyncio.sleep(delay_ms / 1000.0)

            return await self.execute_trade(
                agent, new_symbol, side, new_quantity, thesis, is_closing, attempt + 1
            )

        logger.warning(f"⚠️ RECOVERY FAILED: {recovery.reason}. Aborting.")
        return result

    def _record_result(self, result: ExecutionResult):
        """Update statistics and history."""
        self.history.append(result)
        if len(self.history) > 100:
            self.history.pop(0)

        p_stats = self.stats[result.platform.value]
        p_stats["trades"] += 1
        if result.success:
            p_stats["wins"] += 1
        else:
            p_stats["errors"] += 1

        # Cumulative average latency
        if result.latency_ms > 0:
            prev_avg = p_stats["avg_latency"]
            count = p_stats["trades"]
            p_stats["avg_latency"] = (prev_avg * (count - 1) + result.latency_ms) / count

    def get_status_summary(self) -> Dict[str, Any]:
        """Summary for Dashboard."""
        return {
            "platform_stats": self.stats,
            "recent_executions": [r.to_dict() for r in self.history[-10:]],
            "total_executions": len(self.history),
        }
