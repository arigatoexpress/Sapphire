"""Dashboard route tests for the v2 Control Plane summary."""

from __future__ import annotations

import base64
import importlib
import os
import sys
from pathlib import Path

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


def test_v2_control_plane_summary_requires_auth() -> None:
    dashboard_app.app.config["TESTING"] = True
    with dashboard_app.app.test_client() as client:
        assert client.get("/api/v2/control-plane/summary").status_code == 401


def test_v2_control_plane_summary_returns_real_x402_card(monkeypatch) -> None:
    dashboard_app.app.config["TESTING"] = True
    dashboard_app._cache.pop("v2_control_plane_summary", None)
    dashboard_app._cache_time.pop("v2_control_plane_summary", None)

    from services.dashboard import control_plane_summary

    monkeypatch.setattr(
        control_plane_summary,
        "_control_plane_health_card",
        lambda now, *, probe_services: {
            "module": "Operations",
            "status": "ok",
            "mode": "live",
            "title": "Control Plane Runtime",
            "value": "local · memory",
            "summary": "stubbed probe",
            "source": {
                "kind": "probe",
                "path_or_url": "http://127.0.0.1:8082/health",
                "generated_at": "2026-05-06T23:59:00Z",
                "age_seconds": 0,
            },
            "actions": [],
        },
    )

    with dashboard_app.app.test_client() as client:
        response = client.get("/api/v2/control-plane/summary", headers=_auth_header())

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["safety"]["live_settlement_allowed"] is False
    assert any(card["title"] == "x402 Product Spine" for card in payload["cards"])
    assert any(card["title"] == "AgentWiki Builder Briefs" for card in payload["cards"])
