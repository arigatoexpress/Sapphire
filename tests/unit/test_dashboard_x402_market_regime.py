"""Dashboard route tests for the simulated x402 market-regime endpoint."""

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

os.environ["AUTH_PASSWORD"] = os.environ.get("AUTH_PASSWORD") or "test-password"
os.environ["X402_ENABLED"] = "0"
os.environ["X402_RECIPIENT"] = RECIPIENT

dashboard_app = importlib.import_module("services.dashboard.app")


def _auth_header() -> dict[str, str]:
    creds = base64.b64encode(
        f"{dashboard_app.AUTH_USERNAME}:{dashboard_app.AUTH_PASSWORD}".encode()
    ).decode("ascii")
    return {"Authorization": f"Basic {creds}"}


def _payment_header(amount: int = 250_000, nonce: str = "mr-1") -> str:
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


def _sample_snapshot() -> dict:
    return {
        "ok": True,
        "mode": "cache_or_dry_run",
        "generated_at": "2026-05-06T15:30:00Z",
        "assets": ["BTC", "ETH", "SPY"],
        "regime": {
            "timestamp": "2026-05-06T15:30:00Z",
            "label": "risk_on_correlated",
            "confidence": 0.82,
            "drivers": ["risk assets positively correlated"],
            "metrics": {"observed_pairs": 3, "risk_asset_correlation": 0.71},
        },
        "breakdowns": [{"pair": ["BTC", "ETH"], "severity": "low"}],
        "lead_lag": [{"pair": ["BTC", "ETH"], "best_lag": 1}],
        "source_summary": {"BTC": {"points": 100, "source": "fixture"}},
        "provenance": {"generator": "test"},
    }


def _sample_fred_features() -> dict:
    return {
        "feature_id": "fred-feature-1",
        "generated_at": "2026-05-06T15:25:00+00:00",
        "source": "fred_alfred",
        "row_count": 2,
        "series_count": 2,
        "latest_observation_date": "2026-05-05",
        "source_path": "data/macro/2026-05-06/fred_observations.jsonl",
        "series": {
            "DFF": {
                "value": 4.33,
                "observation_date": "2026-05-05",
                "realtime_start": "2026-05-06",
                "realtime_end": "2026-05-06",
                "units": "lin",
                "frequency": "Daily",
            },
            "DGS10": {
                "value": 4.12,
                "observation_date": "2026-05-05",
                "realtime_start": "2026-05-06",
                "realtime_end": "2026-05-06",
                "units": "lin",
                "frequency": "Daily",
            },
        },
    }


@pytest.fixture
def client(monkeypatch, tmp_path: Path):
    from lib.payments.x402_products import ReceiptLedger

    ledger_path = tmp_path / "x402_market_regime_receipts.jsonl"
    dashboard_app.app.config["TESTING"] = True
    dashboard_app._cache.pop("cross_asset_snapshot", None)
    dashboard_app._cache_time.pop("cross_asset_snapshot", None)
    dashboard_app._X402_PRODUCT_MIDDLEWARE_CACHE.clear()
    monkeypatch.setenv("X402_RECIPIENT", RECIPIENT)
    monkeypatch.setattr(dashboard_app, "_build_cross_asset_snapshot", _sample_snapshot)
    monkeypatch.setattr(dashboard_app, "_x402_fred_features_cached", _sample_fred_features)
    monkeypatch.setattr(
        dashboard_app,
        "_x402_receipt_ledger",
        lambda: ReceiptLedger(ledger_path),
    )
    with dashboard_app.app.test_client() as test_client:
        yield test_client, ledger_path


def _read_receipts(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_market_regime_endpoint_requires_auth(client) -> None:
    test_client, _ledger_path = client
    assert test_client.post("/api/x402/market-regime").status_code == 401


def test_market_regime_endpoint_returns_product_402_and_receipt(client) -> None:
    test_client, ledger_path = client

    response = test_client.post("/api/x402/market-regime", headers=_auth_header())
    payload = response.get_json()
    receipts = _read_receipts(ledger_path)

    assert response.status_code == 402
    assert response.headers["X-Payment-Required"] == "true"
    assert payload["x402Version"] == 1
    assert payload["accepts"][0]["maxAmountRequired"] == "250000"
    assert payload["accepts"][0]["extra"]["productId"] == "market_regime_report"
    assert payload["receipt"]["status"] == "required"
    assert receipts[0]["status"] == "required"
    assert receipts[0]["payment_payload_hash"] is None


def test_market_regime_endpoint_accepts_mock_payment_and_ledgers_receipt(client) -> None:
    test_client, ledger_path = client
    header = _payment_header(nonce="mr-accepted")

    response = test_client.post(
        "/api/x402/market-regime",
        headers={**_auth_header(), "X-PAYMENT": header},
    )
    payload = response.get_json()
    receipts = _read_receipts(ledger_path)

    assert response.status_code == 200
    assert payload["product_id"] == "market_regime_report"
    assert payload["artifact_kind"] == "market_regime_report"
    assert payload["settlement_mode"] == "simulated_or_testnet"
    assert payload["live_settlement_allowed"] is False
    assert payload["summary"]["label"] == "risk_on_correlated"
    assert payload["summary"]["macro_series_count"] == 2
    assert payload["macro_features"]["series"]["DFF"]["value"] == 4.33
    assert payload["payment"]["status"] == "accepted"
    assert payload["payment"]["live_settlement_allowed"] is False
    assert receipts[0]["status"] == "accepted"
    assert receipts[0]["artifact_id"] == payload["artifact_id"]
    assert receipts[0]["payment_payload_hash"] != header
    assert header not in json.dumps(receipts[0])


def test_market_regime_endpoint_rejects_underpayment_and_ledgers_receipt(client) -> None:
    test_client, ledger_path = client
    header = _payment_header(amount=1, nonce="mr-underpaid")

    response = test_client.post(
        "/api/x402/market-regime",
        headers={**_auth_header(), "X-PAYMENT": header},
    )
    payload = response.get_json()
    receipts = _read_receipts(ledger_path)

    assert response.status_code == 402
    assert "amount" in payload["error"].lower()
    assert payload["receipt"]["status"] == "rejected"
    assert receipts[0]["status"] == "rejected"
    assert "amount" in receipts[0]["verification_reason"].lower()


def test_market_regime_endpoint_blocks_nonce_replay(client) -> None:
    test_client, ledger_path = client
    header = _payment_header(nonce="mr-replay")

    first = test_client.post(
        "/api/x402/market-regime",
        headers={**_auth_header(), "X-PAYMENT": header},
    )
    second = test_client.post(
        "/api/x402/market-regime",
        headers={**_auth_header(), "X-PAYMENT": header},
    )
    receipts = _read_receipts(ledger_path)

    assert first.status_code == 200
    assert second.status_code == 402
    assert "nonce" in second.get_json()["error"].lower()
    assert [receipt["status"] for receipt in receipts] == ["accepted", "rejected"]
