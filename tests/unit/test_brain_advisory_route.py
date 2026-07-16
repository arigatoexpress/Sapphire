"""Dashboard endpoint tests for /api/brain/advisory."""

from __future__ import annotations

import base64
import importlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

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


def _sample_bridge_response(action: str = "read") -> dict:
    if action == "decide":
        return {
            "symbol": "BTC",
            "proxy_symbol": "IBIT",
            "signal": "GO_LONG",
            "direction": "bullish",
            "confidence": 0.72,
            "source": "BrainAdvisory",
            "detail": "advisory LONG via IBIT",
        }
    if action == "publish":
        return {
            "success": True,
            "mode": "dry-run",
            "count": 1,
            "signals": [{"strategy": "brain_advisory", "symbol": "IBIT", "direction": "long"}],
        }
    return {
        "success": True,
        "row_count": 4,
        "rows": [
            {"symbol": "IBIT", "signal": "LONG"},
            {"symbol": "MSTR", "signal": "FLAT"},
        ],
    }


def test_brain_advisory_requires_auth(client):
    response = client.get("/api/brain/advisory")
    assert response.status_code == 401


def test_brain_advisory_read_returns_bridge_payload(client):
    with patch("services.dashboard.app.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = json.dumps(_sample_bridge_response("read"))
        mock_run.return_value.stderr = ""

        response = client.get("/api/brain/advisory?action=read", headers=_auth_header())

    assert response.status_code == 200
    data = response.get_json()
    assert data["success"] is True
    assert data["row_count"] == 4


def test_brain_advisory_decide_requires_symbol(client):
    response = client.get("/api/brain/advisory?action=decide", headers=_auth_header())
    assert response.status_code == 400
    assert "symbol required" in response.get_json()["error"]


def test_brain_advisory_decide_passes_symbol(client):
    with patch("services.dashboard.app.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = json.dumps(_sample_bridge_response("decide"))
        mock_run.return_value.stderr = ""

        response = client.get(
            "/api/brain/advisory?action=decide&symbol=BTC", headers=_auth_header()
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["symbol"] == "BTC"
    assert data["signal"] == "GO_LONG"


def test_brain_advisory_publish_respects_live_flag(client):
    with patch("services.dashboard.app.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = json.dumps(_sample_bridge_response("publish"))
        mock_run.return_value.stderr = ""

        response = client.get(
            "/api/brain/advisory?action=publish&live=true", headers=_auth_header()
        )

    assert response.status_code == 200
    data = response.get_json()
    assert data["mode"] == "dry-run"
    # Verify the subprocess was invoked with live=true in the payload.
    call_input = json.loads(mock_run.call_args.kwargs["input"])
    assert call_input["live"] is True


def test_brain_advisory_unknown_action_returns_400(client):
    response = client.get("/api/brain/advisory?action=invalid", headers=_auth_header())
    assert response.status_code == 400
