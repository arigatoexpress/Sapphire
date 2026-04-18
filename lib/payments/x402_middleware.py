"""x402 HTTP 402 payment middleware for Sapphire APIs.

Implements the x402 protocol (github.com/coinbase/x402) as a framework-agnostic
core plus a Flask decorator. Produces correctly-shaped 402 responses, accepts
the `X-PAYMENT` / `PAYMENT-SIGNATURE` header, and delegates cryptographic
verification to a pluggable `PaymentVerifier`.

Design
------
- Core types (`PaymentRequirements`, `PaymentVerificationResult`) model the
  protocol payload so the same types are reusable across Flask, a raw
  `BaseHTTPRequestHandler` (inference proxy), or FastAPI.
- `PaymentVerifier` is a Protocol with a single `verify()` method. The default
  `MockVerifier` accepts any base64 payload whose inner JSON references the
  expected recipient/asset/network — enough to drive tests and testnet flows
  without hitting a facilitator. For production, plug in an SDK-backed
  verifier that calls Coinbase's facilitator or a Base JSON-RPC node.
- `X402Middleware` is a small orchestrator: owns the route→price table,
  holds the verifier, emits events on the Sapphire event bus, and enforces
  a bounded nonce cache to prevent payment replay.
- `require_payment(...)` is a Flask decorator built on top of the middleware.

Env vars
--------
- ``X402_ENABLED`` — when unset or "0", the decorator is a no-op. Default OFF.
- ``X402_NETWORK`` — "base" | "base-sepolia". Default "base-sepolia".
- ``X402_RECIPIENT`` — the USDC recipient address (0x...).
- ``X402_ASSET`` — USDC contract address on the chosen network.
- ``X402_FACILITATOR_URL`` — optional Coinbase facilitator URL for verification.

Event bus
---------
- ``payment.required`` — published when a 402 is returned.
- ``payment.received`` — published on successful verification.
- ``payment.rejected`` — published when a payment header fails verification.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys as _sys
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Protocol

log = logging.getLogger(__name__)

# Event bus (optional — middleware works without it). Adding lib/core to sys.path
# dynamically keeps this module importable from any working directory.
_EVT_PATH = Path(__file__).resolve().parents[1] / "core"
if str(_EVT_PATH) not in _sys.path:
    _sys.path.insert(0, str(_EVT_PATH))
try:
    from event_bus import get_bus as _get_bus
    _BUS = _get_bus(source="x402")
except Exception:  # pragma: no cover — optional
    _BUS = None


# ---------------------------------------------------------------------------
# Protocol types — match x402 spec shape
# ---------------------------------------------------------------------------


# Network → USDC contract address (mainnet + testnet defaults).
# Callers can override via `X402_ASSET` env or explicit constructor arg.
DEFAULT_USDC_CONTRACTS = {
    "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "base-sepolia": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
}


@dataclass
class PaymentRequirements:
    """A single accepted payment option advertised in the 402 response."""

    scheme: str                  # "exact" — the only scheme we support today
    network: str                 # "base" or "base-sepolia"
    max_amount_required: str     # string-encoded integer, atomic units (USDC: 6dp)
    resource: str                # absolute URL of the resource being paid for
    description: str
    mime_type: str
    pay_to: str                  # 0x... recipient address
    max_timeout_seconds: int
    asset: str                   # ERC-20 contract address (USDC)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "network": self.network,
            "maxAmountRequired": self.max_amount_required,
            "resource": self.resource,
            "description": self.description,
            "mimeType": self.mime_type,
            "payTo": self.pay_to,
            "maxTimeoutSeconds": self.max_timeout_seconds,
            "asset": self.asset,
            "extra": self.extra,
        }


@dataclass
class PaymentVerificationResult:
    ok: bool
    reason: str = ""
    payer: str | None = None
    tx_hash: str | None = None
    amount_atomic: int | None = None
    nonce: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)


class PaymentVerifier(Protocol):
    """Verifies an x402 payment payload against expected requirements."""

    def verify(
        self,
        header_value: str,
        requirements: PaymentRequirements,
    ) -> PaymentVerificationResult: ...


# ---------------------------------------------------------------------------
# MockVerifier — for tests and local/testnet use without a facilitator
# ---------------------------------------------------------------------------


class MockVerifier:
    """Accepts a payment if its payload JSON has matching recipient/asset/network
    and an amount >= the required amount. Designed for test flows and local
    development; **never** use in production without a real verifier.
    """

    def verify(
        self,
        header_value: str,
        requirements: PaymentRequirements,
    ) -> PaymentVerificationResult:
        if not header_value:
            return PaymentVerificationResult(ok=False, reason="missing header")
        try:
            raw = base64.b64decode(header_value).decode("utf-8")
            payload = json.loads(raw)
        except Exception as e:
            return PaymentVerificationResult(ok=False, reason=f"bad base64/json: {e}")

        p = payload.get("payload", payload)
        try:
            amount = int(p.get("amount", p.get("value", 0)))
        except (TypeError, ValueError):
            return PaymentVerificationResult(ok=False, reason="amount not an integer")

        required = int(requirements.max_amount_required)
        if amount < required:
            return PaymentVerificationResult(
                ok=False, reason=f"amount {amount} < required {required}"
            )
        if (p.get("payTo") or "").lower() != requirements.pay_to.lower():
            return PaymentVerificationResult(ok=False, reason="payTo mismatch")
        if (p.get("asset") or "").lower() != requirements.asset.lower():
            return PaymentVerificationResult(ok=False, reason="asset mismatch")
        if p.get("network") and p["network"] != requirements.network:
            return PaymentVerificationResult(ok=False, reason="network mismatch")

        return PaymentVerificationResult(
            ok=True,
            payer=p.get("from") or p.get("payer"),
            tx_hash=p.get("txHash"),
            amount_atomic=amount,
            nonce=p.get("nonce"),
            raw=payload,
        )


# ---------------------------------------------------------------------------
# 402 response builder (framework-agnostic)
# ---------------------------------------------------------------------------


def build_402_response(
    requirements: list[PaymentRequirements],
    error: str = "X-PAYMENT header is required",
) -> dict[str, Any]:
    """Produce the JSON body of an HTTP 402 response."""
    return {
        "x402Version": 1,
        "accepts": [r.to_wire() for r in requirements],
        "error": error,
    }


# ---------------------------------------------------------------------------
# X402Middleware — orchestrator with nonce cache + bus integration
# ---------------------------------------------------------------------------


class _BoundedLRU:
    """A tiny bounded LRU used as the nonce-seen cache."""

    def __init__(self, maxsize: int = 10_000) -> None:
        self._d: OrderedDict[str, float] = OrderedDict()
        self._max = maxsize
        self._lock = threading.Lock()

    def seen(self, key: str) -> bool:
        with self._lock:
            if key in self._d:
                self._d.move_to_end(key)
                return True
            self._d[key] = time.time()
            while len(self._d) > self._max:
                self._d.popitem(last=False)
            return False


class X402Middleware:
    """Wraps any Sapphire endpoint with an HTTP 402 payment gate."""

    def __init__(
        self,
        recipient_address: str | None = None,
        pricing: dict[str, float] | None = None,
        *,
        network: str | None = None,
        asset: str | None = None,
        verifier: PaymentVerifier | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.network = network or os.environ.get("X402_NETWORK", "base-sepolia")
        self.recipient = recipient_address or os.environ.get("X402_RECIPIENT", "")
        self.asset = asset or os.environ.get(
            "X402_ASSET", DEFAULT_USDC_CONTRACTS.get(self.network, "")
        )
        self.pricing = dict(pricing or {})
        if enabled is None:
            enabled = os.environ.get("X402_ENABLED", "0") == "1"
        self.enabled = enabled
        self.verifier: PaymentVerifier = verifier or MockVerifier()
        self._nonces = _BoundedLRU(maxsize=10_000)
        self._configured_ok = bool(self.recipient) and bool(self.asset)

        if self.enabled and not self._configured_ok:
            log.warning(
                "X402_ENABLED=1 but recipient or asset not configured — middleware "
                "will deny all paid requests until configured."
            )

    # ── Configuration ────────────────────────────────────────────────────────

    def set_price(self, route: str, amount_usd: float) -> None:
        self.pricing[route] = amount_usd

    def price_for(self, route: str) -> float | None:
        return self.pricing.get(route)

    # ── Requirements construction ────────────────────────────────────────────

    def build_requirements(
        self, resource_url: str, amount_usd: float, description: str = ""
    ) -> PaymentRequirements:
        # USDC is 6-decimal. 1 USDC = 1_000_000 atomic units.
        atomic = int(round(amount_usd * 1_000_000))
        return PaymentRequirements(
            scheme="exact",
            network=self.network,
            max_amount_required=str(atomic),
            resource=resource_url,
            description=description or f"Sapphire API access — {resource_url}",
            mime_type="application/json",
            pay_to=self.recipient,
            max_timeout_seconds=60,
            asset=self.asset,
            extra={"currency": "USDC", "humanAmount": f"${amount_usd:.4f}"},
        )

    # ── Main entry point ─────────────────────────────────────────────────────

    def gate(
        self,
        resource_url: str,
        amount_usd: float,
        header_value: str | None,
        description: str = "",
    ) -> tuple[bool, dict[str, Any] | None, PaymentVerificationResult | None]:
        """Returns (allowed, response_body_if_blocked, verification_result).

        - allowed=True  → caller may serve the resource. verification_result may
                          be None when middleware is disabled.
        - allowed=False → caller must return HTTP 402 with response_body and
                          the `X-Payment-Required` header (already encoded in
                          the body's `accepts` field).
        """
        if not self.enabled:
            return True, None, None

        if not self._configured_ok:
            body = build_402_response(
                [], error="x402 is enabled but not configured on this server"
            )
            return False, body, None

        reqs = self.build_requirements(resource_url, amount_usd, description)

        if not header_value:
            self._emit("payment.required", {
                "resource": resource_url,
                "amount_usd": amount_usd,
                "network": self.network,
            })
            return False, build_402_response([reqs]), None

        result = self.verifier.verify(header_value, reqs)
        if not result.ok:
            self._emit("payment.rejected", {
                "resource": resource_url,
                "reason": result.reason,
                "payer": result.payer,
            })
            return False, build_402_response([reqs], error=f"payment invalid: {result.reason}"), result

        if result.nonce and self._nonces.seen(result.nonce):
            self._emit("payment.rejected", {
                "resource": resource_url,
                "reason": "nonce replay",
                "nonce": result.nonce,
            })
            return False, build_402_response([reqs], error="payment nonce already used"), result

        self._emit("payment.received", {
            "resource": resource_url,
            "amount_atomic": result.amount_atomic,
            "payer": result.payer,
            "tx_hash": result.tx_hash,
            "network": self.network,
        })
        return True, None, result

    # ── Event bus integration ────────────────────────────────────────────────

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if _BUS is None:
            return
        try:
            _BUS.publish(event_type, data)
        except Exception as e:  # pragma: no cover — defensive
            log.warning("x402 event publish failed: %s", e)


# ---------------------------------------------------------------------------
# Flask adapter
# ---------------------------------------------------------------------------


_DEFAULT_MIDDLEWARE: X402Middleware | None = None
_MIDDLEWARE_LOCK = threading.Lock()


def get_default_middleware() -> X402Middleware:
    global _DEFAULT_MIDDLEWARE
    with _MIDDLEWARE_LOCK:
        if _DEFAULT_MIDDLEWARE is None:
            _DEFAULT_MIDDLEWARE = X402Middleware()
        return _DEFAULT_MIDDLEWARE


def require_payment(
    amount_usd: float,
    *,
    description: str = "",
    middleware: X402Middleware | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Flask route decorator. Requires a valid x402 payment to proceed.

    Usage::

        @app.route('/api/premium')
        @require_payment(0.01, description='premium API')
        def premium():
            return jsonify(...)
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Imported lazily so the middleware module stays framework-free
            from flask import jsonify, request

            mw = middleware or get_default_middleware()
            header = request.headers.get("X-PAYMENT") or request.headers.get("PAYMENT-SIGNATURE")
            allowed, body, _ = mw.gate(
                resource_url=request.url,
                amount_usd=amount_usd,
                header_value=header,
                description=description,
            )
            if allowed:
                return fn(*args, **kwargs)
            # 402 Payment Required
            resp = jsonify(body)
            resp.status_code = 402
            resp.headers["X-Payment-Required"] = "true"
            return resp

        return wrapper

    return decorator


__all__ = [
    "PaymentRequirements",
    "PaymentVerificationResult",
    "PaymentVerifier",
    "MockVerifier",
    "X402Middleware",
    "build_402_response",
    "require_payment",
    "get_default_middleware",
    "DEFAULT_USDC_CONTRACTS",
]
