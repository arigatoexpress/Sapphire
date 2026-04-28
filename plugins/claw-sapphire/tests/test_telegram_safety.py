"""Unit tests for the Telegram operator-console safety primitives.

These exercise pure functions only — no I/O, no network, no Telegram. The
goal is to nail down the safety posture so a regression to
``_telegram_safety.py`` cannot ship without breaking these tests.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from internal import _telegram_safety as safety

# ---------------------------------------------------------------------------
# Allowlist — fail-closed.
# ---------------------------------------------------------------------------


def test_load_allowed_user_ids_empty_env(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", raising=False)
    assert safety.load_allowed_user_ids() == set()


def test_load_allowed_user_ids_parses_csv(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", "111, 222 ,333")
    assert safety.load_allowed_user_ids() == {111, 222, 333}


def test_load_allowed_user_ids_skips_invalid(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", "111,foo,222,,bar")
    assert safety.load_allowed_user_ids() == {111, 222}


def test_is_allowed_denies_none_user():
    assert safety.is_allowed(None, {111}) is False


def test_is_allowed_denies_unknown_user():
    assert safety.is_allowed(999, {111, 222}) is False


def test_is_allowed_permits_listed_user():
    assert safety.is_allowed(111, {111, 222}) is True


def test_is_allowed_denies_when_set_is_empty():
    """Empty allowlist denies everyone — fail-closed by construction."""
    assert safety.is_allowed(111, set()) is False


# ---------------------------------------------------------------------------
# Secret denylist — outgoing redaction.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "needle",
    [
        "API_KEY=sk-abc123",
        "api-key: redacted",
        "api key broken",
        "Authorization: Bearer xyz",
        "user provided password=hunter2",
        "PASSWD=root",
        "client_secret leaked",
        "private_key path",
        "access_token expired",
        "refresh-token rotated",
        "The token is sk-abcdef0123456789",
        "ghp_AAAAAAAA leaked into log",
        "AIzaSyAAAAAAAAAAAAAAAAAAAAAAA",
    ],
)
def test_secret_denylist_matches_typical_patterns(needle):
    assert safety.contains_secret(needle), f"missed: {needle!r}"


@pytest.mark.parametrize(
    "safe_text",
    [
        "everything fine",
        "balanced=up premium=down",
        "Mesh devices: 1/2 online",
        "Paper-trading signals today: 7",
        "Created PM task: stand up the bot",
        "open issue #371 ready for merge",
        # "key" / "tok" alone are not enough — denylist is keyword-anchored.
        "key insight: ship fast",
        "tokenize the input",
    ],
)
def test_secret_denylist_no_false_positives_on_normal_text(safe_text):
    assert not safety.contains_secret(safe_text), f"false positive: {safe_text!r}"


def test_redact_secrets_replaces_only_offending_lines():
    text = "user=ari\nAPI_KEY=sk-abc123\nstatus=ok\n"
    out = safety.redact_secrets(text)
    assert "user=ari" in out
    assert "status=ok" in out
    assert "sk-abc123" not in out
    assert safety.REDACTED_PLACEHOLDER in out


def test_redact_secrets_handles_empty_and_none():
    assert safety.redact_secrets("") == ""
    assert safety.redact_secrets(None) == ""  # type: ignore[arg-type]


def test_redact_secrets_preserves_clean_text():
    text = "Mesh devices: 1/2 online\nbalanced=up"
    assert safety.redact_secrets(text) == text


# ---------------------------------------------------------------------------
# Forbidden top-level commands.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cmd",
    [
        "/trade BTC long",
        "/buy 100 SPY",
        "/sell ETH",
        "/transfer funds",
        "/withdraw 1000",
        "/deposit",
        "/rotate-key telegram",
        "/rotate_key",
        "/rotate-secret all",
        "/launch missiles",
        "/deploy prod",
        "/exec ls",
        "/eval 1+1",
        "/sudo reboot",
        "/shell",
        "/bash whoami",
        "/cmd anything",
        "/ssh aribs@windows",
        "/kill-switch on",
        "/wire 10000 to bank",
        "/send-funds elsewhere",
        "/TRADE upper case still rejected",
    ],
)
def test_is_forbidden_command_rejects_dangerous_verbs(cmd):
    assert safety.is_forbidden_command(cmd), f"should reject: {cmd!r}"


@pytest.mark.parametrize(
    "cmd",
    [
        "/help",
        "/status",
        "/services",
        "/health",
        "/pm list",
        "/rag what's the latest",
        "/whoami",
        "/digest morning",
        "/routines list",
        "/routines pause sapphire-morning-briefing",
        # "trade today" embedded mid-sentence is not a command.
        "I want to trade today",
        # forbidden verb mid-command-name is allowed; only stems match.
        "/help-trade-tutorial",
    ],
)
def test_is_forbidden_command_allows_safe_or_non_command_text(cmd):
    assert not safety.is_forbidden_command(cmd), f"should allow: {cmd!r}"


def test_is_forbidden_command_handles_empty_and_none():
    assert safety.is_forbidden_command("") is False
    assert safety.is_forbidden_command(None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Live-trading tripwire.
# ---------------------------------------------------------------------------


def test_assert_no_live_trading_passes_when_flag_true():
    """Default state — flag is True → assertion passes silently."""
    assert safety.LIVE_TRADING_DISABLED_FROM_TELEGRAM is True
    safety.assert_no_live_trading()  # must not raise


def test_assert_no_live_trading_raises_if_flag_flipped(monkeypatch):
    """Flip the constant under monkeypatch and confirm the tripwire fires."""
    monkeypatch.setattr(safety, "LIVE_TRADING_DISABLED_FROM_TELEGRAM", False)
    with pytest.raises(RuntimeError, match="LIVE_TRADING_DISABLED_FROM_TELEGRAM"):
        safety.assert_no_live_trading()


# ---------------------------------------------------------------------------
# Rate limiter — sliding-window correctness.
# ---------------------------------------------------------------------------


def test_rate_limiter_allows_below_minute_cap():
    rl = safety.RateLimiter(per_minute=3, per_hour=100)
    assert rl.check(1, now=1000.0).allowed is True
    assert rl.check(1, now=1000.5).allowed is True
    assert rl.check(1, now=1001.0).allowed is True


def test_rate_limiter_blocks_at_minute_cap():
    rl = safety.RateLimiter(per_minute=2, per_hour=100)
    assert rl.check(1, now=1000.0).allowed is True
    assert rl.check(1, now=1001.0).allowed is True
    decision = rl.check(1, now=1001.5)
    assert decision.allowed is False
    assert decision.reason == "per_minute"
    assert decision.retry_after_seconds > 0


def test_rate_limiter_window_resets_after_minute():
    rl = safety.RateLimiter(per_minute=2, per_hour=100)
    rl.check(1, now=1000.0)
    rl.check(1, now=1010.0)
    # 60+ seconds later — window has rolled.
    assert rl.check(1, now=1071.0).allowed is True


def test_rate_limiter_blocks_at_hour_cap():
    rl = safety.RateLimiter(per_minute=100, per_hour=3)
    rl.check(1, now=1000.0)
    rl.check(1, now=1100.0)
    rl.check(1, now=1200.0)
    decision = rl.check(1, now=1300.0)
    assert decision.allowed is False
    assert decision.reason == "per_hour"


def test_rate_limiter_isolates_users():
    rl = safety.RateLimiter(per_minute=1, per_hour=100)
    rl.check(1, now=1000.0)
    # Different user must not be affected.
    decision = rl.check(2, now=1000.0)
    assert decision.allowed is True


def test_rate_limiter_reset_global():
    rl = safety.RateLimiter(per_minute=1, per_hour=100)
    rl.check(1, now=1000.0)
    rl.reset()
    assert rl.check(1, now=1000.5).allowed is True


def test_rate_limiter_reset_single_user():
    rl = safety.RateLimiter(per_minute=1, per_hour=100)
    rl.check(1, now=1000.0)
    rl.check(2, now=1000.0)
    rl.reset(user_id=1)
    assert rl.check(1, now=1000.5).allowed is True
    # User 2 is still capped.
    assert rl.check(2, now=1000.5).allowed is False


# ---------------------------------------------------------------------------
# Routine-name validation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "sapphire-morning-briefing",
        "factory_test_guardian",
        "x",
        "a" * 64,
    ],
)
def test_is_valid_routine_name_accepts_safe_names(name):
    assert safety.is_valid_routine_name(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "",
        "../etc/passwd",
        "name/with/slash",
        "name with space",
        "name;rm -rf /",
        "$(whoami)",
        "a" * 65,
        "../../sensitive",
    ],
)
def test_is_valid_routine_name_rejects_unsafe_names(name):
    assert safety.is_valid_routine_name(name) is False
