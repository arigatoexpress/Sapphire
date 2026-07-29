"""Kimi-Claw PM bridge — authenticated endpoint for local agents.

Provides POST /api/kimi/pm so Kimi agents on rari1 (or cloud) can orchestrate the
control plane: create tasks, sync boards, query state, run autonomy cycles.

Authentication: X-Control-Token header (matches CONTROL_PLANE_TOKEN env var).

Usage from Kimi agent:
    POST /api/kimi/pm
    X-Control-Token: <token>
    {"action": "create_task", "title": "...", "project": "sapphire", "priority": "high"}
"""

from __future__ import annotations

import logging
import os
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

CONTROL_TOKEN = os.getenv("CONTROL_PLANE_TOKEN", "").strip()

# Actions that don't mutate state — can be called without extra auth
READ_ACTIONS = {
    "overview",
    "list_tasks",
    "list_agents",
    "get_task",
    "list_events",
    "control_overview",
}

# Actions that mutate state — require valid control token
WRITE_ACTIONS = {
    "create_task",
    "update_task",
    "create_card",
    "update_card",
    "sync_board",
    "autonomy_cycle",
    "org_overview",
    "cleanup_stale_agents",
    "set_executor_policy",
}

ALL_ACTIONS = READ_ACTIONS | WRITE_ACTIONS


def verify_token(token: str) -> bool:
    """Return True if the provided token matches the control plane token."""
    if not CONTROL_TOKEN:
        logger.warning("CONTROL_PLANE_TOKEN not set — all requests denied")
        return False
    return token == CONTROL_TOKEN


