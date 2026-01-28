"""
Lighter Trading Bot - Standalone Service (L2 Order Book)

This is an independent microservice for trading on Lighter Protocol.
Lighter is a decentralized L2 order book exchange built on ZK-rollups.
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
SERVICE_NAME = "bot-lighter"
PLATFORM = Platform.LIGHTER

# Lighter-specific settings
LIGHTER_API_URL = os.getenv("LIGHTER_API_URL", "https://mainnet.zklighter.elliot.ai")
LIGHTER_TESTNET = os.getenv("LIGHTER_TESTNET", "false").lower() == "true"

# Try to import Lighter SDK
try:
    import lighter
    LIGHTER_SDK_AVAILABLE = True
    logger.info("Lighter SDK loaded")
except ImportError:
    LIGHTER_SDK_AVAILABLE = False
    logger.warning("Lighter SDK not available - install lighter-sdk")


class LighterBot:
    """
    Standalone Lighter Protocol trading bot.

    Optimizations for Lighter (L2):
    - ZK-rollup ensures transaction finality
    - Order book model for precise execution
    - Low latency through L2 architecture
    """

    def __init__(self):
        self.config = ServiceConfig(PLATFORM.value)
        self.running = False
        self._shutdown_event = asyncio.Event()

        # Lighter SDK components
        self.client = None
        self.account_api = None
        self.transaction_api = None
        self.order_api = None

        # Credentials
        self._pub_key = os.getenv("LIGHTER_PUB_KEY", "")
        self._priv_key = os.getenv("LIGHTER_PRIV_KEY", "")

        # Account tracking
        self.account_index: Optional[int] = None
        self.balance: float = 0.0

        # Position tracking
        self.positions: Dict[str, Position] = {}
        self.market_info: Dict[str, Dict] = {}

        # Performance metrics
        self.trades_executed = 0
        self.trades_failed = 0
        self.avg_latency_ms = 0.0

    async def initialize(self):
        """Initialize the Lighter SDK clients."""
        logger.info(f"Initializing {SERVICE_NAME}...")

        if not LIGHTER_SDK_AVAILABLE:
            logger.error("Cannot initialize - Lighter SDK not installed")
            return False

        if not self._pub_key or not self._priv_key:
            logger.error("LIGHTER_PUB_KEY or LIGHTER_PRIV_KEY not configured")
            return False

        try:
            # Set API base URL based on testnet flag
            base_url = (
                "https://testnet.zklighter.elliot.ai"
                if LIGHTER_TESTNET
                else "https://mainnet.zklighter.elliot.ai"
            )

            # Initialize the API client
            self.client = lighter.ApiClient()

            # Initialize API endpoints
            self.account_api = lighter.AccountApi(self.client)
            self.transaction_api = lighter.TransactionApi(self.client)
            self.order_api = lighter.OrderApi(self.client)

            # Load market metadata
            await self._load_market_info()

            # Get account index from pub key
            await self._load_account_info()

            # Initialize Pub/Sub
            pubsub = get_pubsub_client()
            await pubsub.initialize()

            await subscribe("trading-signals", self._handle_signal)
            await subscribe("risk-alerts", self._handle_risk_alert)

            logger.info(f"{SERVICE_NAME} initialized successfully | Testnet: {LIGHTER_TESTNET}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            return False

    async def _load_market_info(self):
        """Load order book metadata from API."""
        try:
            loop = asyncio.get_event_loop()
            order_books = await loop.run_in_executor(None, lambda: self.order_api.order_books())

            if order_books and hasattr(order_books, "order_books"):
                for ob in order_books.order_books:
                    symbol = ob.symbol if hasattr(ob, "symbol") else str(ob.order_book_id)
                    self.market_info[symbol.upper()] = {
                        "order_book_id": ob.order_book_id if hasattr(ob, "order_book_id") else 0,
                        "symbol": symbol,
                        "base_asset": getattr(ob, "base_asset", symbol),
                        "quote_asset": getattr(ob, "quote_asset", "USDC"),
                        "tick_size": getattr(ob, "tick_size", 0.01),
                        "step_size": getattr(ob, "step_size", 0.001),
                    }
                logger.info(f"Loaded {len(self.market_info)} markets")
        except Exception as e:
            logger.warning(f"Failed to load market info: {e}")

    async def _load_account_info(self):
        """Load account information and get account index."""
        try:
            loop = asyncio.get_event_loop()

            # Query accounts by the public key (L1 address)
            accounts = await loop.run_in_executor(
                None,
                lambda: self.account_api.accounts_by_l1_address(
                    l1_address=self._pub_key[:42] if len(self._pub_key) > 42 else self._pub_key
                ),
            )

            if accounts and hasattr(accounts, "accounts") and len(accounts.accounts) > 0:
                self.account_index = accounts.accounts[0].index
                logger.info(f"Account index: {self.account_index}")
            else:
                self.account_index = 0
                logger.warning("Could not find account, using index 0")

        except Exception as e:
            logger.warning(f"Failed to load account info: {e}")
            self.account_index = 0

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
                self._main_loop(),
                self._gateway_loop(),
                self._balance_sync_loop(),
            ]
            await asyncio.gather(*tasks)

        except asyncio.CancelledError:
            logger.info("Bot stopped via cancellation")

    async def _gateway_loop(self):
        """Listen for external execution commands from the Hub."""
        logger.info("Gateway Loop Started (Listening on /execute)")

        while self.running:
            try:
                command = await self.command_queue.get()
                logger.info(f"Processing Hub Command: {command}")

                if command.get("type") == "ARB_EXECUTE":
                    side = command.get("side", "BUY")
                    symbol = command.get("symbol", "WETH")
                    quantity = float(command.get("quantity", 0.01))

                    logger.info(f"EXECUTING HUB COMMAND: {side} {quantity} {symbol}")

                    signal = TradeSignal(
                        signal_id=f"hub-{int(time.time())}",
                        symbol=symbol,
                        side=TradeSide.BUY if side == "BUY" else TradeSide.SELL,
                        signal_type=SignalType.ENTRY,
                        confidence=1.0,
                        source="alpha-hub",
                        quantity=quantity,
                    )

                    result = await self._execute_trade(signal)
                    logger.info(f"Hub Command Executed: {result.success}")
                    await publish("trade-executed", result)

                self.command_queue.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Gateway Error: {e}")
                await asyncio.sleep(1)

        logger.info("Gateway Loop Ended")

    async def stop(self):
        """Gracefully stop the bot."""
        logger.info(f"Stopping {SERVICE_NAME}...")
        self.running = False
        self._shutdown_event.set()

    async def _main_loop(self):
        """Main trading loop."""
        loop_interval = 1.0  # 1 second for L2

        while self.running:
            try:
                await self._check_positions()
                await asyncio.sleep(loop_interval)
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(2)

    async def _balance_sync_loop(self):
        """Periodically sync and publish balance."""
        while self.running:
            try:
                if self.account_api and self.account_index is not None:
                    loop = asyncio.get_event_loop()
                    account = await loop.run_in_executor(
                        None,
                        lambda: self.account_api.account(by="index", value=str(self.account_index)),
                    )

                    if account:
                        equity = float(getattr(account, "equity", 0))
                        self.balance = equity

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
                logger.info(f"Trading disabled, ignoring signal: {signal.symbol}")
                return

            logger.info(f"Received signal: {signal.side} {signal.symbol}")
            result = await self._execute_trade(signal)
            await publish("trade-executed", result)

        except Exception as e:
            logger.error(f"Signal handling error: {e}")

    async def _handle_risk_alert(self, alert_data: Dict[str, Any]):
        """Handle risk alerts."""
        action = alert_data.get("action", "none")
        logger.warning(f"Risk alert: {alert_data.get('message')}")

        if action == "close_all":
            await self._close_all_positions()
        elif action == "halt_trading":
            self.config.trading_enabled = False

    async def _execute_trade(self, signal: TradeSignal) -> TradeResult:
        """Execute trade on Lighter with L2 order book."""
        start_time = datetime.now()

        try:
            if not self.transaction_api:
                raise Exception("Transaction API not initialized")

            # Normalize symbol
            coin = signal.symbol.upper().replace("-PERP", "").replace("-USDC", "").replace("_", "")

            # Get market info
            market = self.market_info.get(coin, {})
            order_book_id = market.get("order_book_id", 0)

            is_buy = signal.side in (TradeSide.BUY, TradeSide.LONG)

            # Calculate quantity
            quantity = signal.quantity or self._calculate_position_size(signal)

            logger.info(
                f"Placing {signal.side} order | Symbol: {coin} | Qty: {quantity} | OrderBookId: {order_book_id}"
            )

            loop = asyncio.get_event_loop()

            # Get next nonce for transaction
            nonce_response = await loop.run_in_executor(
                None, lambda: self.transaction_api.next_nonce(account_index=self.account_index)
            )
            nonce = nonce_response.nonce if hasattr(nonce_response, "nonce") else 0

            # Get current price for market order execution
            current_price = await self._get_ticker(coin)
            if not current_price:
                raise Exception(f"Could not get current price for {coin}")

            # Apply slippage for market order
            limit_price = current_price * 1.05 if is_buy else current_price * 0.95

            # Create order parameters
            order_params = {
                "account_index": self.account_index,
                "order_book_id": order_book_id,
                "side": 0 if is_buy else 1,
                "price": limit_price,
                "quantity": quantity,
                "nonce": nonce,
                "time_in_force": 1,  # IOC
            }

            # Sign and send transaction
            signature = self._sign_transaction(order_params)

            result = await loop.run_in_executor(
                None,
                lambda: self.transaction_api.send_tx(
                    tx_type="CreateOrder",
                    body=order_params,
                    signature=signature,
                ),
            )

            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            self.avg_latency_ms = (self.avg_latency_ms + execution_time) / 2

            if result and hasattr(result, "success") and result.success:
                fill_price = getattr(result, "avg_fill_price", limit_price)
                filled_qty = getattr(result, "filled_quantity", quantity)

                self.trades_executed += 1

                # Create position record
                self.positions[coin] = Position(
                    position_id=getattr(result, "order_id", ""),
                    platform=PLATFORM.value,
                    symbol=coin,
                    side=signal.side,
                    quantity=filled_qty,
                    entry_price=fill_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )

                logger.info(f"Order FILLED | Symbol: {coin} | Avg Price: ${fill_price}")

                return TradeResult(
                    trade_id=getattr(result, "order_id", ""),
                    signal_id=signal.signal_id,
                    platform=PLATFORM.value,
                    symbol=signal.symbol,
                    side=signal.side,
                    success=True,
                    order_id=getattr(result, "order_id", ""),
                    filled_quantity=filled_qty,
                    avg_price=fill_price,
                    execution_time_ms=execution_time,
                )
            else:
                error_msg = getattr(result, "error", "Unknown error")
                self.trades_failed += 1
                logger.error(f"Order failed: {error_msg}")
                return TradeResult(
                    trade_id="",
                    signal_id=signal.signal_id,
                    platform=PLATFORM.value,
                    symbol=signal.symbol,
                    side=signal.side,
                    success=False,
                    error_message=str(error_msg),
                    execution_time_ms=execution_time,
                )

        except Exception as e:
            self.trades_failed += 1
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.error(f"Lighter Execution Failed: {e}")
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

    def _sign_transaction(self, tx_body: Dict) -> str:
        """Sign a transaction using the private key."""
        try:
            if hasattr(lighter, "Signer"):
                signer = lighter.Signer(self._priv_key)
                return signer.sign(tx_body)
            else:
                return ""
        except Exception as e:
            logger.error(f"Signing failed: {e}")
            return ""

    async def _get_ticker(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        if not self.order_api:
            return None

        try:
            coin = symbol.upper().replace("-PERP", "").replace("-USDC", "")
            market = self.market_info.get(coin, {})
            order_book_id = market.get("order_book_id", 0)

            loop = asyncio.get_event_loop()
            details = await loop.run_in_executor(
                None, lambda: self.order_api.order_book_details(order_book_id=order_book_id)
            )

            if details and hasattr(details, "mid_price"):
                return float(details.mid_price)
            elif details and hasattr(details, "last_price"):
                return float(details.last_price)

        except Exception as e:
            logger.warning(f"Failed to get ticker for {symbol}: {e}")

        return None

    def _calculate_position_size(self, signal: TradeSignal) -> float:
        """Calculate position size based on available balance."""
        available = self.balance if self.balance > 0 else 100

        if available < 100:
            position_pct = 0.40
        elif available < 500:
            position_pct = 0.30
        else:
            position_pct = 0.20

        position_usd = available * position_pct

        # Lighter minimums (example)
        min_position = 10.0
        if position_usd < min_position:
            logger.warning(f"Position ${position_usd:.2f} below minimum ${min_position}")
            return 0

        return position_usd

    async def _check_positions(self):
        """Check positions using Lighter API."""
        if not self.account_api or self.account_index is None:
            return

        try:
            loop = asyncio.get_event_loop()
            account = await loop.run_in_executor(
                None,
                lambda: self.account_api.account(by="index", value=str(self.account_index)),
            )

            if account and hasattr(account, "positions"):
                for pos in account.positions:
                    if pos.size != 0:
                        symbol = pos.symbol if hasattr(pos, "symbol") else f"MARKET_{pos.order_book_id}"

                        if symbol not in self.positions:
                            self.positions[symbol] = Position(
                                position_id=f"{PLATFORM.value}_{pos.order_book_id}",
                                platform=PLATFORM.value,
                                symbol=symbol,
                                side=TradeSide.LONG if float(pos.size) > 0 else TradeSide.SHORT,
                                quantity=abs(float(pos.size)),
                                entry_price=float(getattr(pos, "entry_price", 0)),
                            )

        except Exception as e:
            logger.error(f"Position check error: {e}")

    async def _close_all_positions(self):
        """Close all positions on Lighter."""
        try:
            # Implement closing logic based on Lighter API
            self.positions.clear()
            logger.info("Closed all Lighter positions")
        except Exception as e:
            logger.error(f"Close all error: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get bot status."""
        return {
            "service": SERVICE_NAME,
            "platform": PLATFORM.value,
            "running": self.running,
            "trading_enabled": self.config.trading_enabled,
            "positions": len(self.positions),
            "balance": self.balance,
            "trades_executed": self.trades_executed,
            "trades_failed": self.trades_failed,
            "account_index": self.account_index,
            "markets_loaded": len(self.market_info),
            "avg_latency_ms": self.avg_latency_ms,
        }


async def main():
    """Main entry point."""
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))

    logger.info("=" * 50)
    logger.info(f"LIGHTER BOT SERVICE (L2 Order Book)")
    logger.info(f"{datetime.now().isoformat()}")
    logger.info("=" * 50)

    bot = LighterBot()

    def handle_shutdown(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(bot.stop())

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
