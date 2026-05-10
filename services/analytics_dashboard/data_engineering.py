"""Admin-only data engineering readiness analysis for the Sapphire website.

This module is deliberately read-only. It inspects BigQuery table metadata and
windowed freshness for the sources the website claims to use, then pairs that
with the existing Vertex/Gemini narrative posture so operators can tell whether
the current data is good enough to build on.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

QueryRows = Callable[[str], list[dict[str, Any]]]

_IDENT_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class WarehouseSource:
    id: str
    label: str
    table: str
    timestamp_column: str
    timestamp_type: str
    freshness_slo_hours: int
    lookback_hours: int
    critical: bool
    lane: str
    rights_envelope: str
    output_policy: str
    gemini_use: str


WAREHOUSE_SOURCES: tuple[WarehouseSource, ...] = (
    WarehouseSource(
        id="service_health",
        label="Service health",
        table="service_health",
        timestamp_column="timestamp",
        timestamp_type="timestamp",
        freshness_slo_hours=1,
        lookback_hours=6,
        critical=True,
        lane="operations",
        rights_envelope="internal operational telemetry",
        output_policy="admin-only raw rows; public aggregates only",
        gemini_use="explain failover and service-risk posture from summarized counts",
    ),
    WarehouseSource(
        id="inference_metrics",
        label="Inference telemetry",
        table="inference_metrics",
        timestamp_column="timestamp",
        timestamp_type="timestamp",
        freshness_slo_hours=24,
        lookback_hours=24,
        critical=True,
        lane="models",
        rights_envelope="internal model-runtime telemetry",
        output_policy="admin-only tier detail; public model status only",
        gemini_use="identify model routing, latency, and error-rate gaps",
    ),
    WarehouseSource(
        id="trading_signals",
        label="Trading research signals",
        table="trading_signals",
        timestamp_column="timestamp",
        timestamp_type="timestamp",
        freshness_slo_hours=24,
        lookback_hours=24 * 7,
        critical=True,
        lane="markets",
        rights_envelope="internal research; paper-only execution boundary",
        output_policy="admin-only rows; public research context without advice",
        gemini_use="summarize evidence quality without buy/sell/hold language",
    ),
    WarehouseSource(
        id="predictions",
        label="Forecast rows",
        table="predictions",
        timestamp_column="timestamp",
        timestamp_type="timestamp",
        freshness_slo_hours=48,
        lookback_hours=24 * 7,
        critical=False,
        lane="markets",
        rights_envelope="internal research and model outputs",
        output_policy="admin-only rows until accuracy evidence is sufficient",
        gemini_use="compare forecast coverage with scored accuracy windows",
    ),
    WarehouseSource(
        id="market_regime",
        label="Market regime",
        table="market_regime",
        timestamp_column="timestamp",
        timestamp_type="timestamp",
        freshness_slo_hours=24,
        lookback_hours=24 * 7,
        critical=True,
        lane="markets",
        rights_envelope="derived market context",
        output_policy="public posture allowed; no personalized advice",
        gemini_use="turn regime/fear-greed data into plain-English context",
    ),
    WarehouseSource(
        id="daily_threats",
        label="Threat trend",
        table="daily_threats",
        timestamp_column="date",
        timestamp_type="date",
        freshness_slo_hours=36,
        lookback_hours=24 * 14,
        critical=False,
        lane="threats",
        rights_envelope="derived defensive cyber summary",
        output_policy="public aggregate trends allowed; no exploit detail",
        gemini_use="summarize defensive threat posture and caveats",
    ),
    WarehouseSource(
        id="brain_synthesis",
        label="Brain OODA history",
        table="brain_synthesis",
        timestamp_column="timestamp",
        timestamp_type="timestamp",
        freshness_slo_hours=6,
        lookback_hours=24 * 7,
        critical=False,
        lane="brain",
        rights_envelope="internal synthesized telemetry",
        output_policy="admin-only history; public sanitized current summary",
        gemini_use="compare current narrative with prior OODA packets",
    ),
    WarehouseSource(
        id="brain_llm_calls",
        label="Gemini audit trail",
        table="brain_llm_calls",
        timestamp_column="ts",
        timestamp_type="timestamp",
        freshness_slo_hours=24,
        lookback_hours=24 * 7,
        critical=False,
        lane="models",
        rights_envelope="internal prompt/usage audit metadata",
        output_policy="admin-only metadata; no prompt bodies in public UI",
        gemini_use="measure Gemini usage, fallback frequency, and eval candidates",
    ),
)

_GOOD_STATUSES = {"ready"}
_WARN_STATUSES = {"stale", "empty", "missing"}


def build_data_engineering_report(
    *,
    project: str,
    dataset: str,
    query_rows: QueryRows,
    env: Mapping[str, str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a read-only BigQuery/Gemini readiness report.

    ``query_rows`` is injected so tests can use fixtures and the Flask app can
    reuse its BigQuery client wrapper.
    """
    env = env or os.environ
    now = _coerce_now(now)
    generated_at = now.isoformat()
    errors: list[str] = []

    try:
        table_metadata = _load_table_metadata(project, dataset, query_rows)
    except Exception as exc:  # noqa: BLE001
        table_metadata = {}
        errors.append(f"table_metadata_unavailable:{_clip_error(exc)}")

    sources = [
        _analyze_source(
            source,
            project=project,
            dataset=dataset,
            query_rows=query_rows,
            metadata=table_metadata,
            now=now,
            errors=errors,
        )
        for source in WAREHOUSE_SOURCES
    ]
    readiness = _readiness_summary(sources)
    gemini = _gemini_posture(project=project, env=env)
    gaps = _engineering_gaps(sources, readiness, gemini)
    next_tests = _next_tests(sources, gemini)

    return {
        "mode": "admin_data_engineering_analysis",
        "read_only": True,
        "requires_passkey": True,
        "generated_at": generated_at,
        "project": project,
        "dataset": dataset,
        "status": readiness["status"],
        "good_data_to_engineer": readiness["good_data_to_engineer"],
        "score": readiness["score"],
        "summary": {
            "plain_english": _plain_read(readiness, gemini, gaps),
            "technical": [
                f"warehouse_sources={len(sources)}",
                f"ready_sources={readiness['ready_sources']}",
                f"critical_ready={readiness['critical_ready']}/{readiness['critical_total']}",
                f"gemini_status={gemini['status']}",
            ],
        },
        "readiness": readiness,
        "sources": sources,
        "gcloud_data_engineering": {
            "bigquery": {
                "status": "degraded"
                if any("table_metadata" in item for item in errors)
                else "ready",
                "dataset": dataset,
                "metadata_source": f"{project}.{dataset}.__TABLES__",
                "query_posture": "metadata plus bounded freshness windows",
            },
            "recommended_lanes": [
                "Promote this report into scheduled BigQuery data-quality artifacts.",
                "Keep retrieval and vector experiments in BigQuery before adding dedicated endpoints.",
                "Use GCS or BigQuery stage tables for batch artifacts before public summaries read them.",
            ],
            "cost_controls": [
                "No training, endpoint deployment, workflow dispatch, or data mutation is performed.",
                "Freshness probes are table-scoped and lookback-bounded.",
                "Gemini is advisory; deterministic source checks remain the truth gate.",
            ],
        },
        "gemini": gemini,
        "engineering_gaps": gaps,
        "next_tests": next_tests,
        "rights_boundary": [
            "Payment or authentication does not grant resale rights to raw upstream data.",
            "Market rows remain research context only; no personalized advice or execution language.",
            "Cyber rows remain defensive summaries; no exploit payloads or unauthorized scanning.",
        ],
        "errors": errors,
    }


