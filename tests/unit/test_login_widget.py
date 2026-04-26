"""Tests for lib/telegram/login_widget.py.

Verifies the HMAC-SHA256 Telegram Login Widget callback verifier — the
gate between an externally-provided form payload and a trusted
``TelegramUser`` object. Bug-for-bug compatibility matters: every code
path that returns ``None`` is a security control.
"""

from __future__ import annotations

import hashlib
import hmac
import time

import pytest

from lib.telegram.login_widget import (
    _MAX_AUTH_AGE_SECONDS,
    TelegramUser,
    verify_telegram_login,
)

_BOT_TOKEN = "1234567890:AAEtest_botToken_NotARealKey"


def _sign(data: dict[str, str], token: str = _BOT_TOKEN) -> str:
    """Compute the Telegram Login Widget hash for a payload."""
    check_items = sorted(f"{k}={v}" for k, v in data.items() if k != "hash")
    check_string = "\n".join(check_items)
    secret = hashlib.sha256(token.encode()).digest()
    return hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()


def _make_payload(*, auth_date: int | None = None, **overrides: str) -> dict[str, str]:
    auth = str(auth_date if auth_date is not None else int(time.time()))
    payload = {
        "id": "12345",
        "first_name": "Ari",
        "username": "aribs",
        "auth_date": auth,
    }
    payload.update(overrides)
    payload["hash"] = _sign(payload)
    return payload


# --- happy path ------------------------------------------------------------


def test_verify_returns_user_for_valid_payload():
    payload = _make_payload()
    user = verify_telegram_login(payload, bot_token=_BOT_TOKEN)
    assert user is not None
    assert isinstance(user, TelegramUser)
    assert user.id == 12345
    assert user.first_name == "Ari"
    assert user.username == "aribs"


def test_verify_includes_optional_fields_when_present():
    payload = _make_payload(
        last_name="Spec",
        photo_url="https://t.me/i/userpic/aribs.jpg",
    )
    user = verify_telegram_login(payload, bot_token=_BOT_TOKEN)
    assert user is not None
    assert user.last_name == "Spec"
    assert user.photo_url == "https://t.me/i/userpic/aribs.jpg"


def test_verify_leaves_optional_fields_none_when_absent():
    payload = {
        "id": "12345",
        "first_name": "Ari",
        "auth_date": str(int(time.time())),
    }
    payload["hash"] = _sign(payload)
    user = verify_telegram_login(payload, bot_token=_BOT_TOKEN)
    assert user is not None
    assert user.username is None
    assert user.last_name is None
    assert user.photo_url is None


def test_telegram_user_to_dict_round_trips_fields():
    user = TelegramUser(
        id=12345,
        first_name="Ari",
        username="aribs",
        last_name=None,
        photo_url=None,
        auth_date=1700000000,
    )
    d = user.to_dict()
    assert d["id"] == 12345
    assert d["first_name"] == "Ari"
    assert d["username"] == "aribs"
    assert d["auth_date"] == 1700000000
    assert d["last_name"] is None
    assert d["photo_url"] is None


# --- security gates --------------------------------------------------------


def test_verify_rejects_missing_hash():
    payload = _make_payload()
    payload.pop("hash")
    assert verify_telegram_login(payload, bot_token=_BOT_TOKEN) is None


def test_verify_rejects_blank_hash():
    payload = _make_payload()
    payload["hash"] = ""
    assert verify_telegram_login(payload, bot_token=_BOT_TOKEN) is None


def test_verify_rejects_tampered_hash():
    payload = _make_payload()
    payload["hash"] = "0" * 64
    assert verify_telegram_login(payload, bot_token=_BOT_TOKEN) is None


def test_verify_rejects_payload_signed_with_different_token():
    payload = _make_payload()
    # Re-sign with a different token; the verifier should reject it.
    payload["hash"] = _sign({k: v for k, v in payload.items() if k != "hash"}, token="other:token")
    assert verify_telegram_login(payload, bot_token=_BOT_TOKEN) is None


