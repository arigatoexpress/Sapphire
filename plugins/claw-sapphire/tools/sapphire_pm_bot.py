#!/usr/bin/env python3
"""Telegram-first Sapphire PM bot tool.

Phase 1 scope (preserved):
- fail-closed Telegram allowlist
- /help
- /status
- /pm list [--project <id>]
- /pm new <title>
- /rag <query>
- /claw <prompt> (stub)

Phase 2 (Wave 4 hardening — operator console):
- per-user rate limiting (≤10/min, ≤60/h) via shared safety module
- secret-denylist regex strips api_key/token/password/bearer from outgoing text
- forbidden-command guard rejects /trade /buy /sell /transfer /withdraw
  /rotate-key /launch /exec /eval /sudo /shell etc. with a generic refusal
- LIVE_TRADING_DISABLED_FROM_TELEGRAM tripwire asserted on every dispatch
- /health, /services, /routines list|pause|resume, /digest morning|dev,
  /cancel-routine, /whoami — all read-only or strictly bounded with
  CONFIRM-token gate on dangerous reversibles

Every command path passes through ``handle_telegram_command`` →
allowlist → forbidden-command guard → rate-limit → dispatcher. The
existing five commands continue to take the dispatcher branch they
always did; the new commands sit alongside them.
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
from internal import _telegram_safety as safety

logger = logging.getLogger(__name__)

# Re-export tripwire so callers / tests can read the canonical value.
LIVE_TRADING_DISABLED_FROM_TELEGRAM = safety.LIVE_TRADING_DISABLED_FROM_TELEGRAM

# Per-process shared rate limiter. The bot runs as a single LaunchAgent so
# in-process state is the right fit. If we ever shard, this becomes a
# Redis ZSET (see safety.RateLimiter docstring).
_RATE_LIMITER = safety.RateLimiter()

# Pause-flag directory for /routines pause|resume + /cancel-routine.
# Scheduled tasks read these flags at startup and skip if present.
_ROUTINE_PAUSE_DIR = Path.home() / ".sapphire" / "routine_pause"
_SCHEDULED_TASKS_DIR = Path.home() / ".claude" / "scheduled-tasks"
_MORNING_DIGEST_LOG = (
    Path.home()
    / "Code"
    / "Sapphire"
    / "data"
    / "morning_digest"
)

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
    "• /health\n"
    "• /services\n"
    "• /dev pulse\n"
    "• /svc status\n"
    "• /pm list [--project <id>]\n"
    "• /pm new <title>\n"
    "• /rag <query>\n"
    "• /claw <prompt>\n"
    "• /routines list\n"
    "• /routines pause <name>\n"
    "• /routines resume <name> CONFIRM\n"
    "• /digest morning\n"
    "• /digest dev\n"
    "• /cancel-routine <name> CONFIRM\n"
    "• /whoami"
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
THO_API_KEY_PATHS = (
    Path.home() / ".config" / "sapphire-secrets" / "tho_api_key",
    Path.home() / ".config" / "sapphire" / "tho_api_key",
)
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
    """Build a Telegram response dict.

    Every outgoing payload runs through ``safety.redact_secrets`` so a
    misconfigured upstream tool that prints an API key into a status
    string cannot leak it via Telegram. The redactor is line-based so
    a single offending line does not blank an entire status report.
    """
    redacted = safety.redact_secrets(text)
    return {"text": redacted, "parse_mode": parse_mode}


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
    """Backward-compatible wrapper around :func:`safety.load_allowed_user_ids`.

    Existing tests import this name; preserve it. The implementation now
    delegates to the shared safety module so policy lives in one place.
    """
    return safety.load_allowed_user_ids("SAPPHIRE_PM_BOT_ALLOWED_USER_IDS")


def _ensure_allowed(update: dict[str, Any]) -> dict[str, Any] | None:
    """Reject senders who are not on the fail-closed allowlist.

    Returns the generic refusal response when denied, or ``None`` when the
    sender is permitted. The wording is identical to the rate-limit and
    forbidden-command refusals — by design, the operator console never
    tells a probe *why* it was rejected, only that it was.
    """
    sender_id = _sender_id(update)
    allowed = _allowed_user_ids()
    if safety.is_allowed(sender_id, allowed):
        return None
    logger.warning("Denied Telegram PM bot request from user_id=%s", sender_id)
    return _response(safety.GENERIC_REFUSAL_TEXT, None)


def _ensure_not_forbidden(text: str) -> dict[str, Any] | None:
    """Reject any forbidden top-level command before dispatch.

    The denylist (``FORBIDDEN_COMMAND_RE`` in the safety module) catches
    ``/trade``, ``/buy``, ``/sell``, ``/transfer``, ``/withdraw``,
    ``/rotate-key``, ``/launch``, ``/exec``, ``/eval``, ``/sudo``,
    ``/shell``, etc. The check fires *after* allowlist + *before* the
    dispatcher, so an allowed user attempting a forbidden command still
    gets a refusal — and the dispatcher never sees the input. This keeps
    policy in source rather than configuration.
    """
    if not safety.is_forbidden_command(text):
        return None
    logger.warning("Rejected forbidden Telegram command attempt: %r", text[:80])
    return _response(safety.OPERATOR_ONLY_PHYSICAL_ACTION_TEXT, None)


def _ensure_within_rate_limit(update: dict[str, Any]) -> dict[str, Any] | None:
    """Apply the per-user sliding-window rate limit.

    Returns the generic refusal when over the cap. The decision's
    ``retry_after_seconds`` is logged for diagnostics but deliberately not
    echoed — telling an attacker the exact reset time helps them pace.
    """
    sender_id = _sender_id(update)
    if sender_id is None:
        # Unknown sender — let allowlist handle it (it will deny).
        return None
    decision = _RATE_LIMITER.check(sender_id)
    if decision.allowed:
        return None
    logger.warning(
        "Rate-limited Telegram user_id=%s reason=%s retry_after=%.1fs",
        sender_id,
        decision.reason,
        decision.retry_after_seconds,
    )
    return _response(safety.GENERIC_REFUSAL_TEXT, None)


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


def _read_secret_file(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def _resolve_tho_api_key() -> str:
    env_key = str(os.getenv("THO_API_KEY", "")).strip()
    if env_key:
        return env_key

    explicit_path = str(os.getenv("THO_API_KEY_FILE", "")).strip()
    if explicit_path:
        return _read_secret_file(Path(explicit_path).expanduser())

    for path in THO_API_KEY_PATHS:
        value = _read_secret_file(path)
        if value:
            return value

    return ""


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
    active_projects = [
        p for p in projects if str(p.get("status", "active")).strip().lower() != "archived"
    ]

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
            lines.append(f"• {title} ({task_id}) | {priority}{project_suffix}")

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

    api_key = _resolve_tho_api_key()
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


def _format_service_supervisor_markdown_v2(result: dict[str, Any]) -> str:
    lines = [
        "svc status (dry run)",
        f"ok: {bool(result.get('ok'))}",
    ]
    for key in ("attempted", "recovered", "failed", "skipped_cooldown"):
        items = result.get(key) or []
        lines.append(f"{key}: {len(items)}")
        for item in items[:8]:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "unknown")
            reason = str(item.get("reason") or item.get("skip_reason") or "n/a")
            action = str(item.get("restart_action") or item.get("skip_reason") or "n/a")
            exit_code = item.get("exit_code_before")
            suffix = f" exit={exit_code}" if exit_code is not None else ""
            lines.append(f"• {label} | {action} | {reason}{suffix}")
    errors = result.get("errors") or []
    if errors:
        lines.append(f"errors: {len(errors)}")
        for error in errors[:5]:
            lines.append(f"• {str(error)[:200]}")
    return "\n".join(escape_markdown_v2(line) for line in lines)


def _handle_svc_status() -> dict[str, Any]:
    """Dry-run LaunchAgent self-healing preview."""
    try:
        import service_supervisor  # type: ignore
    except Exception as e:
        return _response(
            escape_markdown_v2(f"service_supervisor unavailable: {type(e).__name__}"),
            "MarkdownV2",
        )
    try:
        result = service_supervisor.supervise_once(dry_run=True)
    except Exception as e:
        return _response(
            escape_markdown_v2(f"service_supervisor failed: {type(e).__name__}: {e}")[:3500],
            "MarkdownV2",
        )
    return _response(_format_service_supervisor_markdown_v2(result), "MarkdownV2")


# ---------------------------------------------------------------------------
# Wave 4 hardening — operator console additions.
# All commands below are read-only or strictly bounded. Dangerous reversibles
# (resume, cancel-routine) require the literal CONFIRM token.
# ---------------------------------------------------------------------------


def _handle_health() -> dict[str, Any]:
    """Single-line health summary from the ``health_check`` tool.

    Read-only, paste-safe. Output passes through the secret-redactor like
    every other response. We deliberately call ``check_services`` /
    ``check_inference`` directly with the ``brief`` profile rather than
    invoking the CLI: the brief profile finishes in ~3 s and skips the
    deep THO PIN probe (no secret in scope).
    """
    safety.assert_no_live_trading()
    try:
        import health_check  # type: ignore
    except Exception as e:
        return _response(
            escape_markdown_v2(f"health_check unavailable: {type(e).__name__}"),
            "MarkdownV2",
        )
    try:
        services = health_check.check_services(profile="brief")
        inference = health_check.check_inference(profile="brief")
    except Exception as e:
        return _response(
            escape_markdown_v2(f"health_check failed: {type(e).__name__}: {e}")[:1000],
            "MarkdownV2",
        )

    counts = {"green": 0, "yellow": 0, "red": 0, "unknown": 0}
    for section in (services, inference):
        for item in section.values():
            status = str(item.get("status") or "unknown")
            counts[status] = counts.get(status, 0) + 1

    if counts["red"] > 0:
        overall = "RED"
    elif counts["yellow"] > 0:
        overall = "YELLOW"
    else:
        overall = "GREEN"

    summary = (
        f"health: {overall} | green={counts['green']} "
        f"yellow={counts['yellow']} red={counts['red']}"
    )
    return _response(escape_markdown_v2(summary), "MarkdownV2")


def _format_services_table(services: dict[str, Any]) -> str:
    lines = ["LaunchAgent + service status"]
    for name in sorted(services.keys()):
        item = services[name]
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "unknown")
        detail = str(item.get("detail") or "")[:80]
        lines.append(f"• {name} | {status} | {detail}")
    return "\n".join(escape_markdown_v2(line) for line in lines)


def _handle_services() -> dict[str, Any]:
    """Read-only LaunchAgent + HTTP service status table."""
    safety.assert_no_live_trading()
    try:
        import health_check  # type: ignore
    except Exception as e:
        return _response(
            escape_markdown_v2(f"health_check unavailable: {type(e).__name__}"),
            "MarkdownV2",
        )
    try:
        services = health_check.check_services(profile="brief")
    except Exception as e:
        return _response(
            escape_markdown_v2(f"services check failed: {type(e).__name__}: {e}")[:1000],
            "MarkdownV2",
        )
    return _response(_format_services_table(services), "MarkdownV2")


def _list_scheduled_tasks() -> list[dict[str, Any]]:
    """Enumerate scheduled-task directories with last-modified hint."""
    if not _SCHEDULED_TASKS_DIR.exists():
        return []
    out: list[dict[str, Any]] = []
    for entry in sorted(_SCHEDULED_TASKS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name.startswith("_") or entry.name.startswith("."):
            continue
        skill = entry / "SKILL.md"
        try:
            mtime = skill.stat().st_mtime if skill.exists() else entry.stat().st_mtime
            last_modified = datetime.fromtimestamp(mtime, tz=UTC).isoformat(timespec="minutes")
        except OSError:
            last_modified = "?"
        paused = (_ROUTINE_PAUSE_DIR / entry.name).exists()
        out.append(
            {
                "name": entry.name,
                "last_modified": last_modified,
                "paused": paused,
            }
        )
    return out


def _handle_routines_list() -> dict[str, Any]:
    safety.assert_no_live_trading()
    try:
        items = _list_scheduled_tasks()
    except Exception as e:
        return _response(
            escape_markdown_v2(f"routines list failed: {type(e).__name__}: {e}")[:500],
            "MarkdownV2",
        )
    if not items:
        return _response(
            escape_markdown_v2("No scheduled tasks found."), "MarkdownV2"
        )
    lines = [f"Scheduled tasks ({len(items)})"]
    for item in items:
        flag = " [PAUSED]" if item["paused"] else ""
        lines.append(f"• {item['name']} | last_mtime={item['last_modified']}{flag}")
    return _response(
        "\n".join(escape_markdown_v2(line) for line in lines), "MarkdownV2"
    )


def _routine_pause_path(name: str) -> Path:
    return _ROUTINE_PAUSE_DIR / name


def _handle_routines_pause(text: str) -> dict[str, Any]:
    """Set a pause flag for a scheduled task. Reversible via /routines resume.

    Pause is *immediately effective* on the next scheduled-task startup —
    tasks check ``~/.sapphire/routine_pause/<name>`` at startup and skip if
    present. Existing in-flight runs are not interrupted; supervisor
    cooldown applies. This is the safe default: pausing should never need
    a CONFIRM token (it does no harm).
    """
    safety.assert_no_live_trading()
    match = re.match(r"^/routines\s+pause\s+(\S+)\s*$", text, re.IGNORECASE)
    if not match:
        return _response("Usage: /routines pause <name>", None)
    name = match.group(1).strip()
    if not safety.is_valid_routine_name(name):
        return _response(safety.GENERIC_REFUSAL_TEXT, None)

    available = {item["name"] for item in _list_scheduled_tasks()}
    if name not in available:
        return _response(
            escape_markdown_v2(f"Unknown routine: {name}"), "MarkdownV2"
        )

    try:
        _ROUTINE_PAUSE_DIR.mkdir(parents=True, exist_ok=True)
        flag = _routine_pause_path(name)
        flag.write_text(_now_utc().isoformat() + "\n")
    except OSError as e:
        return _response(
            escape_markdown_v2(f"Failed to pause: {type(e).__name__}")[:200],
            "MarkdownV2",
        )

    return _response(
        escape_markdown_v2(f"Paused routine: {name}. Use /routines resume {name} CONFIRM to re-enable."),
        "MarkdownV2",
    )


def _handle_routines_resume(text: str) -> dict[str, Any]:
    """Remove a routine pause flag. Requires CONFIRM token.

    Resume is *destructive of the pause state* — it re-enables a routine
    that the operator deliberately paused. We require the operator to
    re-state intent with the literal ``CONFIRM`` suffix to prevent fat-
    finger reactivation of a routine that was paused for a reason.
    """
    safety.assert_no_live_trading()
    match = re.match(
        r"^/routines\s+resume\s+(\S+)(?:\s+(\S+))?\s*$", text, re.IGNORECASE
    )
    if not match:
        return _response("Usage: /routines resume <name> CONFIRM", None)
    name = match.group(1).strip()
    confirm = (match.group(2) or "").strip()
    if not safety.is_valid_routine_name(name):
        return _response(safety.GENERIC_REFUSAL_TEXT, None)
    if confirm != safety.CONFIRM_TOKEN:
        return _response(
            escape_markdown_v2(
                f"Confirmation required. Re-send: /routines resume {name} CONFIRM"
            ),
            "MarkdownV2",
        )
    flag = _routine_pause_path(name)
    if not flag.exists():
        return _response(
            escape_markdown_v2(f"No pause flag set for: {name}"), "MarkdownV2"
        )
    try:
        flag.unlink()
    except OSError as e:
        return _response(
            escape_markdown_v2(f"Failed to resume: {type(e).__name__}")[:200],
            "MarkdownV2",
        )
    return _response(
        escape_markdown_v2(f"Resumed routine: {name}."), "MarkdownV2"
    )


def _handle_cancel_routine(text: str) -> dict[str, Any]:
    """Pause a routine in-flight. Same flag mechanism; CONFIRM required.

    Differs from ``/routines pause`` in that it is the *explicit dangerous
    action* form — the wording in the help text and runbook is
    deliberately stronger, and we never make this the easy path. The
    underlying flag-file mechanism is identical, so recovery is
    symmetric: ``/routines resume <name> CONFIRM`` reverses it.
    """
    safety.assert_no_live_trading()
    match = re.match(
        r"^/cancel-routine\s+(\S+)(?:\s+(\S+))?\s*$", text, re.IGNORECASE
    )
    if not match:
        return _response("Usage: /cancel-routine <name> CONFIRM", None)
    name = match.group(1).strip()
    confirm = (match.group(2) or "").strip()
    if not safety.is_valid_routine_name(name):
        return _response(safety.GENERIC_REFUSAL_TEXT, None)
    if confirm != safety.CONFIRM_TOKEN:
        return _response(
            escape_markdown_v2(
                f"Confirmation required. Re-send: /cancel-routine {name} CONFIRM"
            ),
            "MarkdownV2",
        )

    available = {item["name"] for item in _list_scheduled_tasks()}
    if name not in available:
        return _response(
            escape_markdown_v2(f"Unknown routine: {name}"), "MarkdownV2"
        )
    try:
        _ROUTINE_PAUSE_DIR.mkdir(parents=True, exist_ok=True)
        flag = _routine_pause_path(name)
        flag.write_text(_now_utc().isoformat() + "\n")
    except OSError as e:
        return _response(
            escape_markdown_v2(f"Failed to cancel: {type(e).__name__}")[:200],
            "MarkdownV2",
        )
    return _response(
        escape_markdown_v2(
            f"Cancelled routine: {name}. Reverse with /routines resume {name} CONFIRM."
        ),
        "MarkdownV2",
    )


def _handle_digest_morning() -> dict[str, Any]:
    """Render today's morning digest if it has run.

    The morning_digest tool persists its rendered MarkdownV2 to
    ``data/morning_digest/<YYYY-MM-DD>.md`` (when the LaunchAgent runs
    with ``--archive``). We read that file directly when present rather
    than re-running the digest from Telegram — the digest is allowed to
    take 30+ s and we do not want to block the bot or re-bill external
    APIs on operator demand. If today's file is missing, we explain why.
    """
    safety.assert_no_live_trading()
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    candidate = _MORNING_DIGEST_LOG / f"{today}.md"
    if candidate.exists():
        try:
            content = candidate.read_text()[:3500]
            return _response(content, "MarkdownV2")
        except OSError as e:
            return _response(
                escape_markdown_v2(f"Failed to read digest: {type(e).__name__}")[:200],
                "MarkdownV2",
            )
    return _response(
        escape_markdown_v2(
            f"No morning digest found for {today}. The 8 AM digest "
            "may not have run yet, or archiving is off."
        ),
        "MarkdownV2",
    )


def _handle_digest_dev() -> dict[str, Any]:
    """Render the latest dev_pulse summary (live, lazy import)."""
    safety.assert_no_live_trading()
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


def _handle_whoami(update: dict[str, Any]) -> dict[str, Any]:
    """Echo back the requesting Telegram chat_id and user_id.

    Useful for debugging the allowlist (operator can see what user_id to
    add to ``SAPPHIRE_PM_BOT_ALLOWED_USER_IDS``). Safe — there are no
    secrets, no environment leak, no sender enumeration."""
    safety.assert_no_live_trading()
    sender_id = _sender_id(update)
    username = _sender_username(update)
    message = _message_from_update(update)
    chat = message.get("chat") if isinstance(message, dict) else {}
    chat_id = chat.get("id") if isinstance(chat, dict) else None
    lines = [
        "whoami",
        f"user_id: {sender_id if sender_id is not None else 'unknown'}",
        f"username: {username}",
        f"chat_id: {chat_id if chat_id is not None else 'unknown'}",
    ]
    return _response(
        "\n".join(escape_markdown_v2(line) for line in lines), "MarkdownV2"
    )


def _dispatch(text: str, update: dict[str, Any]) -> dict[str, Any]:
    """Pure command-dispatch table. Allowlist + safety guards are upstream.

    Extracted from ``handle_telegram_command`` so the two responsibilities
    (gates vs routing) remain testable in isolation. New commands must
    not bypass the gates; if you find yourself adding a branch here that
    is sensitive, also extend the forbidden-command list in
    ``_telegram_safety``.
    """
    if text in {"/help", "/start"}:
        return _handle_help()
    if text == "/status":
        return _format_status_report()
    if text == "/health":
        return _handle_health()
    if text == "/services":
        return _handle_services()
    if text in {"/dev", "/dev pulse", "/pulse"}:
        return _handle_dev_pulse()
    if text == "/svc status":
        return _handle_svc_status()
    if text == "/whoami":
        return _handle_whoami(update)
    if text == "/routines list":
        return _handle_routines_list()
    if text.startswith("/routines pause"):
        return _handle_routines_pause(text)
    if text.startswith("/routines resume"):
        return _handle_routines_resume(text)
    if text.startswith("/cancel-routine"):
        return _handle_cancel_routine(text)
    if text == "/digest morning":
        return _handle_digest_morning()
    if text == "/digest dev":
        return _handle_digest_dev()
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


def handle_telegram_command(update: dict[str, Any]) -> dict[str, Any]:
    """Route a normalized Telegram update into a formatted bot response.

    Order is load-bearing:
    1. Live-trading tripwire (assert_no_live_trading).
    2. Allowlist (fail-closed, generic refusal on miss).
    3. Forbidden-command guard (rejects /trade, /buy, /sell, etc. with
       a generic refusal; identical wording to allowlist denial so a
       probe cannot tell which gate fired).
    4. Per-user rate limit (10/min, 60/h sliding window).
    5. Dispatch to the per-command handler.

    Every step short-circuits on refusal. The handler return value is
    re-redacted by ``_response`` so even if a downstream tool prints a
    secret, the operator never sees it.
    """
    safety.assert_no_live_trading()

    refusal = _ensure_allowed(update)
    if refusal is not None:
        return refusal

    text = _message_text(update)

    refusal = _ensure_not_forbidden(text)
    if refusal is not None:
        return refusal

    refusal = _ensure_within_rate_limit(update)
    if refusal is not None:
        return refusal

    return _dispatch(text, update)


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        print(json.dumps({"error": "Input must be JSON"}))
        raise SystemExit(1)
    print(json.dumps(handle_telegram_command(payload), indent=2, default=str))


if __name__ == "__main__":
    main()
