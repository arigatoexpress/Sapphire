"""Telegram reader backends.

The protocol is synchronous at the service boundary so tests and plugin calls
can inject fake readers without an event loop. The live MTProto backend imports
Telethon lazily, and Bot API reads are explicit method calls only.
"""

from __future__ import annotations

import asyncio
import json
import os
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from services.telegram_intel.models import ChannelConfig, RawMessage

DEFAULT_SESSION_PATH = Path.home() / ".sapphire" / "telegram_intel.session"


class BackendError(RuntimeError):
    """Reader backend failed or was not configured."""


class ReaderBackend(Protocol):
    """Protocol implemented by Telegram reader backends."""

    def pull_channel(
        self,
        channel: ChannelConfig,
        *,
        limit: int,
        since_id: str | None = None,
    ) -> list[RawMessage]:
        """Return newest messages for one channel without persisting them."""


def _iso_from_timestamp(value: int | float | None) -> str:
    if value is None:
        return datetime.now(UTC).replace(microsecond=0).isoformat()
    return datetime.fromtimestamp(float(value), tz=UTC).replace(microsecond=0).isoformat()


def _message_text_from_telegram(obj: Any) -> str:
    return str(getattr(obj, "raw_text", None) or getattr(obj, "text", None) or "")


class MTProtoBackend:
    """Telethon-backed MTProto reader.

    Requires ``TELEGRAM_API_ID`` and ``TELEGRAM_API_HASH`` unless passed
    explicitly. The session path is intentionally outside the repo.
    """

    def __init__(
        self,
        *,
        api_id: str | int | None = None,
        api_hash: str | None = None,
        session_path: Path | str = DEFAULT_SESSION_PATH,
    ) -> None:
        self.api_id = str(api_id or os.environ.get("TELEGRAM_API_ID") or "").strip()
        self.api_hash = str(api_hash or os.environ.get("TELEGRAM_API_HASH") or "").strip()
        self.session_path = Path(session_path).expanduser()
        if not self.api_id or not self.api_hash:
            raise BackendError("MTProto requires TELEGRAM_API_ID and TELEGRAM_API_HASH")

    def pull_channel(
        self,
        channel: ChannelConfig,
        *,
        limit: int,
        since_id: str | None = None,
    ) -> list[RawMessage]:
        async def _pull() -> list[RawMessage]:
            try:
                from telethon import TelegramClient
            except ImportError as exc:
                raise BackendError("Telethon is not installed") from exc

            min_id = int(since_id) if since_id and str(since_id).isdigit() else 0
            messages: list[RawMessage] = []
            async with TelegramClient(str(self.session_path), int(self.api_id), self.api_hash) as client:
                async for item in client.iter_messages(channel.source, limit=limit, min_id=min_id):
                    text = _message_text_from_telegram(item)
                    if not text:
                        continue
                    published = getattr(item, "date", None)
                    if isinstance(published, datetime):
                        published_at = published.astimezone(UTC).replace(microsecond=0).isoformat()
                    else:
                        published_at = _iso_from_timestamp(None)
                    messages.append(
                        RawMessage(
                            channel_id=channel.id,
                            message_id=str(getattr(item, "id", "")),
                            text=text,
                            published_at=published_at,
                            url=None,
                            metadata={"backend": "mtproto"},
                        )
                    )
            return messages

        return asyncio.run(_pull())


class BotAPIBackend:
    """Telegram Bot API reader for channel posts visible to the bot."""

    def __init__(
        self,
        *,
        token: str | None = None,
        api_base: str = "https://api.telegram.org",
        timeout_seconds: int = 10,
    ) -> None:
        self.token = str(token or os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
        self.api_base = api_base.rstrip("/")
        self.timeout_seconds = timeout_seconds
        if not self.token:
            raise BackendError("BotAPI requires TELEGRAM_BOT_TOKEN")

    def pull_channel(
        self,
        channel: ChannelConfig,
        *,
        limit: int,
        since_id: str | None = None,
    ) -> list[RawMessage]:
        params = urllib.parse.urlencode(
            {
                "limit": max(1, min(int(limit), 100)),
                "timeout": 0,
                "allowed_updates": json.dumps(["channel_post"]),
            }
        )
        url = f"{self.api_base}/bot{self.token}/getUpdates?{params}"
        with urllib.request.urlopen(url, timeout=self.timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not payload.get("ok"):
            raise BackendError("Bot API returned ok=false")
        since_num = int(since_id) if since_id and str(since_id).isdigit() else 0
        messages: list[RawMessage] = []
        for update in payload.get("result", []):
            post = update.get("channel_post") or {}
            chat = post.get("chat") or {}
            if not _matches_channel(channel, chat):
                continue
            message_id = int(post.get("message_id") or 0)
            if message_id <= since_num:
                continue
            text = str(post.get("text") or post.get("caption") or "").strip()
            if not text:
                continue
            messages.append(
                RawMessage(
                    channel_id=channel.id,
                    message_id=str(message_id),
                    text=text,
                    published_at=_iso_from_timestamp(post.get("date")),
                    url=None,
                    metadata={"backend": "botapi", "update_id": update.get("update_id")},
                )
            )
        return messages[:limit]


def _matches_channel(channel: ChannelConfig, chat: dict[str, Any]) -> bool:
    source = channel.source.strip().lstrip("@").lower()
    username = str(chat.get("username") or "").strip().lstrip("@").lower()
    chat_id = str(chat.get("id") or "").strip()
    return bool(source and (source == username or channel.source.strip() == chat_id))


def build_backend(name: str) -> ReaderBackend:
    normalized = (name or "mtproto").strip().lower()
    if normalized == "mtproto":
        return MTProtoBackend()
    if normalized == "botapi":
        return BotAPIBackend()
    raise BackendError(f"unsupported backend: {name}")
