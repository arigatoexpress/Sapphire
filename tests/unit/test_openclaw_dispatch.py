"""Tests for OpenClaw Gateway Dispatcher.

Verifies:
  - Dispatcher initializes correctly from env vars
  - Disabled state when credentials missing
  - dispatch_instruction builds correct payload (fire-and-forget pattern)
  - Background task handles responses and errors
  - dispatch_session_decision forwards decisions
  - status() returns health info
  - Error handling for network failures
"""

import asyncio
import os
import sys
from unittest.mock import patch

import pytest

# Add alpha-engine source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "alpha-engine"))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "alpha-engine", "src")
)

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
        with patch.dict(
            os.environ,
            {
                "OPENCLAW_GATEWAY_URL": "http://test:9999",
                "OPENCLAW_GATEWAY_TOKEN": "env-token",
            },
        ):
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
                # Fire-and-forget: let the background task complete
                await asyncio.sleep(0)
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
                await asyncio.sleep(0)
        assert result["dispatched"]

    @pytest.mark.asyncio
    async def test_gateway_error_response(self):
        """Fire-and-forget: dispatch returns True immediately; error logged in background."""
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=500, body="Internal Server Error")
        fake_session = _FakeSession(fake_resp)

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                result = await d.dispatch_instruction("OBSIDIAN", "test")
                await asyncio.sleep(0)
        # Fire-and-forget: always returns dispatched=True
        assert result["dispatched"]
        # But the background task records the error
        assert d._last_error != ""
        assert "500" in d._last_error

    @pytest.mark.asyncio
    async def test_network_exception(self):
        """Fire-and-forget: dispatch returns True; network error recorded in background."""
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        err_session = _ErrorSession(ConnectionError("Connection refused"))

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=err_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                result = await d.dispatch_instruction("OBSIDIAN", "test")
                await asyncio.sleep(0)
        # Fire-and-forget: always returns dispatched=True
        assert result["dispatched"]
        # Background task records the error
        assert "ConnectionError" in d._last_error

    @pytest.mark.asyncio
    async def test_session_key_generation(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=200)
        fake_session = _FakeSession(fake_resp)

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                result = await d.dispatch_instruction("OBSIDIAN", "test")
                await asyncio.sleep(0)
        assert len(result["session_key"]) == 16  # sha256 truncated to 16

    @pytest.mark.asyncio
    async def test_payload_includes_context(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=200)
        fake_session = _FakeSession(fake_resp)

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                await d.dispatch_instruction(
                    "OBSIDIAN",
                    "test",
                    context={"extra": "data"},
                    allow_code_changes=True,
                    trigger="manual",
                )
                await asyncio.sleep(0)
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
                await asyncio.sleep(0)
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


# ── Multi-Agent Routing Tests ────────────────────────────────────────


class TestMultiAgentRouting:
    """Verify all three agents can be dispatched and routed correctly."""

    @pytest.mark.asyncio
    async def test_dispatch_to_obsidian(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=200)
        fake_session = _FakeSession(fake_resp)

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                result = await d.dispatch_instruction("OBSIDIAN", "test")
                await asyncio.sleep(0)
        assert result["dispatched"]
        assert result["agent"] == "OBSIDIAN"
        _, kwargs = fake_session.post_calls[0]
        assert kwargs["headers"]["x-openclaw-agent-id"] == "obsidian"

    @pytest.mark.asyncio
    async def test_dispatch_to_emerald(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=200)
        fake_session = _FakeSession(fake_resp)

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                result = await d.dispatch_instruction("EMERALD", "review code quality")
                await asyncio.sleep(0)
        assert result["dispatched"]
        assert result["agent"] == "EMERALD"
        _, kwargs = fake_session.post_calls[0]
        assert kwargs["headers"]["x-openclaw-agent-id"] == "emerald"
        assert "EMERALD" in kwargs["json"]["messages"][0]["content"]

    @pytest.mark.asyncio
    async def test_dispatch_to_sapphire(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=200)
        fake_session = _FakeSession(fake_resp)

        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                result = await d.dispatch_instruction("SAPPHIRE", "security audit")
                await asyncio.sleep(0)
        assert result["dispatched"]
        assert result["agent"] == "SAPPHIRE"
        _, kwargs = fake_session.post_calls[0]
        assert kwargs["headers"]["x-openclaw-agent-id"] == "sapphire"
        assert "SAPPHIRE" in kwargs["json"]["messages"][0]["content"]

    @pytest.mark.asyncio
    async def test_all_agents_smoke(self):
        """Simulate a smoke test dispatching to all 3 agents."""
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        fake_resp = _FakeResponse(status=200)
        fake_session = _FakeSession(fake_resp)

        agents = ["OBSIDIAN", "EMERALD", "SAPPHIRE"]
        results = []
        with patch("openclaw_dispatch.aiohttp.ClientSession", return_value=fake_session):
            with patch("openclaw_dispatch.aiohttp.ClientTimeout"):
                for agent in agents:
                    result = await d.dispatch_instruction(
                        agent, "health ping", trigger="smoke_test"
                    )
                    results.append(result)
                # Let all background tasks complete
                await asyncio.sleep(0)

        assert all(r["dispatched"] for r in results)
        assert d._dispatch_count == 3
        assert len(fake_session.post_calls) == 3
        # Verify each call routed to the right agent
        for i, agent in enumerate(agents):
            _, kwargs = fake_session.post_calls[i]
            assert kwargs["headers"]["x-openclaw-agent-id"] == agent.lower()

    @pytest.mark.asyncio
    async def test_system_context_includes_agent_identity(self):
        d = OpenClawDispatcher(gateway_url="http://localhost:18789", gateway_token="tok")
        ctx = d._build_system_context(
            "EMERALD",
            context={"task": "code_review"},
            allow_code_changes=True,
            trigger="scheduled_improvement",
        )
        assert "EMERALD" in ctx
        assert "code_review" in ctx
        assert "scheduled_improvement" in ctx
        assert "allow_code_changes" in ctx
