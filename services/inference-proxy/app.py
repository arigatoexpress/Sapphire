"""Sapphire Inference Proxy - local fallback behind hosted agent lanes.

Current agentic Telegram direction:
  - Kimi/Gemini hosted lanes are primary for operator work and structured triage.
  - The PM bot owns Telegram ingress; this proxy must not create a sender path.
  - Local Ollama is fallback-only, with an inventory-verified common model.

Legacy/local tiers:
Tier 1: Windows GPU (192.168.1.61:11434) - primary local accelerator
Tier 2: Pi (rari1/rari2 via Tailscale) - disabled unless explicitly enabled
Tier 3: Mac local (127.0.0.1:11434) - sensitive/local fallback
Tier 4: Kimi Cloud (api.moonshot.ai/cn) - non-sensitive cloud fallback

Routing rules:
  - Kimi/Gemini agentic Telegram work routes outside this local proxy.
  - Sensitive queries: never reach Kimi Cloud (blocked at classifier)
  - Pi: lightweight models only (≤4B), not offered GPU-only jobs
  - All tiers use OpenAI-compatible output regardless of backend format

Fresh routing:
  auto/fast/quick/balanced     -> gemma3:4b common Mac/Windows fallback
  code/fast-code               -> qwen2.5-coder:14b common coder
  qwen3.6                      -> qwen3.6:35b-a3b exact Windows route
  kimi/cloud/research          -> Kimi Cloud, non-sensitive only
  nemotron/hermes              -> explicit compatibility only, never default

Endpoints:
  /v1/chat/completions  — OpenAI-compatible (what hermes-agent uses)
  /v1/models            — List models
  /v1/quota             — Current tenant quota policy and usage
  /v1/cache-stats       — Prompt-cache aggregate stats
  /health               — Full tier health report
  /failover/status      — Operator-grade failover mode + active fallback route
  /metrics              — Per-tier request/success/failure counters
"""

import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn

# Task classifier for auto-routing (no LLM required — keyword matching)
try:
    from task_classifier import classify_messages as _classify_messages

    _CLASSIFIER_AVAILABLE = True
except ImportError:
    _CLASSIFIER_AVAILABLE = False

# Kimi Claw Telegram relay — T4 fallback when Moonshot/OpenRouter API unavailable
_KIMI_RELAY_AVAILABLE = False
_kimi_relay_fn = None
_LIB_TELEGRAM = Path(__file__).parents[2] / "lib" / "telegram"
if str(_LIB_TELEGRAM) not in sys.path:
    sys.path.insert(0, str(_LIB_TELEGRAM))
try:
    from kimi_relay import relay_query as _relay_query

    _kimi_relay_fn = _relay_query
    _KIMI_RELAY_AVAILABLE = True
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("inference-proxy")

# ─── x402 payment gate (optional — X402_ENABLED=1 to activate) ────────────────
_SAPPHIRE_ROOT = Path(__file__).resolve().parents[2]
if str(_SAPPHIRE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SAPPHIRE_ROOT))
try:
    from lib.payments.x402_middleware import X402Middleware

    _X402 = X402Middleware(
        pricing={
            "/v1/chat/completions": float(os.getenv("X402_PRICE_CHAT", "0.001")),
            "/v1/completions": float(os.getenv("X402_PRICE_COMPLETIONS", "0.001")),
            "/v1/embeddings": float(os.getenv("X402_PRICE_EMBED", "0.0005")),
        }
    )
    _X402_AVAILABLE = True
    log.info(
        "x402 payment gate: enabled=%s recipient=%s network=%s",
        _X402.enabled,
        _X402.recipient[:10] + "..." if _X402.recipient else "-",
        _X402.network,
    )
except Exception as e:
    log.warning("x402 middleware unavailable: %s", e)
    _X402 = None
    _X402_AVAILABLE = False

# ─── Endpoints (overridable via env vars for network changes) ────────────────
WINDOWS_GPU = os.getenv("WINDOWS_GPU_URL", "http://192.168.1.61:11434")
PI_RARI1 = os.getenv("PI_RARI1_URL", "http://100.x.x.x:11434")
PI_RARI2 = os.getenv("PI_RARI2_URL", "http://100.x.x.y:11434")
MAC_LOCAL = os.getenv("MAC_LOCAL_URL", "http://127.0.0.1:11434")

