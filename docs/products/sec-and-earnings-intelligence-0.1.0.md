# SEC Filings + Earnings Call Intelligence 0.1.0

**Status:** internal release · **Lane:** Tranche-6 Lane 7 · **Date:** 2026-04-29

## Why this exists

Sapphire's correlator already fuses signal across nine market-derived sources
(TradingView webhooks, Telegram intel, Hyperliquid public feed, Kronos
forecasts, TA scanner, threat intel, convergence watchlist, sovereign thesis,
cross-asset regime). What it has been missing for the entire run-up to
Tranche 6 is **primary corporate disclosure**.

For US equities, the most authoritative source for company-specific signal is
the SEC's EDGAR system: 8-K material event filings, 10-Q quarterly reports,
10-K annual reports, and their amendments. EDGAR is **free** to query, has
a documented public API, and has been the single most important corporate
data source for institutional research desks for two decades. A trading
intelligence platform without an EDGAR feed is, in the buyer's eyes,
incomplete.

The second-most information-dense corporate source is the earnings call
transcript itself — a quarterly hour-long broadcast in which company
management is forced to speak on record, in plain English, about the
business. Most well-known transcript providers are paywalled, ToS-restrictive,
or both. We deliberately ship only the **free-tier** subset in 0.1.0:
operator-curated investor-relations RSS feeds plus operator-supplied
transcript fixtures. Paid providers are documented but **not wired**.

This release adds:

1. `lib/sources/sec_edgar.py` — pulls 8-K / 10-Q / 10-K filings for a curated
   ticker list, classifies each filing, and exposes a `latest_for(symbol,
   timeframe)` adapter that the correlator can consume directly.
2. `lib/sources/earnings_calls.py` — pulls earnings-related items from
   operator-supplied IR RSS feeds, scores them with a deterministic
   bag-of-words sentiment classifier, and exposes the same correlator-input
   contract.
3. `lib/sources/sec_classifier.py` — pure deterministic classifier mapping
   8-K item codes (1.01 material agreement, 4.01 auditor change, 4.02
   restatement, etc.) and 10-K/10-Q forms to structured `FilingEvent`
   records carrying severity / direction / asset hints.
4. Registration of both adapters as correlator input sources via
   `lib/correlator/sources.py`.
5. An example operator config at `infra/sec_tickers.example.yaml` (zero real
   ticker handles by default).

