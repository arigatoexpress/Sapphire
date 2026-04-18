"""
Kimi Claw Telegram relay — T4 inference fallback via @rarikimibot.

Architecture (relay-reader bot):
  1. kimi_relay sends the query to the relay group using NemotronRariBot's token.
     Kimi Claw (@rarikimibot) sees this and responds.
  2. kimi_relay polls getUpdates on a dedicated relay-reader bot (RELAY_READER_TOKEN)
     which sits in the same group and can see all messages including @rarikimibot's.
  3. The read loop filters for messages from @rarikimibot in KIMI_RELAY_CHAT_ID and
     returns the first matching response.

Why a third bot?
  - NemotronRariBot's getUpdates are consumed by the hermes gateway.
  - @rarikimibot's getUpdates are consumed by Kimi Claw's own polling loop.
  - The relay-reader bot is idle — its getUpdates stream is exclusively ours to consume.

Environment variables (loaded from ~/.hermes/.env):
    TELEGRAM_BOT_TOKEN   — NemotronRariBot token (sends to the group)
    RELAY_READER_TOKEN   — relay-reader bot token (reads @rarikimibot responses)
    KIMI_RELAY_CHAT_ID   — numeric group chat ID (negative integer)

Usage:
    from kimi_relay import relay_query
    response_text = relay_query("Analyse ETH/BTC over 30 days")
"""

import json
import os
import ssl
import threading
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_ENV_FILE = Path.home() / ".hermes" / ".env"


def _load_env() -> None:
    """Load .hermes/.env into os.environ if keys are missing."""
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key not in os.environ:
                os.environ[key] = val.strip()


_load_env()

# NemotronRariBot — sends the query; Kimi Claw can see it
SEND_TOKEN: str = os.environ.get("TELEGRAM_BOT_TOKEN", "")
# relay-reader bot — sits in group, reads @rarikimibot responses
READER_TOKEN: str = os.environ.get("RELAY_READER_TOKEN", "")
RELAY_CHAT_ID: str = os.environ.get("KIMI_RELAY_CHAT_ID", "")

RESPONSE_TIMEOUT: int = 120
POLL_INTERVAL: float = 1.0

OUTBOUND_TAG = "[SAPPHIRE→KIMI]"
KIMI_MENTION = "@rarikimibot"  # must be @mentioned so Kimi Claw's privacy-mode bot sees it
KIMI_BOT_ID = 7950001873  # @rarikimibot's numeric user ID

# Serialise concurrent callers so the read loop can't cross-match responses.
_relay_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Telegram helpers
# ---------------------------------------------------------------------------


def _tg(token: str, method: str, **params) -> dict:
    """Call a Telegram Bot API method. Returns parsed JSON dict."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
        return json.loads(r.read())


def _send_message(text: str) -> int:
    """Send a message to RELAY_CHAT_ID via NemotronRariBot. Returns message_id."""
    if not SEND_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set — cannot send relay query")
    if not RELAY_CHAT_ID:
        raise RuntimeError("KIMI_RELAY_CHAT_ID not set — cannot send relay query")
    resp = _tg(SEND_TOKEN, "sendMessage", chat_id=RELAY_CHAT_ID, text=text)
    if not resp.get("ok"):
        raise RuntimeError(f"sendMessage failed: {resp.get('description')}")
    return resp["result"]["message_id"]


# ---------------------------------------------------------------------------
# Response polling via relay-reader bot
# ---------------------------------------------------------------------------


def _get_initial_offset() -> int:
    """Return offset one past the latest update so we skip stale messages."""
    try:
        result = _tg(READER_TOKEN, "getUpdates", limit=1, timeout=0)
        updates = result.get("result", [])
        if updates:
            return updates[-1]["update_id"] + 1
    except Exception:
        pass
    return 0


def _poll_for_response(req_id: str, offset: int, deadline: float) -> str | None:
    """Poll relay-reader bot's getUpdates for @rarikimibot's response."""
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        long_poll_secs = min(int(remaining), 3)
        if long_poll_secs <= 0:
            break
        try:
            updates = _tg(
                READER_TOKEN,
                "getUpdates",
                offset=offset,
                limit=10,
                timeout=long_poll_secs,
            )
        except Exception:
            time.sleep(POLL_INTERVAL)
            continue

        for u in updates.get("result", []):
            offset = u["update_id"] + 1
            msg = u.get("message", {})
            chat_id = msg.get("chat", {}).get("id")
            sender_id = msg.get("from", {}).get("id")
            text = (msg.get("text") or "").strip()

            if sender_id == KIMI_BOT_ID and str(chat_id) == str(RELAY_CHAT_ID) and text:
                return text

    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def relay_query(query: str, timeout: int = RESPONSE_TIMEOUT) -> str:
    """
    Send *query* to @rarikimibot via the relay group and return its response.

    Flow:
      1. Snapshot the current getUpdates offset (skip old messages).
      2. Send the query as NemotronRariBot → Kimi Claw responds.
      3. Poll relay-reader bot's getUpdates for a message from @rarikimibot
         in the relay group chat.

    The _relay_lock ensures only one query is in-flight at a time.

    Raises RuntimeError on timeout or misconfiguration.
    """
    if not SEND_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set — cannot use Kimi relay")
    if not READER_TOKEN:
        raise RuntimeError("RELAY_READER_TOKEN not set — cannot use Kimi relay")
    if not RELAY_CHAT_ID:
        raise RuntimeError("KIMI_RELAY_CHAT_ID not set — cannot use Kimi relay")

    req_id = uuid.uuid4().hex[:8]

    with _relay_lock:
        # 1. Snapshot offset BEFORE sending so we don't miss an instant reply
        offset = _get_initial_offset()

        # 2. Send the query (@mention required for privacy-mode delivery)
        tagged = f"[REQ-{req_id}] {KIMI_MENTION} {OUTBOUND_TAG} {query}"
        _send_message(tagged)

        # 3. Poll relay-reader bot for @rarikimibot's response
        deadline = time.monotonic() + timeout
        response = _poll_for_response(req_id, offset, deadline)

        if response is not None:
            if len(response) > 16000:
                response = response[:16000] + "\n…[truncated]"
            return response

    raise RuntimeError(
        f"Kimi relay timeout after {timeout}s — @rarikimibot did not respond "
        f"(req_id={req_id}). Check that:\n"
        f"  • RELAY_READER_TOKEN is set (~/.hermes/.env)\n"
        f"  • relay-reader bot is a member of the relay group ({RELAY_CHAT_ID})\n"
        f"  • @rarikimibot is active in the relay group"
    )


# ---------------------------------------------------------------------------
# CLI test harness
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Hello from Sapphire — are you online?"
    print(f"Sending to relay group as NemotronRariBot: {query!r}")
    print(f"Relay chat: {RELAY_CHAT_ID}")
    print(f"Reader bot configured: {'yes' if READER_TOKEN else 'NO — set RELAY_READER_TOKEN'}")
    print(f"Polling via relay-reader bot every ~1s")
    try:
        response = relay_query(query, timeout=60)
        print(f"\nResponse:\n{response}")
    except RuntimeError as e:
        print(f"\nError: {e}")
        sys.exit(1)
