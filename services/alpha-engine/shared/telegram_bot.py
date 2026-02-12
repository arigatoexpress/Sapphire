"""
Focused Telegram bot service for Sapphire Alpha.

Design goals:
- Keep control flow scoped to Sapphire and enabled venues.
- Support heartbeat/control commands and owner steering notes.
- Operate safely in either polling mode or webhook mode.
"""

import asyncio
import os
import re
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
        batch_text = "📋 **Sapphire Activity Digest**\n" + "\n".join(self.message_buffer)
        self.message_buffer.clear()
        await self._dispatch_message(batch_text, allow_markdown=True)

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
                "💓 Heartbeat response captured and queued for Sapphire execution context."
                if intent in {"answer", "reply", "respond"}
                else "🧠 Owner directive captured and queued for Sapphire execution context."
            )
            await self.send_message(
                response_ack,
                priority=NotificationPriority.HIGH,
            )
            await self._dispatch_callback("CONTROL", directive, "OWNER_STEER", 0.0)
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
                f"🧭 Control command accepted: `{raw_action.upper()}` target `{target}`",
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
                f"🧭 Allocation command accepted: `{raw_action.upper()}` `{target}` -> `{allocation*100:.0f}%`",
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
                    "🧠 Owner note captured from @alpha command and queued.",
                    priority=NotificationPriority.HIGH,
                )
                await self._dispatch_callback("CONTROL", directive, "OWNER_STEER", 0.0)
