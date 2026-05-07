#!/usr/bin/env python3
"""Telegram-facing service wrapper for sapphire_pm_bot."""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException, Request

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

_TELEGRAM_BOT_URL_RE = re.compile(r"(https://api\.telegram\.org/bot)[^/\s]+(/[^,\s)]*)?")
_TELEGRAM_TOKEN_RE = re.compile(r"\b\d{7,12}:[A-Za-z0-9_-]{20,}\b")


def _redact_sensitive_text(value: object) -> str:
    """Return log/health-safe text with bot credentials removed."""
    text = str(value)
    text = _TELEGRAM_BOT_URL_RE.sub(r"\1[REDACTED]\2", text)
    return _TELEGRAM_TOKEN_RE.sub("[REDACTED_TELEGRAM_TOKEN]", text)


# Fallback secret file paths, matching plugins/claw-sapphire/tools/notify.py.
# Lets the PM bot share a Telegram bot with the rest of the Sapphire stack
# without duplicating token plumbing.
_SECRET_PATHS = [
    Path.home() / ".config" / "sapphire-secrets" / "telegram_bot_token",
    Path.home() / ".config" / "sapphire" / "telegram_bot_token",
]

_WEBHOOK_SECRET_PATHS = [
    Path.home() / ".config" / "sapphire-secrets" / "sapphire_pm_bot_webhook_secret",
    Path.home() / ".config" / "sapphire-secrets" / "telegram_webhook_secret",
    Path.home() / ".config" / "sapphire" / "telegram_webhook_secret",
]

_TRUE_VALUES = {"1", "true", "yes", "on"}
_DEDICATED_TOKEN_SOURCES = {"explicit_env"}
_SUPPORTED_UPDATE_TYPES = [
    "message",
    "edited_message",
    "channel_post",
    "edited_channel_post",
]


def _read_first_secret_file(paths: list[Path]) -> str:
    for path in paths:
        try:
            if path.exists():
                contents = path.read_text().strip()
                if contents:
                    return contents
        except OSError:
            continue
    return ""


def _read_first_secret_file_with_path(paths: list[Path]) -> tuple[str, Path | None]:
    for path in paths:
        try:
            if path.exists():
                contents = path.read_text().strip()
                if contents:
                    return contents, path
        except OSError:
            continue
    return "", None


def _bot_token_file_source(path: Path) -> str:
    if path.name == "telegram_bot_token" and path.parent.name == "sapphire-secrets":
        return "shared_secret_file"
    return "legacy_secret_file"


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def _resolve_bot_token_with_source() -> tuple[str, str]:
    explicit = os.getenv("SAPPHIRE_PM_BOT_TOKEN", "").strip()
    if explicit:
        return explicit, "explicit_env"

    shared = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if shared:
        return shared, "shared_env"

    file_token, path = _read_first_secret_file_with_path(_SECRET_PATHS)
    if file_token:
        return file_token, _bot_token_file_source(path) if path is not None else "secret_file"

    return "", "missing"


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
    token, _source = _resolve_bot_token_with_source()
    return token


def _resolve_webhook_secret() -> str:
    """Resolve the Telegram webhook secret without embedding it in launchd plists."""
    explicit = os.getenv("SAPPHIRE_PM_BOT_WEBHOOK_SECRET", "").strip()
    if explicit:
        return explicit

    shared = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if shared:
        return shared

    return _read_first_secret_file(_WEBHOOK_SECRET_PATHS)


