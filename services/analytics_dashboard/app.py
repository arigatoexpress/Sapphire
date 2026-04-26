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

import logging
import os
from datetime import UTC, datetime

from flask import Flask, jsonify, render_template, request
from google.cloud import bigquery

PROJECT = os.environ.get("GCP_PROJECT", "tho-ai-agent")
DATASET = os.environ.get("BQ_DATASET", "sapphire")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("analytics")

app = Flask(__name__)
bq = bigquery.Client(project=PROJECT)

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
    return {"ok": True, "project": PROJECT, "dataset": DATASET,
            "ts": datetime.now(UTC).isoformat()}


@app.get("/__/hosting/verification")
def firebase_hosting_verification():
    """Return 200 for Firebase Hosting ownership probes routed to this service."""
    return ("ok\n", 200, {"Cache-Control": "no-store", "Content-Type": "text/plain"})


@app.get("/api/summary")
def summary():
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


@app.get("/api/performance")
def performance():
    days = int(request.args.get("days", "30"))
    rows = _rows(f"""
        SELECT date, symbol, total_signals, wins, losses, win_rate,
               daily_pnl_usd, profit_factor, avg_confidence
        FROM `{PROJECT}.{DATASET}.daily_performance`
        WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL @days DAY)
        ORDER BY date DESC, symbol
    """, params=[bigquery.ScalarQueryParameter("days", "INT64", days)])
    return jsonify({"rows": _clean(rows), "days": days})


@app.get("/api/regime")
def regime():
    limit = int(request.args.get("limit", "100"))
    rows = _rows(f"""
        SELECT timestamp, regime, score, confidence, btc_price_usd,
               btc_dominance, avg_funding_8h_pct, fear_greed_score, fear_greed_label
        FROM `{PROJECT}.{DATASET}.market_regime`
        ORDER BY timestamp DESC
        LIMIT @limit
    """, params=[bigquery.ScalarQueryParameter("limit", "INT64", limit)])
    return jsonify({"rows": _clean(rows)})


@app.get("/api/predictions")
def predictions():
    limit = int(request.args.get("limit", "50"))
    rows = _rows(f"""
        SELECT timestamp, symbol, model, direction, confidence,
               current_price, predicted_price_24h, predicted_move_pct,
               accuracy_score
        FROM `{PROJECT}.{DATASET}.predictions`
        ORDER BY timestamp DESC
        LIMIT @limit
    """, params=[bigquery.ScalarQueryParameter("limit", "INT64", limit)])
    return jsonify({"rows": _clean(rows)})


@app.get("/api/threats")
def threats():
    days = int(request.args.get("days", "30"))
    rows = _rows(f"""
        SELECT date, severity, cves, exploited_cves, kev_cves, avg_cvss
        FROM `{PROJECT}.{DATASET}.daily_threats`
        WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL @days DAY)
        ORDER BY date DESC, severity
    """, params=[bigquery.ScalarQueryParameter("days", "INT64", days)])
    return jsonify({"rows": _clean(rows)})


@app.get("/api/signals/recent")
def signals_recent():
    limit = int(request.args.get("limit", "100"))
    rows = _rows(f"""
        SELECT timestamp, signal_id, symbol, action, direction, confidence,
               score, source, outcome, pnl_usd, regime
        FROM `{PROJECT}.{DATASET}.trading_signals`
        ORDER BY timestamp DESC
        LIMIT @limit
    """, params=[bigquery.ScalarQueryParameter("limit", "INT64", limit)])
    return jsonify({"rows": _clean(rows)})


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
