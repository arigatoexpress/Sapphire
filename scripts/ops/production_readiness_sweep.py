#!/usr/bin/env python3
"""Enumerate and probe Sapphire production readiness surfaces.

The default sweep is read-only: repo/worktree state, LaunchAgents, local
endpoints, safety reports, routine soak state, and Google/GCP metadata. Optional
flags perform bounded live probes that intentionally avoid secret rendering:
Telegram Bot API read probes and tiny GCS/BigQuery write evidence.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

ROOT = Path(__file__).resolve().parents[2]
ORG_REPOS_MANIFEST = ROOT / "infra" / "org-repos.yaml"
DEFAULT_PROJECT = "tho-ai-agent"
DEFAULT_REGION = "us-central1"
DEFAULT_BUCKET = "sapphire-data-lake"
DEFAULT_DATASET = "sapphire"
DEFAULT_BQ_TABLE = "production_readiness_probes"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_SECRET_ENV = Path.home() / ".sapphire" / "secrets.env"
SAPPHIRE_SECRETS_DIR = Path.home() / ".config" / "sapphire-secrets"
DEFAULT_WINDOWS_GPU_URL = "http://192.168.1.61:11434"
DEFAULT_WINDOWS_HOST = "192.168.1.61"
DEFAULT_WINDOWS_HTTP_TIMEOUT_SECONDS = 5.0
DEFAULT_WINDOWS_TCP_TIMEOUT_SECONDS = 3.0
DEFAULT_WINDOWS_SSH_TIMEOUT_SECONDS = 8
GEMINI_PROBE_PROMPT = "Return exactly SAPPHIRE_GEMINI_PROBE_OK and nothing else."
GEMINI_PROBE_RESPONSE = "SAPPHIRE_GEMINI_PROBE_OK"
WINDOWS_REQUIRED_MODELS = {
    "fast": "gemma3:4b",
    "balanced": "gemma3:4b",
    "code": "qwen2.5-coder:14b",
    "reason": "deepseek-r1:14b",
    "qwen-reason": "qwen3.5:4b",
    "deep": "qwen3:14b",
    "qwen3.6": "qwen3.6:35b-a3b",
    "large": "qwen3-coder:30b",
}
WINDOWS_SERVICE_PORTS = {
    "desktop_ssh_tcp": 22,
    "tradingview_agent_tcp": 8081,
    "tradingview_webhook_tcp": 9090,
    "telemetry_dashboard_tcp": 3001,
}
WINDOWS_EXPECTED_TASK_STATES = {
    "SapphireDashboard": {"Running"},
    "SapphireWebhook": {"Running"},
    "Sapphire-TV-Agent": {"Running"},
    "SapphireResearchWorker": {"Ready", "Running"},
    "SapphireTradingViewCDP": {"Ready", "Running"},
    "SapphireWindowsAvailabilityGuard": {"Ready", "Running"},
}
WINDOWS_RESEARCH_WORKER_MAX_AGE_SECONDS = int(
    os.getenv("WINDOWS_RESEARCH_WORKER_MAX_AGE_SECONDS", "129600")
)
NO_SPEND_CI_STRATEGIES = {
    "local_evidence_skip_ci_bootstrap",
    "sapphire_self_hosted_gate",
}
NO_SPEND_CI_EXCEPTION_REASONS = {
    "draft_auto_deploy": "Cloud Run deploy path intentionally stays on hosted Actions",
    "upstream_fork_local_only": "Upstream/fork work uses local evidence rather than Ari-owned hosted CI",
}


@dataclass
class Check:
    category: str
    name: str
    status: str
    evidence: str
    duration_ms: int = 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    started = time.perf_counter()
    checks: list[Check] = []

    env = load_secret_env(args.secret_env)
    checks.extend(probe_repo())
    checks.append(probe_satellite_ci_no_spend_gates())
    checks.append(probe_satellite_merge_posture(no_external=args.no_external))
    checks.extend(probe_launchagents())
    checks.extend(probe_local_endpoints(env))
    checks.extend(probe_windows_desktop_server())
    checks.extend(probe_safety())
    checks.extend(probe_provenance())
    checks.extend(probe_routines(no_external=args.no_external))
    checks.extend(probe_github(no_external=args.no_external))
    checks.extend(probe_google_readiness(args, no_external=args.no_external))
    if args.include_gemini_live_probe and args.no_external:
        checks.append(Check("gemini", "vertex_live_probe", "SKIP", "--no-external"))
    elif args.include_gemini_live_probe:
        gemini_checks = probe_gemini_live(args)
        checks.extend(gemini_checks)
        apply_gemini_probe_to_google_gate(checks, gemini_checks)
    if args.include_telegram_probe:
        checks.extend(probe_telegram(env))
    if args.include_gcp_write_probe:
        checks.extend(probe_gcp_writes(args))

    # `--json` is a convenience shortcut for `--format json`. Both paths emit
    # the same payload via build_report() so the dashboard SLO panel
    # (`/api/readiness/latest`) and operators reading stdout see the same shape.
    fmt = "json" if args.json else args.format

    report = build_report(checks, started, args)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        if fmt == "json":
            args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        else:
            args.output.write_text(render_markdown(report))

    if fmt == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0 if report["summary"]["fail"] == 0 else 20


def build_report(checks: list[Check], started: float, args: argparse.Namespace) -> dict[str, Any]:
    """Assemble the canonical sweep report payload.

    Each check entry carries both ``category`` (legacy, original Check field)
    and ``section`` (alias for the dashboard SLO panel) so neither side has to
    rename without coordination. Adds NO new fields beyond the alias and does
    NOT change PASS/WARN/FAIL classifications.
    """
    report_checks: list[dict[str, Any]] = []
    for check in checks:
        entry = asdict(check)
        # Alias category -> section for dashboard consumers without breaking
        # consumers that key off `category`.
        entry["section"] = entry["category"]
        report_checks.append(entry)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "duration_ms": int((time.perf_counter() - started) * 1000),
        "mode": {
            "external": not args.no_external,
            "gemini_live_probe": args.include_gemini_live_probe,
            "telegram_probe": args.include_telegram_probe,
            "gcp_write_probe": args.include_gcp_write_probe,
        },
        "summary": summarize(checks),
        "checks": report_checks,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--bucket", default=DEFAULT_BUCKET)
    parser.add_argument("--dataset", default=DEFAULT_DATASET)
    parser.add_argument("--bq-table", default=DEFAULT_BQ_TABLE)
    parser.add_argument("--gemini-model", default=DEFAULT_GEMINI_MODEL)
    parser.add_argument("--secret-env", type=Path, default=DEFAULT_SECRET_ENV)
    parser.add_argument("--no-external", action="store_true")
    parser.add_argument("--include-gemini-live-probe", action="store_true")
    parser.add_argument("--include-telegram-probe", action="store_true")
    parser.add_argument("--include-gcp-write-probe", action="store_true")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Shortcut for --format json. Used by the dashboard SLO panel cache LaunchAgent.",
    )
    parser.add_argument("--output", type=Path)
    return parser


def load_secret_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip().strip("'\"")
    for key in ("AUTH_PASSWORD", "AUTH_USERNAME", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
        if os.environ.get(key):
            env[key] = os.environ[key]
    token_file = SAPPHIRE_SECRETS_DIR / "telegram_bot_token"
    chat_file = SAPPHIRE_SECRETS_DIR / "telegram_chat_id"
    if token_file.exists() and "TELEGRAM_BOT_TOKEN" not in env:
        env["TELEGRAM_BOT_TOKEN"] = token_file.read_text(encoding="utf-8").strip()
    if chat_file.exists() and "TELEGRAM_CHAT_ID" not in env:
        env["TELEGRAM_CHAT_ID"] = chat_file.read_text(encoding="utf-8").strip()
    return env


def probe_repo() -> list[Check]:
    checks: list[Check] = []
    status = run(["git", "status", "--porcelain=v1"], cwd=ROOT)
    branch = run(["git", "status", "--short", "--branch"], cwd=ROOT)
    dirty = bool(status.stdout.strip())
    checks.append(
        Check(
            "repo",
            "canonical_checkout_clean",
            "WARN" if dirty else "PASS",
            (
                branch.stdout.strip().splitlines()[0]
                if branch.stdout.strip()
                else "git status unavailable"
            )
            + (f"; dirty entries={len(status.stdout.splitlines())}" if dirty else ""),
            status.duration_ms + branch.duration_ms,
        )
    )
    worktrees = run(["git", "worktree", "list"], cwd=ROOT)
    checks.append(
        Check(
            "repo",
            "worktree_inventory",
            "PASS" if worktrees.ok else "WARN",
            f"{len(worktrees.stdout.splitlines())} worktrees observed",
            worktrees.duration_ms,
        )
    )
    return checks


def probe_satellite_ci_no_spend_gates(manifest_path: Path = ORG_REPOS_MANIFEST) -> Check:
    started = time.perf_counter()
    if not manifest_path.exists():
        return Check(
            "org",
            "satellite_ci_no_spend_gates",
            "WARN",
            f"manifest_missing={manifest_path}",
            int((time.perf_counter() - started) * 1000),
        )
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return Check(
            "org",
            "satellite_ci_no_spend_gates",
            "WARN",
            f"manifest_parse_error={exc.__class__.__name__}",
            int((time.perf_counter() - started) * 1000),
        )

    repos = manifest.get("repos") if isinstance(manifest, dict) else []
    if not isinstance(repos, list):
        return Check(
            "org",
            "satellite_ci_no_spend_gates",
            "WARN",
            "manifest repos is not a list",
            int((time.perf_counter() - started) * 1000),
        )

    violations: list[str] = []
    missing_local: list[str] = []
    checked_repos = 0
    checked_workflows = 0
    checked_jobs = 0
    no_workflow_repos: list[str] = []
    skipped: list[str] = []
    exceptions: list[str] = []

    for repo in repos:
        if not isinstance(repo, dict):
            continue
        repo_id = str(repo.get("id") or repo.get("name") or "unknown")
        strategy = str(repo.get("ci_strategy") or "")
        local_path = Path(str(repo.get("local_path") or ""))
        if strategy not in NO_SPEND_CI_STRATEGIES:
            if strategy in NO_SPEND_CI_EXCEPTION_REASONS:
                exceptions.append(f"{repo_id}:{strategy}")
            else:
                skipped.append(f"{repo_id}:{strategy or 'no_ci_strategy'}")
            continue
        if not local_path.exists():
            missing_local.append(repo_id)
            continue

        workflow_dir = local_path / ".github" / "workflows"
        workflows = (
            sorted([*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")])
            if workflow_dir.exists()
            else []
        )
        checked_repos += 1
        if not workflows:
            no_workflow_repos.append(repo_id)
            continue
        for workflow in workflows:
            checked_workflows += 1
            job_violations, job_count = workflow_no_spend_gate_violations(repo_id, workflow)
            checked_jobs += job_count
            violations.extend(job_violations)

    status = "PASS"
    if violations:
        status = "FAIL"
    elif missing_local:
        status = "WARN"

    evidence_parts = [
        f"checked_repos={checked_repos}",
        f"workflows={checked_workflows}",
        f"jobs={checked_jobs}",
    ]
    if violations:
        evidence_parts.append(f"violations={','.join(violations[:8])}")
        if len(violations) > 8:
            evidence_parts.append(f"violations_omitted={len(violations) - 8}")
    if missing_local:
        evidence_parts.append(f"missing_local={','.join(missing_local)}")
    if no_workflow_repos:
        evidence_parts.append(f"no_workflows={','.join(no_workflow_repos)}")
    if exceptions:
        evidence_parts.append(f"exceptions={','.join(exceptions)}")
    if skipped:
        evidence_parts.append(f"skipped={len(skipped)}")
    return Check(
        "org",
        "satellite_ci_no_spend_gates",
        status,
        "; ".join(evidence_parts),
        int((time.perf_counter() - started) * 1000),
    )


# WARN-by-design: this probe emits WARN whenever any satellite repo has
# `allow_auto_merge=false`. That posture is intentional across the org — Ari's
# autonomy playbook explicitly avoids GitHub auto-merge in favor of explicit
# admin-squash-merge after local verification is green (see the Codex tranche
# megaprompts under `docs/handoffs/` and CLAUDE.md "Cloud Routines" section,
# which lists "no auto-merge" as a hard policy for the 8 routines). The check
# would only flip to PASS if every satellite enabled `allow_auto_merge=true`,
# which would weaken the autonomy posture. WARN is the correct steady state and
# should be left as-is until/unless the org-wide merge policy changes. The
# probe still escalates to FAIL on truly broken settings (no squash, no
# branch-delete, runner gate missing), so genuinely critical drift is caught.
# Re-evaluate only if the autonomy playbook changes its merge policy.
def probe_satellite_merge_posture(
    *,
    no_external: bool,
    manifest_path: Path = ORG_REPOS_MANIFEST,
) -> Check:
    started = time.perf_counter()
    if no_external:
        return Check("org", "satellite_merge_posture", "SKIP", "--no-external")
    manifest_check = load_org_repos(manifest_path)
    if isinstance(manifest_check, Check):
        manifest_check.name = "satellite_merge_posture"
        return manifest_check
    repos = [
        repo
        for repo in manifest_check
        if str(repo.get("ci_strategy") or "") in NO_SPEND_CI_STRATEGIES and repo.get("github")
    ]

    details: list[str] = []
    api_errors: list[str] = []
    auto_merge_false: list[str] = []
    critical: list[str] = []
    unevaluated: list[str] = []

    for repo in repos:
        repo_id = str(repo.get("id") or repo.get("name") or "unknown")
        github = str(repo.get("github"))
        settings = github_repo_merge_settings(github)
        if settings is None:
            api_errors.append(repo_id)
            details.append(f"{repo_id}(api=unavailable)")
            continue

        allow_auto = bool(settings.get("allow_auto_merge"))
        allow_squash = bool(settings.get("allow_squash_merge"))
        delete_branch = bool(settings.get("delete_branch_on_merge"))
        runner_gate = repo_runner_gate_state(repo)
        details.append(
            f"{repo_id}(auto={str(allow_auto).lower()},"
            f"squash={str(allow_squash).lower()},"
            f"delete={str(delete_branch).lower()},"
            f"runner_gate={runner_gate})"
        )
        if not allow_auto:
            auto_merge_false.append(repo_id)
        if not allow_squash:
            critical.append(f"{repo_id}:allow_squash_merge=false")
        if not delete_branch:
            critical.append(f"{repo_id}:delete_branch_on_merge=false")
        if runner_gate == "missing_local":
            # Absence of a local clone is not evidence of a broken runner gate —
            # it is absence of evidence. Most of the old arigatoexpress fleet is
            # archived and deliberately not cloned on this Mac, so treating
            # "can't look" as "found a violation" pinned this check to FAIL
            # forever and buried the one real violation it did find.
            unevaluated.append(repo_id)
        elif runner_gate != "pass":
            critical.append(f"{repo_id}:runner_gate={runner_gate}")

    status = "PASS"
    if critical:
        status = "FAIL"
    elif api_errors or auto_merge_false or unevaluated:
        status = "WARN"

    evidence_parts = [f"checked_repos={len(repos)}"]
    if unevaluated:
        evidence_parts.append(f"runner_gate_unevaluated={','.join(unevaluated)}")
    if auto_merge_false:
        evidence_parts.append(f"auto_merge_false={','.join(auto_merge_false)}")
    if api_errors:
        evidence_parts.append(f"api_errors={','.join(api_errors)}")
    if critical:
        evidence_parts.append(f"violations={','.join(critical[:8])}")
        if len(critical) > 8:
            evidence_parts.append(f"violations_omitted={len(critical) - 8}")
    if details:
        evidence_parts.append(f"details={';'.join(details)}")
    return Check(
        "org",
        "satellite_merge_posture",
        status,
        "; ".join(evidence_parts),
        int((time.perf_counter() - started) * 1000),
    )


def load_org_repos(manifest_path: Path) -> list[dict[str, Any]] | Check:
    started = time.perf_counter()
    if not manifest_path.exists():
        return Check(
            "org",
            "org_repos_manifest",
            "WARN",
            f"manifest_missing={manifest_path}",
            int((time.perf_counter() - started) * 1000),
        )
    try:
        manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return Check(
            "org",
            "org_repos_manifest",
            "WARN",
            f"manifest_parse_error={exc.__class__.__name__}",
            int((time.perf_counter() - started) * 1000),
        )
    repos = manifest.get("repos") if isinstance(manifest, dict) else []
    if not isinstance(repos, list):
        return Check(
            "org",
            "org_repos_manifest",
            "WARN",
            "manifest repos is not a list",
            int((time.perf_counter() - started) * 1000),
        )
    return [repo for repo in repos if isinstance(repo, dict)]


def github_repo_merge_settings(repo_full_name: str) -> dict[str, Any] | None:
    result = run(
        [
            "gh",
            "api",
            f"repos/{repo_full_name}",
            "--jq",
            (
                "{allow_auto_merge,allow_squash_merge,"
                "delete_branch_on_merge,allow_merge_commit,allow_rebase_merge}"
            ),
        ],
        cwd=ROOT,
        timeout=30,
    )
    if not result.ok:
        return None
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def repo_runner_gate_state(repo: dict[str, Any]) -> str:
    repo_id = str(repo.get("id") or repo.get("name") or "unknown")
    local_path = Path(str(repo.get("local_path") or ""))
    if not local_path.exists():
        return "missing_local"
    workflow_dir = local_path / ".github" / "workflows"
    workflows = (
        sorted([*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")])
        if workflow_dir.exists()
        else []
    )
    if not workflows:
        return "no_workflows"
    violations: list[str] = []
    jobs = 0
    for workflow in workflows:
        found, job_count = workflow_no_spend_gate_violations(repo_id, workflow)
        violations.extend(found)
        jobs += job_count
    if violations:
        return f"fail:{len(violations)}"
    return "pass" if jobs else "no_jobs"


def runs_on_labels(job: dict[str, Any]) -> list[str]:
    """Normalise every `runs-on` spelling to a flat list of label strings.

    GitHub accepts a bare string (`ubuntu-latest`), a label list
    (`[self-hosted, Windows, X64]`), and a group/labels mapping.
    """
    runs_on = job.get("runs-on")
    if isinstance(runs_on, str):
        return [runs_on]
    if isinstance(runs_on, list):
        return [str(label) for label in runs_on]
    if isinstance(runs_on, dict):
        labels = runs_on.get("labels")
        if isinstance(labels, str):
            return [labels]
        if isinstance(labels, list):
            return [str(label) for label in labels]
    return []


def workflow_no_spend_gate_violations(repo_id: str, workflow: Path) -> tuple[list[str], int]:
    """Flag jobs that could bill GitHub-hosted Actions minutes.

    Two spellings satisfy the no-spend invariant:

    1. The `vars.SAPPHIRE_RUNNER` gate — `runs-on` resolves from the var and the
       job is `if`-guarded on it being set, so the job cannot fall back to a
       hosted runner when the self-hosted runner is unregistered.
    2. An explicit `self-hosted` label in `runs-on`. This targets Ari's own
       hardware and bills nothing, so it needs no gate.

    Only recognising (1) made `win-runner-smoke.yml` a permanent FAIL even
    though it pins `runs-on: [self-hosted, Windows, X64, sapphire-win]` — free
    by construction. The invariant is "don't spend", not "use one idiom".
    """
    try:
        data = yaml.safe_load(workflow.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return [f"{repo_id}:{workflow.name}:parse_error:{exc.__class__.__name__}"], 0
    jobs = data.get("jobs") if isinstance(data, dict) else {}
    if not isinstance(jobs, dict):
        return [], 0
    violations: list[str] = []
    for job_name, job in jobs.items():
        if not isinstance(job, dict):
            continue
        labels = runs_on_labels(job)
        if any(label.strip().lower() == "self-hosted" for label in labels):
            continue
        if_text = str(job.get("if") or "")
        runs_on_text = " ".join(labels)
        if "vars.SAPPHIRE_RUNNER" not in if_text or "vars.SAPPHIRE_RUNNER" not in runs_on_text:
            violations.append(f"{repo_id}:{workflow.name}:{job_name}")
    return violations, len(jobs)


def _probe_windows_tasks() -> list[Check]:
    expected = {
        "SapphireDashboard": "Running",
        "SapphireResearchWorker": "Ready",
        "Sapphire-TV-Agent-Logon": "Ready",
    }
    checks: list[Check] = []

    # Run Get-ScheduledTask
    try:
        res = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-ScheduledTask -TaskName 'Sapphire*' | Select-Object TaskName, State | ConvertTo-Json",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        import json

        tasks_data = json.loads(res.stdout)
        if isinstance(tasks_data, dict):
            tasks_data = [tasks_data]
        parsed = {t["TaskName"]: t["State"] for t in tasks_data}
    except Exception:
        parsed = {}

    for label, expected_state in expected.items():
        state = parsed.get(label)
        if not state:
            checks.append(Check("windows_task", label, "FAIL", "not loaded", 0))
        elif expected_state == "Running" and str(state) not in ("Running", "4"):
            checks.append(Check("windows_task", label, "FAIL", f"expected Running, got {state}", 0))
        elif expected_state == "Ready" and str(state) not in ("Ready", "3"):
            checks.append(Check("windows_task", label, "FAIL", f"expected Ready, got {state}", 0))
        else:
            checks.append(Check("windows_task", label, "PASS", f"state={state}", 0))

    return checks


def probe_launchagents() -> list[Check]:
    import sys

    if sys.platform == "win32":
        return _probe_windows_tasks()

    # Source of truth: plists under infra/launchagents/. Retired 2026-07-25:
    #   com.sapphire.dashboard      — CLAUDE.md: "No LaunchAgent — run manually"
    #   com.sapphire.inference-proxy — no plist; run manually if needed
    #   com.sapphire.cloudflare-tunnel — renamed to webhook-tunnel (kept below)
    # Kept intentionally even though no plist in infra/launchagents/:
    #   com.sapphire.pm-bot — plist lives at services/pm_bot/launchagent/;
    #     last active 2026-05-13 per log — real regression, do NOT hide.
    expected = {
        "com.sapphire.control-plane": "always_on",
        "com.sapphire.signal-logger": "always_on",
        "com.sapphire.pm-bot": "always_on",
        "com.sapphire.heartbeat": "always_on",
        "com.sapphire.openbb-api": "always_on",
        "com.sapphire.webhook-tunnel": "always_on",
        "actions.runner.arigatoexpress-Sapphire.ari-macbook-sapphire": "always_on",
        "com.sapphire.gcp-sync": "scheduled",
        "com.sapphire.content-engine": "scheduled",
        "com.sapphire.threat-refresh": "scheduled",
        "com.sapphire.morning-brief": "scheduled",
        "com.sapphire.backtest-weekly": "scheduled",
        "com.sapphire.security-pipeline": "scheduled",
        "com.sapphire.telemetry-collector": "scheduled",
        "com.sapphire.foundry-sync": "scheduled",
        "com.sapphire.tradingview-cdp": "scheduled",
    }
    listing = run(["launchctl", "list"])
    parsed = parse_launchctl_list(listing.stdout)
    checks: list[Check] = []
    for label, kind in expected.items():
        item = parsed.get(label)
        if not item:
            checks.append(Check("launchagent", label, "FAIL", "not loaded", listing.duration_ms))
            continue
        pid, status = item
        if kind == "always_on" and pid == "-":
            checks.append(
                Check(
                    "launchagent", label, "FAIL", f"loaded but not running (last_status={status})"
                )
            )
        else:
            evidence = "running" if pid != "-" else f"loaded idle (last_status={status})"
            check_status = "PASS"
            if kind == "scheduled" and pid == "-" and status != "0":
                check_status = "WARN"
            checks.append(Check("launchagent", label, check_status, evidence))
    return checks


def parse_launchctl_list(output: str) -> dict[str, tuple[str, str]]:
    parsed: dict[str, tuple[str, str]] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            parsed[parts[2]] = (parts[0], parts[1])
    return parsed


def dashboard_port() -> str:
    """Port the Sapphire dashboard actually binds on this host.

    Not 8080: `com.sovereign.openwebui` squats that port. Not the app.py default
    8082 either: control-plane owns it. 8085 is the working slot.
    """
    return os.environ.get("SAPPHIRE_DASHBOARD_PORT", "8085")


def probe_local_endpoints(env: dict[str, str]) -> list[Check]:
    dash = dashboard_port()
    checks = [
        inference_proxy_health_check(),
        http_check(
            "local",
            "inference_proxy_metrics",
            "http://127.0.0.1:11435/metrics",
            warn_on_error=True,
        ),
        http_check(
            "local",
            "dashboard_health",
            f"http://127.0.0.1:{dash}/health",
            expect_json={"status": "healthy"},
        ),
        http_check("local", "control_plane_health", "http://127.0.0.1:8082/health"),
        http_check("local", "signal_logger_health", "http://127.0.0.1:18081/health"),
        tcp_check("local", "openbb_api_tcp", "127.0.0.1", 6900),
        tcp_check("local", "redis_tcp", "127.0.0.1", 6379),
        http_check("local", "ollama_tags", "http://127.0.0.1:11434/api/tags"),
        http_check(
            "local",
            "tradingview_cdp_version",
            "http://127.0.0.1:9222/json/version",
            warn_on_error=True,
        ),
    ]
    password = env.get("AUTH_PASSWORD")
    if password:
        checks.append(
            http_check(
                "local",
                "dashboard_authenticated_root",
                f"http://127.0.0.1:{dash}/",
                auth=("sapphire", password),
            )
        )
    else:
        checks.append(
            Check(
                "local",
                "dashboard_authenticated_root",
                "WARN",
                "AUTH_PASSWORD not available to probe",
            )
        )
    return checks


def inference_proxy_health_check() -> Check:
    # Inference proxy is optional infra on this Mac (no LaunchAgent by design;
    # run manually via services/inference-proxy/app.py when needed). A missing
    # proxy is a WARN, not a FAIL — same treatment as tradingview_cdp_version.
    started = time.perf_counter()
    url = "http://127.0.0.1:11435/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as response:  # nosec B310 - fixed localhost health URL.
            status_code = response.status
            body = response.read(1024 * 1024)
    except urllib.error.HTTPError as exc:
        return Check(
            "local",
            "inference_proxy_health",
            "WARN",
            f"http={exc.code}",
            int((time.perf_counter() - started) * 1000),
        )
    except Exception as exc:
        return Check(
            "local",
            "inference_proxy_health",
            "WARN",
            exc.__class__.__name__,
            int((time.perf_counter() - started) * 1000),
        )

    status = "PASS" if 200 <= status_code < 300 else "FAIL"
    evidence = f"http={status_code}"
    with contextlib_suppress():
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            if parsed.get("status"):
                evidence += f"; status={parsed.get('status')}"
            endpoints = parsed.get("endpoints")
            if isinstance(endpoints, dict):
                disabled = sorted(
                    str(name)
                    for name, value in endpoints.items()
                    if str(value).lower() in {"disabled"}
                )
                degraded = sorted(
                    str(name)
                    for name, value in endpoints.items()
                    if str(value).lower() not in {"healthy", "ok", "available", "disabled"}
                )
                if disabled:
                    evidence += f"; disabled_tiers={','.join(disabled)}"
                if degraded and status == "PASS":
                    status = "WARN"
                    evidence += f"; degraded_tiers={','.join(degraded)}"
    return Check(
        "local",
        "inference_proxy_health",
        status,
        evidence,
        int((time.perf_counter() - started) * 1000),
    )


def probe_windows_desktop_server(env: dict[str, str] | None = None) -> list[Check]:
    """Probe Ari's Windows desktop as the private Sapphire accelerator node."""
    values = env or os.environ
    gpu_url = str(values.get("WINDOWS_GPU_URL") or DEFAULT_WINDOWS_GPU_URL).rstrip("/")
    host = str(values.get("WINDOWS_GPU_HOST") or urlparse(gpu_url).hostname or DEFAULT_WINDOWS_HOST)

    checks = [
        windows_ollama_inventory_check(gpu_url),
        windows_webhook_health_check(host),
        windows_research_worker_check(host),
        windows_tv_agent_cdp_check(host),
        windows_scheduled_tasks_check(host),
        windows_power_availability_check(host),
    ]
    checks.extend(
        tcp_check("windows", name, host, port, warn_on_error=True)
        for name, port in WINDOWS_SERVICE_PORTS.items()
    )
    return checks


