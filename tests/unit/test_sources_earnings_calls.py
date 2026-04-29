"""Unit tests for :mod:`lib.sources.earnings_calls`.

All HTTP is mocked.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from lib.sources import earnings_calls
from lib.sources.earnings_calls import (
    PAID_PROVIDER_STUBS,
    EarningsCallSource,
    IRSubscription,
    RateLimiter,
    TranscriptSentiment,
    _parse_minimal_yaml,
    load_ir_config,
    summarize_directions,
)

# ---------------------------------------------------------------------------
# Config + minimal YAML parsing
# ---------------------------------------------------------------------------


def test_load_ir_config_returns_empty_when_file_missing(tmp_path: Path) -> None:
    assert load_ir_config(tmp_path / "nope.yaml") == []


def test_load_ir_config_parses_minimal_yaml(tmp_path: Path) -> None:
    cfg = tmp_path / "earnings_rss.yaml"
    cfg.write_text(
        "feeds:\n"
        "  - ticker: AAPL\n"
        "    rss_url: https://investor.apple.com/rss-news\n"
        "  - ticker: nvda\n"
        "    rss_url: https://investor.nvidia.com/rss\n",
        encoding="utf-8",
    )
    subs = load_ir_config(cfg)
    assert [s.ticker for s in subs] == ["AAPL", "NVDA"]
    assert subs[0].rss_url.endswith("rss-news")


def test_minimal_yaml_handles_top_level_and_list_mappings() -> None:
    parsed = _parse_minimal_yaml(
        "version: 1\nfeeds:\n  - ticker: A\n    rss_url: u1\n  - ticker: B\n    rss_url: u2\n"
    )
    assert parsed["version"] == "1"
    assert isinstance(parsed["feeds"], list)
    assert parsed["feeds"][0]["ticker"] == "A"
    assert parsed["feeds"][1]["rss_url"] == "u2"


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


def test_rate_limiter_default_rate_is_5() -> None:
    rl = RateLimiter()
    assert rl.rate == 5


def test_rate_limiter_throttles_close_calls() -> None:
    rl = RateLimiter(rate=5)
    sleeps: list[float] = []
    times = iter([0.0, 0.0, 0.05, 0.05])

    rl.acquire(sleep=lambda d: sleeps.append(d), now=lambda: next(times))
    rl.acquire(sleep=lambda d: sleeps.append(d), now=lambda: next(times))
    assert any(s > 0 for s in sleeps)


# ---------------------------------------------------------------------------
# RSS parsing
# ---------------------------------------------------------------------------


_RSS_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Apple Investor Relations</title>
    <item>
      <title>Apple Q2 2026 earnings results</title>
      <link>https://investor.apple.com/q2-2026</link>
      <pubDate>Mon, 28 Apr 2026 12:00:00 GMT</pubDate>
      <description>Apple beat consensus revenue estimates and raised guidance.</description>
    </item>
    <item>
      <title>Press release: Recycling program update</title>
      <link>https://investor.apple.com/recycling</link>
      <pubDate>Mon, 14 Apr 2026 12:00:00 GMT</pubDate>
      <description>Not earnings related.</description>
    </item>
    <item>
      <title>Apple Q1 2026 earnings call replay</title>
      <link>https://investor.apple.com/q1-2026</link>
      <pubDate>Mon, 14 Jan 2026 12:00:00 GMT</pubDate>
      <description>Strong growth and record services revenue.</description>
    </item>
  </channel>
</rss>
"""


def test_rss_parser_returns_items() -> None:
    rows = EarningsCallSource._parse_rss(_RSS_FIXTURE)
    assert len(rows) == 3
    assert rows[0]["title"].startswith("Apple Q2")
    assert rows[2]["title"].startswith("Apple Q1")


def test_is_earnings_related_filters_non_earnings_items() -> None:
    assert EarningsCallSource._is_earnings_related("Apple Q2 2026 earnings results") is True
    assert EarningsCallSource._is_earnings_related("Recycling program update") is False
    # Filter is title-only — descriptions can mention "earnings" without the
    # item itself being an earnings event.
    assert EarningsCallSource._is_earnings_related(
        "Recycling press release", "Q3 earnings comparison"
    ) is False
    assert EarningsCallSource._is_earnings_related("Annual results FY26") is True


