"""Tests for the Google benefits control-tower inventory."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "google_benefits_inventory.py"

SPEC = importlib.util.spec_from_file_location("google_benefits_inventory", SCRIPT)
assert SPEC and SPEC.loader
google_benefits = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = google_benefits
SPEC.loader.exec_module(google_benefits)


def _fake_runner(args: list[str]) -> google_benefits.CommandResult:
    command = " ".join(args)
    if command.startswith("gcloud config list"):
        return google_benefits.CommandResult(
            True,
            {"core": {"account": "ari@example.com", "project": "tho-ai-agent"}},
        )
    if command.startswith("gcloud storage buckets list"):
        return google_benefits.CommandResult(
            True,
            [{"name": "gs://sapphire-data-lake"}, {"name": "gs://sapphire-archives"}],
        )
    if command.startswith("bq ls"):
        return google_benefits.CommandResult(
            True,
            [{"datasetReference": {"datasetId": "sapphire"}}],
        )
    raise AssertionError(f"unexpected command: {command}")


def _fake_text_runner(args: list[str]) -> google_benefits.CommandResult:
    return google_benefits.CommandResult(True, f"{args[0]} version")


def test_no_external_mode_does_not_call_runners() -> None:
    def fail_runner(args: list[str]) -> google_benefits.CommandResult:
        raise AssertionError(f"runner should not be called: {args}")

    inventory = google_benefits.collect_inventory(
        memberships=["google_developer_premium", "google_ai_plus"],
        external=False,
        runner=fail_runner,
        text_runner=fail_runner,
    )

    assert inventory["mode"] == "no-external"
    assert inventory["local"] == {}
    assert "Developer Program" in {entry["lane"] for entry in inventory["catalog"]}
    assert any("Cloud/GenAI credits" in note for note in inventory["membership_notes"])


def test_read_only_inventory_collects_non_secret_local_metadata() -> None:
    inventory = google_benefits.collect_inventory(
        memberships=["google_developer_premium"],
        external=True,
        runner=_fake_runner,
        text_runner=_fake_text_runner,
    )

    assert inventory["local"]["account"] == {
        "available": True,
        "account": "ari@example.com",
        "project": "tho-ai-agent",
    }
    assert inventory["local"]["gcs_buckets"]["names"] == [
        "sapphire-archives",
        "sapphire-data-lake",
    ]
    assert inventory["local"]["bigquery_datasets"]["datasets"] == ["sapphire"]
    assert inventory["local"]["tools"]["gemini"]["available"] is True


def test_markdown_includes_gmail_drive_safety_gate_and_sources() -> None:
    inventory = google_benefits.collect_inventory(
        memberships=["google_ai_plus", "youtube_premium"],
        external=True,
        runner=_fake_runner,
        text_runner=_fake_text_runner,
    )

    markdown = google_benefits.render_markdown(inventory)

    assert "Gmail / Drive Threat Hygiene" in markdown
    assert "No Gmail or Drive content is read." in markdown
    assert "No email/body/attachment reads" in markdown
    assert "https://developers.google.com/workspace/gmail/api/auth/scopes" in markdown
    assert "YouTube Premium" in markdown