def windows_ssh_target(host: str) -> str:
    return os.getenv("SAPPHIRE_WINDOWS_SSH_TARGET", f"aribs@{host}")


def windows_ssh_timeout_seconds() -> int:
    raw = os.getenv("SAPPHIRE_WINDOWS_SSH_TIMEOUT_SECONDS")
    if raw is None:
        return DEFAULT_WINDOWS_SSH_TIMEOUT_SECONDS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_WINDOWS_SSH_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_WINDOWS_SSH_TIMEOUT_SECONDS


def windows_powershell_json(host: str, script: str, *, timeout: int | None = None) -> RunResult:
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    connect_timeout = max(1, int(windows_tcp_timeout_seconds()))
    return run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={connect_timeout}",
            windows_ssh_target(host),
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-EncodedCommand",
            encoded,
        ],
        timeout=timeout or windows_ssh_timeout_seconds(),
    )


def windows_tv_agent_cdp_check(host: str = DEFAULT_WINDOWS_HOST) -> Check:
    started = time.perf_counter()
    url = f"http://{host}:8081/health"
    try:
        with urllib.request.urlopen(url, timeout=windows_http_timeout_seconds()) as response:  # nosec B310 - fixed private Tailscale readiness URL.
            status_code = response.status
            body = response.read(1024 * 1024)
    except urllib.error.HTTPError as exc:
        return Check(
            "windows",
            "tradingview_cdp_status",
            "WARN",
            f"http={exc.code}",
            int((time.perf_counter() - started) * 1000),
        )
    except Exception as exc:
        return Check(
            "windows",
            "tradingview_cdp_status",
            "WARN",
            exc.__class__.__name__,
            int((time.perf_counter() - started) * 1000),
        )

    evidence = f"http={status_code}"
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return Check(
            "windows",
            "tradingview_cdp_status",
            "WARN",
            f"{evidence}; invalid_json",
            int((time.perf_counter() - started) * 1000),
        )
    if not isinstance(parsed, dict):
        return Check(
            "windows",
            "tradingview_cdp_status",
            "WARN",
            f"{evidence}; invalid_payload",
            int((time.perf_counter() - started) * 1000),
        )

    service_status = str(parsed.get("status") or "unknown")
    cdp = parsed.get("cdp") if isinstance(parsed.get("cdp"), dict) else {}
    cdp_status = str(cdp.get("status") or "unknown")
    cdp_healthy = cdp.get("healthy") is True
    status = "PASS" if 200 <= status_code < 300 and cdp_healthy else "WARN"
    evidence += f"; status={service_status}; cdp={cdp_status}"
    if cdp.get("latency_ms") is not None:
        evidence += f"; cdp_latency_ms={cdp.get('latency_ms')}"
    if cdp.get("tab_count") is not None:
        evidence += f"; tab_count={cdp.get('tab_count')}"
    if cdp.get("tradingview_tab_count") is not None:
        evidence += f"; tradingview_tab_count={cdp.get('tradingview_tab_count')}"
    return Check(
        "windows",
        "tradingview_cdp_status",
        status,
        evidence,
        int((time.perf_counter() - started) * 1000),
    )


