"""Dashboard route tests for AgentWiki x402 endpoints."""

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

RECIPIENT = "0x1111111111111111111111111111111111111111"
ASSET = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
NETWORK = "base-sepolia"
ARTIFACT_ID = "aw_opportunities_federal_fit"

os.environ["AUTH_PASSWORD"] = os.environ.get("AUTH_PASSWORD") or "test-password"
os.environ["X402_ENABLED"] = "0"
os.environ["X402_RECIPIENT"] = RECIPIENT

dashboard_app = importlib.import_module("services.dashboard.app")


def _auth_header() -> dict[str, str]:
    creds = base64.b64encode(
        f"{dashboard_app.AUTH_USERNAME}:{dashboard_app.AUTH_PASSWORD}".encode()
    ).decode("ascii")
    return {"Authorization": f"Basic {creds}"}


def _payment_header(amount: int = 250_000, nonce: str = "aw-1") -> str:
    payload = {
        "payload": {
            "amount": amount,
            "payTo": RECIPIENT,
            "asset": ASSET,
            "network": NETWORK,
            "from": "0x2222222222222222222222222222222222222222",
            "txHash": f"0x{nonce}",
            "nonce": nonce,
        }
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


@pytest.fixture
def client(monkeypatch, tmp_path: Path):
    from lib.payments.x402_products import ReceiptLedger

    ledger_path = tmp_path / "x402_agentwiki_receipts.jsonl"
    dashboard_app.app.config["TESTING"] = True
    dashboard_app._X402_PRODUCT_MIDDLEWARE_CACHE.clear()
    monkeypatch.setenv("X402_RECIPIENT", RECIPIENT)
    monkeypatch.setattr(
        dashboard_app,
        "_x402_receipt_ledger",
        lambda: ReceiptLedger(ledger_path),
    )
    with dashboard_app.app.test_client() as test_client:
        yield test_client, ledger_path


def _read_receipts(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_agentwiki_search_requires_auth(client) -> None:
    test_client, _ledger_path = client

    assert test_client.get("/api/x402/agentwiki/search").status_code == 401


def test_agentwiki_grants_source_search_requires_auth(client) -> None:
    test_client, _ledger_path = client

    assert test_client.post("/api/x402/agentwiki/sources/grants-gov/search").status_code == 401


def test_agentwiki_search_and_quote_return_rights_context(client) -> None:
    test_client, _ledger_path = client

    search = test_client.get(
        "/api/x402/agentwiki/search?q=grants",
        headers=_auth_header(),
    )
    quote = test_client.get(
        f"/api/x402/agentwiki/artifacts/{ARTIFACT_ID}/quote",
        headers=_auth_header(),
    )

    search_payload = search.get_json()
    quote_payload = quote.get_json()
    assert search.status_code == 200
    assert quote.status_code == 200
    assert search_payload["artifacts"][0]["artifact_id"] == ARTIFACT_ID
    assert search_payload["artifacts"][0]["rights"]["bypass_allowed"] is False
    assert quote_payload["payment"]["amount_atomic"] == 250_000
    assert quote_payload["preflight"]["requires_rights_envelope"] is True


def test_agentwiki_grants_source_search_is_dry_run_by_default(
    client,
    monkeypatch,
    tmp_path: Path,
) -> None:
    test_client, _ledger_path = client
    monkeypatch.setenv("SAPPHIRE_AGENTWIKI_GRANTS_CACHE_DIR", str(tmp_path / "grants-cache"))

    response = test_client.post(
        "/api/x402/agentwiki/sources/grants-gov/search",
        headers=_auth_header(),
        json={"query": "wildfire", "limit": 4},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["mode"] == "agentwiki_grants_gov_source_search"
    assert payload["source_mode"] == "dry_run"
    assert payload["safety_mode"] == "read_only"
    assert payload["request"]["body"]["keyword"] == "wildfire"
    assert payload["request"]["body"]["rows"] == 4
    assert payload["summary"]["network_called"] is False
    assert payload["summary"]["official_award_status_claimed"] is False
    assert payload["rights"]["requires_attribution"] is True


def test_agentwiki_content_returns_402_and_receipt(client) -> None:
    test_client, ledger_path = client

    response = test_client.post(
        f"/api/x402/agentwiki/artifacts/{ARTIFACT_ID}/content",
        headers=_auth_header(),
    )
    payload = response.get_json()
    receipts = _read_receipts(ledger_path)

    assert response.status_code == 402
    assert response.headers["X-Payment-Required"] == "true"
    assert payload["x402Version"] == 1
    assert payload["accepts"][0]["maxAmountRequired"] == "250000"
    assert payload["accepts"][0]["extra"]["productId"] == "agentwiki_builder_brief"
    assert payload["receipt"]["status"] == "required"
    assert receipts[0]["status"] == "required"
    assert ARTIFACT_ID in receipts[0]["metadata"]["endpoint"]


def test_agentwiki_content_accepts_payment_and_logs_non_secret_receipt(client) -> None:
    test_client, ledger_path = client
    header = _payment_header(nonce="aw-accepted")

    response = test_client.post(
        f"/api/x402/agentwiki/artifacts/{ARTIFACT_ID}/content",
        headers={**_auth_header(), "X-PAYMENT": header},
    )
    payload = response.get_json()
    receipts = _read_receipts(ledger_path)

    assert response.status_code == 200
    assert payload["product_id"] == "agentwiki_builder_brief"
    assert payload["artifact_id"] == ARTIFACT_ID
    assert payload["rights"]["payment_is_permission"] is False
    assert payload["safety"]["no_paywall_bypass"] is True
    assert payload["payment"]["status"] == "accepted"
    assert payload["payment"]["amount_atomic"] == 250_000
    assert receipts[0]["status"] == "accepted"
    assert receipts[0]["artifact_id"] == payload["delivery_id"]
    assert receipts[0]["payment_payload_hash"] != header
    assert header not in json.dumps(receipts[0])


def test_agentwiki_content_rejects_underpayment_and_replay(client) -> None:
    test_client, ledger_path = client
    underpaid = _payment_header(amount=1, nonce="aw-underpaid")
    replay = _payment_header(nonce="aw-replay")

    rejected = test_client.post(
        f"/api/x402/agentwiki/artifacts/{ARTIFACT_ID}/content",
        headers={**_auth_header(), "X-PAYMENT": underpaid},
    )
    first = test_client.post(
        f"/api/x402/agentwiki/artifacts/{ARTIFACT_ID}/content",
        headers={**_auth_header(), "X-PAYMENT": replay},
    )
    second = test_client.post(
        f"/api/x402/agentwiki/artifacts/{ARTIFACT_ID}/content",
        headers={**_auth_header(), "X-PAYMENT": replay},
    )
    receipts = _read_receipts(ledger_path)

    assert rejected.status_code == 402
    assert "amount" in rejected.get_json()["error"].lower()
    assert first.status_code == 200
    assert second.status_code == 402
    assert "nonce" in second.get_json()["error"].lower()
    assert [receipt["status"] for receipt in receipts] == ["rejected", "accepted", "rejected"]
