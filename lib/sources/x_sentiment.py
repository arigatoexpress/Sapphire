"""X API v2 sentiment source.

Primary docs retrieved 2026-04-28:
https://developer.x.com/en/docs/x-api/search-overview
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
SEARCH_URL = "https://api.x.com/2/tweets/search/recent"
POSITIVE = {"bull", "breakout", "accumulate", "bid", "inflow", "adoption", "upgrade"}
NEGATIVE = {"bear", "selloff", "hack", "outflow", "liquidation", "downgrade", "risk"}


@dataclass
class XSentimentSource:
    """Handle-based X sentiment; empty config returns no signal."""

    name: str = "x_sentiment"
    handles: Sequence[str] = ()
    cache_path: Path = field(default_factory=lambda: cache_dir("x_sentiment") / "latest.json")
    fetcher: FetchJson | None = None

    def _fetch(self, url: str, headers: Mapping[str, str] | None) -> Any:
        if self.fetcher:
            return self.fetcher(url, headers)
        return http_get_json(url, headers=headers)

    def _snapshot(self, symbol: str) -> dict[str, Any]:
        if not self.handles:
            return {"tweets": []}
        if not live_enabled("X_SENTIMENT"):
            cached = read_json(self.cache_path)
            return cached if isinstance(cached, dict) else {"tweets": []}
        token = secret_value("X_BEARER_TOKEN")
        if not token:
            return {"tweets": []}
        handle_query = " OR ".join(f"from:{handle.lstrip('@')}" for handle in self.handles)
        query = f"({handle_query}) {symbol} -is:retweet"
        url = build_url(
            SEARCH_URL,
            {
                "query": query,
                "max_results": 50,
                "tweet.fields": "created_at,public_metrics,lang",
            },
        )
        payload = self._fetch(url, {"Authorization": f"Bearer {token}"})
        snapshot = {"retrieved_at": utc_now().isoformat(), "tweets": payload.get("data", [])}
        write_json(self.cache_path, snapshot)
        return snapshot

    @staticmethod
    def _score(text: str) -> float:
        words = {w.strip(".,:;!?$#").lower() for w in text.split()}
        return float(len(words & POSITIVE) - len(words & NEGATIVE))

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        target = canonical_symbol(symbol)
        tweets = self._snapshot(target).get("tweets") or []
        if not isinstance(tweets, list) or not tweets:
            return None
        score = 0.0
        newest = None
        for tweet in tweets:
            if not isinstance(tweet, Mapping):
                continue
            score += self._score(str(tweet.get("text") or ""))
            ts = parse_iso(tweet.get("created_at"))
            if ts and (newest is None or ts > newest):
                newest = ts
        direction = "bull" if score > 0 else "bear" if score < 0 else "neutral"
        confidence = clamp(0.45 + min(abs(score), 5.0) / 10, default=0.45)
        timestamp = newest or utc_now()
        return SourceSignal(
            source=self.name,
            symbol=target,
            timeframe=timeframe,
            direction=direction,
            confidence=confidence,
            age_seconds=age_seconds(timestamp),
            timestamp_iso=timestamp.isoformat(),
            raw={
                "tweet_count": len(tweets),
                "handles": [h.lstrip("@") for h in self.handles],
                "live_operator_flag": live_enabled("X_SENTIMENT"),
            },
        )
