"""Unit tests for lib/intel/houston_leads.py."""

from __future__ import annotations

import pytest

from lib.intel import houston_leads

SAMPLE_311 = """SR_ID|STATUS|CREATED_DATE|SR_TYPE|DEPT|ADDRESS|CITY|ZIP
311-1001|OPEN|2026-04-20|Water Leak|PWE|123 Main St|Houston|77002
311-1002|OPEN|2026-04-20|Pothole|PWE|456 Elm|Houston|77004
311-1003|OPEN|2026-04-21|Foundation Concern|PWE|789 Oak|Houston|77005
311-1004|OPEN|2026-04-22|Roof Damage|PWE|321 Pine|Houston|77006
311-1005|OPEN|2026-04-22|Loud Music|HPD|555 Mockingbird|Houston|77007
"""


@pytest.fixture
def temp_store(tmp_path, monkeypatch):
    """Redirect houston_leads paths to a tmp dir for isolation."""
    leads_dir = tmp_path / "leads"
    leads_dir.mkdir()
    monkeypatch.setattr(houston_leads, "LEADS_DIR", leads_dir)
    monkeypatch.setattr(houston_leads, "LEADS_FILE", leads_dir / "houston_leads.jsonl")
    return leads_dir


def test_is_home_relevant_311_matches_keywords():
    assert houston_leads._is_home_relevant_311("Water Leak")
    assert houston_leads._is_home_relevant_311("Foundation Concern")
    assert houston_leads._is_home_relevant_311("Roof Damage")
    assert not houston_leads._is_home_relevant_311("Loud Music")
    assert not houston_leads._is_home_relevant_311("Pothole")


def test_is_renovation_permit_matches():
    assert houston_leads._is_renovation_permit("RES", "kitchen remodel")
    assert houston_leads._is_renovation_permit("HVAC", "replace AC unit")
    assert houston_leads._is_renovation_permit("ROOF", "tear-off and replace")
    assert not houston_leads._is_renovation_permit("COMM", "office sign installation")


def test_parse_311_row_handles_short_lines():
    assert houston_leads._parse_311_row("a|b|c") is None
    row = houston_leads._parse_311_row("1|OPEN|2026-04-20|Water Leak|PWE|123 Main|Houston|77002")
    assert row is not None
    assert row["sr_id"] == "1"
    assert row["sr_type"] == "Water Leak"
    assert row["zip"] == "77002"


def test_fetch_311_filters_to_home_relevant(temp_store):
    leads = houston_leads.fetch_311_complaints(text=SAMPLE_311)
    types = {l["type"] for l in leads}
    assert "Water Leak" in types
    assert "Foundation Concern" in types
    assert "Roof Damage" in types
    assert "Pothole" not in types
    assert "Loud Music" not in types
    # Each lead has the canonical schema
    for l in leads:
        assert l["source"] == "311"
        assert l["id"].startswith("311:")
        assert "Houston, TX" in l["address"]
        assert l["raw_data"]["sr_id"]


def test_save_and_load_leads_round_trip(temp_store):
    recs = houston_leads.fetch_311_complaints(text=SAMPLE_311)
    added = houston_leads.save_leads(recs)
    assert added == len(recs)

    loaded = houston_leads.load_leads()
    assert len(loaded) == len(recs)
    assert {l["id"] for l in loaded} == {l["id"] for l in recs}


def test_save_leads_dedups_by_id(temp_store):
    recs = houston_leads.fetch_311_complaints(text=SAMPLE_311)
    houston_leads.save_leads(recs)
    # Re-saving should add zero new records.
    added2 = houston_leads.save_leads(recs)
    assert added2 == 0
    loaded = houston_leads.load_leads()
    assert len(loaded) == len(recs)


def test_save_leads_merges_new_fields(temp_store):
    rec = {
        "id": "test:1",
        "source": "311",
        "address": "1 Main",
        "ingested_at": "2026-04-28T00:00:00+00:00",
    }
    houston_leads.save_leads([rec])
    # Add a score later — should merge, not duplicate.
    rec_with_score = {**rec, "score": 88, "score_reason": "Foundation"}
    houston_leads.save_leads([rec_with_score])
    loaded = houston_leads.load_leads()
    assert len(loaded) == 1
    assert loaded[0]["score"] == 88
    assert loaded[0]["score_reason"] == "Foundation"


def test_fetch_regional_intel_handles_unavailable(temp_store, monkeypatch):
    monkeypatch.setattr(houston_leads, "_fetch_json", lambda url: None)
    out = houston_leads.fetch_regional_intel()
    assert out == []


def test_fetch_regional_intel_filters_renovation(temp_store, monkeypatch):
    snapshot = {
        "permits": [
            {
                "permit_no": "P-1",
                "address": "100 Renovation St",
                "permit_type": "RES",
                "description": "kitchen remodel",
            },
            {
                "permit_no": "P-2",
                "address": "200 Sign Ln",
                "permit_type": "COMM",
                "description": "new signage",
            },
        ]
    }
    monkeypatch.setattr(houston_leads, "_fetch_json", lambda url: snapshot)
    out = houston_leads.fetch_regional_intel()
    assert len(out) == 1
    assert out[0]["id"] == "regional_intel:permit:P-1"


def test_ingest_returns_per_source_counts(temp_store, monkeypatch):
    monkeypatch.setattr(
        houston_leads,
        "fetch_311_complaints",
        lambda: [{"id": "311:A", "source": "311", "address": "1 A St", "ingested_at": "x"}],
    )
    monkeypatch.setattr(houston_leads, "fetch_permit_activity", lambda: [])
    monkeypatch.setattr(houston_leads, "fetch_regional_intel", lambda region="houston_tx": [])
    counts = houston_leads.ingest()
    assert counts == {"311": 1, "permit": 0, "regional_intel": 0}
