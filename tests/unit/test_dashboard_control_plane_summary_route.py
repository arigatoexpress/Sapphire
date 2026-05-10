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


def test_v2_control_plane_summary_matches_react_workbench_contract(monkeypatch) -> None:
    dashboard_app.app.config["TESTING"] = True
    dashboard_app._cache.pop("v2_control_plane_summary", None)
    dashboard_app._cache_time.pop("v2_control_plane_summary", None)

    from services.dashboard import control_plane_summary

    monkeypatch.setattr(
        control_plane_summary,
        "_control_plane_health_card",
        lambda now, *, probe_services: {
            "module": "Operations",
            "status": "unknown",
            "mode": "blocked",
            "title": "Control Plane Runtime",
            "value": "not probed",
            "summary": "stubbed probe",
            "source": {
                "kind": "probe",
                "path_or_url": "http://127.0.0.1:8082/health",
                "generated_at": "2026-05-06T23:59:00Z",
                "age_seconds": 0,
            },
            "actions": [
                {
                    "label": "Wire read-only adapters",
                    "mode": "dry_run",
                    "requires_confirm": False,
                }
            ],
        },
    )

    with dashboard_app.app.test_client() as client:
        response = client.get("/api/v2/control-plane/summary", headers=_auth_header())

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["schema_version"] == 1
    assert payload["mode"] == "read_only"
    assert payload["summary"]["card_count"] == len(payload["cards"])
    assert payload["safety"] == {
        "live_settlement_allowed": False,
        "production_mutation_enabled": False,
        "real_trading_enabled": False,
        "telegram_sends_enabled": False,
    }
    assert {module["name"] for module in payload["modules"]} >= {
        "Home / Worldline",
        "Operations",
        "Intelligence",
        "Markets",
        "Security",
        "Products / Diligence",
        "Automation",
        "Settings / Contracts",
    }

    for card in payload["cards"]:
        assert card["module"]
        assert card["status"] in {"ok", "warn", "fail", "unknown"}
        assert card["mode"] in {"live", "read_only", "paper", "modeled", "stale", "blocked"}
        assert card["source"]["path_or_url"]
        for action in card["actions"]:
            assert action["mode"] in {"dry_run", "read_only", "blocked"}
            assert isinstance(action["requires_confirm"], bool)


def test_app_preview_requires_auth_and_serves_built_bundle(monkeypatch, tmp_path) -> None:
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (dist / "index.html").write_text(
        '<html><head><script type="module" src="/app-preview/assets/app.js"></script></head>'
        "<body><div id='root'></div></body></html>",
        encoding="utf-8",
    )
    (assets / "app.js").write_text("console.log('preview');\n", encoding="utf-8")
    monkeypatch.setattr(dashboard_app, "_FRONTEND_DIST_DIR", dist)

    dashboard_app.app.config["TESTING"] = True
    with dashboard_app.app.test_client() as client:
        unauthenticated = client.get("/app-preview")
        page = client.get("/app-preview", headers=_auth_header())
        asset = client.get("/app-preview/assets/app.js", headers=_auth_header())

    assert unauthenticated.status_code == 401
    assert page.status_code == 200
    assert "id='root'" in page.get_data(as_text=True)
    assert asset.status_code == 200
    assert asset.get_data(as_text=True) == "console.log('preview');\n"


def test_app_preview_reports_blocked_when_bundle_is_missing(monkeypatch, tmp_path) -> None:
    missing_dist = tmp_path / "missing-dist"
    monkeypatch.setattr(dashboard_app, "_FRONTEND_DIST_DIR", Path(missing_dist))

    dashboard_app.app.config["TESTING"] = True
    with dashboard_app.app.test_client() as client:
        response = client.get("/app-preview", headers=_auth_header())

    payload = response.get_json()
    assert response.status_code == 503
    assert payload["mode"] == "blocked"
    assert payload["source"]["path_or_url"] == "services/dashboard/frontend/dist/index.html"
    assert payload["actions"][0]["mode"] == "dry_run"
