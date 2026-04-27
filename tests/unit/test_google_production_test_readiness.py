"""Tests for the Google production-testing readiness harness."""

from __future__ import annotations

import importlib.util
import plistlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "google_production_test_readiness.py"

SPEC = importlib.util.spec_from_file_location("google_production_test_readiness", SCRIPT)
assert SPEC and SPEC.loader
readiness = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = readiness
SPEC.loader.exec_module(readiness)


def _benefits_runner(args: list[str]) -> readiness.google_benefits_inventory.CommandResult:
    command = " ".join(args)
    if command.startswith("gcloud config list"):
        return readiness.google_benefits_inventory.CommandResult(
            True,
            {"core": {"account": "ari@example.com", "project": "tho-ai-agent"}},
        )
    if command.startswith("gcloud storage buckets list"):
        return readiness.google_benefits_inventory.CommandResult(
            True,
            [{"name": "gs://sapphire-data-lake"}, {"name": "gs://tho-secure-documents"}],
        )
    if command.startswith("bq ls"):
        return readiness.google_benefits_inventory.CommandResult(
            True,
            [{"datasetReference": {"datasetId": "sapphire"}}],
        )
    raise AssertionError(f"unexpected benefits command: {command}")


def _benefits_text_runner(
    args: list[str],
) -> readiness.google_benefits_inventory.CommandResult:
    if args[0] == "gemini":
        return readiness.google_benefits_inventory.CommandResult(True, "0.39.1")
    return readiness.google_benefits_inventory.CommandResult(True, f"{args[0]} version")


def _gcp_runner(args: list[str]) -> readiness.gcp_ai_inventory.CommandResult:
    command = " ".join(args)
    if command.startswith("gcloud services list"):
        return readiness.gcp_ai_inventory.CommandResult(
            True,
            [
                {"config": {"name": "aiplatform.googleapis.com"}},
                {"config": {"name": "bigquery.googleapis.com"}},
                {"config": {"name": "storage.googleapis.com"}},
            ],
        )
    if command.startswith("bq ls --format=json --project_id=tho-ai-agent sapphire"):
        return readiness.gcp_ai_inventory.CommandResult(
            True,
            [{"tableReference": {"tableId": "regional_intel_items"}}],
        )
    if command.startswith("bq ls --format=json --project_id=tho-ai-agent"):
        return readiness.gcp_ai_inventory.CommandResult(
            True,
            [{"datasetReference": {"datasetId": "sapphire"}}],
        )
    if any(label in command for label in ("custom-jobs", "models", "endpoints", "indexes")):
        return readiness.gcp_ai_inventory.CommandResult(True, [])
    raise AssertionError(f"unexpected gcp command: {command}")


def _cost_builder(*_args: object, **_kwargs: object) -> dict[str, object]:
    return {
        "warning_lookback": "24h",
        "projects": [
            {
                "project": "tho-ai-agent",
                "cloud_run": {"service_count": 2, "risk_count": 0},
            }
        ],
    }


def _write_plist(path: Path, env: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        plistlib.dumps(
            {
                "Label": path.stem,
                "ProgramArguments": ["/bin/bash", "/tmp/start.sh"],
                "EnvironmentVariables": env,
            }
        )
    )


def test_collect_readiness_combines_google_surfaces_without_writes() -> None:
    report = readiness.collect_readiness(
        projects=["tho-ai-agent"],
        regions=["us-central1"],
        memberships=["google_developer_premium", "google_ai_plus"],
        benefits_runner=_benefits_runner,
        benefits_text_runner=_benefits_text_runner,
        gcp_runner=_gcp_runner,
    )

    assert report["mode"] == "read-only"
    assert report["summary"]["gemini_cli"]["available"] is True
    assert report["summary"]["ready_gcp_projects"] == ["tho-ai-agent"]
    assert report["summary"]["vertex_resource_totals"]["endpoints"] == 0
    assert "gmail.users.messages.delete" in report["summary"]["blocked_workspace_actions"]
    assert any(gate["id"] == "launchagent_retargeting" for gate in report["readiness_gates"])


