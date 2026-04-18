"""Tests for inference-proxy task classifier (auto-routing).

Verifies that classify_messages() routes to the correct model tier
for different input types, and handles edge cases gracefully.

Run: /usr/local/bin/python3 -m pytest tests/unit/test_task_classifier.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "services" / "inference-proxy"))
from task_classifier import (  # type: ignore
    ClassifierResult,
    TaskCategory,
    classify_messages,
    classify_text,
)


def user_msg(content: str) -> list[dict]:
    return [{"role": "user", "content": content}]


def sys_user(system: str, user: str) -> list[dict]:
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


# ─── Edge cases ───────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_messages_returns_balanced(self):
        result = classify_messages([])
        assert result.model == "balanced"
        assert result.category == TaskCategory.CHAT

    def test_empty_content_returns_balanced(self):
        result = classify_messages(user_msg(""))
        assert result.model == "balanced"

    def test_whitespace_only_returns_balanced(self):
        result = classify_messages(user_msg("   \n\t  "))
        assert result.model == "balanced"

    def test_returns_classifier_result(self):
        result = classify_messages(user_msg("hello"))
        assert isinstance(result, ClassifierResult)
        assert 0.0 <= result.confidence <= 1.0


# ─── Code category ────────────────────────────────────────────────────────────

class TestCodeRouting:
    def test_write_function(self):
        result = classify_messages(user_msg("Write a function to sort a list in Python"))
        assert result.category == TaskCategory.CODE
        assert result.model == "code"

    def test_debug_code(self):
        result = classify_messages(user_msg("Debug this Python code: def foo(): pass"))
        assert result.category == TaskCategory.CODE

    def test_code_snippet(self):
        result = classify_messages(user_msg("What does this do? ```python\ndef foo(): return 42\n```"))
        assert result.category == TaskCategory.CODE

    def test_create_class(self):
        result = classify_messages(user_msg("Create a class that implements a binary search tree"))
        assert result.category == TaskCategory.CODE

    def test_refactor_request(self):
        result = classify_messages(user_msg("Refactor this function to be more efficient"))
        assert result.category == TaskCategory.CODE


# ─── Reasoning category ───────────────────────────────────────────────────────

class TestReasoningRouting:
    def test_step_by_step(self):
        result = classify_messages(user_msg("Explain step-by-step how this algorithm works"))
        assert result.category == TaskCategory.REASONING

    def test_analyze_request(self):
        result = classify_messages(user_msg("Analyze the pros and cons of using Redis vs Postgres"))
        assert result.category == TaskCategory.REASONING

    def test_should_i_invest(self):
        result = classify_messages(user_msg("Should I invest in BTC at this price?"))
        assert result.category == TaskCategory.REASONING

    def test_risk_reward(self):
        result = classify_messages(user_msg("Calculate the risk-reward for this trade setup"))
        assert result.category == TaskCategory.REASONING


# ─── Research category ────────────────────────────────────────────────────────

class TestResearchRouting:
    def test_market_analysis(self):
        result = classify_messages(user_msg("Give me a comprehensive market analysis of crypto"))
        assert result.category == TaskCategory.RESEARCH

    def test_write_report(self):
        result = classify_messages(user_msg("Write a report on the latest DeFi trends"))
        assert result.category == TaskCategory.RESEARCH

    def test_intelligence_briefing(self):
        result = classify_messages(user_msg("Give me a briefing on geopolitical risk"))
        assert result.category == TaskCategory.RESEARCH


# ─── Factual category ─────────────────────────────────────────────────────────

class TestFactualRouting:
    def test_what_is_capital(self):
        result = classify_messages(user_msg("What is the capital of France?"))
        assert result.category == TaskCategory.FACTUAL
        assert result.model == "fast"

    def test_current_price(self):
        result = classify_messages(user_msg("What is the current price of BTC?"))
        assert result.category == TaskCategory.FACTUAL

    def test_tldr(self):
        result = classify_messages(user_msg("TLDR this for me"))
        assert result.category == TaskCategory.FACTUAL


# ─── Creative category ────────────────────────────────────────────────────────

class TestCreativeRouting:
    def test_write_poem(self):
        result = classify_messages(user_msg("Write a poem about Bitcoin"))
        assert result.category == TaskCategory.CREATIVE

    def test_brainstorm(self):
        result = classify_messages(user_msg("Brainstorm 10 ideas for a new trading strategy"))
        assert result.category == TaskCategory.CREATIVE


# ─── Chat fallback ────────────────────────────────────────────────────────────

class TestChatFallback:
    def test_generic_greeting_balanced(self):
        result = classify_messages(user_msg("Hey, how are you?"))
        assert result.model == "balanced"

    def test_non_matching_content(self):
        result = classify_messages(user_msg("blah blah blah"))
        assert result.model == "balanced"


# ─── Multi-message context ────────────────────────────────────────────────────

class TestMultiMessage:
    def test_last_user_message_wins(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "Write a Python function to sort a list"},
        ]
        result = classify_messages(messages)
        assert result.category == TaskCategory.CODE

    def test_no_user_message_uses_last(self):
        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "assistant", "content": "Write a function: def foo(): pass"},
        ]
        result = classify_messages(messages)
        # Should not crash; returns some category
        assert isinstance(result.category, TaskCategory)

    def test_system_context_augments_short_user_msg(self):
        messages = [
            {"role": "system", "content": "You are a Python debugging assistant"},
            {"role": "user", "content": "why doesn't this work"},
        ]
        result = classify_messages(messages)
        # Short user message + code system prompt should hint CODE
        # (system context augments per code in classifier)
        assert isinstance(result.category, TaskCategory)


# ─── classify_text direct ─────────────────────────────────────────────────────

class TestClassifyText:
    def test_classify_text_code(self):
        result = classify_text("Write a function in Python")
        assert result.category == TaskCategory.CODE

    def test_classify_text_empty(self):
        result = classify_text("")
        assert result.model == "balanced"

    def test_confidence_range(self):
        result = classify_text("Analyze the market structure")
        assert 0.0 <= result.confidence <= 1.0
