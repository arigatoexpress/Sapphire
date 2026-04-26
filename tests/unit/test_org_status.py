"""Tests for the Sapphire autonomous-org control tower."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "org_status.py"
MANIFEST = ROOT / "infra" / "org-repos.yaml"

SPEC = importlib.util.spec_from_file_location("org_status", SCRIPT)
assert SPEC and SPEC.loader
org_status = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(org_status)


def _manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def test_manifest_tracks_required_core_and_satellite_fields() -> None:
    manifest = _manifest()
    allowed_classes = {
        "core",
        "satellite",
        "integration",
        "candidate_absorb",
        "candidate_archive",
    }
    required = {
        "id",
        "name",
        "classification",
        "role",
        "local_path",
        "default_branch",
        "production_adjacent",
        "required_guardrails",
        "migration_state",
    }

    repos = manifest["repos"]
    assert {repo["id"] for repo in repos} >= {
        "sapphire",
        "project-go-forward",
        "cyber-threat-bot",
        "tradingview-mcp-v2",
        "hermes-agent",
    }
    for repo in repos:
        assert repo["classification"] in allowed_classes
        if repo["classification"] in {"core", "satellite"}:
            assert required <= set(repo)
            assert repo["github"], f"{repo['id']} needs a GitHub repo"
            assert repo["required_guardrails"]


def test_collect_status_no_external_handles_local_ci_without_live_tools() -> None:
    manifest = _manifest()

    report = org_status.collect_status(manifest, external=False)

    assert report["schema_version"] == 1
    assert report["summary"]["repo_count"] == len(manifest["repos"])
    assert "repo_classifications" in report["summary"]
    assert len(report["gcp_projects"]) == len(manifest["gcp_projects"])
    assert report["local_runtime"]["docker"]["checked"] is False
    assert all(row["status"] == "not_checked" for row in report["local_runtime"]["launchagents"])


def test_render_markdown_includes_control_board_sections() -> None:
    report = org_status.collect_status(_manifest(), external=False)

    markdown = org_status.render_markdown(report)

    assert "# Sapphire Autonomous Org Status" in markdown
    assert "## Summary" in markdown
    assert "## Repos" in markdown
    assert "## Waves" in markdown
    assert "| sapphire | core |" in markdown


def test_parse_launchctl_maps_pid_and_last_status() -> None:
    output = "\n".join(
        [
            "PID\tStatus\tLabel",
            "-\t0\tcom.sapphire.threat-refresh",
            "123\t0\tcom.sapphire.dashboard",
            "48423\t-15\tai.hermes.gateway",
        ]
    )

    parsed = org_status.parse_launchctl(output)

    assert parsed["com.sapphire.threat-refresh"] == {
        "loaded": True,
        "pid": None,
        "last_status": 0,
    }
    assert parsed["com.sapphire.dashboard"]["pid"] == 123
    assert parsed["ai.hermes.gateway"]["last_status"] == -15


def test_status_json_shape_omits_secret_payloads() -> None:
    report = org_status.collect_status(_manifest(), external=False)

    serialized = json.dumps(report)

    assert "Secret Manager" not in serialized
    assert "PRIVATE KEY" not in serialized
    assert "BEGIN RSA" not in serialized
    assert "token=" not in serialized.lower()
