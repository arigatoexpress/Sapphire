"""Tests for ChatIntentEngine — conversational intent classification.

Verifies:
  - Fast local pattern matching (no LLM call)
  - IntentType enum completeness
  - LLM fallback classification
  - Edge cases (empty strings, very short input)
"""

import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add alpha-engine source to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "alpha-engine"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "alpha-engine", "src"))

from src.ai.chat_intent import ChatIntentEngine, IntentType


@pytest.fixture
def mock_guard():
    guard = MagicMock()
    guard.classify_intent = AsyncMock(return_value='{"intent": "general_chat", "parameters": {"reply": "Hello!"}}')
    return guard


@pytest.fixture
def engine(mock_guard):
    return ChatIntentEngine(ai_guard=mock_guard)


# ── IntentType Enum ──────────────────────────────────────────────────


class TestIntentType:
    def test_has_all_intent_types(self):
        expected = {
            "status_report", "control_trading", "media_publish",
            "media_status", "operations", "agent_question",
            "general_chat", "unknown",
        }
        actual = {e.value for e in IntentType}
        assert expected == actual

    def test_string_comparison(self):
        assert IntentType.STATUS_REPORT == "status_report"
        assert IntentType.OPERATIONS == "operations"
        assert IntentType.AGENT_QUESTION == "agent_question"


# ── Fast Local Classification ────────────────────────────────────────


class TestFastClassify:
    """Tests for _fast_classify — local regex patterns that bypass the LLM."""

    def test_empty_string(self, engine):
        assert engine._fast_classify("") is None
        assert engine._fast_classify("   ") is None

    # ── Status patterns ──

    @pytest.mark.parametrize("msg", [
        "how are we doing?",
        "how's it going",
        "status",
        "report",
        "give me an update",
        "what's the status?",
        "sitrep",
        "quick check",
        "morning update",
        "evening report",
        "daily brief",
        "where do we stand",
        "catch me up",
        "how's the portfolio",
        "how's trading?",
        "how's the P&L",
    ])
    def test_status_patterns(self, engine, msg):
        result = engine._fast_classify(msg)
        assert result is not None
        assert result["intent"] == "status_report"

    # ── Kill/halt patterns ──

    @pytest.mark.parametrize("msg", [
        "kill",
        "halt",
        "stop everything",
        "emergency stop",
        "shut it down",
        "panic",
    ])
    def test_kill_patterns(self, engine, msg):
        result = engine._fast_classify(msg)
        assert result is not None
        assert result["intent"] == "control_trading"
        assert result["parameters"]["action"] == "PAUSE"
        assert result["parameters"]["target"] == "ALL"

    # ── Resume patterns ──

    @pytest.mark.parametrize("msg", [
        "resume",
        "restart",
        "start trading",
        "bring it back",
        "go live",
        "turn it on",
    ])
    def test_resume_patterns(self, engine, msg):
        result = engine._fast_classify(msg)
        assert result is not None
        assert result["intent"] == "control_trading"
        assert result["parameters"]["action"] == "RESUME"
        assert result["parameters"]["target"] == "ALL"

    # ── Health patterns ──

    @pytest.mark.parametrize("msg", [
        "health check",
        "health",
        "check health",
        "run a diagnostic",
        "diagnostics",
        "is everything ok?",
        "anything broken?",
        "any issues?",
    ])
    def test_health_patterns(self, engine, msg):
        result = engine._fast_classify(msg)
        assert result is not None
        assert result["intent"] == "operations"
        assert result["parameters"]["action"] == "HEALTH"

    # ── Proposals patterns ──

    @pytest.mark.parametrize("msg", [
        "show proposals",
        "show me the proposals",
        "pending code",
        "any proposals?",
        "what needs my approval?",
        "what's pending?",
        "anything to review?",
    ])
    def test_proposals_patterns(self, engine, msg):
        result = engine._fast_classify(msg)
        assert result is not None
        assert result["intent"] == "operations"
        assert result["parameters"]["action"] == "PROPOSALS"

    # ── Agent status patterns ──

    @pytest.mark.parametrize("msg", [
        "agents",
        "agent status",
        "agent stats",
        "who's working?",
        "dispatch status",
        "what are the agents doing?",
    ])
    def test_agents_patterns(self, engine, msg):
        result = engine._fast_classify(msg)
        assert result is not None
        assert result["intent"] == "operations"
        assert result["parameters"]["action"] == "AGENT_STATUS"

    # ── Venue-specific pause/resume ──

    def test_pause_aster(self, engine):
        result = engine._fast_classify("pause aster")
        assert result is not None
        assert result["intent"] == "control_trading"
        assert result["parameters"]["action"] == "PAUSE"
        assert result["parameters"]["target"] == "ASTER"

    def test_resume_lighter(self, engine):
        result = engine._fast_classify("resume lighter")
        assert result is not None
        assert result["intent"] == "control_trading"
        assert result["parameters"]["action"] == "RESUME"
        assert result["parameters"]["target"] == "LIGHTER"

    # ── Non-matching messages fall through ──

    @pytest.mark.parametrize("msg", [
        "draft a tweet about BTC",
        "what do you think about ETH?",
        "approve proposal abc123",
        "hello there",
        "this is a complex multi-sentence message that shouldn't match any fast pattern",
    ])
    def test_non_matching_returns_none(self, engine, msg):
        result = engine._fast_classify(msg)
        assert result is None


