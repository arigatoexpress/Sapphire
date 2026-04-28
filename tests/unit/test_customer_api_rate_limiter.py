from __future__ import annotations

from services.customer_api.app import CustomerApiConfig, InMemoryRateLimiter, create_app


def test_rate_limiter_blocks_after_limit_and_reports_retry_after() -> None:
    now = [1000.0]

    def clock() -> float:
        return now[0]

    cfg = CustomerApiConfig(
        api_keys=frozenset({"demo"}),
        live_enabled=False,
        payment_infra_verified=False,
        rate_limit=2,
        rate_window_seconds=10,
    )
    limiter = InMemoryRateLimiter(2, 10, clock=clock)
    client = create_app(cfg, limiter).test_client()
    headers = {"Authorization": "Bearer demo"}

    assert client.get("/v1/cross-asset", headers=headers).status_code == 200
    assert client.get("/v1/cross-asset", headers=headers).status_code == 200
    blocked = client.get("/v1/cross-asset", headers=headers)
    assert blocked.status_code == 429
    assert blocked.headers["Retry-After"] == "10"
    assert blocked.headers["X-RateLimit-Remaining"] == "0"


def test_rate_limiter_window_expires() -> None:
    now = [1000.0]

    def clock() -> float:
        return now[0]

    limiter = InMemoryRateLimiter(1, 10, clock=clock)
    assert limiter.check("k") == (True, 0, 0)
    assert limiter.check("k")[0] is False
    now[0] = 1011.0
    assert limiter.check("k") == (True, 0, 0)
