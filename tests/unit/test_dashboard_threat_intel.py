"""Tests for the /threat-intel and /api/threat-intel dashboard surfaces.

Asserts:
* HTML page renders under basic auth, rejects without auth.
* JSON envelope shape — empty state when no snapshot, populated state
  when a snapshot file exists, error fallback on unreadable files.
* Severity classification (critical/high/medium/low) is applied to KEV
  and NVD rows.
* MITRE ATT&CK technique aggregation.
* Read-only safety envelope is always present.
"""

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


@pytest.fixture
def snapshot_dir(tmp_path, monkeypatch):
    """Point the threat-intel route at a temp data/intelligence dir."""
    intel = tmp_path / "intelligence"
    intel.mkdir()
    monkeypatch.setattr(dashboard_app, "_THREAT_INTEL_INTELLIGENCE_DIR", intel)
    monkeypatch.setattr(
        dashboard_app, "_THREAT_INTEL_LATEST_SYMLINK", intel / "latest"
    )
    return intel


def _write_snapshot(snapshot_dir: Path, date: str, threats: list[dict]) -> Path:
    day_dir = snapshot_dir / date
    day_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "refreshed_at": f"{date}T03:00:00+00:00",
        "source_count": len(threats),
        "threats": threats,
    }
    out = day_dir / "threats.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


# ── HTML page ────────────────────────────────────────────────────────


def test_threat_intel_page_requires_auth(client):
    response = client.get("/threat-intel")
    assert response.status_code == 401


def test_threat_intel_page_renders_with_auth(client):
    response = client.get("/threat-intel", headers=_auth_header())
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Threat_Intel" in body
    # Must reference paste-safe banner copy.
    assert "Read-only" in body
    # Must NOT leak operator names or internal commentary.
    assert "operator" not in body.lower() or "operator names" in body.lower()


# ── JSON empty state ─────────────────────────────────────────────────


def test_api_threat_intel_empty_state_when_dir_missing(client, tmp_path, monkeypatch):
    monkeypatch.setattr(
        dashboard_app, "_THREAT_INTEL_INTELLIGENCE_DIR", tmp_path / "does-not-exist"
    )
    monkeypatch.setattr(
        dashboard_app,
        "_THREAT_INTEL_LATEST_SYMLINK",
        tmp_path / "does-not-exist" / "latest",
    )
    response = client.get("/api/threat-intel", headers=_auth_header())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["available"] is False
    assert payload["error"] == "no_snapshot_available"
    assert payload["summary"]["total_threats"] == 0
    assert payload["kev_top"] == []
    assert payload["nvd_critical"] == []
    assert payload["mitre_techniques"] == []
    # Safety envelope is always present.
    assert payload["safety"]["execution_enabled"] is False
    assert payload["safety"]["live_trading_enabled"] is False
    assert payload["safety"]["telegram_sends_enabled"] is False
    assert "read_only_endpoint" in payload["safety"]["guards"]


def test_api_threat_intel_unreadable_snapshot_returns_safe_envelope(
    client, snapshot_dir
):
    bad = snapshot_dir / "2026-04-28"
    bad.mkdir()
    (bad / "threats.json").write_text("not json", encoding="utf-8")

    response = client.get("/api/threat-intel", headers=_auth_header())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["available"] is False
    assert payload["error"].startswith("snapshot_unreadable")
    assert payload["safety"]["execution_enabled"] is False


# ── JSON happy path ──────────────────────────────────────────────────


def test_api_threat_intel_populated_snapshot(client, snapshot_dir):
    threats = [
        {
            "source": "cisa-kev+nvd",
            "source_type": "cve",
            "canonical_id": "CVE-2026-1340",
            "title": "Ivanti EPMM Code Injection",
            "url": "https://example.com/cve",
            "published_at": "2026-04-08T06:00:00Z",
            "summary": "Exploit chain.",
            "score": 9.8,
            "exploited": True,
            "tags": ["kev", "rce"],
            "metadata": {"vendor_project": "Ivanti", "product": "EPMM", "due_date": "2026-04-11"},
        },
        {
            "source": "nvd",
            "source_type": "cve",
            "canonical_id": "CVE-2026-9999",
            "title": "Sample Critical NVD",
            "url": "https://example.com/cve2",
            "score": 9.2,
            "exploited": False,
            "tags": [],
            "metadata": {"product": "Sample"},
        },
        {
            "source": "mitre-attack",
            "source_type": "technique",
            "canonical_id": "T1059.003",
            "title": "Windows Command Shell",
            "score": 5.0,
            "exploited": False,
            "tags": ["T1059.003"],
        },
        {
            "source": "darkreading",
            "source_type": "article",
            "canonical_id": "art-1",
            "title": "Some article",
            "score": 0.0,
            "exploited": False,
            "tags": [],
        },
    ]
    _write_snapshot(snapshot_dir, "2026-04-28", threats)

    response = client.get("/api/threat-intel", headers=_auth_header())
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["available"] is True
    assert payload["snapshot_date"] == "2026-04-28"
    assert payload["refreshed_at"] == "2026-04-28T03:00:00+00:00"
    assert payload["summary"]["total_threats"] == 4
    assert payload["summary"]["critical"] == 1
    assert payload["summary"]["high"] == 1
    # KEV bucket: only the cisa-kev one.
    assert len(payload["kev_top"]) == 1
    assert payload["kev_top"][0]["canonical_id"] == "CVE-2026-1340"
    assert payload["kev_top"][0]["severity"] == "critical"
    # NVD criticals: both score >=9 entries.
    assert len(payload["nvd_critical"]) == 2
    # MITRE technique: at least one.
    techniques = {t["id"] for t in payload["mitre_techniques"]}
    assert "T1059.003" in techniques


