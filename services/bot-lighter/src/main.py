"""
Lighter Trading Bot - Standalone Service (L2 Order Book)

This is an independent microservice for trading on Lighter Protocol.
Lighter is a decentralized L2 order book exchange built on ZK-rollups.
"""

import asyncio
import math
import json
import inspect
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
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
        self._processed_signal_ids: Dict[str, float] = {}

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
        self._single_symbol_mode = self._env_flag(
            "LIGHTER_SINGLE_SYMBOL_MODE",
            default=True,
        )
        self._default_take_profit_pct = self._env_float(
            ("LIGHTER_DEFAULT_TAKE_PROFIT_PCT", "SAPPHIRE_TV_TAKE_PROFIT_PCT"),
            default=3.0,
        )
        self._default_stop_loss_pct = self._env_float(
            ("LIGHTER_DEFAULT_STOP_LOSS_PCT", "SAPPHIRE_TV_STOP_LOSS_PCT"),
            default=2.0,
        )
        self._max_order_notional_usd = max(
            0.0,
            self._env_float(("LIGHTER_MAX_ORDER_NOTIONAL_USD",), default=0.0),
        )
        self._max_position_notional_usd = max(
            0.0,
            self._env_float(("LIGHTER_MAX_POSITION_NOTIONAL_USD",), default=0.0),
        )
        self._entry_cooldown_seconds = max(
            0.0,
            self._env_float(("LIGHTER_ENTRY_COOLDOWN_SECONDS",), default=0.0),
        )
        self._last_entry_ts: Dict[str, float] = {}
        self._allowed_strategies = {
            s.strip().lower()
            for s in str(os.getenv("LIGHTER_ALLOWED_STRATEGIES", "")).split(",")
            if s.strip()
        }
        self._allowed_timeframes = {
            s.strip().lower()
            for s in str(os.getenv("LIGHTER_ALLOWED_TIMEFRAMES", "")).split(",")
            if s.strip()
        }
        self._strategy_require_metadata = self._env_flag(
            "LIGHTER_STRATEGY_REQUIRE_METADATA",
            default=False,
        )
        self._trading_enabled = self._env_flag("TRADING_ENABLED", default=True)
        self._allow_live_trading = self._env_flag("ALLOW_LIVE_TRADING", default=True)
        self._trading_mode = str(os.getenv("TRADING_MODE", "live")).strip().lower() or "live"
        self._risk_exit_cooldown_seconds = max(
            5.0,
            self._env_float(("LIGHTER_RISK_EXIT_COOLDOWN_SECONDS",), default=15.0),
        )
        self._risk_exit_attempted_at: Dict[str, float] = {}
        self._progress_verify_interval_seconds = max(
            30,
            int(self._env_float(("LIGHTER_PROGRESS_VERIFY_INTERVAL_SECONDS",), default=180.0)),
        )
        self._max_drawdown_alert_pct = max(
            0.0,
            self._env_float(("LIGHTER_MAX_DRAWDOWN_ALERT_PCT",), default=5.0),
        )
        self._drawdown_alert_cooldown_seconds = max(
            60.0,
            self._env_float(("LIGHTER_DRAWDOWN_ALERT_COOLDOWN_SECONDS",), default=900.0),
        )
        self._sync_stale_alert_seconds = max(
            60,
            int(self._env_float(("LIGHTER_SYNC_STALE_ALERT_SECONDS",), default=300.0)),
        )
        self._sync_stale_alert_cooldown_seconds = max(
            60.0,
            self._env_float(("LIGHTER_SYNC_STALE_ALERT_COOLDOWN_SECONDS",), default=900.0),
        )
        self._max_risk_level_deviation_pct = max(
            1.0,
            self._env_float(("LIGHTER_MAX_RISK_LEVEL_DEVIATION_PCT",), default=20.0),
        )
        self._equity_baseline: Optional[float] = None
        self._equity_peak: Optional[float] = None
        self._equity_trough: Optional[float] = None
        self._last_drawdown_alert_ts: float = 0.0
        self._last_sync_stale_alert_ts: float = 0.0
        self._last_balance_sync_ts: float = 0.0
        self._last_position_check_ts: float = 0.0
        self._last_balance_sync_error: str = ""
        self._last_position_check_error: str = ""
        self._empty_position_snapshot_streak: int = 0
        self._empty_position_confirmations = max(
            1,
            int(self._env_float(("LIGHTER_EMPTY_POSITION_CONFIRMATIONS",), default=5.0)),
        )
        self._telegram_bot_token = str(os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
        self._telegram_chat_id = (
            str(os.getenv("TELEGRAM_CHAT_ID", "")).strip()
            or str(os.getenv("TELEGRAM_BOT_CHAT_ID", "")).strip()
            or str(os.getenv("TELEGRAM_OWNER_USER_ID", "")).strip()
        )
        logger.info(
            "Strategy policy | allowed_strategies=%s allowed_timeframes=%s "
            "require_metadata=%s entry_cooldown=%.1fs max_order_notional=%.2f "
            "max_position_notional=%.2f progress_verify=%.0fs dd_alert=%.2f%% "
            "sync_stale_alert=%.0fs risk_level_max_dev=%.1f%% empty_pos_confirm=%d",
            sorted(self._allowed_strategies) if self._allowed_strategies else ["*"],
            sorted(self._allowed_timeframes) if self._allowed_timeframes else ["*"],
            self._strategy_require_metadata,
            self._entry_cooldown_seconds,
            self._max_order_notional_usd,
            self._max_position_notional_usd,
            self._progress_verify_interval_seconds,
            self._max_drawdown_alert_pct,
            self._sync_stale_alert_seconds,
            self._max_risk_level_deviation_pct,
            self._empty_position_confirmations,
        )

    @staticmethod
    def _env_flag(name: str, default: bool = False) -> bool:
        raw = str(os.getenv(name, "")).strip().lower()
        if not raw:
            return bool(default)
        return raw in {"1", "true", "yes", "on"}

    @staticmethod
    def _env_float(names: tuple[str, ...], default: float = 0.0) -> float:
        for name in names:
            raw = str(os.getenv(name, "")).strip()
            if not raw:
                continue
            try:
                return float(raw)
            except ValueError:
                continue
        return float(default)

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

        call_timeout = max(
            2.0,
            float(os.getenv("LIGHTER_API_CALL_TIMEOUT_SECONDS", "10") or 10),
        )
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
                    return await asyncio.wait_for(
                        api_callable(*args, **kwargs),
                        timeout=call_timeout,
                    )

                loop = asyncio.get_running_loop()
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: api_callable(*args, **kwargs)),
                    timeout=call_timeout,
                )
                if inspect.isawaitable(result):
                    return await asyncio.wait_for(result, timeout=call_timeout)
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
                self._progress_verification_loop(),
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
                await self._record_execution_verification(signal, result, channel="hub")
                logger.info(f"Hub Command Executed: {result.success}")
                await publish("trade-executed", result)
                await self._send_trade_telegram_alert(signal, result, channel="hub")

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
        await self._close_clients()

    async def _sleep_or_stop(self, timeout_seconds: float) -> None:
        """Sleep with early wakeup when shutdown is requested."""
        if timeout_seconds <= 0:
            return
        try:
            await asyncio.wait_for(
                self._shutdown_event.wait(),
                timeout=float(timeout_seconds),
            )
        except asyncio.TimeoutError:
            return

    async def _close_clients(self) -> None:
        """Best-effort close of SDK/network clients to avoid aiohttp session leaks."""
        api_client = getattr(self.client, "api_client", None)
        if api_client is None:
            return

        close_fn = getattr(api_client, "close", None)
        if callable(close_fn):
            try:
                maybe = close_fn()
                if inspect.isawaitable(maybe):
                    await maybe
            except Exception as exc:
                logger.debug("API client close failed: %s", exc)

        rest_client = getattr(api_client, "rest_client", None)
        pool_manager = getattr(rest_client, "pool_manager", None) if rest_client else None
        close_pool = getattr(pool_manager, "close", None) if pool_manager else None
        if callable(close_pool):
            try:
                close_pool()
            except Exception as exc:
                logger.debug("REST pool close failed: %s", exc)

    async def _main_loop(self):
        """Main trading loop."""
        loop_interval = 1.0  # 1 second for L2

        while self.running:
            try:
                await self._check_positions()
                await self._enforce_position_risk_exits()
                await self._sleep_or_stop(loop_interval)
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await self._sleep_or_stop(2)

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
                        account_dict = {}
                        if isinstance(account, dict):
                            account_dict = account
                        elif hasattr(account, "to_dict"):
                            try:
                                maybe = account.to_dict()  # type: ignore[attr-defined]
                                if isinstance(maybe, dict):
                                    account_dict = maybe
                            except Exception:
                                account_dict = {}

                        account_record = None
                        accounts_payload = account_dict.get("accounts")
                        if isinstance(accounts_payload, list) and accounts_payload:
                            target_idx = int(self.account_index)
                            for row in accounts_payload:
                                if not isinstance(row, dict):
                                    continue
                                try:
                                    idx_val = int(
                                        row.get("account_index", row.get("index", -1)) or -1
                                    )
                                except (TypeError, ValueError):
                                    idx_val = -1
                                if idx_val == target_idx:
                                    account_record = row
                                    break
                            if account_record is None:
                                account_record = accounts_payload[0]

                        def _pick_positive(*vals: object) -> float:
                            for v in vals:
                                try:
                                    f = float(v or 0.0)
                                except (TypeError, ValueError):
                                    f = 0.0
                                if f > 0:
                                    return f
                            return 0.0

                        parsed_total_balance = _pick_positive(
                            (account_record or {}).get("collateral"),
                            getattr(account, "equity", None),
                            getattr(account, "total_account_value", None),
                            getattr(account, "collateral", None),
                            account_dict.get("equity"),
                            account_dict.get("total_account_value"),
                            account_dict.get("collateral"),
                        )
                        parsed_available_balance = _pick_positive(
                            (account_record or {}).get("available_balance"),
                            getattr(account, "available_balance", None),
                            getattr(account, "free_collateral", None),
                            account_dict.get("available_balance"),
                            account_dict.get("free_collateral"),
                            parsed_total_balance,
                        )
                        if parsed_total_balance <= 0 and self.balance > 0:
                            logger.warning(
                                "Balance snapshot had no positive equity fields; retaining prior balance %.6f",
                                self.balance,
                            )
                            parsed_total_balance = self.balance
                            parsed_available_balance = self.balance

                        self.balance = float(parsed_total_balance)
                        self._last_balance_sync_ts = time.time()
                        self._last_balance_sync_error = ""

                        await publish(
                            "balance-updates",
                            BalanceUpdate(
                                platform=PLATFORM.value,
                                total_balance=float(parsed_total_balance),
                                available_balance=float(parsed_available_balance),
                                assets={"USDC": self.balance},
                            ),
                        )
            except Exception as e:
                self._last_balance_sync_error = f"{type(e).__name__}: {e}"
                logger.error(f"Balance sync error: {e}")
            await self._sleep_or_stop(30)

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
            await self._sleep_or_stop(self._position_publish_interval_seconds)

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

            allowed, reason = self._is_signal_allowed_by_policy(signal)
            if not allowed:
                logger.warning(
                    "Policy reject on %s: signal=%s symbol=%s reason=%s",
                    PLATFORM.value,
                    signal.signal_id,
                    signal.symbol,
                    reason,
                )
                result = TradeResult(
                    trade_id="",
                    signal_id=str(signal.signal_id or ""),
                    platform=PLATFORM.value,
                    symbol=signal.symbol,
                    side=signal.side,
                    success=False,
                    error_message=f"policy_reject: {reason}",
                    metadata={"policy_reject": True, "reason": reason},
                )
                await self._record_execution_verification(signal, result, channel="signal")
                await publish("trade-executed", result)
                await self._send_trade_telegram_alert(signal, result, channel="signal")
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
            await self._record_execution_verification(signal, result, channel="signal")

            # Persist outcome to idempotency store.
            if idempotency is not None:
                if result.success:
                    await idempotency.mark_executed(signal_id, result.order_id or "")
                else:
                    await idempotency.mark_failed(signal_id, result.error_message or "")

            # Don't emit trade events for explicit no-op signals (ex: reduce-only without exposure).
            if not (result.metadata or {}).get("noop"):
                await publish("trade-executed", result)
                await self._send_trade_telegram_alert(signal, result, channel="signal")

        except Exception as e:
            logger.error(f"Signal handling error: {e}")

    async def _send_trade_telegram_alert(
        self,
        signal: TradeSignal,
        result: TradeResult,
        channel: str = "signal",
    ) -> None:
        """Push a compact execution/rejection alert to Telegram."""
        if not self._telegram_bot_token or not self._telegram_chat_id:
            return

        side = str(getattr(signal, "side", "")).upper()
        symbol = str(getattr(signal, "symbol", "")).upper()
        qty = float(getattr(signal, "quantity", 0.0) or 0.0)
        ok = bool(getattr(result, "success", False))
        order_id = str(getattr(result, "order_id", "") or "")
        fill_qty = float(getattr(result, "filled_quantity", 0.0) or 0.0)
        fill_price = float(
            getattr(result, "avg_price", None)
            or getattr(result, "fill_price", 0.0)
            or 0.0
        )
        err = str(getattr(result, "error_message", "") or "")
        tp = getattr(signal, "take_profit", None)
        sl = getattr(signal, "stop_loss", None)
        status = "FILLED" if ok else "REJECTED"
        lines = [
            f"LIGHTER {status}",
            f"src={channel} signal={signal.signal_id}",
            f"{side} {symbol} qty={qty:g}",
        ]
        if tp or sl:
            lines.append(f"tp={tp or '-'} sl={sl or '-'}")
        if fill_qty > 0:
            lines.append(f"filled={fill_qty:g} @ {fill_price:g}")
        if order_id:
            lines.append(f"order={order_id}")
        if err:
            lines.append(f"error={err[:180]}")
        text = "\n".join(lines)
        await self._send_telegram_message(text)

    async def _send_telegram_message(self, text: str) -> None:
        if not self._telegram_bot_token or not self._telegram_chat_id:
            return

        try:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=8)
            url = f"https://api.telegram.org/bot{self._telegram_bot_token}/sendMessage"
            payload = {
                "chat_id": self._telegram_chat_id,
                "text": text,
                "disable_web_page_preview": True,
            }
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as response:
                    if response.status >= 400:
                        body = await response.text()
                        logger.warning(
                            "Telegram alert failed (%s): %s",
                            response.status,
                            body[:160],
                        )
        except Exception as exc:
            logger.warning("Telegram alert error: %s", exc)

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

    def _active_position_symbols(self) -> set[str]:
        active: set[str] = set()
        for symbol, position in self.positions.items():
            try:
                qty = float(getattr(position, "quantity", 0.0) or 0.0)
            except (TypeError, ValueError):
                qty = 0.0
            if qty > 0:
                active.add(self._normalize_coin_symbol(symbol))
        return active

    def _signal_strategy_info(self, signal: TradeSignal) -> tuple[str, str]:
        metadata = signal.metadata or {}
        strategy = str(
            metadata.get("strategy")
            or metadata.get("strategy_id")
            or metadata.get("system")
            or ""
        ).strip().lower()
        timeframe = str(
            metadata.get("timeframe")
            or metadata.get("tf")
            or metadata.get("interval")
            or ""
        ).strip().lower()
        return strategy, timeframe

    def _is_signal_allowed_by_policy(self, signal: TradeSignal) -> tuple[bool, str]:
        strategy, timeframe = self._signal_strategy_info(signal)
        if self._strategy_require_metadata and (not strategy or not timeframe):
            return False, "strategy metadata required"
        if self._allowed_strategies and strategy and strategy not in self._allowed_strategies:
            return False, f"strategy '{strategy}' not allowed"
        if self._allowed_timeframes and timeframe and timeframe not in self._allowed_timeframes:
            return False, f"timeframe '{timeframe}' not allowed"
        if self._allowed_strategies and not strategy and self._strategy_require_metadata:
            return False, "missing strategy metadata"
        if self._allowed_timeframes and not timeframe and self._strategy_require_metadata:
            return False, "missing timeframe metadata"
        return True, ""

    def _apply_default_risk_levels(
        self,
        signal: TradeSignal,
        *,
        is_buy: bool,
        reference_price: float,
        reduce_only: bool,
    ) -> None:
        if reduce_only:
            return
        if signal.signal_type not in {SignalType.ENTRY, SignalType.SCALE_IN}:
            return
        if reference_price <= 0:
            return

        tp = None
        sl = None
        try:
            tp = float(signal.take_profit) if signal.take_profit is not None else None
        except (TypeError, ValueError):
            tp = None
        try:
            sl = float(signal.stop_loss) if signal.stop_loss is not None else None
        except (TypeError, ValueError):
            sl = None

        if (tp is None or tp <= 0.0) and self._default_take_profit_pct > 0:
            signal.take_profit = round(
                reference_price * (1 + self._default_take_profit_pct / 100.0)
                if is_buy
                else reference_price * (1 - self._default_take_profit_pct / 100.0),
                8,
            )
        if (sl is None or sl <= 0.0) and self._default_stop_loss_pct > 0:
            signal.stop_loss = round(
                reference_price * (1 - self._default_stop_loss_pct / 100.0)
                if is_buy
                else reference_price * (1 + self._default_stop_loss_pct / 100.0),
                8,
            )

    def _sanitize_signal_risk_levels(
        self,
        signal: TradeSignal,
        *,
        is_buy: bool,
        reference_price: float,
        reduce_only: bool,
    ) -> None:
        """
        Guard against stale/invalid external TP/SL values.

        If incoming TP/SL is on the wrong side of market price or is too far from
        market (> LIGHTER_MAX_RISK_LEVEL_DEVIATION_PCT), drop it and let defaults
        be re-applied from current executable price.
        """
        if reduce_only or reference_price <= 0:
            return

        max_dev = max(0.1, float(self._max_risk_level_deviation_pct))

        def _maybe_drop(level_name: str, level_value: Optional[float]) -> Optional[float]:
            if level_value is None or level_value <= 0:
                return level_value
            dev_pct = abs((float(level_value) - float(reference_price)) / float(reference_price)) * 100.0
            invalid_side = False
            if level_name == "take_profit":
                invalid_side = (is_buy and level_value <= reference_price) or (
                    (not is_buy) and level_value >= reference_price
                )
            elif level_name == "stop_loss":
                invalid_side = (is_buy and level_value >= reference_price) or (
                    (not is_buy) and level_value <= reference_price
                )
            if invalid_side or dev_pct > max_dev:
                logger.warning(
                    "Dropping stale %s for %s: level=%.8f ref=%.8f dev=%.2f%% max=%.2f%%",
                    level_name,
                    signal.symbol,
                    level_value,
                    reference_price,
                    dev_pct,
                    max_dev,
                )
                return None
            return level_value

        tp = None
        sl = None
        try:
            tp = float(signal.take_profit) if signal.take_profit is not None else None
        except (TypeError, ValueError):
            tp = None
        try:
            sl = float(signal.stop_loss) if signal.stop_loss is not None else None
        except (TypeError, ValueError):
            sl = None

        signal.take_profit = _maybe_drop("take_profit", tp)
        signal.stop_loss = _maybe_drop("stop_loss", sl)

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    async def _estimate_equity_snapshot(self) -> Dict[str, Any]:
        """
        Build a lightweight equity snapshot from current balance + tracked positions.
        Uses current_price when available, otherwise falls back to entry_price.
        """
        now_ts = time.time()
        now_iso = datetime.now(timezone.utc).isoformat()
        cash_balance = self._to_float(self.balance, 0.0)
        unrealized_pnl = 0.0
        position_notional = 0.0
        stale_price_positions = 0
        positions_count = 0

        for symbol, position in self.positions.items():
            qty = abs(self._to_float(getattr(position, "quantity", 0.0), 0.0))
            if qty <= 0:
                continue
            positions_count += 1

            entry = self._to_float(getattr(position, "entry_price", 0.0), 0.0)
            mark = self._to_float(getattr(position, "current_price", 0.0), 0.0)
            if mark <= 0 and entry > 0:
                mark = entry
                stale_price_positions += 1
            elif mark <= 0:
                stale_price_positions += 1
                continue

            side = getattr(position, "side", None)
            is_long = side in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG")
            if entry > 0:
                pnl = ((mark - entry) * qty) if is_long else ((entry - mark) * qty)
                unrealized_pnl += pnl

            position_notional += abs(mark * qty)

        equity_estimate = cash_balance + unrealized_pnl
        balance_sync_age_sec = (
            round(max(0.0, now_ts - self._last_balance_sync_ts), 3)
            if self._last_balance_sync_ts > 0
            else None
        )
        position_check_age_sec = (
            round(max(0.0, now_ts - self._last_position_check_ts), 3)
            if self._last_position_check_ts > 0
            else None
        )
        balance_sync_stale = (
            balance_sync_age_sec is None or balance_sync_age_sec > self._sync_stale_alert_seconds
        )
        position_check_stale = (
            position_check_age_sec is None or position_check_age_sec > self._sync_stale_alert_seconds
        )

        return {
            "platform": PLATFORM.value,
            "timestamp": now_iso,
            "cash_balance": round(cash_balance, 8),
            "unrealized_pnl": round(unrealized_pnl, 8),
            "equity_estimate": round(equity_estimate, 8),
            "position_notional_usd": round(position_notional, 8),
            "positions_count": int(positions_count),
            "stale_price_positions": int(stale_price_positions),
            "balance_sync_age_sec": balance_sync_age_sec,
            "position_check_age_sec": position_check_age_sec,
            "balance_sync_stale": bool(balance_sync_stale),
            "position_check_stale": bool(position_check_stale),
            "last_balance_sync_at": (
                datetime.fromtimestamp(self._last_balance_sync_ts, tz=timezone.utc).isoformat()
                if self._last_balance_sync_ts > 0
                else None
            ),
            "last_position_check_at": (
                datetime.fromtimestamp(self._last_position_check_ts, tz=timezone.utc).isoformat()
                if self._last_position_check_ts > 0
                else None
            ),
            "last_balance_sync_error": self._last_balance_sync_error,
            "last_position_check_error": self._last_position_check_error,
        }

    async def _persist_equity_snapshot(self, snapshot: Dict[str, Any], reason: str) -> None:
        if self._db is None:
            return
        payload = dict(snapshot)
        payload["reason"] = str(reason)
        payload["recorded_at"] = datetime.now(timezone.utc)
        payload["service"] = SERVICE_NAME
        snapshot_id = f"{PLATFORM.value}_{int(time.time() * 1000)}"
        try:
            await self._db.collection("equity_snapshots").document(snapshot_id).set(payload)
            await self._db.collection("equity_snapshots_current").document(PLATFORM.value).set(payload)
        except Exception as exc:
            logger.debug("Equity snapshot write error: %s", exc)

    async def _record_execution_verification(
        self,
        signal: TradeSignal,
        result: TradeResult,
        channel: str,
    ) -> None:
        """Persist per-signal execution audit row for traceability."""
        strategy, timeframe = self._signal_strategy_info(signal)
        snapshot = await self._estimate_equity_snapshot()
        payload: Dict[str, Any] = {
            "service": SERVICE_NAME,
            "platform": PLATFORM.value,
            "channel": channel,
            "signal_id": str(signal.signal_id or ""),
            "symbol": str(signal.symbol or ""),
            "side": str(signal.side),
            "signal_type": str(signal.signal_type),
            "strategy": strategy,
            "timeframe": timeframe,
            "quantity": self._to_float(getattr(signal, "quantity", 0.0), 0.0),
            "take_profit": self._to_float(getattr(signal, "take_profit", 0.0), 0.0),
            "stop_loss": self._to_float(getattr(signal, "stop_loss", 0.0), 0.0),
            "success": bool(getattr(result, "success", False)),
            "error_message": str(getattr(result, "error_message", "") or ""),
            "filled_quantity": self._to_float(getattr(result, "filled_quantity", 0.0), 0.0),
            "avg_price": self._to_float(getattr(result, "avg_price", 0.0), 0.0),
            "order_id": str(getattr(result, "order_id", "") or ""),
            "execution_time_ms": self._to_float(getattr(result, "execution_time_ms", 0.0), 0.0),
            "equity_estimate": snapshot.get("equity_estimate", 0.0),
            "cash_balance": snapshot.get("cash_balance", 0.0),
            "position_notional_usd": snapshot.get("position_notional_usd", 0.0),
            "metadata": (signal.metadata or {}),
            "recorded_at": datetime.now(timezone.utc),
        }
        logger.info(
            "Execution verify | signal=%s ok=%s fill=%s@%s equity=%s",
            payload["signal_id"],
            payload["success"],
            payload["filled_quantity"],
            payload["avg_price"],
            payload["equity_estimate"],
        )
        if self._db is None:
            return
        try:
            key = payload["signal_id"] or f"noid-{int(time.time() * 1000)}"
            doc_id = f"{PLATFORM.value}_{key}_{channel}"
            await self._db.collection("execution_verifications").document(doc_id).set(payload)
        except Exception as exc:
            logger.debug("Execution verification write error: %s", exc)

    async def _progress_verification_loop(self) -> None:
        """
        Periodic process verifier:
        - snapshots equity estimates
        - tracks baseline/peak/trough progress
        - alerts on sustained drawdown breaches
        """
        while self.running:
            try:
                snap = await self._estimate_equity_snapshot()
                equity = self._to_float(snap.get("equity_estimate"), 0.0)
                if equity > 0 and self._equity_baseline is None:
                    self._equity_baseline = equity
                    self._equity_peak = equity
                    self._equity_trough = equity

                if equity > 0:
                    self._equity_peak = max(self._equity_peak or equity, equity)
                    self._equity_trough = min(self._equity_trough or equity, equity)

                baseline = self._equity_baseline or 0.0
                peak = self._equity_peak or 0.0
                progress_pct = ((equity - baseline) / baseline * 100.0) if baseline > 0 else 0.0
                drawdown_pct = ((equity - peak) / peak * 100.0) if peak > 0 else 0.0
                snap["progress_pct"] = round(progress_pct, 6)
                snap["drawdown_pct"] = round(drawdown_pct, 6)
                snap["baseline_equity"] = round(baseline, 8) if baseline > 0 else 0.0
                snap["peak_equity"] = round(peak, 8) if peak > 0 else 0.0

                logger.info(
                    "Progress verify | equity=%.6f progress=%.3f%% drawdown=%.3f%% "
                    "cash=%.6f upnl=%.6f pos_notional=%.6f positions=%s "
                    "bal_age=%ss pos_age=%ss",
                    equity,
                    progress_pct,
                    drawdown_pct,
                    self._to_float(snap.get("cash_balance"), 0.0),
                    self._to_float(snap.get("unrealized_pnl"), 0.0),
                    self._to_float(snap.get("position_notional_usd"), 0.0),
                    snap.get("positions_count", 0),
                    snap.get("balance_sync_age_sec"),
                    snap.get("position_check_age_sec"),
                )

                await self._persist_equity_snapshot(snap, reason="progress_loop")

                now_ts = time.time()
                if bool(snap.get("balance_sync_stale")) or bool(snap.get("position_check_stale")):
                    logger.warning(
                        "Data freshness warning | balance_stale=%s age=%ss pos_stale=%s age=%ss "
                        "balance_err=%s position_err=%s",
                        snap.get("balance_sync_stale"),
                        snap.get("balance_sync_age_sec"),
                        snap.get("position_check_stale"),
                        snap.get("position_check_age_sec"),
                        snap.get("last_balance_sync_error") or "none",
                        snap.get("last_position_check_error") or "none",
                    )
                    if (
                        (now_ts - self._last_sync_stale_alert_ts)
                        >= self._sync_stale_alert_cooldown_seconds
                    ):
                        self._last_sync_stale_alert_ts = now_ts
                        await self._send_telegram_message(
                            (
                                "LIGHTER DATA FRESHNESS ALERT\n"
                                f"balance_sync_age={snap.get('balance_sync_age_sec')}s "
                                f"position_check_age={snap.get('position_check_age_sec')}s\n"
                                f"balance_error={snap.get('last_balance_sync_error') or 'none'}\n"
                                f"position_error={snap.get('last_position_check_error') or 'none'}"
                            )
                        )

                if (
                    self._max_drawdown_alert_pct > 0
                    and drawdown_pct <= -abs(self._max_drawdown_alert_pct)
                    and (now_ts - self._last_drawdown_alert_ts) >= self._drawdown_alert_cooldown_seconds
                ):
                    self._last_drawdown_alert_ts = now_ts
                    await self._send_telegram_message(
                        (
                            "LIGHTER DRAWDOWN ALERT\n"
                            f"equity={equity:.4f} baseline={baseline:.4f} peak={peak:.4f}\n"
                            f"progress={progress_pct:.2f}% drawdown={drawdown_pct:.2f}%"
                        )
                    )

            except Exception as exc:
                logger.error("Progress verification error: %s", exc)

            await self._sleep_or_stop(self._progress_verify_interval_seconds)

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
        logger.debug(
            "Resolving symbol '%s' -> coin='%s', alias='%s', candidates=%s, markets=%s",
            raw,
            coin,
            alias,
            candidates,
            list(self.market_info.keys())[:5],
        )

        for candidate in candidates:
            direct = self.market_info.get(candidate)
            logger.debug("Looking up candidate='%s' -> found=%s", candidate, direct is not None)
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
        platform = str(alert_data.get("platform", "") or "").strip().lower()
        if platform and platform not in {PLATFORM.value, "lighter"}:
            logger.info(
                "Ignoring risk alert for foreign platform '%s': %s",
                platform,
                alert_data.get("message", ""),
            )
            return

        action = alert_data.get("action", "none")
        logger.warning(f"Risk alert: {alert_data.get('message')}")

        if action == "close_all":
            await self._close_all_positions()
        elif action == "halt_trading":
            self.config.trading_enabled = False
            self._trading_enabled = False
        elif action == "resume_trading":
            self.config.trading_enabled = True
            self._trading_enabled = True

    async def _execute_trade(
        self,
        signal: TradeSignal,
        *,
        ignore_trading_guard: bool = False,
    ) -> TradeResult:
        """Execute trade on Lighter with L2 order book."""
        start_time = datetime.now()

        try:
            if not ignore_trading_guard:
                if not self._trading_enabled:
                    raise Exception("Trading disabled (TRADING_ENABLED=false)")
                if self._trading_mode == "live" and not self._allow_live_trading:
                    raise Exception("Live trading disabled (ALLOW_LIVE_TRADING=0)")
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
            if signal.signal_type in {
                SignalType.EXIT,
                SignalType.SCALE_OUT,
                SignalType.TAKE_PROFIT,
                SignalType.STOP_LOSS,
            }:
                reduce_only = True
            entry_like = signal.signal_type in {SignalType.ENTRY, SignalType.SCALE_IN}

            if self._single_symbol_mode and entry_like and not reduce_only:
                active_symbols = self._active_position_symbols()
                if active_symbols and coin not in active_symbols:
                    locked = sorted(active_symbols)[0]
                    raise ValueError(
                        f"Single-symbol mode active: open symbol={locked}, rejected symbol={coin}"
                    )
                if self._entry_cooldown_seconds > 0:
                    now_ts = time.time()
                    last_ts = float(self._last_entry_ts.get(coin, 0.0) or 0.0)
                    if last_ts and (now_ts - last_ts) < self._entry_cooldown_seconds:
                        wait_s = self._entry_cooldown_seconds - (now_ts - last_ts)
                        raise ValueError(
                            f"Entry cooldown active for {coin}: wait {wait_s:.1f}s"
                        )

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

            if (
                not reduce_only
                and self._max_order_notional_usd > 0
                and current_price > 0
                and quantity > 0
            ):
                requested_notional = float(quantity) * float(current_price)
                if requested_notional > self._max_order_notional_usd:
                    size_decimals = int(market.get("size_decimals", 3) or 3)
                    scale = 10 ** max(0, size_decimals)
                    capped_qty = math.floor(
                        (self._max_order_notional_usd / float(current_price)) * scale
                    ) / scale
                    if capped_qty <= 0:
                        raise ValueError(
                            f"Max order notional cap too low for {coin}: "
                            f"cap={self._max_order_notional_usd} price={current_price}"
                        )
                    logger.warning(
                        "Notional cap applied for %s: requested %.6f USD -> cap %.2f USD "
                        "(qty %.8f -> %.8f)",
                        coin,
                        requested_notional,
                        self._max_order_notional_usd,
                        quantity,
                        capped_qty,
                    )
                    quantity = float(capped_qty)

            if (
                not reduce_only
                and entry_like
                and self._max_position_notional_usd > 0
                and current_price > 0
                and quantity > 0
            ):
                requested_notional = float(quantity) * float(current_price)
                current = self.positions.get(coin)
                current_qty = float(getattr(current, "quantity", 0.0) or 0.0) if current else 0.0
                current_notional = abs(current_qty * float(current_price))
                current_side = getattr(current, "side", None) if current else None
                same_direction = (
                    (is_buy and current_side in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG"))
                    or ((not is_buy) and current_side in (TradeSide.SELL, TradeSide.SHORT, "SELL", "SHORT"))
                )
                if not current or current_qty <= 0:
                    projected_notional = requested_notional
                elif same_direction:
                    projected_notional = current_notional + requested_notional
                else:
                    projected_notional = abs(current_notional - requested_notional)
                if projected_notional > self._max_position_notional_usd:
                    raise ValueError(
                        f"Max position notional exceeded for {coin}: "
                        f"projected={projected_notional:.4f} cap={self._max_position_notional_usd:.4f}"
                    )

            self._sanitize_signal_risk_levels(
                signal,
                is_buy=is_buy,
                reference_price=float(current_price),
                reduce_only=reduce_only,
            )
            self._apply_default_risk_levels(
                signal,
                is_buy=is_buy,
                reference_price=float(current_price),
                reduce_only=reduce_only,
            )

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
                    if entry_like:
                        self._last_entry_ts[coin] = time.time()

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
                        "stop_loss": signal.stop_loss,
                        "take_profit": signal.take_profit,
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
            api_key_index=int(self._api_key_index),
        )
        if err is not None:
            raise RuntimeError(f"Signer create_market_order failed: {err}")

        tx_hash = getattr(api_response, "tx_hash", "") if api_response else ""
        code = getattr(api_response, "code", None) if api_response else None
        message = getattr(api_response, "message", "") if api_response else ""
        accepted = bool(code == 200)

        filled_qty = 0.0
        avg_fill_price = 0.0
        execution_state = "accepted" if accepted else "rejected"

        # Best-effort reconciliation: if the tx is already indexed, parse fill data
        # so platform telemetry reflects real execution instead of 0/0 placeholders.
        if accepted and tx_hash and self.transaction_api:
            for _ in range(3):
                try:
                    tx = await self._call_lighter_api(
                        self.transaction_api.tx,
                        by="hash",
                        value=str(tx_hash),
                    )
                    event_info_raw = getattr(tx, "event_info", "") if tx else ""
                    if event_info_raw:
                        event = json.loads(str(event_info_raw))
                        trade = event.get("t") or {}
                        size_int = float(trade.get("s") or 0.0)
                        price_int_fill = float(trade.get("p") or 0.0)
                        if size_int > 0:
                            filled_qty = size_int / float(10 ** max(0, size_decimals))
                            avg_fill_price = price_int_fill / float(10 ** max(0, price_decimals)) if price_int_fill > 0 else 0.0
                            execution_state = "filled"
                            break
                except Exception:
                    # tx may not be visible immediately after send_tx
                    pass
                await asyncio.sleep(0.5)

        return {
            "success": accepted,
            "order_id": tx_hash or f"lighter_tx_{signal_id}",
            "filled_quantity": float(filled_qty),
            "avg_fill_price": float(avg_fill_price),
            "error": None if accepted else (message or "send_tx rejected"),
            "metadata": {
                "execution_state": execution_state,
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

            # Mark freshness on any successful account fetch, even if no positions.
            self._last_position_check_ts = time.time()
            self._last_position_check_error = ""

            raw_positions = []
            if account is None:
                raw_positions = []
            elif isinstance(account, dict):
                raw_positions = account.get("positions") or []
            else:
                as_dict = {}
                if hasattr(account, "to_dict"):
                    as_dict = account.to_dict()  # type: ignore[attr-defined]
                if isinstance(as_dict, dict):
                    raw_positions = as_dict.get("positions") or []
                    # Newer SDK schema: DetailedAccounts -> accounts[].positions[]
                    if not raw_positions:
                        accounts_payload = as_dict.get("accounts")
                        if isinstance(accounts_payload, list) and accounts_payload:
                            target_idx = int(self.account_index or -1)
                            account_record = None
                            for row in accounts_payload:
                                if not isinstance(row, dict):
                                    continue
                                try:
                                    idx_val = int(
                                        row.get("account_index", row.get("index", -1)) or -1
                                    )
                                except (TypeError, ValueError):
                                    idx_val = -1
                                if idx_val == target_idx:
                                    account_record = row
                                    break
                            if account_record is None:
                                account_record = accounts_payload[0]
                            if isinstance(account_record, dict):
                                raw_positions = account_record.get("positions") or []
                # Legacy schema fallback
                if not raw_positions and hasattr(account, "positions"):
                    raw_positions = getattr(account, "positions", None) or []

            next_positions: Dict[str, Position] = {}

            for pos in raw_positions:
                getv = pos.get if isinstance(pos, dict) else lambda k, d=None: getattr(pos, k, d)

                try:
                    size = float(getv("size", getv("position", 0)))
                except (TypeError, ValueError):
                    size = 0.0
                if abs(size) > 0 and getv("size", None) is None and getv("position", None) is not None:
                    try:
                        sign = float(getv("sign", 1) or 1)
                    except (TypeError, ValueError):
                        sign = 1.0
                    size = abs(size) if sign >= 0 else -abs(size)
                if size == 0:
                    continue

                symbol_raw = getv("symbol", None)
                order_book_id = getv("order_book_id", getv("market_id", 0))
                symbol = str(symbol_raw or "").strip().upper() or f"MARKET_{order_book_id}"

                side = TradeSide.LONG if size > 0 else TradeSide.SHORT
                qty = abs(size)
                try:
                    entry_price = float(getv("entry_price", getv("avg_entry_price", 0)) or 0.0)
                except (TypeError, ValueError):
                    entry_price = 0.0

                current_price = 0.0
                for field in ("mark_price", "current_price", "last_price", "index_price", "mid_price"):
                    try:
                        current_price = float(getv(field, 0) or 0.0)
                    except (TypeError, ValueError):
                        current_price = 0.0
                    if current_price > 0:
                        break
                if current_price <= 0:
                    try:
                        pos_val = float(getv("position_value", 0) or 0.0)
                    except (TypeError, ValueError):
                        pos_val = 0.0
                    if qty > 0 and pos_val != 0:
                        current_price = abs(pos_val) / qty

                existing = self.positions.get(symbol)
                if existing is None:
                    existing = Position(
                        position_id=f"{PLATFORM.value}_{order_book_id}",
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

                if current_price > 0:
                    existing.current_price = current_price
                if current_price > 0 and existing.entry_price > 0:
                    if existing.side in (TradeSide.BUY, TradeSide.LONG):
                        existing.unrealized_pnl = (current_price - existing.entry_price) * qty
                    else:
                        existing.unrealized_pnl = (existing.entry_price - current_price) * qty

                # Ensure reconciled exchange positions also have local TP/SL guards.
                ref_price = 0.0
                try:
                    ref_price = float(existing.entry_price or 0.0)
                except (TypeError, ValueError):
                    ref_price = 0.0
                if ref_price <= 0:
                    try:
                        ref_price = float(existing.current_price or 0.0)
                    except (TypeError, ValueError):
                        ref_price = 0.0

                if ref_price > 0:
                    is_long = existing.side in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG")
                    try:
                        tp = float(existing.take_profit) if existing.take_profit is not None else 0.0
                    except (TypeError, ValueError):
                        tp = 0.0
                    try:
                        sl = float(existing.stop_loss) if existing.stop_loss is not None else 0.0
                    except (TypeError, ValueError):
                        sl = 0.0
                    if tp <= 0 and self._default_take_profit_pct > 0:
                        existing.take_profit = round(
                            ref_price * (1 + self._default_take_profit_pct / 100.0)
                            if is_long
                            else ref_price * (1 - self._default_take_profit_pct / 100.0),
                            8,
                        )
                    if sl <= 0 and self._default_stop_loss_pct > 0:
                        existing.stop_loss = round(
                            ref_price * (1 - self._default_stop_loss_pct / 100.0)
                            if is_long
                            else ref_price * (1 + self._default_stop_loss_pct / 100.0),
                            8,
                        )
                existing.updated_at = utc_now()

                next_positions[symbol] = existing

            # Replace with the authoritative snapshot (clears closed positions).
            had_local_positions = bool(self.positions)
            if had_local_positions and not next_positions:
                self._empty_position_snapshot_streak += 1
                if self._empty_position_snapshot_streak < self._empty_position_confirmations:
                    logger.warning(
                        "Empty position snapshot (%d/%d) while local positions exist; "
                        "retaining local state until confirmed",
                        self._empty_position_snapshot_streak,
                        self._empty_position_confirmations,
                    )
                    return
                logger.warning(
                    "Confirmed empty position snapshot after %d checks; clearing local positions",
                    self._empty_position_snapshot_streak,
                )
            else:
                self._empty_position_snapshot_streak = 0

            self.positions = next_positions

        except Exception as e:
            self._last_position_check_error = f"{type(e).__name__}: {e}"
            logger.error(f"Position check error: {e}")

    async def _enforce_position_risk_exits(self) -> None:
        """Trigger reduce-only closes when TP/SL thresholds are reached."""
        if not self.positions:
            return

        now = time.time()
        for symbol, position in list(self.positions.items()):
            try:
                qty = float(getattr(position, "quantity", 0.0) or 0.0)
            except (TypeError, ValueError):
                qty = 0.0
            if qty <= 0:
                continue

            tp = getattr(position, "take_profit", None)
            sl = getattr(position, "stop_loss", None)
            try:
                tp = float(tp) if tp is not None else None
            except (TypeError, ValueError):
                tp = None
            try:
                sl = float(sl) if sl is not None else None
            except (TypeError, ValueError):
                sl = None
            if (tp is None or tp <= 0) and (sl is None or sl <= 0):
                self._risk_exit_attempted_at.pop(symbol, None)
                continue

            price = float(getattr(position, "current_price", 0.0) or 0.0)
            if price <= 0:
                price = float(await self._get_ticker(symbol) or 0.0)
                if price > 0:
                    position.current_price = price
                    position.updated_at = utc_now()
            if price <= 0:
                continue

            is_long = position.side in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG")
            hit_tp = bool(tp and ((price >= tp) if is_long else (price <= tp)))
            hit_sl = bool(sl and ((price <= sl) if is_long else (price >= sl)))
            if not hit_tp and not hit_sl:
                self._risk_exit_attempted_at.pop(symbol, None)
                continue

            last_attempt = float(self._risk_exit_attempted_at.get(symbol, 0.0))
            if now - last_attempt < self._risk_exit_cooldown_seconds:
                continue
            self._risk_exit_attempted_at[symbol] = now

            reason = "take_profit" if hit_tp else "stop_loss"
            exit_side = TradeSide.SELL if is_long else TradeSide.BUY
            exit_type = SignalType.TAKE_PROFIT if hit_tp else SignalType.STOP_LOSS
            exit_signal = TradeSignal(
                signal_id=f"risk-{reason}-{symbol}-{int(now * 1000)}",
                symbol=symbol,
                side=exit_side,
                signal_type=exit_type,
                confidence=1.0,
                source=f"{SERVICE_NAME}-risk-guard",
                quantity=qty,
                metadata={
                    "reduce_only": True,
                    "risk_exit": reason,
                    "trigger_price": price,
                    "origin": "tp_sl_guard",
                },
            )

            logger.warning(
                "Risk exit trigger %s on %s | price=%s tp=%s sl=%s qty=%s",
                reason,
                symbol,
                price,
                tp,
                sl,
                qty,
            )
            result = await self._execute_trade(exit_signal)
            if not (result.metadata or {}).get("noop"):
                await publish("trade-executed", result)
            filled_qty = self._to_float(getattr(result, "filled_quantity", 0.0), 0.0)
            if result.success and (filled_qty > 0 or (result.metadata or {}).get("noop")):
                self._risk_exit_attempted_at.pop(symbol, None)

    async def _close_all_positions(self):
        """Close all positions on Lighter."""
        try:
            if not self.positions:
                logger.info("Close-all requested but no local positions are tracked")
                return

            closed = 0
            failed = 0
            for symbol, position in list(self.positions.items()):
                try:
                    qty = float(getattr(position, "quantity", 0.0) or 0.0)
                except (TypeError, ValueError):
                    qty = 0.0
                if qty <= 0:
                    continue

                pos_side = getattr(position, "side", None)
                close_side = (
                    TradeSide.SELL
                    if pos_side in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG")
                    else TradeSide.BUY
                )
                exit_signal = TradeSignal(
                    signal_id=f"close-all-{symbol.lower()}-{int(time.time())}",
                    symbol=symbol,
                    side=close_side,
                    signal_type=SignalType.EXIT,
                    quantity=abs(qty),
                    source="risk-close-all",
                    metadata={"reduce_only": True, "origin": "risk_close_all"},
                )
                result = await self._execute_trade(exit_signal, ignore_trading_guard=True)
                if result.success:
                    closed += 1
                else:
                    failed += 1
                    logger.error(
                        "Close-all failed for %s: %s",
                        symbol,
                        result.error_message or "unknown_error",
                    )
            logger.info("Close-all complete | requested=%d failed=%d", closed, failed)
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
