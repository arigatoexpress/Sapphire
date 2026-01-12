"""
Symphony Trading Bot - Standalone Service

This is an independent microservice for trading on Symphony (Monad/Base).
It communicates with other services via Pub/Sub and stores state in Firestore.
"""

import asyncio
import logging
import os
import signal

# Add shared library to path
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pubsub import get_pubsub_client, publish, subscribe
from utils import ServiceConfig, format_percent, format_price, setup_logging, utc_now

from models import (
    BalanceUpdate,
    Platform,
    Position,
    SignalType,
    TradeResult,
    TradeSide,
    TradeSignal,
)

logger = logging.getLogger(__name__)

# Service configuration
SERVICE_NAME = "bot-symphony"
PLATFORM = Platform.SYMPHONY


class SymphonyBot:
    """
    Standalone Symphony trading bot.

    Features:
    - Listens for trading signals via Pub/Sub
    - Executes trades on Symphony platform
    - Publishes trade results and position updates
    - Independent scaling and deployment
    """

    def __init__(self):
        self.config = ServiceConfig(PLATFORM.value)
        self.running = False
        self._shutdown_event = asyncio.Event()

        # Symphony client (imported lazily to avoid circular deps)
        self.client = None

        # Position tracking
        self.positions: Dict[str, Position] = {}
        self.balance: float = 0.0

        # Metrics
        self.trades_executed = 0
        self.trades_failed = 0
        self.last_sync = None

    async def initialize(self):
        """Initialize the Symphony client and connect to services."""
        import os

        self.trading_mode = os.getenv("TRADING_MODE", "PERPS").upper()
        logger.info(f"🚀 Initializing {SERVICE_NAME} in {self.trading_mode} mode...")

        try:
            # Import Symphony client
            # In production, this would be the actual symphony_client.py
            from symphony_client import SymphonyClient
            from symphony_config import SYMPHONY_AGENT_ID, SYMPHONY_MILF_ID

            logger.info(
                f"🔑 Configured Agent IDs - Default: {SYMPHONY_AGENT_ID}, MILF: {SYMPHONY_MILF_ID}"
            )

            self.client = SymphonyClient()

            # Initialize Pub/Sub
            pubsub = get_pubsub_client()
            await pubsub.initialize()

            # Subscribe to trading signals
            await subscribe("trading-signals", self._handle_signal)
            await subscribe("risk-alerts", self._handle_risk_alert)

            logger.info(f"✅ {SERVICE_NAME} initialized successfully")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to initialize: {e}")
            return False

    async def start(self):
        """Start the bot's main trading loop."""
        # Start Execution Gateway FIRST (Cloud Run Health Check requirement)
        from gateway import start_gateway_server

        self.command_queue = await start_gateway_server()

        if not await self.initialize():
            logger.error("Failed to initialize, exiting")
            return

        self.running = True
        logger.info(f"🎯 {SERVICE_NAME} is now running in HYBRID MODE")

        try:
            # Perform initial state verification
            await self._verify_state()

            # Start sync loop as a background task
            asyncio.create_task(self._sync_loop())

            # Run main loop and other loops concurrently
            tasks = [
                self._main_loop(),
                self._gateway_loop(),  # Hub Listener
                self._balance_sync_loop(),
            ]
            await asyncio.gather(*tasks)

        except asyncio.CancelledError:
            logger.info("Bot stopped via cancellation")

    async def _gateway_loop(self):
        """Listen for Hub commands."""
        logger.info("Gateway Loop Started (Listening on /execute)")
        import time

        from models import SignalType, TradeSide, TradeSignal

        while self.running:
            try:
                # Wait for command from Queue (pushed by Gateway Server)
                command = await self.command_queue.get()
                logger.info(f"📥 Processing Hub Command: {command}")

                # Map command to Action
                if command.get("type") == "ARB_EXECUTE":
                    side = command.get("side", "BUY")
                    symbol = command.get("symbol", "SOL")
                    quantity = float(command.get("quantity", 0.1))

                    logger.info(f"⚡ EXECUTING HUB COMMAND: {side} {quantity} {symbol}")

                    # Convert to TradeSignal
                    signal = TradeSignal(
                        signal_id=f"hub-{int(time.time())}",
                        symbol=symbol,
                        side=TradeSide.BUY if side == "BUY" else TradeSide.SELL,
                        signal_type=SignalType.ENTRY,
                        confidence=1.0,
                        source="alpha-hub",
                        quantity=quantity,
                    )

                    # Execute
                    result = await self._execute_trade(signal)
                    logger.info(f"✅ Hub Command Executed: {result.success}")

                    # Notify
                    await publish("trade-executed", result)

                self.command_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Gateway Error: {e}")
                await asyncio.sleep(1)

    async def stop(self):
        """Gracefully stop the bot."""
        logger.info(f"Stopping {SERVICE_NAME}...")
        self.running = False
        self._shutdown_event.set()

    async def _main_loop(self):
        """Main trading loop - processes signals and manages positions."""
        loop_interval = self.config.loop_interval_ms / 1000.0

        while self.running:
            try:
                # Check and manage existing positions
                await self._check_positions()

                # Wait for next iteration
                await asyncio.sleep(loop_interval)

            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(5)  # Back off on error

    async def _sync_loop(self):
        """Periodically sync positions with Symphony."""
        while self.running:
            try:
                await self._sync_positions()
                self.last_sync = utc_now()
            except Exception as e:
                logger.error(f"Sync error: {e}")
            await asyncio.sleep(30)  # Sync every 30 seconds

    async def _balance_sync_loop(self):
        """Periodically publish balance updates."""
        while self.running:
            try:
                await self._publish_balance()
            except Exception as e:
                logger.error(f"Balance sync error: {e}")
            await asyncio.sleep(60)  # Every minute

    async def _handle_signal(self, signal_data: Dict[str, Any]):
        """Handle incoming trading signal from Pub/Sub."""
        try:
            signal = TradeSignal(**signal_data)

            # Check if this signal targets us
            if not signal.should_execute_on(PLATFORM.value):
                return

            # Check if trading is enabled
            if not self.config.trading_enabled:
                logger.info(f"⏸️ Trading disabled, ignoring signal: {signal.symbol}")
                return

            logger.info(f"📥 Received signal: {signal.side} {signal.symbol}")

            # Execute the trade
            try:
                result = await self._execute_trade(signal)
                logger.info(
                    f"✅ Trade result: success={result.success}, error={result.error_message}"
                )
            except Exception as exec_error:
                logger.error(f"❌ Trade execution exception: {exec_error}")
                import traceback

                logger.error(traceback.format_exc())
                return

            # Publish result
            await publish("trade-executed", result)

        except Exception as e:
            logger.error(f"Signal handling error: {e}")
            import traceback

            logger.error(traceback.format_exc())

    async def _handle_risk_alert(self, alert_data: Dict[str, Any]):
        """Handle risk alerts from Risk Manager."""
        severity = alert_data.get("severity", "warning")
        action = alert_data.get("action", "none")

        logger.warning(f"⚠️ Risk alert ({severity}): {alert_data.get('message')}")

        if action == "close_all":
            await self._close_all_positions()
        elif action == "halt_trading":
            self.config.trading_enabled = False
            logger.warning("🚨 Trading halted due to risk alert")

    async def _verify_state(self):
        """Perform deep verification of account state."""
        try:
            logger.info("🔍 STARTING DEEP VERIFICATION: SYMPHONY")

            # Check Funds
            funds = await self.client.get_my_funds()
            logger.info(f"💰 SYMPHONY RAW FUNDS: {funds}")

            balance = 0
            if isinstance(funds, list) and len(funds) > 0:
                balance = funds[0].get("available", 0)  # Assumption
            elif isinstance(funds, dict):
                balance = funds.get("available", 0)

            logger.info(f"📊 SYMPHONY VERIFICATION_REPORT | ESTIMATED_BALANCE: {balance}")

            # Check Positions
            positions = await self.client.get_perpetual_positions()
            logger.info(f"📈 SYMPHONY RAW POSITIONS: {positions}")

            active_positions = []
            if isinstance(positions, list):
                active_positions = [p for p in positions if float(p.get("size", 0)) != 0]

            count = len(active_positions)
            logger.info(f"📊 SYMPHONY VERIFICATION_REPORT | OPEN_POSITIONS_COUNT: {count}")

            if count > 0:
                logger.warning(f"⚠️ SYMPHONY HAS OPEN POSITIONS: {active_positions}")
            else:
                logger.info("✅ SYMPHONY POSITIONS: CLEARED")

        except Exception as e:
            logger.error(f"❌ SYMPHONY VERIFICATION FAILED: {e}")

    async def _execute_trade(self, signal: TradeSignal) -> TradeResult:
        """Execute a trade on Symphony."""
        start_time = datetime.now()

        try:
            if not self.client:
                raise Exception("Symphony client not initialized")

            # Determine quantity/weight for Symphony
            quantity = signal.quantity or self._calculate_position_size(signal)

            # Symphony uses weight as percentage of collateral (0-100)
            # Convert our dollar amount to a weight estimate (assuming ~$250 account)
            # Ensure weight is at least 1% and max 100%
            # Determine Action
            action = "LONG" if signal.side in [TradeSide.BUY, TradeSide.LONG] else "SHORT"

            # Calculate weight
            # Symphony min trade size is $5 USDC.
            # With $250 balance, 1% ($2.50) fails.
            # We enforce a minimum weight of 10% ($25) to be safe.
            raw_quantity = signal.quantity if signal.quantity else 10
            weight = max(int(raw_quantity), 10)

            # Cap at 100
            weight = min(weight, 100)

            agent_id = self.client.default_agent_id  # Define agent_id from client
            logger.info(
                f"Executing with AgentID: {agent_id}, Weight: {weight}% (Min 10% enforced) Mode: {self.trading_mode}"
            )

            # AI SYMBOL RESOLVER: Dynamically resolve symbol for Symphony
            try:
                from shared.ai_symbol_resolver import resolve_symbol

                resolved_symbol = await resolve_symbol(
                    signal.symbol, "symphony", use_llm_fallback=True
                )
                if resolved_symbol != signal.symbol:
                    logger.info(f"🔄 Symbol resolved: {signal.symbol} -> {resolved_symbol}")
                    signal_symbol = resolved_symbol
                else:
                    signal_symbol = signal.symbol
            except Exception as e:
                logger.warning(f"Symbol resolution failed: {e}, using original: {signal.symbol}")
                signal_symbol = signal.symbol

            if self.trading_mode == "SPOT":
                # Spot Execution (Swap)
                # Parse Symbol (e.g., "MON-USDC") - use resolved symbol
                base, quote = "MON", "USDC"  # Default
                if "-" in signal_symbol:
                    parts = signal_symbol.split("-")
                    base = parts[0]
                    if len(parts) > 1:
                        quote = parts[1]

                # Determine In/Out
                if action == "LONG":  # BUY Base
                    token_in, token_out = quote, base
                else:  # SELL Base
                    token_in, token_out = base, quote

                order_result = await self.client.execute_swap(
                    token_in=token_in, token_out=token_out, weight=weight, agent_id=agent_id
                )
            else:
                # Perpetual Execution - use resolved symbol
                order_result = await self.client.open_perpetual_position(
                    symbol=signal_symbol.replace("1000", ""),  # Normalize
                    action=action,
                    weight=weight,
                    leverage=2.0,  # Increased leverage to 2x per docs example
                    agent_id=agent_id,
                )

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            # Check success
            # Docs say response has 'successful': number
            if order_result.get("successful", 0) > 0 and not order_result.get("failed", 0):
                # SUCCESS
                results_array = order_result.get("results", [])
                logger.info(f"✅ Trade EXECUTION CONFIRMED: {results_array}")

                # Create position record (using original logic for position creation)
                # Note: The new instruction's TradeResult structure is simpler and doesn't directly map to all position fields.
                # We'll try to extract what's available or use defaults.
                # Assuming 'results_array' might contain details for position.
                # For now, using signal.symbol and weight as quantity for position.
                position = Position(
                    position_id=order_result.get("batchId", ""),  # Using batchId as position_id
                    platform=PLATFORM.value,
                    symbol=signal.symbol,
                    side=signal.side,
                    quantity=weight,  # Using weight as a proxy for quantity
                    entry_price=0.0,  # Not directly available in new order_result structure
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )
                self.positions[signal.symbol] = position

                # Publish position update
                await publish(
                    "position-updates",
                    {
                        "platform": PLATFORM.value,
                        "positions": [p.__dict__ for p in self.positions.values()],
                    },
                )

                return TradeResult(
                    signal_id=signal.signal_id,
                    platform=PLATFORM.value,
                    symbol=signal.symbol,
                    side=signal.side,
                    success=True,
                    order_id=order_result.get("order_id"),
                    filled_quantity=order_result.get("filled_quantity", quantity),
                    avg_price=order_result.get("avg_price", 0.0),
                    fee=order_result.get("fee", 0.0),
                    execution_time_ms=execution_time,
                )
            else:
                self.trades_failed += 1
                return TradeResult(
                    trade_id="",
                    signal_id=signal.signal_id,
                    platform=PLATFORM.value,
                    symbol=signal.symbol,
                    side=signal.side,
                    success=False,
                    error_message=order_result.get("message")
                    or order_result.get("error", "Unknown error"),
                    execution_time_ms=execution_time,
                )

        except Exception as e:
            self.trades_failed += 1
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            return TradeResult(
                trade_id="",
                signal_id=signal.signal_id,
                platform=PLATFORM.value,
                symbol=signal.symbol,
                side=signal.side,
                success=False,
                error_message=str(e),
                execution_time_ms=execution_time,
            )

    def _calculate_position_size(self, signal: TradeSignal) -> float:
        """Calculate position size based on config and signal."""
        # Simple fixed size for now, can be enhanced with risk-based sizing
        max_size = self.config.max_position_size
        return min(max_size, self.balance * 0.1)  # 10% of balance max

    async def _check_positions(self):
        """Check existing positions for TP/SL conditions."""
        for symbol, position in list(self.positions.items()):
            try:
                # Get current price
                current_price = await self._get_current_price(symbol)
                if not current_price:
                    continue

                position.current_price = current_price
                position.updated_at = utc_now()

                # Check stop loss
                if position.stop_loss and current_price <= position.stop_loss:
                    logger.info(f"🛑 Stop loss triggered for {symbol}")
                    await self._close_position(symbol, "stop_loss")
                    continue

                # Check take profit
                if position.take_profit and current_price >= position.take_profit:
                    logger.info(f"🎯 Take profit triggered for {symbol}")
                    await self._close_position(symbol, "take_profit")

            except Exception as e:
                logger.error(f"Error checking position {symbol}: {e}")

    async def _close_position(self, symbol: str, reason: str):
        """Close a position."""
        if symbol not in self.positions:
            return

        position = self.positions[symbol]

        try:
            # Close via Symphony
            result = await self.client.close_position(symbol)

            if result.get("success"):
                del self.positions[symbol]
                logger.info(f"✅ Closed position {symbol} ({reason})")

                # Publish position update
                await publish(
                    "position-updates",
                    {
                        "platform": PLATFORM.value,
                        "positions": [p.__dict__ for p in self.positions.values()],
                    },
                )

        except Exception as e:
            logger.error(f"Error closing position {symbol}: {e}")

    async def _close_all_positions(self):
        """Close all open positions."""
        for symbol in list(self.positions.keys()):
            await self._close_position(symbol, "risk_alert")

    async def _sync_positions(self):
        """Sync positions with Symphony."""
        try:
            if not self.client:
                return

            # Fetch positions from Symphony
            symphony_positions = await self.client.get_perpetual_positions()

            # Update local state
            for pos_data in symphony_positions:
                symbol = pos_data.get("symbol")
                if symbol:
                    if symbol in self.positions:
                        # Update existing
                        self.positions[symbol].current_price = pos_data.get("mark_price", 0.0)
                        self.positions[symbol].unrealized_pnl = pos_data.get("unrealized_pnl", 0.0)
                    else:
                        # New position (opened externally)
                        self.positions[symbol] = Position(
                            position_id=pos_data.get("id", ""),
                            platform=PLATFORM.value,
                            symbol=symbol,
                            side=(
                                TradeSide.LONG
                                if pos_data.get("side") == "LONG"
                                else TradeSide.SHORT
                            ),
                            quantity=pos_data.get("quantity", 0.0),
                            entry_price=pos_data.get("entry_price", 0.0),
                            current_price=pos_data.get("mark_price", 0.0),
                            unrealized_pnl=pos_data.get("unrealized_pnl", 0.0),
                        )

            logger.debug(f"Synced {len(self.positions)} positions")

        except Exception as e:
            logger.error(f"Position sync error: {e}")

    async def _publish_balance(self):
        """Publish current balance to other services."""
        try:
            if not self.client:
                return

            balance_data = await self.client.get_balance()
            self.balance = balance_data.get("total", 0.0)

            await publish(
                "balance-updates",
                BalanceUpdate(
                    platform=PLATFORM.value,
                    total_balance=self.balance,
                    available_balance=balance_data.get("available", self.balance),
                    assets=balance_data.get("assets", {}),
                ),
            )

        except Exception as e:
            logger.error(f"Balance publish error: {e}")

    async def _get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        try:
            if not self.client:
                return None
            ticker = await self.client.get_ticker(symbol)
            return ticker.get("price")
        except Exception:
            return None

    def get_status(self) -> Dict[str, Any]:
        """Get bot status for health checks."""
        return {
            "service": SERVICE_NAME,
            "platform": PLATFORM.value,
            "running": self.running,
            "trading_enabled": self.config.trading_enabled,
            "positions": len(self.positions),
            "balance": self.balance,
            "trades_executed": self.trades_executed,
            "trades_failed": self.trades_failed,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
        }


async def main():
    """Main entry point."""
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))

    logger.info("=" * 50)
    logger.info(f"🎵 SYMPHONY BOT SERVICE")
    logger.info(f"📅 {datetime.now().isoformat()}")
    logger.info("=" * 50)

    bot = SymphonyBot()

    # Handle shutdown signals
    def handle_shutdown(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(bot.stop())

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
# Syntax Validated