@dataclass(frozen=True)
class Settings:
    token: str
    webhook_secret: str
    mode: str
    host: str
    port: int
    telegram_timeout_seconds: float
    token_source: str = "explicit_env"
    shared_polling_allowed: bool = False
    bot_username: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        port_text = os.getenv("SAPPHIRE_PM_BOT_PORT", "18082").strip() or "18082"
        token, token_source = _resolve_bot_token_with_source()
        return cls(
            token=token,
            webhook_secret=_resolve_webhook_secret(),
            mode=os.getenv("MODE", "webhook").strip().lower() or "webhook",
            host=os.getenv("SAPPHIRE_PM_BOT_HOST", "127.0.0.1").strip() or "127.0.0.1",
            port=int(port_text),
            telegram_timeout_seconds=float(os.getenv("SAPPHIRE_PM_BOT_TIMEOUT_SECONDS", "30")),
            token_source=token_source,
            shared_polling_allowed=_env_flag("SAPPHIRE_PM_BOT_ALLOW_SHARED_POLLING"),
            bot_username=os.getenv("SAPPHIRE_PM_BOT_BOT_USERNAME", "").strip().lstrip("@"),
        )


class TelegramAPI:
    def __init__(self, token: str, timeout_seconds: float = 30.0) -> None:
        self._token = token
        self._timeout = timeout_seconds

    def _url(self, method: str) -> str:
        return f"https://api.telegram.org/bot{self._token}/{method}"

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(self._url(method), json=payload, timeout=self._timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = _redact_sensitive_text(response.text[:500])
            raise RuntimeError(
                f"Telegram API HTTP error for {method}: status={response.status_code} body={detail}"
            ) from exc
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error for {method}: {data}")
        return data

    def _get(self, method: str) -> dict[str, Any]:
        response = requests.get(self._url(method), timeout=self._timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = _redact_sensitive_text(response.text[:500])
            raise RuntimeError(
                f"Telegram API HTTP error for {method}: status={response.status_code} body={detail}"
            ) from exc
        data = response.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API error for {method}: {data}")
        result = data.get("result")
        return result if isinstance(result, dict) else {}

    def send_message(
        self,
        *,
        chat_id: int,
        text: str,
        parse_mode: str | None,
        disable_notification: bool = False,
        reply_parameters: dict[str, Any] | None = None,
        message_thread_id: int | None = None,
        direct_messages_topic_id: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if disable_notification:
            payload["disable_notification"] = True
        if reply_parameters:
            payload["reply_parameters"] = reply_parameters
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id
        if direct_messages_topic_id is not None:
            payload["direct_messages_topic_id"] = direct_messages_topic_id
        return self._post("sendMessage", payload)

    def get_updates(self, *, offset: int, timeout: int = 30) -> list[dict[str, Any]]:
        data = self._post(
            "getUpdates",
            {"offset": offset, "timeout": timeout, "allowed_updates": _SUPPORTED_UPDATE_TYPES},
        )
        result = data.get("result")
        if isinstance(result, list):
            return [item for item in result if isinstance(item, dict)]
        return []

    def delete_webhook(self, *, drop_pending_updates: bool = False) -> dict[str, Any]:
        return self._post("deleteWebhook", {"drop_pending_updates": drop_pending_updates})

    def get_me(self) -> dict[str, Any]:
        return self._get("getMe")

    def get_webhook_info(self) -> dict[str, Any]:
        return self._get("getWebhookInfo")


SETTINGS = Settings.from_env()
TELEGRAM_API = TelegramAPI(SETTINGS.token, timeout_seconds=SETTINGS.telegram_timeout_seconds)
POLLING_STOP = threading.Event()
POLLING_STATE: dict[str, Any] = {
    "thread": None,
    "last_error": None,
    "offset": 0,
}
_RECENT_UPDATE_IDS: OrderedDict[int, float] = OrderedDict()
_RECENT_UPDATE_IDS_LOCK = threading.Lock()
_RECENT_UPDATE_WINDOW_SECONDS = 600.0
_RECENT_UPDATE_LIMIT = 2048
_TELEGRAM_PROBE_TTL_SECONDS = 60.0
_TELEGRAM_PROBE_CACHE: dict[str, Any] = {"expires_at": 0.0, "value": None}
_TELEGRAM_PROBE_CACHE_LOCK = threading.Lock()

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
    if (
        SETTINGS.mode == "polling"
        and SETTINGS.token_source not in _DEDICATED_TOKEN_SOURCES
        and not SETTINGS.shared_polling_allowed
    ):
        logger.critical(
            "Refusing to start Telegram polling with token_source=%s. Polling with the shared "
            "Sapphire Telegram bot conflicts with Hermes or webhook consumers. Set "
            "SAPPHIRE_PM_BOT_TOKEN for a dedicated PM bot, switch MODE=webhook, or set "
            "SAPPHIRE_PM_BOT_ALLOW_SHARED_POLLING=1 only for a deliberate break-glass run.",
            SETTINGS.token_source,
        )
        raise RuntimeError(
            "Polling mode requires SAPPHIRE_PM_BOT_TOKEN or "
            "SAPPHIRE_PM_BOT_ALLOW_SHARED_POLLING=1"
        )


def _message_payload(update: dict[str, Any]) -> dict[str, Any]:
    for key in _SUPPORTED_UPDATE_TYPES:
        message = update.get(key)
        if isinstance(message, dict):
            return message
    return update


def _message_id(update: dict[str, Any]) -> int | None:
    message = _message_payload(update)
    value = message.get("message_id")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _message_thread_id(update: dict[str, Any]) -> int | None:
    message = _message_payload(update)
    value = message.get("message_thread_id")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _direct_messages_topic_id(update: dict[str, Any]) -> int | None:
    message = _message_payload(update)
    value = message.get("direct_messages_topic_id")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _mark_update_seen(update: dict[str, Any]) -> bool:
    """Return True when this update_id was already processed recently."""

    update_id = update.get("update_id")
    if not isinstance(update_id, int):
        return False
    now = time.time()
    with _RECENT_UPDATE_IDS_LOCK:
        expired = []
        for seen_id, seen_at in _RECENT_UPDATE_IDS.items():
            if now - seen_at > _RECENT_UPDATE_WINDOW_SECONDS:
                expired.append(seen_id)
            else:
                break
        for seen_id in expired:
            _RECENT_UPDATE_IDS.pop(seen_id, None)

        if update_id in _RECENT_UPDATE_IDS:
            _RECENT_UPDATE_IDS.move_to_end(update_id)
            return True

        _RECENT_UPDATE_IDS[update_id] = now
        _RECENT_UPDATE_IDS.move_to_end(update_id)
        while len(_RECENT_UPDATE_IDS) > _RECENT_UPDATE_LIMIT:
            _RECENT_UPDATE_IDS.popitem(last=False)
    return False


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
    if _mark_update_seen(update):
        logger.info("Ignoring duplicate Telegram update_id=%s", update.get("update_id"))
        return False

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
        disable_notification=bool(response.get("disable_notification", False)),
        reply_parameters=(
            {"message_id": response.get("reply_to_message_id", _message_id(update))}
            if response.get("reply_to_message_id", _message_id(update)) is not None
            else None
        ),
        message_thread_id=_message_thread_id(update),
        direct_messages_topic_id=_direct_messages_topic_id(update),
    )
    return True


def _polling_loop() -> None:
    logger.info("Starting Telegram polling loop")
    try:
        TELEGRAM_API.delete_webhook(drop_pending_updates=False)
    except Exception as exc:  # pragma: no cover - network/runtime behavior
        logger.warning(
            "Could not delete Telegram webhook before polling: %s", _redact_sensitive_text(exc)
        )

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
            safe_error = _redact_sensitive_text(exc)
            POLLING_STATE["last_error"] = safe_error
            logger.warning("Telegram polling error: %s", safe_error)
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


def _telegram_runtime_probe() -> dict[str, Any]:
    """Read-only Telegram readiness probe with a short in-process cache."""

    now = time.time()
    with _TELEGRAM_PROBE_CACHE_LOCK:
        cached = _TELEGRAM_PROBE_CACHE.get("value")
        expires_at = float(_TELEGRAM_PROBE_CACHE.get("expires_at") or 0.0)
        if isinstance(cached, dict) and expires_at > now:
            return dict(cached)

    username = SETTINGS.bot_username
    try:
        me = TELEGRAM_API.get_me()
        webhook = TELEGRAM_API.get_webhook_info()
        username = str(me.get("username") or username or "").strip().lstrip("@")
        webhook_url = str(webhook.get("url") or "").strip()
        webhook_registered = bool(webhook_url)
        polling_active = bool(
            isinstance(POLLING_STATE.get("thread"), threading.Thread)
            and POLLING_STATE["thread"].is_alive()
        )
        pending_update_count = webhook.get("pending_update_count")
        allowed_updates = webhook.get("allowed_updates")
        result = {
            "probe_ok": True,
            "bot_username": username,
            "bot_id": me.get("id"),
            "webhook_registered": webhook_registered,
            "pending_update_count": pending_update_count
            if isinstance(pending_update_count, int)
            else None,
            "allowed_updates": allowed_updates if isinstance(allowed_updates, list) else None,
            "delivery_ready": webhook_registered if SETTINGS.mode == "webhook" else polling_active,
            "delivery_mode_reason": (
                "webhook_registered"
                if SETTINGS.mode == "webhook" and webhook_registered
                else "webhook_missing"
                if SETTINGS.mode == "webhook"
                else "polling_active"
                if polling_active
                else "polling_inactive"
            ),
            "probe_error": None,
        }
    except Exception as exc:  # pragma: no cover - network/runtime behavior
        result = {
            "probe_ok": False,
            "bot_username": username,
            "bot_id": None,
            "webhook_registered": None,
            "pending_update_count": None,
            "allowed_updates": None,
            "delivery_ready": False,
            "delivery_mode_reason": "probe_failed",
            "probe_error": _redact_sensitive_text(exc),
        }

    with _TELEGRAM_PROBE_CACHE_LOCK:
        _TELEGRAM_PROBE_CACHE["value"] = dict(result)
        _TELEGRAM_PROBE_CACHE["expires_at"] = now + _TELEGRAM_PROBE_TTL_SECONDS
    return result


@app.on_event("startup")
def on_startup() -> None:
    _validate_startup_config()
    if SETTINGS.mode == "polling":
        _start_polling_thread()
    logger.info(
        "Sapphire PM bot ready (mode=%s token_source=%s)",
        SETTINGS.mode,
        SETTINGS.token_source,
    )


@app.on_event("shutdown")
def on_shutdown() -> None:
    POLLING_STOP.set()


@app.get("/health")
def health() -> dict[str, Any]:
    thread = POLLING_STATE.get("thread")
    polling_active = bool(isinstance(thread, threading.Thread) and thread.is_alive())
    telegram_probe = _telegram_runtime_probe()
    return {
        "status": "ok",
        "service": "sapphire-pm-bot",
        "mode": SETTINGS.mode,
        "token_source": SETTINGS.token_source,
        "polling_active": polling_active,
        "last_poll_error": POLLING_STATE.get("last_error"),
        "shared_polling_allowed": SETTINGS.shared_polling_allowed,
        "webhook_secret_configured": bool(SETTINGS.webhook_secret),
        "bot_username": telegram_probe.get("bot_username") or SETTINGS.bot_username,
        "supported_update_types": list(_SUPPORTED_UPDATE_TYPES),
        "telegram_delivery_ready": bool(telegram_probe.get("delivery_ready")),
        "telegram_delivery_reason": telegram_probe.get("delivery_mode_reason"),
        "telegram_probe_ok": bool(telegram_probe.get("probe_ok")),
        "telegram_probe_error": telegram_probe.get("probe_error"),
        "telegram_webhook_registered": telegram_probe.get("webhook_registered"),
        "telegram_pending_update_count": telegram_probe.get("pending_update_count"),
        "telegram_allowed_updates": telegram_probe.get("allowed_updates"),
    }


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> dict[str, Any]:
    if SETTINGS.webhook_secret:
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if secret != SETTINGS.webhook_secret:
            raise HTTPException(status_code=403, detail="invalid secret")

    update = await request.json()
    processed = process_update(update)
    return {"ok": True, "processed": processed}


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    _validate_startup_config()
    uvicorn.run("server:app", host=SETTINGS.host, port=SETTINGS.port, reload=False)
