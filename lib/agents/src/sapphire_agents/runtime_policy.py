"""Runtime policy for agent/executor membership and capability whitelisting.

Loads the agent_runtime_policy.json (file or Firestore backend) that gates
which agents may execute which command classes. Consumed by the orchestrator
before any OpenClaw/NemoClaw dispatch; cached with a 5s TTL.
"""

from __future__ import annotations

import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_CACHE: dict[str, Any] = {"key": "", "mtime": 0.0, "ts": 0.0, "payload": None}
_FIRESTORE_CACHE_TTL_SECONDS = 5.0


def _now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()


def runtime_policy_path() -> Path:
    override = str(os.getenv("AGENTIC_RUNTIME_POLICY_PATH") or "").strip()
    if override:
        return Path(override).expanduser()
    return Path(__file__).resolve().parent / "data" / "agent_runtime_policy.json"


def _runtime_policy_backend_kind() -> str:
    # Explicit file path always wins for tests/local overrides.
    if str(os.getenv("AGENTIC_RUNTIME_POLICY_PATH") or "").strip():
        return "file"
    backend = str(os.getenv("AGENTIC_RUNTIME_POLICY_BACKEND") or "file").strip().lower()
    if backend in {"firestore", "gcp_firestore"}:
        return "firestore"
    return "file"


def _runtime_policy_firestore_project() -> str:
    return (
        str(os.getenv("AGENTIC_RUNTIME_POLICY_FIRESTORE_PROJECT") or "").strip()
        or str(os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()
        or str(os.getenv("GCP_PROJECT_ID") or "").strip()
    )


def _runtime_policy_firestore_collection() -> str:
    return str(os.getenv("AGENTIC_RUNTIME_POLICY_FIRESTORE_COLLECTION") or "agentic_runtime_meta").strip() or "agentic_runtime_meta"


def _runtime_policy_firestore_document() -> str:
    return str(os.getenv("AGENTIC_RUNTIME_POLICY_FIRESTORE_DOCUMENT") or "executor_policy").strip() or "executor_policy"


def _runtime_policy_cache_key() -> str:
    backend = _runtime_policy_backend_kind()
    if backend == "firestore":
        return f"firestore:{_runtime_policy_firestore_project()}:{_runtime_policy_firestore_collection()}:{_runtime_policy_firestore_document()}"
    return f"file:{runtime_policy_path()}"


def _firestore_runtime_policy_load() -> dict[str, Any] | None:
    project = _runtime_policy_firestore_project()
    if not project:
        return None
    try:
        from google.cloud import firestore  # type: ignore
    except Exception:
        return None
    client = firestore.Client(project=project)
    doc = client.collection(_runtime_policy_firestore_collection()).document(_runtime_policy_firestore_document()).get()
    if not getattr(doc, "exists", False):
        return None
    data = doc.to_dict() or {}
    return data if isinstance(data, dict) else None


def _firestore_runtime_policy_save(payload: dict[str, Any]) -> None:
    project = _runtime_policy_firestore_project()
    if not project:
        raise RuntimeError("firestore runtime policy backend requires GOOGLE_CLOUD_PROJECT or AGENTIC_RUNTIME_POLICY_FIRESTORE_PROJECT")
    try:
        from google.cloud import firestore  # type: ignore
    except Exception as exc:
        raise RuntimeError("google-cloud-firestore is not available") from exc
    client = firestore.Client(project=project)
    client.collection(_runtime_policy_firestore_collection()).document(_runtime_policy_firestore_document()).set(dict(payload))


def _sanitize_values(values: list[str] | None) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        text = str(item or "").strip().lower()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _coerce_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _default_policy_payload() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": _now_iso(),
        "mode": "open",
        "description": "No executor restrictions.",
        "allowed_executor_agent_ids": [],
        "allowed_executor_membership_ids": [],
        "updated_by": "system",
    }


