"""
Hyperliquid Trading Bot - Standalone Service

This is an independent microservice for trading on Hyperliquid L1.
Optimized for Hyperliquid's sub-second block times and high TPS.
"""

import asyncio
import logging
import os
import signal
import sys
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
SERVICE_NAME = "bot-hyperliquid"
PLATFORM = Platform.HYPERLIQUID

# Hyperliquid uses 'k' prefix for 1000x multiplied micro-cap tokens
HL_SYMBOL_MAP = {
    "BONK": "kBONK",
    "PEPE": "kPEPE",
    "FLOKI": "kFLOKI",
    "SHIB": "kSHIB",
}

# Hyperliquid-specific settings
HL_API_URL = os.getenv("HL_API_URL", "https://api.hyperliquid.xyz")
HL_WS_URL = os.getenv("HL_WS_URL", "wss://api.hyperliquid.xyz/ws")


class HyperliquidBot:
    """
    Standalone Hyperliquid trading bot.

    Optimizations for Hyperliquid:
    - Sub-second block times for fast execution
    - Native leverage up to 50x
    - Websocket feeds for real-time orderbook
    - IOC orders for HFT strategies
    """

    def __init__(self):
        self.config = ServiceConfig(PLATFORM)
        self.running = False
        self._shutdown_event = asyncio.Event()

        # HL SDK components
        self.info = None
        self.exchange = None
        self.wallet_address = None

        # Position tracking
        self.positions: Dict[str, Position] = {}
        self.balance: float = 0.0

        # HL-specific metrics
        self.funding_rate: float = 0.0
        self.open_interest: float = 0.0

        # Performance
        self.trades_executed = 0
        self.trades_failed = 0
        self.avg_latency_ms = 0.0

        # HFT Optimization: Price cache to avoid blocking calls during execution
        self._price_cache: Dict[str, float] = {}
        self._price_cache_time: float = 0.0
        self._price_cache_ttl: float = 1.0  # 1 second TTL

    async def initialize(self):
        """Initialize Hyperliquid connection."""
        logger.info(f"🚀 Initializing {SERVICE_NAME}...")

        try:
            # Get credentials
            secret_key = os.getenv("HL_SECRET_KEY")
            self.wallet_address = os.getenv("HL_ACCOUNT_ADDRESS")

            if not secret_key or not self.wallet_address:
                logger.error("❌ HL_SECRET_KEY or HL_ACCOUNT_ADDRESS not configured")
                return False

            # Import Hyperliquid SDK
            from eth_account import Account
            from hyperliquid.exchange import Exchange
            from hyperliquid.info import Info
            from hyperliquid.utils import constants

            # Initialize Info client
            # Enable WS for real-time updates (runs in background thread)
            self.info = Info(constants.MAINNET_API_URL, skip_ws=False)

            # Create LocalAccount for signing - CRITICAL: Must be Account object, not string
            if not secret_key:
                raise ValueError("HL_SECRET_KEY is required")

            # Ensure proper hex format
            if not secret_key.startswith("0x"):
                secret_key = "0x" + secret_key

            try:
                wallet = Account.from_key(secret_key)
                logger.info(f"✅ Created Hyperliquid LocalAccount: {wallet.address}")

                # Validate it's actually an Account object
                if not hasattr(wallet, "sign_message"):
                    raise TypeError(f"Invalid wallet type: {type(wallet)}")

            except Exception as e:
                logger.error(f"❌ Failed to create LocalAccount: {e}")
                raise ValueError(f"Invalid HL_SECRET_KEY: {e}")

            # Initialize Exchange with LocalAccount (NO FALLBACK)
            self.exchange = Exchange(
                wallet=wallet,  # Must be LocalAccount with sign_message method
                base_url=constants.MAINNET_API_URL,
            )

            logger.info(f"🔑 HL wallet: {self.wallet_address}")

            # Initialize Pub/Sub
            pubsub = get_pubsub_client()
            await pubsub.initialize()

            await subscribe("trading-signals", self._handle_signal)
            await subscribe("risk-alerts", self._handle_risk_alert)

            logger.info(f"✅ {SERVICE_NAME} initialized successfully")
            return True

        except ImportError as e:
            logger.warning(f"⚠️ Hyperliquid SDK not available: {e}")
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
            # HFT: Pre-warm price cache before trading
            await self._warm_price_cache()

            # Perform initial state verification
            await self._verify_state()

            tasks = [
                self._main_loop(),  # Local Strategy
                self._gateway_loop(),  # Hub Commands
                self._balance_sync_loop(),  # Maintenance
                self._funding_monitor_loop(),  # Maintenance
                self._price_cache_loop(),  # HFT: Keep prices fresh
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

    async def stop(self):
        """Gracefully stop the bot."""
        logger.info(f"🛑 Stopping {SERVICE_NAME}...")
        self.running = False
        self._shutdown_event.set()

    async def _main_loop(self):
        """Main trading loop optimized for HL's fast execution."""
        # HL has very fast blocks, can check frequently
        loop_interval = 0.25  # 250ms

        while self.running:
            try:
                await self._check_positions()
                await asyncio.sleep(loop_interval)
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(2)

    async def _funding_monitor_loop(self):
        """Monitor funding rates for arbitrage opportunities."""
        while self.running:
            try:
                if self.info:
                    meta = await asyncio.to_thread(self.info.meta)
                    # Extract funding data
                    for market in meta.get("universe", []):
                        if market.get("name") == "ETH":
                            self.funding_rate = float(market.get("funding", 0))

                    logger.debug(f"ETH Funding Rate: {self.funding_rate:.4%}")
            except Exception as e:
                logger.error(f"Funding monitor error: {e}")
            await asyncio.sleep(60)  # Check every minute

    async def _balance_sync_loop(self):
        """Sync balance with Hyperliquid."""
        while self.running:
            try:
                if self.info and self.wallet_address:
                    user_state = await asyncio.to_thread(self.info.user_state, self.wallet_address)

                    margin_summary = user_state.get("marginSummary", {})
                    self.balance = float(margin_summary.get("accountValue", 0))

                    await publish(
                        "balance-updates",
                        BalanceUpdate(
                            platform=PLATFORM,
                            total_balance=self.balance,
                            available_balance=float(margin_summary.get("availableBalance", 0)),
                            margin_used=float(margin_summary.get("marginUsed", 0)),
                            assets={"USDC": self.balance},
                        ),
                    )
            except Exception as e:
                logger.error(f"Balance sync error: {e}")
            await asyncio.sleep(30)

    async def _warm_price_cache(self):
        """Pre-warm price cache on startup for HFT latency."""
        try:
            import time

            all_mids = await asyncio.to_thread(self.info.all_mids)
            self._price_cache = {k: float(v) for k, v in all_mids.items()}
            self._price_cache_time = time.time()
            logger.info(f"⚡ Price cache warmed: {len(self._price_cache)} coins")
        except Exception as e:
            logger.warning(f"Price cache warm failed: {e}")

    async def _price_cache_loop(self):
        """Keep price cache fresh for HFT execution (500ms refresh)."""
        import time

        while self.running:
            try:
                all_mids = await asyncio.to_thread(self.info.all_mids)
                self._price_cache = {k: float(v) for k, v in all_mids.items()}
                self._price_cache_time = time.time()
            except Exception as e:
                logger.debug(f"Price cache refresh error: {e}")
            await asyncio.sleep(0.5)  # 500ms refresh for HFT

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
            logger.info("🔍 STARTING DEEP VERIFICATION: HYPERLIQUID")

            user_state = await asyncio.to_thread(self.info.user_state, self.wallet_address)
            margin_summary = user_state.get("marginSummary", {})
            balance = margin_summary.get("accountValue", 0)
            logger.info(f"📊 HL VERIFICATION_REPORT | BALANCE: {balance} | RAW: {margin_summary}")

            # Check Positions
            asset_positions = user_state.get("assetPositions", [])
            active = [p for p in asset_positions if float(p.get("position", {}).get("szi", 0)) != 0]
            count = len(active)
            logger.info(f"📊 HL VERIFICATION_REPORT | OPEN_POSITIONS_COUNT: {count}")
            if count > 0:
                logger.warning(f"⚠️ HL HAS OPEN POSITIONS: {active}")
            else:
                logger.info("✅ HL POSITIONS: CLEARED")

        except Exception as e:
            logger.error(f"❌ HL VERIFICATION FAILED: {e}")

    async def _execute_trade(self, signal: TradeSignal) -> TradeResult:
        """Execute trade on Hyperliquid with HFT-optimized latency."""
        start_time = datetime.now()

        try:
            if not self.exchange:
                raise Exception("Exchange not initialized")

            # Convert symbol (HL uses just the base, e.g., "ETH" not "ETH-USDC")
            base_symbol = (
                signal.symbol.replace("-USDC", "").replace("-PERP", "").replace("USDT", "")
            )

            # Apply Hyperliquid-specific symbol mapping (e.g., BONK -> 1000BONK)
            coin = HL_SYMBOL_MAP.get(base_symbol, base_symbol)

            # HFT OPTIMIZATION: Use cached price. Do NOT block for refresh.
            import time

            now = time.time()
            if now - self._price_cache_time > self._price_cache_ttl:
                logger.warning(f"Using stale price cache ({now - self._price_cache_time:.2f}s old)")

            if coin not in self._price_cache:
                logger.warning(f"Coin {coin} not in cache, fetching sync (latency penalty)")
                try:
                    all_mids = await asyncio.to_thread(self.info.all_mids)
                    self._price_cache = {k: float(v) for k, v in all_mids.items()}
                    self._price_cache_time = now
                except Exception as e:
                    logger.error(f"Price fetch failed: {e}")
                    raise e

            mid_price = self._price_cache.get(coin, 0)

            if mid_price <= 0:
                available_coins = list(self._price_cache.keys())[:20]
                logger.error(
                    f"❌ Could not get price for '{coin}'. Available coins (partial): {available_coins}"
                )
                raise Exception(f"Could not get price for {coin}")

            # Calculate limit price with slippage
            is_buy = signal.side in (TradeSide.BUY, TradeSide.LONG)
            slippage = 0.005  # 0.5%
            limit_price = mid_price * (1 + slippage) if is_buy else mid_price * (1 - slippage)

            # Calculate quantity
            quantity = signal.quantity or self._calculate_position_size(signal, mid_price)

            # PRECISION NORMALIZER: Ensure order meets exchange requirements
            from shared.precision_normalizer import normalize_order

            normalized = await normalize_order(
                symbol=coin,
                platform="hyperliquid",
                price=limit_price,
                quantity=quantity,
                side="BUY" if is_buy else "SELL",
            )

            if not normalized["valid"]:
                logger.warning(f"⚠️ Order validation failed: {normalized['warnings']}")
                # Still attempt if only warnings, but log them

            # Use normalized values
            limit_price = normalized["price"]
            quantity = normalized["quantity"]

            logger.info(f"📐 Normalized order: {coin} @ ${limit_price:.4f} x {quantity:.6f}")

            # HFT OPTIMIZATION: Direct order execution with minimal overhead
            order_result = await asyncio.to_thread(
                self.exchange.order,
                coin,
                is_buy,
                quantity,
                limit_price,
                {"limit": {"tif": "Ioc"}},  # Immediate or Cancel (HFT)
            )

            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            self.avg_latency_ms = (self.avg_latency_ms + execution_time) / 2
            logger.info(
                f"⚡ Execution Latency: {execution_time:.2f}ms (Avg: {self.avg_latency_ms:.2f}ms)"
            )

            if order_result.get("status") == "ok":
                # Deep check of order status
                response_data = order_result.get("response", {}).get("data", {})
                statuses = response_data.get("statuses", [])

                if not statuses:
                    # Unusual case
                    logger.error(f"❌ Order OK but no status items: {order_result}")
                    return TradeResult(
                        trade_id="",
                        signal_id="",
                        platform=PLATFORM,
                        symbol=signal.symbol,
                        side=signal.side,
                        success=False,
                        error_message="No status returned",
                    )

                first_status = statuses[0]

                # Check for error in status (e.g., {"error": "..."})
                if "error" in first_status:
                    error_msg = first_status["error"]
                    logger.error(f"❌ Trade REJECTED by Engine: {error_msg} | Resp: {first_status}")
                    self.trades_failed += 1
                    return TradeResult(
                        trade_id="",
                        signal_id=signal.signal_id,
                        platform=PLATFORM,
                        symbol=signal.symbol,
                        side=signal.side,
                        success=False,
                        error_message=error_msg,
                    )

                # If we get here, it submitted successfully (resting or filled)
                # For IoC, if it wasn't filled, it might be cancelled immediately?
                # Usually returns {"filled": ...} or {"resting": ...}

                oid = first_status.get("resting", {}).get("oid") or first_status.get(
                    "filled", {}
                ).get("oid")
                if not oid:
                    # Check if it was purely IOC and killed?
                    # Sometimes 'status': 'filled' contains details directly?
                    # fallback
                    oid = "unknown"

                self.trades_executed += 1

                # Create position record
                self.positions[coin] = Position(
                    position_id=str(oid),
                    platform=PLATFORM,
                    symbol=coin,
                    side=signal.side,
                    quantity=quantity,
                    entry_price=limit_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )

                return TradeResult(
                    trade_id=str(oid),
                    signal_id=signal.signal_id,
                    platform=PLATFORM,
                    symbol=signal.symbol,
                    side=signal.side,
                    success=True,
                    filled_quantity=quantity,
                    avg_price=limit_price,
                    execution_time_ms=execution_time,
                )
            else:
                self.trades_failed += 1
                return TradeResult(
                    trade_id="",
                    signal_id=signal.signal_id if signal else "",
                    platform=PLATFORM,
                    symbol=signal.symbol if signal else "",
                    side=signal.side if signal else TradeSide.BUY,
                    success=False,
                    error_message=f"API connection error: {order_result}",
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

    def _calculate_position_size(self, signal: TradeSignal, price: float) -> float:
        """
        Calculate position size dynamically based on Hyperliquid account balance.

        Adapts to available funds - uses percentage based on account size.

        Args:
            signal: Trade signal
            price: Current market price

        Returns:
            Quantity in base asset (e.g., number of SOL, BTC, etc.)
        """
        # Use current balance (synced via _balance_sync_loop)
        available_usd = self.balance if self.balance > 0 else 100  # Default if not synced yet

        # Dynamic percentage based on account size
        if available_usd < 100:
            position_pct = 0.50  # Small account: 50%
        elif available_usd < 500:
            position_pct = 0.30  # Medium account: 30%
        else:
            position_pct = 0.20  # Larger account: 20%

        # Calculate USD position size
        position_usd = available_usd * position_pct

        # Convert to base asset quantity
        quantity = position_usd / price if price > 0 else 0

        # Round to appropriate precision (Hyperliquid uses 4 decimals for most)
        quantity = round(quantity, 4)

        logger.info(
            f"💰 HL Dynamic Sizing: Balance=${available_usd:.2f}, "
            f"Using {position_pct*100:.0f}% = ${position_usd:.2f} "
            f"({quantity} @ ${price:.2f})"
        )

        return quantity

    async def _check_positions(self):
        """Check positions on Hyperliquid."""
        if not self.info or not self.wallet_address:
            return

        try:
            user_state = await asyncio.to_thread(self.info.user_state, self.wallet_address)

            asset_positions = user_state.get("assetPositions", [])
            for pos_data in asset_positions:
                pos = pos_data.get("position", {})
                coin = pos.get("coin")
                size = float(pos.get("szi", 0))

                if size != 0 and coin:
                    if coin in self.positions:
                        self.positions[coin].current_price = float(pos.get("entryPx", 0))
                        self.positions[coin].unrealized_pnl = float(pos.get("unrealizedPnl", 0))

        except Exception as e:
            logger.error(f"Position check error: {e}")

    async def _close_all_positions(self):
        """Close all positions on HL."""
        try:
            if self.exchange and self.info:
                user_state = await asyncio.to_thread(self.info.user_state, self.wallet_address)

                for pos_data in user_state.get("assetPositions", []):
                    pos = pos_data.get("position", {})
                    coin = pos.get("coin")
                    size = float(pos.get("szi", 0))

                    if size != 0:
                        # Market close
                        is_buy = size < 0  # Close short = buy, close long = sell
                        await asyncio.to_thread(self.exchange.market_close, coin)

                self.positions.clear()
                logger.info("✅ Closed all Hyperliquid positions")
        except Exception as e:
            logger.error(f"Close all error: {e}")

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
            "funding_rate": self.funding_rate,
            "avg_latency_ms": self.avg_latency_ms,
        }


async def main():
    """Main entry point."""
    setup_logging(os.getenv("LOG_LEVEL", "INFO"))

    logger.info("=" * 50)
    logger.info(f"🌊 HYPERLIQUID BOT SERVICE")
    logger.info(f"📅 {datetime.now().isoformat()}")
    logger.info("=" * 50)

    bot = HyperliquidBot()

    def handle_shutdown(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        asyncio.create_task(bot.stop())

    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
# Syntax Validated
