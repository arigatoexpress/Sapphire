#!/usr/bin/env python3
"""Dry-run Gmail and Drive threat-hygiene planner.

The planner emits queries, risk signals, and reversible action templates for
future Gmail/Drive cleanup. It does not call Google APIs, read message/file
contents, apply labels, move anything to trash, or delete data.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from typing import Any

DEFAULT_LOOKBACK_DAYS = 30

GMAIL_QUERY_TEMPLATES = [
    {
        "id": "spam_recent",
        "query": "in:spam newer_than:{days}d",
        "signals": ["already_classified_spam", "recent"],
        "safe_action": "Summarize counts only; do not read bodies.",
    },
    {
        "id": "dangerous_attachments",
        "query": "newer_than:{days}d has:attachment (filename:exe OR filename:js OR filename:vbs OR filename:bat OR filename:cmd OR filename:scr OR filename:iso OR filename:img)",
        "signals": ["executable_attachment", "script_attachment"],
        "safe_action": "Propose label Sapphire/Review/Suspicious-Attachment.",
    },
    {
        "id": "archive_attachment_pressure",
        "query": "newer_than:{days}d has:attachment (filename:zip OR filename:rar OR filename:7z)",
        "signals": ["compressed_attachment"],
        "safe_action": "Review sender/domain before attachment retrieval.",
    },
    {
        "id": "credential_phishing_language",
        "query": 'newer_than:{days}d ("verify your account" OR "password expires" OR "unusual activity" OR "gift card" OR "invoice attached" OR "wire transfer")',
        "signals": ["phishing_language", "finance_social_engineering"],
        "safe_action": "Extract metadata and sender domain only.",
    },
    {
        "id": "oversized_recent_mail",
        "query": "newer_than:{days}d larger:10M",
        "signals": ["storage_pressure", "large_attachment"],
        "safe_action": "Propose archive/storage cleanup after human review.",
    },
]

DRIVE_QUERY_TEMPLATES = [
    {
        "id": "public_or_link_shared",
        "query": "List files where sharing visibility is anyone-with-link or public.",
        "signals": ["external_exposure", "permission_review"],
        "safe_action": "Report file ID, owner, sharing role, and last modified time only.",
    },
    {
        "id": "risky_file_types",
        "query": "List non-trashed files with executable/archive extensions by metadata.",
        "signals": ["executable_or_archive", "malware_review"],
        "safe_action": "Do not download; propose Drive label Sapphire/Review/Suspicious.",
    },
    {
        "id": "stale_large_files",
        "query": "List large files not modified in the last 180 days.",
        "signals": ["storage_pressure", "retention_review"],
        "safe_action": "Propose archive/delete candidates only after owner confirmation.",
    },
    {
        "id": "external_owners",
        "query": "List files owned by external accounts but accessible to Ari.",
        "signals": ["third_party_owner", "shared_drive_review"],
        "safe_action": "Review access path; no permission changes by default.",
    },
]

APPROVAL_STEPS = [
    "metadata_count",
    "metadata_sample",
    "local_report",
    "human_approve_label",
    "human_approve_archive_or_trash",
]


def build_plan(*, days: int = DEFAULT_LOOKBACK_DAYS) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "dry-run-plan",
        "lookback_days": days,
        "guardrails": [
            "No Gmail or Drive APIs are called by this planner.",
            "No message bodies, attachments, Drive file contents, or secrets are read.",
            "No labels, permissions, archive states, trash states, or deletes are changed.",
            "Permanent delete is outside the autonomous lane.",
        ],
        "gmail_queries": [
            {**template, "query": template["query"].format(days=days)}
            for template in GMAIL_QUERY_TEMPLATES
        ],
        "drive_queries": DRIVE_QUERY_TEMPLATES,
        "approval_steps": APPROVAL_STEPS,
        "recommended_labels": [
            "Sapphire/Review/Suspicious",
            "Sapphire/Review/Suspicious-Attachment",
            "Sapphire/Review/Storage-Cleanup",
            "Sapphire/Review/External-Share",
        ],
        "blocked_actions": [
            "gmail.users.messages.delete",
            "gmail.users.messages.batchDelete",
            "drive.files.delete",
            "drive.files.emptyTrash",
            "attachment download without approval",
            "Drive file download without approval",
        ],
    }


def render_markdown(plan: dict[str, Any]) -> str:
    lines = [
        "# Google Workspace Threat Hygiene Plan",
        "",
        f"- Generated: `{plan['generated_at']}`",
        f"- Mode: `{plan['mode']}`",
        f"- Lookback days: `{plan['lookback_days']}`",
        "",
        "## Guardrails",
        "",
    ]
    for guardrail in plan["guardrails"]:
        lines.append(f"- {guardrail}")

    lines.extend(
        [
            "",
            "## Gmail Review Queries",
            "",
            "| ID | Query | Signals | Safe Action |",
            "|---|---|---|---|",
        ]
    )
    for query in plan["gmail_queries"]:
        lines.append(
            "| {id} | `{query}` | {signals} | {safe_action} |".format(
                id=query["id"],
                query=query["query"],
                signals=", ".join(query["signals"]),
                safe_action=query["safe_action"],
            )
        )

    lines.extend(
        [
            "",
            "## Drive Review Queries",
            "",
            "| ID | Query | Signals | Safe Action |",
            "|---|---|---|---|",
        ]
    )
    for query in plan["drive_queries"]:
        lines.append(
            "| {id} | {query} | {signals} | {safe_action} |".format(
                id=query["id"],
                query=query["query"],
                signals=", ".join(query["signals"]),
                safe_action=query["safe_action"],
            )
        )

    lines.extend(["", "## Approval Ladder", ""])
    for index, step in enumerate(plan["approval_steps"], start=1):
        lines.append(f"{index}. `{step}`")

    lines.extend(["", "## Blocked Autonomous Actions", ""])
    for action in plan["blocked_actions"]:
        lines.append(f"- `{action}`")

    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run Gmail/Drive threat hygiene planner.")
    parser.add_argument("--days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.days < 1:
        raise SystemExit("--days must be >= 1")
    plan = build_plan(days=args.days)
    if args.format == "json":
        print(json.dumps(plan, indent=2, sort_keys=True))
    else:
        print(render_markdown(plan), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
