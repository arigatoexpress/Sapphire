"""
Drift Trading Bot - Standalone Service (Solana)

This is an independent microservice for trading on Drift Protocol (Solana).
Optimized for Solana's fast finality and low latency.
"""

import asyncio
import logging
import os
import signal
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add shared library to path
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
SERVICE_NAME = "bot-drift"
PLATFORM = Platform.DRIFT

# Drift-specific optimizations
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
DRIFT_SUBACCOUNT_ID = int(os.getenv("DRIFT_SUBACCOUNT_ID", "0"))


class DriftBot:
    """
    Standalone Drift Protocol trading bot.

    Optimizations for Solana:
    - Fast block times (~400ms) allow quick order confirmation
    - Uses websocket subscriptions for real-time updates
    - Handles Solana-specific error codes
    """

    def __init__(self):
        self.config = ServiceConfig(PLATFORM.value)
        self.running = False
        self._shutdown_event = asyncio.Event()

        # Drift SDK client
        self.client = None
        self.sdk_client = None
        self.connection = None
        self.keypair = None

        # Position tracking
        self.positions: Dict[str, Position] = {}
        self.balance: float = 0.0

        # Solana-specific
        self.slot_height: int = 0
        self.last_blockhash: str = ""

        # Metrics
        self.trades_executed = 0
        self.trades_failed = 0
        self.avg_confirmation_ms = 0.0

    async def initialize(self):
        """Initialize the Drift client with Solana connection."""
        logger.info(f"🚀 Initializing {SERVICE_NAME}...")

        try:
            # Get private key from environment
            private_key = os.getenv("SOLANA_PRIVATE_KEY")
            if not private_key:
                logger.error("❌ SOLANA_PRIVATE_KEY not configured")
                return False

            # Import Drift SDK components
            from driftpy.account_subscription_config import AccountSubscriptionConfig
            from driftpy.drift_client import DriftClient as SDKDriftClient

            try:
                from driftpy.priority_fees.priority_fee_subscriber import PriorityFeeSubscriber
                from driftpy.priority_fees.types import PriorityFeeSubscriberConfig

                HAS_PF_CLIENT = True
            except ImportError:
                logger.warning("⚠️ PriorityFeeSubscriber not available in this version of driftpy")
                HAS_PF_CLIENT = False
            from solana.rpc.async_api import AsyncClient
            from solders.keypair import Keypair

            # Setup Solana connection
            self.connection = AsyncClient(SOLANA_RPC_URL)

            # Setup keypair from base58 private key
            if "[" in private_key:
                import json

                raw_key = json.loads(private_key)
                self.keypair = Keypair.from_bytes(bytes(raw_key))
            else:
                self.keypair = Keypair.from_base58_string(private_key)

            logger.info(f"🔑 Drift wallet: {self.keypair.pubkey()}")

            if HAS_PF_CLIENT:
                try:
                    # Setup Priority Fee Subscriber (Critical for landing txs)
                    pf_config = PriorityFeeSubscriberConfig(
                        connection=self.connection,
                        frequency=2.0,  # Update every 2s
                        lookback_distance=150,  # Recent blocks
                        addresses=None,  # Global/mixed
                    )
                    self.pf_subscriber = PriorityFeeSubscriber(pf_config)
                    await self.pf_subscriber.subscribe()
                    logger.info("⚡ Priority Fee Subscriber active")
                except Exception as e:
                    logger.warning(f"⚠️ Failed to init pf_subscriber (continuing anyway): {e}")
                    self.pf_subscriber = None
            else:
                self.pf_subscriber = None

            # Initialize Drift client
            self.sdk_client = SDKDriftClient(
                self.connection,
                self.keypair,
                env="mainnet",
                account_subscription=AccountSubscriptionConfig("websocket"),
                tx_params=None,  # We will dynamically set CU price later or let SDK handle
            )

            await self.sdk_client.subscribe()

            # Initialize Pub/Sub
            pubsub = get_pubsub_client()
            await pubsub.initialize()

            # Subscribe to trading signals
            await subscribe("trading-signals", self._handle_signal)
            await subscribe("risk-alerts", self._handle_risk_alert)

            logger.info(f"✅ {SERVICE_NAME} initialized successfully")
            return True

        except ImportError as e:
            logger.warning(f"⚠️ Drift SDK not available: {e}")
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
            tasks = [
                self._main_loop(),  # Local Strategy
                self._gateway_loop(),  # Hub Commands
                self._balance_sync_loop(),  # Maintenance
                self._slot_monitor_loop(),  # Maintenance
            ]
            await asyncio.gather(*tasks)

        except asyncio.CancelledError:
            logger.info("Bot stopped via cancellation")

    async def _gateway_loop(self):
        """Listen for external execution commands from the Hub."""
        logger.info("Gateway Loop Started (Listening on /execute)")
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

                    # Convert to TradeSignal for the existing execution pipeline
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
                    logger.info(
                        f"✅ Hub Command Executed: {result.success} (ID: {result.trade_id})"
                    )
                    if not result.success:
                        logger.error(f"❌ Execution Error: {result.error_message}")

                    # Notify cleanup
                    await publish("trade-executed", result)

                self.command_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Gateway Error: {e}")
                await asyncio.sleep(1)

        logger.info("🔌 Gateway Loop Ended")

    async def stop(self):
        """Gracefully stop the bot."""
        logger.info(f"🛑 Stopping {SERVICE_NAME}...")
        self.running = False
        self._shutdown_event.set()

        # Cleanup Solana connection
        if self.connection:
            await self.connection.close()

    async def _main_loop(self):
        """Main trading loop optimized for Solana's fast block times."""
        # Faster loop for Solana (400ms blocks)
        loop_interval = 0.5

        while self.running:
            try:
                await self._check_positions()
                await asyncio.sleep(loop_interval)
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(2)

    async def _slot_monitor_loop(self):
        """
        Monitor Solana slot height for network health with resilient reconnection.

        Implements exponential backoff and circuit breaking to prevent error spam
        from constant WebSocket disconnections.
        """
        max_consecutive_failures = 5
        consecutive_failures = 0
        base_retry_delay = 10  # seconds

        while self.running:
            try:
                if self.connection:
                    slot = await self.connection.get_slot()
                    self.slot_height = slot.value
                    logger.debug(f"Solana slot: {self.slot_height}")

                    # Reset failure count on success
                    consecutive_failures = 0

            except (TimeoutError, ConnectionError) as e:
                consecutive_failures += 1

                if consecutive_failures <= 3:
                    # Log first few failures at WARNING level
                    logger.warning(
                        f"Slot monitor connection issue ({consecutive_failures}/{max_consecutive_failures}): {e}"
                    )
                elif consecutive_failures == max_consecutive_failures:
                    # Circuit break - log at ERROR and enter degraded mode
                    logger.error(
                        f"🚨 Slot monitor connectivity failed {max_consecutive_failures} times. "
                        f"Entering degraded mode (will retry every 5 minutes)"
                    )
                # Beyond max failures, only log at DEBUG to prevent spam
                else:
                    logger.debug(f"Slot monitor still failing (degraded mode): {e}")

            except Exception as e:
                # Unexpected errors - always log
                logger.error(f"Slot monitor error: {e}")
                consecutive_failures += 1

            # Exponential backoff if failing
            if consecutive_failures >= max_consecutive_failures:
                # Degraded mode - wait 5 minutes between retries
                await asyncio.sleep(300)
            elif consecutive_failures > 0:
                # Exponential backoff: 10s, 20s, 40s, 80s, 160s
                retry_delay = min(base_retry_delay * (2**consecutive_failures), 300)
                await asyncio.sleep(retry_delay)
            else:
                # Normal operation
                await asyncio.sleep(10)

    async def _balance_sync_loop(self):
        """Periodically sync and publish balance."""
        while self.running:
            try:
                if self.sdk_client:
                    user = self.sdk_client.get_user(DRIFT_SUBACCOUNT_ID)
                    # Get collateral in USDC terms
                    collateral = user.get_total_collateral() / 1e6  # Convert from base units
                    self.balance = float(collateral)

                    await publish(
                        "balance-updates",
                        BalanceUpdate(
                            platform=PLATFORM.value,
                            total_balance=self.balance,
                            available_balance=self.balance,
                            assets={"USDC": self.balance},
                        ),
                    )
            except Exception as e:
                logger.error(f"Balance sync error: {e}")
            await asyncio.sleep(30)

    async def _handle_signal(self, signal_data: Dict[str, Any]):
        """Handle incoming trading signal."""
        try:
            signal = TradeSignal(**signal_data)

            if not signal.should_execute_on(PLATFORM.value):
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

    async def _execute_trade(self, signal: TradeSignal) -> TradeResult:
        """Execute trade on Drift with Solana-optimized confirmation."""
        start_time = datetime.now()

        try:
            if not self.sdk_client:
                raise Exception("Drift SDK not initialized")

            # Convert symbol to Drift market index
            market_index = self._symbol_to_market_index(signal.symbol)
            if market_index is None:
                raise Exception(f"Unknown market: {signal.symbol}")

            # 1. Check Account Margin Health (Log only, don't block)
            # We rely on _calculate_position_size to handle actual availability
            margin_health = await self._get_margin_health()
            if margin_health < 10:
                logger.warning(
                    f"⚠️ Low Margin Health ({margin_health}%). Proceeding with caution based on available funds."
                )

            # Calculate USD position size - ALWAYS use our controlled sizing, ignore signal.quantity
            usd_quantity = await self._calculate_position_size(signal)
            if usd_quantity <= 0:
                return TradeResult(
                    trade_id="",
                    signal_id=signal.signal_id,
                    platform=PLATFORM.value,
                    symbol=signal.symbol,
                    side=signal.side,
                    success=False,
                    error_message="Insufficient available funds for trade",
                    execution_time_ms=0,
                )

            usd_quantity = abs(usd_quantity)  # Ensure positive

            # Get oracle price to convert USD to base asset amount
            try:
                oracle_price_data = self.sdk_client.get_oracle_price_data_for_perp_market(
                    market_index
                )
                oracle_price = float(oracle_price_data.price) / 1e6  # Price is in 6 decimals
                if oracle_price <= 0:
                    oracle_price = 150.0  # Fallback for SOL
                    logger.warning(f"Using fallback price: ${oracle_price}")
            except Exception as e:
                oracle_price = 150.0  # Fallback price
                logger.warning(f"Oracle price fetch failed, using fallback: ${oracle_price} - {e}")

            # Convert USD to base asset units (e.g., $50 @ $145/SOL = 0.34 SOL)
            base_asset_quantity = usd_quantity / oracle_price

            # Apply minimum trade size
            MIN_BASE_ASSET = 0.01  # Minimum 0.01 SOL
            base_asset_quantity = max(base_asset_quantity, MIN_BASE_ASSET)

            logger.info(
                f"📊 Position sizing: ${usd_quantity:.2f} @ ${oracle_price:.2f} = {base_asset_quantity:.6f} base units"
            )

            # Determine direction
            from driftpy.types import MarketType, OrderParams, OrderType, PositionDirection

            direction = (
                PositionDirection.Long()
                if signal.side in (TradeSide.BUY, TradeSide.LONG)
                else PositionDirection.Short()
            )

            # Place perp order with required market_type
            # base_asset_amount uses 9 decimals for precision
            order_params = OrderParams(
                order_type=OrderType.Market(),
                market_type=MarketType.Perp(),
                market_index=market_index,
                base_asset_amount=int(base_asset_quantity * 1e9),
                direction=direction,
            )

            tx_sig = await self.sdk_client.place_perp_order(order_params)

            # Wait for confirmation (Solana is fast)
            await self.connection.confirm_transaction(tx_sig)

            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            self.avg_latency_ms = (self.avg_latency_ms + execution_time) / 2
            logger.info(
                f"⚡ Execution Latency: {execution_time:.2f}ms (Avg: {self.avg_latency_ms:.2f}ms)"
            )

            self.trades_executed += 1

            return TradeResult(
                trade_id=str(tx_sig),
                signal_id=signal.signal_id,
                platform=PLATFORM.value,
                symbol=signal.symbol,
                side=signal.side,
                success=True,
                order_id=str(tx_sig),
                filled_quantity=base_asset_quantity,
                avg_price=oracle_price,
                execution_time_ms=execution_time,
            )

        except Exception as e:
            logger.error(f"❌ Drift Execution Failed: {e}")
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

    async def place_oracle_order(self, signal: TradeSignal, offset_format: str = "PRICE"):
        """
        Place an Oracle Order (Limit order relative to Oracle price).

        Args:
            signal: Trade signal details
            offset_format: "PRICE" or "PCT" (not yet implemented)
        """
        try:
            from driftpy.types import OrderParams, OrderType, PositionDirection

            market_index = self._symbol_to_market_index(signal.symbol)
            # ALWAYS use our controlled sizing, ignore signal.quantity
            quantity = self._calculate_position_size(signal)
            direction = (
                PositionDirection.Long()
                if signal.side in (TradeSide.BUY, TradeSide.LONG)
                else PositionDirection.Short()
            )

            # Example HFT tactic: Bid 5 ticks below oracle (providing liquidity)
            oracle_offset = -5000 if direction.index == 0 else 5000  # +/- $0.005 roughly

            order_params = OrderParams(
                order_type=OrderType.Limit(),
                market_index=market_index,
                base_asset_amount=int(quantity * 1e9),
                direction=direction,
                oracle_price_offset=oracle_offset,
                auction_duration=10,  # JIT auction duration
            )

            await self.sdk_client.place_order(order_params)
            logger.info(f"✅ Placed Oracle Order for {signal.symbol}")

        except Exception as e:
            logger.error(f"Oracle Order failed: {e}")

    def _symbol_to_market_index(self, symbol: str) -> Optional[int]:
        """Convert symbol to Drift market index."""
        # Drift market indices (mainnet)
        markets = {
            "SOL": 0,
            "SOL-USDC": 0,
            "BTC": 1,
            "BTC-USDC": 1,
            "ETH": 2,
            "ETH-USDC": 2,
            "JUP": 8,
            "JUP-USDC": 8,
            "PYTH": 12,
            "PYTH-USDC": 12,
            "BONK": 15,
            "BONK-USDC": 15,
        }
        clean_symbol = symbol.replace("-PERP", "").upper()
        return markets.get(clean_symbol)

    async def _get_margin_health(self) -> float:
        """Get the margin health percentage of the account (0-100)."""
        if not self.sdk_client:
            return 0.0
        try:
            # get_health() returns 0-100 where 0 is liquidation
            user = self.sdk_client.get_user(DRIFT_SUBACCOUNT_ID)
            return float(user.get_health())
        except Exception as e:
            logger.warning(f"Failed to get margin health: {e}")
            return 50.0  # Assume middle health on error

    async def _calculate_position_size(self, signal: TradeSignal) -> float:
        """
        Calculate position size dynamically based on available funds.

        Adapts to account size - works with any balance from $1 to $10,000+.
        Respects platform minimums but skips trades if insufficient funds.

        Returns:
            Position size in USD, or 0 if insufficient funds
        """
        try:
            user = self.sdk_client.get_user(DRIFT_SUBACCOUNT_ID)

            # Get actual available funds
            collateral = user.get_total_collateral() / 1e6  # USDC
            margin_req = user.get_margin_requirement(None) / 1e6
            available = max(0, collateral - margin_req)

            # Use conservative percentage of available funds
            # Smaller accounts get higher % (to enable trading)
            # Larger accounts get lower % (for safety)
            if available < 50:
                # Small account: use up to 40% of available
                position_pct = 0.40
            elif available < 200:
                # Medium account: use 30%
                position_pct = 0.30
            else:
                # Larger account: use 20%
                position_pct = 0.20

            position_size = available * position_pct

            # Drift has platform-level minimums per market
            # Lowered for small account support - Drift actually allows micro-positions
            drift_minimums = {
                "SOL-PERP": 5,  # ~0.03 SOL minimum
                "SOL": 5,
                "BTC-PERP": 5,
                "BTC": 5,
                "ETH-PERP": 5,
                "ETH": 5,
                "SOL-PERP": 5,
                "SOL": 5,
                "BONK-PERP": 1,
                "BONK": 1,
                "JUP-PERP": 1,
                "JUP": 1,
            }

            # Match symbol with or without -PERP suffix
            symbol_key = signal.symbol.replace("-USDC", "").replace("-PERP", "")
            market_min = drift_minimums.get(symbol_key, drift_minimums.get(signal.symbol, 5))

            if position_size < market_min:
                logger.warning(
                    f"⏭️ Skipping {signal.symbol}: Position ${position_size:.2f} below "
                    f"minimum ${market_min}. Available: ${available:.2f}. "
                    f"Add more USDC or wait for position to close."
                )
                return 0

            logger.info(
                f"💰 Dynamic Sizing: Available=${available:.2f}, "
                f"Using {position_pct*100:.0f}% = ${position_size:.2f} "
                f"(min: ${market_min})"
            )

            return position_size

        except Exception as e:
            logger.error(f"Position sizing failed: {e}")
            # Conservative fallback for small accounts
            return 5.0  # Minimal fallback

    async def _check_positions(self):
        """Check positions using Drift's oracle prices."""
        if not self.sdk_client:
            return

        try:
            # Use the correct driftpy API: get_user_account() returns the UserAccount (sync)
            user_account = self.sdk_client.get_user_account(DRIFT_SUBACCOUNT_ID)
            perp_positions = user_account.perp_positions

            for pos in perp_positions:
                if pos.base_asset_amount != 0:
                    symbol = f"MARKET_{pos.market_index}"

                    # Get entry price - driftpy uses quote_entry_amount and base_asset_amount
                    # or simply get cost basis if available
                    try:
                        # Try quote_entry_amount / base_asset_amount for average price
                        if hasattr(pos, "quote_entry_amount") and pos.base_asset_amount != 0:
                            entry_price = abs(pos.quote_entry_amount / pos.base_asset_amount)
                        elif hasattr(pos, "quote_asset_amount"):
                            entry_price = abs(pos.quote_asset_amount / pos.base_asset_amount)
                        else:
                            entry_price = 0.0
                    except:
                        entry_price = 0.0

                    # Update or create position record
                    if symbol not in self.positions:
                        self.positions[symbol] = Position(
                            position_id=f"{PLATFORM.value}_{pos.market_index}",
                            platform=PLATFORM.value,
                            symbol=symbol,
                            side=TradeSide.LONG if pos.base_asset_amount > 0 else TradeSide.SHORT,
                            quantity=abs(pos.base_asset_amount) / 1e9,
                            entry_price=entry_price,
                        )
        except Exception as e:
            logger.error(f"Position check error: {e}")

    async def _close_all_positions(self):
        """Close all positions on Drift."""
        try:
            if self.sdk_client:
                user = self.sdk_client.get_user(DRIFT_SUBACCOUNT_ID)
                for pos in user.get_perp_positions():
                    if pos.base_asset_amount != 0:
                        await self.sdk_client.close_position(pos.market_index)
                self.positions.clear()
        except Exception as e:
            logger.error(f"Close all error: {e}")

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
            "solana_slot": self.slot_height,
            "avg_confirmation_ms": self.avg_confirmation_ms,
        }


async def main():
    """Main entry point."""
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))

    logger.info("=" * 50)
    logger.info(f"🌀 DRIFT BOT SERVICE (Solana)")
    logger.info(f"📅 {datetime.now().isoformat()}")
    logger.info("=" * 50)

    bot = DriftBot()

    def handle_shutdown(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(bot.stop())

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
# Syntax Validated
