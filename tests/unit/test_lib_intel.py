"""Isolated unit tests for ``lib.intel``.

Exercises the pure scoring + parsing layer of:

* ``sovereign_thesis`` — lens parsing, asset parsing, fit labeling, ops queue,
  evidence summary; all on hand-rolled fixtures (no YAML / JSON files).
* ``lead_enricher`` — score → grade mapping, property-value heuristics, region
  centroid lookup, decision-maker extraction.
* ``market_intelligence`` — RSS keyword scoring, ForexFactory date parsing,
  liquidation band estimator, funding velocity classification.

No live HTTP, no real config files.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from lib.intel import lead_enricher
from lib.intel import sovereign_thesis as st

# ---------------------------------------------------------------------------
# sovereign_thesis
# ---------------------------------------------------------------------------


def _lens(**kw: Any) -> st.ThesisLens:
    return st.ThesisLens(
        id=kw.get("id", "money_layer"),
        label=kw.get("label", "Money Layer"),
        weight=float(kw.get("weight", 1.0)),
        austrian_principle=kw.get("austrian_principle", "sound money"),
        positive_tags=tuple(kw.get("positive_tags", ("hard-money",))),
        negative_tags=tuple(kw.get("negative_tags", ("inflation-friendly",))),
        source_requirements=tuple(kw.get("source_requirements", ("sec:companyfacts",))),
    )


def _asset(**kw: Any) -> st.ThesisAsset:
    return st.ThesisAsset(
        symbol=kw.get("symbol", "BTC"),
        name=kw.get("name", "Bitcoin"),
        asset_class=kw.get("asset_class", "crypto"),
        conviction=float(kw.get("conviction", 0.8)),
        thesis_tags=tuple(kw.get("thesis_tags", ("hard-money", "monetary-debasement"))),
        lens_scores=dict(kw.get("lens_scores", {})),
        venue_symbols=dict(kw.get("venue_symbols", {"tradingview": "BINANCE:BTCUSDT"})),
        evidence_sources=tuple(kw.get("evidence_sources", ())),
        invalidation_triggers=tuple(kw.get("invalidation_triggers", ())),
    )


class TestSovereignThesisHelpers:
    def test_as_float_returns_default_on_garbage(self) -> None:
        assert st._as_float("not-a-number", 7.5) == 7.5
        assert st._as_float(None, 0.0) == 0.0

    def test_as_str_tuple_strips_falsy(self) -> None:
        assert st._as_str_tuple(["a", "", None, "b"]) == ("a", "b")

    def test_as_mapping_falls_back_to_empty(self) -> None:
        assert st._as_mapping("not a dict") == {}
        assert st._as_mapping({"k": "v"}) == {"k": "v"}

    def test_cell_state_thresholds(self) -> None:
        assert st._cell_state(0.9) == "core"
        assert st._cell_state(0.5) == "supporting"
        assert st._cell_state(0.0) == "neutral"
        assert st._cell_state(-0.1) == "risk"

    def test_fit_label_thresholds(self) -> None:
        assert st._fit_label(72.0) == "core"
        assert st._fit_label(50.0) == "aligned"
        assert st._fit_label(30.0) == "watch"
        assert st._fit_label(0.0) == "speculative"

    def test_inferred_lens_value_explicit_score_clamped(self) -> None:
        lens = _lens()
        asset = _asset(lens_scores={"money_layer": 5.0})  # out-of-range → clamp to 1.0
        assert st._inferred_lens_value(asset, lens) == 1.0
        asset_neg = _asset(lens_scores={"money_layer": -42.0})
        assert st._inferred_lens_value(asset_neg, lens) == -1.0

    def test_inferred_lens_value_falls_back_to_tag_match(self) -> None:
        lens = _lens(positive_tags=("growth",), negative_tags=("decay",))
        # Asset has the positive tag → 0.5
        positive_asset = _asset(thesis_tags=("growth", "ai"), lens_scores={})
        assert st._inferred_lens_value(positive_asset, lens) == 0.5
        # Asset has the negative tag → -0.5
        negative_asset = _asset(thesis_tags=("decay",), lens_scores={})
        assert st._inferred_lens_value(negative_asset, lens) == -0.5
        # Asset has both → 0.25 (the "ambiguous" branch the integration tests skip)
        both = _asset(thesis_tags=("growth", "decay"), lens_scores={})
        assert st._inferred_lens_value(both, lens) == 0.25
        # Asset has neither → 0.0
        none = _asset(thesis_tags=("unrelated",), lens_scores={})
        assert st._inferred_lens_value(none, lens) == 0.0


class TestSovereignThesisParsing:
    def test_parse_lenses_defaults(self) -> None:
        cfg = {
            "lenses": [
                {
                    "id": "money_layer",
                    "label": "Money Layer",
                    "weight": 1.5,
                    "positive_tags": ["hard-money"],
                },
            ],
        }
        lenses = st.parse_lenses(cfg)
        assert len(lenses) == 1
        assert lenses[0].id == "money_layer"
        assert lenses[0].weight == 1.5
        assert lenses[0].positive_tags == ("hard-money",)

    def test_parse_lenses_rejects_missing_id(self) -> None:
        cfg = {"lenses": [{"label": "missing-id"}]}
        with pytest.raises(ValueError):
            st.parse_lenses(cfg)

    def test_parse_assets_normalizes_symbol(self) -> None:
        cfg = {
            "assets": [
                {"symbol": " btc ", "name": "Bitcoin", "conviction": 0.9},
            ],
        }
        assets = st.parse_assets(cfg)
        assert len(assets) == 1
        assert assets[0].symbol == "BTC"
        assert assets[0].conviction == 0.9

    def test_parse_assets_clamps_conviction(self) -> None:
        cfg = {"assets": [{"symbol": "ETH", "conviction": 999.0}]}
        assets = st.parse_assets(cfg)
        assert assets[0].conviction == 1.0
        cfg_neg = {"assets": [{"symbol": "ETH", "conviction": -0.5}]}
        assets_neg = st.parse_assets(cfg_neg)
        assert assets_neg[0].conviction == 0.0


class TestSovereignThesisReportShape:
    def test_build_report_aggregates_lenses_and_assets(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Build a tiny self-contained config so we don't depend on the repo file.
        config = {
            "worldview": {"label": "test"},
            "lenses": [
                {
                    "id": "money_layer",
                    "label": "Money Layer",
                    "weight": 2.0,
                    "positive_tags": ["hard-money"],
                    "source_requirements": ["sec:companyfacts"],
                },
                {
                    "id": "energy_independence",
                    "label": "Energy",
                    "weight": 1.0,
                    "positive_tags": ["energy"],
                    "source_requirements": ["eia:electricity"],
                },
            ],
            "assets": [
                {
                    "symbol": "BTC",
                    "name": "Bitcoin",
                    "asset_class": "crypto",
                    "conviction": 0.9,
                    "thesis_tags": ["hard-money"],
                    "venue_symbols": {"tradingview": "BINANCE:BTCUSDT"},
                    "evidence_sources": ["sec:companyfacts"],
                    "invalidation_triggers": [
                        {"id": "regulatory_freeze", "severity": "high", "status": "watch"}
                    ],
                },
                {
                    "symbol": "FSLR",
                    "name": "First Solar",
                    "asset_class": "equity",
                    "conviction": 0.5,
                    "thesis_tags": ["energy"],
                    "venue_symbols": {},  # missing tradingview symbol → P3 ops queue entry
                },
            ],
        }
        # Patch load_thesis_config so we don't read any YAML/JSON file.
        monkeypatch.setattr(st, "load_thesis_config", lambda *a, **kw: config)
        report = st.build_sovereign_thesis_report()
        assert report["totals"]["assets"] == 2
        assert report["totals"]["lenses"] == 2
        # BTC should be ranked first by relative_score
        assert report["assets"][0]["symbol"] == "BTC"
        assert report["assets"][0]["fit"] in {"core", "aligned"}
        # An ops queue entry for the missing tradingview symbol must exist.
        ops_actions = {row["action"] for row in report["ops_queue"]}
        assert "complete_symbol_mapping" in ops_actions

    def test_build_report_raises_on_empty_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(st, "load_thesis_config", lambda *a, **kw: {"lenses": [], "assets": []})
        with pytest.raises(ValueError):
            st.build_sovereign_thesis_report()


# ---------------------------------------------------------------------------
# lead_enricher
# ---------------------------------------------------------------------------


class TestLeadEnricherGrading:
    def test_grade_from_score_buckets(self) -> None:
        assert lead_enricher._grade_from_score(0.95) == "A"
        assert lead_enricher._grade_from_score(0.70) == "B"
        assert lead_enricher._grade_from_score(0.55) == "C"
        assert lead_enricher._grade_from_score(0.40) == "D"
        assert lead_enricher._grade_from_score(0.00) == "F"

    def test_score_lead_boosts_for_premium_keywords(self) -> None:
        plain = {"name": "Plain Subdivision", "category": "C2", "value_usd": 0}
        luxury = {
            "name": "Luxury Estates Project",
            "category": "C3F",
            "value_usd": 2_000_000,
        }
        assert lead_enricher._score_lead(luxury) > lead_enricher._score_lead(plain)

    def test_score_lead_handles_garbage_values(self) -> None:
        # value_usd is non-numeric — must not raise.
        bad = {"name": "x", "value_usd": "not-a-number"}
        score = lead_enricher._score_lead(bad)
        assert 0.0 <= score <= 0.99


class TestLeadEnricherFields:
    def test_estimate_property_value_uses_explicit(self) -> None:
        lead = {"permit_value_usd": 750_000}
        assert lead_enricher._estimate_property_value(lead) == 750_000

    def test_estimate_property_value_uses_permit_class(self) -> None:
        lead = {"category": "C3F luxury subdivision"}
        # C3F prior is $850k
        assert lead_enricher._estimate_property_value(lead) == 850_000

    def test_estimate_property_value_falls_back_to_default(self) -> None:
        lead = {"description": "random unrelated text"}
        assert (
            lead_enricher._estimate_property_value(lead)
            == lead_enricher.PERMIT_VALUE_PRIORS["DEFAULT"]
        )

    def test_extract_builder_recognizes_entity_suffix(self) -> None:
        info = lead_enricher._extract_builder({"applicant": "ACME HOMES LLC"})
        assert info["raw_name"] == "ACME HOMES LLC"
        assert info["entity_type"] == "registered_business"
        assert info["sector"] == "residential_construction"

    def test_extract_builder_returns_none_when_blank(self) -> None:
        info = lead_enricher._extract_builder({"applicant": "", "description": "  "})
        assert info["raw_name"] is None

    def test_geocode_explicit_lat_lng_wins(self) -> None:
        lat, lng, src = lead_enricher._geocode_lead({"latitude": 30.0, "longitude": -90.0})
        assert (lat, lng, src) == (30.0, -90.0, "explicit")

    def test_geocode_falls_back_to_region_centroid(self) -> None:
        lat, lng, src = lead_enricher._geocode_lead({"region": "houston_tx"})
        assert src == "region_centroid"
        # Houston centroid is around (29.76, -95.36).
        assert 29 < lat < 30
        assert -96 < lng < -95

    def test_geocode_returns_none_on_unknown_region(self) -> None:
        lat, lng, src = lead_enricher._geocode_lead({"region": "atlantis"})
        assert (lat, lng, src) == (None, None, None)

    def test_decision_maker_uses_explicit_field(self) -> None:
        lead = {"contact_name": "Jane Doe"}
        name, src = lead_enricher._find_decision_maker(lead)
        assert name == "Jane Doe"
        assert src == "contact_name"

    def test_decision_maker_parses_attn_pattern(self) -> None:
        lead = {"description": "Permit submitted attn: John Smith for development"}
        name, src = lead_enricher._find_decision_maker(lead)
        assert name == "John Smith"
        assert src == "description_parse"


class TestLeadEnricherEnrichLead:
    def test_enrich_lead_marks_status_ok_on_clean_record(self) -> None:
        lead = {
            "name": "Luxury Estates",
            "category": "C3F",
            "permit_value_usd": 1_500_000,
            "applicant": "BIG HOMES LLC",
            "region": "austin_tx",
            "score": 0.90,
        }
        enriched = lead_enricher.enrich_lead(lead)
        assert enriched.enrichment_status == "ok"
        assert enriched.grade == "A"
        assert enriched.property_value_estimate_usd == 1_500_000
        assert enriched.geo_source == "region_centroid"


# ---------------------------------------------------------------------------
# market_intelligence
# ---------------------------------------------------------------------------


class TestMarketIntelHelpers:
    def test_score_text_crypto_keywords_dominate(self) -> None:
        from lib.intel import market_intelligence as mi

        text = "bitcoin and ethereum hit new highs"
        score, kws = mi._score_text(text)
        assert score > 0
        assert "bitcoin" in kws
        assert "ethereum" in kws

    def test_score_text_clamps_at_one(self) -> None:
        from lib.intel import market_intelligence as mi

        # Stuff a lot of crypto keywords into one string.
        text = " ".join(mi.CRYPTO_KEYWORDS) + " " + " ".join(mi.MARKET_KEYWORDS)
        score, _ = mi._score_text(text)
        assert score == 1.0

    def test_parse_ff_date_handles_known_format(self) -> None:
        from lib.intel import market_intelligence as mi

        dt = mi._parse_ff_date("Apr 04, 2025", "8:30am")
        assert isinstance(dt, datetime)
        assert dt.year == 2025
        assert dt.month == 4
        assert dt.hour == 8
        assert dt.minute == 30

    def test_parse_ff_date_returns_none_on_garbage(self) -> None:
        from lib.intel import market_intelligence as mi

        assert mi._parse_ff_date("not-a-date", "now") is None

    def test_estimate_liq_band_long_cascade_when_close(self) -> None:
        from lib.intel import market_intelligence as mi

        # Funding > 0.0001 and price within 8% of long liq → cascade_risk_long
        band = mi._estimate_liq_band(
            "BTC",
            mark=100_000.0,
            oi_coins=10_000.0,
            funding=0.0015,  # very crowded longs
        )
        assert band.coin == "BTC"
        # liq_dist=0.06 at funding>=0.001 → long_prox==0.06 ≤ CASCADE_PROXIMITY=0.08
        assert band.flag == "cascade_risk_long"

    def test_estimate_liq_band_short_cascade_when_close(self) -> None:
        from lib.intel import market_intelligence as mi

        band = mi._estimate_liq_band(
            "ETH",
            mark=3000.0,
            oi_coins=1000.0,
            funding=-0.002,  # very crowded shorts
        )
        assert band.flag == "cascade_risk_short"

    def test_estimate_liq_band_neutral_when_calm(self) -> None:
        from lib.intel import market_intelligence as mi

        band = mi._estimate_liq_band(
            "BTC",
            mark=100_000.0,
            oi_coins=1000.0,
            funding=0.0,
        )
        # Zero funding → falls into the neutral branch
        assert band.flag == "neutral"


__all__ = [
    "TestLeadEnricherEnrichLead",
    "TestLeadEnricherFields",
    "TestLeadEnricherGrading",
    "TestMarketIntelHelpers",
    "TestSovereignThesisHelpers",
    "TestSovereignThesisParsing",
    "TestSovereignThesisReportShape",
]