def test_api_threat_intel_picks_latest_dated_dir(client, snapshot_dir):
    # Two days of data; the latest should win.
    _write_snapshot(snapshot_dir, "2026-04-25", [
        {"canonical_id": "CVE-2026-OLD", "title": "Old", "score": 1.0, "exploited": False, "source": "nvd", "tags": []}
    ])
    _write_snapshot(snapshot_dir, "2026-04-28", [
        {"canonical_id": "CVE-2026-NEW", "title": "New", "score": 9.5, "exploited": True, "source": "cisa-kev", "tags": ["kev"], "metadata": {}}
    ])
    response = client.get("/api/threat-intel", headers=_auth_header())
    payload = response.get_json()
    assert payload["snapshot_date"] == "2026-04-28"
    assert any(r["canonical_id"] == "CVE-2026-NEW" for r in payload["kev_top"])


def test_api_threat_intel_safety_envelope_always_present(client, snapshot_dir):
    _write_snapshot(snapshot_dir, "2026-04-28", [])
    response = client.get("/api/threat-intel", headers=_auth_header())
    payload = response.get_json()
    safety = payload["safety"]
    assert safety["execution_enabled"] is False
    assert safety["live_trading_enabled"] is False
    assert safety["telegram_sends_enabled"] is False
    assert safety["writes_by_default"] is False
    assert "no_live_network_calls" in safety["guards"]


def test_api_threat_intel_requires_auth(client):
    response = client.get("/api/threat-intel")
    assert response.status_code == 401


def test_api_threat_intel_no_post_or_put(client):
    # The route is GET-only — anything else should be method-not-allowed.
    for method in ("post", "put", "delete", "patch"):
        response = getattr(client, method)("/api/threat-intel", headers=_auth_header())
        assert response.status_code in (405, 401), (
            f"expected method-not-allowed or auth-fail for {method.upper()}"
        )


def test_api_threat_intel_severity_classification_maps_correctly(client, snapshot_dir):
    threats = [
        {"canonical_id": "C1", "title": "kev critical", "score": 9.5, "exploited": True, "source": "cisa-kev", "tags": [], "metadata": {}},
        {"canonical_id": "C2", "title": "kev high", "score": 8.0, "exploited": True, "source": "cisa-kev", "tags": [], "metadata": {}},
        {"canonical_id": "N1", "title": "nvd high", "score": 9.0, "exploited": False, "source": "nvd", "tags": []},
        {"canonical_id": "N2", "title": "nvd medium", "score": 7.5, "exploited": False, "source": "nvd", "tags": []},
        {"canonical_id": "L1", "title": "low", "score": 3.0, "exploited": False, "source": "nvd", "tags": []},
    ]
    _write_snapshot(snapshot_dir, "2026-04-28", threats)
    response = client.get("/api/threat-intel", headers=_auth_header())
    payload = response.get_json()
    s = payload["summary"]
    # 1 critical (C1), 2 high (C2 + N1), 1 medium (N2), 1 low (L1)
    assert s["critical"] == 1
    assert s["high"] == 2
    assert s["medium"] == 1
    assert s["low"] == 1


def test_api_threat_intel_paste_safe_no_internal_commentary(client, snapshot_dir):
    """Paste-safe contract: no operator names or internal terms in the response."""
    threats = [
        {
            "canonical_id": "CVE-2026-1340",
            "title": "Sample title",
            "score": 9.5,
            "exploited": True,
            "source": "cisa-kev",
            "tags": [],
            "metadata": {},
        }
    ]
    _write_snapshot(snapshot_dir, "2026-04-28", threats)
    response = client.get("/api/threat-intel", headers=_auth_header())
    payload = response.get_json()
    serialized = json.dumps(payload)
    # The response must NOT contain operator names from the user-prefs / memory.
    for forbidden in ("Aribs", "aribs", "@aristotlespec", "MOONSHOT_API_KEY"):
        assert forbidden not in serialized, f"leaked internal term: {forbidden!r}"
