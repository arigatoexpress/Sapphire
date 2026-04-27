# Investment Intel Data Sources

Sapphire now has a read-only investment intelligence mesh for the solar,
drones, space, AI-energy, and crypto thesis universe. It is designed to deepen
source coverage without enabling trading, Telegram sends, or live data writes.

## Runtime Surface

- Dashboard page: `/investment-intel`
- Report API: `/api/investments/intel`
- Source API: `/api/investments/sources`
- Module: `lib.intel.investment_intel`

The APIs return normalized assets, connector coverage, source readiness, ops
queue items, analysis lenses, and research-pack mindset principles.
Add `?live=1` to `/api/investments/intel` to request a read-only CoinGecko
spot/trending preview for the crypto bridge.

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

## Next Materialization Step

The next safe PR can add scheduled, dry-run collectors that write normalized
NDJSON to a staging path, then let the existing GCS-to-BigQuery path handle
materialization after review. Keep raw research packs and live data artifacts
out of git.