def _load_table_metadata(
    project: str, dataset: str, query_rows: QueryRows
) -> dict[str, dict[str, Any]]:
    rows = query_rows(
        f"""
        SELECT table_id AS table_name,
               row_count,
               size_bytes,
               TIMESTAMP_MILLIS(last_modified_time) AS last_modified
        FROM `{_dataset_ref(project, dataset)}.__TABLES__`
        """
    )
    metadata: dict[str, dict[str, Any]] = {}
    for row in rows:
        table_name = str(row.get("table_name") or "")
        if table_name:
            metadata[table_name] = row
    return metadata


def _analyze_source(
    source: WarehouseSource,
    *,
    project: str,
    dataset: str,
    query_rows: QueryRows,
    metadata: dict[str, dict[str, Any]],
    now: datetime,
    errors: list[str],
) -> dict[str, Any]:
    table_meta = metadata.get(source.table)
    metadata_known = bool(metadata)
    if metadata_known and table_meta is None:
        return _source_row(
            source,
            status="missing",
            rows_total=0,
            rows_recent=0,
            latest_timestamp=None,
            age_hours=None,
            metadata=table_meta,
            error="table_missing_from_metadata",
        )

    try:
        freshness = _load_source_freshness(source, project, dataset, query_rows)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"{source.id}_freshness_unavailable:{_clip_error(exc)}")
        return _source_row(
            source,
            status="unavailable",
            rows_total=_metadata_int(table_meta, "row_count"),
            rows_recent=0,
            latest_timestamp=None,
            age_hours=None,
            metadata=table_meta,
            error="freshness_query_unavailable",
        )

    latest = _coerce_datetime(freshness.get("latest_timestamp"))
    latest_iso = latest.isoformat() if latest else None
    age_hours = _age_hours(now, latest) if latest else None
    rows_total = _metadata_int(table_meta, "row_count")
    rows_recent = _as_int(freshness.get("recent_rows"))
    missing_ts = _as_int(freshness.get("missing_timestamp_rows"))
    status = _freshness_status(
        rows_total=rows_total,
        rows_recent=rows_recent,
        latest=latest,
        age_hours=age_hours,
        freshness_slo_hours=source.freshness_slo_hours,
    )

    row = _source_row(
        source,
        status=status,
        rows_total=rows_total,
        rows_recent=rows_recent,
        latest_timestamp=latest_iso,
        age_hours=age_hours,
        metadata=table_meta,
        error=None,
    )
    row["quality_checks"] = [
        {
            "check": "freshness",
            "status": "pass" if status == "ready" else "review",
            "basis": f"latest age {age_hours}h vs {source.freshness_slo_hours}h SLO",
        },
        {
            "check": "recent_rows",
            "status": "pass" if rows_recent else "review",
            "basis": f"{rows_recent} row(s) in the bounded lookback window",
        },
        {
            "check": "timestamp_completeness",
            "status": "pass" if missing_ts == 0 else "review",
            "basis": f"{missing_ts} null {source.timestamp_column} value(s) in the scan",
        },
    ]
    return row


