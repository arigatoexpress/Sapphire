# SEC Filings + Earnings Call Intelligence — Operator Runbook

**Module status:** internal · **Lane:** Tranche-6 Lane 7 · **Updated:** 2026-04-29

This runbook covers operating the SEC EDGAR + earnings-call adapters in day-
to-day Sapphire operations. It is written for the **operator** (Ari or any
delegated human in the loop), not for end users. The product overview lives
in `docs/products/sec-and-earnings-intelligence-0.1.0.md`.

## TL;DR

```bash
# Dry-run (default): adapter reads cache, never hits network.
echo $SAPPHIRE_SEC_LIVE         # should be empty
echo $SAPPHIRE_EARNINGS_LIVE    # should be empty

# Curate tickers
cp infra/sec_tickers.example.yaml ~/.sapphire/sec_tickers.yaml
$EDITOR ~/.sapphire/sec_tickers.yaml         # add 1-5 tickers

# Curate IR feeds (optional)
mkdir -p ~/.sapphire
$EDITOR ~/.sapphire/earnings_rss.yaml         # add operator-trusted feeds

# Configure SEC's required UA (REQUIRED before going live)
export SAPPHIRE_SEC_UA_NAME="YourFirmName"
export SAPPHIRE_SEC_UA_EMAIL="ops@yourdomain.example"

# Flip live (independently)
export SAPPHIRE_SEC_LIVE=1                   # SEC live; UA must be set
export SAPPHIRE_EARNINGS_LIVE=1              # earnings-RSS live

# Inspect cache
ls ~/.cache/sapphire/sec_edgar/
ls ~/.cache/sapphire/earnings_calls/
```

## 1. Files this module owns

| Path | What it is |
|---|---|
| `lib/sources/sec_edgar.py` | SEC EDGAR HTTP adapter + rate limiter |
| `lib/sources/sec_classifier.py` | Pure deterministic 8-K item / form classifier |
| `lib/sources/earnings_calls.py` | IR-RSS + transcript-fixture earnings adapter |
| `lib/correlator/sources.py` | Adds SEC + earnings to `available_sources()` |
| `infra/sec_tickers.example.yaml` | Operator template (ZERO real tickers) |
| `~/.sapphire/sec_tickers.yaml` | Operator runtime config (live source of truth) |
| `~/.sapphire/earnings_rss.yaml` | Operator IR-feed config |
| `~/.cache/sapphire/sec_edgar/filings.json` | Filings cache (1h TTL) |
| `~/.cache/sapphire/sec_edgar/ticker_map.json` | Ticker→CIK cache (24h TTL) |
| `~/.cache/sapphire/earnings_calls/latest.json` | Earnings cache (1h TTL) |
| `~/.cache/sapphire/earnings_calls/<TICKER>/*.{json,txt}` | Operator transcript fixtures |

## 2. Adding a ticker to the SEC watchlist

Step 1 — copy the example to the runtime path:

```bash
cp ~/Code/Sapphire/infra/sec_tickers.example.yaml ~/.sapphire/sec_tickers.yaml
```

Step 2 — open and edit. Add up to **5 tickers** (the lane spec hard-caps
this; the adapter clamps higher operator overrides automatically):

```yaml
tickers:
  - AAPL
  - NVDA
  - TSLA
# max_per_pull: 5     # uncomment if you want a smaller cap (e.g. 3)
```

Step 3 — verify the dry-run pickup. From the repo root:

```bash
/usr/local/bin/python3 - <<'PY'
from lib.sources import SECEdgarSource
from lib.sources.sec_edgar import load_tickers_config, DEFAULT_TICKERS_CONFIG
print("loaded:", load_tickers_config(DEFAULT_TICKERS_CONFIG))
src = SECEdgarSource()
print("dry-run events:", len(src.list_events()))
PY
```

If `loaded:` shows your tickers and dry-run events show what's in your
existing cache (likely 0 the first time), you're set.

