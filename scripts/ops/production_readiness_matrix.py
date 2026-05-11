#!/usr/bin/env python3
"""Full-system Sapphire production-readiness matrix.

This is the aggressive but safe control-tower sweep for Sapphire OS. It
enumerates core surfaces, runs read-only or dry-run probes, and emits a single
operator report that can be repeated before production testing or after any
significant merge.

The command never reads secret payloads, sends Telegram messages, executes
trades, writes to GCP/Foundry/BigQuery/GCS, dispatches workflows, mutates
Gmail/Drive, or retargets LaunchAgents.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import google_production_test_readiness
import hermes_runtime_readiness
import org_status
import routine_soak_status
import safety_status_report

DEFAULT_OUTPUT = ROOT / "data" / "readiness" / "production-readiness-latest.md"
DEFAULT_PROJECT = "tho-ai-agent"
DEFAULT_REGION = "us-central1"
DEFAULT_MEMBERSHIPS = ("google_developer_premium", "google_ai_plus")

ALWAYS_ON_LAUNCHAGENTS = (
    "com.sapphire.pm-bot",
    "com.sapphire.control-plane",
    "com.sapphire.regional-intel",
    "com.sapphire.cloudflare-tunnel",
    "com.sapphire.pm-bot-tunnel",
    "com.sapphire.heartbeat",
    "com.sapphire.openbb-api",
    "com.sapphire.inference-proxy",
    "com.sapphire.dashboard",
    "com.sapphire.signal-logger",
    "actions.runner.arigatoexpress-Sapphire.ari-macbook-sapphire",
)

LOCAL_HTTP_PROBES = (
    {
        "id": "local_inference_proxy",
        "url": "http://127.0.0.1:11435/health",
        "ok_statuses": (200,),
        "area": "local-runtime",
    },
    {
        "id": "local_dashboard",
        "url": "http://127.0.0.1:8080/health",
        "ok_statuses": (200, 401, 403),
        "area": "local-runtime",
    },
    {
        "id": "local_control_plane",
        "url": "http://127.0.0.1:8082/health",
        "ok_statuses": (200, 401, 403, 503),
        "area": "local-runtime",
    },
    {
        "id": "local_signal_logger",
        "url": "http://127.0.0.1:18081/health",
        "ok_statuses": (200, 401, 403),
        "area": "local-runtime",
    },
    {
        "id": "local_regional_intel",
        "url": "http://127.0.0.1:8787/api/health",
        "ok_statuses": (200, 401, 403),
        "area": "regional-intel",
    },
    {
        "id": "local_openbb",
        "url": "http://127.0.0.1:6900/health",
        "ok_statuses": (200, 401, 403, 404),
        "area": "market-data",
    },
)


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0


Runner = Callable[[list[str]], CommandResult]
HttpProbe = Callable[[str, tuple[int, ...]], dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_command(args: list[str], *, timeout: int = 45) -> CommandResult:
    executable = args[0]
    if shutil.which(executable) is None:
        return CommandResult(False, stderr=f"{executable} not found on PATH", returncode=127)
    try:
        proc = subprocess.run(
            args,
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(False, stderr=f"{' '.join(args[:3])} timed out", returncode=124)
    return CommandResult(
        proc.returncode == 0,
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
    )


def http_probe(url: str, ok_statuses: tuple[int, ...]) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=4) as response:  # noqa: S310  # nosec B310
            status = int(response.status)
            return {
                "available": status in ok_statuses,
                "status": status,
                "error": "",
            }
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        return {
            "available": status in ok_statuses,
            "status": status,
            "error": "",
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "available": False,
            "status": None,
            "error": compact(str(exc), 160),
        }


def collect_matrix(
    *,
    external: bool = True,
    include_cost: bool = False,
    projects: list[str] | None = None,
    regions: list[str] | None = None,
    memberships: list[str] | None = None,
    runner: Runner = run_command,
    http: HttpProbe = http_probe,
    ci_report_dir: Path | None = None,
) -> dict[str, Any]:
    selected_projects = projects or [DEFAULT_PROJECT]
    selected_regions = regions or [DEFAULT_REGION]
    selected_memberships = memberships or list(DEFAULT_MEMBERSHIPS)
    surfaces: list[dict[str, Any]] = []
    subreports: dict[str, Any] = {}

    surfaces.extend(git_surfaces(runner))
    surfaces.extend(local_ci_surfaces(ci_report_dir or ROOT / "data" / "ci"))
    surfaces.extend(org_surfaces(external=False))
    surfaces.extend(hermes_surfaces())
    surfaces.extend(safety_surfaces())
    surfaces.extend(media_surfaces())

    if external:
        surfaces.extend(github_surfaces(runner))
        surfaces.extend(launchagent_surfaces(runner))
        surfaces.extend(local_http_surfaces(http))
        surfaces.extend(required_secret_surfaces(runner))
        surfaces.extend(frontend_drift_surfaces(runner))
        subreports["routine_soak"] = collect_routine_soak(external=True)
        surfaces.extend(routine_surfaces(subreports["routine_soak"]))
    else:
        subreports["routine_soak"] = collect_routine_soak(external=False)
        surfaces.extend(routine_surfaces(subreports["routine_soak"]))

    subreports["google_readiness"] = google_production_test_readiness.collect_readiness(
        projects=selected_projects,
        regions=selected_regions,
        memberships=selected_memberships,
        external=external,
        include_cost=include_cost,
    )
    surfaces.extend(google_surfaces(subreports["google_readiness"]))

    report = {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "mode": "read-only" if external else "no-external",
        "projects": selected_projects,
        "regions": selected_regions,
        "memberships": selected_memberships,
        "guardrails": [
            "No secret values are read or printed.",
            "No real trades, money movement, Telegram sends, Gmail/Drive mutations, GCP/Foundry/BigQuery/GCS writes, workflow dispatches, billing changes, API enablement, or LaunchAgent retargeting are performed.",
            "External probes are read-only metadata, health checks, or local dry-run status checks.",
            "Any live action must name the exact target, budget/blast-radius cap, output path, and rollback.",
        ],
        "summary": {},
        "surfaces": surfaces,
        "subreports": subreports,
        "next_actions": next_actions(surfaces),
    }
    report["summary"] = summarize_surfaces(surfaces)
    return report


def git_surfaces(runner: Runner) -> list[dict[str, Any]]:
    status = runner(["git", "status", "--short", "--branch"])
    head = runner(["git", "rev-parse", "--short=12", "HEAD"])
    if not status.ok:
        return [
            surface(
                "repo_git_status",
                "repo",
                "fail",
                "git status failed",
                compact(status.stderr or status.stdout),
            )
        ]
    dirty_lines = [
        line
        for line in status.stdout.splitlines()
        if line and not line.startswith("##") and not line.startswith("!!")
    ]
    branch_line = status.stdout.splitlines()[0] if status.stdout.splitlines() else "unknown"
    evidence = f"{branch_line}; dirty entries={len(dirty_lines)}"
    if head.ok:
        evidence = f"{evidence}; head={head.stdout.strip()}"
    return [
        surface(
            "repo_git_status",
            "repo",
            "pass" if not dirty_lines else "warn",
            evidence,
            "Keep canonical Sapphire clean; isolate PR work in /Users/aribs/Code/_worktrees/.",
        )
    ]


def local_ci_surfaces(report_dir: Path) -> list[dict[str, Any]]:
    latest = latest_local_ci_report(report_dir)
    if not latest:
        return [
            surface(
                "local_ci_latest",
                "repo",
                "warn",
                "No local CI report found.",
                "Run scripts/ops/local_ci_verify.py before production promotion.",
            )
        ]
    verdict = str(latest.get("verdict") or "UNKNOWN")
    completed_at = latest.get("completed_at") or latest.get("started_at") or "unknown"
    head = latest.get("head", "")[:12]
    checks = latest.get("checks", [])
    failed = [item.get("name") for item in checks if item.get("status") == "FAIL"]
    status = "pass" if verdict == "PASS" else "fail"
    evidence = f"{verdict} at {head or 'unknown'} ({completed_at}); checks={len(checks)}"
    if failed:
        evidence = f"{evidence}; failed={', '.join(str(item) for item in failed)}"
    return [
        surface(
            "local_ci_latest",
            "repo",
            status,
            evidence,
            "Fix failing checks before merging or promoting production-adjacent changes.",
        )
    ]


def latest_local_ci_report(report_dir: Path) -> dict[str, Any] | None:
    candidates = sorted(report_dir.glob("local-ci-verify-*.json"))
    for path in reversed(candidates):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            return data
    return None


def org_surfaces(*, external: bool) -> list[dict[str, Any]]:
    report = org_status.collect_status(org_status.load_manifest(), external=external)
    summary = report.get("summary", {})
    dirty_repos = summary.get("dirty_repos", [])
    missing = summary.get("missing_local_repos", [])
    dirty_worktrees = summary.get("dirty_worktrees", [])
    surfaces = [
        surface(
            "org_repos",
            "org",
            "pass" if not dirty_repos and not missing else "warn",
            f"repos={summary.get('repo_count', 0)}, dirty={len(dirty_repos)}, missing={len(missing)}",
            "Clean dirty or missing repos before production cutover.",
        ),
        surface(
            "org_worktrees",
            "org",
            "pass" if not dirty_worktrees else "warn",
            f"worktrees={summary.get('worktree_count', 0)}, dirty={', '.join(dirty_worktrees) or 'none'}",
            "Remove or resolve stale dirty worktrees after preserving user WIP.",
        ),
        surface(
            "org_ci_strategy",
            "ci",
            "pass",
            json.dumps(summary.get("ci_strategies", {}), sort_keys=True),
            "Keep no-spend CI strategies explicit per repo.",
        ),
        surface(
            "hermes_skill_surface",
            "agents",
            "warn" if summary.get("hermes_production_adjacent_skills", 0) else "pass",
            f"production-adjacent skills={summary.get('hermes_production_adjacent_skills', 0)}",
            "Keep Hermes production-adjacent commands gated through CommandGuard and dry-run defaults.",
        ),
    ]
    return surfaces


def hermes_surfaces() -> list[dict[str, Any]]:
    report = hermes_runtime_readiness.collect_readiness()
    required = report.get("required_runtime_controls", {})
    quick = report.get("quick_commands", {})
    status = report.get("status")
    if status == "fail":
        matrix_status = "fail"
    elif status == "pass":
        matrix_status = "pass"
    else:
        matrix_status = "warn"
    evidence = (
        f"runtime_guard={'yes' if required.get('runtime_quick_exec_command_guard') else 'no'}, "
        f"sapphire_repo_path_env={'yes' if required.get('launchagent_sapphire_repo_path_env') else 'no'}, "
        f"exec_quick={quick.get('exec_quick_command_count', 0)}, "
        f"prod_adjacent_exec={quick.get('production_adjacent_exec_count', 0)}"
    )
    return [
        surface(
            "hermes_runtime_quick_exec_guard",
            "agents",
            matrix_status,
            evidence,
            str(
                report.get("next_action")
                or "Keep Hermes quick exec gated through Sapphire CommandGuard."
            ),
        )
    ]


def safety_surfaces() -> list[dict[str, Any]]:
    report = safety_status_report.build_report(recent=5)
    firewall = report["confirmation_firewall"]
    kill_switch = report["kill_switch"]
    autonomy = report["autonomy_audit"]
    schema = autonomy.get("schema", {})
    return [
        surface(
            "confirmation_firewall",
            "safety",
            "pass" if firewall.get("expired_pending_count", 0) == 0 else "warn",
            f"pending={firewall.get('pending_count', 0)}, expired={firewall.get('expired_pending_count', 0)}",
            "Archive expired confirmations so financial approvals cannot linger in ambiguous state.",
        ),
        surface(
            "kill_switch",
            "safety",
            "pass" if kill_switch.get("inferred_active") is False else "manual_gate",
            f"active={kill_switch.get('inferred_active')}, source={kill_switch.get('state_source')}",
            "Confirm kill-switch state before live trading or money movement.",
        ),
        surface(
            "autonomy_audit_schema",
            "safety",
            "pass"
            if schema.get("malformed_lines", 0) == 0
            and not schema.get("missing_required_fields")
            and schema.get("unredacted_secret_risk_records", 0) == 0
            else "fail",
            f"valid={schema.get('valid_records', 0)}, malformed={schema.get('malformed_lines', 0)}, secret-risk={schema.get('unredacted_secret_risk_records', 0)}",
            "Fix audit schema or redaction failures before increasing autonomy.",
        ),
    ]


def media_surfaces() -> list[dict[str, Any]]:
    try:
        from lib.media.factory import media_factory_status
    except Exception as exc:  # pragma: no cover - defensive import guard
        return [
            surface(
                "media_factory_status",
                "media",
                "fail",
                f"media import failed: {type(exc).__name__}",
                "Fix media module import before live media work orders.",
            )
        ]
    status = media_factory_status()
    return [
        surface(
            "media_factory_status",
            "media",
            "pass" if status.get("count", 0) > 0 else "warn",
            f"dry-run runs={status.get('count', 0)}, missing={len(status.get('missing', []))}",
            "Generate at least one dry-run media readiness run before live image/audio/video APIs.",
        )
    ]


def github_surfaces(runner: Runner) -> list[dict[str, Any]]:
    prs = gh_json(
        runner,
        [
            "gh",
            "pr",
            "list",
            "--repo",
            "arigatoexpress/Sapphire",
            "--state",
            "open",
            "--limit",
            "50",
            "--json",
            "number,title,isDraft",
        ],
    )
    issues = gh_json(
        runner,
        [
            "gh",
            "issue",
            "list",
            "--repo",
            "arigatoexpress/Sapphire",
            "--state",
            "open",
            "--limit",
            "50",
            "--json",
            "number,title",
        ],
    )
    surfaces = []
    if prs is None:
        surfaces.append(
            surface("github_open_prs", "github", "warn", "unavailable", "Check gh auth.")
        )
    else:
        drafts = [item for item in prs if item.get("isDraft")]
        surfaces.append(
            surface(
                "github_open_prs",
                "github",
                "pass" if not prs else "warn",
                f"open={len(prs)}, drafts={len(drafts)}",
                "Clear or classify open PRs before production cutover.",
            )
        )
    if issues is None:
        surfaces.append(
            surface("github_open_issues", "github", "warn", "unavailable", "Check gh auth.")
        )
    else:
        surfaces.append(
            surface(
                "github_open_issues",
                "github",
                "pass" if not issues else "warn",
                f"open={len(issues)}",
                "Triage open issues or turn them into explicit production blockers.",
            )
        )
    return surfaces


def gh_json(runner: Runner, args: list[str]) -> list[dict[str, Any]] | None:
    result = runner(args)
    if not result.ok:
        return None
    try:
        data = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def launchagent_surfaces(runner: Runner) -> list[dict[str, Any]]:
    result = runner(["launchctl", "list"])
    if not result.ok:
        return [
            surface(
                "launchagents",
                "local-runtime",
                "warn",
                compact(result.stderr or result.stdout),
                "Run on macOS operator host for LaunchAgent visibility.",
            )
        ]
    rows = parse_launchctl_list(result.stdout)
    missing = [label for label in ALWAYS_ON_LAUNCHAGENTS if label not in rows]
    not_running = [
        label
        for label in ALWAYS_ON_LAUNCHAGENTS
        if label in rows and rows[label].get("pid") in {"-", ""}
    ]
    return [
        surface(
            "launchagents_always_on",
            "local-runtime",
            "pass" if not missing and not not_running else "warn",
            f"tracked={len(ALWAYS_ON_LAUNCHAGENTS)}, missing={len(missing)}, not_running={len(not_running)}",
            "Inspect missing/not-running LaunchAgents; do not retarget or unload without an exact live-action gate.",
            details={"missing": missing, "not_running": not_running},
        )
    ]


def parse_launchctl_list(output: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        pid, status, label = parts[0], parts[1], parts[2]
        rows[label] = {"pid": pid, "status": status}
    return rows


def local_http_surfaces(http: HttpProbe) -> list[dict[str, Any]]:
    rows = []
    for probe in LOCAL_HTTP_PROBES:
        result = http(probe["url"], tuple(probe["ok_statuses"]))
        status = "pass" if result.get("available") else "warn"
        evidence = (
            f"{probe['url']} -> {result.get('status') or result.get('error') or 'unavailable'}"
        )
        rows.append(
            surface(
                str(probe["id"]),
                str(probe["area"]),
                status,
                evidence,
                "Start or inspect local service if this probe is expected to be live.",
            )
        )
    return rows


def required_secret_surfaces(runner: Runner) -> list[dict[str, Any]]:
    result = runner(["bash", "scripts/ops/check_required_secrets.sh"])
    if not result.ok:
        return [
            surface(
                "required_secret_presence",
                "secrets",
                "fail",
                compact(result.stderr or result.stdout),
                "Fix missing required secret presence without printing secret payloads.",
            )
        ]
    output = result.stdout
    optional_missing = "VIRUSTOTAL_API_KEY: missing" in output
    return [
        surface(
            "required_secret_presence",
            "secrets",
            "pass",
            "required groups ready; optional VirusTotal missing"
            if optional_missing
            else "required groups ready",
            "Optional integrations can remain fallback-mode until exact need is proven.",
        )
    ]


def frontend_drift_surfaces(runner: Runner) -> list[dict[str, Any]]:
    result = runner(["bash", "scripts/ops/check_frontend_endpoint_drift.sh"])
    return [
        surface(
            "frontend_endpoint_drift",
            "frontend",
            "pass" if result.ok else "fail",
            compact(result.stdout if result.ok else result.stderr or result.stdout),
            "Use platform API wrappers and update frontend contracts before shipping UI changes.",
        )
    ]


def collect_routine_soak(*, external: bool) -> dict[str, Any]:
    return routine_soak_status.build_report(
        routine_soak_status.load_manifest(),
        external=external,
        run_limit=50,
    )


def routine_surfaces(report: dict[str, Any]) -> list[dict[str, Any]]:
    summary = report.get("summary", {})
    blocked = int(summary.get("blocked", 0))
    collecting = int(summary.get("collecting", 0))
    ready = int(summary.get("ready_for_artifact_review", 0))
    external_disabled = int(summary.get("external_disabled", 0))
    return [
        surface(
            "routine_soak",
            "routines",
            "fail" if blocked else ("warn" if collecting or external_disabled else "pass"),
            f"ready={ready}, collecting={collecting}, blocked={blocked}, external_disabled={external_disabled}, routines={report.get('routine_count', 0)}",
            "Accumulate scheduled soak cycles and review artifacts before retiring local routines.",
        )
    ]


def google_surfaces(report: dict[str, Any]) -> list[dict[str, Any]]:
    surfaces = []
    for gate in report.get("readiness_gates", []):
        status = str(gate.get("status") or "unknown")
        mapped = {
            "pass": "pass",
            "needs_attention": "warn",
            "manual_gate": "manual_gate",
            "blocked": "blocked",
            "unknown": "warn",
        }.get(status, "warn")
        surfaces.append(
            surface(
                f"google_{gate.get('id')}",
                "google-gcp",
                mapped,
                str(gate.get("evidence") or ""),
                str(gate.get("next_gate") or ""),
            )
        )
    return surfaces


def summarize_surfaces(surfaces: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_area: dict[str, int] = {}
    for item in surfaces:
        by_status[item["status"]] = by_status.get(item["status"], 0) + 1
        by_area[item["area"]] = by_area.get(item["area"], 0) + 1
    hard_blockers = [
        item
        for item in surfaces
        if item["status"] in {"fail", "blocked"}
        and item["id"] not in {"google_launchagent_retargeting"}
    ]
    return {
        "surface_count": len(surfaces),
        "by_status": dict(sorted(by_status.items())),
        "by_area": dict(sorted(by_area.items())),
        "hard_blocker_count": len(hard_blockers),
        "hard_blockers": [item["id"] for item in hard_blockers],
        "production_testing_posture": "go" if not hard_blockers else "blocked",
    }


def next_actions(surfaces: list[dict[str, Any]]) -> list[dict[str, str]]:
    priority = {"fail": 0, "blocked": 1, "warn": 2, "manual_gate": 3, "pass": 4}
    rows = sorted(
        surfaces, key=lambda item: (priority.get(item["status"], 9), item["area"], item["id"])
    )
    actions = []
    for item in rows:
        if item["status"] == "pass":
            continue
        actions.append(
            {
                "id": item["id"],
                "status": item["status"],
                "area": item["area"],
                "next_action": item["next_action"],
            }
        )
        if len(actions) >= 12:
            break
    return actions


def surface(
    item_id: str,
    area: str,
    status: str,
    evidence: str,
    next_action: str,
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "area": area,
        "status": status,
        "evidence": evidence,
        "next_action": next_action,
        "details": details or {},
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Sapphire Production Readiness Matrix",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Mode: `{report['mode']}`",
        f"- Production testing posture: `{summary['production_testing_posture']}`",
        f"- Surfaces checked: `{summary['surface_count']}`",
        f"- Hard blockers: `{summary['hard_blocker_count']}` ({', '.join(summary['hard_blockers']) or 'none'})",
        f"- Status counts: `{json.dumps(summary['by_status'], sort_keys=True)}`",
        "",
        "## Guardrails",
        "",
    ]
    for guardrail in report["guardrails"]:
        lines.append(f"- {guardrail}")

    lines.extend(
        [
            "",
            "## Surfaces",
            "",
            "| Area | Surface | Status | Evidence | Next Action |",
            "|---|---|---|---|---|",
        ]
    )
    for item in sorted(report["surfaces"], key=lambda row: (row["area"], row["id"])):
        lines.append(
            "| {area} | `{id}` | {status} | {evidence} | {next_action} |".format(
                area=item["area"],
                id=item["id"],
                status=item["status"],
                evidence=md_cell(item["evidence"]),
                next_action=md_cell(item["next_action"]),
            )
        )

    lines.extend(["", "## Next Actions", ""])
    if report["next_actions"]:
        for index, item in enumerate(report["next_actions"], start=1):
            lines.append(
                f"{index}. `{item['status']}` `{item['area']}/{item['id']}`: {item['next_action']}"
            )
    else:
        lines.append("No non-pass surfaces in this run.")

    lines.extend(["", "## Routine Soak", ""])
    routine = report.get("subreports", {}).get("routine_soak", {})
    if routine:
        lines.append(f"- External probes: `{'yes' if routine.get('external') else 'no'}`")
        for row in routine.get("routines", []):
            latest = row.get("github_runs", {}).get("latest_run", {})
            lines.append(
                "- `{id}`: `{gate}` scheduled {scheduled}/{required}; latest `{latest}`".format(
                    id=row.get("id"),
                    gate=row.get("gate_state"),
                    scheduled=row.get("github_runs", {}).get("scheduled_success_since_start", 0),
                    required=row.get("required_scheduled_successes", 0),
                    latest=latest.get("conclusion") or latest.get("status") or "none",
                )
            )

    return "\n".join(lines) + "\n"


def write_output(report: dict[str, Any], *, output: Path, output_format: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:
        output.write_text(render_markdown(report), encoding="utf-8")


def compact(value: str, limit: int = 320) -> str:
    cleaned = " ".join(str(value or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def md_cell(value: object) -> str:
    return compact(str(value or "-"), 500).replace("|", "\\|").replace("\n", " ")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-external", action="store_true")
    parser.add_argument("--include-cost", action="store_true")
    parser.add_argument("--project", action="append", dest="projects")
    parser.add_argument("--region", action="append", dest="regions")
    parser.add_argument(
        "--membership",
        action="append",
        choices=sorted(google_production_test_readiness.google_benefits_inventory.MEMBERSHIPS),
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = collect_matrix(
        external=not args.no_external,
        include_cost=args.include_cost,
        projects=args.projects or [DEFAULT_PROJECT],
        regions=args.regions or [DEFAULT_REGION],
        memberships=args.membership or list(DEFAULT_MEMBERSHIPS),
    )
    if args.output:
        write_output(report, output=args.output, output_format=args.format)
    elif args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0 if report["summary"]["hard_blocker_count"] == 0 else 20


if __name__ == "__main__":
    raise SystemExit(main())
