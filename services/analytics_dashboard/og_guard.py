"""Public 0guard progress payload for sapphirealpha.xyz.

This module intentionally reads only public-safe 0guard HTTP endpoints. It does
not read local key files, secret env values, Telegram payloads, or private
operator state. Network failures are represented as degraded data instead of
raising through the public landing page.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import UTC, datetime
from threading import Lock
from typing import Any

DEFAULT_0GUARD_URL = "https://guard0-miniapp-s77j6bxyra-uc.a.run.app"
ENV_0GUARD_URL = "SAPPHIRE_0GUARD_URL"
ENV_0GUARD_CANDIDATE_URL = "SAPPHIRE_0GUARD_CANDIDATE_URL"

PUBLIC_ENDPOINTS = {
    "health": "/api/healthz",
    "ready": "/api/readyz",
    "summary": "/api/data/summary",
    "coverage": "/api/data/detection-coverage",
    "events": "/api/intelligence/events",
    "events_live": "/api/intelligence/events?live=1&limit=6",
    "reputation_worker": "/api/reputation/connectors/live?live=1&limit=3",
    "detector_candidates": "/api/intelligence/detector-candidates?live=1&limit=5",
    "arbitrum": "/api/integrations/arbitrum",
    "metamask": "/api/integrations/metamask",
    "hackathons": "/api/hackathons/next",
}

PUBLIC_ENDPOINT_TIMEOUTS = {
    "health": 6.0,
    "ready": 6.0,
    "summary": 6.0,
    "coverage": 6.0,
    "events": 10.0,
    "events_live": 22.0,
    "reputation_worker": 22.0,
    "detector_candidates": 22.0,
    "arbitrum": 4.0,
    "metamask": 4.0,
}

PROGRESS_CACHE_TTL_SECONDS = 120.0
PROGRESS_STALE_TTL_SECONDS = 300.0

_progress_cache_lock = Lock()
_progress_cache: dict[str, Any] | None = None
_progress_cache_at: datetime | None = None
_progress_cache_key: tuple[str, str, int] | None = None


def _cache_key(base_url: str, candidate_url: str) -> tuple[str, str, int]:
    return (base_url, candidate_url, id(_fetch_json))


def _has_live_stream_counts(live_streams: dict[str, Any] | None) -> bool:
    if not isinstance(live_streams, dict):
        return False
    return any(
        int(live_streams.get(key) or 0) > 0
        for key in (
            "active_domain_count",
            "detector_candidate_count",
            "live_event_count",
            "sampled_evidence_count",
        )
    )


def _cached_progress(
    key: tuple[str, str, int], now: datetime
) -> tuple[dict[str, Any] | None, float | None]:
    with _progress_cache_lock:
        if _progress_cache is None or _progress_cache_at is None or _progress_cache_key != key:
            return None, None
        age = max(0.0, (now - _progress_cache_at).total_seconds())
        if age > PROGRESS_CACHE_TTL_SECONDS:
            return None, age
        cached = deepcopy(_progress_cache)
    cached["cache"] = {
        "status": "fresh",
        "age_seconds": int(age),
        "ttl_seconds": int(PROGRESS_CACHE_TTL_SECONDS),
    }
    return cached, age


def _cached_live_streams(
    key: tuple[str, str, int], now: datetime
) -> tuple[dict[str, Any] | None, float | None]:
    with _progress_cache_lock:
        if _progress_cache is None or _progress_cache_at is None or _progress_cache_key != key:
            return None, None
        age = max(0.0, (now - _progress_cache_at).total_seconds())
        if age > PROGRESS_STALE_TTL_SECONDS:
            return None, age
        live_streams = deepcopy(_progress_cache.get("live_streams"))
    if not _has_live_stream_counts(live_streams):
        return None, age
    return live_streams, age


def _store_progress(key: tuple[str, str, int], now: datetime, payload: dict[str, Any]) -> None:
    if not _has_live_stream_counts(payload.get("live_streams")):
        return
    with _progress_cache_lock:
        global _progress_cache, _progress_cache_at, _progress_cache_key
        _progress_cache = deepcopy(payload)
        _progress_cache_at = now
        _progress_cache_key = key


def _clean_base_url(url: str | None) -> str:
    candidate = (url or DEFAULT_0GUARD_URL).strip().rstrip("/")
    parsed = urllib.parse.urlparse(candidate)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        return DEFAULT_0GUARD_URL
    return candidate


def _fetch_json(
    base_url: str, endpoint: str, *, timeout: float = 2.5
) -> tuple[dict[str, Any] | None, str]:
    url = base_url.rstrip("/") + endpoint
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"https", "http"}:
        return None, "invalid_url"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "sapphirealpha-0guard-progress/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            if resp.status != 200:
                return None, f"http_{resp.status}"
            loaded = json.loads(resp.read().decode("utf-8"))
            return (loaded if isinstance(loaded, dict) else None), "ok"
    except urllib.error.HTTPError as exc:
        return None, f"http_{exc.code}"
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None, "unreachable"


def _money(value: int | float | None) -> str:
    if not isinstance(value, int | float):
        return "unknown"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"


def _pct(value: float | None) -> str:
    if not isinstance(value, int | float):
        return "unknown"
    return f"{max(0.0, min(1.0, float(value))) * 100:.0f}%"


def _top_counts(counts: dict[str, Any] | None, limit: int = 6) -> list[dict[str, Any]]:
    if not isinstance(counts, dict):
        return []
    rows = []
    for name, count in counts.items():
        if isinstance(name, str) and isinstance(count, int | float):
            rows.append({"name": name, "count": int(count)})
    return sorted(rows, key=lambda row: row["count"], reverse=True)[:limit]


def _coverage_stats(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {
            "covered": 0,
            "total": 0,
            "ratio": None,
            "blockers": 0,
            "warnings": 0,
            "sample": [],
        }
    rows = payload.get("coverage")
    rows = rows if isinstance(rows, list) else []
    covered = 0
    blockers = 0
    warnings = 0
    sample = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        covered += 1 if row.get("matched") is True else 0
        blockers += int(row.get("blockerCount") or 0)
        warnings += int(row.get("warningCount") or 0)
        incident = row.get("incident") if isinstance(row.get("incident"), dict) else {}
        if len(sample) < 5:
            sample.append(
                {
                    "protocol": incident.get("protocol") or "unknown",
                    "chain": incident.get("chain") or "unknown",
                    "attack": incident.get("attack_vector") or "unknown",
                    "matched": row.get("matched") is True,
                    "blockers": int(row.get("blockerCount") or 0),
                    "warnings": int(row.get("warningCount") or 0),
                }
            )
    total = len(rows)
    return {
        "covered": covered,
        "total": total,
        "ratio": covered / total if total else None,
        "blockers": blockers,
        "warnings": warnings,
        "sample": sample,
    }


def _ready_checks(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    checks = payload.get("checks")
    checks = checks if isinstance(checks, list) else []
    public = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        public.append(
            {
                "id": check.get("id") or "unknown",
                "status": check.get("status") or "unknown",
                "summary": check.get("summary") or "",
            }
        )
    return public


def _optional_feed_status(
    feeds: dict[str, tuple[dict[str, Any] | None, str]],
) -> list[dict[str, Any]]:
    labels = {
        "events": "intelligence events",
        "events_live": "live intelligence poll",
        "reputation_worker": "PhishDestroy worker",
        "detector_candidates": "detector candidates",
        "arbitrum": "Arbitrum lane",
        "metamask": "MetaMask lane",
        "hackathons": "hackathon roadmap",
    }
    rows = []
    for key in (
        "events",
        "events_live",
        "reputation_worker",
        "detector_candidates",
        "arbitrum",
        "metamask",
        "hackathons",
    ):
        payload, status = feeds.get(key, (None, "missing"))
        rows.append(
            {
                "key": key,
                "label": labels[key],
                "status": "online" if payload is not None and status == "ok" else status,
                "available": payload is not None and status == "ok",
            }
        )
    return rows


def _live_stream_stats(
    feeds: dict[str, tuple[dict[str, Any] | None, str]],
) -> dict[str, Any]:
    worker = feeds.get("reputation_worker", (None, "missing"))[0]
    candidates = feeds.get("detector_candidates", (None, "missing"))[0]
    events = feeds.get("events_live", (None, "missing"))[0]
    fetch = worker.get("fetch") if isinstance(worker, dict) else {}
    fetch = fetch if isinstance(fetch, dict) else {}
    return {
        "active_domain_count": int(fetch.get("parsedDomainCount") or 0),
        "sampled_evidence_count": int(fetch.get("sampledEvidenceCount") or 0),
        "detector_candidate_count": int(candidates.get("candidateCount") or 0)
        if isinstance(candidates, dict)
        else 0,
        "high_priority_candidate_count": int(candidates.get("highPriorityCount") or 0)
        if isinstance(candidates, dict)
        else 0,
        "live_event_count": int(events.get("eventCount") or 0) if isinstance(events, dict) else 0,
        "raw_payloads_returned": False,
    }


def build_0guard_progress(*, now: datetime | None = None) -> dict[str, Any]:
    """Return a normalized, public-safe progress snapshot for 0guard."""
    observed_at = now or datetime.now(UTC)
    generated_at = observed_at.isoformat()
    base_url = _clean_base_url(os.environ.get(ENV_0GUARD_URL))
    candidate_url = _clean_base_url(os.environ.get(ENV_0GUARD_CANDIDATE_URL) or base_url)
    cache_key = _cache_key(base_url, candidate_url)
    cached, _age = _cached_progress(cache_key, observed_at)
    if cached is not None:
        return cached

    fetched: dict[str, tuple[dict[str, Any] | None, str]] = {}
    with ThreadPoolExecutor(max_workers=min(8, len(PUBLIC_ENDPOINTS))) as pool:
        futures = {
            pool.submit(
                _fetch_json,
                base_url,
                endpoint,
                timeout=PUBLIC_ENDPOINT_TIMEOUTS.get(key, 2.5),
            ): key
            for key, endpoint in PUBLIC_ENDPOINTS.items()
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                fetched[key] = future.result()
            except Exception:
                fetched[key] = (None, "unreachable")

    health, health_status = fetched["health"]
    ready, ready_status = fetched["ready"]
    summary, summary_status = fetched["summary"]
    coverage, coverage_status = fetched["coverage"]

    meta = summary.get("meta", {}) if isinstance(summary, dict) else {}
    stats = summary.get("stats", {}) if isinstance(summary, dict) else {}
    coverage_view = _coverage_stats(coverage)
    incident_count = int(stats.get("incidentCount") or meta.get("total_incidents") or 0)
    total_loss = meta.get("total_loss_usd")
    if not isinstance(total_loss, int | float):
        total_loss = stats.get("totalLossUsd")

    service_ok = isinstance(health, dict) and health.get("ok") is True
    readiness = ready.get("readiness") if isinstance(ready, dict) else None
    ready_ok = isinstance(ready, dict) and ready.get("ok") is True
    coverage_full = bool(
        coverage_view["total"] and coverage_view["covered"] == coverage_view["total"]
    )
    posture = "operational-review"
    if service_ok and ready_ok and coverage_full:
        posture = "live"
    elif service_ok and coverage_full:
        posture = "review-ready"
    elif service_ok:
        posture = "degraded"

    optional_feeds = _optional_feed_status(fetched)
    live_streams = _live_stream_stats(fetched)
    stale_live_streams, stale_age = _cached_live_streams(cache_key, observed_at)
    live_streams_source = "live_fetch"
    if not _has_live_stream_counts(live_streams) and stale_live_streams is not None:
        live_streams = stale_live_streams
        live_streams_source = "stale_success_cache"
        live_streams["stale_age_seconds"] = int(stale_age or 0)
    live_streams["source"] = live_streams_source

    payload = {
        "schema": "sapphire.0guard.progress.v1",
        "generated_at": generated_at,
        "base_url": base_url,
        "candidate_url": candidate_url,
        "posture": posture,
        "service_ok": service_ok,
        "readiness": readiness or "unknown",
        "health_status": health_status,
        "ready_status": ready_status,
        "summary_status": summary_status,
        "coverage_status": coverage_status,
        "metrics": {
            "incident_count": incident_count,
            "incident_month": meta.get("month") or "unknown",
            "reported_loss": _money(total_loss),
            "coverage": _pct(coverage_view["ratio"]),
            "covered_count": coverage_view["covered"],
            "coverage_total": coverage_view["total"],
            "blocker_rules": coverage_view["blockers"],
            "warning_rules": coverage_view["warnings"],
            "active_phishing_domains": live_streams["active_domain_count"],
            "detector_candidates": live_streams["detector_candidate_count"],
        },
        "sources": meta.get("source_urls") if isinstance(meta.get("source_urls"), list) else [],
        "chain_counts": _top_counts(stats.get("chainCounts")),
        "attack_counts": _top_counts(stats.get("attackVectorCounts")),
        "coverage_sample": coverage_view["sample"],
        "ready_checks": _ready_checks(ready),
        "optional_feeds": optional_feeds,
        "live_streams": live_streams,
        "raw_payloads_returned": False,
        "safety": {
            "read_only": True,
            "secret_display_enabled": False,
            "wallet_signatures_blocked": True,
            "telegram_sends_enabled": False,
            "money_movement_enabled": False,
        },
    }
    _store_progress(cache_key, observed_at, payload)
    return payload
