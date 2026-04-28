"""Tests for the free-tier on-chain provider clients.

Every HTTP call is monkey-patched against the *provider* module's
``http_get`` / ``http_post_json`` binding (because each provider does
``from ._common import http_get`` — a name capture at import time that
patching ``_common`` would not catch).
"""

from __future__ import annotations

import http.client
import json

import pytest

from lib.chain import sources
from lib.chain.providers import (
    BGeometricsClient,
    CoinAPIClient,
    CoinglassClient,
    DuneClient,
    SantimentClient,
    WhaleAlertClient,
    _common,
)
from lib.chain.providers import (
    bgeometrics as bg_mod,
)
from lib.chain.providers import (
    coinapi as coinapi_mod,
)
from lib.chain.providers import (
    coinglass as coinglass_mod,
)
from lib.chain.providers import (
    dune as dune_mod,
)
from lib.chain.providers import (
    santiment as santiment_mod,
)
from lib.chain.providers import (
    whale_alert as whale_mod,
)

# --- _common.get_env --------------------------------------------------------


def test_get_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("DOES_NOT_EXIST", raising=False)
    with pytest.raises(sources.SourceError):
        _common.get_env("DOES_NOT_EXIST")


# --- shared source HTTP helpers -------------------------------------------


def _clear_source_cache() -> None:
    with sources._cache_lock:
        sources._cache.clear()


