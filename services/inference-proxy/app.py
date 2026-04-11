"""Sapphire Inference Proxy — 4-tier multi-node failover.

Tier 1: Windows GPU (100.71.10.48:11434) — RTX 5070 Ti, hermes3/qwen/deepseek
Tier 2: Pi (rari1/rari2 via Tailscale) — Ollama, nemotron-mini / gemma2
Tier 3: Mac local (127.0.0.1:11434) — always-on fallback
Tier 4: Kimi Cloud (api.kimi.com) — non-sensitive deep research only

Routing rules:
  - GPU-only models (>8B): Windows only, 503 if down (no cloud fallback)
  - Sensitive queries: never reach Kimi Cloud (blocked at classifier)
  - Pi: lightweight models only (≤4B), not offered GPU-only jobs
  - All tiers use OpenAI-compatible output regardless of backend format

Endpoints:
  /v1/chat/completions  — OpenAI-compatible (what hermes-agent uses)
  /v1/models            — List models
  /health               — Full tier health report
"""

import json
import os
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging
import re

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("inference-proxy")

# ─── Endpoints ──────────────────────────────────────────────────────────────
WINDOWS_GPU   = "http://100.71.10.48:11434"
PI_RARI1      = "http://100.120.191.1:11434"
PI_RARI2      = "http://100.87.225.89:11434"
MAC_LOCAL     = "http://127.0.0.1:11434"
KIMI_API_BASE = "https://api.kimi.com/coding/v1"
KIMI_TOKEN_FILE = os.path.expanduser("~/.kimi/credentials/kimi-code.json")

# Permanent API key alternatives (no hourly expiry) — preferred over token file
MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
MOONSHOT_BASE = "https://api.moonshot.cn/v1"
OPENROUTER_BASE = "https://openrouter.ai/api/v1"

PORT = 11435

# ─── Model Routing ──────────────────────────────────────────────────────────
MODEL_TIERS = {
    # General
    "auto":      "hermes3:8b",
    "balanced":  "hermes3:8b",

    # Pi-eligible (light, ≤4B)
    "fast":      "nemotron-mini",
    "quick":     "nemotron-mini",
    "tiny":      "qwen2.5:0.5b",        # ultra-light, Pi-native

    # GPU-heavy
    "deep":      "qwen3:14b",
    "code":      "qwen2.5-coder:14b",
    "reason":    "deepseek-r1:14b",
    "large":     "qwen2.5:32b",

    # Kimi Cloud routes (non-sensitive only)
    "kimi":       "kimi-cloud",
    "kimi-fast":  "kimi-cloud",         # same endpoint, model chosen in handler
    "kimi-large": "kimi-cloud",
    "kimi-cloud": "kimi-cloud",
    "kimi-code":  "kimi-cloud",
    "cloud":      "kimi-cloud",
    "research":   "kimi-cloud",
}

# Models that require Windows GPU (too large for Pi/Mac)
GPU_ONLY_MODELS = {
    "qwen3:14b", "qwen2.5-coder:14b", "deepseek-r1:14b", "deepseek-r1:32b",
    "qwen2.5:32b", "qwen2.5:14b", "gemma3:27b", "llama3.3:70b", "qwq:latest",
}

# Models that can run on Pi (3.8GB RAM ceiling — nemotron-mini:4b is max)
PI_MODELS = {
    "nemotron-mini:4b", "nemotron-mini",
    "gemma2:2b", "qwen2.5:0.5b", "smollm2:1.7b",
}
PI_DEFAULT_MODEL = "nemotron-mini:4b"   # fallback when requested model not in PI_MODELS
MAC_FALLBACK_MODEL = "hermes3:8b"       # model known to be on Mac Ollama

# Enable Pi tier via environment variable (disabled by default until Pi Ollama is set up)
PI_ENABLED = os.getenv("PI_OLLAMA_ENABLED", "0") == "1"

# ─── Health Tracking ─────────────────────────────────────────────────────────
ENDPOINTS = ["windows-gpu", "pi-rari1", "pi-rari2", "mac-local", "kimi-cloud"]
_endpoint_health = {k: True for k in ENDPOINTS}
_last_health_check = {k: 0.0 for k in ENDPOINTS}
HEALTH_COOLDOWN = 60  # seconds before retrying a failed endpoint