def windows_scheduled_tasks_check(host: str = DEFAULT_WINDOWS_HOST) -> Check:
    names = sorted(WINDOWS_EXPECTED_TASK_STATES)
    quoted_names = ", ".join(f'"{name}"' for name in names)
    script = f"""
$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Continue'
$names = @({quoted_names})
$rows = foreach ($name in $names) {{
  $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
  if ($task) {{
    $info = $task | Get-ScheduledTaskInfo
    [pscustomobject]@{{
      TaskName = $task.TaskName
      State = $task.State.ToString()
      LastTaskResult = $info.LastTaskResult
    }}
  }} else {{
    [pscustomobject]@{{
      TaskName = $name
      State = 'Missing'
      LastTaskResult = $null
    }}
  }}
}}
$rows | ConvertTo-Json -Depth 4 -Compress
""".strip()
    result = windows_powershell_json(host, script)
    if not result.ok:
        return Check("windows", "scheduled_tasks", "WARN", short_error(result), result.duration_ms)
    try:
        parsed = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return Check("windows", "scheduled_tasks", "WARN", "invalid_json", result.duration_ms)
    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        return Check("windows", "scheduled_tasks", "WARN", "invalid_payload", result.duration_ms)

    states = {
        str(item.get("TaskName")): str(item.get("State"))
        for item in parsed
        if isinstance(item, dict)
    }
    missing = [name for name in names if states.get(name) in {None, "Missing"}]
    unexpected = [
        f"{name}:{states.get(name, 'Missing')}"
        for name, allowed in WINDOWS_EXPECTED_TASK_STATES.items()
        if states.get(name) not in allowed
    ]
    status = "PASS" if not missing and not unexpected else "WARN"
    evidence = f"checked={len(names)}"
    if missing:
        evidence += f"; missing={','.join(missing)}"
    if unexpected:
        evidence += f"; unexpected={','.join(unexpected)}"
    if not missing and not unexpected:
        evidence += "; states=ok"
    return Check("windows", "scheduled_tasks", status, evidence, result.duration_ms)


