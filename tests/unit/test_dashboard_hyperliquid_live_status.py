"""/api/hyperliquid/live-status reuses the plugin tool helper safely.

The endpoint dynamically imports plugins/claw-sapphire/tools/internal/
hyperliquid.py at request time (the helper ``_live_status_payload`` is added by
PRs #443/#444/#453). These tests verify the endpoint:
  * passes through the helper's payload + ``?limit=`` query param,
  * fails closed with HTTP 503 if the helper is unavailable.

The mocking strategy intercepts ``importlib.util.spec_from_file_location`` so
we don't need the real plugin tool to be present on the branch under test.
"""

from __future__ import annotations

import base64
import importlib
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["AUTH_PASSWORD"] = os.environ.get("AUTH_PASSWORD") or "test-password"
os.environ["X402_ENABLED"] = "0"

dashboard_app = importlib.import_module("services.dashboard.app")


def _auth_header() -> dict[str, str]:
    creds = base64.b64encode(
        f"{dashboard_app.AUTH_USERNAME}:{dashboard_app.AUTH_PASSWORD}".encode()
    ).decode("ascii")
    return {"Authorization": f"Basic {creds}"}


@pytest.fixture
def client():
    dashboard_app.app.config["TESTING"] = True
    with dashboard_app.app.test_client() as test_client:
        yield test_client


def _stub_module_factory(payload_fn):
    """Build the fake spec/module pair the endpoint will use."""

    def fake_spec_from_file_location(name, _path):
        loader = types.SimpleNamespace(
            exec_module=lambda module: setattr(module, "_live_status_payload", payload_fn),
        )
        return types.SimpleNamespace(name=name, loader=loader)

    def fake_module_from_spec(spec):
        module = types.ModuleType(spec.name)
        module.__loader__ = spec.loader
        return module

    return fake_spec_from_file_location, fake_module_from_spec


def test_live_status_returns_helper_payload(client):
    sample = {
        "ok": True,
        "killswitch_active": False,
        "trading_enabled": False,
        "testnet": True,
        "recent_trades": [],
        "daily_pnl": {"realized_loss_usd": 0.0},
        "policy": {"max_daily_loss_usd": 50.0},
    }
    captured: dict[str, int] = {}

    def helper(limit):
        captured["limit"] = limit
        return sample

    spec_fn, mod_fn = _stub_module_factory(helper)
    with (
        patch("importlib.util.spec_from_file_location", side_effect=spec_fn),
        patch("importlib.util.module_from_spec", side_effect=mod_fn),
    ):
        response = client.get("/api/hyperliquid/live-status", headers=_auth_header())

    assert response.status_code == 200
    assert response.get_json() == sample
    assert captured["limit"] == 5  # default


def test_live_status_passes_through_limit_query(client):
    captured: dict[str, int] = {}

    def helper(limit):
        captured["limit"] = limit
        return {"ok": True, "limit_echo": limit}

    spec_fn, mod_fn = _stub_module_factory(helper)
    with (
        patch("importlib.util.spec_from_file_location", side_effect=spec_fn),
        patch("importlib.util.module_from_spec", side_effect=mod_fn),
    ):
        response = client.get("/api/hyperliquid/live-status?limit=10", headers=_auth_header())

    assert response.status_code == 200
    assert captured["limit"] == 10


def test_live_status_clamps_limit_to_bounds(client):
    captured: list[int] = []

    def helper(limit):
        captured.append(limit)
        return {"ok": True}

    spec_fn, mod_fn = _stub_module_factory(helper)
    with (
        patch("importlib.util.spec_from_file_location", side_effect=spec_fn),
        patch("importlib.util.module_from_spec", side_effect=mod_fn),
    ):
        client.get("/api/hyperliquid/live-status?limit=0", headers=_auth_header())
        client.get("/api/hyperliquid/live-status?limit=999", headers=_auth_header())
        client.get("/api/hyperliquid/live-status?limit=garbage", headers=_auth_header())

    # 0 → clamped up to 1; 999 → clamped down to 50; garbage → default 5.
    assert captured == [1, 50, 5]


def test_live_status_returns_503_when_helper_raises_import_error(client):
    def boom(_limit):
        raise ImportError("simulated missing helper")

    spec_fn, mod_fn = _stub_module_factory(boom)
    with (
        patch("importlib.util.spec_from_file_location", side_effect=spec_fn),
        patch("importlib.util.module_from_spec", side_effect=mod_fn),
    ):
        response = client.get("/api/hyperliquid/live-status", headers=_auth_header())

    assert response.status_code == 503
    body = response.get_json()
    assert body["error"] == "live-status unavailable"
    assert "simulated missing helper" in body["reason"]


def test_live_status_returns_503_when_helper_missing(client):
    """Helper-not-exported branch (older plugin tool, no _live_status_payload)."""

    def fake_spec(name, _path):
        loader = types.SimpleNamespace(exec_module=lambda module: None)
        return types.SimpleNamespace(name=name, loader=loader)

    def fake_module(spec):
        module = types.ModuleType(spec.name)
        return module

    with (
        patch("importlib.util.spec_from_file_location", side_effect=fake_spec),
        patch("importlib.util.module_from_spec", side_effect=fake_module),
    ):
        response = client.get("/api/hyperliquid/live-status", headers=_auth_header())

    assert response.status_code == 503
    body = response.get_json()
    assert body["error"] == "live-status unavailable"
    assert "_live_status_payload" in body["reason"]


def test_live_status_requires_auth(client):
    response = client.get("/api/hyperliquid/live-status")
    assert response.status_code == 401
