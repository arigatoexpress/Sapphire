"""Unit tests for lib/payments/x402_middleware.py."""

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
    MockVerifier,
    PaymentRequirements,
    X402Middleware,
    build_402_response,
)

RECIPIENT = "0x1111111111111111111111111111111111111111"
NETWORK = "base-sepolia"
ASSET = DEFAULT_USDC_CONTRACTS[NETWORK]


def _pay_header(amount_atomic: int, *, recipient=RECIPIENT, asset=ASSET,
                network=NETWORK, nonce: str | None = "n-1") -> str:
    payload = {
        "payload": {
            "amount": amount_atomic,
            "payTo": recipient,
            "asset": asset,
            "network": network,
            "from": "0x2222222222222222222222222222222222222222",
            "txHash": "0xdeadbeef",
            "nonce": nonce,
        },
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


@pytest.fixture
def mw() -> X402Middleware:
    return X402Middleware(
        recipient_address=RECIPIENT,
        pricing={"/api/premium": 0.01},
        network=NETWORK,
        asset=ASSET,
        enabled=True,
    )


def test_disabled_middleware_is_noop():
    mw = X402Middleware(recipient_address=RECIPIENT, network=NETWORK, asset=ASSET, enabled=False)
    allowed, body, _ = mw.gate("http://x/", 0.01, header_value=None)
    assert allowed
    assert body is None


def test_enabled_without_config_fails_closed():
    mw = X402Middleware(recipient_address="", network=NETWORK, asset="", enabled=True)
    allowed, body, _ = mw.gate("http://x/", 0.01, header_value="whatever")
    assert not allowed
    assert body["error"]


def test_missing_header_returns_402(mw: X402Middleware):
    allowed, body, _ = mw.gate("http://x/api/premium", 0.01, header_value=None)
    assert not allowed
    assert body["x402Version"] == 1
    assert len(body["accepts"]) == 1
    req = body["accepts"][0]
    assert req["payTo"] == RECIPIENT
    assert req["network"] == NETWORK
    assert req["asset"] == ASSET
    assert req["maxAmountRequired"] == "10000"  # 0.01 USDC * 1e6


def test_valid_payment_is_accepted(mw: X402Middleware):
    header = _pay_header(10_000)
    allowed, body, result = mw.gate("http://x/api/premium", 0.01, header_value=header)
    assert allowed, (body, result)
    assert result is not None
    assert result.ok
    assert result.amount_atomic == 10_000
    assert result.payer == "0x2222222222222222222222222222222222222222"


def test_underpayment_rejected(mw: X402Middleware):
    header = _pay_header(5_000)  # 0.005 USDC < 0.01 required
    allowed, body, result = mw.gate("http://x/api/premium", 0.01, header_value=header)
    assert not allowed
    assert result is not None and not result.ok
    assert "amount" in result.reason.lower()


def test_wrong_recipient_rejected(mw: X402Middleware):
    header = _pay_header(10_000, recipient="0x9999999999999999999999999999999999999999")
    allowed, body, result = mw.gate("http://x/api/premium", 0.01, header_value=header)
    assert not allowed
    assert "payto" in result.reason.lower()


def test_wrong_network_rejected(mw: X402Middleware):
    header = _pay_header(10_000, network="ethereum")
    allowed, body, result = mw.gate("http://x/api/premium", 0.01, header_value=header)
    assert not allowed
    assert "network" in result.reason.lower()


def test_nonce_replay_rejected(mw: X402Middleware):
    header = _pay_header(10_000, nonce="replay-1")
    ok1, _, _ = mw.gate("http://x/api/premium", 0.01, header_value=header)
    ok2, body2, result2 = mw.gate("http://x/api/premium", 0.01, header_value=header)
    assert ok1
    assert not ok2
    assert "nonce" in body2["error"].lower()


def test_malformed_header_rejected(mw: X402Middleware):
    allowed, body, result = mw.gate("http://x/api/premium", 0.01, header_value="not-base64!!")
    assert not allowed
    assert result is not None and not result.ok


def test_build_requirements_math():
    mw = X402Middleware(recipient_address=RECIPIENT, network=NETWORK, asset=ASSET, enabled=True)
    req = mw.build_requirements("http://x/", 0.05)
    assert req.max_amount_required == "50000"  # 0.05 * 1e6


def test_mock_verifier_direct():
    v = MockVerifier()
    reqs = PaymentRequirements(
        scheme="exact", network=NETWORK, max_amount_required="10000",
        resource="http://x/", description="", mime_type="application/json",
        pay_to=RECIPIENT, max_timeout_seconds=60, asset=ASSET,
    )
    result = v.verify(_pay_header(15_000), reqs)
    assert result.ok
    assert result.amount_atomic == 15_000


def test_build_402_body_shape():
    req = PaymentRequirements(
        scheme="exact", network=NETWORK, max_amount_required="10000",
        resource="http://x/", description="d", mime_type="application/json",
        pay_to=RECIPIENT, max_timeout_seconds=60, asset=ASSET,
    )
    body = build_402_response([req])
    assert body["x402Version"] == 1
    assert body["accepts"][0]["scheme"] == "exact"
    assert body["accepts"][0]["maxAmountRequired"] == "10000"