## 3. Going live (SEC EDGAR)

**Pre-flight checklist** (do not skip — SEC will eventually rate-limit
non-compliant callers):

- [ ] `SAPPHIRE_SEC_UA_NAME` is set to a real firm name.
- [ ] `SAPPHIRE_SEC_UA_EMAIL` is a contact you actively monitor.
- [ ] `~/.sapphire/sec_tickers.yaml` lists the tickers you intend to
      track (1–5).
- [ ] You have read SEC's "Accessing EDGAR Data" page at
      <https://www.sec.gov/os/accessing-edgar-data> within the past 6
      months. SEC adjusts policies; stay current.

Then:

```bash
export SAPPHIRE_SEC_LIVE=1
```

The next call to `SECEdgarSource.list_events()` (or any consumer that
calls `latest_for(...)` for an SEC-tracked ticker) will pull live. Cache
is 1h, so you will see network activity at most once an hour per ticker.

**Verifying the User-Agent** is what you think it is:

```bash
/usr/local/bin/python3 - <<'PY'
from lib.sources.sec_edgar import _user_agent
print(_user_agent())
PY
```

You should see `YourFirmName/0.1 (ops@yourdomain.example)` (or the override
you passed to the source via `user_agent_override`). If it falls back to
the lib default, **stop** and fix the env vars before continuing.

## 4. Going live (earnings calls)

Step 1 — write `~/.sapphire/earnings_rss.yaml`:

```yaml
feeds:
  - ticker: AAPL
    rss_url: https://investor.apple.com/rss-news
  - ticker: NVDA
    rss_url: https://investor.nvidia.com/rss
  # add operator-trusted feeds; do NOT add anything that scrapes a paywalled
  # site. We only consume RSS that the company itself publishes.
```

Step 2 — flip the gate:

```bash
export SAPPHIRE_EARNINGS_LIVE=1
```

Step 3 — verify:

```bash
/usr/local/bin/python3 - <<'PY'
from lib.sources import EarningsCallSource
src = EarningsCallSource()
print(len(src.list_sentiments()))
PY
```

## 5. Reading the caches

### SEC filings cache

```bash
jq '.filings | keys' ~/.cache/sapphire/sec_edgar/filings.json
jq '.filings.AAPL[:3]' ~/.cache/sapphire/sec_edgar/filings.json
```

Sample shape:

```json
{
  "retrieved_at": "2026-04-29T01:00:00+00:00",
  "rate_limit_req_per_sec": 10,
  "filings": {
    "AAPL": [
      {
        "form": "8-K",
        "accession": "0000320193-26-000001",
        "filed": "2026-04-28",
        "report_date": "2026-04-28",
        "items": "1.01,2.02",
        "primary_document": "aapl-20260428.htm"
      }
    ]
  }
}
```

### Ticker→CIK map cache

```bash
jq '.map | length' ~/.cache/sapphire/sec_edgar/ticker_map.json
jq '.map.AAPL' ~/.cache/sapphire/sec_edgar/ticker_map.json
```

The map is refreshed at most every 24h. If you add a tiny-cap ticker that
SEC's official ticker map doesn't know about, the adapter will silently
skip that ticker (no error, no signal) — confirm via the cache before
debugging further.

### Earnings cache

```bash
jq '.entries | keys' ~/.cache/sapphire/earnings_calls/latest.json
jq '.entries.AAPL[0]' ~/.cache/sapphire/earnings_calls/latest.json
```

## 6. When SEC rate-limits you

Symptoms: `urllib.error.HTTPError: 403 Forbidden` from
`http_get_json` calls under `lib/sources/sec_edgar.py`. Possible causes:

1. **UA missing or generic.** Set `SAPPHIRE_SEC_UA_NAME` and
   `SAPPHIRE_SEC_UA_EMAIL`, then restart the calling process.
