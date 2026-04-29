"""Dashboard walk-forward result routes degrade safely and surface latest artifacts."""

from __future__ import annotations

import base64
import importlib
import json
import os
import sys
from datetime import UTC, datetime
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


def _strategy_payload(
    *,
    strategy: str = "RegimeAwareRSI",
    sortino: float = 1.42,
    dsr_passed: bool = True,
    dsr_probability: float = 0.97,
) -> dict:
    return {
        "version": "0.1.0",
        "generated_at": datetime(2026, 4, 29, tzinfo=UTC).isoformat(),
        "strategy_cls": strategy,
        "symbol": "BTC-USD",
        "param_grid": {"rsi_period": [14]},
        "horizons": [
            {
                "horizon_days": 90,
                "config": {"train_bars": 60, "test_bars": 20},
                "result": {
                    "n_windows": 3,
                    "n_active_windows": 2,
                    "mean_test_sortino": sortino,
                    "median_test_sortino": sortino,
                    "test_sortino_cv": 0.31,
                    "mean_test_sharpe": 1.12,
                    "mean_test_calmar": 0.84,
                    "mean_test_total_return_pct": 0.11,
                    "mean_test_win_rate": 0.57,
                    "mean_test_profit_factor": 1.8,
                    "aggregate_test_max_drawdown_pct": -0.04,
                },
                "regime_decomposition": {
                    "dominant_regime": "risk_on_correlated",
                    "n_labelled": 52,
                    "n_unlabelled": 8,
                },
                "deflated_sharpe": {
                    "passed": dsr_passed,
                    "probability": dsr_probability,
                    "deflated_sharpe": 1.08,
                    "threshold": 0.95,
                },
            }
        ],
    }


def _seed_walkforward(
    tmp_path: Path,
    *,
    report_date: str = "2026-04-29",
    strategy: str = "RegimeAwareRSI",
    manifest_path_value: str | None = None,
    sortino: float = 1.42,
) -> Path:
    daily = tmp_path / report_date
    daily.mkdir(parents=True)
    artifact = daily / f"{strategy}.json"
    artifact.write_text(
        json.dumps(_strategy_payload(strategy=strategy, sortino=sortino), sort_keys=True),
        encoding="utf-8",
    )
    manifest = {
        "version": "0.1.0",
        "generated_at": datetime(2026, 4, 29, tzinfo=UTC).isoformat(),
        "symbol": "BTC-USD",
        "bars_source": "synthetic",
        "n_bars": 365,
        "horizons_days": [90],
        "selection_metric": "sortino",
        "bankroll": 10_000,
        "regime_label_count": 4,
        "artifacts": [
            {
                "strategy": strategy,
                "path": manifest_path_value if manifest_path_value is not None else str(artifact),
            }
        ],
    }
    (daily / "manifest.json").write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    return daily / "manifest.json"


def test_walkforward_api_requires_auth(client):
    response = client.get("/api/walkforward-results")

    assert response.status_code == 401


def test_walkforward_api_returns_no_data_when_manifest_missing(client, tmp_path, monkeypatch):
    monkeypatch.setattr(dashboard_app, "_WALKFORWARD_RESULTS_ROOT", tmp_path)

    response = client.get("/api/walkforward-results", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "no_data"
    assert payload["summary"]["strategy_count"] == 0
    assert payload["strategies"] == []


def test_walkforward_api_summarizes_seeded_artifacts(client, tmp_path, monkeypatch):
    _seed_walkforward(tmp_path)
    monkeypatch.setattr(dashboard_app, "_WALKFORWARD_RESULTS_ROOT", tmp_path)

    response = client.get("/api/walkforward-results", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["report_date"] == "2026-04-29"
    assert payload["summary"]["strategy_count"] == 1
    assert payload["summary"]["horizon_count"] == 1
    assert payload["summary"]["dsr_pass_count"] == 1
    assert payload["summary"]["best_strategy"] == "RegimeAwareRSI"
    strategy = payload["strategies"][0]
    assert strategy["status"] == "ok"
    assert strategy["artifact_path"].endswith("RegimeAwareRSI.json")
    assert strategy["best_horizon"]["horizon_days"] == 90
    assert strategy["best_horizon"]["mean_test_sortino"] == pytest.approx(1.42)
    assert strategy["best_horizon"]["dsr_passed"] is True
    assert strategy["best_horizon"]["dominant_regime"] == "risk_on_correlated"


def test_walkforward_api_falls_back_from_stale_absolute_artifact_path(
    client, tmp_path, monkeypatch
):
    _seed_walkforward(
        tmp_path,
        manifest_path_value="/Users/other/checkout/data/backtests/walkforward/old/RegimeAwareRSI.json",
    )
    monkeypatch.setattr(dashboard_app, "_WALKFORWARD_RESULTS_ROOT", tmp_path)

    response = client.get("/api/walkforward-results", headers=_auth_header())

    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["strategies"][0]["status"] == "ok"
    assert payload["strategies"][0]["best_horizon"]["dsr_probability"] == pytest.approx(0.97)


def test_walkforward_api_picks_newest_dated_manifest(client, tmp_path, monkeypatch):
    _seed_walkforward(tmp_path, report_date="2026-04-01", sortino=0.1)
    _seed_walkforward(tmp_path, report_date="2026-04-29", sortino=2.5)
    monkeypatch.setattr(dashboard_app, "_WALKFORWARD_RESULTS_ROOT", tmp_path)

    response = client.get("/api/walkforward-results", headers=_auth_header())

    payload = response.get_json()
    assert payload["report_date"] == "2026-04-29"
    assert payload["summary"]["best_sortino"] == pytest.approx(2.5)


def test_performance_page_wires_walkforward_panel(client):
    response = client.get("/performance", headers=_auth_header())

    assert response.status_code == 200
    assert b"Walk-Forward Validation" in response.data
    assert b"/api/walkforward-results" in response.data