def test_verify_rejects_field_tampered_after_signing():
    payload = _make_payload()
    payload["first_name"] = "AttackerImpersonatingAri"
    assert verify_telegram_login(payload, bot_token=_BOT_TOKEN) is None


def test_verify_uses_constant_time_compare(monkeypatch):
    """`hmac.compare_digest` is the only correct equality for HMAC verification."""
    calls = {"n": 0}
    real_compare = hmac.compare_digest

    def spy(a, b):
        calls["n"] += 1
        return real_compare(a, b)

    monkeypatch.setattr("lib.telegram.login_widget.hmac.compare_digest", spy)
    payload = _make_payload()
    verify_telegram_login(payload, bot_token=_BOT_TOKEN)
    assert calls["n"] >= 1


# --- auth_date freshness ---------------------------------------------------


def test_verify_rejects_expired_auth_date():
    expired = int(time.time()) - _MAX_AUTH_AGE_SECONDS - 60
    payload = _make_payload(auth_date=expired)
    assert verify_telegram_login(payload, bot_token=_BOT_TOKEN) is None


def test_verify_accepts_recent_auth_date():
    recent = int(time.time()) - 30
    payload = _make_payload(auth_date=recent)
    assert verify_telegram_login(payload, bot_token=_BOT_TOKEN) is not None


def test_verify_accepts_explicit_max_age_window():
    """A short max_age window rejects an otherwise-valid auth_date."""
    auth = int(time.time()) - 120
    payload = _make_payload(auth_date=auth)
    assert verify_telegram_login(payload, bot_token=_BOT_TOKEN, max_age=60) is None
    assert verify_telegram_login(payload, bot_token=_BOT_TOKEN, max_age=600) is not None


def test_verify_handles_zero_auth_date_as_expired():
    """An auth_date of 0 is in 1970 and must be rejected by the freshness check."""
    payload = _make_payload(auth_date=0)
    assert verify_telegram_login(payload, bot_token=_BOT_TOKEN) is None


# --- token resolution ------------------------------------------------------


def test_verify_raises_when_no_token_provided_and_env_unset(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    payload = _make_payload()
    with pytest.raises(ValueError, match="bot_token or TELEGRAM_BOT_TOKEN"):
        verify_telegram_login(payload, bot_token=None)


def test_verify_raises_when_token_blank_and_env_blank(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    payload = _make_payload()
    with pytest.raises(ValueError):
        verify_telegram_login(payload, bot_token="")


def test_verify_falls_back_to_env_var_when_no_arg(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", _BOT_TOKEN)
    payload = _make_payload()
    user = verify_telegram_login(payload)  # no bot_token arg
    assert user is not None


def test_verify_arg_token_overrides_env_var(monkeypatch):
    """Explicit bot_token wins over the env var (so callers can rotate cleanly)."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "wrong:env:token")
    payload = _make_payload()
    user = verify_telegram_login(payload, bot_token=_BOT_TOKEN)
    assert user is not None


# --- payload shape edge cases ----------------------------------------------


def test_verify_accepts_extra_unknown_fields_in_payload():
    """Unknown fields are included in the check string per Telegram spec."""
    payload = {
        "id": "12345",
        "first_name": "Ari",
        "auth_date": str(int(time.time())),
        "lang": "en",  # unknown to TelegramUser dataclass
    }
    payload["hash"] = _sign(payload)
    user = verify_telegram_login(payload, bot_token=_BOT_TOKEN)
    # Verifier should still validate successfully (extra fields participate in HMAC).
    assert user is not None


def test_verify_rejects_when_extra_field_added_after_signing():
    """If a field is added without re-signing, the HMAC won't match."""
    payload = _make_payload()
    payload["lang"] = "en"
    assert verify_telegram_login(payload, bot_token=_BOT_TOKEN) is None


def test_verify_handles_id_as_numeric_string():
    payload = _make_payload(id="98765")
    user = verify_telegram_login(payload, bot_token=_BOT_TOKEN)
    assert user is not None
    assert user.id == 98765
