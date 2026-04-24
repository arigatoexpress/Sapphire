#!/usr/bin/env python3
"""Telegram-first Sapphire PM bot tool.

Phase 1 scope:
- fail-closed Telegram allowlist
- /help
- /status
- /pm list [--project <id>]
- /pm new <title>
- /rag <query>
- /claw <prompt> (stub)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests

try:
    from google.cloud import firestore  # type: ignore
except Exception:  # pragma: no cover
    firestore = None

import status as sapphire_status_tool

logger = logging.getLogger(__name__)

SAPPHIRE_ROOT = Path.home() / "Code" / "Sapphire"
THO_FIRESTORE_PROJECT = os.getenv("THO_FIRESTORE_PROJECT", "tho-ai-agent")
THO_BASE_URL = os.getenv(
    "THO_API_BASE_URL",
    "https://project-go-forward-trgi34bxuq-uc.a.run.app",
)
STATUS_HELP_TEXT = (
    "Available commands:\n"
    "• /help\n"
    "• /status\n"
    "• /dev pulse\n"
    "• /pm list [--project <id>]\n"
    "• /pm new <title>\n"
    "• /rag <query>\n"
    "• /claw <prompt>"
)
TASK_STATE_ORDER = ("todo", "in_progress", "in_review", "blocked")
PRIORITY_LABELS = {
    "no_priority": "no_priority",
    0: "no_priority",
    "0": "no_priority",
    1: "low",
    "1": "low",
    2: "medium",
    "2": "medium",
    3: "high",
    "3": "high",
    4: "urgent",
    "4": "urgent",
}
SAPPHIRE_PROJECT_NAMES = {
    "sapphire",
    "sapphire ai pm manager",
    "sapphire platform",
}
CRM_DEAL_URL_TEMPLATE = THO_BASE_URL.rstrip("/") + "/crm/deals/{deal_id}"
MDV2_ESCAPE_RE = re.compile(r"([_*\[\]()~`>#\+\-=|{}.!\\])")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"\b(?:\+?1[-.\s]*)?(?:\(?\d{3}\)?[-.\s]*)\d{3}[-.\s]*\d{4}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def escape_markdown_v2(text: str) -> str:
    """Escape Telegram MarkdownV2 special characters."""
    return MDV2_ESCAPE_RE.sub(r"\\\1", text)


def redact_pii(text: str) -> str:
    """Remove common PII patterns from user-visible text."""
    cleaned = EMAIL_RE.sub("[redacted email]", str(text or ""))
    cleaned = PHONE_RE.sub("[redacted phone]", cleaned)
    cleaned = SSN_RE.sub("[redacted ssn]", cleaned)
    return cleaned


def _response(text: str, parse_mode: str | None = None) -> dict[str, Any]:
    return {"text": text, "parse_mode": parse_mode}


def _now_utc() -> datetime:
    return datetime.now(tz=UTC)


def _message_from_update(update: dict[str, Any]) -> dict[str, Any]:
    message = update.get("message")
    if isinstance(message, dict):
        return message
    return update


def _sender_from_update(update: dict[str, Any]) -> dict[str, Any]:
    message = _message_from_update(update)
    sender = message.get("from")
    return sender if isinstance(sender, dict) else {}


def _sender_id(update: dict[str, Any]) -> int | None:
    value = _sender_from_update(update).get("id")
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sender_username(update: dict[str, Any]) -> str:
    sender = _sender_from_update(update)
    username = str(sender.get("username") or "").strip()
    if username:
        return username
    sender_id = _sender_id(update)
    if sender_id is not None:
        return f"telegram:{sender_id}"
    return "telegram:unknown"


def _message_text(update: dict[str, Any]) -> str:
    message = _message_from_update(update)
    text = message.get("text")
    return str(text or "").strip()


def _allowed_user_ids() -> set[int]:
    raw = os.getenv("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS", "")
    allowed: set[int] = set()
    for item in raw.split(","):
        text = item.strip()
        if not text:
            continue
        try:
            allowed.add(int(text))
        except ValueError:
            logger.warning("Ignoring invalid Telegram allowlist entry: %r", text)
    return allowed


def _ensure_allowed(update: dict[str, Any]) -> dict[str, Any] | None:
    sender_id = _sender_id(update)
    allowed = _allowed_user_ids()
    if sender_id is not None and sender_id in allowed:
        return None
    logger.warning("Denied Telegram PM bot request from user_id=%s", sender_id)
    return _response(
        "This Sapphire PM bot is not enabled for your Telegram user ID on this host.",
        None,
    )


def _parse_iso_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return datetime.min.replace(tzinfo=UTC)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    return datetime.min.replace(tzinfo=UTC)


def _priority_label(task: dict[str, Any]) -> str:
    explicit = task.get("priority_label") or task.get("priority_name")
    if explicit:
        return str(explicit)
    return PRIORITY_LABELS.get(task.get("priority"), str(task.get("priority") or "no_priority"))


def _preview(text: str, limit: int = 200) -> str:
    compact = re.sub(r"\s+", " ", redact_pii(text)).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _task_public_url(task: dict[str, Any]) -> str | None:
    related_deal_id = str(task.get("related_deal_id") or "").strip()
    if related_deal_id:
        return CRM_DEAL_URL_TEMPLATE.format(deal_id=related_deal_id)
    return None


def _get_firestore_client():
    if firestore is None:
        raise RuntimeError("google-cloud-firestore is not available")
    return firestore.Client(project=THO_FIRESTORE_PROJECT)


def _stream_docs(query: Any) -> list[Any]:
    stream = getattr(query, "stream", None)
    if callable(stream):
        return list(stream())
    return []


def _read_doc(doc: Any) -> dict[str, Any]:
    data = doc.to_dict() or {}
    if "id" not in data and getattr(doc, "id", None):
        data["id"] = str(doc.id)
    return data


def _resolve_default_project_id(db: Any) -> str:
    override = str(os.getenv("SAPPHIRE_PM_BOT_DEFAULT_PROJECT_ID", "")).strip()
    if override:
        return override

    projects = [_read_doc(doc) for doc in _stream_docs(db.collection("projects"))]
    active_projects = [p for p in projects if str(p.get("status", "active")).strip().lower() != "archived"]

    for project in active_projects:
        if str(project.get("github_repo") or "").strip().lower() == "arigatoexpress/sapphire":
            return str(project["id"])

    for project in active_projects:
        name = str(project.get("name") or "").strip().lower()
        if name in SAPPHIRE_PROJECT_NAMES:
            return str(project["id"])

    if len(active_projects) == 1:
        return str(active_projects[0]["id"])

    if active_projects:
        active_projects.sort(
            key=lambda item: (
                _parse_iso_dt(item.get("updated_at")),
                _parse_iso_dt(item.get("created_at")),
            ),
            reverse=True,
        )
        return str(active_projects[0]["id"])

    raise RuntimeError(
        "No PM project found in Firestore. Set SAPPHIRE_PM_BOT_DEFAULT_PROJECT_ID or create a project first."
    )


def _list_tasks(project_id: str | None = None) -> list[dict[str, Any]]:
    db = _get_firestore_client()
    query = db.collection("tasks")
    where = getattr(query, "where", None)
    if project_id and callable(where):
        query = where("project_id", "==", project_id)

    tasks = []
    for doc in _stream_docs(query):
        task = _read_doc(doc)
        state = str(task.get("state") or "").strip().lower()
        if state not in TASK_STATE_ORDER:
            continue
        if project_id and str(task.get("project_id") or "").strip() != project_id:
            continue
        tasks.append(task)

    tasks.sort(
        key=lambda item: (
            _parse_iso_dt(item.get("updated_at")),
            _parse_iso_dt(item.get("created_at")),
        ),
        reverse=True,
    )
    return tasks[:10]


def _create_task(title: str, creator: str) -> dict[str, Any]:
    db = _get_firestore_client()
    project_id = _resolve_default_project_id(db)
    task_id = str(uuid.uuid4())
    task = {
        "id": task_id,
        "title": title.strip(),
        "description": None,
        "project_id": project_id,
        "state": "todo",
        "priority": 0,
        "priority_label": "no_priority",
        "labels": [],
        "assignee": None,
        "creator": creator,
        "parent_task_id": None,
        "related_github_issue": None,
        "related_github_pr": None,
        "related_deal_id": None,
        "estimate_hours": None,
        "actual_hours": None,
        "due_date": None,
        "started_at": None,
        "completed_at": None,
        "state_history": [],
        "created_at": _now_utc(),
        "updated_at": _now_utc(),
    }
    db.collection("tasks").document(task_id).set(task)
    return task


def _fetch_tho_health() -> str:
    try:
        response = requests.get(f"{THO_BASE_URL.rstrip('/')}/health", timeout=10)
        return f"{response.status_code} {response.reason}"
    except requests.RequestException as exc:
        return f"unreachable ({exc})"


def _count_signals_today() -> int:
    today = datetime.now().strftime("%Y-%m-%d")
    signal_path = SAPPHIRE_ROOT / "data" / "signals" / f"{today}.jsonl"
    if not signal_path.exists():
        return 0
    try:
        with signal_path.open() as handle:
            return sum(1 for _ in handle)
    except OSError:
        return 0


def _format_proxy_health(raw: Any) -> str:
    if not isinstance(raw, dict) or not raw:
        return "unknown"
    parts: list[str] = []
    for name, payload in sorted(raw.items()):
        if isinstance(payload, dict):
            if "healthy" in payload:
                state = "up" if payload.get("healthy") else "down"
            elif "status" in payload:
                state = str(payload.get("status"))
            else:
                state = "ok"
        else:
            state = str(payload)
        parts.append(f"{name}={state}")
    return ", ".join(parts)


def _format_status_report() -> dict[str, Any]:
    try:
        raw_status = sapphire_status_tool.run()
        status_payload = json.loads(raw_status)
    except Exception as exc:
        logger.warning("sapphire_status failed: %s", exc)
        status_payload = {}

    devices = status_payload.get("devices", []) if isinstance(status_payload, dict) else []
    online_devices = [
        str(device.get("name") or "unknown")
        for device in devices
        if isinstance(device, dict) and device.get("online")
    ]
    offline_devices = [
        str(device.get("name") or "unknown")
        for device in devices
        if isinstance(device, dict) and not device.get("online")
    ]

    proxy_health = {}
    if isinstance(status_payload, dict):
        proxy_health = (
            status_payload.get("inference", {}).get("proxy_health", {})
            if isinstance(status_payload.get("inference"), dict)
            else {}
        )

    lines = [
        "Sapphire PM bot status",
        f"Mesh devices: {len(online_devices)}/{len(devices)} online",
        f"Online: {', '.join(online_devices) if online_devices else 'none'}",
        f"Offline: {', '.join(offline_devices) if offline_devices else 'none'}",
        f"Inference proxy: {_format_proxy_health(proxy_health)}",
        f"Paper-trading signals today: {_count_signals_today()}",
        f"THO prod health: {_fetch_tho_health()}",
    ]
    escaped = "\n".join(escape_markdown_v2(line) for line in lines)
    return _response(escaped, "MarkdownV2")


def _handle_help() -> dict[str, Any]:
    escaped = "\n".join(escape_markdown_v2(line) for line in STATUS_HELP_TEXT.splitlines())
    return _response(escaped, "MarkdownV2")


def _handle_pm_list(text: str) -> dict[str, Any]:
    project_id = None
    match = re.search(r"--project\s+([^\s]+)", text)
    if match:
        project_id = match.group(1).strip()

    try:
        tasks = _list_tasks(project_id=project_id)
    except Exception as exc:
        logger.exception("pm list failed")
        return _response(f"Task list unavailable: {exc}", None)

    if not tasks:
        suffix = f" for project {project_id}" if project_id else ""
        return _response(
            escape_markdown_v2(f"No open PM tasks found{suffix}."),
            "MarkdownV2",
        )

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        grouped[str(task.get("state") or "todo")].append(task)

    lines = [
        "Open PM tasks",
        f"Filter: {project_id}" if project_id else "Filter: all projects",
    ]
    for state in TASK_STATE_ORDER:
        bucket = grouped.get(state, [])
        if not bucket:
            continue
        lines.append(f"{state}:")
        for task in bucket:
            title = redact_pii(str(task.get("title") or "Untitled task"))
            task_id = str(task.get("id") or "unknown")
            priority = _priority_label(task)
            project_suffix = ""
            if not project_id:
                project_value = str(task.get("project_id") or "").strip()
                if project_value:
                    project_suffix = f" | project {project_value}"
            lines.append(
                f"• {title} ({task_id}) | {priority}{project_suffix}"
            )

    escaped = "\n".join(escape_markdown_v2(line) for line in lines)
    return _response(escaped, "MarkdownV2")


def _handle_pm_new(text: str, update: dict[str, Any]) -> dict[str, Any]:
    match = re.match(r"^/pm\s+new\s+(.+)$", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return _response("Usage: /pm new <title>", None)

    title = match.group(1).strip()
    if not title:
        return _response("Usage: /pm new <title>", None)

    try:
        task = _create_task(title, _sender_username(update))
    except Exception as exc:
        logger.exception("pm new failed")
        return _response(f"Task creation failed: {exc}", None)

    url = _task_public_url(task)
    lines = [
        "Created PM task",
        f"ID: {task['id']}",
        f"Title: {redact_pii(task['title'])}",
        f"State: {task['state']}",
        "Priority: no_priority",
        f"Project: {task['project_id']}",
    ]
    if url:
        lines.append(f'<a href="{url}">Open related CRM record</a>')
    return _response("<br/>".join(lines), "HTML")


def _rag_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("results", "matches", "documents", "sources", "chunks"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _rag_template(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return str(
        item.get("template")
        or item.get("template_name")
        or metadata.get("template")
        or metadata.get("template_name")
        or item.get("source")
        or "Unknown template"
    )


def _rag_page(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    return str(item.get("page") or metadata.get("page") or metadata.get("page_number") or "?")


def _rag_preview(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    text = (
        item.get("preview")
        or item.get("text")
        or item.get("excerpt")
        or item.get("content")
        or metadata.get("preview")
        or metadata.get("text")
        or ""
    )
    return _preview(str(text))


def _handle_rag(text: str) -> dict[str, Any]:
    match = re.match(r"^/rag\s+(.+)$", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return _response("Usage: /rag <query>", None)

    api_key = str(os.getenv("THO_API_KEY", "")).strip()
    if not api_key:
        return _response("THO API not configured on this host", None)

    query = match.group(1).strip()
    if not query:
        return _response("Usage: /rag <query>", None)

    try:
        response = requests.post(
            f"{THO_BASE_URL.rstrip('/')}/api/v1/rag/query",
            json={"query": query, "k": 5},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning("RAG request failed: %s", exc)
        return _response(f"RAG request failed: {exc}", None)
    except ValueError as exc:
        logger.warning("RAG response was not JSON: %s", exc)
        return _response("RAG request failed: invalid JSON response", None)

    results = _rag_results(payload)[:3]
    if not results:
        return _response(
            escape_markdown_v2("No RAG matches found."),
            "MarkdownV2",
        )

    lines = [f'RAG results for: "{query}"']
    for item in results:
        template_name = _rag_template(item)
        page = _rag_page(item)
        preview = _rag_preview(item)
        lines.append(f"• {template_name} | page {page} | {preview}")

    escaped = "\n".join(escape_markdown_v2(line) for line in lines)
    return _response(escaped, "MarkdownV2")


def _handle_claw(_text: str) -> dict[str, Any]:
    return _response("claw session not yet wired (phase 2)", None)


def _handle_dev_pulse() -> dict[str, Any]:
    """Cross-repo dev pulse via dev_pulse tool — imported lazily to keep
    sapphire_pm_bot importable without gh/gcloud/git installed in test envs.
    """
    try:
        import dev_pulse  # type: ignore
    except Exception as e:
        return _response(
            escape_markdown_v2(f"dev_pulse unavailable: {type(e).__name__}"),
            "MarkdownV2",
        )
    try:
        result = dev_pulse.pulse()
    except Exception as e:
        return _response(
            escape_markdown_v2(f"dev_pulse failed: {type(e).__name__}: {e}")[:3500],
            "MarkdownV2",
        )
    return _response(dev_pulse.format_markdown_v2(result), "MarkdownV2")


def handle_telegram_command(update: dict[str, Any]) -> dict[str, Any]:
    """Route a normalized Telegram update into a formatted bot response."""
    refusal = _ensure_allowed(update)
    if refusal is not None:
        return refusal

    text = _message_text(update)
    if text in {"/help", "/start"}:
        return _handle_help()
    if text == "/status":
        return _format_status_report()
    if text in {"/dev", "/dev pulse", "/pulse"}:
        return _handle_dev_pulse()
    if text.startswith("/pm list"):
        return _handle_pm_list(text)
    if text.startswith("/pm new"):
        return _handle_pm_new(text, update)
    if text.startswith("/rag"):
        return _handle_rag(text)
    if text.startswith("/claw"):
        return _handle_claw(text)
    return _response(
        escape_markdown_v2("Unrecognized input. Try /help."),
        "MarkdownV2",
    )


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        print(json.dumps({"error": "Input must be JSON"}))
        raise SystemExit(1)
    print(json.dumps(handle_telegram_command(payload), indent=2, default=str))


if __name__ == "__main__":
    main()
