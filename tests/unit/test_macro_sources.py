from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from lib.macro import feedparser_compat
from lib.macro.sources import (
    FED_PRESS_RSS_URL,
    BISRSSSource,
    BLSEmploymentRSSSource,
    CFTCRSSSource,
    ECBRSSSource,
    FedRSSSource,
    FOMCCalendarSource,
    MacroEvent,
    SECAtomSource,
    SourceError,
    TreasuryAuctionsSource,
    build_default_sources,
    cache_base_dir,
    canonical_event_id,
    parse_feed_events,
    parse_fomc_calendar_html,
    parse_treasury_auctions_html,
    user_agent,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "macro"
SINCE = datetime(2026, 1, 1, tzinfo=UTC)


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("source_cls", "fixture_name", "title_fragment"),
    [
        (FedRSSSource, "fed_press_all.xml", "FOMC statement"),
        (CFTCRSSSource, "cftc_press_releases.rss", "Crypto Exchange"),
        (SECAtomSource, "sec_current.atom", "Coinbase"),
        (BLSEmploymentRSSSource, "bls_empsit.rss", "Payroll employment"),
        (ECBRSSSource, "ecb_press.rss", "Governing Council"),
        (BISRSSSource, "bis_press.rss", "crypto leverage"),
    ],
)
def test_feed_source_parses_official_fixture(source_cls, fixture_name, title_fragment, tmp_path):
    source = source_cls(cache_dir=tmp_path)
    events = source.parse(fixture(fixture_name), since=SINCE)
    assert len(events) == 2
    assert title_fragment in events[0].title
    assert events[0].metadata["official_source"] is True
    assert events[0].metadata["source_url"].startswith("https://")
    assert events[0].metadata["feed_url"] == source.url


@pytest.mark.parametrize(
    ("source_cls", "fixture_name"),
    [
        (FedRSSSource, "fed_press_all.xml"),
        (CFTCRSSSource, "cftc_press_releases.rss"),
        (SECAtomSource, "sec_current.atom"),
        (BLSEmploymentRSSSource, "bls_empsit.rss"),
        (ECBRSSSource, "ecb_press.rss"),
        (BISRSSSource, "bis_press.rss"),
    ],
)
def test_feed_since_filter_excludes_old_rows(source_cls, fixture_name, tmp_path):
    source = source_cls(cache_dir=tmp_path)
    since = datetime(2026, 3, 1, tzinfo=UTC)
    events = source.parse(fixture(fixture_name), since=since)
    assert all(event.published_at >= since for event in events)


@pytest.mark.parametrize(
    ("source_cls", "fixture_name"),
    [
        (FedRSSSource, "fed_press_all.xml"),
        (CFTCRSSSource, "cftc_press_releases.rss"),
        (SECAtomSource, "sec_current.atom"),
        (BLSEmploymentRSSSource, "bls_empsit.rss"),
        (ECBRSSSource, "ecb_press.rss"),
        (BISRSSSource, "bis_press.rss"),
    ],
)
def test_feed_event_ids_are_stable(source_cls, fixture_name, tmp_path):
    source = source_cls(cache_dir=tmp_path)
    first = source.parse(fixture(fixture_name), since=SINCE)[0]
    second = source.parse(fixture(fixture_name), since=SINCE)[0]
    assert first.id == second.id
    assert first.id == canonical_event_id(first.source, first.title, first.url, first.published_at)


def test_parse_feed_events_strips_html_summary():
    xml = """<?xml version="1.0"?><rss version="2.0"><channel><item>
    <title>Fed &amp; markets</title><link>https://example.test/fed</link>
    <pubDate>Thu, 29 Jan 2026 19:00:00 GMT</pubDate>
    <description><![CDATA[<p>Policy <b>unchanged</b></p>]]></description>
    </item></channel></rss>"""
    events = parse_feed_events(xml, source="fed_rss", label="Fed", feed_url=FED_PRESS_RSS_URL)
    assert events[0].title == "Fed & markets"
    assert events[0].summary == "Policy unchanged"


def test_parse_feed_events_uses_stdlib_fallback_when_feedparser_legacy_shim_missing(
    monkeypatch,
):
    monkeypatch.setattr(feedparser_compat, "_load_feedparser", lambda: None)
    xml = """<?xml version="1.0"?><rss version="2.0"><channel><item>
    <title>Fallback feed</title><link>https://example.test/fallback</link>
    <pubDate>Thu, 29 Jan 2026 19:00:00 GMT</pubDate>
    <description><![CDATA[<p>Parsed <b>safely</b></p>]]></description>
    </item></channel></rss>"""

    events = parse_feed_events(xml, source="fed_rss", label="Fed", feed_url=FED_PRESS_RSS_URL)

    assert events[0].title == "Fallback feed"
    assert events[0].summary == "Parsed safely"
    assert events[0].published_at == datetime(2026, 1, 29, 19, tzinfo=UTC)


