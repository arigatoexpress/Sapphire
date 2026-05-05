"""Workflow guardrails for no-spend GitHub Actions operation."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
RUNNER_IF = "${{ vars.SAPPHIRE_RUNNER != '' }}"
RUNNER_IF_ALWAYS = "${{ always() && vars.SAPPHIRE_RUNNER != '' }}"
RUNNER_IF_MAIN = "github.ref == 'refs/heads/main' && vars.SAPPHIRE_RUNNER != ''"
RUNNER_IF_MAIN_WITH_GCP_WIF = (
    "github.ref == 'refs/heads/main' && vars.SAPPHIRE_RUNNER != '' "
    "&& vars.GCP_WORKLOAD_IDENTITY_PROVIDER != '' && vars.GCP_SERVICE_ACCOUNT != ''"
)
ALLOWED_RUNNER_IFS = {
    RUNNER_IF,
    RUNNER_IF_ALWAYS,
    RUNNER_IF_MAIN,
    RUNNER_IF_MAIN_WITH_GCP_WIF,
}
RUNS_ON = "${{ fromJSON(vars.SAPPHIRE_RUNNER) }}"


def _workflow(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_workflow_jobs_do_not_fall_back_to_github_hosted_runners() -> None:
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = _workflow(path)
        for job_name, job in workflow.get("jobs", {}).items():
            assert (
                job.get("if") in ALLOWED_RUNNER_IFS
            ), f"{path.name}:{job_name} must skip when no runner is set"
            assert job.get("runs-on") == RUNS_ON, f"{path.name}:{job_name} must use SAPPHIRE_RUNNER"
            assert "ubuntu-latest" not in str(
                job
            ), f"{path.name}:{job_name} reintroduced hosted runner fallback"
