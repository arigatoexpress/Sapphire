"""Telegram notification tool for claw-code.

Sends messages to the Sapphire Telegram bot. Can be called directly
or invoked by Claude Dispatch scheduled tasks.

Usage:
    python -m plugins.claw-sapphire.src.tools.notify "Your message here"
    python -m plugins.claw-sapphire.src.tools.notify --priority p0 "ALERT: Something broke"
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.request
from pathlib import Path

# macOS system Python may lack updated CA certs — use permissive context for Telegram API
_SSL_CTX = ssl.create_default_context()
try:
    import certifi
    _SSL_CTX.load_verify_locations(certifi.where())
except ImportError:
    _SSL_CTX.check_hostname = False
    _SSL_CTX.verify_mode = ssl.CERT_NONE

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
    payload = json.dumps(
        {
            "chat_id": target,
            "text": formatted,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
    ).encode()

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10, context=_SSL_CTX) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return {"error": f"HTTP {e.code}: {body}"}
    except Exception as e:
        return {"error": str(e)}


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
