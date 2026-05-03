# Data Sources Expansion — 2026-05-03

**Goal**: broaden Sapphire's market view beyond CoinGecko + paper-trading + CISA threat feeds. Below: 15 high-signal sources researched, ranked, with copy-pasteable Python skeletons and a recommended Sapphire landing zone for each.

**Current ingest baseline** (from CLAUDE.md + memory):
- Trading: paper-trading from local signal-logger (Mac, currently silent)
- Threat: CISA KEV + NVD + MITRE ATT&CK + EPSS (FIRST.org)
- Markets: CoinGecko free tier (top-10 crypto)
- Regional: county news scrape
- Wildfire: drone signals (self-generated)
- THO/CRM: Firestore
- Dev: GitHub PRs + github-discovery routine

---

## Top 5 to integrate this week (ranked by impact x ease)

| # | Source | Why this week | Effort |
|---|--------|---------------|--------|
| 1 | **DefiLlama** | Free, no auth, no rate limit, gives TVL across 350+ chains + stablecoin flows + DEX volumes. Best free-tier-to-signal ratio in this entire doc. | 2 hr |
| 2 | **FRED (St. Louis Fed)** | Macro regime is the missing layer in our trading stack. 840K series, free key, 120K req/day. Fed funds + DXY + 10Y + CPI trivially feed prediction engine. | 3 hr |
| 3 | **GDELT 2.0 DOC API** | Free, no auth, 15-min refresh, multi-language news event volume. Geopolitical + macro early-warning that complements county-news scraper. | 4 hr |
| 4 | **NASA FIRMS** | Direct fit for wildfire-watch Phase 0. Free key, 5K req/10min, near-real-time MODIS/VIIRS hotspots globally. Ground-truth for drone signal triage. | 2 hr |
| 5 | **SEC EDGAR data.sec.gov** | Free, no auth, sub-second updates on 10-K/10-Q/8-K. THO + Palantir diligence packets benefit; insider-buy/8-K events are tradeable. | 4 hr |

**"I was surprised by" findings** flagged inline as `[!]`.

---

## CRYPTO DEEP DATA

### 1. DefiLlama (rank: 10/10)
**What it gives us**: TVL by protocol/chain, stablecoin float per issuer per chain, DEX volume, yields, bridges, fees. The single most useful free crypto data API in existence.
**Free tier**: yes — **no auth, no rate limit on the public API**. Pro is $300/mo for higher limits + extras. `[!]` Surprised: zero auth, zero throttling for a service that serves billions of req/mo.
**API**: `https://api.llama.fi/protocols`, `https://api.llama.fi/v2/chains`, `https://stablecoins.llama.fi/stablecoins`, `https://yields.llama.fi/pools`.
**Implementation sketch**:
```python
import requests
r = requests.get("https://api.llama.fi/v2/chains", timeout=10)
chains = r.json()
top10 = sorted(chains, key=lambda c: c.get("tvl", 0), reverse=True)[:10]
for c in top10:
    print(f"{c['name']:<20} TVL=${c['tvl']/1e9:.2f}B  7d={c.get('change_7d', 0):.1f}%")
```
**Where it lands**: new BQ table `sapphire.markets.defillama_tvl_daily` ingested by a new `tools/ingest_defillama.py`; surface on `/dashboard` macro panel + feed prediction engine as a regime feature.
**Time to integrate**: 2 hrs.
**Caveats**: refresh cadence varies per protocol (most ~hourly). Some niche chains lag. No WebSocket — poll on 5-15min cadence.

### 2. CoinGlass funding rates (rank: 5/10)
**What it gives us**: cross-exchange perp funding rates, OI, liquidations, long/short ratios.
**Free tier**: web only. API requires Hobbyist $29/mo (30 rpm) or Startup $79/mo (80 rpm). `[!]` Surprised: no actual free API tier despite popular perception.
**API**: `https://open-api.coinglass.com/public/v2/funding` (paid).
**Implementation sketch**: skip until paid OR scrape funding-rate page on a cron (legal grey).
**Where it lands**: defer — derive funding signal from Bitquery/Hyperliquid/Binance API instead.
**Time to integrate**: N/A (paid).
**Caveats**: cost-benefit is poor when Hyperliquid/Binance public APIs give per-venue funding for free.