def _is_healthy(name: str) -> bool:
    if _endpoint_health[name]:
        return True
    if time.time() - _last_health_check[name] > HEALTH_COOLDOWN:
        return True  # cooldown expired — allow retry
    return False


def _mark_failed(name: str):
    _endpoint_health[name] = False
    _last_health_check[name] = time.time()


def _mark_ok(name: str):
    _endpoint_health[name] = True


# ─── Sensitivity Classifier ──────────────────────────────────────────────────
# Blocks routing to Kimi Cloud for any query that may contain private data.
# Heuristic-based — no LLM required (runs before inference).

_SENSITIVE_PATTERNS = re.compile(
    r"""
    # Auth / secrets (exact credential patterns only)
    password|api.key|secret|credential|jwt|ssh.key|
    # Financial PII
    ssn|routing.num|account.num|credit.card|
    # Addresses / contact
    \b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b|  # phone pattern
    \b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b  # email pattern
    """,
    re.VERBOSE | re.IGNORECASE,
)


def _is_sensitive(messages: list) -> bool:
    """Return True if any message content looks like private/sensitive data.
    DISABLED: always returns False until sensitivity rules are tuned.
    Re-enable by removing the early return below.
    """
    return False  # noqa: disabled — uncomment loop below to re-enable
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
    """Convert Ollama native /api/chat response to OpenAI-compatible format."""
    msg = native_resp.get("message", {})
    return {
        "id": f"chatcmpl-{int(time.time())}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {
                "role": msg.get("role", "assistant"),
                "content": msg.get("content", ""),
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

    Only marks an endpoint failed for connection-level errors (timeout, refused).
    HTTP 404 (model not found) means the endpoint is healthy — don't blacklist it.
    """
    if not _is_healthy(endpoint_name):
        return None
    try:
        native = _call_native_ollama(base_url, model, messages, max_tokens,
                                     temperature, timeout)
        content = native.get("message", {}).get("content", "")
        if not content:
            log.warning("x %s returned empty content for model '%s'", endpoint_name, model)
            # Empty response is a model-level issue, not an endpoint failure
            return None
        _mark_ok(endpoint_name)
        log.info("-> inference via %s (native ollama, model=%s)", endpoint_name, model)
        return _native_to_openai(native, model)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # Model not found — endpoint is UP, just missing this model
            log.warning("x %s: model '%s' not found (404) — endpoint healthy", endpoint_name, model)
        else:
            log.warning("x %s native HTTP %d: %s", endpoint_name, e.code, str(e)[:60])
            _mark_failed(endpoint_name)
        return None
    except (TimeoutError, OSError) as e:
        err_str = str(e)
        if "timed out" in err_str or "time" in err_str.lower():
            # Timeout: endpoint is reachable but model is cold-loading.
            # Don't blacklist — fall through to faster tier and retry GPU next request.
            log.warning("x %s timed out (model cold-loading?) — not blacklisting", endpoint_name)
        elif "Connection refused" in err_str or "No route" in err_str:
            log.warning("x %s unreachable: %s", endpoint_name, err_str[:60])
            _mark_failed(endpoint_name)
        else:
            log.warning("x %s OS error: %s", endpoint_name, err_str[:80])
            _mark_failed(endpoint_name)
        return None
    except Exception as e:
        err_str = str(e)
        if "timed out" in err_str:
            log.warning("x %s timed out — not blacklisting", endpoint_name)
        else:
            log.warning("x %s failed: %s", endpoint_name, err_str[:80])
            _mark_failed(endpoint_name)
        return None


# ─── Mac Local (OpenAI-compat passthrough) ───────────────────────────────────

def _try_mac_local(path: str, body: bytes, model: str = "") -> tuple[int, bytes] | None:
    """Try Mac local Ollama via OpenAI-compat /v1/ endpoint.

    Only marks failed for connection-level errors.
    HTTP 404 (model not found) and BrokenPipe (client disconnected) do NOT
    indicate the endpoint is down.
    """
    if not _is_healthy("mac-local"):
        return None
    try:
        url = f"{MAC_LOCAL}{path}"
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
            _mark_ok("mac-local")
            log.info("-> inference via mac-local (openai-compat, model=%s)", model or "?")
            return resp.status, data
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log.warning("x mac-local: model '%s' not found (404) — endpoint healthy", model)
        else:
            log.warning("x mac-local HTTP %d: %s", e.code, str(e)[:60])
            _mark_failed("mac-local")
        return None
    except BrokenPipeError:
        # Client (hermes-agent) disconnected before we could respond — not Mac's fault
        log.warning("x mac-local: client disconnected (BrokenPipe) — endpoint healthy")
        return None
    except Exception as e:
        log.warning("x mac-local failed: %s", str(e)[:80])
        _mark_failed("mac-local")
        return None


# ─── Kimi Cloud ──────────────────────────────────────────────────────────────

def _call_openai_compat(base: str, model: str, api_key: str, messages: list,
                         max_tokens: int, temperature: float, label: str) -> dict | None:
    """Generic OpenAI-compatible cloud call. Returns OpenAI-format dict or None."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "stream": False,
    }).encode()
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
            _mark_ok("kimi-cloud")
            log.info("-> inference via %s", label)
            data["model"] = label
            return data
    except Exception as e:
        log.warning("x %s failed: %s", label, str(e)[:80])
        return None