Source of truth for SEC API behavior: [SEC EDGAR API
documentation](https://www.sec.gov/edgar/sec-api-documentation), retrieved
2026-04-29.

## What an 8-K item code means

The 8-K is the SEC's "current report" form. When a public company has a
material event between 10-Q / 10-K filings, it must file an 8-K within four
business days. Each 8-K names one or more **item codes** — the SEC's
structured taxonomy for what the event is.

We classify a representative subset:

| Code | Severity | Direction | Meaning |
|------|----------|-----------|---------|
| 1.01 | high | neutral | Material definitive agreement entered into |
| 1.02 | high | bear    | Material definitive agreement terminated |
| 1.03 | high | bear    | Bankruptcy or receivership |
| 2.01 | high | neutral | Completion of acquisition or disposition |
| 2.02 | high | neutral | Results of operations and financial condition (earnings press release) |
| 2.04 | high | bear    | Triggering events accelerating financial obligation |
| 2.06 | high | bear    | Material impairments |
| 3.01 | high | bear    | Listing standards / delisting notice |
| 4.01 | high | bear    | Change in registrant's certifying accountant |
| 4.02 | high | bear    | Non-reliance on previously issued financials (restatement) |
| 5.02 | medium | neutral | Departure / appointment of officers / directors |
| 7.01 | low | neutral | Regulation FD disclosure |
| 8.01 | low | neutral | Other events (registrant elected disclosure) |
| 9.01 | low | neutral | Financial statements and exhibits |

The full mapping lives in `ITEM_8K_MAP`. For a multi-item 8-K, the highest
severity wins; ties break toward `bear`. This is intentional — an 8-K is
material by definition, and downside events (impairments, restatements,
auditor change) are far more often the reason multiple items are bundled
together than upside ones.

## Architecture

```
+-----------------------------------------------+
|  ~/.sapphire/sec_tickers.yaml (operator)      |
+-----------------------------------------------+
                  |
                  v
+-----------------------------------------------+        +-----------------+
|  lib/sources/sec_edgar.py                     |  ----> |  RateLimiter    |
|  (10 req/sec hard cap)                        |        |  (10 req/sec)   |
+-----------------------------------------------+        +-----------------+
                  |                                              |
                  | classify_filing()                            v
                  v                                       +-----------------+
+-----------------------------------------------+        |  data.sec.gov   |
|  lib/sources/sec_classifier.py                |        |  (live mode     |
|  (FilingEvent: form, items, severity, dir)    |        |   only)         |
+-----------------------------------------------+        +-----------------+
                  |
                  | latest_for(symbol, timeframe)
                  v
+-----------------------------------------------+
|  lib/correlator/sources.py                    |
|  (registers SEC + earnings as new correlator  |
|   input sources alongside the existing 14)    |
+-----------------------------------------------+
```

Earnings calls follow the same input-shape:

```
+-----------------------------------------------+
|  ~/.sapphire/earnings_rss.yaml (operator)     |
+-----------------------------------------------+
                  |
                  v
+-----------------------------------------------+
|  lib/sources/earnings_calls.py                |
|  - operator IR RSS feeds                      |
|  - operator transcript fixtures               |
|  (5 req/sec ceiling)                          |
+-----------------------------------------------+
                  |
                  v latest_for() → SourceSignal
```

## Live-mode posture

Both adapters default to **dry-run**. They consume cached data only. To go
live, the operator sets:

- `SAPPHIRE_SEC_LIVE=1` for SEC EDGAR.
- `SAPPHIRE_EARNINGS_LIVE=1` for earnings calls.

These flags are **independent**. You can run earnings live while keeping
SEC dry, or vice versa.

### SEC's User-Agent requirement

SEC EDGAR is **free** but mandates a `User-Agent` header that identifies
the requester plus a contact email. From the [SEC's published guidance][1]:

> Please declare your traffic by updating your user agent to include
> company specific information.

We construct a UA from two operator env vars:

```bash
export SAPPHIRE_SEC_UA_NAME="YourFirmName"
export SAPPHIRE_SEC_UA_EMAIL="ops@yourfirm.example"
```

The adapter falls back to the lib-wide default UA if either is unset, but
the fallback is generic. **In production, set both.** Operators that fail
to identify themselves are eventually rate-limited or permanently blocked
by SEC.

[1]: https://www.sec.gov/os/accessing-edgar-data

### Rate limit posture

SEC EDGAR's published ceiling is **10 requests per second per IP**. The
adapter ships with a thread-safe leaky-bucket `RateLimiter` set to that
ceiling. If an operator passes a higher rate (e.g. `RateLimiter(rate=99)`),
it is silently clamped to `RATE_LIMIT_REQ_PER_SEC` (10) — the ceiling can
only be lowered, never raised.

We also cache submission rosters and ticker→CIK maps for **1h** (filings)
and **24h** (ticker map), so a typical hourly correlator pass burns very
few requests against SEC infrastructure.

## Free-tier earnings call coverage

The adapter currently consumes two free input shapes:

1. **Investor-relations RSS feeds.** Public companies often syndicate
   their own press releases via RSS (e.g. apple.com, nvidia.com,
   microsoft.com, alphabet.com). The operator adds these to
   `~/.sapphire/earnings_rss.yaml`:

   ```yaml
   feeds:
     - ticker: AAPL
       rss_url: https://investor.apple.com/rss-news
     - ticker: NVDA
       rss_url: https://investor.nvidia.com/rss
   ```

2. **Operator-supplied transcript fixtures.** Drop a `.txt` or `.json`
   transcript into `~/.cache/sapphire/earnings_calls/<TICKER>/<date>.txt`
   and the adapter will read + classify it on the next pull. This is the
   right path for backtest replay or for tickers whose IR feed is not
   syndicated.

### Paid providers we do NOT wire

For transparency, the following providers are documented in
`PAID_PROVIDER_STUBS` but are **not** called by 0.1.0:

- AlphaVantage's earnings-call-transcript add-on.
- Polygon.io's earnings-call data plan.
- Tiingo's news-with-transcripts plan.

These would each add a few hundred USD / month to the run rate and require
operator credentials. They are out of scope for a free-tier release. A
follow-up tranche can wire any of them behind a separate
`SAPPHIRE_<PROVIDER>_LIVE` flag.

## Sentiment scoring

Earnings call sentiment is intentionally **bag-of-words**, not LLM-based.
This keeps it:

- Fast (sub-millisecond per transcript).
- Deterministic (the same transcript yields the same sentiment forever).
- Tested (no flaky model behavior).

Positive terms (`POSITIVE_TERMS` in `earnings_calls.py`) include `beat`,
`record`, `exceeded`, `raised`, `growth`, `tailwind`, `expansion`,
`buyback`. Negative terms include `miss`, `shortfall`, `lowered`,
`headwind`, `weak`, `delay`, `investigation`, `subpoena`, `lawsuit`,
`restatement`, `downgrade`, `layoff`, `warning`. We count both
absolute occurrences and distinct hits.

A net positive score yields `bull`; net negative yields `bear`; tie yields
`neutral`. Confidence scales with magnitude, capped at 0.80.

This is a coarse signal by design. The correlator already runs LLM-based
narrative synthesis on top of all inputs (Tranche 5 Lane 6); duplicating
LLM sentiment here would add latency without adding signal.

## Dataclasses

### `FilingEvent` (sec_classifier.py)

```python
@dataclass(frozen=True)
class FilingEvent:
    ticker: str
    form: str               # "8-K", "10-Q", "10-K", "10-K/A", ...
    items: str              # "1.01,2.02" for 8-K, "" otherwise
    severity: str           # "low" | "medium" | "high"
    direction: str          # "bull" | "bear" | "neutral"
    summary: str            # short human-readable hint
    filed_at: str           # ISO date from SEC
    accession: str
    primary_document: str
    retrieved_at: str
    asset_hints: tuple[str, ...]  # e.g. ("AAPL",)
```

### `TranscriptSentiment` (earnings_calls.py)

```python
@dataclass(frozen=True)
class TranscriptSentiment:
    ticker: str
    direction: str          # "bull" | "bear" | "neutral"
    confidence: float       # 0..1
    title: str
    published_at: str
    source_url: str
    source_kind: str        # "rss" | "fixture"
    positive_hits: int
    negative_hits: int
```

## Correlator integration

Both adapters appear in `lib.correlator.sources.available_sources()` and
`build_default_sources()`. The signal correlation engine treats them like
any other source:

- They emit a normalized `SourceSignal(symbol, timeframe, direction,
  confidence, age_seconds, timestamp_iso, raw=…)`.
- They never raise from `latest_for()` — failures degrade to `None`.
- The `raw` field includes provenance metadata: `live_operator_flag`,
  `rate_limit_req_per_sec`, the underlying form / items / source URL.

This means the correlator's existing weighting, freshness penalties, and
direction-agreement logic just work on the new sources.

## Testing posture

- **40+ unit tests** across the three modules:
  - `tests/unit/test_sources_sec_edgar.py` (≥ 16): config loading, UA
    contract, rate-limit ceiling, dry-run vs live, max-tickers cap,
    cache TTL, latest_for behavior, correlator registration.
  - `tests/unit/test_sources_sec_classifier.py` (≥ 12): item-code parsing,
    classification of 4.01 (bear), 1.01 (high neutral), 4.02 (bear),
    multi-item highest-wins, 10-K/10-Q form-base mapping, amendment
    detection, severity + direction aggregations, asset hints.
  - `tests/unit/test_sources_earnings_calls.py` (≥ 12): config loading,
    rate limiter, RSS parsing, earnings-relatedness filter (title-only),
    sentiment scoring, fixture loader, live-pull flow, paid-provider
    stubs are documented-only.
- **No live HTTP** — every test uses an injected `fetcher` callable.
- **Independent of CI runners** — no requests, no responses library, no
  network in any code path under test.

## What's deliberately out of scope for 0.1.0

- **No XBRL parsing.** 10-K / 10-Q financials in machine-structured form
  require an XBRL parser; we only consume the filings *index*. The body
  of the filing is referenced by `primary_document` URL but not fetched.
- **No paid earnings transcripts.** See "Free-tier coverage" above.
- **No insider-transaction Form 4.** Adding Form 4 would add a separate
  classifier for insider buys vs sells; out of scope here.
- **No 13F holdings.** Quarterly fund-holdings filings are interesting but
  warrant their own adapter and aggregation engine.
- **No PDF extraction.** Earnings press releases that arrive as PDF
  attachments are not parsed; the title + description are used.

These are good Tranche 7+ candidates.

## Operator runbook

See `docs/ops/sec-and-earnings-runbook.md` for day-to-day operations:
how to add a ticker, how to flip live mode, how to read the cache, and
what to do when SEC rate-limits you.
