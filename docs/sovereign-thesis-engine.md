# Sovereign Thesis Engine

The Sovereign Thesis Engine converts Ari's cypherpunk/Austrian investment
worldview into a deterministic, falsifiable research matrix. It is not a trading
signal and does not place orders.

## Surfaces

- Config: `config/investment_thesis.yaml`
- Library: `lib/intel/sovereign_thesis.py`
- Dashboard: `/sovereign-thesis`
- API: `/api/investments/thesis`
- CLI: `python3 -m lib.intel.sovereign_thesis --pretty`

## Safety

The engine is read-only by construction:

- no order signing
- no order submission
- no Telegram sends
- no default network fetches
- no writes to `data/`

Every asset carries invalidation triggers so the dashboard can track when a
thesis should be questioned before any strategy work uses it.

## Model

The config defines lenses such as hard money, self custody, censorship
resistance, counterparty minimization, energy abundance, autonomy defense, AI
infrastructure, tokenized finance, jurisdictional resilience, and productive
capital. Assets are scored against those lenses using conviction-adjusted
weights.

The first universe includes Sapphire-liked crypto assets plus the solar, drone,
space, defense, AI, nuclear, grid, and energy names from the Kimi research pack.

## Source Plan

The matrix intentionally separates current thesis conviction from evidence
coverage. Source gaps become ops tasks rather than silent confidence:

- SEC EDGAR for filings, financial statements, and company facts
- FRED and Treasury FiscalData for monetary and debt-cycle context
- EIA for electricity, gas, grid, and energy abundance data
- CoinGecko, Hyperliquid, and DeFiLlama for crypto market, perps, and DeFi data
- Robinhood read-only holdings/venue readiness
- Kimi research pack as a source-pack signal, not a source of truth

## Local Checks

```bash
python3 -m lib.intel.sovereign_thesis --pretty
ruff check lib/intel/sovereign_thesis.py tests/unit/test_sovereign_thesis.py
python3 -m pytest tests/unit/test_sovereign_thesis.py tests/integration/test_dashboard_endpoints.py -q
```
