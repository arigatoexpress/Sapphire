# Macro Intel Runbook

This runbook covers Sapphire's regulatory and macro intelligence daemon at
`services/macro_intel/run.py` and the matching plugin tool at
`plugins/claw-sapphire/tools/internal/macro_intel.py`. The service watches
official macro, central-bank, and regulatory sources, classifies the resulting
events, writes append-only JSONL artifacts, and optionally publishes to the
Sapphire event bus.

The primary safety rule is simple: the default path is dry-run. A normal status
or plugin query must not contact official sites, must not publish to Redis, must
not send Telegram messages, and must not require secrets. Live public HTTP is
available only when intentionally enabled.

## Files

| Path | Purpose |
|---|---|
| `lib/macro/sources.py` | Official source fetchers, parsers, cache, robots checks, and rate caps. |
| `lib/macro/fred_loader.py` | Cache-first FRED/ALFRED observation loader for macro regime features and vintage-aware backtests. |
| `lib/macro/classifier.py` | Pure heuristic category, severity, direction, and asset classifier. |
| `lib/macro/calendar.py` | Forward calendar utilities for FOMC, Treasury auctions, and payroll planning. |
| `services/macro_intel/run.py` | CLI daemon and single-tick runner. |
| `services/macro_intel/launchagent/com.sapphire.macro-intel.plist.template` | Safe LaunchAgent template. It does not enable live HTTP by default. |
| `plugins/claw-sapphire/tools/internal/macro_intel.py` | Stdin-JSON plugin tool for recent events, calendar queries, and bounded pull-once. |
| `plugins/claw-sapphire/tools/macro_intel.py` | Compatibility shim. |
| `data/macro/<YYYY-MM-DD>/events.jsonl` | Runtime event output. Do not commit. |
| `data/macro/<YYYY-MM-DD>/calendar.jsonl` | Runtime calendar output. Do not commit. |
| `data/macro/<YYYY-MM-DD>/fred_observations.jsonl` | Optional FRED/ALFRED observation output. Do not commit. |
| `~/.cache/sapphire/macro/<source>/` | Per-source raw response cache and counters. |
| `~/.cache/sapphire/macro/fred/` | Default FRED payload cache when `SAPPHIRE_FRED_CACHE_DIR` is unset. |

## Commands

Dry-run status:

```bash
python3 services/macro_intel/run.py status
python3 services/macro_intel/run.py run-once
```

Live one-shot pull from official public sources:

```bash
SAPPHIRE_MACRO_INTEL_LIVE=1 \
python3 services/macro_intel/run.py run-once --live
```

Live daemon loop, no event bus:

```bash
SAPPHIRE_MACRO_INTEL_LIVE=1 \
python3 services/macro_intel/run.py daemon --poll-interval-seconds 900 --live
```

Live daemon loop with event-bus publishing:

```bash
SAPPHIRE_MACRO_INTEL_LIVE=1 \
SAPPHIRE_MACRO_INTEL_LIVE_BUS=1 \
python3 services/macro_intel/run.py daemon --poll-interval-seconds 900 --live --publish
```

Cache-first FRED/ALFRED observation writer:

```bash
python3 services/macro_intel/run.py run-once --fred
```

Daily bounded FRED export routine:

```bash
python3 services/macro_intel/run.py fred-daily-export
```

Live FRED pull for cache misses:

```bash
SAPPHIRE_FRED_LIVE=1 \
FRED_API_KEY=... \
python3 services/macro_intel/run.py fred-daily-export --live
```

Dry-run the GCS upload transform after local FRED artifacts exist:

```bash
python3 -m services.pipeline.gcp_sync --dry-run --source fred
```

Plugin examples:

```bash
echo '{"action":"status"}' | python3 plugins/claw-sapphire/tools/macro_intel.py
echo '{"action":"calendar","hours":48}' | python3 plugins/claw-sapphire/tools/macro_intel.py
echo '{"action":"next-event-for-asset","asset":"BTC"}' | python3 plugins/claw-sapphire/tools/macro_intel.py
echo '{"action":"pull-once","live":true}' | python3 plugins/claw-sapphire/tools/macro_intel.py
```

