import asyncio
import hashlib
import json
import os
import signal
import sys
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional, Set

import aiohttp
import uvloop
from src.ai.chat_intent import ChatIntentEngine
from src.ai.gemini_guard import GeminiGuard
from src.collaboration.forum import SapphireForumService
from src.collaboration.reputation import BotReputationService
from src.collaboration.swarm import SwarmAggregator
from src.collaboration.learning import SwarmLearning
from src.collaboration.molthub_outreach import MolthubOutreach
from src.collaboration.task_manager import TaskManager
from src.execution.dispatcher import dispatcher
from src.execution.portfolio import PortfolioTracker
from src.feeds.market_data import MarketDataAggregator
from src.signals.alpha_scanner import AlphaSignalScanner
from src.signals.grid_trader import GridSignalPlanner


from src.telegram_handlers import dispatch_control_command
from src.api_handlers import (
    handle_market_ohlc,
    handle_platform_status,
    handle_routing_info,
    handle_performance_stats,
    handle_system_logs,
    handle_control_status,

    handle_security_skills_status,
    handle_security_skill_scan,
    handle_forum_topics,
    handle_forum_topic_detail,
    handle_forum_create_topic,
    handle_forum_replies,
    handle_forum_scout_status,
    handle_forum_scout_register,
    handle_forum_scout_publish,
)
from src.security.skill_auditor import SkillAuditor
from src.security.virustotal_scanner import VirusTotalSkillScanner
from src.security.prompt_sanitizer import sanitize_for_prompt, log_injection_attempt
from src.security.agent_permissions import gate, Capability, PermissionDenied, ApprovalPolicy
from src.strategy.engine import AlphaStrategyEngine

# Add shared library to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.error_classifier import ErrorCategory, ErrorSeverity, classify_error
from shared.enhanced_episodic_memory import EnhancedMemoryBank, MarketSnapshot
from shared.dual_speed_cognition import DualSpeedCognition, CognitionRequest, CognitionSpeed
from health import start_health_server
from smart_notifications import notification_manager
from telegram_bot import SAPPHIRE, OBSIDIAN, EMERALD

# Install uvloop as the default event loop policy
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# Configure high-performance logging
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")


class TelegramRateLimiter:
    """Per-action rate limiter for Telegram commands."""

    # Critical actions (mutable trading state)
    CRITICAL_ACTIONS = frozenset({
        "KILL", "HALT", "HALT_TRADING", "RESUME", "RESUME_TRADING",
        "BUY", "SELL", "CLOSE", "SET_EXECUTION_STAGE", "SET_DEX_EXECUTION_STAGE",
        "SET_ALLOCATION", "DEALLOCATE", "APPROVE_SESSION", "REJECT_SESSION",
        "APPROVE_ALL_SESSIONS", "REP_BAN_BOT", "MEDIA_PUBLISH", "MEDIA_DISPATCH",
    })

    # Read-only actions (safe, higher limit)
    READONLY_ACTIONS = frozenset({
        "STATUS", "CONTROL_STATUS", "HEARTBEAT", "PING", "MARKET_PRICES", "PRICES",
        "PORTFOLIO", "POSITIONS", "MEMORY_STATUS", "COGNITION_STATUS",
        "GATE_STATS", "PERMISSIONS", "PERM_STATS", "SKILL_AUDIT_STATS",
        "FORUM_TOP_TOPICS", "FORUM_AGENTS", "REP_LEADERBOARD", "SWARM_STATS",
        "LEARN_REPORT", "LEARN_SUMMARY", "TASK_LIST", "TASK_REPORT",
        "SCOUT_STATUS", "FORUM_SCOUT_STATUS", "SECURITY_STATUS", "VT_STATUS",
        "MEDIA_STATUS", "MEDIA_QUEUE_STATUS", "OUTREACH_STATS",
    })

    def __init__(self):
        self._windows: Dict[str, Deque[float]] = defaultdict(deque)
        self._limits = {
            "critical": 3,   # 3/min for trading-critical
            "default": 10,   # 10/min for standard
            "readonly": 30,  # 30/min for read-only
        }

    def _tier(self, action: str) -> str:
        upper = action.upper()
        if upper in self.CRITICAL_ACTIONS:
            return "critical"
        if upper in self.READONLY_ACTIONS:
            return "readonly"
        return "default"

    def check(self, action: str) -> bool:
        tier = self._tier(action)
        limit = self._limits[tier]
        now = time.time()
        key = f"tg:{tier}"
        window = self._windows[key]

        # Purge entries older than 60s
        while window and now - window[0] > 60:
            window.popleft()

        if len(window) >= limit:
            logger.warning(f"🛡️ Telegram rate limit ({tier}:{limit}/min) hit for action={action}")
            return False

        window.append(now)
        return True


