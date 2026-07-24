"""Repo-grounded Palantir Foundry readiness helpers.

This module inspects local Sapphire artifacts and a small set of common
environment variable names without ever returning secret values. The goal is to
answer: "Is Sapphire's data surface ready for Foundry, and is repo-side auth
configured enough to start wiring it up?"
"""

from __future__ import annotations

import hashlib
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
    # Tranche-3 expansion (ontology v0.2.0).
    "IntelVectorRecord": ("id", "record_id", "text", "source", "embedding_dims"),
    "TelegramIntelMessage": (
        "id",
        "canonical_id",
        "channel_id",
        "message_id",
        "text",
    ),
    "HyperliquidSignal": ("id", "topic", "symbol", "signal_type", "published_at"),
    "OODAPacket": ("id", "request_hash", "observe", "orient", "decide", "model"),
    "ThreatIndicator": (
        "id",
        "advisory_id",
        "title",
        "severity",
        "ioc_total",
    ),
}

_SYNC_HISTORY_REQUIRED_FIELDS = ("ok", "timestamp", "duration_s")
_SYNC_HISTORY_FILE = "data/foundry_sync_history.jsonl"
_REGIONAL_MANIFEST_FILE = "data/foundry/regional-intel/manifest.json"
_REGIONAL_OBJECT_TYPES = ("Region", "IntelItem", "IntelSourceHealth")
_REGIONAL_MANIFEST_FIELDS = (
    "schema_version",
    "generated_at",
    "snapshot_updated_at",
    "region",
    "object_types",
    "dropped_rows",
    "source_health_summary",
    "policy",
)
_DROPPED_ROW_DETAIL_FIELDS = (
    "reason",
    "object_type",
    "kind",
    "item_id",
    "region_id",
    "missing_fields",
)


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
        return json.loads(path.read_text(encoding="utf-8"))
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


def _missing_required_fields(obj: dict[str, Any], required_fields: tuple[str, ...]) -> list[str]:
    return [field for field in required_fields if field not in obj or obj.get(field) is None]


def _sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _count_ndjson_rows(path: Path) -> int | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return sum(1 for line in fh if line.strip())
    except OSError:
        return None


def _is_nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _count_bucket_total(
    bucket: dict[str, Any],
    *,
    errors: list[str],
    error_prefix: str,
) -> int:
    total = 0
    for key, value in bucket.items():
        if not _is_nonnegative_int(value):
            errors.append(f"{error_prefix}.invalid_count:{key}")
            continue
        total += value
    return total


