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
import time
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


class AgentPersona:
    """Represents an OpenClaw agent's conversational identity."""

    def __init__(self, name: str, emoji: str, role: str):
        self.name = name
        self.emoji = emoji
        self.role = role

    def speak(self, message: str) -> str:
        """Format a message as this agent speaking."""
        return f"{self.emoji} **{self.name}**: {message}"

    def __repr__(self) -> str:
        return f"AgentPersona({self.name})"


# The three OpenClaw agents
SAPPHIRE = AgentPersona("Sapphire", "💎", "trading & scout ops")
OBSIDIAN = AgentPersona("Obsidian", "🖤", "infrastructure & deployments")
EMERALD = AgentPersona("Emerald", "💚", "strategy & improvement")


class TelegramPlatformBot:
    """Telegram bot with conversational plain-text interaction.

    Messages from the system are attributed to one of three agent personas
    (SAPPHIRE 💎, OBSIDIAN 🖤, EMERALD 💚) so the chat feels like a
    conversation between the owner and their autonomous employees.
    The owner can respond in plain text — "yes", "looks good", "hold off",
    "approve that", etc. — and the bot routes intent correctly.
    Slash commands still work for power-users but are not required.
    """

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
        "media": "MEDIA_STATUS",
    }
    TARGET_ALIASES = {
        "LIGHT": "LIGHTER",
        "L2": "LIGHTER",
        "LT": "LIGHTER",
    }

    # ── Conversational intent patterns ──────────────────────────────
    # Affirmative: owner approves, agrees, or greenlights something
    _AFFIRM_PATTERNS = re.compile(
        r"^("
        r"y(es|eah|ep|up)?|sure|ok(ay)?|go\s*(ahead|for\s*it)?|approved?|"
        r"do\s*it|ship\s*it|lgtm|looks?\s*good|sounds?\s*good|fine|"
        r"green\s*light|confirmed?|absolutely|affirmative|proceed|"
        r"that\s*works?|perfect|love\s*it|let'?s\s*(go|do\s*(it|that))|"
        r"makes?\s*sense|agreed?|roger|100|bet|send\s*it|"
        r"thumbs?\s*up|all\s*good|nice|great|cool"
        r")[\s!.]*$",
        re.IGNORECASE,
    )
    # Negative: owner rejects, declines, or wants to hold off
    _REJECT_PATTERNS = re.compile(
        r"^("
        r"n(o|ah|ope)?|reject(ed)?|decline[d]?|deny|denied|"
        r"hold\s*(off|on)|wait|stop|don'?t|cancel|skip|pass|"
        r"not?\s*(now|yet|that|this)|negative|nah|nay|hard\s*pass|"
        r"back\s*off|stand\s*down|abort|scratch\s*that|never\s*mind"
        r")[\s!.]*$",
        re.IGNORECASE,
    )
    # Questioning: owner wants more info
    _QUESTION_PATTERNS = re.compile(
        r"^("
        r"(what|how|why|when|where|which|who|can\s+you|could\s+you|"
        r"tell\s+me|explain|show\s+me|what'?s|how'?s).*\??"
        r")$",
        re.IGNORECASE,
    )

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

        # ── Conversation context ──────────────────────────────────────
        # Tracks which agent last sent a message that expects a reply
        # so bare "yes"/"no" responses can be routed correctly.
        self._pending_agent_context: Optional[Dict[str, Any]] = None
        # Timestamp of last pending context to auto-expire stale ones.
        self._pending_context_ts: float = 0.0
        # Max age of pending context before it expires (5 minutes).
        self._pending_context_ttl: float = 300.0

        # Restrict command targets to explicit venues for focused operations.
        self.allowed_targets = self._parse_allowed_targets(
            os.getenv("TELEGRAM_ALLOWED_TARGETS", "ASTER,LIGHTER,ALL")
        )
        self.allowed_trade_targets = {target for target in self.allowed_targets if target != "ALL"}
        self._noise_suppression_enabled = os.getenv(
            "TELEGRAM_NOISE_SUPPRESSION_ENABLED",
            "true",
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._buffer_non_urgent_high = os.getenv(
            "TELEGRAM_BUFFER_NON_URGENT_HIGH",
            "true",
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._generic_suppress_seconds = max(
            15,
            int(os.getenv("TELEGRAM_GENERIC_SUPPRESS_SECONDS", "120")),
        )
        self._heartbeat_suppress_seconds = max(
            120,
            int(os.getenv("TELEGRAM_HEARTBEAT_SUPPRESS_SECONDS", "720")),
        )
        self._workspace_suppress_seconds = max(
            60,
            int(os.getenv("TELEGRAM_WORKSPACE_SUPPRESS_SECONDS", "600")),
        )
        self._flash_suppress_seconds = max(
            300,
            int(os.getenv("TELEGRAM_FLASH_SUPPRESS_SECONDS", "1800")),
        )
        self._last_signature_sent_at: Dict[str, float] = {}
        self._last_signature_suppressed: Dict[str, int] = {}
        self._signature_cache_max = max(
            100,
            int(os.getenv("TELEGRAM_SIGNATURE_CACHE_MAX", "800")),
        )

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

    @staticmethod
    def _is_urgent_message(message: str) -> bool:
        text = str(message or "").strip()
        lowered = text.lower()
        if text.startswith(("🚨", "🚨🚨", "🛑", "❌")):
            return True
        urgent_markers = (
            " kill switch",
            " dispatch failed",
            " handler_failed",
            " forbidden",
            " not ready",
            " blocked",
            " failed",
            " exception",
            " error",
        )
        return any(marker in lowered for marker in urgent_markers)

    def _signature_window_seconds(self, signature: str) -> int:
        key = str(signature or "").strip().lower()
        if key == "gemini_flash":
            return self._flash_suppress_seconds
        if key == "heartbeat":
            return self._heartbeat_suppress_seconds
        if key.startswith("workspace:"):
            return self._workspace_suppress_seconds
        return self._generic_suppress_seconds

    def _should_suppress(self, text: str, level: NotificationPriority) -> bool:
        if not self._noise_suppression_enabled:
            return False
        if level == NotificationPriority.CRITICAL:
            return False

        cleaned = self._clean_digest_text(text)
        summarized = self._summarize_digest_text(cleaned)
        signature = self._digest_signature(summarized)
        if not signature:
            return False

        now = time.time()
        window = float(self._signature_window_seconds(signature))
        last_sent_at = float(self._last_signature_sent_at.get(signature, 0.0))
        if last_sent_at and now - last_sent_at < window:
            self._last_signature_suppressed[signature] = int(
                self._last_signature_suppressed.get(signature, 0)
            ) + 1
            return True

        self._last_signature_sent_at[signature] = now
        self._last_signature_suppressed.pop(signature, None)
        if len(self._last_signature_sent_at) > self._signature_cache_max:
            oldest = sorted(self._last_signature_sent_at.items(), key=lambda item: float(item[1]))[
                : len(self._last_signature_sent_at) - self._signature_cache_max
            ]
            for old_key, _ in oldest:
                self._last_signature_sent_at.pop(old_key, None)
                self._last_signature_suppressed.pop(old_key, None)
        return False

    @staticmethod
    def _parse_media_publish_arg(media_arg: str) -> Dict[str, Any]:
        text = str(media_arg or "").strip()
        payload: Dict[str, Any] = {
            "topic": "",
            "targets": ["twitter", "substack"],
            "note": "",
        }
        if not text:
            return payload

        def _extract_segment(key: str, source: str) -> tuple[str, str]:
            pattern = rf"(?:^|\s){key}(?:=|:)\s*(.+?)(?=\s+(?:targets?|topic|note)(?:=|:)|$)"
            match = re.search(pattern, source, flags=re.IGNORECASE)
            if not match:
                return "", source
            value = str(match.group(1) or "").strip()
            updated = (source[: match.start()] + " " + source[match.end() :]).strip()
            return value, re.sub(r"\s+", " ", updated).strip()

        target_text, text = _extract_segment("targets?", text)
        topic_text, text = _extract_segment("topic", text)
        note_text, text = _extract_segment("note", text)

        if target_text:
            tokens = [chunk.strip().lower() for chunk in re.split(r"[,+/|]", target_text) if chunk.strip()]
            if len(tokens) == 1 and " " in tokens[0]:
                tokens = [chunk.strip().lower() for chunk in tokens[0].split(" ") if chunk.strip()]
            if tokens:
                payload["targets"] = tokens

        payload["topic"] = topic_text or text
        payload["note"] = note_text
        return payload

    @staticmethod
    def _parse_media_request_arg(media_arg: str) -> Dict[str, str]:
        text = str(media_arg or "").strip()
        if not text:
            return {"request_id": "latest", "note": ""}

        head, tail = text, ""
        if " " in text:
            head, tail = text.split(" ", 1)
            head = head.strip()
            tail = tail.strip()

        if re.fullmatch(r"(latest|[A-Za-z0-9:._-]+)", head, flags=re.IGNORECASE):
            request_id = head
            note = tail
        else:
            request_id = "latest"
            note = text
        return {"request_id": request_id or "latest", "note": note}

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

        if self._should_suppress(full_message, level):
            return

        non_urgent_high = (
            level == NotificationPriority.HIGH
            and self._buffer_non_urgent_high
            and not self._is_urgent_message(full_message)
        )
        if level in {NotificationPriority.LOW, NotificationPriority.MEDIUM} or non_urgent_high:
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
            "💎 **SAPPHIRE COMMAND DECK**\n"
            f"Active venues: `{targets}`\n\n"
            "**Just talk to us in plain text.** Your three agents are:\n"
            "💎 **Sapphire** — trading ops, scout, execution\n"
            "🖤 **Obsidian** — infra, deployments, autonomy\n"
            "💚 **Emerald** — strategy, optimization, improvement\n\n"
            "**Examples — just type normally:**\n"
            "• `status` — get a status update\n"
            "• `yes` / `no` / `looks good` — respond to pending requests\n"
            "• `approve all` — greenlight all pending sessions\n"
            "• `kill` / `resume` — emergency stop or restart trading\n"
            "• `scout publish <message>` — post to Moltbook\n"
            "• `trade on 0.03` — enable live trading\n"
            "• `focus on reducing drawdown` — steer strategy direction\n"
            "• `lighter buy 0.5 ETH` — manual trade override\n\n"
            "Slash commands still work (`/status`, `/kill`, etc.) but aren't required.\n"
            "When an agent asks you something, just reply — we'll figure out the rest."
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

    @staticmethod
    def _strip_control_mention(text: str) -> str:
        value = str(text or "").strip()
        return re.sub(r"^@(alpha|control)\s+", "", value, flags=re.IGNORECASE).strip()

    # ── Conversation context management ────────────────────────────
    def _set_pending_context(
        self,
        agent: "AgentPersona",
        action: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record that an agent just asked the owner something."""
        self._pending_agent_context = {
            "agent": agent,
            "action": action,
            "metadata": metadata or {},
        }
        self._pending_context_ts = time.time()

    def _consume_pending_context(self) -> Optional[Dict[str, Any]]:
        """Return and clear the pending context if it hasn't expired."""
        if not self._pending_agent_context:
            return None
        age = time.time() - self._pending_context_ts
        if age > self._pending_context_ttl:
            self._pending_agent_context = None
            return None
        ctx = self._pending_agent_context
        self._pending_agent_context = None
        return ctx

    def _classify_intent(self, text: str) -> str:
        """Classify a short plain-text message as affirm/reject/question/other."""
        cleaned = text.strip()
        if self._AFFIRM_PATTERNS.match(cleaned):
            return "affirm"
        if self._REJECT_PATTERNS.match(cleaned):
            return "reject"
        if self._QUESTION_PATTERNS.match(cleaned):
            return "question"
        return "other"

    def _route_agent(self, text: str) -> "AgentPersona":
        """Pick which agent should respond based on message content."""
        lowered = text.lower()
        # Explicit agent addressing
        if re.search(r"\b(obsidian|infra|deploy|cloud|server|docker|gcloud)\b", lowered):
            return OBSIDIAN
        if re.search(r"\b(emerald|strategy|improve|optimize|perf|review|masterplan)\b", lowered):
            return EMERALD
        # Scout, trade, and default go to Sapphire
        return SAPPHIRE

    async def send_as(
        self,
        agent: "AgentPersona",
        message: str,
        priority: str = "high",
        expects_reply: bool = False,
        pending_action: str = "",
        pending_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send a message attributed to a specific agent persona."""
        await self.send_message(
            agent.speak(message),
            priority=priority,
        )
        if expects_reply and pending_action:
            self._set_pending_context(agent, pending_action, pending_metadata)

    def _parse_plain_text_command(self, text: str) -> Optional[Dict[str, Any]]:
        raw = self._strip_control_mention(text)
        normalized = raw.lower().strip()
        if not normalized:
            return None
        if normalized.startswith("/"):
            return None

        if re.search(r"\b(scout\s+status)\b", normalized):
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "SCOUT_STATUS",
                "quantity": 0.0,
                "agent": SAPPHIRE,
                "ack": "Checking on our scout — one sec.",
            }

        scout_register = re.search(
            r"\bscout\s+register\s+([A-Za-z0-9_-]{3,32})(?:\s+(.+))?$",
            raw,
            flags=re.IGNORECASE,
        )
        if scout_register:
            payload = json.dumps(
                {
                    "username": str(scout_register.group(1) or "").strip(),
                    "display_name": str(scout_register.group(2) or "").strip() or "Sapphire Scout",
                    "bio": "Least-privilege scout for public collaboration. No secrets, no trading actions.",
                },
                separators=(",", ":"),
            )
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "SCOUT_REGISTER",
                "quantity": 0.0,
                "agent": SAPPHIRE,
                "ack": "Registering our scout identity now.",
            }

        scout_publish = re.search(
            r"\bscout\s+publish\s+(.+)$",
            raw,
            flags=re.IGNORECASE,
        )
        if scout_publish:
            publish_note = str(scout_publish.group(1) or "").strip()
            topic_id = ""
            post_id = ""

            topic_match = re.search(r"\btopic(?:=|:)\s*(TOPIC-[0-9]{5})\b", publish_note, flags=re.IGNORECASE)
            if topic_match:
                topic_id = str(topic_match.group(1) or "").strip().upper()
                publish_note = re.sub(
                    r"\btopic(?:=|:)\s*TOPIC-[0-9]{5}\b",
                    " ",
                    publish_note,
                    flags=re.IGNORECASE,
                )

            post_match = re.search(
                r"\bpost(?:=|:)\s*([A-Za-z0-9_\-]{3,80})\b",
                publish_note,
                flags=re.IGNORECASE,
            )
            if post_match:
                post_id = str(post_match.group(1) or "").strip()
                publish_note = re.sub(
                    r"\bpost(?:=|:)\s*[A-Za-z0-9_\-]{3,80}\b",
                    " ",
                    publish_note,
                    flags=re.IGNORECASE,
                )

            publish_note = re.sub(r"\s+", " ", publish_note).strip()
            payload = json.dumps(
                {
                    "topic_id": topic_id,
                    "post_id": post_id,
                    "body": publish_note,
                    "author": "SAPPHIRE_SCOUT",
                    "kind": "note",
                    "lane": "external",
                    "tags": ["scout", "external"],
                },
                separators=(",", ":"),
            )
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "SCOUT_PUBLISH",
                "quantity": 0.0,
                "agent": SAPPHIRE,
                "ack": (
                    f"On it — {'replying to post `' + post_id + '`' if post_id else 'publishing to Moltbook now'}."
                ),
            }

        if re.search(r"\b(what'?s\s+status|status)\b", normalized):
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "CONTROL_STATUS",
                "quantity": 0.0,
                "agent": SAPPHIRE,
                "ack": "Pulling up the current status for you.",
            }
        if "heartbeat" in normalized or normalized == "ping":
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "HEARTBEAT",
                "quantity": 0.0,
                "agent": SAPPHIRE,
                "ack": "Running a heartbeat check now.",
            }
        if "focus" in normalized:
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "CONTROL_FOCUS",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": "Here's where we're focused right now.",
            }
        if re.search(r"\b(autonomy|restart)\b", normalized):
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "AUTONOMY_CYCLE",
                "quantity": 0.0,
                "agent": OBSIDIAN,
                "ack": "Kicking off a fresh autonomy cycle now.",
            }
        if re.search(r"\b(kill|halt)\b", normalized):
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "HALT_TRADING",
                "quantity": 0.0,
                "agent": SAPPHIRE,
                "ack": "🛑 Hitting the kill switch — all trading halted immediately.",
            }
        if "resume" in normalized:
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "RESUME_TRADING",
                "quantity": 0.0,
                "agent": SAPPHIRE,
                "ack": "Resuming trading operations now.",
            }
        if "approve all" in normalized or "approve backlog" in normalized:
            note = re.sub(r"^.*approve(?:\s+all|\s+backlog)\s*", "", raw, flags=re.IGNORECASE).strip()
            payload = json.dumps({"note": note}, separators=(",", ":"))
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "APPROVE_ALL_SESSIONS",
                "quantity": 0.0,
                "agent": OBSIDIAN,
                "ack": "Got it — approving all pending sessions now.",
            }

        approve_match = re.search(
            r"\bapprove\s+([A-Za-z0-9:._-]+|latest)(?:\s+(.+))?$",
            raw,
            flags=re.IGNORECASE,
        )
        if approve_match:
            payload = json.dumps(
                {
                    "session_key": str(approve_match.group(1) or "").strip(),
                    "note": str(approve_match.group(2) or "").strip(),
                },
                separators=(",", ":"),
            )
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "APPROVE_SESSION",
                "quantity": 0.0,
                "agent": OBSIDIAN,
                "ack": "Approved — dispatching that session now.",
            }

        reject_match = re.search(
            r"\breject\s+([A-Za-z0-9:._-]+|latest)(?:\s+(.+))?$",
            raw,
            flags=re.IGNORECASE,
        )
        if reject_match:
            payload = json.dumps(
                {
                    "session_key": str(reject_match.group(1) or "").strip(),
                    "note": str(reject_match.group(2) or "").strip(),
                },
                separators=(",", ":"),
            )
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "REJECT_SESSION",
                "quantity": 0.0,
                "agent": OBSIDIAN,
                "ack": "Understood — rejecting that session.",
            }

        trade_mode_match = re.search(
            r"\b(?:trade|tradingview|tv)\s+(on|off)(?:\s+([0-9]*\.?[0-9]+))?",
            normalized,
        )
        if trade_mode_match:
            mode = str(trade_mode_match.group(1) or "").strip().upper()
            qty_text = str(trade_mode_match.group(2) or "").strip()
            qty = float(qty_text) if qty_text else 0.0
            return {
                "platform": "CONTROL",
                "symbol": mode,
                "action": "SET_TRADING_EXECUTION",
                "quantity": qty,
                "agent": SAPPHIRE,
                "ack": f"Switching TradingView to `{'LIVE' if mode == 'ON' else 'DRY-RUN'}` mode.",
            }

        stage_match = re.search(
            r"\b(?:stage|promotion)\s+(paper|staged_live|staged|full_live|full|live)\b",
            normalized,
        )
        if stage_match:
            return {
                "platform": "CONTROL",
                "symbol": str(stage_match.group(1) or "").strip(),
                "action": "SET_EXECUTION_STAGE",
                "quantity": 0.0,
                "agent": SAPPHIRE,
                "ack": f"Moving execution stage to `{str(stage_match.group(1) or '').strip()}`.",
            }

        allocate_match = re.search(
            r"\ballocate\s+(all|aster|lighter|light)\s+([0-9]{1,3}(?:\.[0-9]+)?)\b",
            normalized,
        )
        if allocate_match:
            target = self._normalize_target(str(allocate_match.group(1) or "").strip())
            percent = float(str(allocate_match.group(2) or "100").strip())
            return {
                "platform": "CONTROL",
                "symbol": target,
                "action": "SET_ALLOCATION",
                "quantity": max(0.0, min(1.0, percent / 100.0)),
                "agent": SAPPHIRE,
                "ack": f"Setting `{target}` allocation to `{percent:.0f}%`.",
            }

        deallocate_match = re.search(r"\b(deallocate|pause)\s+(all|aster|lighter|light)\b", normalized)
        if deallocate_match:
            target = self._normalize_target(str(deallocate_match.group(2) or "").strip())
            return {
                "platform": "CONTROL",
                "symbol": target,
                "action": "SET_ALLOCATION",
                "quantity": 0.0,
                "agent": SAPPHIRE,
                "ack": f"Pausing `{target}` — allocation set to 0%.",
            }

        manual_trade = re.search(
            r"\b(aster|lighter|all)\s+(buy|sell|close)\s+([0-9]*\.?[0-9]+)\s+([A-Za-z0-9:_-]+)\b",
            normalized,
        )
        if manual_trade:
            platform = self._normalize_target(str(manual_trade.group(1) or "").strip())
            action = str(manual_trade.group(2) or "").strip().upper()
            qty = float(str(manual_trade.group(3) or "0").strip())
            symbol = str(manual_trade.group(4) or "").strip().upper()
            return {
                "platform": platform,
                "symbol": symbol,
                "action": action,
                "quantity": qty,
                "agent": SAPPHIRE,
                "ack": f"⚡ Executing: `{action}` `{qty}` `{symbol}` on `{platform}`.",
            }

        return None

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

        # Restart — dispatch as a control command
        if re.search(r"^/restart\b", text_lower):
            await self.send_as(OBSIDIAN, "Restarting — kicking off a fresh autonomy cycle.")
            await self._dispatch_callback("CONTROL", "ALL", "AUTONOMY_CYCLE", 0.0)
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
            await self.send_as(SAPPHIRE, "Checking scout status — one sec.")
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
            await self.send_as(SAPPHIRE, f"Registering scout as `@{username}` — stand by.")
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
            post_id = ""
            body = raw_note
            topic_match = re.search(r"\btopic(?:=|:)\s*(TOPIC-[0-9]{5})\b", raw_note, flags=re.IGNORECASE)
            if topic_match:
                topic_id = str(topic_match.group(1) or "").strip().upper()
                body = re.sub(
                    r"\btopic(?:=|:)\s*TOPIC-[0-9]{5}\b",
                    " ",
                    body,
                    flags=re.IGNORECASE,
                )

            post_match = re.search(
                r"\bpost(?:=|:)\s*([A-Za-z0-9_\-]{3,80})\b",
                body,
                flags=re.IGNORECASE,
            )
            if post_match:
                post_id = str(post_match.group(1) or "").strip()
                body = re.sub(
                    r"\bpost(?:=|:)\s*[A-Za-z0-9_\-]{3,80}\b",
                    " ",
                    body,
                    flags=re.IGNORECASE,
                )

            body = re.sub(r"\s+", " ", body).strip()

            if not body:
                await self.send_message(
                    "❌ Scout publish requires note text.",
                    priority=NotificationPriority.HIGH,
                )
                return

            payload = json.dumps(
                {
                    "topic_id": topic_id,
                    "post_id": post_id,
                    "body": body,
                    "author": "SAPPHIRE_SCOUT",
                    "kind": "note",
                    "lane": "external",
                    "tags": ["scout", "external"],
                },
                separators=(",", ":"),
            )
            target_note = f" → replying to `{post_id}`" if post_id else ""
            await self.send_as(SAPPHIRE, f"Publishing scout note{target_note}.")
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
                await self.send_as(OBSIDIAN, "Pulling VirusTotal security status.")
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
            upload_label = " (will upload if missing)" if upload_if_missing else ""
            await self.send_as(OBSIDIAN, f"Scanning `{skill or 'all'}` with VirusTotal{upload_label}.")
            await self._dispatch_callback("CONTROL", payload, "SECURITY_SCAN", 0.0)
            return

        # Media workflow commands (Twitter + Substack automation plane)
        slash_media_cmd = re.search(
            r"^/media\s+(status|mode|draft|publish|queue|approve|reject)(?:\s+(.+))?$",
            text,
            flags=re.IGNORECASE,
        )
        mention_media_cmd = re.search(
            r"@(alpha|control)\s+media\s+(status|mode|draft|publish|queue|approve|reject)(?:\s+(.+))?$",
            text,
            flags=re.IGNORECASE,
        )
        if slash_media_cmd or mention_media_cmd:
            if slash_media_cmd:
                media_command = str(slash_media_cmd.group(1) or "").strip().lower()
                media_arg = str(slash_media_cmd.group(2) or "").strip()
            else:
                media_command = str(mention_media_cmd.group(2) or "").strip().lower()
                media_arg = str(mention_media_cmd.group(3) or "").strip()

            if media_command == "status":
                await self.send_as(EMERALD, "Checking media pipeline status.")
                await self._dispatch_callback("CONTROL", "ALL", "MEDIA_STATUS", 0.0)
                return

            if media_command == "queue":
                await self.send_as(EMERALD, "Pulling up the media queue.")
                await self._dispatch_callback("CONTROL", "ALL", "MEDIA_QUEUE_STATUS", 0.0)
                return

            if media_command == "mode":
                if not media_arg:
                    await self.send_message(
                        "❌ Media mode requires a value: `draft_only`, `owner_approval`, or `auto_post`.",
                        priority=NotificationPriority.HIGH,
                    )
                    return

                payload = json.dumps({"mode": media_arg}, separators=(",", ":"))
                await self.send_as(EMERALD, f"Switching media mode to `{media_arg}`.")
                await self._dispatch_callback("CONTROL", payload, "MEDIA_SET_MODE", 0.0)
                return

            if media_command == "publish":
                payload_data = self._parse_media_publish_arg(media_arg)
                payload = json.dumps(payload_data, separators=(",", ":"))
                targets = ", ".join(payload_data.get("targets", [])) or "twitter, substack"
                topic = str(payload_data.get("topic", "")).strip() or "latest draft"
                await self.send_as(EMERALD, f"Publishing `{topic}` → `{targets}`.")
                await self._dispatch_callback("CONTROL", payload, "MEDIA_PUBLISH", 0.0)
                return

            if media_command in {"approve", "reject"}:
                parsed = self._parse_media_request_arg(media_arg)
                payload = json.dumps(parsed, separators=(",", ":"))
                request_id = parsed.get("request_id", "latest") or "latest"
                decision = "approve" if media_command == "approve" else "reject"
                ack = (
                    f"Approved media request `{request_id}` — queuing for publish."
                    if decision == "approve"
                    else f"Rejected media request `{request_id}`."
                )
                await self.send_as(EMERALD, ack)
                action = "MEDIA_APPROVE" if media_command == "approve" else "MEDIA_REJECT"
                await self._dispatch_callback("CONTROL", payload, action, 0.0)
                return

            topic = media_arg or "weekly research update"
            payload = json.dumps({"topic": topic}, separators=(",", ":"))
            await self.send_as(EMERALD, f"Drafting content on `{topic}`.")
            await self._dispatch_callback("CONTROL", payload, "MEDIA_DRAFT", 0.0)
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
            agent = self._route_agent(directive)
            if intent in {"answer", "reply", "respond"}:
                await self.send_as(agent, f"Got your reply — feeding it into our next cycle.")
            else:
                await self.send_as(agent, "Noted — updating our direction accordingly.")
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
            await self.send_as(OBSIDIAN, "Approving all pending sessions now.")
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

            ack = (
                f"Approved `{session_key or 'latest'}` — dispatching now."
                if raw_action == "approve"
                else f"Rejected `{session_key or 'latest'}`."
            )
            await self.send_as(OBSIDIAN, ack)
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
            mode_label = "LIVE" if enabled else "DRY-RUN"
            qty_note = f" at qty `{qty_value}`" if qty_value > 0 else ""
            await self.send_as(SAPPHIRE, f"Switching TradingView to `{mode_label}`{qty_note}.")
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
            await self.send_as(SAPPHIRE, f"Moving execution stage to `{requested_stage}`.")
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

            await self.send_as(SAPPHIRE, f"Setting default trade quantity to `{qty_value}`.")
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

            # Route to the right agent persona
            _control_agent_map = {
                "HALT_TRADING": SAPPHIRE,
                "RESUME_TRADING": SAPPHIRE,
                "CONTROL_STATUS": SAPPHIRE,
                "HEARTBEAT": SAPPHIRE,
                "PROMOTION_GATE": EMERALD,
                "CONTROL_FOCUS": EMERALD,
                "AUTONOMY_CYCLE": OBSIDIAN,
                "SECURITY_STATUS": OBSIDIAN,
                "MEDIA_STATUS": SAPPHIRE,
            }
            agent = _control_agent_map.get(mapped_action, SAPPHIRE)
            _control_ack_map = {
                "HALT_TRADING": "🛑 Trading halted immediately.",
                "RESUME_TRADING": "Resuming trading operations.",
                "CONTROL_STATUS": "Pulling up status now.",
                "HEARTBEAT": "Running heartbeat check.",
                "PROMOTION_GATE": "Checking promotion gate status.",
                "CONTROL_FOCUS": "Here's our current focus.",
                "AUTONOMY_CYCLE": "Kicking off an autonomy cycle.",
                "SECURITY_STATUS": "Running security check.",
                "MEDIA_STATUS": "Checking media pipeline status.",
            }
            ack = _control_ack_map.get(mapped_action, f"Running `{raw_action}`.")
            if target != "ALL":
                ack += f" (target: `{target}`)"
            await self.send_as(
                agent, ack,
            )
            await self._dispatch_callback("CONTROL", target, mapped_action, 0.0)
            return

        # Prices command: /prices
        if re.search(r"^/prices?\b", text_lower):
            await self.send_as(SAPPHIRE, "Fetching live prices across all venues.")
            await self._dispatch_callback("CONTROL", "ALL", "MARKET_PRICES", 0.0)
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

            ack = (
                f"Setting `{target}` allocation to `{allocation*100:.0f}%`."
                if raw_action == "allocate"
                else f"Pausing `{target}` — allocation set to 0%."
            )
            await self.send_as(SAPPHIRE, ack)
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

            await self.send_as(
                SAPPHIRE,
                f"Manual override — `{action} {quantity} {symbol}` on `{', '.join(targets)}`.",
            )
            for target in targets:
                await self._dispatch_callback(target, symbol, action, quantity)
            return

        # AI assistant commands: @alpha recap|analyze|report
        ai_match = re.search(r"@(alpha|control)\s+(recap|analyze|report)", text_lower)
        if ai_match:
            action = ai_match.group(2).upper()
            ai_ack_map = {
                "RECAP": "Pulling together a recap now.",
                "ANALYZE": "Running analysis — give me a moment.",
                "REPORT": "Generating a report for you.",
            }
            await self.send_as(EMERALD, ai_ack_map.get(action, f"On it — running `{action}`."))
            await self._dispatch_callback("alpha", "AI", action, 0.0)
            return

        # ── Conversational reply handling ──────────────────────────
        # Short messages like "yes", "no", "looks good", "hold off"
        # are routed to the agent that last asked a question.
        directive = self._strip_control_mention(text)
        intent = self._classify_intent(directive)

        if intent in {"affirm", "reject"} and self._pending_agent_context:
            ctx = self._consume_pending_context()
            if ctx:
                agent = ctx["agent"]
                action = ctx["action"]
                metadata = ctx.get("metadata", {})
                if intent == "affirm":
                    note = directive if len(directive) > 3 else ""
                    if action == "APPROVE_SESSION":
                        payload = json.dumps(
                            {"session_key": metadata.get("session_key", "latest"), "note": note},
                            separators=(",", ":"),
                        )
                        await self.send_as(agent, "Got it — approved.")
                        await self._dispatch_callback("CONTROL", payload, "APPROVE_SESSION", 0.0)
                    elif action == "APPROVE_ALL_SESSIONS":
                        payload = json.dumps({"note": note}, separators=(",", ":"))
                        await self.send_as(agent, "Approving all pending sessions.")
                        await self._dispatch_callback("CONTROL", payload, "APPROVE_ALL_SESSIONS", 0.0)
                    else:
                        await self.send_as(agent, f"Confirmed — proceeding with `{action}`.")
                        await self._dispatch_callback(
                            "CONTROL",
                            json.dumps({"note": note}, separators=(",", ":")),
                            action,
                            0.0,
                        )
                else:
                    if action in {"APPROVE_SESSION", "APPROVE_ALL_SESSIONS"}:
                        payload = json.dumps(
                            {"session_key": metadata.get("session_key", "latest"), "note": directive},
                            separators=(",", ":"),
                        )
                        await self.send_as(agent, "Understood — holding off on that.")
                        await self._dispatch_callback("CONTROL", payload, "REJECT_SESSION", 0.0)
                    else:
                        await self.send_as(agent, "Okay, standing down on that.")
                return

        # ── Structured plain-text command parsing ─────────────────
        parsed_plain = self._parse_plain_text_command(text)
        if parsed_plain:
            agent = parsed_plain.get("agent", SAPPHIRE)
            ack = str(parsed_plain.get("ack") or "On it.")
            await self.send_as(agent, ack)
            await self._dispatch_callback(
                str(parsed_plain.get("platform") or "CONTROL"),
                str(parsed_plain.get("symbol") or "ALL"),
                str(parsed_plain.get("action") or "OWNER_STEER"),
                float(parsed_plain.get("quantity") or 0.0),
            )
            return

        # ── Freeform steering directive ───────────────────────────
        if directive:
            if len(directive) > 500:
                directive = directive[:500]
            agent = self._route_agent(directive)
            await self.send_as(
                agent,
                "Noted — I'll factor that into our next cycle.",
            )
            await self._dispatch_callback("CONTROL", directive, "OWNER_STEER", 0.0)
