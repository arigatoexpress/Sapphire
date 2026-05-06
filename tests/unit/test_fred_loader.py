from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from lib.macro.fred_loader import (
    DEFAULT_MARKET_REGIME_SERIES,
    FredLoader,
    FredLoaderError,
    build_fred_observations_url,
    canonical_observation_id,
    fred_cache_dir,
    fred_observation_rows,
    latest_observation,
    macro_feature_row,
    parse_fred_observations,
)


def sample_payload() -> dict:
    return {
        "realtime_start": "2026-01-01",
        "realtime_end": "2026-01-31",
        "observation_start": "2025-12-01",
        "observation_end": "2026-01-31",
        "units": "lin",
        "frequency": "Daily",
        "count": 3,
        "observations": [
            {
                "realtime_start": "2026-01-01",
                "realtime_end": "2026-01-31",
                "date": "2026-01-02",
                "value": "4.33",
            },
            {
                "realtime_start": "2026-01-01",
                "realtime_end": "2026-01-31",
                "date": "2026-01-01",
                "value": ".",
            },
            {
                "realtime_start": "2026-01-01",
                "realtime_end": "2026-01-31",
                "date": "2026-01-03",
                "value": "4.35",
            },
        ],
    }


def test_parse_fred_observations_handles_nulls_and_vintages():
    snapshot = parse_fred_observations(sample_payload(), series_id="dff")

    assert snapshot.series_id == "DFF"
    assert snapshot.realtime_start == date(2026, 1, 1)
    assert snapshot.realtime_end == date(2026, 1, 31)
    assert snapshot.observations[0].observation_date == date(2026, 1, 1)
    assert snapshot.observations[0].value is None
    assert snapshot.observations[1].value == 4.33
    assert snapshot.latest and snapshot.latest.value == 4.35
    assert snapshot.units == "lin"
    assert snapshot.frequency == "Daily"


def test_latest_observation_prefers_latest_non_null():
    payload = sample_payload()
    payload["observations"].append(
        {
            "realtime_start": "2026-01-01",
            "realtime_end": "2026-01-31",
            "date": "2026-01-04",
            "value": ".",
        }
    )
    snapshot = parse_fred_observations(payload, series_id="DFF")

    assert latest_observation(snapshot).observation_date == date(2026, 1, 3)


def test_build_fred_url_includes_vintage_and_observation_params():
    url = build_fred_observations_url(
        "DGS10",
        api_key="secret-key",
        observation_start=date(2026, 1, 1),
        realtime_start="2026-02-01",
        realtime_end="2026-02-28",
        units="pc1",
        limit=25,
    )
    query = parse_qs(urlsplit(url).query)

    assert query["series_id"] == ["DGS10"]
    assert query["api_key"] == ["secret-key"]
    assert query["file_type"] == ["json"]
    assert query["observation_start"] == ["2026-01-01"]
    assert query["realtime_start"] == ["2026-02-01"]
    assert query["realtime_end"] == ["2026-02-28"]
    assert query["units"] == ["pc1"]
    assert query["limit"] == ["25"]


def test_loader_reads_cache_before_network(tmp_path):
    loader = FredLoader(cache_dir=tmp_path, fetcher=lambda *_: pytest.fail("network disabled"))
    cache_path = loader.cache_path("DFF", limit=3)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(sample_payload()), encoding="utf-8")

    snapshot = loader.pull_series("DFF", limit=3)

    assert snapshot.cached is True
    assert snapshot.latest and snapshot.latest.value == 4.35


def test_loader_blocks_live_reads_without_gate(tmp_path, monkeypatch):
    monkeypatch.delenv("SAPPHIRE_FRED_LIVE", raising=False)
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    loader = FredLoader(cache_dir=tmp_path)

    with pytest.raises(FredLoaderError, match="live reads are disabled"):
        loader.pull_series("DFF")


def test_loader_live_fetch_writes_redacted_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SAPPHIRE_FRED_LIVE", "1")
    calls: list[tuple[str, dict[str, str], float]] = []

    def fetcher(url, headers, timeout):
        calls.append((url, dict(headers), timeout))
        assert parse_qs(urlsplit(url).query)["api_key"] == ["live-key"]
        return sample_payload()

    loader = FredLoader(cache_dir=tmp_path, api_key="live-key", fetcher=fetcher)
    snapshot = loader.pull_series("DFF", limit=3)

    assert snapshot.cached is False
    assert calls and "SapphireFredLoader" in calls[0][1]["User-Agent"]
    cached_files = list(Path(tmp_path).glob("DFF-*.json"))
    assert len(cached_files) == 1
    payload = json.loads(cached_files[0].read_text(encoding="utf-8"))
    assert "api_key=%2A%2A%2A" in payload["_source_url"]
    assert "live-key" not in cached_files[0].read_text(encoding="utf-8")


def test_loader_cache_only_market_regime_series_uses_requested_ids(tmp_path):
    loader = FredLoader(cache_dir=tmp_path)
    for series_id in ("DFF", "DGS10"):
        cache_path = loader.cache_path(series_id, limit=5)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(sample_payload()), encoding="utf-8")

    snapshots = loader.pull_market_regime_series(
        series_ids=("DFF", "DGS10"),
        limit=5,
        cache_only=True,
    )

    assert [snapshot.series_id for snapshot in snapshots] == ["DFF", "DGS10"]


def test_macro_feature_row_is_stable_and_latest_value_only():
    snapshot = parse_fred_observations(sample_payload(), series_id="DFF")
    row = macro_feature_row([snapshot], generated_at=datetime(2026, 1, 5, tzinfo=UTC))

    assert row["schema_version"] == 1
    assert row["generated_at"] == "2026-01-05T00:00:00+00:00"
    assert row["source"] == "fred_alfred"
    assert row["series"]["DFF"] == {
        "value": 4.35,
        "observation_date": "2026-01-03",
        "realtime_start": "2026-01-01",
        "realtime_end": "2026-01-31",
        "units": "lin",
    }
    assert len(row["feature_id"]) == 24


def test_observation_rows_include_stable_ids_and_payload_hash():
    snapshot = parse_fred_observations(sample_payload(), series_id="DFF")
    rows = fred_observation_rows(
        snapshot,
        ingested_at=datetime(2026, 1, 5, 12, 30, tzinfo=UTC),
    )

    assert rows[0]["id"] == canonical_observation_id(
        "DFF",
        "2026-01-01",
        "2026-01-01",
        "2026-01-31",
    )
    assert rows[0]["observation_id"] == rows[0]["id"]
    assert rows[0]["payload_hash"] == rows[1]["payload_hash"]
    assert len(rows[0]["payload_hash"]) == 64
    assert rows[0]["ingested_at"] == "2026-01-05T12:30:00+00:00"


def test_cache_dir_can_follow_macro_root(monkeypatch, tmp_path):
    monkeypatch.delenv("SAPPHIRE_FRED_CACHE_DIR", raising=False)
    monkeypatch.setenv("SAPPHIRE_MACRO_CACHE_DIR", str(tmp_path))

    assert fred_cache_dir() == tmp_path / "fred"


def test_default_market_regime_series_has_core_rates_and_risk_series():
    assert {"DFF", "DGS10", "T10Y2Y", "VIXCLS", "BAMLH0A0HYM2"} <= set(DEFAULT_MARKET_REGIME_SERIES)
