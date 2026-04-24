"""Telegram alerts via NemotronRariBot for claw-code.

Sends messages to the Sapphire Telegram bot with priority tags (p0-p3).
Called directly by scripts or invoked by scheduled tasks.

Usage:
    python3 notify.py "Your message here"
    python3 notify.py --priority p0 "ALERT: Something broke"
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path

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
    chat_id = os.environ.get("TELEGRAM_CHAT_ID") or os.environ.get(
        "ALLOWED_TELEGRAM_CHAT_IDS", ""
    ).split(",")[0].strip()
    if chat_id:
        return chat_id

    # Check secrets
    for prefix in [Path.home() / ".config" / "sapphire-secrets", Path.home() / ".config" / "sapphire"]:
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
    """Send a message via the Telegram Bot API.

    Args:
        message: The message text (supports Markdown).
        priority: p0 (immediate), p1 (normal), p2 (low).
        bot_token: Override bot token.
        chat_id: Override chat ID.

    Returns:
        API response dict or error dict.
    """
    token = bot_token or get_bot_token()
    target = chat_id or get_chat_id()

    if not token:
        return {"error": "No TELEGRAM_BOT_TOKEN found in env or secrets"}
    if not target:
        return {"error": "No TELEGRAM_CHAT_ID found in env or secrets"}

    # Format with priority prefix
    prefix_map = {"p0": "🚨", "p1": "📋", "p2": "ℹ️"}
    prefix = prefix_map.get(priority, "📋")
    formatted = f"{prefix} *Sapphire OS*\n\n{message}"

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
            with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as resp:
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
    parser.add_argument("--priority", default="p1", choices=["p0", "p1", "p2"])
    args = parser.parse_args()

    print(run(args.message, args.priority))
