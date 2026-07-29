"""Sapphire control plane — local-first FastAPI entry point.

This service now serves the operational frontend and a minimal truthful API
surface derived from:

- SQLite task/agent state (`app.control_plane`)
- JSONL event stream (`app.event_stream`)
- Local repo inventory / board state (`app.project_board`)

The goal is to keep the PM surface accurate for the current on-prem runtime
instead of replaying the older Cloud Run / Firestore topology.
"""

from __future__ import annotations

import hmac
import logging
import os
import shutil
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.control_plane import ControlPlaneStore
from app.event_stream import append_event, recent_events
from app.kimi_bridge import ALL_ACTIONS, dispatch
from app.project_board import (
    create_card,
    get_projects_overview,
    load_roadmap_snapshot,
    sync_board_artifacts,
    update_card,
)
from app.runtime_policy import (
    allowed_executor_agent_ids,
    allowed_executor_membership_ids,
    load_runtime_policy,
)

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = BASE_DIR / "frontend"
ASSETS_DIR = FRONTEND_DIR / "assets"
FRONTEND_PAGES = {
    "index": "index.html",
    "projects": "projects.html",
    "organization": "organization.html",
    "architecture": "architecture.html",
    "logbook": "logbook.html",
    "secops": "secops.html",
    "status": "status.html",
}
_OPS_CACHE: dict[str, Any] = {"ts": 0.0, "payload": None}
_OPS_CACHE_TTL_SECONDS = 20.0


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _utc_iso_now() -> str:
    return _utc_now().isoformat()


def _runtime_mode() -> str:
    return "cloud_run" if os.getenv("K_SERVICE", "").strip() else "local"


def _service_name() -> str:
    return os.getenv("K_SERVICE", "").strip() or "sapphire-control-plane"


def _service_revision() -> str:
    return os.getenv("K_REVISION", "").strip() or "local"


@lru_cache(maxsize=1)
def _control_store() -> ControlPlaneStore:
    return ControlPlaneStore()


@lru_cache(maxsize=1)
def _asset_version() -> str:
    mtimes: list[int] = []
    for path in FRONTEND_DIR.rglob("*"):
        if path.is_file():
            try:
                mtimes.append(int(path.stat().st_mtime))
            except OSError:
                continue
    return str(max(mtimes) if mtimes else int(_utc_now().timestamp()))


def _render_page(page_key: str) -> str:
    filename = FRONTEND_PAGES[page_key]
    path = FRONTEND_DIR / filename
    html = path.read_text(encoding="utf-8")
    return html.replace("__ASSET_VERSION__", _asset_version())


def _control_token() -> str:
    settings = get_settings()
    return settings.control_plane_shared_token or os.getenv("CONTROL_PLANE_TOKEN", "").strip()


def _require_control_token(token: str) -> None:
    expected = _control_token()
    if not expected:
        # Fail closed when the shared token is unconfigured — the previous
        # behavior (silently accepting every request) turned every write
        # endpoint into an open relay on hosts that forgot to set the env.
        raise HTTPException(
            status_code=503,
            detail="control token not configured — set CONTROL_PLANE_TOKEN",
        )
    if not hmac.compare_digest(str(token or ""), expected):
        raise HTTPException(status_code=403, detail="invalid control token")


def _safe_json_body(body: Any) -> dict[str, Any]:
    return body if isinstance(body, dict) else {}


def _tool_summary() -> dict[str, bool]:
    return {
        "gh": bool(shutil.which("gh")),
        "gcloud": bool(shutil.which("gcloud")),
        "docker": bool(shutil.which("docker")),
        "node": bool(shutil.which("node")),
    }


def _tag_value(tags: list[str] | None, namespace: str) -> str:
    for tag in tags or []:
        text = str(tag or "").strip()
        if text.startswith(f"{namespace}:"):
            return text.split(":", 1)[1].strip()
    return ""


def _event_headline(event: dict[str, Any]) -> str:
    message = str(event.get("message") or "").strip()
    if message:
        return message[:160]
    event_type = str(event.get("event_type") or "event").strip().replace("_", " ")
    return event_type.title()


def _event_log_kind(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or "").strip().lower()
    severity = str(event.get("severity") or "info").strip().lower()
    message = str(event.get("message") or "").strip().lower()
    if severity in {"error", "critical"} or "incident" in event_type or "fail" in event_type:
        return "incident"
    if "verification" in event_type or "verified" in event_type or "completed" in event_type:
        return "verification"
    if "handoff" in event_type or "lease" in event_type:
        return "handoff"
    if "decision" in event_type or "policy" in event_type or "route" in event_type:
        return "decision"
    if "operator_alert" in event_type and "review" in message:
        return "decision"
    return "progress"