# Kimi Cloud — permanent API keys only (no expiring CLI tokens)
# T4 primary:  Moonshot HTTP API (MOONSHOT_API_KEY → api.moonshot.cn)
# T4 fallback: @rarikimibot Telegram relay (KIMI_CLAW_BOT_TOKEN, needs shared group relay)
#              Bot token stored in ~/.hermes/.env — see docs/tradingview-cdp-setup.md and
#              ~/.hermes/skills/sapphire/kimi-delegate/SKILL.md for relay architecture
MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MOONSHOT_BASE = "https://api.moonshot.cn/v1"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
KIMI_RELAY_ENABLED = os.getenv("KIMI_RELAY_ENABLED", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

PORT = 11435

# ─── Model Routing ──────────────────────────────────────────────────────────
MODEL_TIERS = {
    # Fresh local fallback. Hosted Kimi/Gemini lanes are primary for agentic Telegram;
    # local aliases are for sensitive/offline work only.
    "auto": "gemma3:4b",
    "balanced": "gemma3:4b",
    "fast": "gemma3:4b",
    "quick": "gemma3:4b",
    "tiny": "gemma3:4b",
    "local": "gemma3:4b",
    "local-fallback": "gemma3:4b",
    # Heavy/local explicit routes
    "deep": "qwen3:14b",  # verified on Windows — deep multi-step
    "code": "qwen2.5-coder:14b",  # exact common Mac/Windows coder
    "fast-code": "qwen2.5-coder:14b",  # alias
    "reason": "deepseek-r1:14b",  # 80 tok/s, 9.0 GB — structured R1 reasoning
    "qwen-reason": "qwen3.5:4b",  # exact installed Windows reasoning route
    "fast-reason": "qwen3.5:4b",  # alias
    "large": "qwen3-coder:30b",  # exact installed Windows large route
    "cascade": "qwen3.6:35b-a3b",  # compatibility alias to installed MoE
    "moe": "qwen3.6:35b-a3b",  # alias
    "qwen3.6": "qwen3.6:35b-a3b",  # exact installed Windows model
    # Legacy aliases (kept for compatibility)
    "legacy-nemotron": "nemotron-3-nano:4b",
    "qwen2.5-coder": "qwen2.5-coder:14b",  # installed on both Mac and Windows
    "phi4": "deepseek-r1:14b",  # compatibility alias; phi4 is not installed
    # Kimi Cloud routes (non-sensitive only)
    "kimi": "kimi-cloud",
    "kimi-fast": "kimi-cloud",
    "kimi-large": "kimi-cloud",
    "kimi-cloud": "kimi-cloud",
    "kimi-code": "kimi-cloud",
    "cloud": "kimi-cloud",
    "research": "kimi-cloud",
}

# Models that require Windows GPU (too large for Pi/Mac).
# gemma3:27b removed — consistently times out on llama-server b8795 (OOM at 17.4 GB).
# The common 4B/14B fallbacks are installed on both Mac and Windows.
# Windows-only names fail closed rather than silently changing model families.
GPU_ONLY_MODELS = {
    # Exact Windows-only models.
    "qwen3:14b",
    "qwen3.5:4b",
    "qwen3.6:35b-a3b",
    "qwen3-coder:30b",
    "gemma4:12b",
    "gpt-oss:20b",
    "qwen2.5:14b",
    "llama3.3:70b",
}

# Models that fit on Pi in principle (used for aliasing + inventory visibility).
PI_MODELS = {
    "nemotron-mini:4b",
    "nemotron-mini",
    "nemotron-mini:latest",
    "gemma2:2b",
    "qwen2.5:0.5b",
    "smollm2:1.7b",
}
# Models we trust for live Pi routing. nemotron-mini is installed on the Pis,
# but it times out often enough that T2 should downshift to the smaller qwen
# default instead of blackholing "fast" traffic.
PI_SERVE_MODELS = {"qwen2.5:0.5b", "smollm2:1.7b", "gemma2:2b"}
PI_DEFAULT_MODEL = "qwen2.5:0.5b"  # fastest Pi model (~20s cold load)
MAC_FALLBACK_MODEL = "gemma3:4b"

# Mac models (models confirmed available locally)
MAC_MODELS = {
    "gemma3:4b",
    "codestral:22b",
    "deepseek-r1:14b",
    "qwen2.5-coder:14b",
    "nemotron-3-nano:4b",
    "nemotron-3-nano:4b-64k",
    "sov-coder:latest",
    "sov-reason:latest",
}
MAC_MODEL_ALIASES = {
    "nemotron-3-nano": "nemotron-3-nano:4b",
    "nemotron-3-nano:latest": "nemotron-3-nano:4b",
}
MAC_EXACT_FALLBACK_MODELS = (MAC_MODELS | set(MAC_MODEL_ALIASES)) - PI_SERVE_MODELS

# Enable Pi tiers independently — both Pis are online as of 2026-04-18.
PI_RARI1_ENABLED = os.getenv("PI_RARI1_ENABLED", os.getenv("PI_OLLAMA_ENABLED", "0")) == "1"
PI_RARI2_ENABLED = os.getenv("PI_RARI2_ENABLED", "0") == "1"
PI_ENABLED = PI_RARI1_ENABLED or PI_RARI2_ENABLED  # any Pi active
PI_PROBE_TIMEOUT_SEC = float(os.getenv("PI_PROBE_TIMEOUT_SEC", "10"))
PI_CHAT_TIMEOUT_SEC = int(os.getenv("PI_CHAT_TIMEOUT_SEC", "30"))
WINDOWS_PROBE_TIMEOUT_SEC = float(os.getenv("WINDOWS_PROBE_TIMEOUT_SEC", "4"))
WINDOWS_CHAT_TIMEOUT_SEC = int(os.getenv("WINDOWS_CHAT_TIMEOUT_SEC", "90"))
MAC_PROBE_TIMEOUT_SEC = float(os.getenv("MAC_PROBE_TIMEOUT_SEC", "4"))

# ─── Health Tracking ─────────────────────────────────────────────────────────
ENDPOINTS = ["windows-gpu", "pi-rari1", "pi-rari2", "mac-local", "kimi-cloud"]
_endpoint_health = {k: True for k in ENDPOINTS}
_last_health_check = {k: 0.0 for k in ENDPOINTS}
_health_lock = threading.Lock()
HEALTH_COOLDOWN = 120  # seconds before retrying a failed endpoint


def _is_healthy(name: str) -> bool:
    with _health_lock:
        if _endpoint_health[name]:
            return True
        # Cooldown avoids hammering a down endpoint on every request — each
        # failed probe costs a 15–90s timeout that blocks the caller.
        return time.time() - _last_health_check[name] > HEALTH_COOLDOWN


def _mark_failed(name: str):
    with _health_lock:
        _endpoint_health[name] = False
        _last_health_check[name] = time.time()


def _mark_ok(name: str):
    with _health_lock:
        was_failed = not _endpoint_health[name]
        _endpoint_health[name] = True
        _last_health_check[name] = time.time()
        if was_failed:
            log.info("Endpoint %s recovered", name)


def _should_preflight(name: str, max_age_sec: float = 30) -> bool:
    """Return True when a healthy endpoint has stale or unverified reachability."""
    with _health_lock:
        age = time.time() - _last_health_check.get(name, 0.0)
        if not _endpoint_health.get(name, False):
            return age > HEALTH_COOLDOWN
        return age > max_age_sec


def _endpoint_enabled(name: str) -> bool:
    """Return whether an endpoint should participate in live probing/routing."""
    if name == "pi-rari1":
        return PI_RARI1_ENABLED
    if name == "pi-rari2":
        return PI_RARI2_ENABLED
    return True


def _endpoint_status(name: str) -> str:
    """Return a health status that distinguishes disabled tiers from failures."""
    if not _endpoint_enabled(name):
        return "disabled"
    return "healthy" if _is_healthy(name) else "failed"


def _tier_inventory() -> dict[str, str]:
    """Return public, non-secret endpoint inventory for health/readiness views."""
    return {
        "t1_windows_gpu": WINDOWS_GPU,
        "t2_pi_rari1": f"{PI_RARI1} (enabled={PI_RARI1_ENABLED})",
        "t2_pi_rari2": f"{PI_RARI2} (enabled={PI_RARI2_ENABLED})",
        "t3_mac_local": MAC_LOCAL,
        "t4_kimi_cloud": MOONSHOT_BASE,
        "t4_kimi_telegram_relay": f"enabled={KIMI_RELAY_ENABLED}",
    }


def _endpoint_status_snapshot() -> dict[str, str]:
    """Return current endpoint status without exposing raw health internals."""
    return {name: _endpoint_status(name) for name in ENDPOINTS}


def _failover_status_payload() -> dict[str, object]:
    """Build the operator contract for Windows-offline/local/cloud failover.

    This intentionally distinguishes "degraded but covered" from "down":
    Windows can be offline while Sapphire remains operational through Mac/Pi
    local tiers and non-sensitive cloud fallback.
    """
    endpoints = _endpoint_status_snapshot()
    local_candidates = ("pi-rari1", "pi-rari2", "mac-local")
    ordered_route = ("windows-gpu", "pi-rari1", "pi-rari2", "mac-local", "kimi-cloud")
    enabled_local = [name for name in local_candidates if endpoints.get(name) != "disabled"]
    healthy_local = [name for name in enabled_local if endpoints.get(name) == "healthy"]
    healthy_cloud = endpoints.get("kimi-cloud") == "healthy"
    cloud_api_configured = bool(MOONSHOT_API_KEY or OPENROUTER_API_KEY)
    windows_healthy = endpoints.get("windows-gpu") == "healthy"
    active_route = next(
        (name for name in ordered_route if endpoints.get(name) == "healthy"),
        None,
    )

    if windows_healthy:
        mode = "primary"
        status = "ok"
    elif healthy_local:
        mode = "local_failover"
        status = "degraded"
    elif healthy_cloud:
        mode = "cloud_failover"
        status = "degraded"
    else:
        mode = "unavailable"
        status = "fail"

    recommended_actions: list[str] = []
    if not windows_healthy:
        recommended_actions.append(
            "Windows GPU tier is offline; keep GPU-only jobs paused or route them to exact Mac models when available."
        )
    if not healthy_local:
        recommended_actions.append(
            "No local fallback tier is healthy; restore Mac Ollama or enable a Pi tier before relying on sensitive inference."
        )
    if not healthy_cloud:
        recommended_actions.append(
            "Cloud fallback is unavailable; verify MOONSHOT_API_KEY or OpenRouter configuration."
        )
    if healthy_cloud and not cloud_api_configured and not KIMI_RELAY_ENABLED:
        recommended_actions.append(
            "Kimi cloud health is optimistic but no API key is configured; Telegram relay is disabled by default to prevent group spam."
        )
    if endpoints.get("pi-rari1") == "disabled" and endpoints.get("pi-rari2") == "disabled":
        recommended_actions.append(
            "Pi tiers are disabled; enable one only after a live probe confirms the device is reachable."
        )
    if not recommended_actions:
        recommended_actions.append("All failover tiers are healthy; keep current routing.")

    tiers = [
        {
            "tier": "T1",
            "endpoint": "windows-gpu",
            "role": "primary_gpu",
            "location": "windows",
            "status": endpoints["windows-gpu"],
            "enabled": endpoints["windows-gpu"] != "disabled",
        },
        {
            "tier": "T2",
            "endpoint": "pi-rari1",
            "role": "local_lightweight",
            "location": "local_device",
            "status": endpoints["pi-rari1"],
            "enabled": endpoints["pi-rari1"] != "disabled",
        },
        {
            "tier": "T2",
            "endpoint": "pi-rari2",
            "role": "local_lightweight",
            "location": "local_device",
            "status": endpoints["pi-rari2"],
            "enabled": endpoints["pi-rari2"] != "disabled",
        },
        {
            "tier": "T3",
            "endpoint": "mac-local",
            "role": "local_sensitive_fallback",
            "location": "mac",
            "status": endpoints["mac-local"],
            "enabled": endpoints["mac-local"] != "disabled",
        },
        {
            "tier": "T4",
            "endpoint": "kimi-cloud",
            "role": "non_sensitive_cloud_fallback",
            "location": "cloud",
            "status": endpoints["kimi-cloud"],
            "enabled": endpoints["kimi-cloud"] != "disabled",
        },
    ]

    return {
        "status": status,
        "service": "inference-proxy",
        "runtime_profile": "kimi_gemini_first_local_fallback",
        "mode": mode,
        "active_route": active_route,
        "fallback_ready": bool(healthy_local or healthy_cloud),
        "windows_offline": not windows_healthy,
        "sensitive_cloud_block": True,
        "local_fallback_model": MAC_FALLBACK_MODEL,
        "deprecated_default_models": ["nemotron-mini:4b", "hermes3:8b"],
        "cloud_api_configured": cloud_api_configured,
        "telegram_relay_available": bool(_KIMI_RELAY_AVAILABLE and _kimi_relay_fn),
        "telegram_relay_enabled": KIMI_RELAY_ENABLED,
        "local_fallbacks": healthy_local,
        "cloud_fallbacks": ["kimi-cloud"] if healthy_cloud else [],
        "endpoints": endpoints,
        "tiers": tiers,
        "recommended_actions": recommended_actions,
    }


# ─── Metrics ─────────────────────────────────────────────────────────────────
_metrics = {
    name: {"requests": 0, "success": 0, "failure": 0, "total_ms": 0}
    for name in ENDPOINTS + ["proxy"]
}
_metrics_lock = threading.Lock()
_call_log_lock = threading.Lock()


_MAX_METRIC_KEYS = 32  # Guard against unbounded growth from unknown tier names
_CALL_LOG_ENABLED = os.getenv("INFERENCE_CALL_LOG_ENABLED", "1") != "0"
_CALL_LOG_DEFAULT_PATH = Path.home() / ".cache" / "sapphire" / "inference_proxy" / "calls.jsonl"
_CALL_LOG_TIER_MAP = {
    "windows-gpu": "T1_windows_gpu",
    "pi-rari1": "T2_pi_rari1",
    "pi-rari2": "T2_pi_rari2",
    "mac-local": "T3_mac_local",
    "kimi-cloud": "T4_kimi_cloud",
}


def _calls_log_path() -> Path:
    return Path(os.getenv("INFERENCE_PROXY_CALLS_PATH", str(_CALL_LOG_DEFAULT_PATH))).expanduser()


def _coerce_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _usage_from_response(response) -> tuple[int, int]:
    if isinstance(response, bytes):
        try:
            response = json.loads(response.decode())
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 0, 0
    if not isinstance(response, dict):
        return 0, 0
    usage = response.get("usage") or {}
    if not isinstance(usage, dict):
        return 0, 0
    return (
        _coerce_int(usage.get("prompt_tokens", usage.get("tokens_in", 0))),
        _coerce_int(usage.get("completion_tokens", usage.get("tokens_out", 0))),
    )


def _append_call_record(
    tier: str,
    *,
    success: bool,
    elapsed_ms: int,
    model: str = "",
    response=None,
    error_class: str | None = None,
) -> None:
    """Append sanitized per-tier telemetry without storing prompts or completions."""
    if not _CALL_LOG_ENABLED:
        return
    canonical_tier = _CALL_LOG_TIER_MAP.get(tier)
    if not canonical_tier:
        return
    tokens_in, tokens_out = _usage_from_response(response)
    record = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "tier": canonical_tier,
        "model": str(model or ""),
        "latency_ms": max(0, int(elapsed_ms or 0)),
        "ok": bool(success),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "error_class": None if success else (error_class or "InferenceError"),
    }
    try:
        path = _calls_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        with _call_log_lock:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line)
    except OSError as exc:
        log.warning("inference call telemetry write failed: %s", exc)


