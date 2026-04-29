"""Dashboard routes for the Houston lead pipeline stay auth-gated and bounded."""

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


@pytest.fixture
def sample_leads():
    return [
        {
            "id": "311:1",
            "source": "311",
            "address": "1 Foundation St, Houston, TX 77002",
            "zip": "77002",
            "type": "Foundation Concern",
            "description": "foundation cracks",
            "score": 94,
            "score_reason": "Foundation repair",
            "urgency": "high",
            "lat": 29.76,
            "lng": -95.36,
            "raw_data": {"secret_shape": "api_key=not-rendered"},
        },
        {
            "id": "permit:2",
            "source": "permit",
            "address": "<script>alert(1)</script>",
            "zip": "77003",
            "type": "Commercial sign",
            "description": "signage",
            "score": 20,
            "urgency": "low",
            "raw_data": {"internal": "kept out of map properties"},
        },
    ]


def test_leads_page_requires_auth(client):
    response = client.get("/intel/leads")

    assert response.status_code == 401


def test_leads_page_renders_authenticated_shell(client):
    response = client.get("/intel/leads", headers=_auth_header())

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Home Leads" in html
    assert "/api/leads" in html


def test_leads_api_filters_and_paginates(client, monkeypatch, sample_leads):
    from lib.intel import houston_leads

    monkeypatch.setattr(houston_leads, "load_leads", lambda: sample_leads)

    response = client.get(
        "/api/leads?score_min=80&source=311&zip=77002&urgency=high",
        headers=_auth_header(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 1
    assert payload["leads"][0]["id"] == "311:1"


def test_leads_map_omits_raw_data_and_unmapped_rows(client, monkeypatch, sample_leads):
    from lib.intel import houston_leads

    monkeypatch.setattr(houston_leads, "load_leads", lambda: sample_leads)

    response = client.get("/api/leads/map", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["type"] == "FeatureCollection"
    assert len(payload["features"]) == 1
    feature = payload["features"][0]
    assert feature["geometry"]["coordinates"] == [-95.36, 29.76]
    assert "raw_data" not in feature["properties"]


def test_leads_score_api_uses_injected_limit(client, monkeypatch):
    from lib.intel import lead_scorer

    calls: list[int | None] = []

    def fake_score_unscored(*, limit=None):
        calls.append(limit)
        return 3

    monkeypatch.setattr(lead_scorer, "score_unscored", fake_score_unscored)

    response = client.post("/api/leads/score", json={"limit": 5}, headers=_auth_header())

    assert response.status_code == 200
    assert response.get_json() == {"scored": 3}
    assert calls == [5]
