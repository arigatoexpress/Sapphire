"""
Platform Router - Direct Execution Layer for Sapphire V2.3

ARCHITECTURE: Independent Platform Traders (No Consensus)
============================================================
Each trader operates autonomously on its dedicated platform:
- Aster Trader    → Aster Platform only (Solana Perps)
- Lighter     → Lighter only (L1 Perps)
- Aster Trader    → Aster only (CEX with Shield Strategy)
- Aster Trader → Aster only (Monad Treasury)
- Lighter Trader  → Lighter only (Eth L2)

Benefits:
1. SPEED: No consensus delays (3-5s eliminated)
2. AUTONOMY: Each trader makes independent decisions
3. PLATFORM EXPERTISE: Optimized for specific platform quirks
4. RESILIENCE: Platform failures don't affect others

Removed: Multi-platform failover, consensus voting, complex routing logic
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional

from .ai_error_recovery import recover_from_error
from .definitions import ASTER_SYMBOLS, LIGHTER_SYMBOLS, ASTER_SYMBOLS, LIGHTER_SYMBOLS, JUPITER_SYMBOLS
from .logger import get_logger

logger = get_logger(__name__)


class PlatformType(Enum):
    ASTER = "aster"
    ASTER = "aster"
    LIGHTER = "lighter"
    ASTER = "aster"
    LIGHTER = "lighter"
    JUPITER = "jupiter"


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

        # INDEPENDENT MODE: Each trader executes directly on its platform (no consensus)
        self.independent_mode = True
        logger.info("⚡ INDEPENDENT MODE ENABLED: Traders operate autonomously (no consensus)")

        # Initialize circuit breakers for each platform
        from .circuit_breaker import CircuitBreakerConfig, get_circuit_breaker

        self.circuit_breakers = {
            PlatformType.ASTER: get_circuit_breaker(
                "aster",
                CircuitBreakerConfig(
                    name="aster", failure_threshold=5, recovery_timeout=60.0, timeout=10.0
                ),
            ),
            PlatformType.ASTER: get_circuit_breaker(
                "aster",
                CircuitBreakerConfig(
                    name="aster", failure_threshold=5, recovery_timeout=60.0, timeout=15.0
                ),
            ),
            PlatformType.ASTER: get_circuit_breaker(
                "aster",
                CircuitBreakerConfig(
                    name="aster", failure_threshold=5, recovery_timeout=60.0, timeout=10.0
                ),
            ),
            PlatformType.LIGHTER: get_circuit_breaker(
                "lighter",
                CircuitBreakerConfig(
                    name="lighter", failure_threshold=5, recovery_timeout=60.0, timeout=10.0
                ),
            ),
            PlatformType.JUPITER: get_circuit_breaker(
                "jupiter",
                CircuitBreakerConfig(
                    name="jupiter", failure_threshold=5, recovery_timeout=60.0, timeout=10.0
                ),
            ),
        }

        logger.info("✅ PlatformRouter initialized with circuit breakers for resilient execution.")

    def _determine_platform(self, agent: Any, symbol: str) -> PlatformType:
        """
        Intelligently select the best platform for the given trade.

        Priority:
        0. Microservice platform isolation (check enabled platforms in config)
        1. Agent preference (system field)
        2. Lighter/Aster for US-compatible trading (Aster blocked in US)
        3. Aster for exclusive symbols
        4. Fallback to Aster (if region allows)
        """
        focused_mode = getattr(getattr(self.service, "settings", None), "sapphire_focused_mode", True)

        # Strategy 0: MICROSERVICE PLATFORM ISOLATION
        # In microservices mode, each service only routes to its designated platform
        enabled_platforms = []
        if hasattr(self.service, 'config'):
            config = self.service.config
            logger.debug(f"🔍 [ROUTER] Checking config for enabled platforms...")
            if getattr(config, 'enable_jupiter', False):
                enabled_platforms.append(PlatformType.JUPITER)
                logger.debug(f"  ✓ Jupiter enabled")
            if getattr(config, 'enable_lighter', False):
                enabled_platforms.append(PlatformType.LIGHTER)
                logger.debug(f"  ✓ Lighter enabled")
            if getattr(config, 'enable_lighter', False):
                enabled_platforms.append(PlatformType.LIGHTER)
                logger.debug(f"  ✓ Lighter enabled")
            if getattr(config, 'enable_aster', False):
                enabled_platforms.append(PlatformType.ASTER)
                logger.debug(f"  ✓ Aster enabled")
            if getattr(config, 'enable_aster', False):
                enabled_platforms.append(PlatformType.ASTER)
                logger.debug(f"  ✓ Aster enabled")
            if getattr(config, 'enable_aster', False):
                enabled_platforms.append(PlatformType.ASTER)
                logger.debug(f"  ✓ Aster enabled")

            logger.info(f"🔍 [ROUTER] Enabled platforms: {[p.value for p in enabled_platforms]} (count={len(enabled_platforms)})")

            # If ONLY ONE platform is enabled, route to that platform EXCLUSIVELY
            if len(enabled_platforms) == 1:
                logger.info(f"🎯 [MICROSERVICE MODE] Routing {symbol} to {enabled_platforms[0].value} (only enabled platform)")
                return enabled_platforms[0]

            # If NO platforms enabled, log warning and continue with normal routing
            if len(enabled_platforms) == 0:
                logger.warning(f"⚠️ No platforms enabled in config, using default routing logic")

        # In Sapphire focused mode we hard-limit routing to ASTER/LIGHTER only.
        if focused_mode:
            if symbol in ASTER_SYMBOLS:
                return PlatformType.ASTER
            if symbol in LIGHTER_SYMBOLS:
                return PlatformType.LIGHTER
            if enabled_platforms:
                if PlatformType.ASTER in enabled_platforms:
                    return PlatformType.ASTER
                if PlatformType.LIGHTER in enabled_platforms:
                    return PlatformType.LIGHTER
                return enabled_platforms[0]
            return PlatformType.LIGHTER

        # Strategy 1: Agent Explicit System Preference (EXCEPT Aster - US blocked)
        if hasattr(agent, "system") and agent.system:
            target_sys = agent.system.lower()
            if target_sys == "aster" and symbol in ASTER_SYMBOLS:
                # Only return if aster is enabled (or no platform restrictions)
                if not enabled_platforms or PlatformType.ASTER in enabled_platforms:
                    return PlatformType.ASTER
            if target_sys == "lighter" and symbol in LIGHTER_SYMBOLS:
                if not enabled_platforms or PlatformType.LIGHTER in enabled_platforms:
                    return PlatformType.LIGHTER
            if target_sys == "aster" and symbol in ASTER_SYMBOLS:
                if not enabled_platforms or PlatformType.ASTER in enabled_platforms:
                    return PlatformType.ASTER
            # CRITICAL FIX: Ignore agent.system="aster" - blocked in US region
            # Fall through to Strategy 2 for smart US-compatible routing
            if target_sys == "aster":
                logger.info(f"🔄 Agent requested Aster for {symbol}, routing to US-compatible exchange instead")
                # Don't return - fall through to Strategy 2

        # Strategy 2: Prefer US-compatible exchanges (Lighter/Aster)
        # Check if symbol is available on Lighter (highest liquidity for majors)
        if symbol in LIGHTER_SYMBOLS:
            if not enabled_platforms or PlatformType.LIGHTER in enabled_platforms:
                return PlatformType.LIGHTER

        # Check if symbol is available on Aster (Solana perps)
        if symbol in ASTER_SYMBOLS:
            if not enabled_platforms or PlatformType.ASTER in enabled_platforms:
                return PlatformType.ASTER

        # Aster for exclusive Monad ecosystem tokens
        if symbol in ASTER_SYMBOLS:
            if not enabled_platforms or PlatformType.ASTER in enabled_platforms:
                return PlatformType.ASTER

        # Strategy 3A: Route perpetual futures to Aster (Solana native perps)
        from .definitions import ASTER_PERP_SYMBOLS
        if symbol in ASTER_PERP_SYMBOLS:
            if not enabled_platforms or PlatformType.ASTER in enabled_platforms:
                logger.info(f"🎯 Routing {symbol} to Aster (Solana perpetuals)")
                return PlatformType.ASTER

        # Strategy 3B: JUPITER DISABLED FOR TRADING (API key issues)
        # Jupiter is available for price data only, not for executing trades
        # Use Lighter or Aster for actual trading instead
        # from .definitions import JUPITER_SPOT_SYMBOLS
        # if symbol in JUPITER_SPOT_SYMBOLS:
        #     if not enabled_platforms or PlatformType.JUPITER in enabled_platforms:
        #         logger.info(f"🔄 Routing {symbol} to Jupiter (best Solana DEX prices)")
        #         return PlatformType.JUPITER

        # Strategy 4: Try Lighter for supported pairs (L2 execution)
        if symbol in LIGHTER_SYMBOLS or symbol.replace("BTC", "WBTC").replace("ETH", "WETH") in LIGHTER_SYMBOLS:
            if not enabled_platforms or PlatformType.LIGHTER in enabled_platforms:
                return PlatformType.LIGHTER

        # Strategy 5: Fallback to Lighter for major pairs (BTC, ETH, SOL)
        # This avoids Aster's US region block
        major_symbols = ["BTC-USDC", "ETH-USDC", "SOL-USDC", "BTCUSDT", "ETHUSDT", "SOLUSDT"]
        if any(major in symbol.upper() for major in major_symbols):
            # Prefer Jupiter for SOL pairs (best Solana DEX aggregation)
            if "SOL" in symbol.upper():
                if not enabled_platforms or PlatformType.JUPITER in enabled_platforms:
                    logger.info(f"🔄 Routing {symbol} to Jupiter (optimal for SOL)")
                    return PlatformType.JUPITER
            # Otherwise use Lighter
            if not enabled_platforms or PlatformType.LIGHTER in enabled_platforms:
                logger.info(f"🔄 Routing {symbol} to Lighter (Aster blocked in US)")
                return PlatformType.LIGHTER

        # Last resort: Try Aster (will fail with -5019 in US) - only if enabled
        if not enabled_platforms or PlatformType.ASTER in enabled_platforms:
            logger.warning(f"⚠️ Defaulting to Aster for {symbol} (may fail in US region)")
            return PlatformType.ASTER

        # If we get here, no suitable platform found - return first enabled platform
        if enabled_platforms:
            logger.warning(f"⚠️ No ideal platform for {symbol}, using {enabled_platforms[0].value}")
            return enabled_platforms[0]

        # Absolute fallback
        return PlatformType.LIGHTER

    def _get_fallback_platform(
        self, failed_platform: PlatformType, symbol: str
    ) -> Optional[PlatformType]:
        """
        Determine the best fallback platform when the primary platform fails.

        NEW Fallback hierarchy (US-compatible):
        1. Lighter (US-compatible, high liquidity)
        2. Aster (US-compatible, Solana perps)
        3. Aster (if symbol supported)
        4. Aster (blocked in US, last resort)
        """
        focused_mode = getattr(getattr(self.service, "settings", None), "sapphire_focused_mode", True)
        if focused_mode:
            if failed_platform == PlatformType.ASTER and symbol in LIGHTER_SYMBOLS:
                return PlatformType.LIGHTER
            if failed_platform == PlatformType.LIGHTER and symbol in ASTER_SYMBOLS:
                return PlatformType.ASTER
            return None

        # If Aster failed (likely US region block), try US-compatible exchanges
        if failed_platform == PlatformType.ASTER:
            # Prefer Jupiter for Solana tokens
            if symbol in JUPITER_SYMBOLS:
                logger.info(f"🔄 Aster failed, falling back to Jupiter for {symbol}")
                return PlatformType.JUPITER
            if symbol in LIGHTER_SYMBOLS:
                logger.info(f"🔄 Aster failed, falling back to Lighter for {symbol}")
                return PlatformType.LIGHTER
            if symbol in ASTER_SYMBOLS:
                logger.info(f"🔄 Aster failed, falling back to Aster for {symbol}")
                return PlatformType.ASTER
            if symbol in ASTER_SYMBOLS:
                return PlatformType.ASTER
            return None

        # If Lighter failed, try Aster
        if failed_platform == PlatformType.LIGHTER:
            if symbol in ASTER_SYMBOLS:
                logger.info(f"🔄 Lighter failed, falling back to Aster for {symbol}")
                return PlatformType.ASTER
            if symbol in ASTER_SYMBOLS:
                return PlatformType.ASTER
            # DO NOT fallback to Aster in US region
            return None

        # If Aster failed, try Lighter
        if failed_platform == PlatformType.ASTER:
            if symbol in LIGHTER_SYMBOLS:
                logger.info(f"🔄 Aster failed, falling back to Lighter for {symbol}")
                return PlatformType.LIGHTER
            if symbol in ASTER_SYMBOLS:
                return PlatformType.ASTER
            # DO NOT fallback to Aster in US region
            return None

        # If Aster failed, try Lighter or Aster
        if failed_platform == PlatformType.ASTER:
            if symbol in LIGHTER_SYMBOLS:
                return PlatformType.LIGHTER
            if symbol in ASTER_SYMBOLS:
                return PlatformType.ASTER
            return None

        return None

    async def execute_trade(
        self,
        agent: Any,
        symbol: str,
        side: str,
        quantity: float,
        thesis: str,
        is_closing: bool = False,
        attempt: int = 1,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Main execution entry point. Handles routing, execution, and error recovery.
        """
        start_time = time.time()
        platform = self._determine_platform(agent, symbol)

        logger.info(
            f"🚀 [ROUTER] {side} {symbol} ({quantity}) -> {platform.value} | Attempt {attempt}"
        )

        # --- PRECISION NORMALIZATION & PLATFORM-AWARE MEV PROTECTION ---
        # Import precision normalizer and MEV protector
        from .precision_normalizer import get_precision_normalizer
        from .execution.mev_protection import MEVProtector
        import random

        # Platform-aware MEV protection (Phase 1 optimization)
        mev_protector = MEVProtector()
        protection_level = mev_protector.get_platform_protection_level(platform.value)

        # Protect order (includes jitter and fuzzing based on platform)
        protected_order = mev_protector.protect_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            level=protection_level
        )

        # Apply timing protection (jitter) if needed
        await mev_protector.apply_timing_protection(protected_order)

        # Use protected quantity (includes fuzzing if applicable)
        fuzzed_quantity = protected_order.protected_quantity

        logger.debug(
            f"⚡ [MEV] {platform.value}: {protection_level.value} | "
            f"Jitter: {protected_order.protected_timing*1000:.1f}ms | "
            f"Qty: {quantity:.4f} → {fuzzed_quantity:.4f}"
        )

        # 3. CRITICAL FIX: Get current market price and normalize order
        normalizer = get_precision_normalizer()

        # Get market price (estimate if not available)
        try:
            if platform == PlatformType.ASTER and hasattr(self.service, '_exchange_client'):
                aster_symbol = self.service._normalize_for_aster(symbol)
                ticker = await self.service._exchange_client.get_ticker(aster_symbol)
                market_price = float(ticker.get("lastPrice", 0)) if ticker else 0
            else:
                # Fallback: use a nominal price for normalization
                market_price = 50000.0  # Default for normalization
        except Exception as e:
            logger.warning(f"Could not fetch market price for {symbol}: {e}")
            market_price = 50000.0  # Fallback

        # Normalize the order to meet exchange precision requirements
        normalized = await normalizer.normalize_order(
            symbol=symbol,
            platform=platform.value,
            price=market_price,
            quantity=fuzzed_quantity,
            side=side
        )

        if not normalized["valid"]:
            error_msg = f"Order normalization failed: {', '.join(normalized['warnings'])}"
            logger.error(f"❌ {error_msg}")
            return ExecutionResult(
                success=False,
                platform=platform,
                symbol=symbol,
                side=side,
                quantity=quantity,
                error=error_msg,
                latency_ms=0,
            )

        # Use the normalized quantity
        formatted_quantity = normalized["quantity"]

        if normalized["warnings"]:
            logger.info(f"📐 [PRECISION] {symbol}: {normalized['warnings']}")

        try:
            # Circuit breaker protection for platform execution
            breaker = self.circuit_breakers.get(platform)

            # Attempt execution with circuit breaker
            try:
                if platform == PlatformType.ASTER:
                    result = await breaker.call(
                        self._execute_aster, symbol, side, formatted_quantity, tp_price, sl_price
                    )
                elif platform == PlatformType.LIGHTER:
                    result = await breaker.call(
                        self._execute_lighter, symbol, side, formatted_quantity, tp_price, sl_price
                    )
                elif platform == PlatformType.ASTER:
                    result = await breaker.call(
                        self._execute_aster, agent, symbol, side, formatted_quantity, is_closing
                    )
                elif platform == PlatformType.JUPITER:
                    result = await breaker.call(
                        self._execute_jupiter, symbol, side, formatted_quantity
                    )
                else:
                    result = await breaker.call(
                        self._execute_aster, symbol, side, formatted_quantity, tp_price, sl_price, market_price
                    )

            except Exception as breaker_exc:
                # Circuit breaker is OPEN or call failed
                logger.warning(f"⚠️ [ROUTER] {platform.value} unavailable: {breaker_exc}")

                # INDEPENDENT MODE: No cross-platform failover
                # Each trader is responsible for its own platform only
                if self.independent_mode:
                    logger.info(f"🚫 [INDEPENDENT] No failover - {platform.value} trader handles its own platform")
                    return ExecutionResult(
                        success=False,
                        platform=platform,
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        error=f"Platform {platform.value} unavailable (independent mode)",
                        latency_ms=int((time.time() - start_time) * 1000),
                    )

                # Legacy mode: Attempt failover to alternative platform (disabled in V2.3)
                # Keeping code for reference, but independent_mode=True disables this
                fallback_platform = self._get_fallback_platform(platform, symbol)
                if fallback_platform and fallback_platform != platform:
                    logger.info(f"🔄 [ROUTER] Failing over to {fallback_platform.value}")
                    fallback_breaker = self.circuit_breakers.get(fallback_platform)

                    if fallback_platform == PlatformType.ASTER:
                        result = await fallback_breaker.call(
                            self._execute_aster, symbol, side, formatted_quantity, tp_price, sl_price
                        )
                    elif fallback_platform == PlatformType.ASTER:
                        result = await fallback_breaker.call(
                            self._execute_aster,
                            agent,
                            symbol,
                            side,
                            formatted_quantity,
                            is_closing,
                        )
                    elif fallback_platform == PlatformType.JUPITER:
                        result = await fallback_breaker.call(
                            self._execute_jupiter, symbol, side, formatted_quantity
                        )
                    elif fallback_platform == PlatformType.LIGHTER:
                        result = await fallback_breaker.call(
                            self._execute_lighter, symbol, side, formatted_quantity, tp_price, sl_price
                        )
                    elif fallback_platform == PlatformType.LIGHTER:
                        result = await fallback_breaker.call(
                            self._execute_lighter, symbol, side, formatted_quantity
                        )
                    else:
                        result = await fallback_breaker.call(
                            self._execute_aster, symbol, side, formatted_quantity, tp_price, sl_price
                        )
                else:
                    # No fallback available
                    raise breaker_exc

            latency_ms = int((time.time() - start_time) * 1000)
            result.latency_ms = latency_ms

            # V2.3: Record execution speed for performance monitoring
            from .execution_monitor import get_execution_monitor
            monitor = get_execution_monitor()
            monitor.record_execution(
                platform=platform.value,
                symbol=symbol,
                total_latency_ms=latency_ms,
                success=result.success
            )

            # Log to internal history
            self._record_result(result)

            if result.success:
                logger.info(
                    f"✅ [ROUTER] SUCCESS on {platform.value}: {symbol} {side} "
                    f"({latency_ms}ms)"
                )
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

    async def _execute_aster(
        self,
        symbol: str,
        side: str,
        quantity: float,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Execute on Aster Protocol (Solana Perpetuals).

        Uses Aster's native perpetual futures for leveraged trading.
        Supports stop-loss and take-profit orders.
        """
        if not self.service.aster or not self.service.aster.is_initialized:
            return ExecutionResult(
                False, PlatformType.ASTER, symbol, side, quantity, error="Aster not initialized"
            )

        try:
            # Determine if this is opening or closing a position
            direction = "long" if side.upper() == "BUY" else "short"

            # Check for existing position
            existing_position = await self.service.aster.get_position(symbol)
            is_closing = existing_position and existing_position.get("amount", 0) != 0

            if is_closing:
                # Close existing position
                logger.info(f"🔒 Closing Aster position: {symbol}")
                res = await self.service.aster.close_perp_position(
                    market=symbol,
                    size=quantity,
                )
            else:
                # Open new position with leverage
                logger.info(f"🚀 Opening Aster {direction} position: {quantity} {symbol}")
                res = await self.service.aster.open_perp_position(
                    market=symbol,
                    direction=direction,
                    size=quantity,
                    leverage=2.0,  # Conservative 2x leverage by default
                    stop_loss=sl_price,
                    take_profit=tp_price,
                )

            success = bool(res and res.get("success"))

            # Extract fill price
            fill_price = 0.0
            if success:
                if is_closing:
                    fill_price = res.get("entry_price", 0)
                else:
                    # For market orders, get current price
                    market_info = await self.service.aster.get_perp_market(symbol)
                    fill_price = market_info.get("oracle_price", 0)

            return ExecutionResult(
                success=success,
                platform=PlatformType.ASTER,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=fill_price,
                tx_sig=res.get("tx_sig") if success else None,
                error=None if success else res.get("error", "Unknown error"),
                raw_response=res,
            )
        except Exception as e:
            logger.error(f"❌ Aster execution error: {e}")
            return ExecutionResult(
                False, PlatformType.ASTER, symbol, side, quantity, error=str(e)
            )

    async def _execute_lighter(
        self, 
        symbol: str, 
        side: str, 
        quantity: float,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
    ) -> ExecutionResult:
        """Execute on Lighter L1."""
        if not self.service.hl_client or not self.service.hl_client.is_initialized:
            return ExecutionResult(
                False,
                PlatformType.LIGHTER,
                symbol,
                side,
                quantity,
                error="Lighter not initialized",
            )

        try:
            # Lighter uses symbol directly (no parsing needed)
            # The client will handle symbol normalization
            res = await self.service.hl_client.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type="MARKET"
            )
            success = bool(res and res.get("status") == "ok")
            
            # Extract fill price from SDK response
            # Lighter client returns: {"status": "ok", "filled": True, "data": {...avgPx...}}
            # Where "data" IS the filled data containing avgPx directly
            fill_price = 0.0
            if success and res:
                try:
                    # Check if order was filled (client sets "filled": True)
                    if res.get("filled"):
                        data = res.get("data", {})
                        if data:
                            # avgPx is directly in data, not nested
                            fill_price = float(data.get("avgPx", 0))
                            logger.info(f"📊 [Lighter] Extracted fill price: ${fill_price}")

                    # Fallback: Try statuses format for resting orders
                    if fill_price == 0.0 and "response" in res:
                        statuses = res.get("response", {}).get("data", {}).get("statuses", [])
                        if statuses:
                            filled_info = statuses[0].get("filled", {})
                            if filled_info:
                                fill_price = float(filled_info.get("avgPx", 0))
                                logger.info(f"📊 [Lighter] Extracted fill price from statuses: ${fill_price}")
                except (ValueError, TypeError, KeyError) as e:
                    logger.warning(f"⚠️ [Lighter] Failed to extract fill price: {e}")
                    
            # ---------------------------------------------------------
            # RISK MANAGEMENT: Place Take Profit & Stop Loss if ordered
            # ---------------------------------------------------------
            if success and (tp_price or sl_price):
                # We need to reverse the side for TP/SL (if we bought, we need to sell)
                close_side = "SELL" if side.upper() == "BUY" else "BUY"
                
                # Place Take Profit
                if tp_price:
                    try:
                        await self.service.hl_client.place_trigger_order(
                            symbol=symbol,
                            side=close_side,
                            quantity=quantity,
                            trigger_price=tp_price,
                            is_tp=True,
                            reduce_only=True
                        )
                    except Exception as tp_err:
                        logger.error(f"⚠️ [ROUTER] Failed to place TP for {symbol}: {tp_err}")
                
                # Place Stop Loss
                if sl_price:
                    try:
                        await self.service.hl_client.place_trigger_order(
                            symbol=symbol,
                            side=close_side,
                            quantity=quantity,
                            trigger_price=sl_price,
                            is_tp=False,
                            reduce_only=True
                        )
                    except Exception as sl_err:
                        logger.error(f"⚠️ [ROUTER] Failed to place SL for {symbol}: {sl_err}")
            
            return ExecutionResult(
                success=success,
                platform=PlatformType.LIGHTER,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=fill_price,
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
                False, PlatformType.LIGHTER, symbol, side, quantity, error=str(e)
            )

    async def _execute_lighter(
        self, symbol: str, side: str, quantity: float
    ) -> ExecutionResult:
        """Execute on Lighter (decentralized perps on Ethereum L2)."""
        if not self.service.lighter_client or not self.service.lighter_client.is_initialized:
            return ExecutionResult(
                False,
                PlatformType.LIGHTER,
                symbol,
                side,
                quantity,
                error="Lighter not initialized",
            )

        try:
            res = await self.service.lighter_client.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type="MARKET"
            )
            success = bool(res and res.get("status") == "ok")
            
            # Extract fill price from Lighter response
            fill_price = 0.0
            if success and res:
                try:
                    data = res.get("data", {})
                    if data:
                        fill_price = float(data.get("avgPx", 0))
                except (ValueError, TypeError, KeyError):
                    pass
                    
            return ExecutionResult(
                success=success,
                platform=PlatformType.LIGHTER,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=fill_price,
                tx_sig=str(res.get("data", {}).get("orderId", "n/a")) if success else None,
                error=None if success else str(res),
                raw_response=res,
            )
        except Exception as e:
            return ExecutionResult(
                False, PlatformType.LIGHTER, symbol, side, quantity, error=str(e)
            )

    async def _execute_jupiter(
        self, symbol: str, side: str, quantity: float
    ) -> ExecutionResult:
        """Execute on Jupiter DEX aggregator (Solana)."""
        if not self.service.jupiter_client:
            return ExecutionResult(
                False,
                PlatformType.JUPITER,
                symbol,
                side,
                quantity,
                error="Jupiter not initialized",
            )

        try:
            res = await self.service.jupiter_client.execute_trade(
                symbol=symbol,
                side=side,
                quantity=quantity,
            )

            success = bool(res and res.get("success"))

            # Extract fill price from Jupiter response
            fill_price = 0.0
            if success and res:
                try:
                    fill_price = float(res.get("price", 0))
                except (ValueError, TypeError, KeyError):
                    pass

            return ExecutionResult(
                success=success,
                platform=PlatformType.JUPITER,
                symbol=symbol,
                side=side,
                quantity=float(res.get("quantity", quantity)) if success else quantity,
                price=fill_price,
                tx_sig=str(res.get("tx_sig", "n/a")) if success else None,
                error=None if success else res.get("error", str(res)),
                raw_response=res,
            )
        except Exception as e:
            return ExecutionResult(
                False, PlatformType.JUPITER, symbol, side, quantity, error=str(e)
            )

    async def _execute_aster(
        self, agent: Any, symbol: str, side: str, quantity: float, is_closing: bool
    ) -> ExecutionResult:
        """Execute on Aster (Monad/Base)."""
        if not self.service.aster or not self.service.aster.client:
            return ExecutionResult(
                False,
                PlatformType.ASTER,
                symbol,
                side,
                quantity,
                error="Aster not initialized",
            )

        try:
            # Aster uses weight/action for perps
            action = "LONG" if side.upper() == "BUY" else "SHORT"

            # Use Aster's default agent ID - the 'agent' parameter is an AI consensus object,
            # not a Aster agent. The Aster client will use its default configured agent.
            aster_agent_id = None  # Let Aster client use its default from config

            if is_closing:
                # Get positions for the default Aster agent
                positions = await self.service.aster.get_perpetual_positions(
                    agent_id=aster_agent_id
                )
                target = next((p for p in positions if p.get("symbol") == symbol), None)
                if target and target.get("batchId"):
                    res = await self.service.aster.close_perpetual_position(
                        target["batchId"], agent_id=aster_agent_id
                    )
                else:
                    return ExecutionResult(
                        False,
                        PlatformType.ASTER,
                        symbol,
                        side,
                        quantity,
                        error="No open position found to close",
                    )
            else:
                # Open with 10% weight as default if not specified
                res = await self.service.aster.open_perpetual_position(
                    symbol=symbol.split("-")[0],
                    action=action,
                    weight=10.0,
                    leverage=1.1,
                    agent_id=aster_agent_id,  # Use default from Aster client
                )

            success = bool(res and (res.get("successful", 0) > 0 or res.get("status") == "ok"))
            return ExecutionResult(
                success=success,
                platform=PlatformType.ASTER,
                symbol=symbol,
                side=side,
                quantity=quantity,
                tx_sig=res.get("batchId") if success else None,
                error=None if success else str(res),
                raw_response=res,
            )
        except Exception as e:
            return ExecutionResult(
                False, PlatformType.ASTER, symbol, side, quantity, error=str(e)
            )

    async def _execute_aster(
        self,
        symbol: str,
        side: str,
        quantity: float,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        market_price: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Execute on Aster using hidden-limit orders with market fallback.

        Uses timeInForce=HIDDEN for stealth entry (not visible in order book).
        Falls back to MARKET if hidden limit fails or price unavailable.
        Then sets STOP_MARKET and TAKE_PROFIT_MARKET for risk management.
        """
        try:
            from .enums import OrderType, WorkingType

            aster_symbol = self.service._normalize_for_aster(symbol)

            # Get builder/feeRate from credentials for Aster Code attribution
            builder = None
            fee_rate = None
            try:
                creds = self.service._credential_manager.get_credentials()
                builder = creds.aster_code_builder_address
                fee_rate = creds.aster_code_fee_rate
            except Exception:
                pass  # Non-critical: proceed without builder attribution

            # Determine entry price for hidden limit order
            if not market_price or market_price <= 0:
                try:
                    ticker = await self.service._exchange_client.get_ticker_price(aster_symbol)
                    market_price = float(ticker.get("price", 0))
                except Exception:
                    market_price = 0

            if market_price and market_price > 0:
                # Use hidden-limit order: set price 0.05% through the book for quick fills
                price_buffer = 0.0005
                if side.upper() == "BUY":
                    limit_price = round(market_price * (1 + price_buffer), 8)
                else:
                    limit_price = round(market_price * (1 - price_buffer), 8)

                logger.info(
                    f"🥷 [ASTER] Hidden-limit {side} {quantity} {aster_symbol} @ {limit_price} "
                    f"(market={market_price}, buffer={price_buffer*100:.2f}%)"
                )

                res = await self.service._exchange_client.place_hidden_limit_order(
                    symbol=aster_symbol,
                    side=side,
                    quantity=quantity,
                    price=limit_price,
                    fill_timeout_seconds=3.0,
                    poll_interval_seconds=0.25,
                    market_fallback=True,
                    builder=builder,
                    fee_rate=fee_rate,
                )
            else:
                # Fallback: no price available, use plain market order
                logger.warning(f"⚠️ [ASTER] No market price for {aster_symbol}, using MARKET order")
                res = await self.service._exchange_client.place_order(
                    symbol=aster_symbol, side=side, order_type=OrderType.MARKET, quantity=quantity
                )

            order_id = res.get("orderId")
            if not order_id:
                raise ValueError(f"No Order ID returned: {res}")

            filled_qty = float(res.get("executedQty", 0.0))
            final_status = res.get("status", "UNKNOWN")

            # For hidden-limit orders, the fill-wait is already handled inside
            # place_hidden_limit_order. Only poll if we used plain MARKET.
            if final_status not in ("FILLED", "PARTIALLY_FILLED"):
                attempts = 0
                while (
                    final_status not in ["FILLED", "CANCELED", "REJECTED", "EXPIRED"]
                    and attempts < 10
                ):
                    await asyncio.sleep(0.5)
                    check_res = await self.service._exchange_client.get_order(
                        symbol=aster_symbol, order_id=str(order_id)
                    )
                    final_status = check_res.get("status", final_status)
                    filled_qty = float(check_res.get("executedQty", filled_qty))
                    attempts += 1
                    logger.debug(f"Verifying order {order_id}: {final_status}")

            is_filled = final_status in ("FILLED", "PARTIALLY_FILLED") and filled_qty > 0
            success = is_filled
            avg_price = float(res.get("avgPrice", res.get("price", 0.0)))

            if not success:
                logger.warning(f"⚠️ Order {order_id} verification failed. Status: {final_status}")

            # ---------------------------------------------------------
            # RISK MANAGEMENT: Place Native SL/TP Orders on Aster
            # ---------------------------------------------------------
            if success and (tp_price or sl_price):
                # For closing orders, we reverse the side
                close_side = "SELL" if side.upper() == "BUY" else "BUY"

                # Use actual filled quantity for SL/TP orders
                sl_tp_qty = filled_qty if filled_qty > 0 else quantity

                # Place Take Profit order (TAKE_PROFIT_MARKET)
                if tp_price:
                    try:
                        tp_res = await self.service._exchange_client.place_order(
                            symbol=aster_symbol,
                            side=close_side,
                            order_type=OrderType.TAKE_PROFIT_MARKET,
                            quantity=sl_tp_qty,
                            stop_price=tp_price,
                            reduce_only=True,
                            working_type=WorkingType.MARK_PRICE,
                        )
                        logger.info(f"✅ [ASTER] TP order placed @ ${tp_price:.2f} | OrderId: {tp_res.get('orderId')}")
                    except Exception as tp_err:
                        logger.error(f"⚠️ [ASTER] Failed to place TP for {symbol}: {tp_err}")

                # Place Stop Loss order (STOP_MARKET)
                if sl_price:
                    try:
                        sl_res = await self.service._exchange_client.place_order(
                            symbol=aster_symbol,
                            side=close_side,
                            order_type=OrderType.STOP_MARKET,
                            quantity=sl_tp_qty,
                            stop_price=sl_price,
                            reduce_only=True,
                            working_type=WorkingType.MARK_PRICE,
                        )
                        logger.info(f"✅ [ASTER] SL order placed @ ${sl_price:.2f} | OrderId: {sl_res.get('orderId')}")
                    except Exception as sl_err:
                        logger.error(f"⚠️ [ASTER] Failed to place SL for {symbol}: {sl_err}")

            return ExecutionResult(
                success=success,
                platform=PlatformType.ASTER,
                symbol=symbol,
                side=side,
                quantity=filled_qty if filled_qty > 0 else quantity,
                price=avg_price,
                tx_sig=str(order_id),
                error=None if success else f"Verification Failed: Status {final_status}",
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