def test_rss_parser_tolerates_garbage_text() -> None:
    assert EarningsCallSource._parse_rss("<not xml>") == []
    assert EarningsCallSource._parse_rss("") == []


# ---------------------------------------------------------------------------
# Sentiment scoring
# ---------------------------------------------------------------------------


def test_score_text_counts_positive_and_negative_terms() -> None:
    pos, neg = EarningsCallSource.score_text(
        "Apple beat consensus and raised guidance; record growth."
    )
    assert pos > 0
    assert neg == 0


def test_score_text_negative_outweighs_for_miss() -> None:
    pos, neg = EarningsCallSource.score_text(
        "Apple missed revenue, lowered guidance, and disclosed a lawsuit."
    )
    assert neg > pos


def test_score_text_blank_returns_zero() -> None:
    assert EarningsCallSource.score_text("") == (0, 0)


def test_classify_entry_returns_bull_for_positive_text() -> None:
    sentiment = EarningsCallSource.classify_entry(
        ticker="AAPL",
        entry={
            "title": "Q2 2026 results — record growth",
            "description": "Apple beat consensus and raised guidance.",
            "published_at": "Mon, 28 Apr 2026 12:00:00 GMT",
            "url": "https://investor.apple.com/q2",
            "source_kind": "rss",
        },
    )
    assert sentiment.direction == "bull"
    assert sentiment.confidence > 0.30
    assert sentiment.ticker == "AAPL"


def test_classify_entry_returns_bear_for_negative_text() -> None:
    sentiment = EarningsCallSource.classify_entry(
        ticker="AAPL",
        entry={
            "title": "Q2 2026 results",
            "description": "Apple missed estimates; lowered guidance and disclosed a lawsuit.",
            "published_at": "Mon, 28 Apr 2026 12:00:00 GMT",
        },
    )
    assert sentiment.direction == "bear"


# ---------------------------------------------------------------------------
# Snapshot orchestration
# ---------------------------------------------------------------------------


