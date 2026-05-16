"""Smoke tests for the per-project sub-pages on sapphirealpha.xyz.

Loads ``services/analytics_dashboard/app.py`` with a stubbed
``google.cloud.bigquery`` so the module imports cleanly outside Cloud
Run, then asserts each ``/p/<name>`` route returns 200 with HTML.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path


def _load_analytics_app(monkeypatch):
    root = Path(__file__).resolve().parents[2]
    module_path = root / "services" / "analytics_dashboard" / "app.py"

    fake_google = types.ModuleType("google")
    fake_cloud = types.ModuleType("google.cloud")
    fake_bigquery = types.ModuleType("google.cloud.bigquery")
    fake_bigquery.Client = lambda project: object()
    fake_bigquery.QueryJobConfig = lambda query_parameters=None: types.SimpleNamespace(
        query_parameters=query_parameters or []
    )
    fake_bigquery.ScalarQueryParameter = lambda name, kind, value: types.SimpleNamespace(
        name=name, kind=kind, value=value
    )
    fake_bigquery.ArrayQueryParameter = lambda name, kind, value: types.SimpleNamespace(
        name=name, kind=kind, value=value
    )
    fake_cloud.bigquery = fake_bigquery

    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.cloud", fake_cloud)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", fake_bigquery)
    monkeypatch.setenv("GCP_PROJECT", "test-project")
    monkeypatch.setenv("BQ_DATASET", "test_dataset")

    # Block outbound HTTP from subpages.py (they probe THO/wildfire/regional
    # health on each request) so tests are hermetic.
    def _no_http(*_a, **_kw):
        return None

    def _fake_0guard_fetch(_base_url, endpoint, *, timeout=2.5):
        del timeout
        payloads = {
            "/api/healthz": {"ok": True},
            "/api/readyz": {
                "ok": False,
                "readiness": "production_review",
                "checks": [
                    {
                        "id": "detector_coverage",
                        "status": "ok",
                        "summary": "Detector seeds cover the public incident set.",
                    },
                    {
                        "id": "telegram_state_store",
                        "status": "review",
                        "summary": "Persistent opt-in storage is still under review.",
                    },
                ],
            },
            "/api/data/summary": {
                "meta": {
                    "month": "April 2026",
                    "total_incidents": 28,
                    "total_loss_usd": 634862000,
                    "source_urls": ["https://defillama.com/hacks"],
                },
                "stats": {
                    "incidentCount": 28,
                    "chainCounts": {"Ethereum": 11, "Arbitrum": 1},
                    "attackVectorCounts": {"signature replay": 1},
                },
            },
            "/api/data/detection-coverage": {
                "coverage": [
                    {
                        "matched": True,
                        "blockerCount": 1,
                        "warningCount": 1,
                        "incident": {
                            "protocol": "Silo V2",
                            "chain": "Arbitrum",
                            "attack_vector": "oracle misconfiguration",
                        },
                    }
                ]
            },
        }
        return payloads.get(endpoint), "ok" if endpoint in payloads else "http_404"

    spec = importlib.util.spec_from_file_location("analytics_dashboard_app_subpages", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    # Replace _http_get_json on the freshly-imported subpages module.
    sub = sys.modules.get("subpages")
    if sub is not None:
        monkeypatch.setattr(sub, "_http_get_json", _no_http, raising=False)
    guard = sys.modules.get("og_guard")
    if guard is not None:
        monkeypatch.setattr(guard, "_fetch_json", _fake_0guard_fetch, raising=False)

    return module.app.test_client()


def _assert_html_200(client, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200, f"{path} -> {resp.status_code}"
    body = resp.data.decode("utf-8", errors="replace")
    assert "<html" in body.lower() or "<!doctype" in body.lower(), f"{path} did not return HTML"


def test_p_hackathon_smoke(monkeypatch):
    client = _load_analytics_app(monkeypatch)
    resp = client.get("/p/hackathon")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Hackathon" in body or "0G APAC" in body
    assert "0G_VERIFICATION_LAYER" in body
    assert "/api/hackathon/0g-proof" in body
    assert "SOURCE READY / LIVE PROOF PENDING" in body
    assert "MegaETH" in body
    assert "Robinhood" in body
    assert "Zama" in body


def test_p_0guard_smoke(monkeypatch):
    client = _load_analytics_app(monkeypatch)
    resp = client.get("/p/0guard")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "0guard turns wallet behavior into auditable verdicts" in body
    assert "28/1" not in body
    assert "28" in body
    assert "634.9M" in body
    assert "0G_NATIVE_SECURITY_SURFACE" in body
    assert "not present on the active public route yet" in body
    assert "OG_PRIVATE_KEY" not in body


def test_0guard_progress_api_is_public_safe(monkeypatch):
    monkeypatch.setenv("OG_PRIVATE_KEY", "0x" + "aa" * 32)
    client = _load_analytics_app(monkeypatch)

    resp = client.get("/api/0guard/progress")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["schema"] == "sapphire.0guard.progress.v1"
    assert payload["metrics"]["incident_count"] == 28
    assert payload["metrics"]["coverage"] == "100%"
    encoded = json.dumps(payload)
    assert "OG_PRIVATE_KEY" not in encoded
    assert ("aa" * 32) not in encoded


def test_og_proof_api_is_public_safe(monkeypatch):
    monkeypatch.setenv("OG_PRIVATE_KEY", "0x" + "aa" * 32)
    client = _load_analytics_app(monkeypatch)

    resp = client.get("/api/hackathon/0g-proof")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["networks"]["mainnet"]["chain_id"] == 16661
    assert payload["status"] in {"live-proof-ready", "source-ready-live-proof-pending"}
    assert any(row["id"] == "verifier_tool" and row["ok"] for row in payload["readiness"])
    assert "OG_PRIVATE_KEY" not in json.dumps(payload)
    assert ("aa" * 32) not in json.dumps(payload)


def test_p_wildfire_smoke(monkeypatch):
    client = _load_analytics_app(monkeypatch)
    resp = client.get("/p/wildfire")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Wildfire" in body
    assert "wildfire.sapphirealpha.xyz/admin" not in body
    assert "embedded admin console" not in body
    assert "api/sensors/health" not in body
    assert "signals_24h" not in body
    assert "signals_7d" not in body
    assert "PUBLIC_STATUS" in body
    assert "MISSION_CONTROLS" in body


def test_p_threats_smoke(monkeypatch):
    client = _load_analytics_app(monkeypatch)
    resp = client.get("/p/threats")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "CISA" in body
    assert "Threat" in body or "threat" in body


def test_p_tho_smoke(monkeypatch):
    client = _load_analytics_app(monkeypatch)
    resp = client.get("/p/tho")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    # THO retains its retail brand — should NOT use the cypherpunk shell
    assert "Texas Home Outlet" in body
    assert "OPEN OPERATIONS CONSOLE" in body


def test_p_regional_smoke(monkeypatch):
    client = _load_analytics_app(monkeypatch)
    resp = client.get("/p/regional")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    assert "Austin" in body
    assert "Regional" in body or "regional" in body
    assert "open admin console" not in body.lower()
    assert "regional.sapphirealpha.xyz/admin" not in body


def test_p_brain_smoke(monkeypatch):
    client = _load_analytics_app(monkeypatch)
    _assert_html_200(client, "/p/brain")
    body = client.get("/p/brain").data.decode("utf-8")
    assert "/api/brain/synthesis" in body
    assert "SIGNALS_24H" not in body
    assert "signal_count_24h" not in body
    assert "threat_count_24h" not in body


def test_p_markets_smoke(monkeypatch):
    client = _load_analytics_app(monkeypatch)
    _assert_html_200(client, "/p/markets")
    body = client.get("/p/markets").data.decode("utf-8")
    assert "/api/markets/snapshot" in body


def test_p_system_smoke(monkeypatch):
    client = _load_analytics_app(monkeypatch)
    _assert_html_200(client, "/p/system")
    body = client.get("/p/system").data.decode("utf-8")
    assert "/api/failover/readiness" in body
    assert "/api/silos/health" in body
    assert 'requires <a href="/admin">admin</a>' in body
    assert "analytics-dashboard" not in body
    assert "cyber-threat-bot" not in body
    assert "us-central1" not in body
    assert "project</div>" not in body
    assert "dataset</div>" not in body


def test_p_about_smoke(monkeypatch):
    client = _load_analytics_app(monkeypatch)
    _assert_html_200(client, "/p/about")
    body = client.get("/p/about").data.decode("utf-8")
    assert "Sapphire" in body
    assert "bloomberg" in body.lower()  # comparison table


def test_p_help_smoke(monkeypatch):
    client = _load_analytics_app(monkeypatch)
    _assert_html_200(client, "/p/help")
    body = client.get("/p/help").data.decode("utf-8")
    # Verifies the per-tab table is present
    assert "/p/brain" in body
    assert "/p/markets" in body


def test_subpages_all_register(monkeypatch):
    """Defensive: every advertised /p/<name> route returns 200."""
    client = _load_analytics_app(monkeypatch)
    for path in [
        "/p/0guard",
        "/p/hackathon",
        "/p/wildfire",
        "/p/threats",
        "/p/tho",
        "/p/regional",
        "/p/brain",
        "/p/markets",
        "/p/system",
        "/p/about",
        "/p/help",
    ]:
        resp = client.get(path)
        assert resp.status_code == 200, f"{path} -> {resp.status_code}"


def test_projects_manifest_api_is_safe_and_complete(monkeypatch):
    client = _load_analytics_app(monkeypatch)

    resp = client.get("/api/projects")

    assert resp.status_code == 200
    projects = resp.get_json()["projects"]
    slugs = [project["slug"] for project in projects]
    assert len(slugs) == len(set(slugs))
    assert {
        "brain",
        "markets",
        "tho",
        "threats",
        "wildfire",
        "regional",
        "0guard",
        "hackathon",
        "system",
    }.issubset(slugs)
    forbidden = ("localhost", "127.0.0.1", "file://", "secret", "token")
    for project in projects:
        assert project["info_route"].startswith("/p/")
        assert project["primary_cta"]["label"]
        for value in str(project).lower().split():
            assert not any(term in value for term in forbidden)


def test_projects_manifest_single_project(monkeypatch):
    client = _load_analytics_app(monkeypatch)

    resp = client.get("/api/projects/tho")
    missing = client.get("/api/projects/not-real")

    assert resp.status_code == 200
    project = resp.get_json()["project"]
    assert project["slug"] == "tho"
    assert project["primary_cta"]["href"] == "https://tho.sapphirealpha.xyz/"
    assert missing.status_code == 404
