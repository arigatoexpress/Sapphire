from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.control_plane_backend import build_control_plane_backend_adapter
from app.runtime_policy import (
    allowed_executor_agent_ids,
    allowed_executor_membership_ids,
    load_runtime_policy,
)

TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled", "blocked_review"}
_QUOTA_EXHAUSTION_PATTERNS = (
    "out of credits",
    "credits ran out",
    "credit limit",
    "quota exhausted",
    "quota exceeded",
    "insufficient_quota",
    "token limit",
    "token budget",
    "too many requests",
    "rate limit",
    "429",
)
_SINGLE_AGENT_TRUE_VALUES = {"1", "true", "yes", "on"}
_SINGLE_AGENT_RESEARCH_TOOL_CAPS = {"web-access", "tool:tavily-search", "tool:summarize"}
_DEADLOCK_ERROR_CODES = {"deadlock", "stuck", "blocked", "architecture_blocked", "no_progress"}
_WATCHDOG_FAILOVER_GRACE_SECONDS = 3600
_WATCHDOG_STALE_LEASE_SECONDS = 6 * 3600
_LOW_SIGNAL_TRUE_VALUES = {"1", "true", "yes", "on"}
_LOW_SIGNAL_CANCEL_PATTERNS = (
    "smoke",
    "probe",
    "sanity check",
    "routing demo",
)
_LOW_SIGNAL_TASK_CLASSES = {"smoke_probe", "test", "low_signal", "diagnostic"}
_PRODUCTION_TASK_CLASS = "production"
_TASK_CONTRACT_VERSION = "v1"
_DEADLOCK_PATTERNS = (
    "deadlock",
    "stuck",
    "blocked",
    "cannot progress",
    "no progress",
    "needs architecture",
    "needs architectural",
)
_MEMBERSHIP_QUEUE_RECOVERY_TITLE_PATTERNS = (
    "fix membership routing queue blockage",
    "membership routing queue blockage",
)
_BLOCKED_MEMBERSHIP_IN_TITLE_RE = re.compile(r"\bblocked\b[^a-z0-9]+([a-z0-9_-]+)", re.IGNORECASE)
_MEMBERSHIP_IN_TEXT_RE = re.compile(r"\bmembership[:=]\s*([a-z0-9_-]+)", re.IGNORECASE)
_CONTROL_PLANE_STORE_BACKEND_SUPPORTED = {"sqlite"}


def _utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _utc_iso_now() -> str:
    return _utc_now().isoformat()


def _utc_epoch_now() -> int:
    return int(_utc_now().timestamp())


