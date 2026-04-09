"""Sapphire Inference Proxy — smart failover between Ollama instances.

Tries Windows GPU first (native /api/chat), falls back to Mac (/v1/).
Translates between OpenAI-compatible format and native Ollama format
so hermes-agent always gets OpenAI-compatible responses regardless
of which backend handles the request.

Endpoints:
  /v1/chat/completions  — OpenAI-compatible (what hermes-agent uses)
  /v1/models            — List models
  /health               — Proxy health
"""

import json
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("inference-proxy")

WINDOWS_GPU = "http://100.71.10.48:11434"
MAC_LOCAL = "http://127.0.0.1:11434"
PORT = 11435

# ─── Smart Model Routing ────────────────────────────────────────────────────
# Map task complexity to optimal model. Client sends model="auto" or a tier name.
MODEL_TIERS = {
    # Tier aliases → actual model names
    "auto": "hermes3:8b",         # Default: good all-rounder
    "fast": "nemotron-mini:4b",   # Quick classification, simple Q&A
    "quick": "nemotron-mini:4b",
    "balanced": "hermes3:8b",     # Tool calling, conversation
    "deep": "qwen3:14b",         # Complex reasoning (Windows GPU only)
    "code": "qwen2.5-coder:14b", # Code generation (Windows GPU only)
    "reason": "deepseek-r1:14b", # Deep chain-of-thought (Windows GPU only)
    "large": "qwen2.5:32b",      # Maximum capability (Windows GPU only)
}

# Models that require Windows GPU (too large for Mac)
GPU_ONLY_MODELS = {"qwen3:14b", "qwen2.5-coder:14b", "deepseek-r1:14b", "deepseek-r1:32b",
                    "qwen2.5:32b", "qwen2.5:14b", "gemma3:27b", "llama3.3:70b", "qwq:latest"}

# Track which endpoint is healthy (avoid repeated timeouts)
_endpoint_health = {"windows-gpu": True, "mac-local": True}
_health_check_interval = 60  # Re-check failed endpoint after 60s
_last_health_check = {"windows-gpu": 0, "mac-local": 0}


def _is_healthy(name):
    """Check if endpoint should be tried (skip if recently failed)."""
    if _endpoint_health[name]:
        return True
    if time.time() - _last_health_check[name] > _health_check_interval:
        return True  # Retry after cooldown
    return False


def _mark_failed(name):
    _endpoint_health[name] = False
    _last_health_check[name] = time.time()


def _mark_ok(name):
    _endpoint_health[name] = True


def _call_native_ollama(base_url, model, messages, max_tokens=512, temperature=0.7):
    """Call Ollama native /api/chat and return the response dict."""
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
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read())


def _native_to_openai(native_resp, model):
    """Convert Ollama native /api/chat response to OpenAI format."""
    msg = native_resp.get("message", {})
    eval_count = native_resp.get("eval_count", 0)
    prompt_count = native_resp.get("prompt_eval_count", 0)

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
            "prompt_tokens": prompt_count,
            "completion_tokens": eval_count,
            "total_tokens": prompt_count + eval_count,
        },
    }


class ProxyHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {
                "status": "ok",
                "service": "inference-proxy",
                "endpoints": {
                    "windows-gpu": "healthy" if _endpoint_health["windows-gpu"] else "failed",
                    "mac-local": "healthy" if _endpoint_health["mac-local"] else "failed",
                },
            })
            return

        # Proxy GET requests (models list, etc.)
        for name, base in [("windows-gpu", WINDOWS_GPU), ("mac-local", MAC_LOCAL)]:
            if not _is_healthy(name):
                continue
            try:
                url = f"{base}{self.path}"
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:
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

        # Parse the OpenAI-format request
        try:
            req_data = json.loads(body)
        except json.JSONDecodeError:
            self._respond(400, {"error": "Invalid JSON"})
            return

        raw_model = req_data.get("model", "hermes3:8b")
        # Resolve tier aliases (auto, fast, deep, code, etc.)
        model = MODEL_TIERS.get(raw_model, raw_model)
        req_data["model"] = model  # Update for passthrough
        body = json.dumps(req_data).encode()  # Re-encode with resolved model

        messages = req_data.get("messages", [])
        max_tokens = req_data.get("max_tokens", 512)
        temperature = req_data.get("temperature", 0.7)

        is_chat = "/v1/chat/completions" in self.path
        needs_gpu = model in GPU_ONLY_MODELS

        # Try Windows GPU first (native API — works reliably)
        # GPU-only models MUST go to Windows (skip Mac fallback for these)
        if (needs_gpu or _is_healthy("windows-gpu")) and is_chat:
            try:
                native_resp = _call_native_ollama(WINDOWS_GPU, model, messages, max_tokens, temperature)
                content = native_resp.get("message", {}).get("content", "")
                if content:  # Only use if we got actual content
                    openai_resp = _native_to_openai(native_resp, model)
                    _mark_ok("windows-gpu")
                    log.info("-> /v1/chat/completions via windows-gpu (native)")
                    self._respond(200, openai_resp)
                    return
                else:
                    log.warning("x windows-gpu returned empty content")
                    _mark_failed("windows-gpu")
            except Exception as e:
                log.warning("x windows-gpu native failed: %s", str(e)[:80])
                _mark_failed("windows-gpu")

        # Try Mac (OpenAI-compat works fine on Mac Ollama)
        if _is_healthy("mac-local"):
            try:
                url = f"{MAC_LOCAL}{self.path}"
                req = urllib.request.Request(
                    url, data=body,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = resp.read()
                    _mark_ok("mac-local")
                    log.info("-> %s via mac-local", self.path)
                    self.send_response(resp.status)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(data)
                    return
            except Exception as e:
                log.warning("x mac-local failed: %s", str(e)[:80])
                _mark_failed("mac-local")

        # Try Windows with direct passthrough as last resort
        if is_chat:
            try:
                native_resp = _call_native_ollama(WINDOWS_GPU, model, messages, max_tokens, temperature)
                openai_resp = _native_to_openai(native_resp, model)
                _mark_ok("windows-gpu")
                log.info("-> /v1/chat/completions via windows-gpu (native, retry)")
                self._respond(200, openai_resp)
                return
            except Exception:
                pass

        self._respond(503, {"error": "All inference endpoints unavailable"})

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("127.0.0.1", PORT), ProxyHandler)
    log.info("Inference proxy on :%d", PORT)
    log.info("Windows GPU: %s (native /api/chat → OpenAI translation)", WINDOWS_GPU)
    log.info("Mac local: %s (direct /v1/ passthrough)", MAC_LOCAL)
    log.info("Health check cooldown: %ds", _health_check_interval)
    server.serve_forever()