2. **Burst over 10 req/sec.** Should not happen — the adapter throttles
   automatically. If it does, check that you haven't constructed
   multiple `SECEdgarSource` instances in parallel without a shared
   `RateLimiter`. Pass a single `RateLimiter()` instance into all of
   them.
3. **You're on a shared NAT.** A coworker on the same egress IP is also
   hammering EDGAR. Coordinate, or move to a dedicated egress.

Fix order:
1. Confirm UA in `_user_agent()` looks right.
2. `rm ~/.cache/sapphire/sec_edgar/filings.json` and let the next pull
   use the rate-limited path.
3. Wait 60 minutes if SEC has dropped you onto a backoff list. They do
   not publish their backoff durations.

## 7. When earnings RSS feeds break

Symptoms: an IR feed returns invalid XML or 4xx. The adapter swallows
errors silently (per the source-error-tolerant design — adapters never
raise from `latest_for`). To diagnose:

```bash
curl -sH "User-Agent: SapphireOps/0.1" https://investor.example.com/rss | head -40
```

If the feed is genuinely down, remove it from `~/.sapphire/earnings_rss.yaml`
or comment it out. The adapter handles a missing feed gracefully (just no
signal for that ticker until it returns).

## 8. Cache invalidation / forced refresh

You should rarely need to do this. The cache TTL is intentionally short.
If you need to force a refresh:

```bash
rm ~/.cache/sapphire/sec_edgar/filings.json
rm ~/.cache/sapphire/earnings_calls/latest.json
```

The next call with `SAPPHIRE_SEC_LIVE=1` (or `SAPPHIRE_EARNINGS_LIVE=1`)
will repopulate. The ticker→CIK map at `~/.cache/sapphire/sec_edgar/ticker_map.json`
has its own 24h TTL; remove it separately if SEC adds a new ticker (e.g.
post-IPO).

## 9. Testing locally

```bash
cd ~/Code/Sapphire
/usr/local/bin/python3 -m pytest tests/unit/test_sources_sec_edgar.py \
                                    tests/unit/test_sources_sec_classifier.py \
                                    tests/unit/test_sources_earnings_calls.py \
                                    -q --tb=short
```

Expect ≥ 40 tests, all green. None hit the network.

## 10. SLO / freshness expectations

- SEC filings: published within 4 business days of the underlying event;
  cache TTL 1h; correlator typically sees a filing within ~5h of SEC
  acceptance, dominated by SEC's own publish lag.
- Earnings RSS: typically published within minutes of the press release;
  cache TTL 1h; correlator sees within ~1h end-to-end.
- Ticker→CIK map: 24h TTL is fine for everything except IPO week.

## 11. Common pitfalls

- **Forgetting to set the UA env vars before flipping `SAPPHIRE_SEC_LIVE=1`.**
  The fallback UA still names the project but is not specific to your
  deployment. Set the env vars on the LaunchAgent plist, not just in your
  shell, so background services use them too.
- **Pointing IR-RSS at a paywalled feed.** Don't. The adapter assumes
  the feed is legally redistributable RSS published by the company itself.
  Paywalled syndication via Seeking Alpha / Motley Fool / FactSet is out
  of scope and explicitly NOT to be scraped.
- **Adding > 5 tickers.** The adapter clamps to 5 per pull. If you
  add more, only the first 5 get fetched. To scale higher, run
  multiple operator instances each with a different watchlist (and
  preferably different egress IPs).
- **Stale ticker→CIK map.** If a ticker was renamed (e.g. corporate
  action), the cached map will route requests to the OLD CIK. Rotate
  the map: `rm ~/.cache/sapphire/sec_edgar/ticker_map.json`.

## 12. Provenance

Every produced `SourceSignal` includes provenance:

```python
sig.raw  # {
  # "form": "8-K",
  # "items": "4.01",
  # "accession": "0000320193-26-000003",
  # "summary": "8-K item 4.01: Change in registrant's certifying accountant",
  # "severity": "high",
  # "live_operator_flag": True,
  # "rate_limit_req_per_sec": 10,
  # "max_tickers_per_pull": 5,
  # ...
# }
```

