from __future__ import annotations

from services.customer_api.app import CustomerApiConfig, InMemoryRateLimiter, create_app


def _client():
    cfg = CustomerApiConfig(
        api_keys=frozenset({"demo"}),
        live_enabled=False,
        payment_infra_verified=False,
        rate_limit=20,
        rate_window_seconds=60,
    )
    return create_app(cfg, InMemoryRateLimiter(20, 60)).test_client()


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer demo"}


def test_health_is_public_and_mock() -> None:
    response = _client().get("/v1/health")
    assert response.status_code == 200
    assert response.json["ok"] is True
    assert response.json["mock"] is True
    assert response.headers["x-sapphire-billed"] == "0"


def test_threat_intel_route_returns_mock_payload() -> None:
    response = _client().get("/v1/threat-intel", headers=_headers())
    assert response.status_code == 200
    assert response.json["mock"] is True
    assert response.json["product"] == "threat-intel"
    assert response.json["signals"]


def test_narrative_route_returns_customer_safe_payload() -> None:
    response = _client().get("/v1/narrative", headers=_headers())
    assert response.status_code == 200
    assert response.json["mock"] is True
    assert response.json["customer_safe"] is True


def test_cross_asset_route_returns_mock_correlations() -> None:
    response = _client().get("/v1/cross-asset", headers=_headers())
    assert response.status_code == 200
    assert response.json["mock"] is True
    assert response.json["correlations"][0]["pair"] == "BTC/SPY"


def test_private_beta_request_is_stub_only_and_not_stored() -> None:
    response = _client().post(
        "/v1/private-beta/request",
        json={"email": "person@example.com", "product": "narrative"},
        headers=_headers(),
    )
    assert response.status_code == 202
    assert response.json["mock"] is True
    assert response.json["accepted"] is False
    assert response.json["status"] == "stub_only"
