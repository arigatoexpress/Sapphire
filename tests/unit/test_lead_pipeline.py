"""Unit tests for lib/intel/pipeline.py."""

from __future__ import annotations

import pytest

from lib.intel import geocoder, houston_leads, lead_scorer, pipeline


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    leads_dir = tmp_path / "leads"
    leads_dir.mkdir()
    monkeypatch.setattr(houston_leads, "LEADS_DIR", leads_dir)
    monkeypatch.setattr(houston_leads, "LEADS_FILE", leads_dir / "houston_leads.jsonl")
    monkeypatch.setattr(lead_scorer, "LEADS_FILE", leads_dir / "houston_leads.jsonl")
    monkeypatch.setattr(geocoder, "LEADS_DIR", leads_dir)
    monkeypatch.setattr(geocoder, "GEOCACHE_FILE", leads_dir / "geocache.json")
    return leads_dir


def test_run_full_pipeline_offline(temp_store, monkeypatch):
    """End-to-end with all network calls stubbed — proves the wiring."""
    monkeypatch.setattr(
        houston_leads,
        "fetch_311_complaints",
        lambda: [
            {
                "id": "311:1",
                "source": "311",
                "address": "1 Foundation St, Houston, TX 77002",
                "zip": "77002",
                "type": "Foundation Concern",
                "description": "foundation cracks",
                "raw_data": {},
                "ingested_at": "x",
                "created_at": "x",
            },
            {
                "id": "311:2",
                "source": "311",
                "address": "2 Roof Ln, Houston, TX 77003",
                "zip": "77003",
                "type": "Roof Damage",
                "description": "shingles missing",
                "raw_data": {},
                "ingested_at": "x",
                "created_at": "x",
            },
        ],
    )
    monkeypatch.setattr(houston_leads, "fetch_permit_activity", lambda: [])
    monkeypatch.setattr(houston_leads, "fetch_regional_intel", lambda region="houston_tx": [])
    monkeypatch.setattr(lead_scorer, "_infer", lambda *a, **k: None)  # heuristic only
    monkeypatch.setattr(geocoder, "geocode", lambda addr, cache=None: (29.76, -95.36))

    summary = pipeline.run()
    assert summary["ingested"]["311"] == 2
    assert summary["scored"] == 2
    assert summary["geocoded"] == 2
    assert summary["total_leads"] == 2
    # Foundation lead should be hot
    assert summary["hot_leads"] >= 1


def test_stats_reports_distributions(temp_store):
    leads = [
        {
            "id": "a",
            "source": "311",
            "address": "1 A",
            "score": 92,
            "urgency": "high",
            "lat": 29.0,
            "lng": -95.0,
            "ingested_at": "x",
        },
        {
            "id": "b",
            "source": "permit",
            "address": "2 B",
            "score": 60,
            "urgency": "medium",
            "ingested_at": "x",
        },
        {
            "id": "c",
            "source": "regional_intel",
            "address": "3 C",
            "score": None,
            "ingested_at": "x",
        },
    ]
    houston_leads.save_leads(leads)
    s = pipeline.stats()
    assert s["total"] == 3
    assert s["scored"] == 2
    assert s["hot_leads"] == 1
    assert s["geocoded"] == 1
    assert s["by_source"] == {"311": 1, "permit": 1, "regional_intel": 1}
    assert s["by_urgency"] == {"high": 1, "medium": 1}
    assert s["avg_score"] == 76.0


def test_run_skips_when_flagged(temp_store, monkeypatch):
    """skip_* flags must short-circuit the corresponding step."""
    monkeypatch.setattr(houston_leads, "fetch_311_complaints", lambda: pytest.fail("called"))
    monkeypatch.setattr(houston_leads, "fetch_permit_activity", lambda: pytest.fail("called"))
    monkeypatch.setattr(
        houston_leads, "fetch_regional_intel", lambda region="houston_tx": pytest.fail("called")
    )
    monkeypatch.setattr(lead_scorer, "score_unscored", lambda **_k: pytest.fail("called"))
    monkeypatch.setattr(geocoder, "geocode_unmapped", lambda **_k: pytest.fail("called"))
    summary = pipeline.run(skip_ingest=True, skip_score=True, skip_geocode=True)
    assert summary["ingested"] == {}
    assert summary["scored"] == 0
    assert summary["geocoded"] == 0