Earnings:

```python
sig.raw  # {
  # "title": "Q2 2026 results — record growth",
  # "source_url": "https://investor.apple.com/rss-news",
  # "source_kind": "rss",
  # "positive_hits": 4,
  # "negative_hits": 0,
  # "live_operator_flag": True,
  # "rate_limit_req_per_sec": 5,
# }
```

Use this to audit signal lineage from a correlator decision back to the
exact filing or RSS item.

## 13. Disabling

If you need to temporarily silence either source from the correlator
output (without removing them from `available_sources()`):

- Empty `~/.sapphire/sec_tickers.yaml`'s `tickers` list — the SEC adapter
  will return an empty events list.
- Empty `~/.sapphire/earnings_rss.yaml`'s `feeds` list — the earnings
  adapter will return no sentiments.

Both adapters short-circuit cleanly when their config is empty.

## 14. Pairing with the correlator

The two new sources slot into Sapphire's existing correlator without any
additional wiring. Verify they show up in the default source list:

```bash
/usr/local/bin/python3 - <<'PY'
from lib.correlator.sources import build_default_sources
print([s.name for s in build_default_sources()])
PY
```

You should see `sec_edgar` and `earnings_calls` near the end of the list,
after the Tranche-3 + Tranche-4 sources (`defillama`, `dune`, `news`,
`labor`, etc.) and before any future Tranche-7 sources.

When the correlator weights file (`~/.sapphire/correlator_weights.yaml`)
is present, you can tune the influence of these sources independently of
the others. Lane 7's defaults intentionally do NOT touch the weights —
operators set them based on observed signal quality once data has
accumulated. A starting point that has worked for early calibration:

```yaml
weights:
  sec_edgar: 0.35
  earnings_calls: 0.25
```

(High-severity 8-K filings carry meaningful weight; sentiment-scored
earnings RSS items carry less because the bag-of-words classifier is
intentionally coarse.)

## 15. Quarter-end load planning

Earnings season produces clustered load (mid-Apr/mid-Jul/mid-Oct/mid-Jan
for US large-cap):

- **SEC EDGAR:** 8-K item 2.02 (results of operations) filings spike
  3-4× during the two weeks following each quarter end. Cache TTL
  remains 1h; you should not see SEC rate limits.
- **Earnings RSS:** IR feeds also spike. The adapter's 5 req/sec ceiling
  is well below any IR-feed rate limit observed in the wild.

If you want the freshest possible signal during earnings season, set
the cache TTL to 30 min (edit `CACHE_TTL_SECONDS` in
`lib/sources/sec_edgar.py`). 1h is fine for steady-state operations.

## 16. Signal lineage from correlator → filing

Given a correlator decision blob, you can trace the exact SEC filing
that contributed. Example:

```python
from lib.correlator.engine import correlate_universe
from lib.correlator.sources import build_default_sources

result = correlate_universe(
    universe=[("AAPL", "1d")],
    sources=build_default_sources(),
)
for symbol_tf, edge in result.items():
    for src in edge.contributing_sources:
        if src.source == "sec_edgar":
            print("SEC filing:", src.raw["form"], src.raw["items"], src.raw["accession"])
            # use the accession to fetch the underlying filing from EDGAR
```

The `accession` is SEC's globally unique filing ID; you can paste it
into <https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany> to
get the human-readable filing. Provenance is preserved end-to-end.

## 17. References

- SEC EDGAR API docs: <https://www.sec.gov/edgar/sec-api-documentation>
  (retrieved 2026-04-29)
- SEC fair-access guidance: <https://www.sec.gov/os/accessing-edgar-data>
  (retrieved 2026-04-29)
- Form 8-K instructions: <https://www.sec.gov/files/form8-k.pdf>
- This module's product doc: `docs/products/sec-and-earnings-intelligence-0.1.0.md`
