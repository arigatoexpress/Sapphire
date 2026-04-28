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


# ---------------------------------------------------------------------------
# Tranche-3 / Lane 2: aggregator-backed endpoints
# ---------------------------------------------------------------------------


def _stub_snapshot_payload() -> dict:
    return {
        "schema_version": 1,
        "mode": "read_only_observability_snapshot",
        "status": "pass",
        "generated_at": "2026-04-28T12:00:00+00:00",
        "heartbeat": {
            "status": "pass",
            "checked_at": "2026-04-28T12:00:00+00:00",
            "totals": {"labels": 1, "running": 1, "loaded": 1, "not_loaded": 0, "unknown": 0},
            "uptime_seconds": 12345,
            "error": None,
            "launchagents": [
                {
                    "label": "com.sapphire.demo",
                    "status_label": "running",
                    "pid": 999,
                    "last_exit": 0,
                    "last_fired_at": "2026-04-28T11:55:00+00:00",
                    "restart_count": 0,
                }
            ],
        },
        "inference_proxy": {
            "cache_dir": "~/.cache/sapphire/inference_proxy",
            "tiers": [
                {"tier": "T1_GPU", "endpoint": "100.71.10.48:11434", "healthy": True,
                 "latency_ms": 410, "last_check": "2026-04-28T12:00:00+00:00"}
            ],
            "token_consumption": {"total": 12345, "by_tier": {"T1_GPU": 12345}, "window": "lifetime"},
            "last_updated": "2026-04-28T11:00:00+00:00",
            "available": True,
            "note": None,
        },
        "signal_streams": [
            {
                "source": "tradingview",
                "relative_path": "data/signals",
                "rate_1h": 3,
                "rate_24h": 21,
                "files_seen": 5,
                "latest_record_at": "2026-04-28T11:55:00+00:00",
                "note": None,
            }
        ],
        "provenance": {
            "status": "pass",
            "checked": 12,
            "missing_or_invalid": 0,
            "last_verify_at": "2026-04-28T12:00:00+00:00",
            "invalid_sample": [],
            "error": None,
        },
        "routine_pause": {
            "status": "pass",
            "totals": {"paused": 0},
            "paused_routines": [],
        },
        "event_bus": {
            "relative_path": "data/events/bus.jsonl",
            "events_seen": 8,
            "distinct_topics": 2,
            "topic_distribution": [
                {"topic": "signal.generated", "count": 5},
                {"topic": "threat.detected", "count": 3},
            ],
            "latest_event_at": "2026-04-28T12:00:00+00:00",
            "earliest_event_at": "2026-04-28T11:00:00+00:00",
            "note": None,
        },
    }


def _stub_stream_rates_payload() -> dict:
    return {
        "mode": "read_only_observability_stream_rates",
        "generated_at": "2026-04-28T12:00:00+00:00",
        "totals": {"rate_1h": 3, "rate_24h": 21},
        "sources": [
            {
                "source": "tradingview",
                "relative_path": "data/signals",
                "rate_1h": 3,
                "rate_24h": 21,
                "files_seen": 5,
                "latest_record_at": "2026-04-28T11:55:00+00:00",
                "note": None,
            }
        ],
    }


def _stub_launchagents_payload() -> dict:
    return {
        "mode": "read_only_observability_launchagents",
        "generated_at": "2026-04-28T12:00:00+00:00",
        "status": "pass",
        "totals": {"labels": 1, "running": 1, "loaded": 1, "not_loaded": 0, "unknown": 0},
        "error": None,
        "launchagents": [
            {
                "label": "com.sapphire.demo",
                "status_label": "running",
                "pid": 999,
                "last_exit": 0,
                "last_fired_at": "2026-04-28T11:55:00+00:00",
                "restart_count": 0,
            }
        ],
    }


def test_observability_system_summary_requires_auth(client):
    response = client.get("/api/observability-system-summary")
    assert response.status_code == 401


def test_observability_system_summary_returns_full_envelope(client, monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "_build_observability_system_summary",
        _stub_snapshot_payload,
    )
    response = client.get("/api/observability-system-summary", headers=_auth_header())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "read_only_observability_snapshot"
    assert payload["heartbeat"]["totals"]["running"] == 1
    assert payload["inference_proxy"]["tiers"][0]["healthy"] is True
    assert payload["signal_streams"][0]["rate_1h"] == 3
    assert payload["event_bus"]["distinct_topics"] == 2


def test_observability_system_summary_handles_aggregator_exception(client, monkeypatch):
    def boom():
        raise RuntimeError("aggregator failed")

    monkeypatch.setattr(dashboard_app, "_build_observability_system_summary", boom)
    response = client.get("/api/observability-system-summary", headers=_auth_header())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "unknown"
    assert "RuntimeError" in payload["error"]


def test_observability_system_summary_no_secrets_in_payload(client, monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "_build_observability_system_summary",
        _stub_snapshot_payload,
    )
    response = client.get("/api/observability-system-summary", headers=_auth_header())
    serialized = json.dumps(response.get_json())
    # Sanity probes: no home directory, no secrets.env, no api-key tokens.
    home = str(Path.home())
    assert home not in serialized
    assert "secrets.env" not in serialized
    assert "api_key" not in serialized.lower()


def test_observability_stream_rates_requires_auth(client):
    response = client.get("/api/observability-stream-rates")
    assert response.status_code == 401


def test_observability_stream_rates_returns_totals(client, monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "_build_observability_stream_rates",
        _stub_stream_rates_payload,
    )
    response = client.get("/api/observability-stream-rates", headers=_auth_header())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "read_only_observability_stream_rates"
    assert payload["totals"]["rate_1h"] == 3
    assert payload["sources"][0]["source"] == "tradingview"


