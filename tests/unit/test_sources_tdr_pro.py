from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from lib.sources.tdr_pro import TDRProEpisode, TDRProSource

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "tdr_pro"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_feed_extracts_episodes_and_transcripts() -> None:
    source = TDRProSource()
    episodes = source.parse(fixture("tdr_pro_feed.xml"))

    assert len(episodes) == 2
    ep = episodes[0]
    assert ep.title == "TDR Pro’s 1st-Year Portfolio Audit"
    assert ep.episode == "28"
    assert ep.duration_seconds == 2893
    assert ep.transcript_url == "https://share.transistor.fm/s/09b6f51a/transcript.txt"
    assert ep.audio_url == "https://media.transistor.fm/09b6f51a/babefc46.mp3"
    assert ep.published_at == datetime(2026, 7, 15, 13, 55, 35, tzinfo=UTC)


def test_parse_feed_html_description_is_stripped() -> None:
    source = TDRProSource()
    episodes = source.parse(fixture("tdr_pro_feed.xml"))
    assert episodes[0].description == "Mike opens the books on TDR Pro’s first year."


def test_episode_slug_uses_episode_and_title() -> None:
    ep = TDRProEpisode(
        guid="g1",
        title="TDR Pro’s 1st-Year Portfolio Audit",
        description="desc",
        url="https://example.test/e28",
        published_at=datetime.now(UTC),
        episode="28",
    )
    assert ep.slug == "e28-tdr-pro-s-1st-year-portfolio-audit"


def test_episode_duration_label_formats_seconds() -> None:
    ep = TDRProEpisode(
        guid="g1",
        title="t",
        description="d",
        url="u",
        published_at=datetime.now(UTC),
        duration_seconds=2893,
    )
    assert ep.duration_label == "48:13"


def test_episode_to_signal_is_neutral_macro() -> None:
    published = datetime(2026, 7, 15, 13, 55, 35, tzinfo=UTC)
    ep = TDRProEpisode(
        guid="g1",
        title="t",
        description="d",
        url="u",
        published_at=published,
    )
    sig = ep.to_signal()
    assert sig.source == "tdr_pro"
    assert sig.symbol == "BTC"
    assert sig.direction == "neutral"
    assert sig.confidence == pytest.approx(0.5)
    assert sig.timestamp == published


def test_to_clipping_has_frontmatter_and_body() -> None:
    ep = TDRProEpisode(
        guid="g1",
        title="TDR Pro’s 1st-Year Portfolio Audit",
        description="Mike opens the books.",
        url="https://share.transistor.fm/s/09b6f51a",
        published_at=datetime(2026, 7, 15, 13, 55, 35, tzinfo=UTC),
        episode="28",
        duration_seconds=2893,
        transcript_url="https://share.transistor.fm/s/09b6f51a/transcript.txt",
        audio_url="https://media.transistor.fm/09b6f51a/babefc46.mp3",
    )
    clipping = ep.to_clipping(transcript="Hello world.")
    assert clipping.startswith("---")
    assert 'type: "clipping"' in clipping
    assert 'domain: "Trading"' in clipping
    assert 'source: "tdr_pro"' in clipping
    assert 'episode: "E28"' in clipping
    assert 'duration: "48:13"' in clipping
    assert "# TDR Pro’s 1st-Year Portfolio Audit" in clipping
    assert "## Transcript" in clipping
    assert "Hello world." in clipping


def test_to_clipping_falls_back_to_show_notes_when_no_transcript() -> None:
    ep = TDRProEpisode(
        guid="g1",
        title="t",
        description="Show notes body.",
        url="u",
        published_at=datetime.now(UTC),
    )
    clipping = ep.to_clipping()
    assert "## Show notes" in clipping
    assert "Show notes body." in clipping
    assert "## Transcript" not in clipping


def test_live_gate_blocks_http_by_default(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("SAPPHIRE_TDR_PRO_LIVE", raising=False)
    source = TDRProSource(inbox_dir=tmp_path, fetcher=lambda url: pytest.fail("network disabled"))
    with pytest.raises(Exception):  # SourceError
        source.poll()


def test_live_gate_allows_http_when_enabled(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SAPPHIRE_TDR_PRO_LIVE", "1")
    calls: list[str] = []

    def fetcher(url: str) -> str:
        calls.append(url)
        if "transcript" in url:
            return "transcript text"
        return fixture("tdr_pro_feed.xml")

    source = TDRProSource(inbox_dir=tmp_path, fetcher=fetcher)
    paths = source.latest_clippings(limit=1)

    assert len(paths) == 1
    assert paths[0].name == "e28-tdr-pro-s-1st-year-portfolio-audit.md"
    assert paths[0].read_text(encoding="utf-8").startswith("---")
    assert any("transcript" in c for c in calls)


def test_write_clippings_respects_dry_run(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("SAPPHIRE_TDR_PRO_LIVE", raising=False)
    source = TDRProSource(inbox_dir=tmp_path)
    ep = TDRProEpisode(
        guid="g1",
        title="t",
        description="d",
        url="u",
        published_at=datetime.now(UTC),
    )
    paths = source.write_clippings([ep], dry_run=True)
    assert len(paths) == 1
    assert not paths[0].exists()


def test_since_filter_excludes_old_episodes() -> None:
    source = TDRProSource()
    since = datetime(2026, 7, 10, tzinfo=UTC)
    episodes = source.parse(fixture("tdr_pro_feed.xml"))
    recent = [ep for ep in episodes if ep.published_at >= since]
    assert len(recent) == 1
    assert recent[0].episode == "28"
