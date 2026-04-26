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


# ---------------------------------------------------------------------------
# Additional coverage — wire shape, custom verifiers, BoundedLRU, env defaults
# ---------------------------------------------------------------------------


def test_wrong_asset_rejected(mw: X402Middleware):
    """If the payload's asset doesn't match the gate's, verifier must reject."""
    header = _pay_header(10_000, asset="0x0000000000000000000000000000000000000000")
    allowed, _body, result = mw.gate("http://x/api/premium", 0.01, header_value=header)
    assert not allowed
    assert result is not None and not result.ok
    assert "asset" in result.reason.lower()


def test_empty_string_header_rejected(mw: X402Middleware):
    """An empty X-PAYMENT header should produce a 402, not crash, not pass."""
    allowed, body, _result = mw.gate("http://x/api/premium", 0.01, header_value="")
    assert not allowed
    # Empty header is treated like missing — the body still advertises requirements
    assert isinstance(body, dict)
    assert body["x402Version"] == 1
    assert len(body["accepts"]) == 1


def test_payment_without_nonce_passes_but_no_replay_tracking(mw: X402Middleware):
    """A payment without a `nonce` field is accepted, but identical replays
    cannot be detected (no key for the LRU). This documents current behaviour.
    """
    header = _pay_header(10_000, nonce=None)
    ok1, _, r1 = mw.gate("http://x/api/premium", 0.01, header_value=header)
    ok2, _, r2 = mw.gate("http://x/api/premium", 0.01, header_value=header)
    assert ok1 and ok2  # No nonce → no replay protection (documented behaviour)
    assert r1 is not None and r2 is not None
    assert r1.ok and r2.ok


def test_invalid_amount_field_rejected(mw: X402Middleware):
    """A non-integer amount value should fail with a clear reason, not crash."""
    payload = {
        "payload": {
            "amount": "not-a-number",
            "payTo": RECIPIENT,
            "asset": ASSET,
            "network": NETWORK,
        }
    }
    header = base64.b64encode(json.dumps(payload).encode()).decode()
    allowed, _body, result = mw.gate("http://x/api/premium", 0.01, header_value=header)
    assert not allowed
    assert result is not None and not result.ok
    assert "amount" in result.reason.lower()


def test_to_wire_shape_matches_x402_protocol():
    """PaymentRequirements.to_wire() emits camelCase field names per spec."""
    req = PaymentRequirements(
        scheme="exact", network=NETWORK, max_amount_required="42",
        resource="https://api/example", description="d", mime_type="application/json",
        pay_to=RECIPIENT, max_timeout_seconds=60, asset=ASSET,
        extra={"currency": "USDC"},
    )
    wire = req.to_wire()
    assert wire["scheme"] == "exact"
    assert wire["maxAmountRequired"] == "42"
    assert wire["payTo"] == RECIPIENT
    assert wire["maxTimeoutSeconds"] == 60
    assert wire["mimeType"] == "application/json"
    assert wire["extra"] == {"currency": "USDC"}
    # Must NOT contain snake_case duplicates
    assert "max_amount_required" not in wire
    assert "pay_to" not in wire


def test_set_price_and_price_for_roundtrip():
    """set_price/price_for behave as a simple route→amount registry."""
    mw = X402Middleware(
        recipient_address=RECIPIENT, network=NETWORK, asset=ASSET, enabled=True,
    )
    assert mw.price_for("/x") is None
    mw.set_price("/x", 0.25)
    assert mw.price_for("/x") == 0.25
    mw.set_price("/x", 1.0)  # overwrite
    assert mw.price_for("/x") == 1.0


def test_custom_verifier_injection_short_circuits_mock():
    """A custom PaymentVerifier should fully replace MockVerifier."""

    class AlwaysOK:
        def verify(self, header_value, requirements):
            from lib.payments.x402_middleware import PaymentVerificationResult
            return PaymentVerificationResult(
                ok=True, payer="0xCAFE", amount_atomic=999, nonce="custom-1"
            )

    mw = X402Middleware(
        recipient_address=RECIPIENT, network=NETWORK, asset=ASSET,
        verifier=AlwaysOK(), enabled=True,
    )
    allowed, _body, result = mw.gate("http://x/", 0.01, header_value="anything")
    assert allowed
    assert result is not None
    assert result.payer == "0xCAFE"
    assert result.amount_atomic == 999


