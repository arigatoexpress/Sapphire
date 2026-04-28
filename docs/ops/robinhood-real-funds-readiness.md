# Robinhood Real-Funds Readiness

This runbook is for a capped Robinhood Crypto pilot using Ari's funded $50
cash budget. It is an execution-safety artifact, not investment advice.

## Current Official Surface

- Robinhood publishes a Robinhood Crypto Trading API for US crypto customers:
  <https://docs.robinhood.com/crypto/trading/>
- The support page says the API can read crypto market data, accounts,
  holdings, orders, products, quotes, and can place crypto orders:
  <https://robinhood.com/us/en/support/articles/crypto-api/>
- v2 is the preferred order path because eligible v2 orders can count toward
  fee tiers; v1 order placement does not.
- Authenticated crypto API calls require an API key, Ed25519 signature, and
  timestamp. Sapphire must never log or surface the key, private key, or raw
  signature.
- Crypto account assets are separate from Robinhood Financial stock/ETF/options
  assets. Crypto is not FDIC insured or SIPC protected.

## Stock Trading Position

No official public Robinhood stock or ETF trading API has been identified in
the public docs. Robinhood documents equity order types for app, web classic,
and Robinhood Legend workflows, but Sapphire must not automate stock orders
through private or reverse-engineered endpoints.

Stock automation therefore stays blocked until one of these is true:

- Robinhood publishes an official public equities trading API with a documented
  authentication and order contract.
- Ari explicitly approves a different broker with an official trading API.
- The stock trade is placed manually in Robinhood by Ari.

Reference: <https://robinhood.com/us/en/support/articles/order-types/>

## Sapphire Stage

Sapphire is at `draft_ready_not_submit_ready`.

Allowed now:

- Read Robinhood Crypto account, holdings, orders, and quotes with redacted
  logs.
- Generate v2-shaped order drafts through `/api/trading/order-draft`.
- Use estimated-price and best-bid/ask preflights.
- Paper trade the same strategy and compare fees, spread, and slippage.
- Run `scripts/ops/robinhood_live_readiness.py --live-read-only` to load local
  Robinhood credentials in-process and perform redacted read-only account,
  product, quote, and estimated-price probes.

Blocked now:

- Submitting, canceling, or replacing a Robinhood order.
- Background schedulers submitting any real trade.
- Stock, ETF, or options automation through unofficial Robinhood endpoints.
- Any order larger than the live pilot caps below.
- Printing secret values, raw signatures, or full account identifiers.

## Pilot Caps

- Funded cash budget: `$50`.
- First live crypto order cap: `$5` notional.
- Daily live pilot cap: `$10` notional.
- Preferred first instrument: `BTC-USD` or `ETH-USD`, because high-liquidity
  symbols reduce spread surprises.
- Preferred first order type: limit order, good-til-canceled, with price derived
  from a just-in-time estimated-price preflight.

## Required Gates Before One Real Crypto Order

1. Local tests pass for Robinhood reader, strategy-lab drafts, and dashboard
   dry-run order endpoint.
2. Robinhood API credential presence is confirmed without reading or printing
   secret values.
3. A read-only live account call confirms:
   - account status is `active`;
   - `is_api_tradable` is true;
   - buying power is at least order notional plus estimated fee.
4. A read-only live product/quote call confirms:
   - symbol is tradable;
   - spread is within the configured pilot threshold;
   - estimated fee and price are recorded.
5. The order draft has:
   - v2 endpoint `/api/v2/crypto/trading/orders/`;
   - `account_number` as a query parameter;
   - UUID `client_order_id`;
   - `side`, `type`, `symbol`, and the matching order config;
   - no API signature generated during draft mode.
6. The kill switch is clear immediately before submit.
7. Ari gives an explicit one-order confirmation in the active terminal with:
   symbol, side, order type, limit price, maximum notional, and maximum loss.

## Promotion Sequence

1. Paper-only replay against the same symbol and notional.
2. Live read-only account and quote check.
3. Generate the order draft and review it.
4. Manually confirmed single live limit order capped at `$5`.
5. Immediately monitor order state, fills, fee, spread, and portfolio delta.
6. Stop. Do not loop. Produce a post-trade note before any second order.

## Hard Stop Conditions

- Any API response shape does not match the documented v2 contract.
- Buying power is lower than expected.
- The symbol is not tradable or quote spread is abnormal.
- The order draft requests market execution for the first pilot.
- Any scheduler, webhook, Telegram path, or TradingView path tries to bypass
  the manual confirmation wall.
- Ari has not provided the exact one-order confirmation details.
