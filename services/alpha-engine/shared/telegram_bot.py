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


def _sanitize_markdown(text: str) -> str:
    """Escape characters that break Telegram legacy Markdown parsing.

    Telegram's legacy Markdown treats ``_`` as italic, ``*`` as bold, and
    backtick as inline-code.  We only need to worry about *unmatched*
    delimiters inside running text.  Dollar signs, parentheses, dots, etc.
    are fine in legacy mode — the failures we've seen come from unmatched
    underscores inside role descriptions and price strings.

    Strategy: replace lone underscores that aren't part of a matched
    ``_italic_`` pair with the Unicode full-width low line (＿) which
    renders identically but doesn't trigger the parser.
    """
    # If the count of underscores is odd, we have an unmatched delimiter.
    if text.count("_") % 2 != 0:
        # Replace all underscores — they can't all be valid italic markers
        # if the count is odd.
        text = text.replace("_", "＿")
    return text


class AgentPersona:
    """Represents an OpenClaw agent's conversational identity."""

    def __init__(self, name: str, emoji: str, role: str):
        self.name = name
        self.emoji = emoji
        self.role = role

    def speak(self, message: str) -> str:
        """Format a message as this agent speaking."""
        safe = _sanitize_markdown(message)
        return f"{self.emoji} *{self.name}*: {safe}"

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

        # ── Agent Activity Feed ────────────────────────────────────────
        # Collects agent actions into periodic non-noisy digest summaries.
        # Each entry: {"agent": str, "category": str, "detail": str, "ts": float}
        self._activity_feed: List[Dict[str, Any]] = []
        self._activity_feed_enabled = os.getenv(
            "TELEGRAM_ACTIVITY_FEED_ENABLED", "true"
        ).strip().lower() in {"1", "true", "yes", "on"}
        self._activity_feed_interval = max(
            60,
            int(os.getenv("TELEGRAM_ACTIVITY_FEED_SECONDS", "300")),
        )
        self._activity_feed_task: Optional[asyncio.Task[Any]] = None
        self._activity_feed_max = 200  # max buffered events before forced flush

        logger.info(
            "Initializing Telegram Bot | token={} chat={} allowed_targets={}",
            "set" if self.bot_token else "missing",
            "set" if self.chat_id else "missing",
            ",".join(sorted(self.allowed_targets)),
        )

    # ── Agent Activity Feed ───────────────────────────────────────────

    def record_activity(
        self,
        agent: "AgentPersona",
        category: str,
        detail: str,
    ) -> None:
        """Record an agent action for the periodic activity digest.

        Categories should be short slugs like: ``trade``, ``cognition``,
        ``memory``, ``portfolio``, ``market_data``, ``audit``, ``system``.
        """
        if not self._activity_feed_enabled:
            return
        self._activity_feed.append({
            "agent": agent.name,
            "emoji": agent.emoji,
            "category": str(category or "misc").strip().lower(),
            "detail": str(detail or "").strip()[:200],
            "ts": time.time(),
        })
        # Hard cap to prevent unbounded memory growth
        if len(self._activity_feed) > self._activity_feed_max:
            self._activity_feed = self._activity_feed[-self._activity_feed_max:]

    async def _activity_feed_loop(self) -> None:
        """Periodically flush the activity feed as a grouped digest."""
        while self.running:
            await asyncio.sleep(self._activity_feed_interval)
            await self._flush_activity_feed()

    async def _flush_activity_feed(self) -> None:
        """Build and send a grouped activity digest, then clear the buffer."""
        if not self._activity_feed:
            return

        events = list(self._activity_feed)
        self._activity_feed.clear()

        # Group by (agent, category) → list of details with counts
        groups: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        for evt in events:
            key = f"{evt['emoji']}:{evt['category']}"
            if key not in groups:
                groups[key] = {
                    "emoji": evt["emoji"],
                    "agent": evt["agent"],
                    "category": evt["category"],
                    "details": OrderedDict(),
                    "count": 0,
                }
            groups[key]["count"] += 1
            # Collapse identical details
            detail = evt["detail"]
            if detail in groups[key]["details"]:
                groups[key]["details"][detail] += 1
            else:
                groups[key]["details"][detail] = 1

        # Format the digest
        lines: List[str] = []
        for group in groups.values():
            emoji = group["emoji"]
            agent = group["agent"]
            cat = group["category"].replace("_", " ").title()
            count = group["count"]
            header = f"{emoji} *{agent}* — {cat}"
            if count > 1:
                header += f" ({count})"
            lines.append(header)
            # Show top 3 details for this group, collapsed
            sorted_details = sorted(
                group["details"].items(), key=lambda x: -x[1]
            )
            for detail, detail_count in sorted_details[:3]:
                suffix = f" _(x{detail_count})_" if detail_count > 1 else ""
                lines.append(f"  • {detail}{suffix}")
            remaining = len(sorted_details) - 3
            if remaining > 0:
                lines.append(f"  • _…and {remaining} more_")

        if not lines:
            return

        digest = "📊 *Agent Activity*\n" + "\n".join(lines)
        await self._dispatch_message(digest, allow_markdown=True)

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
        if self._activity_feed_task:
            self._activity_feed_task.cancel()
            self._activity_feed_task = None
        if self._session and not self._session.closed:
            await self._session.close()

    async def start(self):
        """Start buffer flush loop, activity feed, and long-poll listener."""
        self.running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        if self._activity_feed_enabled:
            self._activity_feed_task = asyncio.create_task(self._activity_feed_loop())
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

                    # Retry without markdown if formatting fails.
                    if resp.status == 400 and payload.get("parse_mode"):
                        payload.pop("parse_mode", None)
                        # Strip markdown formatting chars so the plain text reads cleanly.
                        raw = payload["text"]
                        raw = raw.replace("**", "").replace("__", "")
                        raw = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"\1", raw)
                        raw = re.sub(r"(?<!\w)_([^_]+)_(?!\w)", r"\1", raw)
                        payload["text"] = raw
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
            "**Forum commands:**\n"
            "• `forum top [category]` — top-scored topics\n"
            "• `forum vote TOPIC-XXXXX up|down` — vote on a topic\n"
            "• `forum agents` — agent personality profiles\n"
            "• `forum thread TOPIC-XXXXX` — threaded replies\n"
            "• `/forum post Title | Body category:trade_idea` — create topic\n"
            "• `forum approvals` — pending approval workflows\n\n"
            "**Reputation commands:**\n"
            "• `rep leaderboard` — top bots by composite score\n"
            "• `rep info <BOT_ID>` — reputation details for a bot\n"
            "• `rep count` — census of registered bots\n"
            "• `/rep ban <BOT_ID> [reason]` — permanently ban a bot\n"
            "• `/rep penalize <BOT_ID> [reason]` — penalize a bot\n\n"
            "**Swarm commands:**\n"
            "• `swarm aggregate <SYMBOL>` — consensus signal for a symbol\n"
            "• `swarm ideas [SYMBOL]` — list open trade ideas\n"
            "• `swarm stats` — aggregation statistics\n\n"
            "**Learning commands:**\n"
            "• `learn report` — full collaborative learning report\n"
            "• `learn summary` — quick learning stats\n"
            "• `learn bias <SYMBOL> [LONG|SHORT] [timeframe]` — bias & adaptive confidence\n\n"
            "**Outreach commands:**\n"
            "• `outreach post [template] [SYMBOL]` — compose & send outreach\n"
            "• `outreach stats` — outreach dispatch statistics\n"
            "• `outreach templates` — list available templates\n\n"
            "**Task commands:**\n"
            "• `task create <title>` — create a new task\n"
            "• `task list [agent|status]` — list tasks with optional filter\n"
            "• `task update <TASK-ID> <status>` — update task status\n"
            "• `task report` — progress report\n"
            "• `task summary` — quick summary\n"
            "• `task agent <AGENT>` — agent-specific report\n\n"
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

        # ── Phase 3: Forum plain-text commands ─────────────────────
        forum_top_match = re.search(r"\bforum\s+top(?:\s+([a-z_]+))?\s*$", normalized)
        if forum_top_match:
            category = str(forum_top_match.group(1) or "").strip()
            payload = json.dumps({"category": category, "limit": 10}, separators=(",", ":"))
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "FORUM_TOP_TOPICS",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": "Pulling top-scored forum topics.",
            }

        forum_vote_match = re.search(
            r"\bforum\s+vote\s+(TOPIC-[0-9]{5})\s+(up|down)\b",
            raw,
            flags=re.IGNORECASE,
        )
        if forum_vote_match:
            topic_id = str(forum_vote_match.group(1) or "").strip().upper()
            direction = str(forum_vote_match.group(2) or "").strip().lower()
            payload = json.dumps(
                {"topic_id": topic_id, "direction": direction, "voter": "SAPPHIRE"},
                separators=(",", ":"),
            )
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "FORUM_VOTE_TOPIC",
                "quantity": 0.0,
                "agent": SAPPHIRE,
                "ack": f"Voting `{direction}` on `{topic_id}`.",
            }

        if re.search(r"\bforum\s+agents\b", normalized):
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "FORUM_AGENTS",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": "Loading agent personality profiles.",
            }

        forum_thread_match = re.search(
            r"\bforum\s+thread\s+(TOPIC-[0-9]{5})\b",
            raw,
            flags=re.IGNORECASE,
        )
        if forum_thread_match:
            topic_id = str(forum_thread_match.group(1) or "").strip().upper()
            payload = json.dumps({"topic_id": topic_id}, separators=(",", ":"))
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "FORUM_THREAD",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": f"Loading thread for `{topic_id}`.",
            }

        if re.search(r"\bforum\s+approvals\b", normalized):
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "FORUM_PENDING_APPROVALS",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": "Checking pending approval workflows.",
            }

        # ── Phase 4: Reputation plain-text commands ──────────────────
        if re.search(r"\brep\s+leaderboard\b", normalized):
            payload = json.dumps({"limit": 10}, separators=(",", ":"))
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "REP_LEADERBOARD",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": "Loading bot reputation leaderboard.",
            }

        rep_info_match = re.search(r"\brep\s+info\s+([A-Za-z0-9_-]+)", raw)
        if rep_info_match:
            bot_id = str(rep_info_match.group(1) or "").strip()
            payload = json.dumps({"bot_id": bot_id}, separators=(",", ":"))
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "REP_BOT_INFO",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": f"Looking up reputation for `{bot_id}`.",
            }

        if re.search(r"\brep\s+count\b", normalized):
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "REP_BOT_COUNT",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": "Counting registered bots.",
            }

        # ── Phase 4: Swarm plain-text commands ───────────────────────
        swarm_agg_match = re.search(r"\bswarm\s+aggregate\s+([A-Za-z0-9/_-]+)", raw)
        if swarm_agg_match:
            symbol = str(swarm_agg_match.group(1) or "").strip().upper()
            payload = json.dumps({"symbol": symbol}, separators=(",", ":"))
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "SWARM_AGGREGATE",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": f"Aggregating swarm consensus for `{symbol}`.",
            }

        swarm_ideas_match = re.search(r"\bswarm\s+ideas(?:\s+([A-Za-z0-9/_-]+))?", raw)
        if swarm_ideas_match:
            symbol = str(swarm_ideas_match.group(1) or "").strip().upper()
            payload = json.dumps({"symbol": symbol}, separators=(",", ":"))
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "SWARM_OPEN_IDEAS",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": f"Listing open swarm ideas{' for `' + symbol + '`' if symbol else ''}.",
            }

        if re.search(r"\bswarm\s+stats\b", normalized):
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "SWARM_STATS",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": "Loading swarm statistics.",
            }

        # ── Phase 4: Learning plain-text commands ──────────────────────
        if re.search(r"\blearn\s+report\b", normalized):
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "LEARN_REPORT",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": "Generating collaborative learning report.",
            }

        if re.search(r"\blearn\s+summary\b", normalized):
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "LEARN_SUMMARY",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": "Loading learning summary.",
            }

        learn_bias_match = re.search(
            r"\blearn\s+bias\s+([A-Za-z0-9/_-]+)(?:\s+(LONG|SHORT))?(?:\s+(\S+))?",
            raw,
            flags=re.IGNORECASE,
        )
        if learn_bias_match:
            symbol = str(learn_bias_match.group(1) or "").strip().upper()
            direction = str(learn_bias_match.group(2) or "LONG").strip().upper()
            timeframe = str(learn_bias_match.group(3) or "1h").strip()
            payload = json.dumps(
                {"symbol": symbol, "direction": direction, "timeframe": timeframe},
                separators=(",", ":"),
            )
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "LEARN_BIAS",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": f"Checking learning bias for `{symbol}` {direction} {timeframe}.",
            }

        # ── Phase 4: Outreach plain-text commands ──────────────────────
        outreach_post_match = re.search(
            r"\boutreach\s+post(?:\s+([A-Za-z0-9_-]+))?(?:\s+([A-Za-z0-9/_-]+))?",
            raw,
            flags=re.IGNORECASE,
        )
        if outreach_post_match:
            template = str(outreach_post_match.group(1) or "general_invite").strip()
            symbol = str(outreach_post_match.group(2) or "").strip().upper()
            payload = json.dumps(
                {"template": template, "symbol": symbol},
                separators=(",", ":"),
            )
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "OUTREACH_COMPOSE",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": f"Composing outreach (template=`{template}`"
                       + (f", symbol=`{symbol}`" if symbol else "")
                       + ").",
            }

        if re.search(r"\boutreach\s+stats\b", normalized):
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "OUTREACH_STATS",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": "Loading outreach statistics.",
            }

        if re.search(r"\boutreach\s+templates\b", normalized):
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "OUTREACH_TEMPLATES",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": "Listing available outreach templates.",
            }

        # ── Phase 5: Task Management plain-text commands ──────────────
        task_create_match = re.search(
            r"\btask\s+create\s+(.+)", normalized
        )
        if task_create_match:
            title = str(task_create_match.group(1) or "").strip()
            payload = json.dumps({"title": title})
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "TASK_CREATE",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": f"Creating task: {title[:80]}",
            }

        if re.search(r"\btask\s+list\b", normalized):
            # Parse optional filter: task list <agent|status>
            list_match = re.search(
                r"\btask\s+list\s+(\S+)", normalized
            )
            filter_val = str(list_match.group(1)).strip().upper() if list_match else ""
            payload_dict: Dict[str, str] = {}
            if filter_val in ("SAPPHIRE", "EMERALD", "OBSIDIAN"):
                payload_dict["agent"] = filter_val
            elif filter_val in ("PENDING", "IN_PROGRESS", "COMPLETED", "BLOCKED"):
                payload_dict["status"] = filter_val.lower()
            payload = json.dumps(payload_dict) if payload_dict else "ALL"
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "TASK_LIST",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": "Loading task list.",
            }

        task_update_match = re.search(
            r"\btask\s+update\s+(TASK-\d+)\s+(\S+)", normalized, flags=re.IGNORECASE
        )
        if task_update_match:
            task_id = str(task_update_match.group(1)).strip().upper()
            new_status = str(task_update_match.group(2)).strip().lower()
            payload = json.dumps({"task_id": task_id, "status": new_status})
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "TASK_UPDATE",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": f"Updating {task_id} → {new_status}.",
            }

        if re.search(r"\btask\s+report\b", normalized):
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "TASK_REPORT",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": "Generating task progress report.",
            }

        if re.search(r"\btask\s+summary\b", normalized):
            return {
                "platform": "CONTROL",
                "symbol": "ALL",
                "action": "TASK_SUMMARY",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": "Loading task summary.",
            }

        task_agent_match = re.search(
            r"\btask\s+agent\s+(\S+)", normalized, flags=re.IGNORECASE
        )
        if task_agent_match:
            agent_name = str(task_agent_match.group(1)).strip().upper()
            payload = json.dumps({"agent": agent_name})
            return {
                "platform": "CONTROL",
                "symbol": payload,
                "action": "TASK_AGENT_REPORT",
                "quantity": 0.0,
                "agent": EMERALD,
                "ack": f"Loading task report for {agent_name}.",
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

        # ── Phase 3: Forum collaboration commands ──────────────────
        # /forum top [category]
        forum_top = re.search(
            r"^/forum\s+top(?:\s+([a-z_]+))?$",
            text,
            flags=re.IGNORECASE,
        )
        if forum_top:
            category = str(forum_top.group(1) or "").strip().lower()
            payload = json.dumps({"category": category, "limit": 10}, separators=(",", ":"))
            await self.send_as(EMERALD, "Pulling top-scored forum topics.")
            await self._dispatch_callback("CONTROL", payload, "FORUM_TOP_TOPICS", 0.0)
            return

        # /forum vote <TOPIC-XXXXX> up|down
        forum_vote = re.search(
            r"^/forum\s+vote\s+(TOPIC-[0-9]{5})\s+(up|down)$",
            text,
            flags=re.IGNORECASE,
        )
        if forum_vote:
            topic_id = str(forum_vote.group(1) or "").strip().upper()
            direction = str(forum_vote.group(2) or "").strip().lower()
            payload = json.dumps(
                {"topic_id": topic_id, "direction": direction, "voter": "SAPPHIRE"},
                separators=(",", ":"),
            )
            await self.send_as(SAPPHIRE, f"Casting `{direction}` vote on `{topic_id}`.")
            await self._dispatch_callback("CONTROL", payload, "FORUM_VOTE_TOPIC", 0.0)
            return

        # /forum agents
        forum_agents = re.search(r"^/forum\s+agents$", text, flags=re.IGNORECASE)
        if forum_agents:
            await self.send_as(EMERALD, "Loading agent personality profiles.")
            await self._dispatch_callback("CONTROL", "ALL", "FORUM_AGENTS", 0.0)
            return

        # /forum thread <TOPIC-XXXXX>
        forum_thread = re.search(
            r"^/forum\s+thread\s+(TOPIC-[0-9]{5})$",
            text,
            flags=re.IGNORECASE,
        )
        if forum_thread:
            topic_id = str(forum_thread.group(1) or "").strip().upper()
            payload = json.dumps({"topic_id": topic_id}, separators=(",", ":"))
            await self.send_as(EMERALD, f"Loading thread for `{topic_id}`.")
            await self._dispatch_callback("CONTROL", payload, "FORUM_THREAD", 0.0)
            return

        # /forum post <title> | <body> [category:<cat>]
        forum_post = re.search(
            r"^/forum\s+post\s+(.+)$",
            text,
            flags=re.IGNORECASE,
        )
        if forum_post:
            raw_content = str(forum_post.group(1) or "").strip()
            # Extract optional category tag
            category = "general"
            cat_match = re.search(r"\bcategory:([a-z_]+)\b", raw_content, flags=re.IGNORECASE)
            if cat_match:
                category = str(cat_match.group(1) or "").strip().lower()
                raw_content = re.sub(r"\bcategory:[a-z_]+\b", "", raw_content, flags=re.IGNORECASE).strip()
            # Split title | body
            parts = raw_content.split("|", 1)
            title = parts[0].strip()
            body = parts[1].strip() if len(parts) > 1 else title
            payload = json.dumps(
                {
                    "title": title,
                    "body": body,
                    "category": category,
                    "lane": "trading",
                    "author": "SAPPHIRE",
                },
                separators=(",", ":"),
            )
            await self.send_as(SAPPHIRE, f"Creating forum topic: *{title[:60]}*")
            await self._dispatch_callback("CONTROL", payload, "FORUM_CREATE_TOPIC", 0.0)
            return

        # /forum approvals
        forum_approvals = re.search(r"^/forum\s+approvals$", text, flags=re.IGNORECASE)
        if forum_approvals:
            await self.send_as(EMERALD, "Checking pending approval workflows.")
            await self._dispatch_callback("CONTROL", "ALL", "FORUM_PENDING_APPROVALS", 0.0)
            return

        # ── Phase 4: Reputation slash commands ───────────────────────
        # /rep leaderboard [limit]
        rep_leaderboard = re.search(
            r"^/rep\s+leaderboard(?:\s+(\d+))?$",
            text,
            flags=re.IGNORECASE,
        )
        if rep_leaderboard:
            limit = max(1, min(25, int(rep_leaderboard.group(1) or "10")))
            payload = json.dumps({"limit": limit}, separators=(",", ":"))
            await self.send_as(EMERALD, "Loading bot reputation leaderboard.")
            await self._dispatch_callback("CONTROL", payload, "REP_LEADERBOARD", 0.0)
            return

        # /rep info <BOT_ID>
        rep_info = re.search(
            r"^/rep\s+info\s+([A-Za-z0-9_-]+)$",
            text,
            flags=re.IGNORECASE,
        )
        if rep_info:
            bot_id = str(rep_info.group(1) or "").strip()
            payload = json.dumps({"bot_id": bot_id}, separators=(",", ":"))
            await self.send_as(EMERALD, f"Looking up reputation for `{bot_id}`.")
            await self._dispatch_callback("CONTROL", payload, "REP_BOT_INFO", 0.0)
            return

        # /rep count
        rep_count = re.search(r"^/rep\s+count$", text, flags=re.IGNORECASE)
        if rep_count:
            await self.send_as(EMERALD, "Counting registered bots.")
            await self._dispatch_callback("CONTROL", "ALL", "REP_BOT_COUNT", 0.0)
            return

        # /rep ban <BOT_ID> [reason]
        rep_ban = re.search(
            r"^/rep\s+ban\s+([A-Za-z0-9_-]+)(?:\s+(.+))?$",
            text,
            flags=re.IGNORECASE,
        )
        if rep_ban:
            bot_id = str(rep_ban.group(1) or "").strip()
            reason = str(rep_ban.group(2) or "manual ban via Telegram").strip()
            payload = json.dumps(
                {"bot_id": bot_id, "reason": reason},
                separators=(",", ":"),
            )
            await self.send_as(SAPPHIRE, f"Banning bot `{bot_id}`.")
            await self._dispatch_callback("CONTROL", payload, "REP_BAN_BOT", 0.0)
            return

        # /rep penalize <BOT_ID> [reason]
        rep_penalize = re.search(
            r"^/rep\s+penalize\s+([A-Za-z0-9_-]+)(?:\s+(.+))?$",
            text,
            flags=re.IGNORECASE,
        )
        if rep_penalize:
            bot_id = str(rep_penalize.group(1) or "").strip()
            reason = str(rep_penalize.group(2) or "manual penalty via Telegram").strip()
            payload = json.dumps(
                {"bot_id": bot_id, "reason": reason},
                separators=(",", ":"),
            )
            await self.send_as(SAPPHIRE, f"Penalizing bot `{bot_id}`.")
            await self._dispatch_callback("CONTROL", payload, "REP_PENALIZE_BOT", 0.0)
            return

        # ── Phase 4: Swarm slash commands ────────────────────────────
        # /swarm aggregate <SYMBOL>
        swarm_agg = re.search(
            r"^/swarm\s+aggregate\s+([A-Za-z0-9/_-]+)$",
            text,
            flags=re.IGNORECASE,
        )
        if swarm_agg:
            symbol = str(swarm_agg.group(1) or "").strip().upper()
            payload = json.dumps({"symbol": symbol}, separators=(",", ":"))
            await self.send_as(EMERALD, f"Aggregating swarm consensus for `{symbol}`.")
            await self._dispatch_callback("CONTROL", payload, "SWARM_AGGREGATE", 0.0)
            return

        # /swarm ideas [SYMBOL]
        swarm_ideas = re.search(
            r"^/swarm\s+ideas(?:\s+([A-Za-z0-9/_-]+))?$",
            text,
            flags=re.IGNORECASE,
        )
        if swarm_ideas:
            symbol = str(swarm_ideas.group(1) or "").strip().upper()
            payload = json.dumps({"symbol": symbol}, separators=(",", ":"))
            await self.send_as(EMERALD, f"Listing open swarm ideas{' for `' + symbol + '`' if symbol else ''}.")
            await self._dispatch_callback("CONTROL", payload, "SWARM_OPEN_IDEAS", 0.0)
            return

        # /swarm stats
        swarm_stats = re.search(r"^/swarm\s+stats$", text, flags=re.IGNORECASE)
        if swarm_stats:
            await self.send_as(EMERALD, "Loading swarm statistics.")
            await self._dispatch_callback("CONTROL", "ALL", "SWARM_STATS", 0.0)
            return

        # ── Phase 4: Learning slash commands ───────────────────────────
        # /learn report
        learn_report = re.search(r"^/learn\s+report$", text, flags=re.IGNORECASE)
        if learn_report:
            await self.send_as(EMERALD, "Generating collaborative learning report.")
            await self._dispatch_callback("CONTROL", "ALL", "LEARN_REPORT", 0.0)
            return

        # /learn summary
        learn_summary = re.search(r"^/learn\s+summary$", text, flags=re.IGNORECASE)
        if learn_summary:
            await self.send_as(EMERALD, "Loading learning summary.")
            await self._dispatch_callback("CONTROL", "ALL", "LEARN_SUMMARY", 0.0)
            return

        # /learn bias <SYMBOL> [LONG|SHORT] [timeframe]
        learn_bias = re.search(
            r"^/learn\s+bias\s+([A-Za-z0-9/_-]+)(?:\s+(LONG|SHORT))?(?:\s+(\S+))?$",
            text,
            flags=re.IGNORECASE,
        )
        if learn_bias:
            symbol = str(learn_bias.group(1) or "").strip().upper()
            direction = str(learn_bias.group(2) or "LONG").strip().upper()
            timeframe = str(learn_bias.group(3) or "1h").strip()
            payload = json.dumps(
                {"symbol": symbol, "direction": direction, "timeframe": timeframe},
                separators=(",", ":"),
            )
            await self.send_as(EMERALD, f"Checking learning bias for `{symbol}` {direction} {timeframe}.")
            await self._dispatch_callback("CONTROL", payload, "LEARN_BIAS", 0.0)
            return

        # ── Phase 4: Outreach slash commands ──────────────────────────
        # /outreach post [template] [SYMBOL]
        outreach_post = re.search(
            r"^/outreach\s+post(?:\s+([A-Za-z0-9_-]+))?(?:\s+([A-Za-z0-9/_-]+))?$",
            text,
            flags=re.IGNORECASE,
        )
        if outreach_post:
            template = str(outreach_post.group(1) or "general_invite").strip()
            symbol = str(outreach_post.group(2) or "").strip().upper()
            payload = json.dumps(
                {"template": template, "symbol": symbol},
                separators=(",", ":"),
            )
            await self.send_as(
                EMERALD,
                f"Composing outreach (template=`{template}`"
                + (f", symbol=`{symbol}`" if symbol else "")
                + ").",
            )
            await self._dispatch_callback("CONTROL", payload, "OUTREACH_COMPOSE", 0.0)
            return

        # /outreach stats
        outreach_stats = re.search(r"^/outreach\s+stats$", text, flags=re.IGNORECASE)
        if outreach_stats:
            await self.send_as(EMERALD, "Loading outreach statistics.")
            await self._dispatch_callback("CONTROL", "ALL", "OUTREACH_STATS", 0.0)
            return

        # /outreach templates
        outreach_tpl = re.search(r"^/outreach\s+templates$", text, flags=re.IGNORECASE)
        if outreach_tpl:
            await self.send_as(EMERALD, "Listing available outreach templates.")
            await self._dispatch_callback("CONTROL", "ALL", "OUTREACH_TEMPLATES", 0.0)
            return

        # ── Phase 5: Task Management slash commands ───────────────────
        # /task create <title>
        task_create = re.search(r"^/task\s+create\s+(.+)$", text, flags=re.IGNORECASE)
        if task_create:
            title = str(task_create.group(1) or "").strip()
            payload = json.dumps({"title": title})
            await self.send_as(EMERALD, f"Creating task: {title[:80]}")
            await self._dispatch_callback("CONTROL", payload, "TASK_CREATE", 0.0)
            return

        # /task list [filter]
        task_list = re.search(r"^/task\s+list(?:\s+(\S+))?$", text, flags=re.IGNORECASE)
        if task_list:
            filter_val = str(task_list.group(1) or "").strip().upper()
            payload_dict: Dict[str, str] = {}
            if filter_val in ("SAPPHIRE", "EMERALD", "OBSIDIAN"):
                payload_dict["agent"] = filter_val
            elif filter_val in ("PENDING", "IN_PROGRESS", "COMPLETED", "BLOCKED"):
                payload_dict["status"] = filter_val.lower()
            payload = json.dumps(payload_dict) if payload_dict else "ALL"
            await self.send_as(EMERALD, "Loading task list.")
            await self._dispatch_callback("CONTROL", payload, "TASK_LIST", 0.0)
            return

        # /task update <TASK-ID> <status>
        task_update = re.search(
            r"^/task\s+update\s+(TASK-\d+)\s+(\S+)$", text, flags=re.IGNORECASE
        )
        if task_update:
            task_id = str(task_update.group(1)).strip().upper()
            new_status = str(task_update.group(2)).strip().lower()
            payload = json.dumps({"task_id": task_id, "status": new_status})
            await self.send_as(EMERALD, f"Updating {task_id} → {new_status}.")
            await self._dispatch_callback("CONTROL", payload, "TASK_UPDATE", 0.0)
            return

        # /task report
        task_report = re.search(r"^/task\s+report$", text, flags=re.IGNORECASE)
        if task_report:
            await self.send_as(EMERALD, "Generating task progress report.")
            await self._dispatch_callback("CONTROL", "ALL", "TASK_REPORT", 0.0)
            return

        # /task summary
        task_summary = re.search(r"^/task\s+summary$", text, flags=re.IGNORECASE)
        if task_summary:
            await self.send_as(EMERALD, "Loading task summary.")
            await self._dispatch_callback("CONTROL", "ALL", "TASK_SUMMARY", 0.0)
            return

        # /task agent <AGENT>
        task_agent = re.search(r"^/task\s+agent\s+(\S+)$", text, flags=re.IGNORECASE)
        if task_agent:
            agent_name = str(task_agent.group(1)).strip().upper()
            payload = json.dumps({"agent": agent_name})
            await self.send_as(EMERALD, f"Loading task report for {agent_name}.")
            await self._dispatch_callback("CONTROL", payload, "TASK_AGENT_REPORT", 0.0)
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

        # Portfolio command: /portfolio or /positions
        if re.search(r"^/(portfolio|positions?|pnl)\b", text_lower):
            await self.send_as(SAPPHIRE, "Pulling portfolio status.")
            await self._dispatch_callback("CONTROL", "ALL", "PORTFOLIO", 0.0)
            return

        # Memory / cognition command: /memory or /cognition
        if re.search(r"^/(memory|cognition|brain)\b", text_lower):
            await self.send_as(EMERALD, "Pulling cognitive system status.")
            await self._dispatch_callback("CONTROL", "ALL", "MEMORY_STATUS", 0.0)
            return

        # Skill security audit command: /audit <skill_content>
        audit_match = re.search(r"^/audit\s+(.+)", text, re.DOTALL | re.IGNORECASE)
        if audit_match:
            await self.send_as(EMERALD, "Running security audit on skill content.")
            await self._dispatch_callback("CONTROL", audit_match.group(1).strip(), "SKILL_AUDIT", 0.0)
            return

        # Security audit stats: /audits
        if re.search(r"^/audits?\s*$", text_lower):
            await self.send_as(EMERALD, "Pulling skill audit statistics.")
            await self._dispatch_callback("CONTROL", "ALL", "SKILL_AUDIT_STATS", 0.0)
            return

        # Activity feed: /activity — flush pending agent activities now
        if re.search(r"^/(activity|feed|actions?)\b", text_lower):
            if self._activity_feed:
                await self._flush_activity_feed()
            else:
                await self.send_as(SAPPHIRE, "No pending agent activities to report.")
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

        # ── Freeform conversation / steering ──────────────────────
        if directive:
            if len(directive) > 500:
                directive = directive[:500]
            agent = self._route_agent(directive)
            # Route through AI chat so agents can respond conversationally.
            await self._dispatch_callback("CONTROL", directive, "OWNER_CHAT", 0.0)
