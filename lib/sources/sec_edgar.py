"""SEC EDGAR filings adapter (8-K / 10-Q / 10-K).

Primary docs retrieved 2026-04-29:
https://www.sec.gov/edgar/sec-api-documentation
https://www.sec.gov/os/accessing-edgar-data

Operational posture
-------------------

- **Free tier only.** SEC EDGAR's data APIs are free but require a
  declarative ``User-Agent`` string identifying the requester + a contact
  email. We construct one from ``SAPPHIRE_SEC_UA_NAME`` /
  ``SAPPHIRE_SEC_UA_EMAIL`` env (or the global default in
  :mod:`lib.sources`). Failing to set a UA gets you rate-limited or
  permanently blocked.
- **Hard rate-limit cap:** 10 req/sec. SEC officially permits 10 req/sec
  per IP; we throttle to that ceiling regardless of operator override
  (the cap can only be lowered, not raised).
- **Cache 1h.** Per-ticker submission rosters and filings indexes are
  cached at ``~/.cache/sapphire/sec_edgar/`` and re-fetched only after
  the cache TTL expires.
- **Live-mode-only.** ``SAPPHIRE_SEC_LIVE=1`` is the operator flag. Off
  by default; tests and CI runs must NEVER hit live SEC.
- **Curated tickers.** ``~/.sapphire/sec_tickers.yaml`` lists the watched
  tickers (CIKs are auto-resolved from SEC's ticker map). The default
  config path is empty — the operator opts in per ticker.

The adapter exposes the standard ``latest_for(symbol, timeframe) ->
SourceSignal | None`` contract. The signal direction comes from the SEC
classifier (:mod:`lib.sources.sec_classifier`) which interprets the
filing form + 8-K item codes as bull / bear / neutral hints.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lib.correlator.sources import SourceSignal

from . import (
    DEFAULT_USER_AGENT,
    age_seconds,
    cache_dir,
    canonical_symbol,
    clamp,
    http_get_json,
    live_enabled,
    parse_iso,
    read_fresh_json,
    read_json,
    utc_now,
    write_json,
)
from .sec_classifier import FilingEvent, classify_filing, summarize_severity

FetchJson = Callable[[str, Mapping[str, str] | None], Any]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
SEC_HOST = "data.sec.gov"

DEFAULT_TICKERS_CONFIG = Path.home() / ".sapphire" / "sec_tickers.yaml"
CACHE_TTL_SECONDS = 3600  # 1h cache per SEC EDGAR best practice
TICKERS_CACHE_TTL_SECONDS = 24 * 3600  # ticker→CIK roster is daily-stable
MAX_TICKERS_PER_PULL = 5  # operator-cap per call (matches lane spec)
TARGET_FORMS = ("8-K", "10-Q", "10-K", "10-K/A", "10-Q/A", "8-K/A")
RATE_LIMIT_REQ_PER_SEC = 10  # SEC hard-cap; we obey strictly


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Thread-safe leaky-bucket limiter capped at ``rate`` req/sec."""

    def __init__(self, rate: int = RATE_LIMIT_REQ_PER_SEC) -> None:
        self._rate = max(1, min(int(rate), RATE_LIMIT_REQ_PER_SEC))
        self._min_interval = 1.0 / self._rate
        self._lock = threading.Lock()
        self._last_call = 0.0

    @property
    def rate(self) -> int:
        return self._rate

    def acquire(self, *, sleep: Callable[[float], None] = time.sleep, now: Callable[[], float] = time.monotonic) -> None:
        with self._lock:
            elapsed = now() - self._last_call
            wait = self._min_interval - elapsed
            if wait > 0:
                sleep(wait)
            self._last_call = now()


# ---------------------------------------------------------------------------
# Operator config loader (no PyYAML dependency — tiny YAML subset)
# ---------------------------------------------------------------------------


def load_tickers_config(path: Path = DEFAULT_TICKERS_CONFIG) -> list[str]:
    """Load a curated ticker list. Tolerates JSON or a tiny YAML subset.

    Recognized YAML shape::

        tickers:
          - AAPL
          - NVDA
        max_per_pull: 5  # optional override (clamped to MAX_TICKERS_PER_PULL)
    """
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    # Try JSON first (lossless).
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        data = _parse_minimal_yaml(text)
    if not isinstance(data, dict):
        return []
    raw = data.get("tickers")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for value in raw:
        if not value:
            continue
        sym = str(value).strip().upper()
        if sym and sym not in out:
            out.append(sym)
    return out


def _parse_minimal_yaml(text: str) -> dict[str, Any]:
    """Parse the tiny YAML subset we need: ``key: value`` and ``- item`` lists."""

    result: dict[str, Any] = {}
    current_key: str | None = None
    current_list: list[Any] | None = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith("- ") and current_key is not None:
            if current_list is None:
                current_list = []
                result[current_key] = current_list
            value = stripped[2:].strip().strip("\"'")
            current_list.append(value)
            continue
        if ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip("\"'")
            if not value:
                current_key = key
                current_list = None
            else:
                # Try to coerce ints/bools.
                if value.lower() == "true":
                    result[key] = True
                elif value.lower() == "false":
                    result[key] = False
                else:
                    try:
                        result[key] = int(value)
                    except ValueError:
                        result[key] = value
                current_key = None
                current_list = None
        # silently ignore lines we don't understand at the indent we're at
        del indent
    return result


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


