"""Unit tests for GrokBridgeClient — no network."""

from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from typing import Any

import pytest

from lib.intel.grok_bridge_client import BridgeChatResult, GrokBridgeClient


class _Resp:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_app_path_style_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GROK_BRIDGE_URL", raising=False)
    monkeypatch.delenv("GROK_BRIDGE_APP_URL", raising=False)
    c = GrokBridgeClient(base_url="http://127.0.0.1:8080")
    assert c.path_style == "app"
    assert c._path("health").endswith("/api/bridge/health")


def test_classic_path_for_19998() -> None:
    c = GrokBridgeClient(base_url="http://127.0.0.1:19998")
    assert c.path_style == "classic"
    assert c._path("chat") == "http://127.0.0.1:19998/chat"


def test_chat_parses_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req: object, timeout: float = 0):  # noqa: ANN001
        return _Resp(
            {
                "ok": True,
                "response": "bridge-pong",
                "latencyMs": 12,
                "mode": "supergrok-oidc",
            }
        )

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    c = GrokBridgeClient(base_url="http://example.test:8080")
    r = c.chat("ping")
    assert isinstance(r, BridgeChatResult)
    assert r.ok
    assert r.response == "bridge-pong"
    assert r.mode == "supergrok-oidc"
    assert r.latency_ms == 12


def test_chat_empty_prompt_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req: object, timeout: float = 0):  # noqa: ANN001
        return _Resp({"ok": False, "error": "prompt is required", "code": "empty_prompt"})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    c = GrokBridgeClient(base_url="http://example.test:8080")
    r = c.chat("   ")
    assert not r.ok
    assert r.error


def test_health(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(req: object, timeout: float = 0):  # noqa: ANN001
        return _Resp({"ok": True, "mode": "supergrok-oidc", "status": "ready"})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    c = GrokBridgeClient(base_url="http://example.test:8080")
    h = c.health()
    assert h["ok"] is True
    assert h["mode"] == "supergrok-oidc"
