"""Earnings call transcript adapter — free-tier RSS sources only.

Why free-tier-only
------------------

Most of the well-known transcript providers (e.g. The Motley Fool,
Seeking Alpha, FactSet StreetEvents) sit behind paywalls or
ToS-restrictive scraping clauses. We deliberately decline to scrape
them. This adapter ships with two safe input modes:

1. **Operator-supplied IR RSS feeds.** Public companies that publish
   call audio/transcripts on their own investor-relations site usually
   expose an RSS feed (or accept a periodic IR-press-release feed).
   Operators add these to ``~/.sapphire/earnings_rss.yaml``.
2. **Operator-supplied transcript fixtures.** During incident review
   or backtest replay, an operator may drop pre-fetched transcripts
   into ``~/.cache/sapphire/earnings_calls/<ticker>/<date>.json``.

Paid providers (AlphaVantage's transcript add-on, Polygon, Tiingo) are
documented in :data:`PAID_PROVIDER_STUBS` for future wiring; **NOT**
called here.

Operational posture
-------------------

- ``SAPPHIRE_EARNINGS_LIVE=1`` gates all live network calls.
- Cache TTL: 1h; same as SEC EDGAR.
- When live, fetches respect a 5 req/sec ceiling (well under any
  realistic IR-page rate limit).
- Sentiment is keyword-based + sentence-level, not LLM-based — keeps
  this fast, deterministic, and testable.
"""

from __future__ import annotations

import re
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from lib.correlator.sources import SourceSignal

from . import (
    age_seconds,
    cache_dir,
    canonical_symbol,
    clamp,
    http_get_text,
    live_enabled,
    parse_iso,
    read_fresh_json,
    read_json,
    utc_now,
    write_json,
)

FetchText = Callable[[str, Mapping[str, str] | None], str]

DEFAULT_RSS_CONFIG = Path.home() / ".sapphire" / "earnings_rss.yaml"
CACHE_TTL_SECONDS = 3600  # 1h
RATE_LIMIT_REQ_PER_SEC = 5
TRANSCRIPT_FIXTURE_ROOT = Path.home() / ".cache" / "sapphire" / "earnings_calls"

# Paid providers we deliberately do NOT hit. Documented for future wiring.
PAID_PROVIDER_STUBS: tuple[dict[str, str], ...] = (
    {
        "name": "alpha_vantage_earnings_call_transcripts",
        "docs": "https://www.alphavantage.co/documentation/#earnings-call-transcript",
        "status": "not_wired",
    },
    {
        "name": "polygon_earnings_calls",
        "docs": "https://polygon.io/docs",
        "status": "not_wired",
    },
    {
        "name": "tiingo_news_with_transcripts",
        "docs": "https://www.tiingo.com/documentation",
        "status": "not_wired",
    },
)


POSITIVE_TERMS = {
    "beat",
    "beats",
    "record",
    "exceed",
    "exceeded",
    "raised",
    "guidance",
    "growth",
    "tailwind",
    "expansion",
    "strong",
    "outperform",
    "buyback",
    "accelerating",
    "ahead",
}
NEGATIVE_TERMS = {
    "miss",
    "missed",
    "shortfall",
    "lowered",
    "guide",  # raised + lowered both common; stays neutral by default
    "headwind",
    "softness",
    "weak",
    "decline",
    "delay",
    "investigation",
    "subpoena",
    "lawsuit",
    "restatement",
    "downgrade",
    "layoff",
    "layoffs",
    "warning",
}


# ---------------------------------------------------------------------------
# Rate limiter (separate from SEC's; earnings calls have different ceilings)
# ---------------------------------------------------------------------------


