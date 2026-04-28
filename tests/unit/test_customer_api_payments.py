from __future__ import annotations

from services.customer_api.app import CustomerApiConfig, InMemoryRateLimiter, create_app


def _client(live: bool = False, payment_verified: bool = False):
    cfg = CustomerApiConfig(
        api_keys=frozenset({"demo"}),
        live_enabled=live,
        payment_infra_verified=payment_verified,
        rate_limit=20,
        rate_window_seconds=60,
    )
    return create_app(cfg, InMemoryRateLimiter(20, 60)).test_client()


def test_demo_requests_are_never_billed() -> None:
    response = _client().get("/v1/threat-intel", headers={"Authorization": "Bearer demo"})
    assert response.status_code == 200
    assert response.headers["x-sapphire-billed"] == "0"
    assert response.json["mock"] is True


def test_live_mode_with_verified_payment_still_returns_demo_billed_zero() -> None:
    response = _client(live=True, payment_verified=True).get(
        "/v1/cross-asset", headers={"Authorization": "Bearer demo"}
    )
    assert response.status_code == 200
    assert response.headers["x-sapphire-billed"] == "0"
    assert response.json["mock"] is True


def test_live_mode_without_verified_payment_fails_before_serving_payload() -> None:
    response = _client(live=True, payment_verified=False).get(
        "/v1/cross-asset", headers={"Authorization": "Bearer demo"}
    )
    assert response.status_code == 503
    assert response.headers["x-sapphire-billed"] == "0"
    assert response.json["error"] == "payment_infra_unverified"
