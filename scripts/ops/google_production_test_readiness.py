#!/usr/bin/env python3
"""Google complement production-testing readiness harness for Sapphire OS.

This command ties together the read-only Google benefits, GCP/Vertex, and
Workspace threat-hygiene inventories into one operator report. It is designed
for production testing without production mutation: no model calls, no Gmail or
Drive writes, no GCS/BigQuery writes, no workflow dispatches, and no secret
values are read or printed.
"""

from __future__ import annotations

import argparse
import json
import plistlib
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import cost_posture_report
import gcp_ai_inventory
import google_benefits_inventory
import google_workspace_threat_hygiene

DEFAULT_PROJECTS = ("sapphire-479610",)
DEFAULT_REGIONS = ("us-central1",)
DEFAULT_MEMBERSHIPS = ("google_developer_premium", "google_ai_plus")

ReadinessStatus = dict[str, Any]
CostBuilder = Callable[..., dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def collect_readiness(
    *,
    projects: list[str] | None = None,
    regions: list[str] | None = None,
    memberships: list[str] | None = None,
    workspace_days: int = google_workspace_threat_hygiene.DEFAULT_LOOKBACK_DAYS,
    external: bool = True,
    include_cost: bool = False,
    cost_hours: int = 24,
    cost_log_limit: int = 25,
    benefits_runner: google_benefits_inventory.Runner = google_benefits_inventory._run_json,
    benefits_text_runner: Callable[
        [list[str]], google_benefits_inventory.CommandResult
    ] = google_benefits_inventory._run_text,
    gcp_runner: gcp_ai_inventory.Runner = gcp_ai_inventory._run_json,
    cost_builder: CostBuilder = cost_posture_report.build_report,
) -> dict[str, Any]:
    selected_projects = projects or list(DEFAULT_PROJECTS)
    selected_regions = regions or list(DEFAULT_REGIONS)
    selected_memberships = memberships or list(DEFAULT_MEMBERSHIPS)

    benefits = google_benefits_inventory.collect_inventory(
        project=selected_projects[0],
        memberships=selected_memberships,
        external=external,
        runner=benefits_runner,
        text_runner=benefits_text_runner,
    )
    gcp = gcp_ai_inventory.collect_inventory(
        selected_projects,
        selected_regions,
        external=external,
        runner=gcp_runner,
    )
    workspace = google_workspace_threat_hygiene.build_plan(days=workspace_days)
    cost = _collect_cost(
        selected_projects,
        selected_regions,
        include_cost=include_cost,
        external=external,
        hours=cost_hours,
        log_limit=cost_log_limit,
        cost_builder=cost_builder,
    )

    report: dict[str, Any] = {
        "generated_at": _utc_now(),
        "mode": "read-only" if external else "no-external",
        "projects": selected_projects,
        "regions": selected_regions,
        "memberships": selected_memberships,
        "guardrails": [
            "No secret values are read or printed.",
            "No Gemini API, Vertex AI, Veo, Gmail, Drive, YouTube, Telegram, trading, Foundry, GCS, or BigQuery live write is invoked.",
            "No workflow dispatches, LaunchAgent retargets, billing changes, credit redemptions, API enablement, resource creation, trash, or delete actions are performed.",
            "All production-testing lanes start with local artifacts, dry-run reports, or read-only metadata.",
        ],
        "inputs": {
            "benefits": benefits,
            "gcp": gcp,
            "workspace_threat_hygiene": workspace,
            "cost_posture": cost,
        },
    }
    report["summary"] = _summary(report)
    report["readiness_gates"] = _readiness_gates(report)
    report["production_test_lanes"] = _production_test_lanes(report)
    report["next_safe_commands"] = _next_safe_commands(
        projects=selected_projects,
        regions=selected_regions,
        memberships=selected_memberships,
        workspace_days=workspace_days,
    )
    return report


def _collect_cost(
    projects: list[str],
    regions: list[str],
    *,
    include_cost: bool,
    external: bool,
    hours: int,
    log_limit: int,
    cost_builder: CostBuilder,
) -> dict[str, Any]:
    if not include_cost:
        return {
            "included": False,
            "reason": "Use --include-cost for read-only billing, Cloud Run, logging, and local retention posture.",
        }
    if not external:
        return {
            "included": False,
            "reason": "--include-cost requires external read-only gcloud calls.",
        }
    return {
        "included": True,
        "report": cost_builder(
            projects,
            region=regions[0],
            days=1,
            hours=hours,
            log_limit=log_limit,
            include_local_retention=True,
        ),
    }


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    benefits = report["inputs"]["benefits"]
    gcp = report["inputs"]["gcp"]
    workspace = report["inputs"]["workspace_threat_hygiene"]
    cost = report["inputs"]["cost_posture"]
    vertex_totals = _vertex_totals(gcp)
    ready_projects = [
        project["project"]
        for project in gcp.get("projects", [])
        if project.get("status") == "ready for dry-run AI complement"
    ]
    local = benefits.get("local", {})
    tools = local.get("tools", {})

    return {
        "gemini_cli": _tool_summary(tools, "gemini"),
        "gcloud": _tool_summary(tools, "gcloud"),
        "bigquery_cli": _tool_summary(tools, "bq"),
        "gcs_bucket_count": local.get("gcs_buckets", {}).get("count", 0),
        "bigquery_dataset_count": local.get("bigquery_datasets", {}).get("count", 0),
        "ready_gcp_projects": ready_projects,
        "vertex_resource_totals": vertex_totals,
        "workspace_gmail_query_count": len(workspace.get("gmail_queries", [])),
        "workspace_drive_query_count": len(workspace.get("drive_queries", [])),
        "blocked_workspace_actions": workspace.get("blocked_actions", []),
        "cost_posture_included": bool(cost.get("included")),
    }


def _tool_summary(tools: dict[str, Any], name: str) -> dict[str, Any]:
    if not tools:
        return {"available": None, "version": "", "error": "not checked"}
    status = tools.get(name, {})
    return {
        "available": bool(status.get("available")),
        "version": status.get("version", ""),
        "error": status.get("error", ""),
    }


def _vertex_totals(gcp: dict[str, Any]) -> dict[str, int]:
    totals = {
        "custom_jobs": 0,
        "models": 0,
        "endpoints": 0,
        "indexes": 0,
        "index_endpoints": 0,
    }
    for project in gcp.get("projects", []):
        for region in project.get("vertex_regions", []):
            resources = region.get("resources", {})
            for key in totals:
                resource = resources.get(key, {})
                if resource.get("ok", False):
                    totals[key] += int(resource.get("count", 0))
    return totals


def _readiness_gates(report: dict[str, Any]) -> list[ReadinessStatus]:
    summary = report["summary"]
    ready_projects = summary["ready_gcp_projects"]
    vertex_totals = summary["vertex_resource_totals"]
    gemini_cli = summary["gemini_cli"]
    vertex_busy = vertex_totals["custom_jobs"] > 0 or vertex_totals["endpoints"] > 0
    launchagent_gate = _launchagent_retargeting_gate()

    gates: list[ReadinessStatus] = [
        {
            "id": "local_google_tooling",
            "status": _status_from_tool(gemini_cli),
            "evidence": _tool_evidence(gemini_cli),
            "next_gate": "Authenticate Gemini CLI manually only if the browser flow appears and no secrets are pasted into prompts.",
        },
        {
            "id": "gcp_data_plane",
            "status": "pass" if ready_projects else "needs_attention",
            "evidence": f"ready projects: {', '.join(ready_projects) or 'none'}",
            "next_gate": "Keep writes blocked until target paths, labels, lifecycle, and budget are reviewed.",
        },
        {
            "id": "vertex_idle_or_batch_ready",
            "status": "needs_attention" if vertex_busy else "pass",
            "evidence": _format_vertex_totals(vertex_totals),
            "next_gate": "Use local dry-run artifacts before any batch prediction, tuning, training, or endpoint deployment.",
        },
        {
            "id": "workspace_threat_hygiene",
            "status": "pass",
            "evidence": f"{summary['workspace_gmail_query_count']} Gmail query templates and {summary['workspace_drive_query_count']} Drive lanes are staged.",
            "next_gate": "Metadata-only scans may come next; label, trash, or delete actions need an explicit live-action command.",
        },
        {
            "id": "gemini_api_or_vertex_live_calls",
            "status": "manual_gate",
            "evidence": "No API key presence, token budget, model call, or Vertex job was invoked by this harness.",
            "next_gate": "Define exact key/project, model, token cap, cost cap, sample cap, output path, and rollback.",
        },
        {
            "id": "launchagent_retargeting",
            "status": launchagent_gate["status"],
            "evidence": launchagent_gate["evidence"],
            "next_gate": launchagent_gate["next_gate"],
        },
    ]
    if summary["cost_posture_included"]:
        gates.append(
            {
                "id": "cost_posture_probe",
                "status": "pass",
                "evidence": "Read-only cost posture was included; inspect Cloud Run risks before live jobs.",
                "next_gate": "Resolve nonzero min instance or high max-scale risks before adding always-on AI services.",
            }
        )
    return gates


def _launchagent_retargeting_gate(
    *,
    secrets_env: Path | None = None,
    live_dir: Path | None = None,
    tracked_plists: list[Path] | None = None,
) -> ReadinessStatus:
    secrets_env = secrets_env or Path.home() / ".sapphire" / "secrets.env"
    secret_keys = _secret_env_keys(secrets_env)
    required_secret_refs = {"AUTH_PASSWORD", "RELAY_READER_TOKEN", "KIMI_RELAY_CHAT_ID"}
    missing_secret_refs = sorted(required_secret_refs - secret_keys)

    secret_env_keys = {
        "com.sapphire.dashboard.plist": {"AUTH_PASSWORD"},
        "com.sapphire.inference-proxy.plist": {
            "KIMI_RELAY_CHAT_ID",
            "OPENROUTER_API_KEY",
            "RELAY_READER_TOKEN",
        },
    }
    live_dir = live_dir or Path.home() / "Library" / "LaunchAgents"
    live_secret_keys: dict[str, list[str]] = {}
    for plist_name, blocked_keys in secret_env_keys.items():
        env = _plist_environment(live_dir / plist_name)
        present = sorted(blocked_keys & set(env))
        if present:
            live_secret_keys[plist_name] = present

    if tracked_plists is None:
        tracked_plists = [
            Path("services/dashboard/launchagent/com.sapphire.dashboard.plist"),
            Path("services/inference-proxy/launchagent/com.sapphire.inference-proxy.plist"),
        ]
    missing_tracked = []
    for path in tracked_plists:
        check_path = path if path.is_absolute() else REPO_ROOT / path
        if not check_path.exists():
            missing_tracked.append(str(path))

    if not missing_secret_refs and not live_secret_keys and not missing_tracked:
        return {
            "status": "pass",
            "evidence": "Live dashboard/inference-proxy plists are sanitized; required secret references are present in ~/.sapphire/secrets.env.",
            "next_gate": "BotFather RELAY_READER_TOKEN rotation is still recommended if the previous relay token is considered burnt.",
        }

    blockers = []
    if missing_secret_refs:
        blockers.append(f"missing secrets-env refs: {', '.join(missing_secret_refs)}")
    if live_secret_keys:
        labels = ", ".join(
            f"{name} has {', '.join(keys)}" for name, keys in live_secret_keys.items()
        )
        blockers.append(f"live plist secret env remains: {labels}")
    if missing_tracked:
        blockers.append(f"missing tracked sanitized plists: {', '.join(missing_tracked)}")
    return {
        "status": "needs_attention",
        "evidence": "; ".join(blockers),
        "next_gate": "Move AUTH_PASSWORD, RELAY_READER_TOKEN, and KIMI_RELAY_CHAT_ID refs to ~/.sapphire/secrets.env, deploy sanitized service-owned plists, bounce dashboard/inference-proxy, then re-run readiness.",
    }


def _secret_env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return keys
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if value.strip():
            keys.add(key.strip())
    return keys


def _plist_environment(path: Path) -> dict[str, str]:
    try:
        data = plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException):
        return {}
    env = data.get("EnvironmentVariables") or {}
    return env if isinstance(env, dict) else {}