class RateLimiter:
    """Thread-safe leaky-bucket limiter for IR-feed pulls."""

    def __init__(self, rate: int = RATE_LIMIT_REQ_PER_SEC) -> None:
        self._rate = max(1, int(rate))
        self._min_interval = 1.0 / self._rate
        self._lock = threading.Lock()
        self._last = 0.0

    @property
    def rate(self) -> int:
        return self._rate

    def acquire(
        self,
        *,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        with self._lock:
            wait = self._min_interval - (now() - self._last)
            if wait > 0:
                sleep(wait)
            self._last = now()


# ---------------------------------------------------------------------------
# Config + transcript file conventions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IRSubscription:
    """One operator-curated IR feed."""

    ticker: str
    rss_url: str = ""
    transcript_dir: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "rss_url": self.rss_url,
            "transcript_dir": str(self.transcript_dir) if self.transcript_dir else "",
        }


def load_ir_config(path: Path = DEFAULT_RSS_CONFIG) -> list[IRSubscription]:
    """Parse the operator's IR-feed config (tiny YAML / JSON subset).

    Recognized shape::

        feeds:
          - ticker: AAPL
            rss_url: https://investor.apple.com/rss-news
          - ticker: NVDA
            rss_url: https://investor.nvidia.com/rss
    """
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    parsed = _parse_minimal_yaml(text)
    feeds = parsed.get("feeds")
    if not isinstance(feeds, list):
        return []
    out: list[IRSubscription] = []
    for entry in feeds:
        if not isinstance(entry, Mapping):
            continue
        ticker = str(entry.get("ticker") or "").upper().strip()
        if not ticker:
            continue
        rss_url = str(entry.get("rss_url") or "").strip()
        td_raw = entry.get("transcript_dir")
        transcript_dir = Path(str(td_raw)).expanduser() if td_raw else None
        out.append(IRSubscription(ticker=ticker, rss_url=rss_url, transcript_dir=transcript_dir))
    return out


def _parse_minimal_yaml(text: str) -> dict[str, Any]:
    """Minimal YAML parser supporting:
    - top-level ``key: value`` scalars
    - top-level ``key:`` followed by indented ``- key: value`` mappings
    """
    result: dict[str, Any] = {}
    current_list_key: str | None = None
    current_item: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.lstrip()
        # Start of a new list item under the current_list_key.
        if stripped.startswith("- ") and current_list_key is not None:
            if current_item is not None:
                result.setdefault(current_list_key, []).append(current_item)
            current_item = {}
            inner = stripped[2:].strip()
            if ":" in inner:
                k, _, v = inner.partition(":")
                current_item[k.strip()] = v.strip().strip("\"'")
            else:
                current_item["_raw"] = inner.strip("\"'")
            continue
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip("\"'")
            indent = len(line) - len(stripped)
            if current_item is not None and indent >= 4:
                # property of the current list item
                current_item[key] = value
                continue
            # New top-level key — flush current list item if any.
            if current_item is not None and current_list_key is not None:
                result.setdefault(current_list_key, []).append(current_item)
                current_item = None
            if not value:
                current_list_key = key
                continue
            result[key] = value
            current_list_key = None
    if current_item is not None and current_list_key is not None:
        result.setdefault(current_list_key, []).append(current_item)
    return result


# ---------------------------------------------------------------------------
# Transcript records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TranscriptSentiment:
    """Sentiment summary for one transcript (or transcript-equivalent feed item)."""

    ticker: str
    direction: str
    confidence: float
    title: str
    published_at: str
    source_url: str
    source_kind: str  # "rss" | "fixture"
    positive_hits: int
    negative_hits: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