The plugin's `"live": true` request is still dry-run unless
`SAPPHIRE_MACRO_INTEL_LIVE=1` is present. This is intentional and should not be
weakened.

## Environment

| Variable | Default | Meaning |
|---|---|---|
| `SAPPHIRE_MACRO_INTEL_LIVE` | unset | Required for official public HTTP pulls. |
| `SAPPHIRE_MACRO_INTEL_LIVE_BUS` | unset | Required, with `--publish`, for event-bus publishing. |
| `SAPPHIRE_MACRO_CACHE_DIR` | `~/.cache/sapphire/macro` | Cache and counter root. Override in tests or temporary runs. |
| `SAPPHIRE_MACRO_OUTPUT_ROOT` | `data/macro` | Local append-only macro artifact root for daily FRED rows. |
| `SAPPHIRE_MACRO_USER_AGENT` | `SapphireMacroIntel/0.1 (+https://github.com/arigatoexpress/Sapphire; contact=ops@sapphirealpha.xyz)` | User-Agent for official pulls and robots checks. |
| `SAPPHIRE_FRED_LIVE` | unset | Required, with `FRED_API_KEY`, for live FRED/ALFRED cache misses. |
| `FRED_API_KEY` | unset | FRED API key. Used only by `--fred` when the FRED live gate is enabled. |
| `SAPPHIRE_FRED_CACHE_DIR` | `~/.cache/sapphire/macro/fred` | FRED payload cache override. |
| `SAPPHIRE_FRED_USER_AGENT` | `SapphireFredLoader/0.1 (+https://github.com/arigatoexpress/Sapphire; contact=ops@sapphirealpha.xyz)` | User-Agent for FRED observations pulls. |

The event-source daemon uses no API keys. FRED/ALFRED is a separate gated
provider: it may read `FRED_API_KEY` only when `--fred` is requested and
`SAPPHIRE_FRED_LIVE=1` is set. Do not write keys into repo files, artifacts, or
operator notes.

## Operating Posture

Macro Intel is bounded along four axes:

1. Live HTTP is opt-in.
2. Event-bus publishing is separately opt-in.
3. Each source is capped at four pulls per rolling hour.
4. Each pull is capped at 100 parsed events and the forward calendar is capped
   at 90 days.

The optional FRED writer is bounded separately: it is cache-first, its live
cache-miss path requires `SAPPHIRE_FRED_LIVE=1`, and every observation row keeps
`realtime_start` and `realtime_end` so ALFRED vintages can be used for
point-in-time backtests without label leakage.

If a source exceeds its cap and a cached raw payload exists, the source parser
uses the cached payload. If no cache exists, the source returns a recoverable
source error. One source failure does not stop other sources from parsing.

The daemon writes append-only JSONL. It deduplicates by event ID inside the
target daily file. Each row is stamped with Sapphire provenance metadata and
each artifact gets an `.envelope.json` sidecar. The sidecar is useful for later
Foundry sync, dashboard lineage checks, and handoff reports.

## Source Credibility Notes

Federal Reserve RSS is first-party and high-trust for Federal Reserve board
announcements. Treat it as authoritative for the fact and wording of a release.
It is not a market-impact oracle. The classifier can tag "rate hike" or "holds
rates" as hawkish or dovish, but later trading logic must still evaluate price,
liquidity, and positioning.

Federal Reserve FOMC calendar is first-party and high-trust for scheduled FOMC
meetings. It is an HTML page, not a feed, so the fetcher checks robots.txt
before retrieving it. Parsed meeting dates should be treated as official
calendar context. The precise statement time is represented as a UTC planning
time; operators should confirm exact release timing for high-risk live trading
windows.

FRED and ALFRED observations are first-party St. Louis Fed time-series data,
not event/news items. Treat `value="."` as missing, respect each series'
native frequency, and keep realtime vintage windows in every warehouse row.
FRED data can be used in paid derived reports and backtests only after source
terms and redistribution posture are reviewed for that product.

