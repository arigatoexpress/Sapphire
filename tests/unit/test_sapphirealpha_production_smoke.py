from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "sapphirealpha_production_smoke.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("sapphirealpha_production_smoke", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sapphirealpha_production_smoke"] = module
    spec.loader.exec_module(module)
    return module


class _FakeHeaders(dict):
    def get(self, key: str, default: Any = None) -> Any:
        return super().get(key.lower(), default)


class _FakeResponse:
    def __init__(self, body: bytes, *, content_type: str = "application/json", status: int = 200):
        self._body = body
        self.status = status
        self.headers = _FakeHeaders({"content-type": content_type})

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        return self._body


def test_smoke_fails_when_api_route_returns_static_html(monkeypatch):
    module = _load_module()

    def fake_urlopen(request, timeout, **_kwargs):
        url = request.full_url
        if "/api/" in url or url.endswith("/health"):
            return _FakeResponse(
                b"<!doctype html><html><body><div id='root'></div></body></html>",
                content_type="text/html",
            )
        return _FakeResponse(b"<html>Sapphire OS</html>", content_type="text/html")

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    report = module.run_smoke("https://sapphirealpha.xyz", 0.1)

    assert report["ok"] is False
    assert report["failed"] >= 1
    failures = [probe for probe in report["probes"] if probe["status"] == "FAIL"]
    assert any("static SPA fallback" in probe["evidence"] for probe in failures)


def test_smoke_passes_for_control_plane_backend_shapes(monkeypatch):
    module = _load_module()

    def fake_urlopen(request, timeout, **_kwargs):
        url = request.full_url
        if url.endswith("/api/projects"):
            return _FakeResponse(json.dumps({"projects": []}).encode())
        if "/api/" in url or url.endswith("/health"):
            return _FakeResponse(b'{"ok": true}')
        return _FakeResponse(b"<html>Sapphire OS</html>", content_type="text/html")

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    report = module.run_smoke("https://sapphirealpha.xyz", 0.1)

    assert report["ok"] is True
    assert report["failed"] == 0
    assert report["passed"] == len(module.PROBES)
