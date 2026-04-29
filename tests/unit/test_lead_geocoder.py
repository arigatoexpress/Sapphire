"""Unit tests for lib/intel/geocoder.py — fully offline (no Nominatim calls)."""

from __future__ import annotations

import json

import pytest

from lib.intel import geocoder, houston_leads


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    leads_dir = tmp_path / "leads"
    leads_dir.mkdir()
    monkeypatch.setattr(houston_leads, "LEADS_DIR", leads_dir)
    monkeypatch.setattr(houston_leads, "LEADS_FILE", leads_dir / "houston_leads.jsonl")
    monkeypatch.setattr(geocoder, "LEADS_DIR", leads_dir)
    monkeypatch.setattr(geocoder, "GEOCACHE_FILE", leads_dir / "geocache.json")
    return leads_dir


def test_normalize_lowercases_and_squashes_whitespace():
    assert geocoder._normalize("  123 Main  St ") == "123 main st"


def test_geocode_uses_cache(temp_store, monkeypatch):
    cache = {"123 main st, houston, tx": {"lat": 29.76, "lng": -95.36}}
    (temp_store / "geocache.json").write_text(json.dumps(cache))
    # Should not reach the network because cache has an entry.
    monkeypatch.setattr(
        geocoder, "_rate_limited_get", lambda *_a, **_k: pytest.fail("network call")
    )
    lat, lng = geocoder.geocode("123 Main St, Houston, TX")
    assert lat == pytest.approx(29.76)
    assert lng == pytest.approx(-95.36)


def test_geocode_writes_negative_cache_on_miss(temp_store, monkeypatch):
    monkeypatch.setattr(geocoder, "_rate_limited_get", lambda *_a, **_k: [])
    lat, lng = geocoder.geocode("nonexistent address xyz")
    assert lat is None and lng is None
    cache = json.loads((temp_store / "geocache.json").read_text())
    assert any(v.get("miss") for v in cache.values())


def test_geocode_parses_nominatim_response(temp_store, monkeypatch):
    monkeypatch.setattr(
        geocoder,
        "_rate_limited_get",
        lambda *_a, **_k: [{"lat": "29.7604", "lon": "-95.3698", "display_name": "Houston"}],
    )
    lat, lng = geocoder.geocode("Houston city hall")
    assert lat == pytest.approx(29.7604)
    assert lng == pytest.approx(-95.3698)


def test_geocode_unmapped_skips_already_mapped(temp_store, monkeypatch):
    leads = [
        {"id": "a", "address": "1 A St", "lat": 29.0, "lng": -95.0, "ingested_at": "x"},
        {"id": "b", "address": "2 B St", "lat": None, "lng": None, "ingested_at": "x"},
    ]
    houston_leads.save_leads(leads)

    calls = []

    def fake_geocode(address, *, cache=None):
        calls.append(address)
        return 30.0, -96.0

    monkeypatch.setattr(geocoder, "geocode", fake_geocode)
    n = geocoder.geocode_unmapped()
    assert n == 1
    assert calls == ["2 B St"]
    saved = {l["id"]: l for l in houston_leads.load_leads()}
    assert saved["a"]["lat"] == 29.0  # unchanged
    assert saved["b"]["lat"] == 30.0  # newly mapped
