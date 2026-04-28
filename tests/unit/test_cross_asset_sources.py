from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from lib.cross_asset.sources import (
    CACHE_TTL_SECONDS,
    CachedOHLCVAdapter,
    HyperliquidCachedSourceAdapter,
    OHLCVPoint,
    OpenBBCachedSourceAdapter,
    build_default_adapters,
    fetch_universe,
    synthetic_ohlcv,
    to_close_series,
)

FROZEN_NOW = datetime(2026, 4, 28, 12, 0, tzinfo=UTC)


class FakeAdapter(CachedOHLCVAdapter):
    name = "fake"

    def __init__(self, **kwargs):
        super().__init__(asset_map={"BTC": "BTC-USD", "ETH": "ETH-USD"}, **kwargs)
        self.live_calls = 0

    def _pull_live(self, asset: str, *, limit: int, now=None):
        self.live_calls += 1
        return [
            OHLCVPoint(
                timestamp=(now or FROZEN_NOW).isoformat(),
                open=1,
                high=2,
                low=1,
                close=123,
                volume=10,
                source=f"live:{asset}",
            )
        ]


def test_synthetic_ohlcv_is_deterministic_for_fixed_time() -> None:
    first = synthetic_ohlcv("BTC", points=5, now=FROZEN_NOW)
    second = synthetic_ohlcv("BTC", points=5, now=FROZEN_NOW)
    assert first == second
    assert len(first) == 5


def test_synthetic_assets_have_distinct_levels() -> None:
    btc = synthetic_ohlcv("BTC", points=1, now=FROZEN_NOW)[0]
    eth = synthetic_ohlcv("ETH", points=1, now=FROZEN_NOW)[0]
    assert btc.close > eth.close


def test_adapter_supports_declared_assets(tmp_path) -> None:
    adapter = FakeAdapter(cache_root=tmp_path)
    assert adapter.supports("btc") is True
    assert adapter.supports("SOL") is False


def test_cache_write_and_read_round_trip(tmp_path) -> None:
    adapter = FakeAdapter(cache_root=tmp_path)
    rows = synthetic_ohlcv("BTC", points=3, now=FROZEN_NOW)
    adapter._write_cache("BTC", rows)
    assert adapter._read_cache("BTC", allow_stale=True, now=FROZEN_NOW) == rows


def test_corrupt_cache_returns_empty(tmp_path) -> None:
    adapter = FakeAdapter(cache_root=tmp_path)
    path = adapter._cache_path("BTC")
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert adapter._read_cache("BTC", allow_stale=True, now=FROZEN_NOW) == []


def test_live_false_never_calls_pull_live(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SAPPHIRE_CROSS_ASSET_LIVE", raising=False)
    adapter = FakeAdapter(cache_root=tmp_path)
    rows = adapter.get_ohlcv("BTC", live=False, limit=4, now=FROZEN_NOW)
    assert adapter.live_calls == 0
    assert len(rows) == 4
    assert rows[-1].source == "fake:dry-run"


def test_live_true_without_env_still_uses_dry_run(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SAPPHIRE_CROSS_ASSET_LIVE", raising=False)
    adapter = FakeAdapter(cache_root=tmp_path)
    rows = adapter.get_ohlcv("BTC", live=True, limit=2, now=FROZEN_NOW)
    assert adapter.live_calls == 0
    assert rows[-1].source == "fake:dry-run"


def test_live_true_with_env_calls_pull_live(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_CROSS_ASSET_LIVE", "1")
    adapter = FakeAdapter(cache_root=tmp_path)
    rows = adapter.get_ohlcv("BTC", live=True, limit=2, now=FROZEN_NOW)
    assert adapter.live_calls == 1
    assert rows[-1].source == "live:BTC"


def test_cached_rows_are_preferred_over_live(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_CROSS_ASSET_LIVE", "1")
    adapter = FakeAdapter(cache_root=tmp_path)
    adapter._write_cache("BTC", synthetic_ohlcv("BTC", points=2, now=FROZEN_NOW, source="fixture"))
    rows = adapter.get_ohlcv("BTC", live=True, limit=2, now=FROZEN_NOW)
    assert adapter.live_calls == 0
    assert rows[-1].source == "fixture"


def test_fetch_universe_uses_adapter_and_synthetic_fallback(tmp_path) -> None:
    adapter = FakeAdapter(cache_root=tmp_path)
    rows = fetch_universe(["BTC", "SOL"], adapters=[adapter], live=False, limit=3, now=FROZEN_NOW)
    assert set(rows) == {"BTC", "SOL"}
    assert rows["SOL"][-1].source == "synthetic:unsupported"


def test_fetch_universe_enforces_asset_cap(tmp_path) -> None:
    adapter = FakeAdapter(cache_root=tmp_path)
    with pytest.raises(ValueError):
        fetch_universe([f"A{i}" for i in range(25)], adapters=[adapter], now=FROZEN_NOW)


def test_to_close_series_is_json_friendly() -> None:
    rows = {"BTC": synthetic_ohlcv("BTC", points=2, now=FROZEN_NOW)}
    close_series = to_close_series(rows)
    assert close_series["BTC"][0]["timestamp"]
    assert "close" in close_series["BTC"][0]


def test_default_adapters_include_openbb_and_hyperliquid(tmp_path) -> None:
    names = {adapter.name for adapter in build_default_adapters(cache_root=tmp_path)}
    assert {"openbb", "hyperliquid"} <= names


def test_hyperliquid_adapter_supports_hype(tmp_path) -> None:
    adapter = HyperliquidCachedSourceAdapter(cache_root=tmp_path)
    assert adapter.supports("HYPE")
    assert adapter.get_ohlcv("HYPE", live=False, limit=2, now=FROZEN_NOW)


def test_openbb_adapter_live_pull_can_be_mocked(tmp_path, monkeypatch) -> None:
    payload = {"results": [{"date": "2026-04-28", "open": 1, "high": 2, "low": 1, "close": 1.5, "volume": 9}]}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(payload).encode()

    monkeypatch.setenv("SAPPHIRE_CROSS_ASSET_LIVE", "1")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: Response())
    adapter = OpenBBCachedSourceAdapter(cache_root=tmp_path)
    rows = adapter.get_ohlcv("SPY", live=True, limit=10, now=FROZEN_NOW)
    assert rows[0].close == 1.5
    assert rows[0].source == "openbb:SPY"


def test_stale_cache_rejected_when_live_true(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_CROSS_ASSET_LIVE", "1")
    adapter = FakeAdapter(cache_root=tmp_path, ttl_seconds=-1)
    adapter._write_cache("BTC", synthetic_ohlcv("BTC", points=2, now=FROZEN_NOW, source="stale"))
    rows = adapter.get_ohlcv("BTC", live=True, limit=2, now=FROZEN_NOW + timedelta(days=1))
    assert adapter.live_calls == 1
    assert rows[-1].source == "live:BTC"


def test_cache_ttl_constant_is_positive() -> None:
    assert CACHE_TTL_SECONDS > 0
