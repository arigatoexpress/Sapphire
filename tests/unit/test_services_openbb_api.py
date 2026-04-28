"""Tests for services/openbb_api/server.py — Sapphire's compatibility wrapper
around the OpenBB FastAPI app.

The wrapper registers a single Sapphire-specific endpoint:
    GET /api/v1/openbb/providers

which returns a sorted list of provider names sourced from
``CommandMap.provider_coverage``. Everything else delegates to OpenBB's
upstream ``rest_api.app``. These tests exercise the wrapper's contract
without requiring any live OpenBB providers or network access.

Strategy:
    * Import the server module via a stable spec so it picks up
      OpenBB's ``app`` (already imported by openbb_core's REST module)
      with the Sapphire endpoint attached.
    * Use FastAPI's ``dependency_overrides`` to inject a fake CommandMap
      with a controlled ``provider_coverage`` mapping. The real OpenBB
      auth + provider loading is bypassed — no creds, no network.
    * Drive the endpoint with starlette TestClient.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_PATH = REPO_ROOT / "services" / "openbb_api" / "server.py"


@pytest.fixture
def openbb_server():
    """Load services/openbb_api/server.py freshly and clean up its module entry."""
    module_name = "sapphire_test_openbb_api_server"
    spec = importlib.util.spec_from_file_location(module_name, SERVER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(module_name, None)


@pytest.fixture
def client(openbb_server):
    """TestClient with the Sapphire provider list dependency overrideable."""
    from openbb_core.api.dependency.coverage import get_command_map

    app = openbb_server.app
    app.dependency_overrides.pop(get_command_map, None)
    try:
        yield app, get_command_map, TestClient(app)
    finally:
        app.dependency_overrides.pop(get_command_map, None)


def _fake_command_map(providers: dict[str, Any]) -> SimpleNamespace:
    """Build a minimal stand-in for openbb_core CommandMap with provider_coverage."""
    return SimpleNamespace(provider_coverage=providers)


def test_providers_endpoint_returns_sorted_keys(client):
    app, dep, http = client

    async def _override():
        return _fake_command_map({"yfinance": [], "fmp": [], "alpha_vantage": []})

    app.dependency_overrides[dep] = _override

    response = http.get("/api/v1/openbb/providers")

    assert response.status_code == 200
    body = response.json()
    assert body == ["alpha_vantage", "fmp", "yfinance"]


def test_providers_endpoint_returns_empty_list_when_no_providers(client):
    app, dep, http = client

    async def _override():
        return _fake_command_map({})

    app.dependency_overrides[dep] = _override

    response = http.get("/api/v1/openbb/providers")

    assert response.status_code == 200
    assert response.json() == []


def test_providers_endpoint_only_returns_keys_not_values(client):
    """provider_coverage maps name -> commands; the endpoint must expose only names."""
    app, dep, http = client

    async def _override():
        return _fake_command_map(
            {
                "yfinance": ["/equity/price/quote", "/equity/historical"],
                "fmp": ["/equity/profile"],
            }
        )

    app.dependency_overrides[dep] = _override

    response = http.get("/api/v1/openbb/providers")

    assert response.status_code == 200
    body = response.json()
    assert body == ["fmp", "yfinance"]
    # No leakage of route lists
    assert all(isinstance(item, str) for item in body)
    assert "/equity/price/quote" not in body


def test_providers_endpoint_is_idempotent(client):
    app, dep, http = client

    async def _override():
        return _fake_command_map({"a": [], "b": []})

    app.dependency_overrides[dep] = _override

    first = http.get("/api/v1/openbb/providers").json()
    second = http.get("/api/v1/openbb/providers").json()

    assert first == second == ["a", "b"]


def test_providers_endpoint_alphabetical_with_mixed_case(client):
    """sorted() is case-sensitive; verify shape matches stdlib lexicographic order."""
    app, dep, http = client

    async def _override():
        return _fake_command_map({"Zscore": [], "alpha": [], "Beta": [], "gamma": []})

    app.dependency_overrides[dep] = _override

    response = http.get("/api/v1/openbb/providers")

    assert response.status_code == 200
    # ASCII: uppercase < lowercase
    assert response.json() == ["Beta", "Zscore", "alpha", "gamma"]


def test_providers_endpoint_handles_single_provider(client):
    app, dep, http = client

    async def _override():
        return _fake_command_map({"only_one": []})

    app.dependency_overrides[dep] = _override

    response = http.get("/api/v1/openbb/providers")

    assert response.status_code == 200
    assert response.json() == ["only_one"]


def test_endpoint_registered_on_underlying_openbb_app(openbb_server):
    """The wrapper must attach the route to the upstream openbb_core app instance,
    not a fresh FastAPI() — that's the entire point of the import-and-decorate pattern.
    """
    from openbb_core.api.rest_api import app as upstream_app

    assert openbb_server.app is upstream_app

    paths = {getattr(route, "path", None) for route in openbb_server.app.routes}
    assert "/api/v1/openbb/providers" in paths


def test_module_only_exposes_one_sapphire_endpoint(openbb_server):
    """Sanity guard: nothing besides the providers helper has been added by Sapphire."""
    module_attrs = {
        name
        for name in dir(openbb_server)
        if not name.startswith("_") and callable(getattr(openbb_server, name))
    }
    # Anchor: the only Sapphire-defined callable in the wrapper is list_openbb_providers
    assert "list_openbb_providers" in module_attrs


def test_providers_endpoint_does_not_call_real_command_map(client, monkeypatch):
    """Override must intercept entirely; the real CommandMap constructor must not run."""
    import openbb_core.app.router as openbb_router

    real_constructor = openbb_router.CommandMap.__init__

    def _exploding_init(self, *args, **kwargs):  # noqa: D401
        raise AssertionError(
            "real CommandMap was constructed even though the dependency was overridden"
        )

    monkeypatch.setattr(openbb_router.CommandMap, "__init__", _exploding_init)
    try:
        app, dep, http = client

        async def _override():
            # Restore __init__ momentarily so we can build a real, empty map
            openbb_router.CommandMap.__init__ = real_constructor
            try:
                cm = openbb_router.CommandMap()
            finally:
                openbb_router.CommandMap.__init__ = _exploding_init
            return cm

        app.dependency_overrides[dep] = _override
        response = http.get("/api/v1/openbb/providers")
        assert response.status_code == 200
        # Whatever providers happen to be loaded, the response must be a sorted list of strings.
        body = response.json()
        assert isinstance(body, list)
        assert body == sorted(body)
        assert all(isinstance(p, str) for p in body)
    finally:
        monkeypatch.setattr(openbb_router.CommandMap, "__init__", real_constructor)
