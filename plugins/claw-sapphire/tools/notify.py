"""Operator-reviewed Telegram drafts via NemotronRariBot for claw-code.

Creates PM-bot-compatible local draft records with priority tags (p0-p3).
Called directly by scripts or invoked by scheduled tasks. Live Telegram sends are
available only through an explicit break-glass environment flag.

Usage:
    python3 notify.py "Your message here"
    python3 notify.py --priority p0 "ALERT: Something broke"
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from importlib import util as importlib_util
from pathlib import Path
from types import ModuleType

# Telegram bot tokens travel in the URL path — MITM-ing this call leaks the
# bot credentials. Always verify the server certificate. We prefer certifi's
# bundle when available (macOS system Python can lag on CAs) and fall back to
# the stock system store, but we do NOT disable verification.
_SSL_CTX = ssl.create_default_context()
try:
    import certifi

    _SSL_CTX.load_verify_locations(certifi.where())
except ImportError:
    pass

# Secret locations (checked in order)
SECRET_PATHS = [
    Path.home() / ".config" / "sapphire-secrets" / "telegram_bot_token",
    Path.home() / ".config" / "sapphire" / "telegram_bot_token",
]
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DRAFT_QUEUE_PATH = Path.home() / ".cache" / "sapphire" / "telegram" / "pm_bot_drafts.jsonl"
DISABLED_VALUES = {"0", "false", "no", "off"}

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from lib.telegram.draft_queue import append_draft, build_draft  # noqa: E402
except ModuleNotFoundError:
    _DRAFT_QUEUE_MODULE_PATH = REPO_ROOT / "lib" / "telegram" / "draft_queue.py"
    _DRAFT_QUEUE_SPEC = importlib_util.spec_from_file_location(
        "sapphire_telegram_draft_queue",
        _DRAFT_QUEUE_MODULE_PATH,
    )
    if _DRAFT_QUEUE_SPEC is None or _DRAFT_QUEUE_SPEC.loader is None:
        raise
    _DRAFT_QUEUE_MODULE = importlib_util.module_from_spec(_DRAFT_QUEUE_SPEC)
    sys.modules.setdefault("sapphire_telegram_draft_queue", _DRAFT_QUEUE_MODULE)
    _DRAFT_QUEUE_SPEC.loader.exec_module(_DRAFT_QUEUE_MODULE)
    if not isinstance(_DRAFT_QUEUE_MODULE, ModuleType):
        raise
    append_draft = _DRAFT_QUEUE_MODULE.append_draft
    build_draft = _DRAFT_QUEUE_MODULE.build_draft


def _env_enabled(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() not in DISABLED_VALUES


def _draft_queue_path() -> Path:
    return Path(
        os.getenv("SAPPHIRE_NOTIFY_DRAFT_QUEUE_PATH", str(DEFAULT_DRAFT_QUEUE_PATH))
    ).expanduser()


def _live_telegram_enabled() -> bool:
    return _env_enabled("SAPPHIRE_NOTIFY_TELEGRAM_LIVE", default=False)


def _draft_queue_enabled() -> bool:
    return _env_enabled("SAPPHIRE_NOTIFY_DRAFT_QUEUE_ENABLED", default=True)


def get_bot_token() -> str | None:
    """Resolve Telegram bot token from secrets or environment."""
    # Environment first
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if token:
        return token.strip()

    # File-based secrets
    for path in SECRET_PATHS:
        if path.exists():
            return path.read_text().strip()

    # Check .env files in Sapphire repo
    env_path = Path.home() / "Code" / "Sapphire" / "services" / "control-plane" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")

    return None


def get_chat_id() -> str | None:
    """Resolve the target Telegram chat ID."""
    chat_id = (
        os.environ.get("TELEGRAM_CHAT_ID")
        or os.environ.get("ALLOWED_TELEGRAM_CHAT_IDS", "").split(",")[0].strip()
    )
    if chat_id:
        return chat_id

    # Check secrets
    for prefix in [
        Path.home() / ".config" / "sapphire-secrets",
        Path.home() / ".config" / "sapphire",
    ]:
        path = prefix / "telegram_chat_id"
        if path.exists():
            return path.read_text().strip()

    return None


def send_telegram_message(
    message: str,
    priority: str = "p1",
    bot_token: str | None = None,
    chat_id: str | None = None,
) -> dict:
    """Queue an operator-reviewed Telegram draft, or send live behind opt-in.

    Args:
        message: The message text (supports Markdown).
        priority: p0 (immediate), p1 (normal), p2 (low), p3 (informational).
        bot_token: Override bot token.
        chat_id: Override chat ID.

    Returns:
        Draft queue response, live API response, or error dict.
    """
    # Format with priority prefix
    prefix_map = {"p0": "🚨", "p1": "📋", "p2": "ℹ️", "p3": "📰"}
    prefix = prefix_map.get(priority, "📋")
    formatted = f"{prefix} *Sapphire OS*\n\n{message}"

    if os.environ.get("TELEGRAM_DRY_RUN", "").strip().lower() in {"1", "true", "yes", "on"}:
        return {
            "ok": True,
            "delivery_mode": "dry_run",
            "method": "sendMessage",
            "text_len": len(formatted),
        }

    if not _live_telegram_enabled():
        return _queue_notify_draft(formatted, priority)

    token = bot_token or get_bot_token()
    target = chat_id or get_chat_id()

    if not token:
        return {"error": "No TELEGRAM_BOT_TOKEN found in env or secrets"}
    if not target:
        return {"error": "No TELEGRAM_CHAT_ID found in env or secrets"}

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    def _post(parse_mode: str | None) -> dict:
        body = {
            "chat_id": target,
            "text": formatted,
            "disable_web_page_preview": True,
        }
        if parse_mode:
            body["parse_mode"] = parse_mode
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as resp:  # nosec B310 - fixed HTTPS Telegram API URL.
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode() if e.fp else ""
            return {"error": f"HTTP {e.code}: {err_body}", "_http_code": e.code, "_body": err_body}
        except Exception as e:
            return {"error": str(e)}

    result = _post("Markdown")
    # Telegram returns 400 with "can't parse entities" when a stray _, *, or `
    # breaks formatting — fall back to plain text so the message still lands.
    if result.get("_http_code") == 400 and "parse entities" in result.get("_body", ""):
        result = _post(None)
    result.pop("_http_code", None)
    result.pop("_body", None)
    return result


def _queue_notify_draft(message: str, priority: str) -> dict:
    if not _draft_queue_enabled():
        return {
            "ok": True,
            "delivery_mode": "disabled",
            "external_side_effect": False,
        }

    draft = build_draft(
        kind="sapphire_notify",
        topic="ops" if priority in {"p0", "p1", "p2"} else "digest",
        body=message,
        source_ids=(f"sapphire_notify:{priority}",),
        provenance_refs=("plugins/claw-sapphire/tools/notify.py",),
        created_by="sapphire-notify",
        requires_confirmation=True,
        metadata={
            "priority": priority,
            "external_side_effect": False,
            "live_telegram_enabled": False,
        },
    )
    target = append_draft(_draft_queue_path(), draft)
    return {
        "ok": True,
        "delivery_mode": "draft",
        "draft_id": draft.draft_id,
        "draft_queue_path": str(target),
        "external_side_effect": False,
    }


def send_alert(message: str, priority: str = "p1") -> dict:
    """Shared alert helper for internal Sapphire tools."""
    return send_telegram_message(message, priority=priority)


def run(message: str, priority: str = "p1") -> str:
    """Tool entry point for claw-code."""
    result = send_telegram_message(message, priority)
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Send Sapphire Telegram notification")
    parser.add_argument("message", help="Message to send")
    parser.add_argument("--priority", default="p1", choices=["p0", "p1", "p2", "p3"])
    args = parser.parse_args()

    print(run(args.message, args.priority))