def _record(
    tier: str,
    success: bool,
    elapsed_ms: int,
    *,
    model: str = "",
    response=None,
    error_class: str | None = None,
):
    with _metrics_lock:
        if tier not in _metrics and len(_metrics) >= _MAX_METRIC_KEYS:
            log.warning(
                "_record: metrics dict full (%d keys), dropping tier '%s'", _MAX_METRIC_KEYS, tier
            )
            return
        m = _metrics.setdefault(tier, {"requests": 0, "success": 0, "failure": 0, "total_ms": 0})
        m["requests"] += 1
        if success:
            m["success"] += 1
        else:
            m["failure"] += 1
        m["total_ms"] += elapsed_ms
    _append_call_record(
        tier,
        success=success,
        elapsed_ms=elapsed_ms,
        model=model,
        response=response,
        error_class=error_class,
    )


# ─── Tenant Quotas + Prompt Cache ────────────────────────────────────────────

_DEFAULT_REQUESTS_PER_DAY = int(os.getenv("INFERENCE_DEFAULT_REQUESTS_PER_DAY", "1000"))
_DEFAULT_TOKENS_PER_DAY = int(os.getenv("INFERENCE_DEFAULT_TOKENS_PER_DAY", "500000"))
_DEFAULT_CACHE_TTL_SECONDS = int(os.getenv("INFERENCE_DEFAULT_CACHE_TTL_SECONDS", "300"))
_MAX_TOKENS_PER_REQUEST = int(os.getenv("INFERENCE_MAX_TOKENS_PER_REQUEST", "4096"))
_REQUIRE_API_KEY = os.getenv("INFERENCE_REQUIRE_API_KEY", "0") == "1"

_tenant_usage: dict[str, dict[str, int | str]] = {}
_tenant_usage_lock = threading.Lock()
_prompt_cache: dict[str, dict] = {}
_prompt_cache_lock = threading.Lock()
_prompt_cache_stats = {"hits": 0, "misses": 0, "writes": 0, "evictions": 0}


def _hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def _stable_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _default_tenant_policy() -> dict:
    return {
        "tenant_id": "anonymous",
        "requests_per_day": _DEFAULT_REQUESTS_PER_DAY,
        "tokens_per_day": _DEFAULT_TOKENS_PER_DAY,
        "cache_ttl_seconds": _DEFAULT_CACHE_TTL_SECONDS,
    }


def _normalize_tenant_policy(raw: dict | None, *, tenant_id: str) -> dict:
    raw = dict(raw or {})
    return {
        "tenant_id": str(raw.get("tenant") or raw.get("tenant_id") or tenant_id),
        "requests_per_day": max(
            0,
            int(raw.get("requests_per_day", _DEFAULT_REQUESTS_PER_DAY)),
        ),
        "tokens_per_day": max(0, int(raw.get("tokens_per_day", _DEFAULT_TOKENS_PER_DAY))),
        "cache_ttl_seconds": max(
            0,
            int(raw.get("cache_ttl_seconds", _DEFAULT_CACHE_TTL_SECONDS)),
        ),
    }