def _power_indices_are_zero(value: Any) -> bool:
    text = str(value or "")
    return (
        "Current AC Power Setting Index: 0x00000000" in text
        and "Current DC Power Setting Index: 0x00000000" in text
    )


def _registry_value_is_zero(value: Any, name: str) -> bool:
    for line in str(value or "").splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].lower() == name.lower():
            return parts[-1].lower() in {"0", "0x0", "0x00000000"}
    return False


def windows_power_availability_check(host: str = DEFAULT_WINDOWS_HOST) -> Check:
    script = """
$ProgressPreference = 'SilentlyContinue'
$ErrorActionPreference = 'Continue'
[pscustomobject]@{
  active_scheme = (powercfg /getactivescheme | Out-String).Trim()
  sleep = (powercfg /query SCHEME_CURRENT SUB_SLEEP STANDBYIDLE | Out-String).Trim()
  display = (powercfg /query SCHEME_CURRENT SUB_VIDEO VIDEOIDLE | Out-String).Trim()
  screen_save_active = (reg query 'HKCU\\Control Panel\\Desktop' /v ScreenSaveActive | Out-String).Trim()
  screen_saver_secure = (reg query 'HKCU\\Control Panel\\Desktop' /v ScreenSaverIsSecure | Out-String).Trim()
  screen_save_timeout = (reg query 'HKCU\\Control Panel\\Desktop' /v ScreenSaveTimeOut | Out-String).Trim()
  inactivity_timeout = (reg query 'HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System' /v InactivityTimeoutSecs | Out-String).Trim()
} | ConvertTo-Json -Depth 4 -Compress
""".strip()
    result = windows_powershell_json(host, script)
    if not result.ok:
        return Check(
            "windows",
            "desktop_availability_settings",
            "WARN",
            short_error(result),
            result.duration_ms,
        )
    try:
        parsed = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return Check(
            "windows", "desktop_availability_settings", "WARN", "invalid_json", result.duration_ms
        )
    if not isinstance(parsed, dict):
        return Check(
            "windows",
            "desktop_availability_settings",
            "WARN",
            "invalid_payload",
            result.duration_ms,
        )

    problems: list[str] = []
    if not _power_indices_are_zero(parsed.get("sleep")):
        problems.append("sleep_timeout")
    if not _power_indices_are_zero(parsed.get("display")):
        problems.append("display_timeout")
    if not _registry_value_is_zero(parsed.get("screen_save_active"), "ScreenSaveActive"):
        problems.append("screensaver_active")
    if not _registry_value_is_zero(parsed.get("screen_saver_secure"), "ScreenSaverIsSecure"):
        problems.append("screensaver_secure")
    if not _registry_value_is_zero(parsed.get("screen_save_timeout"), "ScreenSaveTimeOut"):
        problems.append("screensaver_timeout")
    if not _registry_value_is_zero(parsed.get("inactivity_timeout"), "InactivityTimeoutSecs"):
        problems.append("inactivity_timeout")

    evidence = "sleep=never; display=never; screensaver=off; inactivity_timeout=0"
    if problems:
        evidence += f"; problems={','.join(problems)}"
    return Check(
        "windows",
        "desktop_availability_settings",
        "PASS" if not problems else "WARN",
        evidence,
        result.duration_ms,
    )