def _status_from_tool(tool: dict[str, Any]) -> str:
    if tool.get("available") is True:
        return "pass"
    if tool.get("available") is None:
        return "unknown"
    return "needs_attention"


def _tool_evidence(tool: dict[str, Any]) -> str:
    if tool.get("available") is True:
        return f"Gemini CLI available: {tool.get('version') or 'version unknown'}"
    return tool.get("error") or "Gemini CLI was not checked."


def _format_vertex_totals(totals: dict[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in sorted(totals.items()))


def _production_test_lanes(report: dict[str, Any]) -> list[dict[str, str]]:
    summary = report["summary"]
    gemini_status = _status_from_tool(summary["gemini_cli"])
    gcp_ready = bool(summary["ready_gcp_projects"])
    return [
        {
            "lane": "Benefits and local tool inventory",
            "status": "ready",
            "command": "python3 scripts/ops/google_benefits_inventory.py --membership google_developer_premium --membership google_ai_plus",
            "artifact": "Markdown/JSON report; no account mutation.",
            "live_gate": "None; read-only local CLI metadata only.",
        },
        {
            "lane": "Gemini CLI operator assist",
            "status": gemini_status,
            "command": "gemini --version",
            "artifact": "Installed CLI and future manual-auth operator reviews.",
            "live_gate": "No model calls until prompt, data-sensitivity, and budget caps are set.",
        },
        {
            "lane": "GCP / Vertex AI inventory",
            "status": "ready" if gcp_ready else "needs_attention",
            "command": "python3 scripts/ops/gcp_ai_inventory.py --project sapphire-479610 --region us-central1",
            "artifact": "Read-only project/API/dataset/Vertex resource report.",
            "live_gate": "No Vertex job, tuning, endpoint, or data write until a reviewed runbook exists.",
        },
        {
            "lane": "Gmail / Drive threat hygiene",
            "status": "ready",
            "command": "python3 scripts/ops/google_workspace_threat_hygiene.py --days 30",
            "artifact": "Local query/action proposal; no Google Workspace API calls.",
            "live_gate": "Metadata scan, labels, archive, trash, or delete each need separate approval.",
        },
        {
            "lane": "Regional and mission OODA batch",
            "status": "ready" if gcp_ready else "needs_attention",
            "command": "Prepare local prompt/input/output artifacts under data/google/production-readiness/.",
            "artifact": "Local OODA packet candidates before Gemini or Vertex batch submission.",
            "live_gate": "Token, spend, sample, retention, and rollback caps before any API call.",
        },
        {
            "lane": "BigQuery/GCS summary promotion",
            "status": "manual_gate",
            "command": "Review schemas, lifecycle labels, and free-tier budget before writes.",
            "artifact": "Schema and mapping docs first; write jobs later.",
            "live_gate": "Explicit write approval with target dataset/bucket and rollback.",
        },
        {
            "lane": "Vertex evals before training",
            "status": "manual_gate",
            "command": "Build golden cases and local scorecards before any tuning/custom job.",
            "artifact": "Eval scorecards that prove a model gap worth spending on.",
            "live_gate": "No custom training until baseline evals prove need and budget is capped.",
        },
        {
            "lane": "Veo/media generation",
            "status": "manual_gate",
            "command": "Keep media factory work orders dry-run until exact live behavior is approved.",
            "artifact": "Auditable image/audio/video work orders.",
            "live_gate": "No Veo, publishing, Telegram sends, or account automation by this harness.",
        },
    ]


def _next_safe_commands(
    *,
    projects: list[str],
    regions: list[str],
    memberships: list[str],
    workspace_days: int,
) -> list[str]:
    membership_args = " ".join(f"--membership {membership}" for membership in memberships)
    project_args = " ".join(f"--project {project}" for project in projects)
    region_args = " ".join(f"--region {region}" for region in regions)
    return [
        f"python3 scripts/ops/google_production_test_readiness.py {project_args} {region_args} {membership_args} --format markdown",
        f"python3 scripts/ops/google_workspace_threat_hygiene.py --days {workspace_days}",
        f"python3 scripts/ops/gcp_ai_inventory.py {project_args} {region_args}",
        "python3 scripts/ops/cost_posture_report.py --project sapphire-479610 --region us-central1 --hours 24 --log-limit 25",
    ]


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Google Production-Testing Readiness",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Mode: `{report['mode']}`",
        f"- Projects: `{', '.join(report['projects'])}`",
        f"- Regions: `{', '.join(report['regions'])}`",
        f"- Membership assumptions: `{', '.join(report['memberships'])}`",
        "- Scope: read-only production-testing posture and local dry-run staging.",
        "",
        "## Guardrails",
        "",
    ]
    for guardrail in report["guardrails"]:
        lines.append(f"- {guardrail}")

    lines.extend(
        [
            "",
            "## Current Signals",
            "",
            f"- Gemini CLI: `{_availability(summary['gemini_cli'])}`",
            f"- gcloud: `{_availability(summary['gcloud'])}`",
            f"- bq: `{_availability(summary['bigquery_cli'])}`",
            f"- GCS buckets observed: `{summary['gcs_bucket_count']}`",
            f"- BigQuery datasets observed: `{summary['bigquery_dataset_count']}`",
            f"- GCP projects ready for dry-run AI complement: `{', '.join(summary['ready_gcp_projects']) or 'none'}`",
            f"- Vertex resource totals: `{_format_vertex_totals(summary['vertex_resource_totals'])}`",
            f"- Workspace hygiene templates: `{summary['workspace_gmail_query_count']} Gmail`, `{summary['workspace_drive_query_count']} Drive`",
            "",
            "## Readiness Gates",
            "",
            "| Gate | Status | Evidence | Next Gate |",
            "|---|---|---|---|",
        ]
    )
    for gate in report["readiness_gates"]:
        lines.append(
            "| {id} | {status} | {evidence} | {next_gate} |".format(
                id=gate["id"],
                status=gate["status"],
                evidence=_md_cell(gate["evidence"]),
                next_gate=_md_cell(gate["next_gate"]),
            )
        )

    lines.extend(
        [
            "",
            "## Production-Test Lanes",
            "",
            "| Lane | Status | Command | Artifact | Live Gate |",
            "|---|---|---|---|---|",
        ]
    )
    for lane in report["production_test_lanes"]:
        lines.append(
            "| {lane} | {status} | `{command}` | {artifact} | {live_gate} |".format(
                lane=lane["lane"],
                status=lane["status"],
                command=lane["command"],
                artifact=_md_cell(lane["artifact"]),
                live_gate=_md_cell(lane["live_gate"]),
            )
        )

    lines.extend(["", "## Next Safe Commands", ""])
    for command in report["next_safe_commands"]:
        lines.append(f"- `{command}`")

    cost = report["inputs"]["cost_posture"]
    lines.extend(["", "## Cost Posture", ""])
    if cost.get("included"):
        cost_report = cost["report"]
        lines.append("- Included: `yes`")
        lines.append(f"- Warning lookback: `{cost_report.get('warning_lookback', 'unknown')}`")
        lines.append("")
        lines.append("| Project | Cloud Run Services | Cost Risks |")
        lines.append("|---|---:|---:|")
        for project in cost_report.get("projects", []):
            cloud_run = project.get("cloud_run", {})
            lines.append(
                "| {project} | {services} | {risks} |".format(
                    project=project["project"],
                    services=cloud_run.get("service_count", 0),
                    risks=cloud_run.get("risk_count", 0),
                )
            )
    else:
        lines.append(f"- Included: `no` ({cost.get('reason', 'not requested')})")

    lines.extend(["", "## Workspace Blocked Actions", ""])
    for action in summary["blocked_workspace_actions"]:
        lines.append(f"- `{action}`")

    return "\n".join(lines) + "\n"


