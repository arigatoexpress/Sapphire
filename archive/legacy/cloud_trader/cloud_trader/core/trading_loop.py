"""
Sapphire V2 Trading Loop
Extracted from TradingService - focused solely on the trading cycle.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ..agents.agent_orchestrator import AgentOrchestrator
    from ..execution.position_tracker import PositionTracker
    from ..platform_router import PlatformRouter
    from .monitoring import MonitoringService
    from .orchestrator import TradingOrchestrator

logger = logging.getLogger(__name__)


@dataclass
class CycleResult:
    """Result of a single trading cycle."""

    symbols_scanned: int
    opportunities_found: int
    trades_executed: int
    errors: List[str]
    duration_ms: int


class TradingLoop:
    """
    The core trading loop - scans markets, generates signals, executes trades.

    Single responsibility: Run the trading cycle.
    """

    def __init__(
        self,
        orchestrator: "TradingOrchestrator",
        agents: "AgentOrchestrator",
        positions: "PositionTracker",
        router: "PlatformRouter",
        monitoring: "MonitoringService",
    ):
        self.orchestrator = orchestrator
        self.agents = agents
        self.positions = positions
        self.router = router
        self.monitoring = monitoring

        # Configuration
        # Watchlist includes tokens for all platforms
        # Jupiter (Solana DEX): SOL, BONK, WIF, JUP, JTO
        # Aster (Solana Perps): SOL-PERP, BTC-PERP
        # Aster/Lighter (Perps): BTC-USDC, ETH-USDC, SOL-USDC
        # Aster (Monad/Base): ETH-USDC, MON-USDC, DEGEN-USDC
        self.watchlist: List[str] = [
            # Solana tokens for Jupiter DEX swaps
            "SOL-USDC",
            "BONK-USDC",
            "WIF-USDC",
            "JUP-USDC",
            "JTO-USDC",
            # Major pairs for Aster/Lighter perps
            "BTC-USDC",
            "ETH-USDC",
            # Monad/Base tokens for Aster
            "MON-USDC",
            "DEGEN-USDC",
        ]
        self.max_positions = 5

        # State
        self._cycle_count = 0
        self._running = False

        logger.info(f"📊 TradingLoop initialized with {len(self.watchlist)} symbols")

    async def run_cycle(self) -> CycleResult:
        """Execute a single trading cycle."""
        import time

        start_time = time.time()

        self._cycle_count += 1
        errors = []
        opportunities = 0
        trades = 0

        logger.info(f"🔄 Starting cycle #{self._cycle_count}")

        try:
            # 1. Get current positions
            current_positions = await self.positions.get_all()
            open_symbols = set(current_positions.keys())

            # 2. Check for exit signals on open positions
            # 2a. First check trailing stops (faster check)
            try:
                prices = {}
                for symbol in current_positions.keys():
                    try:
                        price = await self._get_current_price(symbol)
                        if price and price > 0:
                            prices[symbol] = price
                    except:
                        pass

                if prices:
                    triggered_stops = await self.positions.check_trailing_stops(prices)
                    for stop in triggered_stops:
                        symbol = stop["symbol"]
                        if symbol in current_positions:
                            await self._execute_exit(
                                symbol,
                                current_positions[symbol],
                                f"Trailing stop @ ${stop['stop_price']:.2f} (PnL: {stop['pnl_pct']:.1f}%)"
                            )
                            trades += 1
                            open_symbols.discard(symbol)
            except Exception as e:
                errors.append(f"Trailing stop check: {e}")

            # 2b. Then check regular exit signals
            for symbol, position in current_positions.items():
                if symbol not in open_symbols:  # Already closed by trailing stop
                    continue
                try:
                    should_exit, reason = await self._check_exit_signal(symbol, position)
                    if should_exit:
                        await self._execute_exit(symbol, position, reason)
                        trades += 1
                except Exception as e:
                    errors.append(f"Exit check {symbol}: {e}")

            # 3. Scan for entry opportunities
            if len(open_symbols) < self.max_positions:
                available_slots = self.max_positions - len(open_symbols)

                for symbol in self.watchlist:
                    if symbol in open_symbols:
                        continue
                    if available_slots <= 0:
                        break

                    try:
                        # Get consensus from all agents
                        consensus = await self.agents.get_consensus(symbol)

                        if (
                            consensus and consensus.confidence >= 0.40
                        ):  # Lowered from 0.65 for testing
                            opportunities += 1

                            # Execute if actionable
                            if consensus.signal in ["BUY", "SELL"]:
                                success = await self._execute_entry(symbol, consensus)
                                if success:
                                    trades += 1
                                    available_slots -= 1

                    except Exception as e:
                        errors.append(f"Entry scan {symbol}: {e}")

            duration_ms = int((time.time() - start_time) * 1000)

            result = CycleResult(
                symbols_scanned=len(self.watchlist),
                opportunities_found=opportunities,
                trades_executed=trades,
                errors=errors,
                duration_ms=duration_ms,
            )

            # Report to monitoring
            self.monitoring.report_cycle(result)

            logger.info(
                f"✅ Cycle #{self._cycle_count} complete: "
                f"{len(self.watchlist)} scanned, {opportunities} opportunities, "
                f"{trades} trades, {len(errors)} errors, {duration_ms}ms"
            )

            return result

        except Exception as e:
            logger.error(f"❌ Cycle error: {e}")
            duration_ms = int((time.time() - start_time) * 1000)
            return CycleResult(
                symbols_scanned=0,
                opportunities_found=0,
                trades_executed=0,
                errors=[str(e)],
                duration_ms=duration_ms,
            )

    async def _check_exit_signal(self, symbol: str, position: Dict) -> tuple[bool, str]:
        """Check if we should exit a position."""
        # Get exit recommendation from agents
        consensus = await self.agents.get_consensus(symbol, context="exit_check")

        # Check for stop loss / take profit
        entry_price = position.get("entry_price", 0)
        current_price = await self._get_current_price(symbol)

        if entry_price > 0 and current_price > 0:
            pnl_pct = (current_price - entry_price) / entry_price

            # Take profit at 5%
            if pnl_pct >= 0.05:
                return True, f"Take profit: {pnl_pct:.1%}"

            # Stop loss at -3%
            if pnl_pct <= -0.03:
                return True, f"Stop loss: {pnl_pct:.1%}"

        # Check agent consensus for exit
        if consensus and consensus.signal in ["SELL", "EXIT"]:
            if consensus.confidence >= 0.7:
                return True, f"Agent consensus: {consensus.reasoning}"

        return False, ""

    async def _execute_entry(self, symbol: str, consensus) -> bool:
        """Execute an entry trade."""
        try:
            # Calculate position size (Dynamic) based on REAL platform balance
            # Use confidence from consensus if available, else default 0.5
            confidence = getattr(consensus, "confidence", 0.5)
            # Ensure confidence is float
            try:
                confidence = float(confidence)
            except (ValueError, TypeError):
                confidence = 0.5

            # Determine platform from agent/consensus
            platform = getattr(consensus, "platform", None) or getattr(consensus, "agent_id", "").split("-")[0] if hasattr(consensus, "agent_id") else None

            size = await self._calculate_position_size(symbol, confidence, platform=platform)

            # Calculate TP/SL prices using Adaptive TP/SL Calculator (ATR-based)
            current_price = await self._get_current_price(symbol)
            tp_price = None
            sl_price = None

            if current_price > 0:
                try:
                    # Use adaptive ATR-based TP/SL calculator
                    from ..adaptive_tpsl import get_adaptive_tpsl_calculator

                    calculator = get_adaptive_tpsl_calculator()
                    agent_id = getattr(consensus, "agent_id", None)

                    adaptive_result = await calculator.calculate(
                        symbol=symbol,
                        side=consensus.signal,
                        entry_price=current_price,
                        agent_id=agent_id,
                        consensus_confidence=confidence,
                    )

                    tp_price = adaptive_result.tp_price
                    sl_price = adaptive_result.sl_price

                    logger.info(
                        f"📊 ATR-based TP/SL for {symbol}: "
                        f"TP={adaptive_result.tp_pct:.1%} (${tp_price:.2f}) | "
                        f"SL={adaptive_result.sl_pct:.1%} (${sl_price:.2f}) | "
                        f"{adaptive_result.reasoning}"
                    )

                except Exception as adaptive_err:
                    # Fallback to static TP/SL if adaptive fails
                    logger.warning(f"⚠️ Adaptive TP/SL failed, using static: {adaptive_err}")
                    tp_pct = 0.05
                    sl_pct = 0.03

                    if consensus.signal == "BUY":
                        tp_price = current_price * (1 + tp_pct)
                        sl_price = current_price * (1 - sl_pct)
                    elif consensus.signal == "SELL":
                        tp_price = current_price * (1 - tp_pct)
                        sl_price = current_price * (1 + sl_pct)

                # Round to 2 decimals for now (precision normalizer in router will handle strict precision)
                tp_price = round(tp_price, 2) if tp_price else None
                sl_price = round(sl_price, 2) if sl_price else None

            # Execute via platform router
            result = await self.router.execute_trade(
                agent=consensus,  # Pass consensus as agent for tracking
                symbol=symbol,
                side=consensus.signal,
                quantity=size,
                thesis=consensus.reasoning,
                is_closing=False,
                tp_price=tp_price,
                sl_price=sl_price,
            )

            # CRITICAL: Verify trade actually executed before notifying
            from .trade_verification import TradeVerificationService

            verifier = TradeVerificationService(self.orchestrator)
            verified_trade = await verifier.verify_trade(
                execution_result=result,
                symbol=symbol,
                side=consensus.signal,
                quantity=result.quantity,
            )

            if verified_trade:
                # Track position
                await self.positions.open(
                    symbol=symbol,
                    side=consensus.signal,
                    quantity=verified_trade.quantity,
                    entry_price=verified_trade.fill_price,
                    platform=verified_trade.platform,
                )

                # Notify monitoring with VERIFIED trade data
                await self.monitoring.notify_trade(
                    {
                        "symbol": verified_trade.symbol,
                        "side": verified_trade.side,
                        "price": verified_trade.fill_price,
                        "quantity": verified_trade.quantity,
                        "platform": verified_trade.platform,
                        "agent_id": (
                            consensus.agent_id if hasattr(consensus, "agent_id") else "swarm"
                        ),
                        "agent_name": (
                            consensus.agent_name if hasattr(consensus, "agent_name") else "AI Swarm"
                        ),
                        # Account & position data
                        "account_equity": verified_trade.account_equity,
                        "account_margin": verified_trade.account_margin,
                        "position_size": verified_trade.position_size,
                        "position_unrealized_pnl": verified_trade.position_unrealized_pnl,
                        "liquidation_price": verified_trade.liquidation_price,
                        "leverage": verified_trade.position_leverage,
                        "notional_value": verified_trade.notional_value,
                        "actual_usd_value": verified_trade.actual_usd_value,
                    }
                )

                logger.info(
                    f"✅ Opened {consensus.signal} {symbol} @ {verified_trade.fill_price} "
                    f"(equity=${verified_trade.account_equity:.2f})"
                )
                return True
            else:
                logger.warning(f"❌ Entry verification FAILED: {result.error or 'Trade could not be verified'}")
                return False

        except Exception as e:
            logger.error(f"❌ Entry error {symbol}: {e}")
            return False

    async def _execute_exit(self, symbol: str, position: Dict, reason: str) -> bool:
        """Execute an exit trade."""
        try:
            side = "SELL" if position.get("side") == "BUY" else "BUY"

            result = await self.router.execute_trade(
                agent=None,
                symbol=symbol,
                side=side,
                quantity=position.get("quantity", 0),
                thesis=reason,
                is_closing=True,
            )

            if result.success:
                await self.positions.close(symbol)
                # Notify monitoring
                await self.monitoring.notify_trade(
                    {
                        "symbol": symbol,
                        "side": side,
                        "price": result.price,
                        "quantity": result.quantity,
                        "platform": result.platform.value,
                        "agent_id": "orchestrator",
                        "agent_name": "Risk Manager",
                        "reason": reason,
                    }
                )

                logger.info(f"✅ Closed {symbol}: {reason}")
                return True
            else:
                logger.warning(f"❌ Exit failed: {result.error}")
                return False

        except Exception as e:
            logger.error(f"❌ Exit error {symbol}: {e}")
            return False

    async def _calculate_position_size(self, symbol: str, confidence: float = 0.5, platform: str = None) -> float:
        """
        Calculate position size based on REAL account balance and portfolio risk management.

        CRITICAL: Uses actual platform account balance, not hardcoded values

        Risk Framework:
        1. Base size from REAL portfolio allocation (max 10% per position)
        2. Confidence multiplier (0.5x to 2x)
        3. Drawdown protection (reduce size after losses)
        4. Exposure limits (cap total portfolio exposure)
        5. Correlation adjustment (reduce for correlated assets)

        Returns: Position size in USD
        """
        # === Get REAL Account Balance ===
        from .account_balance_manager import AccountBalanceManager

        balance_manager = AccountBalanceManager(self.orchestrator)

        # Get real balance for the platform
        if platform:
            real_balance = await balance_manager.get_platform_balance(platform)
        else:
            # If no platform specified, use total balance
            real_balance = await balance_manager.get_total_balance()

        # Fallback to conservative estimate if balance unavailable
        if not real_balance or real_balance <= 0:
            logger.warning(f"⚠️ Could not fetch real balance for {platform}, using fallback $50")
            real_balance = 50.0

        base_portfolio_value = real_balance
        logger.info(f"💰 Using REAL balance: ${base_portfolio_value:.2f} for {platform or 'total'}")

        # === Risk Configuration ===
        max_position_pct = 0.10  # Max 10% per position
        max_total_exposure_pct = 0.50  # Max 50% total exposure
        drawdown_threshold = 0.05  # Start reducing at 5% drawdown
        max_drawdown_reduction = 0.50  # Reduce size up to 50% at max drawdown

        # Min/Max absolute limits
        min_position_size = 5.0  # Reduced minimum to support small accounts
        max_position_size = base_portfolio_value * max_total_exposure_pct  # Max 50% of balance

        # === Step 1: Calculate base size from REAL portfolio allocation ===
        base_size = base_portfolio_value * max_position_pct  # 10% of REAL balance

        # === Step 2: Apply confidence multiplier ===
        # Confidence 0.0 -> 0.5x, 0.5 -> 1.25x, 1.0 -> 2.0x
        confidence_multiplier = 0.5 + (confidence * 1.5)
        sized_amount = base_size * confidence_multiplier

        # === Step 3: Drawdown protection ===
        drawdown_multiplier = 1.0
        try:
            stats = self.positions.get_stats()
            total_pnl = stats.get("total_pnl", 0) + stats.get("unrealized_pnl", 0)

            if total_pnl < 0:
                # Calculate drawdown as percentage of portfolio
                drawdown_pct = abs(total_pnl) / base_portfolio_value

                if drawdown_pct > drawdown_threshold:
                    # Linear reduction: 5% DD = 0% reduction, 15% DD = 50% reduction
                    reduction_factor = min(
                        (drawdown_pct - drawdown_threshold) / 0.10,
                        max_drawdown_reduction
                    )
                    drawdown_multiplier = 1.0 - reduction_factor
                    logger.info(
                        f"📉 Drawdown protection: {drawdown_pct:.1%} DD -> "
                        f"{drawdown_multiplier:.1%} size multiplier"
                    )
        except Exception as e:
            logger.warning(f"⚠️ Could not calculate drawdown: {e}")

        sized_amount *= drawdown_multiplier

        # === Step 4: Portfolio exposure limit ===
        exposure_multiplier = 1.0
        try:
            current_exposure = self.positions.get_total_exposure()
            max_exposure = base_portfolio_value * max_total_exposure_pct

            if current_exposure > 0:
                remaining_capacity = max(0, max_exposure - current_exposure)
                if remaining_capacity < sized_amount:
                    exposure_multiplier = remaining_capacity / sized_amount
                    logger.info(
                        f"📊 Exposure limit: ${current_exposure:.0f} of ${max_exposure:.0f} used -> "
                        f"{exposure_multiplier:.1%} size allowed"
                    )
        except Exception as e:
            logger.warning(f"⚠️ Could not calculate exposure: {e}")

        sized_amount *= exposure_multiplier

        # === Step 5: Correlation adjustment ===
        # Reduce size for correlated assets (same base asset family)
        correlation_multiplier = 1.0
        try:
            current_positions = await self.positions.get_all()
            base_asset = symbol.split("-")[0] if "-" in symbol else symbol[:3]

            # Group similar assets (BTC, ETH, SOL are uncorrelated; meme coins correlated)
            high_correlation_groups = {
                "MEME": ["DEGEN", "BRETT", "PEPE", "WIF", "BONK"],
                "DEFI": ["JUP", "AAVE", "UNI", "SUSHI"],
                "L1": ["SOL", "AVAX", "NEAR", "APT"],
            }

            # Find which group our symbol belongs to
            symbol_group = None
            for group, members in high_correlation_groups.items():
                if base_asset in members:
                    symbol_group = group
                    break

            if symbol_group:
                # Count existing positions in same correlation group
                correlated_count = 0
                for pos_symbol in current_positions.keys():
                    pos_base = pos_symbol.split("-")[0] if "-" in pos_symbol else pos_symbol[:3]
                    if pos_base in high_correlation_groups.get(symbol_group, []):
                        correlated_count += 1

                if correlated_count > 0:
                    # Reduce size by 25% per existing correlated position
                    correlation_multiplier = max(0.25, 1.0 - (correlated_count * 0.25))
                    logger.info(
                        f"🔗 Correlation adjustment: {correlated_count} correlated {symbol_group} positions -> "
                        f"{correlation_multiplier:.0%} size"
                    )
        except Exception as e:
            logger.warning(f"⚠️ Could not calculate correlation: {e}")

        sized_amount *= correlation_multiplier

        # === Final: Apply absolute limits ===
        final_size = max(min_position_size, min(sized_amount, max_position_size))

        # Skip if size is too small after all adjustments
        if sized_amount < min_position_size * 0.5:
            logger.warning(
                f"⚠️ Position size too small after risk adjustments: ${sized_amount:.2f} -> "
                f"Using minimum ${min_position_size:.0f}"
            )

        logger.info(
            f"💰 Risk-based sizing for {symbol}: "
            f"Base ${base_size:.0f} × Conf {confidence_multiplier:.2f} × "
            f"DD {drawdown_multiplier:.2f} × Exp {exposure_multiplier:.2f} × "
            f"Corr {correlation_multiplier:.2f} = ${final_size:.2f}"
        )

        return final_size

    async def _get_current_price(self, symbol: str) -> float:
        """Get current market price from any available platform client."""
        try:
            if not self.orchestrator:
                logger.warning(f"⚠️ Cannot fetch price for {symbol}: No orchestrator")
                return 0.0

            # Try Jupiter first (for Solana tokens like SOL, BONK, etc.)
            if self.orchestrator.jupiter_client:
                try:
                    # Jupiter has get_current_price() method
                    price_decimal = await self.orchestrator.jupiter_client.get_current_price(symbol)
                    if price_decimal and price_decimal > 0:
                        price = float(price_decimal)
                        logger.info(f"📊 Jupiter price for {symbol}: ${price:,.4f}")
                        return price
                except Exception as e:
                    logger.debug(f"Jupiter price fetch failed for {symbol}: {e}")

            # Try Aster (for perps like SOL-PERP)
            if self.orchestrator.aster and symbol.endswith("-PERP"):
                try:
                    # Aster has market data access
                    logger.info(f"📊 Aster price fetch for {symbol}")
                    # TODO: Implement Aster.get_oracle_price()
                    return 0.0  # Temporary
                except Exception as e:
                    logger.debug(f"Aster price fetch failed for {symbol}: {e}")

            # Try Aster (for CEX-style pairs like BTCUSDT)
            if self.orchestrator._exchange_client:
                try:
                    # Normalize symbol for Aster (e.g. BTC-USDC -> BTCUSDT)
                    api_symbol = self.orchestrator._normalize_for_aster(symbol.replace("-", ""))
                    response = await self.orchestrator._exchange_client.get_ticker_price(api_symbol)

                    if isinstance(response, dict):
                        price = float(response.get("price", 0.0))
                        if price > 0:
                            logger.info(f"📊 Aster price for {symbol}: ${price:,.2f}")
                            return price
                except Exception as e:
                    logger.debug(f"Aster price fetch failed for {symbol}: {e}")

            # Try Lighter
            if self.orchestrator.hl_client:
                try:
                    # Lighter has its own price API
                    logger.info(f"📊 Lighter price fetch for {symbol}")
                    # TODO: Implement Lighter.get_mark_price()
                    return 0.0  # Temporary
                except Exception as e:
                    logger.debug(f"Lighter price fetch failed for {symbol}: {e}")

            # Try Aster
            if self.orchestrator.aster:
                try:
                    logger.info(f"📊 Aster price fetch for {symbol}")
                    # TODO: Implement Aster.get_price()
                    return 0.0  # Temporary
                except Exception as e:
                    logger.debug(f"Aster price fetch failed for {symbol}: {e}")

            # Try Lighter
            if self.orchestrator.lighter_client:
                try:
                    logger.info(f"📊 Lighter price fetch for {symbol}")
                    # TODO: Implement Lighter.get_price()
                    return 0.0  # Temporary
                except Exception as e:
                    logger.debug(f"Lighter price fetch failed for {symbol}: {e}")

            logger.warning(f"⚠️ Cannot fetch price for {symbol}: No platform client available or all failed")
            return 0.0

        except Exception as e:
            logger.error(f"❌ Failed to fetch price for {symbol}: {e}")
            return 0.0

    async def stop(self):
        """Stop the trading loop."""
        self._running = False
        logger.info("📊 TradingLoop stopped")
