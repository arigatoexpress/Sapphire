from __future__ import annotations

from datetime import UTC, datetime

from lib.event_impact.impact_modeler import ImpactModel, ImpactProfile
from lib.event_impact.lookup import MacroEvent, lookup


def _model():
    return ImpactModel(
        generated_at="2024-01-01T00:00:00+00:00",
        horizons_hours=(1, 24),
        profiles=(
            ImpactProfile(
                "fomc_decision", "rate_hike", "BTC", 24, -1.2, -1.0, 8, 2.0, (-3.0, 0.6), -0.5
            ),
            ImpactProfile("fomc_decision", "*", "BTC", 24, -0.4, -0.2, 30, 1.0, (-0.8, 0.0), -0.2),
            ImpactProfile("macro_shock", "*", "ETH", 1, 2.5, 2.1, 3, 4.0, (-9.5, 14.5), 0.33),
        ),
    )


def test_macro_event_from_dict_accepts_assets_alias():
    event = MacroEvent.from_any({"title": "x", "category": "fomc_decision", "assets": ["btc"]})
    assert event.assets_likely_affected == ("BTC",)


def test_macro_event_from_dict_parses_timestamp():
    event = MacroEvent.from_any(
        {"title": "x", "category": "fomc_decision", "timestamp": "2024-01-01T00:00:00Z"}
    )
    assert event.timestamp == datetime(2024, 1, 1, tzinfo=UTC)


def test_macro_event_from_object_shape():
    class Obj:
        title = "x"
        category = "macro_shock"
        sub_category = "bank_failure"
        timestamp = None
        assets_likely_affected = ["ETH"]
        source_url = "https://example.com"
        metadata = {}

    assert MacroEvent.from_any(Obj()).assets_likely_affected == ("ETH",)


def test_lookup_prefers_exact_profile():
    reaction = lookup(
        {"category": "fomc_decision", "sub_category": "rate_hike"}, "BTC", 24, model=_model()
    )
    assert reaction.matched_level == "exact"
    assert reaction.mean_return_pct == -1.2


def test_lookup_falls_back_to_category_profile():
    reaction = lookup(
        {"category": "fomc_decision", "sub_category": "dovish_hold"}, "BTC", 24, model=_model()
    )
    assert reaction.matched_level == "category"
    assert reaction.n == 30


def test_lookup_returns_wide_band_when_no_data():
    reaction = lookup(
        {"category": "etf_approval", "sub_category": "spot_btc_etf_approval"},
        "SOL",
        24,
        model=_model(),
    )
    assert reaction.matched_level == "no_data"
    assert reaction.confidence_interval_95 == (-100.0, 100.0)


def test_lookup_accepts_model_dict():
    reaction = lookup(
        {"category": "fomc_decision", "sub_category": "rate_hike"},
        "BTC",
        24,
        model=_model().to_dict(),
    )
    assert reaction.matched_level == "exact"


def test_lookup_normalizes_asset_case():
    reaction = lookup(
        {"category": "macro_shock", "sub_category": "bank_failure"}, "eth", 1, model=_model()
    )
    assert reaction.asset == "ETH"


def test_lookup_confidence_medium_for_large_n():
    reaction = lookup(
        {"category": "fomc_decision", "sub_category": "other"}, "BTC", 24, model=_model()
    )
    assert reaction.confidence == "medium"


def test_lookup_confidence_low_for_profile_n_between_5_and_19():
    reaction = lookup(
        {"category": "fomc_decision", "sub_category": "rate_hike"}, "BTC", 24, model=_model()
    )
    assert reaction.confidence == "low"


def test_lookup_confidence_very_low_for_small_profile():
    reaction = lookup(
        {"category": "macro_shock", "sub_category": "bank_failure"}, "ETH", 1, model=_model()
    )
    assert reaction.confidence == "very_low"


def test_expected_reaction_to_dict_uses_list_ci():
    reaction = lookup(
        {"category": "fomc_decision", "sub_category": "rate_hike"}, "BTC", 24, model=_model()
    )
    assert isinstance(reaction.to_dict()["confidence_interval_95"], list)


def test_lookup_default_subcategory_is_wildcard():
    reaction = lookup({"category": "fomc_decision"}, "BTC", 24, model=_model())
    assert reaction.matched_level == "category"


def test_lookup_unknown_horizon_returns_no_data():
    reaction = lookup(
        {"category": "fomc_decision", "sub_category": "rate_hike"}, "BTC", 168, model=_model()
    )
    assert reaction.n == 0


def test_lookup_keeps_no_data_note_honest():
    reaction = lookup({"category": "unknown"}, "BTC", 24, model=_model())
    assert "not a trading signal" in reaction.notes[0]
