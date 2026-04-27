"""Tests for control-plane RSS news ingestion and source metadata.

The control-plane news fetcher turns reputable RSS feeds into stable
``NewsItem`` records before scoring/digesting them. These tests keep the
network mocked and pin URL normalization, feed parsing, source failure
handling, de-duplication, and the reputable-source registry.
"""

from __future__ import annotations

import contextlib
import importlib
import logging
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CP_ROOT = REPO_ROOT / "services" / "control-plane"


@contextlib.contextmanager
def _control_plane_app_namespace():
    """Temporarily make ``app`` resolve to control-plane's package."""
    saved = {
        name: sys.modules.pop(name, None)
        for name in ("app", "app.models", "app.news", "app.sources")
    }
    sys.path.insert(0, str(CP_ROOT))
    try:
        importlib.invalidate_caches()
        yield
    finally:
        sys.path.remove(str(CP_ROOT))
        for name in ("app", "app.models", "app.news", "app.sources"):
            sys.modules.pop(name, None)
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod


with _control_plane_app_namespace():
    import app.news as news_module  # noqa: E402
    from app.models import NewsItem, NewsSource  # noqa: E402
    from app.news import (  # noqa: E402
        DEFAULT_USER_AGENT,
        NewsFetcher,
        _normalize_url,
        _parse_published,
        _stable_id,
        _strip_html,
    )
    from app.sources import REPUTABLE_NEWS_SOURCES  # noqa: E402


NOW = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def _source(key: str = "test-feed", *, reliability: float = 0.9) -> NewsSource:
    return NewsSource(
        key=key,
        name=f"{key} wire",
        rss_url=f"https://example.test/{key}.xml",
        reliability=reliability,
        category="markets",
    )


def _item(
    item_id: str,
    url: str,
    *,
    source: NewsSource,
    age_minutes: int,
) -> NewsItem:
    return NewsItem(
        id=item_id,
        title=f"Story {item_id}",
        url=url,
        summary="summary",
        published_at=NOW - timedelta(minutes=age_minutes),
        source=source,
    )


class _FakeResponse:
    def __init__(self, text: str, *, error: Exception | None = None) -> None:
        self.text = text
        self._error = error

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error


class _FakeClient:
    def __init__(self, text: str, *, error: Exception | None = None) -> None:
        self.text = text
        self.error = error
        self.urls: list[str] = []

    async def get(self, url: str) -> _FakeResponse:
        self.urls.append(url)
        return _FakeResponse(self.text, error=self.error)


def _rss(*items: str) -> str:
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<rss version='2.0'><channel><title>Test</title>" + "".join(items) + "</channel></rss>"
    )


def _rss_item(
    title: str,
    link: str,
    *,
    summary: str = "",
    pub_date: str = "Mon, 27 Apr 2026 12:34:56 GMT",
) -> str:
    return (
        "<item>"
        f"<title>{title}</title>"
        f"<link>{link}</link>"
        f"<description>{summary}</description>"
        f"<pubDate>{pub_date}</pubDate>"
        "</item>"
    )


def test_strip_html_decodes_entities_and_collapses_whitespace():
    raw = "<p>Alpha&nbsp;&amp;&nbsp;beta</p>\n<br>gamma"

    assert _strip_html(raw) == "Alpha & beta gamma"


def test_normalize_url_canonicalizes_scheme_host_path_only():
    assert _normalize_url("HTTP://www.Example.COM/path/?utm=abc#frag") == "http://example.com/path"
    assert _normalize_url("https://example.com/path/") == "https://example.com/path"


def test_stable_id_ignores_title_changes_and_www_trailing_slash():
    first = _stable_id("source-a", "https://www.Example.com/story/", "Old title")
    second = _stable_id("source-a", "https://example.com/story", "Updated title")

    assert first == second
    assert _stable_id("source-b", "https://example.com/story", "Updated title") != first


