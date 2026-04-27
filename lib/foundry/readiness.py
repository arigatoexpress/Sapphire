"""Repo-grounded Palantir Foundry readiness helpers.

This module inspects local Sapphire artifacts and a small set of common
environment variable names without ever returning secret values. The goal is to
answer: "Is Sapphire's data surface ready for Foundry, and is repo-side auth
configured enough to start wiring it up?"
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_URL_ENV_VARS = (
    "PALANTIR_FOUNDRY_URL",
    "FOUNDRY_URL",
)
_TOKEN_ENV_VARS = (
    "PALANTIR_FOUNDRY_TOKEN",
    "FOUNDRY_TOKEN",
    "FOUNDRY_API_TOKEN",
    "PALANTIR_API_TOKEN",
)
_CLIENT_ID_ENV_VARS = (
    "PALANTIR_FOUNDRY_CLIENT_ID",
    "FOUNDRY_CLIENT_ID",
)
_CLIENT_SECRET_ENV_VARS = (
    "PALANTIR_FOUNDRY_CLIENT_SECRET",
    "FOUNDRY_CLIENT_SECRET",
)
_S3_KEY_ENV_VARS = (
    "PALANTIR_FOUNDRY_S3_ACCESS_KEY_ID",
    "FOUNDRY_S3_ACCESS_KEY_ID",
)
_S3_SECRET_ENV_VARS = (
    "PALANTIR_FOUNDRY_S3_SECRET_ACCESS_KEY",
    "FOUNDRY_S3_SECRET_ACCESS_KEY",
)

_DATASET_GROUPS = (
    {
        "id": "system-events",
        "label": "System Events",
        "patterns": ("data/system_events.jsonl",),
        "transport": "Dataset upload or S3-compatible API",
        "ontology": ("AgentRun", "Incident", "Task", "Service"),
    },
    {
        "id": "ops-telemetry",
        "label": "Health + Metrics",
        "patterns": ("data/health/*.ndjson", "data/metrics/*.ndjson"),
        "transport": "Batch dataset sync",
        "ontology": ("Service", "ModelEndpoint", "Incident"),
    },
    {
        "id": "market-forecasts",
        "label": "Predictions + Signals",
        "patterns": (
            "data/trading_predictions.jsonl",
            "data/trading_signals.jsonl",
            "data/intelligence/*/predictions.json",
        ),
        "transport": "Batch dataset sync",
        "ontology": ("Asset", "Signal", "PredictionRun", "PaperTrade"),
    },
    {
        "id": "paper-trading",
        "label": "Paper Trading State",
        "patterns": (
            "data/paper_trading.jsonl",
            "data/paper_portfolio.json",
            "data/performance/signals.jsonl",
        ),
        "transport": "Batch dataset sync",
        "ontology": ("PaperTrade", "PortfolioSnapshot", "Signal"),
    },
    {
        "id": "threat-intel",
        "label": "Threat Intel",
        "patterns": (
            "data/threat_intel/*.md",
            "data/intelligence/*/threats.json",
        ),
        "transport": "Media sets + extracted datasets",
        "ontology": ("Threat", "ThreatObservation", "IntelItem", "Region"),
    },
    {
        "id": "governance",
        "label": "Decisions + Research",
        "patterns": (
            "data/decisions/*.jsonl",
            "data/trading_research.jsonl",
            "data/market_pulse/*.md",
        ),
        "transport": "Batch dataset sync + media sets",
        "ontology": ("Decision", "IntelItem", "Task", "Region"),
    },
    {
        "id": "regional-intel",
        "label": "Regional Intelligence",
        "patterns": (
            "data/foundry/regional-intel/Region.ndjson",
            "data/foundry/regional-intel/IntelItem.ndjson",
            "data/foundry/regional-intel/IntelSourceHealth.ndjson",
            "data/foundry/regional-intel/manifest.json",
        ),
        "transport": "Sibling workbench export + batch dataset sync",
        "ontology": ("Region", "IntelItem", "IntelSourceHealth"),
    },
)

_OBJECT_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "PaperTrade": ("id", "symbol", "direction", "action", "opened_at"),
    "Alert": ("id", "title", "severity", "category", "source", "timestamp"),
    "ServiceHealth": ("id", "service", "status", "last_check"),
    "ThreatIntel": ("id", "title", "source", "published_at"),
    "DailyBrief": ("id", "date", "title"),
    "Region": ("object_id", "region_id", "name", "snapshot_updated_at"),
    "IntelItem": (
        "object_id",
        "item_id",
        "kind",
        "region_id",
        "title",
        "source_name",
        "source_url",
        "snapshot_updated_at",
    ),
    "IntelSourceHealth": (
        "object_id",
        "source_key",
        "name",
        "status",
        "snapshot_updated_at",
    ),
}

_SYNC_HISTORY_REQUIRED_FIELDS = ("ok", "timestamp", "duration_s")
_SYNC_HISTORY_FILE = "data/foundry_sync_history.jsonl"


def _repo_root() -> Path:
    override = os.getenv("SAPPHIRE_REPO_ROOT")
    if override:
        return Path(override).expanduser()

    home_repo = Path.home() / "Code" / "Sapphire"
    local_repo = Path(__file__).resolve().parents[2]
    for candidate in (local_repo, home_repo):
        if (candidate / "lib" / "foundry").exists() or (candidate / "AGENTS.md").exists():
            return candidate
    return local_repo


def _configured_vars(names: tuple[str, ...]) -> list[str]:
    return [name for name in names if os.getenv(name)]


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _match_files(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    matches: dict[Path, None] = {}
    for pattern in patterns:
        for match in root.glob(pattern):
            if match.is_file():
                matches[match] = None
    return sorted(matches, key=lambda path: path.stat().st_mtime, reverse=True)


def _isoformat_timestamp(path: Path | None) -> str | None:
    if path is None:
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()


def _relative_path(root: Path, path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _find_foundry_connector(root: Path) -> dict | None:
    connector_doc = _load_json(root / "data" / "connectors.json")
    for connector in connector_doc.get("connectors") or []:
        haystack = " ".join(
            str(connector.get(key) or "")
            for key in ("id", "name", "description", "type", "protocol")
        ).lower()
        if "foundry" in haystack or "palantir" in haystack:
            return connector
    return None


def _missing_required_fields(
    obj: dict[str, Any], required_fields: tuple[str, ...]
) -> list[str]:
    return [
        field
        for field in required_fields
        if field not in obj or obj.get(field) is None
    ]


def _audit_sync_history(root: Path) -> dict[str, Any]:
    history_path = root / _SYNC_HISTORY_FILE
    summary: dict[str, Any] = {
        "path": _SYNC_HISTORY_FILE,
        "exists": history_path.is_file(),
        "records": 0,
        "malformed_lines": 0,
        "missing_required_fields": {},
        "recent_error_runs": 0,
        "latest_ok": None,
        "latest_dry_run": None,
        "latest_skipped": None,
        "latest_changed_types": 0,
        "latest_uploaded_types": 0,
    }
    if not history_path.is_file():
        return summary

    missing_counts: Counter[str] = Counter()
    latest: dict[str, Any] | None = None

    try:
        for line in history_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError:
                summary["malformed_lines"] += 1
                continue
            if not isinstance(record, dict):
                summary["malformed_lines"] += 1
                continue

            summary["records"] += 1
            latest = record
            if record.get("ok") is False:
                summary["recent_error_runs"] += 1
            for field in _SYNC_HISTORY_REQUIRED_FIELDS:
                if field not in record or record.get(field) is None:
                    missing_counts[field] += 1
    except OSError:
        summary["read_error"] = True
        return summary

    if latest is not None:
        changed_types = latest.get("changed_types")
        uploaded_types = latest.get("uploaded_types")
        summary["latest_ok"] = latest.get("ok")
        summary["latest_dry_run"] = latest.get("dry_run")
        summary["latest_skipped"] = latest.get("skipped")
        summary["latest_changed_types"] = (
            len(changed_types) if isinstance(changed_types, dict) else 0
        )
        summary["latest_uploaded_types"] = (
            len(uploaded_types) if isinstance(uploaded_types, dict) else 0
        )

    summary["missing_required_fields"] = dict(sorted(missing_counts.items()))
    return summary


def build_foundry_schema_audit(root: Path | None = None) -> dict[str, Any]:
    """Return a paste-safe audit of local Foundry object and sync schemas."""
    root = root or _repo_root()
    object_types: list[dict[str, Any]] = []
    totals = {
        "object_types": 0,
        "objects": 0,
        "invalid_objects": 0,
        "missing_required_fields": 0,
        "source_refs": 0,
        "transform_errors": 0,
    }

    from lib.foundry.ingestion import ALL_TRANSFORMS

    for object_type, transform in ALL_TRANSFORMS.items():
        required_fields = _OBJECT_REQUIRED_FIELDS.get(object_type, ("id",))
        missing_counts: Counter[str] = Counter()
        object_count = 0
        invalid_objects = 0
        source_refs = 0
        transform_error: str | None = None

        try:
            objects = transform(root)
        except Exception as exc:  # pragma: no cover - defensive dashboard path
            objects = []
            transform_error = exc.__class__.__name__

        for obj in objects:
            object_count += 1
            if not isinstance(obj, dict):
                invalid_objects += 1
                continue
            if obj.get("_sapphire_source"):
                source_refs += 1
            missing_counts.update(_missing_required_fields(obj, required_fields))

        missing_total = sum(missing_counts.values())
        if transform_error:
            status = "error"
        elif invalid_objects or missing_total:
            status = "schema_warning"
        elif object_count:
            status = "ready"
        else:
            status = "empty"

        totals["object_types"] += 1
        totals["objects"] += object_count
        totals["invalid_objects"] += invalid_objects
        totals["missing_required_fields"] += missing_total
        totals["source_refs"] += source_refs
        totals["transform_errors"] += 1 if transform_error else 0

        object_types.append(
            {
                "object_type": object_type,
                "status": status,
                "objects": object_count,
                "invalid_objects": invalid_objects,
                "required_fields": list(required_fields),
                "missing_required_fields": dict(sorted(missing_counts.items())),
                "source_refs": source_refs,
                "transform_error": transform_error,
            }
        )

    if totals["transform_errors"]:
        status = "error"
    elif totals["invalid_objects"] or totals["missing_required_fields"]:
        status = "schema_warning"
    elif totals["objects"]:
        status = "ready"
    else:
        status = "empty"

    return {
        "status": status,
        "object_types": object_types,
        "totals": totals,
        "sync_history_readback": _audit_sync_history(root),
    }


def build_foundry_readiness(root: Path | None = None) -> dict:
    """Return a safe readiness summary for Sapphire's Foundry integration."""
    root = root or _repo_root()

    url_vars = _configured_vars(_URL_ENV_VARS)
    token_vars = _configured_vars(_TOKEN_ENV_VARS)
    client_id_vars = _configured_vars(_CLIENT_ID_ENV_VARS)
    client_secret_vars = _configured_vars(_CLIENT_SECRET_ENV_VARS)
    s3_key_vars = _configured_vars(_S3_KEY_ENV_VARS)
    s3_secret_vars = _configured_vars(_S3_SECRET_ENV_VARS)

    has_url = bool(url_vars)
    has_token = bool(token_vars)
    has_oauth_client = bool(client_id_vars and client_secret_vars)
    has_s3_credentials = bool(s3_key_vars and s3_secret_vars)
    connector = _find_foundry_connector(root)

    dataset_groups = []
    total_files = 0
    latest_materialization: Path | None = None

    for spec in _DATASET_GROUPS:
        files = _match_files(root, spec["patterns"])
        total_files += len(files)
        latest = files[0] if files else None
        if latest is not None and (
            latest_materialization is None
            or latest.stat().st_mtime > latest_materialization.stat().st_mtime
        ):
            latest_materialization = latest
        dataset_groups.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "status": "ready" if files else "missing",
                "files": len(files),
                "latest_path": _relative_path(root, latest),
                "latest_modified_at": _isoformat_timestamp(latest),
                "transport": spec["transport"],
                "ontology": list(spec["ontology"]),
            }
        )

    if has_url and has_token:
        auth_mode = "token"
        status = "ready"
        badge = "CONNECTED"
        connection_label = "Repo-side Foundry URL and token are configured."
        next_step = (
            "Start with dataset sync for events, health, predictions, and threat intel, "
            "then model the Ontology over those datasets."
        )
    elif has_url and has_oauth_client:
        auth_mode = "oauth-client"
        status = "ready"
        badge = "CONNECTED"
        connection_label = "Repo-side Foundry URL and OAuth client credentials are configured."
        next_step = (
            "Use the custom application for OSDK/app work and reserve generic API or S3 flows "
            "for ingestion and administrative automation."
        )
    elif has_url and has_s3_credentials:
        auth_mode = "s3-api"
        status = "ready"
        badge = "CONNECTED"
        connection_label = "Repo-side Foundry URL and S3-compatible API credentials are configured."
        next_step = (
            "Push the first Sapphire operational datasets into Foundry, then back them with Ontology objects."
        )
    elif connector or total_files:
        auth_mode = "not-configured"
        status = "partial"
        badge = "DATA READY"
        if connector:
            connection_label = (
                "Sapphire has a Foundry connector record, but repo-side auth signals are not configured."
            )
        else:
            connection_label = (
                "Sapphire artifacts are ready for Foundry, but repo-side auth signals are not configured."
            )
        next_step = (
            "Create a Developer Console custom application, grant project access, and wire one "
            "batch ingestion path before attempting actions or agents."
        )
    else:
        auth_mode = "not-configured"
        status = "planned"
        badge = "PLANNED"
        connection_label = "No repo-side Foundry linkage was detected yet."
        next_step = (
            "Register a Foundry custom application first, then start with one dataset sync and one Workshop app."
        )

    return {
        "status": status,
        "badge": badge,
        "auth_mode": auth_mode,
        "connection_label": connection_label,
        "connector_registered": connector is not None,
        "connector_status": connector.get("status") if connector else None,
        "configured_envs": {
            "url": url_vars,
            "token": token_vars,
            "client_id": client_id_vars,
            "client_secret": client_secret_vars,
            "s3_key": s3_key_vars,
            "s3_secret": s3_secret_vars,
        },
        "recommended_first_app": "Sapphire Mission Control",
        "transport_hint": "S3 or dataset sync first, external transforms for live pull APIs later.",
        "dataset_groups": dataset_groups,
        "totals": {
            "groups": len(dataset_groups),
            "files": total_files,
        },
        "latest_materialization": _isoformat_timestamp(latest_materialization),
        "schema_audit": build_foundry_schema_audit(root),
        "next_step": next_step,
        "docs": {
            "strategy": "docs/palantir-foundry-strategy-2026-04-19.md",
            "ontology_schema": "docs/foundry-ontology-schema.md",
        },
    }
