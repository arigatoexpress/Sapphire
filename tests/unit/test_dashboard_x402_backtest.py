"""Dashboard route tests for the simulated x402 backtest receipt endpoint."""

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


def _payment_header(amount: int = 2_000_000, nonce: str = "bt-1") -> str:
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


def _summary() -> dict:
    return {
        "have_results": True,
        "total_backtests": 756,
        "computed_at": "2026-05-06T12:00:00+00:00",
        "age_hours": 1.0,
        "source_file": "best_per_symbol_20260506T120000Z.json",
        "best_per_symbol": [{"symbol": "BTC-USD"}],
    }


def _leaderboard(metric: str = "sortino", limit: int = 10, include_minimal_trades: bool = False):
    assert include_minimal_trades is False
    return {
        "metric": metric,
        "limit": limit,
        "total_rows": 2,
        "filtered_rows": 2,
        "source_file": "strategy_sweep_20260506T120000Z.json",
        "computed_at": "2026-05-06T12:00:00+00:00",
        "rows": [
            {"strategy_cls": "Trend", "symbol": "BTC-USD", "sortino": 2.4, "total_trades": 12},
            {"strategy_cls": "MeanRev", "symbol": "ETH-USD", "sortino": 1.7, "total_trades": 8},
        ],
    }


@pytest.fixture
def client(monkeypatch, tmp_path: Path):
    from lib.payments.x402_products import ReceiptLedger

    ledger_path = tmp_path / "x402_backtest_receipts.jsonl"
    dashboard_app.app.config["TESTING"] = True
    dashboard_app._X402_PRODUCT_MIDDLEWARE_CACHE.clear()
    monkeypatch.setenv("X402_RECIPIENT", RECIPIENT)
    monkeypatch.setattr(
        dashboard_app,
        "_x402_receipt_ledger",
        lambda: ReceiptLedger(ledger_path),
    )
    monkeypatch.setattr("lib.analytics.backtest_results.summary", _summary)
    monkeypatch.setattr("lib.analytics.backtest_results.leaderboard", _leaderboard)
    with dashboard_app.app.test_client() as test_client:
        yield test_client, ledger_path


def _read_receipts(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_backtest_endpoint_requires_auth(client) -> None:
    test_client, _ledger_path = client
    assert test_client.post("/api/x402/backtest").status_code == 401


def test_backtest_endpoint_returns_product_402_and_receipt(client) -> None:
    test_client, ledger_path = client

    response = test_client.post("/api/x402/backtest", headers=_auth_header())
    payload = response.get_json()
    receipts = _read_receipts(ledger_path)

    assert response.status_code == 402
    assert response.headers["X-Payment-Required"] == "true"
    assert payload["x402Version"] == 1
    assert payload["accepts"][0]["maxAmountRequired"] == "2000000"
    assert payload["accepts"][0]["extra"]["productId"] == "backtest_receipt"
    assert payload["receipt"]["status"] == "required"
    assert receipts[0]["status"] == "required"
    assert receipts[0]["metadata"]["endpoint"] == "/api/x402/backtest"


def test_backtest_endpoint_accepts_payment_and_ledgers_receipt(client) -> None:
    test_client, ledger_path = client
    header = _payment_header(nonce="bt-accepted")

    response = test_client.post(
        "/api/x402/backtest",
        json={"metric": "sortino", "symbols": ["BTC-USD"], "limit": 5},
        headers={**_auth_header(), "X-PAYMENT": header},
    )
    payload = response.get_json()
    receipts = _read_receipts(ledger_path)

    assert response.status_code == 200
    assert payload["product_id"] == "backtest_receipt"
    assert payload["paper_only"] is True
    assert payload["assumptions"]["no_live_market_data_pull"] is True
    assert payload["leaderboard"]["rows"][0]["symbol"] == "BTC-USD"
    assert payload["payment"]["status"] == "accepted"
    assert payload["payment"]["amount_atomic"] == 2_000_000
    assert receipts[0]["status"] == "accepted"
    assert receipts[0]["artifact_id"] == payload["artifact_id"]
    assert receipts[0]["payment_payload_hash"] != header
    assert header not in json.dumps(receipts[0])


def test_backtest_endpoint_rejects_underpayment_and_blocks_replay(client) -> None:
    test_client, ledger_path = client
    underpaid = _payment_header(amount=1, nonce="bt-underpaid")
    replay = _payment_header(nonce="bt-replay")

    rejected = test_client.post(
        "/api/x402/backtest",
        headers={**_auth_header(), "X-PAYMENT": underpaid},
    )
    first = test_client.post(
        "/api/x402/backtest",
        headers={**_auth_header(), "X-PAYMENT": replay},
    )
    second = test_client.post(
        "/api/x402/backtest",
        headers={**_auth_header(), "X-PAYMENT": replay},
    )
    receipts = _read_receipts(ledger_path)

    assert rejected.status_code == 402
    assert "amount" in rejected.get_json()["error"].lower()
    assert first.status_code == 200
    assert second.status_code == 402
    assert "nonce" in second.get_json()["error"].lower()
    assert [receipt["status"] for receipt in receipts] == ["rejected", "accepted", "rejected"]