def test_no_external_mode_does_not_call_runners() -> None:
    def fail_benefits(args: list[str]) -> readiness.google_benefits_inventory.CommandResult:
        raise AssertionError(f"benefits runner should not be called: {args}")

    def fail_text(args: list[str]) -> readiness.google_benefits_inventory.CommandResult:
        raise AssertionError(f"text runner should not be called: {args}")

    def fail_gcp(args: list[str]) -> readiness.gcp_ai_inventory.CommandResult:
        raise AssertionError(f"gcp runner should not be called: {args}")

    report = readiness.collect_readiness(
        external=False,
        benefits_runner=fail_benefits,
        benefits_text_runner=fail_text,
        gcp_runner=fail_gcp,
    )

    assert report["mode"] == "no-external"
    assert report["summary"]["gemini_cli"]["available"] is None
    assert report["readiness_gates"][0]["status"] == "unknown"


def test_include_cost_adds_read_only_cost_gate() -> None:
    report = readiness.collect_readiness(
        projects=["tho-ai-agent"],
        regions=["us-central1"],
        include_cost=True,
        benefits_runner=_benefits_runner,
        benefits_text_runner=_benefits_text_runner,
        gcp_runner=_gcp_runner,
        cost_builder=_cost_builder,
    )

    gate_ids = {gate["id"] for gate in report["readiness_gates"]}
    assert "cost_posture_probe" in gate_ids
    assert report["inputs"]["cost_posture"]["included"] is True


def test_markdown_contains_gates_and_live_action_blocks() -> None:
    report = readiness.collect_readiness(
        projects=["tho-ai-agent"],
        regions=["us-central1"],
        include_cost=True,
        benefits_runner=_benefits_runner,
        benefits_text_runner=_benefits_text_runner,
        gcp_runner=_gcp_runner,
        cost_builder=_cost_builder,
    )

    markdown = readiness.render_markdown(report)

    assert "# Google Production-Testing Readiness" in markdown
    assert "No workflow dispatches, LaunchAgent retargets" in markdown
    assert "Vertex evals before training" in markdown
    assert "RELAY_READER_TOKEN" in markdown
    assert "Cost Posture" in markdown


def test_launchagent_retargeting_gate_passes_when_runtime_is_sanitized(tmp_path: Path) -> None:
    secrets_env = tmp_path / ".sapphire" / "secrets.env"
    secrets_env.parent.mkdir()
    secrets_env.write_text(
        "\n".join(
            [
                "AUTH_PASSWORD=present",
                "RELAY_READER_TOKEN=present",
                "KIMI_RELAY_CHAT_ID=present",
            ]
        )
    )
    live_dir = tmp_path / "LaunchAgents"
    _write_plist(live_dir / "com.sapphire.dashboard.plist", {"PATH": "/bin", "PORT": "8080"})
    _write_plist(
        live_dir / "com.sapphire.inference-proxy.plist",
        {"PI_RARI1_ENABLED": "1", "PI_RARI2_ENABLED": "1"},
    )
    tracked = [tmp_path / "dashboard.plist", tmp_path / "inference.plist"]
    for path in tracked:
        _write_plist(path, {})

    gate = readiness._launchagent_retargeting_gate(
        secrets_env=secrets_env,
        live_dir=live_dir,
        tracked_plists=tracked,
    )

    assert gate["status"] == "pass"


def test_launchagent_retargeting_gate_flags_live_secret_env(tmp_path: Path) -> None:
    secrets_env = tmp_path / ".sapphire" / "secrets.env"
    secrets_env.parent.mkdir()
    secrets_env.write_text("AUTH_PASSWORD=present\n")
    live_dir = tmp_path / "LaunchAgents"
    _write_plist(live_dir / "com.sapphire.dashboard.plist", {"AUTH_PASSWORD": "secret"})
    _write_plist(
        live_dir / "com.sapphire.inference-proxy.plist",
        {"RELAY_READER_TOKEN": "secret", "PI_RARI1_ENABLED": "1"},
    )

    gate = readiness._launchagent_retargeting_gate(
        secrets_env=secrets_env,
        live_dir=live_dir,
        tracked_plists=[],
    )

    assert gate["status"] == "needs_attention"
    assert "live plist secret env remains" in gate["evidence"]
