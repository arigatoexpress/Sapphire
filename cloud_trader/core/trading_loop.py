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
        self.watchlist: List[str] = [
            "BTC-USDC",
            "ETH-USDC",
            "SOL-USDC",
            "DOGE-USDC",
            "PEPE-USDC",
            "WIF-USDC",
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
            for symbol, position in current_positions.items():
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

                        if consensus and consensus.confidence >= 0.65:
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
            # Calculate position size
            size = await self._calculate_position_size(symbol)

            # Execute via platform router
            result = await self.router.execute_trade(
                agent=consensus,  # Pass consensus as agent for tracking
                symbol=symbol,
                side=consensus.signal,
                quantity=size,
                thesis=consensus.reasoning,
                is_closing=False,
            )

            if result.success:
                # Track position
                await self.positions.open(
                    symbol=symbol,
                    side=consensus.signal,
                    quantity=result.quantity,
                    entry_price=result.price,
                    platform=result.platform.value,
                )
                # Notify monitoring
                await self.monitoring.notify_trade(
                    {
                        "symbol": symbol,
                        "side": consensus.signal,
                        "price": result.price,
                        "quantity": result.quantity,
                        "platform": result.platform.value,
                        "agent_id": (
                            consensus.agent_id if hasattr(consensus, "agent_id") else "swarm"
                        ),
                        "agent_name": (
                            consensus.agent_name if hasattr(consensus, "agent_name") else "AI Swarm"
                        ),
                    }
                )

                logger.info(f"✅ Opened {consensus.signal} {symbol} @ {result.price}")
                return True
            else:
                logger.warning(f"❌ Entry failed: {result.error}")
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

    async def _calculate_position_size(self, symbol: str) -> float:
        """Calculate position size based on risk parameters."""
        # TODO: Integrate with risk manager
        # For now, use fixed size
        return 100.0  # $100 per position

    async def _get_current_price(self, symbol: str) -> float:
        """Get current market price from the exchange."""
        try:
            if not self.orchestrator or not self.orchestrator._exchange_client:
                logger.warning(f"⚠️ Cannot fetch price for {symbol}: No exchange client")
                return 0.0

            # Normalize symbol if needed (e.g. BTC-USDC -> BTCUSDT for Aster)
            api_symbol = self.orchestrator._normalize_for_aster(symbol.replace("-", ""))

            # Fetch price
            # get_ticker_price returns dict like {'symbol': 'BTCUSDT', 'price': '12345.67'}
            response = await self.orchestrator._exchange_client.get_ticker_price(api_symbol)

            if isinstance(response, dict):
                price = float(response.get("price", 0.0))
                if price > 0:
                    return price

            logger.warning(f"⚠️ Invalid price response for {symbol}: {response}")
            return 0.0

        except Exception as e:
            logger.error(f"❌ Failed to fetch price for {symbol}: {e}")
            return 0.0

    async def stop(self):
        """Stop the trading loop."""
        self._running = False
        logger.info("📊 TradingLoop stopped")
