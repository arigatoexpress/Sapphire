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


def _healthy_json_for(url: str) -> bytes | None:
    """Return a well-shaped body for each live JSON probe, or None if not a JSON route."""
    bodies: dict[str, dict[str, Any]] = {
        "/api/health": {
            "status": "ok",
            "service": "sapphire-alpha-dashboard",
            "version": "0.2.0",
        },
        "/api/v1/status": {"service": "sapphire-alpha-dashboard", "version": "0.2.0", "gate": {}},
        "/api/v1/live": {"version": 1, "summary": {"state": "ok"}},
        "/api/v1/transparency": {"records": [], "counts": {}},
        "/api/v1/widgets": {"gate": {}},
        "/api/fleet": {"public_view": True},
    }
    for path, payload in bodies.items():
        if url.endswith(path):
            return json.dumps(payload).encode()
    return None


def test_smoke_fails_when_api_route_returns_static_html(monkeypatch):
    """The catchall route serves index.html at HTTP 200 for unmatched paths.

    That is the exact regression this smoke exists to catch: a dropped API
    route looks 'healthy' to any status-code-only monitor.
    """
    module = _load_module()

    def fake_urlopen(request, timeout, **_kwargs):
        url = request.full_url
        if "/api/" in url:
            return _FakeResponse(
                b"<!doctype html><html><body><div id='root'></div></body></html>",
                content_type="text/html",
            )
        return _FakeResponse(b"<html>SAPPHIRE ALPHA</html>", content_type="text/html")

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    report = module.run_smoke("https://sapphirealpha.xyz", 0.1)

    assert report["ok"] is False
    assert report["failed"] >= 1
    failures = [probe for probe in report["probes"] if probe["status"] == "FAIL"]
    assert any("static SPA fallback" in probe["evidence"] for probe in failures)


def test_smoke_fails_with_crisp_route_owner_mismatch(monkeypatch):
    module = _load_module()

    def fake_urlopen(request, timeout, **_kwargs):
        url = request.full_url
        if url.endswith("/api/health"):
            # Healthy JSON, correct shape - but the wrong Cloud Run service.
            return _FakeResponse(
                json.dumps(
                    {
                        "status": "ok",
                        "service": "agent-opportunity-exchange",
                        "version": "1.0.0",
                    }
                ).encode()
            )
        if (body := _healthy_json_for(url)) is not None:
            return _FakeResponse(body)
        return _FakeResponse(
            b"<html>SAPPHIRE ALPHA Sapphire Command</html>", content_type="text/html"
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    report = module.run_smoke("https://sapphirealpha.xyz", 0.1)

    health_probe = next(probe for probe in report["probes"] if probe["name"] == "health_json")
    assert report["ok"] is False
    assert health_probe["status"] == "FAIL"
    assert "route owner mismatch" in health_probe["evidence"]
    assert "agent-opportunity-exchange" in health_probe["evidence"]


def test_smoke_passes_for_alpha_dashboard_backend_shapes(monkeypatch):
    module = _load_module()

    def fake_urlopen(request, timeout, **_kwargs):
        url = request.full_url
        if (body := _healthy_json_for(url)) is not None:
            return _FakeResponse(body)
        return _FakeResponse(
            b"<html>SAPPHIRE ALPHA Sapphire Command</html>", content_type="text/html"
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", fake_urlopen)

    report = module.run_smoke("https://sapphirealpha.xyz", 0.1)

    assert report["ok"] is True
    assert report["failed"] == 0
    assert report["passed"] == len(module.PROBES)


def test_smoke_probes_avoid_healthz_which_gfe_intercepts(monkeypatch):
    """/healthz always 404s on Cloud Run - GFE reserves it. Never probe it."""
    module = _load_module()
    assert all(probe.path != "/healthz" for probe in module.PROBES)
