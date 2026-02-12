import asyncio
import hashlib
import json
import os
import signal
import sys
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional, Set

import uvloop
from src.ai.gemini_guard import GeminiGuard
from src.execution.dispatcher import dispatcher
from src.feeds.market_data import MarketDataAggregator
from src.integrations.tradingview_autonomy import TradingViewAutonomyPlugin
from src.strategy.engine import AlphaStrategyEngine

# Add shared library to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from error_classifier import ErrorSeverity, classify_error
from health import start_health_server
from smart_notifications import notification_manager

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
        self._telegram_webhook_mode = bool(self._telegram_webhook_url)
        self._tradingview_webhook_secret = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "").strip()
        self._tradingview_execution_enabled = (
            os.getenv("TRADINGVIEW_EXECUTION_ENABLED", "false").strip().lower()
            in {"1", "true", "yes", "on"}
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
        self._owner_directive = str(os.getenv("SAPPHIRE_OWNER_DIRECTIVE", "")).strip()
        self._owner_directive_updated_at = int(time.time()) if self._owner_directive else 0
        self._full_autonomy_enabled = self._env_flag("SAPPHIRE_FULL_AUTONOMY_ENABLED", default=False)
        self._autonomy_allow_code_changes = self._env_flag(
            "SAPPHIRE_AUTONOMY_ALLOW_CODE_CHANGES", default=True
        )
        self._autonomy_allow_gcloud_changes = self._env_flag(
            "SAPPHIRE_AUTONOMY_ALLOW_GCLOUD_CHANGES", default=True
        )
        self._autonomy_dry_run = self._env_flag("SAPPHIRE_AUTONOMY_DRY_RUN", default=False)
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
        self._trade_metrics: Dict[str, float] = {
            "total_trades": 0.0,
            "wins": 0.0,
            "losses": 0.0,
            "realized_pnl": 0.0,
        }

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
                "TradingView rules enforced",
                self._tradingview_enforce_strategy_rules and bool(self._tradingview_strategy_rules),
                "Strategy rules not enforced or missing",
            ),
            (
                "TradingView execution still dry-run",
                not self._tradingview_execution_enabled,
                "TRADINGVIEW_EXECUTION_ENABLED=true",
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
                f"Rules configured: `{len(self._tradingview_strategy_rules)}`",
                f"TV autonomy enabled: `{self.tv_autonomy.enabled}`",
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
        state = dispatcher.get_control_state()
        pending_sessions = [
            session
            for session in self._autonomy_sessions.values()
            if session.get("decision", "pending") == "pending"
        ]
        lines = [
            "📊 **CONTROL STATUS**",
            f"Kill switch: `{'ACTIVE' if self._kill_switch_active else 'INACTIVE'}`",
            f"Full autonomy: `{'ON' if self._full_autonomy_enabled else 'OFF'}`",
            f"Autonomy dispatches: `{self._autonomy_dispatch_count}`",
            f"Pending autonomy decisions: `{len(pending_sessions)}`",
            "",
        ]
        for venue in sorted(state.keys()):
            item = state[venue]
            status = "PAUSED" if item["paused"] else "LIVE"
            fail_count = self._failure_counts.get(venue, 0)
            lines.append(
                f"- `{venue}` | {status} | alloc `{item['allocation']*100:.0f}%` | failures `{fail_count}`"
            )

        await self.telegram.send_message("\n".join(lines), priority="medium")

    async def _send_focus_snapshot(self) -> None:
        state = dispatcher.get_control_state()
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
            f"TradingView autonomy: `{'ON' if self.tv_autonomy.enabled else 'OFF'}`",
            f"Community scripts: `{'ON' if self.tv_autonomy.community_access_enabled else 'OFF'}`",
            f"Owner directive: `{directive}`",
            f"Directive updated: `{directive_updated}`",
            "",
            "Use `/steer <directive>` or `/answer <response>` to update direction.",
        ]
        await self.telegram.send_message("\n".join(lines), priority="medium")

    async def _send_heartbeat(self, reason: str) -> None:
        state = dispatcher.get_control_state()
        live = [venue for venue, item in state.items() if not item["paused"] and item["allocation"] > 0]
        paused = [venue for venue, item in state.items() if item["paused"] or item["allocation"] <= 0]
        total_failures = sum(self._failure_counts.values())
        directive = self._owner_directive.strip() or "none"
        if len(directive) > 120:
            directive = directive[:117] + "..."

        msg = (
            f"💓 **SAPPHIRE HEARTBEAT** (`{reason}`)\n"
            f"Active venues: `{', '.join(live) if live else 'none'}`\n"
            f"Paused/deallocated: `{', '.join(paused) if paused else 'none'}`\n"
            f"Kill switch: `{'ACTIVE' if self._kill_switch_active else 'OFF'}`\n"
            f"Full autonomy: `{'ON' if self._full_autonomy_enabled else 'OFF'}`\n"
            f"Failure pressure: `{total_failures}`\n\n"
            f"Owner directive: `{directive}`\n\n"
            "Reply with `/status`, `/heartbeat`, `/focus`, `/promotion`, `/autonomy`, `/kill`, `/resume`, `/steer <directive>`, `/answer <response>`, "
            "`/approve <session_key>`, `/reject <session_key> <reason>`, "
            "or `@alpha deallocate <venue>`."
        )
        await self.telegram.send_message(msg, priority="medium")

    def _autonomy_context_snapshot(self) -> Dict[str, Any]:
        state = dispatcher.get_control_state()
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
            "pending_autonomy_sessions": len(
                [
                    session
                    for session in self._autonomy_sessions.values()
                    if session.get("decision", "pending") == "pending"
                ]
            ),
            "latest_autonomy_session_key": self._latest_autonomy_session_key,
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
        instruction = (
            f"{directive} Execute an autonomous maintenance and improvement cycle for code + cloud. "
            "Prioritize production safety first, then reliability, then performance."
        )

        if self._autonomy_dry_run:
            await self.telegram.send_message(
                (
                    "🧪 Full autonomy dry-run cycle prepared.\n"
                    f"Trigger: `{trigger}`\n"
                    f"Active venues: `{', '.join(context['active_venues']) if context['active_venues'] else 'none'}`\n"
                    f"Failure pressure: `{context['total_failure_pressure']}`"
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
            await self.telegram.send_message(
                (
                    "🤖 Full autonomy cycle dispatched.\n"
                    f"Trigger: `{trigger}`\n"
                    f"Session: `{hook_result.get('session_key', 'n/a')}`\n"
                    "Decision loop: `/approve <session_key>` or `/reject <session_key> <reason>`."
                ),
                priority="high",
            )
        else:
            self._record_system_log(
                f"Full autonomy dispatch unavailable ({trigger}): {hook_result.get('reason', 'unknown')}",
                level="warning",
                tags=["autonomy", "dispatch"],
            )
            await self.telegram.send_message(
                (
                    "⚠️ Full autonomy dispatch unavailable.\n"
                    f"Trigger: `{trigger}`\n"
                    f"Reason: `{hook_result.get('reason', 'unknown')}`"
                ),
                priority="high",
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

            entry = self._autonomy_sessions.get(session_key, {"session_key": session_key})
            if len(note) > 400:
                note = note[:400]
            entry["decision"] = "approved" if decision == "APPROVE" else "rejected"
            entry["decision_note"] = note
            entry["decision_at"] = int(time.time())
            self._autonomy_sessions[session_key] = entry

            hook_result = await self.tv_autonomy.dispatch_session_decision(
                session_key=session_key,
                decision=decision,
                note=note,
            )
            if hook_result.get("dispatched"):
                await self.telegram.send_message(
                    (
                        f"✅ Session `{session_key}` marked `{decision}`.\n"
                        f"Dispatch: `{hook_result.get('session_key', 'n/a')}`"
                    ),
                    priority="high",
                )
                self._record_system_log(
                    f"Owner session decision {decision} for {session_key}",
                    level="info",
                    tags=["autonomy", "decision"],
                    metadata={"session_key": session_key, "decision": decision, "note": note},
                )
            else:
                await self.telegram.send_message(
                    (
                        f"⚠️ Session decision captured locally but dispatch failed for `{session_key}`.\n"
                        f"Reason: `{hook_result.get('reason', 'unknown')}`"
                    ),
                    priority="high",
                )
                self._record_system_log(
                    f"Session decision dispatch failed for {session_key}",
                    level="warning",
                    tags=["autonomy", "decision"],
                    metadata={"session_key": session_key, "decision": decision, "reason": hook_result.get("reason", "")},
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

        if normalized_action in {"FOCUS", "CONTROL_FOCUS"}:
            await self._send_focus_snapshot()
            return

        if normalized_action in {"PROMOTION_GATE", "STRATEGY_GATE", "PROMOTION", "GATE"}:
            await self._send_promotion_gate_report("manual")
            return

        if normalized_action in {"AUTONOMY", "AUTONOMY_CYCLE"}:
            await self._dispatch_full_autonomy_cycle(trigger="manual_telegram", force=True)
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

            await self.telegram.send_message(
                f"🧠 Owner directive recorded: `{directive}`",
                priority="high",
            )

            hook_result = await self.tv_autonomy.dispatch_owner_instruction(directive)
            if hook_result.get("dispatched"):
                await self.telegram.send_message(
                    f"✅ OpenClaw steering dispatch queued (`{hook_result.get('session_key', 'n/a')}`).",
                    priority="medium",
                )
            else:
                await self.telegram.send_message(
                    (
                        "⚠️ OpenClaw steering dispatch unavailable "
                        f"(`{hook_result.get('reason', 'unknown')}`). Directive kept in focus context."
                    ),
                    priority="high",
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

        if self.tv_autonomy.is_workspace_action(normalized_action):
            workspace_result = await self.tv_autonomy.handle_action(normalized_action, merged_payload)
            result_type = workspace_result.get("accepted", "unknown")
            if result_type in {"workspace_updated", "workspace_noop", "scan_requested", "custom_requested"}:
                dispatch = workspace_result.get("dispatch", {})
                dispatch_status = "yes" if dispatch.get("dispatched") else f"no ({dispatch.get('reason', 'n/a')})"
                await self.telegram.send_message(
                    (
                        f"🧩 TradingView workspace action `{normalized_action}` processed.\n"
                        f"Result: `{result_type}`\n"
                        f"OpenClaw dispatch: `{dispatch_status}`"
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
        for venue in targets:
            venue_cap = self._max_quantity_for_venue(venue)
            strategy_cap = strategy_rule.get("max_quantity") if strategy_rule else None
            if strategy_cap is not None:
                venue_cap = strategy_cap if venue_cap is None else min(venue_cap, strategy_cap)
            venue_qty = quantity
            if venue_cap is not None and venue_qty > venue_cap:
                venue_qty = venue_cap
                capped_targets.append(venue)
            per_target_quantity[venue] = venue_qty

        if not self._tradingview_execution_enabled:
            qty_parts = [f"{venue}:{per_target_quantity[venue]}" for venue in sorted(targets)]
            cap_note = (
                f" Caps applied on `{', '.join(sorted(set(capped_targets)))}`."
                if capped_targets
                else ""
            )
            await self.telegram.send_message(
                (
                    f"📥 TradingView signal captured (dry-run): `{normalized_action.upper()} {symbol}` "
                    f"with quantities `{', '.join(qty_parts)}`. Set `TRADINGVIEW_EXECUTION_ENABLED=true` to execute."
                    f"{cap_note}"
                ),
                priority="medium",
            )
            return {
                "accepted": "dry_run",
                "targets": targets,
                "signal_key": signal_key,
                "quantities": per_target_quantity,
                "capped_targets": sorted(set(capped_targets)),
                "strategy": strategy_label or None,
            }

        dispatch_results: Dict[str, bool] = {}
        for venue in targets:
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
            await self.telegram.send_message(
                f"❌ TradingView dispatch failed for `{', '.join(failed_targets)}` (`{signal_key}`).",
                priority="high",
            )
            return {
                "accepted": "partial_failure",
                "targets": targets,
                "failed_targets": failed_targets,
                "signal_key": signal_key,
                "quantities": per_target_quantity,
                "capped_targets": sorted(set(capped_targets)),
                "strategy": strategy_label or None,
            }

        qty_parts = [f"{venue}:{per_target_quantity[venue]}" for venue in sorted(targets)]
        await self.telegram.send_message(
            f"✅ TradingView executed: `{normalized_action.upper()} {symbol}` with `{', '.join(qty_parts)}` (`{signal_key}`).",
            priority="high",
        )
        return {
            "accepted": "executed",
            "targets": targets,
            "signal_key": signal_key,
            "quantities": per_target_quantity,
            "capped_targets": sorted(set(capped_targets)),
            "strategy": strategy_label or None,
        }

    async def _record_trade_outcome(self, platform: str, success: bool, error_message: str = "") -> None:
        venue = self._normalize_platform(platform)
        if venue not in dispatcher.bot_urls:
            return

        if success:
            self._failure_counts[venue] = 0
            return

        self._failure_counts[venue] += 1
        failures = self._failure_counts[venue]

        if failures < self._deallocation_failure_threshold:
            return
        if venue in self._auto_deallocated:
            return

        dispatcher.set_venue_allocation(venue, 0.0)
        dispatcher.pause_venue(
            venue,
            reason=f"auto-deallocated after {failures} failures",
            cooldown_seconds=self._deallocation_cooldown_seconds,
        )
        self._auto_deallocated.add(venue)
        self._record_system_log(
            f"{venue} auto-deallocated after {failures} failures",
            level="error",
            tags=["risk", "auto_deallocation"],
            metadata={"failures": failures},
        )

        await self._publish_risk_alert(
            action="halt_trading",
            severity="critical",
            alert_type="auto_deallocation",
            message=(
                f"{venue} auto-deallocated after {failures} consecutive failures. "
                f"Cooldown {self._deallocation_cooldown_seconds}s."
            ),
            platforms=[venue],
            metadata={
                "source": "alpha-engine",
                "failure_count": failures,
                "last_error": error_message[:200],
            },
        )

        await self.telegram.send_message(
            f"🛑 **AUTO DEALLOCATION**\nVenue: `{venue}`\nFailures: `{failures}`\nCooldown: `{self._deallocation_cooldown_seconds}s`",
            priority="high",
        )

    async def _heartbeat_loop(self) -> None:
        while self.running:
            try:
                await asyncio.sleep(max(60, self._heartbeat_interval_seconds))
                await self._send_heartbeat("scheduled")

                resumed = dispatcher.resume_expired_venues()
                for venue in resumed:
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

        # Dispatch command via ExecutionDispatcher
        await dispatcher.send_command(
            platform,
            {
                "action": action,
                "symbol": symbol,
                "quantity": quantity,
                "source": "telegram_override",
            },
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
                tradingview_update_handler=self._handle_tradingview_signal,
                tradingview_webhook_secret=self._tradingview_webhook_secret,
                market_ohlc_handler=self._handle_market_ohlc_request,
                platform_status_handler=self._handle_platform_status_request,
                routing_info_handler=self._handle_routing_info_request,
                performance_stats_handler=self._handle_performance_stats_request,
                system_logs_handler=self._handle_system_logs_request,
            )
        else:
            await start_health_server(
                tradingview_update_handler=self._handle_tradingview_signal,
                tradingview_webhook_secret=self._tradingview_webhook_secret,
                market_ohlc_handler=self._handle_market_ohlc_request,
                platform_status_handler=self._handle_platform_status_request,
                routing_info_handler=self._handle_routing_info_request,
                performance_stats_handler=self._handle_performance_stats_request,
                system_logs_handler=self._handle_system_logs_request,
            )

        # 1. Start Telegram FIRST for immediate status
        logger.info("📡 Initializing Telegram Notification Task...")
        asyncio.create_task(
            self.telegram.send_message("💎 Sapphire Alpha Hub Online & Listening", priority="high")
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

                    # Check if we should notify
                    should_notify = notification_manager.should_notify(err, category, severity)

                    if should_notify:
                        msg = f"❌ TRADE FAILED: {platform} | {side} {symbol} | Error: {err}"
                        self._record_system_log(
                            msg,
                            level="error",
                            tags=["trade", "failure", platform.lower()],
                            metadata={"side": side, "symbol": symbol},
                        )

                        # Use appropriate priority based on severity
                        priority = "high" if severity >= ErrorSeverity.ERROR else "medium"
                        await self.telegram.send_message(msg, priority=priority)
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
            "timestamp": int(time.time()),
        }

    async def _handle_routing_info_request(self, _: Dict[str, Any]) -> Dict[str, Any]:
        state = dispatcher.get_control_state()
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

    async def stop(self):
        logger.info("🛑 Stopping Alpha Engine...")
        self.running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._autonomy_task:
            self._autonomy_task.cancel()
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
