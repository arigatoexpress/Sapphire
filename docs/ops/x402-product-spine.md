# x402 Product Spine

Date: 2026-05-06

Sapphire now has a small, testable spine for x402-paid information products.
This does not enable live settlement, live trading, Telegram sends, or any
production data mutation. It gives future paid endpoints a shared contract.

## Files

- `config/x402_products.json` - product/SKU catalog for agent-buyable APIs.
- `config/x402_source_registry.json` - source registry with auth, terms, freshness,
  redistribution, and allowed-product notes.
- `lib/payments/x402_products.py` - typed loader, validator, payment-requirement
  builder, and non-secret receipt ledger.
- `infra/gcp/schemas/x402_payment_receipts.json` - future BigQuery receipt table.
- `infra/gcp/schemas/x402_source_registry.json` - future BigQuery source table.

## Current Products

- `research_pack_basic`
- `market_regime_report`
- `backtest_receipt`
- `prediction_market_brief`
- `cyber_exploit_risk`
- `regional_brief`
- `paid_inference_chat`
- `paid_embeddings`

All products currently set `live_settlement_allowed=false` and
`settlement_mode=simulated_or_testnet`.

## Receipt Policy

Receipt records store:

- product id,
- resource,
- amount/network/asset,
- requirement hash,
- payment payload hash,
- payer/tx/nonce when a verifier supplies them,
- artifact id and source ids.

They do not store raw `X-PAYMENT` or `PAYMENT-SIGNATURE` header values.

The default local JSONL ledger path is outside the repo:

`~/.sapphire/x402_payment_receipts.jsonl`

Override with:

```bash
export X402_RECEIPT_LEDGER=/path/to/x402_payment_receipts.jsonl
```

## Next Wiring Step

Wire `market_regime_report` into a simulated endpoint:

1. Load `load_validated_catalogs()`.
2. Build requirements with `product.to_payment_requirements(...)`.
3. Reuse `X402Middleware` for verification.
4. Write a `ReceiptRecord` after payment-required, rejected, or accepted states.
5. Return an artifact id that points to a reproducible report.

Keep Base Sepolia/CDP facilitator work behind explicit env toggles until a
tiny operator-approved settlement test is planned.

## Simulated Market-Regime Endpoint

The first route using the spine is:

`POST /api/x402/market-regime`

Properties:

- requires dashboard Basic Auth first;
- returns product-specific x402 requirements from `market_regime_report`;
- uses `X402Middleware.gate(...)` with catalog-built requirements;
- writes non-secret receipt records for `required`, `rejected`, and `accepted`;
- uses the cache-first cross-asset snapshot path;
- includes local FRED/ALFRED latest-value features from
  `data/macro/<YYYY-MM-DD>/fred_observations.jsonl` when the daily export
  artifact exists;
- does not call live settlement, trading, Telegram, or chain-history writers.

The FRED feature section is intentionally local-artifact-only. Missing
`fred_observations.jsonl` rows produce a warning in the paid report rather than
triggering a live public API call inside the dashboard request path.

## Simulated Backtest Receipt Endpoint

The second paid route using the spine is:

`POST /api/x402/backtest`

Properties:

- requires dashboard Basic Auth first;
- returns product-specific x402 requirements from `backtest_receipt`;
- uses `X402Middleware.gate(...)` with catalog-built requirements;
- writes non-secret receipt records for `required`, `rejected`, and `accepted`;
- reads already-materialized local `data/backtests/strategies/` artifacts;
- returns paper-only assumptions and a reproducibility hash;
- does not run strategies, pull live market data, place orders, or enable live
  settlement.

## Product Discovery Endpoint

Agents can inspect the currently configured paid products at:

`GET /api/x402/products`

Properties:

- requires dashboard Basic Auth;
- does not require an x402 payment;
- returns catalog product metadata, route, pricing, source status, and readiness;
- makes the all-products `live_settlement_allowed=false` posture explicit;
- does not write receipts or mutate any production data.