def test_dry_run_returns_empty_when_no_cache_and_no_live(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("SAPPHIRE_EARNINGS_LIVE", raising=False)
    src = EarningsCallSource(
        config_path=tmp_path / "missing.yaml",
        cache_path=tmp_path / "cache.json",
        fixture_root=tmp_path / "fixtures",
        fetcher=lambda url, headers: "",
    )
    sigs = src.list_sentiments()
    assert sigs == []


def test_live_pull_consumes_rss_and_filters_to_earnings_items(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SAPPHIRE_EARNINGS_LIVE", "1")
    cfg = tmp_path / "feeds.yaml"
    cfg.write_text(
        "feeds:\n  - ticker: AAPL\n    rss_url: https://investor.apple.com/rss\n",
        encoding="utf-8",
    )
    src = EarningsCallSource(
        config_path=cfg,
        cache_path=tmp_path / "cache.json",
        fixture_root=tmp_path / "fixtures",
        fetcher=lambda url, headers: _RSS_FIXTURE,
    )
    sentiments = src.list_sentiments()
    # Two of the three RSS items are earnings related.
    assert len(sentiments) == 2
    # Both Apple → all bull or neutral; the recycling press release was filtered out.
    for s in sentiments:
        assert s.ticker == "AAPL"
    assert {s.title for s in sentiments} == {
        "Apple Q2 2026 earnings results",
        "Apple Q1 2026 earnings call replay",
    }


def test_fixture_loader_picks_up_local_transcripts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_EARNINGS_LIVE", "1")
    cfg = tmp_path / "feeds.yaml"
    cfg.write_text(
        "feeds:\n  - ticker: NVDA\n    rss_url: \"\"\n",
        encoding="utf-8",
    )
    fixture_dir = tmp_path / "fixtures" / "NVDA"
    fixture_dir.mkdir(parents=True)
    (fixture_dir / "2026-q1.txt").write_text(
        "NVIDIA beat estimates and announced record growth in data-center revenue.",
        encoding="utf-8",
    )
    src = EarningsCallSource(
        config_path=cfg,
        cache_path=tmp_path / "cache.json",
        fixture_root=tmp_path / "fixtures",
        fetcher=lambda url, headers: "",
    )
    sentiments = src.list_sentiments()
    assert len(sentiments) == 1
    assert sentiments[0].source_kind == "fixture"
    assert sentiments[0].direction == "bull"


def test_latest_for_returns_signal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_EARNINGS_LIVE", "1")
    cfg = tmp_path / "feeds.yaml"
    cfg.write_text(
        "feeds:\n  - ticker: AAPL\n    rss_url: https://investor.apple.com/rss\n",
        encoding="utf-8",
    )
    src = EarningsCallSource(
        config_path=cfg,
        cache_path=tmp_path / "cache.json",
        fixture_root=tmp_path / "fixtures",
        fetcher=lambda url, headers: _RSS_FIXTURE,
    )
    sig = src.latest_for("AAPL", "1d")
    assert sig is not None
    assert sig.symbol == "AAPL"
    assert sig.direction == "bull"
    assert sig.raw["live_operator_flag"] is True


def test_latest_for_returns_none_for_unknown_ticker(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_EARNINGS_LIVE", "1")
    cfg = tmp_path / "feeds.yaml"
    cfg.write_text(
        "feeds:\n  - ticker: AAPL\n    rss_url: https://investor.apple.com/rss\n",
        encoding="utf-8",
    )
    src = EarningsCallSource(
        config_path=cfg,
        cache_path=tmp_path / "cache.json",
        fixture_root=tmp_path / "fixtures",
        fetcher=lambda url, headers: _RSS_FIXTURE,
    )
    assert src.latest_for("ZZZZ", "1d") is None


def test_paid_provider_stubs_are_documented_only() -> None:
    # We MUST NOT have any "wired" provider in the free-tier-only release.
    for stub in PAID_PROVIDER_STUBS:
        assert stub["status"] == "not_wired"
        assert stub["docs"].startswith("https://")


def test_summarize_directions_aggregates() -> None:
    items = [
        TranscriptSentiment("A", "bull", 0.5, "", "", "", "rss", 0, 0),
        TranscriptSentiment("A", "bear", 0.5, "", "", "", "rss", 0, 0),
        TranscriptSentiment("A", "bull", 0.5, "", "", "", "rss", 0, 0),
        TranscriptSentiment("A", "neutral", 0.5, "", "", "", "rss", 0, 0),
    ]
    out = summarize_directions(items)
    assert out == {"bull": 2, "bear": 1, "neutral": 1}


def test_earnings_registered_in_correlator_default_sources() -> None:
    from lib.correlator.sources import available_sources

    assert EarningsCallSource in available_sources()


def test_cache_used_within_ttl(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SAPPHIRE_EARNINGS_LIVE", "1")
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "retrieved_at": datetime.now(UTC).isoformat(),
                "entries": {
                    "AAPL": [
                        {
                            "title": "Q2 earnings beat",
                            "description": "Beat consensus, raised guidance.",
                            "published_at": "2026-04-28T12:00:00+00:00",
                            "url": "https://x",
                            "source_kind": "rss",
                            "ticker": "AAPL",
                        }
                    ]
                },
                "subs": [],
            }
        ),
        encoding="utf-8",
    )
    fetched: list[str] = []
    src = EarningsCallSource(
        config_path=tmp_path / "missing.yaml",
        cache_path=cache_path,
        fixture_root=tmp_path / "fixtures",
        fetcher=lambda url, headers: fetched.append(url) or "",
    )
    sentiments = src.list_sentiments(subscriptions=[IRSubscription(ticker="AAPL", rss_url="https://x")])
    assert fetched == [], "cache hit should suppress all live fetches"
    assert len(sentiments) == 1
    assert sentiments[0].direction == "bull"


def test_module_exports_match_public_api() -> None:
    public = set(earnings_calls.__all__)
    expected = {
        "EarningsCallSource",
        "IRSubscription",
        "PAID_PROVIDER_STUBS",
        "POSITIVE_TERMS",
        "NEGATIVE_TERMS",
        "RateLimiter",
        "TranscriptSentiment",
        "load_ir_config",
        "summarize_directions",
    }
    assert expected.issubset(public)