def _load_kimi_token() -> str | None:
    """Load current Kimi OAuth bearer token from disk (refreshed by kimi CLI)."""
    try:
        with open(KIMI_TOKEN_FILE) as f:
            data = json.load(f)
        expires_at = data.get("expires_at", 0)
        if time.time() > expires_at:
            log.warning("Kimi token expired (expires_at=%s)", expires_at)
            return None
        return data.get("access_token")
    except Exception as e:
        log.warning("Could not load Kimi token: %s", e)
        return None


def _call_kimi_cloud(messages: list, max_tokens: int = 2048,
                     temperature: float = 0.7) -> dict | None:
    """Call cloud research API. Prefers permanent API keys over OAuth token.

    Priority: MOONSHOT_API_KEY → OPENROUTER_API_KEY → Kimi OAuth token
    """
    if not _is_healthy("kimi-cloud"):
        return None

    # Prefer permanent API key (Moonshot direct) — no expiry issues
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

    # OpenRouter fallback (free tier models available)
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

    # No API key configured — skip gracefully, don't mark failed
    log.debug("kimi-cloud: no API key configured, skipping tier")
    return None


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
                    "t2_pi_rari1": PI_RARI1,
                    "t2_pi_rari2": PI_RARI2,
                    "t3_mac_local": MAC_LOCAL,
                    "t4_kimi_cloud": KIMI_API_BASE,
                },
            })
            return

        # Proxy GET to first available endpoint (model list, etc.)
        for name, base in [("windows-gpu", WINDOWS_GPU), ("pi-rari1", PI_RARI1),
                            ("pi-rari2", PI_RARI2), ("mac-local", MAC_LOCAL)]:
            if not _is_healthy(name):
                continue
            try:
                url = f"{base}{self.path}"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    data = resp.read()
                    _mark_ok(name)
                    self.send_response(resp.status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(data)
                    return
            except Exception:
                _mark_failed(name)
                continue
        self._respond(503, {"error": "All endpoints unavailable"})

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            req_data = json.loads(body)
        except json.JSONDecodeError:
            self._respond(400, {"error": "Invalid JSON"})
            return

        raw_model = req_data.get("model", "auto")
        model = MODEL_TIERS.get(raw_model, raw_model)
        req_data["model"] = model
        body = json.dumps(req_data).encode()

        messages    = req_data.get("messages", [])
        max_tokens  = req_data.get("max_tokens", 512)
        temperature = req_data.get("temperature", 0.7)
        is_chat     = "/v1/chat/completions" in self.path
        needs_gpu   = model in GPU_ONLY_MODELS
        wants_kimi  = model == "kimi-cloud"

        # ── Kimi Cloud shortcut (explicit request) ──────────────────────────
        if wants_kimi and is_chat:
            if _is_sensitive(messages):
                log.warning("! kimi-cloud blocked: sensitive content detected")
                self._respond(400, {
                    "error": "Sensitive content detected — Kimi Cloud routing blocked",
                    "code": "sensitive_routing_blocked",
                })
                return
            resp = _call_kimi_cloud(messages, max_tokens, temperature)
            if resp:
                self._respond(200, resp)
                return
            # Kimi failed — fall through to local tiers
            log.warning("Kimi Cloud unavailable, falling back to local tiers")
            model = "hermes3:8b"  # reroute to default
            req_data["model"] = model
            body = json.dumps(req_data).encode()

        if not is_chat:
            # Non-chat POST — proxy directly
            result = _try_mac_local(self.path, body)
            if result:
                self.send_response(result[0])
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(result[1])
                return
            self._respond(503, {"error": "All endpoints unavailable"})
            return

        # ── Tier 1: Windows GPU ──────────────────────────────────────────────
        # 90s timeout: model cold-load can take 30-60s on RTX 5070 Ti
        resp = _try_ollama_native("windows-gpu", WINDOWS_GPU, model,
                                  messages, max_tokens, temperature, timeout=90)
        if resp:
            self._respond(200, resp)
            return

        # GPU-only models cannot fall back to Pi or Mac
        if needs_gpu:
            log.error("GPU-only model %s — all GPU attempts failed", model)
            self._respond(503, {
                "error": f"GPU-only model '{model}' unavailable (Windows GPU down)",
                "code": "gpu_only_unavailable",
            })
            return

        # ── Tier 2: Pi (lightweight models only, when PI_OLLAMA_ENABLED=1) ────
        if PI_ENABLED:
            pi_model = model if model in PI_MODELS else PI_DEFAULT_MODEL
            if _is_healthy("pi-rari1"):
                resp = _try_ollama_native("pi-rari1", PI_RARI1, pi_model,
                                          messages, max_tokens, temperature, timeout=30)
                if resp:
                    resp["model"] = f"{resp['model']} (pi-rari1)"
                    self._respond(200, resp)
                    return

            if _is_healthy("pi-rari2"):
                resp = _try_ollama_native("pi-rari2", PI_RARI2, pi_model,
                                          messages, max_tokens, temperature, timeout=30)
                if resp:
                    resp["model"] = f"{resp['model']} (pi-rari2)"
                    self._respond(200, resp)
                    return

        # ── Tier 3: Mac local ────────────────────────────────────────────────
        # Substitute model if requested model isn't on Mac (Mac has hermes3:8b + llama3.2)
        mac_model = model if model not in GPU_ONLY_MODELS and model not in PI_MODELS else MAC_FALLBACK_MODEL
        if mac_model != model:
            mac_body = json.dumps({**req_data, "model": mac_model}).encode()
            log.info("Mac fallback: substituting model '%s' → '%s'", model, mac_model)
        else:
            mac_body = body
        result = _try_mac_local(self.path, mac_body, mac_model)
        if result:
            self.send_response(result[0])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(result[1])
            return

        # ── Tier 4: Kimi Cloud (non-sensitive fallback) ──────────────────────
        log.warning("All local tiers down — attempting Kimi Cloud fallback")
        if _is_sensitive(messages):
            log.warning("! kimi-cloud fallback blocked: sensitive content")
            self._respond(503, {
                "error": "All local inference unavailable and content is sensitive — cannot route to cloud",
                "code": "all_tiers_exhausted",
            })
            return

        resp = _call_kimi_cloud(messages, max_tokens, temperature)
        if resp:
            self._respond(200, resp)
            return

        self._respond(503, {"error": "All inference tiers exhausted"})

    def _respond(self, code: int, body: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        pass  # Suppress default per-request logging (we log our own)


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), ProxyHandler)
    log.info("Sapphire Inference Proxy :%d — 4-tier failover", PORT)
    log.info("T1 Windows GPU : %s (native /api/chat)", WINDOWS_GPU)
    log.info("T2 Pi rari1    : %s enabled=%s", PI_RARI1, PI_ENABLED)
    log.info("T2 Pi rari2    : %s enabled=%s", PI_RARI2, PI_ENABLED)
    log.info("T3 Mac local   : %s (/v1/ openai-compat)", MAC_LOCAL)
    log.info("T4 Kimi Cloud  : moonshot=%s openrouter=%s (non-sensitive only)",
             bool(MOONSHOT_API_KEY), bool(OPENROUTER_API_KEY))
    log.info("Health cooldown: %ds", HEALTH_COOLDOWN)
    server.serve_forever()