def test_bounded_lru_remembers_seen_keys_and_evicts_oldest():
    """_BoundedLRU.seen() returns False the first time a key is observed,
    True on subsequent calls; once `maxsize` is exceeded, the oldest key is
    evicted (so it returns False again, by design).
    """
    from lib.payments.x402_middleware import _BoundedLRU

    cache = _BoundedLRU(maxsize=3)
    # First time each key is offered, report False ("not seen").
    assert cache.seen("a") is False
    assert cache.seen("b") is False
    assert cache.seen("c") is False
    # All three are still in cache and report True on repeat.
    assert cache.seen("a") is True
    assert cache.seen("b") is True
    assert cache.seen("c") is True
    # Now LRU order is a, b, c (each was just bumped to end in turn).
    # Inserting "d" overflows the size-3 cache and evicts the LRU entry "a".
    assert cache.seen("d") is False
    assert cache.seen("a") is False  # evicted → treated as new


def test_bounded_lru_returns_true_on_repeat_within_capacity():
    """Repeated lookup of a key still in the cache always returns True."""
    from lib.payments.x402_middleware import _BoundedLRU

    cache = _BoundedLRU(maxsize=10)
    assert cache.seen("nonce-1") is False
    for _ in range(5):
        assert cache.seen("nonce-1") is True


def test_default_middleware_singleton(monkeypatch):
    """get_default_middleware() returns the same instance across calls."""
    import lib.payments.x402_middleware as mod

    # Reset module state so we get a fresh singleton built from current env
    monkeypatch.setattr(mod, "_DEFAULT_MIDDLEWARE", None)
    a = mod.get_default_middleware()
    b = mod.get_default_middleware()
    assert a is b


def test_middleware_disabled_by_default_via_env(monkeypatch):
    """Without X402_ENABLED=1, a freshly built middleware is a passthrough."""
    monkeypatch.delenv("X402_ENABLED", raising=False)
    monkeypatch.setenv("X402_RECIPIENT", RECIPIENT)
    mw = X402Middleware()
    allowed, body, _ = mw.gate("http://x/", 0.01, header_value=None)
    assert allowed
    assert body is None
    assert mw.enabled is False


def test_middleware_picks_default_asset_for_known_network(monkeypatch):
    """When X402_ASSET isn't set, the constructor uses DEFAULT_USDC_CONTRACTS."""
    monkeypatch.delenv("X402_ASSET", raising=False)
    monkeypatch.setenv("X402_NETWORK", "base")
    mw = X402Middleware(recipient_address=RECIPIENT)
    assert mw.asset == DEFAULT_USDC_CONTRACTS["base"]


def test_amount_in_value_field_alias():
    """MockVerifier accepts `value` as a fallback for `amount` for compat."""
    payload = {
        "payload": {
            "value": 25_000,  # not "amount"
            "payTo": RECIPIENT,
            "asset": ASSET,
            "network": NETWORK,
            "from": "0xabc",
            "nonce": "v1",
        }
    }
    header = base64.b64encode(json.dumps(payload).encode()).decode()
    v = MockVerifier()
    reqs = PaymentRequirements(
        scheme="exact", network=NETWORK, max_amount_required="10000",
        resource="http://x/", description="", mime_type="application/json",
        pay_to=RECIPIENT, max_timeout_seconds=60, asset=ASSET,
    )
    result = v.verify(header, reqs)
    assert result.ok
    assert result.amount_atomic == 25_000


def test_payer_field_recovered_deterministically_from_payload(mw: X402Middleware):
    """Smoke test for the 'recovered' payer surface — given a known payload,
    the verification result reports the same payer string deterministically.

    NOTE: production deployments substitute MockVerifier with an SDK-backed
    verifier that does real ECDSA recovery against the message. The contract
    here is that whatever verifier is plugged in, its `payer` field is what
    the middleware exposes downstream (audit, event bus, telemetry).
    """
    header = _pay_header(10_000, nonce="payer-recovery-1")
    allowed, _body, result = mw.gate("http://x/", 0.01, header_value=header)
    assert allowed
    assert result is not None
    assert result.payer == "0x2222222222222222222222222222222222222222"
    # Calling again with the same payload (different nonce to bypass replay)
    # must yield the same payer recovery — i.e. the function is deterministic.
    header2 = _pay_header(10_000, nonce="payer-recovery-2")
    _ok, _body, result2 = mw.gate("http://x/", 0.01, header_value=header2)
    assert result2 is not None
    assert result.payer == result2.payer
