from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from lib.event_impact.event_corpus import HistoricalEvent
from lib.event_impact.impact_modeler import (
    ImpactModel,
    PriceBar,
    build_impact_model,
    normalize_bars,
)

BASE = datetime(2024, 1, 1, tzinfo=UTC)


def _event(event_id: str, hours: int, category="fomc_decision", sub_category="rate_hike", assets=("BTC",)):
    return HistoricalEvent(
        event_id=event_id,
        timestamp=BASE + timedelta(hours=hours),
        category=category,
        sub_category=sub_category,
        title=event_id,
        assets=tuple(assets),
        metadata={"source_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"},
    )


def _bars(asset="BTC", start=100.0, step=1.0, count=220):
    return [
        PriceBar(timestamp=BASE + timedelta(hours=i), close=start + step * i)
        for i in range(count)
    ]


def _profile(model, category="fomc_decision", sub_category="rate_hike", asset="BTC", horizon=6):
    return model.profile_map()[(category, sub_category, asset, horizon)]


def test_normalize_bars_accepts_dicts_and_sorts():
    bars = normalize_bars(
        [
            {"timestamp": "2024-01-01T02:00:00+00:00", "close": 102},
            {"timestamp": "2024-01-01T00:00:00+00:00", "close": 100},
        ]
    )
    assert [bar.close for bar in bars] == [100.0, 102.0]


def test_price_bar_from_dict_requires_timestamp():
    with pytest.raises(ValueError, match="timestamp"):
        PriceBar.from_dict({"close": 1})


def test_price_bar_from_dict_normalizes_naive_timestamp_to_utc():
    assert PriceBar.from_dict({"timestamp": "2024-01-01T00:00:00", "close": 1}).timestamp.tzinfo is not None


def test_model_computes_expected_positive_reaction():
    event = _event("e1", 0)
    model = build_impact_model([event], {"BTC": _bars()}, horizons_hours=(6,))
    profile = _profile(model)
    assert profile.mean_return_pct == 6.0


def test_model_computes_negative_reaction():
    model = build_impact_model([_event("e1", 0)], {"BTC": _bars(start=200, step=-1)}, horizons_hours=(6,))
    assert _profile(model).mean_return_pct == -3.0


def test_model_uses_close_at_or_after_event_timestamp():
    event = _event("e1", 1)
    bars = [PriceBar(BASE, 100), PriceBar(BASE + timedelta(hours=2), 110), PriceBar(BASE + timedelta(hours=8), 121)]
    model = build_impact_model([event], {"BTC": bars}, horizons_hours=(6,))
    assert _profile(model).mean_return_pct == 10.0


def test_model_emits_category_fallback_profile():
    model = build_impact_model([_event("e1", 0)], {"BTC": _bars()}, horizons_hours=(1,))
    assert ("fomc_decision", "*", "BTC", 1) in model.profile_map()


def test_model_handles_multiple_assets():
    event = _event("e1", 0, assets=("BTC", "ETH"))
    model = build_impact_model([event], {"BTC": _bars(), "ETH": _bars(start=50, step=2)}, horizons_hours=(1,))
    assert ("fomc_decision", "rate_hike", "ETH", 1) in model.profile_map()


def test_missing_asset_bars_are_skipped():
    model = build_impact_model([_event("e1", 0, assets=("SOL",))], {"BTC": _bars()}, horizons_hours=(1,))
    assert model.profiles == ()


def test_missing_future_horizon_is_skipped():
    model = build_impact_model([_event("e1", 219)], {"BTC": _bars(count=220)}, horizons_hours=(6,))
    assert model.profiles == ()


def test_small_sample_forces_wide_band():
    model = build_impact_model([_event("e1", 0)], {"BTC": _bars()}, horizons_hours=(1,), min_sample_for_tight_band=5)
    profile = _profile(model, horizon=1)
    assert profile.confidence_interval_95[1] - profile.confidence_interval_95[0] >= 24
    assert "small_sample_wide_band" in profile.notes


