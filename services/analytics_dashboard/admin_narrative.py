"""Admin-only narrative synthesis for the Sapphire analysis console.

The public site never calls this module. It takes the already-built
``/api/admin/analysis`` payload, trims it to a compact prompt-safe snapshot,
and optionally asks Vertex/Gemini for a clearer operator read. The deterministic
fallback is always present and remains the source of truth.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from typing import Any

log = logging.getLogger("sapphire.admin_narrative")

ADMIN_ANALYSIS_NARRATIVE_ENABLED = os.environ.get("ADMIN_ANALYSIS_NARRATIVE_ENABLED", "1") == "1"
ADMIN_ANALYSIS_NARRATIVE_MODEL = os.environ.get(
    "ADMIN_ANALYSIS_NARRATIVE_MODEL",
    os.environ.get("LLM_BRAIN_MODEL", "gemini-2.0-flash-exp"),
)
ADMIN_ANALYSIS_NARRATIVE_REGION = os.environ.get(
    "ADMIN_ANALYSIS_NARRATIVE_REGION",
    os.environ.get("LLM_BRAIN_REGION", "us-central1"),
)
ADMIN_ANALYSIS_NARRATIVE_CACHE_TTL_S = float(
    os.environ.get(
        "ADMIN_ANALYSIS_NARRATIVE_CACHE_TTL_S",
        os.environ.get("LLM_BRAIN_CACHE_TTL_S", "120"),
    )
)

_SENSITIVE_RE = re.compile(
    r"("
    r"api[_-]?key|"
    r"client[_-]?secret|"
    r"secret[_-]?key|"
    r"password|"
    r"access[_-]?token|"
    r"refresh[_-]?token|"
    r"bearer\s+[a-z0-9._-]{12,}|"
    r"jwt|"
    r"private[_-]?key|"
    r"ssn|"
    r"credit[_-]?card"
    r")",
    re.IGNORECASE,
)

_NARRATIVE_FIELDS = ("plain_english", "operator_read", "risk_read", "next_action")
_cache_lock = threading.Lock()
_cache: dict[str, Any] = {"key": None, "ts": 0.0, "value": None}


def build_admin_narrative(payload: dict[str, Any]) -> dict[str, Any]:
    """Return model-assisted admin narrative metadata for an admin payload.

    This function is caller-fail-safe: it returns a deterministic narrative on
    disabled, unavailable, malformed, or sensitivity-blocked model paths.
    """
    fallback = _deterministic_narrative(payload)
    if not ADMIN_ANALYSIS_NARRATIVE_ENABLED:
        return _with_status(fallback, status="disabled", source="deterministic")

    snapshot = _safe_snapshot(payload)
    serialized = json.dumps(snapshot, sort_keys=True, default=str)
    if _has_sensitive_data(serialized):
        blocked = _with_status(fallback, status="blocked_sensitive", source="deterministic")
        blocked["blocked_reason"] = "prompt_snapshot_matched_sensitive_blocklist"
        return blocked

    key = _cache_key(snapshot)
    now = time.time()
    with _cache_lock:
        if (
            _cache.get("key") == key
            and _cache.get("value") is not None
            and (now - float(_cache.get("ts") or 0.0)) < ADMIN_ANALYSIS_NARRATIVE_CACHE_TTL_S
        ):
            cached = dict(_cache["value"])
            cached["cached"] = True
            cached["status"] = "cached"
            return cached

    model_result = _vertex_generate(_build_prompt(snapshot))
    if not model_result or not model_result.get("narrative"):
        return _with_status(fallback, status="unavailable", source="deterministic")

    narrative_text = str(model_result.get("narrative") or "").strip()
    parsed = _parse_model_narrative(narrative_text, fallback)
    if _has_sensitive_data(json.dumps(parsed, sort_keys=True, default=str)):
        blocked = _with_status(fallback, status="blocked_sensitive", source="deterministic")
        blocked["blocked_reason"] = "model_output_matched_sensitive_blocklist"
        return blocked

    status = parsed.pop("status", "generated")
    response = {
        **fallback,
        **parsed,
        "status": status,
        "source": "vertex",
        "enabled": True,
        "model": model_result.get("model") or ADMIN_ANALYSIS_NARRATIVE_MODEL,
        "cached": False,
        "prompt_tokens": model_result.get("prompt_tokens"),
        "completion_tokens": model_result.get("completion_tokens"),
        "latency_ms": model_result.get("latency_ms"),
    }
    with _cache_lock:
        _cache["key"] = key
        _cache["ts"] = now
        _cache["value"] = response
    return response


def _with_status(payload: dict[str, Any], *, status: str, source: str) -> dict[str, Any]:
    out = dict(payload)
    out.update(
        {
            "status": status,
            "source": source,
            "enabled": ADMIN_ANALYSIS_NARRATIVE_ENABLED,
            "model": ADMIN_ANALYSIS_NARRATIVE_MODEL if ADMIN_ANALYSIS_NARRATIVE_ENABLED else None,
            "cached": False,
            "prompt_tokens": None,
            "completion_tokens": None,
            "latency_ms": None,
        }
    )
    return out


def _deterministic_narrative(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    data_quality = (
        payload.get("data_quality") if isinstance(payload.get("data_quality"), dict) else {}
    )
    failover = payload.get("failover") if isinstance(payload.get("failover"), dict) else {}
    model_telemetry = (
        payload.get("model_telemetry") if isinstance(payload.get("model_telemetry"), dict) else {}
    )
    priorities = (
        payload.get("priority_actions") if isinstance(payload.get("priority_actions"), list) else []
    )
    sections = payload.get("sections") if isinstance(payload.get("sections"), list) else []

    signals = _as_int(metrics.get("signals"))
    predictions = _as_int(metrics.get("predictions"))
    threats = _as_int(metrics.get("threats"))
    leads = _as_int(metrics.get("leads"))
    win_rate = _as_pct(metrics.get("win_rate"))
    calls = _as_int(model_telemetry.get("calls_24h"))
    errors = _as_int(model_telemetry.get("errors_24h"))
    ready = _as_int(data_quality.get("ready_sources"))
    total = _as_int(data_quality.get("total_sources"))
    failover_status = str(failover.get("overall_status") or "unknown")
    highest = _first_priority(priorities)

    health_read = f"{ready}/{total} source(s) ready"
    market_read = f"{signals} signal row(s), {predictions} prediction row(s)"
    if win_rate is not None:
        market_read = f"{market_read}, {win_rate} win rate"
    plain = (
        f"Admin analysis is showing {market_read}, {threats} threat record(s), "
        f"and {leads} lead row(s). Data quality is {data_quality.get('status', 'unknown')} "
        f"with {health_read}; failover is {failover_status}."
    )
    operator_read = (
        f"Model telemetry reports {calls} call(s) and {errors} error(s) in the 24 hour "
        f"window. The strongest current operator item is: {highest['title']}."
    )
    risk_read = (
        f"{_priority_count(priorities, 'high')} high and "
        f"{_priority_count(priorities, 'medium')} medium priority action(s) are present."
    )
    next_action = highest["plain_english"] or "Keep monitoring from the admin console."

    return {
        "mode": "admin_model_narrative",
        "plain_english": plain,
        "operator_read": operator_read,
        "risk_read": risk_read,
        "next_action": next_action,
        "technical": [
            f"safe_sections={len(sections)}",
            f"source_status={data_quality.get('status', 'unknown')}",
            f"failover_status={failover_status}",
            f"model_error_rate={round(errors / calls, 4) if calls else 0.0}",
        ],
        "redaction_policy": [
            "Prompt snapshot excludes raw rows, service hosts, operator links, THO SHA, and session material.",
            "Model output is discarded if it matches the sensitive-token blocklist.",
            "Deterministic analysis remains the source of truth.",
        ],
    }


def _safe_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    data_quality = (
        payload.get("data_quality") if isinstance(payload.get("data_quality"), dict) else {}
    )
    model_telemetry = (
        payload.get("model_telemetry") if isinstance(payload.get("model_telemetry"), dict) else {}
    )
    failover = payload.get("failover") if isinstance(payload.get("failover"), dict) else {}
    priorities = (
        payload.get("priority_actions") if isinstance(payload.get("priority_actions"), list) else []
    )
    sections = payload.get("sections") if isinstance(payload.get("sections"), list) else []

    calls = _as_int(model_telemetry.get("calls_24h"))
    errors = _as_int(model_telemetry.get("errors_24h"))
    return {
        "mode": payload.get("mode"),
        "generated_at": payload.get("generated_at"),
        "data_quality": {
            "status": data_quality.get("status"),
            "ready_sources": _as_int(data_quality.get("ready_sources")),
            "total_sources": _as_int(data_quality.get("total_sources")),
            "sources": [
                {
                    "id": _safe_text(source.get("id")),
                    "status": _safe_text(source.get("status")),
                    "rows": _as_int(source.get("rows")),
                }
                for source in _dicts(data_quality.get("sources"))
            ],
        },
        "metrics": {
            "signals": _as_int(metrics.get("signals")),
            "predictions": _as_int(metrics.get("predictions")),
            "regime_snapshots": _as_int(metrics.get("regime_snapshots")),
            "threats": _as_int(metrics.get("threats")),
            "leads": _as_int(metrics.get("leads")),
            "win_rate": _as_float(metrics.get("win_rate")),
            "latest_regime": _safe_text(metrics.get("latest_regime")),
            "fear_greed": _as_float(metrics.get("fear_greed")),
        },
        "model_telemetry": {
            "calls_24h": calls,
            "errors_24h": errors,
            "error_rate": round(errors / calls, 4) if calls else 0.0,
            "tier_count": len(_dicts(model_telemetry.get("tiers"))),
        },
        "failover": {
            "overall_status": _safe_text(failover.get("overall_status")),
            "degraded_lane_count": len(failover.get("degraded_lanes") or []),
            "lanes": [
                {
                    "lane": _safe_text(lane.get("lane")),
                    "label": _safe_text(lane.get("label")),
                    "status": _safe_text(lane.get("status")),
                    "counts": _safe_counts(lane.get("counts")),
                }
                for lane in _dicts(failover.get("lanes"))
            ],
        },
        "priority_actions": [
            {
                "lane": _safe_text(item.get("lane")),
                "severity": _safe_text(item.get("severity")),
                "title": _safe_text(item.get("title")),
                "plain_english": _safe_text(item.get("plain_english")),
            }
            for item in _dicts(priorities)[:6]
        ],
        "sections": [
            {
                "id": _safe_text(section.get("id")),
                "title": _safe_text(section.get("title")),
                "quality": _section_quality(section),
                "plain_english": _safe_text(section.get("plain_english")),
                "metrics": [
                    {
                        "label": _safe_text(metric.get("label")),
                        "value": _safe_value(metric.get("value")),
                    }
                    for metric in _dicts(section.get("metrics"))
                ],
            }
            for section in _dicts(sections)
        ],
        "analysis_guardrails": [
            "Research and market rows are not execution instructions.",
            "Public summaries omit raw operator evidence.",
            "Admin narrative must cite only numbers present in this snapshot.",
        ],
    }


def _build_prompt(snapshot: dict[str, Any]) -> str:
    body = json.dumps(snapshot, indent=2, sort_keys=True, default=str)
    return (
        "You are Sapphire OS's admin analysis agent. The operator needs a concise, "
        "professional interpretation of a passkey-gated dashboard snapshot. Use only "
        "the numbers and statuses in the JSON. Do not mention service names, hosts, "
        "raw links, secrets, credentials, or trade execution. Return JSON only with "
        "these string keys: plain_english, operator_read, risk_read, next_action. "
        "Keep each value under 42 words.\n\n"
        f"SNAPSHOT:\n{body}\n"
    )


def _vertex_generate(prompt: str) -> dict[str, Any] | None:
    try:
        import vertexai  # type: ignore[import-not-found]
        from vertexai.generative_models import GenerativeModel  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        log.info("admin narrative Vertex SDK unavailable: %s", exc)
        return None

    project = os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        log.info("admin narrative GCP project unset; skipping Vertex call")
        return None

    try:
        vertexai.init(project=project, location=ADMIN_ANALYSIS_NARRATIVE_REGION)
        model = GenerativeModel(ADMIN_ANALYSIS_NARRATIVE_MODEL)
        started = time.time()
        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.15,
                "max_output_tokens": 360,
                "top_p": 0.9,
            },
        )
        latency_ms = int((time.time() - started) * 1000)
        usage = getattr(response, "usage_metadata", None)
        return {
            "narrative": (getattr(response, "text", None) or "").strip(),
            "model": ADMIN_ANALYSIS_NARRATIVE_MODEL,
            "prompt_tokens": int(getattr(usage, "prompt_token_count", 0) or 0),
            "completion_tokens": int(getattr(usage, "candidates_token_count", 0) or 0),
            "latency_ms": latency_ms,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("admin narrative Vertex generate failed: %s", exc)
        return None


def _parse_model_narrative(text: str, fallback: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] | None = None
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            loaded = json.loads(text[start : end + 1])
            if isinstance(loaded, dict):
                payload = loaded
        except json.JSONDecodeError:
            payload = None

    if payload is None:
        return {
            "status": "parse_fallback",
            "plain_english": _clip(text, 420),
            "operator_read": fallback["operator_read"],
            "risk_read": fallback["risk_read"],
            "next_action": fallback["next_action"],
        }

    parsed = {}
    for field in _NARRATIVE_FIELDS:
        value = payload.get(field)
        parsed[field] = _clip(str(value).strip(), 420) if value else fallback[field]
    return parsed


def _cache_key(snapshot: dict[str, Any]) -> str:
    payload = {k: v for k, v in snapshot.items() if k != "generated_at"}
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _has_sensitive_data(text: str) -> bool:
    return bool(_SENSITIVE_RE.search(text or ""))


def _dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _as_pct(value: Any) -> str | None:
    number = _as_float(value)
    if number is None:
        return None
    return f"{number:.1%}"


def _safe_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return _SENSITIVE_RE.sub("[redacted]", text)[:180]


def _safe_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return _safe_text(value)


def _safe_counts(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _as_int(count) for key, count in value.items()}


def _section_quality(section: dict[str, Any]) -> dict[str, str]:
    quality = section.get("quality") if isinstance(section.get("quality"), dict) else {}
    return {
        "status": _safe_text(quality.get("status")),
        "basis": _safe_text(quality.get("basis")),
    }


def _first_priority(priorities: list[Any]) -> dict[str, str]:
    for item in priorities:
        if isinstance(item, dict):
            return {
                "title": str(item.get("title") or "No urgent admin action detected"),
                "plain_english": str(item.get("plain_english") or ""),
            }
    return {
        "title": "No urgent admin action detected",
        "plain_english": "Keep monitoring from the admin console.",
    }


def _priority_count(priorities: list[Any], severity: str) -> int:
    return sum(
        1
        for item in priorities
        if isinstance(item, dict) and str(item.get("severity") or "").lower() == severity
    )


def _clip(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 1].rstrip() + "..."
