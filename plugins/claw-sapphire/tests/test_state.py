"""Tests for persistent factory state."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))
# Import tool functions directly
sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import state as state_tool

sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))


def test_record_and_skip():
    """Record issue, fail attempts, check backoff."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = Path(f.name)

    with patch.object(state_tool, "STATE_PATH", tmp):
        # Record a new issue
        issue = state_tool.record_issue("Sapphire", "lint_error", "main.py", "unused import os")
        iid = issue["issue_id"]
        assert issue["status"] == "open"

        # First failure — no backoff yet
        state_tool.record_attempt(iid, "t0", "failed", "model couldn't fix it")
        skip = state_tool.should_skip(iid)
        assert not skip["skip"]

        # Second failure — triggers backoff
        state_tool.record_attempt(iid, "t1", "failed", "kimi couldn't fix it either")
        skip = state_tool.should_skip(iid)
        assert skip["skip"]
        assert "backoff" in skip["reason"]

    tmp.unlink()


def test_fixed_issue_skipped():
    """Fixed issues should be skipped."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = Path(f.name)

    with patch.object(state_tool, "STATE_PATH", tmp):
        issue = state_tool.record_issue(
            "Cointracker", "test_fail", "test_csv.py", "timestamp parse error"
        )
        iid = issue["issue_id"]

        state_tool.record_attempt(iid, "t1", "fixed")
        skip = state_tool.should_skip(iid)
        assert skip["skip"]
        assert "fixed" in skip["reason"]

    tmp.unlink()


def test_metrics():
    """Metrics should track daily activity."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = Path(f.name)

    with patch.object(state_tool, "STATE_PATH", tmp):
        issue = state_tool.record_issue("Sapphire", "lint", "a.py", "error")
        iid = issue["issue_id"]
        state_tool.record_attempt(iid, "t0", "fixed")

        metrics = state_tool.get_metrics()
        assert metrics["fixed"] == 1
        assert metrics["total_issues"] == 1

    tmp.unlink()


def test_deterministic_issue_id():
    """Same issue recorded twice should return same ID."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = Path(f.name)

    with patch.object(state_tool, "STATE_PATH", tmp):
        i1 = state_tool.record_issue("Sapphire", "lint", "a.py", "unused import")
        i2 = state_tool.record_issue("Sapphire", "lint", "a.py", "unused import")
        assert i1["issue_id"] == i2["issue_id"]

    tmp.unlink()
