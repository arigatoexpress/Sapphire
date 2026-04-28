"""Tests for the starred_repos tool."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import starred_repos as sr


def test_classify_repo_detects_multiple_domains():
    """Repo classification should pick up strong keyword overlap."""
    repo = {
        "full_name": "example/agent-security-stack",
        "description": "Autonomous agent security scanner for CVE and OSINT workflows",
        "topics": ["agent", "security", "osint"],
        "language": "Python",
    }

    got = sr.classify_repo(repo)

    assert "ai-agents" in got
    assert "cybersecurity" in got


def test_sync_stars_reports_gh_failure(monkeypatch):
    """GitHub CLI failures should return a structured error."""
    monkeypatch.setattr(
        sr.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="auth failed"),
    )

    got = sr.sync_stars()

    assert "error" in got
    assert "gh api failed" in got["error"]