def _load_source_freshness(
    source: WarehouseSource, project: str, dataset: str, query_rows: QueryRows
) -> dict[str, Any]:
    table = _table_ref(project, dataset, source.table)
    column = _identifier(source.timestamp_column)
    if source.timestamp_type == "date":
        days = max(1, round(source.lookback_hours / 24))
        sql = f"""
        SELECT COUNT(1) AS recent_rows,
               MAX({column}) AS latest_timestamp,
               COUNTIF({column} IS NULL) AS missing_timestamp_rows
        FROM `{table}`
        WHERE {column} >= DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
        """
    else:
        hours = max(1, source.lookback_hours)
        sql = f"""
        SELECT COUNT(1) AS recent_rows,
               MAX({column}) AS latest_timestamp,
               COUNTIF({column} IS NULL) AS missing_timestamp_rows
        FROM `{table}`
        WHERE {column} >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        """
    rows = query_rows(sql)
    return rows[0] if rows else {}


def _source_row(
    source: WarehouseSource,
    *,
    status: str,
    rows_total: int,
    rows_recent: int,
    latest_timestamp: str | None,
    age_hours: float | None,
    metadata: dict[str, Any] | None,
    error: str | None,
) -> dict[str, Any]:
    return {
        "id": source.id,
        "label": source.label,
        "table": source.table,
        "lane": source.lane,
        "critical": source.critical,
        "status": status,
        "rows_total": rows_total,
        "rows_recent": rows_recent,
        "latest_timestamp": latest_timestamp,
        "age_hours": age_hours,
        "freshness_slo_hours": source.freshness_slo_hours,
        "last_modified": _iso_or_none((metadata or {}).get("last_modified")),
        "size_bytes": _metadata_int(metadata, "size_bytes"),
        "timestamp_column": source.timestamp_column,
        "rights_envelope": source.rights_envelope,
        "output_policy": source.output_policy,
        "gemini_use": source.gemini_use,
        "quality_checks": [],
        "error": error,
    }