# ── LLM Classification ───────────────────────────────────────────────


class TestLLMClassification:
    @pytest.mark.asyncio
    async def test_llm_fallback_for_complex_message(self, engine, mock_guard):
        mock_guard.classify_intent = AsyncMock(
            return_value='{"intent": "media_publish", "parameters": {"topic": "BTC ATH", "channels": ["twitter"]}}'
        )
        result = await engine.analyze("draft a tweet about BTC hitting a new all time high")
        assert result["intent"] == "media_publish"
        assert "BTC" in result["parameters"]["topic"]

    @pytest.mark.asyncio
    async def test_llm_strips_markdown_code_blocks(self, engine, mock_guard):
        mock_guard.classify_intent = AsyncMock(
            return_value='```json\n{"intent": "operations", "parameters": {"action": "HEALTH"}}\n```'
        )
        result = await engine.analyze("run diagnostics on the whole system")
        assert result["intent"] == "operations"
        assert result["parameters"]["action"] == "HEALTH"

    @pytest.mark.asyncio
    async def test_llm_error_returns_general_chat(self, engine, mock_guard):
        mock_guard.classify_intent = AsyncMock(side_effect=Exception("API error"))
        result = await engine.analyze("some message")
        assert result["intent"] == "general_chat"
        assert "reply" in result["parameters"]

    @pytest.mark.asyncio
    async def test_llm_empty_response_returns_general_chat(self, engine, mock_guard):
        mock_guard.classify_intent = AsyncMock(return_value="")
        result = await engine.analyze("hello")
        # "hello" doesn't match fast patterns, so it goes to LLM
        # LLM returns empty → fallback to general_chat
        assert result["intent"] == "general_chat"

    @pytest.mark.asyncio
    async def test_llm_invalid_json_returns_general_chat(self, engine, mock_guard):
        mock_guard.classify_intent = AsyncMock(return_value="not valid json at all")
        result = await engine.analyze("something complex")
        assert result["intent"] == "general_chat"

    @pytest.mark.asyncio
    async def test_llm_invalid_intent_defaults_to_general_chat(self, engine, mock_guard):
        mock_guard.classify_intent = AsyncMock(
            return_value='{"intent": "bogus_intent", "parameters": {}}'
        )
        result = await engine.analyze("something unusual")
        assert result["intent"] == "general_chat"

    @pytest.mark.asyncio
    async def test_fast_pattern_skips_llm(self, engine, mock_guard):
        """Fast patterns should NOT call the LLM."""
        result = await engine.analyze("status")
        assert result["intent"] == "status_report"
        mock_guard.classify_intent.assert_not_called()

    @pytest.mark.asyncio
    async def test_agent_question_from_llm(self, engine, mock_guard):
        mock_guard.classify_intent = AsyncMock(
            return_value='{"intent": "agent_question", "parameters": {"question": "should we add SOL?", "agent": "SAPPHIRE"}}'
        )
        result = await engine.analyze("should we add SOL to our portfolio?")
        assert result["intent"] == "agent_question"
        assert result["parameters"]["agent"] == "SAPPHIRE"

    @pytest.mark.asyncio
    async def test_operations_from_llm(self, engine, mock_guard):
        mock_guard.classify_intent = AsyncMock(
            return_value='{"intent": "operations", "parameters": {"action": "ROADMAP_SYNC"}}'
        )
        result = await engine.analyze("sync up the roadmap please")
        assert result["intent"] == "operations"
        assert result["parameters"]["action"] == "ROADMAP_SYNC"
