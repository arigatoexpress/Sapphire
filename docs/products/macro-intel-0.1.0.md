# Regulatory + Macro Intelligence Daemon 0.1.0

Sapphire Macro Intel 0.1.0 is a first-party official-source watcher for
monetary policy, regulatory enforcement, Treasury supply, labor-market data,
and international central-bank signals. It exists because trading and
intelligence decisions are fragile when they know price action but not the
official calendar around that price action. A BTC long opened five minutes
before an FOMC statement, a SOL thesis formed during a CFTC enforcement window,
or an equity risk-on signal during a hot payrolls release should all carry a
different risk label than the same signal on an empty calendar.

The first release is deliberately deterministic. It does not call an LLM. It
does not need secrets. It reads official RSS, Atom, and HTML sources, parses
them into a shared `MacroEvent` schema, classifies each event with a documented
keyword table, and builds a forward-looking calendar that downstream agents can
query. The default runtime posture is dry-run and bounded: no official HTTP
pull is made unless `--live` or `SAPPHIRE_MACRO_INTEL_LIVE=1` is set, event-bus
publishing is separately gated by `--publish` and
`SAPPHIRE_MACRO_INTEL_LIVE_BUS=1`, and source counters cap pulls at four per
hour per source.

## Supported Sources

Version 0.1.0 covers the requested official sources:

| Source | Type | URL | Use |
|---|---|---|---|
| Federal Reserve press feed | RSS | `https://www.federalreserve.gov/feeds/press_all.xml` | FOMC statements, supervision releases, policy speeches, and board announcements. |
| Federal Reserve FOMC calendar | HTML | `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm` | Scheduled FOMC meetings. HTML fetches check robots.txt first. |
| CFTC press releases | RSS | `https://www.cftc.gov/PressRoom/PressReleases.rss` | Enforcement, market manipulation, crypto platform, and derivatives-market actions. |
| SEC current Atom feed | Atom | `https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=&company=&dateb=&owner=include&count=40&output=atom` | Current SEC filing and release stream surfaced as a regulatory context layer. |
| TreasuryDirect auctions | HTML | `https://www.treasurydirect.gov/auctions/auctions-query/` | Scheduled bill, note, and bond auctions. HTML fetches check robots.txt first. |
| BLS Employment Situation | RSS | `https://www.bls.gov/feed/news_release/empsit.rss` | Payrolls, unemployment, wage, and labor-market data releases. |
| ECB press releases | RSS | `https://www.ecb.europa.eu/rss/press.html` | Euro-area monetary policy and international FX context. |
| BIS press releases | RSS | `https://www.bis.org/list/press_releases/index.rss` | Global central-bank coordination, Basel, systemic risk, and crypto-prudential context. |

Every parsed event includes a `metadata.source_url`, and feed events also carry
`metadata.feed_url`. This is a product requirement, not decorative metadata:
dashboards and later Foundry ontology syncs should be able to deep-link back to
the official source rather than treating the local JSONL as the source of
truth.

## Event Schema

The core event model lives in `lib/macro/sources.py`:

```json
{
  "id": "24-char-sha256-prefix",
  "source": "fed_rss",
  "title": "Federal Reserve issues FOMC statement and holds rates unchanged",
  "summary": "The Committee decided to maintain the target range...",
  "url": "https://www.federalreserve.gov/newsevents/...",
  "published_at": "2026-01-29T19:00:00+00:00",
  "metadata": {
    "source_name": "Federal Reserve press releases",
    "source_url": "https://www.federalreserve.gov/newsevents/...",
    "feed_url": "https://www.federalreserve.gov/feeds/press_all.xml",
    "official_source": true,
    "parser": "feedparser"
  }
}
```

The ID is stable across runs because it is derived from source, title, URL, and
timestamp. This lets the daemon append to `data/macro/<date>/events.jsonl`
without creating duplicate rows when the same item appears in a feed on multiple
polls. Runtime rows are provenance-stamped with the shared Sapphire provenance
envelope and the daily JSONL gets an `.envelope.json` sidecar.

## Classification

`lib/macro/classifier.py` implements a pure heuristic classifier. It returns:

| Field | Values |
|---|---|
| `category` | `monetary_policy`, `regulatory_enforcement`, `data_release`, `treasury_auction`, `international`, `other` |
| `assets_likely_affected` | Examples: `BTC`, `ETH`, `SOL`, `equities`, `gold`, `USD`, `EUR`, `bonds` |
| `expected_impact_severity` | `low`, `medium`, `high`, `extreme` |
| `direction_hint` | `hawkish`, `dovish`, `neutral`, `mixed` |
| `confidence` | Bounded heuristic score from 0 to 0.95 |
| `reasons` | Compact explanation strings showing source and keyword matches |

