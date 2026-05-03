"""Customer-facing Sapphire API.

The service is intentionally demo-safe by default: mock payloads, demo keys,
in-memory rate limits, and x402 billing headers that always report zero billed
unless a future live payment layer is explicitly wired and verified.
"""

from __future__ import annotations

import os
import secrets
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any

from flask import Flask, Response, current_app, jsonify, make_response, request

DEMO_KEYS = frozenset(
    {
        "sapphire_demo_public",
        "sapphire_demo_partner",
        "sapphire_beta_demo",
    }
)
LIVE_DATA_ERROR = "real customer data is disabled for this API surface"


@dataclass(frozen=True)
class CustomerApiConfig:
    api_keys: frozenset[str]
    live_enabled: bool
    payment_infra_verified: bool
    rate_limit: int
    rate_window_seconds: int

    @classmethod
    def from_env(cls) -> CustomerApiConfig:
        raw_keys = os.getenv("SAPPHIRE_CUSTOMER_API_KEYS", "")
        keys = {k.strip() for k in raw_keys.split(",") if k.strip()}
        if not keys:
            keys = set(DEMO_KEYS)
        return cls(
            api_keys=frozenset(keys),
            live_enabled=_truthy(os.getenv("SAPPHIRE_CUSTOMER_API_LIVE", "")),
            payment_infra_verified=_truthy(
                os.getenv("SAPPHIRE_CUSTOMER_PAYMENT_INFRA_VERIFIED", "")
            ),
            rate_limit=int(os.getenv("SAPPHIRE_CUSTOMER_API_RATE_LIMIT", "60")),
            rate_window_seconds=int(os.getenv("SAPPHIRE_CUSTOMER_API_RATE_WINDOW_SECONDS", "60")),
        )


class InMemoryRateLimiter:
    """Small process-local sliding-window limiter keyed by caller id."""

    def __init__(self, limit: int, window_seconds: int, clock: Callable[[], float] = time.time):
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> tuple[bool, int, int]:
        now = self.clock()
        bucket = self._hits.setdefault(key, deque())
        cutoff = now - self.window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= self.limit:
            retry_after = max(1, int(bucket[0] + self.window_seconds - now))
            return False, 0, retry_after
        bucket.append(now)
        return True, self.limit - len(bucket), 0


def create_app(
    config: CustomerApiConfig | None = None,
    limiter: InMemoryRateLimiter | None = None,
) -> Flask:
    cfg = config or CustomerApiConfig.from_env()
    app = Flask(__name__)
    app.config["CUSTOMER_API_CONFIG"] = cfg
    app.config["CUSTOMER_API_LIMITER"] = limiter or InMemoryRateLimiter(
        cfg.rate_limit, cfg.rate_window_seconds
    )

    @app.after_request
    def _demo_billing_header(response: Response) -> Response:
        response.headers.setdefault("x-sapphire-billed", "0")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.get("/v1/health")
    def health() -> Response:
        return jsonify(
            {
                "ok": True,
                "service": "customer-api",
                "version": "0.1.0",
                "mock": True,
                "live_enabled": cfg.live_enabled,
                "payment_infra_verified": cfg.payment_infra_verified,
            }
        )

    @app.get("/v1/threat-intel")
    @customer_guard
    def threat_intel() -> Response:
        blocked = _reject_live_data_request()
        if blocked:
            return blocked
        return jsonify(
            {
                "mock": True,
                "product": "threat-intel",
                "generated_at": "2026-04-28T00:00:00Z",
                "summary": "Mock Sapphire threat sweep for demo integration.",
                "signals": [
                    {
                        "id": "mock-ti-001",
                        "severity": "medium",
                        "title": "Credential phishing kit chatter increased",
                        "recommended_action": "Rotate demo tokens and confirm MFA posture.",
                    },
                    {
                        "id": "mock-ti-002",
                        "severity": "low",
                        "title": "Typosquat domain watchlist changed",
                        "recommended_action": "Review candidate domains before launch.",
                    },
                ],
                "sources": ["mock:cisa", "mock:vendor-bulletin", "mock:telegram-intel"],
            }
        )

    @app.get("/v1/narrative")
    @customer_guard
    def narrative() -> Response:
        blocked = _reject_live_data_request()
        if blocked:
            return blocked
        return jsonify(
            {
                "mock": True,
                "product": "narrative",
                "thesis": "Risk appetite is neutral while security and liquidity narratives diverge.",
                "drivers": [
                    {"label": "security", "direction": "caution", "confidence": 0.72},
                    {"label": "liquidity", "direction": "supportive", "confidence": 0.64},
                    {"label": "macro", "direction": "mixed", "confidence": 0.58},
                ],
                "customer_safe": True,
            }
        )

    @app.get("/v1/cross-asset")
    @customer_guard
    def cross_asset() -> Response:
        blocked = _reject_live_data_request()
        if blocked:
            return blocked
        return jsonify(
            {
                "mock": True,
                "product": "cross-asset",
                "window": "7d",
                "correlations": [
                    {"pair": "BTC/SPY", "rho": 0.31, "regime": "loose"},
                    {"pair": "ETH/NVDA", "rho": 0.44, "regime": "tightening"},
                    {"pair": "SOL/DXY", "rho": -0.28, "regime": "inverse"},
                ],
                "note": "Static demo output; not investment advice.",
            }
        )

    @app.post("/v1/private-beta/request")
    @customer_guard
    def private_beta_request() -> Response:
        payload = request.get_json(silent=True) or {}
        requested_product = str(payload.get("product", "customer-api"))[:80]
        return (
            jsonify(
                {
                    "mock": True,
                    "accepted": False,
                    "status": "stub_only",
                    "message": "Private beta requests are not stored by this demo service.",
                    "requested_product": requested_product,
                }
            ),
            202,
        )

    return app


def customer_guard(fn: Callable[..., Any]) -> Callable[..., Response]:
    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Response:
        cfg: CustomerApiConfig = current_app.config["CUSTOMER_API_CONFIG"]
        limiter: InMemoryRateLimiter = current_app.config["CUSTOMER_API_LIMITER"]

        key = _extract_api_key()
        if not key or not any(secrets.compare_digest(key, allowed) for allowed in cfg.api_keys):
            return _json_error("unauthorized", "demo API key required", 401)

        if cfg.live_enabled and not cfg.payment_infra_verified:
            return _json_error(
                "payment_infra_unverified",
                "live mode refuses requests until payment infrastructure is verified",
                503,
            )

        allowed, remaining, retry_after = limiter.check(key)
        if not allowed:
            response = _json_error("rate_limited", "rate limit exceeded", 429)
            response.headers["Retry-After"] = str(retry_after)
            response.headers["X-RateLimit-Remaining"] = "0"
            return response

        response = make_response(fn(*args, **kwargs))
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    return wrapper


def _extract_api_key() -> str:
    bearer = request.headers.get("Authorization", "")
    if bearer.lower().startswith("bearer "):
        return bearer[7:].strip()
    return request.headers.get("X-Sapphire-API-Key", "").strip()


def _reject_live_data_request() -> Response | None:
    requested = request.headers.get("X-Sapphire-Data-Mode", "mock").strip().lower()
    if requested in {"live", "real", "customer"}:
        return _json_error("live_data_refused", LIVE_DATA_ERROR, 403)
    return None


def _json_error(code: str, message: str, status: int) -> Response:
    response = jsonify({"ok": False, "error": code, "message": message, "mock": True})
    response.status_code = status
    return response


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=9000)
