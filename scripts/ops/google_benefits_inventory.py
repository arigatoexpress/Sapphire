#!/usr/bin/env python3
"""Google benefits control-tower inventory for Sapphire OS.

This command is deliberately conservative. It maps Google memberships and free
tiers to Sapphire operating lanes, and can optionally gather non-secret local
tool/GCP metadata. It does not read Gmail or Drive contents, redeem credits,
enable APIs, create resources, launch model jobs, or perform account changes.
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

DEFAULT_PROJECT = "tho-ai-agent"

MEMBERSHIPS = {
    "google_developer_standard": "Google Developer Program Standard",
    "google_developer_premium": "Google Developer Program Premium",
    "google_ai_plus": "Google AI Plus",
    "google_ai_pro": "Google AI Pro",
    "google_ai_ultra": "Google AI Ultra",
    "youtube_premium": "YouTube Premium",
}

SOURCE_URLS = {
    "developer_plans": "https://developers.google.com/program/plans-and-pricing",
    "developer_faq": "https://developers.google.com/profile/help/benefits",
    "google_ai_plans": "https://one.google.com/about/google-ai-plans/?hl=en",
    "gemini_api_pricing": "https://ai.google.dev/gemini-api/docs/pricing",
    "gemini_api_rate_limits": "https://ai.google.dev/gemini-api/docs/rate-limits",
    "gcp_free_tier": "https://docs.cloud.google.com/free/docs/free-cloud-features",
    "cloud_storage_pricing": "https://cloud.google.com/storage/pricing",
    "bigquery_pricing": "https://cloud.google.com/bigquery/pricing",
    "gmail_scopes": "https://developers.google.com/workspace/gmail/api/auth/scopes",
    "gmail_api": "https://developers.google.com/workspace/gmail/api/reference/rest",
    "gmail_push": "https://developers.google.com/gmail/api/guides/push",
    "drive_api": "https://developers.google.com/drive/api/reference/rest/v3",
    "safe_browsing": "https://developers.google.com/safe-browsing/v4",
    "vertex_pricing": "https://cloud.google.com/vertex-ai/generative-ai/pricing",
    "veo_api": "https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/veo-video-generation",
    "youtube_premium": "https://support.google.com/youtube/answer/6308116",
}


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    data: Any
    error: str = ""


Runner = Callable[[list[str]], CommandResult]


def _truncate(value: str, limit: int = 320) -> str:
    return " ".join(str(value or "").split())[:limit]


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
        return CommandResult(False, None, _truncate(completed.stderr))

    output = completed.stdout.strip()
    if not output:
        return CommandResult(True, [])

    try:
        return CommandResult(True, json.loads(output))
    except json.JSONDecodeError as exc:
        return CommandResult(False, None, f"invalid JSON from {executable}: {exc}")


def _run_text(args: list[str]) -> CommandResult:
    executable = args[0]
    if shutil.which(executable) is None:
        return CommandResult(False, "", f"{executable} not found on PATH")

    try:
        completed = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(False, "", f"{' '.join(args[:2])} timed out")

    if completed.returncode != 0:
        return CommandResult(False, "", _truncate(completed.stderr or completed.stdout))
    return CommandResult(True, _truncate(completed.stdout.strip(), 500))


def _catalog() -> list[dict[str, Any]]:
    return [
        {
            "lane": "Developer Program",
            "benefits": [
                "Gemini Code Assist and Gemini CLI access",
                "Firebase Studio workspaces",
                "premium plans can include recurring GenAI and Google Cloud credits",
                "premium plans can include certification and Google Skills benefits",
            ],
            "safe_use": "Use for operator-side coding, labs, architecture reviews, and bounded Sapphire experiments.",
            "gate": "Do not purchase, redeem credits, change billing, or create projects from automation.",
            "sources": ["developer_plans", "developer_faq"],
        },
        {
            "lane": "Google AI Memberships",
            "benefits": [
                "Gemini app higher access by tier",
                "Flow/Whisk AI credits by tier",
                "Google One storage by tier",
                "NotebookLM/Jules/AI Studio/Gemini Code Assist benefits by tier and region",
            ],
            "safe_use": "Use manually for research, prompt exploration, video concepting, and non-secret Sapphire artifacts.",
            "gate": "Do not automate consumer-account sessions or assume a personal subscription grants production API capacity.",
            "sources": ["google_ai_plans"],
        },
        {
            "lane": "Gemini Developer API",
            "benefits": [
                "free-tier and paid-tier Gemini API access through AI Studio",
                "low-volume text and multimodal prototypes",
                "rate-limit-aware API testing before Vertex promotion",
            ],
            "safe_use": "Prototype local dry-runs with explicit API key, token cap, and output artifacts.",
            "gate": "No paid calls without a budget cap and explicit key/project selection.",
            "sources": ["gemini_api_pricing", "gemini_api_rate_limits"],
        },
        {
            "lane": "Vertex AI / Veo",
            "benefits": [
                "production-oriented Gemini, Imagen, Veo, embeddings, batch prediction, and tuning",
                "batch inference discounts for non-urgent work",
                "eligible Google Cloud credits can offset bounded experiments",
            ],
            "safe_use": "Run batch OODA, evals, embeddings, and media readiness only after local dry-run artifacts.",
            "gate": "No Vertex job, Veo generation, tuning, endpoint, or API enablement without reviewed budget and rollback.",
            "sources": ["vertex_pricing", "veo_api"],
        },
        {
            "lane": "Google Cloud Free Tier",
            "benefits": [
                "Cloud Storage Always Free usage in eligible US regions",
                "BigQuery free monthly storage and analysis quota",
                "Cloud Run, Pub/Sub, Secret Manager, Firestore, and other limited monthly free usage",
            ],
            "safe_use": "Keep Sapphire metadata, eval summaries, and telemetry within free-tier-aware caps.",
            "gate": "No bucket/project/data writes until lifecycle, labels, retention, and cost caps are documented.",
            "sources": ["gcp_free_tier", "cloud_storage_pricing", "bigquery_pricing"],
        },
        {
            "lane": "Gmail / Drive Threat Hygiene",
            "benefits": [
                "Gmail labels, metadata, read-only, modify, trash, and push-notification APIs",
                "Drive file metadata, labels, permissions, revisions, and trash APIs",
                "Safe Browsing URL checks for non-commercial threat triage",
            ],
            "safe_use": "Start with metadata-only scans, labels/quarantine, allowlists, and human approval before trash.",
            "gate": "No email/body/attachment reads, Drive downloads, label mutation, trash, or delete by default.",
            "sources": ["gmail_scopes", "gmail_api", "gmail_push", "drive_api", "safe_browsing"],
        },
        {
            "lane": "YouTube Premium / YouTube",
            "benefits": [
                "ad-free viewing, offline downloads, background play, and YouTube Music Premium",
                "useful for manual research flow, not a production API entitlement",
            ],
            "safe_use": "Use manually for research; build repo-native transcript/intel adapters only through normal APIs.",
            "gate": "Do not automate YouTube account activity or bypass YouTube terms.",
            "sources": ["youtube_premium"],
        },
    ]


def _membership_notes(memberships: list[str]) -> list[str]:
    selected = set(memberships)
    notes: list[str] = []
    if not selected:
        return [
            "No membership flags were asserted; treating benefits as unverified until Ari confirms exact plan names in Google dashboards."
        ]
    if "google_developer_premium" in selected:
        notes.append("Prioritize redeemable Cloud/GenAI credits for bounded Vertex/Gemini experiments.")
    elif "google_developer_standard" in selected:
        notes.append("Use free developer tooling and Skills credits; do not assume paid Cloud credits.")
    if "google_ai_plus" in selected:
        notes.append("Use AI Plus consumer benefits for manual research and non-secret storage; verify API entitlements separately.")
    if "google_ai_pro" in selected or "google_ai_ultra" in selected:
        notes.append("Use AI plan storage and AI credits for human-driven media/research; production API use still needs budget gates.")
    if "google_ai_ultra" in selected:
        notes.append("YouTube Premium may be included by plan/region, but Sapphire should treat it as manual research convenience only.")
    if "youtube_premium" in selected:
        notes.append("YouTube Premium is useful for manual research ergonomics, not autonomous production capability.")
    return notes


def _account_summary(runner: Runner) -> dict[str, Any]:
    result = runner(["gcloud", "config", "list", "--format=json"])
    if not result.ok:
        return {"available": False, "error": result.error}

    core = (result.data or {}).get("core", {})
    return {
        "available": True,
        "account": core.get("account", ""),
        "project": core.get("project", ""),
    }


def _buckets(project: str, runner: Runner) -> dict[str, Any]:
    result = runner(["gcloud", "storage", "buckets", "list", f"--project={project}", "--format=json"])
    if not result.ok:
        return {"available": False, "error": result.error, "count": 0, "names": []}

    names = sorted(
        item.get("name", "").replace("gs://", "")
        for item in (result.data or [])
        if item.get("name")
    )
    return {"available": True, "count": len(names), "names": names[:25]}


def _bq_datasets(project: str, runner: Runner) -> dict[str, Any]:
    result = runner(["bq", "ls", "--format=json", f"--project_id={project}"])
    if not result.ok:
        return {"available": False, "error": result.error, "count": 0, "datasets": []}

    datasets = sorted(
        item.get("datasetReference", {}).get("datasetId", "")
        for item in (result.data or [])
        if item.get("datasetReference", {}).get("datasetId")
    )
    return {"available": True, "count": len(datasets), "datasets": datasets[:25]}


def _tool_status(runner: Callable[[list[str]], CommandResult] = _run_text) -> dict[str, Any]:
    tools = {
        "gcloud": ["gcloud", "--version"],
        "bq": ["bq", "version"],
        "gemini": ["gemini", "--version"],
        "node": ["node", "--version"],
        "uv": ["uv", "--version"],
    }
    status: dict[str, Any] = {}
    for name, command in tools.items():
        result = runner(command)
        status[name] = {
            "available": result.ok,
            "version": result.data if result.ok else "",
            "error": "" if result.ok else result.error,
        }
    return status


def collect_inventory(
    *,
    project: str = DEFAULT_PROJECT,
    memberships: list[str] | None = None,
    external: bool = True,
    runner: Runner = _run_json,
    text_runner: Callable[[list[str]], CommandResult] = _run_text,
) -> dict[str, Any]:
    selected_memberships = memberships or []
    inventory: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "read-only" if external else "no-external",
        "project": project,
        "memberships": [
            {"id": membership, "label": MEMBERSHIPS[membership]}
            for membership in selected_memberships
            if membership in MEMBERSHIPS
        ],
        "membership_notes": _membership_notes(selected_memberships),
        "catalog": _catalog(),
        "guardrails": [
            "No Gmail or Drive content is read.",
            "No labels, files, messages, buckets, APIs, billing, credits, subscriptions, workflows, or resources are modified.",
            "No Gemini, Veo, Vertex, Gmail, Drive, or YouTube live action is invoked.",
            "Threat cleanup defaults to label/quarantine proposals and human approval before trash or delete.",
        ],
        "local": {},
    }

    if not external:
        return inventory

    account = _account_summary(runner)
    effective_project = account.get("project") or project
    inventory["local"] = {
        "account": account,
        "tools": _tool_status(text_runner),
        "gcs_buckets": _buckets(effective_project, runner),
        "bigquery_datasets": _bq_datasets(effective_project, runner),
    }
    return inventory


def _join(values: list[str], *, empty: str = "-") -> str:
    return ", ".join(values) if values else empty


def render_markdown(inventory: dict[str, Any]) -> str:
    lines = [
        "# Google Benefits Control-Tower Inventory",
        "",
        f"- Generated: `{inventory['generated_at']}`",
        f"- Mode: `{inventory['mode']}`",
        f"- Project hint: `{inventory['project']}`",
        "- Scope: benefits mapping plus non-secret local metadata only.",
        "",
        "## Membership Assumptions",
        "",
    ]

    memberships = inventory.get("memberships", [])
    if memberships:
        for membership in memberships:
            lines.append(f"- `{membership['id']}`: {membership['label']}")
    else:
        lines.append("- No membership flags asserted.")

    for note in inventory.get("membership_notes", []):
        lines.append(f"- {note}")

    lines.extend(["", "## Guardrails", ""])
    for guardrail in inventory.get("guardrails", []):
        lines.append(f"- {guardrail}")

    local = inventory.get("local", {})
    if local:
        account = local.get("account", {})
        lines.extend(
            [
                "",
                "## Local Metadata",
                "",
                f"- gcloud available: `{'yes' if account.get('available') else 'no'}`",
                f"- gcloud account: `{account.get('account') or '-'}`",
                f"- gcloud project: `{account.get('project') or '-'}`",
                f"- GCS buckets: `{local.get('gcs_buckets', {}).get('count', 0)}` ({_join(local.get('gcs_buckets', {}).get('names', []))})",
                f"- BigQuery datasets: `{local.get('bigquery_datasets', {}).get('count', 0)}` ({_join(local.get('bigquery_datasets', {}).get('datasets', []))})",
                "",
                "| Tool | Available | Version / Error |",
                "|---|:---:|---|",
            ]
        )
        for name, status in sorted(local.get("tools", {}).items()):
            detail = status.get("version") or status.get("error") or "-"
            lines.append(f"| {name} | {'yes' if status.get('available') else 'no'} | {detail} |")

    lines.extend(
        [
            "",
            "## Benefit Lanes",
            "",
            "| Lane | Benefits | Safe Sapphire Use | Gate | Sources |",
            "|---|---|---|---|---|",
        ]
    )
    for entry in inventory.get("catalog", []):
        sources = ", ".join(f"[{key}]({SOURCE_URLS[key]})" for key in entry["sources"])
        lines.append(
            "| {lane} | {benefits} | {safe_use} | {gate} | {sources} |".format(
                lane=entry["lane"],
                benefits="<br>".join(entry["benefits"]),
                safe_use=entry["safe_use"],
                gate=entry["gate"],
                sources=sources,
            )
        )

    lines.extend(
        [
            "",
            "## Recommended Order",
            "",
            "1. Confirm exact memberships from Google dashboards without sharing secrets.",
            "2. Keep GCP/Gemini/Veo work in local dry-run artifacts until a budget cap is written down.",
            "3. Add Gmail/Drive threat hygiene as metadata-only scan proposals before any labels or trash actions.",
            "4. Use Cloud Storage and BigQuery free-tier-aware caps for summarized artifacts, not raw secrets or personal mail.",
            "5. Promote Vertex batch/evals before tuning or always-on endpoints.",
        ]
    )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only Google benefits inventory and Sapphire utilization map."
    )
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument(
        "--membership",
        action="append",
        choices=sorted(MEMBERSHIPS),
        help="Assert a membership/benefit tier Ari has. Repeatable.",
    )
    parser.add_argument("--no-external", action="store_true", help="Do not call local CLIs.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    inventory = collect_inventory(
        project=args.project,
        memberships=args.membership or [],
        external=not args.no_external,
    )
    if args.format == "json":
        print(json.dumps(inventory, indent=2, sort_keys=True))
    else:
        print(render_markdown(inventory), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
