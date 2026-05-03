# MegaETH Price Source Status (2026-05-02)

## TL;DR

**Chainlink Data Feeds are NOT deployed on MegaETH** (mainnet or testnet) as of
2026-05-02. The Lane BTC-arb pattern from PR #570 (Chainlink fallback for GMX
markets without Aave overlap) cannot be backported to MegaETH today.

**Pyth Network IS deployed on MegaETH mainnet** (chain ID 4326,
`https://mainnet.megaeth.com/rpc`) at the canonical EVM address
`0x2880aB155794e7179c9eE2e38200202908C17B43`. Pyth is the recommended
alternative oracle path for MegaETH GMX BTC pricing.

## Verification

Probed via `eth_getCode` on 2026-05-02:

| Endpoint | Chain ID | Pyth `0x2880...7B43` | Chainlink BTC/USD `0xf403...e88c` |
|---|---|---|---|
| `https://mainnet.megaeth.com/rpc` | 0x10e6 (4326) | 356-char bytecode (deployed) | `0x` (empty) |
| `https://carrot.megaeth.com/rpc`  | 0x18c7 (6343, testnet) | `0x` (empty) | `0x` (empty) |

Other Chainlink mainnet/L2 aggregator addresses also probed on the MegaETH
mainnet RPC and returned empty bytecode (ETH/USD ETH-mainnet, ETH/USD
Arbitrum, BTC/USD Arbitrum). Chainlink's own
[CCIP testnet directory page for MegaETH](https://docs.chain.link/ccip/directory/testnet/chain/megaeth-testnet)
documents only CCIP infrastructure (router, RMN, token admin registry); no
price-feed (AggregatorV3) addresses are listed.
[Chainlink's Data Feeds address index](https://docs.chain.link/data-feeds/price-feeds/addresses)
does not list MegaETH at all.

## Why this matters

The MegaETH GMX integration in `lib/chains/megaeth/contracts/gmx_price_adapter.py`
currently prices ETH/USDC via Aave V3, leaving every other market unpriced —
the same Lane I problem that PR #570 solved for Arbitrum. The single BTC
funding number we have for MegaETH (-75% APR, referenced in some hackathon
artifacts) was hardcoded from a wrapper test, not queried live. Without an
on-chain price source for BTC on MegaETH there is no real-time path to fix
that today.

## Recommended path: Pyth Network fallback

Pyth ships a single contract (`IPyth`) that exposes per-feed-id reads via
`getPriceUnsafe(bytes32)` / `getPriceNoOlderThan(bytes32, uint)`. The feed
ids are deterministic (BTC/USD = `0xe62df6c8...43e6f2a3a3a4f4af4`) and the
same across every chain Pyth supports. Mirroring the PR #570 structure:

- `lib/chains/megaeth/contracts/pyth_oracle.py` — `PythAggregator` +
  `PythRegistry` typed wrappers around the `IPyth` ABI; canonical MegaETH
  contract baked in (`0x2880aB155794e7179c9eE2e38200202908C17B43`); same
  wrapped→underlying symbol resolution map; `verify_addresses()` via
  `eth_getCode`.
- `lib/chains/megaeth/abis/pyth/pyth.json` — pinned `IPyth` ABI
  (subset: `getPriceUnsafe`, `getPriceNoOlderThan`, `getValidTimePeriod`).
- `lib/chains/megaeth/contracts/gmx_price_adapter.py` — extend with
  `pyth: PythRegistry | None` constructor arg; `TokenPrice` gains `source`
  ("aave"|"pyth") and `stale` fields; `fetch_token_price()` tries Aave then
  falls back to Pyth before raising.
- Tests: ≥6 unit tests with recorded fixtures + 1 gated integration test
  asserting `perps_market_info(BTC_market)` returns a non-zero price.

This is structurally identical to PR #570's Chainlink work; only the wrapper
contract surface differs.

## Revisit when Chainlink ships MegaETH

If/when Chainlink deploys `AggregatorV3Interface` price feeds to MegaETH
mainnet (currently they only have CCIP on testnet — see
[`docs.chain.link/ccip/directory/testnet/chain/megaeth-testnet`](https://docs.chain.link/ccip/directory/testnet/chain/megaeth-testnet)),
the PR #570 pattern can be ported almost verbatim:

1. Drop `lib/chains/megaeth/contracts/chainlink_oracle.py` mirroring
   `lib/chains/arbitrum/contracts/chainlink_oracle.py`.
2. Drop `lib/chains/megaeth/abis/chainlink/aggregator_v3.json`.
3. Add the new MegaETH feed addresses to a `MEGAETH_FEEDS` dict.
4. Wire `chainlink: ChainlinkRegistry | None` into the existing
   `GmxPriceAdapter` (or chain Chainlink → Pyth as tertiary if Pyth lands first).

A periodic check of the Chainlink Data Feeds index for MegaETH every ~quarter
is sufficient — the integration work itself is mechanical once the feed
addresses are published.

## References

- PR #570 (Arbitrum Chainlink fallback we are mirroring): `feat/arbitrum-gmx-chainlink-fallback`
- Chainlink Data Feeds index (no MegaETH entry): https://docs.chain.link/data-feeds/price-feeds/addresses
- Chainlink CCIP testnet MegaETH directory: https://docs.chain.link/ccip/directory/testnet/chain/megaeth-testnet
- Pyth Network EVM contract addresses (MegaETH listed): https://docs.pyth.network/price-feeds/contract-addresses/evm
- MegaETH mainnet RPC: https://mainnet.megaeth.com/rpc (chain ID 4326)
- MegaETH testnet RPC: https://carrot.megaeth.com/rpc (chain ID 6343)
