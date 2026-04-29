"""Dashboard Windows research-worker route is read-only and path-safe."""

from __future__ import annotations

import base64
import importlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["AUTH_PASSWORD"] = os.environ.get("AUTH_PASSWORD") or "test-password"
os.environ["X402_ENABLED"] = "0"

dashboard_app = importlib.import_module("services.dashboard.app")


class _FakeHTTPResponse:
    def __init__(self, payload: dict) -> None:
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def read(self, _limit: int) -> bytes:
        return self._body


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


def _worker_payload() -> dict:
    return {
        "mode": "read_only_windows_research_worker",
        "status": "ok",
        "source": "windows_webhook",
        "generated_at": datetime(2026, 4, 29, 21, 4, 24, tzinfo=UTC).isoformat(),
        "host": "DESKTOP-HFCK6U9",
        "git_sha_short": "6e7c1067",
        "run_id": "20260429T210424Z",
        "manifest_path_label": ".../research-worker/20260429T210424Z/manifest.json",
        "run_dir_label": "E:\\Sapphire\\research-worker\\20260429T210424Z",
        "summary": {
            "command_count": 2,
            "failed_count": 0,
            "artifact_count": 2,
            "safety_clear": True,
        },
        "safety": {
            "paper_only": True,
            "live_trading_enabled": False,
            "telegram_sends_enabled": False,
        },
        "commands": [
            {
                "name": "strategy_sweep",
                "status": "ok",
                "exit_code": 0,
                "duration_seconds": 5.043,
                "log_path_label": "E:\\Sapphire\\research-worker\\20260429T210424Z\\backtest.log",
            },
            {
                "name": "walkforward",
                "status": "ok",
                "exit_code": 0,
                "duration_seconds": 3.056,
                "log_path_label": ".../research-worker/20260429T210424Z/walkforward.log",
            },
        ],
        "artifacts": [
            {"kind": "backtest", "path_label": "E:\\Sapphire\\research-worker\\run\\backtest"}
        ],
    }


def test_windows_research_worker_api_requires_auth(client):
    response = client.get("/api/windows-research-worker")

    assert response.status_code == 401


def test_windows_research_worker_api_summarizes_worker_payload(
    client, monkeypatch
):
    def fake_urlopen(url: str, timeout: float) -> _FakeHTTPResponse:
        assert "windows/research-worker/latest" in url
        assert timeout == 5.0
        return _FakeHTTPResponse(_worker_payload())

    monkeypatch.setattr(dashboard_app.urllib.request, "urlopen", fake_urlopen)

    response = client.get("/api/windows-research-worker", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["summary"]["command_count"] == 2
    assert payload["summary"]["failed_count"] == 0
    assert payload["summary"]["safety_clear"] is True
    assert payload["safety"]["paper_only"] is True
    assert payload["safety"]["live_trading_enabled"] is False
    assert payload["commands"][0]["name"] == "strategy_sweep"
    assert payload["commands"][0]["log_path_label"] == ".../research-worker/20260429T210424Z/backtest.log"
    assert payload["artifacts"][0]["path_label"] == ".../research-worker/run/backtest"


def test_windows_research_worker_api_falls_back_to_webhook_health(
    client, monkeypatch
):
    calls: list[str] = []

    def fake_urlopen(url: str, timeout: float) -> _FakeHTTPResponse:
        del timeout
        calls.append(url)
        if "windows/research-worker/latest" in url:
            raise URLError("not deployed")
        return _FakeHTTPResponse({"research_worker": _worker_payload()})

    monkeypatch.setattr(dashboard_app.urllib.request, "urlopen", fake_urlopen)

    response = client.get("/api/windows-research-worker", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert len(calls) == 2


def test_performance_page_wires_windows_research_worker_panel(client):
    response = client.get("/performance", headers=_auth_header())

    assert response.status_code == 200
    assert b"Windows Research Worker" in response.data
    assert b"/api/windows-research-worker" in response.data
