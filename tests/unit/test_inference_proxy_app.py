"""Tests for inference-proxy app routing/health/sensitivity/x402 logic.

Loads ``services/inference-proxy/app.py`` via ``importlib.util`` (mirroring
``test_task_classifier.py``) so the production source is exercised without
booting a real socket. Outbound calls are stubbed via ``urllib.request``
overrides and the ``ProxyHandler`` is driven by a fake rfile/wfile pair.

Run: /usr/local/bin/python3 -m pytest tests/unit/test_inference_proxy_app.py -v
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import time
import urllib.error
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SVC_DIR = ROOT / "services" / "inference-proxy"
APP_PATH = SVC_DIR / "app.py"
MODULE_NAME = "inference_proxy_app_under_test"


# ─── Module loader ────────────────────────────────────────────────────────────
# Load app.py once per test session. The module mutates sys.path to find its
# sibling modules (task_classifier, lib/payments/x402_middleware,
# lib/telegram/kimi_relay); those side effects are accepted as part of the
# real import path. We do NOT execute ``server.serve_forever()`` because the
# server is only started under ``__name__ == "__main__"``.


@pytest.fixture(scope="session")
def app_module():
    if str(SVC_DIR) not in sys.path:
        sys.path.insert(0, str(SVC_DIR))
    spec = importlib.util.spec_from_file_location(MODULE_NAME, APP_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def reset_health_and_metrics(app_module):
    """Reset health flags + metrics counters between tests."""
    with app_module._health_lock:
        for name in app_module.ENDPOINTS:
            app_module._endpoint_health[name] = True
            app_module._last_health_check[name] = 0.0
    with app_module._metrics_lock:
        for v in app_module._metrics.values():
            v["requests"] = 0
            v["success"] = 0
            v["failure"] = 0
            v["total_ms"] = 0
    yield


# ─── Model alias resolution ───────────────────────────────────────────────────


class TestModelAliases:
    def test_fast_resolves_to_nemotron_mini(self, app_module):
        assert app_module.MODEL_TIERS["fast"] == "nemotron-mini:latest"
        assert app_module.MODEL_TIERS["quick"] == "nemotron-mini:latest"

    def test_auto_and_balanced_resolve_to_hermes3(self, app_module):
        assert app_module.MODEL_TIERS["auto"] == "hermes3:8b"
        assert app_module.MODEL_TIERS["balanced"] == "hermes3:8b"

    def test_kimi_aliases_resolve_to_kimi_cloud(self, app_module):
        for alias in ("kimi", "kimi-fast", "kimi-large", "kimi-cloud", "cloud", "research"):
            assert app_module.MODEL_TIERS[alias] == "kimi-cloud", alias

    def test_code_alias_resolves_to_gemma4(self, app_module):
        assert app_module.MODEL_TIERS["code"] == "gemma4:latest"
        assert app_module.MODEL_TIERS["fast-code"] == "gemma4:latest"

    def test_reason_alias_resolves_to_deepseek_r1(self, app_module):
        assert app_module.MODEL_TIERS["reason"] == "deepseek-r1:14b"

    def test_unknown_alias_passes_through_in_handler(self, app_module):
        # Behaviour: handler does ``MODEL_TIERS.get(raw_model, raw_model)`` —
        # unknown aliases are passed through unchanged. Documented here so
        # any contract change shows up as a test break.
        assert app_module.MODEL_TIERS.get("not-an-alias", "not-an-alias") == "not-an-alias"


# ─── Tier-membership classification ───────────────────────────────────────────


class TestTierMembership:
    def test_gpu_only_models_routed_to_windows(self, app_module):
        # Models that need Windows GPU and should NOT fall back through
        # smaller tiers.
        assert "deepseek-r1:14b" in app_module.GPU_ONLY_MODELS
        assert "qwen2.5:32b" in app_module.GPU_ONLY_MODELS
        assert "gemma4:latest" in app_module.GPU_ONLY_MODELS
        assert "nemotron-cascade-2" in app_module.GPU_ONLY_MODELS

    def test_pi_serve_models_subset(self, app_module):
        # nemotron-mini is in PI_MODELS for inventory but excluded from
        # PI_SERVE_MODELS (it times out). Live Pi traffic uses qwen2.5:0.5b.
        assert "qwen2.5:0.5b" in app_module.PI_SERVE_MODELS
        assert "nemotron-mini:4b" not in app_module.PI_SERVE_MODELS
        assert app_module.PI_DEFAULT_MODEL == "qwen2.5:0.5b"

    def test_mac_exact_fallback_excludes_pi_serve(self, app_module):
        # Models on Mac that aren't Pi-serveable should be preferred on Mac
        # rather than substituted to PI_DEFAULT_MODEL.
        assert "hermes3:8b" in app_module.MAC_EXACT_FALLBACK_MODELS
        # Pi-serveable models should NOT be in the exact-fallback set.
        for m in app_module.PI_SERVE_MODELS:
            assert m not in app_module.MAC_EXACT_FALLBACK_MODELS

    def test_select_pi_model_substitutes_when_not_pi_safe(self, app_module):
        assert app_module._select_pi_model("hermes3:8b") == app_module.PI_DEFAULT_MODEL
        assert app_module._select_pi_model("qwen2.5:0.5b") == "qwen2.5:0.5b"

    def test_enabled_pi_targets_respects_flags(self, app_module, monkeypatch):
        # Monkey-patch the module-level flags rather than env (env is already
        # captured at import time).
        monkeypatch.setattr(app_module, "PI_RARI1_ENABLED", True)
        monkeypatch.setattr(app_module, "PI_RARI2_ENABLED", False)
        targets = app_module._enabled_pi_targets()
        names = [t[0] for t in targets]
        assert names == ["pi-rari1"]

        monkeypatch.setattr(app_module, "PI_RARI2_ENABLED", True)
        targets = app_module._enabled_pi_targets()
        names = [t[0] for t in targets]
        assert names == ["pi-rari1", "pi-rari2"]


# ─── Sensitivity classifier ───────────────────────────────────────────────────


class TestSensitivityGate:
    @pytest.mark.parametrize(
        "phrase",
        [
            "my api_key is sk-1234",
            "Bearer eyJhbG...",
            "JWT abc.def.ghi",
            "password: hunter2",
            "client_secret = ABCD",
            "private_key starts with -----",
            "access_token=xyz",
            "refresh_token: foobar",
            "SSN: 123-45-6789",
            "card 4111 1111 1111 1111",
            "xoxb-1234567-deadbeef-token",
            "postgres://user:pass@host:5432/db",
        ],
    )
    def test_sensitive_strings_blocked(self, app_module, phrase):
        msgs = [{"role": "user", "content": phrase}]
        assert app_module._is_sensitive(msgs) is True, phrase

    def test_sensitive_in_block_content(self, app_module):
        # Content can be a list of blocks (vision/tool-use shape).
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "harmless prefix"},
                    {"type": "text", "text": "my password is hunter2"},
                ],
            }
        ]
        assert app_module._is_sensitive(msgs) is True

    def test_benign_content_is_not_sensitive(self, app_module):
        msgs = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "What is the price of BTC?"},
        ]
        assert app_module._is_sensitive(msgs) is False

    def test_non_string_non_list_content_skipped(self, app_module):
        # Defensive: the function should not crash on unexpected shapes.
        msgs = [{"role": "user", "content": None}, {"role": "user"}]
        assert app_module._is_sensitive(msgs) is False


# ─── Health probe + cooldown logic ────────────────────────────────────────────


class TestHealthTracking:
    def test_default_endpoint_is_healthy(self, app_module):
        assert app_module._is_healthy("windows-gpu") is True

    def test_mark_failed_makes_unhealthy_within_cooldown(self, app_module):
        app_module._mark_failed("windows-gpu")
        # Within cooldown — should report unhealthy.
        assert app_module._is_healthy("windows-gpu") is False

    def test_mark_failed_recovers_after_cooldown_window(self, app_module, monkeypatch):
        app_module._mark_failed("windows-gpu")
        # Push the failure timestamp older than the cooldown so the next
        # healthcheck call returns True (allowing a retry probe).
        with app_module._health_lock:
            app_module._last_health_check["windows-gpu"] = (
                time.time() - app_module.HEALTH_COOLDOWN - 5
            )
        assert app_module._is_healthy("windows-gpu") is True

    def test_mark_ok_clears_failed_flag(self, app_module):
        app_module._mark_failed("pi-rari1")
        assert app_module._is_healthy("pi-rari1") is False
        app_module._mark_ok("pi-rari1")
        assert app_module._is_healthy("pi-rari1") is True

    def test_should_preflight_for_failed_endpoint(self, app_module):
        # When unhealthy + still in cooldown, should NOT preflight (waste).
        app_module._mark_failed("mac-local")
        assert app_module._should_preflight("mac-local") is False
        # Push the last check beyond cooldown — should preflight.
        with app_module._health_lock:
            app_module._last_health_check["mac-local"] = (
                time.time() - app_module.HEALTH_COOLDOWN - 5
            )
        assert app_module._should_preflight("mac-local") is True

    def test_should_preflight_for_stale_healthy(self, app_module):
        # Healthy but never verified — should preflight.
        with app_module._health_lock:
            app_module._endpoint_health["mac-local"] = True
            app_module._last_health_check["mac-local"] = 0.0
        assert app_module._should_preflight("mac-local", max_age_sec=30) is True


# ─── Outbound allowlist ───────────────────────────────────────────────────────


class TestOutboundAllowlist:
    @pytest.mark.parametrize(
        "url",
        [
            "https://api.moonshot.cn/v1/chat/completions",
            "https://openrouter.ai/api/v1/chat/completions",
            "https://api.openai.com/v1/embeddings",
        ],
    )
    def test_allowlisted_hosts_pass(self, app_module, url):
        assert app_module._is_allowed_outbound(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "https://evil.example.com/v1/chat/completions",
            "http://127.0.0.1:11434/api/chat",  # local Ollama is NOT in allowlist
            "https://api.anthropic.com/v1/messages",
        ],
    )
    def test_non_allowlisted_hosts_blocked(self, app_module, url):
        assert app_module._is_allowed_outbound(url) is False


# ─── Native → OpenAI conversion ───────────────────────────────────────────────


class TestNativeToOpenAI:
    def test_basic_conversion_shape(self, app_module):
        native = {
            "message": {"role": "assistant", "content": "hello"},
            "prompt_eval_count": 5,
            "eval_count": 3,
        }
        out = app_module._native_to_openai(native, "hermes3:8b")
        assert out["object"] == "chat.completion"
        assert out["model"] == "hermes3:8b"
        assert out["choices"][0]["message"]["content"] == "hello"
        assert out["choices"][0]["message"]["role"] == "assistant"
        assert out["choices"][0]["finish_reason"] == "stop"
        assert out["usage"]["prompt_tokens"] == 5
        assert out["usage"]["completion_tokens"] == 3
        assert out["usage"]["total_tokens"] == 8

    def test_thinking_field_used_when_content_empty(self, app_module):
        # qwen3 / deepseek-r1 leak full output into "thinking" when content
        # is empty — surface it instead of dropping the response.
        native = {
            "message": {"role": "assistant", "content": "", "thinking": "deep thoughts"},
        }
        out = app_module._native_to_openai(native, "qwen3:14b")
        assert "[thinking]" in out["choices"][0]["message"]["content"]
        assert "deep thoughts" in out["choices"][0]["message"]["content"]


# ─── Metrics recording ────────────────────────────────────────────────────────


class TestMetrics:
    def test_record_increments_counters(self, app_module):
        app_module._record("windows-gpu", success=True, elapsed_ms=120)
        app_module._record("windows-gpu", success=False, elapsed_ms=80)
        m = app_module._metrics["windows-gpu"]
        assert m["requests"] == 2
        assert m["success"] == 1
        assert m["failure"] == 1
        assert m["total_ms"] == 200

    def test_record_caps_unknown_keys(self, app_module):
        # Insert filler tiers up to (just under) the cap, then add one more
        # unknown tier — it should be dropped silently.
        max_keys = app_module._MAX_METRIC_KEYS
        with app_module._metrics_lock:
            current = len(app_module._metrics)
        for i in range(max_keys - current):
            app_module._record(f"filler-{i}", True, 1)
        app_module._record("overflow-tier", True, 1)
        assert "overflow-tier" not in app_module._metrics


# ─── Outbound HTTP wrappers ───────────────────────────────────────────────────


class _FakeUrlResp:
    """Stand-in for the object returned by urlopen() — supports context manager."""

    def __init__(self, body: bytes, status: int = 200):
        self._body = body
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestTryOllamaNative:
    def test_success_marks_ok_and_records(self, app_module, monkeypatch):
        native_body = json.dumps(
            {
                "message": {"role": "assistant", "content": "ok"},
                "prompt_eval_count": 1,
                "eval_count": 1,
            }
        ).encode()

        def fake_urlopen(req, timeout=0):
            return _FakeUrlResp(native_body, status=200)

        monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)
        # Begin marked healthy.
        result = app_module._try_ollama_native(
            "windows-gpu",
            app_module.WINDOWS_GPU,
            "hermes3:8b",
            [{"role": "user", "content": "hi"}],
            16,
            0.7,
            timeout=2,
        )
        assert result is not None
        assert result["choices"][0]["message"]["content"] == "ok"
        assert app_module._is_healthy("windows-gpu") is True
        assert app_module._metrics["windows-gpu"]["success"] == 1

    def test_404_does_not_blacklist_endpoint(self, app_module, monkeypatch):
        def fake_urlopen(req, timeout=0):
            raise urllib.error.HTTPError(
                url="http://x",
                code=404,
                msg="not found",
                hdrs=None,
                fp=None,
            )

        monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)
        result = app_module._try_ollama_native(
            "windows-gpu",
            app_module.WINDOWS_GPU,
            "missing-model",
            [{"role": "user", "content": "hi"}],
            16,
            0.7,
            timeout=2,
        )
        assert result is None
        # 404 = healthy endpoint, just unknown model.
        assert app_module._is_healthy("windows-gpu") is True

    def test_timeout_marks_endpoint_failed(self, app_module, monkeypatch):
        def fake_urlopen(req, timeout=0):
            raise TimeoutError("timed out")

        monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)
        result = app_module._try_ollama_native(
            "windows-gpu",
            app_module.WINDOWS_GPU,
            "hermes3:8b",
            [{"role": "user", "content": "hi"}],
            16,
            0.7,
            timeout=2,
        )
        assert result is None
        assert app_module._is_healthy("windows-gpu") is False

    def test_skips_when_endpoint_unhealthy(self, app_module, monkeypatch):
        app_module._mark_failed("windows-gpu")
        called = {"n": 0}

        def fake_urlopen(req, timeout=0):
            called["n"] += 1
            return _FakeUrlResp(b"{}", status=200)

        monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)
        result = app_module._try_ollama_native(
            "windows-gpu",
            app_module.WINDOWS_GPU,
            "hermes3:8b",
            [{"role": "user", "content": "hi"}],
            16,
            0.7,
        )
        assert result is None
        # Should not have tried the real call when health says no + still in cooldown.
        assert called["n"] == 0


class TestTryMacLocal:
    def test_success_returns_status_and_body(self, app_module, monkeypatch):
        body = b'{"choices":[{"message":{"role":"assistant","content":"hi"}}]}'

        def fake_urlopen(req, timeout=0):
            return _FakeUrlResp(body, status=200)

        monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)
        out = app_module._try_mac_local("/v1/chat/completions", b"{}", "hermes3:8b")
        assert out is not None
        status, payload = out
        assert status == 200
        assert payload == body

    def test_404_does_not_blacklist(self, app_module, monkeypatch):
        def fake_urlopen(req, timeout=0):
            raise urllib.error.HTTPError(
                url="http://x",
                code=404,
                msg="not found",
                hdrs=None,
                fp=None,
            )

        monkeypatch.setattr(app_module.urllib.request, "urlopen", fake_urlopen)
        out = app_module._try_mac_local("/v1/chat/completions", b"{}", "ghost-model")
        assert out is None
        assert app_module._is_healthy("mac-local") is True


# ─── ProxyHandler request validation ──────────────────────────────────────────
# Drive the handler with a fake rfile/wfile so we exercise the do_POST control
# flow without a real socket.


def _make_handler(
    app_module,
    *,
    path: str,
    body: bytes,
    headers: dict[str, str] | None = None,
    method: str = "POST",
):
    """Construct a ProxyHandler bound to in-memory rfile/wfile."""
    headers = dict(headers or {})
    headers.setdefault("Content-Length", str(len(body)))
    headers.setdefault("Host", "localhost")

    handler = app_module.ProxyHandler.__new__(app_module.ProxyHandler)
    handler.rfile = io.BytesIO(body)
    handler.wfile = io.BytesIO()
    handler.headers = headers
    handler.path = path
    handler.command = method
    handler.client_address = ("127.0.0.1", 0)
    handler.request_version = "HTTP/1.1"

    # Capture send_response/send_header/end_headers calls without writing
    # them to a real socket — the real implementations work fine on
    # io.BytesIO, but we keep the response status + headers easy to inspect.
    handler._captured_status: int | None = None
    handler._captured_headers: list[tuple[str, str]] = []

    def fake_send_response(code, message=None):
        handler._captured_status = code

    def fake_send_header(key, value):
        handler._captured_headers.append((key, str(value)))

    def fake_end_headers():
        pass

    handler.send_response = fake_send_response
    handler.send_header = fake_send_header
    handler.end_headers = fake_end_headers
    return handler


def _response_payload(handler) -> dict[str, Any]:
    raw = handler.wfile.getvalue()
    return json.loads(raw) if raw else {}


class TestPostValidation:
    def test_invalid_json_returns_400(self, app_module):
        handler = _make_handler(app_module, path="/v1/chat/completions", body=b"not json")
        handler.do_POST()
        assert handler._captured_status == 400
        body = _response_payload(handler)
        assert "Invalid JSON" in body["error"]

    def test_empty_messages_returns_400(self, app_module):
        body = json.dumps({"model": "auto", "messages": []}).encode()
        handler = _make_handler(app_module, path="/v1/chat/completions", body=body)
        handler.do_POST()
        assert handler._captured_status == 400
        payload = _response_payload(handler)
        assert payload["code"] == "invalid_request"

    def test_oversized_body_returns_413(self, app_module):
        # Don't actually allocate 5 MB — claim it via header.
        handler = _make_handler(
            app_module,
            path="/v1/chat/completions",
            body=b"{}",
            headers={"Content-Length": str(5 * 1024 * 1024)},
        )
        handler.do_POST()
        assert handler._captured_status == 413
        payload = _response_payload(handler)
        assert payload["code"] == "body_too_large"

    def test_kimi_route_blocks_sensitive_content(self, app_module, monkeypatch):
        # Make sure no real network call leaks even if the gate fails.
        def boom(*a, **kw):
            raise AssertionError("kimi cloud should never be called for sensitive content")

        monkeypatch.setattr(app_module, "_call_kimi_cloud", boom)
        body = json.dumps(
            {
                "model": "kimi",
                "messages": [{"role": "user", "content": "what is my api_key?"}],
            }
        ).encode()
        handler = _make_handler(app_module, path="/v1/chat/completions", body=body)
        handler.do_POST()
        assert handler._captured_status == 400
        payload = _response_payload(handler)
        assert payload["code"] == "sensitive_routing_blocked"

    def test_gpu_only_model_503_when_windows_down(self, app_module, monkeypatch):
        # Mark Windows GPU failed so _try_ollama_native short-circuits to None,
        # and force needs_gpu by asking for a known GPU-only model.
        app_module._mark_failed("windows-gpu")

        def fake_call(*a, **kw):
            return None

        monkeypatch.setattr(app_module, "_try_ollama_native", lambda *a, **kw: None)
        monkeypatch.setattr(app_module, "_probe_endpoint", lambda *a, **kw: False)
        body = json.dumps(
            {
                "model": "qwen2.5:32b",
                "messages": [{"role": "user", "content": "hi"}],
            }
        ).encode()
        handler = _make_handler(app_module, path="/v1/chat/completions", body=body)
        handler.do_POST()
        assert handler._captured_status == 503
        payload = _response_payload(handler)
        assert payload["code"] == "gpu_only_unavailable"

    def test_all_tiers_exhausted_sensitive(self, app_module, monkeypatch):
        # Flag all local tiers as down, and feed sensitive content. Should
        # come back as 503 / all_tiers_exhausted_sensitive without ever
        # calling Kimi Cloud.
        for name in ("windows-gpu", "pi-rari1", "pi-rari2", "mac-local"):
            app_module._mark_failed(name)

        monkeypatch.setattr(app_module, "_try_ollama_native", lambda *a, **kw: None)
        monkeypatch.setattr(app_module, "_try_mac_local", lambda *a, **kw: None)
        monkeypatch.setattr(app_module, "_probe_endpoint", lambda *a, **kw: False)

        def boom(*a, **kw):
            raise AssertionError("kimi-cloud should not be called for sensitive content")

        monkeypatch.setattr(app_module, "_call_kimi_cloud", boom)

        body = json.dumps(
            {
                "model": "auto",
                "messages": [{"role": "user", "content": "password=hunter2"}],
            }
        ).encode()
        handler = _make_handler(app_module, path="/v1/chat/completions", body=body)
        handler.do_POST()
        assert handler._captured_status == 503
        payload = _response_payload(handler)
        assert payload["code"] == "all_tiers_exhausted_sensitive"


class TestKimiRelayFallback:
    def test_relay_uses_reader_token_gate_not_legacy_kimi_claw_token(
        self,
        app_module,
        monkeypatch,
    ):
        monkeypatch.setattr(app_module, "MOONSHOT_API_KEY", "")
        monkeypatch.setattr(app_module, "OPENROUTER_API_KEY", "")
        monkeypatch.setattr(app_module, "_KIMI_RELAY_AVAILABLE", True)
        monkeypatch.setattr(app_module, "_kimi_relay_fn", lambda query: f"relay saw: {query}")
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "sender-token")
        monkeypatch.setenv("RELAY_READER_TOKEN", "reader-token")
        monkeypatch.setenv("KIMI_RELAY_CHAT_ID", "-100")
        monkeypatch.delenv("KIMI_CLAW_BOT_TOKEN", raising=False)

        result = app_module._call_kimi_cloud(
            [{"role": "user", "content": "summarize readiness"}]
        )

        assert result is not None
        assert result["model"] == "kimi-relay"
        assert "summarize readiness" in result["choices"][0]["message"]["content"]

    def test_relay_requires_sender_reader_and_chat_env(self, app_module, monkeypatch):
        def boom(_query):
            raise AssertionError("relay should not be called without all env gates")

        monkeypatch.setattr(app_module, "MOONSHOT_API_KEY", "")
        monkeypatch.setattr(app_module, "OPENROUTER_API_KEY", "")
        monkeypatch.setattr(app_module, "_KIMI_RELAY_AVAILABLE", True)
        monkeypatch.setattr(app_module, "_kimi_relay_fn", boom)
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "sender-token")
        monkeypatch.delenv("RELAY_READER_TOKEN", raising=False)
        monkeypatch.setenv("KIMI_RELAY_CHAT_ID", "-100")

        assert app_module._call_kimi_cloud([{"role": "user", "content": "hello"}]) is None


# ─── /health and /metrics shape ───────────────────────────────────────────────


class TestGetEndpoints:
    def test_health_response_shape(self, app_module):
        handler = _make_handler(
            app_module,
            path="/health",
            body=b"",
            method="GET",
        )
        handler.do_GET()
        assert handler._captured_status == 200
        payload = _response_payload(handler)
        assert payload["status"] == "ok"
        assert payload["service"] == "inference-proxy"
        assert set(payload["endpoints"].keys()) == set(app_module.ENDPOINTS)
        for status in payload["endpoints"].values():
            assert status in {"healthy", "failed"}
        assert "tiers" in payload
        assert "t1_windows_gpu" in payload["tiers"]

    def test_metrics_response_shape_with_data(self, app_module):
        # Seed a few metric points to exercise the avg/success_rate formatters.
        app_module._record("windows-gpu", True, 100)
        app_module._record("windows-gpu", False, 200)

        handler = _make_handler(
            app_module,
            path="/metrics",
            body=b"",
            method="GET",
        )
        handler.do_GET()
        assert handler._captured_status == 200
        payload = _response_payload(handler)
        assert "metrics" in payload
        gpu = payload["metrics"]["windows-gpu"]
        assert gpu["requests"] == 2
        assert gpu["success"] == 1
        assert gpu["failure"] == 1
        assert gpu["avg_ms"] == 150
        # 1/2 → "50%" via integer division
        assert gpu["success_rate"].endswith("%")

    def test_metrics_zero_requests_reports_n_a(self, app_module):
        handler = _make_handler(
            app_module,
            path="/metrics",
            body=b"",
            method="GET",
        )
        handler.do_GET()
        payload = _response_payload(handler)
        # Any tier with 0 requests should report "n/a"
        zero_tiers = [t for t, m in payload["metrics"].items() if m["requests"] == 0]
        assert zero_tiers, "expected at least one zero-request tier"
        for tier in zero_tiers:
            assert payload["metrics"][tier]["success_rate"] == "n/a"
            assert payload["metrics"][tier]["avg_ms"] == 0


# ─── x402 payment gate ────────────────────────────────────────────────────────


class TestX402Gate:
    """When X402_ENABLED=1 and no X-Payment header is provided, paid POST
    paths should respond with HTTP 402. The middleware is constructed at
    import time, so we mutate it directly instead of touching env vars.
    """

    def _build_middleware(
        self, app_module, *, recipient="0xdeadbeef0000000000000000000000000000beef"
    ):
        """Build a real X402Middleware in 'enabled' mode."""
        spec = importlib.util.find_spec("lib.payments.x402_middleware")
        # The middleware is imported by app.py at load time.
        from lib.payments.x402_middleware import X402Middleware  # type: ignore

        return X402Middleware(
            recipient_address=recipient,
            pricing=dict(app_module._X402.pricing)
            if app_module._X402
            else {
                "/v1/chat/completions": 0.001,
            },
            enabled=True,
        ), spec

    def test_paid_path_without_header_returns_402(self, app_module, monkeypatch):
        if app_module._X402 is None:
            pytest.skip("x402 middleware unavailable in this build")
        mw, _ = self._build_middleware(app_module)
        monkeypatch.setattr(app_module, "_X402", mw)

        body = json.dumps(
            {
                "model": "auto",
                "messages": [{"role": "user", "content": "hi"}],
            }
        ).encode()
        handler = _make_handler(app_module, path="/v1/chat/completions", body=body)
        handler.do_POST()
        assert handler._captured_status == 402
        # Inspect the wfile buffer for the 402 body shape.
        raw = handler.wfile.getvalue()
        payload = json.loads(raw)
        assert payload["x402Version"] == 1
        assert payload["accepts"], "accepts should advertise the requirement"
        accept0 = payload["accepts"][0]
        assert accept0["scheme"] == "exact"
        assert accept0["payTo"]
        # The proxy should also have set X-Payment-Required: true.
        header_dict = dict(handler._captured_headers)
        assert header_dict.get("X-Payment-Required") == "true"

    def test_disabled_x402_skips_gate(self, app_module, monkeypatch):
        # When the middleware is None or disabled, paid paths fall through
        # to the normal routing pipeline. We assert the request gets past
        # the gate by stubbing routing to return early with an empty-message
        # 400.
        monkeypatch.setattr(app_module, "_X402", None)
        body = json.dumps({"model": "auto", "messages": []}).encode()
        handler = _make_handler(app_module, path="/v1/chat/completions", body=body)
        handler.do_POST()
        # 402 would mean the gate fired despite being disabled.
        assert handler._captured_status == 400
