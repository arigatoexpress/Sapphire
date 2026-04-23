#!/usr/bin/env python3
"""Telegram-facing service wrapper for sapphire_pm_bot."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, Request

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_DIR = REPO_ROOT / "plugins" / "claw-sapphire" / "tools"

if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))

import sapphire_pm_bot

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("sapphire.pm_bot")


# Fallback secret file paths, matching plugins/claw-sapphire/tools/notify.py.
# Lets the PM bot share a Telegram bot with the rest of the Sapphire stack
# without duplicating token plumbing.
_SECRET_PATHS = [
    Path.home() / ".config" / "sapphire-secrets" / "telegram_bot_token",
    Path.home() / ".config" / "sapphire" / "telegram_bot_token",
]


def _resolve_bot_token() -> str:
    """Resolve the Telegram bot token in priority order.

    1. `SAPPHIRE_PM_BOT_TOKEN`   — explicit override (per-bot deployment)
    2. `TELEGRAM_BOT_TOKEN`      — shared Sapphire bot (notify, watchdog, etc.)
    3. `~/.config/sapphire-secrets/telegram_bot_token` file
    4. `~/.config/sapphire/telegram_bot_token` file

    Returns empty string if nothing is configured. The caller (`main()`)
    fails-closed on empty so the service refuses to start with a clear
    critical-log message.
    """
    explicit = os.getenv("SAPPHIRE_PM_BOT_TOKEN", "").strip()
    if explicit:
        return explicit

    shared = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if shared:
        return shared

    for path in _SECRET_PATHS:
        try:
            if path.exists():
                contents = path.read_text().strip()
                if contents:
                    return contents
        except OSError:
            continue

    return ""


@dataclass(frozen=True)
class Settings:
    token: str
    mode: str
    host: str
    port: int
    telegram_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        port_text = os.getenv("SAPPHIRE_PM_BOT_PORT", "18082").strip() or "18082"
        return cls(
            token=_resolve_bot_token(),
            mode=os.getenv("MODE", "webhook").strip().lower() or "webhook",
            host=os.getenv("SAPPHIRE_PM_BOT_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=int(port_text),
            telegram_timeout_seconds=float(os.getenv("SAPPHIRE_PM_BOT_TIMEOUT_SECONDS", "30")),
        )


class TelegramAPI:
    def __init__(self, token: str, timeout_seconds: float = 30.0) -> None:
        self._token = token
        self._timeout = timeout_seconds

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self._token}/{method}"

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(self._url(method), json=payload, timeout=self._timeout)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error for {method}: {data}")
        return data

    def send_message(self, *, chat_id: int, text: str, parse_mode: str | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        return self._post("sendMessage", payload)

    def get_updates(self, *, offset: int, timeout: int = 30) -> list[dict[str, Any]]:
        data = self._post("getUpdates", {"offset": offset, "timeout": timeout, "allowed_updates": ["message"]})
        result = data.get("result")
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        return []

    def delete_webhook(self, *, drop_pending_updates: bool = False) -> dict[str, Any]:
        return self._post("deleteWebhook", {"drop_pending_updates": drop_pending_updates})


SETTINGS = Settings.from_env()
TELEGRAM_API = TelegramAPI(SETTINGS.token, timeout_seconds=SETTINGS.telegram_timeout_seconds)
POLLING_STOP = threading.Event()
POLLING_STATE: dict[str, Any] = {
    "thread": None,
    "last_error": None,
    "offset": 0,
}

app = FastAPI(title="Sapphire PM Bot", version="0.1.0")


def _validate_startup_config() -> None:
    if not SETTINGS.token:
        logger.critical(
            "No Telegram bot token found. Set SAPPHIRE_PM_BOT_TOKEN (override) "
            "or TELEGRAM_BOT_TOKEN (shared with notify/watchdog) or drop it "
            "at ~/.config/sapphire-secrets/telegram_bot_token. Refusing to start."
        )
        raise RuntimeError("Telegram bot token is required")
    if SETTINGS.mode not in {"webhook", "polling"}:
        raise RuntimeError(f"Unsupported MODE={SETTINGS.mode!r}; expected 'webhook' or 'polling'")


def _message_payload(update: dict[str, Any]) -> dict[str, Any]:
    message = update.get("message")
    if isinstance(message, dict):
        return message
    return update


def _chat_id(update: dict[str, Any]) -> int | None:
    message = _message_payload(update)
    chat = message.get("chat")
    if isinstance(chat, dict) and chat.get("id") is not None:
        try:
            return int(chat["id"])
        except (TypeError, ValueError):
            return None
    value = message.get("chat_id")
    if value is not None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
    return None


def process_update(update: dict[str, Any]) -> bool:
    message = _message_payload(update)
    if not isinstance(message, dict):
        return False
    if not isinstance(message.get("text"), str):
        return False

    chat_id = _chat_id(update)
    if chat_id is None:
        logger.warning("Skipping Telegram update without chat id: %s", update.get("update_id"))
        return False

    response = sapphire_pm_bot.handle_telegram_command(update)
    text = str(response.get("text") or "").strip()
    if not text:
        return False

    TELEGRAM_API.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=response.get("parse_mode"),
    )
    return True


def _polling_loop() -> None:
    logger.info("Starting Telegram polling loop")
    try:
        TELEGRAM_API.delete_webhook(drop_pending_updates=False)
    except Exception as exc:  # pragma: no cover - network/runtime behavior
        logger.warning("Could not delete Telegram webhook before polling: %s", exc)

    offset = int(POLLING_STATE.get("offset") or 0)
    while not POLLING_STOP.is_set():
        try:
            updates = TELEGRAM_API.get_updates(offset=offset, timeout=30)
            POLLING_STATE["last_error"] = None
            for update in updates:
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    offset = update_id + 1
                    POLLING_STATE["offset"] = offset
                try:
                    process_update(update)
                except Exception as exc:  # pragma: no cover - network/runtime behavior
                    logger.exception("Failed to process Telegram update: %s", exc)
        except Exception as exc:  # pragma: no cover - network/runtime behavior
            POLLING_STATE["last_error"] = str(exc)
            logger.warning("Telegram polling error: %s", exc)
            time.sleep(5)

    logger.info("Telegram polling loop stopped")


def _start_polling_thread() -> None:
    current = POLLING_STATE.get("thread")
    if isinstance(current, threading.Thread) and current.is_alive():
        return
    POLLING_STOP.clear()
    thread = threading.Thread(target=_polling_loop, daemon=True, name="sapphire-pm-bot-poller")
    POLLING_STATE["thread"] = thread
    thread.start()


@app.on_event("startup")
def on_startup() -> None:
    _validate_startup_config()
    if SETTINGS.mode == "polling":
        _start_polling_thread()
    logger.info("Sapphire PM bot ready (mode=%s)", SETTINGS.mode)


@app.on_event("shutdown")
def on_shutdown() -> None:
    POLLING_STOP.set()


@app.get("/health")
def health() -> dict[str, Any]:
    thread = POLLING_STATE.get("thread")
    polling_active = bool(isinstance(thread, threading.Thread) and thread.is_alive())
    return {
        "status": "ok",
        "service": "sapphire-pm-bot",
        "mode": SETTINGS.mode,
        "polling_active": polling_active,
        "last_poll_error": POLLING_STATE.get("last_error"),
    }


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict[str, Any]:
    update = await request.json()
    processed = process_update(update)
    return {"ok": True, "processed": processed}


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    _validate_startup_config()
    uvicorn.run("server:app", host=SETTINGS.host, port=SETTINGS.port, reload=False)
