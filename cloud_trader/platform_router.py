"""
Platform Router - Universal Execution Layer for Sapphire.
Handles intelligent routing between Aster, Drift, Hyperliquid, Symphony, and Lighter.

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
from .definitions import DRIFT_SYMBOLS, HYPERLIQUID_SYMBOLS, SYMPHONY_SYMBOLS, LIGHTER_SYMBOLS, JUPITER_SYMBOLS
from .logger import get_logger

logger = get_logger(__name__)


class PlatformType(Enum):
    ASTER = "aster"
    DRIFT = "drift"
    HYPERLIQUID = "hyperliquid"
    SYMPHONY = "symphony"
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
        2. Hyperliquid/Drift for US-compatible trading (Aster blocked in US)
        3. Symphony for exclusive symbols
        4. Fallback to Aster (if region allows)
        """
        # Strategy 0: MICROSERVICE PLATFORM ISOLATION
        # In microservices mode, each service only routes to its designated platform
        enabled_platforms = []
        if hasattr(self.service, 'config'):
            config = self.service.config
            logger.debug(f"🔍 [ROUTER] Checking config for enabled platforms...")
            if getattr(config, 'enable_hyperliquid', False):
                enabled_platforms.append(PlatformType.HYPERLIQUID)
                logger.debug(f"  ✓ Hyperliquid enabled")
            if getattr(config, 'enable_lighter', False):
                enabled_platforms.append(PlatformType.LIGHTER)
                logger.debug(f"  ✓ Lighter enabled")
            if getattr(config, 'enable_drift', False):
                enabled_platforms.append(PlatformType.DRIFT)
                logger.debug(f"  ✓ Drift enabled")
            if getattr(config, 'enable_aster', False):
                enabled_platforms.append(PlatformType.ASTER)
                logger.debug(f"  ✓ Aster enabled")
            if getattr(config, 'enable_symphony', False):
                enabled_platforms.append(PlatformType.SYMPHONY)
                logger.debug(f"  ✓ Symphony enabled")

            logger.info(f"🔍 [ROUTER] Enabled platforms: {[p.value for p in enabled_platforms]} (count={len(enabled_platforms)})")

            # If ONLY ONE platform is enabled, route to that platform EXCLUSIVELY
            if len(enabled_platforms) == 1:
                logger.info(f"🎯 [MICROSERVICE MODE] Routing {symbol} to {enabled_platforms[0].value} (only enabled platform)")
                return enabled_platforms[0]

            # If NO platforms enabled, log warning and continue with normal routing
            if len(enabled_platforms) == 0:
                logger.warning(f"⚠️ No platforms enabled in config, using default routing logic")

        # Strategy 1: Agent Explicit System Preference (EXCEPT Aster - US blocked)
        if hasattr(agent, "system") and agent.system:
            target_sys = agent.system.lower()
            if target_sys == "drift" and symbol in DRIFT_SYMBOLS:
                # Only return if drift is enabled (or no platform restrictions)
                if not enabled_platforms or PlatformType.DRIFT in enabled_platforms:
                    return PlatformType.DRIFT
            if target_sys == "hyperliquid" and symbol in HYPERLIQUID_SYMBOLS:
                if not enabled_platforms or PlatformType.HYPERLIQUID in enabled_platforms:
                    return PlatformType.HYPERLIQUID
            if target_sys == "symphony" and symbol in SYMPHONY_SYMBOLS:
                if not enabled_platforms or PlatformType.SYMPHONY in enabled_platforms:
                    return PlatformType.SYMPHONY
            # CRITICAL FIX: Ignore agent.system="aster" - blocked in US region
            # Fall through to Strategy 2 for smart US-compatible routing
            if target_sys == "aster":
                logger.info(f"🔄 Agent requested Aster for {symbol}, routing to US-compatible exchange instead")
                # Don't return - fall through to Strategy 2

        # Strategy 2: Prefer US-compatible exchanges (Hyperliquid/Drift)
        # Check if symbol is available on Hyperliquid (highest liquidity for majors)
        if symbol in HYPERLIQUID_SYMBOLS:
            if not enabled_platforms or PlatformType.HYPERLIQUID in enabled_platforms:
                return PlatformType.HYPERLIQUID

        # Check if symbol is available on Drift (Solana perps)
        if symbol in DRIFT_SYMBOLS:
            if not enabled_platforms or PlatformType.DRIFT in enabled_platforms:
                return PlatformType.DRIFT

        # Symphony for exclusive Monad ecosystem tokens
        if symbol in SYMPHONY_SYMBOLS:
            if not enabled_platforms or PlatformType.SYMPHONY in enabled_platforms:
                return PlatformType.SYMPHONY

        # Strategy 3A: Route perpetual futures to Drift (Solana native perps)
        from .definitions import DRIFT_PERP_SYMBOLS
        if symbol in DRIFT_PERP_SYMBOLS:
            if not enabled_platforms or PlatformType.DRIFT in enabled_platforms:
                logger.info(f"🎯 Routing {symbol} to Drift (Solana perpetuals)")
                return PlatformType.DRIFT

        # Strategy 3B: Route spot swaps to Jupiter (Solana DEX aggregator)
        from .definitions import JUPITER_SPOT_SYMBOLS
        if symbol in JUPITER_SPOT_SYMBOLS:
            if not enabled_platforms or PlatformType.JUPITER in enabled_platforms:
                logger.info(f"🔄 Routing {symbol} to Jupiter (best Solana DEX prices)")
                return PlatformType.JUPITER

        # Strategy 4: Try Lighter for supported pairs (L2 execution)
        if symbol in LIGHTER_SYMBOLS or symbol.replace("BTC", "WBTC").replace("ETH", "WETH") in LIGHTER_SYMBOLS:
            if not enabled_platforms or PlatformType.LIGHTER in enabled_platforms:
                return PlatformType.LIGHTER

        # Strategy 5: Fallback to Hyperliquid for major pairs (BTC, ETH, SOL)
        # This avoids Aster's US region block
        major_symbols = ["BTC-USDC", "ETH-USDC", "SOL-USDC", "BTCUSDT", "ETHUSDT", "SOLUSDT"]
        if any(major in symbol.upper() for major in major_symbols):
            # Prefer Jupiter for SOL pairs (best Solana DEX aggregation)
            if "SOL" in symbol.upper():
                if not enabled_platforms or PlatformType.JUPITER in enabled_platforms:
                    logger.info(f"🔄 Routing {symbol} to Jupiter (optimal for SOL)")
                    return PlatformType.JUPITER
            # Otherwise use Hyperliquid
            if not enabled_platforms or PlatformType.HYPERLIQUID in enabled_platforms:
                logger.info(f"🔄 Routing {symbol} to Hyperliquid (Aster blocked in US)")
                return PlatformType.HYPERLIQUID

        # Last resort: Try Aster (will fail with -5019 in US) - only if enabled
        if not enabled_platforms or PlatformType.ASTER in enabled_platforms:
            logger.warning(f"⚠️ Defaulting to Aster for {symbol} (may fail in US region)")
            return PlatformType.ASTER

        # If we get here, no suitable platform found - return first enabled platform
        if enabled_platforms:
            logger.warning(f"⚠️ No ideal platform for {symbol}, using {enabled_platforms[0].value}")
            return enabled_platforms[0]

        # Absolute fallback
        return PlatformType.HYPERLIQUID

    def _get_fallback_platform(
        self, failed_platform: PlatformType, symbol: str
    ) -> Optional[PlatformType]:
        """
        Determine the best fallback platform when the primary platform fails.

        NEW Fallback hierarchy (US-compatible):
        1. Hyperliquid (US-compatible, high liquidity)
        2. Drift (US-compatible, Solana perps)
        3. Symphony (if symbol supported)
        4. Aster (blocked in US, last resort)
        """
        # If Aster failed (likely US region block), try US-compatible exchanges
        if failed_platform == PlatformType.ASTER:
            # Prefer Jupiter for Solana tokens
            if symbol in JUPITER_SYMBOLS:
                logger.info(f"🔄 Aster failed, falling back to Jupiter for {symbol}")
                return PlatformType.JUPITER
            if symbol in HYPERLIQUID_SYMBOLS:
                logger.info(f"🔄 Aster failed, falling back to Hyperliquid for {symbol}")
                return PlatformType.HYPERLIQUID
            if symbol in DRIFT_SYMBOLS:
                logger.info(f"🔄 Aster failed, falling back to Drift for {symbol}")
                return PlatformType.DRIFT
            if symbol in SYMPHONY_SYMBOLS:
                return PlatformType.SYMPHONY
            return None

        # If Hyperliquid failed, try Drift
        if failed_platform == PlatformType.HYPERLIQUID:
            if symbol in DRIFT_SYMBOLS:
                logger.info(f"🔄 Hyperliquid failed, falling back to Drift for {symbol}")
                return PlatformType.DRIFT
            if symbol in SYMPHONY_SYMBOLS:
                return PlatformType.SYMPHONY
            # DO NOT fallback to Aster in US region
            return None

        # If Drift failed, try Hyperliquid
        if failed_platform == PlatformType.DRIFT:
            if symbol in HYPERLIQUID_SYMBOLS:
                logger.info(f"🔄 Drift failed, falling back to Hyperliquid for {symbol}")
                return PlatformType.HYPERLIQUID
            if symbol in SYMPHONY_SYMBOLS:
                return PlatformType.SYMPHONY
            # DO NOT fallback to Aster in US region
            return None

        # If Symphony failed, try Hyperliquid or Drift
        if failed_platform == PlatformType.SYMPHONY:
            if symbol in HYPERLIQUID_SYMBOLS:
                return PlatformType.HYPERLIQUID
            if symbol in DRIFT_SYMBOLS:
                return PlatformType.DRIFT
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

        # --- PRECISION NORMALIZATION & OBFUSCATION ---
        # Import precision normalizer
        from .precision_normalizer import get_precision_normalizer
        import random

        # 1. Jitter: Reduced random delay for higher efficiency (was 0.1-1.5s)
        jitter = random.uniform(0.05, 0.2)
        logger.debug(f"⚡ [ROUTER] Speed optimized: {jitter:.3f}s jitter")
        await asyncio.sleep(jitter)

        # 2. Fuzzing: Slightly adjust quantity to avoid round-number patterns
        quantity_fuzz = random.uniform(0.98, 1.02)  # +/- 2%
        fuzzed_quantity = quantity * quantity_fuzz

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
                if platform == PlatformType.DRIFT:
                    result = await breaker.call(
                        self._execute_drift, symbol, side, formatted_quantity, tp_price, sl_price
                    )
                elif platform == PlatformType.HYPERLIQUID:
                    result = await breaker.call(
                        self._execute_hyperliquid, symbol, side, formatted_quantity, tp_price, sl_price
                    )
                elif platform == PlatformType.SYMPHONY:
                    result = await breaker.call(
                        self._execute_symphony, agent, symbol, side, formatted_quantity, is_closing
                    )
                elif platform == PlatformType.JUPITER:
                    result = await breaker.call(
                        self._execute_jupiter, symbol, side, formatted_quantity
                    )
                else:
                    result = await breaker.call(
                        self._execute_aster, symbol, side, formatted_quantity, tp_price, sl_price
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
                            self._execute_drift, symbol, side, formatted_quantity, tp_price, sl_price
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
                    elif fallback_platform == PlatformType.JUPITER:
                        result = await fallback_breaker.call(
                            self._execute_jupiter, symbol, side, formatted_quantity
                        )
                    elif fallback_platform == PlatformType.HYPERLIQUID:
                        result = await fallback_breaker.call(
                            self._execute_hyperliquid, symbol, side, formatted_quantity, tp_price, sl_price
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

    async def _execute_drift(
        self,
        symbol: str,
        side: str,
        quantity: float,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Execute on Drift Protocol (Solana Perpetuals).

        Uses Drift's native perpetual futures for leveraged trading.
        Supports stop-loss and take-profit orders.
        """
        if not self.service.drift or not self.service.drift.is_initialized:
            return ExecutionResult(
                False, PlatformType.DRIFT, symbol, side, quantity, error="Drift not initialized"
            )

        try:
            # Determine if this is opening or closing a position
            direction = "long" if side.upper() == "BUY" else "short"

            # Check for existing position
            existing_position = await self.service.drift.get_position(symbol)
            is_closing = existing_position and existing_position.get("amount", 0) != 0

            if is_closing:
                # Close existing position
                logger.info(f"🔒 Closing Drift position: {symbol}")
                res = await self.service.drift.close_perp_position(
                    market=symbol,
                    size=quantity,
                )
            else:
                # Open new position with leverage
                logger.info(f"🚀 Opening Drift {direction} position: {quantity} {symbol}")
                res = await self.service.drift.open_perp_position(
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
                    market_info = await self.service.drift.get_perp_market(symbol)
                    fill_price = market_info.get("oracle_price", 0)

            return ExecutionResult(
                success=success,
                platform=PlatformType.DRIFT,
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=fill_price,
                tx_sig=res.get("tx_sig") if success else None,
                error=None if success else res.get("error", "Unknown error"),
                raw_response=res,
            )
        except Exception as e:
            logger.error(f"❌ Drift execution error: {e}")
            return ExecutionResult(
                False, PlatformType.DRIFT, symbol, side, quantity, error=str(e)
            )

    async def _execute_hyperliquid(
        self, 
        symbol: str, 
        side: str, 
        quantity: float,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
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
            # Hyperliquid uses symbol directly (no parsing needed)
            # The client will handle symbol normalization
            res = await self.service.hl_client.place_order(
                symbol=symbol,
                side=side,
                quantity=quantity,
                order_type="MARKET"
            )
            success = bool(res and res.get("status") == "ok")
            
            # Extract fill price from SDK response
            # SDK returns price in: data.fills[0].avgPx or data.statuses[0].filled.avgPx
            fill_price = 0.0
            if success and res:
                try:
                    data = res.get("data", {})
                    if data:
                        # Try filled order format
                        filled = data.get("filled", {})
                        if filled:
                            fill_price = float(filled.get("avgPx", 0))
                        # Or try statuses format
                        elif "statuses" in res.get("response", {}):
                            statuses = res.get("response", {}).get("data", {}).get("statuses", [])
                            if statuses:
                                filled_info = statuses[0].get("filled", {})
                                if filled_info:
                                    fill_price = float(filled_info.get("avgPx", 0))
                except (ValueError, TypeError, KeyError):
                    pass
                    
                    pass
                    
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
                platform=PlatformType.HYPERLIQUID,
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
                False, PlatformType.HYPERLIQUID, symbol, side, quantity, error=str(e)
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
                # Get positions for the specific agent (MILF or AGDG)
                agent_symphony_id = agent.id if agent else None
                positions = await self.service.symphony.get_perpetual_positions(
                    agent_id=agent_symphony_id
                )
                target = next((p for p in positions if p.get("symbol") == symbol), None)
                if target and target.get("batchId"):
                    res = await self.service.symphony.close_perpetual_position(
                        target["batchId"], agent_id=agent_symphony_id
                    )
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

    async def _execute_aster(
        self,
        symbol: str,
        side: str,
        quantity: float,
        tp_price: Optional[float] = None,
        sl_price: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Execute on Aster (Main Liquidity) with native SL/TP orders.

        Places market order first, then sets STOP_MARKET and TAKE_PROFIT_MARKET
        orders for risk management (positions close automatically on exchange).
        """
        try:
            from .enums import OrderType, WorkingType

            aster_symbol = self.service._normalize_for_aster(symbol)

            # CRITICAL FIX: Use place_order instead of create_order
            # CRITICAL FIX: Use OrderType.MARKET enum
            res = await self.service._exchange_client.place_order(
                symbol=aster_symbol, side=side, order_type=OrderType.MARKET, quantity=quantity
            )

            # CRITICAL CHECK: Verify FILL with Polling
            # Aster/Binance API might return NEW if not immediately filled
            order_id = res.get("orderId")
            if not order_id:
                raise ValueError(f"No Order ID returned: {res}")

            # Polling Verification (Max 5 seconds)
            final_status = res.get("status", "UNKNOWN")
            filled_qty = float(res.get("executedQty", 0.0))
            attempts = 0

            while (
                final_status not in ["FILLED", "CANCELED", "REJECTED", "EXPIRED"] and attempts < 10
            ):
                await asyncio.sleep(0.5)
                # Check order status
                check_res = await self.service._exchange_client.get_order(
                    symbol=aster_symbol, orderId=order_id
                )
                final_status = check_res.get("status", final_status)
                filled_qty = float(check_res.get("executedQty", filled_qty))
                attempts += 1
                logger.debug(f"🕵️ Verifying order {order_id}: {final_status}")

            is_filled = final_status == "FILLED"

            # If still not filled after 5s, we might consider it a partial success or failure depending on strictness
            # User asked for "100% verified completed", so if not FILLED, we treat as incomplete.

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