The classifier gives source hints a baseline score, then applies category
keywords. For example, Fed/FOMC source material starts with a monetary-policy
prior, CFTC/SEC starts with regulatory-enforcement prior, and TreasuryDirect
starts with treasury-auction prior. Keyword matches can still override or
strengthen that prior. A BLS title containing "CPI" and "inflation" lands in
`data_release`; a BIS release containing "crypto leverage" lands in
`international` while also affecting `BTC`, `ETH`, and `SOL`.

Severity is similarly explicit. "Emergency", "surprise", "100 basis", major
exchange names, sanctions, and bans are `extreme`. FOMC rate decisions,
payrolls, CPI, enforcement charges, settlements, and long-bond auctions are
`high`. Speeches, minutes, generic auctions, ECB/BIS publications, and guidance
are `medium`. Weakly matched official notices are `low`.

Direction is a policy-posture hint rather than a trading instruction. "Hike",
"restrictive", "hotter than expected", weak auction demand, and enforcement
language are `hawkish`. "Cut", "pause", "holds rates", "unchanged", "cooling
inflation", and approval/exemption language are `dovish`. Mixed or conflicting
phrases produce `mixed`; otherwise the classifier returns `neutral`.

## Calendar

`lib/macro/calendar.py` converts scheduled macro events into a forward calendar.
FOMC HTML rows and Treasury auction rows become first-class `CalendarEvent`
objects. The calendar also adds an approximation for upcoming BLS Employment
Situation releases using the first Friday of each month at 8:30 AM Eastern
represented as 12:30 UTC. The runbook labels this BLS helper as a planning
approximation and confirmation-only until an operator verifies the official BLS
schedule page.

The calendar API supports:

* `in_next_hours(hours)` for "what official windows are opening soon?"
* `next_event_for_asset(asset)` for asset-specific context.
* `to_dicts()` / `calendar_from_dicts()` for JSONL round trips.

The daemon publishes a `macro.calendar.window_opening` payload only for events
inside the next 24 hours, and only when bus publishing is explicitly enabled.
The plugin can query the calendar without enabling live pulls.

## Daemon and Tooling

The daemon entrypoint is:

```bash
python3 services/macro_intel/run.py run-once
python3 services/macro_intel/run.py run-once --live
python3 services/macro_intel/run.py daemon --poll-interval-seconds 900 --live
python3 services/macro_intel/run.py status
```

An optional FRED/ALFRED extension writes point-in-time observations for macro
regime features:

```bash
python3 services/macro_intel/run.py run-once --fred
```

Live cache misses require `SAPPHIRE_FRED_LIVE=1` and `FRED_API_KEY`. These rows
use `observation_date`, `value`, `realtime_start`, and `realtime_end` rather
than the `MacroEvent` schema, because they are historical observations rather
than announcements.

Default `run-once` is dry-run. It builds the static planning calendar, reports
the gate reason, and exits without official HTTP calls. Live pulls are bounded
by per-source counters under `~/.cache/sapphire/macro/<source>/`. The cache also
stores raw response bodies and metadata with URL, user agent, and fetch time.

The plugin tool lives at
`plugins/claw-sapphire/tools/internal/macro_intel.py` with a top-level shim at
`plugins/claw-sapphire/tools/macro_intel.py`. It accepts stdin JSON:

```json
{"action": "recent", "limit": 10}
{"action": "calendar", "hours": 48}
{"action": "next-event-for-asset", "asset": "BTC"}
{"action": "pull-once", "live": true}
{"action": "status"}
```

The tool has a double live gate. Passing `"live": true` is not enough; the env
must also include `SAPPHIRE_MACRO_INTEL_LIVE=1`. This mirrors the bounded
posture used elsewhere in Sapphire, keeps tests hermetic, and prevents a casual
operator query from touching official sites.

## Product Boundaries

Macro Intel 0.1.0 is a context feed, not a prediction engine. It does not say
"buy BTC" because payrolls were strong, and it does not infer hidden policy
intent. It says that an official event happened or is scheduled, it classifies
the event with deterministic rules, and it supplies context that other systems
can join to trading signals, narrative synthesis, diligence pages, or event
impact lookup. That distinction matters. Sapphire should know when an event is
official and relevant, but the trading system still needs separate evidence
before acting.

The release also avoids real Telegram sends, secret reads, authenticated
endpoints, and paid APIs. All sources are public official pages. The SEC and
HTML scrapes use a descriptive User-Agent with a contact string, and HTML
fetches check robots.txt before retrieving the target page. Tests commit small
historical fixture XML/HTML files under `tests/fixtures/macro/`; they do not
make live calls.

Future versions should add richer source-specific parsing, official BLS schedule
HTML parsing, dashboard pages, Foundry ontology sync, and integration with the
Lane 7 event-impact lookup. Version 0.1.0 intentionally stops at the durable
foundation: official-source ingestion, source citations, local cache/caps,
heuristic classification, forward calendar windows, daemon output, and plugin
queries.
