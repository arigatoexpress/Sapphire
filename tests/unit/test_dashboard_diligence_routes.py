"""Dashboard diligence aggregate routes stay auth-gated, read-only, and paste-safe."""

from __future__ import annotations

import base64
import importlib
import json
import os
import subprocess
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


def test_diligence_page_requires_auth(client):
    response = client.get("/diligence")

    assert response.status_code == 401


def test_diligence_page_renders_packet_seed_and_cards(client):
    response = client.get("/diligence", headers=_auth_header())

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Diligence Packet" in html
    assert "Risk Kernel" in html
    assert "Provenance" in html
    assert "LaunchAgents" in html
    assert "/api/diligence-summary" in html
    assert "/Users/aribs" not in html


def test_diligence_page_includes_all_fetch_endpoints(client):
    response = client.get("/diligence", headers=_auth_header())

    html = response.get_data(as_text=True)
    for endpoint in (
        "/api/diligence-summary",
        "/api/risk-kernel-summary",
        "/api/provenance-summary",
        "/api/test-suite-health",
        "/api/launchagent-summary",
    ):
        assert endpoint in html
    assert "method: 'POST'" not in html
    assert 'method: "POST"' not in html


def test_diligence_page_buyer_profile_fetches_buyer_safe_endpoints(client):
    response = client.get("/diligence?profile=buyer", headers=_auth_header())

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Buyer-safe profile" in html
    assert "/api/diligence-summary${buyerSafeQuery}" in html
    assert "profile=buyer" in html
    assert "/Users/aribs" not in html


def test_diligence_summary_api_requires_auth(client):
    response = client.get("/api/diligence-summary")

    assert response.status_code == 401