def _load_quota_config() -> dict:
    """Load tenant quota policy from env/file without logging raw keys."""
    raw = os.getenv("INFERENCE_QUOTAS_JSON", "").strip()
    config_path = os.getenv("INFERENCE_QUOTAS_FILE", "").strip()
    if not raw and config_path:
        try:
            raw = Path(config_path).expanduser().read_text().strip()
        except OSError as exc:
            log.warning("Could not read inference quota config file: %s", exc)
            raw = ""

    default_policy = _default_tenant_policy()
    key_policies: dict[str, dict] = {}
    if not raw:
        return {"default": default_policy, "keys": key_policies}

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.warning("Invalid INFERENCE_QUOTAS_JSON; using defaults: %s", exc)
        return {"default": default_policy, "keys": key_policies}

    if not isinstance(parsed, dict):
        log.warning("INFERENCE_QUOTAS_JSON must be a JSON object; using defaults")
        return {"default": default_policy, "keys": key_policies}

    default_policy = _normalize_tenant_policy(parsed.get("default"), tenant_id="anonymous")
    keys = parsed.get("keys") or {}
    if not isinstance(keys, dict):
        log.warning("INFERENCE_QUOTAS_JSON.keys must be a JSON object; ignoring keys")
        keys = {}

    for api_key, policy in keys.items():
        if not isinstance(api_key, str) or not api_key:
            continue
        if not isinstance(policy, dict):
            policy = {}
        key_hash = _hash_api_key(api_key)
        key_policies[key_hash] = _normalize_tenant_policy(
            policy,
            tenant_id=f"key-{key_hash[:12]}",
        )
    return {"default": default_policy, "keys": key_policies}


_quota_config = _load_quota_config()


def _extract_api_key(headers) -> str | None:
    header_value = headers.get("X-API-Key") or headers.get("X-Sapphire-API-Key")
    if header_value:
        return header_value.strip() or None
    auth = headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(None, 1)[1].strip() or None
    return None


def _tenant_context(headers) -> tuple[dict | None, dict | None]:
    api_key = _extract_api_key(headers)
    if not api_key:
        if _REQUIRE_API_KEY:
            return None, {
                "error": "Inference API key required",
                "code": "api_key_required",
            }
        return dict(_quota_config["default"]), None

    key_hash = _hash_api_key(api_key)
    known = _quota_config["keys"].get(key_hash)
    if known:
        return dict(known), None
    if _REQUIRE_API_KEY:
        return None, {
            "error": "Unknown inference API key",
            "code": "api_key_unknown",
        }

    policy = dict(_quota_config["default"])
    policy["tenant_id"] = f"key-{key_hash[:12]}"
    return policy, None


def _usage_day(now: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(now or time.time()))


def _tenant_usage_snapshot(tenant_id: str, *, policy: dict | None = None) -> dict:
    with _tenant_usage_lock:
        day = _usage_day()
        usage = _tenant_usage.get(tenant_id)
        if usage is None or usage.get("day") != day:
            usage = {"day": day, "requests": 0, "tokens": 0}
        result = dict(usage)
    if policy:
        result["remaining_requests"] = max(0, policy["requests_per_day"] - result["requests"])
        result["remaining_tokens"] = max(0, policy["tokens_per_day"] - result["tokens"])
    return result