def _readiness_summary(sources: list[dict[str, Any]]) -> dict[str, Any]:
    ready = sum(1 for source in sources if source["status"] in _GOOD_STATUSES)
    warn = sum(1 for source in sources if source["status"] in _WARN_STATUSES)
    unavailable = len(sources) - ready - warn
    critical = [source for source in sources if source["critical"]]
    critical_ready = sum(1 for source in critical if source["status"] in _GOOD_STATUSES)
    weighted = 0.0
    for source in sources:
        if source["status"] in _GOOD_STATUSES:
            weighted += 1.0
        elif source["status"] in {"stale"}:
            weighted += 0.45
        elif source["status"] in {"empty"}:
            weighted += 0.25
    score = round(weighted / max(len(sources), 1), 3)
    if critical and critical_ready < len(critical):
        status = "degraded"
    elif unavailable:
        status = "partial"
    elif warn:
        status = "review"
    else:
        status = "ready"

    return {
        "status": status,
        "score": score,
        "good_data_to_engineer": score >= 0.7 and critical_ready == len(critical),
        "ready_sources": ready,
        "review_sources": warn,
        "unavailable_sources": unavailable,
        "total_sources": len(sources),
        "critical_ready": critical_ready,
        "critical_total": len(critical),
        "status_counts": _status_counts(sources),
    }


def _gemini_posture(*, project: str, env: Mapping[str, str]) -> dict[str, Any]:
    enabled = env.get("ADMIN_ANALYSIS_NARRATIVE_ENABLED", "1") == "1"
    model = env.get("ADMIN_ANALYSIS_NARRATIVE_MODEL") or env.get(
        "LLM_BRAIN_MODEL", "gemini-2.0-flash-exp"
    )
    region = env.get("ADMIN_ANALYSIS_NARRATIVE_REGION") or env.get(
        "LLM_BRAIN_REGION", "us-central1"
    )
    configured_project = env.get("GCP_PROJECT") or env.get("GOOGLE_CLOUD_PROJECT") or project
    if not enabled:
        status = "disabled"
    elif configured_project:
        status = "configured"
    else:
        status = "fallback_only"
    return {
        "status": status,
        "enabled": enabled,
        "project": configured_project,
        "region": region,
        "model": model,
        "safe_uses": [
            "operator narrative over aggregated readiness only",
            "batch OODA summaries from BigQuery/GCS artifacts",
            "prompt and UI copy evals against golden cases before tuning",
        ],
        "blocked_uses": [
            "secret-bearing prompts",
            "live trading or money movement",
            "raw customer or private-service evidence in public copy",
        ],
    }


