"""Guardrails for remote-shadow routine workflows."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
ROUTINE_WORKFLOWS = (
    "content-engine.yml",
    "threat-refresh.yml",
    "weekly-backtest.yml",
)


def _workflow(name: str) -> dict:
    return yaml.load((WORKFLOWS / name).read_text(), Loader=yaml.BaseLoader)


def test_weekly_backtest_has_manual_and_scheduled_triggers() -> None:
    triggers = _workflow("weekly-backtest.yml")["on"]

    assert "workflow_dispatch" in triggers
    assert triggers["schedule"] == [{"cron": "0 4 * * 0"}]


def test_weekly_backtest_runs_strategy_sweep_and_uploads_artifacts() -> None:
    workflow = _workflow("weekly-backtest.yml")
    steps = workflow["jobs"]["strategy-sweep"]["steps"]
    run_blocks = "\n".join(step.get("run", "") for step in steps)
    used_actions = {step.get("uses", "") for step in steps}

    assert "python -m lib.analytics.run_strategies --days 90 --bankroll 10000" in run_blocks
    assert "data/backtests/strategies/*.json" in run_blocks or any(
        "data/backtests/strategies/*.json" in str(step.get("with", {})) for step in steps
    )
    assert "actions/upload-artifact@v4" in used_actions


def test_weekly_backtest_needs_no_repository_write_permission() -> None:
    permissions = _workflow("weekly-backtest.yml")["permissions"]

    assert permissions == {"contents": "read"}


def test_threat_refresh_has_manual_and_scheduled_triggers() -> None:
    triggers = _workflow("threat-refresh.yml")["on"]

    assert "workflow_dispatch" in triggers
    assert triggers["schedule"] == [{"cron": "10 1,5,9,13,17,21 * * *"}]


def test_threat_refresh_uses_native_public_sources_and_uploads_artifacts() -> None:
    workflow = _workflow("threat-refresh.yml")
    steps = workflow["jobs"]["refresh"]["steps"]
    run_blocks = "\n".join(step.get("run", "") for step in steps)
    used_actions = {step.get("uses", "") for step in steps}
    env_blocks = [step.get("env", {}) for step in steps]

    assert "python services/dashboard/refresh_threats.py" in run_blocks
    assert "actions/upload-artifact@v4" in used_actions
    assert any("data/intelligence/**/threats.json" in str(step.get("with", {})) for step in steps)
    assert any(
        env.get("SAPPHIRE_THREATS_BOT_BIN") == "native"
        and "data/intelligence" in env.get("SAPPHIRE_THREATS_DATA_DIR", "")
        for env in env_blocks
    )


def test_threat_refresh_needs_no_repository_write_permission() -> None:
    workflow = _workflow("threat-refresh.yml")

    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] == "false"


def test_remote_routines_pin_self_hosted_runner_tool_cache() -> None:
    expected = "/Users/aribs/.github-runners/toolcache"

    for workflow_name in ROUTINE_WORKFLOWS:
        env = _workflow(workflow_name)["env"]

        assert env["AGENT_TOOLSDIRECTORY"] == expected
        assert env["RUNNER_TOOL_CACHE"] == expected


def test_remote_routines_use_uv_instead_of_setup_python() -> None:
    for workflow_name in ROUTINE_WORKFLOWS:
        workflow = _workflow(workflow_name)
        steps = [step for job in workflow["jobs"].values() for step in job["steps"]]
        run_blocks = "\n".join(step.get("run", "") for step in steps)
        used_actions = {step.get("uses", "") for step in steps}

        assert "actions/setup-python" not in used_actions
        assert "uv run --python 3.11 --no-project" in run_blocks
