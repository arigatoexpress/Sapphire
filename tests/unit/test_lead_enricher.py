"""Unit tests for lib.intel.lead_enricher — property value, builder extraction,
decision-maker parsing, cache behaviour, pipeline enrichment.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


def test_grade_from_score_thresholds():
    from lib.intel.lead_enricher import _grade_from_score
    assert _grade_from_score(0.90) == "A"
    assert _grade_from_score(0.80) == "A"
    assert _grade_from_score(0.70) == "B"
    assert _grade_from_score(0.50) == "C"
    assert _grade_from_score(0.40) == "D"
    assert _grade_from_score(0.10) == "F"


def test_score_lead_boosts_on_keywords_and_class():
    from lib.intel.lead_enricher import _score_lead
    baseline = _score_lead({"name": "generic lot"})
    boosted = _score_lead({
        "name": "ENCLAVE ESTATES",
        "description": "C3F luxury subdivision",
        "value_usd": 1_500_000,
    })
    assert boosted > baseline
    assert boosted <= 0.99


# ---------------------------------------------------------------------------
# Property value estimation
# ---------------------------------------------------------------------------


def test_estimate_property_value_uses_stated_value():
    from lib.intel.lead_enricher import _estimate_property_value
    assert _estimate_property_value({"value_usd": 750_000}) == 750_000


def test_estimate_property_value_from_permit_class():
    from lib.intel.lead_enricher import PERMIT_VALUE_PRIORS, _estimate_property_value
    assert _estimate_property_value({"description": "type C3F final plat"}) == PERMIT_VALUE_PRIORS["C3F"]
    assert _estimate_property_value({"description": "C2R subdivision"}) == PERMIT_VALUE_PRIORS["C2R"]


def test_estimate_property_value_commercial():
    from lib.intel.lead_enricher import PERMIT_VALUE_PRIORS, _estimate_property_value
    assert _estimate_property_value({"category": "commercial office"}) == PERMIT_VALUE_PRIORS["COMM"]


def test_estimate_property_value_default_fallback():
    from lib.intel.lead_enricher import PERMIT_VALUE_PRIORS, _estimate_property_value
    assert _estimate_property_value({}) == PERMIT_VALUE_PRIORS["DEFAULT"]


def test_estimate_property_value_rejects_bad_stated():
    from lib.intel.lead_enricher import PERMIT_VALUE_PRIORS, _estimate_property_value
    # Non-numeric stated value → falls through to class / default
    v = _estimate_property_value({"value_usd": "not-a-number"})
    assert v == PERMIT_VALUE_PRIORS["DEFAULT"]


# ---------------------------------------------------------------------------
# Builder extraction
# ---------------------------------------------------------------------------


def test_extract_builder_from_applicant_field():
    from lib.intel.lead_enricher import _extract_builder
    info = _extract_builder({"applicant": "Lennar Homes LLC"})
    assert info["raw_name"] == "Lennar Homes LLC"
    assert info["entity_type"] == "registered_business"
    assert info["sector"] == "residential_construction"


def test_extract_builder_from_description_pattern():
    from lib.intel.lead_enricher import _extract_builder
    info = _extract_builder({
        "description": "Site work BY TOLL BROTHERS HOMES LLC on 20 acres",
    })
    assert info["raw_name"] is not None
    assert "HOMES" in info["raw_name"].upper()


def test_extract_builder_none_when_no_info():
    from lib.intel.lead_enricher import _extract_builder
    info = _extract_builder({"description": "vacant parcel"})
    assert info["raw_name"] is None


# ---------------------------------------------------------------------------
# Decision-maker discovery
# ---------------------------------------------------------------------------


def test_find_decision_maker_explicit_field():
    from lib.intel.lead_enricher import _find_decision_maker
    name, src = _find_decision_maker({"contact_name": "Jane Doe"})
    assert name == "Jane Doe"
    assert src == "contact_name"


def test_find_decision_maker_from_attn_pattern():
    from lib.intel.lead_enricher import _find_decision_maker
    name, src = _find_decision_maker({"description": "Permit attn: Robert Smith at acme"})
    assert name == "Robert Smith"
    assert src == "description_parse"


def test_find_decision_maker_from_co_pattern():
    from lib.intel.lead_enricher import _find_decision_maker
    name, src = _find_decision_maker({"description": "Mail c/o Alice Brown thanks"})
    assert name == "Alice Brown"


def test_find_decision_maker_no_match_returns_none():
    from lib.intel.lead_enricher import _find_decision_maker
    name, src = _find_decision_maker({"description": "just a permit"})
    assert name is None
    assert src is None


# ---------------------------------------------------------------------------
# enrich_lead (top-level)
# ---------------------------------------------------------------------------


def test_enrich_lead_populates_all_fields():
    from lib.intel.lead_enricher import enrich_lead
    lead = {
        "name": "ENCLAVE AT MANOR",
        "description": "C3F final plat attn: John Foster",
        "applicant": "Acme Homes LLC",
        "region": "austin_tx",
        "value_usd": 2_000_000,
        "score": 0.85,
    }
    en = enrich_lead(lead)
    assert en.grade == "A"
    assert en.property_value_estimate_usd == 2_000_000
    assert en.neighborhood_median_home_price_usd is not None
    assert en.builder_info.get("raw_name") is not None
    assert en.decision_maker_name == "John Foster"
    assert en.enrichment_status == "ok"


def test_enrich_lead_handles_non_numeric_score():
    from lib.intel.lead_enricher import enrich_lead
    en = enrich_lead({"score": "not-a-float", "name": "x", "region": "default"})
    assert 0 <= en.score <= 1
    assert en.grade in {"A", "B", "C", "D", "F"}


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------


def test_cache_roundtrip(tmp_path, monkeypatch):
    from lib.intel import lead_enricher as le

    monkeypatch.setattr(le, "CACHE_DIR", tmp_path)
    le._cache_put("mykey", {"hello": "world"})
    assert le._cache_get("mykey") == {"hello": "world"}


def test_cache_expires_past_ttl(tmp_path, monkeypatch):
    from lib.intel import lead_enricher as le

    monkeypatch.setattr(le, "CACHE_DIR", tmp_path)
    path = le._cache_key("stale")
    path.write_text(json.dumps({"_ts": time.time() - 10 * le.CACHE_TTL_SECS, "value": "old"}))
    assert le._cache_get("stale") is None


def test_cache_key_sanitises_path():
    from lib.intel.lead_enricher import _cache_key
    p = _cache_key("weird/key:with spaces?and&punct")
    # All unsafe chars replaced with underscores
    assert "/" not in p.name
    assert ":" not in p.name
    assert p.name.endswith(".json")


# ---------------------------------------------------------------------------
# Pipeline enrichment
# ---------------------------------------------------------------------------


def test_enrich_pipeline_filters_by_grade(tmp_path, monkeypatch):
    from lib.intel import lead_enricher as le

    monkeypatch.setattr(le, "CACHE_DIR", tmp_path / "cache")
    (tmp_path / "cache").mkdir()

    pipeline = tmp_path / "pipeline_test.json"
    pipeline.write_text(json.dumps({
        "leads": [
            {"name": "high", "score": 0.90, "region": "austin_tx", "value_usd": 1_000_000},
            {"name": "low", "score": 0.40, "region": "austin_tx"},
            {"name": "grade_b", "score": 0.70, "region": "austin_tx"},
        ],
    }))
    result = le.enrich_pipeline(pipeline, grade_filter="A")
    assert result["enriched_count"] == 1
    # Verify on-disk rewrite
    reloaded = json.loads(pipeline.read_text())
    assert "enriched_leads" in reloaded
    assert len(reloaded["enriched_leads"]) == 1
    # Merged fields into source lead
    assert reloaded["leads"][0]["property_value_estimate_usd"] == 1_000_000


def test_enrich_pipeline_missing_file():
    from lib.intel.lead_enricher import enrich_pipeline
    result = enrich_pipeline(Path("/tmp/does_not_exist_pipeline.json"))
    assert "error" in result


def test_enrich_pipeline_bad_leads_field(tmp_path):
    from lib.intel.lead_enricher import enrich_pipeline
    pipeline = tmp_path / "p.json"
    pipeline.write_text(json.dumps({"leads": "not-a-list"}))
    result = enrich_pipeline(pipeline)
    assert "error" in result
