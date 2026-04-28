"""Aster DEX perpetuals trading bot — standalone service.

Solana-native perp DEX with a CEX-style REST/WebSocket API. Consumes
trading signals via pubsub, executes with the Shield HFT strategy,
and publishes fills/positions back for portfolio tracking.
"""

import asyncio
import logging
import os
import signal

# Add shared library to path
import sys
import time
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from circuit_breaker import CircuitBreaker, CircuitBreakerOpen
from execution_idempotency import ExecutionIdempotency
from models import (
    BalanceUpdate,
    Platform,
    Position,
    SignalType,
    TradeResult,
    TradeSide,
    TradeSignal,
)
from pubsub import get_pubsub_client, publish, subscribe
from utils import ServiceConfig, setup_logging

logger = logging.getLogger(__name__)

# Service configuration
SERVICE_NAME = "bot-aster"
PLATFORM = Platform.ASTER

_PAPER_TRADING_TRUE = {"1", "true", "yes", "y", "on"}
_PAPER_TRADING_FALSE = {"0", "false", "no", "n", "off"}


def _paper_trading_env_enabled() -> bool:
    """Return paper-trading mode, defaulting safely to enabled."""
    raw = os.getenv("PAPER_TRADING")
    if raw is None or raw.strip() == "":
        return True

    value = raw.strip().lower()
    if value in _PAPER_TRADING_TRUE:
        return True
    if value in _PAPER_TRADING_FALSE:
        return False

    logger.warning("Aster: unrecognized PAPER_TRADING=%r; defaulting to paper", raw)
    return True


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
        self.positions: dict[str, Position] = {}
        self.balance: float = 0.0

        # Order management
        self.open_orders: dict[str, dict] = {}
        self.trailing_stops: dict[str, dict] = {}

        # Performance
        self.trades_executed = 0
        self.trades_failed = 0
        self.total_fees = 0.0

        # Firestore client shared by idempotency guard + position persistence.
        self._db = None
        # Signal idempotency guard: Firestore-backed (durable across restarts) with
        # in-memory fast path.
        self._idempotency: ExecutionIdempotency | None = None
        self._signal_dedupe_ttl_seconds = max(
            60, int(os.getenv("SIGNAL_DEDUPE_TTL_SECONDS", "900"))
        )

        # Circuit breaker: open after 5 consecutive venue API failures, reset after 120s.
        self._circuit_breaker = CircuitBreaker(
            "aster",
            fail_max=int(os.getenv("ASTER_CIRCUIT_BREAKER_FAIL_MAX", "5")),
            reset_timeout=float(os.getenv("ASTER_CIRCUIT_BREAKER_RESET_SECONDS", "120")),
        )

        # Paper trading mode defaults on. Real venue execution requires an
        # explicit PAPER_TRADING=0/false environment choice.
        self.is_paper_trading = _paper_trading_env_enabled()

        # Telemetry publishing (consumed by api-gateway for realtime dashboard)
        self._position_publish_interval_seconds = max(
            3, int(os.getenv("POSITION_PUBLISH_INTERVAL_SECONDS", "10"))
        )

        # Optional signal auto-sizing for edge workers receiving signals without explicit quantity.
        # Disabled by default in cloud; enable on trusted edge nodes with a small notional budget.
        self._auto_size_notional_usd = max(
            0.0, float(os.getenv("ASTER_AUTO_SIZE_NOTIONAL_USD", "0") or 0)
        )
        self._auto_size_fallback_quantity = max(
            0.0, float(os.getenv("ASTER_AUTO_SIZE_FALLBACK_QUANTITY", "0.01") or 0.01)
        )

        # Cache leverage set per-symbol to avoid spamming the exchange API.
        self._last_leverage_by_symbol: dict[str, int] = {}

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
                account_info = await self.client.get_account_info()
                wallet_balance = (
                    account_info.get("availableBalance")
                    or account_info.get("totalWalletBalance")
                    or "n/a"
                )
                logger.info(f"✅ Aster API accessible (wallet balance: {wallet_balance})")
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

            # Initialize Firestore-backed idempotency guard and warm from recent history.
            try:
                from google.cloud import firestore as _fs

                _fs_client = _fs.AsyncClient(project=os.getenv("GCP_PROJECT_ID", "sapphire-479610"))
                self._db = _fs_client
                self._idempotency = ExecutionIdempotency(
                    platform=PLATFORM.value,
                    firestore_client=_fs_client,
                    ttl_seconds=self._signal_dedupe_ttl_seconds,
                )
                warmed = await self._idempotency.warm_from_firestore()
                logger.info(
                    "✅ Idempotency guard ready (warmed %d recent IDs from Firestore)", warmed
                )
            except Exception as _idem_err:
                logger.warning("⚠️ Idempotency guard degraded to memory-only: %s", _idem_err)
                self._idempotency = ExecutionIdempotency(
                    platform=PLATFORM.value,
                    firestore_client=None,
                    ttl_seconds=self._signal_dedupe_ttl_seconds,
                )

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
                self._balance_sync_loop(),
                self._position_publish_loop(),
                self._trailing_stop_loop(),
            ]
            await asyncio.gather(*tasks)

        except asyncio.CancelledError:
            logger.info("Bot stopped via cancellation")

    async def _gateway_loop(self):
        """Listen for Hub commands."""
        logger.info("Gateway Loop Started (Listening on /execute)")

        while self.running:
            has_command = False
            try:
                # Wait for command from Queue (pushed by Gateway Server)
                command = await self.command_queue.get()
                has_command = True
                logger.info(f"📥 Processing Hub Command: {command}")

                if not isinstance(command, dict):
                    logger.warning(f"Ignoring non-dict gateway command: {type(command)}")
                    continue

                action = str(command.get("action", "")).strip().upper()
                if action in {"HALT_TRADING", "RESUME_TRADING", "CLOSE_ALL"}:
                    await self._handle_risk_alert(
                        {
                            "action": action.lower(),
                            "message": f"Gateway command: {action}",
                        }
                    )
                    logger.info(f"✅ Applied gateway risk command: {action}")
                    continue

                if action in {"HEARTBEAT", "STATUS", "CONTROL_STATUS"}:
                    logger.info(f"✅ Gateway control command acknowledged: {action}")
                    continue

                signal = self._build_signal_from_gateway_command(command)
                if signal is None:
                    logger.warning(f"Ignoring unsupported gateway command payload: {command}")
                    continue

                logger.info(
                    f"⚡ EXECUTING HUB COMMAND: {signal.side} {signal.quantity} {signal.symbol}"
                )
                result = await self._execute_trade(signal)
                logger.info(f"✅ Hub Command Executed: {result.success}")
                await publish("trade-executed", result)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Gateway Error: {e}")
                await asyncio.sleep(1)
            finally:
                if has_command:
                    self.command_queue.task_done()

        logger.info("🔌 Gateway Loop Ended")
        await self.user_stream.stop()

    def _build_signal_from_gateway_command(self, command: dict[str, Any]) -> TradeSignal | None:
        """Normalize legacy and action-style gateway payloads into TradeSignal objects."""
        command_type = str(command.get("type", "")).strip().upper()
        action = str(command.get("action", "")).strip().upper()
        if command_type == "ARB_EXECUTE" and not action:
            action = str(command.get("side", "BUY")).strip().upper()

        if action not in {"BUY", "SELL", "LONG", "SHORT", "CLOSE"}:
            return None

        symbol = str(command.get("symbol", "SOL")).strip().upper() or "SOL"

        raw_qty = command.get("quantity", 0.0)
        try:
            quantity = float(raw_qty)
        except (TypeError, ValueError):
            quantity = 0.0

        signal_side: TradeSide
        signal_type = SignalType.ENTRY

        if action == "CLOSE":
            position = self.positions.get(symbol)
            if position is None:
                logger.warning(f"Ignoring CLOSE command for {symbol}: no tracked position")
                return None
            if quantity <= 0:
                quantity = float(position.quantity)
            signal_side = (
                TradeSide.SELL
                if position.side in (TradeSide.BUY, TradeSide.LONG)
                else TradeSide.BUY
            )
            signal_type = SignalType.EXIT
        else:
            if quantity <= 0:
                logger.warning(
                    f"Ignoring {action} command for {symbol}: invalid quantity {raw_qty}"
                )
                return None
            signal_side = TradeSide.BUY if action in {"BUY", "LONG"} else TradeSide.SELL

        signal_id = (
            str(command.get("signal_key", "")).strip() or str(command.get("signal_id", "")).strip()
        )
        if not signal_id:
            signal_id = f"hub-{int(time.time() * 1000)}"

        return TradeSignal(
            signal_id=signal_id,
            symbol=symbol,
            side=signal_side,
            signal_type=signal_type,
            confidence=1.0,
            source=str(command.get("source", "")).strip() or "alpha-hub",
            quantity=quantity,
            metadata={"gateway_action": action},
        )

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

    async def _position_publish_loop(self):
        """Periodically publish a snapshot of positions for the realtime dashboard."""
        from dataclasses import asdict
        from datetime import datetime

        while self.running:
            try:
                positions_payload = []
                for position in self.positions.values():
                    try:
                        positions_payload.append(asdict(position))
                    except Exception:
                        continue

                await publish(
                    "position-updates",
                    {
                        "platform": PLATFORM.value,
                        "positions": positions_payload,
                    },
                )

                # Persist snapshot to Firestore for position reconciliation.
                if self._db is not None:
                    try:
                        doc_ref = self._db.collection("live_positions").document(PLATFORM.value)
                        await doc_ref.set(
                            {
                                "platform": PLATFORM.value,
                                "position_count": len(positions_payload),
                                "positions": positions_payload,
                                "updated_at": datetime.now(UTC),
                            }
                        )
                    except Exception as _fs_err:
                        logger.debug("Position Firestore write error: %s", _fs_err)

            except Exception as e:
                logger.error(f"Position publish error: {e}")
            await asyncio.sleep(self._position_publish_interval_seconds)

    async def _handle_user_event(self, event: dict[str, Any]):
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

    async def _handle_signal(self, signal_data: dict[str, Any]):
        """Handle incoming trading signal."""
        try:
            payload = self._sanitize_trade_signal_payload(signal_data)
            signal = TradeSignal(**payload)

            if not signal.should_execute_on(PLATFORM.value):
                return

            if not self.config.trading_enabled:
                logger.info(f"⏸️ Trading disabled, ignoring signal: {signal.symbol}")
                return

            metadata = signal.metadata or {}
            if bool(metadata.get("dry_run", False)):
                logger.info(f"🧪 Dry-run signal ignored on {PLATFORM}: {signal.signal_id}")
                return

            if signal.quantity is None:
                auto_quantity = await self._derive_auto_quantity(signal)
                if auto_quantity is None:
                    logger.warning(
                        f"🧯 Rejected signal without explicit quantity on {PLATFORM}: "
                        f"{signal.signal_id} {signal.symbol}"
                    )
                    return
                signal.quantity = auto_quantity
                metadata = {
                    **metadata,
                    "auto_sized": True,
                    "auto_size_notional_usd": self._auto_size_notional_usd,
                    "auto_size_quantity": auto_quantity,
                }
                signal.metadata = metadata
                logger.info(
                    f"🧮 Auto-sized signal quantity on {PLATFORM}: "
                    f"{signal.signal_id} {signal.symbol} qty={auto_quantity}"
                )

            signal_id = str(signal.signal_id or "").strip()
            if not signal_id:
                logger.warning(
                    f"🧯 Rejected signal without signal_id on {PLATFORM}: {signal.symbol}"
                )
                return

            # Durable idempotency check (memory-first, Firestore-backed).
            idempotency = self._idempotency
            if idempotency is not None:
                claimed = await idempotency.claim(signal_id, signal.symbol)
                if not claimed:
                    return
            else:
                if self._is_duplicate_signal(signal_id):
                    logger.warning(f"🧯 Duplicate signal ignored on {PLATFORM}: {signal_id}")
                    return
                self._mark_signal_processed(signal_id)

            logger.info(f"📥 Received signal: {signal.side} {signal.symbol}")
            result = await self._execute_trade(signal)

            # Persist outcome to idempotency store.
            if idempotency is not None:
                if result.success:
                    await idempotency.mark_executed(signal_id, result.order_id or "")
                else:
                    await idempotency.mark_failed(signal_id, result.error_message or "")

            # Don't emit trade events for explicit no-op signals (ex: reduce-only without exposure).
            if not (result.metadata or {}).get("noop"):
                await publish("trade-executed", result)

        except Exception as e:
            logger.error(f"Signal handling error: {e}")

    def _prune_processed_signals(self):
        now_ts = time.time()
        cutoff = now_ts - self._signal_dedupe_ttl_seconds
        stale = [key for key, ts in self._processed_signal_ids.items() if ts < cutoff]
        for key in stale:
            self._processed_signal_ids.pop(key, None)

    def _is_duplicate_signal(self, signal_id: str) -> bool:
        self._prune_processed_signals()
        return signal_id in self._processed_signal_ids

    def _mark_signal_processed(self, signal_id: str):
        self._processed_signal_ids[signal_id] = time.time()

    @staticmethod
    def _sanitize_trade_signal_payload(signal_data: dict[str, Any]) -> dict[str, Any]:
        """Drop unknown keys so malformed debug payloads don't break signal handling."""
        if not isinstance(signal_data, dict):
            return {}
        allowed = set(getattr(TradeSignal, "__dataclass_fields__", {}).keys())
        payload = {key: value for key, value in signal_data.items() if key in allowed}
        dropped = sorted(set(signal_data.keys()) - set(payload.keys()))
        if dropped:
            logger.warning(
                "Ignoring unsupported signal keys on %s: %s", PLATFORM.value, ",".join(dropped)
            )
        return payload

    async def _derive_auto_quantity(self, signal: TradeSignal) -> float | None:
        """Best-effort quantity derivation for trusted edge execution paths."""
        if self._auto_size_notional_usd <= 0:
            return None
        if not self.client:
            return (
                self._auto_size_fallback_quantity if self._auto_size_fallback_quantity > 0 else None
            )

        symbol = str(signal.symbol or "").strip().upper()
        normalized_symbol = (
            self.client._normalize_symbol(symbol)
            if hasattr(self.client, "_normalize_symbol")
            else symbol
        )
        raw_price = signal.entry_price
        if not raw_price or float(raw_price) <= 0:
            try:
                ticker = await self.client.get_ticker_price(normalized_symbol)
                raw_price = float((ticker or {}).get("price", 0) or 0)
            except Exception:
                raw_price = 0.0

        if raw_price and float(raw_price) > 0:
            return max(0.0, self._auto_size_notional_usd / float(raw_price))
        if self._auto_size_fallback_quantity > 0:
            return self._auto_size_fallback_quantity
        return None

    async def _handle_risk_alert(self, alert_data: dict[str, Any]):
        """Handle risk alerts."""
        action = alert_data.get("action", "none")
        logger.warning(f"⚠️ Risk alert: {alert_data.get('message')}")

        if action == "close_all":
            await self._close_all_positions()
        elif action == "halt_trading":
            self.config.trading_enabled = False
        elif action == "resume_trading":
            self.config.trading_enabled = True

    async def _verify_state(self):
        """Perform deep verification of account state."""
        try:
            logger.info("🔍 STARTING DEEP VERIFICATION: ASTER")

            # Check Funds
            info = await self.client.get_account_info()
            balance = info.get("availableBalance") or info.get("totalWalletBalance") or "N/A"
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

    @staticmethod
    def _to_decimal(value: Any, fallback: str = "0") -> Decimal:
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(fallback)

    @classmethod
    def _round_quantity(cls, quantity: float, step_size: Decimal, precision: int | None) -> float:
        qty = cls._to_decimal(quantity, "0")
        if step_size > 0:
            qty = (qty / step_size).to_integral_value(rounding=ROUND_DOWN) * step_size
        if isinstance(precision, int) and precision >= 0:
            quant = Decimal("1").scaleb(-precision)
            qty = qty.quantize(quant, rounding=ROUND_DOWN)
        if qty < 0:
            qty = Decimal("0")
        return float(qty)

    async def _prepare_aster_order(
        self, symbol: str, requested_quantity: float
    ) -> tuple[str, float]:
        """Normalize symbol/quantity and enforce exchange notional constraints before submit."""
        normalized_symbol = (
            self.client._normalize_symbol(symbol)
            if hasattr(self.client, "_normalize_symbol")
            else str(symbol or "").strip().upper()
        )
        filters = await self.client.get_symbol_filters(normalized_symbol)
        step_size = self._to_decimal(filters.get("step_size"), "1")
        min_qty = self._to_decimal(filters.get("min_qty"), "0")
        max_qty = self._to_decimal(filters.get("max_qty"), "0")
        min_notional = self._to_decimal(filters.get("min_notional"), "0")
        quantity_precision = filters.get("quantity_precision")

        quantity = self._round_quantity(requested_quantity, step_size, quantity_precision)
        if min_qty > 0 and Decimal(str(quantity)) < min_qty:
            quantity = self._round_quantity(float(min_qty), step_size, quantity_precision)

        if min_notional > 0:
            ticker = await self.client.get_ticker_price(normalized_symbol)
            mark_price = self._to_decimal((ticker or {}).get("price"), "0")
            if mark_price <= 0:
                raise ValueError(
                    f"Preflight failed for {normalized_symbol}: ticker price unavailable for min-notional check"
                )

            current_notional = mark_price * self._to_decimal(quantity, "0")
            if current_notional < min_notional:
                # Keep a small buffer to avoid edge rejects after rounding.
                required_qty = (min_notional * Decimal("1.02")) / mark_price
                quantity = self._round_quantity(float(required_qty), step_size, quantity_precision)
                if min_qty > 0 and Decimal(str(quantity)) < min_qty:
                    quantity = self._round_quantity(float(min_qty), step_size, quantity_precision)
                logger.info(
                    f"🧮 ASTER preflight quantity raised for min-notional: "
                    f"{requested_quantity} -> {quantity} ({normalized_symbol})"
                )

        if max_qty > 0 and Decimal(str(quantity)) > max_qty:
            raise ValueError(
                f"Preflight blocked for {normalized_symbol}: quantity {quantity} exceeds max {max_qty}"
            )
        if quantity <= 0:
            raise ValueError(
                f"Preflight blocked for {normalized_symbol}: non-positive quantity {quantity}"
            )

        return normalized_symbol, quantity

    async def _execute_trade(self, signal: TradeSignal) -> TradeResult:
        """Execute trade on Aster with advanced order types."""
        start_time = datetime.now()

        try:
            if not self.client:
                raise Exception("Aster client not initialized")

            reduce_only = bool((signal.metadata or {}).get("reduce_only", False))

            # Safety: require explicit quantity in inbound signal.
            if signal.quantity is None:
                raise ValueError("Signal quantity is required for live execution")

            # Calculate quantity
            quantity = float(signal.quantity)
            symbol = str(signal.symbol or "").strip().upper() or "SOLUSDT"
            symbol, quantity = await self._prepare_aster_order(symbol, float(quantity))

            # Determine order side
            side = "BUY" if signal.side in (TradeSide.BUY, TradeSide.LONG) else "SELL"

            # Reduce-only safety: avoid opening new exposure and avoid flipping through zero.
            if reduce_only:
                current = self.positions.get(symbol)
                current_qty = float(getattr(current, "quantity", 0.0) or 0.0) if current else 0.0
                if current_qty <= 0:
                    logger.info(f"🧯 Reduce-only ignored for {symbol}: no tracked position")
                    return TradeResult(
                        trade_id="noop",
                        signal_id=signal.signal_id,
                        platform=PLATFORM,
                        symbol=symbol,
                        side=signal.side,
                        success=True,
                        metadata={
                            "noop": True,
                            "reason": "reduce_only_no_position",
                            "reduce_only": True,
                        },
                    )

                current_side = getattr(current, "side", None)
                if (
                    current_side in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG")
                    and side != "SELL"
                ):
                    logger.info(
                        f"🧯 Reduce-only ignored for {symbol}: expected SELL to reduce long"
                    )
                    return TradeResult(
                        trade_id="noop",
                        signal_id=signal.signal_id,
                        platform=PLATFORM,
                        symbol=symbol,
                        side=signal.side,
                        success=True,
                        metadata={
                            "noop": True,
                            "reason": "reduce_only_direction_mismatch",
                            "reduce_only": True,
                        },
                    )

                if (
                    current_side in (TradeSide.SELL, TradeSide.SHORT, "SELL", "SHORT")
                    and side != "BUY"
                ):
                    logger.info(
                        f"🧯 Reduce-only ignored for {symbol}: expected BUY to reduce short"
                    )
                    return TradeResult(
                        trade_id="noop",
                        signal_id=signal.signal_id,
                        platform=PLATFORM,
                        symbol=symbol,
                        side=signal.side,
                        success=True,
                        metadata={
                            "noop": True,
                            "reason": "reduce_only_direction_mismatch",
                            "reduce_only": True,
                        },
                    )

                if quantity > current_qty:
                    quantity = current_qty
                if quantity <= 0:
                    return TradeResult(
                        trade_id="noop",
                        signal_id=signal.signal_id,
                        platform=PLATFORM,
                        symbol=symbol,
                        side=signal.side,
                        success=True,
                        metadata={
                            "noop": True,
                            "reason": "reduce_only_quantity_zero",
                            "reduce_only": True,
                        },
                    )

            desired_leverage: int | None = None
            if signal.leverage is not None:
                try:
                    desired_leverage = int(float(signal.leverage))
                except (TypeError, ValueError):
                    desired_leverage = None

            if (
                desired_leverage is not None
                and desired_leverage > 0
                and not self.is_paper_trading
                and self.client is not None
            ):
                desired_leverage = max(1, min(125, desired_leverage))
                previous = self._last_leverage_by_symbol.get(symbol)
                if previous != desired_leverage:
                    try:
                        await self.client.change_leverage(symbol, desired_leverage)
                        self._last_leverage_by_symbol[symbol] = desired_leverage
                        logger.info(f"🧯 Leverage set: {symbol} {desired_leverage}x")
                    except Exception as e:
                        logger.warning(
                            f"Failed to set leverage for {symbol} to {desired_leverage}x: {e}"
                        )

            logger.info(f"⚡ Executing on Aster: {symbol} {side} {quantity}")

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
                # Real execution — circuit breaker gates the venue API call.
                self._circuit_breaker.check()
                try:
                    from aster_client import OrderType

                    order_result = await self.client.place_order(
                        symbol=symbol,
                        side=side,
                        order_type=OrderType.MARKET,
                        quantity=quantity,
                        reduce_only=reduce_only,
                    )
                    logger.info(f"✅ Aster Order Result: {order_result}")
                    self._circuit_breaker.record_success()
                except CircuitBreakerOpen:
                    raise
                except Exception as _venue_err:
                    self._circuit_breaker.record_failure(_venue_err)
                    raise

                # Market orders can return NEW before exchange matching finishes.
                # Poll briefly for terminal status so telemetry reflects real fills.
                order_id = str(order_result.get("orderId", "") or "").strip()
                status = str(order_result.get("status", "")).upper()
                if order_id and status in {"", "NEW", "PENDING_NEW"}:
                    terminal_statuses = {
                        "FILLED",
                        "PARTIALLY_FILLED",
                        "CANCELED",
                        "EXPIRED",
                        "REJECTED",
                    }
                    for _ in range(max(1, int(os.getenv("ASTER_ORDER_STATUS_POLLS", "5")))):
                        await asyncio.sleep(
                            max(
                                0.05,
                                float(
                                    os.getenv("ASTER_ORDER_STATUS_POLL_INTERVAL_SECONDS", "0.35")
                                ),
                            )
                        )
                        try:
                            latest = await self.client.get_order(symbol=symbol, order_id=order_id)
                        except Exception:
                            latest = {}
                        if isinstance(latest, dict) and latest:
                            order_result = {**order_result, **latest}
                            status = str(order_result.get("status", "")).upper()
                            if status in terminal_statuses:
                                break
                    logger.info(f"📊 Aster Final Order State: {order_result}")

            execution_time = (datetime.now() - start_time).total_seconds() * 1000

            status = str(order_result.get("status", "")).upper()
            executed_qty = float(
                order_result.get("executedQty", order_result.get("cumQty", 0)) or 0
            )
            is_filled = status in ("FILLED", "PARTIALLY_FILLED") or executed_qty > 0

            if is_filled:
                self.trades_executed += 1

                filled_qty = executed_qty if executed_qty > 0 else float(quantity)
                avg_price = float(order_result.get("avgPrice", 0))

                # Create position record (reduce-only fills are reconciled via WS/REST sync).
                if not reduce_only:
                    self.positions[symbol] = Position(
                        position_id=order_result.get("orderId", ""),
                        platform=PLATFORM,
                        symbol=symbol,
                        side=signal.side,
                        quantity=filled_qty,
                        entry_price=avg_price,
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit,
                    )

                # Set up trailing stop if configured
                if (signal.metadata or {}).get("trailing_stop") and not reduce_only:
                    self.trailing_stops[symbol] = {
                        "trail_percent": signal.metadata.get("trail_percent", 0.02),
                        "stop_price": (
                            avg_price * (1 - 0.02) if side == "BUY" else avg_price * (1 + 0.02)
                        ),
                    }

                # Set TP/SL orders on exchange
                if signal.stop_loss and not reduce_only:
                    await self._place_stop_loss(symbol, signal.stop_loss, filled_qty, side)
                if signal.take_profit and not reduce_only:
                    await self._place_take_profit(symbol, signal.take_profit, filled_qty, side)

                return TradeResult(
                    trade_id=order_result.get("orderId", ""),
                    signal_id=signal.signal_id,
                    platform=PLATFORM,
                    symbol=symbol,
                    side=signal.side,
                    success=True,
                    order_id=order_result.get("orderId"),
                    filled_quantity=filled_qty,
                    avg_price=avg_price,
                    fee=float(order_result.get("commission", 0)),
                    execution_time_ms=execution_time,
                    metadata={
                        **(signal.metadata or {}),
                        "reduce_only": reduce_only,
                    },
                )
            else:
                self.trades_failed += 1
                return TradeResult(
                    trade_id="",
                    signal_id=signal.signal_id,
                    platform=PLATFORM,
                    symbol=symbol,
                    side=signal.side,
                    success=False,
                    error_message=order_result.get(
                        "msg", f"Order not filled (status={status or 'UNKNOWN'})"
                    ),
                    execution_time_ms=execution_time,
                )

        except CircuitBreakerOpen as _cb_err:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.warning("Trade blocked by circuit breaker: %s", _cb_err)
            return TradeResult(
                trade_id="",
                signal_id=signal.signal_id,
                platform=PLATFORM,
                symbol=str(signal.symbol or "").strip().upper() or "SOLUSDT",
                side=signal.side,
                success=False,
                error_message=str(_cb_err),
                execution_time_ms=execution_time,
                metadata={"circuit_breaker_open": True},
            )
        except Exception as e:
            self.trades_failed += 1
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.error(f"Aster Execution Failed: {e}")
            return TradeResult(
                trade_id="",
                signal_id=signal.signal_id,
                platform=PLATFORM,
                symbol=str(signal.symbol or "").strip().upper() or "SOLUSDT",
                side=signal.side,
                success=False,
                error_message=str(e),
                execution_time_ms=execution_time,
            )

    async def _place_stop_loss(self, symbol: str, price: float, quantity: float, entry_side: str):
        """Place native STOP_MARKET order on Aster for risk management."""
        try:
            from aster_client import OrderType, WorkingType

            exit_side = "SELL" if entry_side == "BUY" else "BUY"

            # Use native STOP_MARKET for reliable execution
            result = await self.client.place_order(
                symbol=symbol,
                side=exit_side,
                order_type=OrderType.STOP_MARKET,
                quantity=quantity,
                stop_price=price,
                reduce_only=True,
                working_type=WorkingType.MARK_PRICE,
            )
            order_id = result.get("orderId", "unknown")
            logger.info(f"✅ [ASTER] Native SL placed @ ${price:.2f} | OrderId: {order_id}")
            return result
        except Exception as e:
            logger.error(f"❌ Failed to place stop-loss: {e}")
            return None

    async def _place_take_profit(self, symbol: str, price: float, quantity: float, entry_side: str):
        """Place native TAKE_PROFIT_MARKET order on Aster for profit capture."""
        try:
            from aster_client import OrderType, WorkingType

            exit_side = "SELL" if entry_side == "BUY" else "BUY"

            # Use TAKE_PROFIT_MARKET for guaranteed execution at TP
            result = await self.client.place_order(
                symbol=symbol,
                side=exit_side,
                order_type=OrderType.TAKE_PROFIT_MARKET,
                quantity=quantity,
                stop_price=price,
                reduce_only=True,
                working_type=WorkingType.MARK_PRICE,
            )
            order_id = result.get("orderId", "unknown")
            logger.info(f"✅ [ASTER] Native TP placed @ ${price:.2f} | OrderId: {order_id}")
            return result
        except Exception as e:
            logger.error(f"❌ Failed to place take-profit: {e}")
            return None

    async def _place_trailing_stop(
        self, symbol: str, callback_rate: float, quantity: float, entry_side: str
    ):
        """Place native TRAILING_STOP_MARKET order on Aster for dynamic profit protection."""
        try:
            from aster_client import OrderType, WorkingType

            exit_side = "SELL" if entry_side == "BUY" else "BUY"

            # Use native TRAILING_STOP_MARKET - Aster supports this
            result = await self.client.place_order(
                symbol=symbol,
                side=exit_side,
                order_type=OrderType.TRAILING_STOP_MARKET,
                quantity=quantity,
                callback_rate=callback_rate,  # e.g., 1.0 = 1% trail
                reduce_only=True,
                working_type=WorkingType.MARK_PRICE,
            )
            order_id = result.get("orderId", "unknown")
            logger.info(
                f"✅ [ASTER] Native Trailing Stop placed @ {callback_rate}% | OrderId: {order_id}"
            )
            return result
        except Exception as e:
            logger.error(f"❌ Failed to place trailing stop: {e}")
            return None

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
            f"Using {position_pct * 100:.0f}% = ${position_usd:.2f}"
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

                if qty != 0 and symbol and symbol in self.positions:
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

        pos = self.positions.get(symbol)
        if pos is None:
            return

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
        """Close all positions (exchange source-of-truth with local fallback)."""
        if not self.client:
            logger.warning("Close-all ignored: Aster client not initialized")
            return

        exchange_positions: dict[str, float] = {}
        try:
            raw_positions = await self.client.get_position_risk()
            for row in raw_positions or []:
                symbol = str((row or {}).get("symbol", "")).strip().upper()
                qty = float((row or {}).get("positionAmt", 0) or 0)
                if symbol and abs(qty) > 0:
                    exchange_positions[symbol] = qty
        except Exception as exc:
            logger.warning(f"Failed to fetch exchange positions for close-all: {exc}")

        symbols = set(self.positions.keys()) | set(exchange_positions.keys())
        if not symbols:
            logger.info("Close-all requested but no positions are open")
            return

        closed = 0
        failed = 0
        for symbol in sorted(symbols):
            signed_qty = exchange_positions.get(symbol)
            if signed_qty is None:
                local = self.positions.get(symbol)
                if local is not None:
                    qty = float(getattr(local, "quantity", 0.0) or 0.0)
                    if qty > 0:
                        side = getattr(local, "side", None)
                        signed_qty = qty if side in (TradeSide.BUY, TradeSide.LONG) else -qty

            if signed_qty is None or abs(float(signed_qty)) <= 0:
                continue

            close_side = "SELL" if float(signed_qty) > 0 else "BUY"
            close_qty = abs(float(signed_qty))
            try:
                await self.client.place_market_order(
                    symbol=symbol,
                    side=close_side,
                    quantity=close_qty,
                    reduce_only=True,
                )
                self.positions.pop(symbol, None)
                self.trailing_stops.pop(symbol, None)
                closed += 1
                logger.info(f"✅ Closed position {symbol} (close_all)")
            except Exception as exc:
                failed += 1
                logger.error(f"Error closing position {symbol}: {exc}")

        logger.info(f"Close-all complete | closed={closed} failed={failed}")

    def get_status(self) -> dict[str, Any]:
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

    # Validate required config at startup — fail fast with a clear error.
    from startup_validator import validate_config

    validate_config(
        service=SERVICE_NAME,
        required=["ASTER_API_KEY"],
        warn_if_missing=["ASTER_PASSPHRASE", "GCP_PROJECT_ID", "SIGNAL_DEDUPE_TTL_SECONDS"],
    )
    # Secret key: accepts ASTER_SECRET_KEY (Cloud Run) or ASTER_API_SECRET (Pi .env)
    if not ASTER_API_SECRET:
        import sys

        logger.critical(
            "❌ [%s] STARTUP FAILED — neither ASTER_SECRET_KEY nor ASTER_API_SECRET is set.",
            SERVICE_NAME,
        )
        sys.exit(f"FATAL [{SERVICE_NAME}]: ASTER_SECRET_KEY or ASTER_API_SECRET must be set")

    logger.info("=" * 50)
    logger.info("⭐ ASTER BOT SERVICE")
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
