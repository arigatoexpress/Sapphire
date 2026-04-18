"""Payment rails for Sapphire APIs.

x402 (Coinbase) — HTTP 402 micropayment middleware for monetizing endpoints.
"""

from .x402_middleware import (
    MockVerifier,
    PaymentRequirements,
    PaymentVerificationResult,
    PaymentVerifier,
    X402Middleware,
    build_402_response,
    require_payment,
)

__all__ = [
    "PaymentRequirements",
    "PaymentVerificationResult",
    "PaymentVerifier",
    "MockVerifier",
    "X402Middleware",
    "build_402_response",
    "require_payment",
]
