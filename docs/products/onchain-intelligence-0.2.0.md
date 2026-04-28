# On-Chain Intelligence 0.2.0

## Executive Summary

On-Chain Intelligence 0.2.0 turns Sapphire's crypto research layer from a thin set of price-adjacent helpers into a read-only, provider-gated on-chain snapshot system. The release joins Glassnode-style holder and profitability metrics, Santiment social and network-growth metrics, Ethereum node health, Solana node health, and a deterministic aggregator into one schema-versioned `OnChainSnapshot`. The output is designed for downstream intelligence, not trading execution: narrative synthesis can cite on-chain regime, event-impact models can compare historical event reactions against current network heat, and the correlator can treat on-chain context as one bounded signal among many.

The most important product decision is restraint. Sapphire does not ask for wallet keys, never signs transactions, never initiates orders, and does not enable live provider calls just because a plugin payload asks for them. Each live path requires an operator-set environment gate plus provider credentials or a read-only RPC URL. Without those gates, every provider returns deterministic fixture data, which keeps tests hermetic and makes local demos honest.

## What Changed In 0.2.0

The provider surface now covers four lanes:

- Glassnode REST metrics for active addresses, transaction rate, SOPR, NUPL, MVRV-Z, HODL-wave style holder-age context, long-term-holder supply, and ETF-adjacent balance proxies derived from available holder/profitability metrics rather than a hard-coded unverified ETF endpoint.
- Santiment GraphQL metrics for social volume, social dominance, age consumed, network growth, developer activity, and exchange open interest.
- Ethereum JSON-RPC reads for chain ID, block number, gas price, latest block hash, and transaction count. The client rejects transaction submission methods.
- Solana JSON-RPC reads for slot, block height, epoch info, latest blockhash, version/supply/performance-ready scaffolding, and transaction count. The client rejects mutating RPC methods such as `sendTransaction` and `requestAirdrop`.

The aggregator joins these sources into a single asset row per BTC, ETH, and SOL by default. Each asset includes provider subdocuments, a composite `onchain_heat_score`, provider gate status, and safety booleans. Node-level snapshots live under `nodes.ethereum` and `nodes.solana` so application layers can inspect chain health without treating it as an asset-level metric.

## Buyer-Facing Value

Institutional crypto intelligence is not only a question of price. Holder profitability, network usage, long-term supply behavior, social attention, exchange exposure, and chain health often explain why price-only signals are fragile. Sapphire 0.2.0 gives a buyer a compact way to see that the system understands those dimensions while remaining safe enough to run in an operator desktop environment.

For an acquisition diligence team, the value is in the bounded architecture:

1. The provider gates are explicit and testable.
2. The aggregator returns one stable schema whether providers are live or fixture-backed.
3. Snapshot writes include provenance sidecars.
4. The plugin can show status or snapshots without enabling live calls.
5. The read-only node providers prove that Sapphire can interact with chain infrastructure without touching wallet material.

This is the layer a larger product could wrap with better data entitlements later. Sapphire does not need to own every provider contract on day one; it needs to demonstrate clean provider boundaries, deterministic fallback behavior, and safe downstream consumption. That is what this release does.

## Provider Gates

Live calls are disabled unless both the provider live gate and the provider credential/RPC value are present:

| Provider | Live gate | Required secret/config |
| --- | --- | --- |
| Glassnode | `SAPPHIRE_GLASSNODE_LIVE=1` | `GLASSNODE_API_KEY` |
| Santiment | `SAPPHIRE_SANTIMENT_LIVE=1` | `SANTIMENT_API_KEY` |
| Ethereum node | `SAPPHIRE_ETH_NODE_LIVE=1` | `ETH_RPC_URL` or `ETHEREUM_RPC_URL` |
| Solana node | `SAPPHIRE_SOL_NODE_LIVE=1` | `SOL_RPC_URL` or `SOLANA_RPC_URL` |

These gates are evaluated inside the provider clients. The service, plugin, and CLI cannot force a provider live by themselves. That separation is deliberate: the operator can safely run the tool from a schedule, dashboard, or agent workflow without worrying that an input JSON field silently turned on paid API usage.

## Caps And Cost Posture

Every live provider call passes through a local usage ledger before the network request is made. Defaults are:

- 60 calls per provider per hour.
- 100,000 calls per provider per day.
- 730 days maximum backfill.

The ledger defaults to `~/.sapphire/onchain_intel/usage.json`. Tests can override it with `SAPPHIRE_ONCHAIN_USAGE_FILE`. The cap is intentionally simple rather than provider-specific billing logic. It is meant to prevent runaway loops, accidental backfills, and agent-driven repeated requests. Provider pricing/free-tier limits still matter; this cap is Sapphire's local safety layer.

## Snapshot Schema

The aggregator returns schema version `0.2.0` with these top-level fields:

