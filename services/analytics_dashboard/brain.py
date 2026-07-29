"""Sapphire Brain — cross-silo synthesis + correlation.

Integration layer that turns siloed dashboards into a single decision
surface. Endpoints:

  GET  /api/brain/synthesis   — observes every silo, emits a single
       situational-awareness brief: degraded silos, top priority actions,
       health score (0-1). Pass ?persist=1 to write the row to the
       brain_synthesis BQ table so the OODA loop builds history.

  GET  /api/brain/correlate   — runs a pattern catalog over the latest
       silo state, emits ranked cross-silo correlations.

  GET  /api/brain/history     — recent brain_synthesis rows for charting.

  POST /api/brain/llm-refresh — bypass the LLM cache and force a fresh
       Gemini call (used by the dashboard "Persist + Run" button).

The deterministic v0 path is unchanged. The LLM-augmented narrative is
ADDITIONAL (``payload["narrative_llm"]``) so the deterministic version
remains the source of truth and we can A/B them.

Wired into the parent Flask app via :func:`register_brain`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any

from auth import admin_required_response, admin_session_payload, requires_admin
from flask import jsonify, request

log = logging.getLogger("sapphire.brain")

THO_HEALTH_URL = os.environ.get("THO_HEALTH_URL", "https://tho.sapphirealpha.xyz/healthz/")
THREAT_FEED_URL = os.environ.get(
    "THREAT_FEED_URL",
    "https://cyber-threat-bot-691674245427.us-central1.run.app/threats?source=all",
)

# ---------------------------------------------------------------------------
# Gemini / Vertex AI augmentation knobs
# ---------------------------------------------------------------------------
LLM_BRAIN_ENABLED = os.environ.get("LLM_BRAIN_ENABLED", "1") == "1"
LLM_BRAIN_MODEL = os.environ.get("LLM_BRAIN_MODEL", "gemini-2.0-flash-exp")
LLM_BRAIN_REGION = os.environ.get("LLM_BRAIN_REGION", "us-central1")
LLM_BRAIN_TIMEOUT_S = float(os.environ.get("LLM_BRAIN_TIMEOUT_S", "2.5"))
LLM_BRAIN_CACHE_TTL_S = float(os.environ.get("LLM_BRAIN_CACHE_TTL_S", "60"))
LLM_BRAIN_AUDIT_TABLE = os.environ.get("LLM_BRAIN_AUDIT_TABLE", "brain_llm_calls")

# Regex blocklist for sensitive identifiers in observation payload. If any
# match is found anywhere in the JSON-serialized snapshot we fall back to
# deterministic-only — better to skip an LLM call than ship a secret to
# Vertex.
_SENSITIVE_RE = re.compile(
    r"(api[_-]?key|secret|password|token|jwt|ssn|credit[_-]?card)",
    re.IGNORECASE,
)

# Process-wide cache for the LLM call. Single-flight per Cloud Run
# instance; with 60s TTL the worst case is ~1 call/min/instance, well
# under any sane Gemini Flash budget.
_llm_cache_lock = threading.Lock()
_llm_cache: dict[str, Any] = {"key": None, "ts": 0.0, "value": None}


def _is_admin_request() -> bool:
    try:
        return admin_session_payload() is not None
    except Exception:  # noqa: BLE001
        return False


def _public_brain_narrative(payload: dict[str, Any]) -> str:
    score = payload.get("health_score")
    if isinstance(score, int | float):
        if score >= 0.8:
            posture = "healthy"
        elif score >= 0.55:
            posture = "degraded"
        else:
            posture = "needs attention"
    else:
        posture = "unknown"
    regime = payload.get("regime") or "unknown"
    degraded = list(payload.get("degraded_silos") or [])
    degraded_count = len(dict.fromkeys(str(s) for s in degraded))
    if degraded_count:
        degraded_sentence = f"{degraded_count} silo lane(s) need attention."
    else:
        degraded_sentence = "No degraded silo lanes are reporting publicly."
    return (
        f"Public Brain sees {posture} cross-silo posture with regime {regime}. "
        f"{degraded_sentence} Detailed actions, signal counts, inference volume, "
        "correlations, history, and persistence require admin."
    )


def _public_synthesis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    actions = (
        payload.get("priority_actions") if isinstance(payload.get("priority_actions"), list) else []
    )
    return {
        "mode": "public_brain_summary",
        "health_score": payload.get("health_score"),
        "confidence": payload.get("confidence"),
        "regime": payload.get("regime"),
        "narrative": _public_brain_narrative(payload),
        "narrative_llm": None,
        "llm_meta": None,
        "degraded_silos": list(payload.get("degraded_silos") or []),
        "silos_observed": list(payload.get("silos_observed") or []),
        "priority_actions": [],
        "priority_action_count": None,
        "priority_actions_locked": len(actions) > 0,
        "admin_required_for": [
            "priority actions",
            "action counts",
            "correlations",
            "history",
            "persistence",
            "signal counts",
            "inference volume",
        ],
        "persisted": False,
    }


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
        {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in r.items()} for r in rows
    ]


def _snapshot_for_llm(obs: dict) -> dict:
    """Trim the raw observation to a Gemini-friendly snapshot.

    Removes BQ error envelopes and verbose service rows; keeps the
    headline numbers for each silo. This both shortens the prompt
    (fewer input tokens) and reduces the surface area for accidental
    PII / credential leakage.
    """
    silos = obs.get("silos", {})
    snap: dict[str, Any] = {"ts": obs.get("ts")}
    silos_out: dict[str, Any] = {}

    trading = silos.get("trading") or {}
    silos_out["trading"] = {
        "signals_24h": int(trading.get("signals_24h") or 0),
        "resolved_24h": int(trading.get("resolved_24h") or 0),
        "latest_signal": trading.get("latest_signal"),
        "error": "error" in trading,
    }

    regime = silos.get("regime") or {}
    latest_valid = regime.get("latest_valid") or {}
    silos_out["regime"] = {
        "regime": latest_valid.get("regime"),
        "score": latest_valid.get("score"),
        "fear_greed_score": latest_valid.get("fear_greed_score"),
    }

    threat = silos.get("threat") or {}
    silos_out["threat"] = {
        "new_24h": int(threat.get("new_24h") or 0),
        "critical_24h": int(threat.get("critical_24h") or 0),
        "total": int(threat.get("total") or 0),
    }

    services = silos.get("services") or []
    if isinstance(services, list):
        silos_out["services"] = {
            "reporting": len(services),
            "down": [
                {"name": s.get("service_name"), "host": s.get("host"), "status": s.get("status")}
                for s in services
                if (s.get("status") or "").lower() in ("down", "degraded")
            ][:5],
        }
    else:
        silos_out["services"] = {"reporting": 0, "down": []}

    inference = silos.get("inference") or {}
    calls = int(inference.get("calls") or 0)
    errs = int(inference.get("errors") or 0)
    silos_out["inference"] = {
        "calls_24h": calls,
        "errors_24h": errs,
        "error_rate": (errs / calls) if calls > 0 else 0.0,
        "avg_latency_ms": inference.get("avg_latency_ms"),
    }

    tho = silos.get("tho") or {}
    silos_out["tho"] = {
        "status": tho.get("status"),
        "warnings": tho.get("warnings"),
    }

    feed = silos.get("threat_live") or {}
    silos_out["threat_live"] = {"records_now": feed.get("records_now") or 0}

    snap["silos"] = silos_out
    return snap


def _has_sensitive_data(text: str) -> bool:
    return bool(_SENSITIVE_RE.search(text or ""))


def _build_prompt(snapshot: dict) -> str:
    body = json.dumps(snapshot, indent=2, sort_keys=True, default=str)
    return (
        "You are the Sapphire OS strategy agent. Below is a structured "
        "snapshot of 7 production silos. Write a 3-sentence operational "
        "brief in the voice of a calm, technically precise CTO. Lead "
        "with the most important fact. Cite specific numbers from the "
        "snapshot — never invent. End with the single highest-priority "
        "action.\n\n"
        f"SNAPSHOT:\n{body}\n\n"
        "Brief:\n"
    )


def _cache_key(snapshot: dict) -> str:
    """Hash the snapshot for cache lookups. Excludes ``ts`` so identical
    silo state served seconds apart hits the cache instead of round-
    tripping to Vertex on every request."""
    payload = {k: v for k, v in snapshot.items() if k != "ts"}
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _vertex_generate(prompt: str) -> dict | None:
    """Call Vertex AI Gemini. Returns dict or None on any failure.

    Imports are deferred so the dashboard still boots if
    google-cloud-aiplatform isn't installed (e.g. local dev without
    the Vertex SDK). Uses Application Default Credentials — on Cloud
    Run that's the runtime SA, no API key needed.
    """
    try:
        import vertexai  # type: ignore[import-not-found]
        from vertexai.generative_models import GenerativeModel  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        log.info("vertex SDK unavailable: %s", exc)
        return None

    project = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        log.info("GCP_PROJECT unset — skipping Vertex call")
        return None

    try:
        vertexai.init(project=project, location=LLM_BRAIN_REGION)
        model = GenerativeModel(LLM_BRAIN_MODEL)
        t0 = time.time()
        resp = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,
                "max_output_tokens": 256,
                "top_p": 0.9,
            },
        )
        latency_ms = int((time.time() - t0) * 1000)
        text = (getattr(resp, "text", None) or "").strip()
        usage = getattr(resp, "usage_metadata", None)
        prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        completion_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
        return {
            "narrative": text,
            "model": LLM_BRAIN_MODEL,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "latency_ms": latency_ms,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("vertex generate failed: %s", exc)
        return None


def _synthesize_llm(obs: dict) -> dict | None:
    """Optional Gemini-augmented narrative. Returns ``None`` on any failure.

    Caller-fail-safe: the deterministic narrative remains the source of
    truth, this is purely additive.
    """
    if not LLM_BRAIN_ENABLED:
        return None
    snapshot = _snapshot_for_llm(obs)
    serialized = json.dumps(snapshot, sort_keys=True, default=str)
    if _has_sensitive_data(serialized):
        log.info("brain LLM: snapshot tripped sensitive-content blocklist; falling back")
        return None

    key = _cache_key(snapshot)
    now = time.time()
    with _llm_cache_lock:
        if (
            _llm_cache.get("key") == key
            and _llm_cache.get("value") is not None
            and (now - float(_llm_cache.get("ts") or 0.0)) < LLM_BRAIN_CACHE_TTL_S
        ):
            cached = dict(_llm_cache["value"])
            cached["cached"] = True
            return cached

    prompt = _build_prompt(snapshot)
    result = _vertex_generate(prompt)
    if not result or not result.get("narrative"):
        return None

    with _llm_cache_lock:
        _llm_cache["key"] = key
        _llm_cache["ts"] = now
        _llm_cache["value"] = result
    enriched = dict(result)
    enriched["cached"] = False
    return enriched


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
            # Pi nodes (rari1/rari2) are removed from the brain's
            # service-health observation as of 2026-05-03 — they were
            # surfacing as perpetually-down noise after the Pi cluster
            # was put on hold. Filter at the BQ-query level so we
            # never report on them.
            rows = _rows(f"""
                SELECT service_name, status, host, MAX(timestamp) AS last_seen
                FROM `{project}.{dataset}.service_health`
                WHERE timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 MINUTE)
                  AND host NOT IN ('rari1', 'rari2')
                  AND service_name NOT LIKE 'ollama-rari%'
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
            actions.append(
                "trading: 0 signals in last 24h — check signal-logger LaunchAgent on Mac"
            )

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
                    actions.append(
                        "regime: no valid (non-UNKNOWN) rows — investigate provider chain"
                    )
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
                actions.append(
                    "threat: no new CVEs in 24h — verify cyber-threat-bot Cloud Scheduler"
                )

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
            actions.append(
                "service: no heartbeats in 60min — telemetry-collector LaunchAgent silent"
            )

        inference = silos.get("inference", {})
        if "error" not in inference:
            calls = int(inference.get("calls") or 0)
            errs = int(inference.get("errors") or 0)
            if calls > 0 and errs / calls > 0.05:
                degraded.append("inference")
                actions.append(
                    f"inference: error rate {errs / calls:.2%} > 5% — check tier failover"
                )
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

    def _audit_llm_call(
        *,
        call_id: str,
        ts: str,
        result: dict | None,
        deterministic_health_score: float,
    ) -> None:
        """Best-effort: append the call to ``brain_llm_calls``. Never raises."""
        if result is None:
            return
        try:
            insert_sql = f"""
                INSERT INTO `{project}.{dataset}.{LLM_BRAIN_AUDIT_TABLE}`
                (call_id, ts, prompt_token_count, completion_token_count,
                 model, narrative, deterministic_health_score, latency_ms)
                VALUES
                (@cid, @ts, @ptok, @ctok, @model, @narr, @health, @lat)
            """
            params = [
                bigquery.ScalarQueryParameter("cid", "STRING", call_id),
                bigquery.ScalarQueryParameter("ts", "TIMESTAMP", ts),
                bigquery.ScalarQueryParameter(
                    "ptok", "INT64", int(result.get("prompt_tokens") or 0)
                ),
                bigquery.ScalarQueryParameter(
                    "ctok", "INT64", int(result.get("completion_tokens") or 0)
                ),
                bigquery.ScalarQueryParameter(
                    "model", "STRING", result.get("model") or LLM_BRAIN_MODEL
                ),
                bigquery.ScalarQueryParameter("narr", "STRING", result.get("narrative") or ""),
                bigquery.ScalarQueryParameter(
                    "health", "FLOAT64", float(deterministic_health_score)
                ),
                bigquery.ScalarQueryParameter("lat", "INT64", int(result.get("latency_ms") or 0)),
            ]
            bq_client.query(
                insert_sql,
                job_config=bigquery.QueryJobConfig(query_parameters=params),
            ).result()
        except Exception as exc:  # noqa: BLE001
            # Audit logging must never break the API surface.
            log.info("brain_llm_calls audit insert skipped: %s", exc)

    def _emit_synthesis_payload(*, persist: bool, force_llm: bool) -> dict[str, Any]:
        obs = _observe()
        syn = _synthesize(obs)
        silos = obs.get("silos", {})
        trading = silos.get("trading", {})
        regime = silos.get("regime", {})
        latest_valid = regime.get("latest_valid") or {}
        threat = silos.get("threat", {})
        fear_greed = latest_valid.get("fear_greed_score")

        # LLM augmentation — fail-safe. The deterministic narrative
        # remains the source of truth.
        llm_result: dict | None = None
        narrative_llm: str | None = None
        if LLM_BRAIN_ENABLED:
            try:
                if force_llm:
                    with _llm_cache_lock:
                        _llm_cache["key"] = None
                        _llm_cache["ts"] = 0.0
                        _llm_cache["value"] = None
                llm_result = _synthesize_llm(obs)
                if llm_result and llm_result.get("narrative"):
                    narrative_llm = llm_result["narrative"]
            except Exception as exc:  # noqa: BLE001
                log.warning("brain LLM augmentation failed: %s", exc)

        payload: dict[str, Any] = {
            **syn,
            "narrative_llm": narrative_llm,
            "ts": obs.get("ts"),
            "silos_observed": list(silos.keys()),
            "signal_count_24h": int(trading.get("signals_24h") or 0),
            "threat_count_24h": int(threat.get("new_24h") or 0),
            "regime": latest_valid.get("regime"),
            "fear_greed": fear_greed,
        }
        if llm_result is not None:
            payload["llm_meta"] = {
                "model": llm_result.get("model"),
                "cached": llm_result.get("cached", False),
                "prompt_tokens": llm_result.get("prompt_tokens"),
                "completion_tokens": llm_result.get("completion_tokens"),
                "latency_ms": llm_result.get("latency_ms"),
            }
            # Audit only fresh (non-cached) calls so we don't double-count.
            if not llm_result.get("cached"):
                _audit_llm_call(
                    call_id=secrets.token_hex(8),
                    ts=obs.get("ts") or datetime.now(UTC).isoformat(),
                    result=llm_result,
                    deterministic_health_score=syn.get("health_score") or 0.0,
                )

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

        return payload

    @app.get("/api/brain/synthesis")
    def _brain_synthesis_endpoint():
        persist = request.args.get("persist", "0") == "1"
        force_llm = request.args.get("force_llm", "0") == "1"
        admin = _is_admin_request()
        if (persist or force_llm) and not admin:
            return admin_required_response()
        payload = _emit_synthesis_payload(persist=persist, force_llm=force_llm)
        return jsonify(payload if admin else _public_synthesis_payload(payload))

    @app.post("/api/brain/llm-refresh")
    @requires_admin
    def _brain_llm_refresh_endpoint():
        """Force a fresh Gemini call, bypassing the 60s cache.

        Used by the dashboard "Persist + Run" flow so the operator can
        get an up-to-date LLM brief on demand. Honors persist=1 like
        the GET endpoint.
        """
        persist = request.args.get("persist", "0") == "1"
        if not LLM_BRAIN_ENABLED:
            payload = _emit_synthesis_payload(persist=persist, force_llm=False)
            payload["llm_disabled"] = True
            return jsonify(payload)
        payload = _emit_synthesis_payload(persist=persist, force_llm=True)
        return jsonify(payload)

    @app.get("/api/brain/correlate")
    @requires_admin
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
                    matches.append(
                        {
                            "pattern_name": "telemetry_collapse",
                            "severity": "HIGH",
                            "silos": ["regime", "threat_live"],
                            "evidence": f"regime_age_h={ago_h:.1f} threat_records=0",
                            "recommendation": "Investigate the LaunchAgent + Cloud Scheduler chain — both ingesting nothing.",
                            "score": 0.9,
                        }
                    )
            except Exception:
                pass

        services = silos.get("services", [])
        inference = silos.get("inference", {})
        down_services = [
            s for s in services if (s.get("status") or "").lower() in ("down", "degraded")
        ]
        calls = int((inference or {}).get("calls") or 0)
        errs = int((inference or {}).get("errors") or 0)
        if down_services and calls > 0 and errs / calls > 0.05:
            matches.append(
                {
                    "pattern_name": "service_inference_failover",
                    "severity": "HIGH",
                    "silos": ["services", "inference"],
                    "evidence": (
                        f"down={[s.get('service_name') for s in down_services[:3]]} "
                        f"err_rate={errs / calls:.2%}"
                    ),
                    "recommendation": "Check inference proxy tier failover — primary may be unreachable.",
                    "score": 0.85,
                }
            )

        threat = silos.get("threat", {})
        crit_24h = int((threat or {}).get("critical_24h") or 0)
        trading = silos.get("trading", {})
        sig24 = int(trading.get("signals_24h") or 0)
        if crit_24h >= 3 and sig24 == 0:
            matches.append(
                {
                    "pattern_name": "threat_with_silent_trading",
                    "severity": "MEDIUM",
                    "silos": ["threat", "trading"],
                    "evidence": f"critical_24h={crit_24h} signals_24h=0",
                    "recommendation": "Manual review: high CVE volume coincides with trading collector silence.",
                    "score": 0.7,
                }
            )

        tho = silos.get("tho", {})
        if tho.get("status") not in ("ok", "ready"):
            matches.append(
                {
                    "pattern_name": "tho_health_degraded",
                    "severity": "HIGH"
                    if tho.get("status") in (None, "unknown", "down")
                    else "MEDIUM",
                    "silos": ["tho"],
                    "evidence": f"tho_status={tho.get('status')!r}",
                    "recommendation": "Check project-go-forward Cloud Run revision + Firestore connectivity.",
                    "score": 0.95,
                }
            )

        matches.sort(key=lambda m: m["score"], reverse=True)
        return jsonify({"ts": obs.get("ts"), "matches": matches, "count": len(matches)})

    @app.get("/api/brain/history")
    @requires_admin
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