def windows_ollama_inventory_check(base_url: str = DEFAULT_WINDOWS_GPU_URL) -> Check:
    started = time.perf_counter()
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=windows_http_timeout_seconds()) as response:  # nosec B310 - fixed private Tailscale readiness URL.
            status_code = response.status
            body = response.read(1024 * 1024)
    except urllib.error.HTTPError as exc:
        return Check(
            "windows",
            "ollama_model_inventory",
            "WARN",
            f"http={exc.code}",
            int((time.perf_counter() - started) * 1000),
        )
    except Exception as exc:
        return Check(
            "windows",
            "ollama_model_inventory",
            "WARN",
            exc.__class__.__name__,
            int((time.perf_counter() - started) * 1000),
        )

    status = "PASS" if 200 <= status_code < 300 else "WARN"
    evidence = f"http={status_code}"
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return Check(
            "windows",
            "ollama_model_inventory",
            "WARN",
            f"{evidence}; invalid_json",
            int((time.perf_counter() - started) * 1000),
        )

    models = parsed.get("models") if isinstance(parsed, dict) else []
    names = sorted(
        str(item.get("name") or item.get("model") or "")
        for item in models
        if isinstance(item, dict) and (item.get("name") or item.get("model"))
    )
    missing = [
        alias
        for alias, required_model in sorted(WINDOWS_REQUIRED_MODELS.items())
        if not model_inventory_has(names, required_model)
    ]
    if missing:
        status = "WARN"
    present = len(WINDOWS_REQUIRED_MODELS) - len(missing)
    evidence += f"; models={len(names)}; required_present={present}/{len(WINDOWS_REQUIRED_MODELS)}"
    if missing:
        evidence += f"; missing_aliases={','.join(missing)}"
    return Check(
        "windows",
        "ollama_model_inventory",
        status,
        evidence,
        int((time.perf_counter() - started) * 1000),
    )


def model_inventory_has(model_names: list[str], required_model: str) -> bool:
    if required_model in model_names:
        return True
    if ":" in required_model:
        return False
    prefix = f"{required_model}:"
    return any(name.startswith(prefix) for name in model_names)


def windows_webhook_health_check(host: str = DEFAULT_WINDOWS_HOST) -> Check:
    started = time.perf_counter()
    url = f"http://{host}:9090/webhook/health"
    try:
        with urllib.request.urlopen(url, timeout=windows_http_timeout_seconds()) as response:  # nosec B310 - fixed private Tailscale readiness URL.
            status_code = response.status
            body = response.read(1024 * 1024)
    except urllib.error.HTTPError as exc:
        return Check(
            "windows",
            "webhook_health",
            "WARN",
            f"http={exc.code}",
            int((time.perf_counter() - started) * 1000),
        )
    except Exception as exc:
        return Check(
            "windows",
            "webhook_health",
            "WARN",
            exc.__class__.__name__,
            int((time.perf_counter() - started) * 1000),
        )

    evidence = f"http={status_code}"
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return Check(
            "windows",
            "webhook_health",
            "WARN",
            f"{evidence}; invalid_json",
            int((time.perf_counter() - started) * 1000),
        )
    services = parsed.get("services") if isinstance(parsed, dict) else {}
    services = services if isinstance(services, dict) else {}
    # `agent_only` is a non-degraded state: the service process is up, but a
    # downstream optional dependency (e.g. CDP for windows_tv_agent on a host
    # that doesn't run TradingView) is not connected. Treat as informational.
    agent_only = sorted(
        str(name)
        for name, value in services.items()
        if isinstance(value, dict) and str(value.get("status", "")).lower() == "agent_only"
    )
    degraded = sorted(
        str(name)
        for name, value in services.items()
        if isinstance(value, dict)
        and value.get("healthy") is not True
        and str(value.get("status", "")).lower() != "agent_only"
    )
    capabilities = parsed.get("capabilities") if isinstance(parsed, dict) else {}
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    root_status = str(parsed.get("status") or "unknown") if isinstance(parsed, dict) else "unknown"
    status = "PASS" if 200 <= status_code < 300 and root_status == "healthy" else "WARN"
    if degraded:
        status = "WARN"
    evidence += f"; status={root_status}"
    if degraded:
        evidence += f"; degraded_services={','.join(degraded)}"
    if agent_only:
        evidence += f"; agent_only_services={','.join(agent_only)}"
    if "ollama_model_count" in capabilities:
        evidence += f"; ollama_model_count={capabilities.get('ollama_model_count')}"
    if "gpu_count" in capabilities:
        evidence += f"; gpu_count={capabilities.get('gpu_count')}"
    return Check(
        "windows",
        "webhook_health",
        status,
        evidence,
        int((time.perf_counter() - started) * 1000),
    )


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _age_seconds(value: Any) -> int | None:
    parsed = _parse_iso_datetime(value)
    if not parsed:
        return None
    return max(0, int((datetime.now(UTC) - parsed).total_seconds()))