def _normalize_policy_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    base = _default_policy_payload()
    if not isinstance(payload, dict):
        return base

    normalized = dict(base)
    normalized["version"] = int(payload.get("version") or 1)
    normalized["updated_at"] = str(payload.get("updated_at") or _now_iso())
    normalized["mode"] = str(payload.get("mode") or "open").strip().lower() or "open"
    normalized["description"] = str(payload.get("description") or "").strip() or base["description"]
    normalized["allowed_executor_agent_ids"] = _sanitize_values(payload.get("allowed_executor_agent_ids"))
    normalized["allowed_executor_membership_ids"] = _sanitize_values(payload.get("allowed_executor_membership_ids"))
    normalized["updated_by"] = str(payload.get("updated_by") or "system").strip() or "system"
    return normalized


def _apply_env_overrides(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    env_agents = str(os.getenv("AGENTIC_ALLOWED_LEASE_AGENT_IDS") or "").strip()
    env_memberships = str(os.getenv("AGENTIC_ALLOWED_LEASE_MEMBERSHIPS") or "").strip()
    applied = False
    if env_agents:
        normalized["allowed_executor_agent_ids"] = _sanitize_values(
            [item for item in env_agents.split(",") if item.strip()]
        )
        applied = True
    if env_memberships:
        normalized["allowed_executor_membership_ids"] = _sanitize_values(
            [item for item in env_memberships.split(",") if item.strip()]
        )
        applied = True
    if applied:
        if str(normalized.get("mode") or "").strip().lower() == "open":
            normalized["mode"] = "custom"
        normalized["description"] = (
            str(normalized.get("description") or "").strip() + " (effective env overrides applied)"
        ).strip()
    return normalized


def _expected_executor_policy_from_env() -> dict[str, Any]:
    mode = str(os.getenv("AGENTIC_EXPECTED_EXECUTOR_POLICY_MODE") or "").strip().lower()
    agent_ids = _sanitize_values(
        [item for item in str(os.getenv("AGENTIC_EXPECTED_EXECUTOR_AGENT_IDS") or "").split(",") if item.strip()]
    )
    membership_ids = _sanitize_values(
        [item for item in str(os.getenv("AGENTIC_EXPECTED_EXECUTOR_MEMBERSHIP_IDS") or "").split(",") if item.strip()]
    )
    enabled = bool(mode or agent_ids or membership_ids)
    return {
        "enabled": enabled,
        "mode": mode,
        "allowed_executor_agent_ids": agent_ids,
        "allowed_executor_membership_ids": membership_ids,
    }


def _expected_policy_lock_enabled() -> bool:
    return _coerce_bool(os.getenv("AGENTIC_ENFORCE_EXPECTED_EXECUTOR_POLICY", "false"))


def _apply_expected_policy_overlay(payload: dict[str, Any]) -> dict[str, Any]:
    expected = _expected_executor_policy_from_env()
    if not _expected_policy_lock_enabled() or not bool(expected.get("enabled")):
        return payload

    normalized = dict(payload)
    expected_mode = str(expected.get("mode") or "").strip().lower()
    expected_agents = _sanitize_values(expected.get("allowed_executor_agent_ids"))
    expected_memberships = _sanitize_values(expected.get("allowed_executor_membership_ids"))

    if expected_mode:
        normalized["mode"] = expected_mode
    if expected_agents:
        normalized["allowed_executor_agent_ids"] = expected_agents
    if expected_memberships:
        normalized["allowed_executor_membership_ids"] = expected_memberships
    normalized["effective_policy_lock_applied"] = True
    normalized["effective_policy_lock_expected"] = {
        "mode": expected_mode,
        "allowed_executor_agent_ids": expected_agents,
        "allowed_executor_membership_ids": expected_memberships,
    }
    normalized["effective_observed_updated_at"] = str(payload.get("updated_at") or "")
    normalized["effective_observed_updated_by"] = str(payload.get("updated_by") or "")
    if str(normalized.get("description") or "").strip():
        normalized["description"] = (
            str(normalized.get("description") or "").strip() + " (effective expected-policy lock overlay applied)"
        )
    return normalized


def load_runtime_policy_observed(force_refresh: bool = False) -> dict[str, Any]:
    backend = _runtime_policy_backend_kind()
    cache_key = _runtime_policy_cache_key()

    if backend == "firestore":
        if not force_refresh and (
            _CACHE.get("payload") is not None
            and str(_CACHE.get("key") or "") == cache_key
            and (time.time() - float(_CACHE.get("ts") or 0.0)) < _FIRESTORE_CACHE_TTL_SECONDS
        ):
            return _apply_env_overrides(dict(_CACHE["payload"]))
        parsed = _firestore_runtime_policy_load()
        if not isinstance(parsed, dict):
            payload = _default_policy_payload()
            try:
                _firestore_runtime_policy_save(payload)
            except Exception:
                # Fall back to default payload in-memory if Firestore write is unavailable.
                payload = _default_policy_payload()
            _CACHE.update({"key": cache_key, "mtime": 0.0, "ts": time.time(), "payload": payload})
            return _apply_env_overrides(dict(payload))

        payload = _normalize_policy_payload(parsed)
        _CACHE.update({"key": cache_key, "mtime": 0.0, "ts": time.time(), "payload": payload})
        return _apply_env_overrides(dict(payload))

    path = runtime_policy_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        payload = _default_policy_payload()
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        _CACHE.update({"key": cache_key, "mtime": path.stat().st_mtime, "ts": time.time(), "payload": payload})
        return _apply_env_overrides(payload)

    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0

    if not force_refresh:
        cached_path = str(_CACHE.get("key") or "")
        cached_mtime = float(_CACHE.get("mtime") or 0.0)
        cached_payload = _CACHE.get("payload")
        if cached_payload and cached_path == cache_key and cached_mtime == mtime:
            return _apply_env_overrides(dict(cached_payload))

    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        parsed = _default_policy_payload()

    payload = _normalize_policy_payload(parsed if isinstance(parsed, dict) else None)
    _CACHE.update({"key": cache_key, "mtime": mtime, "ts": time.time(), "payload": payload})
    return _apply_env_overrides(payload)


def load_runtime_policy(force_refresh: bool = False) -> dict[str, Any]:
    observed = load_runtime_policy_observed(force_refresh=force_refresh)
    return _apply_expected_policy_overlay(dict(observed))


def save_runtime_policy(payload: dict[str, Any], *, updated_by: str = "system") -> dict[str, Any]:
    normalized = _normalize_policy_payload(payload)
    normalized["updated_at"] = _now_iso()
    normalized["updated_by"] = str(updated_by or "system").strip() or "system"
    backend = _runtime_policy_backend_kind()
    cache_key = _runtime_policy_cache_key()
    if backend == "firestore":
        _firestore_runtime_policy_save(normalized)
        _CACHE.update({"key": cache_key, "mtime": 0.0, "ts": time.time(), "payload": normalized})
        return normalized

    path = runtime_policy_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, indent=2), encoding="utf-8")
    try:
        mtime = path.stat().st_mtime
    except OSError:
        mtime = 0.0
    _CACHE.update({"key": cache_key, "mtime": mtime, "ts": time.time(), "payload": normalized})
    return normalized


def allowed_executor_agent_ids(policy: dict[str, Any] | None = None) -> set[str]:
    source = policy if isinstance(policy, dict) else load_runtime_policy()
    values = _sanitize_values(source.get("allowed_executor_agent_ids"))
    env_override = str(os.getenv("AGENTIC_ALLOWED_LEASE_AGENT_IDS") or "").strip()
    if env_override:
        values = _sanitize_values([item for item in env_override.split(",") if item.strip()])
    return set(values)


def allowed_executor_membership_ids(policy: dict[str, Any] | None = None) -> set[str]:
    source = policy if isinstance(policy, dict) else load_runtime_policy()
    values = _sanitize_values(source.get("allowed_executor_membership_ids"))
    env_override = str(os.getenv("AGENTIC_ALLOWED_LEASE_MEMBERSHIPS") or "").strip()
    if env_override:
        values = _sanitize_values([item for item in env_override.split(",") if item.strip()])
    return set(values)