def _parse_iso_datetime(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _single_agent_mode_enabled() -> bool:
    text = str(os.getenv("AGENTIC_SINGLE_AGENT_MODE") or "").strip().lower()
    return text in _SINGLE_AGENT_TRUE_VALUES


def _single_agent_membership_id() -> str:
    return str(os.getenv("AGENTIC_SINGLE_AGENT_MEMBERSHIP") or "").strip().lower()


def _single_agent_capability_profile() -> list[str]:
    caps = ["python", "git", "repo-write"]
    membership_id = _single_agent_membership_id()
    if membership_id:
        caps.insert(0, f"membership:{membership_id}")
    return _normalize_capabilities(caps)


def _low_signal_autocancel_enabled() -> bool:
    text = str(os.getenv("AGENTIC_LOW_SIGNAL_AUTOCANCEL_ENABLED") or "true").strip().lower()
    return text in _LOW_SIGNAL_TRUE_VALUES


def _low_signal_cancel_age_seconds() -> int:
    raw = str(os.getenv("AGENTIC_LOW_SIGNAL_CANCEL_AGE_SECONDS") or "").strip()
    try:
        seconds = int(raw)
    except ValueError:
        seconds = 45 * 60
    return max(300, min(seconds, 7 * 24 * 3600))


def _low_signal_cancel_limit() -> int:
    raw = str(os.getenv("AGENTIC_LOW_SIGNAL_CANCEL_LIMIT") or "").strip()
    try:
        limit = int(raw)
    except ValueError:
        limit = 10
    return max(1, min(limit, 100))


def _low_signal_title_fallback_enabled() -> bool:
    text = str(os.getenv("AGENTIC_LOW_SIGNAL_TITLE_FALLBACK") or "false").strip().lower()
    return text in _LOW_SIGNAL_TRUE_VALUES


def _dead_letter_enabled() -> bool:
    text = str(os.getenv("AGENTIC_DEAD_LETTER_ENABLED") or "true").strip().lower()
    return text in _LOW_SIGNAL_TRUE_VALUES


def _slo_window_seconds() -> int:
    raw = str(os.getenv("AGENTIC_SLO_WINDOW_SECONDS") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 6 * 3600
    return max(15 * 60, min(value, 7 * 24 * 3600))


def _slo_queue_drain_threshold_seconds() -> int:
    raw = str(os.getenv("AGENTIC_SLO_QUEUE_DRAIN_SECONDS_MAX") or "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = 45 * 60
    return max(5 * 60, min(value, 7 * 24 * 3600))


def _slo_stale_lease_rate_threshold() -> float:
    raw = str(os.getenv("AGENTIC_SLO_STALE_LEASE_RATE_MAX") or "").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 0.1
    return max(0.0, min(value, 1.0))


def _slo_autocancel_rate_threshold() -> float:
    raw = str(os.getenv("AGENTIC_SLO_AUTOCANCEL_RATE_MAX") or "").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 0.35
    return max(0.0, min(value, 1.0))


def _task_contract_kind(task_type: str) -> str:
    normalized = str(task_type or "").strip().lower()
    if normalized in {"trading", "trading_operation"}:
        return "trading"
    if normalized in {"research"}:
        return "research"
    if normalized in {"deploy", "deployment", "operations", "infrastructure", "infra"}:
        return "deploy"
    return "coding"


def _default_task_contract(*, kind: str, title: str, task_type: str) -> dict[str, Any]:
    normalized_kind = str(kind or "coding").strip().lower() or "coding"
    normalized_type = str(task_type or "").strip().lower()
    base = {
        "version": _TASK_CONTRACT_VERSION,
        "kind": normalized_kind,
        "task_type": normalized_type,
        "objective": str(title or "").strip(),
        "inputs": [],
        "steps": [],
        "success_criteria": [],
        "validation": [],
        "artifacts": [],
        "rollback": [],
    }
    if normalized_kind == "trading":
        base["inputs"] = ["venue", "action", "symbol(optional)", "size(optional)"]
        base["steps"] = [
            "preflight.gateway_status",
            "preflight.risk_check",
            "execute_or_dry_run",
            "record_result",
        ]
        base["success_criteria"] = [
            "risk checks pass",
            "venue response captured",
            "result persisted to control plane",
        ]
        base["validation"] = [
            "payload.trading.action present",
            "gateway reachable",
            "no auth errors",
        ]
        base["artifacts"] = ["task.result", "execution log excerpt"]
        base["rollback"] = ["cancel open orders if any", "revert policy changes if applied"]
    elif normalized_kind == "deploy":
        base["inputs"] = ["service/repo", "target environment", "release reference"]
        base["steps"] = ["build", "deploy", "post-deploy health check", "report"]
        base["success_criteria"] = [
            "new revision ready",
            "health endpoint 200",
            "rollback path known",
        ]
        base["validation"] = [
            "deterministic checks pass",
            "service reachable",
            "no critical alerts",
        ]
        base["artifacts"] = ["revision id", "deploy logs", "health check output"]
        base["rollback"] = [
            "pin previous stable revision",
            "notify operator with rollback evidence",
        ]
    elif normalized_kind == "research":
        base["inputs"] = ["topic", "scope", "evidence sources"]
        base["steps"] = ["collect evidence", "synthesize findings", "propose decision options"]
        base["success_criteria"] = [
            "sources cited",
            "clear recommendation",
            "operator decision-ready output",
        ]
        base["validation"] = ["source coverage >1", "claims traceable", "output concise"]
        base["artifacts"] = ["research summary", "decision options"]
        base["rollback"] = ["mark findings stale if contradicted", "re-run with tightened scope"]
    else:
        base["inputs"] = ["target files/modules", "acceptance criteria"]
        base["steps"] = ["implement", "run deterministic checks", "summarize diff and risk"]
        base["success_criteria"] = [
            "checks pass",
            "no regressions in touched surface",
            "clear next steps",
        ]
        base["validation"] = ["unit/integration checks", "lint/static checks where applicable"]
        base["artifacts"] = ["changed files", "test output summary"]
        base["rollback"] = ["revert commit or patch", "document regression trigger"]
    return base


def _normalized_task_class(task_payload: dict[str, Any]) -> str:
    raw = str(task_payload.get("task_class") or "").strip().lower()
    if raw:
        return raw
    autonomy = task_payload.get("autonomy")
    if isinstance(autonomy, dict) and bool(autonomy.get("low_signal")):
        return "low_signal"
    return _PRODUCTION_TASK_CLASS


def _normalize_task_payload(*, payload: dict[str, Any] | None, title: str) -> dict[str, Any]:
    task_payload = dict(payload or {})
    task_type = _task_type_from_payload(task_payload) or "coding"
    task_payload["task_type"] = task_type

    task_class = _normalized_task_class(task_payload)
    task_payload["task_class"] = task_class

    autonomy = task_payload.get("autonomy")
    if not isinstance(autonomy, dict):
        autonomy = {}
    if task_class in _LOW_SIGNAL_TASK_CLASSES:
        autonomy["low_signal"] = True
        task_payload.setdefault("cleanup_policy", "autocancel")
    task_payload["autonomy"] = autonomy

    contract = task_payload.get("task_contract")
    if not isinstance(contract, dict):
        contract = {}
    kind = _task_contract_kind(task_type)
    default_contract = _default_task_contract(kind=kind, title=title, task_type=task_type)
    merged_contract = dict(default_contract)
    for key, value in contract.items():
        merged_contract[str(key)] = value
    merged_contract["version"] = str(merged_contract.get("version") or _TASK_CONTRACT_VERSION)
    merged_contract["kind"] = str(merged_contract.get("kind") or kind).strip().lower() or kind
    merged_contract["task_type"] = (
        str(merged_contract.get("task_type") or task_type).strip().lower() or task_type
    )
    if not str(merged_contract.get("objective") or "").strip():
        merged_contract["objective"] = str(title or "").strip()
    for list_key in ("inputs", "steps", "success_criteria", "validation", "artifacts", "rollback"):
        value = merged_contract.get(list_key)
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            merged_contract[list_key] = cleaned
        else:
            merged_contract[list_key] = list(default_contract.get(list_key) or [])
    task_payload["task_contract"] = merged_contract
    return task_payload


def _normalize_capabilities(values: list[str] | None) -> list[str]:
    if not values:
        return []
    cleaned = sorted({str(value).strip().lower() for value in values if str(value).strip()})
    return cleaned


def _agent_membership_ids(agent_row: sqlite3.Row, worker_capabilities: list[str]) -> set[str]:
    memberships: set[str] = set()

    labels = _decode_json(agent_row["labels_json"], {})
    if isinstance(labels, dict):
        for key in ("membership_id", "model_membership", "router_membership"):
            value = str(labels.get(key) or "").strip().lower()
            if value:
                memberships.add(value)

    for capability in worker_capabilities:
        text = str(capability).strip().lower()
        if text.startswith("membership:"):
            membership_id = text.split(":", 1)[1].strip()
            if membership_id:
                memberships.add(membership_id)
    return memberships


def _task_membership_requirement(task_payload: dict[str, Any]) -> tuple[str, bool]:
    routing = task_payload.get("routing")
    if not isinstance(routing, dict):
        return "", False

    required = str(routing.get("required_membership_id") or "").strip().lower()
    recommended = str(routing.get("recommended_membership_id") or "").strip().lower()
    enforce = bool(routing.get("enforce_membership", False))
    membership_id = required or recommended
    return membership_id, enforce


def _normalize_lock_keys(values: list[Any] | Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _task_exclusive_lock_keys(task_payload: dict[str, Any]) -> list[str]:
    keys: list[str] = []

    coordination = task_payload.get("coordination")
    if isinstance(coordination, dict):
        keys.extend(_normalize_lock_keys(coordination.get("exclusive_lock_keys")))
        single = str(coordination.get("exclusive_lock_key") or "").strip().lower()
        if single:
            keys.append(single)

    task_type = _task_type_from_payload(task_payload)
    if task_type == "tradingview_control":
        tv = task_payload.get("tradingview")
        if isinstance(tv, dict):
            for field in ("account_lock_key", "session_lock_key", "lock_key"):
                value = str(tv.get(field) or "").strip().lower()
                if value:
                    keys.append(value)

    normalized: list[str] = []
    seen: set[str] = set()
    for value in keys:
        text = str(value or "").strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _normalize_membership_ids(values: list[Any] | Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _task_type_from_payload(task_payload: dict[str, Any]) -> str:
    direct = str(task_payload.get("task_type") or "").strip().lower()
    if direct:
        return direct
    routing = task_payload.get("routing")
    if isinstance(routing, dict):
        profile = routing.get("task_profile")
        if isinstance(profile, dict):
            return str(profile.get("task_type") or "").strip().lower()
    return ""


def _error_indicates_deadlock(error_text: str, error_code: str = "") -> bool:
    if str(error_code).strip().lower() in _DEADLOCK_ERROR_CODES:
        return True
    text = error_text.strip().lower()
    if not text:
        return False
    return any(pattern in text for pattern in _DEADLOCK_PATTERNS)


def _error_indicates_quota_exhaustion(error_text: str, error_code: str = "") -> bool:
    if str(error_code).strip().lower() == "quota_exhausted":
        return True
    text = error_text.strip().lower()
    if not text:
        return False
    return any(pattern in text for pattern in _QUOTA_EXHAUSTION_PATTERNS)


def _is_ambiguous_failure(
    *,
    error_text: str,
    error_code: str,
    deadlock_error: bool,
    quota_exhausted: bool,
    failover_target: str,
) -> bool:
    if quota_exhausted or deadlock_error or bool(str(failover_target or "").strip()):
        return False
    normalized_code = str(error_code or "").strip().lower()
    if normalized_code in {"syntax_error", "assertion_failed", "validation_error", "test_failed"}:
        return False
    if normalized_code in {"timeout", "unknown_error", "transient_error", "upstream_error"}:
        return True
    text = str(error_text or "").strip().lower()
    if not text:
        return True
    deterministic_hints = (
        "assert",
        "test failed",
        "syntax",
        "typeerror",
        "valueerror",
        "permission denied",
        "not found",
        "intentional",
        "invalid request",
        "forbidden",
        "unauthorized",
        "authentication",
        "auth error",
        "schema",
        "lint",
        "compile",
    )
    if any(hint in text for hint in deterministic_hints):
        return False
    ambiguous_hints = (
        "timeout",
        "timed out",
        "temporary",
        "transient",
        "unknown error",
        "upstream",
        "service unavailable",
        "connection reset",
        "gateway timeout",
    )
    return any(hint in text for hint in ambiguous_hints)


def _extract_membership_from_error(error_text: str) -> str:
    text = error_text.strip().lower()
    if not text:
        return ""
    match = re.search(r"membership(?:_id)?[=:]\s*([a-z0-9_-]+)", text)
    if not match:
        return ""
    return str(match.group(1) or "").strip().lower()


def _normalized_title_fingerprint(title: str) -> str:
    text = str(title or "").strip().lower()
    if not text:
        return ""
    text = text.replace("—", "-").replace("–", "-")
    text = re.sub(r"\s+", " ", text)
    return text


def _extract_membership_queue_blocked_membership(
    *, title: str, task_payload: dict[str, Any]
) -> str:
    metadata = task_payload.get("metadata")
    if isinstance(metadata, dict):
        for key in ("blocked_membership_id", "membership_id", "required_membership_id"):
            value = str(metadata.get(key) or "").strip().lower()
            if value:
                return value
    routing = task_payload.get("routing")
    if isinstance(routing, dict):
        for key in (
            "queue_blocked_membership_id",
            "required_membership_id",
            "recommended_membership_id",
        ):
            value = str(routing.get(key) or "").strip().lower()
            if value:
                return value
    title_text = str(title or "")
    for regex in (_BLOCKED_MEMBERSHIP_IN_TITLE_RE, _MEMBERSHIP_IN_TEXT_RE):
        match = regex.search(title_text)
        if match:
            return str(match.group(1) or "").strip().lower()
    instructions = str(task_payload.get("instructions") or "")
    for regex in (_BLOCKED_MEMBERSHIP_IN_TITLE_RE, _MEMBERSHIP_IN_TEXT_RE):
        match = regex.search(instructions)
        if match:
            return str(match.group(1) or "").strip().lower()
    return ""


def _membership_queue_recovery_dedupe_key(*, title: str, task_payload: dict[str, Any]) -> str:
    title_fingerprint = _normalized_title_fingerprint(title)
    metadata = task_payload.get("metadata")
    blocker_reason = ""
    if isinstance(metadata, dict):
        blocker_reason = str(metadata.get("blocker_reason") or "").strip().lower()
    is_membership_queue_recovery = blocker_reason == "membership_queue" or any(
        pattern in title_fingerprint for pattern in _MEMBERSHIP_QUEUE_RECOVERY_TITLE_PATTERNS
    )
    if not is_membership_queue_recovery:
        return ""
    blocked_membership = (
        _extract_membership_queue_blocked_membership(title=title, task_payload=task_payload)
        or "unknown"
    )
    return f"membership_queue_recovery:{blocked_membership}:{title_fingerprint}"


def _apply_membership_failover(
    *,
    task_payload: dict[str, Any],
    required_capabilities: list[str],
    exhausted_membership_id: str,
    reason: str,
    allowed_membership_ids: set[str] | None = None,
) -> tuple[dict[str, Any], list[str], str]:
    routing = task_payload.get("routing")
    if not isinstance(routing, dict):
        return task_payload, required_capabilities, ""

    required_membership = str(routing.get("required_membership_id") or "").strip().lower()
    recommended_membership = str(routing.get("recommended_membership_id") or "").strip().lower()
    current_membership = required_membership or recommended_membership

    exhausted = exhausted_membership_id.strip().lower() or current_membership
    fallback_ids = _normalize_membership_ids(routing.get("fallback_membership_ids"))
    if not fallback_ids:
        return task_payload, required_capabilities, ""

    allowed_set: set[str] | None = None
    if allowed_membership_ids is not None:
        allowed_set = {
            str(item).strip().lower() for item in allowed_membership_ids if str(item).strip()
        }

    next_membership = ""
    for candidate in fallback_ids:
        if (
            candidate
            and candidate not in {exhausted, current_membership}
            and (allowed_set is None or candidate in allowed_set)
        ):
            next_membership = candidate
            break
    if not next_membership:
        return task_payload, required_capabilities, ""

    previous_ids = _normalize_membership_ids(routing.get("previous_membership_ids"))
    for value in (current_membership, exhausted):
        if value and value not in previous_ids:
            previous_ids.append(value)
    exhausted_ids = _normalize_membership_ids(routing.get("exhausted_membership_ids"))
    if exhausted and exhausted not in exhausted_ids:
        exhausted_ids.append(exhausted)

    routing["required_membership_id"] = next_membership
    routing["enforce_membership"] = True
    routing["active_membership_id"] = next_membership
    routing["last_failed_membership_id"] = exhausted
    routing["last_failover_reason"] = reason
    routing["last_failover_at"] = _utc_iso_now()
    routing["previous_membership_ids"] = previous_ids
    routing["exhausted_membership_ids"] = exhausted_ids
    routing["fallback_membership_ids"] = [
        item for item in fallback_ids if item not in {next_membership, exhausted}
    ]

    capability_set = [
        cap
        for cap in _normalize_capabilities(required_capabilities)
        if not cap.startswith("membership:")
    ]
    capability_set.append(f"membership:{next_membership}")
    return task_payload, _normalize_capabilities(capability_set), next_membership


def _default_db_path() -> Path:
    env_override = os.getenv("CONTROL_PLANE_DB_PATH", "").strip()
    if env_override:
        return Path(env_override)
    return Path(__file__).resolve().parent / "data" / "control_plane.db"


def _control_plane_store_backend_kind() -> str:
    raw = str(os.getenv("AGENTIC_CONTROL_PLANE_STORE_BACKEND") or "sqlite").strip().lower()
    return raw or "sqlite"


def _control_plane_store_postgres_env() -> dict[str, Any]:
    dsn = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_DSN") or "").strip()
    cloudsql_instance = str(os.getenv("AGENTIC_CONTROL_PLANE_CLOUDSQL_INSTANCE") or "").strip()
    cloudsql_project = str(
        os.getenv("AGENTIC_CONTROL_PLANE_CLOUDSQL_PROJECT")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or ""
    ).strip()
    database = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_DB") or "").strip()
    user = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_USER") or "").strip()
    host = str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_HOST") or "").strip()
    sslmode = (
        str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_SSLMODE") or "").strip().lower() or "default"
    )
    password_present = bool(str(os.getenv("AGENTIC_CONTROL_PLANE_POSTGRES_PASSWORD") or "").strip())
    socket_path = f"/cloudsql/{cloudsql_instance}" if cloudsql_instance else ""
    explicit_parts_configured = bool(database and user and (host or socket_path))
    return {
        "dsn_present": bool(dsn),
        "cloudsql_instance_present": bool(cloudsql_instance),
        "cloudsql_project_present": bool(cloudsql_project),
        "database_present": bool(database),
        "user_present": bool(user),
        "host_present": bool(host),
        "socket_path_present": bool(socket_path),
        "password_present": password_present,
        "sslmode": sslmode,
        "configured_minimally": bool(dsn) or explicit_parts_configured,
    }


def _control_plane_store_backend_status(*, db_path: Path) -> dict[str, Any]:
    requested = _control_plane_store_backend_kind()
    postgres = _control_plane_store_postgres_env()
    sqlite_exists = False
    try:
        sqlite_exists = db_path.exists()
    except OSError:
        sqlite_exists = False

    warnings: list[str] = []
    if requested not in {"sqlite", "postgres"}:
        warnings.append(f"unsupported_requested_backend:{requested}")
    if requested == "postgres":
        if not postgres.get("configured_minimally"):
            warnings.append("postgres_requested_but_not_configured")
        warnings.append("postgres_requested_but_adapter_not_implemented")
    if not sqlite_exists:
        warnings.append("sqlite_db_file_not_initialized_yet")

    return {
        "requested_backend": requested,
        "active_backend": "sqlite",
        "migration_phase": "sqlite_active_postgres_adapter_pending",
        "supported_backends": sorted(_CONTROL_PLANE_STORE_BACKEND_SUPPORTED),
        "implementation": {
            "sqlite": True,
            "postgres": False,
            "postgres_adapter_ready": False,
        },
        "switch_ready": False,
        "sqlite": {
            "db_path": str(db_path),
            "db_file_exists": sqlite_exists,
        },
        "postgres": postgres,
        "warnings": warnings,
    }


def _decode_json(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return default
    return value


class ControlPlaneStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path else _default_db_path()
        self._backend_adapter = build_control_plane_backend_adapter(db_path=self.db_path)
        self._backend_status = self._backend_adapter.status()
        if not bool(getattr(self._backend_adapter, "implemented", False)):
            self._backend_adapter.connect()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> Any:
        return self._backend_adapter.connect()

    def backend_status(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._backend_status))

    def _sql(self, sql: str) -> str:
        translator = getattr(self._backend_adapter, "translated_sql", None)
        if callable(translator):
            try:
                return str(translator(sql))
            except Exception:
                return sql
        return sql

    def _execute(self, conn: Any, sql: str, params: tuple[Any, ...] | None = None):
        if params is None:
            return conn.execute(self._sql(sql))
        return conn.execute(self._sql(sql), params)

    def _initialize(self) -> None:
        with self._connect() as conn:
            bootstrap = getattr(self._backend_adapter, "bootstrap_store_schema", None)
            if callable(bootstrap):
                try:
                    if bool(bootstrap(conn)):
                        conn.commit()
                        return
                except NotImplementedError:
                    raise
                except Exception:
                    # Fall back to sqlite bootstrap if adapter-specific bootstrap is not viable yet.
                    pass
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agents (
                  agent_id TEXT PRIMARY KEY,
                  name TEXT NOT NULL,
                  capabilities_json TEXT NOT NULL,
                  labels_json TEXT NOT NULL,
                  metadata_json TEXT NOT NULL,
                  status TEXT NOT NULL,
                  registered_at TEXT NOT NULL,
                  last_heartbeat_at TEXT NOT NULL,
                  last_heartbeat_unix INTEGER NOT NULL,
                  updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                  task_id TEXT PRIMARY KEY,
                  title TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  required_capabilities_json TEXT NOT NULL,
                  status TEXT NOT NULL,
                  priority INTEGER NOT NULL,
                  created_by TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  lease_owner TEXT,
                  lease_expires_unix INTEGER,
                  attempts INTEGER NOT NULL,
                  max_attempts INTEGER NOT NULL,
                  result_json TEXT,
                  error_text TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_events (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  event_id TEXT NOT NULL UNIQUE,
                  task_id TEXT,
                  agent_id TEXT,
                  event_type TEXT NOT NULL,
                  payload_json TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  created_at_unix INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agents_last_heartbeat ON agents(last_heartbeat_unix)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_status_priority ON tasks(status, priority, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_lease_expiry ON tasks(lease_expires_unix)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_created ON task_events(created_at_unix DESC)"
            )
            conn.commit()

    def _record_event(
        self,
        conn: sqlite3.Connection,
        *,
        event_type: str,
        task_id: str | None,
        agent_id: str | None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        now_iso = _utc_iso_now()
        now_unix = _utc_epoch_now()
        self._execute(
            conn,
            """
            INSERT INTO task_events(event_id, task_id, agent_id, event_type, payload_json, created_at, created_at_unix)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                task_id,
                agent_id,
                event_type,
                json.dumps(payload or {}, separators=(",", ":")),
                now_iso,
                now_unix,
            ),
        )

    def _record_operator_alert(
        self,
        conn: sqlite3.Connection,
        *,
        task_id: str | None,
        action: str,
        message: str,
        category: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "action": action.strip(),
            "message": message.strip(),
            "category": category.strip(),
        }
        if metadata:
            payload.update(metadata)
        self._record_event(
            conn,
            event_type="operator_alert",
            task_id=task_id,
            agent_id=None,
            payload=payload,
        )

    def _available_membership_ids(
        self, conn: sqlite3.Connection, *, heartbeat_ttl_seconds: int
    ) -> set[str]:
        now_unix = _utc_epoch_now()
        rows = self._execute(conn, "SELECT * FROM agents WHERE status != 'disabled'").fetchall()
        allowed_agent_ids = allowed_executor_agent_ids()
        allowed_memberships = allowed_executor_membership_ids()
        membership_ids: set[str] = set()
        for row in rows:
            agent_id = str(row["agent_id"] or "").strip().lower()
            if allowed_agent_ids and agent_id not in allowed_agent_ids:
                continue
            last_heartbeat_unix = int(row["last_heartbeat_unix"] or 0)
            if (now_unix - last_heartbeat_unix) > heartbeat_ttl_seconds:
                continue
            capabilities = _decode_json(row["capabilities_json"], [])
            if not isinstance(capabilities, list):
                capabilities = []
            memberships = _agent_membership_ids(row, capabilities)
            if allowed_memberships:
                memberships = {item for item in memberships if item in allowed_memberships}
            membership_ids.update(memberships)
        return membership_ids

    def _row_to_agent(self, row: sqlite3.Row, heartbeat_ttl_seconds: int) -> dict[str, Any]:
        now_unix = _utc_epoch_now()
        last_heartbeat_unix = int(row["last_heartbeat_unix"])
        heartbeat_age_seconds = max(0, now_unix - last_heartbeat_unix)
        online = heartbeat_age_seconds <= heartbeat_ttl_seconds and row["status"] != "disabled"
        return {
            "agent_id": row["agent_id"],
            "name": row["name"],
            "capabilities": _decode_json(row["capabilities_json"], []),
            "labels": _decode_json(row["labels_json"], {}),
            "metadata": _decode_json(row["metadata_json"], {}),
            "status": row["status"],
            "registered_at": row["registered_at"],
            "last_heartbeat_at": row["last_heartbeat_at"],
            "last_heartbeat_unix": last_heartbeat_unix,
            "heartbeat_age_seconds": heartbeat_age_seconds,
            "updated_at": row["updated_at"],
            "online": online,
            # Backward-compat key used by some external Telegram agents.
            "is_online": online,
        }

    def _row_to_task(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "task_id": row["task_id"],
            "title": row["title"],
            "payload": _decode_json(row["payload_json"], {}),
            "required_capabilities": _decode_json(row["required_capabilities_json"], []),
            "status": row["status"],
            "priority": int(row["priority"]),
            "created_by": row["created_by"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "lease_owner": row["lease_owner"],
            "lease_expires_unix": row["lease_expires_unix"],
            "attempts": int(row["attempts"]),
            "max_attempts": int(row["max_attempts"]),
            "result": _decode_json(row["result_json"], None),
            "error_text": row["error_text"],
        }

    def register_agent(
        self,
        *,
        agent_id: str,
        name: str,
        capabilities: list[str] | None,
        labels: dict[str, str] | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        cleaned_agent_id = agent_id.strip()
        if not cleaned_agent_id:
            raise ValueError("agent_id is required")

        cleaned_name = name.strip() if name.strip() else cleaned_agent_id
        now_iso = _utc_iso_now()
        now_unix = _utc_epoch_now()
        capabilities_json = json.dumps(_normalize_capabilities(capabilities), separators=(",", ":"))
        labels_json = json.dumps(labels or {}, separators=(",", ":"))
        metadata_json = json.dumps(metadata or {}, separators=(",", ":"))

        with self._connect() as conn:
            existing = self._execute(
                conn,
                "SELECT agent_id, registered_at FROM agents WHERE agent_id = ?",
                (cleaned_agent_id,),
            ).fetchone()
            registered_at = existing["registered_at"] if existing else now_iso
            self._execute(
                conn,
                """
                INSERT INTO agents(
                  agent_id, name, capabilities_json, labels_json, metadata_json,
                  status, registered_at, last_heartbeat_at, last_heartbeat_unix, updated_at
                ) VALUES(?, ?, ?, ?, ?, 'online', ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                  name = excluded.name,
                  capabilities_json = excluded.capabilities_json,
                  labels_json = excluded.labels_json,
                  metadata_json = excluded.metadata_json,
                  status = 'online',
                  last_heartbeat_at = excluded.last_heartbeat_at,
                  last_heartbeat_unix = excluded.last_heartbeat_unix,
                  updated_at = excluded.updated_at
                """,
                (
                    cleaned_agent_id,
                    cleaned_name,
                    capabilities_json,
                    labels_json,
                    metadata_json,
                    registered_at,
                    now_iso,
                    now_unix,
                    now_iso,
                ),
            )
            self._record_event(
                conn,
                event_type="agent_registered",
                task_id=None,
                agent_id=cleaned_agent_id,
                payload={"capabilities": _decode_json(capabilities_json, [])},
            )
            row = self._execute(
                conn,
                "SELECT * FROM agents WHERE agent_id = ?",
                (cleaned_agent_id,),
            ).fetchone()
            conn.commit()

        return self._row_to_agent(row, heartbeat_ttl_seconds=120)

    def heartbeat_agent(
        self,
        *,
        agent_id: str,
        status: str | None,
        metadata_update: dict[str, Any] | None,
        capabilities: list[str] | None,
    ) -> dict[str, Any]:
        cleaned_agent_id = agent_id.strip()
        if not cleaned_agent_id:
            raise ValueError("agent_id is required")

        now_iso = _utc_iso_now()
        now_unix = _utc_epoch_now()
        with self._connect() as conn:
            row = self._execute(
                conn,
                "SELECT * FROM agents WHERE agent_id = ?",
                (cleaned_agent_id,),
            ).fetchone()
            if not row:
                raise KeyError(cleaned_agent_id)

            next_status = status.strip().lower() if status and status.strip() else row["status"]
            next_metadata = _decode_json(row["metadata_json"], {})
            next_labels = _decode_json(row["labels_json"], {})
            if metadata_update:
                next_metadata.update(metadata_update)
                heartbeat_membership = (
                    str(
                        metadata_update.get("worker_membership_id")
                        or metadata_update.get("membership_id")
                        or metadata_update.get("router_membership")
                        or metadata_update.get("model_membership")
                        or ""
                    )
                    .strip()
                    .lower()
                )
                if heartbeat_membership:
                    next_labels["membership_id"] = heartbeat_membership
                    next_labels.setdefault("model_membership", heartbeat_membership)
                    next_labels.setdefault("router_membership", heartbeat_membership)

            next_capabilities = _decode_json(row["capabilities_json"], [])
            if capabilities is not None:
                next_capabilities = _normalize_capabilities(capabilities)
            if not str(next_labels.get("membership_id") or "").strip():
                inferred_memberships = [
                    str(cap).split(":", 1)[1].strip().lower()
                    for cap in next_capabilities
                    if isinstance(cap, str) and str(cap).strip().lower().startswith("membership:")
                ]
                if inferred_memberships:
                    next_labels["membership_id"] = inferred_memberships[-1]

            self._execute(
                conn,
                """
                UPDATE agents
                SET status = ?,
                    labels_json = ?,
                    metadata_json = ?,
                    capabilities_json = ?,
                    last_heartbeat_at = ?,
                    last_heartbeat_unix = ?,
                    updated_at = ?
                WHERE agent_id = ?
                """,
                (
                    next_status,
                    json.dumps(next_labels, separators=(",", ":")),
                    json.dumps(next_metadata, separators=(",", ":")),
                    json.dumps(next_capabilities, separators=(",", ":")),
                    now_iso,
                    now_unix,
                    now_iso,
                    cleaned_agent_id,
                ),
            )
            self._record_event(
                conn,
                event_type="agent_heartbeat",
                task_id=None,
                agent_id=cleaned_agent_id,
                payload={"status": next_status},
            )
            updated = self._execute(
                conn,
                "SELECT * FROM agents WHERE agent_id = ?",
                (cleaned_agent_id,),
            ).fetchone()
            conn.commit()

        return self._row_to_agent(updated, heartbeat_ttl_seconds=120)

    def list_agents(
        self, *, heartbeat_ttl_seconds: int = 120, include_disabled: bool = True
    ) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if include_disabled:
                rows = self._execute(
                    conn,
                    "SELECT * FROM agents ORDER BY last_heartbeat_unix DESC, agent_id ASC",
                ).fetchall()
            else:
                rows = self._execute(
                    conn,
                    "SELECT * FROM agents WHERE status != 'disabled' ORDER BY last_heartbeat_unix DESC, agent_id ASC",
                ).fetchall()
        return [
            self._row_to_agent(row, heartbeat_ttl_seconds=heartbeat_ttl_seconds) for row in rows
        ]

    def cleanup_stale_agents(
        self,
        *,
        stale_after_seconds: int = 21600,
        keep_agent_ids: list[str] | None = None,
        keep_membership_ids: list[str] | None = None,
        dry_run: bool = False,
        actor: str = "maintenance",
    ) -> dict[str, Any]:
        threshold_seconds = max(300, min(int(stale_after_seconds), 31 * 24 * 3600))
        keep_agents = {str(item).strip() for item in (keep_agent_ids or []) if str(item).strip()}
        keep_memberships = {
            str(item).strip().lower() for item in (keep_membership_ids or []) if str(item).strip()
        }
        now_iso = _utc_iso_now()
        now_unix = _utc_epoch_now()

        candidate_rows: list[tuple[sqlite3.Row, int, list[str], list[str]]] = []
        skipped: list[dict[str, Any]] = []
        disabled_agents: list[dict[str, Any]] = []
        registered_count = 0

        with self._connect() as conn:
            rows = self._execute(
                conn,
                "SELECT * FROM agents ORDER BY last_heartbeat_unix ASC, agent_id ASC",
            ).fetchall()
            registered_count = len(rows)
            for row in rows:
                agent_id = str(row["agent_id"] or "").strip()
                status = str(row["status"] or "").strip().lower()
                last_heartbeat_unix = int(row["last_heartbeat_unix"] or 0)
                age_seconds = max(0, now_unix - last_heartbeat_unix)
                capabilities = _decode_json(row["capabilities_json"], [])
                if not isinstance(capabilities, list):
                    capabilities = []
                memberships = sorted(_agent_membership_ids(row, capabilities))

                if not agent_id:
                    skipped.append({"agent_id": "", "reason": "invalid_agent_id"})
                    continue
                if agent_id in keep_agents:
                    skipped.append({"agent_id": agent_id, "reason": "keep_agent_id"})
                    continue
                if keep_memberships and any(
                    membership in keep_memberships for membership in memberships
                ):
                    skipped.append(
                        {
                            "agent_id": agent_id,
                            "reason": "keep_membership_id",
                            "memberships": memberships,
                        }
                    )
                    continue
                if status == "disabled":
                    skipped.append({"agent_id": agent_id, "reason": "already_disabled"})
                    continue
                if age_seconds < threshold_seconds:
                    skipped.append(
                        {
                            "agent_id": agent_id,
                            "reason": "fresh_heartbeat",
                            "age_seconds": age_seconds,
                        }
                    )
                    continue

                candidate_rows.append((row, age_seconds, capabilities, memberships))

            if not dry_run:
                for row, age_seconds, capabilities, memberships in candidate_rows:
                    agent_id = str(row["agent_id"] or "").strip()
                    metadata = _decode_json(row["metadata_json"], {})
                    if not isinstance(metadata, dict):
                        metadata = {}
                    metadata["stale_cleanup"] = {
                        "disabled_at": now_iso,
                        "disabled_by": actor.strip() or "maintenance",
                        "stale_after_seconds": threshold_seconds,
                        "heartbeat_age_seconds": age_seconds,
                    }
                    self._execute(
                        conn,
                        """
                        UPDATE agents
                        SET status = 'disabled',
                            metadata_json = ?,
                            updated_at = ?
                        WHERE agent_id = ?
                        """,
                        (json.dumps(metadata, separators=(",", ":")), now_iso, agent_id),
                    )
                    self._record_event(
                        conn,
                        event_type="agent_disabled_stale_cleanup",
                        task_id=None,
                        agent_id=agent_id,
                        payload={
                            "stale_after_seconds": threshold_seconds,
                            "heartbeat_age_seconds": age_seconds,
                            "capabilities": capabilities,
                            "memberships": memberships,
                            "actor": actor.strip() or "maintenance",
                        },
                    )
                    refreshed = self._execute(
                        conn,
                        "SELECT * FROM agents WHERE agent_id = ?",
                        (agent_id,),
                    ).fetchone()
                    if refreshed:
                        disabled_agents.append(
                            self._row_to_agent(refreshed, heartbeat_ttl_seconds=threshold_seconds)
                        )
                conn.commit()

        candidates: list[dict[str, Any]] = []
        for row, age_seconds, capabilities, memberships in candidate_rows:
            candidates.append(
                {
                    "agent_id": str(row["agent_id"] or "").strip(),
                    "status": str(row["status"] or "").strip(),
                    "heartbeat_age_seconds": age_seconds,
                    "capabilities": capabilities,
                    "memberships": memberships,
                }
            )

        return {
            "generated_at": now_iso,
            "stale_after_seconds": threshold_seconds,
            "dry_run": bool(dry_run),
            "registered_count": registered_count,
            "candidate_count": len(candidates),
            "disabled_count": len(disabled_agents) if not dry_run else 0,
            "keep_agent_ids": sorted(keep_agents),
            "keep_membership_ids": sorted(keep_memberships),
            "candidates": candidates,
            "disabled_agents": disabled_agents,
            "skipped": skipped,
        }

    def create_task(
        self,
        *,
        title: str,
        payload: dict[str, Any] | None,
        required_capabilities: list[str] | None,
        priority: int,
        max_attempts: int,
        created_by: str,
    ) -> dict[str, Any]:
        cleaned_title = title.strip()
        if not cleaned_title:
            raise ValueError("title is required")

        now_iso = _utc_iso_now()
        task_id = f"task-{uuid.uuid4().hex}"
        normalized_payload = _normalize_task_payload(payload=payload, title=cleaned_title)
        dedupe_key = _membership_queue_recovery_dedupe_key(
            title=cleaned_title, task_payload=normalized_payload
        )
        normalized_required_capabilities = _normalize_capabilities(required_capabilities)
        normalized_priority = max(0, min(priority, 1000))
        normalized_max_attempts = max(1, max_attempts)
        with self._connect() as conn:
            if dedupe_key:
                active_rows = self._execute(
                    conn,
                    """
                    SELECT * FROM tasks
                    WHERE status IN ('queued', 'leased', 'blocked_review')
                    ORDER BY created_at ASC
                    LIMIT 500
                    """,
                ).fetchall()
                for existing_row in active_rows:
                    existing_payload = _decode_json(existing_row["payload_json"], {})
                    if not isinstance(existing_payload, dict):
                        existing_payload = {}
                    existing_key = _membership_queue_recovery_dedupe_key(
                        title=str(existing_row["title"] or ""),
                        task_payload=existing_payload,
                    )
                    if existing_key != dedupe_key:
                        continue

                    existing_priority = int(existing_row["priority"] or 0)
                    next_priority = min(existing_priority, normalized_priority)
                    payload_changed = False
                    metadata = existing_payload.get("metadata")
                    if not isinstance(metadata, dict):
                        metadata = {}
                        existing_payload["metadata"] = metadata
                        payload_changed = True
                    dedupe_meta = metadata.get("dedupe")
                    if not isinstance(dedupe_meta, dict):
                        dedupe_meta = {}
                        metadata["dedupe"] = dedupe_meta
                        payload_changed = True
                    dedupe_count = int(dedupe_meta.get("count") or 1)
                    dedupe_meta["count"] = max(2, dedupe_count + 1)
                    dedupe_meta["last_duplicate_at"] = now_iso
                    dedupe_meta["reason"] = "membership_queue_recovery"
                    dedupe_meta["suppressed_dedupe_key"] = dedupe_key
                    payload_changed = True

                    if payload_changed or next_priority != existing_priority:
                        self._execute(
                            conn,
                            """
                            UPDATE tasks
                            SET payload_json = ?, priority = ?, updated_at = ?
                            WHERE task_id = ?
                            """,
                            (
                                json.dumps(existing_payload, separators=(",", ":")),
                                next_priority,
                                now_iso,
                                str(existing_row["task_id"]),
                            ),
                        )
                    self._record_event(
                        conn,
                        event_type="task_create_deduped",
                        task_id=str(existing_row["task_id"]),
                        agent_id=None,
                        payload={
                            "dedupe_reason": "membership_queue_recovery",
                            "suppressed_title": cleaned_title,
                            "suppressed_priority": normalized_priority,
                            "suppressed_required_capabilities": normalized_required_capabilities,
                            "dedupe_key": dedupe_key,
                        },
                    )
                    row = self._execute(
                        conn,
                        "SELECT * FROM tasks WHERE task_id = ?",
                        (str(existing_row["task_id"]),),
                    ).fetchone()
                    conn.commit()
                    return self._row_to_task(row)

            self._execute(
                conn,
                """
                INSERT INTO tasks(
                  task_id, title, payload_json, required_capabilities_json,
                  status, priority, created_by, created_at, updated_at,
                  lease_owner, lease_expires_unix, attempts, max_attempts,
                  result_json, error_text
                ) VALUES(?, ?, ?, ?, 'queued', ?, ?, ?, ?, NULL, NULL, 0, ?, NULL, NULL)
                """,
                (
                    task_id,
                    cleaned_title,
                    json.dumps(normalized_payload, separators=(",", ":")),
                    json.dumps(normalized_required_capabilities, separators=(",", ":")),
                    normalized_priority,
                    created_by.strip(),
                    now_iso,
                    now_iso,
                    normalized_max_attempts,
                ),
            )
            self._record_event(
                conn,
                event_type="task_created",
                task_id=task_id,
                agent_id=None,
                payload={
                    "priority": priority,
                    "task_class": str(normalized_payload.get("task_class") or ""),
                    "task_type": str(normalized_payload.get("task_type") or ""),
                },
            )
            row = self._execute(
                conn,
                "SELECT * FROM tasks WHERE task_id = ?",
                (task_id,),
            ).fetchone()
            conn.commit()

        return self._row_to_task(row)

    def get_task(self, *, task_id: str) -> dict[str, Any]:
        cleaned_task_id = task_id.strip()
        if not cleaned_task_id:
            raise ValueError("task_id is required")

        with self._connect() as conn:
            self._run_watchdog_recovery(conn, heartbeat_ttl_seconds=120)
            row = self._execute(
                conn,
                "SELECT * FROM tasks WHERE task_id = ?",
                (cleaned_task_id,),
            ).fetchone()
            conn.commit()
        if not row:
            raise KeyError(cleaned_task_id)
        return self._row_to_task(row)

    def update_task(
        self,
        *,
        task_id: str,
        updated_by: str,
        title: str | None,
        payload_merge: dict[str, Any] | None,
        required_capabilities: list[str] | None,
        priority: int | None,
        note: str | None,
    ) -> dict[str, Any]:
        cleaned_task_id = task_id.strip()
        if not cleaned_task_id:
            raise ValueError("task_id is required")

        now_iso = _utc_iso_now()
        actor = updated_by.strip()
        with self._connect() as conn:
            row = self._execute(
                conn,
                "SELECT * FROM tasks WHERE task_id = ?",
                (cleaned_task_id,),
            ).fetchone()
            if not row:
                raise KeyError(cleaned_task_id)

            next_title = row["title"]
            if title is not None:
                candidate = title.strip()
                if not candidate:
                    raise ValueError("title cannot be empty")
                next_title = candidate

            next_priority = int(row["priority"])
            if priority is not None:
                next_priority = max(0, min(int(priority), 1000))

            next_required = _decode_json(row["required_capabilities_json"], [])
            if not isinstance(next_required, list):
                next_required = []
            if required_capabilities is not None:
                next_required = _normalize_capabilities(required_capabilities)

            next_payload = _decode_json(row["payload_json"], {})
            if not isinstance(next_payload, dict):
                next_payload = {}
            if payload_merge:
                for key, value in payload_merge.items():
                    next_payload[str(key)] = value

            note_text = (note or "").strip()
            if note_text:
                notes = next_payload.get("notes")
                if not isinstance(notes, list):
                    notes = []
                notes.append(
                    {
                        "at": now_iso,
                        "by": actor,
                        "text": note_text,
                    }
                )
                next_payload["notes"] = notes
            next_payload = _normalize_task_payload(payload=next_payload, title=next_title)

            self._execute(
                conn,
                """
                UPDATE tasks
                SET title = ?,
                    payload_json = ?,
                    required_capabilities_json = ?,
                    priority = ?,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    next_title,
                    json.dumps(next_payload, separators=(",", ":")),
                    json.dumps(next_required, separators=(",", ":")),
                    next_priority,
                    now_iso,
                    cleaned_task_id,
                ),
            )
            self._record_event(
                conn,
                event_type="task_updated",
                task_id=cleaned_task_id,
                agent_id=actor or None,
                payload={
                    "title_changed": title is not None,
                    "priority_changed": priority is not None,
                    "required_capabilities_changed": required_capabilities is not None,
                    "payload_merge_keys": sorted([str(key) for key in (payload_merge or {})]),
                    "note_added": bool(note_text),
                },
            )
            updated = self._execute(
                conn,
                "SELECT * FROM tasks WHERE task_id = ?",
                (cleaned_task_id,),
            ).fetchone()
            conn.commit()

        return self._row_to_task(updated)

    def _requeue_expired_leases(self, conn: sqlite3.Connection) -> int:
        now_unix = _utc_epoch_now()
        now_iso = _utc_iso_now()
        rows = self._execute(
            conn,
            """
            SELECT task_id, attempts, max_attempts FROM tasks
            WHERE status = 'leased' AND lease_expires_unix IS NOT NULL AND lease_expires_unix <= ?
            """,
            (now_unix,),
        ).fetchall()
        if not rows:
            return 0

        retry_task_ids: list[str] = []
        exhausted_rows: list[sqlite3.Row] = []
        for row in rows:
            attempts = int(row["attempts"] or 0)
            max_attempts = max(1, int(row["max_attempts"] or 1))
            if attempts >= max_attempts:
                exhausted_rows.append(row)
            else:
                retry_task_ids.append(str(row["task_id"]))

        if retry_task_ids:
            self._execute(
                conn,
                f"""
                UPDATE tasks
                SET status = 'queued', lease_owner = NULL, lease_expires_unix = NULL, updated_at = ?
                WHERE task_id IN ({",".join(["?"] * len(retry_task_ids))})
                """,
                (now_iso, *retry_task_ids),
            )
        for task_id in retry_task_ids:
            self._record_event(
                conn,
                event_type="task_requeued_expired_lease",
                task_id=task_id,
                agent_id=None,
                payload={},
            )
            self._record_operator_alert(
                conn,
                task_id=task_id,
                action="requeued_expired_lease",
                message=f"{task_id} lease expired; requeued",
                category="stale_lease_watchdog",
                metadata={"resolution": "task returned to queued"},
            )

        for row in exhausted_rows:
            task_id = str(row["task_id"])
            attempts = int(row["attempts"] or 0)
            max_attempts = max(1, int(row["max_attempts"] or 1))
            self._execute(
                conn,
                """
                UPDATE tasks
                SET status = 'failed',
                    lease_owner = NULL,
                    lease_expires_unix = NULL,
                    updated_at = ?,
                    error_text = COALESCE(error_text || ' | ', '') || 'lease expired and retry budget exhausted'
                WHERE task_id = ?
                """,
                (now_iso, task_id),
            )
            self._record_event(
                conn,
                event_type="task_failed_final",
                task_id=task_id,
                agent_id=None,
                payload={
                    "retryable": False,
                    "attempts": attempts,
                    "max_attempts": max_attempts,
                    "error_code": "retry_budget_exhausted_watchdog",
                    "watchdog": True,
                },
            )
            self._record_operator_alert(
                conn,
                task_id=task_id,
                action="expired_lease_exhausted",
                message=f"{task_id} lease expired and exhausted retry budget",
                category="stale_lease_watchdog",
                metadata={
                    "attempts": attempts,
                    "max_attempts": max_attempts,
                    "resolution": "task marked failed",
                },
            )
        return len(retry_task_ids) + len(exhausted_rows)

    def _fail_exhausted_queued_tasks(self, conn: sqlite3.Connection) -> int:
        now_iso = _utc_iso_now()
        now_dt = _utc_now()
        rows = self._execute(
            conn,
            """
            SELECT task_id, attempts, max_attempts, payload_json, created_at FROM tasks
            WHERE status = 'queued' AND attempts >= max_attempts
            ORDER BY priority ASC, created_at ASC
            LIMIT 500
            """,
        ).fetchall()
        if not rows:
            return 0

        failed_count = 0
        for row in rows:
            task_id = str(row["task_id"])
            attempts = int(row["attempts"] or 0)
            max_attempts = max(1, int(row["max_attempts"] or 1))
            created_dt = _parse_iso_datetime(row["created_at"])
            age_seconds = int((now_dt - created_dt).total_seconds()) if created_dt else 0
            task_payload = _decode_json(row["payload_json"], {})
            if not isinstance(task_payload, dict):
                task_payload = {}
            routing = task_payload.get("routing")
            if isinstance(routing, dict):
                # Preserve freshly rerouted tasks for a short grace window so the
                # fallback membership can take one execution pass.
                failover_at = str(routing.get("last_failover_at") or "").strip()
                active_membership = (
                    str(
                        routing.get("active_membership_id")
                        or routing.get("required_membership_id")
                        or ""
                    )
                    .strip()
                    .lower()
                )
                last_failed_membership = (
                    str(routing.get("last_failed_membership_id") or "").strip().lower()
                )
                if (
                    failover_at
                    and active_membership
                    and active_membership != last_failed_membership
                    and age_seconds <= _WATCHDOG_FAILOVER_GRACE_SECONDS
                ):
                    continue
            self._execute(
                conn,
                """
                UPDATE tasks
                SET status = 'failed',
                    updated_at = ?,
                    error_text = COALESCE(error_text || ' | ', '') || 'retry budget exhausted while queued'
                WHERE task_id = ?
                """,
                (now_iso, task_id),
            )
            self._record_event(
                conn,
                event_type="task_failed_final",
                task_id=task_id,
                agent_id=None,
                payload={
                    "retryable": False,
                    "attempts": attempts,
                    "max_attempts": max_attempts,
                    "error_code": "retry_budget_exhausted_watchdog",
                    "watchdog": True,
                    "from_status": "queued",
                    "age_seconds": age_seconds,
                },
            )
            self._record_operator_alert(
                conn,
                task_id=task_id,
                action="queued_retry_budget_exhausted",
                message=f"{task_id} exceeded retry budget while queued",
                category="queue_unblock_watchdog",
                metadata={
                    "attempts": attempts,
                    "max_attempts": max_attempts,
                    "age_seconds": age_seconds,
                    "resolution": "task marked failed",
                },
            )
            failed_count += 1
        return failed_count

    def _fail_stale_leased_tasks(self, conn: sqlite3.Connection) -> int:
        now_iso = _utc_iso_now()
        now_dt = _utc_now()
        rows = self._execute(
            conn,
            """
            SELECT task_id, attempts, max_attempts, created_at FROM tasks
            WHERE status = 'leased' AND attempts >= max_attempts
            ORDER BY created_at ASC
            LIMIT 500
            """,
        ).fetchall()
        if not rows:
            return 0

        failed_count = 0
        for row in rows:
            created_dt = _parse_iso_datetime(row["created_at"])
            age_seconds = int((now_dt - created_dt).total_seconds()) if created_dt else 0
            if age_seconds < _WATCHDOG_STALE_LEASE_SECONDS:
                continue

            task_id = str(row["task_id"])
            attempts = int(row["attempts"] or 0)
            max_attempts = max(1, int(row["max_attempts"] or 1))
            self._execute(
                conn,
                """
                UPDATE tasks
                SET status = 'failed',
                    lease_owner = NULL,
                    lease_expires_unix = NULL,
                    updated_at = ?,
                    error_text = COALESCE(error_text || ' | ', '') || 'stale leased task exceeded retry budget'
                WHERE task_id = ?
                """,
                (now_iso, task_id),
            )
            self._record_event(
                conn,
                event_type="task_failed_final",
                task_id=task_id,
                agent_id=None,
                payload={
                    "retryable": False,
                    "attempts": attempts,
                    "max_attempts": max_attempts,
                    "error_code": "retry_budget_exhausted_stale_lease_watchdog",
                    "watchdog": True,
                    "from_status": "leased",
                    "age_seconds": age_seconds,
                },
            )
            self._record_operator_alert(
                conn,
                task_id=task_id,
                action="stale_leased_retry_budget_exhausted",
                message=f"{task_id} stale leased task exceeded retry budget",
                category="stale_lease_watchdog",
                metadata={
                    "attempts": attempts,
                    "max_attempts": max_attempts,
                    "age_seconds": age_seconds,
                },
            )
            failed_count += 1
        return failed_count

    def _recover_queue_blocked_memberships(
        self, conn: sqlite3.Connection, *, heartbeat_ttl_seconds: int
    ) -> int:
        now_iso = _utc_iso_now()
        available_memberships = self._available_membership_ids(
            conn, heartbeat_ttl_seconds=heartbeat_ttl_seconds
        )
        queued_rows = self._execute(
            conn,
            """
            SELECT task_id, payload_json, required_capabilities_json
            FROM tasks
            WHERE status = 'queued'
            ORDER BY priority ASC, created_at ASC
            LIMIT 500
            """,
        ).fetchall()

        recovered_count = 0
        for row in queued_rows:
            task_payload = _decode_json(row["payload_json"], {})
            if not isinstance(task_payload, dict):
                continue

            membership_id, enforce_membership = _task_membership_requirement(task_payload)
            if not enforce_membership or not membership_id:
                continue
            if membership_id in available_memberships:
                continue

            required_capabilities = _decode_json(row["required_capabilities_json"], [])
            if not isinstance(required_capabilities, list):
                required_capabilities = []

            task_payload, required_capabilities, failover_target = _apply_membership_failover(
                task_payload=task_payload,
                required_capabilities=required_capabilities,
                exhausted_membership_id=membership_id,
                reason="membership_unavailable_watchdog",
                allowed_membership_ids=available_memberships,
            )
            routing = task_payload.get("routing")
            if not isinstance(routing, dict):
                routing = {}
                task_payload["routing"] = routing

            task_id = str(row["task_id"])
            if failover_target:
                routing.pop("queue_blocked_membership_id", None)
                routing.pop("queue_blocked_detected_at", None)
                self._execute(
                    conn,
                    """
                    UPDATE tasks
                    SET payload_json = ?, required_capabilities_json = ?, updated_at = ?
                    WHERE task_id = ?
                    """,
                    (
                        json.dumps(task_payload, separators=(",", ":")),
                        json.dumps(
                            _normalize_capabilities(required_capabilities), separators=(",", ":")
                        ),
                        now_iso,
                        task_id,
                    ),
                )
                self._record_event(
                    conn,
                    event_type="task_queue_unblocked_membership_failover",
                    task_id=task_id,
                    agent_id=None,
                    payload={
                        "from_membership_id": membership_id,
                        "to_membership_id": failover_target,
                    },
                )
                self._record_operator_alert(
                    conn,
                    task_id=task_id,
                    action=f"failover_to:{failover_target}",
                    message=f"{task_id} rerouted {membership_id}->{failover_target}",
                    category="queue_unblock_watchdog",
                    metadata={"resolution": "task rerouted to available fallback membership"},
                )
                recovered_count += 1
                continue

            already_blocked = str(routing.get("queue_blocked_membership_id") or "").strip().lower()
            if already_blocked == membership_id:
                continue
            routing["queue_blocked_membership_id"] = membership_id
            routing["queue_blocked_detected_at"] = now_iso
            self._execute(
                conn,
                """
                UPDATE tasks
                SET payload_json = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    json.dumps(task_payload, separators=(",", ":")),
                    now_iso,
                    task_id,
                ),
            )
            self._record_event(
                conn,
                event_type="task_queue_blocked_membership_unavailable",
                task_id=task_id,
                agent_id=None,
                payload={"membership_id": membership_id},
            )
            self._record_operator_alert(
                conn,
                task_id=task_id,
                action="manual_membership_recovery_required",
                message=f"{task_id} blocked on membership:{membership_id}",
                category="queue_unblock_watchdog",
                metadata={"resolution": "restore membership or add fallback"},
            )
        return recovered_count

    def _recover_single_agent_queue_constraints(self, conn: sqlite3.Connection) -> int:
        if not _single_agent_mode_enabled():
            return 0

        now_iso = _utc_iso_now()
        single_agent_membership = _single_agent_membership_id()
        baseline_caps = _single_agent_capability_profile()

        queued_rows = self._execute(
            conn,
            """
            SELECT task_id, payload_json, required_capabilities_json
            FROM tasks
            WHERE status = 'queued'
            ORDER BY priority ASC, created_at ASC
            LIMIT 500
            """,
        ).fetchall()

        updated_count = 0
        for row in queued_rows:
            task_id = str(row["task_id"] or "").strip()
            if not task_id:
                continue
            task_payload = _decode_json(row["payload_json"], {})
            if not isinstance(task_payload, dict):
                task_payload = {}
            routing = task_payload.get("routing")
            if isinstance(routing, dict):
                current_required = str(routing.get("required_membership_id") or "").strip().lower()
                escalation_active = bool(routing.get("escalation_active", False))
                if escalation_active and current_required == "claude_code":
                    # Preserve active Kimi->Claude deadlock escalations even in single-agent mode.
                    continue
            existing_required = _decode_json(row["required_capabilities_json"], [])
            if not isinstance(existing_required, list):
                existing_required = []

            task_type = str(task_payload.get("task_type") or "").strip().lower()
            required = _normalize_capabilities(existing_required)
            is_trading_task = task_type in {"trading_operation", "trading"} or any(
                cap.startswith("trading:") or cap.startswith("venue:") for cap in required
            )
            next_required: list[str] = []
            has_non_target_membership = False
            dropped_research_tools = False
            dropped_trading_baseline_caps = False

            for capability in required:
                if capability.startswith("membership:"):
                    membership_id = capability.split(":", 1)[1].strip().lower()
                    if single_agent_membership and membership_id != single_agent_membership:
                        has_non_target_membership = True
                        continue
                if is_trading_task and capability in {"python", "git", "repo-write"}:
                    dropped_trading_baseline_caps = True
                    continue
                if task_type == "research" and capability in _SINGLE_AGENT_RESEARCH_TOOL_CAPS:
                    dropped_research_tools = True
                    continue
                next_required.append(capability)

            if single_agent_membership:
                membership_cap = f"membership:{single_agent_membership}"
                next_required = [cap for cap in next_required if not cap.startswith("membership:")]
                next_required.append(membership_cap)

            if not is_trading_task:
                for capability in baseline_caps:
                    if capability not in next_required:
                        next_required.append(capability)

            normalized_required = _normalize_capabilities(next_required)
            if normalized_required == required:
                continue

            if not isinstance(routing, dict):
                routing = {}
                task_payload["routing"] = routing
            if single_agent_membership:
                routing["required_membership_id"] = single_agent_membership
                routing["recommended_membership_id"] = single_agent_membership
                routing["enforce_membership"] = True
                routing["fallback_membership_ids"] = []
            routing["single_agent_normalized_at"] = now_iso
            reasons: list[str] = []
            if has_non_target_membership:
                reasons.append("membership_alignment")
            if dropped_research_tools:
                reasons.append("research_tool_downgrade")
            if is_trading_task and (
                dropped_trading_baseline_caps or required != normalized_required
            ):
                reasons.append("trading_capability_preserved")
            if reasons:
                routing["single_agent_normalization_reason"] = ",".join(reasons)

            self._execute(
                conn,
                """
                UPDATE tasks
                SET payload_json = ?, required_capabilities_json = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (
                    json.dumps(task_payload, separators=(",", ":")),
                    json.dumps(normalized_required, separators=(",", ":")),
                    now_iso,
                    task_id,
                ),
            )
            self._record_event(
                conn,
                event_type="task_queue_single_agent_normalized",
                task_id=task_id,
                agent_id=None,
                payload={
                    "single_agent_membership": single_agent_membership,
                    "from_capabilities": required,
                    "to_capabilities": normalized_required,
                    "reasons": reasons,
                },
            )
            self._record_operator_alert(
                conn,
                task_id=task_id,
                action="single_agent_queue_normalized",
                message=f"{task_id} normalized for single-agent routing",
                category="queue_unblock_watchdog",
                metadata={"single_agent_membership": single_agent_membership},
            )
            updated_count += 1

        return updated_count

    def _auto_cancel_low_signal_tasks(self, conn: sqlite3.Connection) -> int:
        if not _low_signal_autocancel_enabled():
            return 0

        now_iso = _utc_iso_now()
        now_dt = _utc_now()
        min_age_seconds = _low_signal_cancel_age_seconds()
        cancel_limit = _low_signal_cancel_limit()

        rows = self._execute(
            conn,
            """
            SELECT task_id, title, status, payload_json, error_text, created_at, updated_at
            FROM tasks
            WHERE status IN ('queued', 'failed')
            ORDER BY updated_at ASC, created_at ASC
            LIMIT 500
            """,
        ).fetchall()
        if not rows:
            return 0

        cancelled_count = 0
        for row in rows:
            if cancelled_count >= cancel_limit:
                break

            task_id = str(row["task_id"] or "").strip()
            if not task_id:
                continue

            title = str(row["title"] or "")
            title_lower = title.strip().lower()

            task_payload = _decode_json(row["payload_json"], {})
            if not isinstance(task_payload, dict):
                task_payload = {}

            if bool(task_payload.get("protect_from_autocancel")):
                continue

            cleanup_policy = str(task_payload.get("cleanup_policy") or "").strip().lower()
            if cleanup_policy in {"retain", "never"}:
                continue

            autonomy = task_payload.get("autonomy")
            low_signal = bool(isinstance(autonomy, dict) and autonomy.get("low_signal"))
            task_class = _normalized_task_class(task_payload)
            if task_class in _LOW_SIGNAL_TASK_CLASSES:
                low_signal = True
            if not low_signal and _low_signal_title_fallback_enabled():
                low_signal = any(pattern in title_lower for pattern in _LOW_SIGNAL_CANCEL_PATTERNS)
            if not low_signal:
                continue

            updated_dt = _parse_iso_datetime(str(row["updated_at"] or "")) or _parse_iso_datetime(
                str(row["created_at"] or "")
            )
            age_seconds = int((now_dt - updated_dt).total_seconds()) if updated_dt else 0
            if age_seconds < min_age_seconds:
                continue

            existing_error = str(row["error_text"] or "").strip()
            appended = "auto-cancelled low-signal task (smoke/probe hygiene)"
            next_error = f"{existing_error} | {appended}" if existing_error else appended
            from_status = str(row["status"] or "").strip().lower()

            self._execute(
                conn,
                """
                UPDATE tasks
                SET status = 'cancelled',
                    error_text = ?,
                    lease_owner = NULL,
                    lease_expires_unix = NULL,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (next_error, now_iso, task_id),
            )
            self._record_event(
                conn,
                event_type="task_auto_cancelled_low_signal",
                task_id=task_id,
                agent_id=None,
                payload={
                    "from_status": from_status,
                    "age_seconds": age_seconds,
                    "min_age_seconds": min_age_seconds,
                    "reason": "smoke_probe_hygiene",
                    "task_class": task_class,
                },
            )
            self._record_operator_alert(
                conn,
                task_id=task_id,
                action="auto_cancel_low_signal",
                message=f"{task_id} auto-cancelled (low-signal smoke/probe task)",
                category="queue_hygiene_watchdog",
                metadata={"age_seconds": age_seconds, "from_status": from_status},
            )
            cancelled_count += 1

        return cancelled_count

    def _run_watchdog_recovery(
        self, conn: sqlite3.Connection, *, heartbeat_ttl_seconds: int = 180
    ) -> dict[str, int]:
        stale_requeued = self._requeue_expired_leases(conn)
        stale_leased_failed = self._fail_stale_leased_tasks(conn)
        queued_exhausted_failed = self._fail_exhausted_queued_tasks(conn)
        queue_unblocked = self._recover_queue_blocked_memberships(
            conn, heartbeat_ttl_seconds=heartbeat_ttl_seconds
        )
        single_agent_normalized = self._recover_single_agent_queue_constraints(conn)
        low_signal_cancelled = self._auto_cancel_low_signal_tasks(conn)
        return {
            "stale_leases_requeued": stale_requeued,
            "stale_leases_failed": stale_leased_failed,
            "queued_retry_budget_failed": queued_exhausted_failed,
            "queue_memberships_unblocked": queue_unblocked,
            "single_agent_queue_normalized": single_agent_normalized,
            "low_signal_auto_cancelled": low_signal_cancelled,
        }

    def lease_tasks(
        self,
        *,
        agent_id: str,
        capabilities: list[str] | None,
        lease_seconds: int,
        limit: int,
    ) -> list[dict[str, Any]]:
        cleaned_agent_id = agent_id.strip()
        if not cleaned_agent_id:
            raise ValueError("agent_id is required")

        effective_limit = max(1, min(limit, 20))
        effective_lease_seconds = max(30, min(lease_seconds, 3600))
        now_unix = _utc_epoch_now()
        now_iso = _utc_iso_now()

        with self._connect() as conn:
            self._execute(conn, "BEGIN IMMEDIATE")
            agent_row = self._execute(
                conn,
                "SELECT * FROM agents WHERE agent_id = ?",
                (cleaned_agent_id,),
            ).fetchone()
            if not agent_row:
                conn.rollback()
                raise KeyError(cleaned_agent_id)

            self._run_watchdog_recovery(conn, heartbeat_ttl_seconds=180)

            worker_capabilities = _normalize_capabilities(capabilities)
            if not worker_capabilities:
                worker_capabilities = _decode_json(agent_row["capabilities_json"], [])
            worker_capability_set = set(worker_capabilities)
            worker_membership_ids = _agent_membership_ids(agent_row, worker_capabilities)
            metadata = _decode_json(agent_row["metadata_json"], {})
            if not isinstance(metadata, dict):
                metadata = {}

            def _policy_denial_should_emit(reason: str, *, cooldown_seconds: int = 120) -> bool:
                last = metadata.get("last_policy_denied")
                if not isinstance(last, dict):
                    return True
                previous_reason = str(last.get("reason") or "").strip().lower()
                try:
                    previous_unix = int(last.get("at_unix") or 0)
                except (TypeError, ValueError):
                    previous_unix = 0
                if previous_reason == reason.strip().lower() and previous_unix > 0:
                    return (now_unix - previous_unix) >= max(30, cooldown_seconds)
                return True

            def _update_policy_denial_metadata(reason: str) -> None:
                metadata["last_policy_denied"] = {
                    "reason": reason.strip().lower(),
                    "at": now_iso,
                    "at_unix": now_unix,
                }

            allowed_agent_ids = allowed_executor_agent_ids()
            if allowed_agent_ids and cleaned_agent_id.strip().lower() not in allowed_agent_ids:
                emit_event = _policy_denial_should_emit("agent_not_in_executor_policy")
                _update_policy_denial_metadata("agent_not_in_executor_policy")
                self._execute(
                    conn,
                    """
                    UPDATE agents
                    SET status = 'online',
                        last_heartbeat_at = ?,
                        last_heartbeat_unix = ?,
                        metadata_json = ?,
                        updated_at = ?
                    WHERE agent_id = ?
                    """,
                    (
                        now_iso,
                        now_unix,
                        json.dumps(metadata, separators=(",", ":")),
                        now_iso,
                        cleaned_agent_id,
                    ),
                )
                if emit_event:
                    self._record_event(
                        conn,
                        event_type="task_lease_policy_denied",
                        task_id=None,
                        agent_id=cleaned_agent_id,
                        payload={
                            "reason": "agent_not_in_executor_policy",
                            "allowed_executor_agent_ids": sorted(allowed_agent_ids),
                        },
                    )
                conn.commit()
                return []

            allowed_memberships = allowed_executor_membership_ids()
            if allowed_memberships and not (worker_membership_ids & allowed_memberships):
                emit_event = _policy_denial_should_emit("membership_not_in_executor_policy")
                _update_policy_denial_metadata("membership_not_in_executor_policy")
                self._execute(
                    conn,
                    """
                    UPDATE agents
                    SET status = 'online',
                        last_heartbeat_at = ?,
                        last_heartbeat_unix = ?,
                        metadata_json = ?,
                        updated_at = ?
                    WHERE agent_id = ?
                    """,
                    (
                        now_iso,
                        now_unix,
                        json.dumps(metadata, separators=(",", ":")),
                        now_iso,
                        cleaned_agent_id,
                    ),
                )
                if emit_event:
                    self._record_event(
                        conn,
                        event_type="task_lease_policy_denied",
                        task_id=None,
                        agent_id=cleaned_agent_id,
                        payload={
                            "reason": "membership_not_in_executor_policy",
                            "worker_membership_ids": sorted(worker_membership_ids),
                            "allowed_executor_membership_ids": sorted(allowed_memberships),
                        },
                    )
                conn.commit()
                return []

            queued_rows = self._execute(
                conn,
                """
                SELECT * FROM tasks
                WHERE status = 'queued'
                ORDER BY priority ASC, created_at ASC
                LIMIT 200
                """,
            ).fetchall()

            active_lock_keys: set[str] = set()
            leased_rows_for_locks = self._execute(
                conn,
                """
                SELECT task_id, payload_json
                FROM tasks
                WHERE status = 'leased'
                """,
            ).fetchall()
            for leased_row in leased_rows_for_locks:
                leased_payload = _decode_json(leased_row["payload_json"], {})
                if not isinstance(leased_payload, dict):
                    continue
                active_lock_keys.update(_task_exclusive_lock_keys(leased_payload))

            selected_task_ids: list[str] = []
            selected_lock_keys: set[str] = set()
            for row in queued_rows:
                required = set(_decode_json(row["required_capabilities_json"], []))
                if required and not required.issubset(worker_capability_set):
                    continue

                task_payload = _decode_json(row["payload_json"], {})
                if not isinstance(task_payload, dict):
                    task_payload = {}
                membership_id, enforce_membership = _task_membership_requirement(
                    task_payload if isinstance(task_payload, dict) else {}
                )
                if (
                    enforce_membership
                    and membership_id
                    and membership_id not in worker_membership_ids
                ):
                    continue

                lock_keys = _task_exclusive_lock_keys(task_payload)
                if lock_keys and any(
                    key in active_lock_keys or key in selected_lock_keys for key in lock_keys
                ):
                    continue

                selected_task_ids.append(row["task_id"])
                for key in lock_keys:
                    selected_lock_keys.add(key)
                if len(selected_task_ids) >= effective_limit:
                    break

            leased_rows: list[sqlite3.Row] = []
            for task_id in selected_task_ids:
                lease_expires_unix = now_unix + effective_lease_seconds
                self._execute(
                    conn,
                    """
                    UPDATE tasks
                    SET status = 'leased',
                        lease_owner = ?,
                        lease_expires_unix = ?,
                        attempts = attempts + 1,
                        updated_at = ?
                    WHERE task_id = ?
                    """,
                    (cleaned_agent_id, lease_expires_unix, now_iso, task_id),
                )
                row = self._execute(
                    conn,
                    "SELECT * FROM tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                leased_rows.append(row)
                self._record_event(
                    conn,
                    event_type="task_leased",
                    task_id=task_id,
                    agent_id=cleaned_agent_id,
                    payload={"lease_seconds": effective_lease_seconds},
                )

            self._execute(
                conn,
                """
                UPDATE agents
                SET status = 'online',
                    last_heartbeat_at = ?,
                    last_heartbeat_unix = ?,
                    updated_at = ?
                WHERE agent_id = ?
                """,
                (now_iso, now_unix, now_iso, cleaned_agent_id),
            )
            conn.commit()

        return [self._row_to_task(row) for row in leased_rows]

    def extend_task_lease(
        self, *, task_id: str, agent_id: str, lease_seconds: int
    ) -> dict[str, Any]:
        cleaned_task_id = task_id.strip()
        cleaned_agent_id = agent_id.strip()
        if not cleaned_task_id or not cleaned_agent_id:
            raise ValueError("task_id and agent_id are required")

        effective_lease_seconds = max(30, min(lease_seconds, 3600))
        now_iso = _utc_iso_now()
        now_unix = _utc_epoch_now()

        with self._connect() as conn:
            row = self._execute(
                conn,
                "SELECT * FROM tasks WHERE task_id = ?",
                (cleaned_task_id,),
            ).fetchone()
            if not row:
                raise KeyError(cleaned_task_id)
            if row["status"] != "leased" or row["lease_owner"] != cleaned_agent_id:
                raise PermissionError("task lease not owned by agent")

            lease_expires_unix = now_unix + effective_lease_seconds
            self._execute(
                conn,
                """
                UPDATE tasks
                SET lease_expires_unix = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (lease_expires_unix, now_iso, cleaned_task_id),
            )
            self._record_event(
                conn,
                event_type="task_lease_extended",
                task_id=cleaned_task_id,
                agent_id=cleaned_agent_id,
                payload={"lease_seconds": effective_lease_seconds},
            )
            updated = self._execute(
                conn,
                "SELECT * FROM tasks WHERE task_id = ?",
                (cleaned_task_id,),
            ).fetchone()
            conn.commit()

        return self._row_to_task(updated)

    def complete_task(
        self, *, task_id: str, agent_id: str, result: dict[str, Any] | None
    ) -> dict[str, Any]:
        cleaned_task_id = task_id.strip()
        cleaned_agent_id = agent_id.strip()
        if not cleaned_task_id or not cleaned_agent_id:
            raise ValueError("task_id and agent_id are required")

        now_iso = _utc_iso_now()
        with self._connect() as conn:
            row = self._execute(
                conn,
                "SELECT * FROM tasks WHERE task_id = ?",
                (cleaned_task_id,),
            ).fetchone()
            if not row:
                raise KeyError(cleaned_task_id)
            if row["status"] != "leased" or row["lease_owner"] != cleaned_agent_id:
                raise PermissionError("task lease not owned by agent")

            self._execute(
                conn,
                """
                UPDATE tasks
                SET status = 'completed',
                    result_json = ?,
                    lease_owner = NULL,
                    lease_expires_unix = NULL,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (json.dumps(result or {}, separators=(",", ":")), now_iso, cleaned_task_id),
            )
            self._record_event(
                conn,
                event_type="task_completed",
                task_id=cleaned_task_id,
                agent_id=cleaned_agent_id,
                payload={},
            )
            updated = self._execute(
                conn,
                "SELECT * FROM tasks WHERE task_id = ?",
                (cleaned_task_id,),
            ).fetchone()
            conn.commit()

        return self._row_to_task(updated)

    def fail_task(
        self,
        *,
        task_id: str,
        agent_id: str,
        error_text: str,
        retryable: bool,
        error_code: str = "",
        membership_id: str = "",
    ) -> dict[str, Any]:
        cleaned_task_id = task_id.strip()
        cleaned_agent_id = agent_id.strip()
        if not cleaned_task_id or not cleaned_agent_id:
            raise ValueError("task_id and agent_id are required")

        now_iso = _utc_iso_now()
        with self._connect() as conn:
            row = self._execute(
                conn,
                "SELECT * FROM tasks WHERE task_id = ?",
                (cleaned_task_id,),
            ).fetchone()
            if not row:
                raise KeyError(cleaned_task_id)
            if row["status"] != "leased" or row["lease_owner"] != cleaned_agent_id:
                raise PermissionError("task lease not owned by agent")

            attempts = int(row["attempts"])
            max_attempts = int(row["max_attempts"])
            task_payload = _decode_json(row["payload_json"], {})
            if not isinstance(task_payload, dict):
                task_payload = {}
            required_capabilities = _decode_json(row["required_capabilities_json"], [])
            if not isinstance(required_capabilities, list):
                required_capabilities = []
            available_membership_ids = self._available_membership_ids(
                conn, heartbeat_ttl_seconds=180
            )

            cleaned_error = error_text.strip()
            current_membership_before_failover, _ = _task_membership_requirement(task_payload)
            reported_membership = membership_id.strip().lower() or _extract_membership_from_error(
                cleaned_error
            )
            exhausted = reported_membership or current_membership_before_failover
            quota_exhausted = _error_indicates_quota_exhaustion(
                cleaned_error, error_code=error_code
            )
            deadlock_error = _error_indicates_deadlock(cleaned_error, error_code=error_code)
            task_type = _task_type_from_payload(task_payload)
            failover_target = ""
            routing = task_payload.get("routing")
            if not isinstance(routing, dict):
                routing = {}
                task_payload["routing"] = routing

            kimi_failed_count = int(routing.get("kimi_failed_count", 0))
            failed_membership = exhausted
            if failed_membership == "kimi":
                kimi_failed_count += 1
                routing["kimi_failed_count"] = kimi_failed_count
                routing["last_kimi_failure_at"] = now_iso

            if quota_exhausted:
                task_payload, required_capabilities, failover_target = _apply_membership_failover(
                    task_payload=task_payload,
                    required_capabilities=required_capabilities,
                    exhausted_membership_id=exhausted,
                    reason="quota_exhausted",
                    allowed_membership_ids=available_membership_ids,
                )

            escalation_policy = routing.get("escalation_policy")
            if not isinstance(escalation_policy, dict):
                escalation_policy = {}
            escalation_enabled = bool(escalation_policy.get("enabled", False))
            escalation_target = (
                str(escalation_policy.get("target_membership_id") or "claude_code").strip().lower()
            )
            allowed_task_types = {
                str(item).strip().lower()
                for item in escalation_policy.get("allowed_task_types", [])
                if str(item).strip()
            }
            if not allowed_task_types:
                allowed_task_types = {"architecture", "debugging", "coding"}
            failure_threshold = int(escalation_policy.get("kimi_failure_threshold", 2) or 2)
            failure_threshold = max(1, min(failure_threshold, 5))

            should_escalate = (
                not failover_target
                and escalation_enabled
                and failed_membership == "kimi"
                and deadlock_error
                and task_type in allowed_task_types
                and kimi_failed_count >= failure_threshold
                and escalation_target in available_membership_ids
            )
            if should_escalate:
                fallback_ids = _normalize_membership_ids(routing.get("fallback_membership_ids"))
                fallback_ids = [item for item in fallback_ids if item != escalation_target]
                fallback_ids.insert(0, escalation_target)
                routing["fallback_membership_ids"] = fallback_ids
                task_payload, required_capabilities, failover_target = _apply_membership_failover(
                    task_payload=task_payload,
                    required_capabilities=required_capabilities,
                    exhausted_membership_id="kimi",
                    reason="kimi_deadlock_escalation",
                    allowed_membership_ids=available_membership_ids,
                )
                if failover_target:
                    routing["escalation_active"] = True
                    routing["escalation_target_membership_id"] = failover_target
                    routing["escalation_triggered_at"] = now_iso

            should_retry = (retryable and attempts < max_attempts) or bool(failover_target)
            dead_letter = False
            if not should_retry and (not retryable) and _dead_letter_enabled():
                dead_letter = _is_ambiguous_failure(
                    error_text=cleaned_error,
                    error_code=error_code,
                    deadlock_error=deadlock_error,
                    quota_exhausted=quota_exhausted,
                    failover_target=failover_target,
                )
            if should_retry:
                next_status = "queued"
            elif dead_letter:
                next_status = "blocked_review"
            else:
                next_status = "failed"
            if failover_target:
                from_value = exhausted or current_membership_before_failover or "unknown"
                cleaned_error = f"{cleaned_error} | auto-failover {from_value} -> {failover_target}"

            self._execute(
                conn,
                """
                UPDATE tasks
                SET status = ?,
                    error_text = ?,
                    payload_json = ?,
                    required_capabilities_json = ?,
                    lease_owner = NULL,
                    lease_expires_unix = NULL,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (
                    next_status,
                    cleaned_error,
                    json.dumps(task_payload, separators=(",", ":")),
                    json.dumps(
                        _normalize_capabilities(required_capabilities), separators=(",", ":")
                    ),
                    now_iso,
                    cleaned_task_id,
                ),
            )
            self._record_event(
                conn,
                event_type=(
                    "task_failed_retry"
                    if should_retry
                    else ("task_dead_lettered" if dead_letter else "task_failed_final")
                ),
                task_id=cleaned_task_id,
                agent_id=cleaned_agent_id,
                payload={
                    "retryable": retryable,
                    "attempts": attempts,
                    "max_attempts": max_attempts,
                    "error_code": error_code.strip().lower(),
                    "quota_exhausted": quota_exhausted,
                    "deadlock_error": deadlock_error,
                    "auto_failover_to": failover_target,
                    "reported_membership_id": membership_id.strip().lower(),
                    "kimi_failed_count": kimi_failed_count,
                    "task_type": task_type,
                    "dead_lettered": dead_letter,
                    "next_status": next_status,
                },
            )
            if dead_letter:
                self._record_operator_alert(
                    conn,
                    task_id=cleaned_task_id,
                    action="review_required_dead_letter",
                    message=f"{cleaned_task_id} moved to blocked_review after ambiguous failure",
                    category="dead_letter_lane",
                    metadata={"error_code": error_code.strip().lower(), "task_type": task_type},
                )
            updated = self._execute(
                conn,
                "SELECT * FROM tasks WHERE task_id = ?",
                (cleaned_task_id,),
            ).fetchone()
            conn.commit()

        return self._row_to_task(updated)

    def cancel_task(self, *, task_id: str, cancelled_by: str, reason: str = "") -> dict[str, Any]:
        cleaned_task_id = task_id.strip()
        cleaned_actor = cancelled_by.strip()
        if not cleaned_task_id:
            raise ValueError("task_id is required")
        if not cleaned_actor:
            raise ValueError("cancelled_by is required")

        now_iso = _utc_iso_now()
        with self._connect() as conn:
            row = self._execute(
                conn,
                "SELECT * FROM tasks WHERE task_id = ?",
                (cleaned_task_id,),
            ).fetchone()
            if not row:
                raise KeyError(cleaned_task_id)

            current_status = str(row["status"] or "").strip().lower()
            if current_status == "completed":
                raise ValueError("completed tasks cannot be cancelled")
            if current_status == "cancelled":
                return self._row_to_task(row)

            existing_error = str(row["error_text"] or "").strip()
            note = reason.strip()
            if note:
                next_error = (
                    f"{existing_error} | cancelled: {note}"
                    if existing_error
                    else f"cancelled: {note}"
                )
            else:
                next_error = existing_error

            self._execute(
                conn,
                """
                UPDATE tasks
                SET status = 'cancelled',
                    error_text = ?,
                    lease_owner = NULL,
                    lease_expires_unix = NULL,
                    updated_at = ?
                WHERE task_id = ?
                """,
                (next_error, now_iso, cleaned_task_id),
            )
            self._record_event(
                conn,
                event_type="task_cancelled",
                task_id=cleaned_task_id,
                agent_id=cleaned_actor,
                payload={
                    "from_status": current_status,
                    "reason": note,
                },
            )
            updated = self._execute(
                conn,
                "SELECT * FROM tasks WHERE task_id = ?",
                (cleaned_task_id,),
            ).fetchone()
            conn.commit()

        return self._row_to_task(updated)

    def list_tasks(self, *, status: str | None, limit: int = 100) -> list[dict[str, Any]]:
        effective_limit = max(1, min(limit, 500))
        with self._connect() as conn:
            self._run_watchdog_recovery(conn, heartbeat_ttl_seconds=120)
            if status:
                rows = self._execute(
                    conn,
                    """
                    SELECT * FROM tasks
                    WHERE status = ?
                    ORDER BY priority ASC, created_at ASC
                    LIMIT ?
                    """,
                    (status, effective_limit),
                ).fetchall()
            else:
                rows = self._execute(
                    conn,
                    """
                    SELECT * FROM tasks
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (effective_limit,),
                ).fetchall()
            conn.commit()
        return [self._row_to_task(row) for row in rows]

    def list_events(self, *, limit: int = 100, task_id: str | None = None) -> list[dict[str, Any]]:
        effective_limit = max(1, min(limit, 500))
        with self._connect() as conn:
            if task_id:
                rows = self._execute(
                    conn,
                    """
                    SELECT * FROM task_events
                    WHERE task_id = ?
                    ORDER BY created_at_unix DESC, id DESC
                    LIMIT ?
                    """,
                    (task_id, effective_limit),
                ).fetchall()
            else:
                rows = self._execute(
                    conn,
                    """
                    SELECT * FROM task_events
                    ORDER BY created_at_unix DESC, id DESC
                    LIMIT ?
                    """,
                    (effective_limit,),
                ).fetchall()

        events: list[dict[str, Any]] = []
        for row in rows:
            events.append(
                {
                    "id": int(row["id"]),
                    "event_id": row["event_id"],
                    "task_id": row["task_id"],
                    "agent_id": row["agent_id"],
                    "event_type": row["event_type"],
                    "payload": _decode_json(row["payload_json"], {}),
                    "created_at": row["created_at"],
                }
            )
        return events

    def overview(self, *, heartbeat_ttl_seconds: int = 120) -> dict[str, Any]:
        now_unix = _utc_epoch_now()
        window_seconds = _slo_window_seconds()
        since_unix = now_unix - window_seconds
        with self._connect() as conn:
            self._run_watchdog_recovery(conn, heartbeat_ttl_seconds=heartbeat_ttl_seconds)
            task_rows = self._execute(
                conn,
                """
                SELECT status, payload_json
                FROM tasks
                """,
            ).fetchall()
            agent_rows = self._execute(conn, "SELECT * FROM agents").fetchall()
            event_rows = self._execute(
                conn,
                """
                SELECT event_type, payload_json, created_at_unix
                FROM task_events
                WHERE created_at_unix >= ?
                ORDER BY created_at_unix DESC, id DESC
                LIMIT 5000
                """,
                (since_unix,),
            ).fetchall()
            conn.commit()

        counts = {
            "queued": 0,
            "leased": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "blocked_review": 0,
        }
        kpi_counts = {
            "queued": 0,
            "leased": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "blocked_review": 0,
        }
        excluded_low_signal = 0
        for row in task_rows:
            status = str(row["status"] or "").strip()
            if not status:
                continue
            if status not in counts:
                counts[status] = 0
            counts[status] += 1

            payload = _decode_json(row["payload_json"], {})
            if not isinstance(payload, dict):
                payload = {}
            task_class = _normalized_task_class(payload)
            if task_class in _LOW_SIGNAL_TASK_CLASSES:
                excluded_low_signal += 1
                continue
            if status not in kpi_counts:
                kpi_counts[status] = 0
            kpi_counts[status] += 1

        created_count = 0
        completed_count = 0
        lease_count = 0
        stale_lease_count = 0
        autocancel_count = 0
        for row in event_rows:
            event_type = str(row["event_type"] or "").strip().lower()
            payload = _decode_json(row["payload_json"], {})
            if not isinstance(payload, dict):
                payload = {}
            if event_type == "task_created":
                created_count += 1
            elif event_type == "task_completed":
                completed_count += 1
            elif event_type in {
                "task_leased",
                "task_lease_extended",
                "task_lease_expired_requeued",
            }:
                lease_count += 1
                if event_type == "task_lease_expired_requeued":
                    stale_lease_count += 1
            elif event_type == "task_failed_final":
                error_code = str(payload.get("error_code") or "").strip().lower()
                if "stale_lease" in error_code:
                    stale_lease_count += 1
            elif event_type == "task_auto_cancelled_low_signal":
                autocancel_count += 1

        agents = [
            self._row_to_agent(row, heartbeat_ttl_seconds=heartbeat_ttl_seconds)
            for row in agent_rows
        ]
        active_agents = [
            agent
            for agent in agents
            if str(agent.get("status") or "").strip().lower() != "disabled"
        ]
        online_active_agents = [agent for agent in active_agents if bool(agent.get("online"))]
        online_agents = len(online_active_agents)

        policy = load_runtime_policy()
        allowed_agent_ids = allowed_executor_agent_ids(policy)
        allowed_membership_ids = allowed_executor_membership_ids(policy)
        executor_candidates = active_agents
        if allowed_agent_ids or allowed_membership_ids:
            filtered: list[dict[str, Any]] = []
            for agent in active_agents:
                agent_id = str(agent.get("agent_id") or "").strip().lower()
                if not agent_id:
                    continue
                caps = (
                    agent.get("capabilities") if isinstance(agent.get("capabilities"), list) else []
                )
                memberships = {
                    str(cap).split(":", 1)[1].strip().lower()
                    for cap in caps
                    if str(cap).strip().lower().startswith("membership:")
                }
                labels = agent.get("labels") if isinstance(agent.get("labels"), dict) else {}
                for key in ("membership_id", "model_membership", "router_membership"):
                    value = str(labels.get(key) or "").strip().lower()
                    if value:
                        memberships.add(value)
                matches_agent = (agent_id in allowed_agent_ids) if allowed_agent_ids else True
                matches_membership = (
                    bool(memberships & allowed_membership_ids) if allowed_membership_ids else True
                )
                if matches_agent and matches_membership:
                    filtered.append(agent)
            executor_candidates = filtered
        executor_online = len([agent for agent in executor_candidates if bool(agent.get("online"))])
        executor_total = len(executor_candidates)
        nonexecutor_online = max(0, online_agents - executor_online)

        queue_depth = int(kpi_counts.get("queued", 0)) + int(kpi_counts.get("leased", 0))
        completion_rate_per_second = (
            (completed_count / float(window_seconds)) if window_seconds > 0 else 0.0
        )
        if queue_depth <= 0:
            queue_drain_seconds: float | None = 0.0
        elif completion_rate_per_second <= 0:
            queue_drain_seconds = None
        else:
            queue_drain_seconds = queue_depth / completion_rate_per_second
        stale_lease_rate = (stale_lease_count / float(lease_count)) if lease_count > 0 else 0.0
        autocancel_rate = (autocancel_count / float(created_count)) if created_count > 0 else 0.0

        queue_drain_threshold = _slo_queue_drain_threshold_seconds()
        stale_lease_threshold = _slo_stale_lease_rate_threshold()
        autocancel_threshold = _slo_autocancel_rate_threshold()
        slo_alerts: list[dict[str, Any]] = []
        if queue_depth > 0 and queue_drain_seconds is None:
            slo_alerts.append(
                {
                    "id": "queue_drain_unknown",
                    "severity": "high",
                    "message": "Queue has work but no completion throughput observed in SLO window.",
                }
            )
        elif queue_drain_seconds is not None and queue_drain_seconds > queue_drain_threshold:
            slo_alerts.append(
                {
                    "id": "queue_drain_time_breach",
                    "severity": "high",
                    "message": "Estimated queue drain time exceeds threshold.",
                    "value_seconds": int(queue_drain_seconds),
                    "threshold_seconds": queue_drain_threshold,
                }
            )
        if stale_lease_rate > stale_lease_threshold:
            slo_alerts.append(
                {
                    "id": "stale_lease_rate_breach",
                    "severity": "medium",
                    "message": "Stale lease rate exceeded threshold in SLO window.",
                    "value": round(stale_lease_rate, 4),
                    "threshold": round(stale_lease_threshold, 4),
                }
            )
        if autocancel_rate > autocancel_threshold:
            slo_alerts.append(
                {
                    "id": "autocancel_rate_breach",
                    "severity": "low",
                    "message": "Auto-cancel rate exceeded threshold (indicates noisy low-signal task flow).",
                    "value": round(autocancel_rate, 4),
                    "threshold": round(autocancel_threshold, 4),
                }
            )
        slo_status = "degraded" if slo_alerts else "ok"

        return {
            "generated_at": _utc_iso_now(),
            "backend": self.backend_status(),
            "agents_total": len(active_agents),
            "agents_online": online_agents,
            "agents_executor_total": executor_total,
            "agents_executor_online": executor_online,
            "agents_nonexecutor_online": nonexecutor_online,
            "agents_registered": len(agents),
            "agents_disabled": max(0, len(agents) - len(active_agents)),
            "tasks": counts,
            "kpi_tasks": kpi_counts,
            "kpi_excluded_low_signal": excluded_low_signal,
            "slo": {
                "status": slo_status,
                "window_seconds": window_seconds,
                "queue_drain_time_seconds": (
                    None if queue_drain_seconds is None else int(queue_drain_seconds)
                ),
                "stale_lease_rate": round(stale_lease_rate, 4),
                "autocancel_rate": round(autocancel_rate, 4),
                "alerts": slo_alerts,
                "thresholds": {
                    "queue_drain_time_seconds_max": queue_drain_threshold,
                    "stale_lease_rate_max": round(stale_lease_threshold, 4),
                    "autocancel_rate_max": round(autocancel_threshold, 4),
                },
                "event_counts": {
                    "created": created_count,
                    "completed": completed_count,
                    "leases": lease_count,
                    "stale_leases": stale_lease_count,
                    "autocancelled_low_signal": autocancel_count,
                },
            },
        }
