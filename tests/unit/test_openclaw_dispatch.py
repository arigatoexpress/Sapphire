"""Tests for OpenClaw Gateway Dispatcher.

Verifies:
  - Dispatcher initializes correctly from env vars
  - Disabled state when credentials missing
  - dispatch_instruction builds correct payload and handles responses
  - dispatch_session_decision forwards decisions
  - status() returns health info
  - Error handling for network failures
"""

import os
import sys
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add alpha-engine source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "alpha-engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "alpha-engine", "src"))

from openclaw_dispatch import OpenClawDispatcher


# ── Helper: build properly nested async context managers ─────────────

class _FakeResponse:
    """Minimal aiohttp response mock supporting async context manager."""
    def __init__(self, status=200, body="ok"):
        self.status = status
        self._body = body
    async def text(self):
        return self._body
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass

class _FakeSession:
    """Minimal aiohttp ClientSession mock supporting async context manager."""
    def __init__(self, response):
        self._response = response
        self.post_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self._response

    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass


class _ErrorSession:
    """Session that raises on post."""
    def __init__(self, exc):
        self._exc = exc
    def post(self, *args, **kwargs):
        raise self._exc
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass


# ── Initialization Tests ──────────────────────────────────────────────


class TestOpenClawDispatcherInit:
    def test_default_disabled_without_token(self):
        """Dispatcher is disabled when no token is set."""
        with patch.dict(os.environ, {"OPENCLAW_GATEWAY_TOKEN": ""}, clear=False):
            d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="")
            assert not d.enabled

    def test_enabled_with_credentials(self):
        d = OpenClawDispatcher(
            gateway_url="http://localhost:18789",
            gateway_token="test-token-123",
        )
        assert d.enabled
        assert d.gateway_url == "http://localhost:18789"

    def test_url_trailing_slash_stripped(self):
        d = OpenClawDispatcher(
            gateway_url="http://localhost:18789/",
            gateway_token="token",
        )
        assert d.gateway_url == "http://localhost:18789"

    def test_env_var_fallback(self):
        with patch.dict(os.environ, {
            "OPENCLAW_GATEWAY_URL": "http://test:9999",
            "OPENCLAW_GATEWAY_TOKEN": "env-token",
        }):
            d = OpenClawDispatcher()
            assert d.gateway_url == "http://test:9999"
            assert d.gateway_token == "env-token"
            assert d.enabled

    def test_scope_defaults(self):
        d = OpenClawDispatcher(gateway_url="http://x", gateway_token="t")
        assert "arigatoexpress/Sapphire" in d.allowed_repo_scope
        assert "sapphire-479610" in d.allowed_project_scope

    def test_initial_counters(self):
        d = OpenClawDispatcher(gateway_url="http://x", gateway_token="t")
        assert d._dispatch_count == 0
        assert d._last_dispatch_at == 0.0
        assert d._last_error == ""


# ── Dispatch Instruction Tests ────────────────────────────────────────


