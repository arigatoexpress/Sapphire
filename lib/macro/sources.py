"""Official regulatory and macro source fetchers.

The fetchers in this module are intentionally small and boring:

* parsing is pure and fixture-friendly;
* live HTTP is injected behind a single callable;
* official-source URLs are carried on every event;
* per-source counters and raw response caches live under
  ``~/.cache/sapphire/macro/<source>/``.

Only stdlib plus ``feedparser`` is used when available. HTML pages are parsed with
``html.parser`` and robots checks use ``urllib.robotparser``.
"""

from __future__ import annotations

import calendar as _calendar
import hashlib
import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from datetime import time as dt_time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from lib.macro import feedparser_compat as feedparser

MAX_PULLS_PER_HOUR_PER_SOURCE = 4
MAX_EVENTS_PER_PULL = 100
MAX_FORWARD_CALENDAR_DAYS = 90
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "sapphire" / "macro"
DEFAULT_USER_AGENT = (
    "SapphireMacroIntel/0.1 "
    "(+https://github.com/arigatoexpress/Sapphire; contact=ops@sapphirealpha.xyz)"
)

FED_PRESS_RSS_URL = "https://www.federalreserve.gov/feeds/press_all.xml"
FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FOMC_SITEMAP_URL = "https://www.federalreserve.gov/sitemap.xml"
CFTC_PRESS_RSS_URL = "https://www.cftc.gov/PressRoom/PressReleases.rss"
SEC_CURRENT_ATOM_URL = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcurrent&type=&company=&dateb=&owner=include&count=40&output=atom"
)
TREASURY_AUCTIONS_URL = "https://www.treasurydirect.gov/auctions/auctions-query/"
BLS_EMPSIT_RSS_URL = "https://www.bls.gov/feed/news_release/empsit.rss"
ECB_PRESS_RSS_URL = "https://www.ecb.europa.eu/rss/press.html"
BIS_PRESS_RSS_URL = "https://www.bis.org/list/press_releases/index.rss"

HttpFetcher = Callable[[str, Mapping[str, str], float], str]


class SourceError(RuntimeError):
    """Source pull failed in a recoverable way."""


@dataclass(frozen=True)
class MacroEvent:
    """A normalized official macro/regulatory event."""

    id: str
    source: str
    title: str
    summary: str
    url: str
    published_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "published_at": self.published_at.astimezone(UTC).isoformat(),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> MacroEvent:
        published = payload.get("published_at")
        if isinstance(published, datetime):
            dt = published
        else:
            dt = _parse_datetime(str(published or "")) or datetime.now(UTC)
        return cls(
            id=str(payload.get("id") or ""),
            source=str(payload.get("source") or ""),
            title=str(payload.get("title") or ""),
            summary=str(payload.get("summary") or ""),
            url=str(payload.get("url") or ""),
            published_at=dt,
            metadata=dict(payload.get("metadata") or {}),
        )


def user_agent() -> str:
    """Return the robots/SEC-friendly User-Agent for official HTTP pulls."""

    return os.environ.get("SAPPHIRE_MACRO_USER_AGENT", DEFAULT_USER_AGENT).strip() or (
        DEFAULT_USER_AGENT
    )


def cache_base_dir() -> Path:
    raw = os.environ.get("SAPPHIRE_MACRO_CACHE_DIR")
    return Path(raw).expanduser() if raw else DEFAULT_CACHE_DIR