CFTC press RSS is first-party and high-trust for enforcement and regulatory
announcements from the Commodity Futures Trading Commission. It is especially
relevant for derivatives, market manipulation, fraud, exchange conduct, and
digital-asset enforcement. Treat it as authoritative for the existence of the
action. Treat market effect as contextual until joined with price and venue
data.

SEC Atom current feed is an official SEC/EDGAR surface, but the current feed is
broad. It can include filings and updates that are not enforcement press
releases. Version 0.1.0 classifies SEC items heuristically and carries the
source URL. Treat this source as first-party but noisy. For high-severity
signals, confirm with the linked SEC release or filing before escalating.

TreasuryDirect auction pages are first-party and high-trust for Treasury
auction schedules and details. The parser expects table rows containing
security type, CUSIP, auction date, issue date, and maturity date. HTML fetches
check robots.txt. Treasury auctions are important for USD, yields, bonds, gold,
and risk assets, but the daemon does not infer auction demand unless the source
text contains demand/yield language.

BLS Employment Situation RSS is first-party and high-trust for published labor
data releases. The forward payroll calendar helper uses a first-Friday planning
rule and points to the official BLS schedule page. Treat generated future BLS
calendar rows as confirmation-only until reviewed against the official schedule
or replaced by a dedicated schedule parser.

ECB RSS is first-party and high-trust for European Central Bank press releases.
It is relevant to EUR, USD, global rates, equities, and crypto through FX and
global liquidity channels. The classifier marks ECB items as `international`
unless stronger monetary-policy terms dominate in a later version.

BIS RSS is first-party and high-trust for Bank for International Settlements
publications and press releases. BIS material often has slower market impact
than FOMC or payrolls, but it is valuable for systemic risk, Basel, global
liquidity, and crypto prudential framing. Treat it as strategic context unless
paired with near-term policy or market stress.

Do not add social-media, news-site, analyst, or scraped secondary sources to
this daemon. Those belong in separate confirmation or narrative lanes. Macro
Intel 0.1.0 is intentionally an official-source spine.

## LaunchAgent

The template is at:

```bash
services/macro_intel/launchagent/com.sapphire.macro-intel.plist.template
```

It points at the canonical checkout path:

```text
/Users/aribs/Code/Sapphire/services/macro_intel/run.py
```

The template omits `--live`, so loading it unchanged will run the safe dry-run
loop. To activate official public pulls after local verification, copy the
template to `~/Library/LaunchAgents/com.sapphire.macro-intel.plist`, add
`--live`, and set `SAPPHIRE_MACRO_INTEL_LIVE=1` in the environment dictionary.
Do not add secrets. Do not load or unload the LaunchAgent from an agent script;
ship the plist and let the operator decide when to load it.

Suggested live ProgramArguments after approval:

```xml
<array>
  <string>/usr/bin/python3</string>
  <string>/Users/aribs/Code/Sapphire/services/macro_intel/run.py</string>
  <string>daemon</string>
  <string>--poll-interval-seconds</string>
  <string>900</string>
  <string>--live</string>
</array>
```

Event-bus publishing should be a later step. Add `--publish` only after the
JSONL output has soaked and downstream consumers are ready for
`macro.event.detected` and `macro.calendar.window_opening`.

## Artifacts

Daily events:

```text
data/macro/2026-04-28/events.jsonl
data/macro/2026-04-28/events.jsonl.envelope.json
```

Daily calendar:

```text
data/macro/2026-04-28/calendar.jsonl
data/macro/2026-04-28/calendar.jsonl.envelope.json
```

Cache:

```text
~/.cache/sapphire/macro/fed_rss/
~/.cache/sapphire/macro/fed_fomc/
~/.cache/sapphire/macro/cftc_rss/
~/.cache/sapphire/macro/sec_atom/
~/.cache/sapphire/macro/treasury_auctions/
~/.cache/sapphire/macro/bls_empsit_rss/
~/.cache/sapphire/macro/ecb_rss/
~/.cache/sapphire/macro/bis_rss/
```

