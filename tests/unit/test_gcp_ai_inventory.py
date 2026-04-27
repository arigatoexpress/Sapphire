"""Tests for the read-only GCP/Vertex AI complement inventory."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "gcp_ai_inventory.py"

SPEC = importlib.util.spec_from_file_location("gcp_ai_inventory", SCRIPT)
assert SPEC and SPEC.loader
gcp_ai_inventory = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gcp_ai_inventory
SPEC.loader.exec_module(gcp_ai_inventory)


def _fake_runner(args: list[str]) -> gcp_ai_inventory.CommandResult:
    command = " ".join(args)
    if command.startswith("gcloud services list"):
        return gcp_ai_inventory.CommandResult(
            True,
            [
                {"config": {"name": "aiplatform.googleapis.com"}},
                {"config": {"name": "bigquery.googleapis.com"}},
                {"config": {"name": "storage.googleapis.com"}},
            ],
        )
    if command.startswith("bq ls --format=json --project_id=tho-ai-agent sapphire"):
        return gcp_ai_inventory.CommandResult(
            True,
            [
                {"tableReference": {"tableId": "inference_metrics"}},
                {"tableReference": {"tableId": "regional_intel_items"}},
            ],
        )
    if command.startswith("bq ls --format=json --project_id=tho-ai-agent"):
        return gcp_ai_inventory.CommandResult(
            True,
            [{"datasetReference": {"datasetId": "sapphire"}}],
        )
    if "custom-jobs" in command:
        return gcp_ai_inventory.CommandResult(True, [])
    if "models list" in command:
        return gcp_ai_inventory.CommandResult(True, [])
    if "endpoints list" in command:
        return gcp_ai_inventory.CommandResult(True, [])
    if "indexes list" in command:
        return gcp_ai_inventory.CommandResult(True, [])
    if "index-endpoints list" in command:
        return gcp_ai_inventory.CommandResult(True, [])
    msg = f"unexpected command: {command}"
    raise AssertionError(msg)


def test_collect_inventory_is_read_only_and_marks_ready_data_plane() -> None:
    inventory = gcp_ai_inventory.collect_inventory(
        ["tho-ai-agent"],
        ["us-central1"],
        runner=_fake_runner,
    )

    assert inventory["mode"] == "read-only"
    assert inventory["projects"][0]["status"] == "ready for dry-run AI complement"
    assert inventory["projects"][0]["bigquery_tables"]["sapphire"] == [
        "inference_metrics",
        "regional_intel_items",
    ]
    region = inventory["projects"][0]["vertex_regions"][0]
    assert region["resources"]["endpoints"]["count"] == 0
    assert "No secret values are read or printed." in inventory["guardrails"]


def test_no_external_mode_does_not_call_runner() -> None:
    def fail_runner(args: list[str]) -> gcp_ai_inventory.CommandResult:
        raise AssertionError(f"runner should not be called: {args}")

    inventory = gcp_ai_inventory.collect_inventory(
        ["tho-ai-agent"],
        ["us-central1"],
        runner=fail_runner,
        external=False,
    )

    assert inventory["mode"] == "no-external"
    assert inventory["projects"] == []
    assert inventory["recommendations"][0]["lane"] == "Data-plane readiness"


def test_markdown_includes_guarded_lane_order() -> None:
    inventory = gcp_ai_inventory.collect_inventory(
        ["tho-ai-agent"],
        ["us-central1"],
        runner=_fake_runner,
    )

    markdown = gcp_ai_inventory.render_markdown(inventory)

    assert "# GCP / Vertex AI Complement Inventory" in markdown
    assert "Batch Gemini OODA packets" in markdown
    assert "Custom training or tuning" in markdown
    assert "No GCP, Foundry, Telegram, trading, workflow, or LaunchAgent mutation" in markdown
