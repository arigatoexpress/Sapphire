"""NewsAPI category source.

Primary docs retrieved 2026-04-28:
https://newsapi.org/docs/endpoints/top-headlines
"""

from __future__ import annotations

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
    live_enabled,
    parse_iso,
    read_json,
    secret_value,
    utc_now,
    write_json,
)

FetchJson = Callable[[str, Mapping[str, str] | None], Any]
TOP_HEADLINES_URL = "https://newsapi.org/v2/top-headlines"
DEFAULT_CATEGORIES = ("business", "technology", "science")
POSITIVE = {"approve", "growth", "rally", "record", "surge", "upgrade", "inflow"}
NEGATIVE = {"hack", "lawsuit", "ban", "crash", "probe", "selloff", "outflow", "default"}


@dataclass
class NewsAPISource:
    """NewsAPI category headlines scored into a lightweight sentiment signal."""

    name: str = "newsapi"
    categories: Sequence[str] = DEFAULT_CATEGORIES
    country: str = "us"
    cache_path: Path = field(default_factory=lambda: cache_dir("newsapi") / "latest.json")
    fetcher: FetchJson | None = None

    def _fetch(self, url: str, headers: Mapping[str, str] | None) -> Any:
        if self.fetcher:
            return self.fetcher(url, headers)
        return http_get_json(url, headers=headers)

    def _snapshot(self) -> dict[str, Any]:
        if not live_enabled("NEWSAPI"):
            cached = read_json(self.cache_path)
            return cached if isinstance(cached, dict) else {"articles": []}
        key = secret_value("NEWSAPI_KEY")
        if not key:
            return {"articles": []}
        articles: list[dict[str, Any]] = []
        for category in self.categories:
            url = build_url(
                TOP_HEADLINES_URL,
                {"country": self.country, "category": category, "pageSize": 50},
            )
            payload = self._fetch(url, {"X-Api-Key": key})
            for article in payload.get("articles") or []:
                if isinstance(article, dict):
                    article["category"] = category
                    articles.append(article)
        snapshot = {"retrieved_at": utc_now().isoformat(), "articles": articles}
        write_json(self.cache_path, snapshot)
        return snapshot

    @staticmethod
    def _article_score(text: str) -> float:
        words = {w.strip(".,:;!?$#").lower() for w in text.split()}
        return float(len(words & POSITIVE) - len(words & NEGATIVE))

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        target = canonical_symbol(symbol)
        articles = self._snapshot().get("articles") or []
        matched: list[Mapping[str, Any]] = []
        for article in articles:
            if not isinstance(article, Mapping):
                continue
            text = " ".join(
                str(article.get(key) or "") for key in ("title", "description", "content")
            )
            if target.lower() in text.lower():
                matched.append(article)
        if not matched:
            return None
        score = sum(
            self._article_score(
                " ".join(str(a.get(k) or "") for k in ("title", "description", "content"))
            )
            for a in matched
        )
        newest = max((parse_iso(a.get("publishedAt")) for a in matched), default=None)
        direction = "bull" if score > 0 else "bear" if score < 0 else "neutral"
        timestamp = newest or utc_now()
        return SourceSignal(
            source=self.name,
            symbol=target,
            timeframe=timeframe,
            direction=direction,
            confidence=clamp(0.45 + min(abs(score), 5.0) / 10, default=0.45),
            age_seconds=age_seconds(timestamp),
            timestamp_iso=timestamp.isoformat(),
            raw={
                "matched_articles": len(matched),
                "categories": list(self.categories),
                "live_operator_flag": live_enabled("NEWSAPI"),
            },
        )
