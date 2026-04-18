"""Sapphire Inference Proxy — 4-tier multi-node failover.

Tier 1: Windows GPU (100.71.10.48:11434) — RTX 5070 Ti, hermes3/qwen/deepseek/gemma4
Tier 2: Pi (rari1/rari2 via Tailscale) — Ollama, nemotron-mini / gemma2
Tier 3: Mac local (127.0.0.1:11434) — always-on fallback
Tier 4: Kimi Cloud (api.moonshot.cn) — non-sensitive deep research only

Routing rules:
  - GPU-only models (>8B): Windows only, 503 if down (no cloud fallback)
  - Sensitive queries: never reach Kimi Cloud (blocked at classifier)
  - Pi: lightweight models only (≤4B), not offered GPU-only jobs
  - All tiers use OpenAI-compatible output regardless of backend format

Benchmark-informed routing (RTX 5070 Ti, 2026-04-14):
  fast/quick  → nemotron-mini:4b     232 tok/s  2.7 GB  T0 classifier + quick facts
  balanced    → hermes3:8b           118 tok/s  4.7 GB  general chat, tool calls
  code        → gemma4:latest        154 tok/s  9.0 GB  code gen (best GPU model, via Ollama)
  reason      → deepseek-r1:14b       80 tok/s  9.0 GB  structured R1 chain-of-thought
  qwen-reason → qwen3.5:9b           107 tok/s  6.6 GB  fast reasoning (via Ollama)
  deep        → qwen3:14b             81 tok/s  9.3 GB  deep analysis, multi-step
  large       → qwen2.5:32b          2.7 tok/s 19.9 GB  background / batch (RAM spill)
  cascade     → nemotron-cascade-2    16 tok/s 22.6 GB  MoE deep analysis (fits in VRAM)

Endpoints:
  /v1/chat/completions  — OpenAI-compatible (what hermes-agent uses)
  /v1/models            — List models
  /health               — Full tier health report
  /metrics              — Per-tier request/success/failure counters
"""

import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
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
    _X402 = X402Middleware(pricing={
        "/v1/chat/completions": float(os.getenv("X402_PRICE_CHAT", "0.001")),
        "/v1/completions":      float(os.getenv("X402_PRICE_COMPLETIONS", "0.001")),
        "/v1/embeddings":       float(os.getenv("X402_PRICE_EMBED", "0.0005")),
    })
    _X402_AVAILABLE = True
    log.info("x402 payment gate: enabled=%s recipient=%s network=%s",
             _X402.enabled, _X402.recipient[:10] + "..." if _X402.recipient else "-",
             _X402.network)
except Exception as e:
    log.warning("x402 middleware unavailable: %s", e)
    _X402 = None
    _X402_AVAILABLE = False

# ─── Endpoints (overridable via env vars for network changes) ────────────────
WINDOWS_GPU   = os.getenv("WINDOWS_GPU_URL",  "http://100.71.10.48:11434")
PI_RARI1      = os.getenv("PI_RARI1_URL",     "http://100.120.191.1:11434")
PI_RARI2      = os.getenv("PI_RARI2_URL",     "http://100.87.225.89:11434")
MAC_LOCAL     = os.getenv("MAC_LOCAL_URL",    "http://127.0.0.1:11434")

