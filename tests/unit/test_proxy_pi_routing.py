"""Tests for inference-proxy Pi routing and health probing."""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "services" / "inference-proxy"))
import app as proxy_app  # type: ignore


@dataclass
class FakePiState:
    """Mutable request/response state for the fake Pi server."""

    behaviors: deque[dict[str, Any]] = field(default_factory=deque)
    requests: list[dict[str, Any]] = field(default_factory=list)


class FakePiHTTPServer(ThreadingMixIn, HTTPServer):
    """Threaded HTTP server carrying shared fake Pi state."""

    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], state: FakePiState) -> None:
        self.state = state
        super().__init__(server_address, FakePiHandler)


class FakeProxyHTTPServer(ThreadingMixIn, HTTPServer):
    """Threaded HTTP server running the real proxy handler."""

    daemon_threads = True


class FakePiHandler(BaseHTTPRequestHandler):
    """Serve minimal Ollama-compatible Pi endpoints for tests."""

    def do_GET(self) -> None:
        self.server.state.requests.append(
            {
                "method": "GET",
                "path": self.path,
                "headers": dict(self.headers.items()),
            }
        )
        if self.path != "/api/tags":
            self.send_error(404)
            return

        body = json.dumps({"models": [{"name": "qwen2.5:0.5b"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)
        try:
            payload = json.loads(raw_body.decode())
        except json.JSONDecodeError:
            payload = {"_raw": raw_body.decode("utf-8", "replace")}

        self.server.state.requests.append(
            {
                "method": "POST",
                "path": self.path,
                "headers": dict(self.headers.items()),
                "body": payload,
            }
        )

        behavior = self.server.state.behaviors.popleft() if self.server.state.behaviors else {}
        delay = float(behavior.get("delay", 0.0) or 0.0)
        if delay > 0:
            time.sleep(delay)

        status = int(behavior.get("status", 200))
        if status >= 400:
            self.send_error(status)
            return

        model = str(payload.get("model") or "")
        body = json.dumps(
            {
                "model": model,
                "message": {"role": "assistant", "content": f"served:{model}"},
                "prompt_eval_count": 3,
                "eval_count": 5,
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress noisy per-request logging in tests."""


@dataclass
class FakePiFixture:
    """Handle to a running fake Pi server."""

    server: FakePiHTTPServer
    thread: threading.Thread
    state: FakePiState

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    @property
    def requests(self) -> list[dict[str, Any]]:
        return self.state.requests


def _start_fake_pi(*behaviors: dict[str, Any]) -> FakePiFixture:
    """Start a fake Pi HTTP server with queued POST behaviors."""
    state = FakePiState(behaviors=deque(behaviors))
    server = FakePiHTTPServer(("127.0.0.1", 0), state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return FakePiFixture(server=server, thread=thread, state=state)


def _start_proxy() -> tuple[FakeProxyHTTPServer, threading.Thread, str]:
    """Start the proxy handler on an ephemeral localhost port."""
    server = FakeProxyHTTPServer(("127.0.0.1", 0), proxy_app.ProxyHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, f"http://{host}:{port}"


@pytest.fixture
def fake_pi() -> FakePiFixture:
    """Yield a healthy fake Pi server."""
    fixture = _start_fake_pi()
    try:
        yield fixture
    finally:
        fixture.server.shutdown()
        fixture.server.server_close()
        fixture.thread.join(timeout=2.0)


def test_probe_endpoint_hits_api_tags(fake_pi: FakePiFixture) -> None:
    proxy_app._endpoint_health["pi-rari1"] = False

    ok = proxy_app._probe_endpoint("pi-rari1", fake_pi.base_url)

    assert ok is True
    assert proxy_app._endpoint_health["pi-rari1"] is True
    assert fake_pi.requests == [
        {
            "method": "GET",
            "path": "/api/tags",
            "headers": fake_pi.requests[0]["headers"],
        }
    ]
    assert fake_pi.requests[0]["headers"]["Accept"] == "application/json"


def test_probe_endpoint_marks_unreachable_targets_failed() -> None:
    proxy_app._endpoint_health["pi-rari1"] = True

    ok = proxy_app._probe_endpoint(
        "pi-rari1",
        "http://127.0.0.1:1",
        timeout=0.05,
        mark_failure=True,
    )

    assert ok is False
    assert proxy_app._endpoint_health["pi-rari1"] is False


def test_pi_rari1_serves_fast_requests_via_safe_model(
    fake_pi: FakePiFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(proxy_app, "PI_RARI1_ENABLED", True)
    monkeypatch.setattr(proxy_app, "PI_RARI2_ENABLED", False)
    monkeypatch.setattr(proxy_app, "PI_ENABLED", True)
    monkeypatch.setattr(proxy_app, "PI_RARI1", fake_pi.base_url)
    proxy_app._endpoint_health["pi-rari1"] = True

    tier, response, tried = proxy_app._try_pi_tier(
        "nemotron-mini:latest",
        [{"role": "user", "content": "hello"}],
        32,
        0.2,
        timeout=1,
    )

    assert tier == "pi-rari1"
    assert tried == ["pi-rari1"]
    assert response is not None
    assert response["model"] == f"{proxy_app.PI_DEFAULT_MODEL} (pi-rari1)"
    assert fake_pi.requests[0]["path"] == "/api/chat"
    assert fake_pi.requests[0]["body"]["model"] == proxy_app.PI_DEFAULT_MODEL


def test_pi_routing_falls_back_to_rari2_when_rari1_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rari1 = _start_fake_pi({"status": 500})
    rari2 = _start_fake_pi()
    try:
        monkeypatch.setattr(proxy_app, "PI_RARI1_ENABLED", True)
        monkeypatch.setattr(proxy_app, "PI_RARI2_ENABLED", True)
        monkeypatch.setattr(proxy_app, "PI_ENABLED", True)
        monkeypatch.setattr(proxy_app, "PI_RARI1", rari1.base_url)
        monkeypatch.setattr(proxy_app, "PI_RARI2", rari2.base_url)
        proxy_app._endpoint_health["pi-rari1"] = True
        proxy_app._endpoint_health["pi-rari2"] = True

        tier, response, tried = proxy_app._try_pi_tier(
            "nemotron-mini:latest",
            [{"role": "user", "content": "fallback"}],
            32,
            0.2,
            timeout=1,
        )

        assert tier == "pi-rari2"
        assert tried == ["pi-rari1", "pi-rari2"]
        assert response is not None
        assert response["model"] == f"{proxy_app.PI_DEFAULT_MODEL} (pi-rari2)"
        rari1_posts = [req for req in rari1.requests if req["method"] == "POST"]
        rari2_posts = [req for req in rari2.requests if req["method"] == "POST"]
        assert rari1_posts[0]["body"]["model"] == proxy_app.PI_DEFAULT_MODEL
        assert rari2_posts[0]["body"]["model"] == proxy_app.PI_DEFAULT_MODEL
    finally:
        for fixture in (rari1, rari2):
            fixture.server.shutdown()
            fixture.server.server_close()
            fixture.thread.join(timeout=2.0)


def test_default_qwen_routes_match_verified_windows_inventory() -> None:
    """Default Qwen routes should use models actually installed on Windows."""
    assert proxy_app.MODEL_TIERS["deep"] == "qwen3:14b"
    assert proxy_app.MODEL_TIERS["qwen-reason"] == "qwen3.5:9b"
    assert proxy_app.MODEL_TIERS["fast-reason"] == "qwen3.5:9b"
    assert "qwen3:14b" in proxy_app.GPU_ONLY_MODELS
    assert "qwen3.5:9b" in proxy_app.GPU_ONLY_MODELS


def test_qwen36_alias_can_fall_back_to_exact_mac_model() -> None:
    """qwen3.6 is Mac-installed, so explicit alias must not force a 503."""
    assert proxy_app.MODEL_TIERS["qwen3.6"] == "qwen3.6:27b"
    assert "qwen3.6:27b" in proxy_app.MAC_MODELS
    assert "qwen3.6:27b" in proxy_app.MAC_EXACT_FALLBACK_MODELS
    assert "qwen3.6:27b" not in proxy_app.GPU_ONLY_MODELS


def test_qwen36_alias_skips_pi_substitution_for_exact_mac_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows miss should fall through to exact Mac qwen3.6, not a Pi tiny model."""
    monkeypatch.setattr(proxy_app, "PI_RARI1_ENABLED", True)
    monkeypatch.setattr(proxy_app, "PI_RARI2_ENABLED", False)
    monkeypatch.setattr(proxy_app, "PI_ENABLED", True)
    monkeypatch.setitem(proxy_app._endpoint_health, "windows-gpu", True)
    monkeypatch.setitem(proxy_app._endpoint_health, "mac-local", True)
    monkeypatch.setattr(proxy_app, "_should_preflight", lambda *args, **kwargs: False)

    def fake_ollama_native(
        endpoint_name: str,
        base_url: str,
        model: str,
        messages: list,
        max_tokens: int,
        temperature: float,
        timeout: int = 60,
    ) -> dict | None:
        assert endpoint_name == "windows-gpu"
        assert model == "qwen3.6:27b"
        return None

    def fake_mac_local(path: str, body: bytes, model: str = "") -> tuple[int, bytes]:
        payload = json.loads(body.decode())
        assert path == "/v1/chat/completions"
        assert model == "qwen3.6:27b"
        assert payload["model"] == "qwen3.6:27b"
        return 200, json.dumps({"model": payload["model"], "choices": []}).encode()

    def fail_pi_tier(*args: Any, **kwargs: Any) -> tuple[str | None, dict | None, list[str]]:
        pytest.fail("Pi tier should be skipped for qwen3.6 exact Mac fallback")

    monkeypatch.setattr(proxy_app, "_try_ollama_native", fake_ollama_native)
    monkeypatch.setattr(proxy_app, "_try_mac_local", fake_mac_local)
    monkeypatch.setattr(proxy_app, "_try_pi_tier", fail_pi_tier)

    server, thread, base_url = _start_proxy()
    try:
        req = urllib.request.Request(
            f"{base_url}/v1/chat/completions",
            data=json.dumps(
                {
                    "model": "qwen3.6",
                    "messages": [{"role": "user", "content": "summarize route"}],
                    "max_tokens": 16,
                    "temperature": 0.1,
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=2) as response:
            payload = json.loads(response.read().decode())

        assert response.status == 200
        assert response.headers["X-Inference-Tier"] == "mac-local"
        assert payload["model"] == "qwen3.6:27b"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
