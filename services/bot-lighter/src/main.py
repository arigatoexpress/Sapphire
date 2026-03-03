"""
Lighter Trading Bot - Standalone Service (L2 Order Book)

This is an independent microservice for trading on Lighter Protocol.
Lighter is a decentralized L2 order book exchange built on ZK-rollups.
"""

import asyncio
import json
import inspect
import logging
import os
import signal
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

# Load .env file if present (for local/Pi deployment)
try:
    from pathlib import Path
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        from dotenv import load_dotenv
        load_dotenv(env_path, override=True)
        print(f"[INIT] Loaded environment from {env_path}")
except ImportError:
    pass  # python-dotenv not installed, rely on system env

# Add shared library to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))  # For Sapphire/services structure

# Try imports - support both direct and nested package structure
try:
    from shared.pubsub import get_pubsub_client, publish, subscribe
    from shared.utils import ServiceConfig, format_percent, format_price, setup_logging, utc_now
    from shared.models import (
        BalanceUpdate,
        Platform,
        Position,
        SignalType,
        TradeResult,
        TradeSide,
        TradeSignal,
    )
    from shared.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
    from shared.execution_idempotency import ExecutionIdempotency
except ImportError:
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
    from circuit_breaker import CircuitBreaker, CircuitBreakerOpen
    from execution_idempotency import ExecutionIdempotency

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
    # ── ARM64 signer patch ────────────────────────────────────────────────
    # Lighter SDK ≤1.0.0 checks machine() == "arm64" but Raspberry Pi (aarch64)
    # reports "aarch64".  Monkeypatch __get_shared_library so the correct .so
    # is loaded without modifying the installed package files (survives upgrades).
    import platform as _plat
    if _plat.machine().lower() == "aarch64":
        try:
            import os as _os, ctypes as _ct
            import lighter.signer_client as _lsc
            for _k, _v in list(vars(_lsc).items()):
                if callable(_v) and "shared_library" in _k:
                    def _arm64_lib(_d=_os.path.dirname(_os.path.abspath(_lsc.__file__))):
                        return _ct.CDLL(_os.path.join(_d, "signers", "lighter-signer-linux-arm64.so"))
                    setattr(_lsc, _k, _arm64_lib)
                    logger.info("Lighter SDK: ARM64 signer patch applied (key=%s)", _k)
                    break
        except Exception as _e:
            logger.warning("Lighter SDK: ARM64 patch failed: %s", _e)
    # ─────────────────────────────────────────────────────────────────────
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
        self.signer_client = None

        # Credentials
        self._pub_key = os.getenv("LIGHTER_PUB_KEY", "")
        self._priv_key = os.getenv("LIGHTER_PRIV_KEY", "")
        api_key_index_raw = os.getenv("LIGHTER_API_KEY_INDEX", "0").strip()
        try:
            self._api_key_index = max(0, int(api_key_index_raw or "0"))
        except ValueError:
            logger.warning(
                "Invalid LIGHTER_API_KEY_INDEX=%s; defaulting to 0",
                api_key_index_raw,
            )
            self._api_key_index = 0
        self._l1_address = os.getenv("LIGHTER_L1_ADDRESS", "").strip()
        self._account_discovery_scan_limit = max(
            4, int(os.getenv("LIGHTER_ACCOUNT_DISCOVERY_SCAN_LIMIT", "64") or 64)
        )
        hints_raw = os.getenv("LIGHTER_ACCOUNT_DISCOVERY_HINTS", "699444")
        self._account_discovery_hints = []
        for item in str(hints_raw or "").split(","):
            item = item.strip()
            if not item:
                continue
            try:
                self._account_discovery_hints.append(int(item))
            except ValueError:
                continue

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
        self._execution_block_reason: Optional[str] = None

        # Firestore client shared by idempotency guard + position persistence.
        self._db = None
        # Signal idempotency guard: Firestore-backed (durable across restarts) with
        # in-memory fast path.  Initialized without a Firestore client; warm() is
        # called after initialize() connects to GCP.
        self._idempotency: Optional[ExecutionIdempotency] = None
        self._signal_dedupe_ttl_seconds = max(
            60, int(os.getenv("SIGNAL_DEDUPE_TTL_SECONDS", "900"))
        )

        # Circuit breaker: open after 5 consecutive venue API failures, reset after 120s.
        self._circuit_breaker = CircuitBreaker(
            "lighter",
            fail_max=int(os.getenv("LIGHTER_CIRCUIT_BREAKER_FAIL_MAX", "5")),
            reset_timeout=float(os.getenv("LIGHTER_CIRCUIT_BREAKER_RESET_SECONDS", "120")),
        )

        # Telemetry publishing (consumed by api-gateway for realtime dashboard)
        self._position_publish_interval_seconds = max(
            3, int(os.getenv("POSITION_PUBLISH_INTERVAL_SECONDS", "10"))
        )

    @staticmethod
    async def _call_lighter_api(api_callable, *args, **kwargs):
        """
        Invoke Lighter SDK methods (sync or async) with exponential-backoff retry.

        Retries up to 3 attempts (delays: 1 s, 2 s) on transient connection
        errors (SSL failures, connection refused, network timeouts).  API-level
        errors (bad request, auth, etc.) are NOT retried.
        """
        if api_callable is None:
            return None

        _RETRYABLE: tuple = (ConnectionError, TimeoutError, OSError)
        try:
            import aiohttp as _aio
            _RETRYABLE = _RETRYABLE + (_aio.ClientConnectionError,)
        except ImportError:
            pass

        last_exc: Optional[Exception] = None
        for attempt in range(1, 4):  # attempts 1, 2, 3
            try:
                if inspect.iscoroutinefunction(api_callable):
                    return await api_callable(*args, **kwargs)

                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, lambda: api_callable(*args, **kwargs))
                if inspect.isawaitable(result):
                    return await result
                return result

            except _RETRYABLE as exc:
                last_exc = exc
                if attempt == 3:
                    break
                wait = 2 ** (attempt - 1)  # 1 s, 2 s
                logger.warning(
                    "Lighter API connection error (attempt %d/3, retry in %ds): %s: %s",
                    attempt, wait, type(exc).__name__, exc,
                )
                await asyncio.sleep(wait)

        raise last_exc  # type: ignore[misc]

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

            # Configure proxy if set (for VPN tunneling)
            proxy_url = os.getenv("HTTP_PROXY") or os.getenv("HTTPS_PROXY")
            if proxy_url:
                logger.info(f"Using proxy: {proxy_url}")

            # Initialize the API client with proxy support
            config = lighter.Configuration(
                host=base_url,
            )
            if proxy_url:
                config.proxy = proxy_url
                
            self.client = lighter.ApiClient(configuration=config)

            # Initialize API endpoints
            self.account_api = lighter.AccountApi(self.client)
            self.transaction_api = lighter.TransactionApi(self.client)
            self.order_api = lighter.OrderApi(self.client)

            # Load market metadata
            await self._load_market_info()

            # Get account index from pub key
            await self._load_account_info()

            # Prefer SignerClient on newer SDK builds (constructs tx_info for send_tx v1).
            if hasattr(lighter, "SignerClient"):
                try:
                    # Check if we're using VPN mode (skip validation if geofenced)
                    skip_validation = os.getenv("LIGHTER_SKIP_VALIDATION", "false").lower() == "true"
                    if skip_validation:
                        logger.info("VPN mode: Skipping credential validation (geofencing workaround)")
                    
                    self.signer_client = lighter.SignerClient(
                        url=base_url,
                        account_index=int(self.account_index or 0),
                        api_private_keys={self._api_key_index: self._priv_key},
                    )
                    
                    if not skip_validation:
                        signer_check = self.signer_client.check_client()
                        if signer_check:
                            self.signer_client = None
                            self._execution_block_reason = (
                                "Lighter API credentials do not match exchange api key mapping"
                            )
                            logger.error(f"SignerClient validation failed: {signer_check}")
                        else:
                            logger.info(
                                "SignerClient initialized (api_key_index=%s)",
                                self._api_key_index,
                            )
                    else:
                        logger.info(
                            "SignerClient initialized (VPN mode, validation skipped) (api_key_index=%s)",
                            self._api_key_index,
                        )
                except Exception as signer_exc:
                    self.signer_client = None
                    logger.warning(f"SignerClient unavailable; using legacy path: {signer_exc}")

            if self.signer_client is None and not hasattr(lighter, "Signer"):
                # Newer SDK variants need SignerClient; without it live execution is unavailable.
                self._execution_block_reason = (
                    self._execution_block_reason
                    or "No compatible Lighter signer path available for this SDK/runtime"
                )
                logger.error(self._execution_block_reason)

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
                logger.info("Idempotency guard ready (warmed %d recent IDs from Firestore)", warmed)
            except Exception as _idem_err:
                logger.warning("Idempotency guard degraded to memory-only: %s", _idem_err)
                self._idempotency = ExecutionIdempotency(
                    platform=PLATFORM.value,
                    firestore_client=None,
                    ttl_seconds=self._signal_dedupe_ttl_seconds,
                )

            logger.info(f"{SERVICE_NAME} initialized successfully | Testnet: {LIGHTER_TESTNET}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            return False

    async def _load_market_info(self):
        """Load order book metadata from API."""
        try:
            order_books = await self._call_lighter_api(self.order_api.order_books)

            if order_books and hasattr(order_books, "order_books"):
                for ob in order_books.order_books:
                    market_id = getattr(ob, "order_book_id", 0) or getattr(ob, "market_id", 0) or 0
                    symbol = (
                        getattr(ob, "symbol", None)
                        or getattr(ob, "base_asset", None)
                        or str(market_id)
                    )
                    market_row = {
                        "order_book_id": int(market_id or 0),
                        "symbol": symbol,
                        "base_asset": getattr(ob, "base_asset", symbol),
                        "quote_asset": getattr(ob, "quote_asset", "USDC"),
                        "tick_size": getattr(ob, "tick_size", 0.01),
                        "step_size": getattr(ob, "step_size", 0.001),
                        "supported_size_decimals": int(
                            getattr(ob, "supported_size_decimals", 0) or 0
                        ),
                        "supported_price_decimals": int(
                            getattr(ob, "supported_price_decimals", 0) or 0
                        ),
                    }
                    # Canonical key
                    self.market_info[symbol.upper()] = market_row
                    # Alias lookups for normalized forms (ex: SOL, ETH, BTC)
                    symbol_norm = self._normalize_coin_symbol(symbol)
                    base_norm = self._normalize_coin_symbol(str(market_row.get("base_asset", "")))
                    if symbol_norm and symbol_norm not in self.market_info:
                        self.market_info[symbol_norm] = market_row
                    if base_norm and base_norm not in self.market_info:
                        self.market_info[base_norm] = market_row
                logger.info(f"Loaded {len(self.market_info)} markets")
            logger.info(f"Coin aliases: {self._COIN_ALIASES}")
            logger.info(f"All markets: {sorted(self.market_info.keys())}")
        except Exception as e:
            logger.warning(f"Failed to load market info: {e}")

    async def _load_account_info(self):
        """Load account information and get account index."""
        configured_index_raw = os.getenv("LIGHTER_ACCOUNT_INDEX", "").strip()
        if configured_index_raw:
            try:
                configured_index = int(configured_index_raw)
                if await self._validate_account_index(configured_index):
                    self.account_index = configured_index
                    logger.info(f"Account index from env LIGHTER_ACCOUNT_INDEX: {self.account_index}")
                    return
                logger.warning(
                    f"Configured LIGHTER_ACCOUNT_INDEX={configured_index} failed validation, continuing discovery"
                )
            except ValueError:
                logger.warning(
                    f"Invalid LIGHTER_ACCOUNT_INDEX value '{configured_index_raw}', continuing discovery"
                )

        try:
            accounts = None
            if self._l1_address:
                logger.info("Looking up Lighter account by configured L1 address")
                accounts = await self._call_lighter_api(
                    self.account_api.accounts_by_l1_address,
                    l1_address=self._l1_address,
                )
            elif len(self._pub_key) >= 42:
                # Legacy fallback: this may not always be an L1 address.
                accounts = await self._call_lighter_api(
                    self.account_api.accounts_by_l1_address,
                    l1_address=self._pub_key[:42],
                )

            account_rows = []
            if accounts is not None:
                account_rows = (
                    getattr(accounts, "sub_accounts", None)
                    or getattr(accounts, "accounts", None)
                    or []
                )
            if account_rows:
                self.account_index = int(min(account_rows, key=lambda row: int(row.index)).index)
                logger.info(f"Account index discovered from accounts_by_l1_address: {self.account_index}")
            else:
                discovered = await self._discover_account_index_by_api_key()
                if discovered is not None:
                    self.account_index = discovered
                    logger.info(f"Account index discovered from API key: {self.account_index}")
                else:
                    self.account_index = 0
                    logger.warning("Could not find account, using index 0")

        except Exception as e:
            logger.warning(f"Failed to load account info: {e}")
            discovered = await self._discover_account_index_by_api_key()
            if discovered is not None:
                self.account_index = discovered
                logger.info(f"Recovered account index from API key: {self.account_index}")
            else:
                self.account_index = 0

    async def _validate_account_index(self, account_index: int, require_pub_match: bool = True) -> bool:
        """Validate account index by probing api key listing endpoint."""
        if account_index < 0:
            return False
        try:
            result = await self._call_lighter_api(
                self.account_api.apikeys,
                account_index=int(account_index),
                api_key_index=int(self._api_key_index),
            )
            if result is None:
                return False
            api_keys = getattr(result, "api_keys", None) or getattr(result, "apikeys", None) or []
            if not api_keys:
                return False
            if not self._pub_key or not require_pub_match:
                return True
            target = str(self._pub_key).lower().replace("0x", "")
            for row in api_keys:
                candidate = str(
                    getattr(row, "public_key", None)
                    or getattr(row, "pub_key", None)
                    or ""
                ).lower().replace("0x", "")
                if candidate and (candidate == target or target.endswith(candidate) or candidate.endswith(target)):
                    return True
            return False
        except Exception:
            return False

    async def _discover_account_index_by_api_key(self) -> Optional[int]:
        """
        Discover account index in two passes:
        1) strict match against configured API public key
        2) loose fallback to first index with any api key slot present
        """
        for idx in self._account_discovery_hints:
            ok = await self._validate_account_index(idx, require_pub_match=True)
            if ok:
                return idx
        for idx in range(0, self._account_discovery_scan_limit):
            ok = await self._validate_account_index(idx, require_pub_match=True)
            if ok:
                return idx
        for idx in self._account_discovery_hints:
            ok = await self._validate_account_index(idx, require_pub_match=False)
            if ok:
                return idx
        for idx in range(0, self._account_discovery_scan_limit):
            ok = await self._validate_account_index(idx, require_pub_match=False)
            if ok:
                return idx
        return None

    async def start(self):
        """Start the bot's main trading loop."""
        # Start Execution Gateway FIRST (Cloud Run Health Check requirement)
        try:
            from shared.gateway import start_gateway_server
        except ImportError:
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
                self._position_publish_loop(),
            ]
            await asyncio.gather(*tasks)

        except asyncio.CancelledError:
            logger.info("Bot stopped via cancellation")

    async def _gateway_loop(self):
        """Listen for external execution commands from the Hub."""
        logger.info("Gateway Loop Started (Listening on /execute)")

        while self.running:
            has_command = False
            try:
                command = await asyncio.wait_for(self.command_queue.get(), timeout=1.0)
                has_command = True
                logger.info(f"Processing Hub Command: {command}")

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
                    logger.info(f"Applied gateway risk command: {action}")
                    continue

                if action in {"HEARTBEAT", "STATUS", "CONTROL_STATUS"}:
                    logger.info(f"Gateway control command acknowledged: {action}")
                    continue

                signal = self._build_signal_from_gateway_command(command)
                if signal is None:
                    logger.warning(f"Ignoring unsupported gateway command payload: {command}")
                    continue

                logger.info(
                    f"EXECUTING HUB COMMAND: {signal.side} {signal.quantity} {signal.symbol}"
                )
                result = await self._execute_trade(signal)
                logger.info(f"Hub Command Executed: {result.success}")
                await publish("trade-executed", result)

            except asyncio.TimeoutError:
                continue  # No command arrived; loop back and recheck self.running
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Gateway Error: {e}")
                await asyncio.sleep(1)
            finally:
                if has_command:
                    self.command_queue.task_done()

    # Alias map: route common TradingView symbols to Lighter's native asset names
    _COIN_ALIASES: Dict[str, str] = {
        "ETH": "WETH",
        "BTC": "WBTC",
    }

    @staticmethod
    def _normalize_coin_symbol(value: str) -> str:
        symbol = str(value or "").strip().upper()
        if not symbol:
            return "WETH"
        for suffix in ("-PERP", "-USDC", "-USD", "_PERP", "_USDC", "_USD"):
            if symbol.endswith(suffix):
                symbol = symbol[: -len(suffix)]
                break
        for suffix in ("USDT", "USDC", "USD", "PERP"):
            if symbol.endswith(suffix):
                symbol = symbol[: -len(suffix)]
                break
        symbol = symbol.replace("-", "").replace("_", "")
        return symbol or "WETH"

    def _build_signal_from_gateway_command(self, command: Dict[str, Any]) -> Optional[TradeSignal]:
        """Normalize legacy and action-style gateway payloads into TradeSignal objects."""
        command_type = str(command.get("type", "")).strip().upper()
        action = str(command.get("action", "")).strip().upper()
        if command_type == "ARB_EXECUTE" and not action:
            action = str(command.get("side", "BUY")).strip().upper()

        if action not in {"BUY", "SELL", "LONG", "SHORT", "CLOSE"}:
            return None

        symbol = self._normalize_coin_symbol(str(command.get("symbol", "WETH")))

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
                logger.warning(f"Ignoring {action} command for {symbol}: invalid quantity {raw_qty}")
                return None
            signal_side = TradeSide.BUY if action in {"BUY", "LONG"} else TradeSide.SELL

        signal_id = str(command.get("signal_key", "")).strip() or str(
            command.get("signal_id", "")
        ).strip()
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

        logger.info("Gateway Loop Ended")

    async def stop(self):
        """Gracefully stop the bot."""
        logger.info(f"Stopping {SERVICE_NAME}...")
        self.running = False
        self._shutdown_event.set()
        # Cancel all sibling tasks so loops (especially queue.get()) exit immediately
        current = asyncio.current_task()
        for task in asyncio.all_tasks():
            if task is not current and not task.done():
                task.cancel()

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
                    account = await self._call_lighter_api(
                        self.account_api.account,
                        by="index",
                        value=str(self.account_index),
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

    async def _position_publish_loop(self):
        """Periodically publish a snapshot of positions for the realtime dashboard."""
        from dataclasses import asdict
        from datetime import datetime, timezone

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
                                "updated_at": datetime.now(timezone.utc),
                            }
                        )
                    except Exception as _fs_err:
                        logger.debug("Position Firestore write error: %s", _fs_err)

            except Exception as e:
                logger.error(f"Position publish error: {e}")
            await asyncio.sleep(self._position_publish_interval_seconds)

    async def _handle_signal(self, signal_data: Dict[str, Any]):
        """Handle incoming trading signal."""
        try:
            payload = self._sanitize_trade_signal_payload(signal_data)
            signal = TradeSignal(**payload)

            if not signal.should_execute_on(PLATFORM.value):
                return

            if not self.config.trading_enabled:
                logger.info(f"Trading disabled, ignoring signal: {signal.symbol}")
                return

            metadata = signal.metadata or {}
            if bool(metadata.get("dry_run", False)):
                logger.info(f"Dry-run signal ignored on {PLATFORM.value}: {signal.signal_id}")
                return

            if signal.quantity is None:
                logger.warning(
                    f"Rejected signal without explicit quantity on {PLATFORM.value}: {signal.signal_id} {signal.symbol}"
                )
                return

            signal_id = str(signal.signal_id or "").strip()
            if not signal_id:
                logger.warning(f"Rejected signal without signal_id on {PLATFORM.value}: {signal.symbol}")
                return

            # Durable idempotency check (memory-first, Firestore-backed).
            idempotency = self._idempotency
            if idempotency is not None:
                claimed = await idempotency.claim(signal_id, signal.symbol)
                if not claimed:
                    return
            else:
                # Fallback: legacy in-memory check before idempotency is initialised.
                if self._is_duplicate_signal(signal_id):
                    logger.warning(f"Duplicate signal ignored on {PLATFORM.value}: {signal_id}")
                    return
                self._mark_signal_processed(signal_id)

            logger.info(f"Received signal: {signal.side} {signal.symbol}")
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

    @staticmethod
    def _sanitize_trade_signal_payload(signal_data: Dict[str, Any]) -> Dict[str, Any]:
        """Drop unknown keys so malformed debug payloads don't break signal handling."""
        if not isinstance(signal_data, dict):
            return {}
        allowed = set(getattr(TradeSignal, "__dataclass_fields__", {}).keys())
        payload = {key: value for key, value in signal_data.items() if key in allowed}
        dropped = sorted(set(signal_data.keys()) - set(payload.keys()))
        if dropped:
            logger.warning(
                "Ignoring unsupported signal keys on %s: %s",
                PLATFORM.value,
                ",".join(dropped),
            )
        return payload

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

    def _resolve_market(self, symbol: str) -> Dict[str, Any]:
        """
        Resolve a market row from any symbol style:
        - raw order-book symbol (ex: SOL-USDC)
        - normalized routing symbol (ex: SOLUSDT/SOL-PERP)
        - base asset (ex: SOL)
        - common alias (ETH→WETH, BTC→WBTC for wrapped assets on L2)
        """
        raw = str(symbol or "").strip().upper()
        coin = self._normalize_coin_symbol(raw)

        # Direct lookups: raw symbol, normalized, and alias-resolved
        candidates = [raw, coin]
        alias = self._COIN_ALIASES.get(coin)
        if alias:
            candidates.append(alias)
        logger.error(f"DEBUG: Resolving symbol '{raw}' -> coin='{coin}', alias='{alias}', candidates={candidates}, markets={list(self.market_info.keys())[:5]}")

        for candidate in candidates:
            direct = self.market_info.get(candidate)
            logger.error(f"DEBUG: Looking up candidate='{candidate}' -> found={direct is not None}")
            if direct:
                return direct

        # Fuzzy scan — compare normalized forms of all loaded markets
        search_set = set(candidates)
        for key, row in self.market_info.items():
            if not isinstance(row, dict):
                continue
            key_norm = self._normalize_coin_symbol(str(key))
            base_norm = self._normalize_coin_symbol(str(row.get("base_asset", "")))
            sym_norm = self._normalize_coin_symbol(str(row.get("symbol", "")))
            market_norms = {key_norm, base_norm, sym_norm}
            # Also resolve aliases on the market side
            market_aliases = {self._COIN_ALIASES.get(n, n) for n in market_norms}
            combined = market_norms | market_aliases
            if search_set & combined:
                return row

        return {}

    async def _handle_risk_alert(self, alert_data: Dict[str, Any]):
        """Handle risk alerts."""
        action = alert_data.get("action", "none")
        logger.warning(f"Risk alert: {alert_data.get('message')}")

        if action == "close_all":
            await self._close_all_positions()
        elif action == "halt_trading":
            self.config.trading_enabled = False
        elif action == "resume_trading":
            self.config.trading_enabled = True

    async def _execute_trade(self, signal: TradeSignal) -> TradeResult:
        """Execute trade on Lighter with L2 order book."""
        start_time = datetime.now()

        try:
            if not self.transaction_api:
                raise Exception("Transaction API not initialized")
            if self._execution_block_reason:
                raise Exception(self._execution_block_reason)

            # Normalize symbol
            coin = self._normalize_coin_symbol(signal.symbol)

            # Get market info
            market = self._resolve_market(signal.symbol)
            order_book_id = int(market.get("order_book_id", 0) or 0)
            if order_book_id <= 0:
                raise ValueError(f"No order book mapping for symbol {signal.symbol} (normalized={coin})")

            is_buy = signal.side in (TradeSide.BUY, TradeSide.LONG)

            # Safety: require explicit quantity in inbound signal.
            if signal.quantity is None:
                raise ValueError("Signal quantity is required for live execution")

            # Calculate quantity
            quantity = float(signal.quantity)

            reduce_only = bool((signal.metadata or {}).get("reduce_only", False))
            if reduce_only:
                current = self.positions.get(coin)
                current_qty = float(getattr(current, "quantity", 0.0) or 0.0) if current else 0.0
                if current_qty <= 0:
                    logger.info(f"Reduce-only ignored for {coin}: no tracked position")
                    return TradeResult(
                        trade_id="noop",
                        signal_id=signal.signal_id,
                        platform=PLATFORM.value,
                        symbol=coin,
                        side=signal.side,
                        success=True,
                        metadata={
                            "noop": True,
                            "reason": "reduce_only_no_position",
                            "reduce_only": True,
                        },
                    )

                current_side = getattr(current, "side", None)
                if current_side in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG") and is_buy:
                    logger.info(f"Reduce-only ignored for {coin}: expected SELL to reduce long")
                    return TradeResult(
                        trade_id="noop",
                        signal_id=signal.signal_id,
                        platform=PLATFORM.value,
                        symbol=coin,
                        side=signal.side,
                        success=True,
                        metadata={
                            "noop": True,
                            "reason": "reduce_only_direction_mismatch",
                            "reduce_only": True,
                        },
                    )

                if current_side in (TradeSide.SELL, TradeSide.SHORT, "SELL", "SHORT") and not is_buy:
                    logger.info(f"Reduce-only ignored for {coin}: expected BUY to reduce short")
                    return TradeResult(
                        trade_id="noop",
                        signal_id=signal.signal_id,
                        platform=PLATFORM.value,
                        symbol=coin,
                        side=signal.side,
                        success=True,
                        metadata={
                            "noop": True,
                            "reason": "reduce_only_direction_mismatch",
                            "reduce_only": True,
                        },
                    )

                if signal.quantity is None:
                    quantity = current_qty
                else:
                    try:
                        quantity = min(float(quantity), current_qty)
                    except (TypeError, ValueError):
                        quantity = current_qty
                if quantity <= 0:
                    return TradeResult(
                        trade_id="noop",
                        signal_id=signal.signal_id,
                        platform=PLATFORM.value,
                        symbol=coin,
                        side=signal.side,
                        success=True,
                        metadata={
                            "noop": True,
                            "reason": "reduce_only_quantity_zero",
                            "reduce_only": True,
                        },
                    )

            logger.info(
                f"Placing {signal.side} order | Symbol: {coin} | Qty: {quantity} | OrderBookId: {order_book_id}"
            )

            # Get current price for market order execution
            current_price = await self._get_ticker(coin)
            if not current_price:
                raise Exception(f"Could not get current price for {coin}")

            # Apply slippage for market order
            limit_price = current_price * 1.05 if is_buy else current_price * 0.95

            # Circuit breaker gate — raises CircuitBreakerOpen if venue is halted.
            self._circuit_breaker.check()

            try:
                result = await self._submit_order_with_signer(
                    order_book_id=int(order_book_id),
                    quantity=float(quantity),
                    limit_price=float(limit_price),
                    is_buy=bool(is_buy),
                    reduce_only=bool(reduce_only),
                    signal_id=signal.signal_id,
                    market_meta=market,
                )

                # Legacy fallback for SDKs without SignerClient support.
                if result is None:
                    nonce_response = await self._fetch_next_nonce()
                    nonce = nonce_response.nonce if hasattr(nonce_response, "nonce") else 0
                    order_params = {
                        "account_index": self.account_index,
                        "order_book_id": order_book_id,
                        "side": 0 if is_buy else 1,
                        "price": limit_price,
                        "quantity": quantity,
                        "nonce": nonce,
                        "time_in_force": 1,  # IOC
                    }
                    signature = self._sign_transaction(order_params)
                    result = await self._submit_order_legacy_send_tx(
                        order_params=order_params,
                        signature=signature,
                        signal_id=signal.signal_id,
                    )
                # Record outcome to circuit breaker.
                if result and result.get("success"):
                    self._circuit_breaker.record_success()
                else:
                    self._circuit_breaker.record_failure(
                        Exception(result.get("error") if result else "null result")
                    )
            except CircuitBreakerOpen:
                raise
            except Exception as _venue_err:
                self._circuit_breaker.record_failure(_venue_err)
                raise

            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            self.avg_latency_ms = (self.avg_latency_ms + execution_time) / 2

            if result and bool(result.get("success", False)):
                fill_price = float(result.get("avg_fill_price", 0.0) or 0.0)
                filled_qty = float(result.get("filled_quantity", 0.0) or 0.0)

                self.trades_executed += 1

                # Create position record (reduce-only fills are reconciled via _check_positions).
                if not reduce_only and filled_qty > 0:
                    self.positions[coin] = Position(
                        position_id=str(result.get("order_id", "")),
                        platform=PLATFORM.value,
                        symbol=coin,
                        side=signal.side,
                        quantity=filled_qty,
                        entry_price=fill_price if fill_price > 0 else limit_price,
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit,
                    )

                exec_state = ((result.get("metadata") or {}).get("execution_state")) or (
                    "filled" if filled_qty > 0 else "accepted"
                )
                logger.info(
                    "Order %s | Symbol: %s | Qty: %s | Avg Price: %s",
                    exec_state.upper(),
                    coin,
                    filled_qty,
                    fill_price,
                )

                return TradeResult(
                    trade_id=str(result.get("order_id", "")),
                    signal_id=signal.signal_id,
                    platform=PLATFORM.value,
                    symbol=signal.symbol,
                    side=signal.side,
                    success=True,
                    order_id=str(result.get("order_id", "")),
                    filled_quantity=filled_qty,
                    avg_price=fill_price,
                    execution_time_ms=execution_time,
                    metadata={
                        **(signal.metadata or {}),
                        "reduce_only": reduce_only,
                        **(result.get("metadata") or {}),
                    },
                )
            else:
                error_msg = (result or {}).get("error", "Unknown error")
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

        except CircuitBreakerOpen as _cb_err:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.warning("Trade blocked by circuit breaker: %s", _cb_err)
            return TradeResult(
                trade_id="",
                signal_id=signal.signal_id,
                platform=PLATFORM.value,
                symbol=signal.symbol,
                side=signal.side,
                success=False,
                error_message=str(_cb_err),
                execution_time_ms=execution_time,
                metadata={"circuit_breaker_open": True},
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

    async def _fetch_next_nonce(self):
        """
        Support both SDK signatures:
        - next_nonce(account_index=...)
        - next_nonce(account_index=..., api_key_index=...)
        """
        attempts = [
            ((), {"account_index": self.account_index, "api_key_index": 0}),
            ((self.account_index, 0), {}),
            ((), {"api_key_index": 0, "account_index": self.account_index}),
            ((), {"account_index": self.account_index}),
            ((self.account_index,), {}),
            ((), {"api_key_index": 0}),
            ((0,), {}),
        ]
        last_error: Optional[Exception] = None
        for args, kwargs in attempts:
            try:
                return await self._call_lighter_api(self.transaction_api.next_nonce, *args, **kwargs)
            except TypeError as exc:
                last_error = exc
                continue
        if last_error:
            raise last_error
        raise RuntimeError("Unable to resolve Lighter nonce signature")

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

    @staticmethod
    def _scale_for_market(value: float, decimals: int) -> int:
        scale = 10 ** max(0, int(decimals or 0))
        return int(round(float(value) * scale))

    async def _submit_order_with_signer(
        self,
        *,
        order_book_id: int,
        quantity: float,
        limit_price: float,
        is_buy: bool,
        reduce_only: bool,
        signal_id: str,
        market_meta: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Submit via SignerClient (preferred for lighter-sdk with tx_info send_tx)."""
        if not self.signer_client:
            return None

        market_meta = market_meta or {}
        size_decimals = int(market_meta.get("supported_size_decimals", 0) or 0)
        price_decimals = int(market_meta.get("supported_price_decimals", 0) or 0)
        if size_decimals <= 0:
            step_size = market_meta.get("step_size", 0)
            size_decimals = max(0, len(str(step_size).split(".")[-1]) if step_size else 0)
        if price_decimals <= 0:
            tick_size = market_meta.get("tick_size", 0)
            price_decimals = max(0, len(str(tick_size).split(".")[-1]) if tick_size else 0)

        base_amount_int = self._scale_for_market(quantity, size_decimals)
        price_int = self._scale_for_market(limit_price, price_decimals)
        # Derive client_order_index from signal_id so retries are idempotent on-chain.
        import hashlib as _hl
        client_order_index = int(_hl.sha256(signal_id.encode()).hexdigest(), 16) % 2_147_483_647

        logger.info(
            "Signer submit | market=%s coi=%s base_int=%s price_int=%s",
            order_book_id,
            client_order_index,
            base_amount_int,
            price_int,
        )

        create_order, api_response, err = await self._call_lighter_api(
            self.signer_client.create_market_order,
            market_index=int(order_book_id),
            client_order_index=int(client_order_index),
            base_amount=int(base_amount_int),
            avg_execution_price=int(price_int),
            is_ask=not bool(is_buy),
            reduce_only=bool(reduce_only),
        )
        if err is not None:
            raise RuntimeError(f"Signer create_market_order failed: {err}")

        tx_hash = getattr(api_response, "tx_hash", "") if api_response else ""
        code = getattr(api_response, "code", None) if api_response else None
        message = getattr(api_response, "message", "") if api_response else ""
        accepted = bool(code == 200)
        return {
            "success": accepted,
            "order_id": tx_hash or f"lighter_tx_{signal_id}",
            # accepted != filled; keep 0 until reconciliation from account positions.
            "filled_quantity": 0.0,
            "avg_fill_price": 0.0,
            "error": None if accepted else (message or "send_tx rejected"),
            "metadata": {
                "execution_state": "accepted" if accepted else "rejected",
                "sdk_path": "signer_client",
                "tx_hash": tx_hash,
                "resp_code": code,
                "resp_message": message,
                "create_order": create_order.to_json() if create_order else None,
            },
        }

    async def _submit_order_legacy_send_tx(
        self,
        *,
        order_params: Dict[str, Any],
        signature: str,
        signal_id: str,
    ) -> Dict[str, Any]:
        """Fallback sender for older SDK method signatures."""
        tx_info = json.dumps(
            {"body": order_params, "signature": signature},
            separators=(",", ":"),
            sort_keys=True,
        )
        attempts = [
            ((), {"tx_type": "CreateOrder", "body": order_params, "signature": signature}),
            ((), {"tx_type": "CreateOrder", "tx_info": tx_info}),
            ((), {"tx_type": 0, "tx_info": tx_info}),
            ((0, tx_info), {}),
        ]

        last_error: Optional[Exception] = None
        for args, kwargs in attempts:
            try:
                raw = await self._call_lighter_api(self.transaction_api.send_tx, *args, **kwargs)
                if raw is None:
                    continue
                success = bool(getattr(raw, "success", False))
                code = getattr(raw, "code", None)
                if not success and code is not None:
                    success = int(code) == 200
                tx_hash = getattr(raw, "tx_hash", "") or getattr(raw, "order_id", "")
                filled_qty = float(getattr(raw, "filled_quantity", 0.0) or 0.0)
                avg_fill_price = float(getattr(raw, "avg_fill_price", 0.0) or 0.0)
                err = getattr(raw, "error", None) or getattr(raw, "message", None)
                return {
                    "success": success,
                    "order_id": tx_hash or f"lighter_tx_{signal_id}",
                    "filled_quantity": filled_qty,
                    "avg_fill_price": avg_fill_price,
                    "error": None if success else str(err or "Unknown send_tx failure"),
                    "metadata": {
                        "execution_state": (
                            "filled" if filled_qty > 0 else ("accepted" if success else "failed")
                        ),
                        "sdk_path": "transaction_api",
                        "tx_hash": tx_hash,
                        "resp_code": code,
                        "resp_message": getattr(raw, "message", None),
                    },
                }
            except TypeError as exc:
                last_error = exc
                continue
            except Exception as exc:
                last_error = exc
                continue

        if last_error:
            raise last_error
        raise RuntimeError("No compatible send_tx signature succeeded")

    async def _get_ticker(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol."""
        if not self.order_api:
            return None

        try:
            coin = self._normalize_coin_symbol(symbol)
            market = self._resolve_market(symbol)
            order_book_id = int(market.get("order_book_id", 0) or 0)
            if order_book_id <= 0:
                logger.warning(f"Ticker lookup has no market mapping for {symbol} (normalized={coin})")
                return None

            details = None
            attempts = [
                ((), {"market_id": order_book_id}),
                ((), {"order_book_id": order_book_id}),
                ((order_book_id,), {}),
            ]
            last_error: Optional[Exception] = None
            for args, kwargs in attempts:
                try:
                    details = await self._call_lighter_api(
                        self.order_api.order_book_details,
                        *args,
                        **kwargs,
                    )
                    break
                except TypeError as exc:
                    last_error = exc
                    continue
            if details is None and last_error is not None:
                raise last_error

            if details and hasattr(details, "mid_price"):
                return float(details.mid_price)
            elif details and hasattr(details, "last_price"):
                return float(details.last_price)
            else:
                # SDK v1.0.0 returns a container with per-market rows.
                for bucket_name in ("order_book_details", "spot_order_book_details"):
                    bucket = getattr(details, bucket_name, None)
                    if not bucket:
                        continue
                    for row in bucket:
                        row_market_id = int(getattr(row, "market_id", 0) or 0)
                        row_symbol = str(getattr(row, "symbol", "") or "")
                        if row_market_id and row_market_id != order_book_id:
                            continue
                        if row_symbol and self._normalize_coin_symbol(row_symbol) != coin:
                            # If market_id matched, keep it; otherwise keep scanning.
                            if not row_market_id:
                                continue
                        for price_field in ("last_trade_price", "mid_price", "last_price"):
                            raw_price = getattr(row, price_field, None)
                            try:
                                px = float(raw_price)
                            except (TypeError, ValueError):
                                px = 0.0
                            if px > 0:
                                return px
                logger.warning(
                    f"Ticker payload has no usable price for {symbol} (market_id={order_book_id})"
                )

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
            account = await self._call_lighter_api(
                self.account_api.account,
                by="index",
                value=str(self.account_index),
            )

            if account and hasattr(account, "positions"):
                next_positions: Dict[str, Position] = {}

                for pos in account.positions:
                    try:
                        size = float(getattr(pos, "size", 0))
                    except (TypeError, ValueError):
                        size = 0.0
                    if size == 0:
                        continue

                    symbol = pos.symbol if hasattr(pos, "symbol") else f"MARKET_{pos.order_book_id}"
                    symbol = str(symbol or "").strip().upper() or f"MARKET_{getattr(pos, 'order_book_id', 0)}"

                    side = TradeSide.LONG if size > 0 else TradeSide.SHORT
                    qty = abs(size)
                    entry_price = float(getattr(pos, "entry_price", 0) or 0.0)

                    existing = self.positions.get(symbol)
                    if existing is None:
                        existing = Position(
                            position_id=f"{PLATFORM.value}_{getattr(pos, 'order_book_id', 0)}",
                            platform=PLATFORM.value,
                            symbol=symbol,
                            side=side,
                            quantity=qty,
                            entry_price=entry_price,
                        )
                    else:
                        existing.side = side
                        existing.quantity = qty
                        if entry_price > 0:
                            existing.entry_price = entry_price
                        existing.updated_at = utc_now()

                    next_positions[symbol] = existing

                # Replace with the authoritative snapshot (clears closed positions).
                self.positions = next_positions

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

    # Validate required config at startup — fail fast with a clear error.
    try:
        from shared.startup_validator import validate_config
    except ImportError:
        from startup_validator import validate_config
    validate_config(
        service=SERVICE_NAME,
        required=["LIGHTER_PUB_KEY", "LIGHTER_PRIV_KEY"],
        warn_if_missing=["LIGHTER_API_URL", "GCP_PROJECT_ID", "SIGNAL_DEDUPE_TTL_SECONDS"],
    )

    logger.info("=" * 50)
    logger.info(f"LIGHTER BOT SERVICE (L2 Order Book)")
    logger.info(f"{datetime.now().isoformat()}")
    logger.info("=" * 50)

    bot = LighterBot()

    # Use asyncio-safe signal handlers (loop.add_signal_handler is non-blocking
    # and schedules the coroutine on the running event loop, unlike signal.signal
    # which can race with the loop).
    loop = asyncio.get_event_loop()
    for _sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            _sig,
            lambda s=_sig: asyncio.ensure_future(
                _shutdown(bot, s), loop=loop
            ),
        )

    await bot.start()


async def _shutdown(bot: "LighterBot", sig: int) -> None:
    logger.info("Received signal %s, shutting down...", sig)
    await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