def test_observability_stream_rates_handles_exception(client, monkeypatch):
    def boom():
        raise OSError("disk gone")

    monkeypatch.setattr(dashboard_app, "_build_observability_stream_rates", boom)
    response = client.get("/api/observability-stream-rates", headers=_auth_header())
    assert response.status_code == 200
    assert response.get_json()["status"] == "unknown"


def test_observability_launchagents_requires_auth(client):
    response = client.get("/api/observability-launchagents")
    assert response.status_code == 401


def test_observability_launchagents_returns_rows(client, monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "_build_observability_launchagents",
        _stub_launchagents_payload,
    )
    response = client.get("/api/observability-launchagents", headers=_auth_header())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "read_only_observability_launchagents"
    assert payload["totals"]["running"] == 1
    assert payload["launchagents"][0]["label"] == "com.sapphire.demo"


def test_observability_launchagents_handles_exception(client, monkeypatch):
    def boom():
        raise RuntimeError("launchctl unavailable")

    monkeypatch.setattr(dashboard_app, "_build_observability_launchagents", boom)
    response = client.get("/api/observability-launchagents", headers=_auth_header())
    assert response.status_code == 200
    assert response.get_json()["status"] == "unknown"


def test_observability_tranche4_feeds_requires_auth(client):
    response = client.get("/api/observability-tranche4-feeds")
    assert response.status_code == 401


def test_observability_tranche4_feeds_returns_rows(client, monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "_build_observability_tranche4_feeds",
        lambda: {
            "mode": "read_only_tranche4_feed_status",
            "status": "pass",
            "totals": {"feeds": 6, "with_events": 6, "events_seen": 12},
            "feeds": [
                {
                    "feed": "narrative_synthesis",
                    "topics": ["narrative.thesis.generated"],
                    "events_seen": 2,
                    "last_event_at": "2026-04-28T12:00:00+00:00",
                }
            ],
        },
    )

    response = client.get("/api/observability-tranche4-feeds", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "read_only_tranche4_feed_status"
    assert payload["feeds"][0]["feed"] == "narrative_synthesis"


def test_observability_tranche4_feeds_handles_exception(client, monkeypatch):
    def boom():
        raise RuntimeError("tranche4 unavailable")

    monkeypatch.setattr(dashboard_app, "_build_observability_tranche4_feeds", boom)
    response = client.get("/api/observability-tranche4-feeds", headers=_auth_header())
    assert response.status_code == 200
    assert response.get_json()["status"] == "unknown"


def test_observability_page_includes_new_panels_and_endpoint_polling(client, monkeypatch, tmp_path):
    monkeypatch.setattr(dashboard_app, "_ROUTINE_PAUSE_DIR", tmp_path / "pause")
    response = client.get("/observability", headers=_auth_header())
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    # New aggregator-backed sections must appear and poll the new endpoint.
    assert "System Heartbeat" in html
    assert "Inference Proxy" in html
    assert "Signal Streams" in html
    assert "Provenance Coverage" in html
    assert "Event Bus" in html
    assert "Tranche 4 Feed Health" in html
    assert "/api/observability-system-summary" in html
    assert "/api/observability-tranche4-feeds" in html


def test_observability_page_buyer_profile_fetches_buyer_safe_endpoints(
    client, monkeypatch, tmp_path
):
    monkeypatch.setattr(dashboard_app, "_ROUTINE_PAUSE_DIR", tmp_path / "pause")

    response = client.get("/observability?profile=buyer", headers=_auth_header())

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Buyer-safe profile" in html
    assert "/api/observability-system-summary${buyerSafeQuery}" in html
    assert "/api/observability-tranche4-feeds${buyerSafeQuery}" in html
    assert "profile=buyer" in html


def test_build_observability_system_summary_redacts_pii(monkeypatch):
    def fake_snapshot():
        class _Stub:
            def to_dict(self_inner):
                return {
                    "name": "Jane Doe",
                    "phone": "+1 555 123 9876",
                    "email": "jane@example.com",
                    "endpoint": "100.71.10.48:11434",
                    "label": "com.sapphire.demo",
                }
        return _Stub()

    monkeypatch.setattr(
        "lib.observability.build_system_snapshot",
        lambda: fake_snapshot(),
    )
    payload = dashboard_app._build_observability_system_summary()
    assert payload["name"].startswith("customer_")
    assert "9876" in payload["phone"]
    assert payload["email"].startswith("ja***")
    # Non-PII fields stay intact.
    assert payload["endpoint"] == "100.71.10.48:11434"
    assert payload["label"] == "com.sapphire.demo"


def test_observability_system_summary_buyer_profile_redacts_operational_identifiers(
    client, monkeypatch
):
    monkeypatch.setattr(
        dashboard_app,
        "_build_observability_system_summary",
        _stub_snapshot_payload,
    )

    response = client.get(
        "/api/observability-system-summary?profile=buyer",
        headers=_auth_header(),
    )

    assert response.status_code == 200
    payload = response.get_json()
    serialized = json.dumps(payload)
    assert payload["audience"] == "buyer_safe"
    assert payload["redaction"]["applied"] is True
    assert payload["heartbeat"]["totals"]["running"] == 1
    assert payload["inference_proxy"]["tiers"][0]["endpoint"] == "[buyer-safe redacted]"
    assert payload["signal_streams"][0]["rate_24h"] == 21
    assert "100.71.10.48:11434" not in serialized
    assert "com.sapphire.demo" not in serialized
    assert "~/.cache/sapphire" not in serialized
    assert "data/signals" not in serialized
    assert '"pid": 999' not in serialized
