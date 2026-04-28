"""Dashboard observability page exposes paused routines without leaking paths."""

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


@pytest.fixture
def client():
    dashboard_app.app.config["TESTING"] = True
    with dashboard_app.app.test_client() as test_client:
        yield test_client


def test_observability_page_requires_auth(client):
    response = client.get("/observability")

    assert response.status_code == 401


def test_observability_page_renders_pause_seed_and_endpoint(client, monkeypatch, tmp_path):
    pause_dir = tmp_path / "pause"
    pause_dir.mkdir()
    (pause_dir / "morning-briefing").write_text("2026-04-28T10:00:00+00:00\n")
    monkeypatch.setattr(dashboard_app, "_ROUTINE_PAUSE_DIR", pause_dir)

    response = client.get("/observability", headers=_auth_header())

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Observability" in html
    assert "Routine Pause Status" in html
    assert "/api/routine-pause-status" in html
    assert "morning-briefing" in html
    assert str(tmp_path) not in html


def test_routine_pause_status_api_requires_auth(client):
    response = client.get("/api/routine-pause-status")

    assert response.status_code == 401


def test_routine_pause_status_api_empty_is_pass(client, monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard_app, "_ROUTINE_PAUSE_DIR", tmp_path / "missing-pause")

    response = client.get("/api/routine-pause-status", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "read_only_routine_pause_status"
    assert payload["status"] == "pass"
    assert payload["totals"]["paused"] == 0
    assert payload["paused_routines"] == []


def test_routine_pause_status_api_returns_valid_flags_only(client, monkeypatch, tmp_path):
    pause_dir = tmp_path / "pause"
    pause_dir.mkdir()
    (pause_dir / "morning-briefing").write_text("2026-04-28T10:00:00+00:00\n")
    (pause_dir / "bad.name").write_text("2026-04-28T10:00:00+00:00\n")
    monkeypatch.setattr(dashboard_app, "_ROUTINE_PAUSE_DIR", pause_dir)

    response = client.get("/api/routine-pause-status", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    serialized = json.dumps(payload)
    assert payload["status"] == "warn"
    assert payload["totals"]["paused"] == 1
    assert payload["paused_routines"] == [
        {"name": "morning-briefing", "paused_at": "2026-04-28T10:00:00+00:00"}
    ]
    assert "bad.name" not in serialized
    assert str(tmp_path) not in serialized


def test_routine_pause_summary_uses_mtime_for_empty_flag(tmp_path):
    pause_dir = tmp_path / "pause"
    pause_dir.mkdir()
    (pause_dir / "factory-repo-fixer").write_text("")

    payload = dashboard_app._build_routine_pause_summary(pause_dir)

    assert payload["totals"]["paused"] == 1
    assert payload["paused_routines"][0]["name"] == "factory-repo-fixer"
    assert payload["paused_routines"][0]["paused_at"]


def test_base_nav_links_observability(client):
    response = client.get("/", headers=_auth_header())

    assert response.status_code == 200
    assert "/observability" in response.get_data(as_text=True)
