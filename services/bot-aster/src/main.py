"""
Aster Trading Bot - Standalone Service

This is an independent microservice for trading on Aster DEX.
Optimized for CEX-style execution with high throughput.
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
SERVICE_NAME = "bot-aster"
PLATFORM = Platform.ASTER

# Aster API settings
ASTER_API_KEY = os.getenv("ASTER_API_KEY", "").strip()
ASTER_API_SECRET = (
    os.getenv("ASTER_SECRET_KEY", "").strip() or os.getenv("ASTER_API_SECRET", "").strip()
)
ASTER_PASSPHRASE = os.getenv("ASTER_PASSPHRASE", "").strip()


class AsterBot:
    """
    Standalone Aster DEX trading bot.

    Optimizations for Aster:
    - CEX-style API with fast order matching
    - Support for multiple order types (limit, market, trailing)
    - Advanced order management (TP/SL, trailing stops)
    - High-frequency trading optimizations
    """

    def __init__(self):
        self.config = ServiceConfig(PLATFORM)
        self.running = False
        self._shutdown_event = asyncio.Event()

        # Aster client
        self.client = None

        # Position tracking
        self.positions: Dict[str, Position] = {}
        self.balance: float = 0.0

        # Order management
        self.open_orders: Dict[str, Dict] = {}
        self.trailing_stops: Dict[str, Dict] = {}

        # Performance
        self.trades_executed = 0
        self.trades_failed = 0
        self.total_fees = 0.0

        # Paper trading mode (disabled by default for production)
        self.is_paper_trading = os.getenv("PAPER_TRADING", "false").lower() == "true"

    async def initialize(self):
        """Initialize Aster client connection."""
        logger.info(f"🚀 Initializing {SERVICE_NAME}...")

        try:
            if not ASTER_API_KEY or not ASTER_API_SECRET:
                logger.error("❌ ASTER_API_KEY or ASTER_API_SECRET not configured")
                return False

            # Import and initialize Aster client
            from aster_client import AsterClient, UserStream
            from credentials import Credentials

            creds = Credentials(api_key=ASTER_API_KEY, api_secret=ASTER_API_SECRET)

            self.client = AsterClient(credentials=creds)

            # Test API connection on startup
            try:
                # Try to fetch server time as a basic connectivity test
                server_time = await self.client.get_server_time()
                logger.info(f"✅ Aster API accessible (server time: {server_time})")
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Aster API Error: {error_msg}")

                # Provide actionable diagnostics for common issues
                if "-2015" in error_msg or "Invalid API-key" in error_msg:
                    logger.error(
                        """