def windows_research_worker_check(host: str = DEFAULT_WINDOWS_HOST) -> Check:
    started = time.perf_counter()
    url = f"http://{host}:9090/windows/research-worker/latest"
    try:
        with urllib.request.urlopen(url, timeout=windows_http_timeout_seconds()) as response:  # nosec B310 - fixed private Tailscale readiness URL.
            status_code = response.status
            body = response.read(1024 * 1024)
    except urllib.error.HTTPError as exc:
        return Check(
            "windows",
            "research_worker_freshness",
            "WARN",
            f"http={exc.code}",
            int((time.perf_counter() - started) * 1000),
        )
    except Exception as exc:
        return Check(
            "windows",
            "research_worker_freshness",
            "WARN",
            exc.__class__.__name__,
            int((time.perf_counter() - started) * 1000),
        )

    evidence = f"http={status_code}"
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return Check(
            "windows",
            "research_worker_freshness",
            "WARN",
            f"{evidence}; invalid_json",
            int((time.perf_counter() - started) * 1000),
        )
    if not isinstance(parsed, dict):
        return Check(
            "windows",
            "research_worker_freshness",
            "WARN",
            f"{evidence}; invalid_payload",
            int((time.perf_counter() - started) * 1000),
        )

    worker_status = str(parsed.get("status") or "unknown")
    summary = parsed.get("summary") if isinstance(parsed.get("summary"), dict) else {}
    safety = parsed.get("safety") if isinstance(parsed.get("safety"), dict) else {}
    freshness = parsed.get("freshness") if isinstance(parsed.get("freshness"), dict) else {}
    schedule = parsed.get("schedule") if isinstance(parsed.get("schedule"), dict) else {}

    age = freshness.get("age_seconds")
    if age is None:
        age = _age_seconds(parsed.get("generated_at"))
    try:
        age_int = int(age) if age is not None else None
    except (TypeError, ValueError):
        age_int = None

    failed_count = int(summary.get("failed_count") or 0)
    safety_clear = bool(summary.get("safety_clear")) or (
        safety.get("paper_only") is True
        and safety.get("live_trading_enabled") is False
        and safety.get("telegram_sends_enabled") is False
    )
    schedule_status = str(schedule.get("status") or "unknown")
    task_result = str(
        schedule.get("last_task_result_label") or schedule.get("last_task_result") or "unknown"
    )
    task_ok = schedule.get("last_result_ok")

    status = "PASS" if 200 <= status_code < 300 and worker_status in {"ok", "stale"} else "WARN"
    reasons: list[str] = []
    if not safety_clear:
        status = "WARN"
        reasons.append("unsafe")
    if failed_count:
        status = "WARN"
        reasons.append(f"failed_commands={failed_count}")
    if age_int is None:
        status = "WARN"
        reasons.append("age_unknown")
    elif age_int > WINDOWS_RESEARCH_WORKER_MAX_AGE_SECONDS:
        status = "WARN"
        reasons.append("manifest_stale")
    if schedule_status not in {"ok", "unavailable", "unknown"}:
        status = "WARN"
        reasons.append(f"task_status={schedule_status}")
    if task_ok is False:
        status = "WARN"
        reasons.append(f"task_result={task_result}")

    evidence += f"; status={worker_status}"
    if parsed.get("run_id"):
        evidence += f"; run_id={parsed.get('run_id')}"
    if parsed.get("git_sha_short"):
        evidence += f"; sha={parsed.get('git_sha_short')}"
    if age_int is not None:
        evidence += f"; age_seconds={age_int}"
    evidence += f"; safety_clear={safety_clear}; failed_count={failed_count}"
    if schedule:
        evidence += f"; task={schedule_status}/{task_result}"
    if reasons:
        evidence += f"; reasons={','.join(reasons)}"
    return Check(
        "windows",
        "research_worker_freshness",
        status,
        evidence,
        int((time.perf_counter() - started) * 1000),
    )


def probe_safety() -> list[Check]:
    result = run(
        [sys.executable, "scripts/ops/safety_status_report.py", "--json"], cwd=ROOT, timeout=30
    )
    if not result.ok:
        return [
            Check("safety", "safety_status_report", "FAIL", short_error(result), result.duration_ms)
        ]
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [Check("safety", "safety_status_report", "FAIL", "invalid JSON", result.duration_ms)]
    checks: list[Check] = []
    kill = report.get("kill_switch", {})
    inferred_active = kill.get("inferred_active")
    state_source = str(kill.get("state_source") or "unknown")
    state_confidence = str(kill.get("state_confidence") or "unknown")
    state_is_bound = state_source in {"last_transition", "operator_baseline"}
    explicitly_inactive = inferred_active is False and state_is_bound
    rendered_state = (
        "true" if inferred_active is True else "false" if inferred_active is False else "unknown"
    )
    checks.append(
        Check(
            "safety",
            "kill_switch_inactive",
            "PASS" if explicitly_inactive else "FAIL",
            (
                f"inferred_active={rendered_state}; source={state_source}; "
                f"confidence={state_confidence}"
            ),
        )
    )
    firewall = report.get("confirmation_firewall", {})
    expired = int(firewall.get("expired_pending_count") or 0)
    checks.append(
        Check(
            "safety",
            "confirmation_firewall_expired_pending",
            "PASS" if expired == 0 else "WARN",
            f"expired_pending_count={expired}",
        )
    )
    schema = (report.get("autonomy_audit") or {}).get("schema", {})
    leaks = int(schema.get("unredacted_secret_risk_records") or 0)
    checks.append(
        Check(
            "safety",
            "autonomy_audit_redaction",
            "PASS" if leaks == 0 else "FAIL",
            f"unredacted_secret_risk_records={leaks}",
        )
    )
    return checks


def probe_provenance() -> list[Check]:
    result = run(
        [sys.executable, "scripts/ops/provenance_verify.py", "--older-than-hours", "24"],
        cwd=ROOT,
        timeout=60,
    )
    try:
        report = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return [
            Check("provenance", "artifact_envelopes", "WARN", "invalid JSON", result.duration_ms)
        ]
    status = "PASS" if result.ok and report.get("ok") else "WARN"
    evidence = (
        f"checked={report.get('checked', 0)}; "
        f"missing_or_invalid={report.get('missing_or_invalid', 0)}"
    )
    return [Check("provenance", "artifact_envelopes", status, evidence, result.duration_ms)]


