from __future__ import annotations

import asyncio
import calendar
import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from html import unescape
from typing import List, Sequence
from urllib.parse import urlparse

import feedparser
import httpx

from app.models import NewsItem, NewsSource


logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; SapphireAlphaBot/1.0; +https://github.com/arigatoexpress/Sapphire)"


def _strip_html(raw: str) -> str:
    stripped = re.sub(r"<[^>]+>", " ", unescape(raw or ""))
    return re.sub(r"\s+", " ", stripped).strip()


def _parse_published(entry: dict) -> datetime:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        # Feed timestamps are UTC; using mktime introduces local timezone skew.
        return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc)
    return datetime.now(tz=timezone.utc)


def _stable_id(source_key: str, url: str, title: str) -> str:
    # Stable per-article id. Do NOT include title because many feeds update titles
    # in-place (which would cause duplicate sends across digests).
    canonical = _normalize_url(url) or (url or "").strip()
    digest = hashlib.sha256(f"{source_key}|{canonical}".encode("utf-8")).hexdigest()
    return digest[:20]


def _normalize_url(url: str) -> str:
    parsed = urlparse(url)
    scheme = (parsed.scheme or "https").lower()
    netloc = (parsed.netloc or "").lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path or ""
    return f"{scheme}://{netloc}{path}".rstrip("/")


class NewsFetcher:
    def __init__(self, request_timeout_seconds: float) -> None:
        self._timeout = request_timeout_seconds

    async def _fetch_source(self, client: httpx.AsyncClient, source: NewsSource) -> List[NewsItem]:
        response = await client.get(source.rss_url)
        response.raise_for_status()

        parsed = feedparser.parse(response.text)
        items: List[NewsItem] = []
        for entry in parsed.entries[:40]:
            title = (entry.get("title") or "").strip()
            url = (entry.get("link") or "").strip()
            summary = _strip_html(entry.get("summary") or entry.get("description") or "")
            if not title or not url:
                continue

            published_at = _parse_published(entry)
            items.append(
                NewsItem(
                    id=_stable_id(source.key, url, title),
                    title=title,
                    url=url,
                    summary=summary,
                    published_at=published_at,
                    source=source,
                )
            )
        return items

    async def fetch(self, sources: Sequence[NewsSource]) -> List[NewsItem]:
        if not sources:
            return []

        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        ) as client:
            tasks = [self._fetch_source(client, source) for source in sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        merged: List[NewsItem] = []
        for source, result in zip(sources, results):
            if isinstance(result, Exception):
                logger.warning("failed source %s: %s", source.key, result)
                continue
            merged.extend(result)

        deduped: dict[str, NewsItem] = {}
        for item in merged:
            key = _normalize_url(item.url) or item.id
            if key not in deduped or item.published_at > deduped[key].published_at:
                deduped[key] = item

        output = sorted(deduped.values(), key=lambda x: x.published_at, reverse=True)
        return output