- `generated_at`: UTC generation timestamp.
- `assets`: asset keyed records for BTC, ETH, SOL, or an operator-supplied subset.
- `nodes`: Ethereum and Solana node health/context.
- `providers`: gate status, credential presence booleans, cap metadata, and any degraded-provider error.
- `summary`: asset count, live-provider count, mode, wallet/trading safety flags.
- `limits`: configured caps and requested backfill.
- `warnings`: provider degradation notices.
- `wallet_keys_required=false`.
- `trading_enabled=false`.

The `assets.<asset>.composite.onchain_heat_score` is not an alpha signal by itself. It is a normalized operational score summarizing how much on-chain/network/social activity the snapshot sees. Its inputs include active addresses, transaction rate, NUPL, MVRV-Z, social volume, network growth, and developer activity when available. A high heat score says "on-chain context is active enough to matter"; it does not say "buy."

## Downstream Uses

Narrative Synthesis can include a sentence such as: "On-chain regime is accumulation/distribution/euphoria based on Glassnode profitability and Santiment network growth." Cross-asset intelligence can compare chain health against macro and equity correlation regimes. Event-impact modeling can ask whether a regulatory or ETF event happened during elevated on-chain heat. Adversarial defense can flag inconsistent social-volume spikes or node/RPC anomalies as inputs to detector lanes. Observability can show last snapshot time, provider mode, and live-provider count.

The important integration boundary is that downstream lanes consume the snapshot, not provider credentials. That keeps secrets local to provider clients and keeps generated artifacts inspectable.

## Non-Goals

On-Chain Intelligence 0.2.0 is not a wallet, not a trading bot, and not a custody system. It does not import private keys, derive addresses, sign transactions, estimate slippage, route orders, or call broker/exchange execution APIs. The Ethereum and Solana clients expose read-only JSON-RPC methods and reject mutating methods. If a downstream system ever needs execution, it must stay behind Sapphire's existing confirmation firewall, kill-switch invariants, and explicit operator authorization. That is out of scope here.

The release also avoids new top-level production dependencies. It does not require `web3.py`, the Santiment SDK, or a Glassnode SDK. This keeps the dependency footprint small and makes unit tests fast. A future production deployment could add richer provider SDKs if the operator approves the dependency and billing posture.

## Worked Example

A dry-run snapshot for BTC may include Glassnode fixture values such as active addresses around 910,000, SOPR around 1.01, NUPL around 0.48, MVRV-Z around 2.4, and long-term-holder supply around 14.6 million units. Santiment fixture values may include social volume around 4,200, social dominance around 18.4, age consumed around 7.9 million, and network growth around 121,000. The aggregator turns those into a heat score and preserves every provider subdocument. The narrative engine can then say the price thesis is supported, contradicted, or merely contextualized by on-chain heat. It should still include caveats and invalidators because fixture or live provider data can be stale, rate-limited, or unavailable.

## Why This Is Acquisition-Relevant

Buyers do not want a demo that secretly spends money or risks funds. They want proof that a small autonomous intelligence system can handle external data with adult supervision. This lane shows that posture in code: explicit gates, local caps, fixture defaults, read-only node methods, provenance sidecars, and a stable schema. It also broadens the acquisition narrative from "Sapphire can watch prices" to "Sapphire can join market, macro, on-chain, social, and infrastructure state under governed automation."

## Data Quality And Honesty

Provider data should be treated as useful context, not ground truth. Glassnode and Santiment both have plan-dependent coverage, naming changes, and rate limits. RPC providers can lag, throttle, or return incomplete node state. Sapphire's response is to make those uncertainties visible. Each provider row includes `mode`; provider status includes `credential_present`, `gate_enabled`, and `live_enabled`; provider errors degrade the snapshot into `warnings` instead of silently disappearing. When a metric is unavailable, the aggregator should leave the field missing or `null`, not fill it with a guess.

The ETF proxy design follows the same honesty rule. Rather than hard-coding an ETF endpoint whose path may differ by provider plan or API version, Sapphire exposes `etf_balance_proxies` as a derived context block from holder profitability and long-term supply data. That is less flashy than claiming a direct ETF feed, but it is safer and easier to defend in diligence. A future lane can replace the proxy with a verified direct provider endpoint after the operator confirms the exact API contract.

## Versioning And Evolution

The schema is versioned as `0.2.0` because this release expands the prior chain surface without promising finality. Future versions should keep backward-compatible fields when possible and add new provider blocks under explicit names. Likely next steps are: direct Glassnode ETF metrics after contract verification, richer Santiment social-source breakdowns, staking/unstaking queue context for Ethereum, validator health context for Solana, and a dashboard card that shows provider mode plus last snapshot age.

The north star is not "more metrics at any cost." It is a governed intelligence substrate where every added metric has a source, a cap, a fallback, and a downstream consumer. Metrics that cannot meet that bar should stay out of the default snapshot. That is the difference between a compelling acquisition asset and a fragile demo: the product can explain why it collected a metric, how often it is allowed to call the provider, what happens when the provider fails, and which downstream decision the metric informs.