# WARN-by-design: each soaking routine emits WARN until its `gate_state` flips
# from "collecting" to "ready_for_artifact_review", which requires the
# scheduled-success threshold in `infra/org-repos.yaml > soak_tracking.
# required_scheduled_successes` to be met. The current cohort started soaking
# 2026-04-26 with cutover gates documented at:
#   - `docs/org/backtest-weekly-shadow-soak-2026-04-26.md`  (4 weekly cycles)
#   - `docs/org/threat-refresh-shadow-soak-2026-04-26.md`   (24 cycles / ~4 days)
#   - `docs/org/content-engine-shadow-soak-2026-04-26.md`   (7 daily cycles)
# These WARNs are the visible read-back of an in-progress soak window, NOT a
# regression. The runbooks (`docs/ops/<routine>-runbook.md`) cover what would
# flip each gate to PASS. Re-evaluate after the targeted cycle counts complete:
# backtest-weekly ~2026-05-24 (4 Saturdays), threat-refresh and content-engine
# converge sooner. Memory ref: `project_remote_shadow_soak_gate.md`.
def probe_routines(*, no_external: bool) -> list[Check]:
    cmd = [sys.executable, "scripts/ops/routine_soak_status.py", "--format", "json"]
    if no_external:
        cmd.append("--no-external")
    result = run(cmd, cwd=ROOT, timeout=60)
    if not result.ok:
        return [
            Check(
                "routines", "routine_soak_status", "WARN", short_error(result), result.duration_ms
            )
        ]
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        return [
            Check("routines", "routine_soak_status", "WARN", "invalid JSON", result.duration_ms)
        ]
    checks: list[Check] = []
    for routine in report.get("routines", []):
        gate = routine.get("gate_state")
        latest = (routine.get("github_runs") or {}).get("latest_run") or {}
        status = "PASS" if gate == "ready_for_artifact_review" else "WARN"
        checks.append(
            Check(
                "routines",
                str(routine.get("id")),
                status,
                f"gate={gate}; latest={latest.get('event')}/{latest.get('conclusion')} {latest.get('created_at')}",
            )
        )
    return checks


def probe_github(*, no_external: bool) -> list[Check]:
    if no_external:
        return [Check("github", "open_prs", "SKIP", "--no-external")]
    result = run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            "arigatoexpress/Sapphire",
            "--json",
            "number,title,state,isDraft",
        ],
        cwd=ROOT,
    )
    if not result.ok:
        return [Check("github", "open_prs", "WARN", short_error(result), result.duration_ms)]
    prs = json.loads(result.stdout or "[]")
    non_draft = [pr for pr in prs if not pr.get("isDraft")]
    status = "PASS" if not non_draft else "WARN"
    return [
        Check(
            "github",
            "open_prs",
            status,
            f"open={len(prs)} non_draft={len(non_draft)}",
            result.duration_ms,
        )
    ]


# WARN-by-design (manual_gate): the readiness gates emitted by
# `google_production_test_readiness.py` include hard-coded `manual_gate`
# entries that the sweep maps to WARN (see `manual_gate -> WARN` mapping
# below). The most-visible one is `gate_gemini_api_or_vertex_live_calls`,
# which is intentionally NEVER allowed to auto-flip to PASS — it represents
# "this harness must not invoke live Gemini/Vertex calls without an explicit
# human-defined target/budget/cap". The runbook
# `docs/ops/production-readiness-matrix-runbook.md` formalizes this:
#   "Manual gates are expected for surfaces such as live Gemini/Vertex calls,
#    BigQuery/GCS writes, Veo generation, and LaunchAgent retargeting."
# This gate would only flip to PASS by removing the manual_gate guardrail in
# `google_production_test_readiness.py`, which would weaken the safety
# posture. Leave as WARN. Re-evaluate only if Sapphire ever moves Gemini/Vertex
# from "manual-target each invocation" to "always-on with budget caps".
def probe_google_readiness(args: argparse.Namespace, *, no_external: bool) -> list[Check]:
    cmd = [
        sys.executable,
        "scripts/ops/google_production_test_readiness.py",
        "--project",
        args.project,
        "--region",
        args.region,
        "--membership",
        "google_developer_premium",
        "--membership",
        "google_ai_plus",
        "--include-cost",
        "--format",
        "json",
    ]
    if no_external:
        cmd.append("--no-external")
    result = run(cmd, cwd=ROOT, timeout=90)
    if not result.ok:
        return [
            Check(
                "gcp",
                "google_production_readiness",
                "WARN",
                short_error(result),
                result.duration_ms,
            )
        ]
    report = json.loads(result.stdout)
    summary = report.get("summary", {})
    gates = report.get("readiness_gates", [])
    checks = [
        Check(
            "gcp",
            "google_production_readiness_summary",
            "PASS" if summary.get("ready_gcp_projects") else "WARN",
            f"ready_projects={summary.get('ready_gcp_projects')}; vertex={summary.get('vertex_resource_totals')}; cost={summary.get('cost_posture_included')}",
            result.duration_ms,
        )
    ]
    for gate in gates:
        gate_status = str(gate.get("status"))
        status = (
            "PASS"
            if gate_status == "pass"
            else (
                "WARN"
                if gate_status in {"manual_gate", "blocked", "unknown", "needs_attention"}
                else "FAIL"
            )
        )
        checks.append(
            Check("gcp", f"gate_{gate.get('id')}", status, f"{gate_status}: {gate.get('evidence')}")
        )
    return checks


def probe_telegram(env: dict[str, str]) -> list[Check]:
    token = env.get("TELEGRAM_BOT_TOKEN") or env.get("RELAY_READER_TOKEN")
    if not token:
        return [Check("telegram", "bot_api_get_me", "WARN", "token not available to probe")]
    checks = [
        telegram_check("bot_api_get_me", token, "getMe"),
        telegram_check("bot_api_get_webhook_info", token, "getWebhookInfo"),
    ]
    return checks


def probe_gcp_writes(args: argparse.Namespace) -> list[Check]:
    probe_id = datetime.now(UTC).strftime("sapphire-prod-readiness-%Y%m%dT%H%M%SZ")
    payload = {
        "probe_id": probe_id,
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": "production_readiness_sweep",
        "mode": "bounded_live_write_probe",
    }
    checks: list[Check] = []
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
        json.dump(payload, handle, sort_keys=True)
        handle.write("\n")
        temp_path = Path(handle.name)
    try:
        gcs_path = f"gs://{args.bucket}/ops/production-readiness/{probe_id}.json"
        gcs = run(["gcloud", "storage", "cp", str(temp_path), gcs_path], cwd=ROOT, timeout=60)
        checks.append(
            Check(
                "gcp_write",
                "gcs_probe_object",
                "PASS" if gcs.ok else "FAIL",
                gcs_path if gcs.ok else short_error(gcs),
                gcs.duration_ms,
            )
        )

        table_ref = f"`{args.project}.{args.dataset}.{args.bq_table}`"
        create_sql = (
            f"CREATE TABLE IF NOT EXISTS {table_ref} "
            "(probe_id STRING, timestamp TIMESTAMP, source STRING, mode STRING)"
        )
        create = bq_query(args.project, create_sql)
        checks.append(
            Check(
                "gcp_write",
                "bq_probe_table",
                "PASS" if create.ok else "FAIL",
                f"{args.dataset}.{args.bq_table}" if create.ok else short_error(create),
                create.duration_ms,
            )
        )
        if create.ok:
            # Operator-supplied BigQuery probe table, not user input.
            insert_sql = (
                f"INSERT INTO {table_ref} (probe_id, timestamp, source, mode) "  # nosec B608
                f"VALUES ('{probe_id}', CURRENT_TIMESTAMP(), 'production_readiness_sweep', 'bounded_live_write_probe')"
            )
            insert = bq_query(args.project, insert_sql)
            checks.append(
                Check(
                    "gcp_write",
                    "bq_probe_insert",
                    "PASS" if insert.ok else "FAIL",
                    f"probe_id={probe_id}" if insert.ok else short_error(insert),
                    insert.duration_ms,
                )
            )
    finally:
        with contextlib_suppress():
            temp_path.unlink()
    return checks


def probe_gemini_live(args: argparse.Namespace) -> list[Check]:
    env = os.environ.copy()
    env.update(
        {
            "GOOGLE_GENAI_USE_VERTEXAI": "true",
            "GOOGLE_CLOUD_PROJECT": args.project,
            "GOOGLE_CLOUD_LOCATION": args.region,
        }
    )
    with tempfile.TemporaryDirectory(prefix="sapphire-gemini-probe-") as probe_dir:
        result = run(
            [
                "gemini",
                "--skip-trust",
                "--approval-mode",
                "plan",
                "--output-format",
                "json",
                "--model",
                args.gemini_model,
                "--prompt",
                GEMINI_PROBE_PROMPT,
            ],
            cwd=Path(probe_dir),
            env=env,
            timeout=60,
        )
    if not result.ok:
        return [
            Check("gemini", "vertex_live_probe", "WARN", short_error(result), result.duration_ms)
        ]
    payload = parse_json_from_mixed_output(result.stdout)
    if not isinstance(payload, dict):
        return [
            Check(
                "gemini",
                "vertex_live_probe",
                "WARN",
                "invalid Gemini JSON output",
                result.duration_ms,
            )
        ]
    response = str(payload.get("response", "")).strip()
    stats = payload.get("stats") if isinstance(payload.get("stats"), dict) else {}
    model_stats = ((stats.get("models") or {}) if isinstance(stats, dict) else {}).get(
        args.gemini_model, {}
    )
    tokens = model_stats.get("tokens", {}) if isinstance(model_stats, dict) else {}
    tools = stats.get("tools", {}) if isinstance(stats, dict) else {}
    ok = response == GEMINI_PROBE_RESPONSE and int(tools.get("totalCalls") or 0) == 0
    evidence = (
        f"model={args.gemini_model}; response_ok={ok}; "
        f"tool_calls={tools.get('totalCalls', 0)}; total_tokens={tokens.get('total', 'unknown')}"
    )
    return [
        Check("gemini", "vertex_live_probe", "PASS" if ok else "WARN", evidence, result.duration_ms)
    ]


