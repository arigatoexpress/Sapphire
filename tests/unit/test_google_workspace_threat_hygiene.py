"""Tests for the dry-run Google Workspace threat hygiene planner."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "google_workspace_threat_hygiene.py"

SPEC = importlib.util.spec_from_file_location("google_workspace_threat_hygiene", SCRIPT)
assert SPEC and SPEC.loader
workspace_hygiene = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = workspace_hygiene
SPEC.loader.exec_module(workspace_hygiene)


def test_plan_is_dry_run_and_blocks_deletes() -> None:
    plan = workspace_hygiene.build_plan(days=14)

    assert plan["mode"] == "dry-run-plan"
    assert plan["lookback_days"] == 14
    assert "gmail.users.messages.delete" in plan["blocked_actions"]
    assert "drive.files.delete" in plan["blocked_actions"]
    assert any("No message bodies" in guardrail for guardrail in plan["guardrails"])


def test_gmail_queries_apply_lookback_window() -> None:
    plan = workspace_hygiene.build_plan(days=7)
    queries = {entry["id"]: entry["query"] for entry in plan["gmail_queries"]}

    assert "newer_than:7d" in queries["spam_recent"]
    assert "filename:exe" in queries["dangerous_attachments"]
    assert "larger:10M" in queries["oversized_recent_mail"]


def test_markdown_exposes_reversible_actions() -> None:
    markdown = workspace_hygiene.render_markdown(workspace_hygiene.build_plan())

    assert "Sapphire/Review/Suspicious-Attachment" in markdown
    assert "human_approve_archive_or_trash" in markdown
    assert "Permanent delete is outside the autonomous lane." in markdown