@dataclass
class EarningsCallSource:
    """Earnings call transcript adapter."""

    name: str = "earnings_calls"
    config_path: Path = DEFAULT_RSS_CONFIG
    cache_path: Path = field(default_factory=lambda: cache_dir("earnings_calls") / "latest.json")
    fixture_root: Path = field(default_factory=lambda: TRANSCRIPT_FIXTURE_ROOT)
    fetcher: FetchText | None = None
    rate_limiter: RateLimiter = field(default_factory=RateLimiter)

    # --- RSS fetcher ---

    def _fetch(self, url: str, headers: Mapping[str, str] | None = None) -> str:
        self.rate_limiter.acquire()
        if self.fetcher:
            return self.fetcher(url, headers)
        return http_get_text(url, headers=headers)

    @staticmethod
    def _parse_rss(text: str) -> list[dict[str, Any]]:
        if not text or not text.strip():
            return []
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []
        rows: list[dict[str, Any]] = []
        for item in root.findall(".//item"):
            rows.append(
                {
                    "title": (item.findtext("title") or "").strip(),
                    "url": (item.findtext("link") or "").strip(),
                    "published_at": (item.findtext("pubDate") or "").strip(),
                    "description": (item.findtext("description") or "").strip(),
                }
            )
        return rows

    @staticmethod
    def _is_earnings_related(title: str, description: str = "") -> bool:
        # Title-only filter — descriptions often namedrop "earnings" without
        # the item itself being an earnings event (e.g. an explicit
        # "Not earnings related." disclaimer).
        text = title.lower()
        return any(
            kw in text
            for kw in (
                "earnings",
                "quarterly results",
                "q1 ",
                "q2 ",
                "q3 ",
                "q4 ",
                "fiscal year",
                "annual results",
                "investor day",
            )
        )

    # --- transcript fixture loader ---

    def _fixture_files(self, ticker: str, *, base: Path | None = None) -> list[Path]:
        directory = base or (self.fixture_root / ticker.upper())
        if not directory.exists() or not directory.is_dir():
            return []
        files = sorted(
            p for p in directory.iterdir() if p.is_file() and p.suffix in {".json", ".txt"}
        )
        return files

    @staticmethod
    def _load_fixture(path: Path) -> dict[str, Any]:
        if path.suffix == ".json":
            data = read_json(path)
            return data if isinstance(data, dict) else {}
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return {}
        # treat .txt as a body-only transcript
        return {
            "title": path.stem,
            "body": text,
            "published_at": "",
            "url": str(path),
        }

    # --- Snapshot orchestration ---

    def _snapshot(self, *, subscriptions: Sequence[IRSubscription] | None = None) -> dict[str, Any]:
        cached = read_fresh_json(self.cache_path, ttl_seconds=CACHE_TTL_SECONDS)
        if isinstance(cached, dict) and cached.get("entries"):
            return cached
        subs = list(subscriptions or load_ir_config(self.config_path))
        if not live_enabled("EARNINGS"):
            stale = read_json(self.cache_path)
            if isinstance(stale, dict):
                return stale
            return {
                "retrieved_at": utc_now().isoformat(),
                "entries": {},
                "subs": [s.to_dict() for s in subs],
            }
        entries: dict[str, list[dict[str, Any]]] = {}
        for sub in subs:
            ticker = sub.ticker.upper()
            ticker_entries: list[dict[str, Any]] = []
            # Fixtures first (cheap).
            for fpath in self._fixture_files(ticker, base=sub.transcript_dir):
                payload = self._load_fixture(fpath)
                payload["source_kind"] = "fixture"
                payload["ticker"] = ticker
                ticker_entries.append(payload)
            # Then RSS.
            if sub.rss_url:
                try:
                    text = self._fetch(sub.rss_url, {"Accept": "application/rss+xml"})
                except Exception:  # noqa: BLE001 — never fail closed
                    text = ""
                for row in self._parse_rss(text):
                    if not self._is_earnings_related(
                        row.get("title") or "", row.get("description") or ""
                    ):
                        continue
                    row["source_kind"] = "rss"
                    row["source_url"] = sub.rss_url
                    row["ticker"] = ticker
                    ticker_entries.append(row)
            entries[ticker] = ticker_entries
        payload = {
            "retrieved_at": utc_now().isoformat(),
            "entries": entries,
            "subs": [s.to_dict() for s in subs],
            "rate_limit_req_per_sec": self.rate_limiter.rate,
        }
        write_json(self.cache_path, payload)
        return payload

    # --- Sentiment scoring ---

    @staticmethod
    def score_text(text: str) -> tuple[int, int]:
        """Return (positive_hits, negative_hits) for ``text``."""
        if not text:
            return 0, 0
        words = re.findall(r"[A-Za-z]+", text.lower())
        word_set = set(words)
        # count by sentence-level positive/negative occurrence — bag of words is fine
        pos = sum(1 for w in words if w in POSITIVE_TERMS)
        neg = sum(1 for w in words if w in NEGATIVE_TERMS)
        # also count distinct hits to avoid one sentence dominating
        pos += len(word_set & POSITIVE_TERMS) // 2
        neg += len(word_set & NEGATIVE_TERMS) // 2
        return pos, neg

    @classmethod
    def classify_entry(cls, ticker: str, entry: Mapping[str, Any]) -> TranscriptSentiment:
        title = str(entry.get("title") or "")
        description = str(entry.get("description") or "")
        body = str(entry.get("body") or "")
        published_at = str(entry.get("published_at") or "")
        source_url = str(entry.get("url") or entry.get("source_url") or "")
        source_kind = str(entry.get("source_kind") or "rss")
        text = " ".join(filter(None, [title, description, body]))
        pos, neg = cls.score_text(text)
        net = pos - neg
        if net > 0:
            direction = "bull"
        elif net < 0:
            direction = "bear"
        else:
            direction = "neutral"
        magnitude = min(abs(net), 6.0) / 12.0  # 0..0.5
        confidence = clamp(0.30 + magnitude, default=0.30)
        return TranscriptSentiment(
            ticker=ticker.upper(),
            direction=direction,
            confidence=confidence,
            title=title,
            published_at=published_at,
            source_url=source_url,
            source_kind=source_kind,
            positive_hits=pos,
            negative_hits=neg,
        )

    # --- Public reads ---

    def list_sentiments(
        self, *, subscriptions: Sequence[IRSubscription] | None = None
    ) -> list[TranscriptSentiment]:
        snapshot = self._snapshot(subscriptions=subscriptions)
        out: list[TranscriptSentiment] = []
        for ticker, entries in (snapshot.get("entries") or {}).items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, Mapping):
                    out.append(self.classify_entry(str(ticker), entry))
        return out

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        target = canonical_symbol(symbol)
        sentiments = self.list_sentiments()
        candidates = [s for s in sentiments if s.ticker == target]
        if not candidates:
            return None
        candidates.sort(
            key=lambda s: parse_iso(s.published_at) or utc_now(),
            reverse=True,
        )
        top = candidates[0]
        ts = parse_iso(top.published_at) or utc_now()
        return SourceSignal(
            source=self.name,
            symbol=target,
            timeframe=timeframe,
            direction=top.direction,
            confidence=top.confidence,
            age_seconds=age_seconds(ts),
            timestamp_iso=ts.isoformat(),
            raw={
                "title": top.title,
                "source_url": top.source_url,
                "source_kind": top.source_kind,
                "positive_hits": top.positive_hits,
                "negative_hits": top.negative_hits,
                "live_operator_flag": live_enabled("EARNINGS"),
                "rate_limit_req_per_sec": self.rate_limiter.rate,
            },
        )


# ---------------------------------------------------------------------------
# Aggregations
# ---------------------------------------------------------------------------


def summarize_directions(items: Iterable[TranscriptSentiment]) -> dict[str, int]:
    out = {"bull": 0, "bear": 0, "neutral": 0}
    for it in items:
        d = (it.direction or "neutral").lower()
        out[d if d in out else "neutral"] += 1
    return out


__all__ = [
    "CACHE_TTL_SECONDS",
    "DEFAULT_RSS_CONFIG",
    "EarningsCallSource",
    "IRSubscription",
    "NEGATIVE_TERMS",
    "PAID_PROVIDER_STUBS",
    "POSITIVE_TERMS",
    "RATE_LIMIT_REQ_PER_SEC",
    "RateLimiter",
    "TRANSCRIPT_FIXTURE_ROOT",
    "TranscriptSentiment",
    "load_ir_config",
    "summarize_directions",
]
