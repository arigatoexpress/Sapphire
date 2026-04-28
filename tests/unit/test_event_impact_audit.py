from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from lib.event_impact.audit import (
    audit_expected_reactions,
    audit_from_files,
    load_bars_by_asset,
    load_model,
    realized_return_pct,
)
from lib.event_impact.event_corpus import HistoricalEvent, load_events
from lib.event_impact.impact_modeler import PriceBar

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "event_impact"
EVENTS = FIXTURES / "audit_events.jsonl"
BARS = FIXTURES / "audit_bars.json"
MODEL = FIXTURES / "audit_model.json"


def test_realized_return_uses_first_bars_at_or_after_horizon():
    event = load_events(EVENTS)[0]
    bars = [
        PriceBar(timestamp=datetime(2024, 1, 1, tzinfo=UTC), close=100),
        PriceBar(timestamp=datetime(2024, 1, 2, tzinfo=UTC), close=98),
    ]
    assert realized_return_pct(event, bars, 24) == -2.0


def test_load_bars_by_asset_accepts_asset_mapping_fixture():
    bars = load_bars_by_asset(BARS)
    assert sorted(bars) == ["BTC", "ETH"]
    assert bars["BTC"][0].close == 100.0


def test_audit_from_files_scores_expected_vs_realized_fixture():
    report = audit_from_files(
        events_path=EVENTS,
        bars_path=BARS,
        model_path=MODEL,
        horizons_hours=(24,),
    ).to_dict()
    summary = report["summary"]
    assert summary["observations"] == 3
    assert summary["scored"] == 3
    assert summary["direction_correct"] == 2
    assert summary["direction_accuracy"] == 0.666667
    assert "small_scored_sample_wide_intervals" in summary["caveats"]


def test_audit_marks_direction_mismatch_without_hiding_error():
    report = audit_from_files(
        events_path=EVENTS,
        bars_path=BARS,
        model_path=MODEL,
        horizons_hours=(24,),
    ).to_dict()
    mismatch = [
        row
        for row in report["observations_detail"]
        if row["event_id"] == "audit_bank_failure"
    ][0]
    assert mismatch["scored"] is True
    assert mismatch["direction_match"] is False
    assert mismatch["actual_return_pct"] == -2.0
    assert mismatch["absolute_error_pct"] == 4.0


def test_audit_reports_no_data_for_missing_profile():
    events = load_events(EVENTS)
    bars = load_bars_by_asset(BARS)
    model = load_model(MODEL)
    report = audit_expected_reactions(events, bars, model, horizons_hours=(6,)).to_dict()
    assert report["summary"]["scored"] == 0
    assert report["summary"]["no_data"] == 3
    assert "some_events_have_no_expected_profile" in report["summary"]["caveats"]


def test_audit_reports_missing_ohlcv_as_unscored():
    events = load_events(EVENTS)
    model = load_model(MODEL)
    report = audit_expected_reactions(events, {"BTC": load_bars_by_asset(BARS)["BTC"]}, model, horizons_hours=(24,)).to_dict()
    eth = [row for row in report["observations_detail"] if row["asset"] == "ETH"][0]
    assert eth["scored"] is False
    assert "missing_post_event_bar" in eth["notes"]
    assert report["summary"]["missing_actual"] == 1


def test_audit_asset_filter_limits_observations():
    report = audit_from_files(
        events_path=EVENTS,
        bars_path=BARS,
        model_path=MODEL,
        horizons_hours=(24,),
        assets=("ETH",),
    ).to_dict()
    assert report["summary"]["observations"] == 1
    assert report["observations_detail"][0]["asset"] == "ETH"


def test_audit_accepts_model_dict_and_raw_bar_dicts():
    events = load_events(EVENTS)[:1]
    bars = {"BTC": [{"timestamp": "2024-01-01T00:00:00Z", "close": 100}, {"timestamp": "2024-01-02T00:00:00Z", "close": 98}]}
    model = load_model(MODEL).to_dict()
    report = audit_expected_reactions(events, bars, model, horizons_hours=(24,)).to_dict()
    assert report["summary"]["direction_accuracy"] == 1.0


def test_historical_event_fixture_has_citations():
    event = HistoricalEvent.from_dict(load_events(EVENTS)[0].to_dict())
    assert event.metadata["source_url"].startswith("https://")
