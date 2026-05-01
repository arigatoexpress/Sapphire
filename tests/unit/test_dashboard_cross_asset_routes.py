"""Dashboard cross-asset routes are auth-gated and cache-first."""

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


def _sample_snapshot() -> dict:
    return {
        "ok": True,
        "mode": "cache_or_dry_run",
        "generated_at": "2026-04-28T12:00:00+00:00",
        "matrix": {
            "windows": {
                "7d": {
                    "pearson": {
                        "method": "pearson",
                        "window": "7d",
                        "assets": ["BTC", "ETH"],
                        "matrix": [[1.0, 0.8], [0.8, 1.0]],
                        "sample_counts": [[168, 168], [168, 168]],
                    }
                }
            }
        },
        "regime": {
            "timestamp": "2026-04-28T12:00:00+00:00",
            "label": "risk_on_correlated",
            "confidence": 0.81,
            "drivers": ["risk assets positively correlated"],
            "metrics": {
                "risk_asset_correlation": 0.8,
                "risk_dollar_correlation": -0.1,
                "observed_pairs": 1,
            },
        },
        "breakdowns": [
            {
                "pair": ["BTC", "ETH"],
                "direction": "correlation_breakdown",
                "current": 0.1,
                "baseline_mean": 0.8,
                "z_score": -2.4,
                "severity": "moderate",
            }
        ],
        "lead_lag": [
            {
                "pair": ["BTC", "ETH"],
                "best_lag": 2,
                "correlation": 0.72,
                "interpretation": "BTC leads ETH by 2 observations",
                "scores": {"2": 0.72},
            }
        ],
        "source_summary": {"BTC": {"points": 100, "source": "fixture"}},
    }


@pytest.fixture
def client(monkeypatch):
    dashboard_app.app.config["TESTING"] = True
    dashboard_app._cache.pop("cross_asset_snapshot", None)
    dashboard_app._cache_time.pop("cross_asset_snapshot", None)
    monkeypatch.setattr(dashboard_app, "_build_cross_asset_snapshot", _sample_snapshot)
    with dashboard_app.app.test_client() as test_client:
        yield test_client


def test_cross_asset_page_requires_auth(client) -> None:
    assert client.get("/cross-asset").status_code == 401


def test_cross_asset_page_renders(client) -> None:
    response = client.get("/cross-asset", headers=_auth_header())
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Correlation heatmap" in html
    assert "/api/cross-asset-matrix" in html


def test_matrix_api_requires_auth(client) -> None:
    assert client.get("/api/cross-asset-matrix").status_code == 401


def test_matrix_api_returns_selected_matrix(client) -> None:
    response = client.get(
        "/api/cross-asset-matrix?window=7d&method=pearson", headers=_auth_header()
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["matrix"]["assets"] == ["BTC", "ETH"]
    assert payload["breakdown_count"] == 1
    assert payload["mode"] == "cache_or_dry_run"


def test_matrix_api_falls_back_to_available_window(client) -> None:
    response = client.get(
        "/api/cross-asset-matrix?window=30d&method=kendall", headers=_auth_header()
    )
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["window"] == "7d"
    assert payload["method"] == "pearson"


def test_regime_api_requires_auth(client) -> None:
    assert client.get("/api/cross-asset-regime").status_code == 401


def test_regime_api_returns_current_regime_when_no_history(client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_ROOTS", (tmp_path,))
    response = client.get("/api/cross-asset-regime", headers=_auth_header())
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["regime"]["label"] == "risk_on_correlated"
    assert payload["history"][0]["label"] == "risk_on_correlated"


def test_regime_history_reads_local_jsonl(client, monkeypatch, tmp_path) -> None:
    data_dir = tmp_path / "data" / "cross_asset" / "2026-04-28"
    data_dir.mkdir(parents=True)
    (data_dir / "regimes.jsonl").write_text(
        json.dumps({"label": "risk_on_decorrelated", "timestamp": "t"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_app, "_DASHBOARD_ROOTS", (tmp_path,))
    response = client.get("/api/cross-asset-regime", headers=_auth_header())
    payload = response.get_json()
    assert payload["history"][-1]["label"] == "risk_on_decorrelated"


def test_breakdowns_api_requires_auth(client) -> None:
    assert client.get("/api/cross-asset-breakdowns").status_code == 401


def test_breakdowns_api_returns_breakdowns_and_lead_lag(client) -> None:
    response = client.get("/api/cross-asset-breakdowns", headers=_auth_header())
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["breakdowns"][0]["pair"] == ["BTC", "ETH"]
    assert payload["lead_lag"][0]["best_lag"] == 2


def test_nav_contains_cross_asset_link(client) -> None:
    response = client.get("/cross-asset", headers=_auth_header())
    assert 'href="/cross-asset"' in response.get_data(as_text=True)
