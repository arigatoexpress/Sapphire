"""Sapphire Analytics Dashboard — Cloud Run service reading BigQuery.

Exposes:
  /             HTML dashboard with charts
  /api/summary  JSON rollup (overall stats)
  /api/performance   Daily signal performance
  /api/regime        Latest regime snapshots
  /api/predictions   Recent predictions
  /api/threats       Severity trends
  /healthz           Readiness probe
"""

from __future__ import annotations

import json
import logging
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from google.cloud import bigquery

# Sibling-import bootstrap: works in Cloud Run (gunicorn cwd is /app where
# app.py + _deflated_sharpe.py live side-by-side) and in tests where the
# importlib.util loader walks the file directly.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _deflated_sharpe import annualized_sharpe, deflated_sharpe  # noqa: E402
from admin_narrative import build_admin_narrative  # noqa: E402
from auth import admin_session_payload, requires_admin  # noqa: E402
from data_engineering import build_data_engineering_report  # noqa: E402
from og_proof import build_og_proof_manifest  # noqa: E402
from project_tabs import get_project_tab, public_project_tabs  # noqa: E402

PROJECT = os.environ.get("GCP_PROJECT", "tho-ai-agent")
DATASET = os.environ.get("BQ_DATASET", "sapphire")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("analytics")

app = Flask(__name__, template_folder=str(_HERE / "templates"))
try:
    bq = bigquery.Client(project=PROJECT)
except Exception as _bq_exc:  # pragma: no cover
    log.warning("BigQuery client unavailable: %s", _bq_exc)
    bq = None

# WebAuthn passkey admin scaffold (gated /admin/* + /api/admin/*).
# Lazily wired so a missing optional dep (webauthn / firestore) doesn't crash
# the whole dashboard at import time — admin pages will return 503 instead.
try:
    from auth import register_blueprint as _register_admin_blueprint

    _register_admin_blueprint(app)
except Exception as _admin_exc:  # noqa: BLE001
    log.warning("admin auth scaffold disabled: %s", _admin_exc)

# Sapphire Brain — cross-silo synthesis + correlation (the integration layer).
# Lazy-wired so a brain module failure can't take down the dashboard.
try:
    from brain import register_brain as _register_brain

    _register_brain(
        app,
        project=PROJECT,
        dataset=DATASET,
        bq_client=bq,
        query_param_factory=bigquery,
    )
except Exception as _brain_exc:  # noqa: BLE001
    log.warning("brain endpoints disabled: %s", _brain_exc)

# Sapphire ASFAO — promotes Brain (passive observe) to action layer.
# Lazy-wired so a missing google-cloud-secretmanager / scheduler doesn't
# crash the whole dashboard.
try:
    from asfao import register_asfao as _register_asfao

    _register_asfao(
        app,
        project=PROJECT,
        dataset=DATASET,
        bq_client=bq,
        query_param_factory=bigquery,
    )
except Exception as _asfao_exc:  # noqa: BLE001
    log.warning("asfao endpoints disabled: %s", _asfao_exc)

# Live global market feed (CoinGecko free tier, 60s in-process cache).
# /api/markets/snapshot powers the "Global Markets" hero strip so the
# dashboard never shows "0 signals" — even when our local trading
# collectors are silent, real-world prices are flowing.
try:
    from markets import register_markets as _register_markets

    _register_markets(app)
except Exception as _markets_exc:  # noqa: BLE001
    log.warning("markets endpoints disabled: %s", _markets_exc)

# Sub-pages — the per-project deep-dive routes that the home shell's
# vertical tabs link to. Lazy-wired so a template/import error can't
# kill the dashboard.
try:
    from subpages import register_subpages as _register_subpages

    _register_subpages(app, project=PROJECT, dataset=DATASET)
except Exception as _subpages_exc:  # noqa: BLE001
    log.warning("subpages disabled: %s", _subpages_exc)

_KNOWN_PROBE_PATHS = {
    "/.git/config",
    "/favicon.ico",
    "/feed",
    "/feed/",
    "/robots.txt",
    "/security.txt",
    "/wp-admin/install.php",
    "/wp-includes/ID3/license.txt",
    "/xmlrpc.php",
}
_KNOWN_PROBE_PREFIXES = (
    "/.env",
    "/.git/",
    "/.well-known/",
    "/__",
    "/_ah/",
    "/_config",
    "/actuator",
    "/boaform",
    "/cgi-bin",
    "/config.",
    "/env.",
    "/phpmyadmin",
    "/runtime-",
    "/settings.",
    "/wp-",
)
_KNOWN_PROBE_SUFFIXES = (
    "/wp-includes/wlwmanifest.xml",
    ".php",
)


def _rows(query: str, params: list[bigquery.ScalarQueryParameter] | None = None) -> list[dict]:
    job = bq.query(
        query,
        job_config=bigquery.QueryJobConfig(query_parameters=params or []),
    )
    return [dict(r) for r in job.result()]


def _jsonable(v):
    if isinstance(v, (datetime,)):
        return v.isoformat()
    return v


def _clean(rows: list[dict]) -> list[dict]:
    return [{k: _jsonable(v) for k, v in r.items()} for r in rows]


def _is_admin_request() -> bool:
    try:
        return admin_session_payload() is not None
    except Exception:  # noqa: BLE001
        return False


_PUBLIC_SUMMARY_ADMIN_LOCKED = [
    "trading PnL",
    "win rate",
    "signals",
    "predictions",
    "lead counts",
    "inference call counts",
    "raw service-health rows",
]


def _summary_rollup_row() -> dict:
    rows = _rows(f"""
        SELECT
          (SELECT COUNT(*) FROM `{PROJECT}.{DATASET}.trading_signals`)    AS signals,
          (SELECT COUNT(*) FROM `{PROJECT}.{DATASET}.predictions`)        AS predictions,
          (SELECT COUNT(*) FROM `{PROJECT}.{DATASET}.market_regime`)      AS regime_snapshots,
          (SELECT COUNT(*) FROM `{PROJECT}.{DATASET}.threat_intel`)       AS threats,
          (SELECT COUNT(*) FROM `{PROJECT}.{DATASET}.leads`)              AS leads,
          (SELECT COUNT(*) FROM `{PROJECT}.{DATASET}.inference_metrics`)  AS inference_metrics,
          (SELECT COUNT(*) FROM `{PROJECT}.{DATASET}.service_health`)     AS service_health,
          (SELECT SUM(pnl_usd) FROM `{PROJECT}.{DATASET}.trading_signals`
             WHERE outcome IN ('win','loss')) AS total_pnl_usd,
          (SELECT SAFE_DIVIDE(COUNTIF(outcome='win'), COUNTIF(outcome IN ('win','loss')))
             FROM `{PROJECT}.{DATASET}.trading_signals`) AS win_rate,
          (SELECT regime FROM `{PROJECT}.{DATASET}.market_regime`
             ORDER BY timestamp DESC LIMIT 1) AS latest_regime,
          (SELECT fear_greed_score FROM `{PROJECT}.{DATASET}.market_regime`
             WHERE fear_greed_score IS NOT NULL
             ORDER BY timestamp DESC LIMIT 1) AS fear_greed
    """)
    return _clean(rows)[0] if rows else {}


