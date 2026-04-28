from __future__ import annotations

from pathlib import Path

from scripts.ops import agent_readiness_audit as audit


def _write_workflow(root: Path, text: str) -> None:
    workflows = root / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text(text, encoding="utf-8")


def test_workflow_readiness_accepts_self_hosted_gate(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        """
name: ci
on: [push]
permissions:
  contents: read
jobs:
  test:
    if: ${{ vars.SAPPHIRE_RUNNER != '' }}
    runs-on: ${{ fromJSON(vars.SAPPHIRE_RUNNER) }}
    steps:
      - run: echo ok
""",
    )

    findings = audit.collect_workflow_readiness(tmp_path)

    assert all(finding.status == "PASS" for finding in findings)


def test_workflow_readiness_flags_hosted_runner_fallback(tmp_path: Path) -> None:
    _write_workflow(
        tmp_path,
        """
name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: echo bad
""",
    )

    findings = audit.collect_workflow_readiness(tmp_path)
    evidence = "\n".join(finding.evidence for finding in findings)

    assert any(finding.status == "WARN" for finding in findings)
    assert "ubuntu-latest" in evidence


def test_render_markdown_redacts_token_like_values() -> None:
    report = {
        "generated_at": "2026-04-28T00:00:00+00:00",
        "repo": "example/repo",
        "summary": {"PASS": 0, "WARN": 1, "UNKNOWN": 0, "SKIP": 0},
        "findings": [
            {
                "category": "secrets",
                "surface": "probe",
                "claim": "observed",
                "status": "WARN",
                "evidence": "token=super-secret-value; pat=ghp_abcdefghijklmnopqrstuvwxyz123456",
            }
        ],
    }

    rendered = audit.render_markdown(report)

    assert "super-secret-value" not in rendered
    assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in rendered
    assert "token=[REDACTED]" in rendered
