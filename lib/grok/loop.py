"""Grok project steering loop — pure taskboard updates from status signals."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping, Sequence


def _utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


DEFAULT_TASKS: list[dict[str, Any]] = [
    {
        "id": "T-bridge-plant",
        "title": "Claude: wire plant sync_grok_web_exports → Knowledge inbox",
        "lane": "bridge",
        "priority": 1,
        "status": "in_progress_external",
        "done_when": "local-export receipt on main",
    },
    {
        "id": "T-policy-kernel",
        "title": "Ship dens/AXTI/free-reign paper policy + tests",
        "lane": "policy",
        "priority": 1,
        "status": "todo",
        "done_when": "lib/grok/policy.py tests green",
    },
    {
        "id": "T-genome",
        "title": "Genome lesson schema + AXTI/dens seed",
        "lane": "genome",
        "priority": 1,
        "status": "todo",
        "done_when": "LessonBook seed + tests",
    },
    {
        "id": "T-win-dc",
        "title": "Windows DC acceptance pack (P0 blocks ARM)",
        "lane": "windows",
        "priority": 1,
        "status": "todo",
        "done_when": "evaluate_windows_acceptance + checklist data",
    },
    {
        "id": "T-research-manifest",
        "title": "Research-worker manifest validator (paper_only)",
        "lane": "research",
        "priority": 2,
        "status": "todo",
        "done_when": "validate_research_manifest rejects live flags",
    },
    {
        "id": "T-automations-catalog",
        "title": "Catalog + clean Grok-related automations",
        "lane": "automations",
        "priority": 2,
        "status": "todo",
        "done_when": "projects/grok/AUTOMATIONS.md",
    },
    {
        "id": "T-ci-readme",
        "title": "Keep README test inventory bullet honest",
        "lane": "ci",
        "priority": 2,
        "status": "done",
        "done_when": "test_inventory --check-readme",
    },
    {
        "id": "T-website-dashboard",
        "title": "Fix sapphirealpha.xyz/dashboard empty SPA shell (~700B)",
        "lane": "website",
        "priority": 1,
        "status": "todo",
        "done_when": "curl /dashboard serves real app assets; Mission Control visible",
    },
    {
        "id": "T-website-evidence",
        "title": "Elevate Evidence Observatory story + architecture proof",
        "lane": "website",
        "priority": 2,
        "status": "todo",
        "done_when": "professional / with working CTAs; no dangling DNS ads",
    },
    {
        "id": "T-gcp-cost-posture",
        "title": "GCP cost posture: min-instances 0, Vertex idle, BQ freshness",
        "lane": "gcp",
        "priority": 2,
        "status": "todo",
        "done_when": "session note with describe + cost_posture_report",
    },
    {
        "id": "T-mission-docs",
        "title": "Win DC master plan + Gemini Cloud Shell prompt",
        "lane": "docs",
        "priority": 2,
        "status": "done",
        "done_when": "docs/strategy + handoffs on main",
    },
]


def tick(
    board: MutableMapping[str, Any],
    signals: Mapping[str, Any],
) -> dict[str, Any]:
    """Update task statuses from signals; return new board snapshot.

    signals examples:
      policy_tests_ok, genome_seeded, windows_module_ok, research_validator_ok,
      automations_catalog_ok, bridge_local_export_seen, monorepo_bridge_tools_ok
    """
    tasks: list[dict[str, Any]] = list(board.get("tasks") or DEFAULT_TASKS)
    by_id = {t["id"]: dict(t) for t in tasks}

    def complete(tid: str) -> None:
        if tid in by_id and by_id[tid].get("status") != "done":
            by_id[tid]["status"] = "done"
            by_id[tid]["completed_at"] = _utc()

    def progress(tid: str, status: str = "in_progress") -> None:
        if tid in by_id and by_id[tid].get("status") not in ("done",):
            by_id[tid]["status"] = status

    if signals.get("policy_tests_ok"):
        complete("T-policy-kernel")
    if signals.get("genome_seeded"):
        complete("T-genome")
    if signals.get("windows_module_ok"):
        complete("T-win-dc")
    if signals.get("research_validator_ok"):
        complete("T-research-manifest")
    if signals.get("automations_catalog_ok"):
        complete("T-automations-catalog")
    if signals.get("monorepo_bridge_tools_ok"):
        progress("T-bridge-plant", "blocked_on_plant")
    if signals.get("bridge_local_export_seen"):
        complete("T-bridge-plant")

    # dynamic follow-ups
    extras: list[dict[str, Any]] = list(board.get("dynamic_tasks") or [])
    existing_ids = set(by_id) | {e["id"] for e in extras}

    if signals.get("policy_tests_ok") and "T-wire-policy-plant" not in existing_ids:
        extras.append(
            {
                "id": "T-wire-policy-plant",
                "title": "Plant: import lib.grok.policy into free-reign decision path",
                "lane": "plant",
                "priority": 1,
                "status": "todo",
                "done_when": "plant free-reign calls evaluate_proposal",
            }
        )
    if signals.get("genome_seeded") and "T-wire-genome-closes" not in existing_ids:
        extras.append(
            {
                "id": "T-wire-genome-closes",
                "title": "Plant: append LessonBook on broker-reconciled closes",
                "lane": "plant",
                "priority": 1,
                "status": "todo",
                "done_when": "outcomes wins/losses non-zero from real closes",
            }
        )
    if by_id.get("T-win-dc", {}).get("status") == "done" and "T-win-post-boot" not in existing_ids:
        extras.append(
            {
                "id": "T-win-post-boot",
                "title": "Plant/Win: run P0 acceptance; only then ARM L2 schtasks",
                "lane": "windows",
                "priority": 1,
                "status": "todo",
                "done_when": "arm_l2_allowed true from real probes",
            }
        )

    ordered = sorted(by_id.values(), key=lambda t: (t.get("priority", 99), t["id"]))
    done = sum(1 for t in ordered if t.get("status") == "done")
    open_ = sum(1 for t in ordered if t.get("status") != "done")
    open_dyn = sum(1 for t in extras if t.get("status") != "done")

    out = {
        "updated_at": _utc(),
        "tasks": ordered,
        "dynamic_tasks": extras,
        "stats": {
            "static_done": done,
            "static_open": open_,
            "dynamic_open": open_dyn,
            "signals": dict(signals),
        },
        "next_actions": _next_actions(ordered, extras),
    }
    return out


def _next_actions(
    tasks: Sequence[Mapping[str, Any]],
    extras: Sequence[Mapping[str, Any]],
) -> list[str]:
    pool = [t for t in list(tasks) + list(extras) if t.get("status") not in ("done",)]
    pool.sort(key=lambda t: (t.get("priority", 99), t["id"]))
    return [f"{t['id']}: {t['title']}" for t in pool[:5]]


def render_markdown(board: Mapping[str, Any]) -> str:
    lines = [
        "# Grok project taskboard",
        "",
        f"_Updated: {board.get('updated_at', '?')}_",
        "",
        "## Next actions",
        "",
    ]
    for a in board.get("next_actions") or []:
        lines.append(f"- {a}")
    lines += ["", "## Static tasks", ""]
    for t in board.get("tasks") or []:
        box = "x" if t.get("status") == "done" else " "
        lines.append(f"- [{box}] `{t['id']}` **{t['status']}** — {t['title']}")
    if board.get("dynamic_tasks"):
        lines += ["", "## Dynamic follow-ups", ""]
        for t in board["dynamic_tasks"]:
            box = "x" if t.get("status") == "done" else " "
            lines.append(f"- [{box}] `{t['id']}` **{t['status']}** — {t['title']}")
    stats = board.get("stats") or {}
    lines += ["", "## Stats", "", f"```json\n{stats}\n```", ""]
    return "\n".join(lines)
