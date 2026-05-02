"""Tests for the customer-dossier 0.2.0 surface upgrades.

These tests exercise the two new contracts in
``services/dashboard/app.py``'s ``/api/customer-dossier`` route:

1. **Cell-suppression**: ``summary.by_status`` reports any bucket with a
   count strictly less than 5 as the literal string ``"<5"``. Buckets at or
   above the threshold pass through with the exact integer count. The
   marker is only ever applied at the dashboard boundary; the underlying
   redactor is unchanged.

2. **Per-tenant hash**: ``customers[*].per_tenant_hash`` is emitted as
   ``tenant_<id>_<16hex>``. Different tenants with the same upstream
   payload yield different hashes. The route never echoes raw PII even
   when emitting hash forms.

Coverage target: ≥ 10 cases. We add 14 to leave headroom for sister
agents touching the same file.
"""

from __future__ import annotations

import base64
import importlib
import json
import os
import re
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
def dossier_dir(tmp_path, monkeypatch):
    d = tmp_path / "tho_intel"
    d.mkdir()
    monkeypatch.setattr(dashboard_app, "_TARGET_TH_INTEL_DIR", d)
    return d


@pytest.fixture(autouse=True)
def _isolated_secrets(tmp_path, monkeypatch):
    """Each test gets a clean isolated secrets path so test runs do not pick
    up the real ``~/.sapphire/secrets.env`` file (which would defeat the
    fallback-salt-path tests). Tests that want a configured salt can write
    into ``tmp_path / 'secrets.env'``."""
    secrets_path = tmp_path / "secrets.env"
    monkeypatch.setattr(dashboard_app, "_DOSSIER_SECRETS_PATH", secrets_path)
    # Strip any inherited env vars that would mask the fallback path.
    for k in list(os.environ.keys()):
        if k.startswith("SAPPHIRE_DOSSIER_HASH_SALT_"):
            monkeypatch.delenv(k, raising=False)
    yield secrets_path


def _write_dossier(dir_: Path, name: str, payload: dict) -> Path:
    out = dir_ / name
    out.write_text(json.dumps(payload), encoding="utf-8")
    return out


def _customers_with_status_counts(counts: dict[str, int]) -> list[dict]:
    """Build a synthetic customer list matching the requested status counts."""
    out: list[dict] = []
    for status, n in counts.items():
        for i in range(n):
            out.append(
                {
                    "customer_id": f"{status.lower()}-{i:04d}",
                    "customer_name": f"Customer {status} {i}",
                    "email": f"c{i}@{status.lower()}.example.com",
                    "status": status,
                }
            )
    return out


# ── Cell-suppression ─────────────────────────────────────────────────


def test_cell_suppression_triggers_on_small_buckets(client, dossier_dir):
    customers = _customers_with_status_counts({"ENROLLED": 2, "LEAD": 1, "CLOSED": 4})
    _write_dossier(dossier_dir, "dossier_2026-04-28.json", {"customers": customers, "deals": []})
    response = client.get("/api/customer-dossier", headers=_auth_header())
    payload = response.get_json()
    assert payload["summary"]["by_status"] == {
        "ENROLLED": "<5",
        "LEAD": "<5",
        "CLOSED": "<5",
    }


def test_cell_suppression_passes_through_buckets_at_threshold(client, dossier_dir):
    customers = _customers_with_status_counts({"ENROLLED": 5, "LEAD": 7, "CLOSED": 12})
    _write_dossier(dossier_dir, "dossier_2026-04-28.json", {"customers": customers, "deals": []})
    response = client.get("/api/customer-dossier", headers=_auth_header())
    payload = response.get_json()
    by_status = payload["summary"]["by_status"]
    assert by_status["ENROLLED"] == 5  # exactly at threshold => exact int
    assert by_status["LEAD"] == 7
    assert by_status["CLOSED"] == 12


def test_cell_suppression_mixed_buckets(client, dossier_dir):
    """Some buckets suppress, others pass through with exact counts."""
    customers = _customers_with_status_counts({"ENROLLED": 1326, "LEAD": 4, "CLOSED": 8})
    _write_dossier(dossier_dir, "dossier_2026-04-28.json", {"customers": customers, "deals": []})
    response = client.get("/api/customer-dossier", headers=_auth_header())
    payload = response.get_json()
    by_status = payload["summary"]["by_status"]
    assert by_status["ENROLLED"] == 1326
    assert by_status["LEAD"] == "<5"  # under threshold
    assert by_status["CLOSED"] == 8