def _audit_regional_manifest_v2(root: Path) -> dict[str, Any]:
    """Validate the regional-intel manifest v2 contract without exposing rows."""
    manifest_path = root / _REGIONAL_MANIFEST_FILE
    regional_dir = manifest_path.parent
    export_files_present = any(
        (regional_dir / f"{object_type}.ndjson").is_file() for object_type in _REGIONAL_OBJECT_TYPES
    )
    summary: dict[str, Any] = {
        "path": _REGIONAL_MANIFEST_FILE,
        "exists": manifest_path.is_file(),
        "status": "absent",
        "schema_version": None,
        "generated_at": None,
        "snapshot_updated_at": None,
        "region": None,
        "errors": [],
        "object_types": {},
        "dropped_rows": {
            "total": 0,
            "by_reason": {},
            "by_object_type": {},
            "by_kind": {},
            "missing_fields": {},
            "details": 0,
        },
        "source_health_summary": {},
        "policy": {"present": False, "keys": []},
    }
    errors: list[str] = summary["errors"]

    if not manifest_path.is_file():
        if export_files_present:
            summary["status"] = "missing"
            errors.append("manifest_missing_with_regional_exports")
        return summary

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        summary["status"] = "invalid"
        errors.append("manifest_unreadable_or_invalid_json")
        return summary

    if not isinstance(manifest, dict):
        summary["status"] = "invalid"
        errors.append("manifest_not_object")
        return summary

    missing_top = [
        field
        for field in _REGIONAL_MANIFEST_FIELDS
        if field not in manifest or manifest.get(field) is None
    ]
    errors.extend(f"missing_top_level:{field}" for field in missing_top)
    if manifest.get("schema_version") != 2:
        errors.append("schema_version_not_2")

    summary["schema_version"] = manifest.get("schema_version")
    summary["generated_at"] = manifest.get("generated_at")
    summary["snapshot_updated_at"] = manifest.get("snapshot_updated_at")
    summary["region"] = manifest.get("region")

    object_types = manifest.get("object_types")
    if not isinstance(object_types, dict):
        errors.append("object_types_not_object")
        object_types = {}
    for object_type in _REGIONAL_OBJECT_TYPES:
        spec = object_types.get(object_type)
        type_summary: dict[str, Any] = {
            "filename": None,
            "rows": None,
            "file_sha256_present": False,
            "file_sha256_matches": None,
            "row_hashes": 0,
            "path_present": False,
            "file_present": False,
            "actual_rows": None,
        }
        if not isinstance(spec, dict):
            errors.append(f"object_type_missing_or_invalid:{object_type}")
            summary["object_types"][object_type] = type_summary
            continue

        filename = spec.get("filename")
        rows = spec.get("rows")
        file_sha256 = spec.get("file_sha256")
        row_hashes = spec.get("row_hashes")
        type_summary.update(
            {
                "filename": filename,
                "rows": rows,
                "file_sha256_present": bool(file_sha256),
                "row_hashes": len(row_hashes) if isinstance(row_hashes, list) else 0,
                "path_present": bool(spec.get("path")),
            }
        )
        for field in ("filename", "rows", "file_sha256", "row_hashes"):
            if field not in spec or spec.get(field) is None:
                errors.append(f"{object_type}.missing:{field}")
        if not isinstance(filename, str) or not filename.endswith(".ndjson"):
            errors.append(f"{object_type}.filename_invalid")
        if not _is_nonnegative_int(rows):
            errors.append(f"{object_type}.rows_invalid")
        if not isinstance(row_hashes, list):
            errors.append(f"{object_type}.row_hashes_invalid")
        elif _is_nonnegative_int(rows) and len(row_hashes) != rows:
            errors.append(f"{object_type}.row_hashes_count_mismatch")

        candidate = regional_dir / str(filename or f"{object_type}.ndjson")
        if candidate.is_file():
            type_summary["file_present"] = True
            type_summary["actual_rows"] = _count_ndjson_rows(candidate)
            if file_sha256:
                type_summary["file_sha256_matches"] = _sha256_file(candidate) == file_sha256
                if type_summary["file_sha256_matches"] is False:
                    errors.append(f"{object_type}.file_sha256_mismatch")
            if _is_nonnegative_int(rows) and type_summary["actual_rows"] != rows:
                errors.append(f"{object_type}.row_count_mismatch")
        summary["object_types"][object_type] = type_summary

    dropped_rows = manifest.get("dropped_rows")
    if not isinstance(dropped_rows, dict):
        errors.append("dropped_rows_not_object")
        dropped_rows = {}
    details_raw = dropped_rows.get("details")
    if details_raw is None:
        details = []
    elif isinstance(details_raw, list):
        details = details_raw
    else:
        errors.append("dropped_rows.details_not_list")
        details = []
    by_object_type: Counter[str] = Counter()
    by_kind: Counter[str] = Counter()
    missing_fields: Counter[str] = Counter()
    for detail in details:
        if not isinstance(detail, dict):
            errors.append("dropped_rows.detail_not_object")
            continue
        for field in _DROPPED_ROW_DETAIL_FIELDS:
            if field not in detail:
                errors.append(f"dropped_rows.detail_missing:{field}")
        if detail.get("object_type"):
            by_object_type[str(detail["object_type"])] += 1
        if detail.get("kind"):
            by_kind[str(detail["kind"])] += 1
        missing_fields_value = detail.get("missing_fields")
        if missing_fields_value is None:
            continue
        if not isinstance(missing_fields_value, list):
            errors.append("dropped_rows.detail_missing_fields_not_list")
            continue
        for field in missing_fields_value:
            missing_fields[str(field)] += 1
    by_reason_raw = dropped_rows.get("by_reason")
    if by_reason_raw is None:
        by_reason = {}
    elif isinstance(by_reason_raw, dict):
        by_reason = by_reason_raw
    else:
        errors.append("dropped_rows.by_reason_not_object")
        by_reason = {}
    total = dropped_rows.get("total")
    if not _is_nonnegative_int(total):
        errors.append("dropped_rows.total_invalid")
        total = 0
    if (
        _count_bucket_total(
            by_reason,
            errors=errors,
            error_prefix="dropped_rows.by_reason",
        )
        != total
    ):
        errors.append("dropped_rows.by_reason_total_mismatch")
    if len(details) != total:
        errors.append("dropped_rows.details_count_mismatch")
    summary["dropped_rows"] = {
        "total": total,
        "by_reason": dict(sorted(by_reason.items())),
        "by_object_type": dict(sorted(by_object_type.items())),
        "by_kind": dict(sorted(by_kind.items())),
        "missing_fields": dict(sorted(missing_fields.items())),
        "details": len(details),
    }

    source_health = manifest.get("source_health_summary")
    if not isinstance(source_health, dict):
        errors.append("source_health_summary_not_object")
        source_health = {}
    for field in (
        "total_sources",
        "live_pull_sources",
        "total_item_count",
        "by_status",
        "by_category",
        "by_region",
    ):
        if field not in source_health:
            errors.append(f"source_health_summary.missing:{field}")
    for field in ("total_sources", "live_pull_sources", "total_item_count"):
        if field in source_health and not _is_nonnegative_int(source_health.get(field)):
            errors.append(f"source_health_summary.invalid_count:{field}")
    for field in ("by_status", "by_category", "by_region"):
        if field in source_health and not isinstance(source_health.get(field), dict):
            errors.append(f"source_health_summary.invalid_bucket:{field}")
    summary["source_health_summary"] = {
        "total_sources": source_health.get("total_sources"),
        "live_pull_sources": source_health.get("live_pull_sources"),
        "total_item_count": source_health.get("total_item_count"),
        "by_status": source_health.get("by_status")
        if isinstance(source_health.get("by_status"), dict)
        else {},
        "by_category": source_health.get("by_category")
        if isinstance(source_health.get("by_category"), dict)
        else {},
        "by_region": source_health.get("by_region")
        if isinstance(source_health.get("by_region"), dict)
        else {},
    }

    policy = manifest.get("policy")
    summary["policy"] = {
        "present": isinstance(policy, dict),
        "keys": sorted(policy.keys()) if isinstance(policy, dict) else [],
    }
    if not isinstance(policy, dict):
        errors.append("policy_not_object")

    summary["status"] = "ready" if not errors else "schema_warning"
    return summary


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
        for line in history_path.read_text(encoding="utf-8").splitlines():
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

    regional_manifest = _audit_regional_manifest_v2(root)
    manifest_blocks_ready = regional_manifest["status"] in {
        "invalid",
        "missing",
        "schema_warning",
    }

    if totals["transform_errors"]:
        status = "error"
    elif totals["invalid_objects"] or totals["missing_required_fields"] or manifest_blocks_ready:
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
        "regional_manifest": regional_manifest,
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
        next_step = "Push the first Sapphire operational datasets into Foundry, then back them with Ontology objects."
    elif connector or total_files:
        auth_mode = "not-configured"
        status = "partial"
        badge = "DATA READY"
        if connector:
            connection_label = "Sapphire has a Foundry connector record, but repo-side auth signals are not configured."
        else:
            connection_label = "Sapphire artifacts are ready for Foundry, but repo-side auth signals are not configured."
        next_step = (
            "Create a Developer Console custom application, grant project access, and wire one "
            "batch ingestion path before attempting actions or agents."
        )
    else:
        auth_mode = "not-configured"
        status = "planned"
        badge = "PLANNED"
        connection_label = "No repo-side Foundry linkage was detected yet."
        next_step = "Register a Foundry custom application first, then start with one dataset sync and one Workshop app."

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
