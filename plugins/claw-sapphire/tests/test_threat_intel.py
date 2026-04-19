"""Tests for the threat_intel tool."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

TOOLS = Path(__file__).parent.parent / "tools"
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(TOOLS.parent / "lib"))

_spec = importlib.util.spec_from_file_location("threat_intel", TOOLS / "internal" / "threat_intel.py")
ti = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ti)


def test_action_scan_handles_missing_dependency(monkeypatch):
    """The tool should degrade cleanly when cyber-threat-bot is unavailable."""
    monkeypatch.setattr(ti, "_import_ctb", lambda: (None, None, None, None))

    got = ti.action_scan()

    assert "error" in got
    assert "cyber-threat-bot" in got["error"]


def test_action_scan_summarizes_critical_records(monkeypatch):
    """Critical records should be surfaced in the scan summary."""
    records = [
        SimpleNamespace(
            canonical_id="CVE-2026-9999",
            title="Critical edge case",
            score=9.8,
            exploited=True,
            source="cisa",
        ),
        SimpleNamespace(
            canonical_id="CVE-2026-1111",
            title="Lower priority issue",
            score=6.4,
            exploited=False,
            source="nvd",
        ),
    ]

    fake_sources = SimpleNamespace(collect_latest_records=lambda days=3, per_source=5: list(records))
    fake_scoring = SimpleNamespace(record_priority=lambda record: (record.score or 0) + (50 if record.exploited else 0))

    monkeypatch.setattr(ti, "_import_ctb", lambda: (fake_sources, None, None, fake_scoring))
    monkeypatch.setattr(ti, "_publish_threats", lambda records, trigger: None)

    got = ti.action_scan()

    assert got["success"] is True
    assert got["status"] == "CRITICAL"
    assert got["critical_count"] == 1
    assert got["critical_items"][0]["id"] == "CVE-2026-9999"

