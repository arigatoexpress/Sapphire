"""
Lighter Trading Bot - Standalone Service (L2 Order Book)

This is an independent microservice for trading on Lighter Protocol.
Lighter is a decentralized L2 order book exchange built on ZK-rollups.
"""

import asyncio
import contextlib
import html
import inspect
import json
import logging
import math
import os
import signal
import sys
import tempfile
import time

import requests
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import requests

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
    from shared.circuit_breaker import CircuitBreaker, CircuitBreakerOpen
    from shared.execution_idempotency import ExecutionIdempotency
    from shared.models import (
        BalanceUpdate,
        Platform,
        Position,
        SignalType,
        TradeResult,
        TradeSide,
        TradeSignal,
    )
    from shared.pubsub import get_pubsub_client, publish, subscribe
    from shared.risk_kernel import HardRiskKernel
    from shared.utils import ServiceConfig, format_percent, format_price, setup_logging, utc_now
except ImportError:
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
    from risk_kernel import HardRiskKernel
    from utils import ServiceConfig, setup_logging, utc_now

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
            import ctypes as _ct
            import os as _os

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
        self._init_complete = False
        self._shutdown_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        self._cleanup_complete = False

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
        self.account_index: int | None = None
        self.balance: float = 0.0

        # Position tracking
        self.positions: dict[str, Position] = {}
        self.market_info: dict[str, dict] = {}

        # Performance metrics
        self.trades_executed = 0
        self.trades_failed = 0
        self.avg_latency_ms = 0.0
        self._execution_block_reason: str | None = None

        # Firestore client shared by idempotency guard + position persistence.
        self._db = None
        # Signal idempotency guard: Firestore-backed (durable across restarts) with
        # in-memory fast path.  Initialized without a Firestore client; warm() is
        # called after initialize() connects to GCP.
        self._idempotency: ExecutionIdempotency | None = None
        self._pubsub_initialized = False
        self._signal_dedupe_ttl_seconds = max(
            60, int(os.getenv("SIGNAL_DEDUPE_TTL_SECONDS", "900"))
        )
        self._processed_signal_ids: dict[str, float] = {}

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
        # Position/account refresh loop. Keep this above 1s to avoid venue 429 storms.
        self._position_check_interval_seconds = max(
            2.0,
            self._env_float(("LIGHTER_POSITION_CHECK_INTERVAL_SECONDS",), default=5.0),
        )
        self._single_symbol_mode = self._env_flag(
            "LIGHTER_SINGLE_SYMBOL_MODE",
            default=True,
        )
        self._entry_symbol_allowlist = {
            self._normalize_coin_symbol(s)
            for s in str(os.getenv("LIGHTER_ENTRY_SYMBOL_ALLOWLIST", "")).split(",")
            if str(s).strip()
        }
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
        self._max_portfolio_notional_usd = max(
            0.0,
            self._env_float(
                ("LIGHTER_MAX_PORTFOLIO_NOTIONAL_USD",),
                default=self._max_position_notional_usd,
            ),
        )
        self._target_order_notional_usd = max(
            0.0,
            self._env_float(("LIGHTER_TARGET_ORDER_NOTIONAL_USD",), default=0.0),
        )
        self._min_entry_notional_usd = max(
            0.0,
            self._env_float(("LIGHTER_MIN_ENTRY_NOTIONAL_USD",), default=0.0),
        )
        self._min_add_notional_usd = max(
            0.0,
            self._env_float(("LIGHTER_MIN_ADD_NOTIONAL_USD",), default=0.0),
        )
        self._cap_near_churn_enabled = self._env_flag(
            "LIGHTER_CAP_NEAR_CHURN_ENABLED",
            default=True,
        )
        self._cap_near_churn_ratio = self._clamp(
            self._env_float(("LIGHTER_CAP_NEAR_CHURN_RATIO",), default=0.90),
            0.50,
            0.999,
        )
        self._cap_near_min_ev_edge_pct = max(
            0.0,
            self._env_float(("LIGHTER_CAP_NEAR_MIN_EV_EDGE_PCT",), default=0.20),
        )
        self._cap_near_min_net_ev_pct = max(
            0.0,
            self._env_float(("LIGHTER_CAP_NEAR_MIN_NET_EV_PCT",), default=0.10),
        )
        self._max_signal_leverage = max(
            1.0,
            self._env_float(("LIGHTER_MAX_SIGNAL_LEVERAGE",), default=20.0),
        )
        self._use_leverage_for_notional = self._env_flag(
            "LIGHTER_USE_LEVERAGE_FOR_NOTIONAL",
            default=False,
        )
        self._target_order_leverage = max(
            1.0,
            self._env_float(("LIGHTER_TARGET_ORDER_LEVERAGE",), default=self._max_signal_leverage),
        )
        if self._target_order_leverage > self._max_signal_leverage:
            logger.warning(
                "LIGHTER_TARGET_ORDER_LEVERAGE %.2f exceeds LIGHTER_MAX_SIGNAL_LEVERAGE %.2f; clamping.",
                self._target_order_leverage,
                self._max_signal_leverage,
            )
            self._target_order_leverage = self._max_signal_leverage
        self._dynamic_sizing_enabled = self._env_flag(
            "LIGHTER_DYNAMIC_SIZING_ENABLED",
            default=True,
        )
        self._dynamic_size_min_mult = max(
            0.05,
            self._env_float(("LIGHTER_DYNAMIC_SIZE_MIN_MULT",), default=0.35),
        )
        self._dynamic_size_max_mult = max(
            self._dynamic_size_min_mult,
            self._env_float(("LIGHTER_DYNAMIC_SIZE_MAX_MULT",), default=1.20),
        )
        self._ev_maker_fee_bps = max(
            0.0,
            self._env_float(("LIGHTER_EV_MAKER_FEE_BPS",), default=1.5),
        )
        self._ev_taker_fee_bps = max(
            0.0,
            self._env_float(("LIGHTER_EV_TAKER_FEE_BPS",), default=4.5),
        )
        self._ev_expected_taker_ratio = self._clamp(
            self._env_float(("LIGHTER_EV_EXPECTED_TAKER_RATIO",), default=1.0),
            0.0,
            1.0,
        )
        self._ev_slippage_base_bps = max(
            0.0,
            self._env_float(("LIGHTER_EV_SLIPPAGE_BASE_BPS",), default=1.5),
        )
        self._ev_slippage_vol_mult_bps = max(
            0.0,
            self._env_float(("LIGHTER_EV_SLIPPAGE_VOL_MULT_BPS",), default=2.0),
        )
        self._ev_slippage_notional_ref_usd = max(
            0.01,
            self._env_float(("LIGHTER_EV_SLIPPAGE_NOTIONAL_REF_USD",), default=4.0),
        )
        self._ev_slippage_notional_mult_bps = max(
            0.0,
            self._env_float(("LIGHTER_EV_SLIPPAGE_NOTIONAL_MULT_BPS",), default=2.0),
        )
        self._sync_before_entry = self._env_flag(
            "LIGHTER_SYNC_BEFORE_ENTRY",
            default=True,
        )
        self._jurisdiction_block_seconds = max(
            0.0,
            self._env_float(("LIGHTER_JURISDICTION_BLOCK_SECONDS",), default=600.0),
        )
        self._jurisdiction_block_until_ts: float = 0.0
        self._jurisdiction_block_reason: str = ""
        self._entry_cooldown_seconds = max(
            0.0,
            self._env_float(("LIGHTER_ENTRY_COOLDOWN_SECONDS",), default=0.0),
        )
        self._last_entry_ts: dict[str, float] = {}
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
        self._entry_min_confidence = self._clamp(
            self._env_float(("LIGHTER_ENTRY_MIN_CONFIDENCE",), default=0.0),
            0.0,
            1.0,
        )
        self._entry_min_edge_pct = max(
            0.0,
            self._env_float(("LIGHTER_ENTRY_MIN_EDGE_PCT",), default=0.0),
        )
        self._perf_guard_enabled = self._env_flag(
            "LIGHTER_PERF_GUARD_ENABLED",
            default=True,
        )
        self._perf_guard_window = max(
            10,
            int(self._env_float(("LIGHTER_PERF_GUARD_WINDOW",), default=40.0)),
        )
        self._perf_guard_min_samples = max(
            5,
            int(self._env_float(("LIGHTER_PERF_GUARD_MIN_SAMPLES",), default=20.0)),
        )
        self._perf_guard_min_fill_rate = self._clamp(
            self._env_float(("LIGHTER_PERF_GUARD_MIN_FILL_RATE",), default=0.20),
            0.0,
            1.0,
        )
        self._perf_guard_max_hard_fail_rate = self._clamp(
            self._env_float(("LIGHTER_PERF_GUARD_MAX_HARD_FAIL_RATE",), default=0.45),
            0.0,
            1.0,
        )
        self._strategy_perf_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self._perf_guard_window)
        )
        self._size_ramp_enabled = self._env_flag(
            "LIGHTER_SIZE_RAMP_ENABLED",
            default=True,
        )
        _base_target_margin = max(0.1, float(self._target_order_notional_usd or 0.0))
        self._size_ramp_min_margin_usd = max(
            0.1,
            self._env_float(("LIGHTER_SIZE_RAMP_MIN_MARGIN_USD",), default=_base_target_margin),
        )
        self._size_ramp_max_margin_usd = max(
            self._size_ramp_min_margin_usd,
            self._env_float(("LIGHTER_SIZE_RAMP_MAX_MARGIN_USD",), default=_base_target_margin),
        )
        self._size_ramp_step_margin_usd = max(
            0.1,
            self._env_float(("LIGHTER_SIZE_RAMP_STEP_MARGIN_USD",), default=0.5),
        )
        self._size_ramp_min_samples = max(
            5,
            int(
                self._env_float(
                    ("LIGHTER_SIZE_RAMP_MIN_SAMPLES",),
                    default=max(10.0, float(self._perf_guard_min_samples)),
                )
            ),
        )
        self._size_ramp_up_fill_rate = self._clamp(
            self._env_float(
                ("LIGHTER_SIZE_RAMP_UP_FILL_RATE",),
                default=max(0.65, float(self._perf_guard_min_fill_rate)),
            ),
            0.0,
            1.0,
        )
        self._size_ramp_down_fill_rate = self._clamp(
            self._env_float(
                ("LIGHTER_SIZE_RAMP_DOWN_FILL_RATE",),
                default=max(0.05, float(self._perf_guard_min_fill_rate) - 0.15),
            ),
            0.0,
            1.0,
        )
        self._size_ramp_max_hard_fail_rate = self._clamp(
            self._env_float(
                ("LIGHTER_SIZE_RAMP_MAX_HARD_FAIL_RATE",),
                default=min(0.10, float(self._perf_guard_max_hard_fail_rate)),
            ),
            0.0,
            1.0,
        )
        self._size_ramp_adjust_cooldown_seconds = max(
            30.0,
            self._env_float(("LIGHTER_SIZE_RAMP_ADJUST_COOLDOWN_SECONDS",), default=300.0),
        )
        self._size_ramp_recent_streak = max(
            2,
            int(self._env_float(("LIGHTER_SIZE_RAMP_RECENT_STREAK",), default=3.0)),
        )
        self._size_ramp_default_margin_usd = self._clamp(
            _base_target_margin,
            self._size_ramp_min_margin_usd,
            self._size_ramp_max_margin_usd,
        )
        self._size_ramp_margin_by_key: dict[str, float] = defaultdict(
            lambda: self._size_ramp_default_margin_usd
        )
        self._size_ramp_last_adjust_ts: dict[str, float] = {}
        self._strategy_require_metadata = self._env_flag(
            "LIGHTER_STRATEGY_REQUIRE_METADATA",
            default=False,
        )
        self._allowed_signal_sources = {
            s.strip().lower()
            for s in str(os.getenv("LIGHTER_ALLOWED_SIGNAL_SOURCES", "")).split(",")
            if s.strip()
        }
        self._trading_enabled = self._env_flag("TRADING_ENABLED", default=True)
        self._allow_live_trading = self._env_flag("ALLOW_LIVE_TRADING", default=True)
        self._trading_mode = str(os.getenv("TRADING_MODE", "live")).strip().lower() or "live"
        self._risk_exit_cooldown_seconds = max(
            5.0,
            self._env_float(("LIGHTER_RISK_EXIT_COOLDOWN_SECONDS",), default=15.0),
        )
        self._risk_exit_reconcile_hold_seconds = max(
            self._risk_exit_cooldown_seconds,
            self._env_float(("LIGHTER_RISK_EXIT_RECONCILE_HOLD_SECONDS",), default=45.0),
        )
        self._max_position_hold_seconds = max(
            0.0,
            self._env_float(("LIGHTER_MAX_POSITION_HOLD_SECONDS",), default=0.0),
        )
        self._risk_exit_attempted_at: dict[str, float] = {}
        self._risk_exit_reconcile_hold_until: dict[str, float] = {}
        self._dynamic_risk_enabled = self._env_flag(
            "LIGHTER_DYNAMIC_RISK_ENABLED",
            default=True,
        )
        self._dynamic_risk_update_seconds = max(
            15.0,
            self._env_float(("LIGHTER_DYNAMIC_RISK_UPDATE_SECONDS",), default=60.0),
        )
        self._dynamic_tp_trend_boost = max(
            0.0,
            self._env_float(("LIGHTER_DYNAMIC_TP_TREND_BOOST_PCT",), default=25.0),
        )
        self._dynamic_sl_tighten = max(
            0.0,
            self._env_float(("LIGHTER_DYNAMIC_SL_TIGHTEN_PCT",), default=20.0),
        )
        self._dynamic_volatility_widen = max(
            0.0,
            self._env_float(("LIGHTER_DYNAMIC_VOL_WIDEN_PCT",), default=20.0),
        )
        self._opportunity_rotation_enabled = self._env_flag(
            "LIGHTER_OPPORTUNITY_ROTATION_ENABLED",
            default=True,
        )
        self._opportunity_rotation_min_edge_pct = max(
            0.0,
            self._env_float(("LIGHTER_OPPORTUNITY_MIN_EDGE_PCT",), default=0.20),
        )
        self._opportunity_rotation_cooldown_seconds = max(
            30.0,
            self._env_float(("LIGHTER_OPPORTUNITY_COOLDOWN_SECONDS",), default=180.0),
        )
        self._last_opportunity_rotation_ts: float = 0.0
        self._last_dynamic_risk_update_ts: dict[str, float] = {}
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
        self._hard_risk_kernel_enabled = self._env_flag(
            "LIGHTER_HARD_RISK_KERNEL_ENABLED",
            default=True,
        )
        self._hard_risk_hold_seconds = max(
            60.0,
            self._env_float(("LIGHTER_HARD_RISK_HOLD_SECONDS",), default=1800.0),
        )
        self._hard_risk_max_daily_loss_pct = max(
            0.0,
            self._env_float(("LIGHTER_HARD_RISK_MAX_DAILY_LOSS_PCT",), default=4.0),
        )
        self._hard_risk_max_daily_loss_usd = max(
            0.0,
            self._env_float(("LIGHTER_HARD_RISK_MAX_DAILY_LOSS_USD",), default=0.0),
        )
        self._hard_risk_max_intraday_drawdown_pct = max(
            0.0,
            self._env_float(("LIGHTER_HARD_RISK_MAX_INTRADAY_DRAWDOWN_PCT",), default=3.5),
        )
        self._hard_risk_max_consecutive_loss_events = max(
            0,
            int(
                self._env_float(
                    ("LIGHTER_HARD_RISK_MAX_CONSECUTIVE_LOSS_EVENTS",),
                    default=4.0,
                )
            ),
        )
        self._hard_risk_max_consecutive_hard_fails = max(
            0,
            int(
                self._env_float(
                    ("LIGHTER_HARD_RISK_MAX_CONSECUTIVE_HARD_FAILS",),
                    default=5.0,
                )
            ),
        )
        self._hard_risk_loss_event_min_delta_usd = max(
            0.0,
            self._env_float(("LIGHTER_HARD_RISK_LOSS_EVENT_MIN_DELTA_USD",), default=0.15),
        )
        self._hard_risk_kernel = HardRiskKernel(
            enabled=self._hard_risk_kernel_enabled,
            hold_seconds=self._hard_risk_hold_seconds,
            max_daily_loss_pct=self._hard_risk_max_daily_loss_pct,
            max_daily_loss_usd=self._hard_risk_max_daily_loss_usd,
            max_intraday_drawdown_pct=self._hard_risk_max_intraday_drawdown_pct,
            max_consecutive_loss_events=self._hard_risk_max_consecutive_loss_events,
            max_consecutive_hard_fails=self._hard_risk_max_consecutive_hard_fails,
            loss_event_min_delta_usd=self._hard_risk_loss_event_min_delta_usd,
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
        self._equity_baseline: float | None = None
        self._equity_peak: float | None = None
        self._equity_trough: float | None = None
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
        self._telegram_enable_charts = self._env_flag(
            "LIGHTER_TELEGRAM_ENABLE_CHARTS",
            default=True,
        )
        self._telegram_digest_seconds = max(
            300,
            int(self._env_float(("LIGHTER_TELEGRAM_DIGEST_SECONDS",), default=1800.0)),
        )
        self._telegram_digest_flat_seconds = max(
            self._telegram_digest_seconds,
            int(
                self._env_float(
                    ("LIGHTER_TELEGRAM_FLAT_DIGEST_SECONDS",),
                    default=14400.0,
                )
            ),
        )
        self._reject_tax_window_hours = max(
            1.0,
            self._env_float(("LIGHTER_REJECT_TAX_WINDOW_HOURS",), default=24.0),
        )
        self._reject_tax_cache_ttl_seconds = max(
            10.0,
            self._env_float(("LIGHTER_REJECT_TAX_CACHE_TTL_SECONDS",), default=45.0),
        )
        self._reject_tax_alert_pct = self._clamp(
            self._env_float(("LIGHTER_REJECT_TAX_ALERT_PCT",), default=65.0),
            0.0,
            100.0,
        )
        self._go_nogo_max_reject_tax_pct = self._clamp(
            self._env_float(("LIGHTER_GO_NOGO_MAX_REJECT_TAX_PCT",), default=75.0),
            0.0,
            100.0,
        )
        self._go_nogo_max_hard_fail_pct = self._clamp(
            self._env_float(("LIGHTER_GO_NOGO_MAX_HARD_FAIL_PCT",), default=10.0),
            0.0,
            100.0,
        )
        self._go_nogo_min_sample_size = max(
            1,
            int(self._env_float(("LIGHTER_GO_NOGO_MIN_SAMPLE_SIZE",), default=20.0)),
        )
        self._go_nogo_gate_enabled = self._env_flag(
            "LIGHTER_GO_NOGO_GATE_ENABLED",
            default=True,
        )
        self._go_nogo_cache_ttl_seconds = max(
            5.0,
            self._env_float(("LIGHTER_GO_NOGO_CACHE_TTL_SECONDS",), default=20.0),
        )
        self._platform_decision_gate_enabled = self._env_flag(
            "LIGHTER_PLATFORM_DECISION_GATE_ENABLED",
            default=True,
        )
        self._platform_decision_url = str(
            os.getenv(
                "LIGHTER_PLATFORM_DECISION_URL",
                "https://sapphirealpha.xyz/api/platform/strategy-ops?days=7",
            )
        ).strip()
        self._platform_decision_cache_ttl_seconds = max(
            10.0,
            self._env_float(("LIGHTER_PLATFORM_DECISION_CACHE_TTL_SECONDS",), default=60.0),
        )
        self._platform_decision_timeout_seconds = max(
            1.0,
            self._env_float(("LIGHTER_PLATFORM_DECISION_TIMEOUT_SECONDS",), default=3.0),
        )
        self._cached_reject_tax_metrics: dict[str, Any] = {}
        self._last_reject_tax_fetch_ts: float = 0.0
        self._cached_reject_tax_window_metrics: dict[str, dict[str, Any]] = {}
        self._last_reject_tax_fetch_by_window: dict[str, float] = {}
        self._cached_go_no_go: dict[str, Any] = {}
        self._last_go_no_go_eval_ts: float = 0.0
        self._cached_platform_decision: dict[str, Any] = {}
        self._last_platform_decision_fetch_ts: float = 0.0
        self._equity_snapshot_cache_ttl_seconds = max(
            3.0,
            self._env_float(("LIGHTER_EQUITY_SNAPSHOT_CACHE_TTL_SECONDS",), default=10.0),
        )
        self._cached_equity_snapshot: dict[str, Any] = {}
        self._last_equity_snapshot_ts: float = 0.0
        self._recent_execution_outcomes: deque = deque(maxlen=3000)
        self._last_telegram_digest_ts: float = 0.0
        self._assistant_brief_enabled = self._env_flag(
            "LIGHTER_ASSISTANT_BRIEF_ENABLED",
            default=True,
        )
        self._assistant_brief_interval_seconds = max(
            60.0,
            self._env_float(("LIGHTER_ASSISTANT_BRIEF_INTERVAL_SECONDS",), default=300.0),
        )
        self._last_assistant_brief_ts: float = 0.0
        self._execution_watchdog_enabled = self._env_flag(
            "LIGHTER_EXECUTION_WATCHDOG_ENABLED",
            default=True,
        )
        self._execution_watchdog_no_fill_seconds = max(
            120.0,
            self._env_float(("LIGHTER_EXECUTION_WATCHDOG_NO_FILL_SECONDS",), default=900.0),
        )
        self._execution_watchdog_cooldown_seconds = max(
            60.0,
            self._env_float(("LIGHTER_EXECUTION_WATCHDOG_COOLDOWN_SECONDS",), default=900.0),
        )
        self._execution_failsafe_enabled = self._env_flag(
            "LIGHTER_EXECUTION_FAILSAFE_ENABLED",
            default=True,
        )
        self._execution_failsafe_alert_threshold = max(
            1,
            int(self._env_float(("LIGHTER_EXECUTION_FAILSAFE_ALERT_THRESHOLD",), default=3.0)),
        )
        self._execution_failsafe_hold_seconds = max(
            300.0,
            self._env_float(("LIGHTER_EXECUTION_FAILSAFE_HOLD_SECONDS",), default=1800.0),
        )
        self._execution_watchdog_alert_streak: int = 0
        self._execution_failsafe_until_ts: float = 0.0
        self._execution_failsafe_reason: str = ""
        self._last_execution_attempt_ts: float = 0.0
        self._last_successful_fill_ts: float = 0.0
        self._last_execution_error_message: str = ""
        self._last_execution_watchdog_alert_ts: float = 0.0
        self._lane_heartbeat_enabled = self._env_flag(
            "LIGHTER_LANE_HEARTBEAT_ENABLED",
            default=True,
        )
        self._lane_heartbeat_seconds = max(
            300.0,
            self._env_float(("LIGHTER_LANE_HEARTBEAT_SECONDS",), default=900.0),
        )
        self._last_lane_heartbeat_ts: float = 0.0
        self._order_submit_retry_attempts = max(
            1,
            int(self._env_float(("LIGHTER_ORDER_SUBMIT_RETRY_ATTEMPTS",), default=2.0)),
        )
        self._order_submit_retry_backoff_seconds = max(
            0.1,
            self._env_float(("LIGHTER_ORDER_SUBMIT_RETRY_BACKOFF_SECONDS",), default=0.75),
        )
        self._price_history_limit = max(
            30,
            int(self._env_float(("LIGHTER_PRICE_HISTORY_POINTS",), default=90.0)),
        )
        self._price_history: dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self._price_history_limit)
        )
        self._stop_gateway_server: Callable[[], Any] | None = None
        self._http_session = None
        # Serialize exchange order submission to avoid nonce collisions when
        # concurrent signals/risk exits attempt to place orders at the same time.
        self._order_submit_lock = asyncio.Lock()
        logger.info(
            "Strategy policy | allowed_strategies=%s allowed_timeframes=%s "
            "allowed_sources=%s symbol_allowlist=%s "
            "require_metadata=%s min_conf=%.2f min_edge=%.3f%% "
            "perf_guard=%s n=%d fill>=%.2f fail<=%.2f "
            "entry_cooldown=%.1fs max_order_notional=%.2f "
            "max_position_notional=%.2f max_portfolio_notional=%.2f "
            "target_order_notional=%.2f min_entry_notional=%.2f min_add_notional=%.2f max_signal_leverage=%.1fx "
            "size_ramp=%s min=%.2f max=%.2f step=%.2f n=%d up>=%.2f down<%.2f hf<=%.2f cd=%.0fs streak=%d "
            "dynamic_sizing=%s mult=[%.2f,%.2f] "
            "sync_before_entry=%s jurisdiction_block=%.0fs progress_verify=%.0fs dd_alert=%.2f%% "
            "sync_stale_alert=%.0fs risk_level_max_dev=%.1f%% empty_pos_confirm=%d "
            "max_hold=%.0fs risk_reconcile_hold=%.0fs "
            "hard_risk=%s dd<=%.2f%% intraday<=%.2f%% cons_loss<=%d hard_fail<=%d hold=%.0fs "
            "tg_digest=%.0fs tg_charts=%s dynamic_risk=%s rotation=%s edge=%.3f%% "
            "watchdog=%s no_fill=%.0fs cooldown=%.0fs failsafe=%s threshold=%d hold=%.0fs "
            "lane_heartbeat=%s hb_int=%.0fs order_submit_retry=%dx backoff=%.2fs",
            sorted(self._allowed_strategies) if self._allowed_strategies else ["*"],
            sorted(self._allowed_timeframes) if self._allowed_timeframes else ["*"],
            sorted(self._allowed_signal_sources) if self._allowed_signal_sources else ["*"],
            sorted(self._entry_symbol_allowlist) if self._entry_symbol_allowlist else ["*"],
            self._strategy_require_metadata,
            self._entry_min_confidence,
            self._entry_min_edge_pct,
            self._perf_guard_enabled,
            self._perf_guard_min_samples,
            self._perf_guard_min_fill_rate,
            self._perf_guard_max_hard_fail_rate,
            self._entry_cooldown_seconds,
            self._max_order_notional_usd,
            self._max_position_notional_usd,
            self._max_portfolio_notional_usd,
            self._target_order_notional_usd,
            self._min_entry_notional_usd,
            self._min_add_notional_usd,
            self._max_signal_leverage,
            self._size_ramp_enabled,
            self._size_ramp_min_margin_usd,
            self._size_ramp_max_margin_usd,
            self._size_ramp_step_margin_usd,
            self._size_ramp_min_samples,
            self._size_ramp_up_fill_rate,
            self._size_ramp_down_fill_rate,
            self._size_ramp_max_hard_fail_rate,
            self._size_ramp_adjust_cooldown_seconds,
            self._size_ramp_recent_streak,
            self._dynamic_sizing_enabled,
            self._dynamic_size_min_mult,
            self._dynamic_size_max_mult,
            self._sync_before_entry,
            self._jurisdiction_block_seconds,
            self._progress_verify_interval_seconds,
            self._max_drawdown_alert_pct,
            self._sync_stale_alert_seconds,
            self._max_risk_level_deviation_pct,
            self._empty_position_confirmations,
            self._max_position_hold_seconds,
            self._risk_exit_reconcile_hold_seconds,
            self._hard_risk_kernel_enabled,
            self._hard_risk_max_daily_loss_pct,
            self._hard_risk_max_intraday_drawdown_pct,
            self._hard_risk_max_consecutive_loss_events,
            self._hard_risk_max_consecutive_hard_fails,
            self._hard_risk_hold_seconds,
            self._telegram_digest_seconds,
            self._telegram_enable_charts,
            self._dynamic_risk_enabled,
            self._opportunity_rotation_enabled,
            self._opportunity_rotation_min_edge_pct,
            self._execution_watchdog_enabled,
            self._execution_watchdog_no_fill_seconds,
            self._execution_watchdog_cooldown_seconds,
            self._execution_failsafe_enabled,
            self._execution_failsafe_alert_threshold,
            self._execution_failsafe_hold_seconds,
            self._lane_heartbeat_enabled,
            self._lane_heartbeat_seconds,
            self._order_submit_retry_attempts,
            self._order_submit_retry_backoff_seconds,
        )
        logger.info(
            "EV policy | maker_fee=%.2fbps taker_fee=%.2fbps taker_ratio=%.2f "
            "slippage_base=%.2fbps slippage_vol_mult=%.2fbps slippage_notional_ref=%.2f "
            "slippage_notional_mult=%.2fbps cap_near=%s ratio=%.3f min_ev=%.3f%% min_edge=%.3f%% "
            "reject_tax_window=%.1fh alert=%.1f%% go_no_go_gate=%s cache=%.0fs "
            "platform_gate=%s platform_cache=%.0fs "
            "go_no_go_reject<=%.1f%% go_no_go_hard_fail<=%.1f%% sample>=%d",
            self._ev_maker_fee_bps,
            self._ev_taker_fee_bps,
            self._ev_expected_taker_ratio,
            self._ev_slippage_base_bps,
            self._ev_slippage_vol_mult_bps,
            self._ev_slippage_notional_ref_usd,
            self._ev_slippage_notional_mult_bps,
            self._cap_near_churn_enabled,
            self._cap_near_churn_ratio,
            self._cap_near_min_net_ev_pct,
            self._cap_near_min_ev_edge_pct,
            self._reject_tax_window_hours,
            self._reject_tax_alert_pct,
            self._go_nogo_gate_enabled,
            self._go_nogo_cache_ttl_seconds,
            self._platform_decision_gate_enabled,
            self._platform_decision_cache_ttl_seconds,
            self._go_nogo_max_reject_tax_pct,
            self._go_nogo_max_hard_fail_pct,
            self._go_nogo_min_sample_size,
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
    def _decimal_places_from_step(step_size: Any) -> int:
        """Return decimal precision implied by a numeric step size."""
        try:
            dec = Decimal(str(step_size))
        except (InvalidOperation, ValueError, TypeError):
            return 0
        norm = dec.normalize()
        exponent = int(norm.as_tuple().exponent)
        return max(0, -exponent)

    def _market_size_decimals(self, market: dict[str, Any]) -> int:
        if not isinstance(market, dict):
            return 0
        try:
            supported = int(
                market.get("supported_size_decimals", market.get("size_decimals", 0)) or 0
            )
        except (TypeError, ValueError):
            supported = 0
        if supported > 0:
            return supported
        return self._decimal_places_from_step(market.get("step_size", 0))

    def _quantize_qty_down(self, qty: float, decimals: int) -> float:
        scale = 10 ** max(0, int(decimals or 0))
        return math.floor(max(0.0, float(qty)) * scale) / scale

    @staticmethod
    def _is_restricted_jurisdiction_error(message: str) -> bool:
        msg = str(message or "").lower()
        return ("restricted jurisdiction" in msg) or ("20558" in msg and "restricted" in msg)

    def _set_jurisdiction_block(self, error_message: str) -> None:
        if self._jurisdiction_block_seconds <= 0:
            return
        if str(error_message or "").lower().startswith("jurisdiction block active"):
            return
        if not self._is_restricted_jurisdiction_error(error_message):
            return
        self._jurisdiction_block_until_ts = time.time() + self._jurisdiction_block_seconds
        self._jurisdiction_block_reason = (
            str(error_message).strip()[:220] or "restricted jurisdiction response"
        )
        logger.warning(
            "Jurisdiction block activated for %.0fs due to execution error: %s",
            self._jurisdiction_block_seconds,
            self._jurisdiction_block_reason,
        )

    async def _call_lighter_api(self, api_callable, *args, **kwargs):
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

        last_exc: Exception | None = None
        for attempt in range(1, 4):  # attempts 1, 2, 3
            if self._shutdown_event.is_set():
                raise asyncio.CancelledError()
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
                if self._shutdown_event.is_set():
                    raise asyncio.CancelledError()
                last_exc = exc
                if attempt == 3:
                    break
                wait = 2 ** (attempt - 1)  # 1 s, 2 s
                logger.warning(
                    "Lighter API connection error (attempt %d/3, retry in %ds): %s: %s",
                    attempt, wait, type(exc).__name__, exc,
                )
                await self._sleep_or_stop(wait)

        raise last_exc  # type: ignore[misc]

    async def initialize(self):
        """Initialize the Lighter SDK clients."""
        logger.info(f"Initializing {SERVICE_NAME}...")
        self._init_complete = False

        if not LIGHTER_SDK_AVAILABLE:
            logger.error("Cannot initialize - Lighter SDK not installed")
            return False

        if not self._pub_key or not self._priv_key:
            logger.error("LIGHTER_PUB_KEY or LIGHTER_PRIV_KEY not configured")
            return False

        try:
            # Respect explicit LIGHTER_API_URL (used for VPN/proxy/tunnel egress).
            # Fallback to network default only when env is unset.
            base_url = str(LIGHTER_API_URL or "").strip()
            if not base_url:
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
            self._pubsub_initialized = True

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
            self._init_complete = True
            return True

        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            self._init_complete = False
            return False

    async def _gateway_status_payload(self) -> dict[str, Any]:
        now_ts = time.time()
        snapshot = await self._get_equity_snapshot_cached()
        go_nogo = await self._evaluate_go_no_go(now_ts=now_ts)
        reject_tax = go_nogo.get("reject_tax", {}) if isinstance(go_nogo.get("reject_tax"), dict) else {}
        if not reject_tax:
            reject_tax = await self._collect_reject_tax_metrics()
        balance_age = snapshot.get("balance_sync_age_sec")
        position_age = snapshot.get("position_check_age_sec")
        block_remaining = max(0.0, self._jurisdiction_block_until_ts - now_ts)
        failsafe_remaining = max(0.0, self._execution_failsafe_until_ts - now_ts)
        ready_reasons: list[str] = []

        if not self._init_complete:
            ready_reasons.append("initialization_incomplete")
        if self.account_index is None:
            ready_reasons.append("account_index_unresolved")
        if not self.market_info:
            ready_reasons.append("market_metadata_missing")
        if bool(snapshot.get("balance_sync_stale", False)):
            ready_reasons.append("balance_sync_stale")
        if bool(snapshot.get("position_check_stale", False)):
            ready_reasons.append("position_sync_stale")
        if self._execution_block_reason:
            ready_reasons.append("execution_blocked")
        if block_remaining > 0:
            ready_reasons.append("jurisdiction_block_active")
        if failsafe_remaining > 0:
            ready_reasons.append("execution_failsafe_active")

        ready = len(ready_reasons) == 0
        return {
            "service": SERVICE_NAME,
            "platform": PLATFORM.value,
            "ready": ready,
            "ready_reasons": ready_reasons,
            "running": bool(self.running),
            "initialized": bool(self._init_complete),
            "trading_enabled": bool(self._trading_enabled),
            "allow_live_trading": bool(self._allow_live_trading),
            "account_index": self.account_index,
            "market_count": len(self.market_info),
            "execution_block_reason": self._execution_block_reason or "",
            "jurisdiction_block_remaining_sec": round(block_remaining, 3),
            "execution_failsafe_remaining_sec": round(failsafe_remaining, 3),
            "execution_failsafe_reason": self._execution_failsafe_reason or "",
            "balance_sync_age_sec": balance_age,
            "position_check_age_sec": position_age,
            "last_balance_sync_error": self._last_balance_sync_error,
            "last_position_check_error": self._last_position_check_error,
            "go_no_go": go_nogo,
            "reject_tax": reject_tax,
            "timestamp": datetime.now(UTC).isoformat(),
        }

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

    async def _discover_account_index_by_api_key(self) -> int | None:
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
            from shared.gateway import start_gateway_server, stop_gateway_server
        except ImportError:
            from gateway import start_gateway_server, stop_gateway_server

        self._stop_gateway_server = stop_gateway_server
        self.command_queue = await start_gateway_server(status_provider=self._gateway_status_payload)

        if not await self.initialize():
            logger.error("Failed to initialize, exiting")
            return

        self.running = True
        self._cleanup_complete = False
        logger.info(f"Bot {SERVICE_NAME} is now running in HYBRID MODE")

        try:
            self._tasks = [
                asyncio.create_task(self._main_loop(), name="lighter_main_loop"),
                asyncio.create_task(self._gateway_loop(), name="lighter_gateway_loop"),
                asyncio.create_task(self._balance_sync_loop(), name="lighter_balance_loop"),
                asyncio.create_task(self._position_publish_loop(), name="lighter_position_loop"),
                asyncio.create_task(self._progress_verification_loop(), name="lighter_progress_loop"),
            ]
            await asyncio.gather(*self._tasks)

        except asyncio.CancelledError:
            logger.info("Bot stopped via cancellation")
        finally:
            await self._finalize_shutdown()
            self._tasks = []

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

            except TimeoutError:
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
    _COIN_ALIASES: dict[str, str] = {
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

    def _build_signal_from_gateway_command(self, command: dict[str, Any]) -> TradeSignal | None:
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

        current = asyncio.current_task()
        pending = [
            t for t in self._tasks
            if t is not None and t is not current and not t.done()
        ]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        await self._finalize_shutdown()

    async def _finalize_shutdown(self) -> None:
        """Idempotent final cleanup for network clients and gateway."""
        if self._cleanup_complete:
            return
        self._cleanup_complete = True
        await self._close_clients()
        if self._stop_gateway_server is not None:
            try:
                maybe = self._stop_gateway_server()
                if inspect.isawaitable(maybe):
                    await maybe
            except Exception as exc:
                logger.debug("Gateway stop failed: %s", exc)

    async def _sleep_or_stop(self, timeout_seconds: float) -> None:
        """Sleep with early wakeup when shutdown is requested."""
        if timeout_seconds <= 0:
            return
        try:
            await asyncio.wait_for(
                self._shutdown_event.wait(),
                timeout=float(timeout_seconds),
            )
        except TimeoutError:
            return

    async def _close_clients(self) -> None:
        """Best-effort close of all SDK/network clients to avoid aiohttp leaks."""
        logger.info("Running shutdown client cleanup...")

        async def _close_aiohttp_session(session: Any) -> None:
            if session is None or getattr(session, "closed", True):
                return
            owner_loop = getattr(session, "_loop", None)
            running_loop = None
            try:
                running_loop = asyncio.get_running_loop()
            except Exception:
                running_loop = None
            try:
                if owner_loop is not None and running_loop is not None and owner_loop is not running_loop:
                    if owner_loop.is_running():
                        fut = asyncio.run_coroutine_threadsafe(session.close(), owner_loop)
                        await asyncio.to_thread(fut.result, timeout=3)
                    else:
                        await session.close()
                else:
                    await session.close()
            except Exception as exc:
                logger.debug("aiohttp close failed: %s", exc)

        async def _close_maybe_async(obj: Any) -> None:
            close_fn = getattr(obj, "close", None)
            if callable(close_fn):
                try:
                    maybe = close_fn()
                    if inspect.isawaitable(maybe):
                        await maybe
                except Exception as exc:
                    logger.debug("Close failed for %s: %s", type(obj).__name__, exc)

        async def _close_embedded_sessions(obj: Any) -> None:
            if obj is None:
                return
            try:
                import aiohttp as _aio
            except Exception:
                _aio = None

            candidates: list[Any] = [obj]
            for attr in ("session", "_session", "client_session", "_client_session", "rest_client"):
                try:
                    candidate = getattr(obj, attr, None)
                    if candidate is not None:
                        candidates.append(candidate)
                except Exception:
                    pass

            for candidate in candidates:
                if candidate is None:
                    continue
                if _aio is not None and isinstance(candidate, _aio.ClientSession):
                    await _close_aiohttp_session(candidate)
                await _close_maybe_async(candidate)

        seen = set()
        targets = [
            self.client,
            self.account_api,
            self.transaction_api,
            self.order_api,
            self.signer_client,
        ]

        for obj in targets:
            if obj is None:
                continue
            api_client = getattr(obj, "api_client", None) or obj
            key = id(api_client)
            if key in seen:
                continue
            seen.add(key)

            await _close_maybe_async(api_client)
            await _close_embedded_sessions(api_client)
            await _close_embedded_sessions(obj)

            rest_client = getattr(api_client, "rest_client", None)
            pool_manager = getattr(rest_client, "pool_manager", None) if rest_client else None
            close_pool = getattr(pool_manager, "close", None) if pool_manager else None
            if callable(close_pool):
                try:
                    maybe = close_pool()
                    if inspect.isawaitable(maybe):
                        await maybe
                except Exception as exc:
                    logger.debug("REST pool close failed: %s", exc)

        # Close global Pub/Sub clients to avoid transport leaks at process shutdown.
        if self._pubsub_initialized:
            try:
                pubsub_client = get_pubsub_client()
                await pubsub_client.close()
            except Exception as exc:
                logger.debug("Pub/Sub close failed: %s", exc)
            finally:
                self._pubsub_initialized = False

        # Shared outbound HTTP client (Telegram + future integrations).
        try:
            if self._http_session is not None:
                await _close_maybe_async(self._http_session)
                self._http_session = None
        except Exception as exc:
            logger.debug("HTTP session close failed: %s", exc)

        # Last-chance sweep: close any leaked aiohttp sessions left by SDK internals.
        try:
            import gc as _gc

            import aiohttp as _aio

            leaked = 0
            for obj in _gc.get_objects():
                if isinstance(obj, _aio.ClientSession) and not obj.closed:
                    try:
                        await _close_aiohttp_session(obj)
                        leaked += 1
                    except Exception:
                        pass
            if leaked:
                logger.info("Closed %d leaked aiohttp sessions during shutdown", leaked)
            else:
                logger.info("Shutdown cleanup found no leaked aiohttp sessions")
        except Exception as exc:
            logger.debug("Leaked aiohttp sweep skipped: %s", exc)

    async def _main_loop(self):
        """Main trading loop."""
        loop_interval = float(self._position_check_interval_seconds)

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
            await self._sleep_or_stop(self._position_publish_interval_seconds)

    async def _handle_signal(self, signal_data: dict[str, Any]):
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

            reduce_only = bool(metadata.get("reduce_only", False))
            if signal.signal_type in {
                SignalType.EXIT,
                SignalType.SCALE_OUT,
                SignalType.TAKE_PROFIT,
                SignalType.STOP_LOSS,
            }:
                reduce_only = True
            entry_like = signal.signal_type in {SignalType.ENTRY, SignalType.SCALE_IN}

            if signal.quantity is None:
                if not (entry_like and not reduce_only and self._target_order_notional_usd > 0):
                    logger.warning(
                        f"Rejected signal without explicit quantity on {PLATFORM.value}: {signal.signal_id} {signal.symbol}"
                    )
                    return
                if signal.metadata is None:
                    signal.metadata = {}
                signal.metadata.setdefault("auto_quantity", "target_notional")

            allowed, reason = self._is_signal_allowed_by_policy(signal)
            if not allowed:
                logger.info(
                    "Policy filter on %s: signal=%s symbol=%s reason=%s",
                    PLATFORM.value,
                    signal.signal_id,
                    signal.symbol,
                    reason,
                )
                result = self._policy_noop_result(signal, reason=reason, symbol=signal.symbol)
                await self._record_execution_verification(signal, result, channel="signal")
                return

            if self._go_nogo_gate_enabled and entry_like and not reduce_only:
                go_nogo = await self._evaluate_go_no_go()
                if not go_nogo.get("go", False):
                    blocker_rows = go_nogo.get("reason_details") or go_nogo.get("reasons") or []
                    blocker_text = "; ".join(str(item) for item in blocker_rows[:2]).strip()
                    reason = f"go_no_go_block: {blocker_text or 'operator_no_go'}"
                    logger.warning(
                        "GO/NO-GO gate blocked entry on %s: signal=%s symbol=%s reason=%s",
                        PLATFORM.value,
                        signal.signal_id,
                        signal.symbol,
                        reason,
                    )
                    result = self._policy_noop_result(signal, reason=reason, symbol=signal.symbol)
                    if result.metadata is None:
                        result.metadata = {}
                    result.metadata["go_no_go"] = {
                        "label": str(go_nogo.get("label", "NO-GO")),
                        "source": str(go_nogo.get("source", "bot_policy")),
                        "reasons": list(blocker_rows[:4]),
                        "evaluated_at": go_nogo.get("evaluated_at"),
                    }
                    await self._record_execution_verification(signal, result, channel="signal")
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
        """Push a richer execution/rejection alert to Telegram."""
        if not self._telegram_bot_token or not self._telegram_chat_id:
            return

        side = str(getattr(signal, "side", "")).upper() or "BUY"
        symbol = self._normalize_coin_symbol(str(getattr(signal, "symbol", "")).upper())
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
        strategy, timeframe = self._signal_strategy_info(signal)
        metadata = signal.metadata or {}
        reasoning = self._compact_reasoning(metadata)

        position = self.positions.get(symbol)
        mark = self._to_float(getattr(position, "current_price", 0.0), 0.0) if position else 0.0
        upnl = self._to_float(getattr(position, "unrealized_pnl", 0.0), 0.0) if position else 0.0
        pnl_pct = self._to_float(getattr(position, "pnl_percent", 0.0), 0.0) if position else 0.0
        entry = 0.0
        if position:
            entry = self._to_float(getattr(position, "entry_price", 0.0), 0.0)
        if entry <= 0:
            entry = fill_price

        status_icon = "🟢" if ok else "🔴"
        status_text = "FILLED" if ok else "REJECTED"
        side_icon = "▲" if side in {"BUY", "LONG"} else "▼"

        lines = [
            f"{status_icon} <b>LIGHTER {status_text}</b>  {side_icon} <b>{html.escape(side)} {html.escape(symbol)}</b>",
            f"<b>Signal</b> <code>{html.escape(str(signal.signal_id or 'n/a'))}</code> · <b>src</b> {html.escape(channel)}",
        ]
        if strategy or timeframe:
            lines.append(
                f"<b>Strategy</b> {html.escape(strategy or 'n/a')} · <b>TF</b> {html.escape(timeframe or 'n/a')}"
            )

        qty_text = f"{qty:g}"
        if fill_qty > 0:
            lines.append(
                f"<b>Order</b> req {qty_text} · fill {fill_qty:g} @ <b>{fill_price:,.4f}</b>"
            )
        else:
            lines.append(f"<b>Order</b> qty {qty_text}")

        tp_v = self._to_float(tp, 0.0)
        sl_v = self._to_float(sl, 0.0)
        if tp_v > 0 or sl_v > 0:
            lines.append(
                f"<b>Risk</b> TP <code>{tp_v:,.4f}</code> · SL <code>{sl_v:,.4f}</code>"
            )
        if mark > 0:
            pnl_icon = "🟢" if upnl >= 0 else "🔻"
            lines.append(
                f"<b>Mark</b> {mark:,.4f} · <b>uPnL</b> {pnl_icon} {upnl:+.4f} ({pnl_pct:+.2f}%)"
            )
        cond, cond_detail = self._market_condition_for_symbol(symbol)
        if cond:
            lines.append(f"<b>Market</b> {html.escape(cond)} · {html.escape(cond_detail)}")
        if reasoning:
            lines.append(f"<b>Why</b> {html.escape(reasoning)}")
        if order_id:
            lines.append(f"<b>Order ID</b> <code>{html.escape(order_id)}</code>")
        if err:
            lines.append(f"<b>Error</b> {html.escape(err[:220])}")

        await self._send_telegram_message("\n".join(lines), parse_mode="HTML")

        if (
            ok
            and self._telegram_enable_charts
            and fill_qty > 0
            and (entry > 0 or fill_price > 0 or mark > 0)
        ):
            chart_path: Path | None = None
            try:
                chart_path = self._build_trade_chart_card(
                    symbol=symbol,
                    side=side,
                    entry_price=float(entry or fill_price or mark),
                    mark_price=float(mark or fill_price or entry),
                    tp_price=float(tp_v) if tp_v > 0 else None,
                    sl_price=float(sl_v) if sl_v > 0 else None,
                    signal_id=str(signal.signal_id or ""),
                )
                if chart_path is not None:
                    caption = (
                        f"<b>{html.escape(symbol)}</b> · {html.escape(side)}\n"
                        f"Entry <code>{float(entry or fill_price):,.4f}</code>"
                    )
                    await self._send_telegram_photo(chart_path, caption=caption, parse_mode="HTML")
            except Exception as exc:
                logger.debug("Trade chart send skipped: %s", exc)
            finally:
                if chart_path and chart_path.exists():
                    with contextlib.suppress(Exception):
                        chart_path.unlink(missing_ok=True)

    async def _send_telegram_message(
        self,
        text: str,
        *,
        parse_mode: str | None = None,
    ) -> None:
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
            if parse_mode:
                payload["parse_mode"] = parse_mode
            session = await self._get_http_session()
            if session is None:
                return
            async with session.post(url, json=payload, timeout=timeout) as response:
                if response.status >= 400:
                    body = await response.text()
                    logger.warning(
                        "Telegram alert failed (%s): %s",
                        response.status,
                        body[:160],
                    )
        except Exception as exc:
            logger.warning("Telegram alert error: %s", exc)

    async def _send_telegram_photo(
        self,
        image_path: Path,
        *,
        caption: str = "",
        parse_mode: str | None = None,
    ) -> None:
        if not self._telegram_bot_token or not self._telegram_chat_id or not image_path.exists():
            return

        try:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=10)
            url = f"https://api.telegram.org/bot{self._telegram_bot_token}/sendPhoto"
            data = aiohttp.FormData()
            data.add_field("chat_id", self._telegram_chat_id)
            if caption:
                data.add_field("caption", caption[:1024])
            if parse_mode:
                data.add_field("parse_mode", parse_mode)
            with open(image_path, "rb") as handle:
                data.add_field(
                    "photo",
                    handle,
                    filename=image_path.name,
                    content_type="image/png",
                )
                session = await self._get_http_session()
                if session is None:
                    return
                async with session.post(url, data=data, timeout=timeout) as response:
                    if response.status >= 400:
                        body = await response.text()
                        logger.warning(
                            "Telegram photo failed (%s): %s",
                            response.status,
                            body[:180],
                        )
        except Exception as exc:
            logger.warning("Telegram photo error: %s", exc)

    async def _get_http_session(self):
        try:
            import aiohttp
        except Exception:
            return None
        session = self._http_session
        if session is None or getattr(session, "closed", False):
            timeout = aiohttp.ClientTimeout(total=12)
            self._http_session = aiohttp.ClientSession(timeout=timeout)
            session = self._http_session
        return session

    def _record_price_point(self, symbol: str, price: float) -> None:
        px = self._to_float(price, 0.0)
        if px <= 0:
            return
        coin = self._normalize_coin_symbol(symbol)
        self._price_history[coin].append((time.time(), px))

    def _recent_prices(self, symbol: str) -> list[float]:
        coin = self._normalize_coin_symbol(symbol)
        points = list(self._price_history.get(coin, []))
        prices: list[float] = []
        for item in points:
            if isinstance(item, tuple) and len(item) >= 2:
                prices.append(self._to_float(item[1], 0.0))
            else:
                prices.append(self._to_float(item, 0.0))
        return [p for p in prices if p > 0]

    @staticmethod
    def _compact_reasoning(metadata: dict[str, Any]) -> str:
        if not isinstance(metadata, dict):
            return ""
        candidates: list[str] = []
        for key in (
            "reason",
            "message",
            "analysis",
            "market_condition",
            "thesis",
            "regime",
            "regime_score",
            "z_score",
            "origin",
        ):
            value = metadata.get(key)
            if value is None:
                continue
            if isinstance(value, (int, float)):
                candidates.append(f"{key}={value}")
            else:
                text = str(value).strip()
                if text:
                    candidates.append(text)
        joined = " | ".join(candidates)
        return joined[:280]

    @staticmethod
    def _position_opened_ts(position: Position) -> float:
        """Best-effort opened timestamp resolution for hold-time risk controls."""
        meta = position.metadata if isinstance(position.metadata, dict) else {}
        opened_raw = meta.get("opened_at")
        if isinstance(opened_raw, (int, float)):
            return float(opened_raw)
        if isinstance(opened_raw, str):
            try:
                return datetime.fromisoformat(opened_raw.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
        created = getattr(position, "created_at", None)
        if isinstance(created, datetime):
            try:
                return created.timestamp()
            except Exception:
                pass
        updated = getattr(position, "updated_at", None)
        if isinstance(updated, datetime):
            try:
                return updated.timestamp()
            except Exception:
                pass
        return 0.0

    def _market_stats_for_symbol(self, symbol: str) -> dict[str, float]:
        prices = self._recent_prices(symbol)
        if len(prices) < 6:
            return {"drift_pct": 0.0, "vol_pct": 0.0, "samples": float(len(prices))}
        first = prices[0]
        last = prices[-1]
        if first <= 0 or last <= 0:
            return {"drift_pct": 0.0, "vol_pct": 0.0, "samples": float(len(prices))}
        drift_pct = ((last - first) / first) * 100.0
        returns: list[float] = []
        for idx in range(1, len(prices)):
            prev = prices[idx - 1]
            cur = prices[idx]
            if prev > 0:
                returns.append((cur - prev) / prev)
        vol_pct = 0.0
        if returns:
            mean = sum(returns) / len(returns)
            var = sum((r - mean) ** 2 for r in returns) / max(len(returns), 1)
            vol_pct = (var ** 0.5) * 100.0
        return {
            "drift_pct": float(drift_pct),
            "vol_pct": float(vol_pct),
            "samples": float(len(prices)),
        }

    def _market_condition_for_symbol(self, symbol: str) -> tuple[str, str]:
        stats = self._market_stats_for_symbol(symbol)
        drift_pct = self._to_float(stats.get("drift_pct"), 0.0)
        vol_pct = self._to_float(stats.get("vol_pct"), 0.0)
        samples = int(self._to_float(stats.get("samples"), 0.0))
        if samples < 6:
            return "insufficient data", "warming price history"
        if abs(drift_pct) < 0.2 and vol_pct < 0.25:
            regime = "flat/range"
        elif drift_pct > 0:
            regime = "uptrend"
        else:
            regime = "downtrend"
        detail = f"drift {drift_pct:+.2f}% · vol {vol_pct:.2f}%"
        return regime, detail

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))

    def _extract_signal_source(self, signal: TradeSignal) -> str:
        metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
        source = str(
            metadata.get("source")
            or metadata.get("origin")
            or getattr(signal, "source", "")
            or ""
        ).strip().lower()
        return source or "unknown"

    def _default_expected_entry_notional_usd(self) -> float:
        margin = max(0.0, float(self._target_order_notional_usd or 0.0))
        if margin <= 0 and self._min_entry_notional_usd > 0:
            margin = float(self._min_entry_notional_usd)
        if margin <= 0:
            margin = 1.0
        if self._use_leverage_for_notional:
            leverage = max(1.0, float(self._target_order_leverage or 1.0))
            margin *= leverage
        return float(max(0.01, margin))

    def _estimate_roundtrip_cost_pct(
        self,
        *,
        notional_usd: float,
        vol_pct: float,
    ) -> dict[str, float]:
        taker_ratio = self._clamp(float(self._ev_expected_taker_ratio), 0.0, 1.0)
        weighted_fee_bps = (
            (taker_ratio * float(self._ev_taker_fee_bps))
            + ((1.0 - taker_ratio) * float(self._ev_maker_fee_bps))
        )
        fee_pct = (weighted_fee_bps / 100.0) * 2.0

        ref_notional = max(0.01, float(self._ev_slippage_notional_ref_usd))
        size_ratio = max(0.0, float(notional_usd) / ref_notional)
        # log2(size_ratio+1) keeps growth bounded while still penalizing larger clips.
        size_penalty = math.log(size_ratio + 1.0, 2.0)
        slippage_bps_one_way = (
            float(self._ev_slippage_base_bps)
            + (max(0.0, float(vol_pct)) * float(self._ev_slippage_vol_mult_bps))
            + (size_penalty * float(self._ev_slippage_notional_mult_bps))
        )
        slippage_pct = (slippage_bps_one_way / 100.0) * 2.0
        total_friction_pct = fee_pct + slippage_pct
        return {
            "fee_pct": round(float(fee_pct), 6),
            "slippage_pct": round(float(slippage_pct), 6),
            "total_friction_pct": round(float(total_friction_pct), 6),
            "weighted_fee_bps": round(float(weighted_fee_bps), 6),
            "slippage_bps_one_way": round(float(slippage_bps_one_way), 6),
            "size_ratio": round(float(size_ratio), 6),
        }

    def _dynamic_entry_size_multiplier(
        self,
        *,
        signal: TradeSignal,
        coin: str,
        is_buy: bool,
        reference_price: float,
        portfolio_notional_usd: float,
        drawdown_pct: float,
    ) -> tuple[float, dict[str, float]]:
        """
        First-principles dynamic sizing:
        - confidence/EV increase size
        - high volatility, deep drawdown, high inventory reduce size
        """
        confidence = self._clamp(self._to_float(getattr(signal, "confidence", 0.0), 0.0), 0.0, 1.0)
        stats = self._market_stats_for_symbol(coin)
        vol_pct = max(0.0, self._to_float(stats.get("vol_pct"), 0.0))
        expected_notional_usd = self._default_expected_entry_notional_usd()
        ev_pct = self._estimate_signal_ev_pct(
            signal,
            coin=coin,
            is_buy=is_buy,
            reference_price=reference_price,
            expected_notional_usd=expected_notional_usd,
        )
        cost_model = self._estimate_roundtrip_cost_pct(
            notional_usd=expected_notional_usd,
            vol_pct=vol_pct,
        )

        ev_score = self._clamp((ev_pct + 1.0) / 3.0, 0.0, 1.0)
        vol_score = self._clamp(1.0 - (vol_pct / 0.60), 0.0, 1.0)

        cap_ref = max(0.0001, float(self._max_portfolio_notional_usd or self._max_position_notional_usd or 0.0))
        inventory_ratio = self._clamp(float(portfolio_notional_usd) / cap_ref, 0.0, 1.5) if cap_ref > 0 else 0.0
        inventory_score = self._clamp(1.0 - inventory_ratio, 0.0, 1.0)

        dd_ref = max(1.0, float(self._max_drawdown_alert_pct or 5.0))
        drawdown_ratio = self._clamp(abs(min(0.0, float(drawdown_pct))) / dd_ref, 0.0, 1.0)
        drawdown_score = self._clamp(1.0 - drawdown_ratio, 0.0, 1.0)

        composite = (
            (0.30 * confidence)
            + (0.25 * ev_score)
            + (0.20 * vol_score)
            + (0.15 * inventory_score)
            + (0.10 * drawdown_score)
        )
        multiplier = self._dynamic_size_min_mult + (
            (self._dynamic_size_max_mult - self._dynamic_size_min_mult) * self._clamp(composite, 0.0, 1.0)
        )
        multiplier = self._clamp(multiplier, self._dynamic_size_min_mult, self._dynamic_size_max_mult)

        factors = {
            "confidence": round(confidence, 4),
            "ev_pct": round(ev_pct, 4),
            "vol_pct": round(vol_pct, 4),
            "portfolio_notional_usd": round(float(portfolio_notional_usd), 6),
            "drawdown_pct": round(float(drawdown_pct), 6),
            "inventory_ratio": round(float(inventory_ratio), 6),
            "expected_notional_usd": round(float(expected_notional_usd), 6),
            "fee_pct": round(self._to_float(cost_model.get("fee_pct"), 0.0), 6),
            "slippage_pct": round(self._to_float(cost_model.get("slippage_pct"), 0.0), 6),
            "friction_pct": round(self._to_float(cost_model.get("total_friction_pct"), 0.0), 6),
            "composite": round(float(composite), 6),
            "multiplier": round(float(multiplier), 6),
        }
        return float(multiplier), factors

    def _project_entry_notional(
        self,
        *,
        coin: str,
        is_buy: bool,
        requested_notional: float,
        mark_price: float,
        portfolio_notional_now: float,
    ) -> dict[str, float]:
        current = self.positions.get(coin)
        current_qty = float(getattr(current, "quantity", 0.0) or 0.0) if current else 0.0
        current_notional = abs(current_qty * float(mark_price)) if mark_price > 0 else 0.0
        current_side = getattr(current, "side", None) if current else None
        same_direction = (
            (is_buy and current_side in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG"))
            or ((not is_buy) and current_side in (TradeSide.SELL, TradeSide.SHORT, "SELL", "SHORT"))
        )
        if not current or current_qty <= 0:
            projected_symbol_notional = requested_notional
        elif same_direction:
            projected_symbol_notional = current_notional + requested_notional
        else:
            projected_symbol_notional = abs(current_notional - requested_notional)

        projected_portfolio_notional = max(
            0.0,
            float(portfolio_notional_now) - current_notional + projected_symbol_notional,
        )
        return {
            "current_symbol_notional": float(current_notional),
            "projected_symbol_notional": float(projected_symbol_notional),
            "projected_portfolio_notional": float(projected_portfolio_notional),
            "same_direction": 1.0 if same_direction else 0.0,
        }

    def _estimate_signal_ev_pct(
        self,
        signal: TradeSignal,
        *,
        coin: str,
        is_buy: bool,
        reference_price: float,
        expected_notional_usd: float | None = None,
    ) -> float:
        """
        Expected-value estimate (percent) using:
        - confidence + regime alignment -> win probability
        - TP/SL geometry -> payoff profile
        - fee/slippage friction -> net EV after execution costs
        """
        confidence = self._to_float(getattr(signal, "confidence", 0.0), 0.0)
        confidence = min(1.0, max(0.0, confidence))

        tp_pct = max(0.01, self._default_take_profit_pct)
        sl_pct = max(0.01, self._default_stop_loss_pct)
        if reference_price > 0:
            tp_val = self._to_float(getattr(signal, "take_profit", None), 0.0)
            sl_val = self._to_float(getattr(signal, "stop_loss", None), 0.0)
            if tp_val > 0:
                tp_pct = abs((tp_val - reference_price) / reference_price) * 100.0
            if sl_val > 0:
                sl_pct = abs((sl_val - reference_price) / reference_price) * 100.0

        stats = self._market_stats_for_symbol(coin)
        drift_pct = self._to_float(stats.get("drift_pct"), 0.0)
        vol_pct = self._to_float(stats.get("vol_pct"), 0.0)
        drift_dir = 1.0 if drift_pct > 0 else -1.0 if drift_pct < 0 else 0.0
        side_dir = 1.0 if is_buy else -1.0
        alignment = drift_dir * side_dir

        base_win_prob = 0.45 + confidence * 0.35
        win_prob = base_win_prob + (0.10 * alignment) - min(0.10, vol_pct / 8.0)
        win_prob = min(0.92, max(0.08, win_prob))

        notional_usd = self._to_float(expected_notional_usd, 0.0)
        if notional_usd <= 0 and reference_price > 0:
            qty = self._to_float(getattr(signal, "quantity", 0.0), 0.0)
            if qty > 0:
                notional_usd = abs(qty * float(reference_price))
        if notional_usd <= 0:
            notional_usd = self._default_expected_entry_notional_usd()
        cost = self._estimate_roundtrip_cost_pct(
            notional_usd=notional_usd,
            vol_pct=vol_pct,
        )
        friction_pct = self._to_float(cost.get("total_friction_pct"), 0.0)

        ev_pct = (win_prob * tp_pct) - ((1.0 - win_prob) * sl_pct) - friction_pct
        return round(ev_pct, 4)

    def _estimate_position_ev_pct(self, symbol: str, position: Position) -> float:
        meta = position.metadata if isinstance(position.metadata, dict) else {}
        cached = self._to_float(meta.get("ev_score_pct"), 0.0)
        if cached != 0.0:
            return float(cached)

        entry = self._to_float(getattr(position, "entry_price", 0.0), 0.0)
        if entry <= 0:
            entry = self._to_float(getattr(position, "current_price", 0.0), 0.0)
        if entry <= 0:
            return 0.0

        side = getattr(position, "side", None)
        is_buy = side in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG")
        pseudo_signal = TradeSignal(
            signal_id=f"ev-{symbol}",
            symbol=symbol,
            side=TradeSide.BUY if is_buy else TradeSide.SELL,
            signal_type=SignalType.ENTRY,
            confidence=self._to_float(meta.get("confidence"), 0.55),
            source="position-ev",
            take_profit=self._to_float(getattr(position, "take_profit", 0.0), 0.0) or None,
            stop_loss=self._to_float(getattr(position, "stop_loss", 0.0), 0.0) or None,
            quantity=self._to_float(getattr(position, "quantity", 0.0), 0.0),
            metadata=meta,
        )
        return self._estimate_signal_ev_pct(
            pseudo_signal,
            coin=symbol,
            is_buy=is_buy,
            reference_price=entry,
            expected_notional_usd=abs(self._to_float(getattr(position, "quantity", 0.0), 0.0) * entry),
        )

    def _build_trade_chart_card(
        self,
        *,
        symbol: str,
        side: str,
        entry_price: float,
        mark_price: float,
        tp_price: float | None,
        sl_price: float | None,
        signal_id: str,
    ) -> Path | None:
        try:
            from PIL import Image, ImageDraw, ImageFont
        except Exception:
            return None

        series = self._recent_prices(symbol)
        anchor = self._to_float(mark_price, 0.0) or self._to_float(entry_price, 0.0)
        if len(series) < 24 and anchor > 0:
            start = self._to_float(entry_price, anchor) or anchor
            steps = 32
            synthetic: list[float] = []
            for i in range(steps):
                t = i / max(steps - 1, 1)
                synthetic.append(start + (anchor - start) * t)
            series = synthetic
        if len(series) < 2:
            return None

        width, height = 1200, 675
        chart_left, chart_top, chart_right, chart_bottom = 80, 180, 1120, 590
        chart_w = chart_right - chart_left
        chart_h = chart_bottom - chart_top

        img = Image.new("RGB", (width, height), "#0b0d11")
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, width, 120), fill="#11151d")
        draw.rectangle((chart_left, chart_top, chart_right, chart_bottom), fill="#0f131a")

        try:
            font_title = ImageFont.truetype("Arial Bold.ttf", 58)
            font_sub = ImageFont.truetype("Arial.ttf", 36)
            font_small = ImageFont.truetype("Arial.ttf", 24)
        except Exception:
            font_title = ImageFont.load_default()
            font_sub = ImageFont.load_default()
            font_small = ImageFont.load_default()

        side_up = str(side).upper()
        is_long = side_up in {"BUY", "LONG"}
        side_color = "#23c6a6" if is_long else "#ff5b6d"

        last_price = series[-1]
        first_price = series[0]
        delta = last_price - first_price
        delta_pct = ((delta / first_price) * 100.0) if first_price > 0 else 0.0

        draw.text((60, 32), f"{symbol}/USDT", fill="#f5f7fa", font=font_title)
        draw.text((60, 96), "LIGHTER · SAPPHIRE", fill="#8d97a5", font=font_sub)
        draw.text((820, 52), f"{last_price:,.4f} USDT", fill="#f5f7fa", font=font_sub)
        draw.text(
            (820, 96),
            f"{delta:+.4f}  ({delta_pct:+.2f}%)",
            fill=side_color if delta >= 0 else "#ff5b6d",
            font=font_sub,
        )

        min_y = min(series)
        max_y = max(series)
        line_levels = [x for x in [entry_price, mark_price, tp_price, sl_price] if self._to_float(x, 0.0) > 0]
        if line_levels:
            min_y = min(min_y, min(line_levels))
            max_y = max(max_y, max(line_levels))
        if max_y <= min_y:
            max_y = min_y + 1.0
        pad = (max_y - min_y) * 0.1
        y_min = min_y - pad
        y_max = max_y + pad

        def y_of(price: float) -> int:
            if y_max <= y_min:
                return chart_bottom
            ratio = (price - y_min) / (y_max - y_min)
            return int(chart_bottom - ratio * chart_h)

        for i in range(6):
            y = chart_top + int((chart_h / 5) * i)
            draw.line((chart_left, y, chart_right, y), fill="#1f2530", width=1)

        pts = []
        total = len(series)
        for i, price in enumerate(series):
            x = chart_left + int((i / max(total - 1, 1)) * chart_w)
            y = y_of(price)
            pts.append((x, y))
        if len(pts) >= 2:
            draw.line(pts, fill=side_color, width=4)
            draw.ellipse((pts[-1][0] - 6, pts[-1][1] - 6, pts[-1][0] + 6, pts[-1][1] + 6), fill=side_color)

        def dashed_hline(price: float, color: str, label: str) -> None:
            if self._to_float(price, 0.0) <= 0:
                return
            y = y_of(float(price))
            x = chart_left
            while x < chart_right:
                draw.line((x, y, min(x + 18, chart_right), y), fill=color, width=2)
                x += 30
            text = f"{label} {price:,.4f}"
            tw = int(draw.textlength(text, font=font_small))
            tx = max(chart_left + 10, chart_right - tw - 18)
            draw.rectangle((tx - 8, y - 17, tx + tw + 8, y + 10), fill="#0a0f15")
            draw.text((tx, y - 16), text, fill=color, font=font_small)

        dashed_hline(entry_price, "#f5f7fa", "ENTRY")
        dashed_hline(mark_price, side_color, "MARK")
        if tp_price:
            dashed_hline(float(tp_price), "#1ddf87", "TP")
        if sl_price:
            dashed_hline(float(sl_price), "#ff5b6d", "SL")

        draw.text(
            (60, 618),
            f"Signal {signal_id[:18]}{'…' if len(signal_id) > 18 else ''}  ·  {side_up}",
            fill="#7f8a98",
            font=font_small,
        )
        draw.text((940, 618), "Sapphire x Lighter", fill="#7f8a98", font=font_small)

        out_dir = Path(tempfile.gettempdir()) / "sapphire_telegram_charts"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"lighter_{symbol}_{int(time.time() * 1000)}.png"
        img.save(out_path, format="PNG")
        return out_path

    async def _maybe_send_portfolio_digest(self, snapshot: dict[str, Any]) -> None:
        if not self._telegram_bot_token or not self._telegram_chat_id:
            return
        now_ts = time.time()
        positions_count = int(snapshot.get("positions_count", 0) or 0)
        interval = self._telegram_digest_seconds if positions_count > 0 else self._telegram_digest_flat_seconds
        if (now_ts - self._last_telegram_digest_ts) < interval:
            return
        self._last_telegram_digest_ts = now_ts
        await self._send_portfolio_digest(snapshot)

    @staticmethod
    def _to_timestamp(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, datetime):
            try:
                return float(value.replace(tzinfo=UTC).timestamp() if value.tzinfo is None else value.timestamp())
            except Exception:
                return 0.0
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return 0.0
            try:
                dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                return float(dt.timestamp())
            except Exception:
                return 0.0
        return 0.0

    @staticmethod
    def _rollup_reject_tax_buckets(rows: list[dict[str, Any]]) -> dict[str, Any]:
        def _bucket_key(value: Any) -> str:
            text = str(value or "").strip().lower()
            return text or "unknown"

        def _new_bucket() -> dict[str, int]:
            return {
                "total": 0,
                "reject_skip": 0,
                "filled_success": 0,
                "hard_failed": 0,
            }

        by_source: dict[str, dict[str, int]] = defaultdict(_new_bucket)
        by_strategy: dict[str, dict[str, int]] = defaultdict(_new_bucket)
        by_timeframe: dict[str, dict[str, int]] = defaultdict(_new_bucket)
        reason_counter: dict[str, int] = defaultdict(int)

        total = 0
        reject_skip = 0
        filled_success = 0
        hard_failed = 0
        accepted_no_fill = 0
        policy_reject = 0
        policy_noop = 0
        noop = 0

        for row in rows:
            total += 1
            outcome = _bucket_key(row.get("outcome"))
            source = _bucket_key(row.get("signal_source") or row.get("source") or row.get("channel"))
            strategy = _bucket_key(row.get("strategy"))
            timeframe = _bucket_key(row.get("timeframe"))
            reason = str(
                row.get("policy_reason")
                or row.get("noop_reason")
                or row.get("error_message")
                or ""
            ).strip().lower()
            if len(reason) > 140:
                reason = reason[:137] + "..."

            reject_like = outcome in {"policy_noop", "policy_reject", "noop"}
            hard_fail_like = outcome == "hard_failed"
            fill_like = outcome == "filled_success"

            if outcome == "policy_noop":
                policy_noop += 1
            elif outcome == "policy_reject":
                policy_reject += 1
            elif outcome == "noop":
                noop += 1
            elif outcome == "accepted_no_fill":
                accepted_no_fill += 1

            if reject_like:
                reject_skip += 1
            if hard_fail_like:
                hard_failed += 1
            if fill_like:
                filled_success += 1

            for bucket in (by_source[source], by_strategy[strategy], by_timeframe[timeframe]):
                bucket["total"] += 1
                if reject_like:
                    bucket["reject_skip"] += 1
                if fill_like:
                    bucket["filled_success"] += 1
                if hard_fail_like:
                    bucket["hard_failed"] += 1

            if reject_like and reason:
                reason_counter[reason] += 1

        def _bucket_rows(src: dict[str, dict[str, int]]) -> list[dict[str, Any]]:
            out: list[dict[str, Any]] = []
            for key, bucket in src.items():
                b_total = max(1, int(bucket["total"]))
                out.append(
                    {
                        "key": key,
                        "total": int(bucket["total"]),
                        "reject_skip": int(bucket["reject_skip"]),
                        "filled_success": int(bucket["filled_success"]),
                        "hard_failed": int(bucket["hard_failed"]),
                        "reject_tax_pct": round((float(bucket["reject_skip"]) / b_total) * 100.0, 2),
                    }
                )
            out.sort(key=lambda item: (item["reject_skip"], item["total"]), reverse=True)
            return out[:6]

        total_safe = max(1, total)
        return {
            "sample_size": int(total),
            "reject_skip_count": int(reject_skip),
            "reject_tax_pct": round((float(reject_skip) / total_safe) * 100.0, 2),
            "hard_failed_count": int(hard_failed),
            "hard_fail_pct": round((float(hard_failed) / total_safe) * 100.0, 2),
            "filled_success_count": int(filled_success),
            "accepted_no_fill_count": int(accepted_no_fill),
            "policy_noop_count": int(policy_noop),
            "policy_reject_count": int(policy_reject),
            "noop_count": int(noop),
            "by_source": _bucket_rows(by_source),
            "by_strategy": _bucket_rows(by_strategy),
            "by_timeframe": _bucket_rows(by_timeframe),
            "top_reasons": [
                {"reason": reason, "count": count}
                for reason, count in sorted(
                    reason_counter.items(),
                    key=lambda item: item[1],
                    reverse=True,
                )[:6]
            ],
        }

    async def _collect_reject_tax_metrics(
        self,
        *,
        force_refresh: bool = False,
        window_hours: float | None = None,
    ) -> dict[str, Any]:
        now_ts = time.time()
        requested_window = (
            float(window_hours)
            if window_hours is not None
            else float(self._reject_tax_window_hours)
        )
        requested_window = max(0.25, requested_window)
        window_key = f"{requested_window:.2f}"
        last_fetch = float(self._last_reject_tax_fetch_by_window.get(window_key, 0.0) or 0.0)
        cached_window = self._cached_reject_tax_window_metrics.get(window_key) or {}
        if (
            not force_refresh
            and cached_window
            and (now_ts - last_fetch) < self._reject_tax_cache_ttl_seconds
        ):
            return dict(cached_window)

        since_ts = now_ts - (requested_window * 3600.0)
        rows: list[dict[str, Any]] = []

        if self._db is not None:
            try:
                from google.cloud import firestore as _fs
                from google.cloud.firestore_v1.base_query import FieldFilter

                query = (
                    self._db.collection("execution_verifications")
                    .where(filter=FieldFilter("platform", "==", PLATFORM.value))
                    .where(filter=FieldFilter("recorded_at", ">=", datetime.fromtimestamp(since_ts, tz=UTC)))
                    .order_by("recorded_at", direction=_fs.Query.DESCENDING)
                    .limit(1500)
                )
                async for doc in query.stream():
                    rows.append(doc.to_dict() or {})
            except Exception as exc:
                logger.debug("Reject-tax indexed query fallback: %s", exc)
                try:
                    from google.cloud import firestore as _fs

                    query = (
                        self._db.collection("execution_verifications")
                        .order_by("recorded_at", direction=_fs.Query.DESCENDING)
                        .limit(2200)
                    )
                    async for doc in query.stream():
                        row = doc.to_dict() or {}
                        if str(row.get("platform", "")).strip().lower() != PLATFORM.value:
                            continue
                        ts = self._to_timestamp(row.get("recorded_at") or row.get("timestamp"))
                        if ts < since_ts:
                            continue
                        rows.append(row)
                except Exception as fallback_exc:
                    logger.debug("Reject-tax Firestore fallback failed: %s", fallback_exc)

        if not rows and self._recent_execution_outcomes:
            for row in list(self._recent_execution_outcomes):
                ts = self._to_timestamp(row.get("recorded_at") or row.get("timestamp"))
                if ts >= since_ts:
                    rows.append(dict(row))

        rolled = self._rollup_reject_tax_buckets(rows)
        rolled["window_hours"] = round(requested_window, 2)
        rolled["computed_at"] = datetime.now(UTC).isoformat()
        rolled["alert_threshold_pct"] = round(float(self._reject_tax_alert_pct), 2)
        rolled["alert"] = (
            bool(rolled.get("sample_size", 0) >= self._go_nogo_min_sample_size)
            and float(rolled.get("reject_tax_pct", 0.0)) >= float(self._reject_tax_alert_pct)
        )

        self._cached_reject_tax_window_metrics[window_key] = dict(rolled)
        self._last_reject_tax_fetch_by_window[window_key] = now_ts
        if abs(requested_window - float(self._reject_tax_window_hours)) < 1e-6:
            self._cached_reject_tax_metrics = dict(rolled)
            self._last_reject_tax_fetch_ts = now_ts
        return dict(rolled)

    async def _collect_reject_tax_deltas(self, *, force_refresh: bool = False) -> dict[str, Any]:
        windows = [1.0, 6.0, 24.0, float(self._reject_tax_window_hours)]
        uniq_windows: list[float] = []
        for value in windows:
            if value not in uniq_windows:
                uniq_windows.append(value)
        result: dict[str, Any] = {}
        for value in uniq_windows:
            key = f"{int(value)}h" if abs(value - int(value)) < 1e-6 else f"{value:.2f}h"
            metrics = await self._collect_reject_tax_metrics(
                force_refresh=force_refresh,
                window_hours=value,
            )
            result[key] = {
                "window_hours": float(metrics.get("window_hours", value) or value),
                "sample_size": int(metrics.get("sample_size", 0) or 0),
                "reject_tax_pct": self._to_float(metrics.get("reject_tax_pct"), 0.0),
                "hard_fail_pct": self._to_float(metrics.get("hard_fail_pct"), 0.0),
                "filled_success_pct": self._to_float(metrics.get("filled_success_pct"), 0.0),
                "reject_skip_count": int(metrics.get("reject_skip_count", 0) or 0),
                "hard_failed_count": int(metrics.get("hard_failed_count", 0) or 0),
            }
        return result

    def _build_go_no_go_assessment(
        self,
        *,
        snapshot: dict[str, Any],
        reject_tax: dict[str, Any],
        now_ts: float | None = None,
    ) -> dict[str, Any]:
        ts = float(now_ts if now_ts is not None else time.time())
        reasons: list[str] = []
        reason_details: list[str] = []

        if not self._trading_enabled:
            reasons.append("trading_disabled")
            reason_details.append("trading_disabled")
        if self._trading_mode == "live" and not self._allow_live_trading:
            reasons.append("live_trading_not_allowed")
            reason_details.append("live_trading_not_allowed")
        if bool(snapshot.get("balance_sync_stale")):
            reasons.append("balance_sync_stale")
            reason_details.append(
                f"balance_sync_stale age={self._to_float(snapshot.get('balance_sync_age_sec'), 0.0):.0f}s"
            )
        if bool(snapshot.get("position_check_stale")):
            reasons.append("position_sync_stale")
            reason_details.append(
                f"position_sync_stale age={self._to_float(snapshot.get('position_check_age_sec'), 0.0):.0f}s"
            )
        if self._execution_block_reason:
            reasons.append("execution_blocked")
            reason_details.append(
                f"execution_blocked: {str(self._execution_block_reason).strip()[:100]}"
            )
        if max(0.0, self._execution_failsafe_until_ts - ts) > 0:
            reasons.append("execution_failsafe_active")
            reason_details.append(
                f"execution_failsafe_active {max(0.0, self._execution_failsafe_until_ts - ts):.0f}s"
            )
        if max(0.0, self._jurisdiction_block_until_ts - ts) > 0:
            reasons.append("jurisdiction_block_active")
            reason_details.append(
                f"jurisdiction_block_active {max(0.0, self._jurisdiction_block_until_ts - ts):.0f}s"
            )
        if bool(snapshot.get("hard_risk_blocked")):
            reasons.append("hard_risk_kernel_hold")
            reason_details.append(
                f"hard_risk_kernel_hold: {str(snapshot.get('hard_risk_block_reason') or 'risk limit breached')[:100]}"
            )

        sample_size = int(reject_tax.get("sample_size", 0) or 0)
        reject_tax_pct = self._to_float(reject_tax.get("reject_tax_pct"), 0.0)
        hard_fail_pct = self._to_float(reject_tax.get("hard_fail_pct"), 0.0)
        if sample_size >= self._go_nogo_min_sample_size:
            if reject_tax_pct > self._go_nogo_max_reject_tax_pct:
                reasons.append(
                    f"reject_tax {reject_tax_pct:.1f}% > {self._go_nogo_max_reject_tax_pct:.1f}%"
                )
                reason_details.append(
                    f"reject_tax {reject_tax_pct:.1f}% > {self._go_nogo_max_reject_tax_pct:.1f}% (n={sample_size})"
                )
            if hard_fail_pct > self._go_nogo_max_hard_fail_pct:
                reasons.append(
                    f"hard_fail_pct {hard_fail_pct:.1f}% > {self._go_nogo_max_hard_fail_pct:.1f}%"
                )
                reason_details.append(
                    f"hard_fail_pct {hard_fail_pct:.1f}% > {self._go_nogo_max_hard_fail_pct:.1f}% (n={sample_size})"
                )

        go = len(reasons) == 0
        return {
            "go": bool(go),
            "label": "GO" if go else "NO-GO",
            "source": "bot_policy",
            "reasons": reasons,
            "reason_details": reason_details,
            "sample_size": sample_size,
            "reject_tax_pct": round(reject_tax_pct, 2),
            "hard_fail_pct": round(hard_fail_pct, 2),
            "evaluated_at": datetime.now(UTC).isoformat(),
            "thresholds": {
                "max_reject_tax_pct": round(float(self._go_nogo_max_reject_tax_pct), 2),
                "max_hard_fail_pct": round(float(self._go_nogo_max_hard_fail_pct), 2),
                "min_sample_size": int(self._go_nogo_min_sample_size),
            },
        }

    async def _get_equity_snapshot_cached(self, *, force_refresh: bool = False) -> dict[str, Any]:
        now_ts = time.time()
        if (
            not force_refresh
            and self._cached_equity_snapshot
            and (now_ts - self._last_equity_snapshot_ts) < self._equity_snapshot_cache_ttl_seconds
        ):
            return dict(self._cached_equity_snapshot)
        snapshot = await self._estimate_equity_snapshot()
        self._cached_equity_snapshot = dict(snapshot)
        self._last_equity_snapshot_ts = now_ts
        return dict(snapshot)

    async def _fetch_platform_decision(self, *, force_refresh: bool = False) -> dict[str, Any]:
        now_ts = time.time()
        if (
            not force_refresh
            and self._cached_platform_decision
            and (now_ts - self._last_platform_decision_fetch_ts) < self._platform_decision_cache_ttl_seconds
        ):
            return dict(self._cached_platform_decision)
        if not self._platform_decision_url:
            return {}

        def _request() -> dict[str, Any]:
            resp = requests.get(
                self._platform_decision_url,
                timeout=float(self._platform_decision_timeout_seconds),
            )
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict):
                return {}
            decision = payload.get("decision", {}) if isinstance(payload.get("decision"), dict) else {}
            assessment = payload.get("assessment", {}) if isinstance(payload.get("assessment"), dict) else {}
            reasons = decision.get("reasons", []) if isinstance(decision.get("reasons"), list) else []
            if not reasons and isinstance(assessment.get("reasons"), list):
                reasons = assessment.get("reasons", [])
            return {
                "go": bool(decision.get("go", assessment.get("go", False))),
                "label": str(decision.get("label", assessment.get("label", "NO-GO"))).upper(),
                "source": str(decision.get("source", "platform_strategy_ops")),
                "reasons": [str(item) for item in reasons[:6] if str(item).strip()],
                "diverged": bool(decision.get("diverged", False)),
                "timestamp": payload.get("timestamp"),
            }

        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(None, _request)
            if data:
                self._cached_platform_decision = dict(data)
                self._last_platform_decision_fetch_ts = now_ts
            return dict(data)
        except Exception as exc:
            logger.debug("Platform decision fetch error: %s", exc)
            return {}

    async def _evaluate_go_no_go(
        self,
        *,
        force_refresh: bool = False,
        now_ts: float | None = None,
    ) -> dict[str, Any]:
        ts = float(now_ts if now_ts is not None else time.time())
        if (
            not force_refresh
            and self._cached_go_no_go
            and (ts - self._last_go_no_go_eval_ts) < self._go_nogo_cache_ttl_seconds
        ):
            return dict(self._cached_go_no_go)

        snapshot = await self._get_equity_snapshot_cached(force_refresh=force_refresh)
        reject_tax = await self._collect_reject_tax_metrics(force_refresh=force_refresh)
        go_nogo = self._build_go_no_go_assessment(
            snapshot=snapshot,
            reject_tax=reject_tax,
            now_ts=ts,
        )
        if self._platform_decision_gate_enabled:
            platform_decision = await self._fetch_platform_decision(force_refresh=force_refresh)
            if platform_decision:
                go_nogo["platform_decision"] = platform_decision
                if not platform_decision.get("go", True):
                    platform_reasons = platform_decision.get("reasons") or []
                    if platform_reasons:
                        reason_text = f"platform_no_go: {platform_reasons[0]}"
                    else:
                        reason_text = "platform_no_go"
                    reasons = go_nogo.get("reasons", [])
                    details = go_nogo.get("reason_details", [])
                    if reason_text not in reasons:
                        reasons.append(reason_text)
                    if reason_text not in details:
                        details.append(reason_text)
                    go_nogo["reasons"] = reasons
                    go_nogo["reason_details"] = details
                    go_nogo["go"] = False
                    go_nogo["label"] = "NO-GO"
                    go_nogo["source"] = "bot_policy+platform_decision"
        go_nogo["reject_tax"] = reject_tax
        go_nogo["deltas"] = await self._collect_reject_tax_deltas(force_refresh=force_refresh)
        self._cached_go_no_go = dict(go_nogo)
        self._last_go_no_go_eval_ts = ts
        return dict(go_nogo)

    async def _send_portfolio_digest(self, snapshot: dict[str, Any]) -> None:
        equity = self._to_float(snapshot.get("equity_estimate"), 0.0)
        cash = self._to_float(snapshot.get("cash_balance"), 0.0)
        upnl = self._to_float(snapshot.get("unrealized_pnl"), 0.0)
        progress_pct = self._to_float(snapshot.get("progress_pct"), 0.0)
        drawdown_pct = self._to_float(snapshot.get("drawdown_pct"), 0.0)
        pos_notional = self._to_float(snapshot.get("position_notional_usd"), 0.0)
        pos_count = int(snapshot.get("positions_count", 0) or 0)
        stale = bool(snapshot.get("balance_sync_stale")) or bool(snapshot.get("position_check_stale"))
        go_nogo = await self._evaluate_go_no_go()
        reject_tax = go_nogo.get("reject_tax", {}) if isinstance(go_nogo.get("reject_tax"), dict) else {}
        if not reject_tax:
            reject_tax = await self._collect_reject_tax_metrics()
        deltas = go_nogo.get("deltas", {}) if isinstance(go_nogo.get("deltas"), dict) else {}

        lines = [
            "📊 <b>LIGHTER Portfolio Digest</b>",
            (
                f"<b>Equity</b> {equity:,.4f} · <b>Cash</b> {cash:,.4f} · "
                f"<b>uPnL</b> {upnl:+.4f}"
            ),
            (
                f"<b>Progress</b> {progress_pct:+.2f}% · <b>Drawdown</b> {drawdown_pct:+.2f}% · "
                f"<b>Exposure</b> {pos_notional:,.4f}"
            ),
            f"<b>Positions</b> {pos_count} · <b>Sync</b> {'stale ⚠️' if stale else 'fresh ✅'}",
            (
                f"<b>Operator</b> {'🟢 GO' if go_nogo.get('go') else '🔴 NO-GO'} · "
                f"<b>Reject Tax {reject_tax.get('window_hours', 24)}h</b> "
                f"{self._to_float(reject_tax.get('reject_tax_pct'), 0.0):.1f}% "
                f"({int(reject_tax.get('reject_skip_count', 0) or 0)}/"
                f"{int(reject_tax.get('sample_size', 0) or 0)})"
            ),
            f"<b>Decision Source</b> {html.escape(str(go_nogo.get('source', 'bot_policy')).replace('_', ' '))}",
            (
                f"<b>Hard Fail</b> {self._to_float(reject_tax.get('hard_fail_pct'), 0.0):.1f}% · "
                f"{int(reject_tax.get('hard_failed_count', 0) or 0)} events"
            ),
        ]
        d1 = deltas.get("1h", {}) if isinstance(deltas.get("1h"), dict) else {}
        d6 = deltas.get("6h", {}) if isinstance(deltas.get("6h"), dict) else {}
        d24 = deltas.get("24h", {}) if isinstance(deltas.get("24h"), dict) else {}
        if d1 or d6 or d24:
            rt_1h = self._to_float(d1.get("reject_tax_pct"), 0.0)
            rt_6h = self._to_float(d6.get("reject_tax_pct"), 0.0)
            rt_24h = self._to_float(d24.get("reject_tax_pct"), 0.0)
            trend = "steady"
            if rt_1h < rt_6h and rt_6h < rt_24h:
                trend = "improving"
            elif rt_1h > rt_6h and rt_6h > rt_24h:
                trend = "worsening"
            lines.append(
                f"<b>Reject Trend</b> 1h {rt_1h:.1f}% · 6h {rt_6h:.1f}% · 24h {rt_24h:.1f}% ({trend})"
            )
        if not go_nogo.get("go"):
            reasons = go_nogo.get("reason_details") or go_nogo.get("reasons") or []
            if reasons:
                lines.append(f"<b>Blockers</b> {html.escape('; '.join(reasons[:3]))}")
        top_source = (reject_tax.get("by_source") or [{}])[0]
        if top_source and top_source.get("total"):
            lines.append(
                f"<b>Top Reject Source</b> {html.escape(str(top_source.get('key', 'unknown')))} "
                f"({self._to_float(top_source.get('reject_tax_pct'), 0.0):.1f}% / n={int(top_source.get('total', 0) or 0)})"
            )
        top_strategy = (reject_tax.get("by_strategy") or [{}])[0]
        if top_strategy and top_strategy.get("total"):
            lines.append(
                f"<b>Top Reject Strategy</b> {html.escape(str(top_strategy.get('key', 'unknown')))} "
                f"({self._to_float(top_strategy.get('reject_tax_pct'), 0.0):.1f}% / n={int(top_strategy.get('total', 0) or 0)})"
            )
        top_timeframe = (reject_tax.get("by_timeframe") or [{}])[0]
        if top_timeframe and top_timeframe.get("total"):
            lines.append(
                f"<b>Top Reject Timeframe</b> {html.escape(str(top_timeframe.get('key', 'unknown')))} "
                f"({self._to_float(top_timeframe.get('reject_tax_pct'), 0.0):.1f}% / n={int(top_timeframe.get('total', 0) or 0)})"
            )
        top_reason = (reject_tax.get("top_reasons") or [{}])[0]
        if top_reason and top_reason.get("reason"):
            lines.append(
                f"<b>Top Reject Reason</b> {html.escape(str(top_reason.get('reason')))} "
                f"(n={int(top_reason.get('count', 0) or 0)})"
            )

        if self.positions:
            lines.append("<b>Open Positions</b>")
            for symbol, pos in sorted(self.positions.items())[:3]:
                qty = self._to_float(getattr(pos, "quantity", 0.0), 0.0)
                if qty <= 0:
                    continue
                side = str(getattr(pos, "side", "")).upper()
                entry = self._to_float(getattr(pos, "entry_price", 0.0), 0.0)
                mark = self._to_float(getattr(pos, "current_price", 0.0), 0.0)
                pnl = self._to_float(getattr(pos, "unrealized_pnl", 0.0), 0.0)
                pnl_pct = self._to_float(getattr(pos, "pnl_percent", 0.0), 0.0)
                tp = self._to_float(getattr(pos, "take_profit", 0.0), 0.0)
                sl = self._to_float(getattr(pos, "stop_loss", 0.0), 0.0)
                regime, detail = self._market_condition_for_symbol(symbol)
                lines.append(
                    
                        f"• <b>{html.escape(symbol)}</b> {html.escape(side)} {qty:g} @ {entry:,.4f} | "
                        f"mark {mark:,.4f} | {pnl:+.4f} ({pnl_pct:+.2f}%)"
                    
                )
                if tp > 0 or sl > 0:
                    lines.append(f"  TP {tp:,.4f} · SL {sl:,.4f}")
                lines.append(f"  {html.escape(regime)} · {html.escape(detail)}")

        await self._send_telegram_message("\n".join(lines), parse_mode="HTML")

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

    def _normalize_strategy_for_policy(self, strategy: str) -> str:
        canonical = str(strategy or "").strip().lower()
        if not canonical:
            return ""

        if canonical in self._allowed_strategies:
            return canonical

        if self._allowed_strategies:
            if canonical.endswith("_lite"):
                base = canonical[:-5].strip("_-")
                if base and base in self._allowed_strategies:
                    return base
            if canonical.endswith("-lite"):
                base = canonical[:-5].strip("_-")
                if base and base in self._allowed_strategies:
                    return base

        return canonical

    def _policy_noop_result(
        self,
        signal: TradeSignal,
        *,
        reason: str,
        symbol: str | None = None,
    ) -> TradeResult:
        return TradeResult(
            trade_id="noop",
            signal_id=str(getattr(signal, "signal_id", "") or ""),
            platform=PLATFORM.value,
            symbol=str(symbol or signal.symbol or ""),
            side=signal.side,
            success=True,
            metadata={
                "noop": True,
                "policy_reject": True,
                "reason": str(reason or "policy_filter"),
            },
        )

    @staticmethod
    def _should_retry_order_submit_failure(error: Any) -> bool:
        text = str(error or "").lower()
        if not text:
            return False
        retryable_markers = (
            "timeout",
            "timed out",
            "temporarily unavailable",
            "service unavailable",
            "connection reset",
            "connection aborted",
            "connection closed",
            "connection error",
            "network",
            "try again",
            "rate limit",
            "429",
            "502",
            "503",
            "504",
            "bad gateway",
            "gateway timeout",
        )
        return any(marker in text for marker in retryable_markers)

    @staticmethod
    def _should_treat_as_preflight_noop(error: Any) -> bool:
        text = str(error or "").lower()
        if not text:
            return False
        preflight_markers = (
            "entry cooldown active for ",
            "position already at symbol cap",
            "entry skipped at symbol cap",
            "signal leverage ",
            "signal quantity is required",
            "target order notional too low",
            "entry notional too low",
            "quantity rounded to zero",
            "no order book mapping for symbol",
            "could not get current price for ",
            "execution failsafe active",
            "jurisdiction block active",
            "trading disabled (trading_enabled=false)",
            "live trading disabled (allow_live_trading=0)",
        )
        return any(marker in text for marker in preflight_markers)

    async def _close_position_for_rotation(self, symbol: str, reason: str) -> TradeResult:
        current = self.positions.get(symbol)
        if current is None:
            return TradeResult(
                trade_id="noop",
                signal_id=f"rotate-close-{symbol}-{int(time.time())}",
                platform=PLATFORM.value,
                symbol=symbol,
                side=TradeSide.SELL,
                success=True,
                metadata={"noop": True, "reason": "no_position_for_rotation"},
            )

        qty = self._to_float(getattr(current, "quantity", 0.0), 0.0)
        if qty <= 0:
            return TradeResult(
                trade_id="noop",
                signal_id=f"rotate-close-{symbol}-{int(time.time())}",
                platform=PLATFORM.value,
                symbol=symbol,
                side=TradeSide.SELL,
                success=True,
                metadata={"noop": True, "reason": "zero_quantity_for_rotation"},
            )

        side = getattr(current, "side", None)
        close_side = (
            TradeSide.SELL
            if side in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG")
            else TradeSide.BUY
        )
        exit_signal = TradeSignal(
            signal_id=f"rotate-close-{symbol.lower()}-{int(time.time() * 1000)}",
            symbol=symbol,
            side=close_side,
            signal_type=SignalType.EXIT,
            confidence=1.0,
            source="opportunity-rotation",
            quantity=abs(qty),
            metadata={
                "reduce_only": True,
                "origin": "opportunity_rotation",
                "reason": reason,
            },
        )
        result = await self._execute_trade(exit_signal, ignore_trading_guard=True)
        if result.success and self._to_float(getattr(result, "filled_quantity", 0.0), 0.0) > 0:
            self.positions.pop(symbol, None)
        return result

    async def _maybe_rotate_opportunity(
        self,
        *,
        target_coin: str,
        signal: TradeSignal,
        is_buy: bool,
        reference_price: float,
    ) -> None:
        active_symbols = self._active_position_symbols()
        if not active_symbols or target_coin in active_symbols:
            return

        locked = sorted(active_symbols)[0]
        if not self._opportunity_rotation_enabled:
            raise ValueError(
                f"Single-symbol mode active: open symbol={locked}, rejected symbol={target_coin}"
            )

        now_ts = time.time()
        if (now_ts - self._last_opportunity_rotation_ts) < self._opportunity_rotation_cooldown_seconds:
            wait_s = self._opportunity_rotation_cooldown_seconds - (
                now_ts - self._last_opportunity_rotation_ts
            )
            raise ValueError(
                f"Opportunity rotation cooldown active: wait {wait_s:.1f}s"
            )

        incoming_ev = self._estimate_signal_ev_pct(
            signal,
            coin=target_coin,
            is_buy=is_buy,
            reference_price=reference_price,
        )
        locked_pos = self.positions.get(locked)
        locked_ev = self._estimate_position_ev_pct(locked, locked_pos) if locked_pos else 0.0
        edge = incoming_ev - locked_ev

        if edge < self._opportunity_rotation_min_edge_pct:
            raise ValueError(
                f"Single-symbol mode active: {target_coin} EV edge {edge:+.3f}% "
                f"below threshold {self._opportunity_rotation_min_edge_pct:.3f}% (locked={locked})"
            )

        close_result = await self._close_position_for_rotation(
            locked,
            reason=f"rotate_{locked}_to_{target_coin}_edge_{edge:+.3f}",
        )
        closed_qty = self._to_float(getattr(close_result, "filled_quantity", 0.0), 0.0)
        if not close_result.success or closed_qty <= 0:
            raise ValueError(
                f"Opportunity rotation failed: could not close {locked} before opening {target_coin}"
            )

        self._last_opportunity_rotation_ts = now_ts
        logger.warning(
            "Opportunity rotation executed: %s -> %s | locked_ev=%.3f%% incoming_ev=%.3f%% edge=%.3f%%",
            locked,
            target_coin,
            locked_ev,
            incoming_ev,
            edge,
        )

    @staticmethod
    def _strategy_perf_key(strategy: str, timeframe: str) -> str:
        s = str(strategy or "").strip().lower()
        tf = str(timeframe or "").strip().lower()
        if not s or not tf:
            return ""
        return f"{s}@{tf}"

    def _size_ramp_key(self, strategy: str, timeframe: str) -> str:
        key = self._strategy_perf_key(strategy, timeframe)
        return key or "global"

    def _target_margin_for_signal(self, strategy: str, timeframe: str) -> float:
        base = max(0.0, float(self._target_order_notional_usd or 0.0))
        if not self._size_ramp_enabled or base <= 0:
            return base
        key = self._size_ramp_key(strategy, timeframe)
        margin = self._to_float(
            self._size_ramp_margin_by_key.get(key, self._size_ramp_default_margin_usd),
            self._size_ramp_default_margin_usd,
        )
        return self._clamp(
            float(margin),
            self._size_ramp_min_margin_usd,
            self._size_ramp_max_margin_usd,
        )

    def _maybe_adjust_size_ramp(self, strategy: str, timeframe: str) -> None:
        if not self._size_ramp_enabled:
            return
        if self._target_order_notional_usd <= 0:
            return
        key_perf = self._strategy_perf_key(strategy, timeframe)
        if not key_perf:
            return
        history = list(self._strategy_perf_history.get(key_perf, []))
        actionable = [o for o in history if o in {"filled_success", "accepted_no_fill", "hard_failed"}]
        if len(actionable) < self._size_ramp_min_samples:
            return

        now_ts = time.time()
        key = self._size_ramp_key(strategy, timeframe)
        last_adjust_ts = float(self._size_ramp_last_adjust_ts.get(key, 0.0) or 0.0)
        if (now_ts - last_adjust_ts) < self._size_ramp_adjust_cooldown_seconds:
            return

        current_margin = self._target_margin_for_signal(strategy, timeframe)
        filled = sum(1 for o in actionable if o == "filled_success")
        hard_failed = sum(1 for o in actionable if o == "hard_failed")
        total = float(len(actionable))
        fill_rate = (filled / total) if total > 0 else 0.0
        hard_fail_rate = (hard_failed / total) if total > 0 else 0.0
        tail_n = min(self._size_ramp_recent_streak, len(actionable))
        tail = actionable[-tail_n:] if tail_n > 0 else []
        recent_consistent = bool(tail) and all(outcome == "filled_success" for outcome in tail)

        next_margin = current_margin
        reason = ""
        if (
            hard_fail_rate > self._size_ramp_max_hard_fail_rate
            or fill_rate < self._size_ramp_down_fill_rate
        ):
            next_margin = max(
                self._size_ramp_min_margin_usd,
                current_margin - self._size_ramp_step_margin_usd,
            )
            reason = (
                f"decrease fill={fill_rate:.1%} hard_fail={hard_fail_rate:.1%}"
            )
        elif (
            fill_rate >= self._size_ramp_up_fill_rate
            and hard_fail_rate <= self._size_ramp_max_hard_fail_rate
            and recent_consistent
        ):
            next_margin = min(
                self._size_ramp_max_margin_usd,
                current_margin + self._size_ramp_step_margin_usd,
            )
            reason = (
                f"increase fill={fill_rate:.1%} hard_fail={hard_fail_rate:.1%} streak={tail_n}"
            )

        if abs(next_margin - current_margin) < 1e-9:
            return
        self._size_ramp_margin_by_key[key] = float(next_margin)
        self._size_ramp_last_adjust_ts[key] = now_ts
        logger.warning(
            "Size ramp adjusted %s | %s -> %.2f USD (prev %.2f USD, n=%d, strategy=%s, timeframe=%s)",
            key,
            reason,
            float(next_margin),
            float(current_margin),
            len(actionable),
            strategy or "n/a",
            timeframe or "n/a",
        )

    def _strategy_perf_policy_reason(self, strategy: str, timeframe: str) -> str:
        if not self._perf_guard_enabled:
            return ""
        key = self._strategy_perf_key(strategy, timeframe)
        if not key:
            return ""
        history = list(self._strategy_perf_history.get(key, []))
        if len(history) < self._perf_guard_min_samples:
            return ""
        actionable = [o for o in history if o in {"filled_success", "accepted_no_fill", "hard_failed"}]
        if len(actionable) < self._perf_guard_min_samples:
            return ""
        filled = sum(1 for o in actionable if o == "filled_success")
        hard_failed = sum(1 for o in actionable if o == "hard_failed")
        total = float(len(actionable))
        fill_rate = filled / total if total > 0 else 0.0
        hard_fail_rate = hard_failed / total if total > 0 else 0.0
        if fill_rate < self._perf_guard_min_fill_rate:
            return (
                f"perf_guard: fill_rate {fill_rate:.1%} below {self._perf_guard_min_fill_rate:.1%} "
                f"({strategy}/{timeframe}, n={int(total)})"
            )
        if hard_fail_rate > self._perf_guard_max_hard_fail_rate:
            return (
                f"perf_guard: hard_fail_rate {hard_fail_rate:.1%} above {self._perf_guard_max_hard_fail_rate:.1%} "
                f"({strategy}/{timeframe}, n={int(total)})"
            )
        return ""

    def _record_strategy_perf_outcome(
        self,
        signal: TradeSignal,
        *,
        strategy: str,
        timeframe: str,
        outcome: str,
    ) -> None:
        if not self._perf_guard_enabled:
            return
        metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
        reduce_only = bool(metadata.get("reduce_only", False))
        if signal.signal_type in {
            SignalType.EXIT,
            SignalType.SCALE_OUT,
            SignalType.TAKE_PROFIT,
            SignalType.STOP_LOSS,
        }:
            reduce_only = True
        entry_like = signal.signal_type in {SignalType.ENTRY, SignalType.SCALE_IN}
        if not entry_like or reduce_only:
            return
        key = self._strategy_perf_key(strategy, timeframe)
        if not key:
            return
        self._strategy_perf_history[key].append(str(outcome or "").strip().lower())
        self._maybe_adjust_size_ramp(strategy, timeframe)

    def _is_signal_allowed_by_policy(self, signal: TradeSignal) -> tuple[bool, str]:
        strategy, timeframe = self._signal_strategy_info(signal)
        metadata = signal.metadata if isinstance(signal.metadata, dict) else {}
        reduce_only = bool(metadata.get("reduce_only", False))
        if signal.signal_type in {
            SignalType.EXIT,
            SignalType.SCALE_OUT,
            SignalType.TAKE_PROFIT,
            SignalType.STOP_LOSS,
        }:
            reduce_only = True
        entry_like = signal.signal_type in {SignalType.ENTRY, SignalType.SCALE_IN}

        if entry_like and not reduce_only:
            coin = self._normalize_coin_symbol(str(signal.symbol or ""))
            can_enter, risk_reason = self._hard_risk_kernel.can_open_entry()
            if not can_enter:
                return False, risk_reason
            if self._entry_symbol_allowlist and coin not in self._entry_symbol_allowlist:
                return (
                    False,
                    f"symbol '{coin}' not in entry allowlist {sorted(self._entry_symbol_allowlist)}",
                )
            if self._entry_cooldown_seconds > 0:
                now_ts = time.time()
                last_ts = float(self._last_entry_ts.get(coin, 0.0) or 0.0)
                if last_ts and (now_ts - last_ts) < self._entry_cooldown_seconds:
                    wait_s = self._entry_cooldown_seconds - (now_ts - last_ts)
                    return False, f"entry cooldown active for {coin}: wait {wait_s:.1f}s"

            existing = self.positions.get(coin)
            if existing is not None and self._max_position_notional_usd > 0:
                existing_qty = self._to_float(getattr(existing, "quantity", 0.0), 0.0)
                if existing_qty > 0:
                    existing_side = getattr(existing, "side", None)
                    existing_is_buy = existing_side in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG")
                    incoming_is_buy = signal.side in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG")
                    if existing_is_buy == incoming_is_buy:
                        mark_price = self._to_float(getattr(existing, "current_price", 0.0), 0.0)
                        if mark_price <= 0:
                            mark_price = self._to_float(getattr(existing, "entry_price", 0.0), 0.0)
                        if mark_price > 0:
                            current_notional = abs(existing_qty * mark_price)
                            if (
                                self._cap_near_churn_enabled
                                and self._max_position_notional_usd > 0
                                and current_notional > 0
                            ):
                                cap_ratio = current_notional / max(
                                    0.0001, float(self._max_position_notional_usd)
                                )
                                if cap_ratio >= self._cap_near_churn_ratio:
                                    incoming_ev = self._estimate_signal_ev_pct(
                                        signal,
                                        coin=coin,
                                        is_buy=incoming_is_buy,
                                        reference_price=float(mark_price),
                                        expected_notional_usd=self._default_expected_entry_notional_usd(),
                                    )
                                    current_ev = self._estimate_position_ev_pct(coin, existing)
                                    ev_edge = incoming_ev - current_ev
                                    if (
                                        incoming_ev < self._cap_near_min_net_ev_pct
                                        or ev_edge < self._cap_near_min_ev_edge_pct
                                    ):
                                        return (
                                            False,
                                            (
                                                f"cap_near_churn: {coin} at {cap_ratio * 100.0:.1f}% of cap; "
                                                f"incoming_ev={incoming_ev:+.3f}% current_ev={current_ev:+.3f}% "
                                                f"edge={ev_edge:+.3f}% (min_ev={self._cap_near_min_net_ev_pct:.3f}% "
                                                f"min_edge={self._cap_near_min_ev_edge_pct:.3f}%)"
                                            ),
                                        )
                            if current_notional >= (self._max_position_notional_usd * 0.995):
                                return (
                                    False,
                                    f"position already at symbol cap for {coin} "
                                    f"({current_notional:.4f}/{self._max_position_notional_usd:.4f})",
                                )

            confidence = self._clamp(self._to_float(getattr(signal, "confidence", 0.0), 0.0), 0.0, 1.0)
            if self._entry_min_confidence > 0 and confidence < self._entry_min_confidence:
                return (
                    False,
                    f"confidence {confidence:.2f} below minimum {self._entry_min_confidence:.2f}",
                )

            raw_edge = metadata.get("edge_pct")
            if raw_edge is not None and self._entry_min_edge_pct > 0:
                edge_pct = self._to_float(raw_edge, 0.0)
                if abs(edge_pct) < self._entry_min_edge_pct:
                    return (
                        False,
                        f"edge_pct {edge_pct:+.3f}% below minimum {self._entry_min_edge_pct:.3f}%",
                    )
                side = str(signal.side)
                if side in {"TradeSide.BUY", "TradeSide.LONG"} and edge_pct <= 0:
                    return False, f"edge_pct {edge_pct:+.3f}% invalid for long entry"
                if side in {"TradeSide.SELL", "TradeSide.SHORT"} and edge_pct >= 0:
                    return False, f"edge_pct {edge_pct:+.3f}% invalid for short entry"

        if self._allowed_signal_sources and entry_like and not reduce_only:
            source_candidates = {
                str(signal.source or "").strip().lower(),
                str(metadata.get("source") or "").strip().lower(),
                str(metadata.get("origin") or "").strip().lower(),
            }
            source_candidates = {s for s in source_candidates if s}
            if not source_candidates:
                return False, "signal source metadata required"
            if not (source_candidates & self._allowed_signal_sources):
                return False, f"source not allowed ({', '.join(sorted(source_candidates))})"

        if self._strategy_require_metadata and (not strategy or not timeframe):
            return False, "strategy metadata required"

        if self._allowed_strategies and strategy:
            strategy = self._normalize_strategy_for_policy(strategy)

        if self._allowed_strategies and strategy and strategy not in self._allowed_strategies:
            return False, f"strategy '{strategy}' not allowed"
        if self._allowed_timeframes and timeframe and timeframe not in self._allowed_timeframes:
            return False, f"timeframe '{timeframe}' not allowed"
        if self._allowed_strategies and not strategy and self._strategy_require_metadata:
            return False, "missing strategy metadata"
        if self._allowed_timeframes and not timeframe and self._strategy_require_metadata:
            return False, "missing timeframe metadata"
        if entry_like and not reduce_only:
            perf_reason = self._strategy_perf_policy_reason(strategy, timeframe)
            if perf_reason:
                return False, perf_reason
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

        def _maybe_drop(level_name: str, level_value: float | None) -> float | None:
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

    async def _estimate_equity_snapshot(self) -> dict[str, Any]:
        """
        Build a lightweight equity snapshot from current balance + tracked positions.
        Uses current_price when available, otherwise falls back to entry_price.
        """
        now_ts = time.time()
        now_iso = datetime.now(UTC).isoformat()
        cash_balance = self._to_float(self.balance, 0.0)
        unrealized_pnl = 0.0
        position_notional = 0.0
        stale_price_positions = 0
        positions_count = 0

        for _symbol, position in self.positions.items():
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
        hard_risk = self._hard_risk_kernel.status(now_ts=now_ts)

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
                datetime.fromtimestamp(self._last_balance_sync_ts, tz=UTC).isoformat()
                if self._last_balance_sync_ts > 0
                else None
            ),
            "last_position_check_at": (
                datetime.fromtimestamp(self._last_position_check_ts, tz=UTC).isoformat()
                if self._last_position_check_ts > 0
                else None
            ),
            "last_balance_sync_error": self._last_balance_sync_error,
            "last_position_check_error": self._last_position_check_error,
            "hard_risk_kernel": hard_risk,
            "hard_risk_blocked": bool(hard_risk.get("blocked", False)),
            "hard_risk_block_reason": str(hard_risk.get("block_reason", "")),
            "hard_risk_block_remaining_sec": float(hard_risk.get("blocked_for_sec", 0.0) or 0.0),
        }

    async def _persist_equity_snapshot(self, snapshot: dict[str, Any], reason: str) -> None:
        if self._db is None:
            return
        payload = dict(snapshot)
        payload["reason"] = str(reason)
        payload["recorded_at"] = datetime.now(UTC)
        payload["service"] = SERVICE_NAME
        snapshot_id = f"{PLATFORM.value}_{int(time.time() * 1000)}"
        try:
            await self._db.collection("equity_snapshots").document(snapshot_id).set(payload)
            await self._db.collection("equity_snapshots_current").document(PLATFORM.value).set(payload)
        except Exception as exc:
            logger.debug("Equity snapshot write error: %s", exc)

    async def _maybe_publish_assistant_brief(self, snapshot: dict[str, Any]) -> None:
        """
        Publish a compact operational brief for Kimi/OpenClaw assistant consumption.
        """
        if not self._assistant_brief_enabled or self._db is None:
            return
        now_ts = time.time()
        if (now_ts - self._last_assistant_brief_ts) < self._assistant_brief_interval_seconds:
            return
        self._last_assistant_brief_ts = now_ts

        positions_payload: list[dict[str, Any]] = []
        for symbol, pos in sorted(self.positions.items()):
            qty = self._to_float(getattr(pos, "quantity", 0.0), 0.0)
            if qty <= 0:
                continue
            ev_pct = self._estimate_position_ev_pct(symbol, pos)
            regime, detail = self._market_condition_for_symbol(symbol)
            positions_payload.append(
                {
                    "symbol": symbol,
                    "side": str(getattr(pos, "side", "")),
                    "quantity": qty,
                    "entry_price": self._to_float(getattr(pos, "entry_price", 0.0), 0.0),
                    "mark_price": self._to_float(getattr(pos, "current_price", 0.0), 0.0),
                    "take_profit": self._to_float(getattr(pos, "take_profit", 0.0), 0.0),
                    "stop_loss": self._to_float(getattr(pos, "stop_loss", 0.0), 0.0),
                    "unrealized_pnl": self._to_float(getattr(pos, "unrealized_pnl", 0.0), 0.0),
                    "ev_score_pct": ev_pct,
                    "regime": regime,
                    "regime_detail": detail,
                    "metadata": pos.metadata if isinstance(pos.metadata, dict) else {},
                }
            )

        advice: list[str] = []
        if not positions_payload:
            advice.append("Flat book: wait for high-confidence entry matching allowed strategy/timeframe.")
        else:
            top = sorted(positions_payload, key=lambda x: x.get("ev_score_pct", 0.0), reverse=True)[0]
            if self._to_float(top.get("ev_score_pct"), 0.0) < 0:
                advice.append("Current EV negative: tighten risk and prioritize rotation on stronger signal.")
            advice.append(
                f"Top position {top.get('symbol')} EV {self._to_float(top.get('ev_score_pct'), 0.0):+.3f}%."
            )
        go_nogo = await self._evaluate_go_no_go()
        reject_tax = go_nogo.get("reject_tax", {}) if isinstance(go_nogo.get("reject_tax"), dict) else {}
        if not reject_tax:
            reject_tax = await self._collect_reject_tax_metrics()
        if not go_nogo.get("go"):
            advice.append(f"NO-GO: {'; '.join((go_nogo.get('reasons') or [])[:2])}")

        brief = {
            "service": SERVICE_NAME,
            "platform": PLATFORM.value,
            "generated_at": datetime.now(UTC),
            "snapshot": snapshot,
            "positions": positions_payload,
            "policy": {
                "single_symbol_mode": self._single_symbol_mode,
                "entry_symbol_allowlist": sorted(self._entry_symbol_allowlist),
                "dynamic_risk_enabled": self._dynamic_risk_enabled,
                "opportunity_rotation_enabled": self._opportunity_rotation_enabled,
                "opportunity_min_edge_pct": self._opportunity_rotation_min_edge_pct,
                "allowed_strategies": sorted(self._allowed_strategies),
                "allowed_timeframes": sorted(self._allowed_timeframes),
                "entry_min_confidence": self._entry_min_confidence,
                "entry_min_edge_pct": self._entry_min_edge_pct,
                "hard_risk_kernel_enabled": self._hard_risk_kernel_enabled,
                "hard_risk_state": self._hard_risk_kernel.status(),
                "perf_guard_enabled": self._perf_guard_enabled,
                "perf_guard_window": self._perf_guard_window,
                "perf_guard_min_samples": self._perf_guard_min_samples,
                "perf_guard_min_fill_rate": self._perf_guard_min_fill_rate,
                "perf_guard_max_hard_fail_rate": self._perf_guard_max_hard_fail_rate,
                "max_order_notional_usd": self._max_order_notional_usd,
                "max_position_notional_usd": self._max_position_notional_usd,
                "target_order_notional_usd": self._target_order_notional_usd,
                "min_entry_notional_usd": self._min_entry_notional_usd,
                "max_signal_leverage": self._max_signal_leverage,
                "size_ramp_enabled": self._size_ramp_enabled,
                "size_ramp_min_margin_usd": self._size_ramp_min_margin_usd,
                "size_ramp_max_margin_usd": self._size_ramp_max_margin_usd,
                "size_ramp_step_margin_usd": self._size_ramp_step_margin_usd,
                "size_ramp_min_samples": self._size_ramp_min_samples,
                "size_ramp_up_fill_rate": self._size_ramp_up_fill_rate,
                "size_ramp_down_fill_rate": self._size_ramp_down_fill_rate,
                "size_ramp_max_hard_fail_rate": self._size_ramp_max_hard_fail_rate,
                "entry_cooldown_seconds": self._entry_cooldown_seconds,
                "sync_before_entry": self._sync_before_entry,
                "jurisdiction_block_until": (
                    datetime.fromtimestamp(self._jurisdiction_block_until_ts, UTC).isoformat()
                    if self._jurisdiction_block_until_ts > 0
                    else ""
                ),
            },
            "reject_tax": reject_tax,
            "go_no_go": go_nogo,
            "assistant_advice": advice,
        }
        try:
            doc_id = f"{PLATFORM.value}_{int(now_ts * 1000)}"
            await self._db.collection("assistant_ops_briefs").document(doc_id).set(brief)
            await self._db.collection("assistant_ops_briefs").document("latest").set(brief)
        except Exception as exc:
            logger.debug("Assistant brief write error: %s", exc)

    async def _record_execution_verification(
        self,
        signal: TradeSignal,
        result: TradeResult,
        channel: str,
    ) -> None:
        """Persist per-signal execution audit row for traceability."""
        strategy, timeframe = self._signal_strategy_info(signal)
        snapshot = await self._estimate_equity_snapshot()
        result_meta = getattr(result, "metadata", {}) or {}
        is_noop = bool(result_meta.get("noop", False))
        policy_reject = bool(result_meta.get("policy_reject", False)) or str(
            getattr(result, "error_message", "") or ""
        ).lower().startswith("policy_reject:")
        filled_qty = self._to_float(getattr(result, "filled_quantity", 0.0), 0.0)
        success = bool(getattr(result, "success", False))

        if is_noop and policy_reject:
            outcome = "policy_noop"
        elif is_noop:
            outcome = "noop"
        elif success and filled_qty > 0:
            outcome = "filled_success"
        elif success:
            outcome = "accepted_no_fill"
        elif policy_reject:
            outcome = "policy_reject"
        else:
            outcome = "hard_failed"

        payload: dict[str, Any] = {
            "service": SERVICE_NAME,
            "platform": PLATFORM.value,
            "channel": channel,
            "signal_id": str(signal.signal_id or ""),
            "symbol": str(signal.symbol or ""),
            "signal_source": self._extract_signal_source(signal),
            "side": str(signal.side),
            "signal_type": str(signal.signal_type),
            "strategy": strategy,
            "timeframe": timeframe,
            "quantity": self._to_float(getattr(signal, "quantity", 0.0), 0.0),
            "take_profit": self._to_float(getattr(signal, "take_profit", 0.0), 0.0),
            "stop_loss": self._to_float(getattr(signal, "stop_loss", 0.0), 0.0),
            "success": success,
            "error_message": str(getattr(result, "error_message", "") or ""),
            "filled_quantity": filled_qty,
            "avg_price": self._to_float(getattr(result, "avg_price", 0.0), 0.0),
            "order_id": str(getattr(result, "order_id", "") or ""),
            "execution_time_ms": self._to_float(getattr(result, "execution_time_ms", 0.0), 0.0),
            "equity_estimate": snapshot.get("equity_estimate", 0.0),
            "cash_balance": snapshot.get("cash_balance", 0.0),
            "position_notional_usd": snapshot.get("position_notional_usd", 0.0),
            "outcome": outcome,
            "is_noop": is_noop,
            "noop_reason": str(result_meta.get("reason", "") or ""),
            "policy_reason": str(
                result_meta.get("reason")
                or getattr(result, "error_message", "")
                or ""
            )[:220],
            "signal_metadata": (signal.metadata or {}),
            "result_metadata": result_meta,
            "metadata": (signal.metadata or {}),
            "recorded_at": datetime.now(UTC),
        }
        risk_event = self._hard_risk_kernel.record_execution_outcome(
            outcome=outcome,
            equity_estimate=self._to_float(payload.get("equity_estimate"), 0.0),
        )
        payload["hard_risk_state"] = self._hard_risk_kernel.status()
        if risk_event:
            payload["hard_risk_event"] = risk_event.as_dict()
            await self._send_telegram_message(
                (
                    "🛑 <b>LIGHTER HARD RISK KERNEL ACTIVATED</b>\n"
                    f"reason={html.escape(risk_event.reason)}\n"
                    f"hold={max(0.0, risk_event.blocked_until_ts - time.time()):.0f}s"
                ),
                parse_mode="HTML",
            )
        self._record_strategy_perf_outcome(
            signal,
            strategy=strategy,
            timeframe=str(timeframe),
            outcome=str(outcome),
        )
        logger.info(
            "Execution verify | signal=%s outcome=%s ok=%s fill=%s@%s equity=%s",
            payload["signal_id"],
            payload["outcome"],
            payload["success"],
            payload["filled_quantity"],
            payload["avg_price"],
            payload["equity_estimate"],
        )
        now_ts = time.time()
        if not is_noop:
            self._last_execution_attempt_ts = now_ts
            if payload["success"] and self._to_float(payload["filled_quantity"], 0.0) > 0:
                self._last_successful_fill_ts = now_ts
                self._last_execution_error_message = ""
                self._execution_watchdog_alert_streak = 0
            else:
                self._last_execution_error_message = str(payload.get("error_message") or "")[:280]
        self._recent_execution_outcomes.append(
            {
                "recorded_at": payload.get("recorded_at"),
                "outcome": payload.get("outcome"),
                "signal_source": payload.get("signal_source"),
                "strategy": payload.get("strategy"),
                "timeframe": payload.get("timeframe"),
                "policy_reason": payload.get("policy_reason"),
                "noop_reason": payload.get("noop_reason"),
                "error_message": payload.get("error_message"),
                "channel": payload.get("channel"),
            }
        )
        if self._db is None:
            return
        try:
            key = payload["signal_id"] or f"noid-{int(time.time() * 1000)}"
            doc_id = f"{PLATFORM.value}_{key}_{channel}"
            await self._db.collection("execution_verifications").document(doc_id).set(payload)
        except Exception as exc:
            logger.debug("Execution verification write error: %s", exc)

    def _clear_execution_failsafe(self) -> bool:
        """Clear active execution failsafe hold if present."""
        if self._execution_failsafe_until_ts <= 0:
            return False
        self._execution_failsafe_until_ts = 0.0
        self._execution_failsafe_reason = ""
        self._execution_watchdog_alert_streak = 0
        return True

    def _activate_execution_failsafe(self, reason: str, *, now_ts: float | None = None) -> bool:
        """Activate (or extend) execution failsafe hold window."""
        if not self._execution_failsafe_enabled:
            return False
        ts = float(now_ts if now_ts is not None else time.time())
        until_ts = ts + self._execution_failsafe_hold_seconds
        changed = until_ts > self._execution_failsafe_until_ts + 1e-6
        self._execution_failsafe_until_ts = max(self._execution_failsafe_until_ts, until_ts)
        self._execution_failsafe_reason = str(reason or self._execution_failsafe_reason or "").strip()[:280]
        return changed

    async def _maybe_send_lane_heartbeat(self, snap: dict[str, Any], now_ts: float | None = None) -> None:
        """Periodic concise lane-status heartbeat for operators."""
        if not self._lane_heartbeat_enabled:
            return
        if not self._telegram_bot_token or not self._telegram_chat_id:
            return
        ts = float(now_ts if now_ts is not None else time.time())
        if self._last_lane_heartbeat_ts and (ts - self._last_lane_heartbeat_ts) < self._lane_heartbeat_seconds:
            return
        self._last_lane_heartbeat_ts = ts

        bal_age = self._to_float(snap.get("balance_sync_age_sec"), 0.0)
        pos_age = self._to_float(snap.get("position_check_age_sec"), 0.0)
        balance_stale = bool(snap.get("balance_sync_stale"))
        position_stale = bool(snap.get("position_check_stale"))
        failsafe_remaining = max(0.0, self._execution_failsafe_until_ts - ts)
        jurisdiction_remaining = max(0.0, self._jurisdiction_block_until_ts - ts)
        hard_risk_remaining = self._to_float(snap.get("hard_risk_block_remaining_sec"), 0.0)
        hard_risk_blocked = bool(snap.get("hard_risk_blocked")) or hard_risk_remaining > 0
        hard_risk_reason = str(snap.get("hard_risk_block_reason") or "")
        attempt_age = (
            ts - self._last_execution_attempt_ts
            if self._last_execution_attempt_ts > 0
            else 0.0
        )
        fill_age = (
            ts - self._last_successful_fill_ts
            if self._last_successful_fill_ts > 0
            else 0.0
        )
        lane_ready = (
            not balance_stale
            and not position_stale
            and failsafe_remaining <= 0
            and jurisdiction_remaining <= 0
            and not hard_risk_blocked
            and not bool(self._execution_block_reason)
            and bool(self._trading_enabled)
            and (self._trading_mode != "live" or bool(self._allow_live_trading))
        )
        go_nogo = await self._evaluate_go_no_go(now_ts=ts)
        reject_tax = go_nogo.get("reject_tax", {}) if isinstance(go_nogo.get("reject_tax"), dict) else {}
        if not reject_tax:
            reject_tax = dict(self._cached_reject_tax_metrics or {})
        deltas = go_nogo.get("deltas", {}) if isinstance(go_nogo.get("deltas"), dict) else {}

        lines = [
            f"{'🟢' if lane_ready else '🟠'} <b>LIGHTER LANE HEARTBEAT</b>",
            (
                f"<b>Ready</b> {'YES' if lane_ready else 'NO'} · "
                f"<b>Mode</b> {html.escape(self._trading_mode)} · "
                f"<b>Positions</b> {int(snap.get('positions_count', 0) or 0)}"
            ),
            (
                f"<b>Operator</b> {'🟢 GO' if go_nogo.get('go') else '🔴 NO-GO'} · "
                f"<b>Reject Tax</b> {self._to_float(reject_tax.get('reject_tax_pct'), 0.0):.1f}%"
            ),
            f"<b>Decision Source</b> {html.escape(str(go_nogo.get('source', 'bot_policy')).replace('_', ' '))}",
            (
                f"<b>Equity</b> {self._to_float(snap.get('equity_estimate'), 0.0):,.4f} · "
                f"<b>Cash</b> {self._to_float(snap.get('cash_balance'), 0.0):,.4f} · "
                f"<b>uPnL</b> {self._to_float(snap.get('unrealized_pnl'), 0.0):+,.4f}"
            ),
            (
                f"<b>Sync</b> bal={bal_age:.0f}s{'⚠️' if balance_stale else ''} · "
                f"pos={pos_age:.0f}s{'⚠️' if position_stale else ''}"
            ),
            (
                f"<b>Execution</b> last_attempt={attempt_age:.0f}s · "
                f"last_fill={fill_age:.0f}s · watchdog_streak={self._execution_watchdog_alert_streak}"
            ),
        ]
        if failsafe_remaining > 0:
            lines.append(
                f"<b>Failsafe</b> active {failsafe_remaining:.0f}s · "
                f"{html.escape(self._execution_failsafe_reason or 'watchdog')}"
            )
        if jurisdiction_remaining > 0:
            lines.append(
                f"<b>Jurisdiction Block</b> {jurisdiction_remaining:.0f}s · "
                f"{html.escape(self._jurisdiction_block_reason or 'restricted jurisdiction')}"
            )
        if hard_risk_blocked:
            lines.append(
                f"<b>Hard Risk Hold</b> {hard_risk_remaining:.0f}s · "
                f"{html.escape(hard_risk_reason or 'risk limit breached')}"
            )
        if self._execution_block_reason:
            lines.append(f"<b>Execution Block</b> {html.escape(self._execution_block_reason[:220])}")
        if not go_nogo.get("go"):
            reasons = go_nogo.get("reason_details") or go_nogo.get("reasons") or []
            if reasons:
                lines.append(f"<b>GO/NO-GO Blockers</b> {html.escape('; '.join(reasons[:2]))}")
        d1 = deltas.get("1h", {}) if isinstance(deltas.get("1h"), dict) else {}
        d6 = deltas.get("6h", {}) if isinstance(deltas.get("6h"), dict) else {}
        d24 = deltas.get("24h", {}) if isinstance(deltas.get("24h"), dict) else {}
        if d1 or d6 or d24:
            lines.append(
                f"<b>Reject Δ</b> 1h {self._to_float(d1.get('reject_tax_pct'), 0.0):.1f}% · "
                f"6h {self._to_float(d6.get('reject_tax_pct'), 0.0):.1f}% · "
                f"24h {self._to_float(d24.get('reject_tax_pct'), 0.0):.1f}%"
            )
        top_timeframe = (reject_tax.get("by_timeframe") or [{}])[0]
        if top_timeframe and top_timeframe.get("total"):
            lines.append(
                f"<b>Top Reject TF</b> {html.escape(str(top_timeframe.get('key', 'unknown')))} "
                f"{self._to_float(top_timeframe.get('reject_tax_pct'), 0.0):.1f}%"
            )

        await self._send_telegram_message("\n".join(lines), parse_mode="HTML")

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

                now_ts = time.time()
                hard_risk_event = self._hard_risk_kernel.ingest_equity_snapshot(snap, now_ts=now_ts)
                hard_risk_state = self._hard_risk_kernel.status(now_ts=now_ts)
                snap["hard_risk_kernel"] = hard_risk_state
                snap["hard_risk_blocked"] = bool(hard_risk_state.get("blocked", False))
                snap["hard_risk_block_reason"] = str(hard_risk_state.get("block_reason", ""))
                snap["hard_risk_block_remaining_sec"] = float(
                    hard_risk_state.get("blocked_for_sec", 0.0) or 0.0
                )
                if hard_risk_event:
                    await self._send_telegram_message(
                        (
                            "🛑 <b>LIGHTER HARD RISK LIMIT BREACHED</b>\n"
                            f"reason={html.escape(hard_risk_event.reason)}\n"
                            f"hold={max(0.0, hard_risk_event.blocked_until_ts - now_ts):.0f}s"
                        ),
                        parse_mode="HTML",
                    )

                await self._persist_equity_snapshot(snap, reason="progress_loop")

                if self._execution_failsafe_until_ts > 0 and now_ts >= self._execution_failsafe_until_ts:
                    if self._clear_execution_failsafe():
                        await self._send_telegram_message(
                            "🟢 <b>LIGHTER EXECUTION FAILSAFE CLEARED</b>\nHold window elapsed; entry lane re-enabled.",
                            parse_mode="HTML",
                        )

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
                            
                                "LIGHTER DATA FRESHNESS ALERT\n"
                                f"balance_sync_age={snap.get('balance_sync_age_sec')}s "
                                f"position_check_age={snap.get('position_check_age_sec')}s\n"
                                f"balance_error={snap.get('last_balance_sync_error') or 'none'}\n"
                                f"position_error={snap.get('last_position_check_error') or 'none'}"
                            
                        )

                if (
                    self._max_drawdown_alert_pct > 0
                    and drawdown_pct <= -abs(self._max_drawdown_alert_pct)
                    and (now_ts - self._last_drawdown_alert_ts) >= self._drawdown_alert_cooldown_seconds
                ):
                    self._last_drawdown_alert_ts = now_ts
                    await self._send_telegram_message(
                        
                            "LIGHTER DRAWDOWN ALERT\n"
                            f"equity={equity:.4f} baseline={baseline:.4f} peak={peak:.4f}\n"
                            f"progress={progress_pct:.2f}% drawdown={drawdown_pct:.2f}%"
                        
                    )

                if self._execution_watchdog_enabled and self._trading_enabled and self._allow_live_trading:
                    no_success_since_attempt = (
                        self._last_execution_attempt_ts > 0
                        and (
                            self._last_successful_fill_ts <= 0
                            or self._last_successful_fill_ts < self._last_execution_attempt_ts
                        )
                    )
                    attempt_age = (
                        now_ts - self._last_execution_attempt_ts
                        if self._last_execution_attempt_ts > 0
                        else 0.0
                    )
                    if (
                        no_success_since_attempt
                        and attempt_age >= self._execution_watchdog_no_fill_seconds
                        and (now_ts - self._last_execution_watchdog_alert_ts)
                        >= self._execution_watchdog_cooldown_seconds
                    ):
                        self._last_execution_watchdog_alert_ts = now_ts
                        self._execution_watchdog_alert_streak += 1
                        await self._send_telegram_message(
                            
                                "LIGHTER EXECUTION WATCHDOG ALERT\n"
                                f"streak={self._execution_watchdog_alert_streak} threshold={self._execution_failsafe_alert_threshold}\n"
                                f"no successful fill for {attempt_age:.0f}s after latest execution attempt\n"
                                f"last_error={self._last_execution_error_message or 'unknown'}\n"
                                f"lane_ready={bool(not snap.get('balance_sync_stale') and not snap.get('position_check_stale'))} "
                                f"jurisdiction_block={max(0.0, self._jurisdiction_block_until_ts - now_ts):.0f}s"
                            
                        )
                        if (
                            self._execution_failsafe_enabled
                            and self._execution_watchdog_alert_streak >= self._execution_failsafe_alert_threshold
                        ):
                            reason = (
                                f"watchdog_no_fill_{attempt_age:.0f}s "
                                f"(streak={self._execution_watchdog_alert_streak})"
                            )
                            activated = self._activate_execution_failsafe(reason, now_ts=now_ts)
                            if activated:
                                await self._send_telegram_message(
                                    (
                                        "🛑 <b>LIGHTER EXECUTION FAILSAFE ACTIVATED</b>\n"
                                        f"hold={self._execution_failsafe_hold_seconds:.0f}s · "
                                        f"reason={html.escape(reason)}\n"
                                        "Entry-like trades are blocked until hold expires."
                                    ),
                                    parse_mode="HTML",
                                )
                    elif not no_success_since_attempt and self._execution_watchdog_alert_streak > 0:
                        self._execution_watchdog_alert_streak = 0

                await self._maybe_send_lane_heartbeat(snap, now_ts=now_ts)
                await self._maybe_send_portfolio_digest(snap)
                await self._maybe_publish_assistant_brief(snap)

            except Exception as exc:
                logger.error("Progress verification error: %s", exc)

            await self._sleep_or_stop(self._progress_verify_interval_seconds)

    def _resolve_market(self, symbol: str) -> dict[str, Any]:
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

    async def _handle_risk_alert(self, alert_data: dict[str, Any]):
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
            summary = await self._close_all_positions()
            if summary.get("failed", 0) > 0:
                logger.warning(
                    "Risk close_all completed with failures | requested=%d closed=%d failed=%d",
                    summary.get("requested", 0),
                    summary.get("closed", 0),
                    summary.get("failed", 0),
                )
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
        coin = self._normalize_coin_symbol(signal.symbol)
        order_submit_started = False

        try:
            is_buy = signal.side in (TradeSide.BUY, TradeSide.LONG)
            reduce_only = bool((signal.metadata or {}).get("reduce_only", False))
            if signal.signal_type in {
                SignalType.EXIT,
                SignalType.SCALE_OUT,
                SignalType.TAKE_PROFIT,
                SignalType.STOP_LOSS,
            }:
                reduce_only = True
            entry_like = signal.signal_type in {SignalType.ENTRY, SignalType.SCALE_IN}
            strategy, timeframe = self._signal_strategy_info(signal)

            if not ignore_trading_guard:
                if not self._trading_enabled:
                    raise Exception("Trading disabled (TRADING_ENABLED=false)")
                if self._trading_mode == "live" and not self._allow_live_trading:
                    raise Exception("Live trading disabled (ALLOW_LIVE_TRADING=0)")
                if entry_like and not reduce_only:
                    failsafe_remaining = max(0.0, self._execution_failsafe_until_ts - time.time())
                    if failsafe_remaining > 0:
                        raise Exception(
                            f"Execution failsafe active ({failsafe_remaining:.0f}s remaining): "
                            f"{self._execution_failsafe_reason or 'watchdog no-fill protection'}"
                        )
                if entry_like and not reduce_only and self._jurisdiction_block_until_ts > time.time():
                    wait_s = max(0.0, self._jurisdiction_block_until_ts - time.time())
                    raise Exception(
                        f"Jurisdiction block active ({wait_s:.0f}s remaining): "
                        f"{self._jurisdiction_block_reason or 'restricted jurisdiction'}"
                    )
                if entry_like and not reduce_only:
                    can_enter, risk_reason = self._hard_risk_kernel.can_open_entry()
                    if not can_enter:
                        return self._policy_noop_result(
                            signal,
                            reason=risk_reason,
                            symbol=coin,
                        )
                if self._go_nogo_gate_enabled and entry_like and not reduce_only:
                    go_nogo = await self._evaluate_go_no_go()
                    if not go_nogo.get("go", False):
                        blocker_rows = go_nogo.get("reason_details") or go_nogo.get("reasons") or []
                        blocker_text = "; ".join(str(item) for item in blocker_rows[:2]).strip()
                        return self._policy_noop_result(
                            signal,
                            reason=f"go_no_go_block: {blocker_text or 'operator_no_go'}",
                            symbol=coin,
                        )
            if not self.transaction_api:
                raise Exception("Transaction API not initialized")
            if self._execution_block_reason:
                raise Exception(self._execution_block_reason)

            # Get market info
            market = self._resolve_market(signal.symbol)
            order_book_id = int(market.get("order_book_id", 0) or 0)
            if order_book_id <= 0:
                raise ValueError(f"No order book mapping for symbol {signal.symbol} (normalized={coin})")

            # Safety: require explicit quantity in inbound signal.
            quantity: float = 0.0
            if signal.quantity is None:
                # Allow quantity-less entry signals when target notional sizing is enabled.
                if not (entry_like and not reduce_only and self._target_order_notional_usd > 0):
                    raise ValueError("Signal quantity is required for live execution")
                if signal.metadata is None:
                    signal.metadata = {}
                signal.metadata.setdefault("auto_quantity", "target_notional")
            else:
                # Calculate quantity
                quantity = float(signal.quantity)
            signal_leverage = self._to_float(getattr(signal, "leverage", 0.0), 0.0)
            if signal_leverage > self._max_signal_leverage:
                raise ValueError(
                    f"Signal leverage {signal_leverage:.2f}x exceeds cap {self._max_signal_leverage:.2f}x"
                )
            if signal.metadata is None:
                signal.metadata = {}
            signal.metadata.setdefault("max_signal_leverage", self._max_signal_leverage)
            if signal_leverage > 0:
                signal.metadata.setdefault("requested_leverage", signal_leverage)
            applied_notional_leverage = 1.0
            if entry_like and not reduce_only and self._use_leverage_for_notional:
                leverage_hint = signal_leverage if signal_leverage > 0 else self._target_order_leverage
                applied_notional_leverage = self._clamp(
                    leverage_hint,
                    1.0,
                    self._max_signal_leverage,
                )
                signal.metadata.setdefault("sizing", {})
                signal.metadata["sizing"].setdefault("use_leverage_for_notional", True)
                signal.metadata["sizing"].setdefault(
                    "applied_notional_leverage",
                    round(float(applied_notional_leverage), 6),
                )
            current_price = 0.0
            size_decimals = self._market_size_decimals(market) or 3

            if self._single_symbol_mode and entry_like and not reduce_only:
                if self._sync_before_entry:
                    await self._check_positions()
                reversed_same_symbol = False
                existing = self.positions.get(coin)
                existing_qty = float(getattr(existing, "quantity", 0.0) or 0.0) if existing else 0.0
                if existing and existing_qty > 0:
                    existing_side = getattr(existing, "side", None)
                    existing_is_buy = existing_side in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG")
                    if existing_is_buy != bool(is_buy):
                        logger.warning(
                            "Single-symbol reversal requested for %s | flattening existing side=%s qty=%.8f first",
                            coin,
                            str(existing_side),
                            existing_qty,
                        )
                        close_result = await self._close_position_for_rotation(
                            coin,
                            reason=f"reverse_{coin}_{'long_to_short' if existing_is_buy else 'short_to_long'}",
                        )
                        await self._check_positions()
                        residual = self.positions.get(coin)
                        residual_qty = (
                            float(getattr(residual, "quantity", 0.0) or 0.0) if residual else 0.0
                        )
                        if residual_qty > 0:
                            raise ValueError(
                                f"Single-symbol reversal blocked for {coin}: "
                                f"could not flatten existing position (remaining_qty={residual_qty:.8f})"
                            )
                        signal.metadata.setdefault("rotation", {})
                        signal.metadata["rotation"].update(
                            {
                                "mode": "same_symbol_reverse",
                                "reason": "close_then_open",
                                "pre_side": str(existing_side),
                                "pre_quantity": round(existing_qty, 8),
                                "close_trade_id": str(getattr(close_result, "trade_id", "") or ""),
                            }
                        )
                        reversed_same_symbol = True
                active_symbols = self._active_position_symbols()
                if active_symbols and coin not in active_symbols:
                    current_price = await self._get_ticker(coin)
                    if not current_price:
                        raise Exception(f"Could not get current price for {coin}")
                    try:
                        await self._maybe_rotate_opportunity(
                            target_coin=coin,
                            signal=signal,
                            is_buy=is_buy,
                            reference_price=float(current_price),
                        )
                    except ValueError as exc:
                        return self._policy_noop_result(signal, reason=str(exc), symbol=coin)
                if self._entry_cooldown_seconds > 0 and not reversed_same_symbol:
                    now_ts = time.time()
                    last_ts = float(self._last_entry_ts.get(coin, 0.0) or 0.0)
                    if last_ts and (now_ts - last_ts) < self._entry_cooldown_seconds:
                        wait_s = self._entry_cooldown_seconds - (now_ts - last_ts)
                        return self._policy_noop_result(
                            signal,
                            reason=f"entry cooldown active for {coin}: wait {wait_s:.1f}s",
                            symbol=coin,
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

            if current_price <= 0:
                current_price = await self._get_ticker(coin)
            if not current_price:
                raise Exception(f"Could not get current price for {coin}")

            portfolio_notional_now = 0.0
            drawdown_pct = 0.0
            if entry_like and not reduce_only:
                snap = await self._estimate_equity_snapshot()
                portfolio_notional_now = self._to_float(snap.get("position_notional_usd"), 0.0)
                drawdown_pct = self._to_float(snap.get("drawdown_pct"), 0.0)
                if drawdown_pct == 0.0:
                    equity_now = self._to_float(snap.get("equity_estimate"), 0.0)
                    peak = self._to_float(self._equity_peak, 0.0)
                    if equity_now > 0 and peak > 0:
                        drawdown_pct = ((equity_now - peak) / peak) * 100.0

            if (
                not reduce_only
                and entry_like
                and self._target_order_notional_usd > 0
                and current_price > 0
            ):
                base_target_margin_usd = float(self._target_margin_for_signal(strategy, timeframe))
                effective_target_margin_usd = float(base_target_margin_usd)
                dynamic_factors: dict[str, float] = {}
                if self._dynamic_sizing_enabled:
                    multiplier, dynamic_factors = self._dynamic_entry_size_multiplier(
                        signal=signal,
                        coin=coin,
                        is_buy=is_buy,
                        reference_price=float(current_price),
                        portfolio_notional_usd=float(portfolio_notional_now),
                        drawdown_pct=float(drawdown_pct),
                    )
                    effective_target_margin_usd *= multiplier
                    if self._min_entry_notional_usd > 0:
                        effective_target_margin_usd = max(
                            effective_target_margin_usd,
                            float(self._min_entry_notional_usd),
                        )
                effective_target_notional = float(effective_target_margin_usd)
                if self._use_leverage_for_notional and applied_notional_leverage > 1.0:
                    effective_target_notional = (
                        float(effective_target_margin_usd) * float(applied_notional_leverage)
                    )
                signal.metadata.setdefault("sizing", {})
                signal.metadata["sizing"].update(
                    {
                        "mode": (
                            "dynamic_target_margin_x_leverage"
                            if self._dynamic_sizing_enabled and self._use_leverage_for_notional
                            else "dynamic_target_notional"
                            if self._dynamic_sizing_enabled
                            else "target_margin_x_leverage"
                            if self._use_leverage_for_notional
                            else "target_notional"
                        ),
                        "base_target_margin_usd": round(float(base_target_margin_usd), 8),
                        "effective_target_margin_usd": round(float(effective_target_margin_usd), 8),
                        "applied_notional_leverage": round(float(applied_notional_leverage), 8),
                        "effective_target_notional_usd": round(float(effective_target_notional), 8),
                        "use_leverage_for_notional": bool(self._use_leverage_for_notional),
                        "size_ramp_enabled": bool(self._size_ramp_enabled),
                        "size_ramp_key": self._size_ramp_key(strategy, timeframe),
                        "size_ramp_margin_usd": round(float(base_target_margin_usd), 8),
                        **dynamic_factors,
                    }
                )
                if self._dynamic_sizing_enabled:
                    logger.info(
                        "Dynamic sizing %s | base_margin=%.4f eff_margin=%.4f lev=%.2f gross_target=%.4f "
                        "mult=%.4f conf=%.2f ev=%.3f%% vol=%.3f%% inv=%.3f dd=%.3f%%",
                        coin,
                        float(base_target_margin_usd),
                        float(effective_target_margin_usd),
                        float(applied_notional_leverage),
                        float(effective_target_notional),
                        self._to_float(dynamic_factors.get("multiplier"), 1.0),
                        self._to_float(dynamic_factors.get("confidence"), 0.0),
                        self._to_float(dynamic_factors.get("ev_pct"), 0.0),
                        self._to_float(dynamic_factors.get("vol_pct"), 0.0),
                        self._to_float(dynamic_factors.get("inventory_ratio"), 0.0),
                        self._to_float(dynamic_factors.get("drawdown_pct"), 0.0),
                    )
                target_qty = self._quantize_qty_down(
                    float(effective_target_notional) / float(current_price),
                    size_decimals,
                )
                if target_qty <= 0:
                    raise ValueError(
                        f"Target order notional too low for {coin}: "
                        f"target={effective_target_notional} price={current_price}"
                    )
                if abs(target_qty - float(quantity)) > 1e-12:
                    logger.info(
                        "Target notional sizing applied for %s: qty %.8f -> %.8f "
                        "(margin %.2f USD, leverage %.2fx, gross %.2f USD)",
                        coin,
                        float(quantity),
                        float(target_qty),
                        float(effective_target_margin_usd),
                        float(applied_notional_leverage),
                        float(effective_target_notional),
                    )
                quantity = float(target_qty)

            logger.info(
                f"Placing {signal.side} order | Symbol: {coin} | Qty: {quantity} | OrderBookId: {order_book_id}"
            )

            if (
                not reduce_only
                and self._max_order_notional_usd > 0
                and current_price > 0
                and quantity > 0
            ):
                requested_notional = float(quantity) * float(current_price)
                if requested_notional > self._max_order_notional_usd:
                    capped_qty = self._quantize_qty_down(
                        self._max_order_notional_usd / float(current_price),
                        size_decimals,
                    )
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
            if not reduce_only:
                quantity = self._quantize_qty_down(float(quantity), size_decimals)
                if quantity <= 0:
                    raise ValueError(
                        f"Quantity rounded to zero for {coin} at size_decimals={size_decimals}"
                    )
            if (
                not reduce_only
                and entry_like
                and self._min_entry_notional_usd > 0
                and current_price > 0
            ):
                final_notional = float(quantity) * float(current_price)
                if final_notional < self._min_entry_notional_usd:
                    raise ValueError(
                        f"Entry notional too low for {coin}: "
                        f"final={final_notional:.4f} floor={self._min_entry_notional_usd:.4f}"
                    )
            if not reduce_only and current_price > 0:
                logger.info(
                    "Final entry sizing %s | qty=%.8f gross_notional=%.4f usd "
                    "(price=%.6f leverage=%.2fx)",
                    coin,
                    float(quantity),
                    float(quantity) * float(current_price),
                    float(current_price),
                    float(applied_notional_leverage),
                )

            if (
                not reduce_only
                and entry_like
                and current_price > 0
                and quantity > 0
            ):
                requested_notional = float(quantity) * float(current_price)
                projected = self._project_entry_notional(
                    coin=coin,
                    is_buy=is_buy,
                    requested_notional=float(requested_notional),
                    mark_price=float(current_price),
                    portfolio_notional_now=float(portfolio_notional_now),
                )
                current_symbol_notional = self._to_float(projected.get("current_symbol_notional"), 0.0)
                projected_symbol_notional = self._to_float(projected.get("projected_symbol_notional"), 0.0)
                projected_portfolio_notional = self._to_float(
                    projected.get("projected_portfolio_notional"),
                    0.0,
                )

                if (
                    self._max_position_notional_usd > 0
                    and projected_symbol_notional > self._max_position_notional_usd
                ):
                    headroom = max(0.0, self._max_position_notional_usd - current_symbol_notional)
                    capped_qty = self._quantize_qty_down(
                        headroom / float(current_price),
                        size_decimals,
                    )
                    capped_notional = float(capped_qty) * float(current_price)
                    min_floor = float(max(0.0, self._min_entry_notional_usd))
                    if capped_qty > 0 and (min_floor <= 0 or capped_notional >= min_floor):
                        logger.info(
                            "Symbol cap trim for %s | requested=%.4f cap=%.4f current=%.4f "
                            "projected=%.4f -> qty %.8f notional %.4f",
                            coin,
                            requested_notional,
                            self._max_position_notional_usd,
                            current_symbol_notional,
                            projected_symbol_notional,
                            capped_qty,
                            capped_notional,
                        )
                        quantity = float(capped_qty)
                        requested_notional = float(capped_notional)
                        projected_symbol_notional = current_symbol_notional + requested_notional
                    else:
                        logger.info(
                            "Entry skipped at symbol cap for %s | current=%.4f cap=%.4f projected=%.4f",
                            coin,
                            current_symbol_notional,
                            self._max_position_notional_usd,
                            projected_symbol_notional,
                        )
                        return TradeResult(
                            trade_id="noop",
                            signal_id=signal.signal_id,
                            platform=PLATFORM.value,
                            symbol=signal.symbol,
                            side=signal.side,
                            success=True,
                            metadata={
                                "noop": True,
                                "policy_reject": True,
                                "reason": "symbol_position_cap",
                                "current_symbol_notional": current_symbol_notional,
                                "projected_symbol_notional": projected_symbol_notional,
                                "cap_notional": self._max_position_notional_usd,
                                "requested_entry_notional": requested_notional,
                                "capped_entry_notional": capped_notional,
                                "applied_notional_leverage": applied_notional_leverage,
                            },
                        )

                if (
                    self._max_portfolio_notional_usd > 0
                    and projected_portfolio_notional > self._max_portfolio_notional_usd
                ):
                    portfolio_headroom = max(
                        0.0,
                        self._max_portfolio_notional_usd - float(portfolio_notional_now),
                    )
                    capped_qty = self._quantize_qty_down(
                        portfolio_headroom / float(current_price),
                        size_decimals,
                    )
                    capped_notional = float(capped_qty) * float(current_price)
                    min_floor = float(max(0.0, self._min_entry_notional_usd))
                    if capped_qty > 0 and (min_floor <= 0 or capped_notional >= min_floor):
                        logger.info(
                            "Portfolio cap trim for %s | requested=%.4f cap=%.4f now=%.4f "
                            "projected=%.4f -> qty %.8f notional %.4f",
                            coin,
                            requested_notional,
                            self._max_portfolio_notional_usd,
                            portfolio_notional_now,
                            projected_portfolio_notional,
                            capped_qty,
                            capped_notional,
                        )
                        quantity = float(capped_qty)
                        requested_notional = float(capped_notional)
                        projected_portfolio_notional = float(portfolio_notional_now) + requested_notional
                    else:
                        logger.info(
                            "Entry skipped at portfolio cap for %s | portfolio_now=%.4f cap=%.4f projected=%.4f",
                            coin,
                            portfolio_notional_now,
                            self._max_portfolio_notional_usd,
                            projected_portfolio_notional,
                        )
                        return TradeResult(
                            trade_id="noop",
                            signal_id=signal.signal_id,
                            platform=PLATFORM.value,
                            symbol=signal.symbol,
                            side=signal.side,
                            success=True,
                            metadata={
                                "noop": True,
                                "policy_reject": True,
                                "reason": "portfolio_position_cap",
                                "portfolio_notional_now": portfolio_notional_now,
                                "projected_portfolio_notional": projected_portfolio_notional,
                                "cap_notional": self._max_portfolio_notional_usd,
                                "requested_entry_notional": requested_notional,
                                "capped_entry_notional": capped_notional,
                                "applied_notional_leverage": applied_notional_leverage,
                            },
                        )

                # Skip tiny additive orders on an already-open same-symbol position.
                same_direction = bool(self._to_float(projected.get("same_direction"), 0.0) >= 0.5)
                if (
                    self._cap_near_churn_enabled
                    and self._max_position_notional_usd > 0
                    and current_symbol_notional > 0
                    and requested_notional > 0
                    and same_direction
                ):
                    cap_ratio = current_symbol_notional / max(
                        0.0001, float(self._max_position_notional_usd)
                    )
                    if cap_ratio >= self._cap_near_churn_ratio:
                        existing_position = self.positions.get(coin)
                        incoming_ev = self._estimate_signal_ev_pct(
                            signal,
                            coin=coin,
                            is_buy=is_buy,
                            reference_price=float(current_price),
                            expected_notional_usd=float(requested_notional),
                        )
                        current_ev = (
                            self._estimate_position_ev_pct(coin, existing_position)
                            if existing_position is not None
                            else 0.0
                        )
                        ev_edge = incoming_ev - current_ev
                        if (
                            incoming_ev < self._cap_near_min_net_ev_pct
                            or ev_edge < self._cap_near_min_ev_edge_pct
                        ):
                            logger.info(
                                "Entry skipped near cap for %s | ratio=%.3f incoming_ev=%.3f%% current_ev=%.3f%% edge=%.3f%%",
                                coin,
                                cap_ratio,
                                incoming_ev,
                                current_ev,
                                ev_edge,
                            )
                            return TradeResult(
                                trade_id="noop",
                                signal_id=signal.signal_id,
                                platform=PLATFORM.value,
                                symbol=signal.symbol,
                                side=signal.side,
                                success=True,
                                metadata={
                                    "noop": True,
                                    "policy_reject": True,
                                    "reason": "cap_near_churn",
                                    "current_symbol_notional": current_symbol_notional,
                                    "requested_entry_notional": requested_notional,
                                    "cap_notional": self._max_position_notional_usd,
                                    "cap_ratio": cap_ratio,
                                    "incoming_ev_pct": incoming_ev,
                                    "current_ev_pct": current_ev,
                                    "ev_edge_pct": ev_edge,
                                    "min_net_ev_pct": self._cap_near_min_net_ev_pct,
                                    "min_ev_edge_pct": self._cap_near_min_ev_edge_pct,
                                    "applied_notional_leverage": applied_notional_leverage,
                                },
                            )

                if (
                    self._min_add_notional_usd > 0
                    and current_symbol_notional > 0
                    and requested_notional > 0
                    and requested_notional < self._min_add_notional_usd
                ):
                    logger.info(
                        "Entry skipped on %s: add-notional %.4f below min-add floor %.4f (current_symbol_notional=%.4f)",
                        coin,
                        requested_notional,
                        self._min_add_notional_usd,
                        current_symbol_notional,
                    )
                    return TradeResult(
                        trade_id="noop",
                        signal_id=signal.signal_id,
                        platform=PLATFORM.value,
                        symbol=signal.symbol,
                        side=signal.side,
                        success=True,
                        metadata={
                            "noop": True,
                            "policy_reject": True,
                            "reason": "add_notional_below_floor",
                            "current_symbol_notional": current_symbol_notional,
                            "requested_entry_notional": requested_notional,
                            "min_add_notional_usd": self._min_add_notional_usd,
                            "applied_notional_leverage": applied_notional_leverage,
                        },
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
            if entry_like and not reduce_only:
                tp_val = self._to_float(getattr(signal, "take_profit", None), 0.0)
                sl_val = self._to_float(getattr(signal, "stop_loss", None), 0.0)
                if tp_val <= 0 or sl_val <= 0:
                    return self._policy_noop_result(
                        signal,
                        reason="missing_tp_sl_after_risk_defaults",
                        symbol=coin,
                    )
                if is_buy and not (sl_val < float(current_price) < tp_val):
                    return self._policy_noop_result(
                        signal,
                        reason=(
                            f"invalid_tp_sl_geometry long sl={sl_val:.8f} "
                            f"mark={float(current_price):.8f} tp={tp_val:.8f}"
                        ),
                        symbol=coin,
                    )
                if (not is_buy) and not (tp_val < float(current_price) < sl_val):
                    return self._policy_noop_result(
                        signal,
                        reason=(
                            f"invalid_tp_sl_geometry short tp={tp_val:.8f} "
                            f"mark={float(current_price):.8f} sl={sl_val:.8f}"
                        ),
                        symbol=coin,
                    )

            # Apply slippage for market order
            limit_price = current_price * 1.05 if is_buy else current_price * 0.95

            try:
                async with self._order_submit_lock:
                    # Circuit breaker gate — raises CircuitBreakerOpen if venue is halted.
                    self._circuit_breaker.check()

                    submit_attempts = max(1, int(self._order_submit_retry_attempts))
                    result = None
                    for submit_attempt in range(1, submit_attempts + 1):
                        order_submit_started = True
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
                        except Exception as submit_err:
                            if (
                                submit_attempt < submit_attempts
                                and self._should_retry_order_submit_failure(submit_err)
                            ):
                                wait_s = float(self._order_submit_retry_backoff_seconds) * submit_attempt
                                logger.warning(
                                    "Order submit transient error on %s (attempt %d/%d): %s; retrying in %.2fs",
                                    coin,
                                    submit_attempt,
                                    submit_attempts,
                                    submit_err,
                                    wait_s,
                                )
                                await self._sleep_or_stop(wait_s)
                                continue
                            raise

                        if result and result.get("success"):
                            break

                        err_msg = str((result or {}).get("error", "") or "")
                        if (
                            submit_attempt < submit_attempts
                            and self._should_retry_order_submit_failure(err_msg)
                        ):
                            wait_s = float(self._order_submit_retry_backoff_seconds) * submit_attempt
                            logger.warning(
                                "Order submit transient rejection on %s (attempt %d/%d): %s; retrying in %.2fs",
                                coin,
                                submit_attempt,
                                submit_attempts,
                                err_msg,
                                wait_s,
                            )
                            await self._sleep_or_stop(wait_s)
                            continue
                        break

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
                    strategy, timeframe = self._signal_strategy_info(signal)
                    pos_meta = {
                        "source": str(signal.source or ""),
                        "signal_id": str(signal.signal_id or ""),
                        "strategy": strategy or "",
                        "timeframe": timeframe or "",
                        "confidence": self._to_float(getattr(signal, "confidence", 0.0), 0.0),
                        "ev_score_pct": self._estimate_signal_ev_pct(
                            signal,
                            coin=coin,
                            is_buy=is_buy,
                            reference_price=float(fill_price if fill_price > 0 else current_price),
                        ),
                        "reasoning": self._compact_reasoning(signal.metadata or {}),
                        "opened_at": datetime.now(UTC).isoformat(),
                    }
                    self.positions[coin] = Position(
                        position_id=str(result.get("order_id", "")),
                        platform=PLATFORM.value,
                        symbol=coin,
                        side=signal.side,
                        quantity=filled_qty,
                        entry_price=fill_price if fill_price > 0 else limit_price,
                        stop_loss=signal.stop_loss,
                        take_profit=signal.take_profit,
                        metadata=pos_meta,
                    )
                    if fill_price > 0:
                        self._record_price_point(coin, fill_price)
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
                self._set_jurisdiction_block(str(error_msg))
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
            err_text = str(e or "")
            if not order_submit_started and self._should_treat_as_preflight_noop(err_text):
                logger.info(
                    "Preflight policy-noop on %s: signal=%s reason=%s",
                    PLATFORM.value,
                    str(getattr(signal, "signal_id", "") or ""),
                    err_text,
                )
                return self._policy_noop_result(signal, reason=err_text, symbol=coin)

            self._set_jurisdiction_block(err_text)
            self.trades_failed += 1
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.error(f"Lighter Execution Failed: {err_text}")
            return TradeResult(
                trade_id="",
                signal_id=signal.signal_id,
                platform=PLATFORM.value,
                symbol=signal.symbol,
                side=signal.side,
                success=False,
                error_message=err_text,
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
        last_error: Exception | None = None
        for args, kwargs in attempts:
            try:
                return await self._call_lighter_api(self.transaction_api.next_nonce, *args, **kwargs)
            except TypeError as exc:
                last_error = exc
                continue
        if last_error:
            raise last_error
        raise RuntimeError("Unable to resolve Lighter nonce signature")

    def _sign_transaction(self, tx_body: dict) -> str:
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
        market_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
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
        order_params: dict[str, Any],
        signature: str,
        signal_id: str,
    ) -> dict[str, Any]:
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

        last_error: Exception | None = None
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

    async def _get_ticker(self, symbol: str) -> float | None:
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
            last_error: Exception | None = None
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
                px = float(details.mid_price)
                self._record_price_point(symbol, px)
                return px
            elif details and hasattr(details, "last_price"):
                px = float(details.last_price)
                self._record_price_point(symbol, px)
                return px
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
                                self._record_price_point(symbol, px)
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

    def _maybe_adjust_position_risk_levels(self, symbol: str, position: Position) -> bool:
        """
        Dynamically adjust TP/SL based on short-term regime and volatility.
        Returns True when risk levels were changed.
        """
        if not self._dynamic_risk_enabled:
            return False

        now_ts = time.time()
        last_update = float(self._last_dynamic_risk_update_ts.get(symbol, 0.0))
        if (now_ts - last_update) < self._dynamic_risk_update_seconds:
            return False

        qty = self._to_float(getattr(position, "quantity", 0.0), 0.0)
        entry = self._to_float(getattr(position, "entry_price", 0.0), 0.0)
        if qty <= 0 or entry <= 0:
            return False

        is_long = getattr(position, "side", None) in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG")
        current_price = self._to_float(getattr(position, "current_price", 0.0), 0.0)

        tp = self._to_float(getattr(position, "take_profit", 0.0), 0.0)
        sl = self._to_float(getattr(position, "stop_loss", 0.0), 0.0)
        base_tp_pct = (
            abs((tp - entry) / entry) * 100.0
            if tp > 0
            else max(0.01, self._default_take_profit_pct)
        )
        base_sl_pct = (
            abs((entry - sl) / entry) * 100.0
            if sl > 0
            else max(0.01, self._default_stop_loss_pct)
        )

        stats = self._market_stats_for_symbol(symbol)
        drift_pct = self._to_float(stats.get("drift_pct"), 0.0)
        vol_pct = self._to_float(stats.get("vol_pct"), 0.0)
        favorable = (drift_pct >= 0 and is_long) or (drift_pct <= 0 and (not is_long))

        tp_factor = 1.0
        sl_factor = 1.0
        if favorable:
            tp_factor += min(0.6, (abs(drift_pct) / 100.0) * self._dynamic_tp_trend_boost)
            sl_factor *= max(0.35, 1.0 - (self._dynamic_sl_tighten / 100.0))
        else:
            tp_factor *= max(0.4, 1.0 - (self._dynamic_sl_tighten / 100.0))
            sl_factor *= max(0.2, 1.0 - ((self._dynamic_sl_tighten * 1.2) / 100.0))

        vol_boost = min(0.8, (vol_pct / 100.0) * self._dynamic_volatility_widen)
        tp_factor *= (1.0 + vol_boost * 0.6)
        sl_factor *= (1.0 + vol_boost)

        next_tp_pct = max(0.05, base_tp_pct * tp_factor)
        next_sl_pct = max(0.03, base_sl_pct * sl_factor)

        if is_long:
            next_tp = entry * (1.0 + next_tp_pct / 100.0)
            next_sl = entry * (1.0 - next_sl_pct / 100.0)
            if current_price > 0 and current_price >= entry * 1.002:
                next_sl = max(next_sl, entry * 1.0005)
        else:
            next_tp = entry * (1.0 - next_tp_pct / 100.0)
            next_sl = entry * (1.0 + next_sl_pct / 100.0)
            if current_price > 0 and current_price <= entry * 0.998:
                next_sl = min(next_sl, entry * 0.9995)

        next_tp = round(float(next_tp), 8)
        next_sl = round(float(next_sl), 8)
        if next_tp <= 0 or next_sl <= 0:
            return False

        changed = False
        if tp <= 0 or abs(next_tp - tp) / max(abs(tp), 1e-9) > 0.015:
            position.take_profit = next_tp
            changed = True
        if sl <= 0 or abs(next_sl - sl) / max(abs(sl), 1e-9) > 0.015:
            position.stop_loss = next_sl
            changed = True

        if changed:
            if not isinstance(position.metadata, dict):
                position.metadata = {}
            position.metadata["risk_regime"] = {
                "drift_pct": round(drift_pct, 4),
                "vol_pct": round(vol_pct, 4),
                "favorable": bool(favorable),
                "tp_factor": round(tp_factor, 4),
                "sl_factor": round(sl_factor, 4),
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._last_dynamic_risk_update_ts[symbol] = now_ts
            logger.info(
                "Dynamic risk update %s | TP %.6f -> %.6f | SL %.6f -> %.6f | drift=%+.3f%% vol=%.3f%% favorable=%s",
                symbol,
                tp,
                next_tp,
                sl,
                next_sl,
                drift_pct,
                vol_pct,
                favorable,
            )
        return changed

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

            next_positions: dict[str, Position] = {}

            for pos in raw_positions:
                getv = pos.get if isinstance(pos, dict) else lambda k, d=None: getattr(pos, k, d)

                try:
                    size = float(getv("size", getv("position", 0)))
                except (TypeError, ValueError):
                    size = 0.0
                # Respect explicit sign metadata from exchange payloads.
                # Some account schemas provide absolute `size` plus a separate
                # `sign` field; without this, shorts can be misread as longs.
                if abs(size) > 0:
                    try:
                        sign = float(getv("sign", 0) or 0)
                    except (TypeError, ValueError):
                        sign = 0.0
                    if sign < 0:
                        size = -abs(size)
                    elif sign > 0:
                        size = abs(size)
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
                        metadata={"source": "exchange_sync"},
                    )
                else:
                    existing.side = side
                    existing.quantity = qty
                    if entry_price > 0:
                        existing.entry_price = entry_price
                    if not isinstance(existing.metadata, dict):
                        existing.metadata = {}
                    existing.metadata.setdefault("source", "exchange_sync")
                if not isinstance(existing.metadata, dict):
                    existing.metadata = {}
                existing.metadata.setdefault("opened_at", datetime.now(UTC).isoformat())

                if current_price > 0:
                    existing.current_price = current_price
                    self._record_price_point(symbol, current_price)
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
                self._risk_exit_attempted_at.clear()
                self._risk_exit_reconcile_hold_until.clear()
            else:
                self._empty_position_snapshot_streak = 0

            self.positions = next_positions
            for symbol in next_positions:
                self._risk_exit_reconcile_hold_until.pop(symbol, None)

        except asyncio.CancelledError:
            return
        except Exception as e:
            if self._shutdown_event.is_set():
                return
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

            hold_until = float(self._risk_exit_reconcile_hold_until.get(symbol, 0.0))
            if hold_until > now:
                continue
            if hold_until > 0:
                self._risk_exit_reconcile_hold_until.pop(symbol, None)

            self._maybe_adjust_position_risk_levels(symbol, position)

            # Time-based turnover guard: recycle stale positions so overnight flow
            # can continue without waiting indefinitely for TP/SL only exits.
            if self._max_position_hold_seconds > 0:
                opened_ts = self._position_opened_ts(position)
                hold_age = (now - opened_ts) if opened_ts > 0 else 0.0
                if hold_age >= self._max_position_hold_seconds:
                    last_attempt = float(self._risk_exit_attempted_at.get(symbol, 0.0))
                    if now - last_attempt < self._risk_exit_cooldown_seconds:
                        continue
                    self._risk_exit_attempted_at[symbol] = now

                    is_long = position.side in (TradeSide.BUY, TradeSide.LONG, "BUY", "LONG")
                    exit_side = TradeSide.SELL if is_long else TradeSide.BUY
                    exit_signal = TradeSignal(
                        signal_id=f"risk-max-hold-{symbol}-{int(now * 1000)}",
                        symbol=symbol,
                        side=exit_side,
                        signal_type=SignalType.EXIT,
                        confidence=1.0,
                        source=f"{SERVICE_NAME}-risk-guard",
                        quantity=qty,
                        metadata={
                            "reduce_only": True,
                            "risk_exit": "max_hold_timeout",
                            "origin": "max_hold_guard",
                            "position_side": str(position.side),
                            "exit_side": str(exit_side),
                            "hold_age_sec": round(hold_age, 3),
                            "max_hold_sec": float(self._max_position_hold_seconds),
                        },
                    )
                    logger.warning(
                        "Risk exit trigger max_hold_timeout on %s | position_side=%s exit_side=%s "
                        "hold_age=%.1fs max_hold=%.1fs qty=%s",
                        symbol,
                        str(position.side),
                        str(exit_side),
                        hold_age,
                        self._max_position_hold_seconds,
                        qty,
                    )
                    result = await self._execute_trade(exit_signal)
                    if not (result.metadata or {}).get("noop"):
                        await publish("trade-executed", result)
                    filled_qty = self._to_float(getattr(result, "filled_quantity", 0.0), 0.0)
                    result_meta = result.metadata or {}
                    noop_reason = str(result_meta.get("reason", "") or "")
                    if result.success and filled_qty > 0:
                        hold_for = max(
                            self._risk_exit_reconcile_hold_seconds,
                            float(self._position_check_interval_seconds)
                            * float(self._empty_position_confirmations),
                        )
                        self._risk_exit_reconcile_hold_until[symbol] = now + hold_for
                        self._risk_exit_attempted_at[symbol] = now
                        logger.info(
                            "Risk exit fill on %s; pausing retries for %.1fs pending reconciliation",
                            symbol,
                            hold_for,
                        )
                    elif result.success and bool(result_meta.get("noop")) and noop_reason in {
                        "reduce_only_no_position",
                        "reduce_only_quantity_zero",
                    }:
                        hold_for = max(
                            self._risk_exit_reconcile_hold_seconds,
                            float(self._position_check_interval_seconds)
                            * float(self._empty_position_confirmations),
                        )
                        self._risk_exit_reconcile_hold_until[symbol] = now + hold_for
                        logger.info(
                            "Risk exit noop on %s (%s); pausing retries for %.1fs pending reconciliation",
                            symbol,
                            noop_reason,
                            hold_for,
                        )
                    elif result.success and filled_qty <= 0:
                        hold_for = max(
                            self._risk_exit_reconcile_hold_seconds,
                            float(self._position_check_interval_seconds)
                            * float(self._empty_position_confirmations),
                        )
                        self._risk_exit_reconcile_hold_until[symbol] = now + hold_for
                        logger.info(
                            "Risk exit accepted-no-fill on %s; pausing retries for %.1fs pending reconciliation",
                            symbol,
                            hold_for,
                        )
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
                    "position_side": str(position.side),
                    "exit_side": str(exit_side),
                },
            )

            logger.warning(
                "Risk exit trigger %s on %s | position_side=%s exit_side=%s "
                "price=%s tp=%s sl=%s qty=%s",
                reason,
                symbol,
                str(position.side),
                str(exit_side),
                price,
                tp,
                sl,
                qty,
            )
            result = await self._execute_trade(exit_signal)
            if not (result.metadata or {}).get("noop"):
                await publish("trade-executed", result)
            filled_qty = self._to_float(getattr(result, "filled_quantity", 0.0), 0.0)
            result_meta = result.metadata or {}
            noop_reason = str(result_meta.get("reason", "") or "")
            if result.success and filled_qty > 0:
                hold_for = max(
                    self._risk_exit_reconcile_hold_seconds,
                    float(self._position_check_interval_seconds)
                    * float(self._empty_position_confirmations),
                )
                self._risk_exit_reconcile_hold_until[symbol] = now + hold_for
                self._risk_exit_attempted_at[symbol] = now
                logger.info(
                    "Risk exit fill on %s (%s); pausing retries for %.1fs pending reconciliation",
                    symbol,
                    reason,
                    hold_for,
                )
            elif result.success and bool(result_meta.get("noop")) and noop_reason in {
                "reduce_only_no_position",
                "reduce_only_quantity_zero",
            }:
                hold_for = max(
                    self._risk_exit_reconcile_hold_seconds,
                    float(self._position_check_interval_seconds)
                    * float(self._empty_position_confirmations),
                )
                self._risk_exit_reconcile_hold_until[symbol] = now + hold_for
                logger.info(
                    "Risk exit noop on %s (%s); pausing retries for %.1fs pending reconciliation",
                    symbol,
                    noop_reason,
                    hold_for,
                )
            elif result.success and filled_qty <= 0:
                hold_for = max(
                    self._risk_exit_reconcile_hold_seconds,
                    float(self._position_check_interval_seconds)
                    * float(self._empty_position_confirmations),
                )
                self._risk_exit_reconcile_hold_until[symbol] = now + hold_for
                logger.info(
                    "Risk exit accepted-no-fill on %s; pausing retries for %.1fs pending reconciliation",
                    symbol,
                    hold_for,
                )

    async def _close_all_positions(self) -> dict[str, int]:
        """Close all positions on Lighter."""
        summary = {"requested": 0, "closed": 0, "failed": 0}
        try:
            # Refresh local view first so close-all uses latest exchange state.
            await self._check_positions()
            if not self.positions:
                logger.info("Close-all requested but no local positions are tracked")
                return summary

            for symbol, position in list(self.positions.items()):
                try:
                    qty = float(getattr(position, "quantity", 0.0) or 0.0)
                except (TypeError, ValueError):
                    qty = 0.0
                if qty <= 0:
                    continue

                summary["requested"] += 1
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
                    confidence=1.0,
                    quantity=abs(qty),
                    source="risk-close-all",
                    metadata={"reduce_only": True, "origin": "risk_close_all"},
                )
                result = await self._execute_trade(exit_signal, ignore_trading_guard=True)
                filled_qty = self._to_float(getattr(result, "filled_quantity", 0.0), 0.0)
                if result.success and (filled_qty > 0 or (result.metadata or {}).get("noop")):
                    summary["closed"] += 1
                    # Clear local state immediately for successfully closed symbols so
                    # follow-up entries are not blocked by stale local position notional.
                    self.positions.pop(symbol, None)
                    self._risk_exit_attempted_at.pop(symbol, None)
                    self._last_entry_ts.pop(symbol, None)
                    self._empty_position_snapshot_streak = 0
                else:
                    summary["failed"] += 1
                    logger.error(
                        "Close-all failed for %s: %s",
                        symbol,
                        result.error_message or "unknown_error",
                    )
            logger.info(
                "Close-all complete | requested=%d closed=%d failed=%d",
                summary["requested"],
                summary["closed"],
                summary["failed"],
            )
        except Exception as e:
            logger.error(f"Close all error: {e}")
            summary["failed"] = max(summary["failed"], 1)
        return summary

    def get_status(self) -> dict[str, Any]:
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
            "min_entry_notional_usd": self._min_entry_notional_usd,
            "target_order_notional_usd": self._target_order_notional_usd,
            "size_ramp_enabled": self._size_ramp_enabled,
            "size_ramp_min_margin_usd": self._size_ramp_min_margin_usd,
            "size_ramp_max_margin_usd": self._size_ramp_max_margin_usd,
            "size_ramp_step_margin_usd": self._size_ramp_step_margin_usd,
            "jurisdiction_block_remaining_sec": max(
                0.0, self._jurisdiction_block_until_ts - time.time()
            ),
            "hard_risk_kernel": self._hard_risk_kernel.status(),
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
    logger.info("LIGHTER BOT SERVICE (L2 Order Book)")
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