def _engineering_gaps(
    sources: list[dict[str, Any]], readiness: dict[str, Any], gemini: dict[str, Any]
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for source in sources:
        if source["critical"] and source["status"] != "ready":
            gaps.append(
                {
                    "severity": "high",
                    "lane": source["lane"],
                    "title": f"{source['label']} is not ready",
                    "evidence": f"{source['id']} status={source['status']}",
                    "next_step": "Fix or backfill this source before building higher-level automations.",
                }
            )
    stale = [source for source in sources if source["status"] == "stale" and not source["critical"]]
    if stale:
        gaps.append(
            {
                "severity": "medium",
                "lane": "freshness",
                "title": "Non-critical sources are stale",
                "evidence": ", ".join(source["id"] for source in stale[:4]),
                "next_step": "Add scheduled refresh evidence or mark the UI lane quiet.",
            }
        )
    if gemini["status"] != "configured":
        gaps.append(
            {
                "severity": "medium",
                "lane": "gemini",
                "title": "Gemini is not fully configured",
                "evidence": f"gemini_status={gemini['status']}",
                "next_step": "Keep deterministic narratives active until Vertex/Gemini auth is verified.",
            }
        )
    if readiness["score"] < 0.7:
        gaps.append(
            {
                "severity": "medium",
                "lane": "warehouse",
                "title": "Warehouse quality score is below engineering threshold",
                "evidence": f"score={readiness['score']}",
                "next_step": "Prioritize table freshness and provenance before widening UI claims.",
            }
        )
    if not gaps:
        gaps.append(
            {
                "severity": "low",
                "lane": "iteration",
                "title": "Data contract is usable for the next iteration",
                "evidence": f"score={readiness['score']}",
                "next_step": "Add eval artifacts and UI readbacks before expanding model-generated copy.",
            }
        )
    return gaps[:8]


def _next_tests(sources: list[dict[str, Any]], gemini: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "name": "freshness-contract-regression",
            "scope": "BigQuery expected tables",
            "command": "pytest tests/unit/test_services_analytics_dashboard.py -q",
            "pass_condition": "Admin report marks missing, stale, empty, and ready sources distinctly.",
        },
        {
            "name": "gemini-fallback-regression",
            "scope": "Vertex/Gemini narrative path",
            "command": "ADMIN_ANALYSIS_NARRATIVE_ENABLED=0 pytest tests/unit/test_services_analytics_dashboard.py -q",
            "pass_condition": f"Deterministic admin narrative remains usable when Gemini is {gemini['status']}.",
        },
        {
            "name": "ui-readback-smoke",
            "scope": "passkey admin console",
            "command": "Open /admin and verify /api/admin/data-engineering renders without console errors.",
            "pass_condition": "Score, Gemini posture, source rows, and gaps are visible behind admin auth.",
        },
        {
            "name": "source-rights-review",
            "scope": ", ".join(sorted({source["lane"] for source in sources})),
            "command": "Review source rights envelopes before exposing new public copy or paid artifacts.",
            "pass_condition": "Public output policies are aggregate, derived, and rights-cleared.",
        },
    ]


def _freshness_status(
    *,
    rows_total: int,
    rows_recent: int,
    latest: datetime | None,
    age_hours: float | None,
    freshness_slo_hours: int,
) -> str:
    if rows_total <= 0 and rows_recent <= 0:
        return "empty"
    if latest is None:
        return "empty"
    if age_hours is not None and age_hours <= freshness_slo_hours:
        return "ready"
    return "stale"


def _plain_read(
    readiness: dict[str, Any], gemini: dict[str, Any], gaps: list[dict[str, str]]
) -> str:
    quality = "good enough" if readiness["good_data_to_engineer"] else "not yet good enough"
    top_gap = gaps[0]["title"] if gaps else "No gap returned"
    return (
        f"The warehouse is {quality} for the next engineering iteration: "
        f"{readiness['ready_sources']}/{readiness['total_sources']} sources are ready, "
        f"critical coverage is {readiness['critical_ready']}/{readiness['critical_total']}, "
        f"and Gemini is {gemini['status']}. Top gap: {top_gap}."
    )


def _status_counts(sources: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source in sources:
        status = str(source.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts


def _coerce_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _coerce_now(value)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return _coerce_now(parsed)
        except ValueError:
            return None
    return None


def _age_hours(now: datetime, latest: datetime | None) -> float | None:
    if latest is None:
        return None
    return round(max(0.0, (now - latest).total_seconds() / 3600), 2)


def _as_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _metadata_int(metadata: dict[str, Any] | None, key: str) -> int:
    return _as_int((metadata or {}).get(key))


def _iso_or_none(value: Any) -> str | None:
    parsed = _coerce_datetime(value)
    return parsed.isoformat() if parsed else None


def _dataset_ref(project: str, dataset: str) -> str:
    return f"{_identifier(project)}.{_identifier(dataset)}"


def _table_ref(project: str, dataset: str, table: str) -> str:
    return f"{_dataset_ref(project, dataset)}.{_identifier(table)}"


def _identifier(value: str) -> str:
    if not _IDENT_RE.match(value or ""):
        raise ValueError(f"unsafe BigQuery identifier: {value!r}")
    return value


def _clip_error(exc: Exception) -> str:
    return " ".join(str(exc).split())[:160]
