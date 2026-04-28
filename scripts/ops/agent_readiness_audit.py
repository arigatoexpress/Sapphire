#!/usr/bin/env python3
"""Read-only Sapphire agent-readiness audit.

The audit labels each claim as observed, inferred, or unknown and avoids
printing secret values. External GitHub probes use names/counts/status only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPO = "arigatoexpress/Sapphire"
RUNNER_IF = "${{ vars.SAPPHIRE_RUNNER != '' }}"
RUNNER_IF_ALWAYS = "${{ always() && vars.SAPPHIRE_RUNNER != '' }}"
ALLOWED_RUNNER_IFS = {RUNNER_IF, RUNNER_IF_ALWAYS}
RUNS_ON = "${{ fromJSON(vars.SAPPHIRE_RUNNER) }}"
SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret|password)=)[^\s;]+"),
)


@dataclass(frozen=True)
class Finding:
    category: str
    surface: str
    claim: str
    status: str
    evidence: str


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    stdout: str
    stderr: str
    duration_ms: int


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = collect_report(root=args.root, repo=args.repo, external=not args.no_external)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.format == "markdown":
        rendered = render_markdown(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--no-external", action="store_true")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    return parser


def collect_report(*, root: Path = ROOT, repo: str = DEFAULT_REPO, external: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    findings: list[Finding] = []
    findings.extend(collect_repo_state(root))
    findings.extend(collect_workflow_readiness(root))
    findings.extend(collect_doc_readiness(root))
    if external:
        findings.extend(collect_github_readiness(repo))
    else:
        findings.append(
            Finding(
                "github",
                "external probes",
                "unknown",
                "SKIP",
                "--no-external requested",
            )
        )
    summary = summarize(findings)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "repo": repo,
        "summary": summary,
        "findings": [asdict(finding) for finding in findings],
    }


def collect_repo_state(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    status = run(["git", "status", "--short", "--branch"], cwd=root)
    findings.append(
        Finding(
            "repo",
            "canonical checkout",
            "observed",
            "PASS" if status.ok and "## main...origin/main" in status.stdout else "WARN",
            first_line(status.stdout) if status.ok else status.stderr,
        )
    )
    worktrees = run(["git", "worktree", "list", "--porcelain"], cwd=root)
    if worktrees.ok:
        count = sum(1 for line in worktrees.stdout.splitlines() if line.startswith("worktree "))
        dirty = run(["git", "status", "--porcelain=v1"], cwd=root)
        findings.append(
            Finding(
                "repo",
                "worktree inventory",
                "observed",
                "PASS" if count == 1 and dirty.ok and not dirty.stdout.strip() else "WARN",
                f"worktrees={count}; canonical_dirty={bool(dirty.stdout.strip())}",
            )
        )
    else:
        findings.append(
            Finding("repo", "worktree inventory", "unknown", "UNKNOWN", worktrees.stderr)
        )
    return findings


def collect_workflow_readiness(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    workflows = sorted((root / ".github" / "workflows").glob("*.yml"))
    if not workflows:
        return [
            Finding("ci", "workflow inventory", "observed", "WARN", "no workflow files found")
        ]
    for path in workflows:
        rel = path.relative_to(root)
        try:
            workflow = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader) or {}
        except Exception as exc:
            findings.append(
                Finding("ci", str(rel), "observed", "WARN", f"workflow parse failed: {type(exc).__name__}")
            )
            continue
        permissions = workflow.get("permissions")
        findings.append(permissions_finding(rel, permissions))
        jobs = workflow.get("jobs") if isinstance(workflow, dict) else {}
        if not isinstance(jobs, dict):
            findings.append(Finding("ci", str(rel), "observed", "WARN", "jobs is not a mapping"))
            continue
        for job_name, job in jobs.items():
            if not isinstance(job, dict):
                continue
            surface = f"{rel}:{job_name}"
            job_if = str(job.get("if") or "")
            runs_on = str(job.get("runs-on") or "")
            job_text = json.dumps(job, sort_keys=True)
            findings.append(
                Finding(
                    "spend controls",
                    surface,
                    "observed",
                    "PASS" if job_if in ALLOWED_RUNNER_IFS else "WARN",
                    f"if={job_if or '<missing>'}",
                )
            )
            findings.append(
                Finding(
                    "spend controls",
                    surface,
                    "observed",
                    "PASS" if runs_on == RUNS_ON else "WARN",
                    f"runs-on={runs_on or '<missing>'}",
                )
            )
            findings.append(
                Finding(
                    "spend controls",
                    surface,
                    "observed",
                    "PASS" if "ubuntu-latest" not in job_text else "WARN",
                    "no hosted fallback string" if "ubuntu-latest" not in job_text else "contains ubuntu-latest",
                )
            )
    return findings


def permissions_finding(rel: Path, permissions: Any) -> Finding:
    if not isinstance(permissions, dict):
        return Finding("permissions", str(rel), "observed", "WARN", "top-level permissions not explicit")
    writes = sorted(key for key, value in permissions.items() if str(value).lower() == "write")
    status = "PASS" if not writes else "WARN"
    evidence = "all declared permissions read/none" if not writes else f"write_permissions={','.join(writes)}"
    return Finding("permissions", str(rel), "observed", status, evidence)


def collect_doc_readiness(root: Path) -> list[Finding]:
    checks = {
        "human approval": root / "AGENTS.md",
        "rollback": root / "docs" / "ops" / "safe-merge-runbook.md",
        "verification": root / "scripts" / "ops" / "local_ci_verify.py",
        "observability": root / "scripts" / "ops" / "production_readiness_sweep.py",
        "ownership": root / ".github" / "CODEOWNERS",
        "pr hygiene": root / ".github" / "pull_request_template.md",
    }
    findings: list[Finding] = []
    for surface, path in checks.items():
        exists = path.exists()
        findings.append(
            Finding(
                "docs",
                surface,
                "observed",
                "PASS" if exists else "WARN",
                str(path.relative_to(root)) if exists else f"missing: {path.relative_to(root)}",
            )
        )
    if checks["human approval"].exists():
        text = checks["human approval"].read_text(encoding="utf-8", errors="replace")
        has_gate = all(term in text for term in ("Human approval is required", "real money movement", "live trade execution"))
        findings.append(
            Finding(
                "human approval",
                "AGENTS.md",
                "observed",
                "PASS" if has_gate else "WARN",
                "explicit high-risk approval gate present" if has_gate else "approval gate text not found",
            )
        )
    return findings


def collect_github_readiness(repo: str) -> list[Finding]:
    findings: list[Finding] = []
    repo_meta = gh_json(["api", f"repos/{repo}"])
    if repo_meta.ok:
        payload = json.loads(repo_meta.stdout)
        findings.append(
            Finding(
                "github",
                "repository metadata",
                "observed",
                "PASS",
                f"default_branch={payload.get('default_branch')}; private={payload.get('private')}",
            )
        )
    else:
        findings.append(Finding("github", "repository metadata", "unknown", "UNKNOWN", repo_meta.stderr))

    protection = gh_json(["api", f"repos/{repo}/branches/main/protection"])
    if protection.ok:
        payload = json.loads(protection.stdout)
        required_reviews = payload.get("required_pull_request_reviews")
        required_checks = payload.get("required_status_checks")
        enforce_admins = payload.get("enforce_admins", {}).get("enabled")
        findings.append(
            Finding(
                "human approval",
                "main branch protection",
                "observed",
                "PASS" if required_reviews or required_checks else "WARN",
                f"reviews={bool(required_reviews)}; checks={bool(required_checks)}; enforce_admins={enforce_admins}",
            )
        )
    else:
        findings.append(
            Finding(
                "human approval",
                "main branch protection",
                "unknown",
                "UNKNOWN",
                compact_error(protection.stderr),
            )
        )

    variables = gh_json(["api", f"repos/{repo}/actions/variables"])
    if variables.ok:
        payload = json.loads(variables.stdout)
        names = sorted(item.get("name", "") for item in payload.get("variables", []))
        findings.append(
            Finding(
                "spend controls",
                "actions variables",
                "observed",
                "PASS" if "SAPPHIRE_RUNNER" in names else "WARN",
                f"names={','.join(name for name in names if name)}",
            )
        )
    else:
        findings.append(Finding("spend controls", "actions variables", "unknown", "UNKNOWN", compact_error(variables.stderr)))

    secrets = run(["gh", "secret", "list", "--repo", repo, "--json", "name,updatedAt,visibility"], cwd=ROOT)
    if secrets.ok:
        payload = json.loads(secrets.stdout or "[]")
        names = sorted(item.get("name", "") for item in payload)
        findings.append(
            Finding(
                "secrets",
                "actions secrets",
                "observed",
                "PASS",
                f"count={len(names)}; names={','.join(name for name in names if name)}",
            )
        )
    else:
        findings.append(Finding("secrets", "actions secrets", "unknown", "UNKNOWN", compact_error(secrets.stderr)))

    environments = gh_json(["api", f"repos/{repo}/environments"])
    if environments.ok:
        payload = json.loads(environments.stdout)
        names = sorted(item.get("name", "") for item in payload.get("environments", []))
        findings.append(
            Finding(
                "deployment",
                "github environments",
                "observed",
                "PASS" if names else "WARN",
                f"names={','.join(name for name in names if name)}" if names else "no environments listed",
            )
        )
    else:
        findings.append(Finding("deployment", "github environments", "unknown", "UNKNOWN", compact_error(environments.stderr)))

    dependabot = gh_json(["api", f"repos/{repo}/dependabot/alerts?state=open&per_page=100"])
    if dependabot.ok:
        payload = json.loads(dependabot.stdout)
        severities = severity_counts(payload)
        findings.append(
            Finding(
                "secrets",
                "dependabot alerts",
                "observed",
                "PASS" if not severities.get("critical") and not severities.get("high") else "WARN",
                f"open={len(payload)}; severities={json.dumps(severities, sort_keys=True)}",
            )
        )
    else:
        findings.append(Finding("secrets", "dependabot alerts", "unknown", "UNKNOWN", compact_error(dependabot.stderr)))

    code_scanning = gh_json(["api", f"repos/{repo}/code-scanning/alerts?state=open&per_page=1"])
    if code_scanning.ok:
        payload = json.loads(code_scanning.stdout)
        findings.append(
            Finding(
                "observability",
                "code scanning",
                "observed",
                "PASS",
                f"open_sample_count={len(payload)}",
            )
        )
    else:
        findings.append(
            Finding("observability", "code scanning", "unknown", "UNKNOWN", compact_error(code_scanning.stderr))
        )
    return findings


def severity_counts(alerts: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for alert in alerts:
        severity = (
            alert.get("security_vulnerability", {})
            .get("severity")
        ) or "unknown"
        counts[str(severity)] = counts.get(str(severity), 0) + 1
    return counts


def summarize(findings: list[Finding]) -> dict[str, int]:
    summary: dict[str, int] = {"PASS": 0, "WARN": 0, "UNKNOWN": 0, "SKIP": 0}
    for finding in findings:
        summary[finding.status] = summary.get(finding.status, 0) + 1
    return summary


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Sapphire Agent Readiness Audit",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Repo: `{report['repo']}`",
        f"- Summary: `{json.dumps(report['summary'], sort_keys=True)}`",
        "",
        "| Category | Surface | Claim | Status | Evidence |",
        "|---|---|---|---:|---|",
    ]
    for row in report["findings"]:
        lines.append(
            "| {category} | {surface} | {claim} | {status} | {evidence} |".format(
                category=escape_cell(row["category"]),
                surface=escape_cell(row["surface"]),
                claim=escape_cell(row["claim"]),
                status=escape_cell(row["status"]),
                evidence=escape_cell(redact(row["evidence"])),
            )
        )
    lines.append("")
    return "\n".join(lines)


def run(cmd: list[str], *, cwd: Path) -> CommandResult:
    started = time.perf_counter()
    completed = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)
    return CommandResult(
        ok=completed.returncode == 0,
        stdout=completed.stdout,
        stderr=completed.stderr,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )


def gh_json(args: list[str]) -> CommandResult:
    return run(["gh", *args], cwd=ROOT)


def first_line(text: str) -> str:
    stripped = text.strip()
    return stripped.splitlines()[0] if stripped else ""


def compact_error(text: str) -> str:
    return first_line(redact(text)) or "command failed"


def redact(text: str) -> str:
    redacted = str(text)
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: match.group(1) + "[REDACTED]" if match.groups() else "[REDACTED]", redacted)
    return redacted


def escape_cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
