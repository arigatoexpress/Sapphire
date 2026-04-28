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


def test_customer_routes_require_demo_key() -> None:
    response = _client().get("/v1/narrative")
    assert response.status_code == 401
    assert response.json["error"] == "unauthorized"


def test_customer_routes_reject_unknown_key() -> None:
    response = _client().get("/v1/narrative", headers={"X-Sapphire-API-Key": "wrong"})
    assert response.status_code == 401
    assert response.json["error"] == "unauthorized"


def test_customer_routes_accept_x_sapphire_api_key() -> None:
    response = _client().get("/v1/narrative", headers={"X-Sapphire-API-Key": "demo"})
    assert response.status_code == 200


def test_live_mode_refuses_without_payment_infra() -> None:
    response = _client(live=True, payment_verified=False).get(
        "/v1/narrative", headers={"Authorization": "Bearer demo"}
    )
    assert response.status_code == 503
    assert response.json["error"] == "payment_infra_unverified"


def test_real_customer_data_header_refused_even_with_valid_key() -> None:
    response = _client().get(
        "/v1/narrative",
        headers={
            "Authorization": "Bearer demo",
            "X-Sapphire-Data-Mode": "live",
        },
    )
    assert response.status_code == 403
    assert response.json["error"] == "live_data_refused"