### 3. Glassnode (rank: 4/10)
**What it gives us**: 800+ on-chain metrics (SOPR, MVRV, exchange flows, miner reserves) on 1,700 assets.
**Free tier**: very limited — daily resolution, delayed timeframe, most useful endpoints behind Pro paywall. Pro ~$39/mo, API add-on extra. 600 rpm when paid.
**API**: `https://api.glassnode.com/v1/metrics/...` with `?api_key=...`.
**Implementation sketch**:
```python
import requests, os
r = requests.get(
    "https://api.glassnode.com/v1/metrics/market/price_usd_close",
    params={"a":"BTC","api_key":os.environ["GLASSNODE_KEY"]}, timeout=10)
print(r.json()[-3:])
```
**Where it lands**: defer until budget approved; prioritize free DefiLlama + Bitquery first.
**Caveats**: free tier has only ~10 metrics; the valuable derivatives/MVRV/SOPR signals require paid.

---

## STOCKS + ETFs + TRADITIONAL FINANCE

### 4. FRED — Federal Reserve Economic Data (rank: 10/10)
**What it gives us**: 840,000 macro time series — fed funds, DXY, 10Y, CPI, unemployment, M2, financial conditions. The macro substrate every market signal lives on top of.
**Free tier**: yes, free API key, generous quota (~120K req/day historically uncapped per endpoint). `[!]` Surprised: you can pull every released series at ~1s latency for free, indefinitely.
**API**: `https://api.stlouisfed.org/fred/series/observations?series_id=DFF&api_key=...&file_type=json`
**Implementation sketch**:
```python
import requests, os
key = os.environ["FRED_API_KEY"]
for sid in ["DFF","DGS10","DTWEXBGS","CPIAUCSL","VIXCLS"]:
    r = requests.get("https://api.stlouisfed.org/fred/series/observations",
        params={"series_id":sid,"api_key":key,"file_type":"json","limit":1,"sort_order":"desc"}, timeout=10)
    obs = r.json()["observations"][0]
    print(f"{sid:<10} {obs['date']} = {obs['value']}")
```
**Where it lands**: BQ `sapphire.markets.fred_series_daily` + new `lib/macro/fred_loader.py`; surface as `/api/macro-regime` endpoint that prediction engine reads as a 7th factor.
**Time to integrate**: 3 hrs (loader + cron + 1 dashboard panel).
**Caveats**: ALFRED for vintage data is separate. Some series are monthly/quarterly — compute regime features at appropriate cadence. Get key at fredaccount.stlouisfed.org.

### 5. SEC EDGAR (rank: 9/10)
**What it gives us**: every 10-K/10-Q/8-K/13F/Form 4 in real time — sub-second filing latency, sub-minute XBRL latency. Insider buys, earnings, M&A, share buybacks.
**Free tier**: yes — **no auth, no API key, no payment**. Just identify yourself with a User-Agent. `[!]` Surprised: real-time EDGAR is fully free and undocumented as a "killer free API".
**API**: `https://data.sec.gov/submissions/CIK0000320193.json` (Apple) and `https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json`.
**Implementation sketch**:
```python
import requests
HDRS = {"User-Agent":"Sapphire research aristotlespec@gmail.com"}
cik = "0000320193"  # Apple
r = requests.get(f"https://data.sec.gov/submissions/CIK{cik}.json", headers=HDRS, timeout=10)
recent = r.json()["filings"]["recent"]
for i in range(5):
    print(f"{recent['filingDate'][i]}  {recent['form'][i]:<6} {recent['primaryDocument'][i]}")
```
**Where it lands**: new `tools/sec_edgar_watcher.py` polling Form 4 (insider transactions) + 8-K (material events) for a watchlist; pipe to Telegram via hermes; BQ table `sapphire.intel.sec_filings`.
**Time to integrate**: 4 hrs.
**Caveats**: must set descriptive User-Agent or get blocked; max 10 req/sec; XBRL is verbose JSON.