def test_diligence_summary_api_returns_ten_docs_and_paste_safe(client):
    response = client.get("/api/diligence-summary", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    serialized = json.dumps(payload)
    assert payload["mode"] == "read_only_diligence_packet"
    assert payload["totals"]["documents"] == 10
    assert [doc["id"] for doc in payload["documents"]] == [f"{idx:02d}" for idx in range(10)]
    assert "/Users/aribs" not in serialized
    assert "MOONSHOT_API_KEY=" not in serialized


def test_diligence_summary_helper_redacts_secret_shaped_text(tmp_path):
    diligence_dir = tmp_path / "docs" / "diligence"
    diligence_dir.mkdir(parents=True)
    for idx in range(10):
        (diligence_dir / f"{idx:02d}-sample.md").write_text(
            "\n".join(
                [
                    f"# {idx:02d} - Sample",
                    "",
                    "Ari stored TOKEN=super-secret-value under /Users/aribs/Code/Sapphire/data.",
                    "",
                    "## Diligence Readout",
                    "",
                    "Ari's packet is safe after api_key=abc123 was removed.",
                    "",
                    "## Evidence",
                    "",
                    "- /Users/aribs/Code/Sapphire/docs/example.md",
                ]
            ),
            encoding="utf-8",
        )

    payload = dashboard_app._build_diligence_summary(tmp_path)
    serialized = json.dumps(payload)

    assert payload["status"] == "pass"
    assert "/Users/aribs" not in serialized
    assert "super-secret-value" not in serialized
    assert "abc123" not in serialized
    assert "the operator" in serialized


def test_risk_kernel_summary_api_requires_auth(client):
    response = client.get("/api/risk-kernel-summary")

    assert response.status_code == 401


def test_risk_kernel_summary_api_reports_headline_numbers(client):
    response = client.get("/api/risk-kernel-summary", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    headline = payload["headline"]
    assert payload["mode"] == "read_only_risk_kernel_summary"
    assert payload["status"] == "pass"
    assert headline["policy_count"] == 5
    assert headline["max_daily_loss_pct"] == 4.0
    assert headline["max_intraday_drawdown_pct"] == 3.5
    assert headline["blocked_fired_gates"] >= 4
    assert payload["sample_verdicts"]["blocked"]["allowed"] is False


def test_provenance_summary_api_requires_auth(client):
    response = client.get("/api/provenance-summary")

    assert response.status_code == 401


def test_provenance_summary_api_returns_sanitized_invalid_sample(client, monkeypatch):
    from scripts.ops import provenance_verify

    def fake_report(_roots, *, older_than_hours):
        return {
            "schema_version": 1,
            "older_than_hours": older_than_hours,
            "checked": 2,
            "ok": False,
            "missing_or_invalid": 1,
            "roots": ["/Users/aribs/Code/Sapphire/data/intelligence"],
            "rows": [
                {
                    "artifact": "/Users/aribs/Code/Sapphire/data/intelligence/bad.json",
                    "ok": False,
                    "reason": "missing_sidecar",
                }
            ],
        }

    monkeypatch.setattr(provenance_verify, "build_report", fake_report)

    response = client.get("/api/provenance-summary?older_than_hours=2", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    serialized = json.dumps(payload)
    assert payload["status"] == "warn"
    assert payload["older_than_hours"] == 2.0
    assert payload["missing_or_invalid"] == 1
    assert "/Users/aribs" not in serialized


def test_invalid_provenance_hours_falls_back_to_default(client, monkeypatch):
    captured = {}

    def fake_summary(*, older_than_hours):
        captured["older_than_hours"] = older_than_hours
        return {"mode": "read_only_provenance_verifier", "status": "pass"}

    monkeypatch.setattr(dashboard_app, "_build_provenance_summary", fake_summary)

    response = client.get(
        "/api/provenance-summary?older_than_hours=garbage", headers=_auth_header()
    )

    assert response.status_code == 200
    assert captured["older_than_hours"] == 24.0


def test_test_suite_health_api_requires_auth(client):
    response = client.get("/api/test-suite-health")

    assert response.status_code == 401


def test_test_suite_health_api_reports_cache_shape(client, monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "_build_test_suite_health",
        lambda: {
            "mode": "read_only_test_suite_health",
            "status": "pass",
            "source": "pytest_cache",
            "totals": {"cached_nodeids": 42, "test_files": 7, "lastfailed": 0},
            "suites": {"unit": {"cached_nodeids": 40}, "plugin": {"cached_nodeids": 2}},
        },
    )

    response = client.get("/api/test-suite-health", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["mode"] == "read_only_test_suite_health"
    assert payload["source"] == "pytest_cache"
    assert payload["totals"]["cached_nodeids"] == 42


def test_launchagent_summary_api_requires_auth(client):
    response = client.get("/api/launchagent-summary")

    assert response.status_code == 401


def test_launchagent_summary_api_reports_labels_and_last_exit(client, monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "_dashboard_launchagent_labels",
        lambda: ["com.sapphire.pm-bot", "com.sapphire.dashboard", "com.sapphire.missing"],
    )

    def fake_run(*args, **kwargs):
        assert args[0] == ["launchctl", "list"]
        assert kwargs["check"] is False
        return subprocess.CompletedProcess(
            args[0],
            0,
            stdout=(
                "PID\tStatus\tLabel\n123\t0\tcom.sapphire.dashboard\n456\t0\tcom.sapphire.pm-bot\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(dashboard_app.subprocess, "run", fake_run)

    response = client.get("/api/launchagent-summary", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    by_label = {row["label"]: row for row in payload["launchagents"]}
    assert by_label["com.sapphire.dashboard"]["status_label"] == "running"
    assert by_label["com.sapphire.dashboard"]["last_exit"] == 0
    assert by_label["com.sapphire.pm-bot"]["status_label"] == "running"
    assert by_label["com.sapphire.pm-bot"]["last_exit"] == 0
    assert by_label["com.sapphire.missing"]["status_label"] == "not_loaded"


def test_launchagent_summary_buyer_profile_redacts_operational_identifiers(client, monkeypatch):
    monkeypatch.setattr(
        dashboard_app,
        "_dashboard_launchagent_labels",
        lambda: ["com.sapphire.pm-bot", "com.sapphire.dashboard"],
    )

    def fake_run(*args, **kwargs):
        assert args[0] == ["launchctl", "list"]
        return subprocess.CompletedProcess(
            args[0],
            0,
            stdout=(
                "PID\tStatus\tLabel\n123\t0\tcom.sapphire.dashboard\n456\t0\tcom.sapphire.pm-bot\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(dashboard_app.subprocess, "run", fake_run)

    response = client.get("/api/launchagent-summary?profile=buyer", headers=_auth_header())

    assert response.status_code == 200
    payload = response.get_json()
    serialized = json.dumps(payload)
    assert payload["audience"] == "buyer_safe"
    assert payload["redaction"]["applied"] is True
    assert payload["totals"]["labels"] == 2
    assert payload["launchagents"][0]["status_label"] in {"running", "exited"}
    assert "com.sapphire.dashboard" not in serialized
    assert "com.sapphire.pm-bot" not in serialized
    assert '"pid": 123' not in serialized
    assert '"pid": 456' not in serialized


def test_new_diligence_routes_are_get_only():
    new_routes = {
        "/diligence",
        "/api/diligence-summary",
        "/api/risk-kernel-summary",
        "/api/provenance-summary",
        "/api/test-suite-health",
        "/api/launchagent-summary",
    }

    for rule in dashboard_app.app.url_map.iter_rules():
        if rule.rule in new_routes:
            assert "GET" in rule.methods
            assert not ({"POST", "PUT", "PATCH", "DELETE"} & rule.methods)
