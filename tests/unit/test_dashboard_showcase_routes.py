"""Unified dashboard route stays auth-gated, paste-safe, and navigable."""

from __future__ import annotations

import base64
import importlib
import os
import re
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


def test_showcase_page_requires_auth(client):
    response = client.get("/showcase")

    assert response.status_code == 401


def test_showcase_page_renders_with_curated_links(client):
    response = client.get("/showcase", headers=_auth_header())

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Unified Sapphire dashboard" in html
    assert "Walkthrough paths" in html
    assert "Satellite frontends" in html
    assert "&lt;built-in method copy" not in html
    assert "Dashboards consolidate live services" in html
    for route in (
        "/",
        "/production-readiness",
        "/diligence",
        "/sovereign-thesis",
        "/intel",
        "/inference-telemetry",
        "/source-quality",
        "/chain/robinhood",
        "/security/overview",
    ):
        assert f'href="{route}"' in html
    assert 'href="/overview"' not in html
    assert 'href="/platform"' not in html


def test_showcase_page_surfaces_guided_walkthroughs(client):
    response = client.get("/showcase", headers=_auth_header())
    html = response.get_data(as_text=True)

    for path in (
        "Buyer proof path",
        "Operator health path",
        "Satellite demo path",
        "Engineering source path",
    ):
        assert path in html

    for href in (
        "/observability",
        "/inference-telemetry",
        "/logs",
        "/infrastructure",
        "https://github.com/arigatoexpress/Sapphire",
    ):
        assert f'href="{href}"' in html


def test_unified_dashboard_aliases_render_same_surface(client):
    for route in ("/unified", "/unified-dashboard"):
        response = client.get(route, headers=_auth_header())

        assert response.status_code == 200
        assert "Unified Sapphire dashboard" in response.get_data(as_text=True)


def test_showcase_page_surfaces_satellite_repositories(client):
    response = client.get("/showcase", headers=_auth_header())
    html = response.get_data(as_text=True)

    for repo in ("regional-intel-workbench", "Project-Go-Forward", "org-platform"):
        assert repo in html

    for href in (
        "https://github.com/arigatoexpress/Project-Go-Forward",
        "https://github.com/arigatoexpress/regional-intel-workbench",
    ):
        assert f'href="{href}"' in html


def test_showcase_page_links_to_satellite_frontends(client):
    response = client.get("/showcase", headers=_auth_header())
    html = response.get_data(as_text=True)

    for href in (
        "https://sapphirealpha.xyz",
        "https://sapphirealpha.xyz/health",
        "http://127.0.0.1:8768/intel",
        "http://127.0.0.1:8768/blanga/austin",
        "http://127.0.0.1:8768/vote-monitor",
        "http://127.0.0.1:3000",
    ):
        assert f'href="{href}"' in html


def test_showcase_page_surfaces_adjacent_project_coverage(client):
    response = client.get("/showcase", headers=_auth_header())
    html = response.get_data(as_text=True)

    for repo in ("tradingview-mcp", "cyber-threat-bot", "crypto-tax-tracker"):
        assert repo in html

    for href in (
        "https://github.com/arigatoexpress/tradingview-mcp",
        "https://github.com/arigatoexpress/cyber-threat-bot",
        "https://github.com/arigatoexpress/crypto-tax-tracker",
    ):
        assert f'href="{href}"' in html


def test_showcase_route_appears_in_global_nav(client):
    response = client.get("/", headers=_auth_header())
    html = response.get_data(as_text=True)

    assert 'href="/showcase"' in html
    assert ">Unified</a>" in html


def test_showcase_active_nav_state(client):
    response = client.get("/showcase", headers=_auth_header())
    html = response.get_data(as_text=True)

    assert "current_page == 'showcase'" not in html
    assert re.search(r'href="/showcase"[^>]*active', html)


def test_showcase_is_paste_safe(client):
    response = client.get("/showcase", headers=_auth_header())
    html = response.get_data(as_text=True)

    assert "/Users/aribs" not in html
    assert "~/" not in html
    assert "local_path" not in html
    assert "AUTH_PASSWORD" not in html
    assert "MOONSHOT_API_KEY" not in html
    assert "HYPERLIQUID_PRIVATE_KEY" not in html


def test_showcase_does_not_advertise_live_mutation_controls(client):
    response = client.get("/showcase", headers=_auth_header())
    html = response.get_data(as_text=True).lower()

    assert "method: 'post'" not in html
    assert 'method="post"' not in html
    assert "telegram_sends_enabled" not in html
    assert "live_trading_enabled" not in html
    assert "execute_signal" not in html
