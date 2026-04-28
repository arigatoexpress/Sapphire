#!/usr/bin/env python3
"""Read-only GCP and Vertex AI complement inventory for Sapphire OS.

The command intentionally avoids secret reads, workflow dispatches, model
training, endpoint deployment, and data writes. It only lists non-secret
resource metadata that helps decide which low-cost AI augmentation lane is
safe to test next.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

DEFAULT_PROJECTS = ("tho-ai-agent",)
DEFAULT_REGIONS = ("us-central1",)

TRACKED_SERVICES = (
    "aiplatform.googleapis.com",
    "bigquery.googleapis.com",
    "bigquerystorage.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudfunctions.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
)

VERTEX_RESOURCE_COMMANDS = {
    "custom_jobs": ("ai", "custom-jobs", "list"),
    "models": ("ai", "models", "list"),
    "endpoints": ("ai", "endpoints", "list"),
    "indexes": ("ai", "indexes", "list"),
    "index_endpoints": ("ai", "index-endpoints", "list"),
}


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    data: Any
    error: str = ""


Runner = Callable[[list[str]], CommandResult]


def _truncate_error(value: str, limit: int = 320) -> str:
    compact = " ".join(str(value or "").split())
    return compact[:limit]


def _run_json(args: list[str]) -> CommandResult:
    executable = args[0]
    if shutil.which(executable) is None:
        return CommandResult(False, None, f"{executable} not found on PATH")

    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(False, None, f"{' '.join(args[:3])} timed out")

    if completed.returncode != 0:
        return CommandResult(False, None, _truncate_error(completed.stderr))

    output = completed.stdout.strip()
    if not output:
        return CommandResult(True, [])

    try:
        return CommandResult(True, json.loads(output))
    except json.JSONDecodeError as exc:
        return CommandResult(False, None, f"invalid JSON from {executable}: {exc}")


def _enabled_services(project: str, runner: Runner) -> CommandResult:
    service_filter = " OR ".join(f"config.name:{service}" for service in TRACKED_SERVICES)
    result = runner(
        [
            "gcloud",
            "services",
            "list",
            "--enabled",
            f"--project={project}",
            f"--filter=({service_filter})",
            "--format=json",
        ]
    )
    if not result.ok:
        return result

    services = sorted(
        item.get("config", {}).get("name", "")
        for item in (result.data or [])
        if item.get("config", {}).get("name")
    )
    return CommandResult(True, services)


def _bq_datasets(project: str, runner: Runner) -> CommandResult:
    result = runner(["bq", "ls", "--format=json", f"--project_id={project}"])
    if not result.ok:
        return result

    datasets = sorted(
        item.get("datasetReference", {}).get("datasetId", "")
        for item in (result.data or [])
        if item.get("datasetReference", {}).get("datasetId")
    )
    return CommandResult(True, datasets)


def _bq_tables(project: str, dataset: str, runner: Runner) -> CommandResult:
    result = runner(["bq", "ls", "--format=json", f"--project_id={project}", dataset])
    if not result.ok:
        return result

    tables = sorted(
        item.get("tableReference", {}).get("tableId", "")
        for item in (result.data or [])
        if item.get("tableReference", {}).get("tableId")
    )
    return CommandResult(True, tables)


def _vertex_resources(project: str, region: str, runner: Runner) -> dict[str, Any]:
    resources: dict[str, Any] = {}
    for label, command in VERTEX_RESOURCE_COMMANDS.items():
        result = runner(
            [
                "gcloud",
                *command,
                f"--project={project}",
                f"--region={region}",
                "--format=json",
            ]
        )
        if result.ok:
            items = result.data or []
            resources[label] = {
                "ok": True,
                "count": len(items),
                "display_names": sorted(
                    str(item.get("displayName") or item.get("name") or "")
                    for item in items[:20]
                    if item.get("displayName") or item.get("name")
                ),
            }
        else:
            resources[label] = {"ok": False, "count": 0, "error": result.error}
    return resources


def _status_for_project(project_info: dict[str, Any]) -> str:
    services = set(project_info.get("enabled_services", []))
    datasets = set(project_info.get("bigquery_datasets", []))

    if "aiplatform.googleapis.com" not in services:
        return "needs Vertex API enablement"
    if "bigquery.googleapis.com" not in services:
        return "needs BigQuery API enablement"
    if "sapphire" not in datasets:
        return "needs sapphire dataset"
    return "ready for dry-run AI complement"


def _recommendations(projects: list[dict[str, Any]]) -> list[dict[str, str]]:
    has_ready_data_plane = any(
        project.get("status") == "ready for dry-run AI complement" for project in projects
    )
    has_vertex_endpoint = any(
        region.get("resources", {}).get("endpoints", {}).get("count", 0) > 0
        for project in projects
        for region in project.get("vertex_regions", [])
    )
    has_vertex_training = any(
        region.get("resources", {}).get("custom_jobs", {}).get("count", 0) > 0
        for project in projects
        for region in project.get("vertex_regions", [])
    )

    recommendations: list[dict[str, str]] = [
        {
            "lane": "Batch Gemini OODA packets",
            "first_test": "Generate regional and mission-digest summaries from BigQuery/GCS prompts in dry-run mode.",
            "cost_posture": "Prefer batch prediction for non-urgent work; no always-on endpoint required.",
            "gate": "Proceed when prompt samples, expected token budget, and artifact output paths are reviewed.",
        },
        {
            "lane": "BigQuery retrieval layer",
            "first_test": "Add embeddings/vector-search tables for docs, OODA packets, incidents, and regional intel.",
            "cost_posture": "Keep retrieval in BigQuery before adding a dedicated Vertex Vector Search endpoint.",
            "gate": "Proceed after table schema and row-level provenance contract are reviewed.",
        },
        {
            "lane": "Vertex eval harness",
            "first_test": "Score Sapphire prompts, Telegram command replies, and media work orders against golden cases.",
            "cost_posture": "Run as scheduled or manual batches with strict sample caps.",
            "gate": "Proceed before any model tuning or custom training.",
        },
        {
            "lane": "Custom training or tuning",
            "first_test": "Only train after the eval harness proves a repeated, measurable gap.",
            "cost_posture": "Use smallest dataset, shortest job, and no deployed endpoint by default.",
            "gate": "Blocked until baseline evals, spend cap, rollback, and artifact retention are documented.",
        },
    ]

    if not has_ready_data_plane:
        recommendations.insert(
            0,
            {
                "lane": "Data-plane readiness",
                "first_test": "Fix project/API/dataset gaps before submitting Vertex jobs.",
                "cost_posture": "Metadata checks only.",
                "gate": "Required.",
            },
        )
    if has_vertex_endpoint:
        recommendations.append(
            {
                "lane": "Endpoint cost review",
                "first_test": "Confirm endpoint min replicas and traffic before adding more online inference.",
                "cost_posture": "Deployed endpoints can incur cost even without requests.",
                "gate": "Required before new endpoints.",
            }
        )
    if has_vertex_training:
        recommendations.append(
            {
                "lane": "Training inventory review",
                "first_test": "Review recent custom jobs and outputs before launching another training run.",
                "cost_posture": "Avoid duplicate experiments.",
                "gate": "Required before new training.",
            }
        )

    return recommendations


def collect_inventory(
    projects: list[str],
    regions: list[str],
    *,
    runner: Runner = _run_json,
    external: bool = True,
) -> dict[str, Any]:
    generated_at = datetime.now(UTC).isoformat(timespec="seconds")
    inventory: dict[str, Any] = {
        "generated_at": generated_at,
        "mode": "read-only" if external else "no-external",
        "projects": [],
        "recommendations": [],
        "guardrails": [
            "No secret values are read or printed.",
            "No GCP, Foundry, Telegram, trading, workflow, or LaunchAgent mutation is performed.",
            "No Vertex training, batch prediction, endpoint deployment, or model tuning is started.",
        ],
    }

    if not external:
        inventory["recommendations"] = _recommendations([])
        return inventory

    for project in projects:
        services = _enabled_services(project, runner)
        datasets = _bq_datasets(project, runner)
        project_info: dict[str, Any] = {
            "project": project,
            "enabled_services": services.data if services.ok else [],
            "enabled_services_error": "" if services.ok else services.error,
            "bigquery_datasets": datasets.data if datasets.ok else [],
            "bigquery_datasets_error": "" if datasets.ok else datasets.error,
            "bigquery_tables": {},
            "vertex_regions": [],
        }

        for dataset in project_info["bigquery_datasets"]:
            if dataset != "sapphire":
                continue
            tables = _bq_tables(project, dataset, runner)
            project_info["bigquery_tables"][dataset] = tables.data if tables.ok else []
            if not tables.ok:
                project_info["bigquery_tables_error"] = tables.error

        for region in regions:
            project_info["vertex_regions"].append(
                {
                    "region": region,
                    "resources": _vertex_resources(project, region, runner),
                }
            )

        project_info["status"] = _status_for_project(project_info)
        inventory["projects"].append(project_info)

    inventory["recommendations"] = _recommendations(inventory["projects"])
    return inventory


def _join(values: list[str], *, empty: str = "-") -> str:
    return ", ".join(values) if values else empty


def _resource_count(region: dict[str, Any], key: str) -> str:
    resource = region.get("resources", {}).get(key, {})
    if not resource.get("ok", False):
        return "?"
    return str(resource.get("count", 0))


def render_markdown(inventory: dict[str, Any]) -> str:
    lines = [
        "# GCP / Vertex AI Complement Inventory",
        "",
        f"- Generated: `{inventory['generated_at']}`",
        f"- Mode: `{inventory['mode']}`",
        "- Scope: read-only metadata; no secrets, writes, training jobs, endpoints, workflow dispatches, Telegram sends, or trading actions.",
        "",
        "## Guardrails",
        "",
    ]

    for guardrail in inventory.get("guardrails", []):
        lines.append(f"- {guardrail}")

    lines.extend(
        [
            "",
            "## Projects",
            "",
            "| Project | Status | Enabled AI/Data APIs | BigQuery Datasets | Sapphire Tables |",
            "|---|---|---|---|---|",
        ]
    )

    for project in inventory.get("projects", []):
        tracked = [
            service for service in project["enabled_services"] if service in TRACKED_SERVICES
        ]
        sapphire_tables = project.get("bigquery_tables", {}).get("sapphire", [])
        lines.append(
            "| {project} | {status} | {services} | {datasets} | {tables} |".format(
                project=project["project"],
                status=project.get("status", "unknown"),
                services=_join(tracked),
                datasets=_join(project.get("bigquery_datasets", [])),
                tables=_join(sapphire_tables),
            )
        )

    lines.extend(
        [
            "",
            "## Vertex AI Metadata",
            "",
            "| Project | Region | Custom Jobs | Models | Endpoints | Indexes | Index Endpoints |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )

    for project in inventory.get("projects", []):
        for region in project.get("vertex_regions", []):
            lines.append(
                "| {project} | {region} | {custom_jobs} | {models} | {endpoints} | {indexes} | {index_endpoints} |".format(
                    project=project["project"],
                    region=region["region"],
                    custom_jobs=_resource_count(region, "custom_jobs"),
                    models=_resource_count(region, "models"),
                    endpoints=_resource_count(region, "endpoints"),
                    indexes=_resource_count(region, "indexes"),
                    index_endpoints=_resource_count(region, "index_endpoints"),
                )
            )

    lines.extend(
        [
            "",
            "## Recommended Test Lanes",
            "",
            "| Lane | First Test | Cost Posture | Gate |",
            "|---|---|---|---|",
        ]
    )

    for recommendation in inventory.get("recommendations", []):
        lines.append(
            "| {lane} | {first_test} | {cost_posture} | {gate} |".format(
                lane=recommendation["lane"],
                first_test=recommendation["first_test"],
                cost_posture=recommendation["cost_posture"],
                gate=recommendation["gate"],
            )
        )

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only GCP/Vertex AI complement inventory for Sapphire OS."
    )
    parser.add_argument(
        "--project",
        dest="projects",
        action="append",
        help="GCP project to inspect. Repeatable. Defaults to tho-ai-agent.",
    )
    parser.add_argument(
        "--region",
        dest="regions",
        action="append",
        help="Vertex AI region to inspect. Repeatable. Defaults to us-central1.",
    )
    parser.add_argument(
        "--no-external",
        action="store_true",
        help="Do not call gcloud or bq; render guardrails and lane order only.",
    )
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = collect_inventory(
        args.projects or list(DEFAULT_PROJECTS),
        args.regions or list(DEFAULT_REGIONS),
        external=not args.no_external,
    )

    if args.format == "json":
        print(json.dumps(inventory, indent=2, sort_keys=True))
    else:
        print(render_markdown(inventory), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
