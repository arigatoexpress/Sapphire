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
# Hybrid split (2026-07-03): portable jobs may prefer the always-on Windows
# runner via SAPPHIRE_RUNNER_TESTS, falling back to the Mac runner. Both
# variables hold self-hosted label arrays — still no hosted-runner spend.
RUNS_ON_HYBRID = "${{ fromJSON(vars.SAPPHIRE_RUNNER_TESTS || vars.SAPPHIRE_RUNNER) }}"
ALLOWED_RUNS_ON = (RUNS_ON, RUNS_ON_HYBRID)
# win-runner-smoke.yml is the manual-dispatch validation workflow for the
# Windows runner; it alone may pin the literal self-hosted Windows labels.
WIN_SMOKE_WORKFLOW = "win-runner-smoke.yml"
WIN_SMOKE_RUNS_ON = ["self-hosted", "Windows", "X64", "sapphire-win"]


def _workflow(path: Path) -> dict:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_workflow_jobs_do_not_fall_back_to_github_hosted_runners() -> None:
    for path in sorted(WORKFLOWS.glob("*.yml")):
        workflow = _workflow(path)
        for job_name, job in workflow.get("jobs", {}).items():
            assert (
                job.get("if") in ALLOWED_RUNNER_IFS
            ), f"{path.name}:{job_name} must skip when no runner is set"
            runs_on = job.get("runs-on")
            if path.name == WIN_SMOKE_WORKFLOW:
                assert runs_on in ALLOWED_RUNS_ON or runs_on == WIN_SMOKE_RUNS_ON, (
                    f"{path.name}:{job_name} must use a self-hosted Sapphire runner"
                )
            else:
                assert runs_on in ALLOWED_RUNS_ON, (
                    f"{path.name}:{job_name} must use SAPPHIRE_RUNNER (or the TESTS hybrid)"
                )
            assert "ubuntu-latest" not in str(
                job
            ), f"{path.name}:{job_name} reintroduced hosted runner fallback"
