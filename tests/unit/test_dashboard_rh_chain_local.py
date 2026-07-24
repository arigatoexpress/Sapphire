"""Dashboard wiring for the local Robinhood Chain stack panels.

Guarantees:
1. The /chain/robinhood page ships the new local-stack markup.
2. The three new /api/chain/robinhood/local-* endpoints return valid JSON,
   require auth, and degrade gracefully when local state files are missing.
3. The local-state summary contract is stable (ok, mode, networks, ai, feed,
   memes, visualizer_url, event_count, updated).
"""

from __future__ import annotations

import base64
import importlib
import json
import os
import sys
from pathlib import Path

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


# ---------------------------------------------------------------------------
# 1. Page scaffold — the template ships with the local-stack panel.
# ---------------------------------------------------------------------------


def test_robinhood_chain_page_renders_local_stack_panel(client):
    response = client.get("/chain/robinhood", headers=_auth_header())
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Local Stack Mission Control" in html
    assert 'id="local-mainnet"' in html
    assert 'id="local-testnet"' in html
    assert 'id="local-feed"' in html
    assert 'id="local-memes"' in html
    assert "open visualizer" in html


# ---------------------------------------------------------------------------
# 2. Endpoint contracts and auth gating.
# ---------------------------------------------------------------------------


def test_local_state_requires_auth(client):
    response = client.get("/api/chain/robinhood/local-state")
    assert response.status_code == 401


def test_local_memes_requires_auth(client):
    response = client.get("/api/chain/robinhood/local-memes")
    assert response.status_code == 401


def test_local_feed_requires_auth(client):
    response = client.get("/api/chain/robinhood/local-feed")
    assert response.status_code == 401


@pytest.fixture
def seeded_rh_state(tmp_path, monkeypatch):
    """Point the loader at a tmp state dir seeded like the local collector.

    RH_CHAIN_STATE_DIR defaults to ``~/ops-state/rh-chain``, which only exists
    on the operator Mac after the collector has run. Reading real $HOME made
    this contract test pass there and fail in CI, on a fresh clone, and in
    cloud containers — the endpoint correctly reports ok=False when there is no
    state to summarize, exactly as this module's docstring promises.
    """
    import lib.chain.rh_chain_local as rh_local

    state_dir = tmp_path / "rh-chain"
    state_dir.mkdir()
    (state_dir / "rh-chain-state.json").write_text(
        json.dumps(
            {
                "updated": 1_780_000_000,
                "networks": {"mainnet": {"head_block": 1234, "gas_gwei": 0.01}},
                "ai": {"status": "idle"},
                "feed": {"connected": True},
            }
        )
    )
    (state_dir / "memes-state.json").write_text(
        json.dumps({"updated": 1_780_000_100, "head_block": 1240, "tokens": [], "tape": []})
    )
    (state_dir / "rh-feed-state.json").write_text(json.dumps({"connected": True}))

    monkeypatch.setattr(rh_local, "RH_CHAIN_STATE_DIR", state_dir)
    # The dashboard memoizes this payload; clear it so the fixture is honoured.
    dashboard_app._cache.pop("rh_chain_local_state", None)
    dashboard_app._cache_time.pop("rh_chain_local_state", None)
    yield state_dir
    dashboard_app._cache.pop("rh_chain_local_state", None)
    dashboard_app._cache_time.pop("rh_chain_local_state", None)


def test_local_state_summary_contract(client, seeded_rh_state):
    response = client.get("/api/chain/robinhood/local-state", headers=_auth_header())
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["mode"] == "local_state_summary"
    assert "visualizer_url" in body
    assert "networks" in body
    assert "ai" in body
    assert "feed" in body
    assert "memes" in body
    assert "event_count" in body
    assert "updated" in body

    # If the live Mac-side state exists, exercise the expected shape.
    networks = body["networks"]
    if networks:
        for name in ("mainnet", "testnet"):
            if name in networks:
                net = networks[name]
                assert "chain_id" in net
                assert "latest_block" in net
                assert "gas_gwei" in net
                assert "rpc_ok" in net

    memes = body["memes"]
    if memes.get("token_count") is not None:
        assert isinstance(memes["token_count"], int)
        assert isinstance(memes["tape_count"], int)


def test_local_memes_returns_memes_state_shape(client):
    response = client.get("/api/chain/robinhood/local-memes", headers=_auth_header())
    assert response.status_code == 200
    body = response.get_json()
    # Empty when files are missing; otherwise the contract keys exist.
    if body:
        assert "updated" in body
        assert "tokens" in body
        assert "tape" in body


def test_local_feed_returns_feed_state_shape(client):
    response = client.get("/api/chain/robinhood/local-feed", headers=_auth_header())
    assert response.status_code == 200
    body = response.get_json()
    if body:
        assert "connected" in body
        assert "updated" in body


# ---------------------------------------------------------------------------
# 3. Graceful degradation when state files are absent.
# ---------------------------------------------------------------------------


def test_local_state_degrades_gracefully_when_state_dir_missing(client, monkeypatch):
    """A missing state dir must not crash the route; ok=False is acceptable."""
    import lib.chain.rh_chain_local as local_module

    monkeypatch.setattr(local_module, "RH_CHAIN_STATE_DIR", Path("/nonexistent-rh-chain-dir"))
    # Clear the in-process cache so the route re-fetches.
    dashboard_app._cache.pop("rh_chain_local_state", None)
    dashboard_app._cache_time.pop("rh_chain_local_state", None)

    response = client.get("/api/chain/robinhood/local-state", headers=_auth_header())
    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is False
    assert body["mode"] == "local_state_summary"
    assert body["networks"] == {}
