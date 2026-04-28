"""End-to-end Flask test for the @require_payment decorator."""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from lib.payments.x402_middleware import (  # noqa: E402
    DEFAULT_USDC_CONTRACTS,
    X402Middleware,
    require_payment,
)

RECIPIENT = "0xAAAABBBBCCCCDDDDEEEEFFFF1111222233334444"
NETWORK = "base-sepolia"
ASSET = DEFAULT_USDC_CONTRACTS[NETWORK]


def _header(amount: int, nonce: str = "t1") -> str:
    payload = {
        "payload": {
            "amount": amount,
            "payTo": RECIPIENT,
            "asset": ASSET,
            "network": NETWORK,
            "from": "0xpayer",
            "nonce": nonce,
        }
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


@pytest.fixture
def app():
    flask = pytest.importorskip("flask")
    app = flask.Flask(__name__)

    mw = X402Middleware(
        recipient_address=RECIPIENT,
        network=NETWORK,
        asset=ASSET,
        enabled=True,
    )

    @app.route("/free")
    def free():
        return {"ok": True}

    @app.route("/premium")
    @require_payment(0.01, description="premium", middleware=mw)
    def premium():
        return {"data": "secret"}

    return app


def test_free_endpoint_bypasses_gate(app):
    resp = app.test_client().get("/free")
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True


def test_premium_requires_payment(app):
    resp = app.test_client().get("/premium")
    assert resp.status_code == 402
    body = resp.get_json()
    assert body["x402Version"] == 1
    assert body["accepts"][0]["payTo"] == RECIPIENT
    assert body["accepts"][0]["maxAmountRequired"] == "10000"
    assert resp.headers.get("X-Payment-Required") == "true"


def test_valid_payment_passes(app):
    resp = app.test_client().get("/premium", headers={"X-PAYMENT": _header(10_000, "p1")})
    assert resp.status_code == 200
    assert resp.get_json()["data"] == "secret"


def test_underpayment_returns_402(app):
    resp = app.test_client().get("/premium", headers={"X-PAYMENT": _header(5_000, "p2")})
    assert resp.status_code == 402
    body = resp.get_json()
    assert "amount" in body["error"].lower()


def test_nonce_replay_blocked(app):
    client = app.test_client()
    h = _header(10_000, "dup-nonce")
    r1 = client.get("/premium", headers={"X-PAYMENT": h})
    r2 = client.get("/premium", headers={"X-PAYMENT": h})
    assert r1.status_code == 200
    assert r2.status_code == 402
    assert "nonce" in r2.get_json()["error"].lower()