def test_parse_published_prefers_published_then_updated():
    published = _parse_published({"published_parsed": (2026, 4, 27, 12, 34, 56, 0, 0, 0)})
    updated = _parse_published({"updated_parsed": (2026, 4, 27, 13, 0, 0, 0, 0, 0)})

    assert published == datetime(2026, 4, 27, 12, 34, 56, tzinfo=UTC)
    assert updated == datetime(2026, 4, 27, 13, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_fetch_source_parses_rss_items_and_skips_incomplete_entries():
    source = _source()
    client = _FakeClient(
        _rss(
            _rss_item(
                "Alpha &amp; beta",
                "https://www.example.com/story/?utm=1",
                summary="<p>Line&nbsp;one</p><p>Line two</p>",
            ),
            _rss_item("", "https://example.com/missing-title"),
            _rss_item("Missing link", ""),
        )
    )

    items = await NewsFetcher(request_timeout_seconds=2.5)._fetch_source(client, source)

    assert client.urls == [source.rss_url]
    assert len(items) == 1
    assert items[0].title == "Alpha & beta"
    assert items[0].summary == "Line one Line two"
    assert items[0].url == "https://www.example.com/story/?utm=1"
    assert items[0].published_at == datetime(2026, 4, 27, 12, 34, 56, tzinfo=UTC)
    assert items[0].source is source
    assert len(items[0].id) == 20


@pytest.mark.asyncio
async def test_fetch_source_limits_each_feed_to_first_forty_entries():
    source = _source()
    rss = _rss(*[_rss_item(f"Story {i}", f"https://example.com/story-{i}") for i in range(45)])

    items = await NewsFetcher(request_timeout_seconds=1)._fetch_source(_FakeClient(rss), source)

    assert len(items) == 40
    assert items[0].title == "Story 0"
    assert items[-1].title == "Story 39"


@pytest.mark.asyncio
async def test_fetch_returns_empty_list_for_empty_source_list():
    assert await NewsFetcher(request_timeout_seconds=1).fetch([]) == []


@pytest.mark.asyncio
async def test_fetch_uses_timeout_redirects_and_user_agent(monkeypatch):
    captured: dict[str, object] = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs) -> None:
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc_info) -> None:
            return None

    async def fake_fetch_source(_self, _client, _source):
        return []

    monkeypatch.setattr(news_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(NewsFetcher, "_fetch_source", fake_fetch_source)

    await NewsFetcher(request_timeout_seconds=7.5).fetch([_source()])

    assert captured["timeout"] == 7.5
    assert captured["follow_redirects"] is True
    assert captured["headers"] == {"User-Agent": DEFAULT_USER_AGENT}


@pytest.mark.asyncio
async def test_fetch_logs_failed_sources_dedupes_and_sorts(monkeypatch, caplog):
    source_a = _source("source-a")
    source_b = _source("source-b")
    source_bad = _source("source-bad")
    older_dupe = _item(
        "older",
        "https://www.example.com/story/?utm=old",
        source=source_a,
        age_minutes=30,
    )
    newer_dupe = _item(
        "newer",
        "https://example.com/story?ref=new",
        source=source_b,
        age_minutes=5,
    )
    distinct = _item(
        "distinct",
        "https://example.com/other",
        source=source_b,
        age_minutes=20,
    )

    async def fake_fetch_source(_self, _client, source):
        if source.key == "source-bad":
            raise RuntimeError("boom")
        return {
            "source-a": [older_dupe],
            "source-b": [distinct, newer_dupe],
        }[source.key]

    monkeypatch.setattr(NewsFetcher, "_fetch_source", fake_fetch_source)

    with caplog.at_level(logging.WARNING):
        output = await NewsFetcher(request_timeout_seconds=1).fetch(
            [source_a, source_bad, source_b]
        )

    assert [item.id for item in output] == ["newer", "distinct"]
    assert "failed source source-bad: boom" in caplog.text


def test_reputable_news_sources_have_unique_keys_and_urls():
    keys = [source.key for source in REPUTABLE_NEWS_SOURCES]
    urls = [source.rss_url for source in REPUTABLE_NEWS_SOURCES]

    assert len(keys) == len(set(keys))
    assert len(urls) == len(set(urls))


def test_reputable_news_sources_have_valid_reliability_and_https_feeds():
    for source in REPUTABLE_NEWS_SOURCES:
        assert 0.0 <= source.reliability <= 1.0
        assert source.rss_url.startswith("https://")


def test_reputable_news_sources_cover_core_market_categories():
    categories = {source.category for source in REPUTABLE_NEWS_SOURCES}

    assert {"equity", "macro", "crypto"} <= categories
