"""Isolated unit tests for ``lib.payments``.

The existing ``test_x402_middleware.py`` and ``test_x402_flask.py`` are
end-to-end integration suites. This module is the focused isolated suite
acquirers can map to a single library: ``lib.payments.x402_middleware``.

Coverage is kept tight on the library's *public* surface and on under-tested
defensive branches: env-var configuration, the bounded LRU's eviction
boundary, the singleton helper, and a few wire-shape invariants the
existing suite leans on but doesn't assert directly.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import pytest

from lib.payments.x402_middleware import (
    DEFAULT_USDC_CONTRACTS,
    MockVerifier,
    PaymentRequirements,
    PaymentVerificationResult,
    X402Middleware,
    _BoundedLRU,
    build_402_response,
    get_default_middleware,
)

RECIPIENT = "0xCAFE000000000000000000000000000000000000"
NETWORK = "base-sepolia"
ASSET = DEFAULT_USDC_CONTRACTS[NETWORK]


def _b64_payload(**fields: Any) -> str:
    payload = {
        "payload": {
            "amount": fields.get("amount", 10_000),
            "payTo": fields.get("payTo", RECIPIENT),
            "asset": fields.get("asset", ASSET),
            "network": fields.get("network", NETWORK),
            "from": fields.get("from_addr", "0xPAYER"),
            "txHash": fields.get("txHash", "0xdeadbeef"),
            "nonce": fields.get("nonce", "n1"),
        },
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


# ---------------------------------------------------------------------------
# Wire shape and dataclass invariants
# ---------------------------------------------------------------------------


class TestPaymentRequirementsWire:
    def test_to_wire_uses_camel_case(self) -> None:
        req = PaymentRequirements(
            scheme="exact",
            network=NETWORK,
            max_amount_required="10000",
            resource="https://x.test/p",
            description="premium",
            mime_type="application/json",
            pay_to=RECIPIENT,
            max_timeout_seconds=60,
            asset=ASSET,
            extra={"currency": "USDC"},
        )
        wire = req.to_wire()
        # Every camelCase field x402 expects must be present.
        for key in (
            "scheme",
            "network",
            "maxAmountRequired",
            "resource",
            "description",
            "mimeType",
            "payTo",
            "maxTimeoutSeconds",
            "asset",
            "extra",
        ):
            assert key in wire
        assert wire["maxAmountRequired"] == "10000"
        assert wire["payTo"] == RECIPIENT

    def test_build_402_response_shape(self) -> None:
        req = PaymentRequirements(
            scheme="exact",
            network=NETWORK,
            max_amount_required="10000",
            resource="https://x.test/p",
            description="",
            mime_type="application/json",
            pay_to=RECIPIENT,
            max_timeout_seconds=60,
            asset=ASSET,
        )
        body = build_402_response([req], error="Need payment")
        assert body["x402Version"] == 1
        assert body["error"] == "Need payment"
        assert isinstance(body["accepts"], list)
        assert body["accepts"][0]["payTo"] == RECIPIENT


# ---------------------------------------------------------------------------
# MockVerifier
# ---------------------------------------------------------------------------


class TestMockVerifier:
    def _reqs(self) -> PaymentRequirements:
        return PaymentRequirements(
            scheme="exact",
            network=NETWORK,
            max_amount_required="10000",
            resource="https://x.test/p",
            description="",
            mime_type="application/json",
            pay_to=RECIPIENT,
            max_timeout_seconds=60,
            asset=ASSET,
        )

    def test_empty_header_rejected(self) -> None:
        result = MockVerifier().verify("", self._reqs())
        assert result.ok is False
        assert "missing" in result.reason.lower()

    def test_garbage_base64_rejected(self) -> None:
        result = MockVerifier().verify("not-base64$$$", self._reqs())
        assert result.ok is False
        assert (
            "bad base64" in result.reason.lower()
            or "json" in result.reason.lower()
        )

    def test_amount_alias_value_field(self) -> None:
        # The verifier accepts `value` as a fallback alias for `amount`.
        payload = {
            "payload": {
                "value": 10_000,
                "payTo": RECIPIENT,
                "asset": ASSET,
                "network": NETWORK,
            }
        }
        header = base64.b64encode(json.dumps(payload).encode()).decode()
        result = MockVerifier().verify(header, self._reqs())
        assert result.ok is True

    def test_non_integer_amount_rejected(self) -> None:
        payload = {"payload": {"amount": "abc", "payTo": RECIPIENT, "asset": ASSET}}
        header = base64.b64encode(json.dumps(payload).encode()).decode()
        result = MockVerifier().verify(header, self._reqs())
        assert result.ok is False
        assert "integer" in result.reason.lower()

    def test_nested_payload_extracts_payer(self) -> None:
        # Defensive branch the integration suite skips: payload may carry a
        # `payer` field instead of `from`.
        payload = {
            "payload": {
                "amount": 10_000,
                "payTo": RECIPIENT,
                "asset": ASSET,
                "network": NETWORK,
                "payer": "0xpayer-via-payer-key",
            }
        }
        header = base64.b64encode(json.dumps(payload).encode()).decode()
        result = MockVerifier().verify(header, self._reqs())
        assert result.payer == "0xpayer-via-payer-key"


# ---------------------------------------------------------------------------
# _BoundedLRU
# ---------------------------------------------------------------------------


class TestBoundedLRU:
    def test_remembers_seen_key(self) -> None:
        lru = _BoundedLRU(maxsize=4)
        assert lru.seen("a") is False
        assert lru.seen("a") is True

    def test_evicts_oldest_when_full(self) -> None:
        lru = _BoundedLRU(maxsize=2)
        lru.seen("a")
        lru.seen("b")
        lru.seen("c")  # inserts 'c', evicts 'a' (first-in)
        # 'a' was evicted; 'b' and 'c' remain.
        # Inspecting the keys directly avoids the "seen() also mutates state"
        # issue that any read-then-check approach has on this LRU.
        assert "a" not in lru._d
        assert "b" in lru._d
        assert "c" in lru._d

    def test_lru_promotion_on_repeat_access(self) -> None:
        lru = _BoundedLRU(maxsize=3)
        lru.seen("a")
        lru.seen("b")
        lru.seen("c")
        # Re-accessing 'a' moves it to the end (most-recently-used).
        assert lru.seen("a") is True
        keys_after_promote = list(lru._d)
        # 'a' is now at the end; 'b' is the oldest.
        assert keys_after_promote[-1] == "a"
        assert keys_after_promote[0] == "b"
        # Inserting a new key should evict 'b', not 'a'.
        lru.seen("d")
        assert "b" not in lru._d
        assert "a" in lru._d


# ---------------------------------------------------------------------------
# X402Middleware orchestration
# ---------------------------------------------------------------------------


class TestX402MiddlewareCoreFlow:
    def _enabled(self) -> X402Middleware:
        return X402Middleware(
            recipient_address=RECIPIENT,
            pricing={"/api/premium": 0.01},
            network=NETWORK,
            asset=ASSET,
            enabled=True,
        )

    def test_disabled_short_circuits_through_gate(self) -> None:
        mw = X402Middleware(
            recipient_address=RECIPIENT,
            network=NETWORK,
            asset=ASSET,
            enabled=False,
        )
        allowed, body, result = mw.gate("https://x.test/p", 0.01, header_value="X")
        assert allowed is True
        assert body is None
        assert result is None

    def test_enabled_without_recipient_fails_closed(self) -> None:
        mw = X402Middleware(
            recipient_address="",  # configuration miss
            network=NETWORK,
            asset=ASSET,
            enabled=True,
        )
        allowed, body, result = mw.gate("https://x.test/p", 0.01, header_value=None)
        assert allowed is False
        assert "not configured" in body["error"].lower()

    def test_underpayment_returns_402_body_with_reason(self) -> None:
        mw = self._enabled()
        header = _b64_payload(amount=1)
        allowed, body, _ = mw.gate("https://x.test/p", 0.01, header_value=header)
        assert allowed is False
        assert "amount" in body["error"].lower()

    def test_set_price_and_price_for_round_trip(self) -> None:
        mw = self._enabled()
        mw.set_price("/api/v2", 0.05)
        assert mw.price_for("/api/v2") == 0.05

    def test_build_requirements_uses_six_decimal_atomic_units(self) -> None:
        mw = self._enabled()
        req = mw.build_requirements("https://x.test/p", 1.234567)
        # USDC has 6 decimals — 1.234567 USDC → 1_234_567 atomic units.
        assert req.max_amount_required == "1234567"

    def test_custom_verifier_replaces_mock(self) -> None:
        called: list[str] = []

        class _Spy:
            def verify(
                self, header_value: str, requirements: PaymentRequirements
            ) -> PaymentVerificationResult:
                called.append(header_value)
                return PaymentVerificationResult(ok=True, payer="0xspy", amount_atomic=10_000)

        mw = X402Middleware(
            recipient_address=RECIPIENT,
            network=NETWORK,
            asset=ASSET,
            enabled=True,
            verifier=_Spy(),
        )
        allowed, _, result = mw.gate("https://x.test/p", 0.01, header_value="anything")
        assert allowed is True
        assert called == ["anything"]
        assert result is not None and result.payer == "0xspy"

    def test_nonce_replay_rejected_on_second_attempt(self) -> None:
        mw = self._enabled()
        header = _b64_payload(amount=10_000, nonce="dup-1")
        first = mw.gate("https://x.test/p", 0.01, header_value=header)
        second = mw.gate("https://x.test/p", 0.01, header_value=header)
        assert first[0] is True
        assert second[0] is False
        assert "nonce" in second[1]["error"].lower()


class TestX402MiddlewareEnvConfig:
    def test_picks_default_asset_when_network_unspecified(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("X402_NETWORK", raising=False)
        monkeypatch.delenv("X402_ASSET", raising=False)
        monkeypatch.setenv("X402_RECIPIENT", RECIPIENT)
        mw = X402Middleware(enabled=True)
        # Defaults to base-sepolia → asset is the sepolia USDC contract.
        assert mw.asset == DEFAULT_USDC_CONTRACTS["base-sepolia"]

    def test_disabled_by_default_via_missing_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("X402_ENABLED", raising=False)
        mw = X402Middleware()
        assert mw.enabled is False

    def test_explicit_constructor_args_override_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("X402_NETWORK", "base")
        # Explicit override wins.
        mw = X402Middleware(network="base-sepolia", recipient_address=RECIPIENT)
        assert mw.network == "base-sepolia"


class TestDefaultMiddlewareSingleton:
    def test_default_middleware_returns_same_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Reset the module-level cache before testing the singleton.
        from lib.payments import x402_middleware as mod

        monkeypatch.setattr(mod, "_DEFAULT_MIDDLEWARE", None)
        a = get_default_middleware()
        b = get_default_middleware()
        assert a is b


__all__ = [
    "TestBoundedLRU",
    "TestDefaultMiddlewareSingleton",
    "TestMockVerifier",
    "TestPaymentRequirementsWire",
    "TestX402MiddlewareCoreFlow",
    "TestX402MiddlewareEnvConfig",
]