def test_larger_sample_can_have_tighter_band():
    events = [_event(f"e{i}", i * 10) for i in range(8)]
    model = build_impact_model(events, {"BTC": _bars(count=200)}, horizons_hours=(1,), min_sample_for_tight_band=5)
    profile = _profile(model, horizon=1)
    assert profile.n == 8
    assert "small_sample_wide_band" not in profile.notes


def test_direction_consensus_all_positive_is_one():
    events = [_event(f"e{i}", i * 10) for i in range(3)]
    profile = _profile(build_impact_model(events, {"BTC": _bars(count=200)}, horizons_hours=(1,)), horizon=1)
    assert profile.direction_consensus == 1.0


def test_direction_consensus_all_negative_is_minus_one():
    events = [_event(f"e{i}", i * 10) for i in range(3)]
    profile = _profile(build_impact_model(events, {"BTC": _bars(start=200, step=-1, count=200)}, horizons_hours=(1,)), horizon=1)
    assert profile.direction_consensus == -1.0


def test_mixed_direction_consensus_is_between_bounds():
    events = [_event("up", 0), _event("down", 10)]
    bars = _bars(count=50)
    bars[11] = PriceBar(BASE + timedelta(hours=11), 50)
    profile = _profile(build_impact_model(events, {"BTC": bars}, horizons_hours=(1,)), horizon=1)
    assert -1.0 <= profile.direction_consensus <= 1.0


def test_model_to_dict_round_trips():
    model = build_impact_model([_event("e1", 0)], {"BTC": _bars()}, horizons_hours=(1,))
    restored = ImpactModel.from_dict(model.to_dict())
    assert restored.profile_map().keys() == model.profile_map().keys()


def test_model_metadata_records_assets_and_events():
    model = build_impact_model([_event("e1", 0)], {"BTC": _bars()}, horizons_hours=(1,))
    assert model.metadata["events_seen"] == 1
    assert model.metadata["assets_seen"] == ["BTC"]


def test_profile_serialization_uses_json_lists():
    profile = _profile(build_impact_model([_event("e1", 0)], {"BTC": _bars()}, horizons_hours=(1,)), horizon=1)
    assert isinstance(profile.to_dict()["confidence_interval_95"], list)


def test_multiple_horizons_are_modeled():
    model = build_impact_model([_event("e1", 0)], {"BTC": _bars()}, horizons_hours=(1, 6, 24))
    keys = model.profile_map()
    assert ("fomc_decision", "rate_hike", "BTC", 24) in keys


def test_different_subcategories_stay_separate():
    events = [_event("hike", 0, sub_category="rate_hike"), _event("cut", 10, sub_category="rate_cut")]
    model = build_impact_model(events, {"BTC": _bars()}, horizons_hours=(1,))
    assert ("fomc_decision", "rate_hike", "BTC", 1) in model.profile_map()
    assert ("fomc_decision", "rate_cut", "BTC", 1) in model.profile_map()


def test_category_fallback_combines_subcategories():
    events = [_event("hike", 0, sub_category="rate_hike"), _event("cut", 10, sub_category="rate_cut")]
    profile = build_impact_model(events, {"BTC": _bars()}, horizons_hours=(1,)).profile_map()[("fomc_decision", "*", "BTC", 1)]
    assert profile.n == 2


def test_zero_or_negative_start_price_skips_reaction():
    bars = [PriceBar(BASE, 0), PriceBar(BASE + timedelta(hours=1), 100)]
    model = build_impact_model([_event("e1", 0)], {"BTC": bars}, horizons_hours=(1,))
    assert model.profiles == ()


def test_survivorship_bias_annotation_can_live_in_event_metadata():
    event = _event("ceased", 0)
    event = HistoricalEvent(**{**event.__dict__, "metadata": {"source_url": "https://example.com", "survivorship_note": "venue ceased"}})
    assert event.metadata["survivorship_note"] == "venue ceased"