# Kimi Cloud — permanent API keys only (no expiring CLI tokens)
# T4 primary:  Moonshot HTTP API (MOONSHOT_API_KEY → api.moonshot.cn)
# T4 fallback: @rarikimibot Telegram relay (KIMI_CLAW_BOT_TOKEN, needs shared group relay)
#              Bot token stored in ~/.hermes/.env — see docs/tradingview-cdp-setup.md and
#              ~/.hermes/skills/sapphire/kimi-delegate/SKILL.md for relay architecture
MOONSHOT_API_KEY   = os.getenv("MOONSHOT_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MOONSHOT_BASE      = "https://api.moonshot.cn/v1"
OPENROUTER_BASE    = "https://openrouter.ai/api/v1"

PORT = 11435

# ─── Model Routing ──────────────────────────────────────────────────────────
MODEL_TIERS = {
    # General
    "auto":      "hermes3:8b",
    "balanced":  "hermes3:8b",

    # Pi-eligible (light, ≤4B)
    "fast":      "nemotron-mini:latest",
    "quick":     "nemotron-mini:latest",
    "tiny":      "qwen2.5:0.5b",        # ultra-light, Pi-native

    # GPU-heavy — benchmark-calibrated 2026-04-14 (RTX 5070 Ti)
    "deep":           "qwen3:14b",              # 81 tok/s, 9.3 GB — deep multi-step
    "code":           "gemma4:latest",          # 154 tok/s, 9.0 GB — best code model (via Ollama)
    "fast-code":      "gemma4:latest",          # alias
    "reason":         "deepseek-r1:14b",        # 80 tok/s, 9.0 GB — structured R1 reasoning
    "qwen-reason":    "qwen3.5:9b",             # 107 tok/s, 6.6 GB — fast reasoning (via Ollama)
    "fast-reason":    "qwen3.5:9b",             # alias
    "large":          "qwen2.5:32b",            # 2.7 tok/s, 19.9 GB — background/batch (RAM spill)
    "cascade":        "nemotron-cascade-2",     # 16 tok/s, 22.6 GB — MoE, fits 16 GB VRAM
    "moe":            "nemotron-cascade-2",     # alias

    # Legacy aliases (kept for compatibility)
    "qwen2.5-coder":  "qwen2.5-coder:14b",     # 72 tok/s — superseded by gemma4 for code
    "phi4":           "phi4:latest",            # 83 tok/s, 9.1 GB — good general + code

    # Kimi Cloud routes (non-sensitive only)
    "kimi":       "kimi-cloud",
    "kimi-fast":  "kimi-cloud",
    "kimi-large": "kimi-cloud",
    "kimi-cloud": "kimi-cloud",
    "kimi-code":  "kimi-cloud",
    "cloud":      "kimi-cloud",
    "research":   "kimi-cloud",
}

# Models that require Windows GPU (too large for Pi/Mac).
# gemma3:27b removed — consistently times out on llama-server b8795 (OOM at 17.4 GB).
# gemma4:latest and qwen3.5:9b are GPU-routed but NOT blocking (they use Ollama backend).
GPU_ONLY_MODELS = {
    # Benchmarked 14B class — confirmed GPU-only (9–10 GB, fit in 16 GB VRAM)
    "qwen3:14b", "qwen2.5-coder:14b", "deepseek-r1:14b", "phi4:latest",
    # Large class — RAM spill but still routed to Windows only
    "deepseek-r1:32b", "qwen2.5:32b", "qwen2.5:14b",
    # Via Ollama (no llama-server compat), GPU Windows only
    "gemma4:latest", "qwen3.5:9b",
    # Oversized / exotic
    "llama3.3:70b", "qwq:latest",
    # MoE — 22.6 GB, fits in 16 GB VRAM via sparse activation
    "nemotron-cascade-2",
}

# Models that can run on Pi (3.8GB RAM ceiling — nemotron-mini:4b is max)
PI_MODELS = {
    "nemotron-mini:4b", "nemotron-mini", "nemotron-mini:latest",
    "gemma2:2b", "qwen2.5:0.5b", "smollm2:1.7b",
}
PI_DEFAULT_MODEL  = "qwen2.5:0.5b"  # fastest Pi model (~20s cold load); nemotron-mini times out
MAC_FALLBACK_MODEL = "hermes3:8b"       # model known to be on Mac Ollama

# Mac models (models confirmed available locally)
MAC_MODELS = {"hermes3:8b", "llama3.2:3b", "nemotron-mini:latest", "llama3.2:latest"}

# Enable Pi tiers independently — rari2 is offline so set PI_RARI2_ENABLED=0 to skip the 30s timeout
PI_RARI1_ENABLED = os.getenv("PI_RARI1_ENABLED", os.getenv("PI_OLLAMA_ENABLED", "0")) == "1"
PI_RARI2_ENABLED = os.getenv("PI_RARI2_ENABLED", "0") == "1"
PI_ENABLED = PI_RARI1_ENABLED or PI_RARI2_ENABLED  # any Pi active

# ─── Health Tracking ─────────────────────────────────────────────────────────
ENDPOINTS = ["windows-gpu", "pi-rari1", "pi-rari2", "mac-local", "kimi-cloud"]
_endpoint_health     = {k: True  for k in ENDPOINTS}
_last_health_check   = {k: 0.0  for k in ENDPOINTS}
_health_lock         = threading.Lock()
HEALTH_COOLDOWN      = 120  # seconds before retrying a failed endpoint


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
        if was_failed:
            log.info("Endpoint %s recovered", name)


# ─── Metrics ─────────────────────────────────────────────────────────────────
_metrics = {
    name: {"requests": 0, "success": 0, "failure": 0, "total_ms": 0}
    for name in ENDPOINTS + ["proxy"]
}
_metrics_lock = threading.Lock()


_MAX_METRIC_KEYS = 32  # Guard against unbounded growth from unknown tier names

def _record(tier: str, success: bool, elapsed_ms: int):
    with _metrics_lock:
        if tier not in _metrics and len(_metrics) >= _MAX_METRIC_KEYS:
            log.warning("_record: metrics dict full (%d keys), dropping tier '%s'",
                        _MAX_METRIC_KEYS, tier)
            return
        m = _metrics.setdefault(tier, {"requests": 0, "success": 0, "failure": 0, "total_ms": 0})
        m["requests"] += 1
        if success:
            m["success"] += 1
        else:
            m["failure"] += 1
        m["total_ms"] += elapsed_ms


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
                if isinstance(block, dict) and _SENSITIVE_PATTERNS.search(
                    block.get("text", "")
                ):
                    return True
    return False


# ─── Ollama Native Caller ────────────────────────────────────────────────────

def _call_native_ollama(base_url: str, model: str, messages: list,
                        max_tokens: int = 512, temperature: float = 0.7,
                        timeout: int = 15) -> dict:
    """Call Ollama native /api/chat and return the raw response dict."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "keep_alive": -1,  # keep model loaded in VRAM between requests
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }).encode()
    req = urllib.request.Request(
        f"{base_url}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
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
        "choices": [{
            "index": 0,
            "message": {
                "role": msg.get("role", "assistant"),
                "content": content,
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": native_resp.get("prompt_eval_count", 0),
            "completion_tokens": native_resp.get("eval_count", 0),
            "total_tokens": native_resp.get("prompt_eval_count", 0)
                           + native_resp.get("eval_count", 0),
        },
    }


def _try_ollama_native(endpoint_name: str, base_url: str, model: str,
                       messages: list, max_tokens: int, temperature: float,
                       timeout: int = 60) -> dict | None:
    """Try a native Ollama endpoint. Returns OpenAI-format dict or None.

    Only marks an endpoint failed for connection-level errors (refused, no route).
    HTTP 404 (model not found) and timeouts (cold model load) do NOT blacklist.
    """
    if not _is_healthy(endpoint_name):
        return None
    t0 = time.time()
    try:
        native = _call_native_ollama(base_url, model, messages, max_tokens,
                                     temperature, timeout)
        msg = native.get("message", {})
        content = msg.get("content", "") or msg.get("thinking", "")
        if not content:
            log.warning("x %s returned empty content for model '%s'", endpoint_name, model)
            return None
        elapsed = int((time.time() - t0) * 1000)
        _mark_ok(endpoint_name)
        _record(endpoint_name, True, elapsed)
        log.info("-> inference via %s (native ollama, model=%s, %dms)",
                 endpoint_name, model, elapsed)
        return _native_to_openai(native, model)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log.warning("x %s: model '%s' not found (404) — endpoint healthy", endpoint_name, model)
        else:
            log.warning("x %s native HTTP %d: %s", endpoint_name, e.code, str(e)[:60])
            _mark_failed(endpoint_name)
            _record(endpoint_name, False, int((time.time() - t0) * 1000))
        return None
    except (TimeoutError, OSError) as e:
        err_str = str(e)
        elapsed = int((time.time() - t0) * 1000)
        # Word-boundary "time" check — the prior `"time" in last.lower()` also
        # matched "timestamp", "timeseries", etc., misclassifying unrelated
        # errors as timeouts. Use explicit substrings instead.
        err_lower = err_str.lower()
        if ("timed out" in err_lower or "timeout" in err_lower
                or isinstance(e, TimeoutError)):
            # Timeout means the host is unreachable or hung — engage circuit breaker.
            # (Cold model loads in Ollama respond normally; a socket timeout = host down.)
            log.warning("x %s timed out after %dms — marking failed", endpoint_name, elapsed)
            _mark_failed(endpoint_name)
            _record(endpoint_name, False, elapsed)
        elif "Connection refused" in err_str or "No route" in err_str:
            log.warning("x %s unreachable (%s): %s", endpoint_name, base_url, err_str[:60])
            _mark_failed(endpoint_name)
            _record(endpoint_name, False, elapsed)
        else:
            log.warning("x %s OS error: %s", endpoint_name, err_str[:80])
            _mark_failed(endpoint_name)
            _record(endpoint_name, False, elapsed)
        return None
    except Exception as e:
        err_str = str(e)
        elapsed = int((time.time() - t0) * 1000)
        if "timed out" in err_str:
            log.warning("x %s timed out — marking failed", endpoint_name)
            _mark_failed(endpoint_name)
            _record(endpoint_name, False, elapsed)
        else:
            log.warning("x %s failed: %s", endpoint_name, err_str[:80])
            _mark_failed(endpoint_name)
            _record(endpoint_name, False, elapsed)
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
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
            elapsed = int((time.time() - t0) * 1000)
            _mark_ok("mac-local")
            _record("mac-local", True, elapsed)
            log.info("-> inference via mac-local (openai-compat, model=%s, %dms)",
                     model or "?", elapsed)
            return resp.status, data
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log.warning("x mac-local: model '%s' not found (404) — endpoint healthy", model)
        else:
            log.warning("x mac-local HTTP %d: %s", e.code, str(e)[:60])
            _mark_failed("mac-local")
            _record("mac-local", False, int((time.time() - t0) * 1000))
        return None
    except BrokenPipeError:
        log.warning("x mac-local: client disconnected (BrokenPipe) — endpoint healthy")
        return None
    except Exception as e:
        log.warning("x mac-local failed: %s", str(e)[:80])
        _mark_failed("mac-local")
        _record("mac-local", False, int((time.time() - t0) * 1000))
        return None


# ─── Kimi Cloud ──────────────────────────────────────────────────────────────

# Allowlist of hostnames the proxy is permitted to make outbound HTTPS calls to.
# Any base URL not matching this set is rejected before the request is sent.
_ALLOWED_CLOUD_HOSTS: frozenset[str] = frozenset({
    "api.moonshot.cn",
    "openrouter.ai",
    "api.openai.com",
    "api.telegram.org",
})


def _is_allowed_outbound(url: str) -> bool:
    """Return True if *url*'s hostname is on the cloud allowlist."""
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    return host in _ALLOWED_CLOUD_HOSTS


def _call_openai_compat(base: str, model: str, api_key: str, messages: list,
                         max_tokens: int, temperature: float, label: str) -> dict | None:
    """Generic OpenAI-compatible cloud call. Returns OpenAI-format dict or None."""
    target_url = f"{base}/chat/completions"
    if not _is_allowed_outbound(target_url):
        log.warning("_call_openai_compat: blocked outbound to %s — not in allowlist", base)
        return None
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }).encode()
    t0 = time.time()
    try:
        req = urllib.request.Request(
            f"{base}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            elapsed = int((time.time() - t0) * 1000)
            _mark_ok("kimi-cloud")
            _record("kimi-cloud", True, elapsed)
            log.info("-> inference via %s (%dms)", label, elapsed)
            data["model"] = label
            return data
    except Exception as e:
        _mark_failed("kimi-cloud")
        _record("kimi-cloud", False, int((time.time() - t0) * 1000))
        log.warning("x %s failed: %s", label, str(e)[:80])
        return None


def _call_kimi_cloud(messages: list, max_tokens: int = 2048,
                     temperature: float = 0.7) -> dict | None:
    """Call cloud research API. Priority: Moonshot API → OpenRouter → Telegram relay."""
    if not _is_healthy("kimi-cloud"):
        return None

    if MOONSHOT_API_KEY:
        result = _call_openai_compat(
            base=MOONSHOT_BASE, model="moonshot-v1-8k", api_key=MOONSHOT_API_KEY,
            messages=messages, max_tokens=max_tokens, temperature=temperature,
            label="moonshot-api",
        )
        if result:
            return result

    if OPENROUTER_API_KEY:
        result = _call_openai_compat(
            base=OPENROUTER_BASE, model="moonshot/moonshot-v1-8k",
            api_key=OPENROUTER_API_KEY,
            messages=messages, max_tokens=max_tokens, temperature=temperature,
            label="openrouter",
        )
        if result:
            return result

    # Telegram relay fallback — @rarikimibot in shared group
    if _KIMI_RELAY_AVAILABLE and _kimi_relay_fn:
        relay_chat_id = os.environ.get("KIMI_RELAY_CHAT_ID", "")
        kimi_token    = os.environ.get("KIMI_CLAW_BOT_TOKEN", "")
        if relay_chat_id and kimi_token:
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
                    elapsed = int((time.time() - t0) * 1000)
                    _mark_ok("kimi-cloud")
                    _record("kimi-cloud", True, elapsed)
                    log.info("-> inference via kimi-relay (telegram, %dms)", elapsed)
                    return {
                        "id": f"chatcmpl-relay-{int(time.time())}",
                        "object": "chat.completion",
                        "created": int(time.time()),
                        "model": "kimi-relay",
                        "choices": [{
                            "index": 0,
                            "message": {"role": "assistant", "content": text},
                            "finish_reason": "stop",
                        }],
                        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                    }
                except Exception as e:
                    elapsed = int((time.time() - t0) * 1000)
                    _mark_failed("kimi-cloud")
                    _record("kimi-cloud", False, elapsed)
                    log.warning("x kimi-relay failed: %s", str(e)[:80])
        else:
            log.debug("kimi-relay: KIMI_RELAY_CHAT_ID or KIMI_CLAW_BOT_TOKEN not set")

    log.debug("kimi-cloud: no API key or relay configured, skipping tier")
    return None


# ─── Background Health Probe ─────────────────────────────────────────────────

def _probe_endpoint(name: str, url: str):
    """Lightweight connectivity check — HEAD /api/tags or /v1/models."""
    try:
        req = urllib.request.Request(f"{url}/api/tags", method="GET",
                                     headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            if resp.status == 200:
                _mark_ok(name)
    except Exception:
        pass  # Probe failures don't change health state — only real requests do


def _background_health_probe():
    """Runs every 30s. Probes failed endpoints to detect recovery early."""
    probes = [
        ("windows-gpu", WINDOWS_GPU),
        ("pi-rari1",    PI_RARI1),
        ("pi-rari2",    PI_RARI2),
        ("mac-local",   MAC_LOCAL),
    ]
    while True:
        try:
            time.sleep(30)
            for name, url in probes:
                # Only probe endpoints that are marked failed (recovery detection)
                with _health_lock:
                    is_failed = not _endpoint_health.get(name, True)
                if is_failed:
                    _probe_endpoint(name, url)
        except Exception:
            pass  # Never let the probe thread die


# ─── HTTP Handler ─────────────────────────────────────────────────────────────

class ProxyHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {
                "status": "ok",
                "service": "inference-proxy",
                "endpoints": {
                    name: ("healthy" if _is_healthy(name) else "failed")
                    for name in ENDPOINTS
                },
                "tiers": {
                    "t1_windows_gpu": WINDOWS_GPU,
                    "t2_pi_rari1": f"{PI_RARI1} (enabled={PI_RARI1_ENABLED})",
                    "t2_pi_rari2": f"{PI_RARI2} (enabled={PI_RARI2_ENABLED})",
                    "t3_mac_local": MAC_LOCAL,
                    "t4_kimi_cloud": MOONSHOT_BASE,
                },
            })
            return

        if self.path == "/metrics":
            with _metrics_lock:
                snapshot = {k: dict(v) for k, v in _metrics.items()}
            for tier, m in snapshot.items():
                n = m["requests"]
                m["avg_ms"] = round(m["total_ms"] / n) if n > 0 else 0
                m["success_rate"] = f"{100*m['success']//n}%" if n > 0 else "n/a"
            self._respond(200, {"metrics": snapshot})
            return

        # Proxy GET to first healthy endpoint (model list, etc.)
        # Note: do NOT call _mark_failed here — a 404 or timeout on /v1/models
        # does not mean the endpoint is down for inference.
        for name, base in [("windows-gpu", WINDOWS_GPU), ("pi-rari1", PI_RARI1),
                            ("pi-rari2", PI_RARI2), ("mac-local", MAC_LOCAL)]:
            if not _is_healthy(name):
                continue
            try:
                url = f"{base}{self.path}"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = resp.read()
                    self.send_response(resp.status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(data)
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
                self.send_response(402)
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Payment-Required", "true")
                self.end_headers()
                self.wfile.write(json.dumps(body_402).encode())
                return

        try:
            req_data = json.loads(body)
        except json.JSONDecodeError:
            self._respond(400, {"error": "Invalid JSON"})
            return

        raw_model   = req_data.get("model", "auto")
        messages    = req_data.get("messages", [])
        max_tokens  = req_data.get("max_tokens", 512)
        temperature = req_data.get("temperature", 0.7)
        is_chat     = "/v1/chat/completions" in self.path

        # Auto-routing: classify task content to pick the best model tier
        if raw_model == "auto" and _CLASSIFIER_AVAILABLE and is_chat and messages:
            clf = _classify_messages(messages)
            model = MODEL_TIERS.get(clf.model, clf.model)
            log.info(
                "auto-route: %s → %s (model=%s, conf=%.2f)",
                clf.category.value, clf.model, model, clf.confidence,
            )
        else:
            model = MODEL_TIERS.get(raw_model, raw_model)

        req_data["model"] = model
        body = json.dumps(req_data).encode()

        needs_gpu   = model in GPU_ONLY_MODELS
        wants_kimi  = model == "kimi-cloud"

        if is_chat and not messages:
            self._respond(400, {"error": "messages array is empty", "code": "invalid_request"})
            return

        tried: list[str] = []  # diagnostic trail

        # ── Kimi Cloud shortcut (explicit request) ──────────────────────────
        if wants_kimi and is_chat:
            # Sensitivity gate runs BEFORE any network call — prevents leaking
            # creds/PnL to a third-party API even if the user asked for Kimi.
            if _is_sensitive(messages):
                log.warning("! kimi-cloud blocked: sensitive content detected")
                self._respond(400, {
                    "error": "Sensitive content detected — Kimi Cloud routing blocked",
                    "code": "sensitive_routing_blocked",
                })
                return
            tried.append("kimi-cloud")
            resp = _call_kimi_cloud(messages, max_tokens, temperature)
            if resp:
                self._respond(200, resp, tier="kimi-cloud")
                return
            log.warning("Kimi Cloud unavailable, falling back to local tiers")
            model = "hermes3:8b"
            req_data["model"] = model
            body = json.dumps(req_data).encode()

        if not is_chat:
            result = _try_mac_local(self.path, body)
            if result:
                self.send_response(result[0])
                self.send_header("Content-Type", "application/json")
                self.send_header("X-Inference-Tier", "mac-local")
                self.end_headers()
                self.wfile.write(result[1])
                _record("proxy", result[0] < 400, 0)
                return
            self._respond(503, {"error": "All endpoints unavailable"})
            return

        # ── Tier 1: Windows GPU ──────────────────────────────────────────────
        # Native /api/chat (not /v1/chat/completions): Windows Ollama's
        # OpenAI-compat layer returns empty responses — the native endpoint works.
        if _is_healthy("windows-gpu"):
            tried.append("windows-gpu")
        resp = _try_ollama_native("windows-gpu", WINDOWS_GPU, model,
                                  messages, max_tokens, temperature, timeout=90)
        if resp:
            self._respond(200, resp, tier="windows-gpu")
            return

        if needs_gpu:
            # GPU-only models short-circuit to 503 — Pi/Mac can't fit the weights
            # and Kimi Cloud is a different model family, so falling through would
            # silently change what the caller asked for.
            log.error("GPU-only model %s — all GPU attempts failed", model)
            self._respond(503, {
                "error": f"GPU-only model '{model}' unavailable (Windows GPU down)",
                "code": "gpu_only_unavailable",
                "tried": tried,
            })
            return

        # ── Tier 2: Pi ────────────────────────────────────────────────────────
        if PI_ENABLED:
            # Graceful model substitution: use Pi-compatible model
            pi_model = model if model in PI_MODELS else PI_DEFAULT_MODEL
            if pi_model != model:
                log.info("Pi fallback: substituting model '%s' → '%s'", model, pi_model)

            if PI_RARI1_ENABLED and _is_healthy("pi-rari1"):
                tried.append("pi-rari1")
                resp = _try_ollama_native("pi-rari1", PI_RARI1, pi_model,
                                          messages, max_tokens, temperature, timeout=30)
                if resp:
                    resp["model"] = f"{resp['model']} (pi-rari1)"
                    self._respond(200, resp, tier="pi-rari1")
                    return

            if PI_RARI2_ENABLED and _is_healthy("pi-rari2"):
                tried.append("pi-rari2")
                resp = _try_ollama_native("pi-rari2", PI_RARI2, pi_model,
                                          messages, max_tokens, temperature, timeout=30)
                if resp:
                    resp["model"] = f"{resp['model']} (pi-rari2)"
                    self._respond(200, resp, tier="pi-rari2")
                    return

        # ── Tier 3: Mac local ────────────────────────────────────────────────
        tried.append("mac-local")
        # Model substitution: use hermes3:8b if requested model not on Mac
        mac_model = model if model in MAC_MODELS else MAC_FALLBACK_MODEL
        if mac_model != model:
            mac_body = json.dumps({**req_data, "model": mac_model}).encode()
            log.info("Mac fallback: substituting model '%s' → '%s'", model, mac_model)
        else:
            mac_body = body
        result = _try_mac_local(self.path, mac_body, mac_model)
        if result:
            self.send_response(result[0])
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Inference-Tier", "mac-local")
            self.end_headers()
            self.wfile.write(result[1])
            _record("proxy", result[0] < 400, 0)
            return

        # ── Tier 4: Kimi Cloud (non-sensitive fallback) ──────────────────────
        log.warning("All local tiers down — attempting Kimi Cloud fallback")
        tried.append("kimi-cloud")
        if _is_sensitive(messages):
            log.warning("! kimi-cloud fallback blocked: sensitive content")
            elapsed_s = round(time.time() - t_start, 1)
            self._respond(503, {
                "error": "All local inference unavailable and content is sensitive",
                "code": "all_tiers_exhausted_sensitive",
                "tried": tried,
                "elapsed_s": elapsed_s,
            })
            return

        resp = _call_kimi_cloud(messages, max_tokens, temperature)
        if resp:
            self._respond(200, resp, tier="kimi-cloud")
            return

        elapsed_s = round(time.time() - t_start, 1)
        self._respond(503, {
            "error": "All inference tiers exhausted",
            "code": "all_tiers_exhausted",
            "tried": tried,
            "elapsed_s": elapsed_s,
            "hint": "Set MOONSHOT_API_KEY for cloud fallback, or check GPU/Pi connectivity",
        })

    def _respond(self, code: int, body: dict, tier: str = ""):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        if tier:
            self.send_header("X-Inference-Tier", tier)
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())
        # Record the aggregate "proxy" outcome only after the upstream reply
        # has been validated and the response has been sent. The prior
        # implementation incremented proxy-success at request-parse time,
        # inflating the metric for every failed/503'd request.
        if self.command == "POST":
            _record("proxy", code < 400, 0)

    def log_message(self, format, *args):
        pass  # Suppress default per-request logging (we log our own)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Handle each request in a separate thread — prevents slow requests from blocking health checks."""
    daemon_threads = True


if __name__ == "__main__":
    # Start background health probe
    probe_thread = threading.Thread(target=_background_health_probe, daemon=True)
    probe_thread.start()

    server = ThreadedHTTPServer(("127.0.0.1", PORT), ProxyHandler)
    log.info("Sapphire Inference Proxy :%d — 4-tier failover (threaded)", PORT)
    log.info("T1 Windows GPU : %s (native /api/chat)", WINDOWS_GPU)
    log.info("T2 Pi rari1    : %s enabled=%s", PI_RARI1, PI_RARI1_ENABLED)
    log.info("T2 Pi rari2    : %s enabled=%s", PI_RARI2, PI_RARI2_ENABLED)
    log.info("T3 Mac local   : %s (/v1/ openai-compat)", MAC_LOCAL)
    log.info("T4 Kimi Cloud  : moonshot=%s openrouter=%s relay=%s (non-sensitive only)",
             bool(MOONSHOT_API_KEY), bool(OPENROUTER_API_KEY), _KIMI_RELAY_AVAILABLE)
    log.info("Health cooldown: %ds | Background probe: 30s", HEALTH_COOLDOWN)
    server.serve_forever()
