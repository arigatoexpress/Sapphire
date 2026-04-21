"""Tests for inference-proxy Pi routing and health probing."""

from __future__ import annotations

import json
import sys
import threading
import time
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

    proxy_app._probe_endpoint("pi-rari1", fake_pi.base_url)

    assert proxy_app._endpoint_health["pi-rari1"] is True
    assert fake_pi.requests == [
        {
            "method": "GET",
            "path": "/api/tags",
            "headers": fake_pi.requests[0]["headers"],
        }
    ]
    assert fake_pi.requests[0]["headers"]["Accept"] == "application/json"


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
        assert rari1.requests[0]["body"]["model"] == proxy_app.PI_DEFAULT_MODEL
        assert rari2.requests[0]["body"]["model"] == proxy_app.PI_DEFAULT_MODEL
    finally:
        for fixture in (rari1, rari2):
            fixture.server.shutdown()
            fixture.server.server_close()
            fixture.thread.join(timeout=2.0)