def _user_agent(*, override: str | None = None) -> str:
    """Build the required SEC User-Agent header.

    SEC asks for ``SoftwareName/Version (contact-email)``. We try operator
    env first (so a real contact ends up in production), then fall back
    to the lib-wide default that already names this project + an email.
    """
    if override:
        return override
    name = os.environ.get("SAPPHIRE_SEC_UA_NAME") or "SapphireIntelBreadth"
    email = os.environ.get("SAPPHIRE_SEC_UA_EMAIL") or "ops@sapphirealpha.xyz"
    if name and email:
        return f"{name}/0.1 ({email})"
    return DEFAULT_USER_AGENT


@dataclass
class SECEdgarSource:
    """Adapter pulling 8-K / 10-Q / 10-K filings for curated tickers."""

    name: str = "sec_edgar"
    config_path: Path = DEFAULT_TICKERS_CONFIG
    cache_path: Path = field(default_factory=lambda: cache_dir("sec_edgar") / "filings.json")
    tickers_cache_path: Path = field(
        default_factory=lambda: cache_dir("sec_edgar") / "ticker_map.json"
    )
    fetcher: FetchJson | None = None
    user_agent_override: str | None = None
    rate_limiter: RateLimiter = field(default_factory=RateLimiter)
    max_tickers: int = MAX_TICKERS_PER_PULL

    # ----- ticker → CIK resolution -----

    def _ticker_map(self) -> dict[str, str]:
        cached = read_fresh_json(self.tickers_cache_path, ttl_seconds=TICKERS_CACHE_TTL_SECONDS)
        if isinstance(cached, dict) and cached.get("map"):
            mp = cached["map"]
            if isinstance(mp, dict):
                return {str(k): str(v) for k, v in mp.items()}
        if not live_enabled("SEC"):
            stale = read_json(self.tickers_cache_path)
            if isinstance(stale, dict) and isinstance(stale.get("map"), dict):
                return {str(k): str(v) for k, v in stale["map"].items()}
            return {}
        try:
            payload = self._fetch(SEC_TICKERS_URL, self._headers(host="www.sec.gov"))
        except Exception:  # noqa: BLE001 — never fail closed
            return {}
        mapping = self._parse_ticker_map(payload)
        write_json(self.tickers_cache_path, {"retrieved_at": utc_now().isoformat(), "map": mapping})
        return mapping

    @staticmethod
    def _parse_ticker_map(payload: Any) -> dict[str, str]:
        out: dict[str, str] = {}
        if isinstance(payload, Mapping):
            for value in payload.values():
                if not isinstance(value, Mapping):
                    continue
                ticker = str(value.get("ticker") or "").strip().upper()
                cik_raw = value.get("cik_str") or value.get("cik")
                if not ticker or cik_raw is None:
                    continue
                try:
                    cik_int = int(cik_raw)
                except (TypeError, ValueError):
                    continue
                out[ticker] = f"{cik_int:010d}"
        return out

    # ----- HTTP helpers -----

    def _headers(self, *, host: str) -> dict[str, str]:
        return {
            "User-Agent": _user_agent(override=self.user_agent_override),
            "Accept-Encoding": "gzip, deflate",
            "Host": host,
        }

    def _fetch(self, url: str, headers: Mapping[str, str] | None) -> Any:
        self.rate_limiter.acquire()
        if self.fetcher:
            return self.fetcher(url, headers)
        return http_get_json(url, headers=headers)

    # ----- Filings pull -----

    def _pull_submissions(self, cik: str) -> dict[str, Any]:
        url = SEC_SUBMISSIONS_URL.format(cik=cik)
        try:
            return self._fetch(url, self._headers(host=SEC_HOST))
        except Exception:  # noqa: BLE001
            return {}

    @staticmethod
    def _flatten_recent_filings(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
        if not isinstance(payload, Mapping):
            return []
        filings = payload.get("filings") or {}
        recent = filings.get("recent") if isinstance(filings, Mapping) else None
        if not isinstance(recent, Mapping):
            return []
        # Recent is column-oriented; we transpose into row-records.
        forms = recent.get("form") or []
        accessions = recent.get("accessionNumber") or []
        filed = recent.get("filingDate") or []
        report = recent.get("reportDate") or []
        items = recent.get("items") or []
        primary_doc = recent.get("primaryDocument") or []
        rows: list[dict[str, Any]] = []
        n = min(len(forms), len(accessions), len(filed))
        for i in range(n):
            rows.append(
                {
                    "form": str(forms[i] or "").upper(),
                    "accession": str(accessions[i] or ""),
                    "filed": str(filed[i] or ""),
                    "report_date": str(report[i] or "") if i < len(report) else "",
                    "items": str(items[i] or "") if i < len(items) else "",
                    "primary_document": str(primary_doc[i] or "") if i < len(primary_doc) else "",
                }
            )
        return rows

    def _snapshot(self, *, tickers: Sequence[str] | None = None) -> dict[str, Any]:
        cached = read_fresh_json(self.cache_path, ttl_seconds=CACHE_TTL_SECONDS)
        if isinstance(cached, dict) and cached.get("filings"):
            return cached
        if not live_enabled("SEC"):
            stale = read_json(self.cache_path)
            return stale if isinstance(stale, dict) else {"filings": {}}
        target_tickers = list(tickers or load_tickers_config(self.config_path))
        target_tickers = [t.upper() for t in target_tickers if t]
        target_tickers = target_tickers[: max(0, min(self.max_tickers, MAX_TICKERS_PER_PULL))]
        if not target_tickers:
            return {"retrieved_at": utc_now().isoformat(), "filings": {}}
        ticker_map = self._ticker_map()
        out: dict[str, list[dict[str, Any]]] = {}
        for ticker in target_tickers:
            cik = ticker_map.get(ticker)
            if not cik:
                continue
            payload = self._pull_submissions(cik)
            rows = [
                row for row in self._flatten_recent_filings(payload)
                if row["form"] in TARGET_FORMS
            ]
            out[ticker] = rows
        snapshot = {
            "retrieved_at": utc_now().isoformat(),
            "filings": out,
            "rate_limit_req_per_sec": self.rate_limiter.rate,
        }
        write_json(self.cache_path, snapshot)
        return snapshot

    # ----- Public reads -----

    def list_events(self, *, tickers: Sequence[str] | None = None) -> list[FilingEvent]:
        """Flatten the cache into classified :class:`FilingEvent` records."""

        snapshot = self._snapshot(tickers=tickers)
        events: list[FilingEvent] = []
        retrieved_iso = snapshot.get("retrieved_at") or utc_now().isoformat()
        for ticker, rows in (snapshot.get("filings") or {}).items():
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                event = classify_filing(
                    ticker=str(ticker),
                    form=str(row.get("form") or ""),
                    items_field=str(row.get("items") or ""),
                    filed_at=str(row.get("filed") or ""),
                    accession=str(row.get("accession") or ""),
                    primary_document=str(row.get("primary_document") or ""),
                    retrieved_at=str(retrieved_iso),
                )
                events.append(event)
        return events

    def latest_for(self, symbol: str, timeframe: str) -> SourceSignal | None:
        target = canonical_symbol(symbol)
        events = self.list_events()
        # Same canonicalization keeps BTC-USD-style asset hints from leaking;
        # SEC filings are equity-symbol keyed (no -USD suffix), so we just
        # compare upper-cased target.
        candidates = [e for e in events if e.ticker.upper() == target]
        if not candidates:
            return None
        # Newest first by filed date.
        candidates.sort(key=lambda e: parse_iso(e.filed_at) or utc_now(), reverse=True)
        top = candidates[0]
        ts = parse_iso(top.filed_at) or utc_now()
        confidence = clamp(_severity_to_confidence(top.severity), default=0.4)
        return SourceSignal(
            source=self.name,
            symbol=target,
            timeframe=timeframe,
            direction=top.direction,
            confidence=confidence,
            age_seconds=age_seconds(ts),
            timestamp_iso=ts.isoformat(),
            raw={
                "form": top.form,
                "items": top.items,
                "accession": top.accession,
                "summary": top.summary,
                "severity": top.severity,
                "live_operator_flag": live_enabled("SEC"),
                "max_tickers_per_pull": min(self.max_tickers, MAX_TICKERS_PER_PULL),
                "rate_limit_req_per_sec": self.rate_limiter.rate,
            },
        )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _severity_to_confidence(severity: str) -> float:
    """Map classifier severity tier to a [0, 1] correlator confidence."""
    severity = (severity or "").lower()
    if severity == "high":
        return 0.75
    if severity == "medium":
        return 0.55
    if severity == "low":
        return 0.35
    return 0.30


def filter_events(
    events: Iterable[FilingEvent],
    *,
    forms: Sequence[str] | None = None,
    severities: Sequence[str] | None = None,
) -> list[FilingEvent]:
    """Filter classified filings; helper used by the plugin tool."""
    forms_set = {f.upper() for f in (forms or [])}
    sev_set = {s.lower() for s in (severities or [])}
    out: list[FilingEvent] = []
    for event in events:
        if forms_set and event.form.upper() not in forms_set:
            continue
        if sev_set and event.severity.lower() not in sev_set:
            continue
        out.append(event)
    return out


def severity_breakdown(events: Iterable[FilingEvent]) -> dict[str, int]:
    """Count events by severity bucket — useful for ops + plugin status."""
    return summarize_severity(events)


__all__ = [
    "CACHE_TTL_SECONDS",
    "DEFAULT_TICKERS_CONFIG",
    "MAX_TICKERS_PER_PULL",
    "RATE_LIMIT_REQ_PER_SEC",
    "RateLimiter",
    "SECEdgarSource",
    "SEC_SUBMISSIONS_URL",
    "SEC_TICKERS_URL",
    "TARGET_FORMS",
    "filter_events",
    "load_tickers_config",
    "severity_breakdown",
]
