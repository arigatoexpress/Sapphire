"""
Enhanced Telegram Bot Service for Sapphire AI.
Supports notifications and interactive commands via @mentions.
"""

import asyncio
import logging
import re
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import aiohttp
from loguru import logger


class NotificationPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TelegramPlatformBot:
    """
    Enhanced Telegram Bot that handles both notifications and command processing.
    """

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        command_callback: Optional[Callable[[str, str, str, float], Any]] = None,
    ):
        self.bot_token = bot_token.strip() if bot_token else None
        self.chat_id = str(chat_id).strip() if chat_id else None
        logger.info(
            f"Initializing Telegram Bot with Token: {'Exists' if self.bot_token else 'MISSING'}, Chat ID: {'Exists' if self.chat_id else 'MISSING'}"
        )
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.command_callback = command_callback
        self.last_update_id = 0
        self.running = False
        self.message_buffer: List[str] = []
        self._flush_task = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def start(self):
        """Start the flush loop and listener."""
        self.running = True
        self._flush_task = asyncio.create_task(self._flush_loop())
        await self.start_listener()

    async def _flush_loop(self):
        """Periodically flush buffered messages."""
        while self.running:
            await asyncio.sleep(20)  # Batch window
            if self.message_buffer:
                await self._flush_buffer()

    async def _flush_buffer(self):
        """Combine and send buffered messages."""
        if not self.message_buffer:
            return

        # Combine messages
        batch_text = "📋 **Activity Digest**\n" + "\n".join(self.message_buffer)
        self.message_buffer.clear()

        # Send as single update (force send)
        await self._dispatch_message(batch_text, NotificationPriority.LOW)

    async def send_message(
        self, text: str, priority: NotificationPriority = NotificationPriority.MEDIUM, **kwargs
    ):
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram configuration missing")
            return

        priority_prefix = {
            NotificationPriority.LOW: "📝",
            NotificationPriority.MEDIUM: "📢",
            NotificationPriority.HIGH: "🚨",
            NotificationPriority.CRITICAL: "🚨🚨",
        }.get(priority, "📢")

        full_message = f"{priority_prefix} {text}"

        # Batch LOW/MEDIUM messages
        if priority in (NotificationPriority.LOW, NotificationPriority.MEDIUM):
            self.message_buffer.append(full_message)
            if len(self.message_buffer) >= 10:  # Flush if buffer gets big
                await self._flush_buffer()
            return

        # Send HIGH/CRITICAL immediately
        await self._dispatch_message(full_message, priority)

    async def _dispatch_message(self, text: str, priority: NotificationPriority):
        """Internal method to actually post to Telegram."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown",  # Re-enabling Markdown for formatting
            "disable_web_page_preview": True,
        }

        try:
            # logger.info(f"📤 Posting to Telegram: {text[:50]}...")
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status != 200:
                        logger.error(f"❌ Telegram API Error: {resp.status}")
                        # If Markdown fails (often due to unescaped chars), retry without it
                        if resp.status == 400:
                            payload.pop("parse_mode")
                            await session.post(url, json=payload)
        except Exception as e:
            logger.error(f"❌ Telegram Post Failed: {e}")

    async def start_listener(self):
        """Starts a long-polling loop to listen for interactive commands."""
        if not self.bot_token:
            logger.error("Cannot start Telegram listener without token")
            return

        logger.info("📡 Telegram Command Listener Started")
        self.running = True

        while self.running:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {"offset": self.last_update_id + 1, "timeout": 30}

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, timeout=35) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("ok"):
                                for update in data.get("result", []):
                                    self.last_update_id = update["update_id"]
                                    await self._process_update(update)
                        elif resp.status == 409:
                            # Use randomized jitter
                            import random

                            jitter = random.uniform(5, 30)
                            logger.warning(f"Telegram conflict, retrying in {jitter:.1f}s...")
                            await asyncio.sleep(jitter)
                        else:
                            logger.error(f"Telegram listener error: {resp.status}")
                            await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Telegram listener crashed: {e}")
                await asyncio.sleep(10)

    async def _process_update(self, update: Dict[str, Any]):
        message = update.get("message", {})
        text = message.get("text", "")
        chat_id = str(message.get("chat", {}).get("id", ""))

        if self.chat_id and chat_id != self.chat_id:
            return

        cmd_match = re.search(r"@(\w+)\s+(buy|sell|close)\s+([\d.]+)\s+(\w+)", text.lower())

        if cmd_match:
            platform = cmd_match.group(1)
            action = cmd_match.group(2).upper()
            quantity = float(cmd_match.group(3))
            symbol = cmd_match.group(4).upper()

            platforms = (
                ["drift", "hyperliquid", "aster", "symphony"] if platform == "all" else [platform]
            )

            await self.send_message(
                f"⚡ **MANUAL OVERRIDE**\n"
                f"🎯 `{platform.upper()}`: `{action} {quantity} {symbol}`",
                priority=NotificationPriority.HIGH,
            )

            if self.command_callback:
                for p in platforms:
                    try:
                        await self.command_callback(p, symbol, action, quantity)
                    except Exception as e:
                        await self.send_message(f"❌ Error dispatching to {p}: {e}")

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def send_message(
        self, text: str, priority: NotificationPriority = NotificationPriority.MEDIUM, **kwargs
    ):
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram configuration missing")
            return

        priority_prefix = {
            NotificationPriority.LOW: "📝",
            NotificationPriority.MEDIUM: "📢",
            NotificationPriority.HIGH: "🚨",
            NotificationPriority.CRITICAL: "🚨🚨",
        }.get(priority, "📢")

        full_message = f"{priority_prefix} {text}"
        url = f"{self.base_url}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": full_message, "disable_web_page_preview": True}

        try:
            logger.info(f"📤 Posting to Telegram: {full_message[:50]}...")
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.post(url, json=payload) as resp:
                    resp_data = await resp.json()
                    if resp.status != 200:
                        logger.error(f"❌ Telegram API Error: {resp.status} - {resp_data}")
                    else:
                        logger.info(
                            f"✅ Telegram Message Sent Successfully (ID: {resp_data.get('result', {}).get('message_id')})"
                        )
        except Exception as e:
            import traceback

            logger.error(f"❌ Telegram Post Failed: {e}\n{traceback.format_exc()}")

    async def start_listener(self):
        """Starts a long-polling loop to listen for interactive commands."""
        if not self.bot_token:
            logger.error("Cannot start Telegram listener without token")
            return

        logger.info("📡 Telegram Command Listener Started")
        self.running = True

        while self.running:
            try:
                url = f"{self.base_url}/getUpdates"
                params = {"offset": self.last_update_id + 1, "timeout": 30}

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, timeout=35) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("ok"):
                                for update in data.get("result", []):
                                    self.last_update_id = update["update_id"]
                                    await self._process_update(update)
                        elif resp.status == 409:
                            # Use randomized jitter to resolve conflicts in scaled environments
                            import random

                            jitter = random.uniform(5, 30)
                            logger.warning(
                                f"Telegram conflict (another instance is listening), retrying in {jitter:.1f}s..."
                            )
                            await asyncio.sleep(jitter)
                        else:
                            logger.error(f"Telegram listener error: {resp.status}")
                            await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"Telegram listener crashed: {e}")
                await asyncio.sleep(10)

    async def _process_update(self, update: Dict[str, Any]):
        message = update.get("message", {})
        text = message.get("text", "")
        chat_id = str(message.get("chat", {}).get("id", ""))

        # Security: Only respond to messages from the authorized group/chat
        if self.chat_id and chat_id != self.chat_id:
            return

        # Pattern 1: @platform action quantity symbol (e.g. @hyperliquid buy 0.1 sol)
        cmd_match = re.search(r"@(\w+)\s+(buy|sell|close)\s+([\d.]+)\s+(\w+)", text.lower())

        # Pattern 2: AI Commands (e.g. @alpha recap)
        ai_match = re.search(r"@(\w+)\s+(recap|analyze|report)", text.lower())

        if ai_match:
            platform = ai_match.group(1)
            action = ai_match.group(2).upper()
            if self.command_callback:
                asyncio.create_task(self.command_callback(platform, "AI", action, 0.0))
            return

        if cmd_match:
            platform = cmd_match.group(1)
            action = cmd_match.group(2).upper()
            quantity = float(cmd_match.group(3))
            symbol = cmd_match.group(4).upper()

            # Special case for "all"
            platforms = (
                ["drift", "hyperliquid", "aster", "symphony"] if platform == "all" else [platform]
            )

            await self.send_message(
                f"⚡ **MANUAL OVERRIDE DETECTED**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **Platform**: `{platform.upper()}`\n"
                f"📝 **Action**: `{action} {quantity} {symbol}`\n"
                f"⏳ **Verification**: Dispatching to execution layer...",
                priority=NotificationPriority.HIGH,
            )

            if self.command_callback:
                for p in platforms:
                    try:
                        await self.command_callback(p, symbol, action, quantity)
                    except Exception as e:
                        await self.send_message(f"❌ Error dispatching to {p}: {e}")
            else:
                logger.warning("No command callback registered for Telegram Bot")
