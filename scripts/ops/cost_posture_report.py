#!/usr/bin/env python3
"""Read-only GCP cost posture report for Sapphire/THO runtime projects.

This intentionally does not call mutating billing, Cloud Run, logging, or IAM
commands. It summarizes only non-secret fields and avoids printing raw log
entries, service environment variables, billing account identifiers, or request
payloads.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

DEFAULT_PROJECTS = ("tho-ai-agent", "sapphire-479610")
DEFAULT_REGION = "us-central1"


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    data: Any
    error: str = ""


def _run_gcloud_json(args: list[str], *, timeout: int = 30) -> CommandResult:
    if shutil.which("gcloud") is None:
        return CommandResult(False, None, "gcloud not found on PATH")
    cmd = ["gcloud", *args, "--format=json"]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(False, None, f"gcloud command timed out after {timeout}s")
    if proc.returncode != 0:
        return CommandResult(False, None, _compact_error(proc.stderr or proc.stdout))
    try:
        return CommandResult(True, json.loads(proc.stdout or "null"))
    except json.JSONDecodeError as exc:
        return CommandResult(False, None, f"gcloud returned invalid JSON: {exc}")


def _compact_error(text: str, *, limit: int = 240) -> str:
    cleaned = " ".join(str(text or "").split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3] + "..."


def summarize_billing(project: str) -> dict[str, Any]:
    result = _run_gcloud_json(["beta", "billing", "projects", "describe", project])
    if not result.ok:
        return {
            "project": project,
            "available": False,
            "billing_enabled": None,
            "billing_account_linked": None,
            "error": result.error,
        }
    data = result.data or {}
    billing_account_name = str(data.get("billingAccountName") or "")
    return {
        "project": project,
        "available": True,
        "billing_enabled": bool(data.get("billingEnabled")),
        "billing_account_linked": bool(billing_account_name),
    }


def summarize_cloud_run(project: str, region: str) -> dict[str, Any]:
    result = _run_gcloud_json([
        "run",
        "services",
        "list",
        "--project",
        project,
        "--region",
        region,
        "--platform",
        "managed",
    ])
    if not result.ok:
        return {
            "project": project,
            "region": region,
            "available": False,
            "services": [],
            "error": result.error,
        }
    services = [summarize_service(project, region, svc) for svc in (result.data or [])]
    return {
        "project": project,
        "region": region,
        "available": True,
        "services": services,
        "service_count": len(services),
        "risk_count": sum(1 for svc in services if svc["cost_risks"]),
    }


def summarize_service(project: str, region: str, service: dict[str, Any]) -> dict[str, Any]:
    metadata = service.get("metadata") or {}
    annotations = metadata.get("annotations") or {}
    status = service.get("status") or {}
    template_obj = ((service.get("spec") or {}).get("template") or {})
    template_annotations = (template_obj.get("metadata") or {}).get("annotations") or {}
    template = template_obj.get("spec") or {}
    containers = template.get("containers") or []
    first_container = containers[0] if containers else {}
    resources = first_container.get("resources") or {}
    limits = resources.get("limits") or {}
    min_scale = _parse_int(
        template_annotations.get("autoscaling.knative.dev/minScale")
        or annotations.get("autoscaling.knative.dev/minScale")
        or annotations.get("run.googleapis.com/minScale")
    )
    max_scale = _parse_int(
        template_annotations.get("autoscaling.knative.dev/maxScale")
        or annotations.get("autoscaling.knative.dev/maxScale")
        or annotations.get("run.googleapis.com/maxScale")
    )
    risks = _service_cost_risks(min_scale=min_scale, max_scale=max_scale)
    return {
        "project": project,
        "region": region,
        "name": metadata.get("name", ""),
        "latest_ready_revision": status.get("latestReadyRevisionName", ""),
        "min_scale": min_scale,
        "max_scale": max_scale,
        "cpu_limit": str(limits.get("cpu", "")),
        "memory_limit": str(limits.get("memory", "")),
        "cost_risks": risks,
    }


def _parse_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except ValueError:
        return None


def _service_cost_risks(*, min_scale: int | None, max_scale: int | None) -> list[str]:
    risks: list[str] = []
    if min_scale and min_scale > 0:
        risks.append("min_instances_nonzero")
    if max_scale is None:
        risks.append("max_scale_unset")
    elif max_scale > 20:
        risks.append("max_scale_high")
    return risks


def summarize_logging_warnings(project: str, *, days: int, limit: int) -> dict[str, Any]:
    since = (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")
    query = (
        'resource.type="cloud_run_revision" '
        f'timestamp>="{since}" '
        'severity>=WARNING'
    )
    result = _run_gcloud_json([
        "logging",
        "read",
        query,
        "--project",
        project,
        "--limit",
        str(limit),
    ], timeout=45)
    if not result.ok:
        return {
            "project": project,
            "available": False,
            "days": days,
            "sample_limit": limit,
            "error": result.error,
        }
    by_service: Counter[str] = Counter()
    by_severity: Counter[str] = Counter()
    for entry in result.data or []:
        labels = ((entry.get("resource") or {}).get("labels") or {})
        service = str(labels.get("service_name") or "unknown")
        severity = str(entry.get("severity") or "DEFAULT")
        by_service[service] += 1
        by_severity[severity] += 1
    return {
        "project": project,
        "available": True,
        "days": days,
        "sample_limit": limit,
        "entries_sampled": sum(by_service.values()),
        "by_service": dict(sorted(by_service.items())),
        "by_severity": dict(sorted(by_severity.items())),
    }


def build_report(projects: list[str], *, region: str, days: int, log_limit: int) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "region": region,
        "projects": [
            {
                "project": project,
                "billing": summarize_billing(project),
                "cloud_run": summarize_cloud_run(project, region),
                "logging_warnings": summarize_logging_warnings(project, days=days, limit=log_limit),
            }
            for project in projects
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Sapphire Cost Posture Report",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Region: `{report['region']}`",
        "- Scope: read-only gcloud summary; no billing accounts, env vars, or raw logs printed.",
        "",
        "## Billing",
        "",
        "| Project | Billing API | Billing Enabled | Account Linked | Notes |",
        "|---|---:|---:|---:|---|",
    ]
    for project in report["projects"]:
        billing = project["billing"]
        lines.append(
            "| {project} | {available} | {enabled} | {linked} | {notes} |".format(
                project=billing["project"],
                available=_yn(billing["available"]),
                enabled=_maybe_yn(billing["billing_enabled"]),
                linked=_maybe_yn(billing["billing_account_linked"]),
                notes=_md_cell(billing.get("error", "")),
            )
        )

    lines.extend([
        "",
        "## Cloud Run",
        "",
        "| Project | Service | Min | Max | CPU | Memory | Latest Ready | Cost Risks |",
        "|---|---|---:|---:|---|---|---|---|",
    ])
    for project in report["projects"]:
        cloud_run = project["cloud_run"]
        if not cloud_run["available"]:
            lines.append(
                f"| {cloud_run['project']} | unavailable |  |  |  |  |  | {_md_cell(cloud_run.get('error', ''))} |"
            )
            continue
        if not cloud_run["services"]:
            lines.append(f"| {cloud_run['project']} | none |  |  |  |  |  |  |")
        for service in cloud_run["services"]:
            lines.append(
                "| {project} | {name} | {min_scale} | {max_scale} | {cpu} | {memory} | {revision} | {risks} |".format(
                    project=service["project"],
                    name=service["name"],
                    min_scale=_none_dash(service["min_scale"]),
                    max_scale=_none_dash(service["max_scale"]),
                    cpu=service["cpu_limit"] or "-",
                    memory=service["memory_limit"] or "-",
                    revision=service["latest_ready_revision"] or "-",
                    risks=", ".join(service["cost_risks"]) or "-",
                )
            )

    lines.extend([
        "",
        "## Warning Logs",
        "",
        "| Project | Available | Entries Sampled | By Service | By Severity | Notes |",
        "|---|---:|---:|---|---|---|",
    ])
    for project in report["projects"]:
        warnings = project["logging_warnings"]
        lines.append(
            "| {project} | {available} | {sampled} | {services} | {severities} | {notes} |".format(
                project=warnings["project"],
                available=_yn(warnings["available"]),
                sampled=warnings.get("entries_sampled", "-"),
                services=_md_cell(_compact_mapping(warnings.get("by_service", {}))),
                severities=_md_cell(_compact_mapping(warnings.get("by_severity", {}))),
                notes=_md_cell(warnings.get("error", "")),
            )
        )
    return "\n".join(lines) + "\n"


def _yn(value: bool) -> str:
    return "yes" if value else "no"


def _maybe_yn(value: bool | None) -> str:
    if value is None:
        return "unknown"
    return _yn(value)


def _none_dash(value: object) -> object:
    return "-" if value is None else value


def _md_cell(value: object) -> str:
    return str(value or "-").replace("|", "\\|")


def _compact_mapping(mapping: dict[str, Any]) -> str:
    if not mapping:
        return "-"
    return ", ".join(f"{key}:{value}" for key, value in sorted(mapping.items()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project",
        action="append",
        dest="projects",
        help="GCP project to include. Repeatable. Defaults to THO + Sapphire projects.",
    )
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--days", type=int, default=7, help="Warning log lookback window.")
    parser.add_argument("--log-limit", type=int, default=1000, help="Max warning log entries to sample.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    projects = args.projects or list(DEFAULT_PROJECTS)
    report = build_report(projects, region=args.region, days=args.days, log_limit=args.log_limit)
    if args.format == "json":
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(render_markdown(report), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
