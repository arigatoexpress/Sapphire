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

PROJECT = os.environ.get("GCP_PROJECT", "tho-ai-agent")
DATASET = os.environ.get("BQ_DATASET", "sapphire")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("analytics")

app = Flask(__name__, template_folder=str(_HERE / "templates"))
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


@app.get("/api/predictions/accuracy")
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
        by_model = _rows(backfill_cte + """
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
        """)
        out["by_model"] = _clean(by_model)
    except Exception as exc:
        log.info("predictions_accuracy by_model bq miss: %s", exc)

    try:
        by_symbol = _rows(backfill_cte + """
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
        """)
        out["by_symbol"] = _clean(by_symbol)
    except Exception as exc:
        log.info("predictions_accuracy by_symbol bq miss: %s", exc)

    try:
        rolling = _rows(backfill_cte + """
            SELECT DATE(timestamp) AS date,
                   IFNULL(model, 'unknown') AS model,
                   AVG(effective_accuracy) AS accuracy,
                   COUNTIF(effective_accuracy IS NOT NULL) AS n
            FROM scored
            WHERE effective_accuracy IS NOT NULL
            GROUP BY date, model
            ORDER BY date ASC, model
        """)
        out["rolling"] = _clean(rolling)
    except Exception as exc:
        log.info("predictions_accuracy rolling bq miss: %s", exc)

    return jsonify(out)


@app.get("/api/correlation/matrix")
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
        return jsonify({"symbols": syms, "matrix": [], "n_obs": 0, "days": days, "warnings": ["bq error"]})

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
        return jsonify({
            "symbols": used_syms,
            "matrix": [[1.0]] if len(used_syms) == 1 else [],
            "n_obs": 0,
            "days": days,
            "warnings": warnings or ["insufficient data"],
        })

    # Common date intersection
    common_dates = set(returns[used_syms[0]].keys())
    for s in used_syms[1:]:
        common_dates &= set(returns[s].keys())
    common = sorted(common_dates)
    n_obs = len(common)

    if n_obs < 3:
        return jsonify({
            "symbols": used_syms,
            "matrix": [[1.0 if i == j else 0.0 for j in range(len(used_syms))] for i in range(len(used_syms))],
            "n_obs": n_obs,
            "days": days,
            "warnings": warnings + [f"only {n_obs} overlapping days"],
        })

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

    return jsonify({
        "symbols": used_syms,
        "matrix": matrix,
        "n_obs": n_obs,
        "days": days,
        "warnings": warnings,
    })


@app.get("/api/vpin")
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
    out: dict = {"symbol": symbol, "buckets": buckets, "vpin": None,
                 "toxicity": "unknown", "history": [], "n_ticks": 0}

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
        window = classified[end - buckets:end]
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
            slc = series[end - window:end]
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
            windows_emitted.append({
                "date": slc[-1][0],
                "strategy": strat,
                "sharpe": round(sharpe, 4),
                "deflated_sharpe": dsr["deflated_sharpe"],
                "probability": dsr["probability"],
                "trials": dsr["trials"],
                "n_obs": len(rets),
            })
        rolling.extend(windows_emitted)

        if windows_emitted:
            latest = windows_emitted[-1]
            summary.append({
                "strategy": strat,
                "latest_sharpe": latest["sharpe"],
                "latest_deflated": latest["deflated_sharpe"],
                "latest_probability": latest["probability"],
                "n_windows": len(windows_emitted),
            })

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
        # Pi nodes (rari1/rari2) are filtered out — Pi cluster removed
        # from the active inference fleet 2026-05-03; their entries
        # were perpetual-down noise.
        rows = _rows(f"""
            SELECT service_name AS service, status, host, response_ms,
                   timestamp AS last_seen
            FROM `{PROJECT}.{DATASET}.service_health`
            WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 MINUTE)
              AND host NOT IN ('rari1', 'rari2')
              AND service_name NOT LIKE 'ollama-rari%'
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