def canonical_event_id(source: str, title: str, url: str, published_at: datetime) -> str:
    material = "|".join(
        [
            source.strip().lower(),
            re.sub(r"\s+", " ", title.strip().lower()),
            url.strip(),
            published_at.astimezone(UTC).isoformat(),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _strip_html(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _parse_datetime(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    for candidate in (text, text.replace(" GMT", "+00:00")):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            pass
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%B %d, %Y",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            continue
    return None


def _entry_datetime(entry: Any) -> datetime:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = getattr(entry, key, None)
        if parsed:
            return datetime.fromtimestamp(_calendar.timegm(parsed), tz=UTC)
    for key in ("published", "updated", "created"):
        parsed = _parse_datetime(str(getattr(entry, key, "") or ""))
        if parsed:
            return parsed
    return datetime.now(UTC).replace(microsecond=0)


def _within_since(event_time: datetime, since: datetime | None) -> bool:
    if since is None:
        return True
    return event_time.astimezone(UTC) >= since.astimezone(UTC)


def _event(
    *,
    source: str,
    title: str,
    summary: str,
    url: str,
    published_at: datetime,
    metadata: Mapping[str, Any],
) -> MacroEvent:
    clean_title = _strip_html(title)
    clean_summary = _strip_html(summary)
    clean_url = str(url or metadata.get("source_url") or "")
    return MacroEvent(
        id=canonical_event_id(source, clean_title, clean_url, published_at),
        source=source,
        title=clean_title,
        summary=clean_summary,
        url=clean_url,
        published_at=published_at.astimezone(UTC),
        metadata=dict(metadata),
    )


def parse_feed_events(
    text: str,
    *,
    source: str,
    label: str,
    feed_url: str,
    since: datetime | None = None,
    limit: int = MAX_EVENTS_PER_PULL,
) -> list[MacroEvent]:
    """Parse RSS or Atom text into normalized events."""

    parsed = feedparser.parse(text)
    events: list[MacroEvent] = []
    for entry in parsed.entries[: max(limit, 0)]:
        published_at = _entry_datetime(entry)
        if not _within_since(published_at, since):
            continue
        title = str(getattr(entry, "title", "") or "Untitled official update")
        summary = str(
            getattr(entry, "summary", "")
            or getattr(entry, "description", "")
            or getattr(entry, "subtitle", "")
            or ""
        )
        link = str(getattr(entry, "link", "") or feed_url)
        events.append(
            _event(
                source=source,
                title=title,
                summary=summary,
                url=link,
                published_at=published_at,
                metadata={
                    "source_name": label,
                    "source_url": link,
                    "feed_url": feed_url,
                    "official_source": True,
                    "parser": "feedparser",
                    "entry_id": str(getattr(entry, "id", "") or getattr(entry, "guid", "") or ""),
                },
            )
        )
    return events


class _TextAndLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.text_parts: list[str] = []
        self.links: list[tuple[str, str]] = []
        self._href_stack: list[str | None] = []
        self._active_link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            href = dict(attrs).get("href")
            self._href_stack.append(href)
            self._active_link_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href_stack:
            href = self._href_stack.pop()
            label = " ".join(self._active_link_text).strip()
            if href:
                self.links.append((href, label))
            self._active_link_text = []

    def handle_data(self, data: str) -> None:
        clean = re.sub(r"\s+", " ", data).strip()
        if not clean:
            return
        self.text_parts.append(clean)
        if self._href_stack:
            self._active_link_text.append(clean)

    @property
    def text(self) -> str:
        return " ".join(self.text_parts)


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower = tag.lower()
        if lower == "tr":
            self._row = []
        elif lower in {"td", "th"} and self._row is not None:
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        lower = tag.lower()
        if lower in {"td", "th"} and self._row is not None and self._cell_parts is not None:
            self._row.append(_strip_html(" ".join(self._cell_parts)))
            self._cell_parts = None
        elif lower == "tr" and self._row is not None:
            if any(cell.strip() for cell in self._row):
                self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)


MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
MONTH_INDEX = {month: idx for idx, month in enumerate(MONTHS, start=1)}
MONTH_PATTERN = "|".join(MONTHS)
FOMC_DATE_RE = re.compile(
    rf"\b({MONTH_PATTERN})\s+(\d{{1,2}})(?:\s*[-–]\s*(\d{{1,2}}))?(?:,\s*(20\d{{2}}))?"
)
YEAR_RE = re.compile(r"\b(20\d{2})\b")


def _as_utc_date_time(day: date, *, hour: int = 19, minute: int = 0) -> datetime:
    return datetime.combine(day, dt_time(hour=hour, minute=minute), tzinfo=UTC)


def _date_from_parts(month: str, day: int, year: int) -> date | None:
    try:
        return date(year, MONTH_INDEX[month], day)
    except (KeyError, ValueError):
        return None


def _best_fomc_url(page_url: str, links: Sequence[tuple[str, str]]) -> str:
    for href, label in links:
        material = f"{href} {label}".lower()
        if "fomc" in material or "monetarypolicy" in material:
            return urllib.parse.urljoin(page_url, href)
    return page_url


def parse_fomc_calendar_html(
    text: str,
    *,
    page_url: str = FOMC_CALENDAR_URL,
    since: datetime | None = None,
    now: datetime | None = None,
    limit: int = MAX_EVENTS_PER_PULL,
) -> list[MacroEvent]:
    """Parse the Federal Reserve FOMC calendar page."""

    parser = _TextAndLinkParser()
    parser.feed(text)
    body = parser.text
    default_year = (now or datetime.now(UTC)).year
    url = _best_fomc_url(page_url, parser.links)
    markers: list[tuple[int, str, re.Match[str]]] = []
    for match in YEAR_RE.finditer(body):
        markers.append((match.start(), "year", match))
    for match in FOMC_DATE_RE.finditer(body):
        markers.append((match.start(), "date", match))
    markers.sort(key=lambda item: item[0])

    current_year = default_year
    seen: set[tuple[date, date]] = set()
    events: list[MacroEvent] = []
    for _, kind, match in markers:
        if kind == "year":
            current_year = int(match.group(1))
            continue
        month = match.group(1)
        start_day = int(match.group(2))
        end_day = int(match.group(3) or start_day)
        year = int(match.group(4) or current_year)
        start_date = _date_from_parts(month, start_day, year)
        end_date = _date_from_parts(month, end_day, year)
        if start_date is None or end_date is None:
            continue
        key = (start_date, end_date)
        if key in seen:
            continue
        seen.add(key)
        when = _as_utc_date_time(end_date)
        if not _within_since(when, since):
            continue
        title = f"FOMC meeting: {month} {start_day}"
        if end_day != start_day:
            title += f"-{end_day}"
        title += f", {year}"
        events.append(
            _event(
                source="fed_fomc",
                title=title,
                summary="Scheduled Federal Open Market Committee meeting.",
                url=url,
                published_at=when,
                metadata={
                    "source_name": "Federal Reserve FOMC calendar",
                    "source_url": page_url,
                    "official_source": True,
                    "parser": "html.parser",
                    "event_kind": "scheduled_meeting",
                    "meeting_start_date": start_date.isoformat(),
                    "meeting_end_date": end_date.isoformat(),
                },
            )
        )
        if len(events) >= limit:
            break
    return events


def _normalize_header(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", header.strip().lower()).strip("_")


def _parse_date_any(value: str) -> date | None:
    text = _strip_html(value)
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    match = re.search(rf"\b({MONTH_PATTERN})\s+(\d{{1,2}}),\s*(20\d{{2}})\b", text)
    if match:
        return _date_from_parts(match.group(1), int(match.group(2)), int(match.group(3)))
    return None


def _row_value(row_map: Mapping[str, str], *names: str) -> str:
    for name in names:
        key = _normalize_header(name)
        if key in row_map and row_map[key]:
            return row_map[key]
    return ""


def parse_treasury_auctions_html(
    text: str,
    *,
    page_url: str = TREASURY_AUCTIONS_URL,
    since: datetime | None = None,
    limit: int = MAX_EVENTS_PER_PULL,
) -> list[MacroEvent]:
    """Parse TreasuryDirect auction rows into scheduled auction events."""

    parser = _TableParser()
    parser.feed(text)
    if not parser.rows:
        return []
    headers = [_normalize_header(cell) for cell in parser.rows[0]]
    events: list[MacroEvent] = []
    for row in parser.rows[1:]:
        if len(row) < 2:
            continue
        row_map = {headers[idx]: cell for idx, cell in enumerate(row[: len(headers)])}
        auction_date_raw = _row_value(row_map, "auction date", "auction_date")
        auction_date = _parse_date_any(auction_date_raw)
        if auction_date is None:
            continue
        when = _as_utc_date_time(auction_date, hour=17)
        if not _within_since(when, since):
            continue
        security = (
            _row_value(
                row_map,
                "security type",
                "security term",
                "security",
                "type",
            )
            or "Treasury security"
        )
        cusip = _row_value(row_map, "cusip")
        issue_date = _row_value(row_map, "issue date")
        maturity_date = _row_value(row_map, "maturity date")
        title = f"Treasury auction: {security}"
        if cusip:
            title = f"{title} ({cusip})"
        events.append(
            _event(
                source="treasury_auctions",
                title=title,
                summary=f"Scheduled Treasury auction for {security}.",
                url=page_url,
                published_at=when,
                metadata={
                    "source_name": "TreasuryDirect auction calendar",
                    "source_url": page_url,
                    "official_source": True,
                    "parser": "html.parser",
                    "event_kind": "scheduled_auction",
                    "auction_date": auction_date.isoformat(),
                    "security_type": security,
                    "cusip": cusip,
                    "issue_date": issue_date,
                    "maturity_date": maturity_date,
                },
            )
        )
        if len(events) >= limit:
            break
    return events


def _default_http_fetcher(url: str, headers: Mapping[str, str], timeout: float) -> str:
    req = urllib.request.Request(url, headers=dict(headers))
    with urllib.request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - official URLs.
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


class BaseMacroSource:
    """Base class with cache, robots and per-hour pull caps."""

    name = "base"
    label = "Official macro source"
    url = ""
    accept = "application/xml, text/xml, application/atom+xml, text/html, */*"
    respect_robots = False

    def __init__(
        self,
        *,
        cache_dir: str | Path | None = None,
        fetcher: HttpFetcher | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        user_agent_value: str | None = None,
    ) -> None:
        self.cache_dir = Path(cache_dir).expanduser() if cache_dir else cache_base_dir()
        self.fetcher = fetcher or _default_http_fetcher
        self.timeout_seconds = timeout_seconds
        self.user_agent_value = user_agent_value or user_agent()

    async def pull(self, since: datetime) -> list[MacroEvent]:
        text = self._fetch_with_cache(self.url)
        return self.parse(text, since=since)[:MAX_EVENTS_PER_PULL]

    def parse(self, text: str, *, since: datetime | None = None) -> list[MacroEvent]:
        raise NotImplementedError

    @property
    def source_cache_dir(self) -> Path:
        return self.cache_dir / self.name

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self.user_agent_value, "Accept": self.accept}

    def _counter_path(self) -> Path:
        return self.source_cache_dir / "counters.json"

    def _raw_cache_path(self, url: str) -> Path:
        stem = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return self.source_cache_dir / f"{stem}.raw"

    def _meta_cache_path(self, url: str) -> Path:
        stem = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return self.source_cache_dir / f"{stem}.json"

    def _load_counters(self) -> dict[str, Any]:
        try:
            return json.loads(self._counter_path().read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"pulls": [], "lifetime": 0}

    def _save_counters(self, counters: Mapping[str, Any]) -> None:
        self.source_cache_dir.mkdir(parents=True, exist_ok=True)
        self._counter_path().write_text(
            json.dumps(dict(counters), indent=2, sort_keys=True), encoding="utf-8"
        )

    def _allowed_by_rate_limit(self) -> tuple[bool, dict[str, Any]]:
        now = time.time()
        counters = self._load_counters()
        pulls = [float(ts) for ts in counters.get("pulls", []) if float(ts) >= now - 3600]
        counters["pulls"] = pulls
        counters["lifetime"] = int(counters.get("lifetime", 0) or 0)
        allowed = len(pulls) < MAX_PULLS_PER_HOUR_PER_SOURCE
        return allowed, counters

    def _record_pull(self, counters: dict[str, Any]) -> None:
        counters.setdefault("pulls", []).append(time.time())
        counters["lifetime"] = int(counters.get("lifetime", 0) or 0) + 1
        self._save_counters(counters)

    def _robots_allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parsed = urllib.parse.urlparse(url)
        robots_url = urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc, "/robots.txt", "", "", "")
        )
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        try:
            robots_text = self.fetcher(robots_url, self._headers(), self.timeout_seconds)
            rp.parse(robots_text.splitlines())
        except Exception as exc:  # noqa: BLE001 - fail closed for HTML scrapes.
            raise SourceError(f"robots.txt check failed for {url}: {exc}") from exc
        return rp.can_fetch(self.user_agent_value, url)

    def _fetch_with_cache(self, url: str) -> str:
        allowed, counters = self._allowed_by_rate_limit()
        raw_path = self._raw_cache_path(url)
        if not allowed:
            if raw_path.exists():
                return raw_path.read_text(encoding="utf-8")
            raise SourceError(f"{self.name} rate limit exceeded and no cache is available")
        if not self._robots_allowed(url):
            raise SourceError(f"robots.txt disallows fetching {url}")
        text = self.fetcher(url, self._headers(), self.timeout_seconds)
        self.source_cache_dir.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(text, encoding="utf-8")
        self._meta_cache_path(url).write_text(
            json.dumps(
                {
                    "url": url,
                    "fetched_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
                    "user_agent": self.user_agent_value,
                    "source": self.name,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        self._record_pull(counters)
        return text

    def cached_payloads(self) -> list[Path]:
        if not self.source_cache_dir.exists():
            return []
        return sorted(self.source_cache_dir.glob("*.raw"))


class FeedMacroSource(BaseMacroSource):
    def parse(self, text: str, *, since: datetime | None = None) -> list[MacroEvent]:
        return parse_feed_events(
            text,
            source=self.name,
            label=self.label,
            feed_url=self.url,
            since=since,
            limit=MAX_EVENTS_PER_PULL,
        )


class FedRSSSource(FeedMacroSource):
    name = "fed_rss"
    label = "Federal Reserve press releases"
    url = FED_PRESS_RSS_URL


class CFTCRSSSource(FeedMacroSource):
    name = "cftc_rss"
    label = "CFTC press releases"
    url = CFTC_PRESS_RSS_URL


class SECAtomSource(FeedMacroSource):
    name = "sec_atom"
    label = "SEC EDGAR current filings Atom feed"
    url = SEC_CURRENT_ATOM_URL


class BLSEmploymentRSSSource(FeedMacroSource):
    name = "bls_empsit_rss"
    label = "BLS Employment Situation RSS"
    url = BLS_EMPSIT_RSS_URL


class ECBRSSSource(FeedMacroSource):
    name = "ecb_rss"
    label = "European Central Bank press releases"
    url = ECB_PRESS_RSS_URL


class BISRSSSource(FeedMacroSource):
    name = "bis_rss"
    label = "Bank for International Settlements press releases"
    url = BIS_PRESS_RSS_URL


class FOMCCalendarSource(BaseMacroSource):
    name = "fed_fomc"
    label = "Federal Reserve FOMC calendar"
    url = FOMC_CALENDAR_URL
    respect_robots = True
    accept = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

    async def pull(self, since: datetime) -> list[MacroEvent]:
        try:
            text = self._fetch_with_cache(self.url)
        except SourceError:
            sitemap = self._fetch_with_cache(FOMC_SITEMAP_URL)
            text = sitemap
        return self.parse(text, since=since)[:MAX_EVENTS_PER_PULL]

    def parse(self, text: str, *, since: datetime | None = None) -> list[MacroEvent]:
        return parse_fomc_calendar_html(text, page_url=self.url, since=since)


class TreasuryAuctionsSource(BaseMacroSource):
    name = "treasury_auctions"
    label = "TreasuryDirect auction calendar"
    url = TREASURY_AUCTIONS_URL
    respect_robots = True
    accept = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"

    def parse(self, text: str, *, since: datetime | None = None) -> list[MacroEvent]:
        return parse_treasury_auctions_html(text, page_url=self.url, since=since)


def build_default_sources(
    *,
    cache_dir: str | Path | None = None,
    fetcher: HttpFetcher | None = None,
) -> list[BaseMacroSource]:
    kwargs = {"cache_dir": cache_dir, "fetcher": fetcher}
    return [
        FedRSSSource(**kwargs),
        FOMCCalendarSource(**kwargs),
        CFTCRSSSource(**kwargs),
        SECAtomSource(**kwargs),
        TreasuryAuctionsSource(**kwargs),
        BLSEmploymentRSSSource(**kwargs),
        ECBRSSSource(**kwargs),
        BISRSSSource(**kwargs),
    ]


def events_to_dicts(events: Iterable[MacroEvent]) -> list[dict[str, Any]]:
    return [event.to_dict() for event in events]


__all__ = [
    "BISRSSSource",
    "BIS_PRESS_RSS_URL",
    "BLS_EMPSIT_RSS_URL",
    "BLSEmploymentRSSSource",
    "CFTC_PRESS_RSS_URL",
    "CFTCRSSSource",
    "DEFAULT_CACHE_DIR",
    "DEFAULT_USER_AGENT",
    "ECB_PRESS_RSS_URL",
    "ECBRSSSource",
    "FED_PRESS_RSS_URL",
    "FOMC_CALENDAR_URL",
    "FOMCCalendarSource",
    "FedRSSSource",
    "HttpFetcher",
    "MAX_EVENTS_PER_PULL",
    "MAX_FORWARD_CALENDAR_DAYS",
    "MAX_PULLS_PER_HOUR_PER_SOURCE",
    "MacroEvent",
    "SECAtomSource",
    "SEC_CURRENT_ATOM_URL",
    "SourceError",
    "TREASURY_AUCTIONS_URL",
    "TreasuryAuctionsSource",
    "build_default_sources",
    "cache_base_dir",
    "canonical_event_id",
    "events_to_dicts",
    "parse_feed_events",
    "parse_fomc_calendar_html",
    "parse_treasury_auctions_html",
    "user_agent",
]