def test_http_post_json_retries_incomplete_reads(monkeypatch):
    _clear_source_cache()
    monkeypatch.setattr(sources.time, "sleep", lambda _seconds: None)
    calls = 0

    def fake_request(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise http.client.IncompleteRead(b"{", 2)
        return 200, "OK", b'{"ok": true}'

    monkeypatch.setattr(sources, "_pooled_https_request", fake_request)
    out = sources._http_post_json("https://api.hyperliquid.xyz/info", {"type": "metaAndAssetCtxs"})

    assert out == {"ok": True}
    assert calls == 3


def test_http_post_json_returns_stale_cache_after_retry_exhaustion(monkeypatch):
    _clear_source_cache()
    monkeypatch.setattr(sources.time, "sleep", lambda _seconds: None)
    url = "https://api.hyperliquid.xyz/info"
    payload = {"type": "metaAndAssetCtxs"}
    cache_key = f"POST {url} {json.dumps(payload, sort_keys=True)}"
    stale = {"cached": True}

    with sources._cache_lock:
        sources._cache[cache_key] = (sources.time.monotonic() - sources.CACHE_TTL - 1, stale)

    def fake_request(*_args, **_kwargs):
        raise http.client.IncompleteRead(b"{", 2)

    monkeypatch.setattr(sources, "_pooled_https_request", fake_request)
    assert sources._http_post_json(url, payload) == stale


def test_coingecko_simple_prices_builds_snapshot_query(monkeypatch):
    captured = {}

    def fake_get(url, timeout=sources.DEFAULT_TIMEOUT):
        captured["url"] = url
        return {"bitcoin": {"usd": 100000, "usd_24h_change": 1.2}}

    monkeypatch.setattr(sources, "_http_get", fake_get)
    out = sources.CoinGeckoClient().simple_prices(["bitcoin", "bitcoin"])

    assert out["bitcoin"]["usd"] == 100000
    assert "/simple/price?" in captured["url"]
    assert "ids=bitcoin" in captured["url"]
    assert "include_24hr_change=true" in captured["url"]


def test_coingecko_trending_normalizes_coin_rows(monkeypatch):
    monkeypatch.setattr(
        sources,
        "_http_get",
        lambda *_args, **_kwargs: {
            "coins": [
                {
                    "item": {
                        "id": "hyperliquid",
                        "symbol": "hype",
                        "name": "Hyperliquid",
                        "market_cap_rank": 15,
                        "score": 0,
                    }
                }
            ]
        },
    )

    trending = sources.CoinGeckoClient().trending()

    assert trending[0].coin_id == "hyperliquid"
    assert trending[0].symbol == "HYPE"
    assert trending[0].market_cap_rank == 15


# --- BGeometrics -----------------------------------------------------------


def test_bgeometrics_uses_bearer_header(monkeypatch):
    monkeypatch.setenv("BGEOMETRICS_API_KEY", "bg-key")
    captured = {}

    def fake(url, *, headers=None, params=None, **_):
        captured.update(url=url, headers=dict(headers or {}))
        return {"metric": "mvrv", "value": 1.8}

    monkeypatch.setattr(bg_mod, "http_get", fake)
    out = BGeometricsClient().mvrv_z_score()
    assert out["value"] == 1.8
    assert captured["headers"]["Authorization"] == "Bearer bg-key"
    assert "mvrv_z_score" in captured["url"]


# --- Santiment -------------------------------------------------------------


def test_santiment_posts_graphql(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPPHIRE_SANTIMENT_LIVE", "1")
    monkeypatch.setenv("SANTIMENT_API_KEY", "s-key")
    monkeypatch.setenv("SAPPHIRE_ONCHAIN_USAGE_FILE", str(tmp_path / "usage.json"))
    captured = {}

    def fake(url, payload, *, headers=None, **_):
        captured.update(url=url, headers=dict(headers or {}), payload=payload)
        return {"data": {"getMetric": {"timeseriesData": []}}}

    monkeypatch.setattr(santiment_mod, "http_post_json", fake)
    SantimentClient().social_volume(
        slug="bitcoin", from_iso="2026-04-01T00:00:00Z", to_iso="2026-04-02T00:00:00Z"
    )
    assert captured["url"].endswith("/graphql")
    assert captured["headers"]["Authorization"] == "Apikey s-key"
    assert captured["payload"]["variables"]["metric"] == "social_volume_total"


def test_santiment_fixture_mode_does_not_post(monkeypatch):
    monkeypatch.delenv("SAPPHIRE_SANTIMENT_LIVE", raising=False)
    monkeypatch.delenv("SANTIMENT_API_KEY", raising=False)

    def boom(*_args, **_kwargs):
        raise AssertionError("network should not be called")

    monkeypatch.setattr(santiment_mod, "http_post_json", boom)
    snap = SantimentClient().asset_snapshot("BTC")

    assert snap["mode"] == "fixture"
    assert snap["social_volume_total"] == 4200
    assert snap["social_dominance_total"] == 18.4
    assert snap["age_consumed"] == 7900000
    assert snap["network_growth"] == 121000


def test_santiment_named_metrics_use_expected_metric_names(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPPHIRE_SANTIMENT_LIVE", "1")
    monkeypatch.setenv("SANTIMENT_API_KEY", "s-key")
    monkeypatch.setenv("SAPPHIRE_ONCHAIN_USAGE_FILE", str(tmp_path / "usage.json"))
    metrics: list[str] = []

    def fake(_url, payload, *, headers=None, **_):
        del headers
        metrics.append(payload["variables"]["metric"])
        return {"data": {"getMetric": {"timeseriesData": []}}}

    monkeypatch.setattr(santiment_mod, "http_post_json", fake)
    client = SantimentClient()
    client.social_dominance("bitcoin")
    client.age_consumed("bitcoin")
    client.network_growth("bitcoin")

    assert metrics == ["social_dominance_total", "age_consumed", "network_growth"]


# --- Dune -----------------------------------------------------------------


def test_dune_execute_returns_execution_id(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "d-key")

    def fake_post(url, payload, *, headers=None, **_):
        assert headers["X-DUNE-API-KEY"] == "d-key"
        assert url.endswith("/query/42/execute")
        return {"execution_id": "exec-1"}

    monkeypatch.setattr(dune_mod, "http_post_json", fake_post)
    assert DuneClient().execute(42) == "exec-1"


def test_dune_run_query_polls_and_returns(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "d-key")
    monkeypatch.setattr(dune_mod, "http_post_json", lambda *a, **k: {"execution_id": "e"})
    responses = iter(
        [
            {"state": "QUERY_STATE_EXECUTING"},
            {"state": "QUERY_STATE_COMPLETED"},
        ]
    )

    def fake_get(url, *, headers=None, **_):
        if url.endswith("/status"):
            return next(responses)
        if url.endswith("/results"):
            return {"result": {"rows": [{"n": 1}]}}
        raise AssertionError(f"unexpected URL {url}")

    monkeypatch.setattr(dune_mod, "http_get", fake_get)
    monkeypatch.setattr(dune_mod.time, "sleep", lambda _s: None)
    out = DuneClient().run_query(42, poll_interval=0, timeout_s=5)
    assert out["result"]["rows"] == [{"n": 1}]


def test_dune_run_query_raises_on_failure(monkeypatch):
    monkeypatch.setenv("DUNE_API_KEY", "d-key")
    monkeypatch.setattr(dune_mod, "http_post_json", lambda *a, **k: {"execution_id": "e"})
    monkeypatch.setattr(
        dune_mod,
        "http_get",
        lambda *a, **k: {"state": "QUERY_STATE_FAILED", "error": "bad sql"},
    )
    monkeypatch.setattr(dune_mod.time, "sleep", lambda _s: None)
    with pytest.raises(sources.SourceError):
        DuneClient().run_query(42, poll_interval=0, timeout_s=5)


# --- Whale Alert ----------------------------------------------------------


def test_whale_alert_attaches_key_in_params(monkeypatch):
    monkeypatch.setenv("WHALE_ALERT_API_KEY", "w-key")
    captured = {}

    def fake(url, *, params=None, **_):
        captured["params"] = dict(params or {})
        return {"result": "success", "transactions": []}

    monkeypatch.setattr(whale_mod, "http_get", fake)
    WhaleAlertClient().transactions(min_value=1_000_000)
    assert captured["params"]["api_key"] == "w-key"
    assert captured["params"]["min_value"] == 1_000_000


# --- CoinAPI --------------------------------------------------------------


def test_coinapi_uses_coinapi_key_header(monkeypatch):
    monkeypatch.setenv("COINAPI_KEY", "c-key")
    captured = {}

    def fake(url, *, headers=None, params=None, **_):
        captured["headers"] = dict(headers or {})
        return []

    monkeypatch.setattr(coinapi_mod, "http_get", fake)
    CoinAPIClient().ohlcv_latest("BITSTAMP_SPOT_BTC_USD")
    assert captured["headers"]["X-CoinAPI-Key"] == "c-key"


# --- Coinglass ------------------------------------------------------------


def test_coinglass_uses_coinglass_secret_header(monkeypatch):
    monkeypatch.setenv("COINGLASS_API_KEY", "cg-key")
    captured = {}

    def fake(url, *, headers=None, params=None, **_):
        captured["headers"] = dict(headers or {})
        captured["params"] = dict(params or {})
        return {"code": "0", "data": []}

    monkeypatch.setattr(coinglass_mod, "http_get", fake)
    CoinglassClient().open_interest(symbol="ETH")
    assert captured["headers"]["coinglassSecret"] == "cg-key"
    assert captured["params"]["symbol"] == "ETH"