Cache folders contain raw payloads, URL metadata, and `counters.json`. The raw
payload cache is an operational aid, not source data to commit. If a local cache
gets corrupted, remove the affected source folder and rerun with live enabled.

## Testing

Run lane tests:

```bash
python3 -m pytest tests/unit/test_macro_sources.py tests/unit/test_macro_classifier.py tests/unit/test_macro_calendar.py -q
python3 -m pytest plugins/claw-sapphire/tests/test_macro_intel.py -q
python3 -m compileall lib/macro services/macro_intel plugins/claw-sapphire/tools/internal/macro_intel.py plugins/claw-sapphire/tools/macro_intel.py
```

Run touched-file lint and registry checks:

```bash
ruff check lib/macro services/macro_intel plugins/claw-sapphire/tools/internal/macro_intel.py plugins/claw-sapphire/tools/macro_intel.py tests/unit/test_macro_sources.py tests/unit/test_macro_classifier.py tests/unit/test_macro_calendar.py plugins/claw-sapphire/tests/test_macro_intel.py
python3 scripts/validate_tool_registry.py
git diff --check
```

Tests use fixtures under `tests/fixtures/macro/`. They must never make live
calls. If a future test needs a new official example, commit a small redacted
fixture rather than reaching out to the source during CI.

## Troubleshooting

If `run-once` returns dry-run, check whether `SAPPHIRE_MACRO_INTEL_LIVE=1` is
set and whether the CLI included `--live`. Both the service and plugin are
intentionally conservative.

If HTML sources fail with a robots error, inspect the source's robots.txt and
do not bypass it casually. The correct response is to document the block, rely
on existing cache if available, or remove the source from live polling until an
allowed official feed or API is available.

If SEC requests are rejected, update `SAPPHIRE_MACRO_USER_AGENT` to a more
specific contact string. SEC systems expect descriptive user agents. Do not use
generic browser spoofing.

If the event bus does not receive events, confirm both gates:

```bash
echo "$SAPPHIRE_MACRO_INTEL_LIVE_BUS"
python3 services/macro_intel/run.py run-once --live --publish
```

Publishing is skipped unless the env equals `1` and the CLI asked to publish.
JSONL output should still be written if live pulls succeeded.

If duplicate rows appear, inspect the event ID fields. IDs are derived from
source, title, URL, and timestamp. If a source changes URL or timestamp for the
same release, it may create a new ID. Preserve both rows unless a parser bug is
confirmed.

If classification looks wrong, add a fixture-backed unit test first. The
classifier is a deterministic table, so fixes should be explicit keyword or
source-prior changes. Do not patch a one-off by adding opaque scoring.

## Rollback

Code rollback is a normal PR revert. Runtime rollback is to stop using the
LaunchAgent or remove `--live` / `SAPPHIRE_MACRO_INTEL_LIVE=1`. Event-bus
rollback is to remove `--publish` or unset `SAPPHIRE_MACRO_INTEL_LIVE_BUS`.
Cache rollback is source-scoped:

```bash
rm -rf ~/.cache/sapphire/macro/<source>
```

Do not delete `data/macro/` artifacts blindly if downstream consumers may have
read them. Quarantine or archive them with a timestamp if cleanup is needed.

## Release Checklist

Before enabling live mode in the canonical checkout:

1. Run the lane unit and plugin tests.
2. Run touched-file Ruff, registry validation, and `git diff --check`.
3. Run `python3 services/macro_intel/run.py run-once` and confirm dry-run.
4. Run a single live pull with `SAPPHIRE_MACRO_INTEL_LIVE=1` and inspect JSONL
   output for source URLs and sane classifications.
5. Leave bus publishing off for the first soak.
6. Confirm `~/.cache/sapphire/macro/<source>/counters.json` increments and does
   not exceed four pulls per hour.
7. Only then consider installing the LaunchAgent template.

Macro Intel should make Sapphire more aware, not more aggressive. The daemon's
job is to provide official context with provenance and restraint.
