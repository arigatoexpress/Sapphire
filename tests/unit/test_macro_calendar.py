from __future__ import annotations

from datetime import UTC, datetime, timedelta

from lib.macro.calendar import (
    MacroCalendar,
    build_calendar,
    calendar_from_dicts,
    event_to_calendar,
    first_friday,
    payroll_calendar_events,
)
from lib.macro.sources import MacroEvent


def macro_event(
    title: str,
    *,
    source: str,
    when: datetime,
    kind: str = "scheduled_meeting",
) -> MacroEvent:
    return MacroEvent(
        id=f"{source}-{when.date()}",
        source=source,
        title=title,
        summary=title,
        url="https://official.example.test/calendar",
        published_at=when,
        metadata={
            "source_url": "https://official.example.test/calendar",
            "official_source": True,
            "event_kind": kind,
        },
    )


NOW = datetime(2026, 3, 1, 12, tzinfo=UTC)


def test_event_to_calendar_converts_fomc_event():
    event = macro_event("FOMC meeting: March 17-18, 2026", source="fed_fomc", when=NOW)
    cal = event_to_calendar(event)
    assert cal is not None
    assert cal.category == "monetary_policy"
    assert cal.source_url.startswith("https://official")


def test_event_to_calendar_ignores_plain_feed_publication():
    event = macro_event("Fed speech", source="fed_rss", when=NOW, kind="publication")
    assert event_to_calendar(event) is None


def test_build_calendar_sorts_forward_events():
    later = macro_event(
        "Treasury auction: 10-Year Note", source="treasury_auctions", when=NOW + timedelta(days=5)
    )
    sooner = macro_event(
        "FOMC meeting: March 17-18, 2026", source="fed_fomc", when=NOW + timedelta(days=2)
    )
    cal = build_calendar([later, sooner], now=NOW, include_static=False)
    assert [event.title for event in cal.events] == [sooner.title, later.title]


def test_build_calendar_filters_past_events():
    past = macro_event("Old FOMC", source="fed_fomc", when=NOW - timedelta(days=1))
    future = macro_event("Future FOMC", source="fed_fomc", when=NOW + timedelta(days=1))
    cal = build_calendar([past, future], now=NOW, include_static=False)
    assert [event.title for event in cal.events] == ["Future FOMC"]


def test_build_calendar_respects_90_day_horizon():
    far = macro_event("Far FOMC", source="fed_fomc", when=NOW + timedelta(days=120))
    cal = build_calendar([far], now=NOW, include_static=False)
    assert cal.events == ()


def test_in_next_hours_returns_window_only():
    soon = macro_event("Soon FOMC", source="fed_fomc", when=NOW + timedelta(hours=6))
    later = macro_event("Later FOMC", source="fed_fomc", when=NOW + timedelta(hours=30))
    cal = build_calendar([soon, later], now=NOW, include_static=False)
    assert [event.title for event in cal.in_next_hours(24, now=NOW)] == ["Soon FOMC"]


def test_next_event_for_asset_matches_assets_case_insensitive():
    event = macro_event(
        "Treasury auction: 10-Year Note", source="treasury_auctions", when=NOW + timedelta(hours=6)
    )
    cal = build_calendar([event], now=NOW, include_static=False)
    assert cal.next_event_for_asset("btc", now=NOW) is not None


def test_next_event_for_asset_returns_none_when_absent():
    event = macro_event("ECB bank lending survey", source="ecb_rss", when=NOW + timedelta(hours=6))
    cal = build_calendar([event], now=NOW, include_static=False)
    assert cal.next_event_for_asset("SOL", now=NOW) is None


def test_calendar_round_trips_dicts():
    event = macro_event(
        "FOMC meeting: March 17-18, 2026", source="fed_fomc", when=NOW + timedelta(hours=6)
    )
    cal = build_calendar([event], now=NOW, include_static=False)
    round_trip = calendar_from_dicts(cal.to_dicts())
    assert round_trip.to_dicts() == cal.to_dicts()


def test_first_friday_helper():
    assert first_friday(2026, 3).isoformat() == "2026-03-06"


def test_payroll_calendar_events_adds_forward_bls_release():
    rows = payroll_calendar_events(now=NOW, days=45)
    assert rows
    assert rows[0].source == "bls_empsit_schedule"
    assert rows[0].metadata["official_source"] is True


def test_macro_calendar_dedupes_ids():
    event = build_calendar(
        [macro_event("FOMC", source="fed_fomc", when=NOW + timedelta(days=1))],
        now=NOW,
        include_static=False,
    ).events[0]
    cal = MacroCalendar([event, event])
    assert len(cal.events) == 1
