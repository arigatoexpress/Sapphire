"""Guardrails for remote-shadow routine workflows."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "weekly-backtest.yml"


def _workflow() -> dict:
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def test_weekly_backtest_has_manual_and_scheduled_triggers() -> None:
    triggers = _workflow()["on"]

    assert "workflow_dispatch" in triggers
    assert triggers["schedule"] == [{"cron": "0 4 * * 0"}]


def test_weekly_backtest_runs_strategy_sweep_and_uploads_artifacts() -> None:
    workflow = _workflow()
    steps = workflow["jobs"]["strategy-sweep"]["steps"]
    run_blocks = "\n".join(step.get("run", "") for step in steps)
    used_actions = {step.get("uses", "") for step in steps}

    assert "python -m lib.analytics.run_strategies --days 90 --bankroll 10000" in run_blocks
    assert "data/backtests/strategies/*.json" in run_blocks or any(
        "data/backtests/strategies/*.json" in str(step.get("with", {})) for step in steps
    )
    assert "actions/upload-artifact@v7" in used_actions


def test_weekly_backtest_needs_no_repository_write_permission() -> None:
    permissions = _workflow()["permissions"]

    assert permissions == {"contents": "read"}