def dispatch(
    action: str,
    payload: dict[str, Any],
    *,
    token: str = "",
) -> dict[str, Any]:
    """Dispatch a Kimi PM bridge action.

    Args:
        action: Action name from ALL_ACTIONS.
        payload: Action-specific parameters.
        token: Control plane auth token.

    Returns:
        Result dict with at minimum {"status": "ok"|"error"}.
    """
    if action not in ALL_ACTIONS:
        return {
            "status": "error",
            "error": f"unknown action: {action}",
            "valid_actions": sorted(ALL_ACTIONS),
        }

    if action in WRITE_ACTIONS and not verify_token(token):
        return {"status": "error", "error": "unauthorized — provide valid X-Control-Token"}

    try:
        handler = _HANDLERS.get(action)
        if handler is None:
            return {"status": "error", "error": f"handler not implemented: {action}"}
        return handler(payload)
    except Exception as exc:
        logger.exception("kimi_bridge dispatch error action=%s", action)
        return {"status": "error", "error": str(exc), "action": action}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _overview(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a high-level system overview."""
    try:
        from .project_board import get_projects_overview

        return {"status": "ok", "overview": get_projects_overview()}
    except Exception as exc:
        logger.warning("project_board overview error: %s", exc)
        return {"status": "ok", "overview": {"message": "overview unavailable", "error": str(exc)}}


def _list_tasks(payload: dict[str, Any]) -> dict[str, Any]:
    from .event_stream import recent_events

    limit = int(payload.get("limit", 20))
    events = recent_events(tags=["type:pm"], limit=limit)
    return {"status": "ok", "tasks": events, "count": len(events)}


def _create_task(payload: dict[str, Any]) -> dict[str, Any]:
    import uuid

    from .event_stream import append_event

    title = str(payload.get("title", "")).strip()
    if not title:
        return {"status": "error", "error": "title required"}
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    append_event(
        "task.created",
        source="kimi-bridge",
        actor=str(payload.get("actor", "kimi")),
        project_id=str(payload.get("project", "sapphire")),
        task_id=task_id,
        message=title,
        tags=["type:pm", f"priority:{payload.get('priority', 'medium')}"],
        payload={"title": title, "description": str(payload.get("description", ""))},
    )
    return {"status": "ok", "task": {"task_id": task_id, "title": title}}


def _update_task(payload: dict[str, Any]) -> dict[str, Any]:
    from .event_stream import append_event

    task_id = str(payload.get("task_id", "")).strip()
    status = str(payload.get("status", "")).strip()
    if not task_id or not status:
        return {"status": "error", "error": "task_id and status required"}
    append_event(
        f"task.{status}",
        source="kimi-bridge",
        task_id=task_id,
        status=status,
        message=str(payload.get("result", "")),
        tags=["type:pm"],
    )
    return {"status": "ok", "task": {"task_id": task_id, "status": status}}


def _list_events(payload: dict[str, Any]) -> dict[str, Any]:
    from .event_stream import recent_events

    tags = payload.get("tags", [])
    limit = int(payload.get("limit", 30))
    events = recent_events(tags=tags or None, limit=limit)
    return {"status": "ok", "events": events, "count": len(events)}


def _list_agents(payload: dict[str, Any]) -> dict[str, Any]:
    agents = [
        {"agent_id": "kimi-main-rari1", "role": "controller", "host": "rari1", "status": "active"},
        {"agent_id": "kimi-slave-rari2", "role": "executor", "host": "rari2", "status": "active"},
    ]
    return {"status": "ok", "agents": agents, "count": len(agents)}


def _autonomy_cycle(payload: dict[str, Any]) -> dict[str, Any]:
    """Trigger a lightweight autonomy cycle — summarise state + emit recommendations."""
    from .event_stream import append_event

    append_event(
        "autonomy.cycle.requested",
        source="kimi-bridge",
        actor=str(payload.get("actor", "kimi")),
        message="Autonomy cycle triggered via Kimi PM bridge",
        tags=["agent:kimi", "type:pm", "priority:p2"],
    )
    _audit_autonomy_cycle_request(payload)
    return {"status": "ok", "message": "autonomy cycle queued"}


def _audit_autonomy_cycle_request(payload: dict[str, Any]) -> None:
    """Append a sanitized autonomy audit event for Kimi bridge requests."""
    try:
        audit_log_cls = _autonomy_audit_log_cls()
        actor = str(payload.get("actor") or "kimi")
        audit_log_cls().append(
            "autonomy.cycle.requested",
            actor="kimi_bridge",
            action="request_autonomy_cycle",
            outcome="queued",
            risk="autonomy_coordination",
            object_ref="control-plane:autonomy_cycle",
            metadata={
                "payload_keys": sorted(str(key) for key in payload),
                "requested_actor_hash": sha256(actor.encode("utf-8")).hexdigest()[:12],
                "requested_actor_chars": len(actor),
            },
        )
    except Exception as exc:
        logger.warning("autonomy cycle audit write failed: %s", exc)


def _autonomy_audit_log_cls() -> type:
    try:
        from lib.core.autonomy_audit import AutonomyAuditLog

        return AutonomyAuditLog
    except ModuleNotFoundError:
        repo_root = Path(__file__).resolve().parents[3]
        repo_root_text = str(repo_root)
        if repo_root_text not in sys.path:
            sys.path.insert(0, repo_root_text)
        from lib.core.autonomy_audit import AutonomyAuditLog

        return AutonomyAuditLog


def _sync_board(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        from .project_board import get_projects_overview

        return {"status": "ok", "board": get_projects_overview()}
    except Exception as exc:
        return {"status": "ok", "board": {"error": str(exc)}}


def _noop(payload: dict[str, Any]) -> dict[str, Any]:
    return {"status": "ok", "message": "not yet implemented"}


_HANDLERS: dict[str, Any] = {
    "overview": _overview,
    "control_overview": _overview,
    "list_tasks": _list_tasks,
    "list_agents": _list_agents,
    "get_task": _noop,
    "list_events": _list_events,
    "create_task": _create_task,
    "update_task": _update_task,
    "create_card": _noop,
    "update_card": _noop,
    "sync_board": _sync_board,
    "autonomy_cycle": _autonomy_cycle,
    "org_overview": _overview,
    "cleanup_stale_agents": _noop,
    "set_executor_policy": _noop,
}