def test_cell_suppression_metadata_is_emitted(client, dossier_dir):
    _write_dossier(
        dossier_dir,
        "dossier_2026-04-28.json",
        {"customers": _customers_with_status_counts({"ENROLLED": 7}), "deals": []},
    )
    response = client.get("/api/customer-dossier", headers=_auth_header())
    payload = response.get_json()
    cs = payload["summary"]["cell_suppression"]
    assert cs["applied"] is True
    assert cs["threshold"] == 5
    assert cs["marker"] == "<5"


def test_cell_suppression_safety_envelope_marks_lt5_guard(client, dossier_dir):
    _write_dossier(
        dossier_dir,
        "dossier_2026-04-28.json",
        {"customers": _customers_with_status_counts({"X": 1}), "deals": []},
    )
    response = client.get("/api/customer-dossier", headers=_auth_header())
    payload = response.get_json()
    safety = payload["safety"]
    assert safety["cell_suppression"] == "applied"
    assert "cell_suppression_lt_5" in safety["guards"]


# ── Per-tenant hash ──────────────────────────────────────────────────


def test_per_tenant_hash_block_is_emitted(client, dossier_dir):
    _write_dossier(
        dossier_dir,
        "dossier_2026-04-28.json",
        {"customers": _customers_with_status_counts({"ENROLLED": 6}), "deals": []},
    )
    response = client.get("/api/customer-dossier?tenant=acme", headers=_auth_header())
    payload = response.get_json()
    assert payload["tenant"]["id"] == "acme"
    # Without a configured salt, the response must say so explicitly.
    assert payload["tenant"]["salt_source"] == "default_fallback"
    assert payload["tenant"]["hash_algorithm"] == "HMAC-SHA256"
    hashes = payload["customer_hashes"]
    assert len(hashes) == 6
    for h in hashes:
        assert re.fullmatch(r"tenant_acme_[0-9a-f]{16}", h["per_tenant_hash"]), h


def test_per_tenant_hash_isolates_across_tenants(client, dossier_dir):
    _write_dossier(
        dossier_dir,
        "dossier_2026-04-28.json",
        {"customers": _customers_with_status_counts({"ENROLLED": 3}), "deals": []},
    )
    a = client.get("/api/customer-dossier?tenant=acme", headers=_auth_header()).get_json()
    b = client.get("/api/customer-dossier?tenant=globex", headers=_auth_header()).get_json()

    a_hashes = {h["per_tenant_hash"] for h in a["customer_hashes"]}
    b_hashes = {h["per_tenant_hash"] for h in b["customer_hashes"]}
    # Different tenants with the same source data must produce DIFFERENT
    # per-tenant hashes — that's the whole isolation contract.
    assert a_hashes.isdisjoint(b_hashes), (
        f"tenant isolation broken: acme={a_hashes} globex={b_hashes}"
    )


def test_per_tenant_hash_uses_configured_salt_from_secrets(
    client, dossier_dir, _isolated_secrets, monkeypatch
):
    secrets_path = _isolated_secrets
    secrets_path.write_text(
        "SAPPHIRE_DOSSIER_HASH_SALT_ACME=top-secret-rot-2026-04-29\n",
        encoding="utf-8",
    )
    _write_dossier(
        dossier_dir,
        "dossier_2026-04-28.json",
        {"customers": _customers_with_status_counts({"X": 2}), "deals": []},
    )
    response = client.get("/api/customer-dossier?tenant=acme", headers=_auth_header())
    payload = response.get_json()
    assert payload["tenant"]["salt_source"] == "configured"
    # And the resulting hashes must differ from the default-fallback hashes.
    monkeypatch.setattr(dashboard_app, "_DOSSIER_SECRETS_PATH", secrets_path.parent / "missing")
    fallback = client.get("/api/customer-dossier?tenant=acme", headers=_auth_header()).get_json()
    assert fallback["tenant"]["salt_source"] == "default_fallback"
    a_hashes = {h["per_tenant_hash"] for h in payload["customer_hashes"]}
    b_hashes = {h["per_tenant_hash"] for h in fallback["customer_hashes"]}
    # Salt rotation invalidates previously-emitted hashes for the same
    # tenant: configured-salt hashes MUST NOT collide with default-salt
    # hashes for the same input.
    assert a_hashes.isdisjoint(b_hashes)