def _event_timeline_row(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    return {
        "event_id": str(event.get("event_id") or ""),
        "event_type": str(event.get("event_type") or "event"),
        "headline": _event_headline(event),
        "message": str(event.get("message") or ""),
        "created_at": str(event.get("generated_at") or ""),
        "severity": str(event.get("severity") or "info"),
        "log_kind": _event_log_kind(event),
        "agent_id": _tag_value(event.get("tags"), "agent") or str(event.get("actor") or ""),
        "project_id": str(event.get("project_id") or "")
        or _tag_value(event.get("tags"), "project"),
        "channel": str(event.get("source") or "control-plane"),
        "status": str(event.get("status") or payload.get("status") or ""),
    }


def _normalized_agent_host(agent: dict[str, Any]) -> dict[str, Any]:
    metadata = agent.get("metadata") if isinstance(agent.get("metadata"), dict) else {}
    labels = agent.get("labels") if isinstance(agent.get("labels"), dict) else {}
    host = metadata.get("host") if isinstance(metadata.get("host"), dict) else {}
    agent_id = str(agent.get("agent_id") or "").strip().lower()
    inferred_host_id = str(
        host.get("host_id")
        or metadata.get("host_id")
        or labels.get("host_id")
        or ("rari1" if "rari1" in agent_id else "rari2" if "rari2" in agent_id else "mac")
    ).strip()
    inferred_host_class = str(
        host.get("host_class")
        or metadata.get("host_class")
        or ("pi" if inferred_host_id.startswith("rari") else "workstation")
    ).strip()
    return {
        "host_id": inferred_host_id or "unknown",
        "host_class": inferred_host_class or "unknown",
        "node_role": str(
            host.get("node_role") or metadata.get("node_role") or labels.get("role") or "executor"
        ).strip(),
        "hostname": str(
            host.get("hostname") or metadata.get("hostname") or inferred_host_id or "unknown"
        ).strip(),
        "workspace_root": str(
            host.get("workspace_root") or metadata.get("workspace_root") or ""
        ).strip(),
    }


def _agent_memberships(agent: dict[str, Any]) -> set[str]:
    memberships: set[str] = set()
    labels = agent.get("labels") if isinstance(agent.get("labels"), dict) else {}
    for key in ("membership_id", "model_membership", "router_membership"):
        value = str(labels.get(key) or "").strip().lower()
        if value:
            memberships.add(value)
    for capability in (
        agent.get("capabilities") if isinstance(agent.get("capabilities"), list) else []
    ):
        text = str(capability or "").strip().lower()
        if text.startswith("membership:"):
            memberships.add(text.split(":", 1)[1].strip())
    return memberships


def _normalized_executor_policy() -> dict[str, Any]:
    policy = load_runtime_policy()
    allowed_agents = allowed_executor_agent_ids(policy)
    allowed_memberships = allowed_executor_membership_ids(policy)
    mode = str(policy.get("mode") or "").strip().lower()
    if not mode:
        mode = "locked" if (allowed_agents or allowed_memberships) else "open"
    return {
        "mode": mode,
        "allowed_executor_agent_ids": allowed_agents,
        "allowed_executor_membership_ids": allowed_memberships,
        "effective_policy_lock_applied": bool(policy),
        "updated_at": str(policy.get("updated_at") or ""),
    }


def _normalized_task(task: dict[str, Any]) -> dict[str, Any]:
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    contract = payload.get("contract") if isinstance(payload.get("contract"), dict) else {}
    normalized = dict(task)
    normalized["routing"] = (
        payload.get("routing") if isinstance(payload.get("routing"), dict) else {}
    )
    normalized["progress"] = str(payload.get("progress") or "").strip()
    normalized["display_title"] = str(
        contract.get("objective") or task.get("title") or task.get("task_id") or ""
    ).strip()
    return normalized


def _primary_executor(agents: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    allowed_agents = {
        str(item).strip().lower() for item in policy.get("allowed_executor_agent_ids", [])
    }
    allowed_memberships = {
        str(item).strip().lower() for item in policy.get("allowed_executor_membership_ids", [])
    }

    candidates: list[dict[str, Any]] = []
    for agent in agents:
        if not bool(agent.get("online")):
            continue
        agent_id = str(agent.get("agent_id") or "").strip().lower()
        memberships = _agent_memberships(agent)
        if allowed_agents and agent_id not in allowed_agents:
            continue
        if allowed_memberships and not (memberships & allowed_memberships):
            continue
        candidates.append(agent)
    if not candidates:
        candidates = [agent for agent in agents if bool(agent.get("online"))]
    if not candidates:
        return {}

    candidates.sort(
        key=lambda agent: (
            0 if _normalized_agent_host(agent).get("host_id", "").startswith("rari") else 1,
            str(agent.get("agent_id") or ""),
        )
    )
    selected = dict(candidates[0])
    selected["host"] = _normalized_executor_policy()  # placeholder to avoid mypy? replaced below
    selected["host"] = _normalized_agent_host(selected)
    selected["membership"] = {
        "labels_membership_id": next(iter(sorted(_agent_memberships(selected))), ""),
        "memberships": sorted(_agent_memberships(selected)),
    }
    return selected


def _queue_routability(
    tasks: list[dict[str, Any]], executors: list[dict[str, Any]]
) -> dict[str, Any]:
    blocker_breakdown: Counter[str] = Counter()
    routable_count = 0
    online_executors = [agent for agent in executors if bool(agent.get("online"))]
    for task in tasks:
        routing = task.get("routing") if isinstance(task.get("routing"), dict) else {}
        required_membership = (
            str(
                routing.get("required_membership_id")
                or routing.get("recommended_membership_id")
                or ""
            )
            .strip()
            .lower()
        )
        required_caps = (
            {
                str(cap).strip().lower()
                for cap in task.get("required_capabilities")
                if isinstance(task.get("required_capabilities"), list)
                for cap in task.get("required_capabilities", [])
            }
            if False
            else {
                str(cap).strip().lower()
                for cap in (
                    task.get("required_capabilities")
                    if isinstance(task.get("required_capabilities"), list)
                    else []
                )
            }
        )
        if not online_executors:
            blocker_breakdown["no_online_executors"] += 1
            continue

        matched = False
        membership_denied = False
        capability_denied = False
        for agent in online_executors:
            memberships = _agent_memberships(agent)
            if required_membership and required_membership not in memberships:
                membership_denied = True
                continue
            agent_caps = {
                str(cap).strip().lower()
                for cap in (
                    agent.get("capabilities") if isinstance(agent.get("capabilities"), list) else []
                )
            }
            if required_caps and not required_caps.issubset(agent_caps):
                capability_denied = True
                continue
            matched = True
            break
        if matched:
            routable_count += 1
        elif membership_denied:
            blocker_breakdown["membership_mismatch"] += 1
        elif capability_denied:
            blocker_breakdown["capability_mismatch"] += 1
        else:
            blocker_breakdown["unclassified"] += 1

    queued_count = len(tasks)
    top_reason = blocker_breakdown.most_common(1)[0][0] if blocker_breakdown else "none"
    recommendations: list[dict[str, Any]] = []
    if queued_count and routable_count == 0:
        recommendations.append(
            {
                "priority": "high",
                "id": "restore_routability",
                "action": f"Restore executor routability ({top_reason}) before adding more queued work.",
            }
        )
    elif queued_count and routable_count < queued_count:
        recommendations.append(
            {
                "priority": "medium",
                "id": "partial_routability",
                "action": f"{queued_count - routable_count} queued task(s) are blocked by routing constraints.",
            }
        )
    return {
        "summary": {
            "queued_count": queued_count,
            "routable_count": routable_count,
            "blocker_breakdown": [
                {"reason": reason, "count": count}
                for reason, count in blocker_breakdown.most_common()
            ],
        },
        "recommendations": recommendations,
    }


def _build_control_plane_payload(*, task_limit: int = 12, event_limit: int = 20) -> dict[str, Any]:
    store = _control_store()
    overview = store.overview()
    agents = store.list_agents(include_disabled=True)
    tasks = [
        _normalized_task(task) for task in store.list_tasks(status=None, limit=max(20, task_limit))
    ]
    events = store.list_events(limit=max(20, event_limit))
    return {
        "generated_at": _utc_iso_now(),
        "overview": overview,
        "agents": agents,
        "tasks": tasks[:task_limit],
        "events": events[:event_limit],
    }


def _build_frontend_logbook_payload(*, event_limit: int = 40) -> dict[str, Any]:
    timeline = [
        _event_timeline_row(event) for event in recent_events(limit=max(20, min(event_limit, 200)))
    ]
    communication_ledgers: dict[str, list[dict[str, Any]]] = {
        "decision": [],
        "handoff": [],
        "incident": [],
        "verification": [],
    }
    categories: dict[str, dict[str, Any]] = {}
    kind_counts: Counter[str] = Counter()
    severity_counts: Counter[str] = Counter()
    event_type_counts: Counter[str] = Counter()
    for row in timeline:
        kind = str(row.get("log_kind") or "progress")
        kind_counts[kind] += 1
        severity_counts[str(row.get("severity") or "info")] += 1
        event_type_counts[str(row.get("event_type") or "event")] += 1
        categories.setdefault(kind, {"count": 0})
        categories[kind]["count"] += 1
        categories[kind]["latest_headline"] = row.get("headline") or ""
        categories[kind]["latest_at"] = row.get("created_at") or ""
        categories[kind]["latest_agent_id"] = row.get("agent_id") or ""
        categories[kind]["latest_project_id"] = row.get("project_id") or ""
        if kind in communication_ledgers and len(communication_ledgers[kind]) < 12:
            communication_ledgers[kind].append(row)

    roadmap = load_roadmap_snapshot()
    horizons = roadmap.get("horizons") if isinstance(roadmap.get("horizons"), dict) else {}
    control = _build_control_plane_payload(task_limit=12, event_limit=20)
    overview = control.get("overview") if isinstance(control.get("overview"), dict) else {}
    tasks = (
        overview.get("kpi_tasks")
        if isinstance(overview.get("kpi_tasks"), dict)
        else overview.get("tasks", {})
    )
    policy = _normalized_executor_policy()

    return {
        "generated_at": _utc_iso_now(),
        "service_revision": _service_revision(),
        "summary": {
            "policy_mode": policy.get("mode", "open"),
            "policy_lock_applied": bool(policy.get("effective_policy_lock_applied")),
            "policy_drift_detected": False,
            "timeline_count": len(timeline),
            "task_event_count": sum(
                1 for row in timeline if str(row.get("event_type") or "").startswith("task_")
            ),
            "system_event_count": sum(
                1 for row in timeline if not str(row.get("event_type") or "").startswith("task_")
            ),
            "tasks_queued": int(tasks.get("queued", 0)),
            "tasks_leased": int(tasks.get("leased", 0)),
            "tasks_failed": int(tasks.get("failed", 0)),
            "roadmap_now_count": len(horizons.get("now", []))
            if isinstance(horizons.get("now"), list)
            else 0,
            "roadmap_next_count": len(horizons.get("next", []))
            if isinstance(horizons.get("next"), list)
            else 0,
        },
        "communication_views": {
            "categories": categories,
            "decision_ledger": communication_ledgers["decision"],
            "handoff_ledger": communication_ledgers["handoff"],
            "incident_ledger": communication_ledgers["incident"],
            "verification_ledger": communication_ledgers["verification"],
        },
        "event_mix": {
            "by_log_kind": dict(kind_counts),
            "by_severity": dict(severity_counts),
            "top_event_types": [
                {"event_type": event_type, "count": count}
                for event_type, count in event_type_counts.most_common(10)
            ],
        },
        "timeline": timeline,
    }


def _build_ops_status_payload(*, refresh: bool = False) -> dict[str, Any]:
    now_ts = _utc_now().timestamp()
    cached_payload = _OPS_CACHE.get("payload")
    cached_ts = float(_OPS_CACHE.get("ts") or 0)
    if not refresh and cached_payload and (now_ts - cached_ts) < _OPS_CACHE_TTL_SECONDS:
        return cached_payload

    control = _build_control_plane_payload(task_limit=20, event_limit=20)
    overview = control.get("overview") if isinstance(control.get("overview"), dict) else {}
    agents = control.get("agents") if isinstance(control.get("agents"), list) else []
    policy = _normalized_executor_policy()
    primary = _primary_executor(agents, policy)
    executors = [
        agent for agent in agents if str(agent.get("status") or "").strip().lower() != "disabled"
    ]
    queued_tasks = [
        task
        for task in control.get("tasks", [])
        if str(task.get("status") or "").lower() == "queued"
    ]
    queue = _queue_routability(queued_tasks, executors)
    queue_summary = queue.get("summary") if isinstance(queue.get("summary"), dict) else {}
    top_blocker = str((queue_summary.get("blocker_breakdown") or [{}])[0].get("reason") or "none")
    tool_summary = _tool_summary()

    online_executors = [agent for agent in executors if bool(agent.get("online"))]
    attestation = {
        "executor_count": len(executors),
        "online_executor_count": len(online_executors),
        "all_online_have_host_attestation": all(
            bool(_normalized_agent_host(agent).get("host_id")) for agent in online_executors
        ),
        "primary_executor_pi_hosted": bool(
            primary and str((primary.get("host") or {}).get("host_id") or "").startswith("rari")
        ),
    }

    recommendations: list[str] = []
    if not online_executors:
        recommendations.append(
            "No online executors are registered in the local control-plane store."
        )
    if queued_tasks and int(queue_summary.get("routable_count", 0)) == 0:
        recommendations.append(
            f"Queued work is stalled by {top_blocker}; restore agent heartbeats or routing policy."
        )
    if not tool_summary.get("gh"):
        recommendations.append(
            "GitHub CLI is unavailable on this host; repo telemetry and auth checks are degraded."
        )
    if not tool_summary.get("node"):
        recommendations.append(
            "Node.js is unavailable on this host; browser/automation helper flows may degrade."
        )

    tasks = (
        overview.get("kpi_tasks")
        if isinstance(overview.get("kpi_tasks"), dict)
        else overview.get("tasks", {})
    )
    payload = {
        "generated_at": _utc_iso_now(),
        "service_revision": _service_revision(),
        "summary": {
            "policy_mode": policy.get("mode", "open"),
            "policy_lock_applied": bool(policy.get("effective_policy_lock_applied")),
            "policy_drift_detected": False,
            "tasks_queued": int(tasks.get("queued", 0)),
            "tasks_leased": int(tasks.get("leased", 0)),
            "tasks_failed": int(tasks.get("failed", 0)),
            "queue_stall_detected": bool(queued_tasks)
            and int(queue_summary.get("routable_count", 0)) == 0,
            "queue_top_blocker_reason": top_blocker,
            "agents_executor_online": int(overview.get("agents_executor_online", 0)),
            "agents_executor_total": int(overview.get("agents_executor_total", 0)),
            "agents_online": int(overview.get("agents_online", 0)),
            "agents_registered": int(overview.get("agents_registered", 0)),
        },
        "policy_drift": {
            "enabled": bool(policy.get("effective_policy_lock_applied")),
            "drift_detected": False,
            "mismatches": [],
            "expected": policy,
            "observed": policy,
        },
        "queue_routability": queue,
        "executor_readiness": {
            "policy_mode": policy.get("mode", "open"),
            "effective_policy_lock_applied": bool(policy.get("effective_policy_lock_applied")),
            "tool_summary": tool_summary,
            "attestation": attestation,
            "primary_executor": primary,
            "recommendations": recommendations,
        },
    }
    _OPS_CACHE["ts"] = now_ts
    _OPS_CACHE["payload"] = payload
    return payload


def _signal_score(row: dict[str, Any]) -> int:
    kind = str(row.get("log_kind") or "progress")
    severity = str(row.get("severity") or "info")
    if kind == "verification":
        return 72
    if kind == "decision":
        return 64
    if kind == "handoff":
        return 58
    if severity in {"error", "critical"}:
        return 32
    return 50


def _build_frontend_overview_payload() -> dict[str, Any]:
    settings = get_settings()
    logbook = _build_frontend_logbook_payload(event_limit=12)
    ops_status = _build_ops_status_payload()
    control = _build_control_plane_payload(task_limit=12, event_limit=12)
    overview = control.get("overview") if isinstance(control.get("overview"), dict) else {}
    timeline = logbook.get("timeline") if isinstance(logbook.get("timeline"), list) else []
    alpha_items = [
        {
            "title": str(row.get("headline") or "System event"),
            "source": str(row.get("channel") or "control-plane"),
            "alpha_score": _signal_score(row),
            "bias": "Operational",
            "confidence": "high"
            if str(row.get("severity") or "") in {"info", "warning"}
            else "guarded",
            "assets": [project] if (project := str(row.get("project_id") or "").strip()) else [],
            "url": "",
            "published_at": str(row.get("created_at") or ""),
        }
        for row in timeline[:6]
    ]
    monitor_healthy = not bool((ops_status.get("summary") or {}).get("queue_stall_detected"))
    tasks = (
        overview.get("kpi_tasks")
        if isinstance(overview.get("kpi_tasks"), dict)
        else overview.get("tasks", {})
    )

    return {
        "status": "ok" if overview.get("slo", {}).get("status", "ok") == "ok" else "degraded",
        "generated_at": _utc_iso_now(),
        "frontend_asset_version": _asset_version(),
        "control_channel": "owner_secure_review",
        "store": "local-memory+sqlite",
        "service_name": _service_name(),
        "service_revision": _service_revision(),
        "heartbeat_interval_minutes": settings.heartbeat_interval_minutes,
        "allowlist_enabled": bool(
            settings.allowed_telegram_user_ids or settings.allowed_telegram_chat_ids
        ),
        "public_prompting_enabled": False,
        "alpha_stream": {"items": alpha_items},
        "signals": alpha_items,
        "overnight_reliability": {
            "monitor": {
                "healthy": monitor_healthy,
                "alert_count": 0 if monitor_healthy else 1,
                "generated_at": _utc_iso_now(),
            },
            "latest_cycle": {
                "timestamp_utc": _utc_iso_now(),
                "age_minutes": 0,
                "unified_ops": "local-first",
                "tests": "not_run",
                "pi_fleet_audit": "pending",
                "canary_soak": "not_configured",
                "queue": int(tasks.get("queued", 0)),
                "failed": int(tasks.get("failed", 0)),
                "slo_status": str((overview.get("slo") or {}).get("status") or "unknown"),
            },
            "tests": {
                "summary_line": "No nightly test artifact wired into the local control plane yet.",
                "duration_seconds": 0,
                "slowest_test_seconds": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
            },
            "soak": {
                "gate_status": "not_configured",
                "latest_observation_outcome": "unknown",
                "success_rate": 0,
                "observations_success": 0,
                "observations_total": 0,
                "observations_error": 0,
                "ignored_observations_total": 0,
                "gate_detail": "Local-first migration is active; canary soak artifacts have not been reconnected yet.",
                "generated_at": _utc_iso_now(),
            },
        },
    }


def _group_workspaces(tracked_projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    definitions = [
        {
            "name": "Autonomy Platform",
            "root": "/Users/aribs/Code/Sapphire",
            "purpose": "Canonical source-of-truth repo for the local control plane, trading orchestration, webhook, and infrastructure.",
        },
        {
            "name": "Codex Workspace",
            "root": "/Users/aribs/Documents/Organized/Codex Projects",
            "purpose": "Operator planning, memory, prompts, and experimental automation that steers the PM loop.",
        },
        {
            "name": "Client Delivery",
            "root": "/Users/aribs/Code/Project-Go-Forward",
            "purpose": "Active client execution lane for current delivery work.",
        },
        {
            "name": "Finance / Tax Ops",
            "root": "/Users/aribs/Code/Cointracker",
            "purpose": "Bookkeeping, accounting, and finance-side operational tracking.",
        },
        {
            "name": "Local Runtimes",
            "root": "/Users/aribs/.openclaw",
            "purpose": "Pi/runtime agent state, local bots, and recovery surfaces.",
        },
    ]
    rows: list[dict[str, Any]] = []
    for definition in definitions:
        root = definition["root"]
        projects = [
            {
                "id": project.get("id"),
                "name": project.get("name"),
                "health": project.get("health"),
            }
            for project in tracked_projects
            if str(project.get("canonical_local_path") or "").startswith(root)
        ]
        healthy_count = len(
            [project for project in projects if str(project.get("health") or "") == "healthy"]
        )
        status = (
            "healthy" if healthy_count == len(projects) else ("attention" if projects else "idle")
        )
        rows.append(
            {
                "name": definition["name"],
                "root": root,
                "purpose": definition["purpose"],
                "status": status,
                "projects": projects,
                "metrics": {
                    "project_count": len(projects),
                    "healthy_count": healthy_count,
                },
            }
        )
    return rows


def _organization_units() -> list[dict[str, Any]]:
    return [
        {
            "id": "organization-os",
            "name": "Organization OS",
            "purpose": "Agentic project management, delegation, memory, and operating cadence for Sapphire as a whole.",
            "surfaces": ["control-plane", "codex-workspace", "linear"],
            "roots": [
                "/Users/aribs/Code/Sapphire/services/control-plane",
                "/Users/aribs/Documents/Organized/Codex Projects",
            ],
        },
        {
            "id": "trading-intelligence",
            "name": "Trading + Market Intelligence",
            "purpose": "Signal intake, venue routing, market/news analysis, and execution readiness for ASTER/LIGHTER.",
            "surfaces": ["alpha-engine", "telegram", "rari1", "rari2"],
            "roots": ["/Users/aribs/Code/Sapphire", "/Users/aribs/.openclaw"],
        },
        {
            "id": "research-lab",
            "name": "Research Lab",
            "purpose": "Local model evaluation, Kimi/OpenClaw recovery, repo scouting, and safe self-improvement experiments.",
            "surfaces": ["kimi-openclaw", "tailscale", "local-models"],
            "roots": ["/Users/aribs/.openclaw", "/Users/aribs/Documents/Organized/Codex Projects"],
        },
        {
            "id": "client-delivery",
            "name": "Client Delivery",
            "purpose": "Execution lane for active client systems such as THO and the BIS intelligence stack.",
            "surfaces": ["project-go-forward", "delivery-board"],
            "roots": ["/Users/aribs/Code/Project-Go-Forward"],
        },
        {
            "id": "finance-compliance",
            "name": "Finance + Compliance",
            "purpose": "Coin tracking, bookkeeping, tax posture, and operational reconciliation.",
            "surfaces": ["cointracker", "books"],
            "roots": ["/Users/aribs/Code/Cointracker"],
        },
    ]


def _build_trading_operations_payload(primary_executor: dict[str, Any]) -> dict[str, Any]:
    host_id = str((primary_executor.get("host") or {}).get("host_id") or "rari1")
    agent_id = str(primary_executor.get("agent_id") or "kimi-main")
    rails = [
        {
            "id": "aster",
            "name": "aster",
            "preferred_node": "rari1",
            "preferred_agent_id": agent_id if host_id == "rari1" else "rari1-executor",
            "required_membership_id": "aster",
            "readiness": "degraded" if host_id == "rari1" else "blocked",
        },
        {
            "id": "lighter",
            "name": "lighter",
            "preferred_node": "rari2",
            "preferred_agent_id": agent_id if host_id == "rari2" else "rari2-executor",
            "required_membership_id": "lighter",
            "readiness": "degraded" if host_id == "rari2" else "blocked",
        },
    ]
    ready_count = len([row for row in rails if row["readiness"] == "ready"])
    degraded_count = len([row for row in rails if row["readiness"] == "degraded"])
    model = "local-first"
    if ready_count == len(rails):
        model = "local-execution"
    elif degraded_count:
        model = "hybrid-local"
    return {
        "recommended_model": model,
        "description": "Local operator hub with Pi execution rails and limited residual cloud references only where still required.",
        "rails": rails,
    }


def _build_org_overview_payload(*, refresh: bool = False) -> dict[str, Any]:
    projects = get_projects_overview(force_refresh=refresh)
    tracked_projects = (
        projects.get("tracked_projects")
        if isinstance(projects.get("tracked_projects"), list)
        else []
    )
    workspaces = _group_workspaces(tracked_projects)
    ops_status = _build_ops_status_payload(refresh=refresh)
    ops_summary = ops_status.get("summary") if isinstance(ops_status.get("summary"), dict) else {}
    primary_executor = (
        (ops_status.get("executor_readiness") or {}).get("primary_executor")
        if isinstance(ops_status.get("executor_readiness"), dict)
        else {}
    )
    policy = _normalized_executor_policy()
    runtime_exists = any(
        str(project.get("id") or "") == "kimi-openclaw-runtime"
        and bool(project.get("canonical_exists"))
        for project in tracked_projects
    )
    source_of_truth_repo = next(
        (
            str(project.get("canonical_local_path") or "")
            for project in tracked_projects
            if str(project.get("id") or "") == "sapphire-platform"
        ),
        "/Users/aribs/Code/Sapphire",
    )

    blockers: list[str] = []
    summary = projects.get("summary") if isinstance(projects.get("summary"), dict) else {}
    if int(summary.get("tracked_missing_local_count", 0)) > 0:
        blockers.append(
            f"{int(summary.get('tracked_missing_local_count', 0))} tracked project(s) point at missing local paths."
        )
    if bool(ops_summary.get("queue_stall_detected")):
        blockers.append(f"Queued work is stalled by {ops_summary.get('queue_top_blocker_reason')}.")
    if not (ops_status.get("executor_readiness") or {}).get("primary_executor"):
        if runtime_exists:
            blockers.append(
                "Kimi/OpenClaw runtime is present locally, but no executor heartbeat is registering into the control plane."
            )
        else:
            blockers.append(
                "No primary local executor is currently registered in the control plane."
            )

    recommendations: list[str] = []
    if int(summary.get("local_dirty_repo_count", 0)) > 0:
        recommendations.append(
            "Reduce dirty-repo drift so the PM board reflects clean, actionable execution state."
        )
    if runtime_exists and not primary_executor:
        recommendations.append(
            "Reconnect local runtime heartbeat/agent registration so PM tasks can route into the Pi or workstation executor pool."
        )
    if not policy.get("effective_policy_lock_applied"):
        recommendations.append(
            "Keep executor policy open while reconnecting runtime heartbeats, then lock allowed executors once the local fleet is stable."
        )
    recommendations.append(
        "Treat GCP as an optional bridge only; keep the PM core, task state, and repo inventory local-first."
    )
    if not blockers:
        recommendations.append(
            "No structural blockers detected; continue wiring live sources into the local PM hub."
        )

    return {
        "generated_at": _utc_iso_now(),
        "organization": {
            "name": "Sapphire Inc",
            "mission": "Autonomous organization coordinating projects, research, trading, and local agent infrastructure.",
            "environment": {
                "primary_runtime": "local-first",
                "cloud_posture": "limited-gcp-integration",
                "source_of_truth_repo": source_of_truth_repo,
                "operator_workspace": "/Users/aribs/Documents/Organized/Codex Projects",
            },
            "principles": [
                "Local-first control surface with limited residual cloud dependencies.",
                "Read-only public observability; operator control remains off the public web surface.",
                "One PM loop across platform, research, delivery, and finance lanes.",
            ],
            "operating_units": _organization_units(),
        },
        "shell_app": {
            "name": "Sapphire Control Plane",
            "runtime_mode": _runtime_mode(),
            "service_name": _service_name(),
            "service_revision": _service_revision(),
        },
        "projects_summary": projects.get("summary", {}),
        "workspaces": workspaces,
        "control_plane": {
            "overview": (ops_status.get("summary") or {})
            | {
                "agents_executor_online": (ops_status.get("summary") or {}).get(
                    "agents_executor_online", 0
                ),
                "agents_executor_total": (ops_status.get("summary") or {}).get(
                    "agents_executor_total", 0
                ),
            },
            "payload": _build_control_plane_payload(),
        },
        "trading_operations": _build_trading_operations_payload(primary_executor or {}),
        "executor_policy": policy,
        "blockers": blockers,
        "recommendations": recommendations,
    }


def _build_project_charts(tracked_projects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    charts: list[dict[str, Any]] = []
    for row in tracked_projects[:6]:
        path = Path(str(row.get("canonical_local_path") or "")).expanduser()
        top_components: list[dict[str, Any]] = []
        if path.exists() and path.is_dir():
            try:
                children = [child for child in sorted(path.iterdir()) if child.is_dir()][:3]
            except OSError:
                children = []
            top_components = [
                {"name": child.name, "files": len(list(child.glob("*")))} for child in children
            ]
        charts.append(
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "health": row.get("health"),
                "canonical_local_path": str(row.get("canonical_local_path") or ""),
                "stack_signals": ["python", "fastapi", "local-state"]
                if "sapphire" in str(row.get("slug") or "")
                else ["repo"],
                "scanned_files": len(top_components),
                "top_components": top_components,
                "mermaid": f'flowchart LR\n  ROOT["{str(row.get("name") or row.get("id") or "Project")}"] --> LOCAL["{path.name or "local"}"]\n  LOCAL --> HEALTH["health: {str(row.get("health") or "unknown")}"]',
            }
        )
    return charts


def _build_architecture_overview_payload(*, refresh: bool = False) -> dict[str, Any]:
    projects = get_projects_overview(force_refresh=refresh)
    logbook = _build_frontend_logbook_payload(event_limit=24)
    control = _build_control_plane_payload(task_limit=20, event_limit=20)
    overview = control.get("overview") if isinstance(control.get("overview"), dict) else {}
    agents = control.get("agents") if isinstance(control.get("agents"), list) else []
    topology_nodes = []
    topology_links = []
    for node_id, label, subtitle, status in [
        ("mac", "Operator Workstation", "Codex workspace", "stable"),
        ("control", "Control Plane", f"{_service_name()} ({_runtime_mode()})", "stable"),
        (
            "rari1",
            "rari1",
            "Pi / local execution",
            "stable"
            if any(
                "rari1" in str(_normalized_agent_host(agent).get("host_id") or "")
                and agent.get("online")
                for agent in agents
            )
            else "guarded",
        ),
        (
            "rari2",
            "rari2",
            "Pi / local research",
            "stable"
            if any(
                "rari2" in str(_normalized_agent_host(agent).get("host_id") or "")
                and agent.get("online")
                for agent in agents
            )
            else "guarded",
        ),
        ("telegram", "Telegram", "Notification-only", "guarded"),
    ]:
        topology_nodes.append(
            {"id": node_id, "label": label, "subtitle": subtitle, "status": status}
        )
    topology_links.extend(
        [
            {"from": "control", "to": "telegram", "label": "review notice"},
            {"from": "mac", "to": "control", "label": "local operator"},
            {"from": "control", "to": "rari1", "label": "task leases"},
            {"from": "control", "to": "rari2", "label": "task leases"},
        ]
    )
    mermaid = (
        "flowchart LR\n"
        '  MAC["Mac / Codex Workspace"] --> HUB["Sapphire Control Plane\\nlocal-first"]\n'
        '  HUB --> TG["Telegram notification-only"]\n'
        '  HUB --> R1["rari1\\nexecution rail"]\n'
        '  HUB --> R2["rari2\\nresearch rail"]\n'
        '  HUB --> REPOS["/Users/aribs/Code\\nSapphire + client repos"]\n'
        '  HUB --> STATE["SQLite + JSONL state"]'
    )
    project_charts = _build_project_charts(
        projects.get("tracked_projects")
        if isinstance(projects.get("tracked_projects"), list)
        else []
    )
    return {
        "generated_at": _utc_iso_now(),
        "service_name": _service_name(),
        "service_revision": _service_revision(),
        "runtime_mode": _runtime_mode(),
        "executor_policy": _normalized_executor_policy(),
        "topology": {
            "mermaid": mermaid,
            "fleet_nodes": [
                {
                    "node": _normalized_agent_host(agent).get("host_id"),
                    "role": _normalized_agent_host(agent).get("node_role"),
                    "reachable": bool(agent.get("online")),
                }
                for agent in agents
            ],
        },
        "stats": {
            "agents_online": int(overview.get("agents_online", 0)),
            "agents_executor_online": int(overview.get("agents_executor_online", 0)),
            "agents_registered": int(overview.get("agents_registered", 0)),
            "agents_disabled": int(overview.get("agents_disabled", 0)),
            "tasks_queued": int(
                (overview.get("kpi_tasks") or overview.get("tasks") or {}).get("queued", 0)
            ),
            "tasks_leased": int(
                (overview.get("kpi_tasks") or overview.get("tasks") or {}).get("leased", 0)
            ),
            "tasks_failed": int(
                (overview.get("kpi_tasks") or overview.get("tasks") or {}).get("failed", 0)
            ),
            "tasks_blocked_review": int(
                (overview.get("kpi_tasks") or overview.get("tasks") or {}).get("blocked_review", 0)
            ),
            "pi_nodes_reachable": len(
                {
                    _normalized_agent_host(agent).get("host_id")
                    for agent in agents
                    if bool(agent.get("online"))
                    and str(_normalized_agent_host(agent).get("host_id") or "").startswith("rari")
                }
            ),
            "pi_nodes_total": 2,
        },
        "logs": logbook.get("timeline", []),
        "slo": overview.get("slo", {}),
        "project_charts": project_charts,
        "project_charts_markdown_path": str(BASE_DIR / "data" / "agentic_roadmap_snapshot.md"),
    }


def _build_secops_payload(*, refresh: bool = False, event_limit: int = 80) -> dict[str, Any]:
    ops_status = _build_ops_status_payload(refresh=refresh)
    _build_architecture_overview_payload(refresh=refresh)
    logbook = _build_frontend_logbook_payload(event_limit=event_limit)
    summary = ops_status.get("summary") if isinstance(ops_status.get("summary"), dict) else {}
    primary = (
        ((ops_status.get("executor_readiness") or {}).get("primary_executor") or {})
        if isinstance(ops_status.get("executor_readiness"), dict)
        else {}
    )
    risk_points = 0
    if summary.get("queue_stall_detected"):
        risk_points += 3
    if summary.get("policy_drift_detected"):
        risk_points += 2
    tools = (
        ((ops_status.get("executor_readiness") or {}).get("tool_summary") or {})
        if isinstance(ops_status.get("executor_readiness"), dict)
        else {}
    )
    if not tools.get("gh"):
        risk_points += 1
    risk_band = "stable" if risk_points == 0 else "guarded" if risk_points <= 2 else "elevated"
    return {
        "generated_at": _utc_iso_now(),
        "service_revision": _service_revision(),
        "runtime_mode": _runtime_mode(),
        "summary": {
            "risk_band": risk_band,
            "risk_points": risk_points,
            **summary,
        },
        "posture": {
            "executor": {
                "tool_summary": tools,
                "primary_executor": primary,
            }
        },
        "analysis": {
            "event_mix": logbook.get("event_mix", {}),
            "topology": {
                "nodes": [
                    {
                        "id": node.get("id"),
                        "label": node.get("label"),
                        "subtitle": node.get("subtitle"),
                        "status": node.get("status"),
                    }
                    for node in [
                        {
                            "id": "control",
                            "label": "Control Plane",
                            "subtitle": _runtime_mode(),
                            "status": "stable",
                        },
                        {
                            "id": "telegram",
                            "label": "Telegram",
                            "subtitle": "operator channel",
                            "status": "stable",
                        },
                        {
                            "id": "rari1",
                            "label": "rari1",
                            "subtitle": "edge executor",
                            "status": "guarded",
                        },
                        {
                            "id": "rari2",
                            "label": "rari2",
                            "subtitle": "edge executor",
                            "status": "guarded",
                        },
                    ]
                ],
                "links": [
                    {"from": "control", "to": "telegram", "label": "review notice"},
                    {"from": "control", "to": "rari1", "label": "leases"},
                    {"from": "control", "to": "rari2", "label": "leases"},
                ],
            },
            "sectors": [
                {
                    "id": "control",
                    "label": "Control Plane",
                    "status": "stable" if not summary.get("queue_stall_detected") else "guarded",
                    "metrics": {
                        "queued": summary.get("tasks_queued", 0),
                        "leased": summary.get("tasks_leased", 0),
                        "failed": summary.get("tasks_failed", 0),
                    },
                    "analysis": "Local-first PM and executor routing state.",
                },
                {
                    "id": "agents",
                    "label": "Executor Fleet",
                    "status": "stable" if summary.get("agents_executor_online", 0) else "guarded",
                    "metrics": {
                        "online": summary.get("agents_executor_online", 0),
                        "total": summary.get("agents_executor_total", 0),
                    },
                    "analysis": "Online executor coverage across Pi/local nodes.",
                },
            ],
        },
        "redaction": {
            "mode": "public-safe",
            "aliases_applied": {"hosts": True, "agents": False, "projects": False},
            "fields_removed": ["task_ids", "raw_repo_urls", "local_paths"],
        },
        "classification": {
            "surface": "public-read-only",
            "command_channel": "owner_secure_review",
            "telegram_role": "notification_only",
        },
        "security_posture": {
            "privacy_first": {
                "public_prompting_enabled": False,
                "browser_token_storage": "operator-local-only",
            },
            "auth_boundaries": {"telegram_inbound_authority": "none"},
            "hardening_signals": {"openclaw_embedded_secret_key_count": 0},
            "recommended_actions": [
                "Keep control tokens off public surfaces and use operator-only pages for mutations.",
                "Re-register live executors so queue routability reflects the actual local fleet.",
                "Prune stale tracked-project paths to keep the PM view aligned with local reality.",
            ],
        },
        "predeploy_gate": [
            {
                "id": "local_runtime_only",
                "label": "Local-first runtime",
                "status": "pass",
                "detail": "Frontend and PM APIs are backed by local SQLite/JSONL state.",
            },
            {
                "id": "executor_presence",
                "label": "Executor coverage",
                "status": "pass" if summary.get("agents_executor_online", 0) else "warn",
                "detail": "Primary blocker is executor visibility, not cloud dependency.",
            },
        ],
        "ledgers": logbook.get("communication_views", {}),
        "timeline": logbook.get("timeline", []),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    append_event(
        "control_plane.startup",
        source="control-plane",
        message="Control plane started (store=local-sqlite+jsonl)",
        tags=["service:control-plane", "type:pm"],
    )
    log.info("Control plane ready — runtime=%s revision=%s", _runtime_mode(), _service_revision())
    yield
    log.info("Control plane shutting down")


app = FastAPI(title="Sapphire Control Plane", version="2.0.0", lifespan=lifespan)
app.mount("/assets", StaticFiles(directory=str(ASSETS_DIR)), name="assets")


@app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    return RedirectResponse(url=f"/assets/favicon.svg?v={_asset_version()}")


@app.get("/", response_class=HTMLResponse)
async def deck_page():
    return HTMLResponse(_render_page("index"))


@app.get("/projects", response_class=HTMLResponse)
async def projects_page():
    return HTMLResponse(_render_page("projects"))


@app.get("/organization", response_class=HTMLResponse)
async def organization_page():
    return HTMLResponse(_render_page("organization"))


@app.get("/architecture", response_class=HTMLResponse)
async def architecture_page():
    return HTMLResponse(_render_page("architecture"))


@app.get("/logbook", response_class=HTMLResponse)
async def logbook_page():
    return HTMLResponse(_render_page("logbook"))


@app.get("/secops", response_class=HTMLResponse)
async def secops_page():
    return HTMLResponse(_render_page("secops"))


@app.get("/status", response_class=HTMLResponse)
async def status_page():
    return HTMLResponse(_render_page("status"))


@app.get("/health")
async def health():
    settings = get_settings()
    return {
        "status": "ok",
        "service": _service_name(),
        "runtime_mode": _runtime_mode(),
        "store": "memory" if settings.use_in_memory_store else "firestore",
        "revision": _service_revision(),
    }


@app.get("/api/ecosystem-health")
async def ecosystem_health():
    """Run the full 20-point ecosystem health check and return JSON."""
    import json as _json
    import subprocess

    tool_path = (
        Path.home()
        / "Code"
        / "Sapphire"
        / "plugins"
        / "claw-sapphire"
        / "tools"
        / "health_check.py"
    )
    try:
        r = subprocess.run(
            [shutil.which("python3") or "python3", str(tool_path)],
            input="{}",
            capture_output=True,
            text=True,
            timeout=30,
        )
        return _json.loads(r.stdout) if r.stdout else {"error": "No output"}
    except Exception as exc:
        return {"error": str(exc)[:200]}


@app.get("/api/events")
async def list_events(limit: int = 50, category: str = "", source: str = "", tags: str = ""):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    events = recent_events(limit=min(limit, 200), category=category, source=source, tags=tag_list)
    return {"events": events, "count": len(events)}


@app.get("/api/tasks")
async def list_tasks(limit: int = 20):
    try:
        tasks = _control_store().list_tasks(status=None, limit=min(limit, 100))
        return {"tasks": tasks, "count": len(tasks)}
    except Exception as exc:
        log.warning("list_tasks error: %s", exc)
        return {"tasks": [], "count": 0, "error": str(exc)}


@app.get("/api/projects/overview")
async def projects_overview(refresh: bool = False):
    payload = get_projects_overview(force_refresh=refresh)
    payload["control_plane"] = _build_control_plane_payload(task_limit=12, event_limit=12)
    return payload


@app.post("/api/projects/sync")
async def projects_sync():
    return sync_board_artifacts()


@app.post("/api/projects/cards")
async def projects_create_card(request: Request):
    body = _safe_json_body(await request.json())
    return {"status": "ok", "card": create_card(body)}


@app.patch("/api/projects/cards/{card_id}")
async def projects_patch_card(card_id: str, request: Request):
    body = _safe_json_body(await request.json())
    return {"status": "ok", "card": update_card(card_id, body)}


@app.get("/api/frontend/overview")
async def frontend_overview():
    return _build_frontend_overview_payload()


@app.get("/api/frontend/logbook")
async def frontend_logbook(event_limit: int = 40, refresh: bool = False):
    return _build_frontend_logbook_payload(event_limit=event_limit)


@app.get("/api/frontend/ops-status")
async def frontend_ops_status(event_limit: int = 20, refresh: bool = False):
    _ = event_limit
    return _build_ops_status_payload(refresh=refresh)


@app.get("/api/org/overview")
async def org_overview(refresh: bool = False):
    return _build_org_overview_payload(refresh=refresh)


@app.get("/api/architecture/overview")
async def architecture_overview(refresh: bool = False):
    return _build_architecture_overview_payload(refresh=refresh)


@app.get("/api/frontend/secops")
async def frontend_secops(refresh: bool = False, event_limit: int = 80):
    return _build_secops_payload(refresh=refresh, event_limit=event_limit)


@app.get("/api/router/overview")
async def router_overview(refresh: bool = False):
    ops_status = _build_ops_status_payload(refresh=refresh)
    primary = (
        ((ops_status.get("executor_readiness") or {}).get("primary_executor") or {})
        if isinstance(ops_status.get("executor_readiness"), dict)
        else {}
    )
    memberships = []
    primary_memberships = sorted(_agent_memberships(primary)) if primary else []
    if primary_memberships:
        for membership in primary_memberships:
            memberships.append(
                {
                    "id": membership,
                    "name": membership,
                    "health": "ready",
                    "kind": "agent",
                    "version": str(primary.get("agent_id") or ""),
                    "quota": {"remaining": None, "unit": "tasks", "next_reset_at": ""},
                    "next_update_at": _utc_iso_now(),
                }
            )
    else:
        memberships.append(
            {
                "id": "local-default",
                "name": "local-default",
                "health": "unknown",
                "kind": "agent",
                "version": "no membership labels detected",
                "quota": {"remaining": None, "unit": "tasks", "next_reset_at": ""},
                "next_update_at": _utc_iso_now(),
            }
        )
    return {
        "generated_at": _utc_iso_now(),
        "summary": {
            "membership_ready_count": len(
                [row for row in memberships if row.get("health") == "ready"]
            ),
            "membership_unavailable_count": len(
                [row for row in memberships if row.get("health") == "unavailable"]
            ),
            "membership_quota_unknown_count": len(
                [row for row in memberships if row.get("quota", {}).get("remaining") is None]
            ),
            "filesystem_status": "local-only",
        },
        "memberships": memberships,
        "access_hub": {
            "accounts": [
                {
                    "name": "GitHub CLI",
                    "provider": "github",
                    "auth_status": "ready" if shutil.which("gh") else "missing",
                    "auth_detail": "Local repo telemetry via gh repo list",
                    "portal_url": "https://github.com",
                    "cli_login_command": "gh auth login",
                },
                {
                    "name": "Telegram",
                    "provider": "telegram",
                    "auth_status": "external",
                    "auth_detail": "Telegram notification-only; secure review is separate.",
                    "portal_url": "https://t.me",
                    "cli_login_command": "",
                },
            ]
        },
        "sample_recommendations": [
            {
                "membership": memberships[0]["name"],
                "reason": "primary local executor",
                "task_type": "coding",
            }
        ],
    }


@app.post("/api/router/quotas/refresh")
async def router_refresh(request: Request):
    _ = _safe_json_body(await request.json())
    return {"status": "ok", "refreshed_at": _utc_iso_now()}


@app.get("/api/control/overview")
async def control_overview():
    return _build_control_plane_payload(task_limit=20, event_limit=20)


@app.post("/api/control/tasks")
async def control_create_task(
    request: Request,
    x_control_token: str = Header(default=""),
):
    _require_control_token(x_control_token)
    body = _safe_json_body(await request.json())
    payload = body.get("payload") if isinstance(body.get("payload"), dict) else {}
    if body.get("task_type"):
        payload["task_type"] = str(body.get("task_type") or "").strip().lower()
    if body.get("requires_browser"):
        payload["requires_browser"] = True
    if body.get("enforce_routing"):
        payload.setdefault("routing", {})
        payload["routing"]["enforce_membership"] = True

    task = _control_store().create_task(
        title=str(body.get("title") or ""),
        payload=payload,
        required_capabilities=body.get("required_capabilities")
        if isinstance(body.get("required_capabilities"), list)
        else None,
        priority=int(body.get("priority") or 100),
        max_attempts=int(body.get("max_attempts") or 3),
        created_by=str(body.get("created_by") or "control-plane"),
    )
    return {
        "status": "ok",
        "task": _normalized_task(task),
        "routing": _normalized_task(task).get("routing", {}),
    }


@app.patch("/api/control/tasks/{task_id}")
async def control_update_task(
    task_id: str,
    request: Request,
    x_control_token: str = Header(default=""),
):
    _require_control_token(x_control_token)
    body = _safe_json_body(await request.json())
    task = _control_store().update_task(
        task_id=task_id,
        updated_by=str(body.get("updated_by") or "control-plane"),
        title=body.get("title"),
        payload_merge=body.get("payload_merge")
        if isinstance(body.get("payload_merge"), dict)
        else None,
        required_capabilities=body.get("required_capabilities")
        if isinstance(body.get("required_capabilities"), list)
        else None,
        priority=body.get("priority"),
        note=str(body.get("note") or ""),
    )
    return {"status": "ok", "task": _normalized_task(task)}


@app.post("/api/control/tasks/lease")
async def control_lease_tasks(
    request: Request,
    x_control_token: str = Header(default=""),
):
    _require_control_token(x_control_token)
    body = _safe_json_body(await request.json())
    leased = _control_store().lease_tasks(
        agent_id=str(body.get("agent_id") or ""),
        capabilities=body.get("capabilities")
        if isinstance(body.get("capabilities"), list)
        else None,
        lease_seconds=int(body.get("lease_seconds") or 300),
        limit=int(body.get("limit") or 1),
    )
    return {"status": "ok", "leased_tasks": [_normalized_task(task) for task in leased]}


@app.post("/api/control/tasks/{task_id}/complete")
async def control_complete_task(
    task_id: str,
    request: Request,
    x_control_token: str = Header(default=""),
):
    _require_control_token(x_control_token)
    body = _safe_json_body(await request.json())
    task = _control_store().complete_task(
        task_id=task_id,
        agent_id=str(body.get("agent_id") or ""),
        result=body.get("result") if isinstance(body.get("result"), dict) else None,
    )
    return {"status": "ok", "task": _normalized_task(task)}


@app.post("/api/control/tasks/{task_id}/fail")
async def control_fail_task(
    task_id: str,
    request: Request,
    x_control_token: str = Header(default=""),
):
    _require_control_token(x_control_token)
    body = _safe_json_body(await request.json())
    task = _control_store().fail_task(
        task_id=task_id,
        agent_id=str(body.get("agent_id") or ""),
        error_text=str(body.get("error") or "task failed"),
        retryable=bool(body.get("retryable")),
        error_code=str(body.get("error_code") or ""),
        membership_id=str(body.get("membership_id") or ""),
    )
    return {"status": "ok", "task": _normalized_task(task)}


@app.post("/api/security/zkpass/verify")
async def zkpass_verify(request: Request, x_control_token: str = Header(default="")):
    _require_control_token(x_control_token)
    body = _safe_json_body(await request.json())
    proof = body.get("proof")
    settings = get_settings()
    valid = bool(proof) and not settings.zkpass_enabled
    errors = (
        []
        if valid
        else (
            ["zkpass disabled or no proof supplied"]
            if not settings.zkpass_enabled
            else ["verification not implemented"]
        )
    )
    return {
        "status": "ok",
        "verification": {
            "valid": valid,
            "mode": settings.zkpass_mode,
            "errors": errors,
            "claims": {"schema_id": "local-advisory"} if valid else {},
        },
    }


@app.post("/api/kimi/pm")
async def kimi_pm(request: Request, x_control_token: str = Header(default="")):
    try:
        body: dict[str, Any] = await request.json()
    except Exception as exc:  # pragma: no cover - FastAPI validation guard
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

    action = str(body.pop("action", "")).strip()
    if not action:
        raise HTTPException(
            status_code=400, detail=f"action required. valid: {sorted(ALL_ACTIONS)}"
        )

    result = dispatch(action, body, token=x_control_token)
    status_code = 200 if result.get("status") != "error" else 400
    return JSONResponse(content=result, status_code=status_code)


@app.post("/telegram/webhook")
async def telegram_webhook(_request: Request):
    return {
        "status": "REFUSED_TELEGRAM_HAS_NO_AUTHORITY",
        "authority": "NONE",
        "mutation_allowed": False,
    }