def test_fomc_calendar_parser_extracts_forward_meetings():
    events = parse_fomc_calendar_html(
        fixture("fomc_calendar.html"),
        since=datetime(2026, 1, 1, tzinfo=UTC),
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert [event.title for event in events][:2] == [
        "FOMC meeting: January 28-29, 2026",
        "FOMC meeting: March 17-18, 2026",
    ]
    assert events[0].metadata["meeting_end_date"] == "2026-01-29"
    assert events[0].metadata["source_url"].endswith("fomccalendars.htm")


def test_fomc_calendar_since_filter():
    events = parse_fomc_calendar_html(
        fixture("fomc_calendar.html"),
        since=datetime(2026, 3, 1, tzinfo=UTC),
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert all(event.published_at >= datetime(2026, 3, 1, tzinfo=UTC) for event in events)
    assert events[0].title.startswith("FOMC meeting: March")


def test_treasury_auction_parser_extracts_table_rows():
    events = parse_treasury_auctions_html(fixture("treasury_auctions.html"), since=SINCE)
    assert len(events) == 2
    assert events[0].title == "Treasury auction: 10-Year Note (91282CZZ9)"
    assert events[0].metadata["security_type"] == "10-Year Note"
    assert events[0].metadata["source_url"].startswith("https://www.treasurydirect.gov")


def test_treasury_auction_since_filter():
    events = parse_treasury_auctions_html(
        fixture("treasury_auctions.html"),
        since=datetime(2026, 3, 8, tzinfo=UTC),
    )
    assert len(events) == 1
    assert "10-Year" in events[0].title


def test_build_default_sources_includes_all_eight(tmp_path):
    sources = build_default_sources(cache_dir=tmp_path, fetcher=lambda *_: "")
    assert [source.name for source in sources] == [
        "fed_rss",
        "fed_fomc",
        "cftc_rss",
        "sec_atom",
        "treasury_auctions",
        "bls_empsit_rss",
        "ecb_rss",
        "bis_rss",
    ]


def test_cache_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("SAPPHIRE_MACRO_CACHE_DIR", str(tmp_path / "macro-cache"))
    assert cache_base_dir() == tmp_path / "macro-cache"


def test_user_agent_env_override(monkeypatch):
    monkeypatch.setenv("SAPPHIRE_MACRO_USER_AGENT", "SapphireTest/1.0 contact=test@example.test")
    assert user_agent() == "SapphireTest/1.0 contact=test@example.test"


def test_pull_writes_cache_and_counter(tmp_path):
    calls: list[str] = []

    def fetcher(url, headers, timeout):
        calls.append(url)
        assert "SapphireMacroIntel" in headers["User-Agent"]
        return fixture("fed_press_all.xml")

    source = FedRSSSource(cache_dir=tmp_path, fetcher=fetcher)
    events = asyncio.run(source.pull(SINCE))
    assert len(events) == 2
    assert len(calls) == 1
    assert source.cached_payloads()
    counters = json.loads((tmp_path / "fed_rss" / "counters.json").read_text(encoding="utf-8"))
    assert counters["lifetime"] == 1


def test_rate_limit_uses_cached_payload(tmp_path):
    source = FedRSSSource(cache_dir=tmp_path, fetcher=lambda *_: pytest.fail("network disabled"))
    source.source_cache_dir.mkdir(parents=True)
    source._raw_cache_path(source.url).write_text(fixture("fed_press_all.xml"), encoding="utf-8")
    (source.source_cache_dir / "counters.json").write_text(
        json.dumps({"pulls": [time.time()] * 4, "lifetime": 4}),
        encoding="utf-8",
    )
    events = asyncio.run(source.pull(SINCE))
    assert len(events) == 2


def test_rate_limit_without_cache_raises(tmp_path):
    source = FedRSSSource(cache_dir=tmp_path, fetcher=lambda *_: "")
    source.source_cache_dir.mkdir(parents=True)
    (source.source_cache_dir / "counters.json").write_text(
        json.dumps({"pulls": [time.time()] * 4, "lifetime": 4}),
        encoding="utf-8",
    )
    with pytest.raises(SourceError):
        asyncio.run(source.pull(SINCE))


def test_html_source_respects_robots_and_user_agent(tmp_path):
    calls: list[tuple[str, str]] = []

    def fetcher(url, headers, timeout):
        calls.append((url, headers["User-Agent"]))
        if url.endswith("/robots.txt"):
            return "User-agent: *\nAllow: /\n"
        return fixture("fomc_calendar.html")

    source = FOMCCalendarSource(cache_dir=tmp_path, fetcher=fetcher)
    events = asyncio.run(source.pull(SINCE))
    assert events
    assert calls[0][0].endswith("/robots.txt")
    assert "SapphireMacroIntel" in calls[0][1]


def test_html_source_fails_closed_when_robots_disallow(tmp_path):
    def fetcher(url, headers, timeout):
        if url.endswith("/robots.txt"):
            return "User-agent: *\nDisallow: /\n"
        return fixture("treasury_auctions.html")

    source = TreasuryAuctionsSource(cache_dir=tmp_path, fetcher=fetcher)
    with pytest.raises(SourceError):
        asyncio.run(source.pull(SINCE))


def test_macro_event_round_trip_dict():
    event = MacroEvent(
        id="abc",
        source="fed_rss",
        title="FOMC Holds Rates",
        summary="Policy unchanged",
        url="https://www.federalreserve.gov/example",
        published_at=datetime(2026, 1, 29, 19, tzinfo=UTC),
        metadata={"source_url": "https://www.federalreserve.gov/example"},
    )
    assert MacroEvent.from_dict(event.to_dict()).to_dict() == event.to_dict()