### 6. Polygon.io (rank: 6/10)
**What it gives us**: real-time + historical equities/options/crypto/FX bars, WebSockets, broad coverage.
**Free tier**: 5 rpm, 1-yr historical only, end-of-day data. Real-time = $29/mo Starter, $199/mo for full real-time.
**API**: `https://api.polygon.io/v2/aggs/ticker/AAPL/range/1/day/2026-04-01/2026-05-01?apiKey=...`
**Implementation sketch**:
```python
import requests, os
r = requests.get("https://api.polygon.io/v2/aggs/ticker/SPY/prev",
    params={"apiKey":os.environ["POLYGON_KEY"]}, timeout=10)
print(r.json()["results"][0])
```
**Where it lands**: defer to paid tier when stock automation is unblocked (currently only crypto live per `project_robinhood_live_capital_posture`).
**Caveats**: free tier too restrictive for live signal generation.

### 7. Alpaca Markets (rank: 7/10)
**What it gives us**: brokerage + data API together — minute bars, real-time quotes (IEX feed free, SIP paid), zero-commission paper trading.
**Free tier**: yes — paper trading account is free, market data IEX feed free, 200 rpm.
**API**: `https://data.alpaca.markets/v2/stocks/AAPL/bars?timeframe=1Day&...`
**Implementation sketch**:
```python
import requests, os
hdrs = {"APCA-API-KEY-ID":os.environ["ALPACA_KEY"],"APCA-API-SECRET-KEY":os.environ["ALPACA_SECRET"]}
r = requests.get("https://data.alpaca.markets/v2/stocks/SPY/bars",
    params={"timeframe":"1Day","start":"2026-04-01","limit":10}, headers=hdrs, timeout=10)
print(r.json()["bars"][-3:])
```
**Where it lands**: when stock-side automation goes live, Alpaca paper account becomes the parallel-rail mirror to Robinhood. New `services/alpaca-paper/` micro-service or plugin tool `tools/alpaca_paper.py`.
**Time to integrate**: 4 hrs once we want stock paper-trading.
**Caveats**: IEX-only feed = ~3% of consolidated tape, OK for paper but not arb. SIP feed is $99/mo.

