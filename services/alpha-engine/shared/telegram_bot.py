"""
Focused Telegram bot service for Sapphire Alpha.

Design goals:
- Keep control flow scoped to Sapphire and enabled venues.
- Support heartbeat/control commands and owner steering notes.
- Operate safely in either polling mode or webhook mode.
"""

import asyncio
import json
import os
import re
from collections import OrderedDict
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import aiohttp
from loguru import logger


class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TelegramPlatformBot:
    """Telegram bot with command parsing and notification batching."""

    CONTROL_ACTION_MAP = {
        "kill": "HALT_TRADING",
        "halt": "HALT_TRADING",
        "resume": "RESUME_TRADING",
        "status": "CONTROL_STATUS",
        "heartbeat": "HEARTBEAT",
        "promotion": "PROMOTION_GATE",
        "gate": "PROMOTION_GATE",
        "focus": "CONTROL_FOCUS",
        "autonomy": "AUTONOMY_CYCLE",
        "security": "SECURITY_STATUS",
    }
    TARGET_ALIASES = {
        "LIGHT": "LIGHTER",
        "L2": "LIGHTER",
        "LT": "LIGHTER",
    }

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        command_callback: Optional[Callable[[str, str, str, float], Any]] = None,
    ):
        self.bot_token = bot_token.strip() if bot_token else ""
        self.chat_id = str(chat_id).strip() if chat_id else ""
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else ""
        self.command_callback = command_callback
        self.last_update_id = 0
        self.running = False
        self.message_buffer: List[str] = []
        self._flush_task: Optional[asyncio.Task[Any]] = None
        self._session: Optional[aiohttp.ClientSession] = None

        # Restrict command targets to explicit venues for focused operations.
        self.allowed_targets = self._parse_allowed_targets(
            os.getenv("TELEGRAM_ALLOWED_TARGETS", "ASTER,LIGHTER,ALL")
        )
        self.allowed_trade_targets = {target for target in self.allowed_targets if target != "ALL"}

        logger.info(
            "Initializing Telegram Bot | token={} chat={} allowed_targets={}",
            "set" if self.bot_token else "missing",
            "set" if self.chat_id else "missing",
            ",".join(sorted(self.allowed_targets)),
        )

    @staticmethod
    def _parse_allowed_targets(value: str) -> Set[str]:
        tokens = re.split(r"[,;|\s]+", str(value or ""))
        parsed = {token.strip().upper() for token in tokens if token.strip()}
        parsed.add("ALL")
        if "LIGHT" in parsed:
            parsed.remove("LIGHT")
            parsed.add("LIGHTER")
        if "L2" in parsed:
            parsed.remove("L2")
            parsed.add("LIGHTER")
        if not ({"ASTER", "LIGHTER"} & parsed):
            parsed.update({"ASTER", "LIGHTER"})
        return parsed

    @classmethod
    def _normalize_target(cls, value: str) -> str:
        normalized = str(value or "").strip().upper()
        return cls.TARGET_ALIASES.get(normalized, normalized)

    @staticmethod
    def _coerce_priority(value: NotificationPriority | str | None) -> NotificationPriority:
        if isinstance(value, NotificationPriority):
            return value
        as_text = str(value or "").strip().lower()
        for candidate in NotificationPriority:
            if candidate.value == as_text:
                return candidate
        return NotificationPriority.MEDIUM

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=20, connect=10, sock_connect=10, sock_read=15)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self):
        self.running = False
        if self._flush_task:
            self._flush_task.cancel()
            self._flush_task = None
        if self._session and not self._session.closed:
            await self._session.close()

    async def start(self):
        """Start buffer flush loop and long-poll listener."""
        self.running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        await self.start_listener()

    async def _flush_loop(self):
        while self.running:
            await asyncio.sleep(20)
            if self.message_buffer:
                await self._flush_buffer()

    async def _flush_buffer(self):
        if not self.message_buffer:
            return
        digest_lines = self._build_digest_lines(self.message_buffer)
        self.message_buffer.clear()
        batch_text = "📋 **Sapphire Update Digest**\n" + "\n".join(digest_lines)
        await self._dispatch_message(batch_text, allow_markdown=True)

    @staticmethod
    def _clean_digest_text(text: str) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "").strip())
        normalized = re.sub(r"Reply with /status.*$", "", normalized, flags=re.IGNORECASE)
        return normalized.strip()

    @staticmethod
    def _extract_section(text: str, marker: str, stop_markers: List[str]) -> str:
        source = str(text or "")
        marker_idx = source.lower().find(marker.lower())
        if marker_idx < 0:
            return ""
        tail = source[marker_idx + len(marker) :]
        lower_tail = tail.lower()
        stop_idx = len(tail)
        for stop in stop_markers:
            idx = lower_tail.find(stop.lower())
            if idx >= 0:
                stop_idx = min(stop_idx, idx)
        return tail[:stop_idx].strip(" `:;,.")

    @staticmethod
    def _trim_summary(text: str, limit: int = 90) -> str:
        value = str(text or "").strip()
        if len(value) <= limit:
            return value
        return value[: max(0, limit - 3)].rstrip() + "..."

    @classmethod
    def _extract_any_section(cls, text: str, markers: List[str], stop_markers: List[str]) -> str:
        for marker in markers:
            value = cls._extract_section(text, marker, stop_markers)
            if value:
                return value
        return ""

    @classmethod
    def _summarize_digest_text(cls, text: str) -> str:
        cleaned = cls._clean_digest_text(text)
        lowered = cleaned.lower()

        if "autonomy decision brief" in lowered:
            session = cls._extract_section(cleaned, "Session:", ["Trigger:", "Why now:"])
            trigger = cls._extract_section(cleaned, "Trigger:", ["Why now:", "Current state:"])
            outcome = cls._extract_section(
                cleaned,
                "Expected outcome:",
                ["Benefit vs current state:", "Risk if deferred:", "Decision:", "Bulk option:"],
            )
            benefit = cls._extract_section(
                cleaned,
                "Benefit vs current state:",
                ["Risk if deferred:", "Decision:", "Bulk option:"],
            )
            return (
                f"🤖 Autonomy brief `{session or 'n/a'}` "
                f"trigger `{trigger or 'n/a'}` | "
                f"outcome {cls._trim_summary(outcome, 72) or 'n/a'} | "
                f"benefit {cls._trim_summary(benefit, 72) or 'n/a'}"
            )

        if "gemini flash" in lowered:
            insight = cls._extract_section(cleaned, "Gemini Flash", [])
            if not insight and ":" in cleaned:
                insight = cleaned.split(":", 1)[1].strip()
            return f"⚡ Market pulse: {insight}" if insight else "⚡ Market pulse update"

        if "sapphire heartbeat" in lowered:
            active = cls._extract_any_section(
                cleaned,
                ["Active venues:", "Active:"],
                ["Paused/deallocated:", "Paused venues:", "Paused:", "Kill switch:"],
            )
            paused = cls._extract_any_section(
                cleaned,
                ["Paused/deallocated:", "Paused venues:", "Paused:"],
                ["Kill switch:", "Autonomy:", "Full autonomy:"],
            )
            kill = cls._extract_section(
                cleaned,
                "Kill switch:",
                ["Full autonomy:", "Autonomy:", "Approvals:", "Failure pressure:"],
            )
            autonomy = cls._extract_any_section(
                cleaned,
                ["Full autonomy:", "Autonomy:"],
                ["Failure pressure:", "Owner directive:", "Approvals:"],
            )
            approvals = cls._extract_section(
                cleaned,
                "Approvals:",
                ["Failure pressure:", "Owner directive:", "Directive:"],
            )
            pending = cls._extract_section(cleaned, "Pending approvals:", ["Failure pressure:", "Directive:"])
            return (
                "💓 Heartbeat: "
                f"active `{active or 'none'}` | paused `{paused or 'none'}` | "
                f"kill `{kill or 'n/a'}` | autonomy `{autonomy or 'n/a'}` | "
                f"approvals `{approvals or 'n/a'}` | pending `{pending or '0'}`"
            )

        if "tradingview workspace action" in lowered:
            action_match = re.search(
                r"workspace action\s+`?([a-z0-9_:-]+)`?",
                cleaned,
                flags=re.IGNORECASE,
            )
            action = str(action_match.group(1) if action_match else "unknown").strip()
            result = cls._extract_section(cleaned, "Result:", ["OpenClaw dispatch:"])
            dispatch = cls._extract_section(cleaned, "OpenClaw dispatch:", [])
            return (
                f"🧩 Workspace `{action}`: `{result or 'processed'}`"
                + (f" (dispatch `{dispatch}`)" if dispatch else "")
            )

        if "expected outcome:" in lowered and (
            "queued" in lowered or "requested" in lowered or "captured" in lowered
        ):
            request = cleaned.split("Expected outcome:", 1)[0].strip(" \n\t-")
            outcome = cls._extract_section(
                cleaned,
                "Expected outcome:",
                ["Benefit:", "Next update:", "Quick actions:", "Use `/help`"],
            )
            benefit = cls._extract_section(
                cleaned,
                "Benefit:",
                ["Next update:", "Quick actions:", "Use `/help`"],
            )
            return (
                f"🧭 {cls._trim_summary(request, 70)} | "
                f"outcome {cls._trim_summary(outcome, 64) or 'n/a'}"
                + (
                    f" | benefit {cls._trim_summary(benefit, 56)}"
                    if benefit
                    else ""
                )
            )

        return cleaned

    @classmethod
    def _digest_signature(cls, text: str) -> str:
        cleaned = cls._clean_digest_text(text).lower()
        # Collapse highly repetitive AI flash lines into one digest bucket.
        if "gemini flash" in cleaned or "market pulse" in cleaned:
            return "gemini_flash"
        if "sapphire heartbeat" in cleaned or cleaned.startswith("💓 heartbeat"):
            return "heartbeat"
        if "tradingview workspace action" in cleaned or cleaned.startswith("🧩 workspace"):
            action_match = re.search(r"(tv_[a-z0-9_:-]+)", cleaned)
            result_match = re.search(r"result[:\s`]+([a-z_]+)", cleaned)
            action_key = action_match.group(1) if action_match else "unknown"
            result_key = result_match.group(1) if result_match else "unknown"
            return f"workspace:{action_key}:{result_key}"
        if "autonomy decision brief" in cleaned or cleaned.startswith("🤖 autonomy brief"):
            session_match = re.search(r"session[:\s`]+([a-z0-9:._-]+)", cleaned)
            trigger_match = re.search(r"trigger[:\s`]+([a-z0-9_:-]+)", cleaned)
            session_key = session_match.group(1) if session_match else "latest"
            trigger_key = trigger_match.group(1) if trigger_match else "unknown"
            return f"autonomy_brief:{session_key}:{trigger_key}"
        return cleaned

    @classmethod
    def _build_digest_lines(cls, raw_messages: List[str]) -> List[str]:
        if not raw_messages:
            return ["- no updates"]

        grouped: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        for raw in raw_messages[-20:]:
            cleaned = cls._clean_digest_text(raw)
            if not cleaned:
                continue
            summary = cls._summarize_digest_text(cleaned)
            signature = cls._digest_signature(summary)
            if signature in grouped:
                grouped[signature]["count"] += 1
                grouped[signature]["text"] = summary
            else:
                grouped[signature] = {"text": summary, "count": 1}

        lines: List[str] = []
        for idx, item in enumerate(grouped.values(), start=1):
            text = item["text"]
            count = int(item["count"])
            suffix = f" _(x{count})_" if count > 1 else ""
            lines.append(f"{idx}. {text}{suffix}")
        return lines

    async def send_message(
        self,
        text: str,
        priority: NotificationPriority | str = NotificationPriority.MEDIUM,
        **_: Any,
    ):
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram configuration missing; message dropped")
            return

        level = self._coerce_priority(priority)
        prefix = {
            NotificationPriority.LOW: "📝",
            NotificationPriority.MEDIUM: "📢",
            NotificationPriority.HIGH: "🚨",
            NotificationPriority.CRITICAL: "🚨🚨",
        }[level]
        full_message = f"{prefix} {text}"

        if level in {NotificationPriority.LOW, NotificationPriority.MEDIUM}:
            self.message_buffer.append(full_message)
            if len(self.message_buffer) >= 10:
                await self._flush_buffer()
            return

        await self._dispatch_message(full_message, allow_markdown=True)

    async def _dispatch_message(self, text: str, allow_markdown: bool = True) -> bool:
        if not self.base_url:
            return False

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if allow_markdown:
            payload["parse_mode"] = "Markdown"

        session = await self._get_session()
        url = f"{self.base_url}/sendMessage"

        for attempt in range(1, 4):
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        return True

                    body = await resp.text()
                    logger.warning(
                        "Telegram sendMessage failed status={} attempt={} body={}",
                        resp.status,
                        attempt,
                        body[:200],
                    )

                    # Retry once without markdown if formatting fails.
                    if resp.status == 400 and payload.get("parse_mode"):
                        payload.pop("parse_mode", None)
                        continue
            except Exception as exc:
                logger.warning("Telegram sendMessage exception attempt={} err={}", attempt, exc)

            if attempt < 3:
                await asyncio.sleep(attempt * 2)

        logger.error("Telegram sendMessage failed after retries")
        return False

    async def configure_webhook(self, webhook_url: str, secret_token: str = "") -> bool:
        """Configure Telegram webhook mode for inbound command delivery."""
        if not self.bot_token:
            logger.error("Cannot configure webhook without bot token")
            return False
        if not webhook_url:
            logger.error("Cannot configure webhook without TELEGRAM_WEBHOOK_URL")
            return False

        payload: Dict[str, Any] = {
            "url": webhook_url,
            "allowed_updates": ["message"],
            "drop_pending_updates": False,
        }
        if secret_token:
            payload["secret_token"] = secret_token

        session = await self._get_session()
        url = f"{self.base_url}/setWebhook"
        try:
            async with session.post(url, json=payload) as resp:
                data = await resp.json()
                if resp.status == 200 and data.get("ok"):
                    logger.info(f"Telegram webhook configured: {webhook_url}")
                    return True
                logger.error(f"Failed to configure Telegram webhook: {data}")
        except Exception as exc:
            logger.error(f"Telegram webhook setup failed: {exc}")
        return False

    async def start_listener(self):
        """Start long-polling listener for Telegram commands."""
        if not self.bot_token:
            logger.error("Cannot start Telegram listener without token")
            return

        logger.info("Telegram command listener started")
        self.running = True

        while self.running:
            try:
                params = {"offset": self.last_update_id + 1, "timeout": 50}
                session = await self._get_session()
                async with session.get(f"{self.base_url}/getUpdates", params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("ok"):
                            for update in data.get("result", []):
                                self.last_update_id = update["update_id"]
                                await self._process_update(update)
                    elif resp.status == 409:
                        # Another listener might be active.
                        await asyncio.sleep(8)
                    else:
                        logger.warning(f"Telegram listener status={resp.status}")
                        await asyncio.sleep(5)
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                logger.error(f"Telegram listener crashed: {exc}")
                await asyncio.sleep(5)

    def _help_text(self) -> str:
        targets = ", ".join(sorted(self.allowed_trade_targets))
        return (
            "💎 **SAPPHIRE TELEGRAM CONTROL**\n"
            f"Focused venues: `{targets}`\n\n"
            "Control commands:\n"
            "- `/status`\n"
            "- `/heartbeat`\n"
            "- `/focus`\n"
            "- `/promotion`\n"
            "- `/autonomy`\n"
            "- `/kill`\n"
            "- `/resume`\n"
            "- `/approve <session_key> [note]`\n"
            "- `/approve_all [note]`\n"
            "- `/reject <session_key> [reason]`\n"
            "- `/trade on [qty]` / `/trade off` (TradingView signal mode)\n"
            "- `/qty <amount>` (TradingView signal qty)\n"
            "- `/stage <paper|staged_live|full_live>`\n"
            "- `/scout status`\n"
            "- `/scout register <username> [display_name]`\n"
            "- `/scout publish <note>`\n"
            "- `/security status`\n"
            "- `/security scan [skill|all] [no-upload|upload]` (default: no-upload)\n"
            "- `/deallocate <venue>`\n"
            "- `/allocate <venue> <percent>`\n\n"
            "Owner steering:\n"
            "- `/steer <directive>`\n"
            "- `/answer <response>` (heartbeat reply)\n"
            "- `@alpha steer <directive>`\n\n"
            "Manual trade override:\n"
            "- `@aster buy 1.0 BTC`\n"
            "- `@lighter sell 0.5 ETH`\n"
        )

    async def _dispatch_callback(self, platform: str, symbol: str, action: str, quantity: float) -> bool:
        if not self.command_callback:
            logger.warning("No Telegram command callback registered")
            return False
        try:
            await self.command_callback(platform, symbol, action, quantity)
            return True
        except Exception as exc:
            logger.error(f"Telegram command callback error: {exc}")
            await self.send_message(f"❌ Command dispatch failed: {exc}", priority=NotificationPriority.HIGH)
            return False

    async def _process_update(self, update: Dict[str, Any]):
        message = update.get("message", {}) or update.get("edited_message", {})
        text = str(message.get("text", "")).strip()
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Security: only process owner-authorized chat.
        if self.chat_id and chat_id != self.chat_id:
            return
        if not text:
            return

        text_lower = text.lower()

        # Help / start
        if re.search(r"^/(start|help)\b", text_lower):
            await self.send_message(self._help_text(), priority=NotificationPriority.MEDIUM)
            return

        # Scout collaboration commands
        slash_scout_status = re.search(
            r"^/scout\s+status$",
            text,
            flags=re.IGNORECASE,
        )
        mention_scout_status = re.search(
            r"@(alpha|control)\s+scout\s+status$",
            text,
            flags=re.IGNORECASE,
        )
        if slash_scout_status or mention_scout_status:
            await self.send_message(
                (
                    "🛰️ Scout status request queued.\n"
                    "Expected outcome: return current scout registration, bridge mode, and fallback readiness.\n"
                    "Benefit: faster triage if external collaboration is blocked."
                ),
                priority=NotificationPriority.HIGH,
            )
            await self._dispatch_callback("CONTROL", "ALL", "SCOUT_STATUS", 0.0)
            return

        slash_scout_register = re.search(
            r"^/scout\s+register\s+([A-Za-z0-9_-]{3,32})(?:\s+(.+))?$",
            text,
            flags=re.IGNORECASE,
        )
        mention_scout_register = re.search(
            r"@(alpha|control)\s+scout\s+register\s+([A-Za-z0-9_-]{3,32})(?:\s+(.+))?$",
            text,
            flags=re.IGNORECASE,
        )
        if slash_scout_register or mention_scout_register:
            if slash_scout_register:
                username = str(slash_scout_register.group(1) or "").strip()
                display_name = str(slash_scout_register.group(2) or "").strip()
            else:
                username = str(mention_scout_register.group(2) or "").strip()
                display_name = str(mention_scout_register.group(3) or "").strip()

            payload = json.dumps(
                {
                    "username": username,
                    "display_name": display_name or "Sapphire Scout",
                    "bio": "Least-privilege scout for public collaboration. No secrets, no trading actions.",
                },
                separators=(",", ":"),
            )
            await self.send_message(
                (
                    f"🛰️ Scout register request queued for `@{username}`.\n"
                    "Expected outcome: scout identity is created/updated with least-privilege defaults.\n"
                    "Next update: registration result will include verification or retry guidance."
                ),
                priority=NotificationPriority.HIGH,
            )
            await self._dispatch_callback("CONTROL", payload, "SCOUT_REGISTER", 0.0)
            return

        slash_scout_publish = re.search(
            r"^/scout\s+publish\s+(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        mention_scout_publish = re.search(
            r"@(alpha|control)\s+scout\s+publish\s+(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if slash_scout_publish or mention_scout_publish:
            raw_note = (
                str(slash_scout_publish.group(1) or "").strip()
                if slash_scout_publish
                else str(mention_scout_publish.group(2) or "").strip()
            )
            topic_id = ""
            body = raw_note
            topic_match = re.search(
                r"^topic(?:=|:)\s*(TOPIC-[0-9]{5})\s+(.+)$",
                raw_note,
                flags=re.IGNORECASE,
            )
            if topic_match:
                topic_id = str(topic_match.group(1) or "").strip().upper()
                body = str(topic_match.group(2) or "").strip()

            if not body:
                await self.send_message(
                    "❌ Scout publish requires note text.",
                    priority=NotificationPriority.HIGH,
                )
                return

            payload = json.dumps(
                {
                    "topic_id": topic_id,
                    "body": body,
                    "author": "SAPPHIRE_SCOUT",
                    "kind": "note",
                    "lane": "external",
                    "tags": ["scout", "external"],
                },
                separators=(",", ":"),
            )
            await self.send_message(
                (
                    "🛰️ Scout publish request queued.\n"
                    "Expected outcome: sanitized note is posted externally or retained locally with explicit reason.\n"
                    "Benefit: keeps external collaboration auditable without exposing sensitive data."
                ),
                priority=NotificationPriority.HIGH,
            )
            await self._dispatch_callback("CONTROL", payload, "SCOUT_PUBLISH", 0.0)
            return

        # VirusTotal security commands
        slash_security_cmd = re.search(
            r"^/security\s+(status|scan)(?:\s+([A-Za-z0-9._-]+|all))?(?:\s+(upload|no-upload))?$",
            text,
            flags=re.IGNORECASE,
        )
        mention_security_cmd = re.search(
            r"@(alpha|control)\s+security\s+(status|scan)(?:\s+([A-Za-z0-9._-]+|all))?(?:\s+(upload|no-upload))?$",
            text,
            flags=re.IGNORECASE,
        )
        if slash_security_cmd or mention_security_cmd:
            if slash_security_cmd:
                command = str(slash_security_cmd.group(1) or "").strip().lower()
                skill = str(slash_security_cmd.group(2) or "").strip()
                upload_token = str(slash_security_cmd.group(3) or "").strip().lower()
            else:
                command = str(mention_security_cmd.group(2) or "").strip().lower()
                skill = str(mention_security_cmd.group(3) or "").strip()
                upload_token = str(mention_security_cmd.group(4) or "").strip().lower()

            if command == "status":
                await self.send_message(
                    (
                        "🛡️ VirusTotal security status request queued.\n"
                        "Expected outcome: return scanner availability, policy mode, and latest scan result.\n"
                        "Benefit: confirms skill-ingestion risk posture before autonomous updates."
                    ),
                    priority=NotificationPriority.HIGH,
                )
                await self._dispatch_callback("CONTROL", "ALL", "SECURITY_STATUS", 0.0)
                return

            upload_if_missing = upload_token == "upload"
            payload = json.dumps(
                {
                    "skill": skill or "all",
                    "upload_if_missing": upload_if_missing,
                },
                separators=(",", ":"),
            )
            await self.send_message(
                (
                    "🛡️ VirusTotal scan request queued.\n"
                    f"Scope: `{skill or 'all'}` | upload-on-miss: `{'YES' if upload_if_missing else 'NO'}`\n"
                    "Expected outcome: skill verdict(s) with policy decision and report linkage.\n"
                    "Benefit: blocks risky skill bundles before they impact autonomy."
                ),
                priority=NotificationPriority.HIGH,
            )
            await self._dispatch_callback("CONTROL", payload, "SECURITY_SCAN", 0.0)
            return

        # Owner steering command
        steer_match = re.search(
            r"^/(steer|directive|note|answer|reply|respond)\s+(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        mention_steer_match = re.search(
            r"@(alpha|control)\s+(steer|directive|note|answer|reply|respond)\s+(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if steer_match or mention_steer_match:
            if steer_match:
                intent = str(steer_match.group(1) or "").strip().lower()
                directive = str(steer_match.group(2) or "").strip()
            else:
                intent = str(mention_steer_match.group(2) or "").strip().lower()
                directive = str(mention_steer_match.group(3) or "").strip()
            if len(directive) > 500:
                directive = directive[:500]
            response_ack = (
                (
                    "💓 Heartbeat response captured and queued.\n"
                    "Expected outcome: next autonomy cycle uses your response as steering context.\n"
                    "Benefit: strategy stays aligned with your latest direction."
                )
                if intent in {"answer", "reply", "respond"}
                else (
                    "🧠 Owner directive captured and queued.\n"
                    "Expected outcome: directive appears in focus snapshots and autonomy dispatch context.\n"
                    "Benefit: reduces drift between system behavior and owner intent."
                )
            )
            await self.send_message(
                response_ack,
                priority=NotificationPriority.HIGH,
            )
            await self._dispatch_callback("CONTROL", directive, "OWNER_STEER", 0.0)
            return

        # Session decision commands
        slash_bulk_approve_match = re.search(
            r"^/approve(?:[_-]?all|\s+all)(?:\s+(.+))?$",
            text,
            flags=re.IGNORECASE,
        )
        mention_bulk_approve_match = re.search(
            r"@(alpha|control)\s+approve(?:[_-]?all|\s+all)(?:\s+(.+))?$",
            text,
            flags=re.IGNORECASE,
        )
        if slash_bulk_approve_match or mention_bulk_approve_match:
            if slash_bulk_approve_match:
                note = str(slash_bulk_approve_match.group(1) or "").strip()
            else:
                note = str(mention_bulk_approve_match.group(2) or "").strip()
            if len(note) > 400:
                note = note[:400]
            payload = json.dumps({"note": note}, separators=(",", ":"))
            await self.send_message(
                (
                    "✅ Bulk approval request queued.\n"
                    "Expected outcome: all pending autonomy sessions move to APPROVE and dispatch.\n"
                    "Next update: you will receive a summary with approved count and failures (if any)."
                ),
                priority=NotificationPriority.HIGH,
            )
            await self._dispatch_callback("CONTROL", payload, "APPROVE_ALL_SESSIONS", 0.0)
            return

        slash_session_decision_match = re.search(
            r"^/(approve|reject)(?:\s+([A-Za-z0-9:._-]+|latest))?(?:\s+(.+))?$",
            text,
            flags=re.IGNORECASE,
        )
        mention_session_decision_match = re.search(
            r"@(alpha|control)\s+(approve|reject)(?:\s+([A-Za-z0-9:._-]+|latest))?(?:\s+(.+))?$",
            text,
            flags=re.IGNORECASE,
        )
        if slash_session_decision_match or mention_session_decision_match:
            if slash_session_decision_match:
                raw_action = str(slash_session_decision_match.group(1) or "").strip().lower()
                session_key = str(slash_session_decision_match.group(2) or "").strip()
                note = str(slash_session_decision_match.group(3) or "").strip()
            else:
                raw_action = str(mention_session_decision_match.group(2) or "").strip().lower()
                session_key = str(mention_session_decision_match.group(3) or "").strip()
                note = str(mention_session_decision_match.group(4) or "").strip()

            if len(note) > 400:
                note = note[:400]

            decision_payload = json.dumps(
                {"session_key": session_key, "note": note},
                separators=(",", ":"),
            )
            decision_action = "APPROVE_SESSION" if raw_action == "approve" else "REJECT_SESSION"
            decision_label = "APPROVE" if raw_action == "approve" else "REJECT"

            await self.send_message(
                (
                    f"🗳️ Session decision queued: `{decision_label}` `{session_key or 'latest'}`.\n"
                    "Expected outcome: session decision is recorded and dispatched to OpenClaw.\n"
                    "Next update: dispatch confirmation includes session key and status."
                ),
                priority=NotificationPriority.HIGH,
            )
            await self._dispatch_callback("CONTROL", decision_payload, decision_action, 0.0)
            return

        # Trading execution mode commands
        slash_trade_mode_match = re.search(
            r"^/(trade|execution|tv)\s+(on|off)(?:\s+([\d.]+))?$",
            text,
            flags=re.IGNORECASE,
        )
        mention_trade_mode_match = re.search(
            r"@(alpha|control)\s+(trade|execution|tv)\s+(on|off)(?:\s+([\d.]+))?$",
            text,
            flags=re.IGNORECASE,
        )
        if slash_trade_mode_match or mention_trade_mode_match:
            if slash_trade_mode_match:
                mode_text = str(slash_trade_mode_match.group(2) or "").strip().upper()
                qty_text = str(slash_trade_mode_match.group(3) or "").strip()
            else:
                mode_text = str(mention_trade_mode_match.group(3) or "").strip().upper()
                qty_text = str(mention_trade_mode_match.group(4) or "").strip()

            qty_value = 0.0
            if qty_text:
                try:
                    qty_value = float(qty_text)
                except ValueError:
                    await self.send_message(
                        "❌ Trade mode quantity must be numeric.",
                        priority=NotificationPriority.HIGH,
                    )
                    return

            enabled = mode_text == "ON"
            await self.send_message(
                (
                    f"🧭 TradingView signal mode change queued: `{'LIVE' if enabled else 'WORKBENCH_DRY-RUN'}`"
                    + (f" | qty `{qty_value}`" if qty_value > 0 else "")
                    + "\nExpected outcome: execution mode is updated with guardrails applied."
                    + "\nBenefit: clear separation between live dispatch and research-only signal flow."
                ),
                priority=NotificationPriority.HIGH,
            )
            await self._dispatch_callback("CONTROL", mode_text, "SET_TRADING_EXECUTION", qty_value)
            return

        # DEX execution stage command
        slash_stage_match = re.search(
            r"^/(stage|promotion_stage)\s+(paper|staged_live|staged|full_live|full|live)$",
            text,
            flags=re.IGNORECASE,
        )
        mention_stage_match = re.search(
            r"@(alpha|control)\s+(stage|promotion_stage)\s+(paper|staged_live|staged|full_live|full|live)$",
            text,
            flags=re.IGNORECASE,
        )
        if slash_stage_match or mention_stage_match:
            requested_stage = (
                str(slash_stage_match.group(2) or "").strip()
                if slash_stage_match
                else str(mention_stage_match.group(3) or "").strip()
            )
            await self.send_message(
                (
                    f"🚀 DEX stage update queued: `{requested_stage}`.\n"
                    "Expected outcome: stage gates and effective quantity are recalculated immediately.\n"
                    "Benefit: controlled progression from paper to staged/live execution."
                ),
                priority=NotificationPriority.HIGH,
            )
            await self._dispatch_callback("CONTROL", requested_stage, "SET_EXECUTION_STAGE", 0.0)
            return

        # Default TradingView quantity command
        slash_qty_match = re.search(
            r"^/(qty|quantity)\s+([\d.]+)$",
            text,
            flags=re.IGNORECASE,
        )
        mention_qty_match = re.search(
            r"@(alpha|control)\s+(qty|quantity)\s+([\d.]+)$",
            text,
            flags=re.IGNORECASE,
        )
        if slash_qty_match or mention_qty_match:
            raw_qty = slash_qty_match.group(2) if slash_qty_match else mention_qty_match.group(3)
            try:
                qty_value = float(raw_qty)
            except (TypeError, ValueError):
                await self.send_message(
                    "❌ Quantity must be numeric.",
                    priority=NotificationPriority.HIGH,
                )
                return
            if qty_value <= 0:
                await self.send_message(
                    "❌ Quantity must be greater than zero.",
                    priority=NotificationPriority.HIGH,
                )
                return

            await self.send_message(
                (
                    f"🧭 Default TradingView quantity update queued: `{qty_value}`.\n"
                    "Expected outcome: default signal quantity is updated with venue/rule caps enforced.\n"
                    "Benefit: lowers risk of under-notional failures or oversizing."
                ),
                priority=NotificationPriority.HIGH,
            )
            await self._dispatch_callback("CONTROL", "ALL", "SET_TRADINGVIEW_DEFAULT_QUANTITY", qty_value)
            return

        # Control commands: /status, /kill, etc.
        slash_control_match = re.search(
            r"^/(kill|halt|resume|status|heartbeat|promotion|gate|focus|autonomy)(?:\s+(\w+))?$",
            text_lower,
        )
        mention_control_match = re.search(
            r"@(alpha|all|control)\s+(kill|halt|resume|status|heartbeat|promotion|gate|focus|autonomy)(?:\s+(\w+))?$",
            text_lower,
        )
        if slash_control_match or mention_control_match:
            if slash_control_match:
                raw_action = slash_control_match.group(1)
                raw_target = slash_control_match.group(2) or "ALL"
            else:
                raw_action = mention_control_match.group(2)
                raw_target = mention_control_match.group(3) or "ALL"

            target = self._normalize_target(raw_target)
            mapped_action = self.CONTROL_ACTION_MAP[raw_action]

            if mapped_action != "CONTROL_FOCUS" and target not in self.allowed_targets:
                await self.send_message(
                    f"❌ Unsupported target `{target}`. Allowed: `{', '.join(sorted(self.allowed_targets))}`.",
                    priority=NotificationPriority.HIGH,
                )
                return

            await self.send_message(
                (
                    f"🧭 Control command queued: `{raw_action.upper()}` target `{target}`.\n"
                    "Expected outcome: control action executes against the active Sapphire runtime state.\n"
                    "Next update: command result is posted with status or remediation."
                ),
                priority=NotificationPriority.HIGH,
            )
            await self._dispatch_callback("CONTROL", target, mapped_action, 0.0)
            return

        # Allocation commands
        slash_allocation_match = re.search(
            r"^/(deallocate|allocate)\s+(\w+)(?:\s+([\d.]+))?$",
            text_lower,
        )
        mention_allocation_match = re.search(
            r"@(alpha|all|control)\s+(deallocate|allocate)\s+(\w+)(?:\s+([\d.]+))?$",
            text_lower,
        )
        if slash_allocation_match or mention_allocation_match:
            if slash_allocation_match:
                raw_action = slash_allocation_match.group(1)
                target = self._normalize_target(slash_allocation_match.group(2))
                raw_percent = slash_allocation_match.group(3)
            else:
                raw_action = mention_allocation_match.group(2)
                target = self._normalize_target(mention_allocation_match.group(3))
                raw_percent = mention_allocation_match.group(4)

            if target not in self.allowed_targets:
                await self.send_message(
                    f"❌ Unsupported target `{target}`. Allowed: `{', '.join(sorted(self.allowed_targets))}`.",
                    priority=NotificationPriority.HIGH,
                )
                return

            allocation = 0.0
            if raw_action == "allocate":
                try:
                    pct = float(raw_percent) if raw_percent is not None else 100.0
                except ValueError:
                    await self.send_message("❌ Allocation percent must be numeric.", priority=NotificationPriority.HIGH)
                    return
                allocation = max(0.0, min(1.0, pct / 100.0))

            await self.send_message(
                (
                    f"🧭 Allocation command queued: `{raw_action.upper()}` `{target}` -> `{allocation*100:.0f}%`.\n"
                    "Expected outcome: venue allocation state updates immediately.\n"
                    "Benefit: preserves execution continuity while rebalancing venue exposure."
                ),
                priority=NotificationPriority.HIGH,
            )
            await self._dispatch_callback("CONTROL", target, "SET_ALLOCATION", allocation)
            return

        # Manual trade override: @aster buy 1.0 btc
        cmd_match = re.search(r"@(\w+)\s+(buy|sell|close)\s+([\d.]+)\s+([A-Za-z0-9:_-]+)", text_lower)
        if cmd_match:
            platform = self._normalize_target(cmd_match.group(1))
            action = cmd_match.group(2).upper()
            try:
                quantity = float(cmd_match.group(3))
            except ValueError:
                await self.send_message("❌ Quantity must be numeric.", priority=NotificationPriority.HIGH)
                return
            symbol = cmd_match.group(4).upper()

            if quantity <= 0:
                await self.send_message("❌ Quantity must be greater than zero.", priority=NotificationPriority.HIGH)
                return

            if platform == "ALL":
                targets = sorted(self.allowed_trade_targets)
            elif platform in self.allowed_trade_targets:
                targets = [platform]
            else:
                await self.send_message(
                    f"❌ Unsupported venue `{platform}`. Allowed: `{', '.join(sorted(self.allowed_trade_targets))}`.",
                    priority=NotificationPriority.HIGH,
                )
                return

            await self.send_message(
                f"⚡ **MANUAL OVERRIDE**\nVenue(s): `{', '.join(targets)}`\nAction: `{action} {quantity} {symbol}`",
                priority=NotificationPriority.HIGH,
            )
            for target in targets:
                await self._dispatch_callback(target, symbol, action, quantity)
            return

        # AI assistant commands: @alpha recap|analyze|report
        ai_match = re.search(r"@(alpha|control)\s+(recap|analyze|report)", text_lower)
        if ai_match:
            action = ai_match.group(2).upper()
            await self._dispatch_callback("alpha", "AI", action, 0.0)
            return

        # Fallback: @alpha <free-text> is treated as steering context.
        fallback_steer = re.search(r"@(alpha|control)\s+(.+)$", text, flags=re.IGNORECASE)
        if fallback_steer:
            directive = fallback_steer.group(2).strip()
            if directive:
                if len(directive) > 500:
                    directive = directive[:500]
                await self.send_message(
                    (
                        "🧠 Owner note captured from @alpha and queued.\n"
                        "Expected outcome: note is injected into autonomy context for the next cycle.\n"
                        "Benefit: keeps long-form guidance synchronized with agent decisions."
                    ),
                    priority=NotificationPriority.HIGH,
                )
                await self._dispatch_callback("CONTROL", directive, "OWNER_STEER", 0.0)
