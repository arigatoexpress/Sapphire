"""Telegram Login Widget verifier.

Validates the HMAC-SHA256 data hash that Telegram sends to your callback URL
after a user logs in via the Telegram Login Widget.

See: https://core.telegram.org/widgets/login#checking-authorization

Usage::

    from lib.telegram.login_widget import verify_telegram_login

    data = {
        "id": "123456789",
        "first_name": "Ari",
        "username": "aribs",
        "auth_date": "1713400000",
        "hash": "<hash from telegram>",
    }
    user = verify_telegram_login(data, bot_token="your:bot:token")
    # user is None if verification fails, else a TelegramUser
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class TelegramUser:
    id: int
    first_name: str
    username: str | None = None
    last_name: str | None = None
    photo_url: str | None = None
    auth_date: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "first_name": self.first_name,
            "username": self.username,
            "last_name": self.last_name,
            "photo_url": self.photo_url,
            "auth_date": self.auth_date,
        }


_MAX_AUTH_AGE_SECONDS = 86_400  # 24 hours


def verify_telegram_login(
    data: dict[str, str],
    bot_token: str | None = None,
    *,
    max_age: int = _MAX_AUTH_AGE_SECONDS,
) -> TelegramUser | None:
    """Verify Telegram Login Widget data and return a TelegramUser or None.

    Args:
        data: The form/query parameters received from the Telegram widget callback.
        bot_token: The bot token used to verify the HMAC. Reads
            ``TELEGRAM_BOT_TOKEN`` from environment if not provided.
        max_age: Reject auth_date older than this many seconds (default 24h).
    """
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("bot_token or TELEGRAM_BOT_TOKEN env var required")

    received_hash = data.get("hash", "")
    if not received_hash:
        return None

    # Build the check string: sorted key=value pairs (excluding hash)
    check_items = sorted(f"{k}={v}" for k, v in data.items() if k != "hash")
    check_string = "\n".join(check_items)

    secret = hashlib.sha256(token.encode()).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        return None

    auth_date = int(data.get("auth_date", "0"))
    if time.time() - auth_date > max_age:
        return None

    return TelegramUser(
        id=int(data.get("id", 0)),
        first_name=data.get("first_name", ""),
        username=data.get("username"),
        last_name=data.get("last_name"),
        photo_url=data.get("photo_url"),
        auth_date=auth_date,
    )


def verify_webapp_init_data(
    init_data: str,
    bot_token: str | None = None,
    *,
    max_age: int = _MAX_AUTH_AGE_SECONDS,
) -> TelegramUser | None:
    """Verify a Telegram Mini App ``initData`` string.

    Mini Apps use a *different* secret derivation than the Login Widget:

    * Login Widget:  ``secret = SHA256(bot_token)``
    * Mini App:      ``secret = HMAC_SHA256(key="WebAppData", msg=bot_token)``

    Getting that inversion wrong would accept forged sessions, so the two
    verifiers are kept as separate functions rather than sharing a branch.

    Args:
        init_data: The raw ``window.Telegram.WebApp.initData`` query string.
        bot_token: Bot token; falls back to ``TELEGRAM_BOT_TOKEN``.
        max_age: Reject ``auth_date`` older than this many seconds.

    Returns:
        A ``TelegramUser`` on success, ``None`` on any verification failure.
    """
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("bot_token or TELEGRAM_BOT_TOKEN env var required")
    if not init_data:
        return None

    from urllib.parse import parse_qsl

    try:
        pairs = parse_qsl(init_data, strict_parsing=True, keep_blank_values=True)
    except ValueError:
        return None

    fields = dict(pairs)
    received_hash = fields.get("hash", "")
    if not received_hash:
        return None

    # `hash` is always excluded; `signature` is excluded too (it belongs to
    # the third-party validation flow, not this one).
    check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(fields.items())
        if key not in {"hash", "signature"}
    )

    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        return None

    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError:
        return None
    if max_age and (time.time() - auth_date > max_age):
        return None

    import json

    try:
        user_payload = json.loads(fields.get("user", "{}"))
    except json.JSONDecodeError:
        return None
    if not isinstance(user_payload, dict) or not user_payload.get("id"):
        return None

    return TelegramUser(
        id=int(user_payload.get("id", 0)),
        first_name=str(user_payload.get("first_name", "")),
        username=user_payload.get("username"),
        last_name=user_payload.get("last_name"),
        photo_url=user_payload.get("photo_url"),
        auth_date=auth_date,
    )
