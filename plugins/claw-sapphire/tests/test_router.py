"""Tests for the task classification router."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from router import _keyword_classify, Classification


def test_t3_keywords():
    """Complex tasks should route to T3."""
    for task in [
        "Refactor the control-plane to support WebSockets",
        "Security audit of the trading module",
        "Architect the new event system",
        "Migrate from SQLite to Postgres",
        "Plan the Q2 trading strategy",
    ]:
        result = _keyword_classify(task)
        assert result.tier == "t3", f"Expected t3 for: {task}, got {result.tier}"


def test_t0_keywords():
    """Read-only tasks should route to T0."""
    for task in [
        "Explain what the Cointracker does",
        "Analyze the test coverage gaps",
        "Summarize the recent changes in Sapphire",
        "Show me the status of all repos",
        "List all open issues",
    ]:
        result = _keyword_classify(task)
        assert result.tier == "t0", f"Expected t0 for: {task}, got {result.tier}"


def test_t1_default():
    """Simple fix tasks should route to T1."""
    for task in [
        "Fix the unused import in main.py",
        "Add type hints to the notify function",
        "Update the docstring in token_governor.py",
    ]:
        result = _keyword_classify(task)
        assert result.tier == "t1", f"Expected t1 for: {task}, got {result.tier}"


def test_classification_method():
    """Keyword classifier should report method as 'keyword'."""
    result = _keyword_classify("anything")
    assert result.method == "keyword"


def test_classification_has_all_fields():
    """Classification should have tier, reason, complexity, method."""
    result = _keyword_classify("fix a bug")
    assert hasattr(result, "tier")
    assert hasattr(result, "reason")
    assert hasattr(result, "complexity")
    assert hasattr(result, "method")
