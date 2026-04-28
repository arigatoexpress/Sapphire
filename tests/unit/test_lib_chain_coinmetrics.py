"""Isolated unit tests for lib/chain/coinmetrics.py.

All HTTP calls and filesystem cache writes are isolated. The CoinMetrics
public/community API is never contacted from these tests.
"""

from __future__ import annotations

import io
import json
import urllib.error
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from lib.chain import coinmetrics
from lib.chain.coinmetrics import CoinMetricsSnapshot

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Redirect the on-disk cache to tmp_path."""
    cache_dir = tmp_path / "coinmetrics"
    monkeypatch.setattr(coinmetrics, "_CACHE_DIR", cache_dir)
    return cache_dir


def _http_response(payload: dict | bytes) -> io.BytesIO:
    """Wrap a payload in a context-manager-compatible BytesIO."""
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    resp = io.BytesIO(body)
    resp.__enter__ = lambda self: self  # type: ignore[attr-defined]
    resp.__exit__ = lambda self, *a: None  # type: ignore[attr-defined]
    return resp


# ---------------------------------------------------------------------------
# _float / _int — coercion edge cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value, expected",
    [
        ("3.14", 3.14),
        (2, 2.0),
        (None, None),
        ("not-a-number", None),
        ("", None),
        ([], None),
    ],
)
def test_float_coercion(value, expected):
    if expected is None:
        assert coinmetrics._float(value) is None
    else:
        assert coinmetrics._float(value) == pytest.approx(expected)


@pytest.mark.parametrize(
    "value, expected",
    [
        ("42", 42),
        (3.9, 3),
        ("100.7", 100),
        (None, None),
        ("not-a-number", None),
        ("", None),
    ],
)
def test_int_coercion(value, expected):
    assert coinmetrics._int(value) == expected


# ---------------------------------------------------------------------------
# Cache freshness logic
# ---------------------------------------------------------------------------


def test_cache_fresh_returns_false_when_file_missing(isolated_cache):
    path = isolated_cache / "btc.json"
    # The freshness check must not need the file to exist
    assert coinmetrics._cache_fresh(path) is False


def test_cache_fresh_returns_true_for_recent_file(isolated_cache):
    isolated_cache.mkdir(parents=True, exist_ok=True)
    path = isolated_cache / "btc.json"
    path.write_text("{}")
    # File mtime is "now" — well within the 6h TTL
    assert coinmetrics._cache_fresh(path) is True


def test_cache_fresh_returns_false_for_stale_file(isolated_cache):
    isolated_cache.mkdir(parents=True, exist_ok=True)
    path = isolated_cache / "btc.json"
    path.write_text("{}")
    # Backdate mtime to 7h ago (TTL is 6h)
    stale = (datetime.now(UTC) - timedelta(hours=7)).timestamp()
    import os

    os.utime(path, (stale, stale))
    assert coinmetrics._cache_fresh(path) is False


def test_cache_path_normalises_asset_to_lowercase(isolated_cache):
    p = coinmetrics._cache_path("BTC")
    assert p.name == "btc.json"
    # Side effect: directory is created
    assert isolated_cache.exists()


# ---------------------------------------------------------------------------
# CoinMetricsSnapshot dataclass
# ---------------------------------------------------------------------------


def test_snapshot_to_dict_excludes_raw_field():
    snap = CoinMetricsSnapshot(
        asset="BTC",
        timestamp="2026-04-27T00:00:00+00:00",
        price_usd=70000.0,
        supply=19_700_000.0,
        active_addresses=900_000,
        tx_count=350_000,
        hash_rate=600e18,
        raw={"PriceUSD": "70000.0"},
    )
    d = snap.to_dict()
    assert "raw" not in d
    assert d["asset"] == "BTC"
    assert d["price_usd"] == 70000.0
    assert d["active_addresses"] == 900_000


def test_snapshot_default_factory_sets_empty_raw():
    snap = CoinMetricsSnapshot(asset="BTC", timestamp="2026-04-27T00:00:00+00:00")
    assert snap.raw == {}
    assert snap.price_usd is None


# ---------------------------------------------------------------------------
# _fetch_raw — retry + failure paths
# ---------------------------------------------------------------------------


def test_fetch_raw_returns_parsed_json_on_success():
    payload = {"data": [{"asset": "btc", "PriceUSD": "70000.0"}]}
    with patch.object(coinmetrics.urllib.request, "urlopen", return_value=_http_response(payload)):
        result = coinmetrics._fetch_raw("BTC")
    assert result == payload


def test_fetch_raw_lowercases_asset_in_url():
    payload = {"data": []}
    with patch.object(
        coinmetrics.urllib.request, "urlopen", return_value=_http_response(payload)
    ) as urlopen:
        coinmetrics._fetch_raw("BTC")
    req = urlopen.call_args.args[0]
    assert "assets=btc" in req.full_url


def test_fetch_raw_raises_after_three_attempts():
    err = urllib.error.URLError("network down")
    with (
        patch.object(coinmetrics.urllib.request, "urlopen", side_effect=err) as urlopen,
        patch.object(coinmetrics.time, "sleep"),
    ):
        with pytest.raises(urllib.error.URLError):
            coinmetrics._fetch_raw("BTC")
    assert urlopen.call_count == 3


def test_fetch_raw_handles_invalid_json_then_succeeds():
    """First call returns garbage, second succeeds → should parse the second."""
    good_payload = {"data": [{"asset": "btc"}]}
    responses = [_http_response(b"<html>"), _http_response(good_payload)]
    with (
        patch.object(coinmetrics.urllib.request, "urlopen", side_effect=responses),
        patch.object(coinmetrics.time, "sleep"),
    ):
        result = coinmetrics._fetch_raw("BTC")
    assert result == good_payload


# ---------------------------------------------------------------------------
# get_snapshot — happy path
# ---------------------------------------------------------------------------


def test_get_snapshot_happy_path_writes_cache(isolated_cache):
    payload = {
        "data": [
            {
                "time": "2026-04-26T00:00:00+00:00",
                "PriceUSD": "70000.0",
                "SplyCur": "19700000.0",
                "AdrActCnt": "950000",
                "TxCnt": "320000",
                "HashRate": "600.5",
            }
        ]
    }
    with patch.object(coinmetrics, "_fetch_raw", return_value=payload):
        snap = coinmetrics.get_snapshot("BTC")

    assert snap.asset == "BTC"
    assert snap.price_usd == 70000.0
    assert snap.supply == pytest.approx(19_700_000.0)
    assert snap.active_addresses == 950_000
    assert snap.tx_count == 320_000
    assert snap.hash_rate == pytest.approx(600.5)
    # Cache file is written
    cache_file = isolated_cache / "btc.json"
    assert cache_file.exists()
    cached = json.loads(cache_file.read_text())
    assert cached["price_usd"] == 70000.0


def test_get_snapshot_uses_latest_row_when_multiple_returned(isolated_cache):
    """The fetcher returns timeseries data — get_snapshot must take the *last* row."""
    payload = {
        "data": [
            {"time": "2026-04-25T00:00:00+00:00", "PriceUSD": "60000"},
            {"time": "2026-04-26T00:00:00+00:00", "PriceUSD": "70000"},
        ]
    }
    with patch.object(coinmetrics, "_fetch_raw", return_value=payload):
        snap = coinmetrics.get_snapshot("BTC")
    assert snap.price_usd == 70000.0
    assert snap.timestamp == "2026-04-26T00:00:00+00:00"


def test_get_snapshot_uses_now_timestamp_when_row_lacks_time(isolated_cache):
    payload = {"data": [{"PriceUSD": "70000"}]}
    with patch.object(coinmetrics, "_fetch_raw", return_value=payload):
        snap = coinmetrics.get_snapshot("BTC")
    # Timestamp should still be a parseable iso string (the now fallback)
    assert datetime.fromisoformat(snap.timestamp) is not None
    assert snap.price_usd == 70000.0


# ---------------------------------------------------------------------------
# get_snapshot — failure / cache-miss paths
# ---------------------------------------------------------------------------


def test_get_snapshot_returns_empty_snapshot_when_data_rows_empty(isolated_cache):
    """An empty data array triggers the ValueError → empty snapshot fallback."""
    with patch.object(coinmetrics, "_fetch_raw", return_value={"data": []}):
        snap = coinmetrics.get_snapshot("BTC")
    assert snap.asset == "BTC"
    assert snap.price_usd is None
    assert snap.tx_count is None
    # Empty snapshot is NOT written to the cache (fetch failed)
    assert not (isolated_cache / "btc.json").exists()


def test_get_snapshot_returns_empty_snapshot_on_fetch_failure(isolated_cache):
    """A network exception from _fetch_raw must be swallowed."""
    with patch.object(coinmetrics, "_fetch_raw", side_effect=urllib.error.URLError("dead")):
        snap = coinmetrics.get_snapshot("ETH")
    assert snap.asset == "ETH"
    assert snap.price_usd is None
    assert snap.timestamp  # still set to "now"


def test_get_snapshot_loads_from_fresh_cache_without_calling_fetch(isolated_cache):
    """If cache is fresh, _fetch_raw must NOT be invoked."""
    isolated_cache.mkdir(parents=True, exist_ok=True)
    cached_payload = {
        "asset": "BTC",
        "timestamp": "2026-04-26T00:00:00+00:00",
        "price_usd": 65000.0,
        "supply": 19_700_000.0,
        "active_addresses": 900_000,
        "tx_count": 350_000,
        "hash_rate": 600.0,
    }
    (isolated_cache / "btc.json").write_text(json.dumps(cached_payload))

    with patch.object(coinmetrics, "_fetch_raw") as fetcher:
        snap = coinmetrics.get_snapshot("BTC")

    fetcher.assert_not_called()
    assert snap.price_usd == 65000.0
    assert snap.tx_count == 350_000


def test_get_snapshot_falls_through_to_fetch_when_cache_corrupt(isolated_cache):
    """Corrupt cache file should be ignored — caller fetches fresh."""
    isolated_cache.mkdir(parents=True, exist_ok=True)
    (isolated_cache / "btc.json").write_text("{not json")

    payload = {"data": [{"PriceUSD": "70000"}]}
    with patch.object(coinmetrics, "_fetch_raw", return_value=payload) as fetcher:
        snap = coinmetrics.get_snapshot("BTC")

    fetcher.assert_called_once()
    assert snap.price_usd == 70000.0


# ---------------------------------------------------------------------------
# get_multi
# ---------------------------------------------------------------------------


def test_get_multi_default_assets():
    """Default call with no args fetches BTC, ETH, SOL in order."""
    seen_assets = []

    def _record(asset):
        seen_assets.append(asset)
        return CoinMetricsSnapshot(asset=asset, timestamp="2026-04-27T00:00:00+00:00")

    with patch.object(coinmetrics, "get_snapshot", side_effect=_record):
        result = coinmetrics.get_multi()

    assert seen_assets == ["BTC", "ETH", "SOL"]
    assert [s.asset for s in result] == ["BTC", "ETH", "SOL"]


def test_get_multi_with_custom_asset_list():
    with patch.object(
        coinmetrics,
        "get_snapshot",
        side_effect=lambda a: CoinMetricsSnapshot(asset=a, timestamp="t"),
    ) as mock_get:
        result = coinmetrics.get_multi(["LTC", "DOGE"])
    assert [s.asset for s in result] == ["LTC", "DOGE"]
    assert mock_get.call_count == 2


def test_get_multi_with_empty_list_returns_empty():
    with patch.object(coinmetrics, "get_snapshot") as mock_get:
        result = coinmetrics.get_multi([])
    assert result == []
    mock_get.assert_not_called()
