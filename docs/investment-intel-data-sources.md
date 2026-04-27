# Investment Intel Data Sources

Sapphire now has a read-only investment intelligence mesh for the solar,
drones, space, AI-energy, and crypto thesis universe. It is designed to deepen
source coverage without enabling trading, Telegram sends, or live data writes.

## Runtime Surface

- Dashboard page: `/investment-intel`
- Report API: `/api/investments/intel`
- Source API: `/api/investments/sources`
- Probe API: `/api/investments/probes`
- Module: `lib.intel.investment_intel`

The APIs return normalized assets, connector coverage, source readiness, ops
queue items, analysis lenses, and research-pack mindset principles.
Add `?live=1` to `/api/investments/intel` to request a read-only CoinGecko
spot/trending preview for the crypto bridge.
Add `?live=1` to `/api/investments/probes` to execute public read-only source
checks. Without that flag, probes return readiness and planned coverage only.

## Research Pack Ingestion

Set `SAPPHIRE_INVESTMENT_RESEARCH_ZIP` to a local research ZIP path. The loader
reads markdown headings, Top 10 table rows, selected mindset principles, and
`*_info.csv` ticker snapshots. It does not copy the ZIP into the repo.

If the env var is absent, the report falls back to
`world_knowledge/research/kimi-p1-sun-drone/convergence_watchlist.json`.

## Source Matrix

| Source | Purpose | Auth | Mode |
|---|---|---:|---|
| SEC EDGAR submissions | Filing history, forms, accession IDs, CIK/ticker metadata | none | read-only |
| SEC XBRL companyfacts | Standardized financial statement facts | none | read-only |
| FRED | Rates, inflation, industrial production, liquidity proxies | `FRED_API_KEY` | read-only |
| EIA v2 | Electricity demand, generation, natural gas, power prices | `EIA_API_KEY` | read-only |
| CoinGecko | Crypto spot, market, trending, metadata | none/public tier | read-only |
| Hyperliquid info endpoint | Perp mark price, funding, open interest, user state | none for public market info | read-only |
| DeFiLlama | TVL, stablecoins, DEX volume, protocol categories | none/public API | read-only |
| Robinhood Crypto | Holdings and best bid/ask through existing reader | local credential presence | read-only |
| TradingView alerts | Research signal ingress and strategy workbench | webhook config | dry-run by default |

Primary documentation:

- SEC EDGAR APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- FRED API: https://fred.stlouisfed.org/docs/api/fred/v2/
- EIA API v2: https://www.eia.gov/opendata/documentation.php
- CoinGecko endpoint overview: https://docs.coingecko.com/reference/endpoint-overview
- Hyperliquid info endpoint: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
- DeFiLlama API docs: https://defillama.com/docs/api

## Safety Posture

- No real trade execution.
- No order endpoints are called by the investment intel module.
- No Telegram sends.
- No Secret Manager or local secret values are returned; Robinhood readiness is
  file-presence only.
- Live-source helper clients are latent infrastructure and raise explicit errors
  when required API keys are absent.

## Dry-Run Materialization

The report includes a materialization preview for five staging tables:

- `investment_assets`
- `investment_source_coverage`
- `investment_ops_queue`
- `investment_crypto_watchlist`
- `investment_research_pack`

Nothing writes by default. To explicitly generate ignored local NDJSON staging
files:

```bash
python3 -m lib.intel.investment_intel \
  --zip "$SAPPHIRE_INVESTMENT_RESEARCH_ZIP" \
  --write-preview data/.gcp_stage/investment_intel
```

This writes under `data/.gcp_stage/investment_intel/raw/<table>/YYYY-MM-DD/*.ndjson`.
It does not call BigQuery, upload to GCS, place trades, or send Telegram
messages.

## Next Materialization Step

The next safe PR can add a scheduler wrapper that invokes the explicit
`--write-preview` command, reviews the NDJSON shape, and only then connects the
ignored staging path to the existing GCS sync flow. Keep raw research packs and
live data artifacts out of git.
