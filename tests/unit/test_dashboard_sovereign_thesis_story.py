"""Flask-client coverage for the sovereign-thesis story dashboard page."""

from __future__ import annotations

import base64
import importlib
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


def test_sovereign_thesis_story_requires_auth(client):
    response = client.get("/sovereign-thesis/story")

    assert response.status_code == 401


def test_sovereign_thesis_story_renders_all_story_sections(client):
    response = client.get("/sovereign-thesis/story", headers=_auth_header())

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    for section in ("Thesis", "Evidence", "Convergence", "Bear case", "Acquirer fit"):
        assert section in html


def test_sovereign_thesis_story_uses_dashboard_base_chrome(client):
    response = client.get("/sovereign-thesis/story", headers=_auth_header())

    html = response.get_data(as_text=True)
    assert "Sapphire_OS" in html
    assert "terminal-nav" in html
    assert "Sovereign Thesis Story" in html


def test_sovereign_thesis_story_fetches_existing_thesis_api_only(client):
    response = client.get("/sovereign-thesis/story", headers=_auth_header())

    html = response.get_data(as_text=True)
    assert "window.location.origin}/api/investments/thesis" in html
    assert "/api/trading/order-draft" not in html
    assert "/api/launchagent-summary" not in html


def test_sovereign_thesis_story_has_client_side_escaping(client):
    response = client.get("/sovereign-thesis/story", headers=_auth_header())

    html = response.get_data(as_text=True)
    assert "function esc(value)" in html
    assert "replace(/[&<>\"']/g" in html
    assert "innerHTML" in html


def test_sovereign_thesis_story_does_not_declare_post_or_live_sends(client):
    response = client.get("/sovereign-thesis/story", headers=_auth_header())

    html = response.get_data(as_text=True).lower()
    assert "method: 'post'" not in html
    assert 'method: "post"' not in html
    assert "telegram_sends_enabled: true" not in html
    assert "live_trading_enabled: true" not in html


def test_existing_sovereign_thesis_matrix_route_still_renders(client):
    response = client.get("/sovereign-thesis", headers=_auth_header())

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Asset Matrix" in html
    assert "/api/investments/thesis" in html


def test_sovereign_thesis_story_route_is_get_only():
    rules = [rule for rule in dashboard_app.app.url_map.iter_rules() if rule.rule == "/sovereign-thesis/story"]

    assert len(rules) == 1
    assert "GET" in rules[0].methods
    assert not ({"POST", "PUT", "PATCH", "DELETE"} & rules[0].methods)