def _estimate_prompt_tokens(messages: list) -> int:
    chars = 0
    for msg in messages:
        content = msg.get("content", "") if isinstance(msg, dict) else ""
        if isinstance(content, str):
            chars += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    chars += len(str(block.get("text", "")))
    return max(1, chars // 4)


def _reserve_quota(tenant_id: str, policy: dict, token_cost: int) -> dict | None:
    with _tenant_usage_lock:
        day = _usage_day()
        usage = _tenant_usage.setdefault(tenant_id, {"day": day, "requests": 0, "tokens": 0})
        if usage.get("day") != day:
            usage.clear()
            usage.update({"day": day, "requests": 0, "tokens": 0})

        next_requests = int(usage["requests"]) + 1
        next_tokens = int(usage["tokens"]) + token_cost
        if next_requests > policy["requests_per_day"]:
            return {
                "error": "Inference request quota exceeded",
                "code": "quota_exceeded",
                "limit": "requests_per_day",
                "tenant": tenant_id,
            }
        if next_tokens > policy["tokens_per_day"]:
            return {
                "error": "Inference token quota exceeded",
                "code": "quota_exceeded",
                "limit": "tokens_per_day",
                "tenant": tenant_id,
            }

        usage["requests"] = next_requests
        usage["tokens"] = next_tokens
    return None


def _quota_headers(tenant_id: str, policy: dict, *, cache_state: str = "") -> dict[str, str]:
    usage = _tenant_usage_snapshot(tenant_id, policy=policy)
    headers = {
        "X-Inference-Tenant": tenant_id,
        "X-Inference-Quota-Remaining-Requests": str(usage["remaining_requests"]),
        "X-Inference-Quota-Remaining-Tokens": str(usage["remaining_tokens"]),
    }
    if cache_state:
        headers["X-Inference-Cache"] = cache_state
    return headers


def _cache_key(tenant_id: str, path: str, request_data: dict) -> str:
    payload = _stable_json({"tenant": tenant_id, "path": path, "request": request_data})
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_get(key: str) -> dict | None:
    now = time.time()
    with _prompt_cache_lock:
        entry = _prompt_cache.get(key)
        if not entry:
            _prompt_cache_stats["misses"] += 1
            return None
        if float(entry.get("expires_at", 0)) <= now:
            _prompt_cache.pop(key, None)
            _prompt_cache_stats["evictions"] += 1
            _prompt_cache_stats["misses"] += 1
            return None
        entry["hits"] = int(entry.get("hits", 0)) + 1
        _prompt_cache_stats["hits"] += 1
        return dict(entry)


def _cache_set(
    key: str,
    *,
    tenant_id: str,
    ttl_seconds: int,
    response: dict,
    tier: str,
) -> None:
    if ttl_seconds <= 0:
        return
    with _prompt_cache_lock:
        _prompt_cache[key] = {
            "tenant_id": tenant_id,
            "expires_at": time.time() + ttl_seconds,
            "response": response,
            "tier": tier,
            "created_at": int(time.time()),
            "hits": 0,
        }
        _prompt_cache_stats["writes"] += 1


def _cache_stats() -> dict:
    with _prompt_cache_lock:
        by_tenant: dict[str, int] = {}
        for entry in _prompt_cache.values():
            tenant = str(entry.get("tenant_id", "unknown"))
            by_tenant[tenant] = by_tenant.get(tenant, 0) + 1
        return {
            "entries": len(_prompt_cache),
            "by_tenant": by_tenant,
            "stats": dict(_prompt_cache_stats),
        }


def _is_http_url(url: str) -> bool:
    """Return True only for HTTP(S) URLs with a hostname."""
    parsed = urllib.parse.urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


# ─── Sensitivity Classifier ──────────────────────────────────────────────────
# Blocks routing to Kimi Cloud for any query that may contain private data.
# Heuristic-based — no LLM required (runs before inference).

_SENSITIVE_PATTERNS = re.compile(
    r"""
    # API keys / tokens (exact patterns only)
    api[_\-.]?key|apikey|\bbearer\b|\bjwt\b|
    # OAuth tokens and service account fields
    access_token|refresh_token|id_token|client_secret|
    # Private key fields (service accounts, OAuth apps)
    private_key|privatekey|
    # Passwords / secrets
    password|passwd|\bsecret\b|
    # SSH private keys (PEM headers)
    BEGIN\s+(?:RSA\s+|OPENSSH\s+|EC\s+)?PRIVATE\s+KEY|
    # Database connection strings with embedded credentials
    (?:postgres|mysql|mongodb|redis)://[^@\s]+:[^@\s]+@|
    # Slack tokens
    xox[bpao]-[0-9A-Za-z\-]+|
    # Financial PII
    \b\d{4}[\s\-]\d{4}[\s\-]\d{4}[\s\-]\d{4}\b|  # credit card
    \b\d{3}-\d{2}-\d{4}\b|                         # SSN
    routing\.num                                    # routing number
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _is_sensitive(messages: list) -> bool:
    """Return True if any message content looks like private/sensitive data."""
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str) and _SENSITIVE_PATTERNS.search(content):
            return True
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and _SENSITIVE_PATTERNS.search(block.get("text", "")):
                    return True
    return False


# ─── Ollama Native Caller ────────────────────────────────────────────────────


def _call_native_ollama(
    base_url: str,
    model: str,
    messages: list,
    max_tokens: int = 512,
    temperature: float = 0.7,
    timeout: int = 15,
) -> dict:
    """Call Ollama native /api/chat and return the raw response dict."""
    target_url = f"{base_url}/api/chat"
    if not _is_http_url(target_url):
        raise ValueError("Blocked non-HTTP Ollama backend URL")
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": -1,  # keep model loaded in VRAM between requests
            "options": {"temperature": temperature, "num_predict": max_tokens},
        }
    ).encode()
    req = urllib.request.Request(
        target_url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
        return json.loads(resp.read())


def _native_to_openai(native_resp: dict, model: str) -> dict:
    """Convert Ollama native /api/chat response to OpenAI-compatible format.

    Handles qwen3/thinking models: if content is empty but thinking is present,
    use the thinking field as the response content (reasoning-mode output).
    """
    msg = native_resp.get("message", {})
    content = msg.get("content", "")
    # Thinking models (qwen3, deepseek-r1) may put all output in 'thinking'
    # and leave 'content' empty. Surface the thinking as the response.
    if not content:
        thinking = msg.get("thinking", "")
        if thinking:
            content = f"[thinking]\n{thinking}"
    return {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": msg.get("role", "assistant"),
                    "content": content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": native_resp.get("prompt_eval_count", 0),
            "completion_tokens": native_resp.get("eval_count", 0),
            "total_tokens": native_resp.get("prompt_eval_count", 0)
            + native_resp.get("eval_count", 0),
        },
    }


def _try_ollama_native(
    endpoint_name: str,
    base_url: str,
    model: str,
    messages: list,
    max_tokens: int,
    temperature: float,
    timeout: int = 60,
) -> dict | None:
    """Try a native Ollama endpoint. Returns OpenAI-format dict or None.

    Only marks an endpoint failed for connection-level errors (refused, no route).
    HTTP 404 (model not found) and timeouts (cold model load) do NOT blacklist.
    """
    if not _is_healthy(endpoint_name):
        return None
    t0 = time.time()
    try:
        native = _call_native_ollama(base_url, model, messages, max_tokens, temperature, timeout)
        msg = native.get("message", {})
        content = msg.get("content", "") or msg.get("thinking", "")
        if not content:
            log.warning("x %s returned empty content for model '%s'", endpoint_name, model)
            return None
        elapsed = int((time.time() - t0) * 1000)
        _mark_ok(endpoint_name)
        openai_response = _native_to_openai(native, model)
        _record(endpoint_name, True, elapsed, model=model, response=openai_response)
        log.info(
            "-> inference via %s (native ollama, model=%s, %dms)", endpoint_name, model, elapsed
        )
        return openai_response
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log.warning("x %s: model '%s' not found (404) — endpoint healthy", endpoint_name, model)
        else:
            log.warning("x %s native HTTP %d: %s", endpoint_name, e.code, str(e)[:60])
            _mark_failed(endpoint_name)
            _record(
                endpoint_name,
                False,
                int((time.time() - t0) * 1000),
                model=model,
                error_class=type(e).__name__,
            )
        return None
    except (TimeoutError, OSError) as e:
        err_str = str(e)
        elapsed = int((time.time() - t0) * 1000)
        # Word-boundary "time" check — the prior `"time" in last.lower()` also
        # matched "timestamp", "timeseries", etc., misclassifying unrelated
        # errors as timeouts. Use explicit substrings instead.
        err_lower = err_str.lower()
        if "timed out" in err_lower or "timeout" in err_lower or isinstance(e, TimeoutError):
            # Timeout means the host is unreachable or hung — engage circuit breaker.
            # (Cold model loads in Ollama respond normally; a socket timeout = host down.)
            log.warning("x %s timed out after %dms — marking failed", endpoint_name, elapsed)
            _mark_failed(endpoint_name)
            _record(endpoint_name, False, elapsed, model=model, error_class=type(e).__name__)
        elif "Connection refused" in err_str or "No route" in err_str:
            log.warning("x %s unreachable (%s): %s", endpoint_name, base_url, err_str[:60])
            _mark_failed(endpoint_name)
            _record(endpoint_name, False, elapsed, model=model, error_class=type(e).__name__)
        else:
            log.warning("x %s OS error: %s", endpoint_name, err_str[:80])
            _mark_failed(endpoint_name)
            _record(endpoint_name, False, elapsed, model=model, error_class=type(e).__name__)
        return None
    except Exception as e:
        err_str = str(e)
        elapsed = int((time.time() - t0) * 1000)
        if "timed out" in err_str:
            log.warning("x %s timed out — marking failed", endpoint_name)
            _mark_failed(endpoint_name)
            _record(endpoint_name, False, elapsed, model=model, error_class=type(e).__name__)
        else:
            log.warning("x %s failed: %s", endpoint_name, err_str[:80])
            _mark_failed(endpoint_name)
            _record(endpoint_name, False, elapsed, model=model, error_class=type(e).__name__)
        return None


# ─── Mac Local (OpenAI-compat passthrough) ───────────────────────────────────


def _try_mac_local(path: str, body: bytes, model: str = "") -> tuple[int, bytes] | None:
    """Try Mac local Ollama via OpenAI-compat /v1/ endpoint.

    Only marks failed for connection-level errors.
    """
    if not _is_healthy("mac-local"):
        return None
    t0 = time.time()
    try:
        url = f"{MAC_LOCAL}{path}"
        if not _is_http_url(url):
            log.warning("x mac-local blocked non-HTTP backend URL")
            return None
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310
            data = resp.read()
            elapsed = int((time.time() - t0) * 1000)
            _mark_ok("mac-local")
            _record("mac-local", True, elapsed, model=model, response=data)
            log.info(
                "-> inference via mac-local (openai-compat, model=%s, %dms)", model or "?", elapsed
            )
            return resp.status, data
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log.warning("x mac-local: model '%s' not found (404) — endpoint healthy", model)
        else:
            log.warning("x mac-local HTTP %d: %s", e.code, str(e)[:60])
            _mark_failed("mac-local")
            _record(
                "mac-local",
                False,
                int((time.time() - t0) * 1000),
                model=model,
                error_class=type(e).__name__,
            )
        return None
    except BrokenPipeError:
        log.warning("x mac-local: client disconnected (BrokenPipe) — endpoint healthy")
        return None
    except Exception as e:
        log.warning("x mac-local failed: %s", str(e)[:80])
        _mark_failed("mac-local")
        _record(
            "mac-local",
            False,
            int((time.time() - t0) * 1000),
            model=model,
            error_class=type(e).__name__,
        )
        return None


# ─── Kimi Cloud ──────────────────────────────────────────────────────────────

# Allowlist of hostnames the proxy is permitted to make outbound HTTPS calls to.
# Any base URL not matching this set is rejected before the request is sent.
_ALLOWED_CLOUD_HOSTS: frozenset[str] = frozenset(
    {
        "api.moonshot.cn",
        "openrouter.ai",
        "api.openai.com",
        "api.telegram.org",
    }
)


def _is_allowed_outbound(url: str) -> bool:
    """Return True if *url*'s hostname is on the cloud allowlist."""
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    return host in _ALLOWED_CLOUD_HOSTS


def _call_openai_compat(
    base: str,
    model: str,
    api_key: str,
    messages: list,
    max_tokens: int,
    temperature: float,
    label: str,
) -> dict | None:
    """Generic OpenAI-compatible cloud call. Returns OpenAI-format dict or None."""
    target_url = f"{base}/chat/completions"
    if not _is_allowed_outbound(target_url):
        log.warning("_call_openai_compat: blocked outbound to %s — not in allowlist", base)
        return None
    payload = json.dumps(
        {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
    ).encode()
    t0 = time.time()
    try:
        req = urllib.request.Request(
            target_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:  # nosec B310
            data = json.loads(resp.read())
            elapsed = int((time.time() - t0) * 1000)
            _mark_ok("kimi-cloud")
            data["model"] = label
            _record("kimi-cloud", True, elapsed, model=label, response=data)
            log.info("-> inference via %s (%dms)", label, elapsed)
            return data
    except Exception as e:
        _mark_failed("kimi-cloud")
        _record(
            "kimi-cloud",
            False,
            int((time.time() - t0) * 1000),
            model=label,
            error_class=type(e).__name__,
        )
        log.warning("x %s failed: %s", label, str(e)[:80])
        return None


def _call_kimi_cloud(
    messages: list, max_tokens: int = 2048, temperature: float = 0.7
) -> dict | None:
    """Call cloud research API. Priority: Moonshot API → OpenRouter → Telegram relay."""
    if not _is_healthy("kimi-cloud"):
        return None

    if MOONSHOT_API_KEY:
        result = _call_openai_compat(
            base=MOONSHOT_BASE,
            model="moonshot-v1-8k",
            api_key=MOONSHOT_API_KEY,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            label="moonshot-api",
        )
        if result:
            return result

    if OPENROUTER_API_KEY:
        result = _call_openai_compat(
            base=OPENROUTER_BASE,
            model="moonshot/moonshot-v1-8k",
            api_key=OPENROUTER_API_KEY,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            label="openrouter",
        )
        if result:
            return result

    # Telegram relay fallback — @rarikimibot in shared group. This can send a
    # real group message, so it is disabled unless deliberately enabled.
    if not KIMI_RELAY_ENABLED:
        log.debug("kimi-relay: disabled by KIMI_RELAY_ENABLED")
    elif _KIMI_RELAY_AVAILABLE and _kimi_relay_fn:
        relay_chat_id = os.environ.get("KIMI_RELAY_CHAT_ID", "")
        send_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        reader_token = os.environ.get("RELAY_READER_TOKEN", "")
        if relay_chat_id and send_token and reader_token:
            # Flatten messages into a single query string for the relay
            query_parts = []
            for m in messages:
                role = m.get("role", "")
                content = m.get("content", "")
                if isinstance(content, list):
                    content = " ".join(b.get("text", "") for b in content if isinstance(b, dict))
                if content:
                    query_parts.append(f"[{role}]: {content}" if role not in ("user",) else content)
            query = "\n".join(query_parts).strip()
            if query:
                t0 = time.time()
                try:
                    text = _kimi_relay_fn(query)
                    if not text or not text.strip():
                        log.warning("x kimi-relay returned empty response")
                        _mark_failed("kimi-cloud")
                        _record(
                            "kimi-cloud",
                            False,
                            int((time.time() - t0) * 1000),
                            model="kimi-relay",
                            error_class="EmptyResponse",
                        )
                        return None
                    elapsed = int((time.time() - t0) * 1000)
                    _mark_ok("kimi-cloud")
                    log.info("-> inference via kimi-relay (telegram, %dms)", elapsed)
                    response = {
                        "id": f"chatcmpl-relay-{int(time.time())}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": "kimi-relay",
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": text},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    }
                    _record("kimi-cloud", True, elapsed, model="kimi-relay", response=response)
                    return response
                except Exception as e:
                    elapsed = int((time.time() - t0) * 1000)
                    _mark_failed("kimi-cloud")
                    _record(
                        "kimi-cloud",
                        False,
                        elapsed,
                        model="kimi-relay",
                        error_class=type(e).__name__,
                    )
                    log.warning("x kimi-relay failed: %s", str(e)[:80])
        else:
            log.debug(
                "kimi-relay: TELEGRAM_BOT_TOKEN, RELAY_READER_TOKEN, or KIMI_RELAY_CHAT_ID not set"
            )

    log.debug("kimi-cloud: no API key or relay configured, skipping tier")
    return None


# ─── Background Health Probe ─────────────────────────────────────────────────


def _probe_endpoint(
    name: str,
    url: str,
    *,
    timeout: float | None = None,
    mark_failure: bool = True,
) -> bool:
    """Lightweight connectivity check against `GET /api/tags`."""
    try:
        target_url = f"{url}/api/tags"
        if not _is_http_url(target_url):
            raise ValueError("Blocked non-HTTP backend URL")
        if timeout is None:
            if name.startswith("pi-"):
                timeout = PI_PROBE_TIMEOUT_SEC
            elif name == "mac-local":
                timeout = MAC_PROBE_TIMEOUT_SEC
            else:
                timeout = WINDOWS_PROBE_TIMEOUT_SEC
        req = urllib.request.Request(
            target_url,
            method="GET",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec B310
            if resp.status == 200:
                _mark_ok(name)
                return True
    except Exception as e:
        if mark_failure:
            log.warning("x %s probe failed: %s", name, str(e)[:80])
            _mark_failed(name)
        return False
    if mark_failure:
        log.warning("x %s probe returned non-200 status", name)
        _mark_failed(name)
    return False


def _enabled_pi_targets() -> list[tuple[str, str]]:
    """Return enabled Pi endpoints in failover order."""
    targets: list[tuple[str, str]] = []
    if PI_RARI1_ENABLED:
        targets.append(("pi-rari1", PI_RARI1))
    if PI_RARI2_ENABLED:
        targets.append(("pi-rari2", PI_RARI2))
    return targets


def _select_pi_model(model: str) -> str:
    """Choose the Pi-safe model to use for T2 routing."""
    return model if model in PI_SERVE_MODELS else PI_DEFAULT_MODEL


def _select_mac_model(model: str) -> str:
    """Choose the Mac-local model while preserving known equivalent aliases."""
    if model in MAC_MODELS:
        return model
    aliased = MAC_MODEL_ALIASES.get(model)
    if aliased in MAC_MODELS:
        return aliased
    return MAC_FALLBACK_MODEL


def _try_pi_tier(
    model: str,
    messages: list,
    max_tokens: int,
    temperature: float,
    timeout: int = PI_CHAT_TIMEOUT_SEC,
) -> tuple[str | None, dict | None, list[str]]:
    """Try the enabled Pi endpoints in order and return the first success."""
    pi_model = _select_pi_model(model)
    if pi_model != model:
        log.info("Pi fallback: substituting model '%s' → '%s'", model, pi_model)

    tried: list[str] = []
    for endpoint_name, base_url in _enabled_pi_targets():
        if not _is_healthy(endpoint_name):
            continue
        if _should_preflight(endpoint_name):
            if not _probe_endpoint(
                endpoint_name,
                base_url,
                timeout=PI_PROBE_TIMEOUT_SEC,
                mark_failure=True,
            ):
                continue
        tried.append(endpoint_name)
        response = _try_ollama_native(
            endpoint_name,
            base_url,
            pi_model,
            messages,
            max_tokens,
            temperature,
            timeout=timeout,
        )
        if response:
            response["model"] = f"{response['model']} ({endpoint_name})"
            return endpoint_name, response, tried
    return None, None, tried


def _background_health_probe():
    """Runs every 30s. Probes failed endpoints to detect recovery early."""
    probes = [
        ("windows-gpu", WINDOWS_GPU),
        *_enabled_pi_targets(),
        ("mac-local", MAC_LOCAL),
    ]
    while True:
        try:
            for name, url in probes:
                # Probe failed endpoints and any endpoint that has not been
                # verified recently enough to avoid stale "green" health.
                with _health_lock:
                    should_probe = (
                        not _endpoint_health.get(name, True)
                        or time.time() - _last_health_check.get(name, 0.0) > 30
                    )
                if should_probe:
                    _probe_endpoint(name, url, mark_failure=True)
            time.sleep(30)
        except Exception:
            pass  # Never let the probe thread die


# ─── HTTP Handler ─────────────────────────────────────────────────────────────


class ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            self._respond(
                200,
                {
                    "status": "ok",
                    "service": "inference-proxy",
                    "endpoints": _endpoint_status_snapshot(),
                    "tiers": _tier_inventory(),
                    "failover": _failover_status_payload(),
                },
            )
            return

        if self.path == "/failover/status":
            self._respond(200, _failover_status_payload())
            return

        if self.path == "/metrics":
            with _metrics_lock:
                snapshot = {k: dict(v) for k, v in _metrics.items()}
            for _tier, m in snapshot.items():
                n = m["requests"]
                m["avg_ms"] = round(m["total_ms"] / n) if n > 0 else 0
                m["success_rate"] = f"{100 * m['success'] // n}%" if n > 0 else "n/a"
            self._respond(200, {"metrics": snapshot})
            return

        if self.path.startswith("/v1/quota"):
            policy, err = _tenant_context(self.headers)
            if err:
                self._respond(401, err)
                return
            tenant_id = policy["tenant_id"]
            self._respond(
                200,
                {
                    "tenant": tenant_id,
                    "policy": {
                        "requests_per_day": policy["requests_per_day"],
                        "tokens_per_day": policy["tokens_per_day"],
                        "cache_ttl_seconds": policy["cache_ttl_seconds"],
                        "max_tokens_per_request": _MAX_TOKENS_PER_REQUEST,
                    },
                    "usage": _tenant_usage_snapshot(tenant_id, policy=policy),
                },
            )
            return

        if self.path.startswith("/v1/cache-stats"):
            self._respond(200, _cache_stats())
            return

        # Proxy GET to first healthy endpoint (model list, etc.)
        # Note: do NOT call _mark_failed here — a 404 or timeout on /v1/models
        # does not mean the endpoint is down for inference.
        for name, base in [
            ("windows-gpu", WINDOWS_GPU),
            *_enabled_pi_targets(),
            ("mac-local", MAC_LOCAL),
        ]:
            if not _is_healthy(name):
                continue
            try:
                url = f"{base}{self.path}"
                if not _is_http_url(url):
                    continue
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:  # nosec B310
                    data = resp.read()
                    self._respond_raw(resp.status, data)
                    return
            except Exception:
                continue  # Try next endpoint — don't blacklist on GET failures
        self._respond(503, {"error": "All endpoints unavailable"})

    def do_POST(self):
        t_start = time.time()
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 4 * 1024 * 1024:  # 4 MB hard limit
            self._respond(413, {"error": "Request body too large", "code": "body_too_large"})
            return
        body = self.rfile.read(content_length)

        # x402 payment gate — /health and /metrics stay free (those are GETs).
        # Any paid POST path is priced via `_X402.pricing`; absent entries fall
        # through. When X402_ENABLED is off, `gate()` is a no-op.
        if _X402 is not None and self.path in _X402.pricing:
            price = _X402.price_for(self.path) or 0.0
            header = self.headers.get("X-PAYMENT") or self.headers.get("PAYMENT-SIGNATURE")
            resource_url = f"http://{self.headers.get('Host', 'localhost')}{self.path}"
            allowed, body_402, _ = _X402.gate(
                resource_url=resource_url,
                amount_usd=price,
                header_value=header,
            )
            if not allowed:
                self._respond_raw(
                    402,
                    json.dumps(body_402).encode(),
                    headers={"X-Payment-Required": "true"},
                )
                return

        try:
            req_data = json.loads(body)
        except json.JSONDecodeError:
            self._respond(400, {"error": "Invalid JSON"})
            return

        raw_model = req_data.get("model", "auto")
        messages = req_data.get("messages", [])
        max_tokens = req_data.get("max_tokens", 512)
        temperature = req_data.get("temperature", 0.7)
        is_chat = "/v1/chat/completions" in self.path

        try:
            max_tokens = int(max_tokens)
        except (TypeError, ValueError):
            self._respond(
                400, {"error": "max_tokens must be an integer", "code": "invalid_request"}
            )
            return
        if max_tokens < 1:
            self._respond(
                400,
                {
                    "error": "max_tokens must be positive",
                    "code": "invalid_request",
                },
            )
            return
        if max_tokens > _MAX_TOKENS_PER_REQUEST:
            self._respond(
                400,
                {
                    "error": "max_tokens exceeds per-request cap",
                    "code": "max_tokens_exceeded",
                    "max_tokens_per_request": _MAX_TOKENS_PER_REQUEST,
                },
            )
            return

        # Auto-routing: classify task content to pick the best model tier
        if raw_model == "auto" and _CLASSIFIER_AVAILABLE and is_chat and messages:
            clf = _classify_messages(messages)
            model = MODEL_TIERS.get(clf.model, clf.model)
            log.info(
                "auto-route: %s → %s (model=%s, conf=%.2f)",
                clf.category.value,
                clf.model,
                model,
                clf.confidence,
            )
        else:
            model = MODEL_TIERS.get(raw_model, raw_model)

        req_data["model"] = model
        body = json.dumps(req_data).encode()

        needs_gpu = model in GPU_ONLY_MODELS
        wants_kimi = model == "kimi-cloud"

        if is_chat and not messages:
            self._respond(400, {"error": "messages array is empty", "code": "invalid_request"})
            return

        policy, err = _tenant_context(self.headers)
        if err:
            self._respond(401, err)
            return
        tenant_id = policy["tenant_id"]
        prompt_tokens = _estimate_prompt_tokens(messages if isinstance(messages, list) else [])
        quota_error = _reserve_quota(tenant_id, policy, prompt_tokens + max_tokens)
        if quota_error:
            self._respond(
                429,
                quota_error,
                headers=_quota_headers(tenant_id, policy),
            )
            return

        content_is_sensitive = _is_sensitive(messages) if is_chat else False
        cache_allowed = is_chat and not content_is_sensitive
        cache_key = _cache_key(tenant_id, self.path, req_data) if cache_allowed else ""
        if cache_allowed:
            cached = _cache_get(cache_key)
            if cached:
                self._respond(
                    200,
                    cached["response"],
                    tier=str(cached.get("tier", "")),
                    headers=_quota_headers(tenant_id, policy, cache_state="hit"),
                )
                return

        def quota_headers(cache_state: str = "") -> dict[str, str]:
            return _quota_headers(tenant_id, policy, cache_state=cache_state)

        def respond_success(response_body: dict, tier: str) -> bool:
            cache_state = "bypass"
            if cache_allowed:
                _cache_set(
                    cache_key,
                    tenant_id=tenant_id,
                    ttl_seconds=policy["cache_ttl_seconds"],
                    response=response_body,
                    tier=tier,
                )
                cache_state = "miss"
            return self._respond(200, response_body, tier=tier, headers=quota_headers(cache_state))

        tried: list[str] = []  # diagnostic trail

        # ── Kimi Cloud shortcut (explicit request) ──────────────────────────
        if wants_kimi and is_chat:
            # Sensitivity gate runs BEFORE any network call — prevents leaking
            # creds/PnL to a third-party API even if the user asked for Kimi.
            if content_is_sensitive:
                log.warning("! kimi-cloud blocked: sensitive content detected")
                self._respond(
                    400,
                    {
                        "error": "Sensitive content detected — Kimi Cloud routing blocked",
                        "code": "sensitive_routing_blocked",
                    },
                    headers=quota_headers("bypass"),
                )
                return
            tried.append("kimi-cloud")
            resp = _call_kimi_cloud(messages, max_tokens, temperature)
            if resp:
                respond_success(resp, "kimi-cloud")
                return
            log.warning("Kimi Cloud unavailable, falling back to local tiers")
            model = MAC_FALLBACK_MODEL
            req_data["model"] = model
            body = json.dumps(req_data).encode()

        if not is_chat:
            result = _try_mac_local(self.path, body)
            if result:
                self._respond_raw(result[0], result[1], tier="mac-local", headers=quota_headers())
                return
            self._respond(503, {"error": "All endpoints unavailable"}, headers=quota_headers())
            return

        # ── Tier 1: Windows GPU ──────────────────────────────────────────────
        # Native /api/chat (not /v1/chat/completions): Windows Ollama's
        # OpenAI-compat layer returns empty responses — the native endpoint works.
        if _should_preflight("windows-gpu"):
            _probe_endpoint(
                "windows-gpu",
                WINDOWS_GPU,
                timeout=WINDOWS_PROBE_TIMEOUT_SEC,
                mark_failure=True,
            )
        if _is_healthy("windows-gpu"):
            tried.append("windows-gpu")
        resp = _try_ollama_native(
            "windows-gpu",
            WINDOWS_GPU,
            model,
            messages,
            max_tokens,
            temperature,
            timeout=WINDOWS_CHAT_TIMEOUT_SEC,
        )
        if resp:
            respond_success(resp, "windows-gpu")
            return

        if needs_gpu:
            # GPU-only models short-circuit to 503 — Pi/Mac can't fit the weights
            # and Kimi Cloud is a different model family, so falling through would
            # silently change what the caller asked for.
            log.error("GPU-only model %s — all GPU attempts failed", model)
            self._respond(
                503,
                {
                    "error": f"GPU-only model '{model}' unavailable (Windows GPU down)",
                    "code": "gpu_only_unavailable",
                    "tried": tried,
                },
                headers=quota_headers("miss" if cache_allowed else "bypass"),
            )
            return

        # ── Tier 2: Pi ────────────────────────────────────────────────────────
        # If the requested model is installed on Mac and not Pi-serveable, keep
        # the exact model instead of silently downshifting to PI_DEFAULT_MODEL.
        prefer_exact_mac = model in MAC_EXACT_FALLBACK_MODELS
        if PI_ENABLED and not prefer_exact_mac:
            tier, resp, pi_tried = _try_pi_tier(
                model,
                messages,
                max_tokens,
                temperature,
                timeout=PI_CHAT_TIMEOUT_SEC,
            )
            tried.extend(pi_tried)
            if resp and tier:
                respond_success(resp, tier)
                return
        elif PI_ENABLED and prefer_exact_mac:
            log.info("Skipping Pi substitute for exact Mac model '%s'", model)

        # ── Tier 3: Mac local ────────────────────────────────────────────────
        tried.append("mac-local")
        # Model substitution: use hermes3:8b if requested model not on Mac
        mac_model = _select_mac_model(model)
        if mac_model != model:
            mac_body = json.dumps({**req_data, "model": mac_model}).encode()
            log.info("Mac fallback: substituting model '%s' → '%s'", model, mac_model)
        else:
            mac_body = body
        result = _try_mac_local(self.path, mac_body, mac_model)
        if result:
            headers = quota_headers("miss" if cache_allowed else "bypass")
            self._respond_raw(result[0], result[1], tier="mac-local", headers=headers)
            return

        # ── Tier 4: Kimi Cloud (non-sensitive fallback) ──────────────────────
        log.warning("All local tiers down — attempting Kimi Cloud fallback")
        tried.append("kimi-cloud")
        if content_is_sensitive:
            log.warning("! kimi-cloud fallback blocked: sensitive content")
            elapsed_s = round(time.time() - t_start, 1)
            self._respond(
                503,
                {
                    "error": "All local inference unavailable and content is sensitive",
                    "code": "all_tiers_exhausted_sensitive",
                    "tried": tried,
                    "elapsed_s": elapsed_s,
                },
                headers=quota_headers("bypass"),
            )
            return

        resp = _call_kimi_cloud(messages, max_tokens, temperature)
        if resp:
            respond_success(resp, "kimi-cloud")
            return

        elapsed_s = round(time.time() - t_start, 1)
        self._respond(
            503,
            {
                "error": "All inference tiers exhausted",
                "code": "all_tiers_exhausted",
                "tried": tried,
                "elapsed_s": elapsed_s,
                "hint": "Set MOONSHOT_API_KEY for cloud fallback, or check GPU/Pi connectivity",
            },
            headers=quota_headers("miss" if cache_allowed else "bypass"),
        )

    def _respond_raw(
        self,
        code: int,
        body: bytes,
        tier: str = "",
        headers: dict[str, str] | None = None,
    ) -> bool:
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            if tier:
                self.send_header("X-Inference-Tier", tier)
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError) as exc:
            log.warning(
                "client disconnected before %s response could be sent: %s",
                self.path,
                type(exc).__name__,
            )
            if self.command == "POST":
                _record("proxy", False, 0)
            return False
        # Record the aggregate "proxy" outcome only after the upstream reply
        # has been validated and the response has been sent. The prior
        # implementation incremented proxy-success at request-parse time,
        # inflating the metric for every failed/503'd request.
        if self.command == "POST":
            _record("proxy", code < 400, 0)
        return True

    def _respond(
        self,
        code: int,
        body: dict,
        tier: str = "",
        headers: dict[str, str] | None = None,
    ) -> bool:
        return self._respond_raw(code, json.dumps(body).encode(), tier=tier, headers=headers)

    def log_message(self, format, *args):
        pass  # Suppress default per-request logging (we log our own)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle each request in a separate thread — prevents slow requests from blocking health checks."""

    daemon_threads = True


if __name__ == "__main__":
    # Start background health probe
    probe_thread = threading.Thread(target=_background_health_probe, daemon=True)
    probe_thread.start()

    server = ThreadedHTTPServer(("0.0.0.0", PORT), ProxyHandler)  # nosec B104
    log.info("Sapphire Inference Proxy :%d — 4-tier failover (threaded)", PORT)
    log.info("T1 Windows GPU : %s (native /api/chat)", WINDOWS_GPU)
    log.info("T2 Pi rari1    : %s enabled=%s", PI_RARI1, PI_RARI1_ENABLED)
    log.info("T2 Pi rari2    : %s enabled=%s", PI_RARI2, PI_RARI2_ENABLED)
    log.info("T3 Mac local   : %s (/v1/ openai-compat)", MAC_LOCAL)
    log.info(
        "T4 Kimi Cloud  : moonshot=%s openrouter=%s relay_available=%s relay_enabled=%s (non-sensitive only)",
        bool(MOONSHOT_API_KEY),
        bool(OPENROUTER_API_KEY),
        _KIMI_RELAY_AVAILABLE,
        KIMI_RELAY_ENABLED,
    )
    log.info("Health cooldown: %ds | Background probe: 30s", HEALTH_COOLDOWN)
    server.serve_forever()