class AlphaEngine:
    def __init__(self):
        self.running = False
        self._telegram_rate_limiter = TelegramRateLimiter()
        self.market_data = MarketDataAggregator()
        self.strategy = AlphaStrategyEngine(self.market_data)
        self.portfolio = PortfolioTracker()

        # Cognitive systems — episodic memory and dual-speed cognition
        self.memory = EnhancedMemoryBank()
        self.cognition = DualSpeedCognition()
        self._cognition_enabled = bool(
            os.getenv("SAPPHIRE_COGNITION_ENABLED", "true").strip().lower()
            in ("true", "1", "yes")
        )
        self._memory_enabled = bool(
            os.getenv("SAPPHIRE_EPISODIC_MEMORY_ENABLED", "true").strip().lower()
            in ("true", "1", "yes")
        )

        # Skill security auditor for Molthub supply-chain monitoring
        self.skill_auditor = SkillAuditor(
            auditor_id=os.getenv("SAPPHIRE_SCOUT_AGENT_ID", "SAPPHIRE_SCOUT")
        )

        requested_stage = self._parse_execution_stage_token(
            os.getenv("SAPPHIRE_DEX_EXECUTION_STAGE", "paper")
        )
        self._dex_execution_stage = requested_stage or "paper"
        self.strategy.set_execution_stage(self._dex_execution_stage)
        self._dex_stage_updated_at = int(time.time())

        # Telegram Bot for Notifications & Commands
        from telegram_bot import TelegramPlatformBot

        token = os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self._telegram_chat_id = str(chat_id or "").strip()
        logger.info(f"Alpha Hub: TELEGRAM_BOT_TOKEN is {'set' if token else 'NOT SET'}")
        self.telegram = TelegramPlatformBot(
            bot_token=token, 
            chat_id=chat_id, 
            command_callback=self._handle_telegram_command,
            message_callback=self._handle_telegram_message
        )
        # Initialize Gemini Guard
        self.ai = GeminiGuard(telegram_bot=self.telegram)
        self.chat_intent = ChatIntentEngine(self.ai)

        self.tv_autonomy = None

        self._heartbeat_task = None
        self._autonomy_task = None
        self._kill_switch_active = self._env_flag(
            "SAPPHIRE_KILL_SWITCH_ACTIVE", default=False
        )
        self._heartbeat_interval_seconds = max(60, int(os.getenv("TELEGRAM_HEARTBEAT_INTERVAL_SECONDS", "900")))
        self._deallocation_failure_threshold = max(1, int(os.getenv("DEALLOCATION_FAILURE_THRESHOLD", "3")))
        self._deallocation_cooldown_seconds = max(60, int(os.getenv("DEALLOCATION_COOLDOWN_SECONDS", "900")))
        self._default_venue_allocation = max(
            0.0, min(1.0, float(os.getenv("DEFAULT_VENUE_ALLOCATION", "1.0")))
        )
        self._telegram_webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL", "").strip()
        # Prefer the Sapphire-scoped secret name, but keep legacy fallback for now.
        self._telegram_webhook_secret = (
            os.getenv("SAPPHIRE_TELEGRAM_WEBHOOK_SECRET", "").strip()
            or os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
        )
        self._control_api_token = os.getenv("SAPPHIRE_CONTROL_API_TOKEN", "").strip()
        self._telegram_webhook_mode = bool(self._telegram_webhook_url)
        self._full_autonomy_enabled = self._env_flag("SAPPHIRE_FULL_AUTONOMY_ENABLED", default=True)
        self._autonomy_allow_code_changes = self._env_flag(
            "SAPPHIRE_AUTONOMY_ALLOW_CODE_CHANGES", default=False
        )
        self._autonomy_allow_gcloud_changes = self._env_flag(
            "SAPPHIRE_AUTONOMY_ALLOW_GCLOUD_CHANGES", default=False
        )
        self._autonomy_dry_run = self._env_flag("SAPPHIRE_AUTONOMY_DRY_RUN", default=False)
        self._autonomy_require_owner_approval = self._env_flag(
            "SAPPHIRE_AUTONOMY_REQUIRE_OWNER_APPROVAL", default=False
        )
        self._autonomy_loop_seconds = max(
            300, int(os.getenv("SAPPHIRE_AUTONOMY_LOOP_SECONDS", "900"))
        )
        self._autonomy_min_dispatch_interval_seconds = max(
            120,
            int(os.getenv("SAPPHIRE_AUTONOMY_MIN_DISPATCH_INTERVAL_SECONDS", "600")),
        )
        self._autonomy_last_dispatch_at = 0.0
        self._autonomy_last_trigger = ""
        self._autonomy_dispatch_count = 0
        self._autonomy_session_history_max = max(
            20, int(os.getenv("SAPPHIRE_AUTONOMY_SESSION_HISTORY_MAX", "200"))
        )
        self._autonomy_sessions: Dict[str, Dict[str, Any]] = {}
        self._latest_autonomy_session_key = ""
        # Multi-agent dispatch history (last N dispatches per agent)
        self._agent_dispatch_history: Dict[str, list] = {
            "OBSIDIAN": [], "EMERALD": [], "SAPPHIRE": [],
        }
        self._agent_dispatch_history_max = 50
        # Graduated escalation: risk-based approval routing
        self._approval_policy = ApprovalPolicy()
        self._proposals: Dict[str, Dict[str, Any]] = {}
        self._proposal_counter = 0
        self._started_at = time.time()
        self._system_log_max_entries = max(100, int(os.getenv("SYSTEM_LOG_MAX_ENTRIES", "500")))
        self._system_logs: Deque[Dict[str, Any]] = deque(maxlen=self._system_log_max_entries)
        self.forum = SapphireForumService()
        self.reputation = BotReputationService()
        self.swarm = SwarmAggregator(reputation=self.reputation)
        self.learning = SwarmLearning()
        self.outreach = MolthubOutreach()
        self.tasks = TaskManager()
        self.vt_scanner = VirusTotalSkillScanner()
        # Phase 6: Social Media Manager
        from src.media.manager import MediaManager
        from src.media.content_generator import ContentGenerator
        self.media_manager = MediaManager(telegram_bot=self.telegram)
        self.content_generator = ContentGenerator(gemini_guard=self.ai)
        self._media_publish_task: Optional[asyncio.Task[Any]] = None
        # Phase 9: OpenClaw Autonomous Operations
        from src.openclaw_dispatch import OpenClawDispatcher
        from src.ci_feedback import CIFeedbackProcessor
        self.openclaw_dispatcher = OpenClawDispatcher()
        self.ci_feedback = CIFeedbackProcessor(
            task_manager=self.tasks,
            telegram_bot=self.telegram,
        )
        # Phase 8: Prediction Market Intelligence
        from src.feeds.prediction_aggregator import PredictionAggregator
        self.prediction_aggregator = PredictionAggregator()
        self.swarm._prediction_aggregator = self.prediction_aggregator
        self._prediction_market_task: Optional[asyncio.Task[Any]] = None
        self._prediction_forum_task: Optional[asyncio.Task[Any]] = None
        # Internal alpha signal scanner — autonomous trade idea generation
        self.alpha_scanner = AlphaSignalScanner(
            market_data=self.market_data,
            cognition=self.cognition,
            memory=self.memory,
            strategy=self.strategy,
            prediction_aggregator=self.prediction_aggregator,
        )
        self._alpha_scanner_task: Optional[asyncio.Task[Any]] = None
        # Grid trader — leveraged grid-style signal generator
        self.grid_trader = GridSignalPlanner(
            market_data=self.market_data,
            strategy=self.strategy,
        )
        self._grid_trader_task: Optional[asyncio.Task[Any]] = None

        self._trade_metrics: Dict[str, float] = {
            "total_trades": 0.0,
            "wins": 0.0,
            "losses": 0.0,
            "realized_pnl": 0.0,
        }
        self._min_notional_by_venue: Dict[str, float] = {
            "ASTER": max(0.0, float(os.getenv("SAPPHIRE_MIN_NOTIONAL_ASTER", "5.0"))),
            "LIGHTER": max(0.0, float(os.getenv("SAPPHIRE_MIN_NOTIONAL_LIGHTER", "10.0"))),
        }
        self._min_notional_buffer_pct = max(
            0.0, float(os.getenv("SAPPHIRE_MIN_NOTIONAL_BUFFER_PCT", "0.05"))
        )
        self._min_trade_quantity_floor = max(
            0.0, float(os.getenv("SAPPHIRE_MIN_TRADE_QUANTITY_FLOOR", "0.0001"))
        )
        self._failure_counts: Dict[str, int] = defaultdict(int)
        self._owner_directive: str = os.getenv("SAPPHIRE_OWNER_DIRECTIVE", "").strip()
        self._trading_gate_max_failure_pressure = max(1, int(os.getenv("SAPPHIRE_TRADING_GATE_MAX_FAILURE_PRESSURE", "3")))
        self._trading_gate_min_active_venues = max(1, int(os.getenv("SAPPHIRE_TRADING_GATE_MIN_ACTIVE_VENUES", "1")))
        self._hard_failure_cooldown_seconds = max(60, int(os.getenv("HARD_FAILURE_COOLDOWN_SECONDS", "3600")))
        self._manual_review_venues: Set[str] = set()
        self._auto_deallocated: Set[str] = set()
        self._owner_directive_updated_at: int = 0
        # TradingView integration attributes (disabled by default, wired by TradingViewAutonomyPlugin if enabled)
        self._tradingview_integration_enabled = self._env_flag("SAPPHIRE_TRADINGVIEW_INTEGRATION_ENABLED", default=False)
        self._tradingview_execution_enabled = False
        self._tradingview_enforce_strategy_rules = False
        self._tradingview_strategy_rules: Dict[str, Dict[str, Any]] = {}
        self._tradingview_allowed_symbols: Set[str] = set()
        self._tradingview_allowed_symbols_by_venue: Dict[str, Set[str]] = {}
        self._tradingview_max_quantity_by_venue: Dict[str, float] = {}
        self._tradingview_max_quantity_default: float = 0.0
        self._tradingview_default_quantity: float = 0.0
        self._tradingview_signal_seen_at: Dict[str, float] = {}
        self._tradingview_idempotency_window_seconds = max(
            30, int(os.getenv("SAPPHIRE_TRADINGVIEW_IDEMPOTENCY_WINDOW_SECONDS", "300"))
        )
        self._tradingview_idempotency_max_keys = max(
            50, int(os.getenv("SAPPHIRE_TRADINGVIEW_IDEMPOTENCY_MAX_KEYS", "500"))
        )

    @staticmethod
    def _env_flag(name: str, default: bool = False) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _as_float(value: Any) -> Optional[float]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not number == number:  # NaN guard
            return None
        return number

    def _record_system_log(
        self,
        message: str,
        level: str = "info",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        text = str(message or "").strip()
        if not text:
            return
        event = {
            "timestamp": int(time.time()),
            "level": str(level or "info").lower(),
            "message": text,
            "tags": list(tags or []),
            "metadata": metadata or {},
        }
        self._system_logs.append(event)

    def _extract_trade_pnl(self, payload: Dict[str, Any]) -> Optional[float]:
        for key in ("realized_pnl", "pnl", "net_pnl", "profit", "realizedPnl", "netPnl"):
            value = self._as_float(payload.get(key))
            if value is not None:
                return value
        return None

    @staticmethod
    def _hard_failure_reason(error_message: str) -> str:
        text = str(error_message or "").strip().lower()
        if not text:
            return ""
        if "-5019" in text or "service not available in your region" in text:
            return "region_not_supported"
        if "-2015" in text or "invalid api-key" in text or "unauthorized" in text:
            return "auth_rejected"
        return ""

    def _normalize_platform(self, platform: str) -> str:
        value = str(platform or "").strip().upper()
        aliases = {
            "LIGHT": "LIGHTER",
            "L2": "LIGHTER",
            "LT": "LIGHTER",
            "ALL": "ALL",
        }
        return aliases.get(value, value)

    @staticmethod
    def _parse_execution_stage_token(raw: Any) -> str:
        value = str(raw or "").strip().lower().replace("-", "_")
        aliases = {
            "paper": "paper",
            "observe": "paper",
            "dry": "paper",
            "dry_run": "paper",
            "staged": "staged_live",
            "staged_live": "staged_live",
            "stage": "staged_live",
            "live": "full_live",
            "full": "full_live",
            "full_live": "full_live",
            "production": "full_live",
        }
        return aliases.get(value, "")


    def _set_execution_stage(self, stage: str, source: str = "manual", agent_id: str = "OBSIDIAN") -> Dict[str, Any]:
        gate.require(agent_id, Capability.SYSTEM_CONFIG, f"set_execution_stage({stage!r})")
        previous = self._dex_execution_stage
        applied = self.strategy.set_execution_stage(stage)
        self._dex_execution_stage = str(applied.get("dex_execution_stage", previous) or previous)
        self._dex_stage_updated_at = int(time.time())
        self._record_system_log(
            f"DEX execution stage set to {self._dex_execution_stage}",
            level="warning",
            tags=["control", "dex_stage"],
            metadata={
                "source": source,
                "previous_stage": previous,
                "applied_stage": self._dex_execution_stage,
                "effective_live_dispatch": bool(applied.get("stage_multiplier", 0) > 0),
                "effective_quantity": float(applied.get("effective_quantity", 0.0)),
            },
        )
        return applied

    @staticmethod
    def _parse_tradingview_message(message: str) -> Dict[str, Any]:
        message = str(message or "").strip()
        if not message:
            return {}

        try:
            parsed = json.loads(message)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        # Lightweight parser for key=value,key2=value2 style alert bodies.
        parsed: Dict[str, Any] = {}
        chunks = [chunk.strip() for chunk in message.replace("\n", ",").split(",") if chunk.strip()]
        for chunk in chunks:
            if "=" in chunk:
                key, value = chunk.split("=", 1)
            elif ":" in chunk:
                key, value = chunk.split(":", 1)
            else:
                continue
            parsed[key.strip()] = value.strip()
        return parsed

    @staticmethod
    def _extract_float_value(data: Dict[str, Any], keys: List[str], default: float = 0.0) -> float:
        for key in keys:
            value = data.get(key)
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return default

    @staticmethod
    def _extract_text_value(data: Dict[str, Any], keys: List[str], default: str = "") -> str:
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return default

    @staticmethod
    def _parse_symbol_set(value: str) -> Set[str]:
        if not value:
            return set()
        tokens = [token.strip().upper() for token in value.replace("|", ",").replace(";", ",").split(",")]
        return {token for token in tokens if token}

    def _symbol_allowed_for_venue(self, venue: str, symbol: str) -> bool:
        symbol = str(symbol or "").strip().upper()
        venue = self._normalize_platform(venue)

        venue_symbols = self._tradingview_allowed_symbols_by_venue.get(venue, set())
        if venue_symbols:
            return symbol in venue_symbols

        if self._tradingview_allowed_symbols:
            return symbol in self._tradingview_allowed_symbols

        return True

    def _max_quantity_for_venue(self, venue: str) -> float | None:
        venue = self._normalize_platform(venue)
        venue_cap = self._tradingview_max_quantity_by_venue.get(venue, 0.0)
        if venue_cap > 0:
            return venue_cap
        if self._tradingview_max_quantity_default > 0:
            return self._tradingview_max_quantity_default
        return None

    @staticmethod
    def _normalize_symbol_base(symbol: str) -> str:
        value = str(symbol or "").strip().upper()
        if not value:
            return value
        cleaned = value.replace("-", "").replace("_", "")
        for suffix in ("USDT", "USDC", "USD", "PERP"):
            if cleaned.endswith(suffix):
                cleaned = cleaned[: -len(suffix)]
                break
        return cleaned or value

    def _resolve_reference_price(self, venue: str, symbol: str) -> float:
        venue_key = self._normalize_platform(venue)
        symbol_key = self._normalize_symbol_base(symbol)
        price = self._as_float(self.market_data.get_price(venue_key, symbol_key))
        if isinstance(price, float) and price > 0:
            return price
        # Fallback to SOL when a symbol tick is unavailable, to keep notional guard operational.
        fallback = self._as_float(self.market_data.get_price(venue_key, "SOL"))
        if isinstance(fallback, float) and fallback > 0:
            return fallback
        return 0.0

    def _apply_min_notional_guard(self, venue: str, symbol: str, quantity: float) -> Dict[str, Any]:
        venue_key = self._normalize_platform(venue)
        base_qty = max(0.0, float(quantity or 0.0))
        min_notional = float(self._min_notional_by_venue.get(venue_key, 0.0))
        if base_qty <= 0:
            return {
                "blocked": True,
                "adjusted": False,
                "quantity": 0.0,
                "reason": "non_positive_quantity",
                "venue": venue_key,
            }

        if min_notional <= 0:
            return {
                "blocked": False,
                "adjusted": False,
                "quantity": base_qty,
                "reason": "guard_disabled",
                "venue": venue_key,
                "min_notional": min_notional,
            }

        reference_price = self._resolve_reference_price(venue_key, symbol)
        if reference_price <= 0:
            return {
                "blocked": True,
                "adjusted": False,
                "quantity": 0.0,
                "reason": "reference_price_unavailable",
                "venue": venue_key,
                "min_notional": min_notional,
            }

        target_notional = min_notional * (1.0 + self._min_notional_buffer_pct)
        required_qty = target_notional / reference_price
        floor_qty = self._min_trade_quantity_floor if self._min_trade_quantity_floor > 0 else 0.0
        adjusted_qty = max(base_qty, required_qty, floor_qty)

        cap = self._max_quantity_for_venue(venue_key)
        if cap is not None and cap > 0 and adjusted_qty > cap:
            return {
                "blocked": True,
                "adjusted": False,
                "quantity": 0.0,
                "reason": "required_quantity_exceeds_cap",
                "venue": venue_key,
                "min_notional": min_notional,
                "target_notional": float(round(target_notional, 6)),
                "required_quantity": float(round(required_qty, 8)),
                "cap_quantity": float(round(cap, 8)),
                "reference_price": float(round(reference_price, 8)),
            }

        rounded_qty = float(round(adjusted_qty, 8))
        adjusted = rounded_qty > (base_qty + 1e-10)
        return {
            "blocked": False,
            "adjusted": adjusted,
            "quantity": rounded_qty,
            "reason": "raised_to_min_notional" if adjusted else "baseline_satisfies_notional",
            "venue": venue_key,
            "min_notional": min_notional,
            "target_notional": float(round(target_notional, 6)),
            "required_quantity": float(round(required_qty, 8)),
            "reference_price": float(round(reference_price, 8)),
        }

    def _effective_trade_quantity_cap(self) -> float | None:
        caps: List[float] = []
        for venue in dispatcher.bot_urls.keys():
            venue_cap = self._max_quantity_for_venue(venue)
            if venue_cap is not None and venue_cap > 0:
                caps.append(float(venue_cap))

        for rule in self._tradingview_strategy_rules.values():
            strategy_cap = rule.get("max_quantity")
            if isinstance(strategy_cap, (int, float)) and float(strategy_cap) > 0:
                caps.append(float(strategy_cap))

        return min(caps) if caps else None

    def _recommended_default_trade_quantity(self) -> float:
        base = 0.02
        cap = self._effective_trade_quantity_cap()
        if cap is None:
            return base
        return round(max(0.001, min(base, float(cap))), 8)

    def _set_tradingview_default_quantity(self, requested_quantity: float, agent_id: str = "SAPPHIRE") -> Dict[str, Any]:
        gate.require(agent_id, Capability.SYSTEM_CONFIG, f"set_tv_quantity({requested_quantity})")
        requested = max(0.0, float(requested_quantity))
        if requested <= 0:
            return {
                "ok": False,
                "reason": "quantity_must_be_positive",
                "requested": requested,
            }

        cap = self._effective_trade_quantity_cap()
        applied = requested
        capped = False
        if cap is not None and applied > cap:
            applied = float(cap)
            capped = True

        applied = round(applied, 8)
        self._tradingview_default_quantity = applied
        return {
            "ok": True,
            "requested": requested,
            "applied": applied,
            "capped": capped,
            "cap": cap,
        }

    def _parse_strategy_rules(self, raw_value: str) -> Dict[str, Dict[str, Any]]:
        if not raw_value:
            return {}

        try:
            payload = json.loads(raw_value)
        except Exception as exc:
            logger.error(f"Failed to parse TRADINGVIEW_STRATEGY_RULES_JSON: {exc}")
            return {}

        if not isinstance(payload, dict):
            logger.error("TRADINGVIEW_STRATEGY_RULES_JSON must be a JSON object.")
            return {}

        rules: Dict[str, Dict[str, Any]] = {}
        for name, rule in payload.items():
            if not isinstance(name, str) or not name.strip():
                continue
            if not isinstance(rule, dict):
                continue

            venues_raw = rule.get("venues", [])
            symbols_raw = rule.get("symbols", [])

            venues: Set[str] = set()
            if isinstance(venues_raw, list):
                venues = {self._normalize_platform(item) for item in venues_raw if isinstance(item, str)}

            symbols: Set[str] = set()
            if isinstance(symbols_raw, list):
                symbols = {
                    str(item).strip().upper() for item in symbols_raw if isinstance(item, str) and str(item).strip()
                }

            max_quantity: Optional[float] = None
            max_quantity_raw = rule.get("max_quantity")
            if max_quantity_raw is not None:
                try:
                    max_quantity_val = float(max_quantity_raw)
                    if max_quantity_val > 0:
                        max_quantity = max_quantity_val
                except (TypeError, ValueError):
                    logger.warning(f"Invalid max_quantity for strategy rule `{name}`: {max_quantity_raw}")

            rules[name.strip().lower()] = {
                "venues": venues,
                "symbols": symbols,
                "max_quantity": max_quantity,
            }

        return rules

    async def _send_promotion_gate_report(self, reason: str = "manual") -> None:
        state = dispatcher.get_control_state()
        strategy_state = self.strategy.execution_state()
        active_venues = [
            venue for venue, item in state.items() if not item["paused"] and item["allocation"] > 0
        ]
        total_failures = sum(self._failure_counts.values())

        checks = [
            (
                "Kill switch off",
                not self._kill_switch_active,
                "Kill switch is active",
            ),
            (
                f"Active venues >= {self._trading_gate_min_active_venues}",
                len(active_venues) >= self._trading_gate_min_active_venues,
                f"Only {len(active_venues)} active venue(s)",
            ),
            (
                f"Failure pressure <= {self._trading_gate_max_failure_pressure}",
                total_failures <= self._trading_gate_max_failure_pressure,
                f"Failure pressure is {total_failures}",
            ),
            (
                "TradingView strategy rules optional in workbench mode",
                (not self._tradingview_execution_enabled)
                or (self._tradingview_enforce_strategy_rules and bool(self._tradingview_strategy_rules)),
                "Enable strategy rules if turning TradingView live mode on",
            ),
            (
                "DEX execution stage configured",
                strategy_state.get("dex_execution_stage") in {"paper", "staged_live", "full_live"},
                "SAPPHIRE_DEX_EXECUTION_STAGE is invalid",
            ),
            (
                "TradingView autonomy plugin enabled",
                getattr(self.tv_autonomy, "enabled", False) if self.tv_autonomy else False,
                "TRADINGVIEW_AUTONOMY_ENABLED is not true (or TV integration disabled)",
            ),
            (
                "TradingView full asset access enabled",
                getattr(self.tv_autonomy, "allow_all_assets", False) if self.tv_autonomy else False,
                "TRADINGVIEW_ALLOW_ALL_ASSETS is not true (or TV integration disabled)",
            ),
            (
                "TradingView community script access enabled",
                getattr(self.tv_autonomy, "community_access_enabled", False) if self.tv_autonomy else False,
                "TRADINGVIEW_COMMUNITY_ACCESS_ENABLED is not true (or TV integration disabled)",
            ),
            (
                "Full autonomy mode enabled",
                self._full_autonomy_enabled,
                "SAPPHIRE_FULL_AUTONOMY_ENABLED is not true",
            ),
            (
                "Autonomy code mutations enabled",
                self._autonomy_allow_code_changes,
                "SAPPHIRE_AUTONOMY_ALLOW_CODE_CHANGES is not true",
            ),
            (
                "Autonomy GCP mutations enabled",
                self._autonomy_allow_gcloud_changes,
                "SAPPHIRE_AUTONOMY_ALLOW_GCLOUD_CHANGES is not true",
            ),
            (
                "OpenClaw gateway configured",
                self.openclaw_dispatcher.enabled,
                "OPENCLAW_GATEWAY_URL or OPENCLAW_GATEWAY_TOKEN not set",
            ),
            (
                "CI feedback processor ready",
                self.ci_feedback is not None,
                "CIFeedbackProcessor not initialized",
            ),
        ]

        failed_checks = [item for item in checks if not item[1]]
        status = "PASS" if not failed_checks else "FAIL"
        icon = "✅" if status == "PASS" else "⚠️"

        lines = [
            f"{icon} **PROMOTION GATE REPORT** (`{reason}`)",
            f"Overall: `{status}`",
            "",
        ]

        for label, ok, note in checks:
            marker = "PASS" if ok else "FAIL"
            lines.append(f"- `{marker}` {label}" + (f" ({note})" if not ok else ""))

        lines.extend(
            [
                "",
                f"Active venues: `{', '.join(active_venues) if active_venues else 'none'}`",
                f"Failure pressure: `{total_failures}`",
                f"DEX stage: `{strategy_state.get('dex_execution_stage', 'paper')}`",
                f"DEX live dispatch: `{bool(strategy_state.get('stage_multiplier', 0) > 0)}`",
                f"DEX effective qty: `{strategy_state.get('effective_quantity', 0.0)}`",
                f"Rules configured: `{len(self._tradingview_strategy_rules)}`",
                f"TV autonomy enabled: `{getattr(self.tv_autonomy, 'enabled', False) if self.tv_autonomy else 'DISABLED'}`",
                (
                    "TV signal mode: `LIVE`"
                    if self._tradingview_execution_enabled
                    else "TV signal mode: `WORKBENCH_DRY_RUN`"
                    if self._tradingview_integration_enabled
                    else "TV signal mode: `DISABLED`"
                ),
                f"TV hook configured: `{bool(getattr(self.tv_autonomy, 'hook_url', '') and getattr(self.tv_autonomy, 'hook_token', '')) if self.tv_autonomy else False}`",
            ]
        )

        await self.telegram.send_message("\n".join(lines), priority="high" if status == "FAIL" else "medium")

    def _build_signal_key(
        self,
        payload: Dict[str, Any],
        action: str,
        targets: List[str],
        symbol: str,
        quantity: float,
    ) -> str:
        explicit_id = self._extract_text_value(
            payload,
            ["signal_id", "alert_id", "id", "uuid", "message_id", "tv_id"],
        )
        if explicit_id:
            return explicit_id

        key_material = {
            "action": action,
            "targets": sorted(targets),
            "symbol": symbol,
            "quantity": quantity,
            "strategy": self._extract_text_value(payload, ["strategy", "strategy_name", "alert_name"]),
            "timeframe": self._extract_text_value(payload, ["timeframe", "tf"]),
            "timestamp": self._extract_text_value(payload, ["timestamp", "time", "bar_time", "t"]),
        }
        digest = hashlib.sha256(
            json.dumps(key_material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return f"auto:{digest[:32]}"

    def _is_duplicate_signal(self, signal_key: str) -> bool:
        now = time.time()
        cutoff = now - float(self._tradingview_idempotency_window_seconds)

        if self._tradingview_signal_seen_at:
            stale_keys = [
                key for key, seen_at in self._tradingview_signal_seen_at.items() if seen_at < cutoff
            ]
            for key in stale_keys:
                self._tradingview_signal_seen_at.pop(key, None)

        seen_at = self._tradingview_signal_seen_at.get(signal_key)
        if seen_at is not None and (now - seen_at) <= self._tradingview_idempotency_window_seconds:
            return True

        self._tradingview_signal_seen_at[signal_key] = now
        if len(self._tradingview_signal_seen_at) > self._tradingview_idempotency_max_keys:
            oldest_keys = sorted(
                self._tradingview_signal_seen_at.items(), key=lambda item: item[1]
            )[: len(self._tradingview_signal_seen_at) - self._tradingview_idempotency_max_keys]
            for old_key, _ in oldest_keys:
                self._tradingview_signal_seen_at.pop(old_key, None)
        return False

    async def _handle_tradingview_signal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle an execution signal and publish it to the bot fleet via Pub/Sub.

        TradingView webhook ingress is intentionally disabled. The name is kept for
        backward-compatibility with internal callers (alpha scanner / grid trader),
        but the pipeline is now venue-native:
        - validate + dedupe
        - apply stage sizing
        - apply per-venue min-notional guard
        - publish `TradeSignal` to `trading-signals`
        """
        from models import SignalType, TradeSide, TradeSignal
        from pubsub.client import publish

        if not isinstance(payload, dict):
            return {"accepted": "rejected", "reason": "payload_not_dict"}

        if self._kill_switch_active:
            return {"accepted": "blocked", "reason": "kill_switch_active"}

        raw_action = str(payload.get("action") or payload.get("side") or "").strip().upper()
        if raw_action in {"LONG"}:
            raw_action = "BUY"
        if raw_action in {"SHORT"}:
            raw_action = "SELL"

        if raw_action not in {"BUY", "SELL"}:
            return {"accepted": "rejected", "reason": "unsupported_action", "action": raw_action}

        symbol = str(payload.get("symbol") or "").strip().upper()
        if not symbol:
            return {"accepted": "rejected", "reason": "missing_symbol"}

        # Determine targets:
        # - explicit target_platforms list wins
        # - explicit venue hint wins
        # - otherwise choose the best active venue (avoid duplicating across venues by default)
        targets_raw = payload.get("target_platforms") or payload.get("targets") or payload.get("target") or []
        targets: List[str] = []
        if isinstance(targets_raw, str):
            import re as _re

            targets = [
                token.strip().lower()
                for token in _re.split(r"[,;|\s]+", targets_raw)
                if token.strip()
            ]
        elif isinstance(targets_raw, list):
            targets = [str(item).strip().lower() for item in targets_raw if str(item).strip()]

        venue_hint = str(payload.get("venue") or "").strip().upper()
        if venue_hint and venue_hint != "ALL" and not targets:
            targets = [self._normalize_platform(venue_hint).lower()]

        if not targets:
            # Pick a single best venue to prevent accidental cross-venue duplication.
            control = dispatcher.get_control_state()
            snapshot = self.market_data.get_market_snapshot(symbol=symbol)
            candidates: List[tuple[float, str]] = []
            for venue in dispatcher.bot_urls.keys():
                venue_state = control.get(venue, {})
                if bool(venue_state.get("paused")):
                    continue
                if float(venue_state.get("allocation", 0.0)) <= 0:
                    continue
                market = snapshot.get(venue, {})
                status = str(market.get("status", "offline"))
                if status not in {"healthy", "degraded"}:
                    continue
                score = float(venue_state.get("allocation", 0.0))
                # Prefer healthy feeds and fresher ticks.
                if status == "healthy":
                    score += 0.25
                age = market.get("age_seconds")
                if isinstance(age, int):
                    score += max(0.0, 0.2 - min(0.2, age / 3000.0))
                candidates.append((score, venue.lower()))

            candidates.sort(reverse=True)
            if candidates:
                targets = [candidates[0][1]]

        if not targets:
            return {"accepted": "blocked", "reason": "no_active_venues"}

        # Quantity: callers provide a baseline quantity (pre-stage sizing).
        requested_quantity = self._as_float(payload.get("quantity"))
        if requested_quantity is None or requested_quantity <= 0:
            requested_quantity = float(self.strategy.default_quantity)

        execution_state = self.strategy.execution_state()
        multiplier = float(execution_state.get("stage_multiplier", 0.0))
        stage = str(execution_state.get("dex_execution_stage", "paper"))

        if multiplier <= 0:
            return {
                "accepted": "dry_run",
                "reason": "execution_stage_paper",
                "stage": stage,
                "targets": targets,
                "requested_quantity": float(requested_quantity),
            }

        # Apply stage sizing once (canonical).
        dispatch_quantity = float(self.strategy.apply_stage_to_quantity(float(requested_quantity)))
        if dispatch_quantity <= 0:
            return {
                "accepted": "dry_run",
                "reason": "quantity_zero_after_stage",
                "stage": stage,
                "targets": targets,
                "requested_quantity": float(requested_quantity),
            }

        # Per-venue notional guard (use the strictest required sizing among targets).
        guarded_quantity = dispatch_quantity
        guard_notes: Dict[str, Any] = {}
        for target in targets:
            venue = self._normalize_platform(target)
            guard = self._apply_min_notional_guard(venue, symbol, guarded_quantity)
            guard_notes[venue.lower()] = guard
            if guard.get("blocked"):
                return {
                    "accepted": "blocked",
                    "reason": guard.get("reason", "min_notional_blocked"),
                    "stage": stage,
                    "targets": targets,
                    "guard": guard_notes,
                }
            guarded_quantity = max(guarded_quantity, float(guard.get("quantity", guarded_quantity)))

        confidence = self._as_float(payload.get("_confidence")) or self._as_float(payload.get("confidence")) or 0.75
        confidence = max(0.01, min(0.99, float(confidence)))
        source = str(payload.get("source") or payload.get("strategy") or "alpha-engine").strip() or "alpha-engine"
        leverage = self._as_float(payload.get("leverage"))
        if leverage is not None and leverage <= 0:
            leverage = None

        signal_key = self._build_signal_key(payload, raw_action, targets, symbol, guarded_quantity)
        if self._is_duplicate_signal(signal_key):
            return {
                "accepted": "duplicate",
                "reason": "idempotent_drop",
                "signal_key": signal_key,
                "stage": stage,
            }

        # Preserve caller metadata, but ensure we never serialize huge blobs.
        metadata = dict(payload.get("metadata") or {})
        for key in ("grid", "strategy", "reduce_only", "price", "_reasoning", "_cognition_latency_ms"):
            if key in payload and key not in metadata:
                metadata[key] = payload.get(key)

        signal = TradeSignal(
            signal_id=signal_key,
            symbol=symbol,
            side=TradeSide.BUY if raw_action == "BUY" else TradeSide.SELL,
            signal_type=SignalType.ENTRY,
            confidence=confidence,
            source=source,
            target_platforms=targets,
            quantity=float(round(guarded_quantity, 8)),
            leverage=float(leverage) if leverage is not None else None,
            metadata=metadata,
        )

        await publish("trading-signals", signal)
        self._record_system_log(
            f"Signal published: {raw_action} {symbol} qty={signal.quantity} targets={','.join(targets)}",
            level="info",
            tags=["signals", "dispatch"],
            metadata={
                "signal_id": signal_key,
                "symbol": symbol,
                "action": raw_action,
                "targets": targets,
                "quantity": signal.quantity,
                "stage": stage,
                "multiplier": multiplier,
                "guard": guard_notes,
            },
        )

        return {
            "accepted": "executed",
            "signal_key": signal_key,
            "stage": stage,
            "targets": targets,
            "quantity": signal.quantity,
            "confidence": confidence,
            "source": source,
        }

    async def _publish_risk_alert(
        self,
        action: str,
        message: str,
        severity: str = "warning",
        alert_type: str = "manual_control",
        platforms: List[str] | None = None,
        metadata: Dict[str, Any] | None = None,
    ) -> None:
        from models import RiskAlert
        from pubsub.client import publish

        affected = []
        for platform in platforms or []:
            normalized = self._normalize_platform(platform)
            if normalized != "ALL":
                affected.append(normalized.lower())

        alert = RiskAlert(
            alert_id=f"{alert_type}-{int(time.time() * 1000)}",
            severity=severity,
            alert_type=alert_type,
            message=message,
            action=action,
            affected_platforms=affected,
            metadata=metadata or {},
        )
        await publish("risk-alerts", alert)

    async def _activate_kill_switch(self, reason: str, agent_id: str = "OBSIDIAN") -> None:
        gate.require(agent_id, Capability.KILL_SWITCH, f"activate_kill_switch({reason!r})")
        self._kill_switch_active = True
        reason = reason.strip() or "Manual kill switch requested via Telegram"
        self._record_system_log(
            f"Kill switch activated: {reason}",
            level="warning",
            tags=["risk", "kill_switch"],
        )

        for venue in dispatcher.bot_urls:
            dispatcher.set_venue_allocation(venue, 0.0)
            dispatcher.pause_venue(
                venue,
                reason=reason,
                cooldown_seconds=max(self._deallocation_cooldown_seconds, 3600),
            )

        await self._publish_risk_alert(
            action="close_all",
            severity="emergency",
            alert_type="kill_switch",
            message=f"Emergency close requested: {reason}",
            platforms=list(dispatcher.bot_urls.keys()),
            metadata={"source": "telegram", "kill_switch": True},
        )
        await self._publish_risk_alert(
            action="halt_trading",
            severity="emergency",
            alert_type="kill_switch",
            message=f"Trading halted by kill switch: {reason}",
            platforms=list(dispatcher.bot_urls.keys()),
            metadata={"source": "telegram", "kill_switch": True},
        )

        self.telegram.record_activity(
            OBSIDIAN, "system", f"Kill switch activated: {reason[:80]}",
        )
        await self.telegram.send_message(
            f"🛑 **KILL SWITCH ACTIVE**\nReason: `{reason}`\nAll venues are halted and deallocated.",
            priority="high",
        )

    async def _resume_from_kill_switch(self, reason: str, agent_id: str = "OBSIDIAN") -> None:
        gate.require(agent_id, Capability.KILL_SWITCH, f"resume_from_kill_switch({reason!r})")
        self._kill_switch_active = False
        reason = reason.strip() or "Manual resume requested via Telegram"
        self._record_system_log(
            f"Trading resumed: {reason}",
            level="info",
            tags=["risk", "resume"],
        )

        for venue in dispatcher.bot_urls:
            dispatcher.resume_venue(venue)
            dispatcher.set_venue_allocation(venue, self._default_venue_allocation)
            self._failure_counts[venue] = 0
            self._auto_deallocated.discard(venue)
            self._manual_review_venues.discard(venue)

        await self._publish_risk_alert(
            action="resume_trading",
            severity="warning",
            alert_type="resume_trading",
            message=f"Trading resumed: {reason}",
            platforms=list(dispatcher.bot_urls.keys()),
            metadata={"source": "telegram", "kill_switch": False},
        )

        self.telegram.record_activity(
            OBSIDIAN, "system", f"Trading resumed: {reason[:80]}",
        )
        await self.telegram.send_message(
            f"✅ **TRADING RESUMED**\nReason: `{reason}`\nDefault allocations restored across all venues.",
            priority="high",
        )

    async def _send_control_status(self) -> None:
        snapshot = self._control_snapshot()
        primary_venues = ", ".join(sorted(snapshot["primary_execution_venues"])) or "none"
        tv_signal_mode = "DISABLED"
        if snapshot.get("tradingview_integration_enabled"):
            tv_signal_mode = (
                "LIVE_SIGNAL_EXECUTION"
                if snapshot["tradingview_signal_mode"] == "live"
                else "WORKBENCH_DRY_RUN"
            )
        media_snapshot = snapshot.get("media", {}) if isinstance(snapshot, dict) else {}
        active_count = len([item for item in snapshot["venues"].values() if not item["paused"]])
        pressure = int(snapshot.get("failure_pressure", 0))
        if snapshot["kill_switch_active"]:
            status_read = "Trading is intentionally halted by kill switch."
        elif active_count < self._trading_gate_min_active_venues:
            status_read = (
                f"Active venue count is below target ({active_count}/{self._trading_gate_min_active_venues})."
            )
        elif pressure > self._trading_gate_max_failure_pressure:
            status_read = (
                f"Failure pressure is elevated ({pressure}/{self._trading_gate_max_failure_pressure})."
            )
        else:
            status_read = "Runtime is inside autonomy guardrails."
        lines = [
            "📊 **CONTROL STATUS**",
            f"Kill switch: `{'ACTIVE' if snapshot['kill_switch_active'] else 'INACTIVE'}`",
            f"Full autonomy: `{'ON' if snapshot['full_autonomy_enabled'] else 'OFF'}`",
            f"Primary execution: `DEX_NATIVE ({primary_venues})`",
            f"DEX stage: `{snapshot['dex_execution_stage']}`",
            f"DEX live dispatch: `{'ON' if snapshot['dex_live_dispatch_enabled'] else 'OFF'}`",
            f"DEX effective qty: `{snapshot['dex_effective_quantity']}`",
            f"TradingView signal mode: `{tv_signal_mode}`",
            (
                f"Signal default quantity: `{snapshot['tradingview_default_quantity']}`"
                if snapshot.get("tradingview_integration_enabled")
                else "Signal default quantity: `n/a (integration disabled)`"
            ),
            (
                "VT skill security: `ON`"
                if snapshot.get("vt_security_enabled")
                else "VT skill security: `OFF`"
            ),
            f"VT policy mode: `{snapshot.get('vt_enforcement_mode', 'warn')}`",
            f"Media mode: `{snapshot.get('media_mode', 'owner_approval')}`",
            (
                f"Media channels: X `{'READY' if media_snapshot.get('twitter_ready') else 'NOT_READY'}` | "
                f"Substack `{'READY' if media_snapshot.get('substack_ready') else 'NOT_READY'}`"
            ),
            (
                "Media queue: pending "
                f"`{media_snapshot.get('queue', {}).get('pending_count', 0)}` | "
                f"queued `{media_snapshot.get('queue', {}).get('queued_count', 0)}`"
            ),
            (
                "Manual-review holds: `none`"
                if not snapshot.get("manual_review_venues")
                else f"Manual-review holds: `{', '.join(snapshot.get('manual_review_venues', []))}`"
            ),
            f"Autonomy dispatches: `{snapshot['autonomy_dispatch_count']}`",
            f"Pending autonomy decisions: `{snapshot['pending_autonomy_decisions']}`",
            f"Operational read: {status_read}",
            "",
        ]
        for venue in sorted(snapshot["venues"].keys()):
            item = snapshot["venues"][venue]
            status = "PAUSED" if item["paused"] else "LIVE"
            fail_count = item.get("failure_count", 0)
            lines.append(
                f"- `{venue}` | {status} | alloc `{item['allocation']*100:.0f}%` | failures `{fail_count}`"
                + (" | `MANUAL_REVIEW_HOLD`" if item.get("manual_review_required") else "")
            )

        # Interactive control commands should respond immediately.
        # Medium/low notifications are buffered into digest messages, which makes
        # `/status` feel slow and can collapse detailed output. Use HIGH here.
        await self.telegram.send_message("\n".join(lines), priority="high")

    async def _send_market_prices(self) -> None:
        """Send multi-symbol price snapshot across all venues."""
        snapshot = self.market_data.get_multi_symbol_snapshot()
        preferred = self.strategy.preferred_symbols
        lines = ["Market Prices"]
        for venue in ("ASTER", "LIGHTER"):
            venue_data = snapshot.get(venue, {})
            profile = self.strategy.venue_profiles.get(venue, {})
            role = profile.get("role", "")
            lines.append(f"\n*{venue}* — {role}")
            # Show preferred symbols first, then any extra tracked ones
            shown: set = set()
            for sym in preferred:
                info = venue_data.get(sym, {})
                price = info.get("price", 0.0)
                status = info.get("status", "offline")
                if price > 0:
                    age = info.get("age_seconds")
                    age_text = f"{age}s" if age is not None else "?"
                    if price >= 1.0:
                        lines.append(f"  `{sym}` {price:,.2f} ({age_text})")
                    else:
                        lines.append(f"  `{sym}` {price:.6f} ({age_text})")
                else:
                    lines.append(f"  `{sym}` no data")
                shown.add(sym)
            # Any extra tracked symbols not in preferred
            for sym, info in sorted(venue_data.items()):
                if sym not in shown and info.get("price", 0) > 0:
                    price = info["price"]
                    if price >= 1.0:
                        lines.append(f"  `{sym}` {price:,.2f}")
                    else:
                        lines.append(f"  `{sym}` {price:.6f}")

        # Update portfolio with latest market prices for unrealized P&L
        self.portfolio.update_prices(snapshot)

        await self.telegram.send_as(SAPPHIRE, "\n".join(lines))

    async def _send_portfolio_status(self) -> None:
        """Send portfolio snapshot via Telegram."""
        snap = self.portfolio.snapshot()
        lines = ["*Portfolio Status*"]

        if snap["open_count"] == 0 and snap["total_trades"] == 0:
            lines.append("No positions or trades recorded yet.")
            await self.telegram.send_as(SAPPHIRE, "\n".join(lines))
            return

        # Open positions
        if snap["open_positions"]:
            lines.append(f"\n*Open Positions* ({snap['open_count']})")
            for pos in snap["open_positions"]:
                upnl = pos["unrealized_pnl"]
                upnl_str = f"{upnl:+.2f}" if abs(upnl) >= 0.01 else "0.00"
                emoji = "🟢" if upnl >= 0 else "🔴"
                lines.append(
                    f"  {emoji} {pos['venue']} {pos['side']} "
                    f"{pos['quantity']:.4f} `{pos['symbol']}` "
                    f"@ {pos['entry_price']:,.4f} | uPnL: {upnl_str}"
                )
        else:
            lines.append("\nNo open positions.")

        # Stats
        lines.append(f"\n*Stats*")
        lines.append(f"  Total fills: {snap['total_trades']}")
        lines.append(
            f"  Realized PnL: {snap['total_realized_pnl']:+.4f}"
        )
        lines.append(
            f"  Unrealized PnL: {snap['total_unrealized_pnl']:+.4f}"
        )
        closed_count = snap["wins"] + snap["losses"]
        if closed_count > 0:
            lines.append(
                f"  Win rate: {snap['win_rate']}% "
                f"({snap['wins']}W / {snap['losses']}L)"
            )

        # Recent closed trades
        if snap["recent_closed"]:
            lines.append(f"\n*Recent Trades*")
            for t in snap["recent_closed"][-5:]:
                emoji = "✅" if t["pnl"] >= 0 else "❌"
                lines.append(
                    f"  {emoji} {t['venue']} {t['side']} `{t['symbol']}` "
                    f"PnL: {t['pnl']:+.4f} ({t['duration_s']}s)"
                )

        await self.telegram.send_as(SAPPHIRE, "\n".join(lines))

    async def _send_cognitive_status(self) -> None:
        """Send episodic memory and cognition status via Telegram."""
        lines = ["*Cognitive Systems*"]

        # Episodic Memory
        lines.append(f"\n*Episodic Memory*: {'enabled' if self._memory_enabled else 'disabled'}")
        if self._memory_enabled:
            try:
                stats = self.memory.get_stats()
                lines.append(f"  Episodes: {stats.get('total_episodes', 0)}")
                lines.append(f"  Trades recorded: {stats.get('total_trades', 0)}")
                lines.append(f"  Total PnL: {stats.get('total_pnl', 0):+.4f}")
                with_lessons = stats.get("episodes_with_full_lessons", 0)
                if with_lessons:
                    lines.append(f"  Episodes with lessons: {with_lessons}")
                regime_dist = stats.get("regime_distribution", {})
                if regime_dist:
                    top = sorted(regime_dist.items(), key=lambda x: x[1], reverse=True)[:3]
                    lines.append(f"  Top regimes: {', '.join(f'{k}({v})' for k, v in top)}")
            except Exception as e:
                lines.append(f"  Error: {e}")

            # Temporal insights
            try:
                temporal = self.memory.get_temporal_insights()
                best = temporal.get("best_hours", [])
                worst = temporal.get("worst_hours", [])
                if best:
                    lines.append(f"  Best hours (UTC): {best[:3]}")
                if worst:
                    lines.append(f"  Worst hours (UTC): {worst[:3]}")
            except Exception:
                pass

        # Dual-Speed Cognition
        lines.append(f"\n*Dual-Speed Cognition*: {'enabled' if self._cognition_enabled else 'disabled'}")
        if self._cognition_enabled:
            try:
                metrics = self.cognition.get_metrics()
                s1_calls = metrics.get("system1_calls", 0)
                s2_calls = metrics.get("system2_calls", 0)
                overrides = metrics.get("overrides", 0)
                lines.append(f"  System 1 (Flash) calls: {s1_calls}")
                lines.append(f"  System 2 (Pro) calls: {s2_calls}")
                if s1_calls > 0:
                    lines.append(
                        f"  Overrides: {overrides} ({metrics.get('override_rate', 0):.0f}%)"
                    )
                    s1_lat = metrics.get("avg_system1_latency_ms", 0)
                    s2_lat = metrics.get("avg_system2_latency_ms", 0)
                    if s1_lat:
                        lines.append(f"  Avg latency: S1={s1_lat:.0f}ms, S2={s2_lat:.0f}ms")
            except Exception as e:
                lines.append(f"  Error: {e}")

        await self.telegram.send_as(EMERALD, "\n".join(lines))

    def _control_snapshot(self) -> Dict[str, Any]:
        state = dispatcher.get_control_state()
        strategy_state = self.strategy.execution_state()
        media_snapshot = self.media_manager.get_status_snapshot()
        pending_sessions = [
            session
            for session in self._autonomy_sessions.values()
            if session.get("decision", "pending") == "pending"
        ]
        pending_sessions.sort(key=lambda item: int(item.get("created_at", 0)), reverse=True)
        pending_summary = [
            {
                "session_key": str(item.get("session_key", "")).strip(),
                "trigger": str(item.get("trigger", "")).strip(),
                "created_at": int(item.get("created_at", 0)),
                "instruction": str(item.get("instruction", "")).strip(),
            }
            for item in pending_sessions[:20]
            if str(item.get("session_key", "")).strip()
        ]

        venues: Dict[str, Dict[str, Any]] = {}
        for venue, venue_state in state.items():
            venues[venue] = {
                "allocation": float(venue_state.get("allocation", 0.0)),
                "paused": bool(venue_state.get("paused", False)),
                "paused_until": venue_state.get("paused_until"),
                "pause_reason": venue_state.get("pause_reason", ""),
                "failure_count": int(self._failure_counts.get(venue, 0)),
                "manual_review_required": venue in self._manual_review_venues,
            }

        return {
            "kill_switch_active": self._kill_switch_active,
            "full_autonomy_enabled": self._full_autonomy_enabled,
            "owner_approval_required": self._autonomy_require_owner_approval,
            "primary_execution_plane": "dex_venues",
            "primary_execution_venues": sorted(venues.keys()),
            "dex_execution_stage": strategy_state.get("dex_execution_stage", "paper"),
            "dex_live_dispatch_enabled": bool(strategy_state.get("stage_multiplier", 0) > 0),
            "dex_stage_multiplier": float(strategy_state.get("stage_multiplier", 0.0)),
            "dex_effective_quantity": float(strategy_state.get("effective_quantity", 0.0)),
            "dex_base_quantity": float(strategy_state.get("base_quantity", 0.0)),
            "tradingview_integration_enabled": bool(self._tradingview_integration_enabled),
            "tradingview_execution_enabled": self._tradingview_execution_enabled,
            "tradingview_signal_mode": (
                "disabled"
                if not self._tradingview_integration_enabled
                else "live"
                if self._tradingview_execution_enabled
                else "workbench_dry_run"
            ),
            "tradingview_default_quantity": float(self._tradingview_default_quantity),
            "autonomy_dispatch_count": int(self._autonomy_dispatch_count),
            "pending_autonomy_decisions": len(pending_summary),
            "pending_sessions": pending_summary,
            "owner_directive": self._owner_directive or "",
            "failure_pressure": int(sum(self._failure_counts.values())),
            "manual_review_venues": sorted(list(self._manual_review_venues)),
            "vt_security_enabled": bool(self.vt_scanner.enabled),
            "vt_api_key_configured": bool(self.vt_scanner.api_key),
            "vt_enforcement_mode": self.vt_scanner.enforcement_mode,
            "media_mode": media_snapshot.get("mode", "owner_approval"),
            "media": media_snapshot,
            "venues": venues,
            "portfolio": self.portfolio.snapshot(),
            "cognition_enabled": self._cognition_enabled,
            "memory_enabled": self._memory_enabled,
            "cognition_metrics": self.cognition.get_metrics() if self._cognition_enabled else {},
            "memory_stats": self.memory.get_stats() if self._memory_enabled else {},
            "alpha_scanner": self.alpha_scanner.get_metrics(),
            "grid_trader": self.grid_trader.metrics(),
            "dispatcher_hardening": dispatcher.get_hardening_status(),
            "timestamp": int(time.time()),
        }





    @staticmethod
    def _fmt_unix_ts(timestamp: Any) -> str:
        try:
            value = int(timestamp or 0)
        except (TypeError, ValueError):
            value = 0
        if value <= 0:
            return "n/a"
        return time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime(value))





    def _collect_media_context(self) -> Dict[str, Any]:
        """Collect system context for AI content generation."""
        snapshot = self._control_snapshot()
        return {
            "metrics": {
                "total_trades": int(self._trade_metrics.get("total_trades", 0)),
                "wins": int(self._trade_metrics.get("wins", 0)),
                "losses": int(self._trade_metrics.get("losses", 0)),
                "win_rate": round(
                    (self._trade_metrics["wins"] / max(1, self._trade_metrics["total_trades"])) * 100, 1
                ),
                "realized_pnl": round(float(self._trade_metrics.get("realized_pnl", 0)), 4),
                "uptime_hours": round((time.time() - self._started_at) / 3600, 1),
                "autonomy_dispatches": int(self._autonomy_dispatch_count),
            },
            "execution": {
                "stage": str(snapshot.get("dex_execution_stage", "paper")),
                "autonomy": "ON" if snapshot.get("full_autonomy_enabled") else "OFF",
                "failure_pressure": int(snapshot.get("failure_pressure", 0)),
                "kill_switch": bool(self._kill_switch_active),
            },
            "forum_topics": [
                {"title": t.get("title", ""), "lane": t.get("lane", "")}
                for t in list(self.forum.list_topics({}).get("topics", []))[:5]
            ],
            "events": [
                str(e.get("message", ""))
                for e in list(self._system_logs)[-10:]
            ],
        }

    def _build_media_draft(self, topic: str) -> Dict[str, Any]:
        normalized_topic = str(topic or "").strip() or "weekly operations update"
        snapshot = self._control_snapshot()
        timestamp = int(time.time())
        stage = str(snapshot.get("dex_execution_stage", "paper"))
        failure_pressure = int(snapshot.get("failure_pressure", 0))
        pending = int(snapshot.get("pending_autonomy_decisions", 0))
        autonomy = "ON" if snapshot.get("full_autonomy_enabled") else "OFF"
        tv_mode = str(snapshot.get("tradingview_signal_mode", "workbench_dry_run"))
        vt_mode = str(snapshot.get("vt_enforcement_mode", "warn"))
        title = f"Sapphire Weekly Lab Note: {normalized_topic}"
        body_lines = [
            f"# {title}",
            "",
            "## Experiment Context",
            "- Scope: arigatoexpress/Sapphire only",
            f"- DEX execution stage: {stage}",
            f"- Full autonomy: {autonomy}",
            f"- TradingView mode: {tv_mode}",
            "",
            "## Operational Snapshot",
            f"- Failure pressure: {failure_pressure}",
            f"- Pending autonomy decisions: {pending}",
            f"- VirusTotal policy mode: {vt_mode}",
            "",
            "## Key Learnings",
            "- Summarize changes that improved stability, security, or execution quality this period.",
            "- Document incidents, observed root causes, and mitigations applied.",
            "",
            "## Next Experiments",
            "- Define measurable hypotheses for reliability, execution quality, and autonomy throughput.",
            "- Track expected benefit and stop conditions before promotion.",
        ]
        body = "\n".join(body_lines)
        self._record_system_log(
            f"Media draft generated for topic '{normalized_topic}'",
            level="info",
            tags=["media", "draft"],
            metadata={"mode": self.media_manager.mode, "topic": normalized_topic},
        )
        return {
            "topic": normalized_topic,
            "title": title,
            "body": body,
            "timestamp": timestamp,
            "mode": self.media_manager.mode,
        }

    def _resolve_media_draft_for_publish(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        requested_topic = str(payload.get("topic", "")).strip()
        if requested_topic:
            return self._build_media_draft(requested_topic)

        # Fallback to a default topic if none provided
        return self._build_media_draft("weekly operations update")

    async def _send_focus_snapshot(self) -> None:
        state = dispatcher.get_control_state()
        strategy_state = self.strategy.execution_state()
        media_snapshot = self.media_manager.get_status_snapshot()
        venue_summary = ", ".join(sorted(state.keys())) if state else "none"

        directive = self._owner_directive.strip() or "none"
        if len(directive) > 180:
            directive = directive[:177] + "..."
        directive_updated = (
            time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime(self._owner_directive_updated_at))
            if self._owner_directive_updated_at
            else "n/a"
        )

        lines = [
            "🎯 **SAPPHIRE FOCUS SNAPSHOT**",
            "Scope: `arigatoexpress/Sapphire` only",
            f"Enabled venues: `{venue_summary}`",
            f"Kill switch: `{'ACTIVE' if self._kill_switch_active else 'OFF'}`",
            f"Full autonomy mode: `{'ON' if self._full_autonomy_enabled else 'OFF'}`",
            (
                f"Owner approval gate: `{'ON' if self._autonomy_require_owner_approval else 'AUTO-APPROVE'}`"
            ),
            "Primary execution plane: `DEX_NATIVE (ASTER/LIGHTER)`",
            f"DEX stage: `{strategy_state.get('dex_execution_stage', 'paper')}`",
            (
                f"DEX live dispatch: `{'ON' if strategy_state.get('stage_multiplier', 0) > 0 else 'OFF'}`"
            ),
            f"DEX effective qty: `{strategy_state.get('effective_quantity', 0.0)}`",
            (
                "TradingView signal mode: `DISABLED`"
                if not self._tradingview_integration_enabled
                else "TradingView signal mode: `LIVE`"
                if self._tradingview_execution_enabled
                else "TradingView signal mode: `WORKBENCH_DRY_RUN`"
            ),
            (
                f"TradingView autonomy: `{'ON' if self.tv_autonomy and self.tv_autonomy.enabled else 'OFF'}`"
                if self._tradingview_integration_enabled
                else "TradingView autonomy: `OFF (integration disabled)`"
            ),
            (
                f"Community scripts: `{'ON' if self.tv_autonomy and self.tv_autonomy.community_access_enabled else 'OFF'}`"
                if self._tradingview_integration_enabled
                else "Community scripts: `OFF (integration disabled)`"
            ),
            f"VT skill security: `{'ON' if self.vt_scanner.enabled else 'OFF'}` (`{self.vt_scanner.enforcement_mode}`)",
            f"Media mode: `{media_snapshot.get('mode', 'owner_approval')}`",
            (
                f"Media channels: X `{'READY' if media_snapshot.get('twitter_ready') else 'NOT_READY'}` | "
                f"Substack `{'READY' if media_snapshot.get('substack_ready') else 'NOT_READY'}`"
            ),
            f"Owner directive: `{directive}`",
            f"Directive updated: `{directive_updated}`",
            "",
            "Use plain text (or `/steer`/`/answer`) to update direction.",
        ]
        await self.telegram.send_message("\n".join(lines), priority="medium")

    async def _send_heartbeat(self, reason: str) -> None:
        state = dispatcher.get_control_state()
        strategy_state = self.strategy.execution_state()
        live = [venue for venue, item in state.items() if not item["paused"] and item["allocation"] > 0]
        paused = [venue for venue, item in state.items() if item["paused"] or item["allocation"] <= 0]
        total_failures = sum(self._failure_counts.values())
        pending_count = len(self._pending_autonomy_session_keys())
        directive = self._owner_directive.strip() or "none"
        if len(directive) > 120:
            directive = directive[:117] + "..."
        if self._kill_switch_active:
            why_now = "Kill switch is active; runtime remains in safety-first containment mode."
        elif total_failures > self._trading_gate_max_failure_pressure:
            why_now = (
                f"Failure pressure is elevated ({total_failures}/{self._trading_gate_max_failure_pressure}); "
                "expect autonomous triage."
            )
        elif len(live) < self._trading_gate_min_active_venues:
            why_now = (
                f"Active venue count is below target ({len(live)}/{self._trading_gate_min_active_venues}); "
                "autonomy will prioritize venue recovery."
            )
        else:
            why_now = "Execution and control state are inside configured guardrails."
        media_snapshot = self.media_manager.get_status_snapshot()

        lines = [
            f"💓 **SAPPHIRE HEARTBEAT** (`{reason}`)",
            "State:",
            f"- Active venues: `{', '.join(live) if live else 'none'}`",
            f"- Paused venues: `{', '.join(paused) if paused else 'none'}`",
            f"- Kill switch: `{'ACTIVE' if self._kill_switch_active else 'OFF'}`",
            (
                f"- Full autonomy: `{'ON' if self._full_autonomy_enabled else 'OFF'}`"
                f" | Approvals: `{'OWNER' if self._autonomy_require_owner_approval else 'AUTO'}`"
            ),
            (
                f"- DEX mode: stage `{strategy_state.get('dex_execution_stage', 'paper')}`"
                f" | live dispatch `{'ON' if strategy_state.get('stage_multiplier', 0) > 0 else 'OFF'}`"
                f" | qty `{strategy_state.get('effective_quantity', 0.0)}`"
            ),
            (
                "- TradingView mode: `DISABLED`"
                if not self._tradingview_integration_enabled
                else f"- TradingView mode: `{'LIVE' if self._tradingview_execution_enabled else 'WORKBENCH_DRY-RUN'}`"
                f" | default qty `{self._tradingview_default_quantity}`"
            ),
            (
                f"- Media mode: `{self.media_manager.mode}`"
                f" | X `{'READY' if media_snapshot.get('twitter_ready') else 'NOT_READY'}`"
                f" | Substack `{'READY' if media_snapshot.get('substack_ready') else 'NOT_READY'}`"
            ),
            f"- Pending approvals: `{pending_count}` | Failure pressure: `{total_failures}`",
            f"- Owner directive: `{directive}`",
            "",
            "Why this matters:",
            f"- {why_now}",
            (
                "- Benefit: concise control state and explicit next actions for rapid operator steering."
            ),
            "",
            "Quick actions:",
            "`status` `focus` `autonomy` `approve all`",
            "Plain-text chat is enabled; slash commands remain supported via `/help`.",
        ]
        await self.telegram.send_message("\n".join(lines), priority="medium")

    def _autonomy_context_snapshot(self) -> Dict[str, Any]:
        state = dispatcher.get_control_state()
        strategy_state = self.strategy.execution_state()
        active_venues = [
            venue for venue, item in state.items() if not item.get("paused") and item.get("allocation", 0) > 0
        ]
        paused_venues = [
            venue for venue, item in state.items() if item.get("paused") or item.get("allocation", 0) <= 0
        ]
        total_failures = sum(self._failure_counts.values())
        return {
            "kill_switch_active": self._kill_switch_active,
            "active_venues": active_venues,
            "paused_venues": paused_venues,
            "failure_counts": dict(self._failure_counts),
            "total_failure_pressure": total_failures,
            "owner_directive": self._owner_directive or "",
            "enabled_venues": sorted(list(dispatcher.bot_urls.keys())),
            "autonomy_dispatch_count": self._autonomy_dispatch_count,
            "agent_dispatch_counts": {k: len(v) for k, v in self._agent_dispatch_history.items()},
            "allowed_repo_scope": sorted(list(getattr(self.tv_autonomy, "allowed_repo_scope", set()))) if self.tv_autonomy else [],
            "allowed_project_scope": sorted(list(getattr(self.tv_autonomy, "allowed_project_scope", set()))) if self.tv_autonomy else [],
            "dex_execution_stage": strategy_state.get("dex_execution_stage", "paper"),
            "dex_live_dispatch": bool(strategy_state.get("stage_multiplier", 0) > 0),
            "dex_effective_quantity": float(strategy_state.get("effective_quantity", 0.0)),
            "pending_autonomy_sessions": len(
                [
                    session
                    for session in self._autonomy_sessions.values()
                    if session.get("decision", "pending") == "pending"
                ]
            ),
            "latest_autonomy_session_key": self._latest_autonomy_session_key,
            "venue_profiles": strategy_state.get("venue_profiles", {}),
            "preferred_symbols": strategy_state.get("preferred_symbols", []),
        }

    def _autonomy_trigger_reason(self, context: Dict[str, Any]) -> str:
        """Legacy string-only trigger (callers that need just the string)."""
        return self._autonomy_trigger_info(context)["trigger"]

    def _autonomy_trigger_info(self, context: Dict[str, Any]) -> Dict[str, str]:
        """Return structured trigger info with multi-agent routing.

        Returns ``{"trigger": str, "agent": str, "category": str}``.

        Routing rules:
        - Emergency / infrastructure → OBSIDIAN (always)
        - Scheduled maintenance      → OBSIDIAN
        - Scheduled improvement       → EMERALD (code quality, refactoring)
        - Scheduled review            → SAPPHIRE (security audit, oversight)
        """
        active_count = len(context.get("active_venues", []))
        total_failures = int(context.get("total_failure_pressure", 0))

        # Emergency and infrastructure triggers always go to OBSIDIAN
        if self._kill_switch_active:
            return {"trigger": "kill_switch_active", "agent": "OBSIDIAN", "category": "emergency"}
        if active_count < self._trading_gate_min_active_venues:
            return {"trigger": "venue_shortfall", "agent": "OBSIDIAN", "category": "infrastructure"}
        if total_failures > self._trading_gate_max_failure_pressure:
            return {"trigger": "failure_pressure", "agent": "OBSIDIAN", "category": "infrastructure"}

        # Rotate scheduled cycles across agents
        cycle = self._autonomy_dispatch_count % 3
        if cycle == 0:
            return {"trigger": "scheduled_maintenance", "agent": "OBSIDIAN", "category": "maintenance"}
        elif cycle == 1:
            return {"trigger": "scheduled_improvement", "agent": "EMERALD", "category": "improvement"}
        else:
            return {"trigger": "scheduled_review", "agent": "SAPPHIRE", "category": "review"}

    def _autonomy_request_brief(self, trigger: str, context: Dict[str, Any]) -> Dict[str, str]:
        trigger_key = str(trigger or "").strip().lower()
        active_count = len(context.get("active_venues", []))
        failure_pressure = int(context.get("total_failure_pressure", 0))

        if trigger_key == "venue_shortfall":
            return {
                "reasoning": (
                    f"Active venues dropped to `{active_count}` (minimum required `{self._trading_gate_min_active_venues}`)."
                ),
                "expected_outcome": (
                    "Run venue diagnostics, repair route/config drift, and restore balanced multi-venue execution."
                ),
                "expected_benefit": (
                    "Higher execution resilience and lower concentration risk versus current reduced venue coverage."
                ),
                "deferral_risk": (
                    "Prolonged single-venue dependency increases outage impact and missed execution windows."
                ),
            }

        if trigger_key == "failure_pressure":
            return {
                "reasoning": (
                    f"Failure pressure reached `{failure_pressure}` (gate max `{self._trading_gate_max_failure_pressure}`)."
                ),
                "expected_outcome": (
                    "Triage root-cause failures, tighten guardrails, and stabilize dispatch reliability."
                ),
                "expected_benefit": (
                    "Lower error rate and safer autonomous throughput compared with current elevated incident pressure."
                ),
                "deferral_risk": (
                    "Unresolved failures can cascade into venue deallocations or kill-switch events."
                ),
            }

        if trigger_key == "kill_switch_active":
            return {
                "reasoning": "Kill switch is active and needs targeted remediation work before safe scale-up.",
                "expected_outcome": (
                    "Produce a recovery plan with diagnostics and staged remediations while preserving trade safety."
                ),
                "expected_benefit": (
                    "Faster, evidence-based recovery versus ad-hoc manual troubleshooting from the current halted state."
                ),
                "deferral_risk": "Extended downtime and stale risk posture until root causes are resolved.",
            }

        if trigger_key == "startup_bootstrap":
            return {
                "reasoning": "Service bootstrapped and requires baseline environment verification.",
                "expected_outcome": "Validate runtime config/state and queue fixes for any drift discovered at startup.",
                "expected_benefit": (
                    "Catches misconfiguration early and improves first-hour reliability versus passive warm-up."
                ),
                "deferral_risk": "Silent drift can persist until it surfaces as a production incident.",
            }

        if trigger_key == "manual_telegram":
            return {
                "reasoning": "Owner explicitly requested an autonomy cycle from Telegram.",
                "expected_outcome": "Run a focused improvement pass across Sapphire code/runtime/cloud controls.",
                "expected_benefit": "Shorter turnaround on reliability and performance enhancements versus manual steps.",
                "deferral_risk": "Improvement backlog grows and operational gains are delayed.",
            }

        return {
            "reasoning": "Scheduled autonomy cycle reached its execution window.",
            "expected_outcome": "Perform maintenance and improvement actions inside Sapphire guardrails.",
            "expected_benefit": "Steady reliability/performance uplift versus remaining in static baseline mode.",
            "deferral_risk": "Known optimizations and preventive fixes remain unapplied until a later cycle.",
        }

    def _format_autonomy_decision_brief(
        self,
        session_key: str,
        trigger: str,
        context: Dict[str, Any],
        approval_required: bool,
    ) -> str:
        brief = self._autonomy_request_brief(trigger, context)
        active = context.get("active_venues", [])
        paused = context.get("paused_venues", [])
        active_text = ", ".join(active) if active else "none"
        paused_text = ", ".join(paused) if paused else "none"
        failure_pressure = int(context.get("total_failure_pressure", 0))
        pending = int(context.get("pending_autonomy_sessions", 0))
        dex_stage = str(context.get("dex_execution_stage", "paper"))
        dex_live = "ON" if bool(context.get("dex_live_dispatch", False)) else "OFF"
        key = str(session_key or "").strip() or "n/a"

        # Venue profile summary
        venue_profiles = context.get("venue_profiles", {})
        venue_lines = []
        for venue, profile in venue_profiles.items():
            status = "active" if venue in active else "paused"
            venue_lines.append(f"  • **{profile.get('name', venue)}** ({status}) — {profile.get('role', 'n/a')}")
        venue_block = "\n".join(venue_lines) if venue_lines else "  (no venue profiles)"

        preferred = context.get("preferred_symbols", [])
        preferred_text = ", ".join(preferred[:6]) + ("…" if len(preferred) > 6 else "") if preferred else "none"

        lines = [
            "🤖 **AUTONOMY DECISION BRIEF**",
            f"Session: `{key}` | Trigger: `{trigger}`",
            f"Why now: {brief['reasoning']}",
            (
                f"State: active `{active_text}` | paused `{paused_text}` | "
                f"failures `{failure_pressure}` | stage `{dex_stage}` | live `{dex_live}`"
            ),
            f"Preferred symbols: `{preferred_text}`",
            "Venues:",
            venue_block,
            f"Outcome: {brief['expected_outcome']}",
        ]
        if approval_required and key != "n/a":
            lines.append("Decision: `/approve <session_key> <note>` or `/reject <session_key> <reason>`")
            lines.append("Bulk option: `/approve_all <note>`")
        elif approval_required:
            lines.append("Decision gate is ON, but no session key was returned from dispatch.")
        else:
            lines.append("Decision mode: `AUTO-APPROVE`")
        return "\n".join(lines)

    def _record_autonomy_session(self, session_key: str, trigger: str, instruction: str) -> None:
        key = str(session_key or "").strip()
        if not key:
            return

        now = int(time.time())
        trimmed_instruction = str(instruction or "").strip()
        if len(trimmed_instruction) > 260:
            trimmed_instruction = trimmed_instruction[:257] + "..."

        self._autonomy_sessions[key] = {
            "session_key": key,
            "trigger": str(trigger or "").strip(),
            "instruction": trimmed_instruction,
            "created_at": now,
            "decision": "pending",
            "decision_note": "",
            "decision_at": 0,
            "dispatched": True,
        }
        self._latest_autonomy_session_key = key

        # Phase 3: Create forum approval topic for audit trail
        try:
            self.forum.create_approval_topic(
                title=f"Autonomy session: {str(trigger or 'unknown').strip()[:50]}",
                body=(
                    f"**Session key:** `{key}`\n"
                    f"**Trigger:** {str(trigger or 'manual').strip()}\n"
                    f"**Instruction:** {trimmed_instruction}\n\n"
                    "Vote ⬆ to approve or ⬇ to reject."
                ),
                session_key=key,
                author="SAPPHIRE",
                category="platform",
            )
        except Exception as exc:
            logger.warning(f"Forum approval topic creation failed: {exc}")

        if len(self._autonomy_sessions) > self._autonomy_session_history_max:
            oldest = sorted(
                self._autonomy_sessions.items(),
                key=lambda item: int(item[1].get("created_at", 0)),
            )[: len(self._autonomy_sessions) - self._autonomy_session_history_max]
            for old_key, _ in oldest:
                self._autonomy_sessions.pop(old_key, None)

    def _resolve_autonomy_session_key(self, raw_session_key: str) -> str:
        candidate = str(raw_session_key or "").strip()
        if candidate and candidate.lower() != "latest":
            return candidate

        if self._latest_autonomy_session_key:
            latest_entry = self._autonomy_sessions.get(self._latest_autonomy_session_key, {})
            if latest_entry and latest_entry.get("decision", "pending") == "pending":
                return self._latest_autonomy_session_key

        pending = [
            item
            for item in self._autonomy_sessions.values()
            if item.get("decision", "pending") == "pending"
        ]
        if not pending:
            return ""
        pending.sort(key=lambda item: int(item.get("created_at", 0)), reverse=True)
        return str(pending[0].get("session_key", "")).strip()

    def _pending_autonomy_session_keys(self) -> List[str]:
        pending = [
            item
            for item in self._autonomy_sessions.values()
            if item.get("decision", "pending") == "pending"
        ]
        pending.sort(key=lambda item: int(item.get("created_at", 0)))
        keys = [str(item.get("session_key", "")).strip() for item in pending]
        return [key for key in keys if key]

    async def _apply_autonomy_session_decision(
        self,
        session_key: str,
        decision: str,
        note: str = "",
        source: str = "owner",
    ) -> Dict[str, Any]:
        normalized_decision = str(decision or "").strip().upper()
        if normalized_decision not in {"APPROVE", "REJECT"}:
            return {"dispatched": False, "reason": "invalid_decision", "session_key": ""}

        resolved_key = self._resolve_autonomy_session_key(session_key)
        if not resolved_key:
            return {"dispatched": False, "reason": "session_not_found", "session_key": ""}

        trimmed_note = str(note or "").strip()
        if len(trimmed_note) > 400:
            trimmed_note = trimmed_note[:400]

        entry = self._autonomy_sessions.get(resolved_key, {"session_key": resolved_key})
        entry["decision"] = "approved" if normalized_decision == "APPROVE" else "rejected"
        entry["decision_note"] = trimmed_note
        entry["decision_at"] = int(time.time())
        entry["decision_source"] = source
        self._autonomy_sessions[resolved_key] = entry

        if self.openclaw_dispatcher and self.openclaw_dispatcher.enabled:
            hook_result = await self.openclaw_dispatcher.dispatch_session_decision(
                session_key=resolved_key,
                decision=normalized_decision,
                note=trimmed_note,
            )
        elif self.tv_autonomy:
            hook_result = await self.tv_autonomy.dispatch_session_decision(
                session_key=resolved_key,
                decision=normalized_decision,
                note=trimmed_note,
            )
        else:
            hook_result = {"dispatched": False, "reason": "no_dispatcher_available"}
        dispatched = bool(hook_result.get("dispatched"))
        reason = str(hook_result.get("reason", "")).strip()
        log_level = "info" if dispatched else "warning"
        self._record_system_log(
            (
                f"Autonomy session {resolved_key} -> {normalized_decision}"
                + (f" ({source})" if source else "")
                + (f" failed: {reason}" if reason and not dispatched else "")
            ),
            level=log_level,
            tags=["autonomy", "decision"],
            metadata={
                "session_key": resolved_key,
                "decision": normalized_decision,
                "source": source,
                "reason": reason,
                "dispatched": dispatched,
            },
        )
        return {
            "dispatched": dispatched,
            "reason": reason,
            "session_key": resolved_key,
            "decision": normalized_decision,
            "dispatch_session_key": str(hook_result.get("session_key", "")).strip(),
        }

    # ── Graduated Escalation: Code & Infrastructure Proposals ──────

    def _record_proposal(
        self,
        agent_id: str,
        capability: Capability,
        description: str,
        context: Optional[Dict[str, Any]] = None,
        diff: str = "",
        files_changed: Optional[List[str]] = None,
    ) -> str:
        """Record a pending proposal for owner review. Returns proposal key."""
        self._proposal_counter += 1
        key = f"P-{self._proposal_counter:04d}"
        risk = self._approval_policy.evaluate(agent_id, capability, context)
        self._proposals[key] = {
            "proposal_key": key,
            "agent_id": agent_id,
            "capability": capability.name,
            "description": description[:500],
            "risk_tier": risk,
            "diff": diff[:5000],
            "files_changed": (files_changed or [])[:20],
            "context": context or {},
            "decision": "pending",
            "decision_note": "",
            "decision_at": 0,
            "created_at": int(time.time()),
        }
        # Trim old proposals (keep last 100)
        if len(self._proposals) > 100:
            oldest_keys = sorted(self._proposals.keys())[:len(self._proposals) - 100]
            for k in oldest_keys:
                del self._proposals[k]
        return key

    async def _apply_proposal_decision(
        self,
        proposal_key: str,
        decision: str,
        note: str = "",
        source: str = "owner",
    ) -> Dict[str, Any]:
        """Apply an owner decision to a pending proposal."""
        normalized = decision.strip().upper()
        if normalized not in ("APPROVE", "REJECT"):
            return {"ok": False, "reason": "invalid_decision"}
        entry = self._proposals.get(proposal_key)
        if not entry:
            return {"ok": False, "reason": "proposal_not_found"}
        if entry["decision"] != "pending":
            return {"ok": False, "reason": "already_decided"}

        entry["decision"] = "approved" if normalized == "APPROVE" else "rejected"
        entry["decision_note"] = note[:500]
        entry["decision_at"] = int(time.time())
        self._record_system_log(
            f"Proposal {proposal_key} {entry['decision']} by {source}: {entry['description'][:100]}",
            level="info",
            tags=["proposal", entry["decision"]],
            metadata={"proposal_key": proposal_key, "source": source},
        )
        return {"ok": True, "decision": entry["decision"], "proposal_key": proposal_key}

    def _pending_proposals(self) -> List[Dict[str, Any]]:
        """Return all pending proposals sorted by creation time."""
        return sorted(
            [p for p in self._proposals.values() if p["decision"] == "pending"],
            key=lambda p: p["created_at"],
        )

    async def _evaluate_and_route_operation(
        self,
        agent_id: str,
        capability: Capability,
        description: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Route an operation through graduated approval based on risk tier.

        Returns ``{'executed': True, 'policy': ...}`` for auto/notify,
        or ``{'executed': False, 'proposal_key': ...}`` for require_approval.
        """
        gate.require(agent_id, capability)
        policy = self._approval_policy.evaluate(agent_id, capability, context)

        if policy == "auto_approve":
            return {"executed": True, "policy": "auto_approve"}

        if policy == "notify_proceed":
            await self.telegram.send_as(
                OBSIDIAN,
                f"⚡ Proceeding: {description}\nRisk: medium | Agent: {agent_id}",
            )
            return {"executed": True, "policy": "notify_proceed"}

        # require_approval — record proposal and await owner decision
        proposal_key = self._record_proposal(
            agent_id, capability, description, context
        )
        await self.telegram.send_as(
            OBSIDIAN,
            (
                f"🔴 **Approval Required**\n"
                f"Proposal `{proposal_key}`: {description}\n"
                f"Risk: HIGH | Agent: {agent_id}\n\n"
                f"`/approve_proposal {proposal_key}` or `/reject_proposal {proposal_key}`"
            ),
        )
        return {"executed": False, "policy": "require_approval", "proposal_key": proposal_key}

    # ── Health Diagnostics ───────────────────────────────────────────

    async def _run_health_diagnostics(self) -> Dict[str, Any]:
        """Run health checks and return detected issues."""
        issues: List[Dict[str, Any]] = []
        # Check venue health
        try:
            state = dispatcher.get_control_state()
            for venue, info in state.items():
                if info.get("paused"):
                    issues.append({
                        "type": "venue_paused",
                        "severity": "high",
                        "venue": venue,
                        "reason": info.get("pause_reason", "unknown"),
                        "agent": "OBSIDIAN",
                    })
        except Exception:
            pass
        # Check failure pressure
        total_failures = sum(self._failure_counts.values())
        threshold = self._trading_gate_max_failure_pressure
        if total_failures > threshold * 0.7:
            issues.append({
                "type": "failure_pressure_warning",
                "severity": "medium" if total_failures <= threshold else "high",
                "pressure": total_failures,
                "threshold": threshold,
                "agent": "OBSIDIAN",
            })
        # Check kill switch
        if self._kill_switch_active:
            issues.append({
                "type": "kill_switch_active",
                "severity": "critical",
                "agent": "OBSIDIAN",
            })
        return {"issues": issues, "checked_at": int(time.time())}

    @staticmethod
    def _parse_session_decision_payload(payload_text: str) -> Dict[str, str]:
        text = str(payload_text or "").strip()
        if not text:
            return {"session_key": "", "note": ""}

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return {
                    "session_key": str(parsed.get("session_key", "")).strip(),
                    "note": str(parsed.get("note", "")).strip(),
                }
        except Exception:
            pass

        if " " in text:
            head, tail = text.split(" ", 1)
            return {"session_key": head.strip(), "note": tail.strip()}

        return {"session_key": text, "note": ""}

    @staticmethod
    def _parse_json_payload(payload_text: str) -> Dict[str, Any]:
        text = str(payload_text or "").strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except Exception:
            return {}
        if isinstance(parsed, dict):
            return parsed
        return {}

    # Map agent ID strings to AgentPersona objects for Telegram messages
    _AGENT_PERSONA_MAP = {
        "OBSIDIAN": OBSIDIAN,
        "EMERALD": EMERALD,
        "SAPPHIRE": SAPPHIRE,
    }

    # Agent-specific instruction focuses
    _AGENT_INSTRUCTION_FOCUS = {
        "OBSIDIAN": (
            "Execute an autonomous maintenance cycle for infrastructure + cloud + CI/CD. "
            "Prioritize production safety first, then reliability, then performance."
        ),
        "EMERALD": (
            "Execute an autonomous improvement cycle for code quality + architecture + testing. "
            "Prioritize test coverage, refactoring, and clean architecture."
        ),
        "SAPPHIRE": (
            "Execute an autonomous security review cycle for risk + audit + code review. "
            "Prioritize security posture, permission boundaries, and injection hardening."
        ),
    }

    async def _dispatch_full_autonomy_cycle(self, trigger: str, force: bool = False, agent_id: str = "OBSIDIAN") -> Dict[str, Any]:
        gate.require(agent_id, Capability.AUTONOMY_DISPATCH, f"autonomy_cycle({trigger!r})")
        if not self._full_autonomy_enabled:
            return {"dispatched": False, "reason": "full_autonomy_disabled"}

        now = time.time()
        since_last = now - self._autonomy_last_dispatch_at
        if not force and since_last < self._autonomy_min_dispatch_interval_seconds:
            return {
                "dispatched": False,
                "reason": "rate_limited",
                "retry_after_seconds": int(self._autonomy_min_dispatch_interval_seconds - since_last),
            }

        context = self._autonomy_context_snapshot()
        directive = self._owner_directive.strip() or "Optimize Sapphire uptime, reliability, and execution quality."
        venue_hints = "; ".join(
            f"{v}: {p.get('role', '')}" for v, p in context.get("venue_profiles", {}).items()
        )
        preferred = ", ".join(context.get("preferred_symbols", [])[:6])
        agent_focus = self._AGENT_INSTRUCTION_FOCUS.get(agent_id.upper(), self._AGENT_INSTRUCTION_FOCUS["OBSIDIAN"])
        instruction = (
            f"{directive} {agent_focus} "
            "IMPORTANT: Venues are segregated specialists with no cross-venue arbitrage. "
            f"Venue roles: {venue_hints}. "
            f"Preferred symbols (slight bias): {preferred}. "
            "Agents may trade any symbol but should favour the preferred list."
        )
        brief = self._autonomy_request_brief(trigger, context)

        if self._autonomy_dry_run:
            await self.telegram.send_message(
                (
                    "🧪 Full autonomy dry-run cycle prepared.\n"
                    f"Agent: `{agent_id}` | Trigger: `{trigger}`\n"
                    f"Active venues: `{', '.join(context['active_venues']) if context['active_venues'] else 'none'}`\n"
                    f"Failure pressure: `{context['total_failure_pressure']}`\n"
                    f"Why now: {brief['reasoning']}\n"
                    f"Expected outcome: {brief['expected_outcome']}\n"
                    f"Benefit vs current state: {brief['expected_benefit']}"
                ),
                priority="medium",
            )
            return {"dispatched": False, "reason": "dry_run", "trigger": trigger}

        # Prefer OpenClaw gateway dispatcher, fall back to tv_autonomy
        if self.openclaw_dispatcher.enabled:
            hook_result = await self.openclaw_dispatcher.dispatch_instruction(
                agent_id=agent_id,
                instruction=instruction,
                trigger=trigger,
                context=context,
                allow_code_changes=self._autonomy_allow_code_changes,
                allow_gcloud_changes=self._autonomy_allow_gcloud_changes,
            )
        elif self.tv_autonomy:
            hook_result = await self.tv_autonomy.dispatch_environment_instruction(
                instruction=instruction,
                trigger=trigger,
                context=context,
                allow_code_changes=self._autonomy_allow_code_changes,
                allow_gcloud_changes=self._autonomy_allow_gcloud_changes,
            )
        else:
            return {"dispatched": False, "reason": "no_dispatcher_available", "trigger": trigger}

        # Resolve agent persona for Telegram messages
        persona = self._AGENT_PERSONA_MAP.get(agent_id.upper(), OBSIDIAN)

        if hook_result.get("dispatched"):
            self._autonomy_last_dispatch_at = now
            self._autonomy_last_trigger = trigger
            self._autonomy_dispatch_count += 1
            # Track per-agent dispatch history
            agent_key = agent_id.upper()
            if agent_key in self._agent_dispatch_history:
                self._agent_dispatch_history[agent_key].append({
                    "trigger": trigger, "ts": now,
                })
                if len(self._agent_dispatch_history[agent_key]) > self._agent_dispatch_history_max:
                    self._agent_dispatch_history[agent_key] = self._agent_dispatch_history[agent_key][-self._agent_dispatch_history_max:]
            session_key = str(hook_result.get("session_key", "")).strip()
            self._record_autonomy_session(session_key, trigger, instruction)
            self._record_system_log(
                f"Full autonomy cycle dispatched ({trigger}) → {agent_id}",
                level="info",
                tags=["autonomy", "dispatch", agent_id.lower()],
                metadata={"session_key": hook_result.get("session_key", ""), "agent": agent_id},
            )
            self.telegram.record_activity(
                persona, "autonomy",
                f"Dispatched cycle: {trigger}",
            )
            if session_key and not self._autonomy_require_owner_approval:
                auto_result = await self._apply_autonomy_session_decision(
                    session_key=session_key,
                    decision="APPROVE",
                    note=f"Auto-approved by Sapphire autonomy policy (agent: {agent_id}).",
                    source="policy_auto",
                )
                decision_brief = self._format_autonomy_decision_brief(
                    session_key=session_key,
                    trigger=trigger,
                    context=context,
                    approval_required=False,
                )
                if auto_result.get("dispatched"):
                    await self.telegram.send_as(
                        persona,
                        f"Autonomy cycle auto-approved (`{trigger}`).\n{decision_brief}",
                    )
                else:
                    await self.telegram.send_as(
                        persona,
                        (
                            f"⚠️ Autonomy cycle approved locally but dispatch failed for `{session_key}`.\n"
                            f"Reason: `{auto_result.get('reason', 'unknown')}`"
                        ),
                    )
            else:
                decision_brief = self._format_autonomy_decision_brief(
                    session_key=session_key,
                    trigger=trigger,
                    context=context,
                    approval_required=self._autonomy_require_owner_approval,
                )
                await self.telegram.send_as(
                    persona,
                    f"Autonomy cycle needs your approval (`{trigger}`).\n{decision_brief}",
                    expects_reply=True,
                    pending_action="APPROVE_SESSION",
                    pending_metadata={"session_key": session_key},
                )
        else:
            reason = hook_result.get("reason", "unknown")
            # Configuration-state reasons are not actionable — log quietly,
            # don't spam Telegram on every scheduled cycle.
            config_reasons = {
                "autonomy_disabled",
                "hook_url_missing",
                "hook_token_missing",
                "chat_id_missing",
                "dry_run",
                "full_autonomy_disabled",
            }
            if reason in config_reasons:
                # Silently skip — these are expected when the TV autonomy
                # plugin or OpenClaw hook is intentionally unconfigured.
                logger.debug(f"Autonomy dispatch skipped ({trigger}): {reason}")
            else:
                self._record_system_log(
                    f"Full autonomy dispatch unavailable ({trigger}): {reason}",
                    level="warning",
                    tags=["autonomy", "dispatch"],
                )
                await self.telegram.send_as(
                    persona,
                    f"Autonomy dispatch unavailable — `{trigger}`: {reason}",
                )
        return hook_result

    async def _autonomy_ops_loop(self) -> None:
        while self.running:
            try:
                await asyncio.sleep(self._autonomy_loop_seconds)
                context = self._autonomy_context_snapshot()
                trigger_info = self._autonomy_trigger_info(context)
                await self._dispatch_full_autonomy_cycle(
                    trigger=trigger_info["trigger"],
                    force=False,
                    agent_id=trigger_info["agent"],
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Autonomy loop error: {exc}")

    async def _handle_control_command(self, target: str, action: str, value: float) -> None:
        """Dispatch control commands to extracted handlers in telegram_handlers.py."""
        await dispatch_control_command(self, target, action, value)

    async def _handle_alpha_scanner_signal(self, signal: Dict[str, Any]) -> None:
        """Callback for internal alpha scanner — feeds signals into the execution pipeline."""
        source = signal.get("source", "alpha_scanner")
        symbol = signal.get("symbol", "")
        action = signal.get("action", "")
        confidence = signal.get("_confidence", 0)
        reasoning = signal.get("_reasoning", "")[:200]

        logger.info(
            f"🔍 Alpha scanner signal: {action.upper()} {symbol} "
            f"(conf={confidence:.2f}, source={source})"
        )

        # Record activity under EMERALD (strategy/analysis agent)
        self.telegram.record_activity(
            EMERALD, "alpha_signal",
            f"{action.upper()} {symbol} (conf={confidence:.0%})",
        )

        # Feed into the same pipeline as TradingView signals
        try:
            result = await self._handle_tradingview_signal(signal)
            accepted = result.get("accepted", "unknown")

            if accepted == "executed":
                await self.telegram.send_as(
                    EMERALD,
                    f"🔍 Internal alpha executed: `{action.upper()} {symbol}` "
                    f"(conf={confidence:.0%})\n"
                    f"Reasoning: {reasoning}",
                )
            elif accepted == "dry_run":
                await self.telegram.send_as(
                    EMERALD,
                    f"🔍 Alpha signal (dry-run): `{action.upper()} {symbol}` "
                    f"(conf={confidence:.0%}) — set `SAPPHIRE_DEX_EXECUTION_STAGE=staged_live|full_live` to execute",
                )
            else:
                logger.info(f"Alpha signal {symbol}: pipeline returned {accepted}")

            # Resolve pending count
            self.alpha_scanner.resolve_signal(
                result.get("signal_key", ""), accepted == "executed"
            )
        except Exception as exc:
            logger.error(f"Alpha scanner pipeline error: {exc}")
            self.alpha_scanner.resolve_signal("", False)

    async def _handle_grid_trader_signal(self, signal: Dict[str, Any]) -> None:
        """Callback for grid trader signals — feeds signals into the execution pipeline."""
        source = signal.get("source", "grid_trader")
        symbol = signal.get("symbol", "")
        action = signal.get("action", "")
        price = signal.get("price", 0)
        level = signal.get("grid", {}).get("level")

        logger.info(
            f"🧭 Grid trader signal: {action} {symbol} @ {price} (level={level}, source={source})"
        )

        # Record activity under EMERALD (strategy/analysis agent)
        self.telegram.record_activity(
            EMERALD, "grid_signal",
            f"{action} {symbol} (lvl {level})",
        )

        try:
            result = await self._handle_tradingview_signal(signal)
            accepted = result.get("accepted", "unknown")

            if accepted == "executed":
                await self.telegram.send_as(
                    EMERALD,
                    f"🧭 Grid executed: `{action} {symbol}` @ `{price}` (lvl {level})",
                )
            elif accepted == "dry_run":
                await self.telegram.send_as(
                    EMERALD,
                    f"🧭 Grid signal (dry-run): `{action} {symbol}` @ `{price}`",
                )
            else:
                logger.info(f"Grid signal {symbol}: pipeline returned {accepted}")
        except Exception as exc:
            logger.error(f"Grid trader pipeline error: {exc}")



    async def _record_trade_outcome(self, platform: str, success: bool, error_message: str = "") -> None:
        venue = self._normalize_platform(platform)
        if venue not in dispatcher.bot_urls:
            return

        if success:
            self._failure_counts[venue] = 0
            self._manual_review_venues.discard(venue)
            return

        category, severity = classify_error(error_message or "")
        hard_reason = self._hard_failure_reason(error_message)
        hard_failure = bool(hard_reason) or category in {
            ErrorCategory.CONFIGURATION,
            ErrorCategory.AUTHENTICATION,
        }

        self._failure_counts[venue] += 1
        failures = self._failure_counts[venue]
        if hard_failure:
            failures = max(failures, self._deallocation_failure_threshold)
            self._failure_counts[venue] = failures

        if failures < self._deallocation_failure_threshold:
            return
        if venue in self._auto_deallocated:
            return

        hold_reason = f"auto-deallocated after {failures} failures"
        cooldown_seconds = self._deallocation_cooldown_seconds
        alert_type = "auto_deallocation"
        if hard_failure:
            hold_reason = (
                f"manual-review hold ({hard_reason})"
                if hard_reason
                else f"manual-review hold ({category.value})"
            )
            cooldown_seconds = max(
                self._deallocation_cooldown_seconds,
                self._hard_failure_cooldown_seconds,
            )
            alert_type = "hard_failure_hold"
            self._manual_review_venues.add(venue)

        dispatcher.set_venue_allocation(venue, 0.0)
        dispatcher.pause_venue(
            venue,
            reason=hold_reason,
            cooldown_seconds=cooldown_seconds,
        )
        self._auto_deallocated.add(venue)
        self._record_system_log(
            (
                f"{venue} manual-review hold after hard failure ({hard_reason or category.value})"
                if hard_failure
                else f"{venue} auto-deallocated after {failures} failures"
            ),
            level="error",
            tags=["risk", "auto_deallocation"],
            metadata={
                "failures": failures,
                "hard_failure": hard_failure,
                "hard_reason": hard_reason,
                "error_category": category.value,
                "error_severity": int(severity),
            },
        )

        await self._publish_risk_alert(
            action="halt_trading",
            severity="critical" if hard_failure else "critical",
            alert_type=alert_type,
            message=(
                (
                    f"{venue} placed in manual-review hold due to hard failure "
                    f"({hard_reason or category.value})."
                )
                if hard_failure
                else f"{venue} auto-deallocated after {failures} consecutive failures."
            )
            + (
                f" Cooldown {cooldown_seconds}s."
            ),
            platforms=[venue],
            metadata={
                "source": "alpha-engine",
                "failure_count": failures,
                "last_error": error_message[:200],
                "hard_failure": hard_failure,
                "hard_reason": hard_reason,
                "error_category": category.value,
            },
        )

        if hard_failure:
            await self.telegram.send_as(
                OBSIDIAN,
                f"🛑 Paused **{venue}** — `{hard_reason or category.value}` ({failures} failures). Needs your `/resume` to restart.",
                expects_reply=True,
                pending_action="RESUME_TRADING",
                pending_metadata={"venue": venue},
            )
        else:
            await self.telegram.send_as(
                OBSIDIAN,
                f"Auto-deallocated **{venue}** after {failures} failures. Cooldown: {cooldown_seconds}s.",
            )

    async def _heartbeat_loop(self) -> None:
        while self.running:
            try:
                await asyncio.sleep(max(60, self._heartbeat_interval_seconds))
                await self._send_heartbeat("scheduled")

                resumed = dispatcher.resume_expired_venues()
                for venue in resumed:
                    if venue in self._manual_review_venues:
                        dispatcher.set_venue_allocation(venue, 0.0)
                        dispatcher.pause_venue(
                            venue,
                            reason="manual-review hold persists",
                            cooldown_seconds=self._hard_failure_cooldown_seconds,
                        )
                        self._record_system_log(
                            f"{venue} remained paused (manual-review hold)",
                            level="warning",
                            tags=["risk", "manual_review_hold"],
                        )
                        await self.telegram.send_message(
                            (
                                f"⏸️ `{venue}` remains paused under manual-review hold.\n"
                                "Use `/status` to inspect state, then `/allocation <venue> 1` or `/resume` to release."
                            ),
                            priority="medium",
                        )
                        continue

                    if venue in self._auto_deallocated:
                        dispatcher.set_venue_allocation(venue, self._default_venue_allocation)
                        self._auto_deallocated.discard(venue)
                        self._failure_counts[venue] = 0
                        self._record_system_log(
                            f"{venue} resumed after cooldown",
                            level="info",
                            tags=["risk", "auto_resume"],
                        )
                        await self._publish_risk_alert(
                            action="resume_trading",
                            severity="warning",
                            alert_type="auto_resume",
                            message=f"{venue} cooldown complete; trading resumed automatically.",
                            platforms=[venue],
                            metadata={"source": "alpha-engine"},
                        )
                        await self.telegram.send_message(
                            f"✅ `{venue}` cooldown complete. Allocation restored to `{self._default_venue_allocation*100:.0f}%`.",
                            priority="medium",
                        )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Heartbeat loop error: {exc}")

    async def _handle_telegram_message(self, text: str):
        """Handle conversational messages via ChatIntentEngine.

        This is the main natural-language handler — the owner talks on
        Telegram like a personal assistant and we route to the right action.
        """
        from src.telegram_handlers import dispatch_control_command

        try:
            intent = await self.chat_intent.analyze(text)
            intent_type = intent.get("intent")
            params = intent.get("parameters", {})

            if intent_type == "status_report":
                await self._send_status_snapshot()

            elif intent_type == "control_trading":
                action = params.get("action", "").upper()
                target = params.get("target", "ALL").upper()
                value = float(params.get("value", 0.0))

                if action == "PAUSE":
                    await self._handle_control_command("ALL", "HALT_TRADING", 0.0)
                    await self.telegram.send_as(
                        OBSIDIAN, f"Trading halted on {target}. Say 'resume' when you're ready."
                    )
                elif action == "RESUME":
                    await self._handle_control_command("ALL", "RESUME_TRADING", 0.0)
                    await self.telegram.send_as(
                        OBSIDIAN, f"Trading resumed on {target}. We're back in action."
                    )
                elif action == "SET_ALLOCATION":
                    await self._handle_control_command(
                        target, "SET_ALLOCATION", value
                    )
                    await self.telegram.send_as(
                        SAPPHIRE, f"Allocation for {target} set to {value:.0%}."
                    )

            elif intent_type == "media_publish":
                topic = params.get("topic", "market update")
                targets = params.get("channels", ["twitter", "substack"])
                await self.media_manager.request_publish(
                    topic=topic, targets=targets
                )
                await self.telegram.send_as(
                    EMERALD,
                    f"Drafting something about {topic} for {', '.join(targets)}. I'll send it for your review.",
                )

            elif intent_type == "media_status":
                status = self.media_manager.get_status_snapshot()
                mode = status.get("mode", "unknown")
                pending = status.get("pending_requests", 0)
                if pending > 0:
                    await self.telegram.send_as(
                        EMERALD,
                        f"We have {pending} piece(s) in the queue. Mode: {mode}.",
                    )
                else:
                    await self.telegram.send_as(
                        EMERALD, f"Queue is clear — nothing pending. Mode: {mode}."
                    )

            elif intent_type == "operations":
                # Route operations to the existing control handler chain
                action = params.get("action", "").upper()
                target = params.get("target", "ALL")
                await dispatch_control_command(self, target, action, 0.0)

            elif intent_type == "agent_question":
                # Owner asked a substantive question — route to the right agent
                question = params.get("question", text)
                agent_name = params.get("agent", "auto").upper()

                # Pick agent persona for the ack message
                if agent_name == "OBSIDIAN":
                    agent_persona = OBSIDIAN
                elif agent_name == "EMERALD":
                    agent_persona = EMERALD
                else:
                    agent_persona = SAPPHIRE

                # Try to dispatch to OpenClaw for a real agent answer
                if hasattr(self, "openclaw_dispatcher") and self.openclaw_dispatcher.enabled:
                    await self.telegram.send_as(
                        agent_persona, "Let me think about that..."
                    )
                    agent_id = agent_name if agent_name != "AUTO" else "OBSIDIAN"
                    await self.openclaw_dispatcher.dispatch_instruction(
                        agent_id=agent_id,
                        instruction=question,
                        context={"source": "owner_question", "original_text": text},
                        trigger="owner_question",
                    )
                else:
                    # Fallback: use the general_chat reply from the LLM
                    await self.telegram.send_as(
                        agent_persona,
                        "Good question — I'd need the full agent framework online to give you a proper answer. "
                        "The gateway isn't connected right now.",
                    )

            elif intent_type == "general_chat":
                reply = params.get("reply", "")
                if reply:
                    await self.telegram.send_as(SAPPHIRE, reply)
                else:
                    await self.telegram.send_as(SAPPHIRE, "I'm here — what do you need?")

            else:
                # Unknown intent — still respond warmly
                await self.telegram.send_as(
                    SAPPHIRE,
                    "I'm not sure what to do with that, but I'm listening. Try asking about status, trading, or operations.",
                )

        except Exception as e:
            logger.error(f"Chat intent handling failed: {e}")
            await self.telegram.send_as(
                SAPPHIRE,
                "Something went wrong processing that. Try again or use a direct command.",
            )

    async def _handle_telegram_command(
        self, platform: str, symbol: str, action: str, quantity: float
    ):
        """Callback for Telegram @mentions to trigger manual overrides."""
        if not self._telegram_rate_limiter.check(action):
            await self.telegram.send_message(
                f"🛡️ Rate limit reached for `{action}`. Please wait before retrying.",
                priority="medium",
            )
            return

        logger.warning(f"🚨 TELEGRAM OVERRIDE: {platform} {action} {quantity} {symbol}")

        try:
            await self._handle_telegram_command_inner(platform, symbol, action, quantity)
        except PermissionDenied as exc:
            logger.warning(f"🚫 Permission denied: {exc}")
            await self.telegram.send_message(
                f"🚫 *Permission Denied*\nAgent `{exc.agent_id}` lacks `{exc.capability.name}`.\n_{exc.detail}_",
                priority="high",
            )

    async def _handle_telegram_command_inner(
        self, platform: str, symbol: str, action: str, quantity: float
    ):
        """Inner handler — separated so PermissionDenied bubbles up cleanly."""
        normalized_platform = self._normalize_platform(platform)

        if normalized_platform == "CONTROL":
            await self._handle_control_command(symbol, action, quantity)
            return

        # intercept AI commands
        if platform.lower() == "alpha" and action.lower() in ("recap", "analyze", "report"):
            await self.telegram.send_message("🧠 **Processing AI Request...**", priority="medium")
            analysis_type = "full" if action.lower() == "report" else "recap"
            await self.ai.force_analyze(analysis_type)
            return

        if self._kill_switch_active:
            await self.telegram.send_message(
                "🛑 Kill switch is active. Use `/resume` before dispatching manual trades.",
                priority="high",
            )
            return

        if not self._symbol_allowed_for_venue(normalized_platform, symbol):
            await self.telegram.send_message(
                f"⚠️ Manual trade blocked: `{symbol}` is outside allowed symbol scope for `{normalized_platform}`.",
                priority="high",
            )
            return

        quantity_guard = self._apply_min_notional_guard(normalized_platform, symbol, quantity)
        if quantity_guard.get("blocked"):
            await self.telegram.send_message(
                (
                    f"⚠️ Manual trade blocked on `{normalized_platform}` by min-notional guard.\n"
                    f"Reason: `{quantity_guard.get('reason', 'guard_blocked')}`\n"
                    f"Required qty: `{quantity_guard.get('required_quantity', 'n/a')}` | "
                    f"Cap: `{quantity_guard.get('cap_quantity', 'n/a')}`"
                ),
                priority="high",
            )
            return

        dispatch_quantity = float(quantity_guard.get("quantity", quantity))
        if quantity_guard.get("adjusted"):
            await self.telegram.send_message(
                (
                    f"🧮 Manual trade quantity auto-adjusted on `{normalized_platform}` to `{dispatch_quantity}` "
                    f"to satisfy minimum notional guardrails."
                ),
                priority="medium",
            )

        # Permission gate: manual trades require TRADE_EXECUTE
        gate.require("SAPPHIRE", Capability.TRADE_EXECUTE, f"manual_trade({action} {symbol} on {normalized_platform})")

        dispatched = await dispatcher.send_command(
            normalized_platform,
            {
                "action": action,
                "symbol": symbol,
                "quantity": dispatch_quantity,
                "source": "telegram_override",
            },
        )
        if dispatched:
            await self.telegram.send_message(
                (
                    f"✅ Manual trade dispatched: `{normalized_platform}` "
                    f"`{action}` `{dispatch_quantity}` `{symbol}`."
                ),
                priority="high",
            )
            return

        dispatch_error = dispatcher.get_last_dispatch_error(normalized_platform)
        await self.telegram.send_message(
            (
                f"❌ Manual trade dispatch failed on `{normalized_platform}`.\n"
                f"Reason: `{dispatch_error.get('reason', 'unknown')}`\n"
                f"Status: `{dispatch_error.get('status', 'n/a')}`\n"
                f"Detail: `{str(dispatch_error.get('body', 'n/a'))[:160]}`"
            ),
            priority="high",
        )

    async def _prediction_market_forum_loop(self) -> None:
        """Periodically post prediction market summaries to the forum."""
        while self.running:
            try:
                await asyncio.sleep(300)  # Check every 5 min
                # Record current signals for accuracy tracking
                self.prediction_aggregator.record_signals_for_accuracy()
                summary = self.prediction_aggregator.generate_forum_summary()
                if summary:
                    await self.forum.create_topic(
                        lane=summary["lane"],
                        category=summary["category"],
                        title=summary["title"],
                        body=summary["body"],
                        author=summary["author"],
                        tags=summary.get("tags", []),
                        priority=summary.get("priority", "medium"),
                    )
                    logger.info(f"🔮 Posted prediction market summary to forum")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"Prediction market forum loop error: {exc}")
                await asyncio.sleep(60)

    async def start(self):
        logger.info("🚀 Sapphire Alpha Engine Starting (uvloop enabled)")
        self.running = True
        self._record_system_log(
            "Sapphire Alpha Engine starting",
            level="info",
            tags=["system", "startup"],
        )

        if self._kill_switch_active:
            logger.warning(
                "⚠️ Kill switch ACTIVE on startup (SAPPHIRE_KILL_SWITCH_ACTIVE=true). "
                "Trading is halted until manually resumed."
            )
            self._record_system_log(
                "Kill switch active on startup via SAPPHIRE_KILL_SWITCH_ACTIVE env var",
                level="warning",
                tags=["risk", "kill_switch", "startup"],
            )

        # Start Health Server (Cloud Run)
        # Start Health Server (Cloud Run)
        if self._telegram_webhook_mode:
            await start_health_server(
                telegram_update_handler=self.telegram._process_update,
                telegram_webhook_secret=self._telegram_webhook_secret,
                control_api_token=self._control_api_token,
                market_ohlc_handler=self._handle_market_ohlc_request,
                platform_status_handler=self._handle_platform_status_request,
                control_status_handler=self._handle_control_status_request,
                routing_info_handler=self._handle_routing_info_request,
                performance_stats_handler=self._handle_performance_stats_request,
                system_logs_handler=self._handle_system_logs_request,
                forum_topics_handler=self._handle_forum_topics_request,
                forum_create_topic_handler=self._handle_forum_create_topic_request,
                forum_topic_detail_handler=self._handle_forum_topic_detail_request,
                forum_replies_handler=self._handle_forum_replies_request,
                forum_scout_status_handler=self._handle_forum_scout_status_request,
                forum_scout_register_handler=self._handle_forum_scout_register_request,
                forum_scout_publish_handler=self._handle_forum_scout_publish_request,
                security_skills_status_handler=self._handle_security_skills_status_request,
                security_skills_scan_handler=self._handle_security_skill_scan_request,
                prediction_dashboard_handler=self._handle_prediction_dashboard_request,
            )
        else:
            await start_health_server(
                control_api_token=self._control_api_token,
                market_ohlc_handler=self._handle_market_ohlc_request,
                platform_status_handler=self._handle_platform_status_request,
                control_status_handler=self._handle_control_status_request,
                routing_info_handler=self._handle_routing_info_request,
                performance_stats_handler=self._handle_performance_stats_request,
                system_logs_handler=self._handle_system_logs_request,
                forum_topics_handler=self._handle_forum_topics_request,
                forum_create_topic_handler=self._handle_forum_create_topic_request,

                forum_topic_detail_handler=self._handle_forum_topic_detail_request,
                forum_replies_handler=self._handle_forum_replies_request,
                forum_scout_status_handler=self._handle_forum_scout_status_request,
                forum_scout_register_handler=self._handle_forum_scout_register_request,
                forum_scout_publish_handler=self._handle_forum_scout_publish_request,
                security_skills_status_handler=self._handle_security_skills_status_request,
                security_skills_scan_handler=self._handle_security_skill_scan_request,
                prediction_dashboard_handler=self._handle_prediction_dashboard_request,
            )

        # 1. Start Telegram FIRST for immediate status
        logger.info("📡 Initializing Telegram Notification Task...")
        asyncio.create_task(
            self.telegram.send_as(SAPPHIRE, "Online and listening. All systems initializing.")
        )
        if self._telegram_webhook_mode:
            logger.info("📡 Configuring Telegram webhook mode...")
            configured = await self.telegram.configure_webhook(
                self._telegram_webhook_url, self._telegram_webhook_secret
            )
            if not configured:
                logger.error("❌ Telegram webhook setup failed; command input may be unavailable.")
        else:
            asyncio.create_task(self.telegram.start_listener())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        await self.media_manager.start()

        # 2. Start Pub/Sub Listener for Trade Results
        asyncio.create_task(self._listen_for_trades())

        # 3. Start Gemini Guard
        asyncio.create_task(self.ai.start())

        # 4. Start Feeds, Strategy, Dispatcher
        await dispatcher.start()
        await self.market_data.start()
        await self.strategy.start()
        self.telegram.record_activity(
            OBSIDIAN, "system",
            f"Startup complete — venues: {', '.join(sorted(dispatcher.bot_urls.keys()))}",
        )
        if self._full_autonomy_enabled:
            self._autonomy_task = asyncio.create_task(self._autonomy_ops_loop())
            # Delay startup bootstrap to let gateway warm up and avoid cold-start races
            async def _deferred_bootstrap():
                await asyncio.sleep(30)
                try:
                    await self._dispatch_full_autonomy_cycle(trigger="startup_bootstrap", force=True)
                except Exception as exc:
                    logger.warning(f"Startup bootstrap dispatch failed (non-fatal): {type(exc).__name__}: {exc}")
            asyncio.create_task(_deferred_bootstrap())
        else:
            logger.info("Full autonomy loop disabled (SAPPHIRE_FULL_AUTONOMY_ENABLED=false)")

        # 6. Start Internal Alpha Scanner (autonomous signal generation)
        if self.alpha_scanner.enabled:
            self._alpha_scanner_task = asyncio.create_task(
                self.alpha_scanner.run_loop(self._handle_alpha_scanner_signal)
            )
            logger.info("🔍 Internal alpha scanner task started")
            self.telegram.record_activity(
                EMERALD, "alpha",
                f"Alpha scanner active — symbols: {','.join(self.alpha_scanner._scan_symbols[:5])}",
            )
        else:
            logger.info("Internal alpha scanner disabled (SAPPHIRE_ALPHA_SCANNER_ENABLED=false)")

        # 7. Start Grid Trader (leveraged grid-style signal generation)
        if self.grid_trader.enabled:
            self._grid_trader_task = asyncio.create_task(
                self.grid_trader.run_loop(self._handle_grid_trader_signal)
            )
            logger.info("🧭 Grid trader task started")
            self.telegram.record_activity(
                EMERALD, "grid",
                f"Grid trader active — symbols: {','.join(self.grid_trader.metrics().get('symbols', [])[:5])}",
            )
        else:
            logger.info("Grid trader disabled (SAPPHIRE_GRID_TRADER_ENABLED=false)")

        # 7. Start Prediction Market Intelligence (Phase 8)
        if self.prediction_aggregator.enabled:
            await self.prediction_aggregator.start()
            self._prediction_forum_task = asyncio.create_task(
                self._prediction_market_forum_loop()
            )
            logger.info("🔮 Prediction market intelligence active")
            self.telegram.record_activity(
                SCOUT, "prediction_market",
                "Prediction market feeds started (Polymarket + Kalshi)",
            )
        else:
            logger.info("Prediction market feeds disabled (SAPPHIRE_PREDICTION_MARKET_ENABLED=false)")

        # Keep-alive loop
        while self.running:
            await asyncio.sleep(1)

    async def _listen_for_trades(self):
        """Listen for trade execution results from all bots."""
        from pubsub.client import subscribe

        logger.info("👂 Initializing Pub/Sub 'trade-executed' listener...")

        async def handle_trade(message_data: dict):
            try:
                # Log to AI for Recaps
                self.ai.log_trade(message_data)

                # Update portfolio tracker with fill
                closed_trade = self.portfolio.process_fill(message_data)
                if closed_trade:
                    logger.info(
                        f"📊 Portfolio: closed {closed_trade.symbol} "
                        f"PnL: {closed_trade.realized_pnl:+.4f}"
                    )
                    self.telegram.record_activity(
                        SAPPHIRE, "portfolio",
                        f"Closed {closed_trade.symbol} — PnL: {closed_trade.realized_pnl:+.4f}",
                    )

                # Resolve any pending fill confirmation
                dispatcher.resolve_fill(message_data)

                # Record trade in episodic memory
                if self._memory_enabled:
                    try:
                        self.memory.record_trade(message_data)
                        self.telegram.record_activity(
                            EMERALD, "memory",
                            f"Recorded trade: {message_data.get('side', '?')} {message_data.get('symbol', '?')}",
                        )
                    except Exception:
                        pass  # Memory is non-critical

                # Format notification
                platform = message_data.get("platform", "Unknown")
                symbol = message_data.get("symbol", "N/A")
                success = message_data.get("success", False)
                side = message_data.get("side", "N/A")
                qty = message_data.get("filled_quantity", 0)

                if success:
                    self._trade_metrics["total_trades"] += 1
                    pnl = self._extract_trade_pnl(message_data)
                    if pnl is not None:
                        self._trade_metrics["realized_pnl"] += pnl
                        if pnl > 0:
                            self._trade_metrics["wins"] += 1
                        elif pnl < 0:
                            self._trade_metrics["losses"] += 1
                    else:
                        self._trade_metrics["wins"] += 1

                    msg = f"✅ TRADE EXECUTED: {platform} | {side} {qty} {symbol}"
                    self._record_system_log(
                        msg,
                        level="info",
                        tags=["trade", "execution", platform.lower()],
                        metadata={"side": side, "symbol": symbol, "quantity": qty},
                    )
                    self.telegram.record_activity(
                        SAPPHIRE, "trade",
                        f"Filled {side} {qty} {symbol} on {platform}",
                    )
                    # Use LOW priority to batch execution updates
                    await self.telegram.send_message(msg, priority="low")
                    await self._record_trade_outcome(platform, success=True)
                else:
                    err = message_data.get("error_message", "Unknown")
                    self._trade_metrics["total_trades"] += 1
                    self._trade_metrics["losses"] += 1
                    await self._record_trade_outcome(platform, success=False, error_message=err)

                    # Classify the error
                    category, severity = classify_error(err)

                    # Auto-pause venue on configuration/region errors — no point retrying
                    if category == ErrorCategory.CONFIGURATION:
                        dispatcher.set_venue_allocation(platform, 0.0)
                        dispatcher.pause_venue(platform, reason=err)
                        self.telegram.record_activity(
                            OBSIDIAN, "system",
                            f"Auto-paused {platform}: {err[:80]}",
                        )
                        await self.telegram.send_as(
                            OBSIDIAN,
                            f"🛑 Auto-paused **{platform}** — `{err}`. This won't fix itself with retries. Use `/resume` when resolved.",
                        )
                        logger.warning(f"Auto-paused {platform} due to config error: {err}")
                        return  # Don't send duplicate trade-failed notification

                    # Check if we should notify
                    should_notify = notification_manager.should_notify(err, category, severity)

                    if should_notify:
                        msg = f"Trade failed on {platform}: `{side} {symbol}` — {err}"
                        self._record_system_log(
                            msg,
                            level="error",
                            tags=["trade", "failure", platform.lower()],
                            metadata={"side": side, "symbol": symbol},
                        )

                        # Severity can come from different enum classes across services.
                        # Compare by numeric value to avoid cross-class TypeError.
                        severity_value = getattr(severity, "value", severity)
                        error_threshold = getattr(ErrorSeverity.ERROR, "value", ErrorSeverity.ERROR)
                        try:
                            priority = (
                                "high"
                                if int(severity_value) >= int(error_threshold)
                                else "medium"
                            )
                        except (TypeError, ValueError):
                            priority = "medium"
                        await self.telegram.send_as(SAPPHIRE, msg)
                        logger.warning(msg)
                    else:
                        # Log but don't spam Telegram
                        logger.info(
                            f"⚠️ Expected/deduplicated failure: {platform} | {side} {symbol} | {err}"
                        )
            except Exception as e:
                logger.error(f"Error in trade result handler: {e}")

        await subscribe("trade-executed", handle_trade)

    async def _handle_market_ohlc_request(self, query: Dict[str, Any]) -> Dict[str, Any]:
        return await handle_market_ohlc(self, query)

    async def _handle_platform_status_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return await handle_platform_status(self, _)

    async def _handle_control_status_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return await handle_control_status(self, _)

    async def _handle_routing_info_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return await handle_routing_info(self, _)

    async def _handle_performance_stats_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return await handle_performance_stats(self, _)

    async def _handle_system_logs_request(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        return await handle_system_logs(self, payload)



    async def _handle_security_skills_status_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return await handle_security_skills_status(self, _)

    async def _handle_security_skill_scan_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await handle_security_skill_scan(self, payload)

    async def _handle_forum_topics_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await handle_forum_topics(self, payload)

    async def _handle_forum_topic_detail_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await handle_forum_topic_detail(self, payload)

    async def _handle_forum_create_topic_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await handle_forum_create_topic(self, payload)

    async def _handle_forum_replies_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await handle_forum_replies(self, payload)

    async def _handle_forum_scout_status_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return await handle_forum_scout_status(self, _)

    async def _handle_forum_scout_register_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await handle_forum_scout_register(self, payload)

    async def _handle_forum_scout_publish_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await handle_forum_scout_publish(self, payload)

    async def _handle_prediction_dashboard_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self.prediction_aggregator.get_prediction_dashboard_data()

    async def stop(self):
        logger.info("🛑 Stopping Alpha Engine...")
        self.running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._autonomy_task:
            self._autonomy_task.cancel()
        await self.media_manager.stop()
        await self.prediction_aggregator.stop()
        if self._prediction_forum_task:
            self._prediction_forum_task.cancel()
        await self.market_data.stop()
        await self.strategy.stop()
        await dispatcher.stop()
        await self.ai.stop()  # Stop AI loop


async def main():
    engine = AlphaEngine()

    def handle_sig(sig, frame):
        asyncio.create_task(engine.stop())

    signal.signal(signal.SIGTERM, handle_sig)
    signal.signal(signal.SIGINT, handle_sig)

    await engine.start()


if __name__ == "__main__":
    asyncio.run(main())
