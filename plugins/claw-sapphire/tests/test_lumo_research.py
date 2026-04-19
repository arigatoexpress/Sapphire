"""Tests for the lumo_research tool."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
import lumo_research as lr


def test_action_ask_offline_returns_fallback(monkeypatch):
    """Offline status should return a structured fallback instead of raising."""
    monkeypatch.setattr(lr, "_is_online", lambda timeout=3: False)

    got = lr.action_ask("What is CVE-2026-1340?")

    assert got["status"] == "offline"
    assert "fallback" in got
    assert "start_command" in got


def test_action_security_brief_redacts_sensitive_input(monkeypatch):
    """Security briefs should sanitize obvious secrets before forwarding."""
    monkeypatch.setattr(lr, "_is_online", lambda timeout=3: True)
    sent: dict[str, object] = {}

    def fake_post(prompt: str, web_search: bool = False, timeout: int = lr.DEFAULT_TIMEOUT) -> str:
        sent["prompt"] = prompt
        sent["web_search"] = web_search
        return "Structured brief"

    monkeypatch.setattr(lr, "_post_lumo", fake_post)

    got = lr.action_security_brief("api_key=supersecret CVE-2026-1340", depth="deep", web_search=False)

    assert got["status"] == "ok"
    assert got["brief"] == "Structured brief"
    assert sent["web_search"] is False
    assert "[REDACTED]" in str(sent["prompt"])
    assert "supersecret" not in str(sent["prompt"])

