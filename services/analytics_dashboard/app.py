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
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime

from flask import Flask, jsonify, render_template, request
from google.cloud import bigquery

PROJECT = os.environ.get("GCP_PROJECT", "tho-ai-agent")
DATASET = os.environ.get("BQ_DATASET", "sapphire")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("analytics")

app = Flask(__name__)
bq = bigquery.Client(project=PROJECT)

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


def _is_known_probe_path(path: str) -> bool:
    normalized = ("/" + path.lstrip("/")).lower().rstrip("/") or "/"
    return (
        normalized in _KNOWN_PROBE_PATHS
        or normalized.startswith(_KNOWN_PROBE_PREFIXES)
        or normalized.endswith(_KNOWN_PROBE_SUFFIXES)
        or "wordpress" in normalized
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
        return jsonify(_clean(rows)[0] if rows else {})
    except Exception as exc:
        log.info("summary bq miss: %s", exc)
        return jsonify({})


@app.get("/api/performance")
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
    return jsonify({
        "records": feed.get("records", [])[:25],
        "fetched_at": feed.get("fetched_at"),
    })


@app.get("/api/silos/health")
def silos_health():
    """Cross-silo health snapshot — what's up, what's degraded.

    Aggregates BigQuery service_health rows + live probes of external silos
    (THO production, sapphirealpha.xyz). Designed for the unified dashboard
    header strip.
    """
    services: list[dict] = []
    try:
        rows = _rows(f"""
            SELECT service_name AS service, status, host, response_ms,
                   timestamp AS last_seen
            FROM `{PROJECT}.{DATASET}.service_health`
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 MINUTE)
            QUALIFY ROW_NUMBER() OVER (PARTITION BY service_name ORDER BY timestamp DESC) = 1
        """)
        services = _clean(rows)
    except Exception as exc:
        log.info("service_health bq miss: %s", exc)

    tho_health = _http_get_json(THO_HEALTH_URL, timeout=2.5)
    silos = {
        "trading": {"status": "ok" if any(s["service"] == "signal-logger" and s["status"] == "ok" for s in services) else "unknown"},
        "intel": {"status": "ok"},
        "tho": {
            "status": "ok" if tho_health and tho_health.get("status") in ("ok", "ready") else "degraded" if tho_health else "unknown",
            "url": THO_PUBLIC_URL,
            "sha": (tho_health or {}).get("sha"),
        },
        "wildfire": {"status": "phase-0"},
        "hackathon": {"status": "active"},
    }

    return jsonify({
        "services": services,
        "silos": silos,
        "ts": datetime.now(UTC).isoformat(),
    })


@app.get("/api/silos/business")
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
    return render_template("index.html", project=PROJECT, dataset=DATASET)


@app.route("/<path:path>", methods=["GET", "HEAD", "POST"])
def probe_sink(path: str):
    if _is_known_probe_path(path):
        return ("", 204, {"Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow"})
    return ("Not found\n", 404, {"Content-Type": "text/plain"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, debug=False)
