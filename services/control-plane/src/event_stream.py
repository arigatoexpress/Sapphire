from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

EVENT_SCHEMA_VERSION = 1
EVENT_SEVERITIES = {"debug", "info", "warning", "error", "critical"}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _event_file_path() -> Path:
    env_override = os.getenv("AGENTIC_SYSTEM_EVENTS_PATH", "").strip()
    if env_override:
        return Path(env_override)
    return Path(__file__).resolve().parent / "data" / "system_events.jsonl"


def append_event(
    event_type: str,
    *,
    source: str,
    actor: str = "",
    category: str = "system",
    severity: str = "info",
    project_id: str = "",
    task_id: str = "",
    card_id: str = "",
    repo: str = "",
    status: str = "",
    message: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    severity_value = str(severity or "info").strip().lower()
    if severity_value not in EVENT_SEVERITIES:
        severity_value = "info"

    row = {
        "schema_version": EVENT_SCHEMA_VERSION,
        "event_id": f"evt-{uuid4().hex[:16]}",
        "generated_at": _now_iso(),
        "event_type": str(event_type or "").strip().lower() or "unknown",
        "category": str(category or "").strip().lower() or "system",
        "severity": severity_value,
        "source": str(source or "").strip().lower() or "unknown",
        "actor": str(actor or "").strip(),
        "project_id": str(project_id or "").strip(),
        "task_id": str(task_id or "").strip(),
        "card_id": str(card_id or "").strip(),
        "repo": str(repo or "").strip(),
        "status": str(status or "").strip(),
        "message": str(message or "").strip(),
        "payload": payload if isinstance(payload, dict) else {},
    }

    path = _event_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":"), ensure_ascii=True, default=str))
        handle.write("\n")
    return row


def recent_events(
    *,
    limit: int = 50,
    category: str = "",
    source: str = "",
    severity: str = "",
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit), 500))
    path = _event_file_path()
    if not path.exists():
        return []

    category_filter = str(category or "").strip().lower()
    source_filter = str(source or "").strip().lower()
    severity_filter = str(severity or "").strip().lower()

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    rows: list[dict[str, Any]] = []
    for line in reversed(lines):
        text = line.strip()
        if not text:
            continue
        try:
            row = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        if category_filter and str(row.get("category") or "").lower() != category_filter:
            continue
        if source_filter and str(row.get("source") or "").lower() != source_filter:
            continue
        if severity_filter and str(row.get("severity") or "").lower() != severity_filter:
            continue
        rows.append(row)
        if len(rows) >= safe_limit:
            break
    return rows
