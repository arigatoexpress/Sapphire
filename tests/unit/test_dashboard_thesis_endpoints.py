"""Tests for the read-only dashboard endpoints that surface the sovereign
thesis matrix and the continuous-intelligence work planner.

Covers happy-path payload shape AND the safety-envelope fallback that
every endpoint emits when its underlying lib import or builder raises.
The endpoints must NEVER leak ``error`` without keeping
``execution_enabled``, ``live_trading_enabled``, ``telegram_sends_enabled``,
and ``write_enabled`` (where applicable) all False, since the dashboard's
public guarantee is that these surfaces are read-only.
"""

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
    dashboard_app._cache.clear()
    dashboard_app._cache_time.clear()
    with dashboard_app.app.test_client() as test_client:
        yield test_client


# ── /api/investments/thesis ─────────────────────────────────────────


def test_investments_thesis_happy_path(client, monkeypatch):
    sample = {
        "mode": "research_intel_only",
        "totals": {"assets": 3, "lenses": 2},
        "assets": [{"symbol": "BTC", "fit": "core"}],
        "safety": {"live_trading_enabled": False},
    }

    import lib.intel.sovereign_thesis as st

    monkeypatch.setattr(st, "build_sovereign_thesis_report", lambda: sample)

    response = client.get("/api/investments/thesis", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "research_intel_only"
    assert payload["totals"]["assets"] == 3
    assert payload["assets"][0]["symbol"] == "BTC"


def test_investments_thesis_error_returns_safety_envelope(client, monkeypatch):
    import lib.intel.sovereign_thesis as st

    def boom():
        raise RuntimeError("upstream config missing")

    monkeypatch.setattr(st, "build_sovereign_thesis_report", boom)

    response = client.get("/api/investments/thesis", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "research_intel_only"
    assert "upstream config missing" in payload["error"]
    assert payload["safety"]["live_trading_enabled"] is False
    assert payload["safety"]["execution_enabled"] is False
    assert payload["safety"]["telegram_sends_enabled"] is False
    assert payload["totals"]["assets"] == 0
    assert payload["assets"] == []
    assert payload["worldview"]["stance"] == "cypherpunk_austrian"


def test_investments_thesis_requires_auth(client):
    response = client.get("/api/investments/thesis")

    assert response.status_code == 401


# ── /api/autonomy/continuous-intelligence ───────────────────────────


def test_continuous_intelligence_happy_path_defaults_to_dry_run(client, monkeypatch):
    captured = {"live": None}

    def fake_build(fetch_live: bool):
        captured["live"] = fetch_live
        return {
            "mode": "read_only_task_planning",
            "totals": {"tasks": 5, "blocked": 0, "lanes": {"thesis": 2}},
            "tasks": [{"id": "t-1"}],
            "live_requested": fetch_live,
            "execution_enabled": False,
            "live_trading_enabled": False,
            "telegram_sends_enabled": False,
            "writes_by_default": False,
        }

    import lib.autonomy.continuous_intelligence as ci

    monkeypatch.setattr(ci, "build_continuous_intelligence_plan", fake_build)

    response = client.get("/api/autonomy/continuous-intelligence", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["totals"]["tasks"] == 5
    assert payload["execution_enabled"] is False
    assert payload["live_trading_enabled"] is False
    assert payload["telegram_sends_enabled"] is False
    assert captured["live"] is False


@pytest.mark.parametrize("flag", ["1", "true", "yes", "TRUE"])
def test_continuous_intelligence_live_query_param(client, monkeypatch, flag):
    captured = {"live": None}

    def fake_build(fetch_live: bool):
        captured["live"] = fetch_live
        return {"mode": "read_only_task_planning", "live_requested": fetch_live}

    import lib.autonomy.continuous_intelligence as ci

    monkeypatch.setattr(ci, "build_continuous_intelligence_plan", fake_build)

    response = client.get(
        f"/api/autonomy/continuous-intelligence?live={flag}", headers=_auth_header()
    )

    assert response.status_code == 200
    assert captured["live"] is True


def test_continuous_intelligence_error_returns_safety_envelope(client, monkeypatch):
    import lib.autonomy.continuous_intelligence as ci

    def boom(fetch_live: bool):  # noqa: ARG001
        raise FileNotFoundError("planner config missing")

    monkeypatch.setattr(ci, "build_continuous_intelligence_plan", boom)

    response = client.get("/api/autonomy/continuous-intelligence", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "read_only_task_planning"
    assert "planner config missing" in payload["error"]
    assert payload["execution_enabled"] is False
    assert payload["live_trading_enabled"] is False
    assert payload["telegram_sends_enabled"] is False
    assert payload["writes_by_default"] is False
    assert payload["totals"]["tasks"] == 0
    assert payload["tasks"] == []


# -- /api/autonomy/quant-intelligence --------------------------------


def test_quant_intelligence_happy_path_defaults_to_dry_run(client, monkeypatch):
    captured = {"live": None}

    def fake_build(*, fetch_live: bool):
        captured["live"] = fetch_live
        return {
            "mode": "quant_intelligence_flywheel",
            "totals": {"work_orders": 4, "watch_universes": 2},
            "dispatch_now": [{"id": "q-1"}],
            "execution_enabled": False,
            "live_trading_enabled": False,
            "telegram_sends_enabled": False,
            "writes_by_default": False,
        }

    import lib.autonomy.quant_intelligence as qi

    monkeypatch.setattr(qi, "build_quant_intelligence_flywheel", fake_build)

    response = client.get("/api/autonomy/quant-intelligence", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["totals"]["work_orders"] == 4
    assert payload["execution_enabled"] is False
    assert payload["live_trading_enabled"] is False
    assert payload["telegram_sends_enabled"] is False
    assert captured["live"] is False


@pytest.mark.parametrize("flag", ["1", "true", "yes", "TRUE"])
def test_quant_intelligence_live_query_param(client, monkeypatch, flag):
    captured = {"live": None}

    def fake_build(*, fetch_live: bool):
        captured["live"] = fetch_live
        return {"mode": "quant_intelligence_flywheel", "live_requested": fetch_live}

    import lib.autonomy.quant_intelligence as qi

    monkeypatch.setattr(qi, "build_quant_intelligence_flywheel", fake_build)

    response = client.get(f"/api/autonomy/quant-intelligence?live={flag}", headers=_auth_header())

    assert response.status_code == 200
    assert captured["live"] is True


def test_quant_intelligence_error_returns_safety_envelope(client, monkeypatch):
    import lib.autonomy.quant_intelligence as qi

    def boom(*, fetch_live: bool):  # noqa: ARG001
        raise RuntimeError("quant registry unavailable")

    monkeypatch.setattr(qi, "build_quant_intelligence_flywheel", boom)

    response = client.get("/api/autonomy/quant-intelligence", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "quant_intelligence_flywheel"
    assert "quant registry unavailable" in payload["error"]
    assert payload["execution_enabled"] is False
    assert payload["live_trading_enabled"] is False
    assert payload["telegram_sends_enabled"] is False
    assert payload["writes_by_default"] is False
    assert payload["dispatch_now"] == []


# ── /api/autonomy/continuous-intelligence/artifacts ─────────────────


def test_continuous_intelligence_artifacts_happy_path(client, monkeypatch):
    import lib.autonomy.continuous_intelligence_artifacts as cia

    monkeypatch.setattr(
        cia,
        "artifact_status",
        lambda: {
            "mode": "continuous_intelligence_artifact_status",
            "files": {"snapshots.jsonl": {"exists": True, "rows": 12}},
            "totals": {"snapshots": 12, "leases": 3},
        },
    )
    monkeypatch.setattr(
        cia,
        "snapshot_tasks",
        lambda write=False: {"records": 12, "write_enabled": False},
    )

    response = client.get("/api/autonomy/continuous-intelligence/artifacts", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["files"]["snapshots.jsonl"]["rows"] == 12
    assert payload["totals"]["snapshots"] == 12
    assert payload["snapshot_preview"] == {"records": 12, "write_enabled": False}
    # Endpoint MUST NEVER advertise write capability — it is the read-only mirror.
    assert payload["write_enabled"] is False


def test_continuous_intelligence_artifacts_calls_snapshot_dry_run(client, monkeypatch):
    """``snapshot_tasks`` MUST be invoked with ``write=False``."""
    captured = {"write": None}

    def fake_snapshot(write=False):
        captured["write"] = write
        return {"records": 0, "write_enabled": False}

    import lib.autonomy.continuous_intelligence_artifacts as cia

    monkeypatch.setattr(cia, "artifact_status", lambda: {"files": {}, "totals": {}})
    monkeypatch.setattr(cia, "snapshot_tasks", fake_snapshot)

    response = client.get("/api/autonomy/continuous-intelligence/artifacts", headers=_auth_header())

    assert response.status_code == 200
    assert captured["write"] is False


def test_continuous_intelligence_artifacts_error_returns_safety_envelope(client, monkeypatch):
    import lib.autonomy.continuous_intelligence_artifacts as cia

    def boom():
        raise RuntimeError("artifact dir missing")

    monkeypatch.setattr(cia, "artifact_status", boom)

    response = client.get("/api/autonomy/continuous-intelligence/artifacts", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "continuous_intelligence_artifact_status"
    assert "artifact dir missing" in payload["error"]
    assert payload["write_enabled"] is False
    assert payload["writes_by_default"] is False
    assert payload["execution_enabled"] is False
    assert payload["live_trading_enabled"] is False
    assert payload["telegram_sends_enabled"] is False
    assert payload["files"] == {}
    assert payload["snapshot_preview"]["write_enabled"] is False


# ── /api/autonomy/continuous-intelligence/lease-preview ─────────────


def test_lease_preview_default_args(client, monkeypatch):
    captured: dict = {}

    def fake_lease(*, agent_id, capabilities, target_runtime, limit, write):
        captured.update(
            {
                "agent_id": agent_id,
                "capabilities": capabilities,
                "target_runtime": target_runtime,
                "limit": limit,
                "write": write,
            }
        )
        return {
            "mode": "dry_run_task_lease",
            "leases": [],
            "leased_count": 0,
            "candidate_count": 8,
            "write_enabled": False,
        }

    import lib.autonomy.continuous_intelligence_artifacts as cia

    monkeypatch.setattr(cia, "lease_tasks", fake_lease)

    response = client.get(
        "/api/autonomy/continuous-intelligence/lease-preview", headers=_auth_header()
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["candidate_count"] == 8
    assert payload["write_enabled"] is False
    assert captured == {
        "agent_id": "windows-gpu",
        "capabilities": [],
        "target_runtime": None,
        "limit": 3,
        "write": False,
    }


def test_lease_preview_respects_query_params(client, monkeypatch):
    captured: dict = {}

    def fake_lease(*, agent_id, capabilities, target_runtime, limit, write):
        captured.update(locals())
        return {"mode": "dry_run_task_lease", "leases": [], "leased_count": 0}

    import lib.autonomy.continuous_intelligence_artifacts as cia

    monkeypatch.setattr(cia, "lease_tasks", fake_lease)

    response = client.get(
        "/api/autonomy/continuous-intelligence/lease-preview"
        "?agent_id=mac-cpu&capability=ta&capability=research"
        "&target_runtime=mac&limit=7",
        headers=_auth_header(),
    )

    assert response.status_code == 200
    assert captured["agent_id"] == "mac-cpu"
    assert captured["capabilities"] == ["ta", "research"]
    assert captured["target_runtime"] == "mac"
    assert captured["limit"] == 7
    assert captured["write"] is False


def test_lease_preview_invalid_limit_falls_back_to_three(client, monkeypatch):
    captured: dict = {}

    def fake_lease(*, agent_id, capabilities, target_runtime, limit, write):
        captured["limit"] = limit
        return {"mode": "dry_run_task_lease", "leases": []}

    import lib.autonomy.continuous_intelligence_artifacts as cia

    monkeypatch.setattr(cia, "lease_tasks", fake_lease)

    response = client.get(
        "/api/autonomy/continuous-intelligence/lease-preview?limit=garbage",
        headers=_auth_header(),
    )

    assert response.status_code == 200
    assert captured["limit"] == 3


def test_lease_preview_filters_blank_capabilities(client, monkeypatch):
    captured: dict = {}

    def fake_lease(*, agent_id, capabilities, target_runtime, limit, write):
        captured["capabilities"] = capabilities
        return {"mode": "dry_run_task_lease", "leases": []}

    import lib.autonomy.continuous_intelligence_artifacts as cia

    monkeypatch.setattr(cia, "lease_tasks", fake_lease)

    response = client.get(
        "/api/autonomy/continuous-intelligence/lease-preview"
        "?capability=ta&capability=&capability=%20%20&capability=research",
        headers=_auth_header(),
    )

    assert response.status_code == 200
    assert captured["capabilities"] == ["ta", "research"]


def test_lease_preview_error_returns_safety_envelope(client, monkeypatch):
    import lib.autonomy.continuous_intelligence_artifacts as cia

    def boom(**_kwargs):
        raise RuntimeError("lease store unavailable")

    monkeypatch.setattr(cia, "lease_tasks", boom)

    response = client.get(
        "/api/autonomy/continuous-intelligence/lease-preview", headers=_auth_header()
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "dry_run_task_lease"
    assert "lease store unavailable" in payload["error"]
    assert payload["write_enabled"] is False
    assert payload["leases"] == []
    assert payload["leased_count"] == 0
    assert payload["candidate_count"] == 0
    assert payload["safety"]["dry_run_dispatch_only"] is True
    assert payload["safety"]["execution_enabled"] is False
    assert payload["safety"]["live_trading_enabled"] is False
    assert payload["safety"]["telegram_sends_enabled"] is False