def parse_json_from_mixed_output(output: str) -> dict[str, Any] | None:
    start = output.find("{")
    end = output.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        parsed = json.loads(output[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def apply_gemini_probe_to_google_gate(checks: list[Check], gemini_checks: list[Check]) -> None:
    probe = next((check for check in gemini_checks if check.name == "vertex_live_probe"), None)
    if probe is None or probe.status != "PASS":
        return
    for check in checks:
        if check.category == "gcp" and check.name == "gate_gemini_api_or_vertex_live_calls":
            check.status = "PASS"
            check.evidence = f"pass: Vertex Gemini live probe succeeded; {probe.evidence}"
            return


def bq_query(project: str, sql: str) -> RunResult:
    return run(
        ["bq", "query", "--project_id", project, "--use_legacy_sql=false", "--quiet", sql],
        cwd=ROOT,
        timeout=90,
    )


def telegram_check(name: str, token: str, method: str) -> Check:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(  # nosec B310 - fixed Telegram HTTPS API base.
            f"https://api.telegram.org/bot{token}/{method}", timeout=10
        ) as response:
            body = response.read(1024 * 1024)
            status_code = response.status
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        body = exc.read(1024 * 1024)
    except Exception as exc:
        return Check(
            "telegram",
            name,
            "WARN",
            exc.__class__.__name__,
            int((time.perf_counter() - started) * 1000),
        )
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        parsed = {}
    ok = bool(parsed.get("ok")) and status_code == 200
    result = parsed.get("result") if isinstance(parsed.get("result"), dict) else {}
    public_hint = ""
    if method == "getMe" and result.get("username"):
        public_hint = f"; username=@{result['username']}"
    elif method == "getWebhookInfo":
        public_hint = f"; pending_update_count={result.get('pending_update_count', 'unknown')}"
    return Check(
        "telegram",
        name,
        "PASS" if ok else "WARN",
        f"http={status_code}{public_hint}",
        int((time.perf_counter() - started) * 1000),
    )


def http_check(
    category: str,
    name: str,
    url: str,
    *,
    auth: tuple[str, str] | None = None,
    warn_on_error: bool = False,
    expect_json: dict[str, Any] | None = None,
) -> Check:
    """Probe an HTTP endpoint.

    `expect_json` turns the probe into an *identity assertion*: the response body
    must parse as a JSON object containing every listed key with the listed
    value, otherwise the check FAILs with `identity_mismatch`. Without it, a
    health check only proves "something answered on this port" — which is how
    `dashboard_health` spent months passing against Open WebUI squatting :8080
    and returning its own `{"status": true}`. Matching is a subset match so a
    service adding new fields does not break the probe.
    """
    started = time.perf_counter()
    request = urllib.request.Request(url)
    if auth:
        token = base64.b64encode(f"{auth[0]}:{auth[1]}".encode()).decode()
        request.add_header("Authorization", f"Basic {token}")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # nosec B310 - readiness probe URL is from static check list.
            status_code = response.status
            body = response.read(1024 * 1024)
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        body = exc.read(4096)
    except Exception as exc:
        return Check(
            category,
            name,
            "WARN" if warn_on_error else "FAIL",
            exc.__class__.__name__,
            int((time.perf_counter() - started) * 1000),
        )
    status = "PASS" if 200 <= status_code < 300 else ("WARN" if warn_on_error else "FAIL")
    hint = ""
    parsed: Any = None
    with contextlib_suppress():
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            if parsed.get("status"):
                hint = f"; status={parsed.get('status')}"
            elif parsed.get("healthy") is not None:
                hint = f"; healthy={parsed.get('healthy')}"

    if expect_json and status == "PASS":
        if not isinstance(parsed, dict):
            status = "FAIL"
            hint += "; identity_mismatch=body_not_json_object"
        else:
            mismatched = [
                f"{key}={parsed.get(key)!r}!={value!r}"
                for key, value in expect_json.items()
                if parsed.get(key) != value
            ]
            if mismatched:
                status = "FAIL"
                hint += f"; identity_mismatch={','.join(mismatched)}"

    return Check(
        category,
        name,
        status,
        f"http={status_code}{hint}",
        int((time.perf_counter() - started) * 1000),
    )


def tcp_check(
    category: str,
    name: str,
    host: str,
    port: int,
    *,
    warn_on_error: bool = False,
) -> Check:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=windows_tcp_timeout_seconds()):
            return Check(
                category,
                name,
                "PASS",
                f"{host}:{port} reachable",
                int((time.perf_counter() - started) * 1000),
            )
    except OSError as exc:
        return Check(
            category,
            name,
            "WARN" if warn_on_error else "FAIL",
            exc.__class__.__name__,
            int((time.perf_counter() - started) * 1000),
        )


def windows_http_timeout_seconds() -> float:
    return positive_float_env(
        "SAPPHIRE_WINDOWS_HTTP_TIMEOUT_SECONDS",
        DEFAULT_WINDOWS_HTTP_TIMEOUT_SECONDS,
    )


def windows_tcp_timeout_seconds() -> float:
    return positive_float_env(
        "SAPPHIRE_WINDOWS_TCP_TIMEOUT_SECONDS",
        DEFAULT_WINDOWS_TCP_TIMEOUT_SECONDS,
    )


def positive_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str
    duration_ms: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 20,
    env: dict[str, str] | None = None,
) -> RunResult:
    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or ROOT),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return RunResult(
            proc.returncode, proc.stdout, proc.stderr, int((time.perf_counter() - started) * 1000)
        )
    except subprocess.TimeoutExpired as exc:
        return RunResult(
            124,
            exc.stdout or "",
            exc.stderr or "timeout",
            int((time.perf_counter() - started) * 1000),
        )
    except FileNotFoundError as exc:
        return RunResult(127, "", str(exc), int((time.perf_counter() - started) * 1000))


def short_error(result: RunResult) -> str:
    text = (result.stderr or result.stdout or f"exit={result.returncode}").strip().splitlines()
    return (text[-1] if text else f"exit={result.returncode}")[:240]


def summarize(checks: list[Check]) -> dict[str, int]:
    return {
        "pass": sum(1 for check in checks if check.status == "PASS"),
        "warn": sum(1 for check in checks if check.status == "WARN"),
        "fail": sum(1 for check in checks if check.status == "FAIL"),
        "skip": sum(1 for check in checks if check.status == "SKIP"),
        "total": len(checks),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Sapphire Production Readiness Sweep",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Duration: `{report['duration_ms']} ms`",
        f"- Checks: `{summary['pass']} pass`, `{summary['warn']} warn`, `{summary['fail']} fail`, `{summary['skip']} skip`",
        "",
        "| Category | Check | Status | Evidence |",
        "|---|---|---:|---|",
    ]
    for check in report["checks"]:
        lines.append(
            "| {category} | {name} | {status} | {evidence} |".format(
                category=check["category"],
                name=check["name"],
                status=check["status"],
                evidence=str(check["evidence"]).replace("|", "\\|").replace("\n", " "),
            )
        )
    return "\n".join(lines) + "\n"


class contextlib_suppress:
    def __enter__(self) -> None:
        return None

    def __exit__(self, *_exc: object) -> bool:
        return True


if __name__ == "__main__":
    raise SystemExit(main())
