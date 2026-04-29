"""Dashboard inference-telemetry routes stay auth-gated, read-only, paste-safe."""

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


def test_inference_telemetry_page_requires_auth(client):
    response = client.get("/inference-telemetry")
    assert response.status_code == 401


def test_inference_telemetry_page_renders(client):
    response = client.get("/inference-telemetry", headers=_auth_header())
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Inference Mesh Telemetry" in html
    assert "/api/inference-telemetry-report" in html
    assert "/api/inference-telemetry-recommendations" in html


def test_inference_telemetry_report_endpoint_returns_json(client):
    response = client.get(
        "/api/inference-telemetry-report",
        headers=_auth_header(),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload is not None
    assert payload.get("ok") is True
    assert "tiers" in payload
    assert "schema_version" in payload
    # Synthetic fixture path is honest about not being real data.
    assert isinstance(payload.get("has_real_data"), bool)


def test_inference_telemetry_report_includes_cost_projection(client):
    response = client.get(
        "/api/inference-telemetry-report",
        headers=_auth_header(),
    )
    payload = response.get_json()
    assert "projected_monthly_cost_usd" in payload
    assert "projected_monthly_calls" in payload
    assert "cost_model_citations" in payload
    citations = payload.get("cost_model_citations", [])
    assert any("moonshot.cn" in c for c in citations)


def test_inference_telemetry_recommendations_endpoint(client):
    response = client.get(
        "/api/inference-telemetry-recommendations",
        headers=_auth_header(),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload is not None
    assert "recommendations" in payload
    assert "caveats" in payload
    # Default model has unsupplied Kimi rates → caveat must be present.
    assert any("Kimi" in c for c in payload.get("caveats", []))


def test_inference_telemetry_cost_model_endpoint(client):
    response = client.get(
        "/api/inference-telemetry-cost-model",
        headers=_auth_header(),
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload.get("ok") is True
    cm = payload.get("cost_model") or {}
    assert "moonshot_pricing_url" in cm
    assert cm.get("kimi_rates_supplied") is False  # default model


def test_inference_telemetry_paste_safe_no_local_paths(client):
    """No /Users/<name> absolute paths bleed into the rendered HTML."""
    response = client.get("/inference-telemetry", headers=_auth_header())
    html = response.get_data(as_text=True)
    assert "/Users/aribs" not in html
    assert "AUTH_PASSWORD" not in html


def test_inference_telemetry_route_appears_in_nav(client):
    """Page is reachable from the global nav."""
    response = client.get("/", headers=_auth_header())
    html = response.get_data(as_text=True)
    assert "/inference-telemetry" in html
