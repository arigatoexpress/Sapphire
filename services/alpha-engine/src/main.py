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
from src.ai.gemini_guard import GeminiGuard
from src.collaboration.forum import SapphireForumService
from src.execution.dispatcher import dispatcher
from src.execution.portfolio import PortfolioTracker
from src.feeds.market_data import MarketDataAggregator
from src.integrations.tradingview_autonomy import TradingViewAutonomyPlugin
from src.security.virustotal_scanner import VirusTotalSkillScanner
from src.strategy.engine import AlphaStrategyEngine

# Add shared library to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared.error_classifier import ErrorCategory, ErrorSeverity, classify_error
from health import start_health_server
from smart_notifications import notification_manager
from telegram_bot import SAPPHIRE, OBSIDIAN, EMERALD

# Install uvloop as the default event loop policy
asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

# Configure high-performance logging
from loguru import logger

logger.remove()
logger.add(sys.stderr, level="INFO")


class AlphaEngine:
    def __init__(self):
        self.running = False
        self.market_data = MarketDataAggregator()
        self.strategy = AlphaStrategyEngine(self.market_data)
        self.portfolio = PortfolioTracker()
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
            bot_token=token, chat_id=chat_id, command_callback=self._handle_telegram_command
        )
        # Initialize Gemini Guard
        self.ai = GeminiGuard(telegram_bot=self.telegram)
        self.tv_autonomy = TradingViewAutonomyPlugin(
            market_data=self.market_data,
            default_chat_id=self._telegram_chat_id,
        )
        self._heartbeat_task = None
        self._autonomy_task = None
        self._kill_switch_active = False
        self._heartbeat_interval_seconds = int(os.getenv("TELEGRAM_HEARTBEAT_INTERVAL_SECONDS", "900"))
        self._deallocation_failure_threshold = int(os.getenv("DEALLOCATION_FAILURE_THRESHOLD", "3"))
        self._deallocation_cooldown_seconds = int(os.getenv("DEALLOCATION_COOLDOWN_SECONDS", "900"))
        self._default_venue_allocation = max(
            0.0, min(1.0, float(os.getenv("DEFAULT_VENUE_ALLOCATION", "1.0")))
        )
        self._telegram_webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL", "").strip()
        self._telegram_webhook_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
        self._control_api_token = os.getenv("SAPPHIRE_CONTROL_API_TOKEN", "").strip()
        self._telegram_webhook_mode = bool(self._telegram_webhook_url)
        self._tradingview_webhook_secret = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "").strip()
        self._tradingview_integration_enabled = self._env_flag(
            "SAPPHIRE_TRADINGVIEW_INTEGRATION_ENABLED",
            default=False,
        )
        self._tradingview_execution_enabled = (
            self._tradingview_integration_enabled
            and (
            os.getenv("TRADINGVIEW_EXECUTION_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "on"}
            )
        )
        self._tradingview_default_quantity = max(
            0.0, float(os.getenv("TRADINGVIEW_DEFAULT_QUANTITY", "0.0"))
        )
        self._tradingview_allowed_symbols = self._parse_symbol_set(
            os.getenv("TRADINGVIEW_ALLOWED_SYMBOLS", "")
        )
        self._tradingview_allowed_symbols_by_venue: Dict[str, Set[str]] = {
            "ASTER": self._parse_symbol_set(os.getenv("TRADINGVIEW_ALLOWED_SYMBOLS_ASTER", "")),
            "LIGHTER": self._parse_symbol_set(os.getenv("TRADINGVIEW_ALLOWED_SYMBOLS_LIGHTER", "")),
        }
        self._tradingview_max_quantity_default = max(
            0.0, float(os.getenv("TRADINGVIEW_MAX_QUANTITY", "0.0"))
        )
        self._tradingview_max_quantity_by_venue: Dict[str, float] = {
            "ASTER": max(0.0, float(os.getenv("TRADINGVIEW_MAX_QUANTITY_ASTER", "0.0"))),
            "LIGHTER": max(0.0, float(os.getenv("TRADINGVIEW_MAX_QUANTITY_LIGHTER", "0.0"))),
        }
        self._tradingview_idempotency_window_seconds = max(
            30, int(os.getenv("TRADINGVIEW_IDEMPOTENCY_WINDOW_SECONDS", "300"))
        )
        self._tradingview_idempotency_max_keys = max(
            100, int(os.getenv("TRADINGVIEW_IDEMPOTENCY_MAX_KEYS", "2000"))
        )
        self._tradingview_enforce_strategy_rules = (
            os.getenv("TRADINGVIEW_ENFORCE_STRATEGY_RULES", "false").strip().lower()
            in {"1", "true", "yes", "on"}
        )
        self._tradingview_strategy_rules = self._parse_strategy_rules(
            os.getenv("TRADINGVIEW_STRATEGY_RULES_JSON", "")
        )
        self._trading_gate_max_failure_pressure = max(
            0, int(os.getenv("TRADING_GATE_MAX_FAILURE_PRESSURE", "2"))
        )
        self._trading_gate_min_active_venues = max(
            0, int(os.getenv("TRADING_GATE_MIN_ACTIVE_VENUES", "1"))
        )
        self._tradingview_signal_seen_at: Dict[str, float] = {}
        self._failure_counts: Dict[str, int] = defaultdict(int)
        self._auto_deallocated: Set[str] = set()
        self._manual_review_venues: Set[str] = set()
        self._hard_failure_cooldown_seconds = max(
            self._deallocation_cooldown_seconds,
            int(os.getenv("SAPPHIRE_HARD_FAILURE_COOLDOWN_SECONDS", "21600")),
        )
        self._owner_directive = str(os.getenv("SAPPHIRE_OWNER_DIRECTIVE", "")).strip()
        self._owner_directive_updated_at = int(time.time()) if self._owner_directive else 0
        self._full_autonomy_enabled = self._env_flag("SAPPHIRE_FULL_AUTONOMY_ENABLED", default=True)
        self._autonomy_allow_code_changes = self._env_flag(
            "SAPPHIRE_AUTONOMY_ALLOW_CODE_CHANGES", default=True
        )
        self._autonomy_allow_gcloud_changes = self._env_flag(
            "SAPPHIRE_AUTONOMY_ALLOW_GCLOUD_CHANGES", default=True
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
        self._started_at = time.time()
        self._system_log_max_entries = max(100, int(os.getenv("SYSTEM_LOG_MAX_ENTRIES", "500")))
        self._system_logs: Deque[Dict[str, Any]] = deque(maxlen=self._system_log_max_entries)
        self.forum = SapphireForumService()
        self.vt_scanner = VirusTotalSkillScanner()
        requested_media_mode = self._normalize_media_mode(
            os.getenv("SAPPHIRE_MEDIA_MODE", "owner_approval")
        )
        self._media_mode = requested_media_mode or "owner_approval"
        self._media_twitter_enabled = self._env_flag("SAPPHIRE_MEDIA_TWITTER_ENABLED", default=True)
        self._media_substack_enabled = self._env_flag("SAPPHIRE_MEDIA_SUBSTACK_ENABLED", default=True)
        self._media_twitter_handle = str(os.getenv("SAPPHIRE_TWITTER_HANDLE", "")).strip()
        self._media_substack_publication = str(
            os.getenv("SAPPHIRE_SUBSTACK_PUBLICATION_URL", "")
        ).strip()
        self._media_twitter_post_url = str(os.getenv("SAPPHIRE_MEDIA_TWITTER_POST_URL", "")).strip()
        self._media_substack_post_url = str(os.getenv("SAPPHIRE_MEDIA_SUBSTACK_POST_URL", "")).strip()
        self._media_twitter_api_token = str(os.getenv("SAPPHIRE_TWITTER_API_TOKEN", "")).strip()
        self._media_substack_api_token = str(os.getenv("SAPPHIRE_SUBSTACK_API_TOKEN", "")).strip()
        self._media_publish_max_attempts = max(1, int(os.getenv("SAPPHIRE_MEDIA_MAX_ATTEMPTS", "4")))
        self._media_retry_base_seconds = max(
            10, int(os.getenv("SAPPHIRE_MEDIA_RETRY_BASE_SECONDS", "120"))
        )
        self._media_publish_timeout_seconds = max(
            5, int(os.getenv("SAPPHIRE_MEDIA_POST_TIMEOUT_SECONDS", "20"))
        )
        self._media_publish_poll_seconds = max(5, int(os.getenv("SAPPHIRE_MEDIA_POLL_SECONDS", "20")))
        self._media_queue_max_items = max(20, int(os.getenv("SAPPHIRE_MEDIA_QUEUE_MAX_ITEMS", "200")))
        self._media_queue: Deque[Dict[str, Any]] = deque(maxlen=self._media_queue_max_items)
        self._media_pending_approvals: Dict[str, Dict[str, Any]] = {}
        self._media_recent_results: Deque[Dict[str, Any]] = deque(maxlen=50)
        self._media_last_draft_payload: Dict[str, Any] = {}
        self._media_last_draft: Dict[str, Any] = {"topic": "", "title": "", "timestamp": 0}
        self._media_last_publish: Dict[str, Any] = {
            "target": "",
            "status": "none",
            "detail": "",
            "timestamp": 0,
        }
        self._media_publish_sequence = 0
        self._media_publish_task: Optional[asyncio.Task[Any]] = None
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

    @staticmethod
    def _normalize_media_mode(raw: Any) -> str:
        value = str(raw or "").strip().lower().replace("-", "_")
        aliases = {
            "draft": "draft_only",
            "draft_only": "draft_only",
            "owner": "owner_approval",
            "owner_approval": "owner_approval",
            "approval": "owner_approval",
            "manual": "owner_approval",
            "auto": "auto_post",
            "auto_post": "auto_post",
            "autopost": "auto_post",
        }
        return aliases.get(value, "")

    @staticmethod
    def _normalize_media_targets(raw_targets: Any) -> List[str]:
        if isinstance(raw_targets, list):
            tokens = [str(item or "").strip().lower() for item in raw_targets]
        else:
            text = str(raw_targets or "").strip().lower()
            if not text:
                text = "both"
            for separator in (";", "|"):
                text = text.replace(separator, ",")
            tokens = [chunk.strip() for chunk in text.split(",") if chunk.strip()]
            if len(tokens) == 1 and " " in tokens[0]:
                tokens = [chunk.strip() for chunk in tokens[0].split(" ") if chunk.strip()]

        normalized: List[str] = []
        for token in tokens:
            if token in {"both", "all", "x+substack", "twitter+substack"}:
                normalized.extend(["twitter", "substack"])
                continue
            if token in {"x", "twitter", "tweet"}:
                normalized.append("twitter")
                continue
            if token in {"substack", "newsletter"}:
                normalized.append("substack")
                continue

        if not normalized:
            normalized = ["twitter", "substack"]

        deduped: List[str] = []
        for target in normalized:
            if target not in deduped:
                deduped.append(target)
        return deduped

    def _next_media_request_id(self) -> str:
        self._media_publish_sequence += 1
        return f"media:{int(time.time())}:{self._media_publish_sequence:04d}"

    def _media_channel_config(self, channel: str) -> Dict[str, Any]:
        target = str(channel or "").strip().lower()
        if target == "twitter":
            enabled = bool(self._media_twitter_enabled)
            token = str(self._media_twitter_api_token or "").strip()
            endpoint = str(self._media_twitter_post_url or "").strip()
            ready = bool(enabled and endpoint and token)
            return {
                "channel": "twitter",
                "enabled": enabled,
                "ready": ready,
                "endpoint": endpoint,
                "token": token,
                "handle": self._media_twitter_handle or "",
                "publication": "",
            }
        if target == "substack":
            enabled = bool(self._media_substack_enabled)
            token = str(self._media_substack_api_token or "").strip()
            endpoint = str(self._media_substack_post_url or "").strip()
            ready = bool(enabled and endpoint and token)
            return {
                "channel": "substack",
                "enabled": enabled,
                "ready": ready,
                "endpoint": endpoint,
                "token": token,
                "handle": "",
                "publication": self._media_substack_publication or "",
            }
        return {
            "channel": target or "unknown",
            "enabled": False,
            "ready": False,
            "endpoint": "",
            "token": "",
            "handle": "",
            "publication": "",
        }

    def _resolve_media_request_id(self, raw_request_id: str) -> str:
        candidate = str(raw_request_id or "").strip()
        if candidate and candidate.lower() != "latest":
            return candidate

        if self._media_pending_approvals:
            latest_pending = sorted(
                self._media_pending_approvals.values(),
                key=lambda item: int(item.get("created_at", 0)),
                reverse=True,
            )
            if latest_pending:
                return str(latest_pending[0].get("request_id", "")).strip()

        if self._media_queue:
            latest_queued = sorted(
                list(self._media_queue),
                key=lambda item: int(item.get("created_at", 0)),
                reverse=True,
            )
            if latest_queued:
                return str(latest_queued[0].get("request_id", "")).strip()

        return ""

    def _enqueue_media_publish_request(
        self,
        draft: Dict[str, Any],
        targets: List[str],
        source: str,
        require_approval: bool,
        note: str = "",
    ) -> Dict[str, Any]:
        now = int(time.time())
        request_id = self._next_media_request_id()
        item = {
            "request_id": request_id,
            "created_at": now,
            "updated_at": now,
            "source": str(source or "manual").strip() or "manual",
            "topic": str(draft.get("topic", "")).strip(),
            "title": str(draft.get("title", "")).strip(),
            "body": str(draft.get("body", "")).strip(),
            "targets": self._normalize_media_targets(targets),
            "status": "pending_approval" if require_approval else "queued",
            "attempts": 0,
            "max_attempts": int(self._media_publish_max_attempts),
            "next_attempt_at": now,
            "note": str(note or "").strip(),
        }

        if require_approval:
            self._media_pending_approvals[request_id] = item
        else:
            self._media_queue.append(item)

        self._record_system_log(
            f"Media publish request {request_id} created ({item['status']})",
            level="info",
            tags=["media", "queue"],
            metadata={
                "targets": item["targets"],
                "source": item["source"],
                "mode": self._media_mode,
            },
        )
        return item

    def _approve_media_publish_request(self, raw_request_id: str, note: str = "") -> Dict[str, Any]:
        request_id = self._resolve_media_request_id(raw_request_id)
        if not request_id:
            return {"ok": False, "error": "request_not_found", "request_id": ""}

        item = self._media_pending_approvals.pop(request_id, None)
        if not item:
            return {"ok": False, "error": "request_not_pending", "request_id": request_id}

        item["status"] = "queued"
        item["updated_at"] = int(time.time())
        if note:
            item["approval_note"] = str(note).strip()[:400]
        self._media_queue.append(item)
        self._record_system_log(
            f"Media publish request {request_id} approved",
            level="info",
            tags=["media", "approval"],
            metadata={"targets": item.get("targets", [])},
        )
        return {
            "ok": True,
            "request_id": request_id,
            "targets": list(item.get("targets", [])),
            "queue_depth": len(self._media_queue),
        }

    def _reject_media_publish_request(self, raw_request_id: str, reason: str = "") -> Dict[str, Any]:
        request_id = self._resolve_media_request_id(raw_request_id)
        if not request_id:
            return {"ok": False, "error": "request_not_found", "request_id": ""}

        item = self._media_pending_approvals.pop(request_id, None)
        if not item:
            return {"ok": False, "error": "request_not_pending", "request_id": request_id}

        reason_text = str(reason or "").strip()[:400]
        self._record_system_log(
            f"Media publish request {request_id} rejected",
            level="warning",
            tags=["media", "approval"],
            metadata={"reason": reason_text},
        )
        return {
            "ok": True,
            "request_id": request_id,
            "reason": reason_text,
            "targets": list(item.get("targets", [])),
        }

    @staticmethod
    def _compose_twitter_text(title: str, body: str, limit: int = 280) -> str:
        headline = str(title or "").strip() or "Sapphire update"
        summary = " ".join(str(body or "").split())
        if summary:
            text = f"{headline} | {summary}"
        else:
            text = headline
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 3)].rstrip() + "..."

    def _build_media_channel_payload(self, channel: str, item: Dict[str, Any]) -> Dict[str, Any]:
        base = {
            "request_id": str(item.get("request_id", "")).strip(),
            "topic": str(item.get("topic", "")).strip(),
            "title": str(item.get("title", "")).strip(),
            "body": str(item.get("body", "")).strip(),
            "source": str(item.get("source", "manual")).strip(),
            "attempt": int(item.get("attempts", 0)) + 1,
            "timestamp": int(time.time()),
        }
        if channel == "twitter":
            base.update(
                {
                    "text": self._compose_twitter_text(
                        str(item.get("title", "")).strip(),
                        str(item.get("body", "")).strip(),
                    ),
                    "handle": self._media_twitter_handle or "",
                }
            )
            return base
        if channel == "substack":
            base.update(
                {
                    "markdown": str(item.get("body", "")).strip(),
                    "publication": self._media_substack_publication or "",
                }
            )
            return base
        return base

    async def _publish_media_channel(self, channel: str, item: Dict[str, Any]) -> Dict[str, Any]:
        config = self._media_channel_config(channel)
        target = str(config.get("channel", channel)).strip() or str(channel or "unknown")
        if not config.get("enabled"):
            return {
                "channel": target,
                "ok": False,
                "retryable": False,
                "reason": "channel_disabled",
                "detail": "channel is disabled",
            }
        if not config.get("ready"):
            return {
                "channel": target,
                "ok": False,
                "retryable": False,
                "reason": "channel_not_ready",
                "detail": "endpoint/token not configured",
            }

        payload = self._build_media_channel_payload(target, item)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.get('token', '')}",
        }
        timeout = aiohttp.ClientTimeout(total=self._media_publish_timeout_seconds)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(str(config.get("endpoint", "")), json=payload, headers=headers) as resp:
                    body = (await resp.text())[:300]
                    if 200 <= resp.status < 300:
                        return {
                            "channel": target,
                            "ok": True,
                            "retryable": False,
                            "reason": "ok",
                            "detail": body,
                            "status_code": resp.status,
                        }
                    retryable = resp.status == 429 or resp.status >= 500
                    return {
                        "channel": target,
                        "ok": False,
                        "retryable": retryable,
                        "reason": "http_error",
                        "detail": f"status={resp.status} body={body}",
                        "status_code": resp.status,
                    }
        except (asyncio.TimeoutError, aiohttp.ClientError) as exc:
            return {
                "channel": target,
                "ok": False,
                "retryable": True,
                "reason": "network_error",
                "detail": str(exc)[:300],
            }

    async def _process_media_queue_item(self, item: Dict[str, Any]) -> None:
        now = int(time.time())
        item["attempts"] = int(item.get("attempts", 0)) + 1
        item["updated_at"] = now
        targets = self._normalize_media_targets(item.get("targets", []))
        results: List[Dict[str, Any]] = []
        retryable_failure = False
        non_retryable_failure = False

        for target in targets:
            result = await self._publish_media_channel(target, item)
            results.append(result)
            if not result.get("ok") and result.get("retryable"):
                retryable_failure = True
            if not result.get("ok") and not result.get("retryable"):
                non_retryable_failure = True

        success_targets = [r["channel"] for r in results if r.get("ok")]
        failed_results = [r for r in results if not r.get("ok")]
        failed_targets = [r.get("channel", "unknown") for r in failed_results]
        max_attempts = int(item.get("max_attempts", self._media_publish_max_attempts))

        if not failed_results:
            self._media_last_publish = {
                "target": ",".join(success_targets) or "none",
                "status": "success",
                "detail": f"request {item.get('request_id', 'n/a')} published",
                "timestamp": now,
            }
            self._media_recent_results.append(
                {
                    "request_id": item.get("request_id", ""),
                    "status": "success",
                    "targets": success_targets,
                    "timestamp": now,
                }
            )
            await self.telegram.send_message(
                (
                    "✅ Media publish completed.\n"
                    f"Request: `{item.get('request_id', 'n/a')}`\n"
                    f"Targets: `{', '.join(success_targets) if success_targets else 'none'}`\n"
                    "Benefit: Sapphire external narrative is synchronized with internal operations."
                ),
                priority="high",
            )
            return

        if retryable_failure and int(item.get("attempts", 0)) < max_attempts:
            delay_seconds = int(self._media_retry_base_seconds * int(item.get("attempts", 0)))
            item["status"] = "queued"
            item["next_attempt_at"] = now + delay_seconds
            self._media_queue.append(item)
            await self.telegram.send_message(
                (
                    "⚠️ Media publish encountered retryable failure.\n"
                    f"Request: `{item.get('request_id', 'n/a')}`\n"
                    f"Failed targets: `{', '.join(failed_targets)}`\n"
                    f"Retry: `{item.get('attempts', 0)}/{max_attempts}` in `{delay_seconds}s`"
                ),
                priority="high",
            )
            return

        failure_reason = "; ".join(
            [f"{r.get('channel', 'unknown')}:{r.get('reason', 'error')}" for r in failed_results]
        )[:300]
        status = "partial_failed" if success_targets else "failed"
        self._media_last_publish = {
            "target": ",".join(targets) or "none",
            "status": status,
            "detail": failure_reason,
            "timestamp": now,
        }
        self._media_recent_results.append(
            {
                "request_id": item.get("request_id", ""),
                "status": status,
                "targets": targets,
                "failed_targets": failed_targets,
                "timestamp": now,
            }
        )
        await self.telegram.send_message(
            (
                "❌ Media publish failed.\n"
                f"Request: `{item.get('request_id', 'n/a')}`\n"
                f"Successful targets: `{', '.join(success_targets) if success_targets else 'none'}`\n"
                f"Failed targets: `{', '.join(failed_targets) if failed_targets else 'none'}`\n"
                f"Reason: `{failure_reason}`\n"
                + (
                    "Benefit retained: published channels remain delivered."
                    if non_retryable_failure and success_targets
                    else "Action: adjust channel credentials/endpoints and re-run `/media publish`."
                )
            ),
            priority="high",
        )

    async def _process_media_queue_once(self) -> None:
        if not self._media_queue:
            return

        now = int(time.time())
        queue_len = len(self._media_queue)
        for _ in range(queue_len):
            item = self._media_queue.popleft()
            if int(item.get("next_attempt_at", 0)) > now:
                self._media_queue.append(item)
                continue
            await self._process_media_queue_item(item)

    async def _media_publish_loop(self) -> None:
        while self.running:
            try:
                await asyncio.sleep(self._media_publish_poll_seconds)
                await self._process_media_queue_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Media publish loop error: {exc}")

    def _set_execution_stage(self, stage: str, source: str = "manual") -> Dict[str, Any]:
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

    def _set_tradingview_default_quantity(self, requested_quantity: float) -> Dict[str, Any]:
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
                self.tv_autonomy.enabled,
                "TRADINGVIEW_AUTONOMY_ENABLED is not true",
            ),
            (
                "TradingView full asset access enabled",
                self.tv_autonomy.allow_all_assets,
                "TRADINGVIEW_ALLOW_ALL_ASSETS is not true",
            ),
            (
                "TradingView community script access enabled",
                self.tv_autonomy.community_access_enabled,
                "TRADINGVIEW_COMMUNITY_ACCESS_ENABLED is not true",
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
                f"TV autonomy enabled: `{self.tv_autonomy.enabled}`",
                (
                    "TV signal mode: `LIVE`"
                    if self._tradingview_execution_enabled
                    else "TV signal mode: `WORKBENCH_DRY_RUN`"
                ),
                f"TV hook configured: `{bool(self.tv_autonomy.hook_url and self.tv_autonomy.hook_token)}`",
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

    async def _activate_kill_switch(self, reason: str) -> None:
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

        await self.telegram.send_message(
            f"🛑 **KILL SWITCH ACTIVE**\nReason: `{reason}`\nAll venues are halted and deallocated.",
            priority="high",
        )

    async def _resume_from_kill_switch(self, reason: str) -> None:
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

        await self.telegram.send_message("\n".join(lines), priority="medium")

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

    def _control_snapshot(self) -> Dict[str, Any]:
        state = dispatcher.get_control_state()
        strategy_state = self.strategy.execution_state()
        media_snapshot = self._media_status_snapshot()
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
            "timestamp": int(time.time()),
        }

    def _media_queue_snapshot(self) -> Dict[str, Any]:
        pending_items = sorted(
            self._media_pending_approvals.values(),
            key=lambda item: int(item.get("created_at", 0)),
            reverse=True,
        )
        queued_items = sorted(
            list(self._media_queue),
            key=lambda item: int(item.get("created_at", 0)),
            reverse=True,
        )
        recent_items = sorted(
            list(self._media_recent_results),
            key=lambda item: int(item.get("timestamp", 0)),
            reverse=True,
        )

        def _summarize_request(item: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "request_id": str(item.get("request_id", "")).strip(),
                "status": str(item.get("status", "")).strip(),
                "targets": list(item.get("targets", [])),
                "topic": str(item.get("topic", "")).strip(),
                "created_at": int(item.get("created_at", 0)),
                "updated_at": int(item.get("updated_at", 0)),
                "attempts": int(item.get("attempts", 0)),
                "max_attempts": int(item.get("max_attempts", self._media_publish_max_attempts)),
                "next_attempt_at": int(item.get("next_attempt_at", 0)),
            }

        return {
            "pending_count": len(pending_items),
            "queued_count": len(queued_items),
            "pending_items": [_summarize_request(item) for item in pending_items[:10]],
            "queued_items": [_summarize_request(item) for item in queued_items[:10]],
            "recent_results": list(recent_items[:10]),
        }

    def _media_status_snapshot(self) -> Dict[str, Any]:
        twitter_config = self._media_channel_config("twitter")
        substack_config = self._media_channel_config("substack")
        queue_snapshot = self._media_queue_snapshot()
        return {
            "mode": self._media_mode,
            "twitter_enabled": bool(self._media_twitter_enabled),
            "twitter_ready": bool(twitter_config.get("ready")),
            "twitter_handle": self._media_twitter_handle or "",
            "twitter_endpoint_configured": bool(twitter_config.get("endpoint")),
            "substack_enabled": bool(self._media_substack_enabled),
            "substack_ready": bool(substack_config.get("ready")),
            "substack_publication": self._media_substack_publication or "",
            "substack_endpoint_configured": bool(substack_config.get("endpoint")),
            "last_draft": dict(self._media_last_draft),
            "last_publish": dict(self._media_last_publish),
            "queue": queue_snapshot,
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

    async def _send_media_status(self) -> None:
        snapshot = self._media_status_snapshot()
        last_draft = snapshot.get("last_draft", {}) if isinstance(snapshot, dict) else {}
        last_publish = snapshot.get("last_publish", {}) if isinstance(snapshot, dict) else {}
        queue = snapshot.get("queue", {}) if isinstance(snapshot, dict) else {}
        pending_items = queue.get("pending_items", []) if isinstance(queue, dict) else []
        queued_items = queue.get("queued_items", []) if isinstance(queue, dict) else []
        recent_results = queue.get("recent_results", []) if isinstance(queue, dict) else []
        mode = str(snapshot.get("mode", "owner_approval"))
        policy_explainer = {
            "draft_only": "generates drafts only; no outbound publishing.",
            "owner_approval": "prepares drafts and waits for owner confirmation before publishing.",
            "auto_post": "publishes automatically when channel credentials are ready.",
        }
        mode_note = policy_explainer.get(mode, "uses configured media policy.")

        lines = [
            "📰 **SAPPHIRE MEDIA STATUS**",
            f"Mode: `{mode}` ({mode_note})",
            (
                f"X/Twitter: `{'READY' if snapshot.get('twitter_ready') else 'NOT_READY'}`"
                f" | enabled `{'YES' if snapshot.get('twitter_enabled') else 'NO'}`"
                f" | handle `{snapshot.get('twitter_handle') or 'n/a'}`"
            ),
            (
                f"Substack: `{'READY' if snapshot.get('substack_ready') else 'NOT_READY'}`"
                f" | enabled `{'YES' if snapshot.get('substack_enabled') else 'NO'}`"
                f" | publication `{snapshot.get('substack_publication') or 'n/a'}`"
            ),
            (
                f"Last draft: `{last_draft.get('title') or 'none'}`"
                f" at `{self._fmt_unix_ts(last_draft.get('timestamp'))}`"
            ),
            (
                f"Last publish: `{last_publish.get('status') or 'none'}`"
                f" target `{last_publish.get('target') or 'n/a'}`"
                f" at `{self._fmt_unix_ts(last_publish.get('timestamp'))}`"
            ),
            (
                f"Queue: pending approvals `{queue.get('pending_count', 0)}`"
                f" | queued publishes `{queue.get('queued_count', 0)}`"
            ),
            "",
            (
                "Commands: `/media mode <draft_only|owner_approval|auto_post>`, `/media draft <topic>`, "
                "`/media publish [topic:<name>] [targets:<x|substack|both>]`, `/media queue`, "
                "`/media approve <request_id|latest>`, `/media reject <request_id|latest>`"
            ),
        ]
        if pending_items:
            latest = pending_items[0]
            lines.append(
                "Latest pending: "
                f"`{latest.get('request_id', 'n/a')}` -> `{', '.join(latest.get('targets', [])) or 'none'}`"
            )
        if queued_items:
            latest = queued_items[0]
            lines.append(
                "Latest queued: "
                f"`{latest.get('request_id', 'n/a')}` retry `{latest.get('attempts', 0)}/{latest.get('max_attempts', 0)}` "
                f"next `{self._fmt_unix_ts(latest.get('next_attempt_at'))}`"
            )
        if recent_results:
            latest = recent_results[0]
            lines.append(
                "Latest outcome: "
                f"`{latest.get('request_id', 'n/a')}` status `{latest.get('status', 'unknown')}`"
            )
        await self.telegram.send_message("\n".join(lines), priority="medium")

    def _set_media_mode(self, requested_mode: str, source: str = "manual") -> Dict[str, Any]:
        normalized = self._normalize_media_mode(requested_mode)
        if not normalized:
            return {
                "ok": False,
                "error": "invalid_mode",
                "allowed_modes": ["draft_only", "owner_approval", "auto_post"],
            }

        previous = self._media_mode
        self._media_mode = normalized
        self._record_system_log(
            f"Media mode set to {normalized}",
            level="warning",
            tags=["media", "control"],
            metadata={"source": source, "previous_mode": previous, "new_mode": normalized},
        )
        return {"ok": True, "previous_mode": previous, "new_mode": normalized}

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
        self._media_last_draft = {"topic": normalized_topic, "title": title, "timestamp": timestamp}
        self._media_last_draft_payload = {
            "topic": normalized_topic,
            "title": title,
            "body": body,
            "timestamp": timestamp,
            "mode": self._media_mode,
        }
        self._record_system_log(
            f"Media draft generated for topic '{normalized_topic}'",
            level="info",
            tags=["media", "draft"],
            metadata={"mode": self._media_mode, "topic": normalized_topic},
        )
        return {
            "topic": normalized_topic,
            "title": title,
            "body": body,
            "timestamp": timestamp,
            "mode": self._media_mode,
        }

    def _resolve_media_draft_for_publish(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        requested_topic = str(payload.get("topic", "")).strip()
        if requested_topic:
            return self._build_media_draft(requested_topic)

        if self._media_last_draft_payload and self._media_last_draft_payload.get("body"):
            return dict(self._media_last_draft_payload)

        fallback_topic = str(self._media_last_draft.get("topic", "")).strip() or "weekly operations update"
        return self._build_media_draft(fallback_topic)

    async def _send_focus_snapshot(self) -> None:
        state = dispatcher.get_control_state()
        strategy_state = self.strategy.execution_state()
        media_snapshot = self._media_status_snapshot()
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
                f"TradingView autonomy: `{'ON' if self.tv_autonomy.enabled else 'OFF'}`"
                if self._tradingview_integration_enabled
                else "TradingView autonomy: `OFF (integration disabled)`"
            ),
            (
                f"Community scripts: `{'ON' if self.tv_autonomy.community_access_enabled else 'OFF'}`"
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
        media_snapshot = self._media_status_snapshot()

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
                f"- Media mode: `{self._media_mode}`"
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
            "allowed_repo_scope": sorted(list(getattr(self.tv_autonomy, "allowed_repo_scope", set()))),
            "allowed_project_scope": sorted(list(getattr(self.tv_autonomy, "allowed_project_scope", set()))),
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
        active_count = len(context.get("active_venues", []))
        total_failures = int(context.get("total_failure_pressure", 0))

        if self._kill_switch_active:
            return "kill_switch_active"
        if active_count < self._trading_gate_min_active_venues:
            return "venue_shortfall"
        if total_failures > self._trading_gate_max_failure_pressure:
            return "failure_pressure"
        return "scheduled_cycle"

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

        hook_result = await self.tv_autonomy.dispatch_session_decision(
            session_key=resolved_key,
            decision=normalized_decision,
            note=trimmed_note,
        )
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

    async def _dispatch_full_autonomy_cycle(self, trigger: str, force: bool = False) -> Dict[str, Any]:
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
        instruction = (
            f"{directive} Execute an autonomous maintenance and improvement cycle for code + cloud. "
            "Prioritize production safety first, then reliability, then performance. "
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
                    f"Trigger: `{trigger}`\n"
                    f"Active venues: `{', '.join(context['active_venues']) if context['active_venues'] else 'none'}`\n"
                    f"Failure pressure: `{context['total_failure_pressure']}`\n"
                    f"Why now: {brief['reasoning']}\n"
                    f"Expected outcome: {brief['expected_outcome']}\n"
                    f"Benefit vs current state: {brief['expected_benefit']}"
                ),
                priority="medium",
            )
            return {"dispatched": False, "reason": "dry_run", "trigger": trigger}

        hook_result = await self.tv_autonomy.dispatch_environment_instruction(
            instruction=instruction,
            trigger=trigger,
            context=context,
            allow_code_changes=self._autonomy_allow_code_changes,
            allow_gcloud_changes=self._autonomy_allow_gcloud_changes,
        )

        if hook_result.get("dispatched"):
            self._autonomy_last_dispatch_at = now
            self._autonomy_last_trigger = trigger
            self._autonomy_dispatch_count += 1
            session_key = str(hook_result.get("session_key", "")).strip()
            self._record_autonomy_session(session_key, trigger, instruction)
            self._record_system_log(
                f"Full autonomy cycle dispatched ({trigger})",
                level="info",
                tags=["autonomy", "dispatch"],
                metadata={"session_key": hook_result.get("session_key", "")},
            )
            if session_key and not self._autonomy_require_owner_approval:
                auto_result = await self._apply_autonomy_session_decision(
                    session_key=session_key,
                    decision="APPROVE",
                    note="Auto-approved by Sapphire autonomy policy.",
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
                        OBSIDIAN,
                        f"Autonomy cycle auto-approved (`{trigger}`).\n{decision_brief}",
                    )
                else:
                    await self.telegram.send_as(
                        OBSIDIAN,
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
                    OBSIDIAN,
                    f"Autonomy cycle needs your approval (`{trigger}`).\n{decision_brief}",
                    expects_reply=True,
                    pending_action="APPROVE_SESSION",
                    pending_metadata={"session_key": session_key},
                )
        else:
            self._record_system_log(
                f"Full autonomy dispatch unavailable ({trigger}): {hook_result.get('reason', 'unknown')}",
                level="warning",
                tags=["autonomy", "dispatch"],
            )
            await self.telegram.send_as(
                OBSIDIAN,
                f"Autonomy dispatch unavailable — `{trigger}`: {hook_result.get('reason', 'unknown')}",
            )
        return hook_result

    async def _autonomy_ops_loop(self) -> None:
        while self.running:
            try:
                await asyncio.sleep(self._autonomy_loop_seconds)
                context = self._autonomy_context_snapshot()
                trigger = self._autonomy_trigger_reason(context)
                await self._dispatch_full_autonomy_cycle(trigger=trigger, force=False)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Autonomy loop error: {exc}")

    async def _handle_control_command(self, target: str, action: str, value: float) -> None:
        normalized_action = action.upper()

        if normalized_action in {"MEDIA_STATUS", "MEDIA_QUEUE_STATUS", "MEDIA_QUEUE", "COMMUNICATION_STATUS"}:
            await self._send_media_status()
            return

        if normalized_action in {"MEDIA_SET_MODE", "SET_MEDIA_MODE"}:
            payload = self._parse_json_payload(target)
            requested_mode = str(payload.get("mode", "")).strip() or str(target or "").strip()
            result = self._set_media_mode(requested_mode, source="telegram")
            if not result.get("ok"):
                await self.telegram.send_message(
                    (
                        "❌ Invalid media mode.\n"
                        "Use one of: `draft_only`, `owner_approval`, `auto_post`."
                    ),
                    priority="high",
                )
                return

            snapshot = self._media_status_snapshot()
            await self.telegram.send_message(
                (
                    f"✅ Media mode updated to `{result.get('new_mode', self._media_mode)}`.\n"
                    f"Previous mode: `{result.get('previous_mode', 'unknown')}`\n"
                    f"X ready: `{'YES' if snapshot.get('twitter_ready') else 'NO'}` | "
                    f"Substack ready: `{'YES' if snapshot.get('substack_ready') else 'NO'}`\n"
                    "Expected outcome: publication workflow now follows the updated automation policy."
                ),
                priority="high",
            )
            return

        if normalized_action in {"MEDIA_DRAFT", "PREPARE_MEDIA_DRAFT"}:
            payload = self._parse_json_payload(target)
            topic = str(payload.get("topic", "")).strip() or str(target or "").strip()
            draft = self._build_media_draft(topic)
            snapshot = self._media_status_snapshot()
            publish_note = {
                "draft_only": "Draft created only; no publish attempts will run.",
                "owner_approval": "Draft created; await owner approval before publishing.",
                "auto_post": (
                    "Draft created; auto-post is enabled when channel credentials are ready."
                ),
            }.get(draft.get("mode", "owner_approval"), "Draft created.")
            await self.telegram.send_message(
                (
                    "📰 Sapphire media draft generated.\n"
                    f"Title: `{draft.get('title', 'n/a')}`\n"
                    f"Mode: `{draft.get('mode', 'owner_approval')}`\n"
                    f"X ready: `{'YES' if snapshot.get('twitter_ready') else 'NO'}` | "
                    f"Substack ready: `{'YES' if snapshot.get('substack_ready') else 'NO'}`\n"
                    f"Policy: {publish_note}\n"
                    "Use `/media status` to review channel readiness."
                ),
                priority="high",
            )
            return

        if normalized_action in {"MEDIA_PUBLISH", "MEDIA_DISPATCH"}:
            payload = self._parse_json_payload(target)
            draft = self._resolve_media_draft_for_publish(payload)
            targets = self._normalize_media_targets(payload.get("targets", []))
            note = str(payload.get("note", "")).strip()
            mode = self._media_mode

            if mode == "draft_only":
                await self.telegram.send_message(
                    (
                        "📰 Media publish request captured, but mode is `draft_only`.\n"
                        f"Draft retained: `{draft.get('title', 'n/a')}`\n"
                        "Expected outcome: no outbound post until mode changes to owner approval or auto-post."
                    ),
                    priority="high",
                )
                return

            require_approval = mode == "owner_approval"
            request = self._enqueue_media_publish_request(
                draft=draft,
                targets=targets,
                source="telegram",
                require_approval=require_approval,
                note=note,
            )
            request_id = str(request.get("request_id", "n/a")).strip() or "n/a"
            targets_text = ", ".join(request.get("targets", [])) or "none"

            if require_approval:
                await self.telegram.send_message(
                    (
                        "📰 Media publish request is pending owner approval.\n"
                        f"Request: `{request_id}`\n"
                        f"Targets: `{targets_text}`\n"
                        "Expected outcome: publish starts after `/media approve <request_id|latest>`.\n"
                        "Benefit: keeps outbound messaging aligned with operator intent."
                    ),
                    priority="high",
                )
                return

            await self.telegram.send_message(
                (
                    "📰 Media publish request queued for immediate delivery.\n"
                    f"Request: `{request_id}`\n"
                    f"Targets: `{targets_text}`\n"
                    "Expected outcome: queue worker will post to ready channels now."
                ),
                priority="high",
            )
            await self._process_media_queue_once()
            return

        if normalized_action in {"MEDIA_APPROVE", "MEDIA_REQUEST_APPROVE"}:
            payload = self._parse_json_payload(target)
            request_id = str(payload.get("request_id", "")).strip() or str(target or "").strip()
            note = str(payload.get("note", "")).strip()
            result = self._approve_media_publish_request(request_id, note=note)
            if not result.get("ok"):
                await self.telegram.send_message(
                    (
                        "❌ Media approval failed.\n"
                        f"Request: `{result.get('request_id', request_id or 'n/a')}`\n"
                        f"Reason: `{result.get('error', 'unknown')}`"
                    ),
                    priority="high",
                )
                return

            await self.telegram.send_message(
                (
                    "✅ Media request approved and queued.\n"
                    f"Request: `{result.get('request_id', 'n/a')}`\n"
                    f"Targets: `{', '.join(result.get('targets', [])) or 'none'}`\n"
                    f"Queue depth: `{result.get('queue_depth', 0)}`"
                ),
                priority="high",
            )
            await self._process_media_queue_once()
            return

        if normalized_action in {"MEDIA_REJECT", "MEDIA_REQUEST_REJECT"}:
            payload = self._parse_json_payload(target)
            request_id = str(payload.get("request_id", "")).strip() or str(target or "").strip()
            reason = str(payload.get("reason", "")).strip() or str(payload.get("note", "")).strip()
            result = self._reject_media_publish_request(request_id, reason=reason)
            if not result.get("ok"):
                await self.telegram.send_message(
                    (
                        "❌ Media rejection failed.\n"
                        f"Request: `{result.get('request_id', request_id or 'n/a')}`\n"
                        f"Reason: `{result.get('error', 'unknown')}`"
                    ),
                    priority="high",
                )
                return

            await self.telegram.send_message(
                (
                    "🛑 Media request rejected.\n"
                    f"Request: `{result.get('request_id', 'n/a')}`\n"
                    f"Targets: `{', '.join(result.get('targets', [])) or 'none'}`\n"
                    f"Reason: `{result.get('reason', 'none') or 'none'}`"
                ),
                priority="high",
            )
            return

        if normalized_action in {"SECURITY_STATUS", "VT_STATUS", "SKILL_SECURITY_STATUS"}:
            status = await self._handle_security_skills_status_request({})
            last_scan = status.get("last_scan", {}) if isinstance(status, dict) else {}
            last_scan_type = str(last_scan.get("type", "none")).strip() or "none"
            last_scan_time = int(last_scan.get("timestamp", 0) or 0)
            last_scan_verdict = str(last_scan.get("verdict", "n/a")).strip() or "n/a"
            await self.telegram.send_message(
                (
                    "🛡️ **VIRUSTOTAL SKILL SECURITY**\n"
                    f"Enabled: `{'YES' if status.get('enabled') else 'NO'}`\n"
                    f"API key configured: `{'YES' if status.get('api_key_configured') else 'NO'}`\n"
                    f"Policy mode: `{status.get('enforcement_mode', 'warn')}`\n"
                    f"Skills dir: `{status.get('skills_dir', '')}`\n"
                    f"Upload-on-miss: `{'YES' if status.get('upload_if_missing_default') else 'NO'}`\n"
                    f"Last scan: `{last_scan_type}` at `{last_scan_time}` verdict `{last_scan_verdict}`"
                ),
                priority="medium",
            )
            return

        if normalized_action in {"SECURITY_SCAN", "VT_SCAN", "SKILL_SECURITY_SCAN"}:
            payload = self._parse_json_payload(target)
            requested_skill = str(payload.get("skill", "")).strip()
            if not requested_skill:
                requested_skill = str(target or "").strip()
            if requested_skill.startswith("{"):
                requested_skill = ""
            upload_if_missing = payload.get("upload_if_missing", self.vt_scanner.upload_if_missing_default)
            upload_bool = str(upload_if_missing).strip().lower() in {"1", "true", "yes", "on"}

            scan_scope = requested_skill if requested_skill and requested_skill.lower() != "all" else "all"
            await self.telegram.send_message(
                f"🛡️ VirusTotal scan requested for `{scan_scope}` (upload-on-miss: `{'YES' if upload_bool else 'NO'}`).",
                priority="high",
            )
            result = await self._handle_security_skill_scan_request(
                {
                    "skill": requested_skill,
                    "upload_if_missing": upload_bool,
                }
            )

            if not result.get("ok"):
                await self.telegram.send_message(
                    (
                        "❌ VirusTotal scan failed.\n"
                        f"Reason: `{result.get('error', 'unknown')}`"
                    ),
                    priority="high",
                )
                return

            if isinstance(result.get("results"), list):
                counts = result.get("counts", {})
                await self.telegram.send_message(
                    (
                        "✅ VirusTotal batch scan completed.\n"
                        f"Skills scanned: `{result.get('skills_scanned', 0)}`\n"
                        f"Benign: `{counts.get('benign', 0)}` | "
                        f"Suspicious: `{counts.get('suspicious', 0)}` | "
                        f"Malicious: `{counts.get('malicious', 0)}` | "
                        f"Unknown: `{counts.get('unknown', 0)}`\n"
                        f"Policy blocked: `{result.get('blocked_count', 0)}`"
                    ),
                    priority="high",
                )
            else:
                security = result.get("security", {})
                policy = security.get("policy", {}) if isinstance(security, dict) else {}
                await self.telegram.send_message(
                    (
                        f"✅ VirusTotal scan completed for `{result.get('skill', 'unknown')}`.\n"
                        f"Verdict: `{security.get('verdict', 'unknown')}` | "
                        f"Code Insight: `{security.get('code_insight_verdict', 'unknown')}`\n"
                        f"Policy: `{policy.get('mode', 'warn')}` | "
                        f"Allowed: `{'YES' if policy.get('allowed') else 'NO'}`\n"
                        f"Report: {result.get('vt', {}).get('report_url', 'n/a')}"
                    ),
                    priority="high",
                )
            return

        if normalized_action in {"SCOUT_STATUS", "FORUM_SCOUT_STATUS"}:
            status = self.forum.scout_status()
            profile = status.get("profile", {}) if isinstance(status, dict) else {}
            registration = status.get("registration", {}) if isinstance(status, dict) else {}
            bridge = status.get("external_bridge", {}) if isinstance(status, dict) else {}
            await self.telegram.send_message(
                (
                    "🛰️ **SCOUT STATUS**\n"
                    f"Agent: `{profile.get('agent_id', 'SAPPHIRE_SCOUT')}`\n"
                    f"Sensitive access: `{profile.get('sensitive_data_access', 'none')}`\n"
                    f"Registered: `{'YES' if registration.get('registered') else 'NO'}`"
                    + (
                        f" (@{registration.get('username')})"
                        if registration.get("username")
                        else ""
                    )
                    + "\n"
                    f"Dispatch mode: `{bridge.get('dispatch_mode', 'none')}`\n"
                    f"External register URL: `{'YES' if bridge.get('register_url_configured') else 'NO'}`\n"
                    f"External post URL: `{'YES' if bridge.get('post_url_configured') else 'NO'}`\n"
                    f"Fallback hook ready: `{'YES' if bridge.get('fallback_hook_token_configured') and bridge.get('fallback_hook_url_configured') and bridge.get('fallback_chat_id_configured') else 'NO'}`"
                ),
                priority="medium",
            )
            return

        if normalized_action in {"SCOUT_REGISTER", "FORUM_SCOUT_REGISTER"}:
            payload = self._parse_json_payload(target)
            username = str(payload.get("username", "")).strip()
            if not username:
                fallback_username = str(target or "").strip().split(" ", 1)[0]
                username = fallback_username.strip()
            if not username:
                await self.telegram.send_message(
                    "❌ Scout register requires a username. Use `/scout register <username> [display_name]`.",
                    priority="high",
                )
                return

            display_name = str(payload.get("display_name", "")).strip()
            if not display_name:
                chunks = str(target or "").strip().split(" ", 1)
                display_name = chunks[1].strip() if len(chunks) > 1 else "Sapphire Scout"
            bio = str(payload.get("bio", "")).strip() or (
                "Least-privilege scout for public collaboration. No secrets, no trading actions."
            )
            result = await self._handle_forum_scout_register_request(
                {
                    "username": username,
                    "display_name": display_name,
                    "bio": bio,
                }
            )
            if not result.get("ok"):
                await self.telegram.send_message(
                    (
                        "❌ Scout registration failed.\n"
                        f"Reason: `{result.get('error', 'unknown')}`"
                    ),
                    priority="high",
                )
            return

        if normalized_action in {"SCOUT_PUBLISH", "FORUM_SCOUT_PUBLISH"}:
            payload = self._parse_json_payload(target)
            body = str(payload.get("body", "")).strip()
            if not body:
                body = str(target or "").strip()
            if not body:
                await self.telegram.send_message(
                    "❌ Scout publish requires message body text. Use `/scout publish <note>`.",
                    priority="high",
                )
                return

            result = await self._handle_forum_scout_publish_request(
                {
                    "topic_id": str(payload.get("topic_id", "")).strip(),
                    "post_id": str(payload.get("post_id", "")).strip(),
                    "title": str(payload.get("title", "")).strip(),
                    "body": body,
                    "author": str(payload.get("author", "")).strip() or "SAPPHIRE_SCOUT",
                    "kind": str(payload.get("kind", "")).strip() or "note",
                    "lane": str(payload.get("lane", "")).strip() or "external",
                    "state": str(payload.get("state", "")).strip() or "open",
                    "priority": str(payload.get("priority", "")).strip() or "medium",
                    "tags": payload.get("tags", ["scout", "external"]),
                }
            )
            if not result.get("ok"):
                await self.telegram.send_message(
                    (
                        "❌ Scout publish failed.\n"
                        f"Reason: `{result.get('error', 'unknown')}`"
                    ),
                    priority="high",
                )
                return

            dispatch = result.get("dispatch", {}) if isinstance(result, dict) else {}
            metadata = dispatch.get("metadata", {}) if isinstance(dispatch, dict) else {}
            metadata = metadata if isinstance(metadata, dict) else {}
            reason = str(dispatch.get("reason", "unknown")).strip() or "unknown"
            dispatch_action = str(result.get("dispatch_action", "publish")).strip() or "publish"
            outcome = "external post accepted."
            if reason == "ok_verified":
                outcome = "accepted and verification challenge solved automatically; content should be publicly visible."
            elif reason == "ok_pending_verification" or metadata.get("verification_required"):
                outcome = "accepted by Moltbook, pending verification before full feed visibility."
            elif reason == "moltbook_rate_limited":
                retry_after_minutes = int(metadata.get("retry_after_minutes", 0) or 0)
                retry_after_seconds = int(metadata.get("retry_after_seconds", 0) or 0)
                if retry_after_minutes > 0:
                    outcome = f"provider cooldown active; retry in about {retry_after_minutes} minutes."
                elif retry_after_seconds > 0:
                    outcome = f"provider cooldown active; retry in about {retry_after_seconds} seconds."
                else:
                    outcome = "provider cooldown active; retry after the next rate-limit window."
            elif reason == "moltbook_pending_claim":
                outcome = "account is pending claim; owner claim completion is required before publishing."
            elif reason == "moltbook_already_registered":
                outcome = "provider already has this scout account registered."
            elif not dispatch.get("dispatched"):
                outcome = "external publish blocked; note remains stored locally for retry."
            await self.telegram.send_message(
                (
                    f"🛰️ Scout {dispatch_action} processed for topic `{result.get('topic_id', 'n/a')}`.\n"
                    f"Dispatch mode: `{dispatch.get('mode', 'none')}` | "
                    f"Dispatch: `{'YES' if dispatch.get('dispatched') else 'NO'}`\n"
                    f"Reason: `{reason}`\n"
                    f"Outcome: {outcome}\n"
                    "Benefit: external collaboration remains sanitized and auditable."
                ),
                priority="high",
            )
            return

        if normalized_action in {"SET_EXECUTION_STAGE", "SET_DEX_EXECUTION_STAGE", "PROMOTION_STAGE"}:
            requested = self._parse_execution_stage_token(target)
            if not requested:
                await self.telegram.send_message(
                    "❌ Invalid stage. Use one of: `paper`, `staged_live`, `full_live`.",
                    priority="high",
                )
                return

            applied = self._set_execution_stage(requested, source="telegram")
            await self.telegram.send_message(
                (
                    f"✅ DEX execution stage set to `{applied.get('dex_execution_stage', requested)}`.\n"
                    f"Live dispatch: `{'ON' if applied.get('stage_multiplier', 0) > 0 else 'OFF'}` | "
                    f"Effective qty: `{applied.get('effective_quantity', 0.0)}`"
                ),
                priority="high",
            )
            return

        if normalized_action in {"SET_TRADING_EXECUTION", "SET_EXECUTION"}:
            if not self._tradingview_integration_enabled:
                self._tradingview_execution_enabled = False
                await self.telegram.send_message(
                    (
                        "ℹ️ TradingView integration is disabled by policy (`SAPPHIRE_TRADINGVIEW_INTEGRATION_ENABLED=false`).\n"
                        "No TradingView signal mode changes were applied.\n"
                        "Core runtime focus remains ASTER/LIGHTER execution + autonomy operations."
                    ),
                    priority="medium",
                )
                return

            mode = str(target or "").strip().upper()
            if mode not in {"ON", "OFF", "TRUE", "FALSE", "1", "0"}:
                await self.telegram.send_message(
                    "❌ Invalid TradingView signal mode. Use `/trade on [qty]` or `/trade off`.",
                    priority="high",
                )
                return

            enable_execution = mode in {"ON", "TRUE", "1"}
            quantity_value = max(0.0, float(value or 0.0))
            quantity_result: Dict[str, Any] | None = None

            self._tradingview_execution_enabled = enable_execution
            if enable_execution:
                if quantity_value > 0:
                    quantity_result = self._set_tradingview_default_quantity(quantity_value)
                elif self._tradingview_default_quantity <= 0:
                    quantity_result = self._set_tradingview_default_quantity(
                        self._recommended_default_trade_quantity()
                    )
            self._record_system_log(
                (
                    f"TradingView signal mode set to {'LIVE' if enable_execution else 'WORKBENCH_DRY-RUN'}"
                    + (
                        f" (qty={self._tradingview_default_quantity})"
                        if enable_execution
                        else ""
                    )
                ),
                level="warning",
                tags=["control", "execution_mode"],
                metadata={
                    "execution_enabled": enable_execution,
                    "default_quantity": self._tradingview_default_quantity,
                },
            )

            if enable_execution:
                qty_note = f"Default qty `{self._tradingview_default_quantity}`."
                if quantity_result and quantity_result.get("capped"):
                    qty_note = (
                        f"Default qty capped to `{quantity_result.get('applied')}` "
                        f"(cap `{quantity_result.get('cap')}`)."
                    )
                await self.telegram.send_message(
                    f"✅ TradingView signal mode: `LIVE`. {qty_note}",
                    priority="high",
                )
            else:
                await self.telegram.send_message(
                    "🧪 TradingView signal mode: `WORKBENCH_DRY-RUN` (signals captured for research/backtests only).",
                    priority="high",
                )
            return

        if normalized_action in {"SET_TRADINGVIEW_DEFAULT_QUANTITY", "SET_DEFAULT_QUANTITY"}:
            if not self._tradingview_integration_enabled:
                await self.telegram.send_message(
                    (
                        "ℹ️ TradingView integration is disabled, so default TradingView quantity is not active.\n"
                        "To re-enable later, set `SAPPHIRE_TRADINGVIEW_INTEGRATION_ENABLED=true` and redeploy alpha."
                    ),
                    priority="medium",
                )
                return

            result = self._set_tradingview_default_quantity(float(value or 0.0))
            if not result.get("ok"):
                await self.telegram.send_message(
                    "❌ Default quantity must be greater than zero.",
                    priority="high",
                )
                return

            self._record_system_log(
                "TradingView default quantity updated",
                level="warning",
                tags=["control", "execution_mode"],
                metadata={
                    "requested_quantity": result.get("requested"),
                    "applied_quantity": result.get("applied"),
                    "capped": bool(result.get("capped")),
                    "cap": result.get("cap"),
                },
            )
            if result.get("capped"):
                await self.telegram.send_message(
                    (
                        f"⚠️ Default quantity capped to `{result.get('applied')}` "
                        f"(requested `{result.get('requested')}`, cap `{result.get('cap')}`)."
                    ),
                    priority="high",
                )
            else:
                live_note = "LIVE" if self._tradingview_execution_enabled else "DRY-RUN"
                await self.telegram.send_message(
                    f"✅ Default TradingView quantity set to `{result.get('applied')}` (mode `{live_note}`).",
                    priority="high",
                )
            return

        if normalized_action == "APPROVE_ALL_SESSIONS":
            decision_payload = self._parse_session_decision_payload(target)
            note = str(decision_payload.get("note", "")).strip()
            if len(note) > 400:
                note = note[:400]

            pending_keys = self._pending_autonomy_session_keys()
            if not pending_keys:
                await self.telegram.send_message(
                    "ℹ️ No pending autonomy sessions to approve.",
                    priority="high",
                )
                return

            success_count = 0
            failed: List[str] = []
            for session_key in pending_keys:
                result = await self._apply_autonomy_session_decision(
                    session_key=session_key,
                    decision="APPROVE",
                    note=note,
                    source="owner_bulk",
                )
                if result.get("dispatched"):
                    success_count += 1
                else:
                    failed.append(
                        f"{result.get('session_key', session_key)}:{result.get('reason', 'unknown')}"
                    )

            if failed:
                await self.telegram.send_message(
                    (
                        f"⚠️ Bulk approval completed with partial failures.\n"
                        f"Approved: `{success_count}` / `{len(pending_keys)}`\n"
                        f"Failed: `{'; '.join(failed[:5])}`\n"
                        "Expected outcome: successful sessions continue without owner delay.\n"
                        "Next step: re-run `/approve_all` after resolving listed failures."
                    ),
                    priority="high",
                )
            else:
                await self.telegram.send_message(
                    (
                        f"✅ Bulk approval completed. Approved `{success_count}` pending session(s).\n"
                        "Expected outcome: queued autonomy changes move immediately into execution."
                    ),
                    priority="high",
                )
            return

        if normalized_action in {"APPROVE_SESSION", "REJECT_SESSION"}:
            decision_payload = self._parse_session_decision_payload(target)
            session_key = self._resolve_autonomy_session_key(decision_payload.get("session_key", ""))
            note = str(decision_payload.get("note", "")).strip()
            decision = "APPROVE" if normalized_action == "APPROVE_SESSION" else "REJECT"

            if not session_key:
                await self.telegram.send_message(
                    "⚠️ No pending autonomy session found. Trigger one with `/autonomy` first.",
                    priority="high",
                )
                return

            result = await self._apply_autonomy_session_decision(
                session_key=session_key,
                decision=decision,
                note=note,
                source="owner_manual",
            )
            if result.get("dispatched"):
                await self.telegram.send_message(
                    (
                        f"✅ Session `{session_key}` marked `{decision}`.\n"
                        f"Dispatch: `{result.get('dispatch_session_key', 'n/a')}`\n"
                        "Expected outcome: session state is synchronized and downstream action is unblocked."
                    ),
                    priority="high",
                )
            else:
                await self.telegram.send_message(
                    (
                        f"⚠️ Session decision captured locally but dispatch failed for `{session_key}`.\n"
                        f"Reason: `{result.get('reason', 'unknown')}`\n"
                        "Benefit: decision is preserved locally for controlled retry."
                    ),
                    priority="high",
                )
            return

        normalized_target = self._normalize_platform(target or "ALL")

        if normalized_action in {"KILL", "HALT", "HALT_TRADING"}:
            await self._activate_kill_switch("Manual command from Telegram")
            return

        if normalized_action in {"RESUME", "RESUME_TRADING"}:
            await self._resume_from_kill_switch("Manual command from Telegram")
            return

        if normalized_action in {"HEARTBEAT", "PING"}:
            await self._send_heartbeat("manual")
            return

        if normalized_action in {"STATUS", "CONTROL_STATUS"}:
            await self._send_control_status()
            return

        if normalized_action in {"MARKET_PRICES", "PRICES"}:
            await self._send_market_prices()
            return

        if normalized_action in {"PORTFOLIO", "POSITIONS"}:
            await self._send_portfolio_status()
            return

        if normalized_action in {"FOCUS", "CONTROL_FOCUS"}:
            await self._send_focus_snapshot()
            return

        if normalized_action in {"PROMOTION_GATE", "STRATEGY_GATE", "PROMOTION", "GATE"}:
            requested_stage = self._parse_execution_stage_token(target)
            if requested_stage:
                applied = self._set_execution_stage(requested_stage, source="promotion_gate")
                await self.telegram.send_message(
                    (
                        f"🚀 Promotion stage updated to `{applied.get('dex_execution_stage', requested_stage)}`.\n"
                        f"Live dispatch: `{'ON' if applied.get('stage_multiplier', 0) > 0 else 'OFF'}` | "
                        f"Effective qty: `{applied.get('effective_quantity', 0.0)}`"
                    ),
                    priority="high",
                )
                await self._send_promotion_gate_report(
                    f"promotion:{applied.get('dex_execution_stage', requested_stage)}"
                )
            else:
                await self._send_promotion_gate_report("manual")
            return

        if normalized_action in {"AUTONOMY", "AUTONOMY_CYCLE"}:
            await self._dispatch_full_autonomy_cycle(trigger="manual_telegram", force=True)
            return

        if normalized_action == "OWNER_CHAT":
            message = str(target or "").strip()
            if not message:
                return

            # Build concise system context for the AI
            strategy_state = self.strategy.execution_state()
            ctrl = self._control_snapshot()
            context_lines = [
                f"Execution stage: {strategy_state.get('dex_execution_stage', 'paper')}",
                f"Stage multiplier: {strategy_state.get('stage_multiplier', 0)}",
                f"Kill switch: {'ACTIVE' if ctrl.get('kill_switch_active') else 'inactive'}",
                f"Preferred symbols: {', '.join(strategy_state.get('preferred_symbols', [])[:5])}",
            ]
            for venue, info in ctrl.get("venues", {}).items():
                status = "PAUSED" if info.get("paused") else "LIVE"
                context_lines.append(
                    f"Venue {venue}: {status}, allocation {info.get('allocation', 1.0)*100:.0f}%"
                )

            # Add portfolio context
            port_snap = self.portfolio.snapshot()
            if port_snap["open_count"] > 0 or port_snap["total_trades"] > 0:
                context_lines.append(
                    f"Portfolio: {port_snap['open_count']} open positions, "
                    f"{port_snap['total_trades']} total fills"
                )
                context_lines.append(
                    f"Realized PnL: {port_snap['total_realized_pnl']:+.4f}, "
                    f"Unrealized PnL: {port_snap['total_unrealized_pnl']:+.4f}"
                )
                if port_snap["wins"] + port_snap["losses"] > 0:
                    context_lines.append(
                        f"Win rate: {port_snap['win_rate']}% "
                        f"({port_snap['wins']}W / {port_snap['losses']}L)"
                    )

            system_context = "\n".join(context_lines)

            # Pick the right agent to respond
            agent = self.telegram._route_agent(message)

            # Ask Gemini for a conversational response
            reply = await self.ai.chat_with_owner(message, system_context=system_context)
            if reply:
                await self.telegram.send_as(agent, reply)
            else:
                # Gemini unavailable — fall back to steering
                self._owner_directive = message[:500]
                self._owner_directive_updated_at = int(time.time())
                await self.telegram.send_as(
                    agent, "Noted — I'll factor that into our next cycle."
                )

            # Also save as steering directive if it looks like an instruction
            lowered = message.lower()
            if any(kw in lowered for kw in (
                "focus", "prioritize", "try", "make sure", "please", "want",
                "should", "need", "let's", "stop", "start", "switch",
            )):
                self._owner_directive = message[:500]
                self._owner_directive_updated_at = int(time.time())
            return

        if normalized_action in {"OWNER_STEER", "STEER"}:
            directive = str(target or "").strip()
            if not directive:
                await self.telegram.send_message(
                    "❌ Owner steering directive is empty. Use `/steer <directive>` or `/answer <response>`.",
                    priority="high",
                )
                return

            if len(directive) > 500:
                directive = directive[:500]
            self._owner_directive = directive
            self._owner_directive_updated_at = int(time.time())

            agent = EMERALD if any(w in directive.lower() for w in ("strategy", "optimize", "improve", "review")) else SAPPHIRE
            await self.telegram.send_as(agent, f"Got it — steering updated: *{directive[:100]}*")

            hook_result = await self.tv_autonomy.dispatch_owner_instruction(directive)
            if hook_result.get("dispatched"):
                await self.telegram.send_message(
                    f"Dispatched to OpenClaw agents (`{hook_result.get('session_key', 'n/a')}`).",
                    priority="medium",
                )
            else:
                await self.telegram.send_as(
                    OBSIDIAN,
                    f"OpenClaw dispatch unavailable ({hook_result.get('reason', 'unknown')}). Directive saved for next cycle.",
                )
            return

        if normalized_action == "SET_ALLOCATION":
            allocation = max(0.0, min(1.0, float(value)))
            targets = (
                list(dispatcher.bot_urls.keys())
                if normalized_target == "ALL"
                else [self._normalize_platform(normalized_target)]
            )

            unknown = [venue for venue in targets if venue not in dispatcher.bot_urls]
            if unknown:
                await self.telegram.send_message(
                    f"❌ Unknown venue(s): `{', '.join(unknown)}`", priority="high"
                )
                return

            for venue in targets:
                dispatcher.set_venue_allocation(venue, allocation)
                if allocation <= 0:
                    dispatcher.pause_venue(
                        venue,
                        reason="Manual deallocation via Telegram",
                        cooldown_seconds=max(self._deallocation_cooldown_seconds, 3600),
                    )
                else:
                    dispatcher.resume_venue(venue)
                    self._failure_counts[venue] = 0
                    self._auto_deallocated.discard(venue)
                    self._manual_review_venues.discard(venue)

            if allocation <= 0:
                self._record_system_log(
                    f"Manual deallocation applied to {', '.join(targets)}",
                    level="warning",
                    tags=["control", "allocation"],
                    metadata={"allocation": allocation},
                )
                await self._publish_risk_alert(
                    action="halt_trading",
                    severity="warning",
                    alert_type="manual_deallocation",
                    message=f"Manual deallocation: {', '.join(targets)} set to 0%",
                    platforms=targets,
                    metadata={"source": "telegram", "allocation": allocation},
                )
                await self.telegram.send_message(
                    f"🧯 Deallocated `{', '.join(targets)}` to `0%` and halted trading on those venues.",
                    priority="high",
                )
            else:
                self._record_system_log(
                    f"Manual allocation set for {', '.join(targets)} to {allocation*100:.0f}%",
                    level="info",
                    tags=["control", "allocation"],
                    metadata={"allocation": allocation},
                )
                await self._publish_risk_alert(
                    action="resume_trading",
                    severity="warning",
                    alert_type="manual_allocation",
                    message=f"Manual allocation update: {', '.join(targets)} set to {allocation*100:.0f}%",
                    platforms=targets,
                    metadata={"source": "telegram", "allocation": allocation},
                )
                await self.telegram.send_message(
                    f"✅ Allocation for `{', '.join(targets)}` set to `{allocation*100:.0f}%`.",
                    priority="high",
                )
            return

        await self.telegram.send_message(
            f"❌ Unknown control action `{normalized_action}`", priority="high"
        )

    async def _handle_tradingview_signal(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process TradingView alerts into heartbeat/control/trade actions."""
        merged_payload: Dict[str, Any] = dict(payload or {})
        message_payload = self._parse_tradingview_message(merged_payload.get("message", ""))
        if isinstance(message_payload, dict):
            merged_payload.update({k: v for k, v in message_payload.items() if k not in merged_payload})

        action_raw = self._extract_text_value(
            merged_payload,
            ["action", "side", "command", "signal", "event", "type"],
        ).lower()
        venue_raw = self._extract_text_value(
            merged_payload,
            ["venue", "platform", "exchange", "target", "bot"],
            default="ALL",
        )
        symbol = self._extract_text_value(
            merged_payload,
            ["symbol", "ticker", "pair", "instrument"],
            default="USDC",
        ).upper()
        quantity = self._extract_float_value(
            merged_payload,
            ["quantity", "qty", "size", "contracts", "notional"],
            default=self._tradingview_default_quantity,
        )
        strategy_label = self._extract_text_value(
            merged_payload,
            ["strategy", "strategy_name", "alert_name", "name"],
        ).strip().lower()
        strategy_rule = (
            self._tradingview_strategy_rules.get(strategy_label) if strategy_label else None
        )
        allocation_percent = self._extract_float_value(
            merged_payload,
            ["allocation", "allocation_percent", "percent"],
            default=100.0,
        )

        normalized_action = action_raw.replace("-", "_")
        normalized_target = self._normalize_platform(venue_raw or "ALL")

        if not self._tradingview_integration_enabled:
            return {
                "accepted": "disabled",
                "reason": "tradingview_integration_disabled",
                "action": normalized_action or "unknown",
                "target": normalized_target,
            }

        if self.tv_autonomy.is_workspace_action(normalized_action):
            workspace_result = await self.tv_autonomy.handle_action(normalized_action, merged_payload)
            result_type = workspace_result.get("accepted", "unknown")
            if result_type in {
                "workspace_updated",
                "workspace_noop",
                "scan_requested",
                "backtest_requested",
                "custom_requested",
            }:
                dispatch = workspace_result.get("dispatch", {})
                dispatch_status = "yes" if dispatch.get("dispatched") else f"no ({dispatch.get('reason', 'n/a')})"
                await self.telegram.send_message(
                    (
                        f"🧩 Workspace `{normalized_action}` -> `{result_type}`"
                        f" (dispatch `{dispatch_status}`)"
                    ),
                    priority="medium",
                )
            elif result_type == "blocked":
                await self.telegram.send_message(
                    f"⚠️ TradingView workspace action blocked: `{workspace_result.get('reason', 'unknown')}`.",
                    priority="high",
                )
            return workspace_result

        if normalized_action in {"heartbeat", "ping"}:
            await self._send_heartbeat("tradingview")
            return {"accepted": "heartbeat"}

        if normalized_action in {"status", "control_status"}:
            await self._send_control_status()
            return {"accepted": "status"}

        if normalized_action in {"kill", "halt", "halt_trading"}:
            await self._handle_control_command(normalized_target, "HALT_TRADING", 0.0)
            return {"accepted": "kill"}

        if normalized_action in {"resume", "resume_trading"}:
            await self._handle_control_command(normalized_target, "RESUME_TRADING", 0.0)
            return {"accepted": "resume"}

        if normalized_action in {"deallocate", "pause"}:
            await self._handle_control_command(normalized_target, "SET_ALLOCATION", 0.0)
            return {"accepted": "deallocate", "target": normalized_target}

        if normalized_action in {"allocate", "set_allocation"}:
            bounded = max(0.0, min(1.0, allocation_percent / 100.0))
            await self._handle_control_command(normalized_target, "SET_ALLOCATION", bounded)
            return {"accepted": "allocate", "target": normalized_target, "allocation": bounded}

        if normalized_action not in {"buy", "sell", "close"}:
            await self.telegram.send_message(
                f"⚠️ TradingView alert ignored: unsupported action `{action_raw or 'missing'}`.",
                priority="medium",
            )
            return {"accepted": "ignored", "reason": "unsupported_action"}

        if normalized_target == "ALL":
            targets = list(dispatcher.bot_urls.keys())
        else:
            targets = [normalized_target]

        unknown = [venue for venue in targets if venue not in dispatcher.bot_urls]
        if unknown:
            await self.telegram.send_message(
                f"❌ TradingView target not enabled: `{', '.join(unknown)}`", priority="high"
            )
            return {"accepted": "rejected", "reason": "unknown_target"}

        if self._tradingview_enforce_strategy_rules:
            if not strategy_label:
                await self.telegram.send_message(
                    "⚠️ TradingView alert blocked: strategy label is required.",
                    priority="high",
                )
                return {"accepted": "blocked", "reason": "missing_strategy"}
            if strategy_rule is None:
                await self.telegram.send_message(
                    f"⚠️ TradingView alert blocked: unknown strategy `{strategy_label}`.",
                    priority="high",
                )
                return {"accepted": "blocked", "reason": "unknown_strategy", "strategy": strategy_label}

        if strategy_rule is not None:
            strategy_venues = strategy_rule.get("venues", set())
            if strategy_venues:
                disallowed_strategy_targets = [venue for venue in targets if venue not in strategy_venues]
                if disallowed_strategy_targets:
                    await self.telegram.send_message(
                        (
                            f"⚠️ TradingView alert blocked: strategy `{strategy_label}` cannot target "
                            f"`{', '.join(disallowed_strategy_targets)}`."
                        ),
                        priority="high",
                    )
                    return {
                        "accepted": "blocked",
                        "reason": "strategy_venue_mismatch",
                        "targets": disallowed_strategy_targets,
                        "strategy": strategy_label,
                    }

            strategy_symbols = strategy_rule.get("symbols", set())
            if strategy_symbols and symbol not in strategy_symbols:
                await self.telegram.send_message(
                    (
                        f"⚠️ TradingView alert blocked: `{symbol}` not allowed for strategy "
                        f"`{strategy_label}`."
                    ),
                    priority="high",
                )
                return {
                    "accepted": "blocked",
                    "reason": "strategy_symbol_mismatch",
                    "strategy": strategy_label,
                }

        disallowed_targets = [venue for venue in targets if not self._symbol_allowed_for_venue(venue, symbol)]
        if disallowed_targets:
            await self.telegram.send_message(
                f"⚠️ TradingView alert blocked: `{symbol}` not allowed for `{', '.join(disallowed_targets)}`.",
                priority="high",
            )
            return {"accepted": "blocked", "reason": "symbol_not_allowed", "targets": disallowed_targets}

        if self._kill_switch_active:
            await self.telegram.send_message(
                "🛑 TradingView alert blocked because kill switch is active.",
                priority="high",
            )
            return {"accepted": "blocked", "reason": "kill_switch"}

        if quantity <= 0:
            await self.telegram.send_message(
                "⚠️ TradingView alert ignored: quantity missing or invalid.",
                priority="medium",
            )
            return {"accepted": "ignored", "reason": "invalid_quantity"}

        signal_key = self._build_signal_key(
            merged_payload,
            normalized_action.upper(),
            targets,
            symbol,
            quantity,
        )
        if self._is_duplicate_signal(signal_key):
            await self.telegram.send_message(
                f"♻️ TradingView duplicate ignored: `{signal_key}` within {self._tradingview_idempotency_window_seconds}s window.",
                priority="medium",
            )
            return {"accepted": "ignored", "reason": "duplicate_signal", "signal_key": signal_key}

        per_target_quantity: Dict[str, float] = {}
        capped_targets: List[str] = []
        notional_adjusted_targets: List[str] = []
        notional_blocked_targets: Dict[str, Dict[str, Any]] = {}
        for venue in targets:
            venue_cap = self._max_quantity_for_venue(venue)
            strategy_cap = strategy_rule.get("max_quantity") if strategy_rule else None
            if strategy_cap is not None:
                venue_cap = strategy_cap if venue_cap is None else min(venue_cap, strategy_cap)
            venue_qty = quantity
            if venue_cap is not None and venue_qty > venue_cap:
                venue_qty = venue_cap
                capped_targets.append(venue)
            quantity_guard = self._apply_min_notional_guard(venue, symbol, venue_qty)
            if quantity_guard.get("blocked"):
                notional_blocked_targets[venue] = quantity_guard
                continue
            if quantity_guard.get("adjusted"):
                notional_adjusted_targets.append(venue)
            per_target_quantity[venue] = float(quantity_guard.get("quantity", venue_qty))

        executable_targets = [venue for venue in targets if venue not in notional_blocked_targets]
        if not executable_targets:
            blocked_fragments = [
                f"{venue}:{details.get('reason', 'guard_blocked')}"
                for venue, details in sorted(notional_blocked_targets.items())
            ]
            await self.telegram.send_message(
                (
                    "⚠️ TradingView alert blocked by min-notional guard on all targets.\n"
                    f"Targets: `{'; '.join(blocked_fragments)}`"
                ),
                priority="high",
            )
            return {
                "accepted": "blocked",
                "reason": "min_notional_guard",
                "targets": targets,
                "blocked_targets": sorted(list(notional_blocked_targets.keys())),
                "signal_key": signal_key,
                "strategy": strategy_label or None,
            }

        if not self._tradingview_execution_enabled:
            qty_parts = [f"{venue}:{per_target_quantity[venue]}" for venue in sorted(executable_targets)]
            cap_note = (
                f" Caps applied on `{', '.join(sorted(set(capped_targets)))}`."
                if capped_targets
                else ""
            )
            adjust_note = (
                f" Min-notional adjustment applied on `{', '.join(sorted(set(notional_adjusted_targets)))}`."
                if notional_adjusted_targets
                else ""
            )
            blocked_note = (
                f" Guard-blocked targets `{', '.join(sorted(notional_blocked_targets.keys()))}`."
                if notional_blocked_targets
                else ""
            )
            await self.telegram.send_message(
                (
                    f"📥 TradingView signal captured (workbench dry-run): `{normalized_action.upper()} {symbol}` "
                    f"with quantities `{', '.join(qty_parts)}`. Set `TRADINGVIEW_EXECUTION_ENABLED=true` to execute."
                    f"{cap_note}"
                    f"{adjust_note}"
                    f"{blocked_note}"
                ),
                priority="medium",
            )
            return {
                "accepted": "dry_run",
                "targets": executable_targets,
                "signal_key": signal_key,
                "quantities": per_target_quantity,
                "capped_targets": sorted(set(capped_targets)),
                "adjusted_targets": sorted(set(notional_adjusted_targets)),
                "blocked_targets": sorted(list(notional_blocked_targets.keys())),
                "strategy": strategy_label or None,
            }

        dispatch_results: Dict[str, bool] = {}
        for venue in executable_targets:
            dispatch_results[venue] = await dispatcher.send_command(
                venue,
                {
                    "action": normalized_action.upper(),
                    "symbol": symbol,
                    "quantity": per_target_quantity[venue],
                    "source": "tradingview_webhook",
                    "signal_key": signal_key,
                },
            )

        failed_targets = [venue for venue, ok in dispatch_results.items() if not ok]
        if failed_targets:
            failed_details: List[str] = []
            for venue in failed_targets:
                dispatch_error = dispatcher.get_last_dispatch_error(venue)
                failed_details.append(
                    f"{venue}:{dispatch_error.get('reason', 'unknown')}:{dispatch_error.get('status', 'n/a')}"
                )
            if notional_blocked_targets:
                failed_details.extend(
                    [
                        f"{venue}:{details.get('reason', 'guard_blocked')}:guard"
                        for venue, details in sorted(notional_blocked_targets.items())
                    ]
                )
            await self.telegram.send_message(
                (
                    f"❌ TradingView dispatch failed (`{signal_key}`).\n"
                    f"Details: `{'; '.join(failed_details[:6])}`"
                ),
                priority="high",
            )
            return {
                "accepted": "partial_failure",
                "targets": executable_targets,
                "failed_targets": failed_targets,
                "signal_key": signal_key,
                "quantities": per_target_quantity,
                "capped_targets": sorted(set(capped_targets)),
                "adjusted_targets": sorted(set(notional_adjusted_targets)),
                "blocked_targets": sorted(list(notional_blocked_targets.keys())),
                "strategy": strategy_label or None,
            }

        qty_parts = [f"{venue}:{per_target_quantity[venue]}" for venue in sorted(executable_targets)]
        blocked_note = (
            f" Blocked targets: `{', '.join(sorted(notional_blocked_targets.keys()))}`."
            if notional_blocked_targets
            else ""
        )
        await self.telegram.send_message(
            (
                f"✅ TradingView executed: `{normalized_action.upper()} {symbol}` with "
                f"`{', '.join(qty_parts)}` (`{signal_key}`).{blocked_note}"
            ),
            priority="high",
        )
        return {
            "accepted": "executed",
            "targets": executable_targets,
            "signal_key": signal_key,
            "quantities": per_target_quantity,
            "capped_targets": sorted(set(capped_targets)),
            "adjusted_targets": sorted(set(notional_adjusted_targets)),
            "blocked_targets": sorted(list(notional_blocked_targets.keys())),
            "strategy": strategy_label or None,
        }

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

    async def _handle_telegram_command(
        self, platform: str, symbol: str, action: str, quantity: float
    ):
        """Callback for Telegram @mentions to trigger manual overrides."""
        logger.warning(f"🚨 TELEGRAM OVERRIDE: {platform} {action} {quantity} {symbol}")
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

    async def start(self):
        logger.info("🚀 Sapphire Alpha Engine Starting (uvloop enabled)")
        self.running = True
        self._record_system_log(
            "Sapphire Alpha Engine starting",
            level="info",
            tags=["system", "startup"],
        )

        # Start Health Server (Cloud Run)
        if self._telegram_webhook_mode:
            await start_health_server(
                telegram_update_handler=self.telegram._process_update,
                telegram_webhook_secret=self._telegram_webhook_secret,
                control_api_token=self._control_api_token,
                tradingview_update_handler=self._handle_tradingview_signal,
                tradingview_webhook_secret=self._tradingview_webhook_secret,
                market_ohlc_handler=self._handle_market_ohlc_request,
                platform_status_handler=self._handle_platform_status_request,
                control_status_handler=self._handle_control_status_request,
                routing_info_handler=self._handle_routing_info_request,
                performance_stats_handler=self._handle_performance_stats_request,
                system_logs_handler=self._handle_system_logs_request,
                tradingview_workspace_handler=self._handle_tradingview_workspace_request,
                forum_topics_handler=self._handle_forum_topics_request,
                forum_create_topic_handler=self._handle_forum_create_topic_request,
                forum_topic_detail_handler=self._handle_forum_topic_detail_request,
                forum_replies_handler=self._handle_forum_replies_request,
                forum_scout_status_handler=self._handle_forum_scout_status_request,
                forum_scout_register_handler=self._handle_forum_scout_register_request,
                forum_scout_publish_handler=self._handle_forum_scout_publish_request,
                security_skills_status_handler=self._handle_security_skills_status_request,
                security_skills_scan_handler=self._handle_security_skill_scan_request,
            )
        else:
            await start_health_server(
                control_api_token=self._control_api_token,
                tradingview_update_handler=self._handle_tradingview_signal,
                tradingview_webhook_secret=self._tradingview_webhook_secret,
                market_ohlc_handler=self._handle_market_ohlc_request,
                platform_status_handler=self._handle_platform_status_request,
                control_status_handler=self._handle_control_status_request,
                routing_info_handler=self._handle_routing_info_request,
                performance_stats_handler=self._handle_performance_stats_request,
                system_logs_handler=self._handle_system_logs_request,
                tradingview_workspace_handler=self._handle_tradingview_workspace_request,
                forum_topics_handler=self._handle_forum_topics_request,
                forum_create_topic_handler=self._handle_forum_create_topic_request,
                forum_topic_detail_handler=self._handle_forum_topic_detail_request,
                forum_replies_handler=self._handle_forum_replies_request,
                forum_scout_status_handler=self._handle_forum_scout_status_request,
                forum_scout_register_handler=self._handle_forum_scout_register_request,
                forum_scout_publish_handler=self._handle_forum_scout_publish_request,
                security_skills_status_handler=self._handle_security_skills_status_request,
                security_skills_scan_handler=self._handle_security_skill_scan_request,
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
        self._media_publish_task = asyncio.create_task(self._media_publish_loop())

        # 2. Start Pub/Sub Listener for Trade Results
        asyncio.create_task(self._listen_for_trades())

        # 3. Start Gemini Guard
        asyncio.create_task(self.ai.start())

        # 4. Start Feeds, Strategy, Dispatcher
        await dispatcher.start()
        await self.market_data.start()
        await self.strategy.start()
        if self._full_autonomy_enabled:
            self._autonomy_task = asyncio.create_task(self._autonomy_ops_loop())
            await self._dispatch_full_autonomy_cycle(trigger="startup_bootstrap", force=True)
        else:
            logger.info("Full autonomy loop disabled (SAPPHIRE_FULL_AUTONOMY_ENABLED=false)")

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

                # Resolve any pending fill confirmation
                dispatcher.resolve_fill(message_data)

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
        venue = self._normalize_platform(str(query.get("venue", "ASTER")))
        if venue not in {"ASTER", "LIGHTER"}:
            return {
                "error": "unsupported_venue",
                "message": "venue must be ASTER or LIGHTER",
                "venue": venue,
                "candles": [],
            }

        symbol = str(query.get("symbol", "SOL")).strip().upper() or "SOL"
        interval = str(query.get("interval", "1m")).strip().lower() or "1m"
        limit_raw = query.get("limit", "120")
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 120
        limit = max(10, min(limit, 500))

        ohlc = await self.market_data.fetch_ohlc(
            venue=venue,
            symbol=symbol,
            interval=interval,
            limit=limit,
        )
        ohlc["generated_at"] = int(time.time())
        return ohlc

    async def _handle_platform_status_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        snapshot = self.market_data.get_market_snapshot(symbol="SOL")
        control_state = dispatcher.get_control_state()
        strategy_state = self.strategy.execution_state()
        platforms: Dict[str, Dict[str, Any]] = {}

        for venue in ("ASTER", "LIGHTER"):
            venue_state = control_state.get(venue, {"paused": True, "allocation": 0.0, "cooldown_until": 0.0})
            market = snapshot.get(
                venue,
                {"price": 0.0, "status": "offline", "age_seconds": None, "last_tick_ts": None},
            )
            paused = bool(venue_state.get("paused", False) or venue_state.get("allocation", 0.0) <= 0)
            feed_status = str(market.get("status", "offline")).lower()

            if self._kill_switch_active:
                status = "degraded"
                mode = "Kill-switch halted"
            elif paused:
                status = "degraded" if feed_status in {"healthy", "degraded"} else "offline"
                mode = "Paused allocation"
            else:
                status = "healthy" if feed_status == "healthy" else "degraded"
                mode = "Autonomous ready" if status == "healthy" else "Awaiting fresh market ticks"

            note = (
                f"Allocation {float(venue_state.get('allocation', 0.0)) * 100:.0f}% | "
                f"Tick age {market.get('age_seconds', 'n/a')}s"
            )
            platforms[venue.lower()] = {
                "status": status,
                "health": status,
                "mode": mode,
                "routing": "autonomous",
                "note": note,
                "price": market.get("price", 0.0),
                "last_tick_ts": market.get("last_tick_ts"),
                "age_seconds": market.get("age_seconds"),
                "allocation": float(venue_state.get("allocation", 0.0)),
                "paused": paused,
            }

        return {
            "platforms": platforms,
            "kill_switch_active": self._kill_switch_active,
            "dex_execution_stage": strategy_state.get("dex_execution_stage", "paper"),
            "dex_live_dispatch": bool(strategy_state.get("stage_multiplier", 0) > 0),
            "dex_effective_quantity": float(strategy_state.get("effective_quantity", 0.0)),
            "timestamp": int(time.time()),
        }

    async def _handle_control_status_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self._control_snapshot()

    async def _handle_routing_info_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        state = dispatcher.get_control_state()
        strategy_state = self.strategy.execution_state()
        active = [venue for venue, item in state.items() if not item.get("paused") and item.get("allocation", 0) > 0]
        paused = [venue for venue, item in state.items() if item.get("paused") or item.get("allocation", 0) <= 0]
        failure_pressure = int(sum(self._failure_counts.values()))
        snapshot = self.market_data.get_market_snapshot(symbol="SOL")

        if self._kill_switch_active:
            confidence = 0.0
            mode = "halted"
        else:
            healthy_active = sum(
                1 for venue in active if snapshot.get(venue, {}).get("status") == "healthy"
            )
            confidence = 0.92
            confidence -= min(0.45, failure_pressure * 0.08)
            if len(active) < max(1, self._trading_gate_min_active_venues):
                confidence -= 0.25
            elif len(active) < 2:
                confidence -= 0.08
            if active and healthy_active < len(active):
                confidence -= 0.15
            confidence = max(0.05, min(0.99, confidence))
            mode = "autonomous" if confidence >= 0.7 else "guarded"

        return {
            "mode": mode,
            "strategy": "policy-gated",
            "confidence": float(round(confidence, 4)),
            "data": {
                "confidence": float(round(confidence, 4)),
            },
            "routing": {
                "confidence": float(round(confidence, 4)),
                "active_venues": active,
                "paused_venues": paused,
                "failure_pressure": failure_pressure,
                "kill_switch_active": self._kill_switch_active,
                "dex_execution_stage": strategy_state.get("dex_execution_stage", "paper"),
                "dex_live_dispatch": bool(strategy_state.get("stage_multiplier", 0) > 0),
            },
            "timestamp": int(time.time()),
        }

    async def _handle_performance_stats_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        total_trades = int(self._trade_metrics["total_trades"])
        wins = int(self._trade_metrics["wins"])
        losses = int(self._trade_metrics["losses"])
        win_rate = float((wins / total_trades) * 100.0) if total_trades > 0 else 0.0
        uptime_seconds = int(max(0, time.time() - self._started_at))
        failure_pressure = int(sum(self._failure_counts.values()))

        return {
            "metrics": {
                "system": {
                    "total_trades": total_trades,
                    "wins": wins,
                    "losses": losses,
                    "win_rate": round(win_rate, 2),
                    "realized_pnl": float(round(self._trade_metrics["realized_pnl"], 6)),
                    "uptime_seconds": uptime_seconds,
                    "failure_pressure": failure_pressure,
                    "autonomy_dispatch_count": int(self._autonomy_dispatch_count),
                }
            },
            "timestamp": int(time.time()),
        }

    async def _handle_system_logs_request(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        limit_raw = payload.get("limit", 80)
        try:
            limit = int(limit_raw)
        except (TypeError, ValueError):
            limit = 80
        limit = max(1, min(limit, self._system_log_max_entries))
        return list(self._system_logs)[-limit:]

    async def _handle_tradingview_workspace_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        if not self._tradingview_integration_enabled:
            snapshot = self.tv_autonomy.status_snapshot()
            snapshot["enabled"] = False
            snapshot["reason"] = "tradingview_integration_disabled"
            return {
                "workspace": snapshot,
                "timestamp": int(time.time()),
            }

        snapshot = self.tv_autonomy.status_snapshot()
        return {
            "workspace": snapshot,
            "timestamp": int(time.time()),
        }

    async def _handle_security_skills_status_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        status = self.vt_scanner.status()
        status["timestamp"] = int(time.time())
        return status

    async def _handle_security_skill_scan_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        requested_skill = str(payload.get("skill", "")).strip()
        upload_if_missing_raw = payload.get("upload_if_missing", self.vt_scanner.upload_if_missing_default)
        upload_if_missing = str(upload_if_missing_raw).strip().lower() in {"1", "true", "yes", "on"}

        if requested_skill and requested_skill.lower() != "all":
            result = await self.vt_scanner.scan_skill(
                requested_skill,
                upload_if_missing=upload_if_missing,
            )
            if result.get("ok"):
                security = result.get("security", {})
                self._record_system_log(
                    f"VirusTotal scan completed for {requested_skill}",
                    level="info",
                    tags=["security", "virustotal", "skills"],
                    metadata={
                        "skill": requested_skill,
                        "verdict": security.get("verdict", "unknown"),
                        "policy_blocked": bool(
                            (security.get("policy", {}) or {}).get("blocked", False)
                        ),
                    },
                )
            return result

        batch_result = await self.vt_scanner.scan_all_skills(upload_if_missing=upload_if_missing)
        if batch_result.get("ok"):
            self._record_system_log(
                "VirusTotal batch scan completed",
                level="info",
                tags=["security", "virustotal", "skills"],
                metadata={
                    "skills_scanned": int(batch_result.get("skills_scanned", 0)),
                    "counts": batch_result.get("counts", {}),
                    "blocked_count": int(batch_result.get("blocked_count", 0)),
                },
            )
        return batch_result

    async def _handle_forum_topics_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        board = self.forum.list_topics(payload)
        control = self._control_snapshot()
        return {
            **board,
            "control": {
                "pending_autonomy_decisions": int(control.get("pending_autonomy_decisions", 0)),
                "owner_directive": str(control.get("owner_directive", "") or ""),
                "failure_pressure": int(control.get("failure_pressure", 0)),
            },
            "timestamp": int(time.time()),
        }

    async def _handle_forum_topic_detail_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        topic_id = str(payload.get("topic_id", "")).strip()
        if not topic_id:
            return {"error": "topic_id_required"}
        topic = self.forum.get_topic_detail(topic_id)
        if not topic:
            return {"error": "topic_not_found", "topic_id": topic_id}
        return {"topic": topic, "timestamp": int(time.time())}

    async def _handle_forum_create_topic_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            topic = self.forum.create_topic(
                {
                    "title": payload.get("title", ""),
                    "body": payload.get("body", ""),
                    "lane": payload.get("lane", "research"),
                    "state": payload.get("state", "open"),
                    "priority": payload.get("priority", "medium"),
                    "author": payload.get("author", "SAPPHIRE"),
                    "tags": payload.get("tags", []),
                    "source": payload.get("source", "internal"),
                }
            )
        except ValueError as exc:
            return {"error": str(exc)}

        self._record_system_log(
            f"Forum topic created: {topic.get('topic_id', 'unknown')}",
            level="info",
            tags=["forum", "topic"],
            metadata={
                "topic_id": topic.get("topic_id", ""),
                "lane": topic.get("lane", ""),
                "priority": topic.get("priority", ""),
            },
        )
        return {"topic": topic, "timestamp": int(time.time())}

    async def _handle_forum_replies_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        topic_id = str(payload.get("topic_id", "")).strip()
        if not topic_id:
            return {"error": "topic_id_required"}

        body = str(payload.get("body", "")).strip()
        if not body:
            return {"error": "body_required"}

        try:
            reply = self.forum.add_reply(
                topic_id,
                {
                    "body": body,
                    "author": payload.get("author", "SAPPHIRE"),
                    "kind": payload.get("kind", "comment"),
                    "state": payload.get("state", ""),
                    "source": payload.get("source", "internal"),
                },
            )
        except ValueError as exc:
            return {"error": str(exc)}

        self._record_system_log(
            f"Forum reply added to {topic_id}",
            level="info",
            tags=["forum", "reply"],
            metadata={"topic_id": topic_id, "reply_id": reply.get("reply_id", "")},
        )
        return {"reply": reply, "timestamp": int(time.time())}

    async def _handle_forum_scout_status_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        return self.forum.scout_status()

    async def _handle_forum_scout_register_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.forum.register_scout_account(payload)
        if result.get("ok"):
            dispatch = result.get("dispatch", {}) or {}
            mode = str(dispatch.get("mode", "none")).strip() or "none"
            metadata = dispatch.get("metadata", {}) if isinstance(dispatch, dict) else {}
            metadata = metadata if isinstance(metadata, dict) else {}
            username = result.get("registration", {}).get("username", "unknown")
            if dispatch.get("dispatched"):
                lines = [
                    "🛰️ Scout registration processed.",
                    f"Mode: `{mode}`",
                    f"User: `@{username}`",
                    "Outcome: least-privilege external collaboration scout is active.",
                ]
                if metadata.get("claim_url"):
                    lines.append(f"Action: complete claim in Moltbook once using `{metadata.get('claim_url')}`.")
                elif metadata.get("already_registered"):
                    lines.append("Action: existing claimed scout account detected; no re-registration needed.")
                await self.telegram.send_message(
                    "\n".join(lines),
                    priority="medium",
                )
            else:
                lines = [
                    "🛰️ Scout registration prepared locally; external provider blocked dispatch.",
                    f"Mode: `{mode}`",
                    f"Reason: `{dispatch.get('reason', 'not_configured')}`",
                    "Benefit preserved: local SapphireBook record exists for retry/audit without exposing sensitive data.",
                ]
                if metadata.get("hint"):
                    lines.append(f"Hint: {metadata.get('hint')}")
                await self.telegram.send_message(
                    "\n".join(lines),
                    priority="medium",
                )
        return result

    async def _handle_forum_scout_publish_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        result = await self.forum.publish_scout_note(payload)
        if result.get("ok"):
            dispatch = result.get("dispatch", {}) or {}
            if not dispatch.get("dispatched"):
                self._record_system_log(
                    "Scout outbound note stored locally; external publish pending",
                    level="warning",
                    tags=["forum", "scout"],
                    metadata={"reason": dispatch.get("reason", "not_configured")},
                )
        return result

    async def stop(self):
        logger.info("🛑 Stopping Alpha Engine...")
        self.running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._autonomy_task:
            self._autonomy_task.cancel()
        if self._media_publish_task:
            self._media_publish_task.cancel()
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
