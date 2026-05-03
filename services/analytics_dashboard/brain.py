"""Sapphire Brain — cross-silo synthesis + correlation.

Integration layer that turns siloed dashboards into a single decision
surface. Three endpoints:

  GET /api/brain/synthesis   — observes every silo, emits a single
      situational-awareness brief: degraded silos, top priority actions,
      health score (0-1). Pass ?persist=1 to write the row to the
      brain_synthesis BQ table so the OODA loop builds history.

  GET /api/brain/correlate   — runs a pattern catalog over the latest
      silo state, emits ranked cross-silo correlations.

  GET /api/brain/history     — recent brain_synthesis rows for charting.

Pure deterministic v0 — no LLM hop. Fast, predictable, auditable.
Wired into the parent Flask app via :func:`register_brain`.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

from flask import jsonify, request

log = logging.getLogger("sapphire.brain")

THO_HEALTH_URL = os.environ.get(
    "THO_HEALTH_URL", "https://tho.sapphirealpha.xyz/healthz/"
)
THREAT_FEED_URL = os.environ.get(
    "THREAT_FEED_URL",
    "https://cyber-threat-bot-691674245427.us-central1.run.app/threats?source=all",
)


def _http_get_json(url: str, timeout: float = 3.0) -> dict | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sapphire-brain/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError):
        return None


def _clean(rows: list[dict]) -> list[dict]:
    return [
        {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in r.items()}
        for r in rows
    ]


def register_brain(app, *, project: str, dataset: str, bq_client, query_param_factory) -> None:
    """Attach brain endpoints to ``app``."""
    bigquery = query_param_factory  # alias

    def _rows(sql: str, params: list | None = None) -> list[dict]:
        job = bq_client.query(
            sql,
            job_config=bigquery.QueryJobConfig(query_parameters=params or []),
        )
        return [dict(r) for r in job.result()]

    def _observe() -> dict:
        obs: dict = {"ts": datetime.now(UTC).isoformat(), "silos": {}}

        try:
            rows = _rows(f"""
                SELECT MAX(timestamp) AS latest_signal,
                       COUNT(*) AS signals_24h,
                       COUNTIF(outcome IN ('win','loss')) AS resolved_24h
                FROM `{project}.{dataset}.trading_signals`
                WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            """)
            obs["silos"]["trading"] = _clean(rows)[0] if rows else {}
        except Exception:
            obs["silos"]["trading"] = {"error": "bq_miss"}

        try:
            rows = _rows(f"""
                SELECT timestamp, regime, score, fear_greed_score
                FROM `{project}.{dataset}.market_regime`
                WHERE score IS NOT NULL AND regime != 'UNKNOWN'
                ORDER BY timestamp DESC LIMIT 1
            """)
            meta = _rows(f"""
                SELECT MAX(timestamp) AS latest_any
                FROM `{project}.{dataset}.market_regime`
            """)
            obs["silos"]["regime"] = {
                "latest_valid": _clean(rows)[0] if rows else None,
                "latest_any": _clean(meta)[0] if meta else None,
            }
        except Exception:
            obs["silos"]["regime"] = {"error": "bq_miss"}

        try:
            rows = _rows(f"""
                SELECT
                  COUNTIF(ingested_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)) AS new_24h,
                  COUNTIF(severity = 'CRITICAL'
                          AND ingested_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)) AS critical_24h,
                  COUNT(*) AS total
                FROM `{project}.{dataset}.threat_intel`
            """)
            obs["silos"]["threat"] = _clean(rows)[0] if rows else {}
        except Exception:
            obs["silos"]["threat"] = {"error": "bq_miss"}

        try:
            rows = _rows(f"""
                SELECT service_name, status, host, MAX(timestamp) AS last_seen
                FROM `{project}.{dataset}.service_health`
                WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 MINUTE)
                GROUP BY service_name, status, host
                QUALIFY ROW_NUMBER() OVER (PARTITION BY service_name ORDER BY MAX(timestamp) DESC) = 1
            """)
            obs["silos"]["services"] = _clean(rows)
        except Exception:
            obs["silos"]["services"] = []

        try:
            rows = _rows(f"""
                SELECT SUM(requests) AS calls, SUM(errors) AS errors,
                       SUM(success) AS oks, AVG(avg_latency_ms) AS avg_latency_ms
                FROM `{project}.{dataset}.inference_metrics`
                WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            """)
            obs["silos"]["inference"] = _clean(rows)[0] if rows else {}
        except Exception:
            obs["silos"]["inference"] = {"error": "bq_miss"}

        obs["silos"]["tho"] = _http_get_json(THO_HEALTH_URL, timeout=2.5) or {"status": "unknown"}
        feed = _http_get_json(THREAT_FEED_URL, timeout=3.0)
        obs["silos"]["threat_live"] = {
            "records_now": len(feed.get("records", [])) if feed else 0,
            "fetched_at": (feed or {}).get("fetched_at"),
        }
        return obs

    def _synthesize(obs: dict) -> dict:
        silos = obs.get("silos", {})
        degraded: list[str] = []
        actions: list[str] = []

        trading = silos.get("trading", {})
        sig24 = int(trading.get("signals_24h") or 0)
        if "error" in trading:
            degraded.append("trading")
            actions.append("trading: BQ trading_signals unreachable — verify dataset IAM")
        elif sig24 == 0:
            degraded.append("trading")
            actions.append("trading: 0 signals in last 24h — check signal-logger LaunchAgent on Mac")

        regime = silos.get("regime", {})
        latest_any_field = (regime.get("latest_any") or {}).get("latest_any")
        latest_valid = regime.get("latest_valid")
        if latest_any_field:
            try:
                ago_h = (
                    datetime.now(UTC)
                    - datetime.fromisoformat(str(latest_any_field).replace("Z", "+00:00"))
                ).total_seconds() / 3600
                if ago_h > 6:
                    degraded.append("regime")
                    actions.append(
                        f"regime: collector stale {ago_h:.1f}h — restart com.sapphire.regime-collector"
                    )
                if not latest_valid:
                    degraded.append("regime")
                    actions.append("regime: no valid (non-UNKNOWN) rows — investigate provider chain")
            except Exception:
                pass

        threat = silos.get("threat", {})
        if "error" not in threat:
            new_24h = int(threat.get("new_24h") or 0)
            crit_24h = int(threat.get("critical_24h") or 0)
            if crit_24h > 0:
                actions.append(f"threat: {crit_24h} CRITICAL CVE(s) in last 24h — review feed")
            if new_24h == 0:
                degraded.append("threat")
                actions.append("threat: no new CVEs in 24h — verify cyber-threat-bot Cloud Scheduler")

        services = silos.get("services", [])
        down = [s for s in services if (s.get("status") or "").lower() in ("down", "degraded")]
        if down:
            for s in down[:5]:
                actions.append(
                    f"service: {s.get('service_name')} on {s.get('host')} is {s.get('status')}"
                )
            degraded.append("services")
        if not services:
            degraded.append("services")
            actions.append("service: no heartbeats in 60min — telemetry-collector LaunchAgent silent")

        inference = silos.get("inference", {})
        if "error" not in inference:
            calls = int(inference.get("calls") or 0)
            errs = int(inference.get("errors") or 0)
            if calls > 0 and errs / calls > 0.05:
                degraded.append("inference")
                actions.append(f"inference: error rate {errs/calls:.2%} > 5% — check tier failover")
            if calls == 0:
                degraded.append("inference")
                actions.append("inference: 0 calls in 24h — proxy or telemetry pipeline halted")

        tho = silos.get("tho", {})
        if tho.get("status") not in ("ok", "ready"):
            degraded.append("tho")
            actions.append("tho: production health probe failed — check Cloud Run rev")
        elif tho.get("warnings"):
            actions.append(f"tho: warnings {tho.get('warnings')}")

        feed = silos.get("threat_live", {})
        if (feed.get("records_now") or 0) == 0:
            degraded.append("threat_live")
            actions.append("threat_live: cyber-threat-bot returned 0 records — verify feed")

        total_silos = 7
        health = max(0.0, 1.0 - len(set(degraded)) / total_silos)
        confidence = 0.85 if not degraded else 0.6

        parts: list[str] = []
        if "trading" not in degraded:
            parts.append(f"Trading: {sig24} signals/24h.")
        if "regime" not in degraded and latest_valid:
            parts.append(f"Regime: {latest_valid.get('regime')} score={latest_valid.get('score')}.")
        if "threat" not in degraded:
            parts.append(
                f"Threat: {threat.get('new_24h', 0)} new CVEs/24h "
                f"({threat.get('critical_24h', 0)} critical)."
            )
        if services and "services" not in degraded:
            parts.append(f"Services: {len(services)} reporting, all healthy.")
        if "inference" not in degraded:
            calls = int(inference.get("calls") or 0)
            parts.append(f"Inference: {calls:,} calls/24h.")
        if "tho" not in degraded:
            parts.append("THO: production nominal.")
        narrative = " ".join(parts) if parts else "All silos degraded — see actions list."

        return {
            "narrative": narrative,
            "priority_actions": actions[:10],
            "degraded_silos": list(dict.fromkeys(degraded)),
            "health_score": round(health, 3),
            "confidence": confidence,
        }

    @app.get("/api/brain/synthesis")
    def _brain_synthesis_endpoint():
        persist = request.args.get("persist", "0") == "1"
        obs = _observe()
        syn = _synthesize(obs)
        silos = obs.get("silos", {})
        trading = silos.get("trading", {})
        regime = silos.get("regime", {})
        latest_valid = regime.get("latest_valid") or {}
        threat = silos.get("threat", {})
        fear_greed = latest_valid.get("fear_greed_score")

        payload: dict[str, Any] = {
            **syn,
            "ts": obs.get("ts"),
            "silos_observed": list(silos.keys()),
            "signal_count_24h": int(trading.get("signals_24h") or 0),
            "threat_count_24h": int(threat.get("new_24h") or 0),
            "regime": latest_valid.get("regime"),
            "fear_greed": fear_greed,
        }

        if persist:
            try:
                now = datetime.now(UTC).isoformat()
                sid = secrets.token_hex(8)
                insert_sql = f"""
                    INSERT INTO `{project}.{dataset}.brain_synthesis`
                    (timestamp, synthesis_id, silos_observed, narrative,
                     priority_actions, degraded_silos, health_score, confidence,
                     signal_count, threat_count_24h, regime, fear_greed, ingested_at)
                    VALUES
                    (@ts, @sid, @silos, @narrative, @actions, @degraded,
                     @health, @conf, @sig, @thr, @reg, @fg, @ing)
                """
                params = [
                    bigquery.ScalarQueryParameter("ts", "TIMESTAMP", obs.get("ts")),
                    bigquery.ScalarQueryParameter("sid", "STRING", sid),
                    bigquery.ArrayQueryParameter("silos", "STRING", payload["silos_observed"]),
                    bigquery.ScalarQueryParameter("narrative", "STRING", syn["narrative"]),
                    bigquery.ArrayQueryParameter("actions", "STRING", syn["priority_actions"]),
                    bigquery.ArrayQueryParameter("degraded", "STRING", syn["degraded_silos"]),
                    bigquery.ScalarQueryParameter("health", "FLOAT64", syn["health_score"]),
                    bigquery.ScalarQueryParameter("conf", "FLOAT64", syn["confidence"]),
                    bigquery.ScalarQueryParameter("sig", "INT64", payload["signal_count_24h"]),
                    bigquery.ScalarQueryParameter("thr", "INT64", payload["threat_count_24h"]),
                    bigquery.ScalarQueryParameter("reg", "STRING", payload["regime"]),
                    bigquery.ScalarQueryParameter(
                        "fg", "INT64", int(fear_greed) if fear_greed is not None else None
                    ),
                    bigquery.ScalarQueryParameter("ing", "TIMESTAMP", now),
                ]
                bq_client.query(
                    insert_sql,
                    job_config=bigquery.QueryJobConfig(query_parameters=params),
                ).result()
                payload["persisted"] = True
                payload["synthesis_id"] = sid
            except Exception as exc:
                log.warning("brain_synthesis persist failed: %s", exc)
                payload["persisted"] = False

        return jsonify(payload)

    @app.get("/api/brain/correlate")
    def _brain_correlate_endpoint():
        obs = _observe()
        silos = obs.get("silos", {})
        matches: list[dict] = []

        regime = silos.get("regime", {})
        latest_any_field = (regime.get("latest_any") or {}).get("latest_any")
        threat_live = silos.get("threat_live", {})
        if latest_any_field:
            try:
                ago_h = (
                    datetime.now(UTC)
                    - datetime.fromisoformat(str(latest_any_field).replace("Z", "+00:00"))
                ).total_seconds() / 3600
                if ago_h > 6 and (threat_live.get("records_now") or 0) == 0:
                    matches.append({
                        "pattern_name": "telemetry_collapse",
                        "severity": "HIGH",
                        "silos": ["regime", "threat_live"],
                        "evidence": f"regime_age_h={ago_h:.1f} threat_records=0",
                        "recommendation": "Investigate the LaunchAgent + Cloud Scheduler chain — both ingesting nothing.",
                        "score": 0.9,
                    })
            except Exception:
                pass

        services = silos.get("services", [])
        inference = silos.get("inference", {})
        down_services = [s for s in services if (s.get("status") or "").lower() in ("down", "degraded")]
        calls = int((inference or {}).get("calls") or 0)
        errs = int((inference or {}).get("errors") or 0)
        if down_services and calls > 0 and errs / calls > 0.05:
            matches.append({
                "pattern_name": "service_inference_failover",
                "severity": "HIGH",
                "silos": ["services", "inference"],
                "evidence": (
                    f"down={[s.get('service_name') for s in down_services[:3]]} "
                    f"err_rate={errs/calls:.2%}"
                ),
                "recommendation": "Check inference proxy tier failover — primary may be unreachable.",
                "score": 0.85,
            })

        threat = silos.get("threat", {})
        crit_24h = int((threat or {}).get("critical_24h") or 0)
        trading = silos.get("trading", {})
        sig24 = int(trading.get("signals_24h") or 0)
        if crit_24h >= 3 and sig24 == 0:
            matches.append({
                "pattern_name": "threat_with_silent_trading",
                "severity": "MEDIUM",
                "silos": ["threat", "trading"],
                "evidence": f"critical_24h={crit_24h} signals_24h=0",
                "recommendation": "Manual review: high CVE volume coincides with trading collector silence.",
                "score": 0.7,
            })

        tho = silos.get("tho", {})
        if tho.get("status") not in ("ok", "ready"):
            matches.append({
                "pattern_name": "tho_health_degraded",
                "severity": "HIGH" if tho.get("status") in (None, "unknown", "down") else "MEDIUM",
                "silos": ["tho"],
                "evidence": f"tho_status={tho.get('status')!r}",
                "recommendation": "Check project-go-forward Cloud Run revision + Firestore connectivity.",
                "score": 0.95,
            })

        matches.sort(key=lambda m: m["score"], reverse=True)
        return jsonify({"ts": obs.get("ts"), "matches": matches, "count": len(matches)})

    @app.get("/api/brain/history")
    def _brain_history_endpoint():
        limit = int(request.args.get("limit", "48"))
        try:
            rows = _rows(
                f"""
                SELECT timestamp, narrative, priority_actions, degraded_silos,
                       health_score, signal_count, threat_count_24h, regime, fear_greed
                FROM `{project}.{dataset}.brain_synthesis`
                ORDER BY timestamp DESC
                LIMIT @limit
            """,
                params=[bigquery.ScalarQueryParameter("limit", "INT64", limit)],
            )
            return jsonify({"rows": _clean(rows)})
        except Exception as exc:
            log.info("brain_history bq miss: %s", exc)
            return jsonify({"rows": []})