def _availability(tool: dict[str, Any]) -> str:
    if tool.get("available") is True:
        return tool.get("version") or "available"
    if tool.get("available") is None:
        return "not checked"
    return tool.get("error") or "unavailable"


def _md_cell(value: object) -> str:
    return str(value or "-").replace("|", "\\|").replace("\n", " ")


def write_output(report: dict[str, Any], *, output: Path, output_format: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output_format == "json":
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    else:
        output.write_text(render_markdown(report))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        dest="projects",
        action="append",
        help="GCP project to inspect. Repeatable. Defaults to sapphire-479610.",
    )
    parser.add_argument(
        "--region",
        dest="regions",
        action="append",
        help="Vertex AI region to inspect. Repeatable. Defaults to us-central1.",
    )
    parser.add_argument(
        "--membership",
        action="append",
        choices=sorted(google_benefits_inventory.MEMBERSHIPS),
        help="Assert a Google membership tier Ari has. Repeatable.",
    )
    parser.add_argument(
        "--workspace-days",
        type=int,
        default=google_workspace_threat_hygiene.DEFAULT_LOOKBACK_DAYS,
    )
    parser.add_argument("--include-cost", action="store_true")
    parser.add_argument("--cost-hours", type=int, default=24)
    parser.add_argument("--cost-log-limit", type=int, default=25)
    parser.add_argument("--no-external", action="store_true", help="Do not call local CLIs.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional output file. Use data/google/production-readiness/ for local ignored artifacts.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.workspace_days < 1:
        raise SystemExit("--workspace-days must be >= 1")
    if args.cost_hours < 1:
        raise SystemExit("--cost-hours must be >= 1")
    if args.cost_log_limit < 0:
        raise SystemExit("--cost-log-limit must be >= 0")

    report = collect_readiness(
        projects=args.projects or list(DEFAULT_PROJECTS),
        regions=args.regions or list(DEFAULT_REGIONS),
        memberships=args.membership or list(DEFAULT_MEMBERSHIPS),
        workspace_days=args.workspace_days,
        external=not args.no_external,
        include_cost=args.include_cost,
        cost_hours=args.cost_hours,
        cost_log_limit=args.cost_log_limit,
    )

    if args.output:
        write_output(report, output=args.output, output_format=args.format)
    elif args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
