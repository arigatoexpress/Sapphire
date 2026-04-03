from __future__ import annotations

from typing import Any

import httpx


class TelegramClient:
    def __init__(self, bot_token: str, timeout_seconds: float = 12.0) -> None:
        self._bot_token = bot_token
        self._timeout = timeout_seconds

    @property
    def enabled(self) -> bool:
        return bool(self._bot_token)

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self._bot_token}/{method}"

    async def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._url(method), json=payload)
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram API error for {method}: {data}")
            return data

    async def send_message(self, chat_id: int, text: str) -> None:
        await self._post(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
        )

    async def set_webhook(self, webhook_url: str, secret_token: str) -> dict[str, Any]:
        payload = {
            "url": webhook_url,
            "secret_token": secret_token,
            "allowed_updates": ["message", "channel_post"],
        }
        return await self._post("setWebhook", payload)
