from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

EVENT_SCHEMA_VERSION = 2
EVENT_SEVERITIES = {"debug", "info", "warning", "error", "critical"}

# Tag namespaces used across the data mesh
# Format: "namespace:value"  e.g. "project:sapphire", "agent:kimi", "priority:p0", "type:trading"
TAG_NAMESPACES = {"project", "agent", "priority", "type", "service", "device"}


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _event_file_path() -> Path:
    env_override = os.getenv("SAPPHIRE_EVENTS_PATH", "").strip()
    if env_override:
        return Path(env_override)
    return Path(__file__).resolve().parent / "data" / "system_events.jsonl"


def _normalize_tags(tags: list[str] | None) -> list[str]:
    """Validate and normalize tags into 'namespace:value' format."""
    if not tags:
        return []
    result = []
    for tag in tags:
        tag = str(tag).strip().lower()
        if ":" not in tag:
            continue  # skip malformed tags
        ns, _, val = tag.partition(":")
        if ns in TAG_NAMESPACES and val:
            result.append(f"{ns}:{val}")
    return sorted(set(result))


def _tags_match(event_tags: list[str], filter_tags: list[str]) -> bool:
    """Return True if event contains ALL filter_tags (AND semantics)."""
    return all(t in event_tags for t in filter_tags)


def append_event(
    event_type: str,
    *,
    source: str,
    actor: str = "",
    category: str = "system",
    severity: str = "info",
    project_id: str = "",
    task_id: str = "",
    repo: str = "",
    status: str = "",
    message: str = "",
    tags: list[str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a tagged event to the event log.

    Tags follow 'namespace:value' format. Supported namespaces:
        project:  project slug (e.g. project:sapphire, project:blanga)
        agent:    agent name   (e.g. agent:kimi, agent:claude, agent:nemoclaw)
        priority: p0–p3        (e.g. priority:p0)
        type:     domain       (e.g. type:trading, type:pm, type:deploy)
        service:  service name (e.g. service:lighter, service:control-plane)
        device:   device name  (e.g. device:rari2, device:mac)
    """
    severity_value = str(severity or "info").strip().lower()
    if severity_value not in EVENT_SEVERITIES:
        severity_value = "info"

    # Auto-derive tags from structured fields if not explicitly tagged
    auto_tags: list[str] = []
    if project_id:
        auto_tags.append(f"project:{project_id.lower()}")
    explicit_tags = _normalize_tags(tags)
    all_tags = _normalize_tags(auto_tags + explicit_tags)

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
        "repo": str(repo or "").strip(),
        "status": str(status or "").strip(),
        "message": str(message or "").strip(),
        "tags": all_tags,
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
    tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Read recent events from the log with optional filtering.

    Args:
        limit: Max events to return (1–500).
        category: Filter by category (exact match).
        source: Filter by source (exact match).
        severity: Filter by severity level (exact match).
        tags: Filter by tags — returns events that match ALL provided tags.
              Example: tags=["project:sapphire", "type:trading"]
    """
    safe_limit = max(1, min(int(limit), 500))
    path = _event_file_path()
    if not path.exists():
        return []

    category_filter = str(category or "").strip().lower()
    source_filter = str(source or "").strip().lower()
    severity_filter = str(severity or "").strip().lower()
    tag_filter = _normalize_tags(tags)

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
        if tag_filter and not _tags_match(row.get("tags") or [], tag_filter):
            continue
        rows.append(row)
        if len(rows) >= safe_limit:
            break
    return rows


def events_by_tags(
    tags: list[str],
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Convenience wrapper: filter events by tags only.

    Example:
        events_by_tags(["agent:kimi", "type:trading"], limit=20)
    """
    return recent_events(tags=tags, limit=limit)