class TestDispatchInstruction:
    @pytest.mark.asyncio
    async def test_disabled_returns_not_dispatched(self):
        d = OpenClawDispatcher(gateway_url="http://x", gateway_token="")
        result = await d.dispatch_instruction("OBSIDIAN", "test instruction")
        assert not result["dispatched"]
        assert result["reason"] == "gateway_not_configured"

    @pytest.mark.asyncio
    async def test_successful_dispatch(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=200)
        fake_session = _FakeSession(fake_resp)

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                result = await d.dispatch_instruction(
                    agent_id="OBSIDIAN",
                    instruction="Run maintenance cycle",
                    trigger="scheduled_maintenance",
                )
        assert result["dispatched"]
        assert "session_key" in result
        assert result["agent"] == "OBSIDIAN"
        assert d._dispatch_count == 1
        assert len(fake_session.post_calls) == 1

    @pytest.mark.asyncio
    async def test_dispatch_202_accepted(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=202)
        fake_session = _FakeSession(fake_resp)

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                result = await d.dispatch_instruction("OBSIDIAN", "test")
        assert result["dispatched"]

    @pytest.mark.asyncio
    async def test_gateway_error_response(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=500, body="Internal Server Error")
        fake_session = _FakeSession(fake_resp)

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                result = await d.dispatch_instruction("OBSIDIAN", "test")
        assert not result["dispatched"]
        assert "gateway_error_500" in result["reason"]
        assert d._last_error != ""

    @pytest.mark.asyncio
    async def test_network_exception(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        err_session = _ErrorSession(ConnectionError("Connection refused"))

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=err_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                result = await d.dispatch_instruction("OBSIDIAN", "test")
        assert not result["dispatched"]
        assert result["reason"] == "dispatch_exception"

    @pytest.mark.asyncio
    async def test_session_key_generation(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=200)
        fake_session = _FakeSession(fake_resp)

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                result = await d.dispatch_instruction("OBSIDIAN", "test")
        assert len(result["session_key"]) == 16  # sha256 truncated to 16

    @pytest.mark.asyncio
    async def test_payload_includes_context(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=200)
        fake_session = _FakeSession(fake_resp)

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                await d.dispatch_instruction(
                    "OBSIDIAN", "test",
                    context={"extra": "data"},
                    allow_code_changes=True,
                    trigger="manual",
                )
        _, kwargs = fake_session.post_calls[0]
        payload = kwargs["json"]
        # OpenAI-compatible format
        assert payload["model"] == "openclaw"
        assert payload["stream"] is False
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"
        assert payload["messages"][1]["content"] == "test"
        # System message contains context metadata
        system_content = payload["messages"][0]["content"]
        assert "OBSIDIAN" in system_content
        assert "allow_code_changes" in system_content
        assert "manual" in system_content
        assert "extra" in system_content
        # Agent ID header
        headers = kwargs.get("headers", {})
        assert headers.get("x-openclaw-agent-id") == "obsidian"

    @pytest.mark.asyncio
    async def test_uses_chat_completions_endpoint(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=200)
        fake_session = _FakeSession(fake_resp)

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                await d.dispatch_instruction("OBSIDIAN", "test")
        url, _ = fake_session.post_calls[0]
        assert url == "http://localhost:18789/v1/chat/completions"

    @pytest.mark.asyncio
    async def test_default_gateway_url_is_cloud_run(self):
        """Default URL should point to Cloud Run when no env var is set."""
        with patch.dict(os.environ, {"OPENCLAW_GATEWAY_URL": ""}, clear=False):
            d = OpenClawDispatcher(gateway_token="tok")
            assert "us-central1.run.app" in d.gateway_url


# ── Session Decision Tests ────────────────────────────────────────────


class TestDispatchSessionDecision:
    @pytest.mark.asyncio
    async def test_disabled_returns_not_dispatched(self):
        d = OpenClawDispatcher(gateway_url="http://x", gateway_token="")
        result = await d.dispatch_session_decision("key123", "APPROVE")
        assert not result["dispatched"]

    @pytest.mark.asyncio
    async def test_successful_decision(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=200)
        fake_session = _FakeSession(fake_resp)

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                result = await d.dispatch_session_decision("key123", "APPROVE", note="LGTM")
        assert result["dispatched"]
        assert result["session_key"] == "key123"

    @pytest.mark.asyncio
    async def test_decision_error(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=400, body="Bad request")
        fake_session = _FakeSession(fake_resp)

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                result = await d.dispatch_session_decision("key123", "APPROVE")
        assert not result["dispatched"]


# ── Status Tests ──────────────────────────────────────────────────────


class TestDispatcherStatus:
    def test_status_returns_all_fields(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        status = d.status()
        assert status["enabled"] is True
        assert status["gateway_url"] == "http://localhost:18789"
        assert status["token_configured"] is True
        assert status["dispatch_count"] == 0
        assert "allowed_repo_scope" in status
        assert "allowed_project_scope" in status

    def test_status_disabled(self):
        d = OpenClawDispatcher(gateway_url="", gateway_token="")
        status = d.status()
        assert status["enabled"] is False
        assert status["token_configured"] is False