╔═══════════════════════════════════════════════════════════╗
║           ASTER API AUTHENTICATION FAILED                 ║
╠═══════════════════════════════════════════════════════════╣
║ Error Code: -2015 (Invalid API-key or permissions)       ║
║                                                           ║
║ ACTION REQUIRED:                                          ║
║ 1. Visit: https://www.asterdex.com/account/api          ║
║ 2. Verify API key has 'Futures Trading' permission      ║
║ 3. Check IP restrictions (Cloud Run uses dynamic IPs)    ║
║ 4. Consider disabling IP whitelist for Cloud Run        ║
║                                                           ║
║ Current Cloud Run IP will vary per container instance.   ║
╚═══════════════════════════════════════════════════════════╝
                    """
                    )
                # Don't fail initialization, but log the issue
                pass

            # Initialize User Stream (Websockets)
            self.user_stream = UserStream(self.client, self._handle_user_event)

            # Initialize Pub/Sub
            pubsub = get_pubsub_client()
            await pubsub.initialize()

            await subscribe("trading-signals", self._handle_signal)
            await subscribe("risk-alerts", self._handle_risk_alert)

            logger.info(f"✅ {SERVICE_NAME} initialized successfully")
            return True

        except ImportError as e:
            logger.warning(f"⚠️ Aster client not available: {e}")
            return False
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
        logger.info(f"Bot {SERVICE_NAME} is now running in HYBRID MODE")

        try:
            # Perform initial state verification
            await self._verify_state()

            # Start User Stream in background
            asyncio.create_task(self.user_stream.start())

            tasks = [
                self._main_loop(),
                self._gateway_loop(),  # Hub Listener
                self._fallback_sync_loop(),
                self._trailing_stop_loop(),
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

        logger.info("🔌 Gateway Loop Ended")
        await self.user_stream.stop()

    async def stop(self):
        """Gracefully stop the bot."""
        logger.info(f"🛑 Stopping {SERVICE_NAME}...")
        self.running = False
        if self.user_stream:
            await self.user_stream.stop()
        self._shutdown_event.set()

    async def _main_loop(self):
        """Main trading loop."""
        loop_interval = self.config.loop_interval_ms / 1000.0

        while self.running:
            try:
                # Still check positions occasionally or logic that depends on position data
                # Position data is now updated via WS, but logic runs here
                pass
                await asyncio.sleep(loop_interval)
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(2)

    async def _fallback_sync_loop(self):
        """Less frequent sync for backup."""
        while self.running:
            await asyncio.sleep(60)  # Sync every 60s instead of rapid polling
            await self._check_positions()

    async def _order_monitor_loop(self):
        """Monitor open orders for fills."""
        while self.running:
            try:
                if self.client:
                    open_orders = await self.client.get_open_orders()
                    self.open_orders = {o["orderId"]: o for o in open_orders}
            except Exception as e:
                logger.error(f"Order monitor error: {e}")
            await asyncio.sleep(5)

    async def _trailing_stop_loop(self):
        """Manage trailing stop orders."""
        # Note: We now prefer Native Trailing Stops (TRAILING_STOP_MARKET)
        # sent directly to the exchange via _place_stop_loss methods.
        # This loop is kept for legacy support or custom complex trailing logic.
        while self.running:
            await asyncio.sleep(60)

    async def _balance_sync_loop(self):
        """Sync balance with Aster."""
        while self.running:
            try:
                if self.client:
                    account_info = await self.client.get_account_info_v2()

                    total = 0.0
                    assets = {}
                    for asset in account_info:
                        balance = float(asset.get("balance", 0))
                        asset_name = asset.get("asset", "")
                        if balance > 0:
                            assets[asset_name] = balance
                            if asset_name in ("USDT", "USDC", "USD"):
                                total += balance

                    self.balance = total

                    await publish(
                        "balance-updates",
                        BalanceUpdate(
                            platform=PLATFORM,
                            total_balance=self.balance,
                            available_balance=self.balance,
                            assets=assets,
                        ),
                    )
            except Exception as e:
                logger.error(f"Balance sync error: {e}")
            await asyncio.sleep(30)

    async def _handle_user_event(self, event: Dict[str, Any]):
        """Handle incoming user data stream event."""
        try:
            event_type = event.get("e")

            if event_type == "ORDER_TRADE_UPDATE":
                order_data = event.get("o", {})
                order_id = str(order_data.get("i"))
                status = order_data.get("X")
                symbol = order_data.get("s")

                logger.info(f"🔄 Order Update: {symbol} {status}")

                # Update open orders tracking
                if status in ("FILLED", "CANCELED", "EXPIRED", "REJECTED"):
                    if order_id in self.open_orders:
                        del self.open_orders[order_id]
                else:
                    self.open_orders[order_id] = order_data

            elif event_type == "ACCOUNT_UPDATE":
                data = event.get("a", {})

                # Update Balances
                for bal in data.get("B", []):
                    asset = bal.get("a")
                    wallet_balance = float(bal.get("wb", 0))
                    if asset == "USDT":
                        self.balance = wallet_balance

                # Update Positions
                for pos in data.get("P", []):
                    symbol = pos.get("s")
                    amount = float(pos.get("pa", 0))
                    entry_price = float(pos.get("ep", 0))

                    if amount != 0:
                        if symbol not in self.positions:
                            # Create placeholder if missing (detailed data comes from REST sync)
                            self.positions[symbol] = Position(
                                position_id=f"pos_{symbol}",
                                platform=PLATFORM,
                                symbol=symbol,
                                side=TradeSide.BUY if amount > 0 else TradeSide.SELL,
                                quantity=abs(amount),
                                entry_price=entry_price,
                            )
                        else:
                            self.positions[symbol].quantity = abs(amount)
                            self.positions[symbol].entry_price = entry_price
                    else:
                        # Position closed
                        if symbol in self.positions:
                            del self.positions[symbol]

        except Exception as e:
            logger.error(f"Error handling user event: {e}")

    async def _handle_signal(self, signal_data: Dict[str, Any]):
        """Handle incoming trading signal."""
        try:
            signal = TradeSignal(**signal_data)

            if PLATFORM not in signal.target_platforms and signal.target_platforms:
                return

            if not self.config.trading_enabled:
                logger.info(f"⏸️ Trading disabled, ignoring signal: {signal.symbol}")
                return

            logger.info(f"📥 Received signal: {signal.side} {signal.symbol}")
            result = await self._execute_trade(signal)
            await publish("trade-executed", result)

        except Exception as e:
            logger.error(f"Signal handling error: {e}")

    async def _handle_risk_alert(self, alert_data: Dict[str, Any]):
        """Handle risk alerts."""
        action = alert_data.get("action", "none")
        logger.warning(f"⚠️ Risk alert: {alert_data.get('message')}")

        if action == "close_all":
            await self._close_all_positions()
        elif action == "halt_trading":
            self.config.trading_enabled = False

    async def _verify_state(self):
        """Perform deep verification of account state."""
        try:
            logger.info("🔍 STARTING DEEP VERIFICATION: ASTER")

            # Check Funds
            # Use get_account_summary or similar
            info = await self.client.get_account_summary()
            # info usually has 'availableBalance'
            balance = info.get("availableBalance", "N/A")
            logger.info(
                f"📊 ASTER VERIFICATION_REPORT | BALANCE: {balance} | RAW_INFO_PARTIAL: {str(info)[:100]}..."
            )

            # Check Positions
            positions = await self.client.get_position_risk()
            # Filter for non-zero
            active = [p for p in positions if float(p.get("positionAmt", 0)) != 0]
            count = len(active)
            logger.info(f"📊 ASTER VERIFICATION_REPORT | OPEN_POSITIONS_COUNT: {count}")
            if count > 0:
                logger.warning(f"⚠️ ASTER HAS OPEN POSITIONS: {active}")
            else:
                logger.info("✅ ASTER POSITIONS: CLEARED")

        except Exception as e:
            logger.error(f"❌ ASTER VERIFICATION FAILED: {e}")

    async def _execute_trade(self, signal: TradeSignal) -> TradeResult:
        """Execute trade on Aster with advanced order types."""
        start_time = datetime.now()

        try:
            if not self.client:
                raise Exception("Aster client not initialized")

            # Calculate quantity
            quantity = signal.quantity or self._calculate_position_size(signal)

            # Determine order side
            side = "BUY" if signal.side in (TradeSide.BUY, TradeSide.LONG) else "SELL"

            logger.info(f"⚡ Executing on Aster: {signal.symbol} {side} {quantity}")

            start_time = datetime.now()

            if self.is_paper_trading:
                # Mock execution
                await asyncio.sleep(0.1)
                order_result = {
                    "status": "filled",
                    "orderId": "paper-" + str(int(time.time())),
                    "avgPrice": 0.0,
                }  # Mock
                logger.info("📝 Paper trade executed")
            else:
                # Real execution
                # Use market order for immediate fill
                from aster_client import OrderType

                order_result = await self.client.place_order(
                    symbol=signal.symbol, side=side, order_type=OrderType.MARKET, quantity=quantity
                )
                logger.info(f"✅ Aster Order Result: {order_result}")

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            if order_result.get("status") in ("FILLED", "NEW"):
                self.trades_executed += 1

                filled_qty = float(order_result.get("executedQty", quantity))
                avg_price = float(order_result.get("avgPrice", 0))

                # Create position record
                self.positions[signal.symbol] = Position(
                    position_id=order_result.get("orderId", ""),
                    platform=PLATFORM,
                    symbol=signal.symbol,
                    side=signal.side,
                    quantity=filled_qty,
                    entry_price=avg_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )

                # Set up trailing stop if configured
                if signal.metadata.get("trailing_stop"):
                    self.trailing_stops[signal.symbol] = {
                        "trail_percent": signal.metadata.get("trail_percent", 0.02),
                        "stop_price": (
                            avg_price * (1 - 0.02) if side == "BUY" else avg_price * (1 + 0.02)
                        ),
                    }

                # Set TP/SL orders on exchange
                if signal.stop_loss:
                    await self._place_stop_loss(signal.symbol, signal.stop_loss, filled_qty, side)
                if signal.take_profit:
                    await self._place_take_profit(
                        signal.symbol, signal.take_profit, filled_qty, side
                    )

                return TradeResult(
                    trade_id=order_result.get("orderId", ""),
                    signal_id=signal.signal_id,
                    platform=PLATFORM,
                    symbol=signal.symbol,
                    side=signal.side,
                    success=True,
                    order_id=order_result.get("orderId"),
                    filled_quantity=filled_qty,
                    avg_price=avg_price,
                    fee=float(order_result.get("commission", 0)),
                    execution_time_ms=execution_time,
                )
            else:
                self.trades_failed += 1
                return TradeResult(
                    trade_id="",
                    signal_id=signal.signal_id,
                    platform=PLATFORM,
                    symbol=signal.symbol,
                    side=signal.side,
                    success=False,
                    error_message=order_result.get("msg", "Order failed"),
                    execution_time_ms=execution_time,
                )

        except Exception as e:
            self.trades_failed += 1
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            return TradeResult(
                trade_id="",
                signal_id=signal.signal_id,
                platform=PLATFORM,
                symbol=signal.symbol,
                side=signal.side,
                success=False,
                error_message=str(e),
                execution_time_ms=execution_time,
            )

    async def _place_stop_loss(self, symbol: str, price: float, quantity: float, entry_side: str):
        """Place stop-loss order (Native)."""
        try:
            exit_side = "SELL" if entry_side == "BUY" else "BUY"

            # Use native TRAILING_STOP_MARKET if dynamic
            # For now, using standard STOP_MARKET for reliability as per audit
            await self.client.place_stop_order(
                symbol=symbol,
                side=exit_side,
                quantity=quantity,
                stop_price=price,
            )
        except Exception as e:
            logger.error(f"Failed to place stop-loss: {e}")

    async def _place_take_profit(self, symbol: str, price: float, quantity: float, entry_side: str):
        """Place take-profit order."""
        try:
            exit_side = "SELL" if entry_side == "BUY" else "BUY"
            await self.client.place_limit_order(
                symbol=symbol, side=exit_side, quantity=quantity, price=price
            )
        except Exception as e:
            logger.error(f"Failed to place take-profit: {e}")

    def _calculate_position_size(self, signal: TradeSignal) -> float:
        """
        Calculate position size dynamically based on Aster account balance.

        Adapts to available funds - uses percentage based on account size.

        Returns:
            Position size in USD
        """
        # Use current balance (synced via _balance_sync_loop)
        available_usd = self.balance if self.balance > 0 else 50  # Default if not synced

        # Dynamic percentage based on account size
        if available_usd < 100:
            position_pct = 0.50  # Small account: 50%
        elif available_usd < 500:
            position_pct = 0.30  # Medium account: 30%
        else:
            position_pct = 0.20  # Larger account: 20%

        # Calculate position size
        position_usd = available_usd * position_pct

        logger.info(
            f"💰 Aster Dynamic Sizing: Balance=${available_usd:.2f}, "
            f"Using {position_pct*100:.0f}% = ${position_usd:.2f}"
        )

        return position_usd

    async def _check_positions(self):
        """Check positions on Aster."""
        if not self.client:
            return

        try:
            exchange_positions = await self.client.get_position_risk()

            for pos_data in exchange_positions:
                symbol = pos_data.get("symbol")
                qty = float(pos_data.get("positionAmt", 0))

                if qty != 0 and symbol:
                    if symbol in self.positions:
                        self.positions[symbol].current_price = float(pos_data.get("markPrice", 0))
                        self.positions[symbol].unrealized_pnl = float(
                            pos_data.get("unrealizedProfit", 0)
                        )

        except Exception as e:
            logger.error(f"Position check error: {e}")

    async def _close_position(self, symbol: str, reason: str):
        """Close a position on Aster."""
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]

        try:
            exit_side = "SELL" if pos.side in (TradeSide.BUY, TradeSide.LONG) else "BUY"

            await self.client.place_market_order(
                symbol=symbol,
                side=exit_side,
                quantity=pos.quantity,
            )

            del self.positions[symbol]
            if symbol in self.trailing_stops:
                del self.trailing_stops[symbol]

            logger.info(f"✅ Closed position {symbol} ({reason})")

        except Exception as e:
            logger.error(f"Error closing position {symbol}: {e}")

    async def _close_all_positions(self):
        """Close all positions."""
        for symbol in list(self.positions.keys()):
            await self._close_position(symbol, "risk_alert")

    def get_status(self) -> Dict[str, Any]:
        """Get bot status."""
        return {
            "service": SERVICE_NAME,
            "platform": PLATFORM,
            "running": self.running,
            "trading_enabled": self.config.trading_enabled,
            "positions": len(self.positions),
            "balance": self.balance,
            "trades_executed": self.trades_executed,
            "trades_failed": self.trades_failed,
            "open_orders": len(self.open_orders),
            "trailing_stops": len(self.trailing_stops),
            "total_fees": self.total_fees,
        }


async def main():
    """Main entry point."""
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))

    logger.info("=" * 50)
    logger.info(f"⭐ ASTER BOT SERVICE")
    logger.info(f"📅 {datetime.now().isoformat()}")
    logger.info("=" * 50)

    bot = AsterBot()

    def handle_shutdown(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(bot.stop())

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
# Syntax Validated
