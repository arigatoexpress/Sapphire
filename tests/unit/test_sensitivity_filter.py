"""Tests for inference-proxy sensitivity classifier.

Verifies that _is_sensitive() correctly blocks sensitive content from Kimi Cloud
and does NOT block innocuous content (false positive check).

Run: /usr/local/bin/python3 -m pytest tests/unit/test_sensitivity_filter.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# We need to import _is_sensitive from the inference proxy.
# The proxy is not a package, so we add its directory to sys.path.
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "inference-proxy"))

from app import _is_sensitive  # type: ignore


def msgs(content: str) -> list[dict]:
    """Helper: wrap a single user message."""
    return [{"role": "user", "content": content}]


# ─── True positives — should be detected ──────────────────────────────────────

class TestSensitiveDetected:
    def test_api_key_field(self):
        assert _is_sensitive(msgs("my api_key is abc123"))

    def test_apikey_no_separator(self):
        assert _is_sensitive(msgs("apikey=sk-supersecretkey"))

    def test_bearer_token(self):
        assert _is_sensitive(msgs("Authorization: Bearer eyJhbGciOiJIUzI1Ni"))

    def test_jwt_token(self):
        assert _is_sensitive(msgs("Here is my JWT: eyJhbGciOi..."))

    def test_password_field(self):
        assert _is_sensitive(msgs("password: hunter2"))

    def test_passwd_field(self):
        assert _is_sensitive(msgs("set passwd to 12345"))

    def test_secret_field(self):
        assert _is_sensitive(msgs('{"secret": "top_secret_value"}'))

    def test_pem_private_key(self):
        assert _is_sensitive(msgs("-----BEGIN RSA PRIVATE KEY-----"))

    def test_openssh_private_key(self):
        assert _is_sensitive(msgs("-----BEGIN OPENSSH PRIVATE KEY-----"))

    def test_ec_private_key(self):
        assert _is_sensitive(msgs("-----BEGIN EC PRIVATE KEY-----"))

    def test_credit_card_number(self):
        assert _is_sensitive(msgs("card: 4111 1111 1111 1111"))

    def test_credit_card_dashes(self):
        assert _is_sensitive(msgs("4111-1111-1111-1111"))

    def test_ssn(self):
        assert _is_sensitive(msgs("SSN: 123-45-6789"))

    def test_routing_number(self):
        assert _is_sensitive(msgs("routing.num: 021000021"))

    # NEW: OAuth / service account patterns (MEDIUM-13 fix)
    def test_access_token(self):
        assert _is_sensitive(msgs("access_token=ya29.A0ARrdaM..."))

    def test_refresh_token(self):
        assert _is_sensitive(msgs("refresh_token: 1//0ABC..."))

    def test_id_token(self):
        assert _is_sensitive(msgs("id_token: eyJhbGci..."))

    def test_client_secret(self):
        assert _is_sensitive(msgs('{"client_secret": "GOCSPX-..."}'))

    def test_private_key_field(self):
        assert _is_sensitive(msgs('"private_key": "-----BEGIN RSA..."'))

    def test_database_url_with_creds(self):
        assert _is_sensitive(msgs("DATABASE_URL=postgres://user:pass@localhost/db"))

    def test_slack_bot_token_xoxb(self):
        assert _is_sensitive(msgs("token: xoxb-12345-67890-abcdef"))

    def test_slack_user_token_xoxp(self):
        assert _is_sensitive(msgs("xoxp-1234-5678-abcd"))


# ─── Multi-part content blocks (list format) ──────────────────────────────────

class TestContentListFormat:
    def test_sensitive_in_list_block(self):
        messages = [{"role": "user", "content": [
            {"type": "text", "text": "api_key=secret123"}
        ]}]
        assert _is_sensitive(messages)

    def test_clean_in_list_block(self):
        messages = [{"role": "user", "content": [
            {"type": "text", "text": "What is the capital of France?"}
        ]}]
        assert not _is_sensitive(messages)


# ─── True negatives — should NOT be detected ──────────────────────────────────

class TestNotSensitive:
    def test_normal_question(self):
        assert not _is_sensitive(msgs("What is the best way to learn Python?"))

    def test_trading_question(self):
        assert not _is_sensitive(msgs("What is BTC doing today?"))

    def test_code_review(self):
        assert not _is_sensitive(msgs("Can you review this Python function?"))

    def test_word_secret_in_casual_context(self):
        # "secret" is technically caught — that's intentional (conservative filter)
        # This test documents the known behavior
        result = _is_sensitive(msgs("It's a secret that pandas are cute"))
        # We accept that 'secret' is blocked — it's a conservative filter
        assert result is True  # expected false positive for "secret"

    def test_empty_messages(self):
        assert not _is_sensitive([])

    def test_empty_content(self):
        assert not _is_sensitive(msgs(""))

    def test_system_message_no_sensitive(self):
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        assert not _is_sensitive(messages)


# ─── Multi-message conversations ──────────────────────────────────────────────

class TestMultiMessage:
    def test_sensitive_in_last_message(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "My api_key is sk-abc123"},
        ]
        assert _is_sensitive(messages)

    def test_sensitive_in_middle_message(self):
        messages = [
            {"role": "user", "content": "My password is hunter2"},
            {"role": "assistant", "content": "I see"},
            {"role": "user", "content": "Now help me with something else"},
        ]
        assert _is_sensitive(messages)

    def test_all_clean_messages(self):
        messages = [
            {"role": "user", "content": "How's the market today?"},
            {"role": "assistant", "content": "BTC is up 2%"},
            {"role": "user", "content": "Should I buy?"},
        ]
        assert not _is_sensitive(messages)
