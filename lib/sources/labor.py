"""Labor-market public-source adapter.

Primary docs retrieved 2026-04-28:
https://www.bls.gov/feed/ and https://developer.usajobs.gov/api-reference/

This source intentionally excludes LinkedIn, Indeed, and other scraping-heavy
job boards. It accepts BLS RSS, USAJOBS API responses, and operator-supplied
career sitemap snapshots only.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lib.correlator.sources import SourceSignal

from . import (
    age_seconds,
    build_url,
    cache_dir,
    canonical_symbol,
    clamp,
    http_get_json,
    http_get_text,
    live_enabled,
    parse_iso,
    read_json,
    secret_value,
    utc_now,
    write_json,
)

FetchText = Callable[[str, Mapping[str, str] | None], str]
FetchJson = Callable[[str, Mapping[str, str] | None], Any]
BLS_EMPSIT_RSS_URL = "https://www.bls.gov/feed/news_release/empsit.rss"
USAJOBS_SEARCH_URL = "https://data.usajobs.gov/api/Search"
FORBIDDEN_HOSTS = ("linkedin.", "indeed.")


@dataclass
class LaborSource:
    """Labor pressure signal from official RSS/API and career sitemaps."""

    name: str = "labor"
    keywords: Sequence[str] = ("engineer", "developer", "ai", "security", "trading")
    career_sitemap_urls: Sequence[str] = ()
    cache_path: Path = field(default_factory=lambda: cache_dir("labor") / "latest.json")
    text_fetcher: FetchText | None = None
    json_fetcher: FetchJson | None = None

    def _fetch_text(self, url: str, headers: Mapping[str, str] | None = None) -> str:
        if self.text_fetcher:
            return self.text_fetcher(url, headers)
        return http_get_text(url, headers=headers)

    def _fetch_json(self, url: str, headers: Mapping[str, str] | None = None) -> Any:
        if self.json_fetcher:
            return self.json_fetcher(url, headers)
        return http_get_json(url, headers=headers)

    def _snapshot(self) -> dict[str, Any]:
        if not live_enabled("LABOR"):
            cached = read_json(self.cache_path)
            return cached if isinstance(cached, dict) else {"items": [], "jobs": []}
        now = utc_now()
        items = self._parse_bls_rss(self._fetch_text(BLS_EMPSIT_RSS_URL))
        jobs = self._pull_usajobs()
        for url in self.career_sitemap_urls:
            if any(host in url.lower() for host in FORBIDDEN_HOSTS):
                continue
            jobs.extend(self._parse_sitemap(self._fetch_text(url), source_url=url))
        snapshot = {"retrieved_at": now.isoformat(), "items": items, "jobs": jobs}
        write_json(self.cache_path, snapshot)
        return snapshot

    @staticmethod
    def _parse_bls_rss(text: str) -> list[dict[str, Any]]:
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []
        rows: list[dict[str, Any]] = []
        for item in root.findall(".//item"):
            rows.append(
                {
                    "title": item.findtext("title") or "",
                    "url": item.findtext("link") or "",
                    "published_at": item.findtext("pubDate") or "",
                    "source": "bls_rss",
                }
            )
        return rows

    @staticmethod
    def _parse_sitemap(text: str, *, source_url: str) -> list[dict[str, Any]]:
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []
        rows: list[dict[str, Any]] = []
        for loc in root.findall(".//{*}loc"):
            url = (loc.text or "").strip()
            if not url or any(host in url.lower() for host in FORBIDDEN_HOSTS):
                continue
            if re.search(r"/(job|career|position|opening)", url, re.I):
                rows.append({"url": url, "source": "career_sitemap", "source_url": source_url})
        return rows

    def _pull_usajobs(self) -> list[dict[str, Any]]:
        key = secret_value("USAJOBS_API_KEY")
        email = secret_value("USAJOBS_USER_AGENT") or "ops@sapphirealpha.xyz"
        if not key:
            return []
        jobs: list[dict[str, Any]] = []
        for keyword in self.keywords:
            url = build_url(
                USAJOBS_SEARCH_URL,
                {"Keyword": keyword, "ResultsPerPage": 25, "WhoMayApply": "public"},
            )
            payload = self._fetch_json(
                url,
                {
                    "Authorization-Key": key,
                    "User-Agent": email,
                    "Host": "data.usajobs.gov",
                },
            )
            items = (((payload.get("SearchResult") or {}).get("SearchResultItems")) or [])
            for item in items:
                descriptor = item.get("MatchedObjectDescriptor") if isinstance(item, Mapping) else None
                if isinstance(descriptor, Mapping):
                    jobs.append(
                        {
                            "title": descriptor.get("PositionTitle"),
                            "url": descriptor.get("PositionURI"),
                            "source": "usajobs",
                            "keyword": keyword,
                        }
                    )
        return jobs

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        target = canonical_symbol(symbol)
        snapshot = self._snapshot()
        jobs = [j for j in snapshot.get("jobs") or [] if isinstance(j, Mapping)]
        items = [i for i in snapshot.get("items") or [] if isinstance(i, Mapping)]
        if not jobs and not items:
            return None
        pressure = len(jobs)
        direction = "bull" if pressure >= 10 else "neutral"
        ts = parse_iso(snapshot.get("retrieved_at")) or utc_now()
        return SourceSignal(
            source=self.name,
            symbol=target,
            timeframe=timeframe,
            direction=direction,
            confidence=clamp(0.35 + min(pressure, 50) / 100, default=0.35),
            age_seconds=age_seconds(ts),
            timestamp_iso=ts.isoformat(),
            raw={
                "bls_items": len(items),
                "public_jobs": len(jobs),
                "live_operator_flag": live_enabled("LABOR"),
            },
        )
