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

from services.telegram_intel.history_export import import_history_export

FIXTURE = ROOT / "tests" / "fixtures" / "telegram_export" / "result.json"


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


def test_telegram_history_intel_api_requires_auth(client) -> None:
    response = client.get("/api/telegram-history-intel")
    assert response.status_code == 401


def test_telegram_history_intel_summary_empty_state(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(dashboard_app, "_TELEGRAM_HISTORY_INTEL_DIR", tmp_path / "missing")
    payload = dashboard_app._telegram_history_intel_summary()
    assert payload["available"] is False
    assert payload["status"] == "missing"
    assert payload["summary"]["messages"] == 0
    assert payload["safety"]["telegram_sends_enabled"] is False
    assert payload["safety"]["live_api_contact"] is False


def test_telegram_history_intel_api_returns_path_safe_summary(
    client,
    tmp_path: Path,
    monkeypatch,
) -> None:
    history_dir = tmp_path / "history"
    import_history_export(FIXTURE, data_dir=history_dir)
    monkeypatch.setattr(dashboard_app, "_TELEGRAM_HISTORY_INTEL_DIR", history_dir)

    response = client.get("/api/telegram-history-intel", headers=_auth_header())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["available"] is True
    assert payload["status"] == "ready"
    assert payload["summary"]["messages"] == 3
    assert payload["summary"]["open_loops"] == 1
    assert payload["artifacts"]["messages_jsonl"] is True
    assert payload["artifacts"]["messages_envelope"] is True
    assert payload["artifacts"]["context_json"] is True
    assert payload["artifacts"]["context_envelope"] is True
    assert payload["artifacts"]["context_provenance_verified"] is True
    assert payload["signals"]["open_loops"][0]["snippet"]

    blob = json.dumps(payload)
    assert str(tmp_path) not in blob
    for raw in (
        "analyst@example.invalid",
        "202-555-0198",
        "Operator Alpha",
        "Research Partner",
        "Client Research Room",
        "@privatealpha",
        "0x1234567890abcdef1234567890abcdef12345678",
        "https://example.com",
        "result.json",
    ):
        assert raw not in blob