def _summary_int(row: dict, key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _public_summary_payload(row: dict | None) -> dict:
    row = row or {}
    threat_records = _summary_int(row, "threats")
    regime_snapshots = _summary_int(row, "regime_snapshots")
    latest_regime = row.get("latest_regime") or "unknown"
    fear_greed = row.get("fear_greed")

    if threat_records is None and regime_snapshots is None:
        headline = "Public operating summary is waiting on fresh warehouse data."
        plain = (
            "Sapphire is serving the public shell, but the warehouse rollup did not return "
            "enough data for a fresh public brief. Admin telemetry remains locked behind "
            "the passkey boundary."
        )
        public_read = [
            "Public-safe project routes and failover summaries can still load independently.",
            "Raw trading, CRM, inference, and service-health detail remains admin-only.",
        ]
    else:
        regime_text = str(latest_regime).replace("_", " ").lower()
        headline = "Public brief: threat context and regime posture are visible; operator detail is locked."
        plain = (
            f"The public view can show threat-intel volume and market-regime posture without exposing "
            f"private forecasts, CRM data, PnL, win rate, service hosts, or model telemetry. "
            f"The latest regime label is {regime_text}."
        )
        public_read = [
            "Threat-intel volume is safe for public situational awareness.",
            "Market-regime context is shown as a public posture indicator, not a trading signal.",
            "Inference-backed Sapphire Brain narrative is rendered separately from raw model telemetry.",
        ]

    return {
        "mode": "public_operating_summary",
        "public_metrics": {
            "threat_records": threat_records,
            "regime_snapshots": regime_snapshots,
            "latest_regime": latest_regime,
            "fear_greed": fear_greed,
        },
        "analysis": {
            "headline": headline,
            "plain_english": plain,
            "public_read": public_read,
            "admin_locked": _PUBLIC_SUMMARY_ADMIN_LOCKED,
        },
        "admin_required_for": _PUBLIC_SUMMARY_ADMIN_LOCKED,
    }


def _public_silos_health_payload(payload: dict) -> dict:
    services = payload.get("services") if isinstance(payload.get("services"), list) else []
    status_counts: dict[str, int] = {}
    for service in services:
        if not isinstance(service, dict):
            continue
        status = str(service.get("status") or "unknown").lower()
        status_counts[status] = status_counts.get(status, 0) + 1

    silos: dict[str, dict] = {}
    for name, silo in (payload.get("silos") or {}).items():
        if not isinstance(silo, dict):
            continue
        row = {"status": silo.get("status", "unknown")}
        if name == "tho" and silo.get("url"):
            row["url"] = silo.get("url")
        silos[str(name)] = row

    return {
        "mode": "public_silos_health_summary",
        "silos": silos,
        "service_summary": {
            "reporting": len(services),
            "status_counts": status_counts,
            "healthy": status_counts.get("healthy", 0) + status_counts.get("ok", 0),
        },
        "services": [],
        "ts": payload.get("ts") or datetime.now(UTC).isoformat(),
        "admin_required_for": ["service names", "hosts", "response times", "SHAs"],
    }


def _latest_service_health_rows() -> list[dict]:
    # Pi nodes (rari1/rari2) are filtered out of the public silo strip because
    # they are not active inference routes yet. The failover endpoint handles
    # standby/offline posture separately so public UI does not confuse inactive
    # devices with broken production dependencies.
    rows = _rows(f"""  # nosec B608 - PROJECT/DATASET are operator env table identifiers.
        SELECT service_name AS service, status, host, response_ms,
               timestamp AS last_seen
        FROM `{PROJECT}.{DATASET}.service_health`
        WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 MINUTE)
          AND host NOT IN ('rari1', 'rari2')
          AND service_name NOT LIKE 'ollama-rari%'
        QUALIFY ROW_NUMBER() OVER (PARTITION BY service_name ORDER BY timestamp DESC) = 1
    """)
    return _clean(rows)


def _status_bucket(status: object) -> str:
    value = str(status or "unknown").strip().lower()
    if value in {"ok", "healthy", "ready", "active", "running", "pass"}:
        return "ready"
    if value in {"degraded", "warn", "warning", "agent_only", "standby"}:
        return "degraded"
    if value in {"down", "fail", "failed", "error", "offline", "unreachable"}:
        return "down"
    return "unknown"


def _lane_for_service(service: dict) -> str:
    text = f"{service.get('service', '')} {service.get('host', '')}".lower()
    if any(token in text for token in ("windows", "gpu", "ollama", "tradingview", "webhook")):
        return "gpu_compute"
    if any(token in text for token in ("gcp", "cloud", "bigquery", "gcs", "pipeline", "sync")):
        return "cloud_data"
    if any(
        token in text
        for token in ("mac", "control-plane", "signal-logger", "inference-proxy", "dashboard")
    ):
        return "local_control"
    return "service_mesh"


def _lane_status(counts: dict[str, int], *, empty: str = "unknown") -> str:
    total = sum(counts.values())
    if total == 0:
        return empty
    if counts.get("down", 0):
        return "degraded"
    if counts.get("degraded", 0) or counts.get("unknown", 0):
        return "degraded"
    return "ready"


def _build_failover_payload(services: list[dict], tho_health: dict | None) -> dict:
    lanes = {
        "cloud_data": {
            "label": "Cloud data plane",
            "role": "Cloud Run, BigQuery, GCS, and scheduled sync durability.",
            "counts": {"ready": 0, "degraded": 0, "down": 0, "unknown": 0},
            "services": [],
        },
        "local_control": {
            "label": "Local control plane",
            "role": "Mac-hosted control surfaces and local operators.",
            "counts": {"ready": 0, "degraded": 0, "down": 0, "unknown": 0},
            "services": [],
        },
        "gpu_compute": {
            "label": "GPU compute lane",
            "role": "High-throughput model and desktop automation capacity.",
            "counts": {"ready": 0, "degraded": 0, "down": 0, "unknown": 0},
            "services": [],
        },
        "service_mesh": {
            "label": "Service mesh",
            "role": "Remaining observed services that support the dashboard.",
            "counts": {"ready": 0, "degraded": 0, "down": 0, "unknown": 0},
            "services": [],
        },
    }
    for service in services:
        if not isinstance(service, dict):
            continue
        lane_key = _lane_for_service(service)
        bucket = _status_bucket(service.get("status"))
        lanes[lane_key]["counts"][bucket] += 1
        lanes[lane_key]["services"].append(service)

    tho_bucket = _status_bucket((tho_health or {}).get("status"))
    if tho_health is None:
        tho_bucket = "unknown"
    lanes["cloud_data"]["counts"][tho_bucket] += 1
    lanes["cloud_data"]["services"].append(
        {
            "service": "tho-production",
            "status": (tho_health or {}).get("status", "unknown"),
            "host": THO_PUBLIC_URL,
            "sha": (tho_health or {}).get("sha"),
        }
    )

    lane_rows = []
    for key, lane in lanes.items():
        counts = lane["counts"]
        status = _lane_status(counts)
        lane_rows.append(
            {
                "lane": key,
                "label": lane["label"],
                "role": lane["role"],
                "status": status,
                "counts": counts,
                "services": lane["services"],
            }
        )

    degraded = [row["lane"] for row in lane_rows if row["status"] != "ready"]
    if not degraded:
        overall = "ready"
    elif any(row["lane"] == "cloud_data" and row["status"] != "ready" for row in lane_rows):
        overall = "needs_attention"
    else:
        overall = "degraded_with_fallback"

    return {
        "mode": "admin_failover_readiness_detail",
        "overall_status": overall,
        "lanes": lane_rows,
        "degraded_lanes": degraded,
        "routing_policy": [
            "Keep public dashboard on cloud-safe summaries when local devices are degraded.",
            "Use local control plane for operator actions only after admin authentication.",
            "Treat GPU/desktop lane outages as degraded capacity, not a public incident, while cloud summaries stay live.",
        ],
        "ts": datetime.now(UTC).isoformat(),
    }


def _public_failover_payload(payload: dict) -> dict:
    public_lanes = {
        "cloud_data": {
            "lane": "cloud_path",
            "label": "Cloud path",
            "role": "Hosted public route and data durability summary.",
        },
        "local_control": {
            "lane": "operator_path",
            "label": "Operator path",
            "role": "Private control route summarized for availability only.",
        },
        "gpu_compute": {
            "lane": "compute_path",
            "label": "Compute path",
            "role": "Model and automation capacity summary.",
        },
        "service_mesh": {
            "lane": "service_path",
            "label": "Service path",
            "role": "Supporting service availability summary.",
        },
    }
    lanes = []
    for lane in payload.get("lanes", []):
        if not isinstance(lane, dict):
            continue
        public = public_lanes.get(str(lane.get("lane")), {})
        counts = lane.get("counts") if isinstance(lane.get("counts"), dict) else {}
        lanes.append(
            {
                "lane": public.get("lane", "service_path"),
                "label": public.get("label", "Service path"),
                "role": public.get("role", "Supporting service availability summary."),
                "status": lane.get("status", "unknown"),
                "reporting": sum(int(v or 0) for v in counts.values()),
            }
        )
    degraded = [
        public_lanes.get(str(lane), {"lane": "service_path"})["lane"]
        for lane in payload.get("degraded_lanes", [])
    ]
    return {
        "mode": "public_failover_readiness_summary",
        "overall_status": payload.get("overall_status", "unknown"),
        "lanes": lanes,
        "degraded_lanes": degraded,
        "ts": payload.get("ts") or datetime.now(UTC).isoformat(),
        "admin_required_for": [
            "service names",
            "hosts",
            "ports",
            "raw check evidence",
            "operator routing policy",
        ],
    }


def _is_known_probe_path(path: str) -> bool:
    normalized = ("/" + path.lstrip("/")).lower().rstrip("/") or "/"
    return (
        normalized in _KNOWN_PROBE_PATHS
        or normalized.startswith(_KNOWN_PROBE_PREFIXES)
        or normalized.endswith(_KNOWN_PROBE_SUFFIXES)
        or "wordpress" in normalized
    )


def _admin_inference_tiers() -> list[dict]:
    rows = _rows(f"""
        SELECT tier,
               SUM(requests) AS calls,
               AVG(avg_latency_ms) AS avg_latency_ms,
               AVG(p95_latency_ms) AS p95_latency_ms,
               SUM(success) AS ok_count,
               SUM(errors) AS err_count
        FROM `{PROJECT}.{DATASET}.inference_metrics`
        WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
        GROUP BY tier
        ORDER BY calls DESC
    """)
    return _clean(rows)


def _admin_recent_signals(limit: int = 8) -> list[dict]:
    rows = _rows(
        f"""
        SELECT timestamp, signal_id, symbol, action, direction, confidence,
               score, source, outcome, pnl_usd, regime
        FROM `{PROJECT}.{DATASET}.trading_signals`
        ORDER BY timestamp DESC
        LIMIT @limit
    """,
        params=[bigquery.ScalarQueryParameter("limit", "INT64", limit)],
    )
    return _clean(rows)


def _num(value: object, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _count(value: object) -> int:
    return int(_num(value, 0.0))


def _pct(value: object) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _metric(label: str, value: object, unit: str | None = None) -> dict:
    payload = {"label": label, "value": value}
    if unit:
        payload["unit"] = unit
    return payload


def _round_metric(value: object, digits: int = 2) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return None


def _source_status(*, rows: int, error_key: str, errors: list[str], optional: bool = False) -> str:
    if error_key in errors:
        return "unavailable"
    if rows:
        return "ready"
    return "quiet" if optional else "empty"


def _admin_data_quality(
    *,
    summary_row: dict,
    services: list[dict],
    inference_tiers: list[dict],
    recent_signals: list[dict],
    tho_health: dict | None,
    errors: list[str],
) -> dict:
    sources = [
        {
            "id": "warehouse_rollup",
            "label": "Warehouse rollup",
            "status": _source_status(
                rows=1 if summary_row else 0,
                error_key="summary_rollup_unavailable",
                errors=errors,
            ),
            "rows": 1 if summary_row else 0,
            "provenance": "BigQuery aggregate across signals, predictions, regimes, threats, leads, inference, and service health.",
        },
        {
            "id": "service_health",
            "label": "Service health",
            "status": _source_status(
                rows=len(services),
                error_key="service_health_unavailable",
                errors=errors,
            ),
            "rows": len(services),
            "provenance": "Latest BigQuery service-health row per service in the last 60 minutes.",
        },
        {
            "id": "model_telemetry",
            "label": "Model telemetry",
            "status": _source_status(
                rows=len(inference_tiers),
                error_key="inference_telemetry_unavailable",
                errors=errors,
                optional=True,
            ),
            "rows": len(inference_tiers),
            "provenance": "BigQuery inference_metrics grouped by model tier over the last 24 hours.",
        },
        {
            "id": "recent_signals",
            "label": "Recent signals",
            "status": _source_status(
                rows=len(recent_signals),
                error_key="recent_signals_unavailable",
                errors=errors,
                optional=True,
            ),
            "rows": len(recent_signals),
            "provenance": "Newest admin-only trading_signals rows, capped for dashboard readability.",
        },
        {
            "id": "tho_dependency",
            "label": "THO dependency",
            "status": _status_bucket((tho_health or {}).get("status"))
            if tho_health is not None
            else "unknown",
            "rows": 1 if tho_health is not None else 0,
            "provenance": "Live THO health probe used for cloud failover posture.",
        },
    ]
    ready_sources = sum(1 for source in sources if source["status"] == "ready")
    if errors:
        status = "degraded"
    elif ready_sources >= 3:
        status = "ready"
    elif ready_sources:
        status = "partial"
    else:
        status = "unavailable"

    return {
        "status": status,
        "ready_sources": ready_sources,
        "total_sources": len(sources),
        "sources": sources,
        "reader_contract": [
            "Start with the simple read, then open the technical notes only when the decision needs raw context.",
            "Treat market rows as research evidence, not execution instructions.",
            "Use source status before trusting a section; quiet data is different from unavailable data.",
        ],
        "freshness_note": (
            "Service health is a 60 minute latest-row view. Model telemetry uses a 24 hour window. "
            "Recent signal rows are capped to keep the console scannable."
        ),
    }


def _admin_analysis_sections(
    *,
    summary_row: dict,
    services: list[dict],
    inference_tiers: list[dict],
    recent_signals: list[dict],
    tho_health: dict | None,
    failover: dict,
    inference_calls: int,
    inference_errors: int,
    symbols: list[str],
    win_rate: float | None,
) -> list[dict]:
    signals = _count(summary_row.get("signals"))
    predictions_count = _count(summary_row.get("predictions"))
    threats = _count(summary_row.get("threats"))
    leads = _count(summary_row.get("leads"))
    regime_snapshots = _count(summary_row.get("regime_snapshots"))
    latest_regime = str(summary_row.get("latest_regime") or "unknown")
    degraded_lanes = failover.get("degraded_lanes") or []
    degraded_services = [
        row
        for row in services
        if isinstance(row, dict) and _status_bucket(row.get("status")) != "ready"
    ]

    lane_rows = []
    for lane in failover.get("lanes", []):
        if not isinstance(lane, dict):
            continue
        counts = lane.get("counts") if isinstance(lane.get("counts"), dict) else {}
        lane_rows.append(
            {
                "lane": lane.get("label") or lane.get("lane"),
                "status": lane.get("status", "unknown"),
                "ready": counts.get("ready", 0),
                "degraded": counts.get("degraded", 0),
                "down": counts.get("down", 0),
                "unknown": counts.get("unknown", 0),
            }
        )

    model_rows = []
    for row in inference_tiers[:8]:
        calls = _count(row.get("calls"))
        ok_count = _count(row.get("ok_count"))
        model_rows.append(
            {
                "tier": row.get("tier", "unknown"),
                "calls": calls,
                "errors": _count(row.get("err_count")),
                "success_rate": round(ok_count / calls, 4) if calls else None,
                "avg_latency_ms": _round_metric(row.get("avg_latency_ms")),
                "p95_latency_ms": _round_metric(row.get("p95_latency_ms")),
            }
        )

    market_rows = [
        {
            "timestamp": row.get("timestamp"),
            "symbol": row.get("symbol"),
            "action": row.get("action"),
            "direction": row.get("direction"),
            "confidence": _round_metric(row.get("confidence"), 4),
            "score": _round_metric(row.get("score"), 4),
            "outcome": row.get("outcome"),
            "pnl_usd": row.get("pnl_usd"),
            "source": row.get("source"),
        }
        for row in recent_signals[:8]
        if isinstance(row, dict)
    ]

    return [
        {
            "id": "operations",
            "title": "Operations",
            "quality": {
                "status": "needs_attention" if degraded_lanes else "ready",
                "basis": f"{len(degraded_lanes)} degraded failover lane(s), {len(degraded_services)} degraded service row(s).",
            },
            "plain_english": (
                "This section answers whether the public site, cloud data plane, local control plane, "
                "and compute lanes can support the next operator move."
            ),
            "technical": [
                f"failover_status={failover.get('overall_status', 'unknown')}",
                f"service_rows_60m={len(services)}",
                f"degraded_lanes={','.join(degraded_lanes) or 'none'}",
            ],
            "metrics": [
                _metric("failover", failover.get("overall_status", "unknown")),
                _metric("service rows", len(services)),
                _metric("degraded lanes", len(degraded_lanes)),
                _metric("degraded services", len(degraded_services)),
            ],
            "rows": lane_rows,
            "links": [
                {"label": "Failover JSON", "href": "/api/failover/readiness"},
                {"label": "Service timeseries", "href": "/api/timeseries/services"},
            ],
        },
        {
            "id": "models",
            "title": "Models",
            "quality": {
                "status": "review" if inference_errors else "ready",
                "basis": f"{inference_errors} error(s) across {len(inference_tiers)} tier row(s).",
            },
            "plain_english": (
                "This section shows whether inference is producing usable analysis and where routing "
                "or latency needs attention before deeper model-generated narratives are trusted."
            ),
            "technical": [
                "window=24h",
                f"calls={inference_calls}",
                f"errors={inference_errors}",
                f"tiers={','.join(str(row.get('tier')) for row in inference_tiers if row.get('tier')) or 'none'}",
            ],
            "metrics": [
                _metric("calls", inference_calls),
                _metric("errors", inference_errors),
                _metric("tiers", len(inference_tiers)),
                _metric(
                    "error rate",
                    round(inference_errors / inference_calls, 4) if inference_calls else None,
                ),
            ],
            "rows": model_rows,
            "links": [
                {"label": "Inference detail", "href": "/api/silos/inference"},
                {"label": "Inference timeseries", "href": "/api/timeseries/inference"},
            ],
        },
        {
            "id": "markets",
            "title": "Markets",
            "quality": {
                "status": "research_only" if signals else "quiet",
                "basis": f"{signals} signal row(s), {predictions_count} prediction row(s), {len(recent_signals)} recent row(s).",
            },
            "plain_english": (
                "This is evidence for analysis and demos, not live execution. Use it to understand "
                "what the system is seeing, how confident it is, and whether recent symbols match the current story."
            ),
            "technical": [
                f"latest_regime={latest_regime}",
                f"win_rate={win_rate if win_rate is not None else 'unknown'}",
                f"recent_symbols={','.join(symbols) or 'none'}",
            ],
            "metrics": [
                _metric("signals", signals),
                _metric("predictions", predictions_count),
                _metric("win rate", win_rate),
                _metric("recent symbols", len(symbols)),
            ],
            "rows": market_rows,
            "links": [
                {"label": "Signals JSON", "href": "/api/signals/recent?limit=25"},
                {"label": "Performance JSON", "href": "/api/performance"},
                {"label": "Deflated Sharpe", "href": "/api/deflated-sharpe/rolling"},
            ],
        },
        {
            "id": "business",
            "title": "Business",
            "quality": {
                "status": "ready" if leads or tho_health else "quiet",
                "basis": f"{leads} lead row(s), THO status={((tho_health or {}).get('status') or 'unknown')}.",
            },
            "plain_english": (
                "This keeps CRM-style rows and THO dependency state in the admin lane, so public pages "
                "can describe capability without leaking customer, lead, or deployment evidence."
            ),
            "technical": [
                f"leads={leads}",
                f"tho_status={((tho_health or {}).get('status') or 'unknown')}",
                f"tho_sha={((tho_health or {}).get('sha') or 'unknown')}",
            ],
            "metrics": [
                _metric("leads", leads),
                _metric("tho status", ((tho_health or {}).get("status") or "unknown")),
                _metric("service health rows", _count(summary_row.get("service_health"))),
            ],
            "rows": [
                {
                    "dataset": "leads",
                    "rows": leads,
                    "admin_note": "Lead counts are summarized publicly; raw CRM rows stay admin-only.",
                },
                {
                    "dataset": "tho-production",
                    "status": ((tho_health or {}).get("status") or "unknown"),
                    "sha": ((tho_health or {}).get("sha") or "unknown"),
                },
            ],
            "links": [
                {"label": "Business silo", "href": "/api/silos/business"},
                {"label": "Decision queue", "href": "/api/asfao/decisions?limit=25"},
            ],
        },
        {
            "id": "threats",
            "title": "Threats And Regime",
            "quality": {
                "status": "ready" if threats or regime_snapshots else "quiet",
                "basis": f"{threats} threat record(s), {regime_snapshots} regime snapshot(s).",
            },
            "plain_english": (
                "This is the safer public-facing intelligence layer: aggregate threat and regime context "
                "can explain the environment while raw operator evidence remains gated here."
            ),
            "technical": [
                f"threat_records={threats}",
                f"regime_snapshots={regime_snapshots}",
                f"fear_greed={summary_row.get('fear_greed') if summary_row.get('fear_greed') is not None else 'unknown'}",
            ],
            "metrics": [
                _metric("threats", threats),
                _metric("regime snapshots", regime_snapshots),
                _metric("latest regime", latest_regime),
                _metric("fear greed", summary_row.get("fear_greed")),
            ],
            "rows": [
                {
                    "dataset": "threat_intel",
                    "rows": threats,
                    "public_safe_summary": "aggregate volume only",
                },
                {
                    "dataset": "market_regime",
                    "rows": regime_snapshots,
                    "latest_regime": latest_regime,
                    "fear_greed": summary_row.get("fear_greed"),
                },
            ],
            "links": [
                {"label": "Threat trend", "href": "/api/threats"},
                {"label": "Regime snapshots", "href": "/api/regime"},
                {"label": "Brain synthesis", "href": "/api/brain/synthesis"},
            ],
        },
    ]


def _admin_analysis_payload() -> dict:
    errors: list[str] = []
    summary_row: dict = {}
    services: list[dict] = []
    inference_tiers: list[dict] = []
    recent_signals: list[dict] = []

    try:
        summary_row = _summary_rollup_row()
    except Exception as exc:  # noqa: BLE001
        log.info("admin analysis summary miss: %s", exc)
        errors.append("summary_rollup_unavailable")

    try:
        services = _latest_service_health_rows()
    except Exception as exc:  # noqa: BLE001
        log.info("admin analysis service-health miss: %s", exc)
        errors.append("service_health_unavailable")

    try:
        inference_tiers = _admin_inference_tiers()
    except Exception as exc:  # noqa: BLE001
        log.info("admin analysis inference miss: %s", exc)
        errors.append("inference_telemetry_unavailable")

    try:
        recent_signals = _admin_recent_signals(limit=8)
    except Exception as exc:  # noqa: BLE001
        log.info("admin analysis recent signals miss: %s", exc)
        errors.append("recent_signals_unavailable")

    tho_health = _http_get_json(THO_HEALTH_URL, timeout=2.5)
    failover = _build_failover_payload(services, tho_health)
    degraded_services = [
        row
        for row in services
        if isinstance(row, dict) and _status_bucket(row.get("status")) != "ready"
    ]
    inference_calls = sum(_count(row.get("calls")) for row in inference_tiers)
    inference_errors = sum(_count(row.get("err_count")) for row in inference_tiers)
    symbols = sorted(
        {
            str(row.get("symbol")).upper()
            for row in recent_signals
            if isinstance(row, dict) and row.get("symbol")
        }
    )
    win_rate = _pct(summary_row.get("win_rate"))
    latest_regime = str(summary_row.get("latest_regime") or "unknown")

    priorities: list[dict] = []
    if failover.get("degraded_lanes"):
        priorities.append(
            {
                "lane": "failover",
                "severity": "high"
                if failover.get("overall_status") == "needs_attention"
                else "medium",
                "title": "Review degraded failover lanes",
                "plain_english": (
                    "One or more operator paths are not fully ready. Public pages can stay "
                    "up, but admin should inspect the raw lane evidence before relying on "
                    "local or GPU-side automation."
                ),
                "evidence": ", ".join(failover.get("degraded_lanes") or []),
            }
        )
    if degraded_services:
        names = [str(row.get("service") or "unknown") for row in degraded_services[:5]]
        priorities.append(
            {
                "lane": "services",
                "severity": "medium",
                "title": "Triage degraded service-health rows",
                "plain_english": (
                    "Some raw service checks are not reporting ready. These are hidden "
                    "publicly, but they matter for operator routing and failover confidence."
                ),
                "evidence": ", ".join(names),
            }
        )
    if inference_errors:
        priorities.append(
            {
                "lane": "models",
                "severity": "medium",
                "title": "Inspect inference errors",
                "plain_english": (
                    "The model telemetry table reports errors in the last 24 hours. Check "
                    "tier routing before trusting deep analysis refreshes."
                ),
                "evidence": f"{inference_errors} errors across {len(inference_tiers)} tier(s)",
            }
        )
    if win_rate is not None and win_rate < 0.5:
        priorities.append(
            {
                "lane": "markets",
                "severity": "medium",
                "title": "Review trading research quality",
                "plain_english": (
                    "Win rate is below 50 percent on scored outcomes. Keep this as research "
                    "evidence, not an execution signal, until the underlying signal family is reviewed."
                ),
                "evidence": f"win_rate={win_rate}",
            }
        )
    if not recent_signals:
        priorities.append(
            {
                "lane": "markets",
                "severity": "low",
                "title": "Confirm recent signal ingestion",
                "plain_english": (
                    "No recent signal rows were returned to the admin aggregate. That can be "
                    "normal during quiet periods, but it is worth checking before analysis demos."
                ),
                "evidence": "recent_signals=0",
            }
        )
    if not priorities:
        priorities.append(
            {
                "lane": "control",
                "severity": "low",
                "title": "No urgent admin action detected",
                "plain_english": (
                    "The current aggregate does not show degraded lanes, model errors, or "
                    "missing market evidence. Continue monitoring from the admin console."
                ),
                "evidence": "derived checks passed",
            }
        )

    signals = _count(summary_row.get("signals"))
    predictions_count = _count(summary_row.get("predictions"))
    threats = _count(summary_row.get("threats"))
    leads = _count(summary_row.get("leads"))
    data_quality = _admin_data_quality(
        summary_row=summary_row,
        services=services,
        inference_tiers=inference_tiers,
        recent_signals=recent_signals,
        tho_health=tho_health,
        errors=errors,
    )
    sections = _admin_analysis_sections(
        summary_row=summary_row,
        services=services,
        inference_tiers=inference_tiers,
        recent_signals=recent_signals,
        tho_health=tho_health,
        failover=failover,
        inference_calls=inference_calls,
        inference_errors=inference_errors,
        symbols=symbols,
        win_rate=win_rate,
    )

    payload = {
        "mode": "admin_analysis",
        "read_only": True,
        "requires_passkey": True,
        "generated_at": datetime.now(UTC).isoformat(),
        "executive_brief": {
            "headline": "Admin analysis: raw Sapphire telemetry is available behind passkeys.",
            "plain_english": (
                f"Sapphire is tracking {signals} signal row(s), {predictions_count} prediction row(s), "
                f"{threats} threat record(s), and {leads} lead row(s). Public pages now show "
                "summaries; this admin view keeps the sensitive evidence, model telemetry, "
                "and operator actions together."
            ),
            "technical": [
                f"latest_regime={latest_regime}",
                f"inference_calls_24h={inference_calls}",
                f"inference_errors_24h={inference_errors}",
                f"service_rows={len(services)}",
                f"failover_status={failover.get('overall_status', 'unknown')}",
            ],
        },
        "data_quality": data_quality,
        "sections": sections,
        "priority_actions": priorities[:6],
        "metrics": {
            "signals": signals,
            "predictions": predictions_count,
            "regime_snapshots": _count(summary_row.get("regime_snapshots")),
            "threats": threats,
            "leads": leads,
            "inference_metrics": _count(summary_row.get("inference_metrics")),
            "service_health": _count(summary_row.get("service_health")),
            "total_pnl_usd": summary_row.get("total_pnl_usd"),
            "win_rate": win_rate,
            "latest_regime": latest_regime,
            "fear_greed": summary_row.get("fear_greed"),
        },
        "model_telemetry": {
            "calls_24h": inference_calls,
            "errors_24h": inference_errors,
            "tiers": inference_tiers,
        },
        "market_evidence": {
            "symbols": symbols,
            "recent_signals": recent_signals,
        },
        "failover": failover,
        "operator_links": [
            {"label": "Brain full synthesis", "href": "/api/brain/synthesis"},
            {"label": "Signals and forecasts", "href": "/api/signals/recent?limit=25"},
            {"label": "Inference detail", "href": "/api/silos/inference"},
            {"label": "Service timeseries", "href": "/api/timeseries/services"},
            {"label": "Decision queue", "href": "/api/asfao/decisions?limit=25"},
        ],
        "errors": errors,
    }
    payload["model_narrative"] = build_admin_narrative(payload)
    return payload


def _admin_data_engineering_payload() -> dict:
    return build_data_engineering_report(
        project=PROJECT,
        dataset=DATASET,
        query_rows=_rows,
        env=os.environ,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
@app.get("/healthz")
@app.get("/healthz/")
@app.get("/_ah/health")
def healthz():
    return {"ok": True, "project": PROJECT, "dataset": DATASET, "ts": datetime.now(UTC).isoformat()}


@app.get("/__/hosting/verification")
def firebase_hosting_verification():
    """Return 200 for Firebase Hosting ownership probes routed to this service."""
    return ("ok\n", 200, {"Cache-Control": "no-store", "Content-Type": "text/plain"})


@app.get("/api/summary")
def summary():
    try:
        row = _summary_rollup_row()
        if _is_admin_request():
            return jsonify(row)
        return jsonify(_public_summary_payload(row))
    except Exception as exc:
        log.info("summary bq miss: %s", exc)
        if _is_admin_request():
            return jsonify({})
        return jsonify(_public_summary_payload(None))


@app.get("/api/admin/analysis")
@requires_admin
def admin_analysis():
    """Readable operator aggregate for the passkey-gated admin console.

    This intentionally lives behind the admin session because it combines raw
    trading counts, model telemetry, service hosts, and failover evidence into
    one operator-facing payload.
    """
    return jsonify(_admin_analysis_payload())


@app.get("/api/admin/data-engineering")
@requires_admin
def admin_data_engineering():
    """Passkey-gated BigQuery/Gemini readiness analysis for engineering work."""
    return jsonify(_admin_data_engineering_payload())


@app.get("/api/performance")
@requires_admin
def performance():
    days = int(request.args.get("days", "30"))
    try:
        rows = _rows(
            f"""
            SELECT date, symbol, total_signals, wins, losses, win_rate,
                   daily_pnl_usd, profit_factor, avg_confidence
            FROM `{PROJECT}.{DATASET}.daily_performance`
            WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL @days DAY)
            ORDER BY date DESC, symbol
        """,
            params=[bigquery.ScalarQueryParameter("days", "INT64", days)],
        )
        return jsonify({"rows": _clean(rows), "days": days})
    except Exception as exc:
        log.info("performance bq miss: %s", exc)
        return jsonify({"rows": [], "days": days})


@app.get("/api/regime")
def regime():
    """Latest regime snapshots — filtered to rows with REAL data.

    Skips rows where score IS NULL or regime = 'UNKNOWN' (those mean the
    regime collector ran but couldn't produce a valid snapshot — they
    pollute the UI with empty cells). Also reports the most recent
    timestamp from the unfiltered table so the UI can flag staleness.
    """
    limit = int(request.args.get("limit", "100"))
    try:
        rows = _rows(
            f"""
            SELECT timestamp, regime, score, confidence, btc_price_usd,
                   btc_dominance, avg_funding_8h_pct, fear_greed_score,
                   fear_greed_label
            FROM `{PROJECT}.{DATASET}.market_regime`
            WHERE score IS NOT NULL AND regime != 'UNKNOWN'
            ORDER BY timestamp DESC
            LIMIT @limit
        """,
            params=[bigquery.ScalarQueryParameter("limit", "INT64", limit)],
        )
        # Also fetch the most-recent timestamp (any row) so the UI can
        # render "regime collector stale for X hours" if no usable rows
        # have come through recently.
        meta_rows = _rows(f"""
            SELECT MAX(timestamp) AS most_recent_any,
                   COUNTIF(regime != 'UNKNOWN' AND score IS NOT NULL) AS valid_rows,
                   COUNT(*) AS total_rows
            FROM `{PROJECT}.{DATASET}.market_regime`
        """)
        meta = _clean(meta_rows)[0] if meta_rows else {}
        return jsonify({"rows": _clean(rows), "meta": meta})
    except Exception as exc:
        log.info("regime bq miss: %s", exc)
        return jsonify({"rows": [], "meta": {}})


@app.get("/api/predictions")
@requires_admin
def predictions():
    limit = int(request.args.get("limit", "50"))
    try:
        rows = _rows(
            f"""
            SELECT timestamp, symbol, model, direction, confidence,
                   current_price, predicted_price_24h, predicted_move_pct,
                   accuracy_score
            FROM `{PROJECT}.{DATASET}.predictions`
            ORDER BY timestamp DESC
            LIMIT @limit
        """,
            params=[bigquery.ScalarQueryParameter("limit", "INT64", limit)],
        )
        return jsonify({"rows": _clean(rows)})
    except Exception as exc:
        log.info("predictions bq miss: %s", exc)
        return jsonify({"rows": []})


@app.get("/api/predictions/accuracy")
@requires_admin
def predictions_accuracy():
    """Rolling 7d/30d prediction accuracy by symbol + by model.

    Backfills accuracy_score for predictions older than 24h on the fly:
    joins each prediction to the closest trading_signals current_price 24h
    after the prediction timestamp and computes whether the predicted
    direction matched the realized move. Materializes the result as the
    `effective_accuracy` column so callers see a meaningful score even
    when the writer never set `accuracy_score`.

    Returns:
        {
          "by_model":  [{model, scored_7d, accuracy_7d, scored_30d, accuracy_30d}],
          "by_symbol": [{symbol, scored_7d, accuracy_7d, scored_30d, accuracy_30d}],
          "rolling":   [{date, model, accuracy, n}],
        }
    Fail-safe: empty payload on any BQ error.
    """
    out = {"by_model": [], "by_symbol": [], "rolling": []}

    backfill_cte = f"""
        WITH preds AS (
          SELECT timestamp, symbol, model, direction, confidence,
                 current_price AS p_price,
                 predicted_price_24h AS p_target,
                 predicted_move_pct,
                 accuracy_score
          FROM `{PROJECT}.{DATASET}.predictions`
          WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
            AND timestamp <= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            AND symbol IS NOT NULL
        ),
        realized AS (
          SELECT
            p.timestamp, p.symbol, p.model, p.direction, p.confidence,
            p.p_price, p.predicted_move_pct, p.accuracy_score,
            (
              SELECT s.current_price
              FROM `{PROJECT}.{DATASET}.trading_signals` s
              WHERE s.symbol = p.symbol
                AND s.timestamp BETWEEN TIMESTAMP_ADD(p.timestamp, INTERVAL 23 HOUR)
                                    AND TIMESTAMP_ADD(p.timestamp, INTERVAL 25 HOUR)
                AND s.current_price IS NOT NULL
              ORDER BY ABS(TIMESTAMP_DIFF(s.timestamp,
                          TIMESTAMP_ADD(p.timestamp, INTERVAL 24 HOUR), SECOND))
              LIMIT 1
            ) AS realized_price
          FROM preds p
        ),
        scored AS (
          SELECT
            timestamp, symbol, model, direction, confidence, p_price,
            realized_price,
            CASE
              WHEN accuracy_score IS NOT NULL THEN accuracy_score
              WHEN realized_price IS NULL OR p_price IS NULL OR p_price = 0 THEN NULL
              WHEN LOWER(IFNULL(direction,'')) IN ('up','bull','long','buy')
                   AND realized_price > p_price THEN 1.0
              WHEN LOWER(IFNULL(direction,'')) IN ('down','bear','short','sell')
                   AND realized_price < p_price THEN 1.0
              WHEN LOWER(IFNULL(direction,'')) IN ('flat','neutral','hold')
                   AND ABS(SAFE_DIVIDE(realized_price - p_price, p_price)) < 0.005 THEN 1.0
              WHEN realized_price IS NOT NULL THEN 0.0
              ELSE NULL
            END AS effective_accuracy
          FROM realized
        )
    """

    try:
        by_model = _rows(
            backfill_cte
            + """
            SELECT model,
                   COUNTIF(effective_accuracy IS NOT NULL
                           AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)) AS scored_7d,
                   AVG(IF(effective_accuracy IS NOT NULL
                          AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY),
                          effective_accuracy, NULL)) AS accuracy_7d,
                   COUNTIF(effective_accuracy IS NOT NULL) AS scored_30d,
                   AVG(effective_accuracy) AS accuracy_30d
            FROM scored
            GROUP BY model
            ORDER BY scored_30d DESC
        """
        )
        out["by_model"] = _clean(by_model)
    except Exception as exc:
        log.info("predictions_accuracy by_model bq miss: %s", exc)

    try:
        by_symbol = _rows(
            backfill_cte
            + """
            SELECT symbol,
                   COUNTIF(effective_accuracy IS NOT NULL
                           AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)) AS scored_7d,
                   AVG(IF(effective_accuracy IS NOT NULL
                          AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY),
                          effective_accuracy, NULL)) AS accuracy_7d,
                   COUNTIF(effective_accuracy IS NOT NULL) AS scored_30d,
                   AVG(effective_accuracy) AS accuracy_30d
            FROM scored
            GROUP BY symbol
            ORDER BY scored_30d DESC
        """
        )
        out["by_symbol"] = _clean(by_symbol)
    except Exception as exc:
        log.info("predictions_accuracy by_symbol bq miss: %s", exc)

    try:
        rolling = _rows(
            backfill_cte
            + """
            SELECT DATE(timestamp) AS date,
                   IFNULL(model, 'unknown') AS model,
                   AVG(effective_accuracy) AS accuracy,
                   COUNTIF(effective_accuracy IS NOT NULL) AS n
            FROM scored
            WHERE effective_accuracy IS NOT NULL
            GROUP BY date, model
            ORDER BY date ASC, model
        """
        )
        out["rolling"] = _clean(rolling)
    except Exception as exc:
        log.info("predictions_accuracy rolling bq miss: %s", exc)

    return jsonify(out)


@app.get("/api/correlation/matrix")
@requires_admin
def correlation_matrix():
    """Cross-asset Pearson correlation matrix of daily log returns.

    Args (query):
        symbols: comma-separated list (default BTC,ETH,SOL,SPY,QQQ,GLD).
        days:    lookback window in days (default 30, max 365).

    Returns:
        {
          "symbols": [...],
          "matrix":  [[1.0, 0.85, ...], ...],   # symmetric, NxN
          "n_obs":   <int>,                     # min number of return obs across pairs
          "days":    <int>,
          "warnings": [...],                    # symbols with insufficient data
        }
    Fail-safe to empty matrix on BQ error.
    """
    raw_syms = request.args.get("symbols", "BTC,ETH,SOL,SPY,QQQ,GLD")
    days = max(7, min(365, int(request.args.get("days", "30"))))
    syms = [s.strip().upper() for s in raw_syms.split(",") if s.strip()]
    syms = list(dict.fromkeys(syms))[:20]  # dedupe + cap at 20
    if not syms:
        return jsonify({"symbols": [], "matrix": [], "n_obs": 0, "days": days, "warnings": []})

    # Pull daily close per symbol — use the last reported current_price per
    # (symbol, date) bucket from trading_signals. This is robust to whichever
    # cadence the signal logger fired at.
    try:
        rows = _rows(
            f"""
            WITH per_day AS (
              SELECT symbol,
                     DATE(timestamp) AS day,
                     ARRAY_AGG(current_price ORDER BY timestamp DESC LIMIT 1)[OFFSET(0)] AS close_px
              FROM `{PROJECT}.{DATASET}.trading_signals`
              WHERE symbol IN UNNEST(@syms)
                AND current_price IS NOT NULL
                AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
              GROUP BY symbol, day
            )
            SELECT symbol, day, close_px
            FROM per_day
            WHERE close_px IS NOT NULL AND close_px > 0
            ORDER BY symbol, day
            """,
            params=[
                bigquery.ArrayQueryParameter("syms", "STRING", syms),
                bigquery.ScalarQueryParameter("days", "INT64", days),
            ],
        )
    except Exception as exc:
        log.info("correlation_matrix bq miss: %s", exc)
        return jsonify(
            {"symbols": syms, "matrix": [], "n_obs": 0, "days": days, "warnings": ["bq error"]}
        )

    # Group by symbol → list of (day, close)
    by_sym: dict[str, list[tuple[str, float]]] = {s: [] for s in syms}
    for r in rows:
        sym = r.get("symbol")
        day = r.get("day")
        px = r.get("close_px")
        if sym in by_sym and day is not None and px is not None:
            by_sym[sym].append((str(day), float(px)))

    # Compute log returns aligned on common dates (intersection)
    returns: dict[str, dict[str, float]] = {}
    warnings: list[str] = []
    for s, series in by_sym.items():
        series.sort(key=lambda x: x[0])
        if len(series) < 3:
            warnings.append(f"{s}: only {len(series)} obs")
            continue
        ret_map: dict[str, float] = {}
        for i in range(1, len(series)):
            d, px = series[i]
            _, prev = series[i - 1]
            if prev > 0 and px > 0:
                ret_map[d] = math.log(px / prev)
        returns[s] = ret_map

    used_syms = [s for s in syms if s in returns]
    if len(used_syms) < 2:
        return jsonify(
            {
                "symbols": used_syms,
                "matrix": [[1.0]] if len(used_syms) == 1 else [],
                "n_obs": 0,
                "days": days,
                "warnings": warnings or ["insufficient data"],
            }
        )

    # Common date intersection
    common_dates = set(returns[used_syms[0]].keys())
    for s in used_syms[1:]:
        common_dates &= set(returns[s].keys())
    common = sorted(common_dates)
    n_obs = len(common)

    if n_obs < 3:
        return jsonify(
            {
                "symbols": used_syms,
                "matrix": [
                    [1.0 if i == j else 0.0 for j in range(len(used_syms))]
                    for i in range(len(used_syms))
                ],
                "n_obs": n_obs,
                "days": days,
                "warnings": warnings + [f"only {n_obs} overlapping days"],
            }
        )

    # Pearson correlation for each pair
    def _pearson(x: list[float], y: list[float]) -> float:
        n = len(x)
        if n < 2:
            return 0.0
        mx = sum(x) / n
        my = sum(y) / n
        num = sum((x[i] - mx) * (y[i] - my) for i in range(n))
        denom_x = math.sqrt(sum((v - mx) ** 2 for v in x))
        denom_y = math.sqrt(sum((v - my) ** 2 for v in y))
        if denom_x == 0 or denom_y == 0:
            return 0.0
        return num / (denom_x * denom_y)

    series_aligned = {s: [returns[s][d] for d in common] for s in used_syms}
    n = len(used_syms)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        matrix[i][i] = 1.0
        for j in range(i + 1, n):
            r = _pearson(series_aligned[used_syms[i]], series_aligned[used_syms[j]])
            matrix[i][j] = round(r, 4)
            matrix[j][i] = round(r, 4)

    return jsonify(
        {
            "symbols": used_syms,
            "matrix": matrix,
            "n_obs": n_obs,
            "days": days,
            "warnings": warnings,
        }
    )


@app.get("/api/vpin")
@requires_admin
def vpin():
    """VPIN — Volume-Synchronized Probability of Informed Trading.

    Approximates Lee-Ready bulk classification using the tick rule on
    successive trading_signals current_price snapshots: if price went up,
    classify the (synthetic unit) volume as buy-initiated; if down, sell.
    VPIN is the rolling mean of |buy - sell| / total over the last
    `buckets` ticks.

    Args:
        symbol:  asset symbol (default BTC).
        buckets: rolling window size (default 50).

    Returns:
        {
          "symbol": "BTC",
          "buckets": 50,
          "vpin": 0.42,
          "toxicity": "normal" | "moderate" | "high" | "extreme",
          "history": [{ts, vpin}, ...],   # last ~120 readings for sparkline
          "n_ticks": 380,
        }
    Fail-safe to {vpin: null, history: []} on BQ error.
    """
    symbol = request.args.get("symbol", "BTC").strip().upper() or "BTC"
    buckets = max(10, min(500, int(request.args.get("buckets", "50"))))
    out: dict = {
        "symbol": symbol,
        "buckets": buckets,
        "vpin": None,
        "toxicity": "unknown",
        "history": [],
        "n_ticks": 0,
    }

    try:
        rows = _rows(
            f"""
            SELECT timestamp, current_price
            FROM `{PROJECT}.{DATASET}.trading_signals`
            WHERE symbol = @symbol
              AND current_price IS NOT NULL
              AND current_price > 0
              AND timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
            ORDER BY timestamp ASC
            """,
            params=[bigquery.ScalarQueryParameter("symbol", "STRING", symbol)],
        )
    except Exception as exc:
        log.info("vpin bq miss: %s", exc)
        return jsonify(out)

    cleaned = _clean(rows)
    if len(cleaned) < buckets + 1:
        out["n_ticks"] = len(cleaned)
        return jsonify(out)

    # Tick-rule classify each price move. Skip identical ticks (zero info).
    classified: list[tuple[str, float, float]] = []  # (ts, buy_unit, sell_unit)
    prev_px: float | None = None
    for r in cleaned:
        px = float(r["current_price"])
        ts = r["timestamp"]
        if prev_px is None:
            prev_px = px
            continue
        # Synthetic unit volume — magnitude proportional to |return| so big
        # moves count more. Bound at 1.0 to avoid one outlier dominating.
        ret = (px - prev_px) / prev_px if prev_px > 0 else 0.0
        unit = min(1.0, abs(ret) * 100)
        if px > prev_px:
            classified.append((ts, unit, 0.0))
        elif px < prev_px:
            classified.append((ts, 0.0, unit))
        # equal price → skip
        prev_px = px

    out["n_ticks"] = len(classified)
    if len(classified) < buckets:
        return jsonify(out)

    # Rolling VPIN history
    history: list[dict] = []
    for end in range(buckets, len(classified) + 1):
        window = classified[end - buckets : end]
        imbalances: list[float] = []
        for _ts, b, s in window:
            tot = b + s
            if tot > 0:
                imbalances.append(abs(b - s) / tot)
        if imbalances:
            score = sum(imbalances) / len(imbalances)
            history.append({"ts": classified[end - 1][0], "vpin": round(score, 4)})

    if not history:
        return jsonify(out)

    # Trim to last ~120 points for sparkline
    sparkline = history[-120:]
    latest = sparkline[-1]["vpin"]

    # Toxicity classification (lifted from lib/analytics/vpin.py)
    if latest >= 0.85:
        toxicity = "extreme"
    elif latest >= 0.70:
        toxicity = "high"
    elif latest >= 0.50:
        toxicity = "moderate"
    else:
        toxicity = "normal"

    out["vpin"] = latest
    out["toxicity"] = toxicity
    out["history"] = sparkline
    return jsonify(out)


@app.get("/api/deflated-sharpe/rolling")
@requires_admin
def deflated_sharpe_rolling():
    """Rolling Deflated Sharpe Ratio per strategy.

    Pulls daily P&L per strategy from trading_signals (grouped on
    `source` as the strategy id), converts to daily returns assuming
    a notional bankroll, then steps a rolling window across the
    timeline emitting Sharpe + DSR-corrected probability per window.

    Args (query):
        strategy: filter to a single source (optional — default all).
        window:   rolling-window size in days (default 90, min 30, max 365).
        days:     total lookback (default 365).

    Fail-safe to empty payload on BQ error.
    """
    strategy = request.args.get("strategy", "").strip()
    window = max(30, min(365, int(request.args.get("window", "90"))))
    lookback = max(window + 30, min(730, int(request.args.get("days", "365"))))

    out = {"window": window, "rolling": [], "summary": []}

    where_strategy = "AND source = @strategy" if strategy else ""
    params = [bigquery.ScalarQueryParameter("days", "INT64", lookback)]
    if strategy:
        params.append(bigquery.ScalarQueryParameter("strategy", "STRING", strategy))

    try:
        rows = _rows(
            f"""
            SELECT
              DATE(timestamp) AS day,
              IFNULL(source, 'unknown') AS strategy,
              SUM(IFNULL(pnl_usd, 0.0)) AS pnl
            FROM `{PROJECT}.{DATASET}.trading_signals`
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @days DAY)
              AND outcome IN ('win', 'loss')
              {where_strategy}
            GROUP BY day, strategy
            ORDER BY strategy, day
            """,
            params=params,
        )
    except Exception as exc:
        log.info("deflated_sharpe_rolling bq miss: %s", exc)
        return jsonify(out)

    cleaned = _clean(rows)

    # Group by strategy → ordered list of (date, daily_return).
    # Notional bankroll converts USD pnl → fractional daily returns. Sharpe
    # is scale-invariant under linear rescaling so this only normalizes
    # magnitude (10k matches paper portfolio scale).
    by_strategy: dict[str, list[tuple[str, float]]] = {}
    NOTIONAL = 10_000.0
    for r in cleaned:
        strat = r.get("strategy") or "unknown"
        day = str(r.get("day"))
        pnl = float(r.get("pnl") or 0.0)
        by_strategy.setdefault(strat, []).append((day, pnl / NOTIONAL))

    rolling: list[dict] = []
    summary: list[dict] = []

    for strat, series in by_strategy.items():
        series.sort(key=lambda x: x[0])
        if len(series) < window:
            continue
        per_window_sharpes: list[float] = []
        windows_emitted: list[dict] = []
        for end in range(window, len(series) + 1):
            slc = series[end - window : end]
            rets = [r for _, r in slc]
            sharpe = annualized_sharpe(rets)
            per_window_sharpes.append(sharpe)
            # DSR using running rolling-Sharpe history as the trial set
            # (selection-from-running-candidates framing).
            dsr = deflated_sharpe(
                per_window_sharpes,
                selected_sharpe=sharpe,
                n_obs=len(rets),
            )
            windows_emitted.append(
                {
                    "date": slc[-1][0],
                    "strategy": strat,
                    "sharpe": round(sharpe, 4),
                    "deflated_sharpe": dsr["deflated_sharpe"],
                    "probability": dsr["probability"],
                    "trials": dsr["trials"],
                    "n_obs": len(rets),
                }
            )
        rolling.extend(windows_emitted)

        if windows_emitted:
            latest = windows_emitted[-1]
            summary.append(
                {
                    "strategy": strat,
                    "latest_sharpe": latest["sharpe"],
                    "latest_deflated": latest["deflated_sharpe"],
                    "latest_probability": latest["probability"],
                    "n_windows": len(windows_emitted),
                }
            )

    out["rolling"] = rolling
    out["summary"] = sorted(summary, key=lambda r: r["latest_probability"], reverse=True)
    return jsonify(out)


@app.get("/api/threats")
def threats():
    days = int(request.args.get("days", "30"))
    try:
        rows = _rows(
            f"""
            SELECT date, severity, cves, exploited_cves, kev_cves, avg_cvss
            FROM `{PROJECT}.{DATASET}.daily_threats`
            WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL @days DAY)
            ORDER BY date DESC, severity
        """,
            params=[bigquery.ScalarQueryParameter("days", "INT64", days)],
        )
        return jsonify({"rows": _clean(rows)})
    except Exception as exc:
        log.info("threats bq miss: %s", exc)
        return jsonify({"rows": []})


def _http_get_json(url: str, timeout: float = 3.0) -> dict | None:
    """Fetch a URL with a tight timeout. Used for cross-silo health probes."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sapphire-unified/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None


THO_HEALTH_URL = os.environ.get(
    "THO_HEALTH_URL",
    "https://tho.sapphirealpha.xyz/healthz/",
)
THO_PUBLIC_URL = os.environ.get(
    "THO_PUBLIC_URL",
    "https://tho.sapphirealpha.xyz/",
)
THREAT_FEED_URL = os.environ.get(
    "THREAT_FEED_URL",
    "https://cyber-threat-bot-691674245427.us-central1.run.app/threats?source=all",
)


@app.get("/api/timeseries/inference")
@requires_admin
def timeseries_inference():
    """Hourly inference-call counts for the last 24h, grouped by tier.

    Powers the sparkline chart in the dashboard header. Returns a list
    of {hour, tier, calls, errors} rows ordered by hour ascending so
    the frontend can plot them directly.
    """
    try:
        rows = _rows(f"""
            SELECT
              TIMESTAMP_TRUNC(timestamp, HOUR) AS hour,
              tier,
              SUM(requests) AS calls,
              SUM(errors)   AS errors
            FROM `{PROJECT}.{DATASET}.inference_metrics`
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            GROUP BY hour, tier
            ORDER BY hour ASC
        """)
        return jsonify({"rows": _clean(rows)})
    except Exception as exc:
        log.info("timeseries_inference bq miss: %s", exc)
        return jsonify({"rows": []})


@app.get("/api/timeseries/threats")
def timeseries_threats():
    """Daily threat counts for the last 30 days, grouped by severity."""
    try:
        rows = _rows(f"""
            SELECT date,
                   IFNULL(severity, 'UNCLASSIFIED') AS severity,
                   SUM(cves) AS cves,
                   SUM(kev_cves) AS kev_cves
            FROM `{PROJECT}.{DATASET}.daily_threats`
            WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
            GROUP BY date, severity
            ORDER BY date ASC
        """)
        return jsonify({"rows": _clean(rows)})
    except Exception as exc:
        log.info("timeseries_threats bq miss: %s", exc)
        return jsonify({"rows": []})


@app.get("/api/timeseries/services")
@requires_admin
def timeseries_services():
    """Service-health rollup over the last hour, per service.

    Returns latest status + p50/p95 response_ms aggregated over the
    window so the UI can show a meaningful response-time bar chart
    instead of a single instantaneous value.
    """
    try:
        rows = _rows(f"""
            WITH recent AS (
              SELECT service_name, host, status, response_ms, timestamp
              FROM `{PROJECT}.{DATASET}.service_health`
              WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 MINUTE)
                AND host NOT IN ('rari1', 'rari2')
                AND service_name NOT LIKE 'ollama-rari%'
            )
            SELECT
              service_name AS service,
              ANY_VALUE(host) AS host,
              COUNTIF(status = 'healthy') AS healthy_n,
              COUNTIF(status = 'degraded') AS degraded_n,
              COUNTIF(status = 'down') AS down_n,
              APPROX_QUANTILES(response_ms, 100)[OFFSET(50)] AS p50_ms,
              APPROX_QUANTILES(response_ms, 100)[OFFSET(95)] AS p95_ms,
              MAX(timestamp) AS last_seen
            FROM recent
            GROUP BY service_name
            ORDER BY service_name
        """)
        return jsonify({"rows": _clean(rows)})
    except Exception as exc:
        log.info("timeseries_services bq miss: %s", exc)
        return jsonify({"rows": []})


@app.get("/api/threats/live")
def threats_live():
    """Proxy the cyber-threat-bot live feed so the dashboard fetches it
    same-origin (no CORS, no extra DNS). Fails-safe to empty list.
    """
    feed = _http_get_json(THREAT_FEED_URL, timeout=4.0)
    if not feed:
        return jsonify({"records": [], "fetched_at": None})
    return jsonify(
        {
            "records": feed.get("records", [])[:25],
            "fetched_at": feed.get("fetched_at"),
        }
    )


@app.get("/api/silos/health")
def silos_health():
    """Cross-silo health snapshot — what's up, what's degraded.

    Aggregates BigQuery service_health rows + live probes of external silos
    (THO production, sapphirealpha.xyz). Designed for the unified dashboard
    header strip.
    """
    services: list[dict] = []
    try:
        services = _latest_service_health_rows()
    except Exception as exc:
        log.info("service_health bq miss: %s", exc)

    tho_health = _http_get_json(THO_HEALTH_URL, timeout=2.5)
    silos = {
        "trading": {
            "status": "ok"
            if any(s["service"] == "signal-logger" and s["status"] == "ok" for s in services)
            else "unknown"
        },
        "intel": {"status": "ok"},
        "tho": {
            "status": "ok"
            if tho_health and tho_health.get("status") in ("ok", "ready")
            else "degraded"
            if tho_health
            else "unknown",
            "url": THO_PUBLIC_URL,
            "sha": (tho_health or {}).get("sha"),
        },
        "wildfire": {"status": "phase-0"},
        "hackathon": {"status": "active"},
    }

    payload = {
        "services": services,
        "silos": silos,
        "ts": datetime.now(UTC).isoformat(),
    }
    if _is_admin_request():
        payload["mode"] = "admin_silos_health_detail"
        return jsonify(payload)
    return jsonify(_public_silos_health_payload(payload))


@app.get("/api/failover/readiness")
def failover_readiness():
    """Public-safe failover posture with admin-only raw device detail.

    This is intentionally separate from /api/silos/health: public users get a
    clear degraded/ready posture by lane, while operators can authenticate to
    inspect the raw services, hosts, and routing policy behind each lane.
    """
    services: list[dict] = []
    try:
        services = _latest_service_health_rows()
    except Exception as exc:
        log.info("failover service_health bq miss: %s", exc)
    tho_health = _http_get_json(THO_HEALTH_URL, timeout=2.5)
    payload = _build_failover_payload(services, tho_health)
    if _is_admin_request():
        return jsonify(payload)
    return jsonify(_public_failover_payload(payload))


@app.get("/api/silos/business")
@requires_admin
def silos_business():
    """Business silo summary — THO customer counts, deals, recent activity.

    Best-effort: returns shape from BigQuery if available, else proxies a
    minimal probe to the THO health endpoint.
    """
    out = {"customers": None, "deals": None, "tho_status": "unknown"}
    try:
        rows = _rows(f"""
            SELECT
              (SELECT COUNT(*) FROM `{PROJECT}.{DATASET}.tho_customers`) AS customers,
              (SELECT COUNT(*) FROM `{PROJECT}.{DATASET}.tho_deals`) AS deals
        """)
        if rows:
            out.update(_clean(rows)[0])
    except Exception as exc:
        log.info("tho bq probe miss: %s", exc)

    tho = _http_get_json(THO_HEALTH_URL, timeout=2.5)
    if tho:
        out["tho_status"] = tho.get("status", "ok")
        out["tho_sha"] = tho.get("sha")
        out["tho_dependencies"] = tho.get("dependencies")
    out["tho_public_url"] = THO_PUBLIC_URL
    return jsonify(out)


@app.get("/api/silos/inference")
@requires_admin
def silos_inference():
    """Inference proxy telemetry from BigQuery. Fails-safe to empty list.

    Aggregates the requests/success/errors counters that the telemetry
    collector writes per (tier, model). Latency is the request-weighted
    average of the per-row avg_latency_ms (good enough for header KPIs).
    """
    try:
        rows = _rows(f"""
            SELECT tier,
                   SUM(requests) AS calls,
                   AVG(avg_latency_ms) AS avg_latency_ms,
                   AVG(p95_latency_ms) AS p95_latency_ms,
                   SUM(success) AS ok_count,
                   SUM(errors) AS err_count
            FROM `{PROJECT}.{DATASET}.inference_metrics`
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            GROUP BY tier
            ORDER BY calls DESC
        """)
        return jsonify({"tiers": _clean(rows)})
    except Exception as exc:
        log.info("inference_metrics bq miss: %s", exc)
        return jsonify({"tiers": []})


@app.get("/api/signals/recent")
@requires_admin
def signals_recent():
    limit = int(request.args.get("limit", "100"))
    try:
        rows = _rows(
            f"""
            SELECT timestamp, signal_id, symbol, action, direction, confidence,
                   score, source, outcome, pnl_usd, regime
            FROM `{PROJECT}.{DATASET}.trading_signals`
            ORDER BY timestamp DESC
            LIMIT @limit
        """,
            params=[bigquery.ScalarQueryParameter("limit", "INT64", limit)],
        )
        return jsonify({"rows": _clean(rows)})
    except Exception as exc:
        log.info("signals_recent bq miss: %s", exc)
        return jsonify({"rows": []})


@app.get("/")
def index():
    return render_template(
        "index.html",
        project=PROJECT,
        dataset=DATASET,
        project_tabs=public_project_tabs(),
    )


@app.get("/api/projects")
def projects_manifest():
    """Public project/satellite manifest backing the landing-page tabs."""
    return jsonify({"projects": public_project_tabs()})


@app.get("/api/projects/<slug>")
def project_manifest(slug: str):
    """Return one public project/satellite manifest entry."""
    tab = get_project_tab(slug)
    if tab is None:
        return jsonify({"error": "project_not_found"}), 404
    return jsonify({"project": tab})


@app.get("/api/hackathon/0g-proof")
def hackathon_og_proof():
    """Public-safe 0G integration proof/readiness manifest."""
    return jsonify(build_og_proof_manifest())


@app.route("/<path:path>", methods=["GET", "HEAD", "POST"])
def probe_sink(path: str):
    if _is_known_probe_path(path):
        return ("", 204, {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})
    return ("Not found\n", 404, {"Content-Type": "text/plain"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