def test_per_tenant_hash_uses_env_var_when_set(client, dossier_dir, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_DOSSIER_HASH_SALT_ACME", "env-salt-2026-04-29")
    _write_dossier(
        dossier_dir,
        "dossier_2026-04-28.json",
        {"customers": _customers_with_status_counts({"X": 2}), "deals": []},
    )
    response = client.get("/api/customer-dossier?tenant=acme", headers=_auth_header())
    payload = response.get_json()
    assert payload["tenant"]["salt_source"] == "configured"


def test_per_tenant_hash_default_tenant_is_default(client, dossier_dir):
    _write_dossier(
        dossier_dir,
        "dossier_2026-04-28.json",
        {"customers": _customers_with_status_counts({"X": 1}), "deals": []},
    )
    response = client.get("/api/customer-dossier", headers=_auth_header())
    payload = response.get_json()
    assert payload["tenant"]["id"] == "default"
    for h in payload["customer_hashes"]:
        assert h["per_tenant_hash"].startswith("tenant_default_")


# ── PII non-leakage even with hashes ─────────────────────────────────


def test_per_tenant_hash_does_not_leak_raw_pii(client, dossier_dir):
    """Hash visible but raw PII must still be absent from the response."""
    payload_in = {
        "customers": [
            {
                "customer_id": "acme-1",
                "customer_name": "Marie Curie",
                "email": "marie@example.org",
                "phone": "555-867-5309",
                "address": "1 Radium Way, Warsaw, NY 10001",
                "status": "ENROLLED",
            },
        ],
        "deals": [],
    }
    _write_dossier(dossier_dir, "dossier_2026-04-28.json", payload_in)
    response = client.get("/api/customer-dossier?tenant=acme", headers=_auth_header())
    serialized = response.get_data(as_text=True)
    # PII strings MUST NOT appear anywhere in the serialized response —
    # the hash is opaque, so the raw value cannot have leaked through it.
    for forbidden in [
        "Marie Curie",
        "marie@",
        "555-867-5309",
        "8675309",
        "1 Radium Way",
        "10001",
    ]:
        assert forbidden not in serialized, f"PII leak: {forbidden!r}"
    # And the hash form must be present.
    assert re.search(r"tenant_acme_[0-9a-f]{16}", serialized) is not None


def test_per_tenant_hash_is_stable_across_requests(client, dossier_dir):
    _write_dossier(
        dossier_dir,
        "dossier_2026-04-28.json",
        {"customers": _customers_with_status_counts({"X": 3}), "deals": []},
    )
    a = client.get("/api/customer-dossier?tenant=acme", headers=_auth_header()).get_json()
    b = client.get("/api/customer-dossier?tenant=acme", headers=_auth_header()).get_json()
    # Idempotent across two requests in the same process.
    a_hashes = sorted(h["per_tenant_hash"] for h in a["customer_hashes"])
    b_hashes = sorted(h["per_tenant_hash"] for h in b["customer_hashes"])
    assert a_hashes == b_hashes


def test_per_tenant_hash_safety_envelope_lists_hmac_guard(client, dossier_dir):
    _write_dossier(
        dossier_dir,
        "dossier_2026-04-28.json",
        {"customers": _customers_with_status_counts({"X": 1}), "deals": []},
    )
    response = client.get("/api/customer-dossier?tenant=acme", headers=_auth_header())
    safety = response.get_json()["safety"]
    assert safety["per_tenant_hash"] == "applied"
    assert "per_tenant_hmac_sha256" in safety["guards"]


def test_dossier_route_normalizes_tenant_id(client, dossier_dir):
    """Tenant ids with dots/slashes/punctuation must be sanitized into the
    response prefix — no raw path-traversal-style characters."""
    _write_dossier(
        dossier_dir,
        "dossier_2026-04-28.json",
        {"customers": _customers_with_status_counts({"X": 2}), "deals": []},
    )
    response = client.get("/api/customer-dossier?tenant=../etc/passwd", headers=_auth_header())
    payload = response.get_json()
    # Normalized tenant id keeps only [A-Za-z0-9_].
    assert re.fullmatch(r"[A-Za-z0-9_]+", payload["tenant"]["id"]), payload["tenant"]["id"]


def test_dossier_empty_customer_list_emits_no_hashes(client, dossier_dir):
    _write_dossier(dossier_dir, "dossier_2026-04-28.json", {"customers": [], "deals": []})
    response = client.get("/api/customer-dossier?tenant=acme", headers=_auth_header())
    payload = response.get_json()
    assert payload["customer_hashes"] == []
    assert payload["summary"]["by_status"] == {}


def test_dossier_route_honors_tenant_query_string(client, dossier_dir):
    """End-to-end: the query string flows into ``customer_hashes`` prefixes."""
    _write_dossier(
        dossier_dir,
        "dossier_2026-04-28.json",
        {"customers": _customers_with_status_counts({"X": 1}), "deals": []},
    )
    a = client.get("/api/customer-dossier?tenant=tenant_a", headers=_auth_header()).get_json()
    b = client.get("/api/customer-dossier?tenant=tenant_b", headers=_auth_header()).get_json()
    a_hash = a["customer_hashes"][0]["per_tenant_hash"]
    b_hash = b["customer_hashes"][0]["per_tenant_hash"]
    assert a_hash.startswith("tenant_tenant_a_")
    assert b_hash.startswith("tenant_tenant_b_")
    assert a_hash != b_hash