### 8. Tiingo (rank: 6/10)
**What it gives us**: EOD prices, fundamentals, news, IEX intraday. Quality over breadth.
**Free tier**: free, 50 unique symbols/hour, 1000 req/day. Academic pricing available.
**API**: `https://api.tiingo.com/tiingo/daily/AAPL/prices?token=...`
**Where it lands**: backup data source if yfinance keeps getting rate-limited (and it will, see #15).
**Time to integrate**: 2 hrs.
**Caveats**: hourly cap of 50 unique symbols stings for broad scanners.

---

## NEWS / MACRO

### 9. GDELT 2.0 DOC API (rank: 9/10)
**What it gives us**: every news article worldwide indexed every 15 min, in 65 languages, with theme/tone/location tags. Volume timelines + article lists by query. Geopolitical event signals that lead price by hours-to-days.
**Free tier**: **fully free, no auth, no rate limits documented**. Funded by Google Jigsaw. `[!]` Surprised: how undermarketed this is — it's effectively a global news superpower for free.
**API**: `https://api.gdeltproject.org/api/v2/doc/doc?query=...&mode=ArtList&format=json`
**Implementation sketch**:
```python
import requests
r = requests.get("https://api.gdeltproject.org/api/v2/doc/doc",
    params={"query":'("federal reserve" OR "interest rate") sourcelang:eng',
            "mode":"timelinevol","timespan":"1d","format":"json"}, timeout=15)
print(r.json()["timeline"][0]["data"][-5:])
```
**Where it lands**: new `tools/gdelt_pulse.py` running every 15 min for: ("fed", "war", "sanctions", "wildfire", "earthquake", THO-relevant terms). BQ `sapphire.intel.gdelt_volume_15m`. Feed regional-intel-workbench + Telegram alerts on volume z-score spikes.
**Time to integrate**: 4 hrs.
**Caveats**: query syntax is bespoke — read GDELT DOC docs carefully. Article text not included (only URLs + metadata) — fetch separately if needed.

### 10. NewsAPI.org (rank: 4/10)
**What it gives us**: aggregated headlines from 80K sources.
**Free tier**: 100 req/day, **dev only — terms forbid production use on free**. Paid starts $449/mo.
**Where it lands**: skip — GDELT covers this need for free without ToS friction.

### 11. Reuters / AP / CoinDesk RSS (rank: 6/10)
**What it gives us**: vendor-curated low-latency headlines.
**Free tier**: yes — RSS is free and unauthenticated.
**Implementation sketch**:
```python
import feedparser
for url in ["https://www.coindesk.com/arc/outboundfeeds/rss/",
            "https://feeds.reuters.com/reuters/businessNews",
            "https://www.theblock.co/rss.xml"]:
    feed = feedparser.parse(url)
    for entry in feed.entries[:3]:
        print(entry.get("published","?"), "—", entry.title[:80])
```
**Where it lands**: complements GDELT for tier-1 sources. New `tools/rss_pulse.py`.
**Time to integrate**: 1 hr.
**Caveats**: some feeds rate-limit aggressive polling — cache + 5-min cadence is fine.

---

## GEOPOLITICAL + PHYSICAL WORLD

### 12. NASA FIRMS — Fire Information for Resource Management (rank: 9/10)
**What it gives us**: near-real-time global hotspots from MODIS + VIIRS, 3-hr latency globally, real-time over US/Canada. Direct ground truth for wildfire-watch Phase 0.
**Free tier**: yes — `MAP_KEY` granted via web form, 5,000 transactions per 10-min window.
**API**: `https://firms.modaps.eosdis.nasa.gov/api/area/csv/<MAP_KEY>/VIIRS_SNPP_NRT/world/1`
**Implementation sketch**:
```python
import os, csv, io, requests
r = requests.get(
    f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{os.environ['NASA_FIRMS_KEY']}"
    "/VIIRS_SNPP_NRT/-125,32,-114,42/1", timeout=20)  # CA bbox, last 1 day
rows = list(csv.DictReader(io.StringIO(r.text)))
print(f"{len(rows)} hotspots in CA last 24h; sample:", rows[0] if rows else "none")
```
**Where it lands**: `~/Code/wildfire-watch` Phase 0 ingest + Sapphire bridge cross-references with drone signals; BQ `sapphire.physical.firms_hotspots_15min`.
**Time to integrate**: 2 hrs.
**Caveats**: VIIRS confidence levels (l/n/h) — filter for h-only in alerts to cut false positives. EarthData login required for some products beyond NRT.

### 13. USGS Earthquake GeoJSON (rank: 7/10)
**What it gives us**: every quake worldwide, GeoJSON feed, sub-minute publish.
**Free tier**: fully free, no auth.
**API**: `https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson` (also `_day`, `_week`, `2.5_*`, `4.5_*`).
**Implementation sketch**:
```python
import requests
r = requests.get("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson", timeout=10)
for f in r.json()["features"][:5]:
    p = f["properties"]
    print(f"M{p['mag']:.1f} {p['place'][:60]} ({p['time']})")
```
**Where it lands**: tail-risk feed feeding regional-intel-workbench + a new `physical_events` BQ table; Telegram alert on M5+ near port/datacenter clusters.
**Time to integrate**: 1 hr.
**Caveats**: location free-text needs geocoding for clean joins.

### 14. ACLED — Armed Conflict Location & Event Data (rank: 7/10)
**What it gives us**: every political-violence event globally, ~1-week latency, country-level coverage.
**Free tier**: yes, free academic/research registration; CSV bulk + REST API.
**API**: `https://api.acleddata.com/acled/read?key=...&email=...&country=Ukraine&limit=10`
**Implementation sketch**:
```python
import requests, os
r = requests.get("https://api.acleddata.com/acled/read",
    params={"key":os.environ["ACLED_KEY"],"email":"aristotlespec@gmail.com",
            "country":"Ukraine","limit":5,"event_date":"2026-04-25|2026-05-01"}, timeout=15)
print(r.json()["data"][:2])
```
**Where it lands**: regional-intel-workbench + macro-regime input (oil/EM-FX correlation features).
**Time to integrate**: 4 hrs (registration + loader).
**Caveats**: 1-week event lag — not real-time. Stricter ToS on commercial use; aristotlespec@gmail.com registration is fine for research.

---

## THREAT INTEL BEYOND CISA

### 15. AlienVault OTX (rank: 8/10)
**What it gives us**: 19M IOCs/day from 100K+ contributors, pulses (named threat groupings), reputation lookups for IPs/domains/hashes.
**Free tier**: yes — free signup, generous limits, full pulse + indicator API.
**API**: `https://otx.alienvault.com/api/v1/pulses/subscribed?modified_since=...` with `X-OTX-API-KEY` header.
**Implementation sketch**:
```python
import requests, os
r = requests.get("https://otx.alienvault.com/api/v1/pulses/subscribed",
    headers={"X-OTX-API-KEY":os.environ["OTX_KEY"]},
    params={"limit":5}, timeout=15)
for p in r.json().get("results", []):
    print(p["created"], p["name"], "indicators:", p["indicator_count"])
```
**Where it lands**: cyber-threat-bot consumes alongside CISA KEV. BQ `sapphire.threat.otx_pulses`. Cross-ref with NVD CVE feed.
**Time to integrate**: 3 hrs.
**Caveats**: pulse quality varies by author — filter by author reputation / pulse vote count.

### 16. GreyNoise Community API (rank: 7/10)
**What it gives us**: tells you if an IP is internet-background-noise (mass scanner) vs targeted attacker. Cuts SOC alert volume dramatically.
**Free tier**: yes — Community API unlimited per account; v3 endpoint.
**API**: `https://api.greynoise.io/v3/community/<ip>` with `key:` header.
**Implementation sketch**:
```python
import requests, os
ip = "8.8.8.8"
r = requests.get(f"https://api.greynoise.io/v3/community/{ip}",
    headers={"key":os.environ["GREYNOISE_KEY"]}, timeout=10)
print(r.json())
```
**Where it lands**: cyber-threat-bot enrichment layer; tag CISA KEV exploit IPs by GreyNoise classification before alerting.
**Time to integrate**: 2 hrs.
**Caveats**: Community endpoint is single-IP lookup only; bulk requires paid tier. 90-day observation window.

### 17. URLhaus (abuse.ch) (rank: 6/10)
**What it gives us**: malware-distribution URLs, hourly CSV + API. Distinct from PhishTank (which is phishing-only).
**Free tier**: yes, fair-use; Auth-Key free from abuse.ch portal.
**API**: `https://urlhaus-api.abuse.ch/v1/urls/recent/` (POST).
**Implementation sketch**:
```python
import requests, os
r = requests.post("https://urlhaus-api.abuse.ch/v1/urls/recent/",
    headers={"Auth-Key":os.environ["ABUSECH_KEY"]}, timeout=10)
for u in r.json()["urls"][:3]:
    print(u["date_added"], u["url"][:70], "tags:", u.get("tags"))
```
**Where it lands**: cyber-threat-bot blocklist generation; daily BQ snapshot.
**Time to integrate**: 2 hrs.
**Caveats**: Auth-Key now required (changed late 2024). Some payloads are large — paginate.

---

## ON-CHAIN / BLOCKCHAIN

### 18. Etherscan + Arbiscan (rank: 7/10)
**What it gives us**: per-address tx history, ERC-20 transfers, contract source, gas tracker.
**Free tier**: yes — free API key, 5 req/sec, 100K req/day. **Note Nov-2025 change**: free tier now limited to selected chains (~90% of major chains still covered for non-PRO endpoints). Arbiscan needs its own key.
**API**: `https://api.etherscan.io/api?module=account&action=balance&address=0x...&apikey=...`
**Implementation sketch**:
```python
import requests, os
r = requests.get("https://api.etherscan.io/api",
    params={"module":"account","action":"txlist",
            "address":"0xab5801a7d398351b8be11c439e05c5b3259aec9b",  # Vitalik
            "startblock":0,"endblock":99999999,"page":1,"offset":5,"sort":"desc",
            "apikey":os.environ["ETHERSCAN_KEY"]}, timeout=10)
for tx in r.json()["result"]:
    print(tx["timeStamp"], tx["from"][:10], "->", tx["to"][:10], "val=", int(tx["value"])/1e18)
```
**Where it lands**: Hyperliquid live executor (PRs #443-#456) gets a passive on-chain audit trail of its own ops; BQ `sapphire.onchain.eth_txs_watchlist`.
**Time to integrate**: 3 hrs.
**Caveats**: free tier excludes some chains and most "PRO" endpoints (token holders, internal txs by hash). Plan around it.

### 19. Bitquery (rank: 7/10)
**What it gives us**: GraphQL across 40+ chains — DEX trades, token transfers, smart contract events, all queryable in one schema.
**Free tier**: yes — 1,000 API calls/day on free, 10K on $49 tier.
**API**: `https://graphql.bitquery.io/` (POST GraphQL).
**Implementation sketch**:
```python
import requests, os
q = """{ EVM(network: eth) { DEXTrades(limit: {count: 5} orderBy: {descending: Block_Time}) {
  Block { Time } Trade { Buy { Currency { Symbol } Amount } Sell { Currency { Symbol } Amount } } } } }"""
r = requests.post("https://graphql.bitquery.io/",
    json={"query":q}, headers={"X-API-KEY":os.environ["BITQUERY_KEY"]}, timeout=20)
print(r.json()["data"]["EVM"]["DEXTrades"][:2])
```
**Where it lands**: cross-chain DEX volume signal for prediction engine; new BQ table `sapphire.onchain.bitquery_dex_trades_hourly`.
**Time to integrate**: 5 hrs (GraphQL learning curve).
**Caveats**: 1K/day free is tight — cache aggressively. Some queries are expensive per-call.

---

## AI / MODEL MARKET INTELLIGENCE

### 20. HuggingFace Hub API (rank: 6/10)
**What it gives us**: trending models + datasets, downloads, paper links. Leading indicator of AI ecosystem direction.
**Free tier**: yes — public read endpoints unauthenticated; 1K req/hr per IP heuristic.
**API**: `https://huggingface.co/api/models?sort=downloads&direction=-1&limit=20`
**Implementation sketch**:
```python
import requests
r = requests.get("https://huggingface.co/api/models",
    params={"sort":"trending","direction":-1,"limit":10}, timeout=10)
for m in r.json():
    print(f"{m['modelId']:<60} downloads={m.get('downloads',0):>8}  likes={m.get('likes',0)}")
```
**Where it lands**: pairs with existing github-discovery routine; new BQ `sapphire.ai_market.hf_trending_daily`. Feeds Kimi P1 convergence research.
**Time to integrate**: 2 hrs.
**Caveats**: download counts gameable; weight toward likes + recency.

### 21. LMArena (rank: 4/10)
**What it gives us**: blind-vote LLM Elo leaderboard.
**Free tier**: no public documented API as of 2026-05; HuggingFace Space scrape only.
**Where it lands**: defer — scrape weekly via Space if needed; not high-signal enough to prioritize.

---

## SAPPHIRE-SPECIFIC: UNDERUTILIZED GCP

### 22. BigQuery Public Datasets (rank: 8/10)
**What it gives us**: 17+ blockchain datasets (Bitcoin, Ethereum, Solana via 3rd party, Polygon, etc.) updated every 24h, plus GitHub Archive (every push event since 2011), plus weather, plus Google Patents, plus Crux web stats. **You only pay for queries, not storage.** `[!]` Surprised: we have a GCP project (`tho-ai-agent`, `sapphire-479610`) and aren't touching this — it's the highest-leverage integration in this doc since data is already next to compute.
**Free tier**: 1 TB queries/month free per billing account. With partition pruning, that's effectively unlimited for our use cases.
**API**: BigQuery client lib or `bq` CLI.
**Implementation sketch**:
```python
from google.cloud import bigquery
client = bigquery.Client()
sql = """
SELECT DATE(block_timestamp) day, COUNT(*) txs, SUM(value)/1e18 eth_volume
FROM `bigquery-public-data.crypto_ethereum.transactions`
WHERE block_timestamp >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY day ORDER BY day DESC
"""
for row in client.query(sql).result():
    print(row.day, row.txs, f"{row.eth_volume:.0f} ETH")
```
**Where it lands**: replaces several Etherscan/Bitquery polls with single BQ joins; macro features computed in-place. New `lib/bq/public_datasets.py`.
**Time to integrate**: 6 hrs (auth + query optimization).
**Caveats**: cost discipline — partition + cluster filters mandatory or you nuke the 1TB monthly free quota in one query. `bigquery-public-data.crypto_*` are only updated daily.

### 23. Google Trends via SerpAPI / pytrends-modern (rank: 5/10)
**What it gives us**: search-interest-over-time for ticker symbols, "buy bitcoin", THO-relevant local queries.
**Free tier**: pytrends archived 2025-04 (broken when Google shifts internals); SerpAPI ~100 free/mo then $50+/mo. Glimpse + Apify alternatives. `[!]` Surprised: pytrends is dead — every script using it is on borrowed time.
**Where it lands**: low priority unless free fork (`pytrends-modern`) proves stable.
**Caveats**: ToS grey-area for any scraping path.

---

## DEFERRED / NOT WORTH IT

- **NewsAPI** — free tier ToS forbids prod use; GDELT obviates it.
- **CoinGlass API** — paid-only; substitute Hyperliquid + Binance public funding.
- **Glassnode free** — too restrictive; budget for Pro later if convinced by backtest.
- **LMArena API** — none public; defer.
- **Whale Alert** — no real free API; sample data only. Substitute: large-tx watch via Etherscan + Bitquery thresholds.
- **yfinance** — keep as throwaway hobby loader, but it's actively rate-limited in 2026 and pytrends-style breakage is inevitable. Budget Tiingo or Alpaca as the real replacement.

---

## Recommended next steps

1. **This week** — implement #1 DefiLlama, #4 FRED, #9 GDELT, #12 FIRMS, #5 SEC EDGAR (top-5 ranked above).
2. **Land all five in a single new module**: `lib/ingest/` with one file per source, all writing to `sapphire.<domain>.<source>_<cadence>` BQ tables. Use the existing `infra/tool-registry.yaml` shim pattern (top-level compat shim → `tools/internal/<name>.py`).
3. **Wire one shared dashboard panel** (`/dashboard/data-sources`) showing per-source last-fetch timestamp + row count + error budget.
4. **Schedule via existing LaunchAgent + scheduled-tasks pattern**: 15-min cadences (GDELT, FIRMS), hourly (DefiLlama, USGS, EDGAR), daily (FRED, ACLED, OTX, BQ public).
5. **Next week** — add #15 OTX, #18 Etherscan, #20 HuggingFace, #22 BQ Public Datasets.
6. **Budget call** — Glassnode Pro vs CoinGlass Hobbyist: defer until backtest proves either lifts Sortino on existing strategies.

Sources:
- [Glassnode API docs](https://docs.glassnode.com/basic-api/api)
- [DefiLlama API docs](https://api-docs.defillama.com/)
- [CoinGlass API pricing](https://www.coinglass.com/pricing)
- [FRED API docs](https://fred.stlouisfed.org/docs/api/fred/)
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [GDELT DOC 2.0 API blog](https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/)
- [ACLED data access](https://acleddata.com/)
- [NASA FIRMS API](https://firms.modaps.eosdis.nasa.gov/api/)
- [USGS Earthquake feed](https://earthquake.usgs.gov/earthquakes/feed/)
- [AlienVault OTX API](https://otx.alienvault.com/api)
- [GreyNoise Community API](https://docs.greynoise.io/docs/using-the-greynoise-community-api)
- [URLhaus API](https://urlhaus.abuse.ch/api/)
- [Etherscan rate limits](https://docs.etherscan.io/resources/rate-limits)
- [Bitquery pricing](https://bitquery.io/pricing)
- [HuggingFace Hub API](https://huggingface.co/docs/hub/en/api)
- [BigQuery public datasets](https://cloud.google.com/bigquery/public-data)
- [NWS weather API](https://www.weather.gov/documentation/services-web-api)
- [yfinance rate-limit issue](https://github.com/ranaroussi/yfinance/issues/2128)
- [pytrends archived](https://github.com/GeneralMills/pytrends)
