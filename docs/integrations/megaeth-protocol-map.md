# MegaETH mainnet — protocol map and phased programmatic-access plan

**Authored:** 2026-04-30 · **Chain ID:** 4326 (`0x10e6`) · **Status:** mainnet live since 2026-02-09

## Table of contents

1. [Live mainnet protocols (ground-truth map)](#1-live-mainnet-protocols-ground-truth-map)
2. [Protocol categories and Sapphire-relevance](#2-protocol-categories-and-sapphire-relevance)
3. [Access-layer architecture](#3-access-layer-architecture)
4. [ABI fetching and caching strategy](#4-abi-fetching-and-caching-strategy)
5. [Phased build plan (Waves A/B/C)](#5-phased-build-plan)
6. ["AI-optimized chain" honest assessment](#6-ai-optimized-chain-honest-assessment)
7. [Open questions and unknowns](#7-open-questions-and-unknowns)

## Sources & method

- All chain reads done live against [`https://mainnet.megaeth.com/rpc`](https://mainnet.megaeth.com/rpc) on 2026-04-30 (chain_id `eth_chainId` → `0x10e6` = 4326; latest block `eth_blockNumber` ≈ `0xe1dbc9` ≈ 14,801,353; gas price `eth_gasPrice` → `0xf4240` = 1,000,000 wei = 0.001 gwei).
- Protocol enumeration cross-referenced from three independent sources: the Blockscout v2 API at [`megaeth.blockscout.com/api/v2/smart-contracts`](https://megaeth.blockscout.com/api/v2/smart-contracts) (verified contracts feed), the DefiLlama protocol API at [`api.llama.fi/protocols`](https://api.llama.fi/protocols) (filtered by `chains` containing `MegaETH`), and the official MegaETH docs at [`docs.megaeth.com/developer-docs/overview-1/contracts.md`](https://docs.megaeth.com/developer-docs/overview-1/contracts.md).
- Every address in this document was either (a) read from one of those three sources verbatim, or (b) live-checked with `eth_getCode` to confirm bytecode is present at the address. Mainnet TVL totals are from [`api.llama.fi/v2/chains`](https://api.llama.fi/v2/chains) which reports `MegaETH` total TVL at $490,101,654.15 as of fetch.

---

## 1. Live mainnet protocols (ground-truth map)

DefiLlama tracks **26 protocols** with TVL on chain `MegaETH` ([`api.llama.fi/protocols` filtered](https://defillama.com/chain/MegaETH)). The Blockscout verified-contracts feed shows the build is much wider than the DefiLlama tracker — many infra/NFT/gaming dApps don't report TVL but are demonstrably deployed (Aave V3 sub-deployments, GMX V2 130-contract diamond, Silo v2 lending, LayerZero DVN, LiFi escrow, Across V4, Enso Router, Permit2, Uniswap V3 fork canon).

The protocol table below is the **integration target list**. Priority is Sapphire-specific (1=must, 2=should, 3=nice). Categories: DEX-spot, DEX-perps, lending, stable, bridge, yield, oracle, prediction, NFT, gaming.

| # | Protocol | Category | TVL (MegaETH) | Entry point address | Source / ABI | Priority | Sapphire rationale |
|---|---|---|---:|---|---|:---:|---|
| 1 | **Aave V3 (MegaETH)** | lending | $392.4M | `Pool` [`0x7e324AbC5De01d112AfC03a584966ff199741C28`](https://megaeth.blockscout.com/address/0x7e324AbC5De01d112AfC03a584966ff199741C28) · `PoolAddressesProvider` `0x46Dcd5F4600319b02649Fd76B55aA6c1035CA478` · `Oracle` `0x421117D7319E96d831972b3F7e970bbfe29C4F21` | [aave-dao/aave-address-book → AaveV3MegaEth.sol](https://github.com/aave-dao/aave-address-book/blob/main/src/AaveV3MegaEth.sol) (canonical), Blockscout-verified | 1 | 80% of mainnet TVL. Read paths: aMegWETH/aMegUSDm balances on `live_portfolio_daemon`, supply/borrow rates feed `lib/chain/intelligence.py`. Write paths: collateral lifecycle for borrow-against-WETH carry trades. |
| 2 | **Kumbaya** | DEX-spot (Uniswap V3 fork) | $74.8M | `SwapRouter02` `0xE5BbEF8De2DB447a7432A47EBa58924d94eE470e` · `UniversalRouter` `0xAAB1C664CeaD881AfBB58555e6A3a79523D3e4C0` · `V3Factory` `0x68b34591f662508076927803c567Cc8006988a09` · `NonfungiblePositionManager` `0x2b781C57e6358f64864Ff8EC464a03Fdaf9974bA` · `QuoterV2` `0x1F1a8dC7E138C34b503Ca080962aC10B75384a27` | [zgos/Kumbaya-xyz-integrator-kit](https://github.com/zgos/Kumbaya-xyz-integrator-kit), npm `@kumbaya_xyz/smart-order-router`, Blockscout-verified | 1 | Canonical DEX. Quote API for `lib/analytics` regime ingestion; future swap surface for `megaeth_executor`. UniV3 ABIs already mature in Sapphire ecosystem (we can lift from `web3.py` examples). |
| 3 | **World Markets (Spot/Perps/Lend)** | hybrid (single-address) | $12.3M | single contract addr (not yet published) | [docs.world.inc](https://docs.world.inc/venue/technical-overview) — *source closed until liquidity threshold* | 3 | High-conviction interesting design (cross-margin spot+perp+lend in one account) but **no public ABI**. Park until source ships. |
| 4 | **GMX V2 (Synthetics)** | DEX-perps | $8.6M | `ExchangeRouter` `0x73B3593F01CF8e573a412D1d0c972b581794ebE0` · `Reader` `0x0f038EB4a38B08cd3c937a3256b51aa01904a684` · `DataStore` `0xE43C7B694f6b652a9F4A0f275C008d18758Dce35` · `OrderHandler` `0x7d5F99Bab016b831648e278B208579e0eCdb3974` · `EventEmitter` `0xAf2E131d483cedE068e21a9228aD91E623a989C2` | [gmx.io docs/contracts/addresses](https://docs.gmx.io/docs/api/contracts/addresses/), [gmx-io/gmx-synthetics](https://github.com/gmx-io/gmx-synthetics) | 1 | **The only mature on-chain perps surface live on MegaETH today.** Sapphire's Hyperliquid bot pattern (`services/hyperliquid/`) ports here cleanly: read `Reader.getMarkets()` + `EventEmitter` logs for OI/funding, write through `ExchangeRouter`. This is the wave-3 executor target. |
| 5 | **Prism DEX** | DEX-spot | $1.6M | `PrismPredictRelayRouter` `0x0d0D7B77427c45C431C5E2acfa3b566D69E5BCD3` (also `0x0D1881E70Fa3b5815a0adeD11a78750C247bbe02`) | Blockscout-verified | 2 | Second-tier DEX. Useful as a price-divergence check vs Kumbaya. |
| 6 | **Gains Network (gTrade)** | DEX-perps | $0.24M | GNS token `0x551DFe38994eC53c9E7E18084D73893225Eea3bf` (proxy stack `GNSTrading*`, `GNSPairsStorage` `0x01F73b37188F66f335F7Da0290b6742B75adFA03`, `GNSReferrals` `0x23785CE446e4B80d8f48d762EC52cB15A556aDD6`, `GNSFeeTiers` `0x9dfAdbF2FD8dA69A75c664d71Cf2b02fD803f869`) | [gains.trade](https://gains.trade/), Blockscout-verified | 2 | Second perps venue. Lower TVL but same well-known ABI as Polygon/Arbitrum; integration is mostly free if we already wire GMX. |
| 7 | **Avon MegaVault** | yield | $0.22M | per-chain Vault accessible via [`bootstrap.avon.xyz/megavault/4326`](https://bootstrap.avon.xyz/megavault/4326) (deposits USDm, mints USDmY `0x2eA493384F42d7Ea78564F3EF4C86986eAB4a890`) | [avon-docs.gitbook.io](https://avon-docs.gitbook.io/docs/avon/megavault) | 2 | Auto-routes USDm to "safe" venues across MegaETH. Useful as a passive base-yield benchmark; comparing USDmY APY vs. our own USDm-routing alpha is a clean control. |
| 8 | **Silo v2 lending** | lending | (not on DefiLlama yet) | `SiloFactory` `0x95a7bC57c738C7f64103B93D04f49cbCa566afFD` · `SiloRouterV2` `0x30d3E6873118147bA84172490F35DbaB002fA230` · `SiloDeployer` `0x52AD68137612fb974A0f246187F14f7ac5452cC2` · `LeverageRouter` `0x1C7861978D11E9fd13257607d3FCf7bF3478f6EB` · `IdleVaultsFactory` `0xB2886994d8E7d84759b6e08D465094E71BfBad67` | Blockscout-verified | 2 | Isolated-pool lending (different risk model than Aave). Worth tracking for dispersion of carry trades. |
| 9 | **Sectorone DLMM + Vaults** | DEX-spot (DLMM) + LM | $0.21M combined | per [sectorone.xyz](https://sectorone.xyz) — addresses not enumerated on Blockscout's verified feed yet | sectorone.xyz | 3 | DLMM (Meteora-style) is interesting for inventory-management strategies but TVL is small. |
| 10 | **MegaUSD (USDM) stack** | stable (CDP-style) | n/a (token = $360M circulating) | Token `0xFAfDdbb3FC7688494971a79cc65DCa3EF82079E7` · `Minter_v2` `0x2A9bd9829B690Ee36B79f735412E0959F7813534` · `StabilityPool_v2` `0xaa47742C019357c7DD85917A4126676265D12EBE` · `ReservePool_v1` `0xa3287C1A9A777426bC3022d2a94AfDA9561bda3a` · `Genesis_v1` `0x6774745AfC1574Cda36D7cc2D53Df0028480790e` | Blockscout-verified | 1 | **Native MegaETH stable.** Critical: every other protocol on the chain quotes against USDM. Sapphire needs price-feed ingestion + reserve solvency monitoring. |
| 11 | **USDT0** | stable (Tether L2) | n/a (token = $4.06B circulating, 6,409 holders) | `0xB8CE59FC3717ada4C02eaDF9682A9e934F625ebb` | Blockscout-verified ERC20 | 1 | Largest stable on chain. Standard ERC-20; trivial to wire. |
| 12 | **Ethena USDe** | stable (synthetic) | n/a (token = $3.9B circulating) | `0x5d3a1Ff2b6BAb83b63cd9AD0787074081a52ef34` | Blockscout-verified ERC20 | 2 | Synthetic dollar; useful as collateral + carry-trade leg. |
| 13 | **Rabbithole / OP Standard Bridge** | bridge (canonical) | n/a | **L1** `L1StandardBridgeProxy` `0x0CA3A2FBC3D770b578223FBB6b062fa875a2eE75`, `OptimismPortalProxy` `0x7f82f57F0Dd546519324392e408b01fcC7D709e8`, `L1CrossDomainMessengerProxy` `0x6C7198250087B29A8040eC63903Bc130f4831Cc9`, `DisputeGameFactoryProxy` `0x8546840adf796875cd9aacc5b3b048f6b2c9d563`, `SystemConfigProxy` `0x1ED92E1bc9A2735216540EDdD0191144681cb77E` · **L2** `L2CrossDomainMessenger` `0x4200…0007`, `L2StandardBridge` `0x4200…0010`, `L2ToL1MessagePasser` `0x4200…0016`, `OptimismMintableERC20Factory` `0x4200…0012` | [docs.megaeth.com/developer-docs/overview-1/contracts.md](https://docs.megaeth.com/developer-docs/overview-1/contracts.md) | 1 | OP Stack v3.0.0 fork; ABIs are upstream Optimism (already widely indexed). Native ETH bridging without trusted intermediaries. |
| 14 | **LiFi Intent Escrow** | bridge-aggregator | n/a | `LiFiIntentEscrowFacet` `0xbbE097FBEefb423056090d798CCaf77Aa4bc5D85` (Diamond pattern) | Blockscout-verified | 2 | Cross-chain intent settlement. Potential for arb-flow ingestion. |
| 15 | **Across V4** | bridge | n/a | `AcrossV4SwapFacet` `0x19Fee51e721B1337354aeEe875dD303E859AB430` | Blockscout-verified | 3 | Single facet; integration is read-only event-monitoring at this stage. |
| 16 | **LayerZero v2** | infra (messaging) | n/a | `BlockedMessageLib` `0xC1cE56B2099cA68720592583C7984CAb4B6d7E7a`, `DeadDVN` `0x6788f52439ACA6BFF597d3eeC2DC9a44B8FEE842` (canonical endpoints not yet on the verified feed) | Blockscout-verified pieces, [LayerZero docs](https://docs.layerzero.network/) for canonical endpoint list | 3 | Messaging infra. Sapphire likely consumes it transitively (LiFi, Stargate-style flows) rather than directly. |
| 17 | **Enso Router** | execution-router (intent) | n/a | `EnsoRouter` `0xCfBAa9Cfce952Ca4F4069874fF1Df8c05e37a3c7`, `EnsoCCIPReceiver` `0x07f1199ed46ae0314DCD8BF1a02cE21b348c497F`, `EnsoWalletV2` `0xA04df79c7e91f393B64e7BfECbfFA13A9f9F2829` | Blockscout-verified | 3 | Intent-routing primitive; alternative execution path for swaps. |
| 18 | **MegaStaking** | staking (native) | n/a | `MegaStakingProxy` `0x42bfAAA203B8259270A1b5EF4576dB6b8359Daa1` (also `0x2bDb714f9e9a9f867005cFa873832Ae20C4F7B12`) · impl `MegaStaking` `0xa47623Af538AAc8D7F0957AB2889E9cC46E80B3b` | Blockscout-verified | 2 | Likely MEGA token staking. Useful for protocol-level economic intel. |
| 19 | **Beefy** | yield-aggregator | $0.005M | `BeefyVaultConcLiq` `0x718591BF31ac44Be363D4900ea1fA6F355fc58dc`, `BeefyRewardPool` `0xF6f41d1eFF7351D195E112c1A434412cfBeF83c3` | [beefy.com](https://beefy.com), Blockscout-verified | 3 | Tiny TVL on this chain. Listed for completeness only. |
| 20 | **Premarket / Evently / PredictionMarketFactory** | prediction | <$0.001M | `PredictionMarketFactory` `0x2f312fFEF4Acc6B91E036Bc5945da87bf0049d7b` · [premarket.xyz](https://premarket.xyz/) · [evently.market](https://evently.market) | Blockscout-verified | 3 | Negligible TVL; ignore until a market with non-trivial volume appears. |
| 21 | **Chainlink-style aggregator price feeds** | oracle | n/a | `Aggregator_USDE_ETH_megaeth` `0x4cd395CB5edF33b44E73257ee614413f95d1a6cD` · `Aggregator_USDM_BTC_megaeth` `0x3d881b3C7B690f05E672cD0F8fCbC0aE3A7292CF` · `Aggregator_USDM_ETH_megaeth` `0xD011778057AA740BB3703Ad4d78b3c79a1aED1cb` · `Aggregator_BTCb_USD_megaeth` `0x46396230c61776A384c1c00c04A9784c4a2F5d8F` · `Aggregator_sUSDe_ETH_megaeth` `0x023DB4ea6fcE8D4F8Fd9aEd622a81312F8B71De0` · `Aggregator_USDE_BTC_megaeth` `0x97984F3D3cB75A6F6993e76893A2A155B1830bd8` · `MegaEthPriceFeedMegaWithoutRoundsV1` `0x948182FBF36203943F568AE73dA87c7d932Ccf12` · `MegaEthPriceFeedUsdmTwap60WithoutRoundsV2` `0x663B50C9DA9Bd586f855aF13e91EF2f0954c9761` · `EACAggregatorProxy` (Chainlink standard) `0x4F2A91150D5D6B91B5F0b0DF6F109C4BCeCefA61`, `0x556ccb034718065067A3d323DDe0B0A27637f5ba`, `0x77243851823F9022962170dAA608de5f3801C0D8`, `0xf6c445343C1d1e7b59968F0E6fEa01E9f5a3b145` · `ChainlinkV3OracleFactory` `0xa1BE84eAf52fC2958789326A464720C1198dB7b1` | Blockscout-verified, ABI is upstream Chainlink `AggregatorV3Interface` | 1 | Oracle layer. Aave/Silo/GMX all depend on these. Sapphire: ingest as primary truth for pair pricing on this chain. |
| 22 | **MEGA token (TGE today)** | infra/token | n/a (token mcap ≈ $194M, $464M 24h volume) | `0x28B7E77f82B25B95953825F1E3eA0E36c1c29861` (10 B fixed supply) | [MegaETH official](https://www.megaeth.com/), Blockscout ERC20 | 1 | TGE 2026-04-30. Critical for Sapphire's protocol-economic ingestion. |
| 23 | **GMContract / ChainGreets gM/gN** | social/onchain-greet | n/a | `GMContract` `0x66de9353a1fa316fE18fB5735898DFEaa6A4d253` · `ChainGreetsGM_Mainnet` `0xb691e7c374490905136b17cd34f1Ea4a3A140635` · `ChainGreetsGN_Mainnet` `0xAC392810e6F92ba8478eccf8a1AbAbfF76fFb6Db` · `MegaTap` `0x0F82D6683eEa46724Bf8F83F23910dE55538ee9A` · `AutoGMContract` `0x7Ca66Bcfc943b79C44ef47ce091A61B04e0EEC93` | Blockscout-verified | 3 | Activity-farming primitives. Useful only as a noise-vs-signal filter when sampling block content. |
| 24 | **Casino games** (FerdyFlip etc.) | luck-games | <$0.01M | `Plinko` `0x062355a2f867724C96F6c1CEf08ea03E74B80f49`, `Slots` `0x03C5433E91AdDEcf3cD9B9167d598f882A05e46f`, `Slide` `0x9F40194914a3116C095B7304c859dA0359d4e3B6`, `RockPaperScissors` `0xB9e036F8d3129179c9eb15615F7a711c4f1Cc413`, `Dice` `0xf9baBEb6e0013e91E669A4872907c19Aa78826Ce`, `Flip` `0xfac05d5F67BD01850378C0C08FB2bC7117045Aa6`, `Keno` `0xfAe58cfD2b2F372229B3610F98BbaE7Cc4c12Ab4`, `HorseRace` `0x11B8f71a3EB3eB6C04B53F7020538a2F501aB6b5`, `PvpFlip` `0xcf9A3e1635D02bc2B6294591607A9B43fcb1B901`, `MegaPlinko` `0xcF0A326702C3fCBb25464d5896195F70f850dc89`, `PokerSession` `0xa5A51F4aBf8c8DeCAe2540CD1eC5C52426b1310A` | Blockscout-verified | 3 | Out of scope. Listed for category-coverage completeness only. |
| 25 | **Hyper7Rush battle/leaderboard** | gaming | n/a | `Hyper7RushFactory` `0xb75891464246BB0C89d642A96843f78c5Cae65Be`, `Hyper7RushVault` `0x8dcB70c0fF687429b5098d03C3c95E3CD740AcD1`, `Hyper7RushPointSBT` `0x095529FDA632B632C03A7A1f1E126F86CC06bb5f`, `Hyper7RushBattle` `0x98d92093eD1dbA58CA71906EAe16eCC046bFa7B9` | Blockscout-verified | 3 | Out of scope. |

**Inactive / announced-but-not-tracked:** Quantus Lend ($489 TVL), Purrlend ($0), Megaswap ($2), WarpX V2/V3, CurrentX V2/V3, Skate AMM, Canonic, Tulpea, SIR ([DefiLlama protocol page](https://defillama.com/protocol/world-markets-spot)). Skip for now; revisit after Wave 1 incentives end (Jun 23) when survivors will be visible.

**Subgraphs / indexers:** Goldsky and SubGraph hosted-service indexers for MegaETH are not yet generally available (per docs.megaeth.com). For Wave A/B we ingest via direct RPC + Blockscout v2 API. Treat indexer adapter as Wave B placeholder, real implementation deferred until at least one major protocol publishes a subgraph URL.


---

## 2. Protocol categories and Sapphire-relevance

For each category present on chain 4326 today: what Sapphire would do with it, and which existing surface in the monorepo (CLAUDE.md anchored) it composes with.

### 2.1 Lending — Aave V3, Silo v2

- **Read-only ingestion**: `Pool.getReserveData(asset)` → liquidity rate, variable borrow rate, utilization. `UI_POOL_DATA_PROVIDER` (`0x1aB55bBdD5DF0782BBCf73553Af93BC6B29A286B`) returns full reserve list in one call. Stream `Supply` / `Withdraw` / `Borrow` / `Repay` events through the existing `services/megaeth-ingest` WSS subscriber (PR #530) — events get enriched and forwarded to signal-logger.
- **Sapphire surfaces**:
  - `lib/chain/intelligence.py` already aggregates supply/borrow rates for other chains; add a MegaETH provider that mirrors `lib/chain/coinmetrics.py` shape.
  - `services/live_portfolio_daemon/` reads aMegWETH/aMegUSDm balances for any wallet we hold positions in.
  - `lib/analytics/strategy_lab.py` consumes the rate spread between Aave V3 and Silo for a borrow-rate-arbitrage strategy candidate.
- **Execution (Wave C only)**: supply WETH, borrow USDM, deposit USDM into Avon MegaVault for carry — fully wired through `lib/trading/megaeth_executor.py` once `signing_verified=True`.

### 2.2 DEX-spot — Kumbaya (UniV3 fork), Prism, Sectorone DLMM

- **Read-only**: `QuoterV2.quoteExactInputSingle(QuoteExactInputSingleParams)` for price discovery. Pool sync events (`Swap`, `Mint`, `Burn`) for liquidity-flow tracking. The UniV3 ABI is already mature in the wider Web3 ecosystem; we lift a pinned version into `lib/chains/megaeth/abis/kumbaya/`.
- **Sapphire surfaces**:
  - `lib/analytics/correlator.py` — cross-DEX price divergence (Kumbaya vs Prism vs CEX) feeds the existing `correlation.broken` event-bus topic.
  - `lib/trading/strategy_lab.py` — Kumbaya/USDT0 vs Kumbaya/USDM vs USDT0/USDM triangle as a stable-arb candidate.
  - `services/dashboard/` — `/api/megaeth/quote?in=USDT0&out=WETH&amount=1000` panel for at-a-glance routing.
- **Execution (Wave C)**: `SwapRouter02.exactInputSingle` for atomic swaps; `UniversalRouter` for batched/permitted flows.

### 2.3 DEX-perps — GMX V2, Gains Network

- **Read-only**: GMX `Reader.getMarkets(DataStore, start, end)` enumerates listed markets; `Reader.getMarketTokenPrice(...)` for GLV pricing; `EventEmitter` logs (`OrderCreated`, `OrderExecuted`, `PositionIncrease`, `PositionDecrease`) for OI/funding tracking.
- **Sapphire surfaces**:
  - `services/hyperliquid/src/hyperliquid_bot/public_feed.py` is the most directly portable pattern — same job (subscribe, decode, fill `MarketSnapshot`), different chain. Clone its shape into a `services/megaeth-ingest/src/megaeth_ingest/gmx_subscriber.py` (Wave B).
  - `lib/analytics/regime_aware_rsi.py` and the funding-rate strategy class consume GMX funding rates (read from `EventEmitter` `MarketFunding` event) once a feed exists.
  - `lib/trading/megaeth_executor.py` (PR #527 scaffold) — wave-C destination is GMX `ExchangeRouter.createOrder(CreateOrderParams)` with the same fail-closed gate stack as Hyperliquid.
- **Why GMX before Gains**: GMX has 35x the TVL on this chain ($8.6M vs $0.24M) and we already have a parallel-pattern executor.

### 2.4 Stablecoins — USDM (native CDP), USDT0 (Tether), Ethena USDe

- **Read-only**: ERC-20 `totalSupply` time-series from the new `lib/chains/megaeth/contracts/usdm.py` wrapper; CDP solvency checks via `StabilityPool_v2.totalDeposits()` + `ReservePool_v1.collateral()`; PSM peg checks via `Aggregator_USDM_ETH` and `Aggregator_USDM_BTC` oracle feeds.
- **Sapphire surfaces**: `lib/chain/intelligence.py` adds a "stable health" panel mirroring Lido stETH/eETH monitoring. Peg deviation > 30 bps → `chain.regime.shift` event-bus emit.
- **Execution**: USDM mint/redeem through `Minter_v2`; not on the priority list.

### 2.5 Bridges — Rabbithole (canonical OP), LiFi, Across V4

- **Read-only**: L2 system contracts at `0x4200…` are predeploys with stable upstream Optimism ABIs. Watch `MessagePassed` events on `L2ToL1MessagePasser` for outgoing-bridge-flow rate tracking.
- **Sapphire surfaces**:
  - The canonical bridge feeds `lib/intel/market_intelligence.py` (cross-chain capital flow signal — large outflow == bearish chain-economic indicator).
  - `lib/trading/` does **not** auto-bridge. Bridging is a manual operator decision (Wave C, behind a separate `bridge_authorized=False` gate).

### 2.6 Yield — Avon MegaVault, Beefy

- Avon MegaVault is the only yield primitive worth integrating today (Beefy is $5K TVL on this chain). Treat it as a passive-yield benchmark in `lib/analytics/run_strategies.py`: any active strategy must beat USDmY APY net of gas after a 30-day soak, otherwise the position should sit in MegaVault.

### 2.7 Oracles — Chainlink-style aggregators

- Sapphire adds a `lib/chains/megaeth/contracts/oracle.py` wrapper around `EACAggregatorProxy` (standard Chainlink ABI: `latestRoundData()`, `decimals()`, `description()`). Poll cadence: 1s (block time supports it; wave-A target). All other on-chain price reads should pull through this wrapper for staleness checks.

### 2.8 Categories that don't exist on MegaETH yet

- **Native CEX-like orderbook DEX** with public ABI: World Markets is the only candidate, source closed. **Gates `lib/trading/megaeth_executor.py`'s spot-orderbook path indefinitely.**
- **Mature liquid-staking derivative** for ETH/USDM: not present. Compare to Lido / Renzo / EtherFi on L1.
- **Real-money options venue**: not present.
- **On-chain ML primitives**: not present, and per Section 6 should not be expected. MegaETH gives us latency + cost — agents do the ML off-chain.
- **Foundry-style point-of-sale receipt anchors**: out of scope for this map.

---

## 3. Access-layer architecture

Goal: every protocol on chain 4326 reachable from Sapphire through a layered API where higher layers compose without re-knowing addresses or ABIs.

### 3.1 Package layout

```
lib/chains/megaeth/
  __init__.py                # re-exports MegaETHClient (PR #529), registry, protocols facade
  registry.py                # protocol metadata: addresses, categories, ABI paths, chain-id pin
  abis/                      # ABI JSONs, version-pinned
    fetcher.py               # Blockscout v2 fetch + cache-on-disk
    aave_v3/                 # one dir per protocol family
      Pool.json
      Oracle.json
      ...
    kumbaya/
      SwapRouter02.json
      QuoterV2.json
      UniswapV3Pool.json
      ...
    gmx/
      ExchangeRouter.json
      Reader.json
      DataStore.json
      EventEmitter.json
    usdm/
      Minter_v2.json
      StabilityPool_v2.json
    bridge/                  # OP Stack predeploys + L1
      L2ToL1MessagePasser.json
      OptimismPortal.json
    oracle/
      EACAggregatorProxy.json   # standard Chainlink ABI shared across feeds
  contracts/                 # typed wrappers — one module per protocol
    __init__.py
    aave_v3.py               # AaveV3Pool, AaveOracle wrappers
    kumbaya.py               # KumbayaQuoter, KumbayaRouter
    gmx_v2.py                # GmxReader, GmxExchangeRouter, GmxEventStream
    usdm.py                  # UsdmReader (totalSupply, peg, reserve health)
    rabbithole_bridge.py     # bridge in/out helpers
    oracle.py                # ChainlinkAggregator (shared)
  protocols.py               # intent-level facade — see 3.3
  indexer.py                 # subgraph adapter (placeholder until subgraphs ship)

plugins/claw-sapphire/tools/megaeth_protocols.py        # agent shim (Wave B)
plugins/claw-sapphire/tools/internal/megaeth_protocols.py  # real impl
```

### 3.2 Module responsibilities

**`registry.py`**

```python
@dataclass(frozen=True)
class ProtocolEntry:
    name: str
    category: str       # "lending" | "dex_spot" | "dex_perps" | "stable" | "bridge" | "yield" | "oracle"
    addresses: dict[str, str]   # role -> 0x address (e.g. "Pool", "Oracle", "Router")
    abi_paths: dict[str, str]   # role -> "lib/chains/megaeth/abis/<dir>/<name>.json"
    priority: int       # 1..3
    docs_url: str
    notes: str = ""

REGISTRY: dict[str, ProtocolEntry] = { ... }   # keyed by name
```

Mirrors `data/chain/deployments.json` in `lib/chain/robinhood_chain.py:DEPLOYMENTS_FILE`, but typed and CI-validated. CI guard: `scripts/validate_megaeth_registry.py` checks that every `addresses[role]` matches `eth_getCode != 0x` on mainnet RPC and that every `abi_paths[role]` exists on disk.

**`contracts/aave_v3.py`** (representative — same shape for all)

```python
class AaveV3Pool:
    def __init__(self, client: MegaETHClient, address: str | None = None):
        self._client = client                       # PR #529's MegaETHClient
        self._address = address or REGISTRY["aave_v3"].addresses["Pool"]
        self._abi = _load_abi("aave_v3/Pool.json")  # cached, version-pinned

    async def get_reserve_data(self, asset: str) -> ReserveData: ...
    async def stream_supply_events(
        self, *, from_block: int | str = "latest"
    ) -> AsyncIterator[SupplyEvent]: ...
```

Pattern: every wrapper (a) takes the existing PR #529 `MegaETHClient` (no new HTTP layer), (b) loads its ABI via the central fetcher (no inline JSON), (c) exposes both call-style reads and event-stream readers, (d) **never accepts a `private_key` parameter** — writes go through `megaeth_executor` only.

**`protocols.py` — intent-level facade**

```python
async def quote_swap(
    token_in: str, token_out: str, amount_in: int, *,
    venues: tuple[str, ...] = ("kumbaya", "prism"),
) -> list[QuoteResult]:
    """Get best-bid quotes from each enabled venue, ranked by output."""

async def supply_apy(asset: str, *, venues=("aave_v3", "silo")) -> dict[str, float]:
    """Read current supply APY for one asset across enabled lending venues."""

async def stable_health(stable: str = "USDM") -> StableHealthSnapshot:
    """For a stable, return total supply, oracle peg deviation, reserve coverage,
    pool TVL — composed from oracle.py + usdm.py + Aave reserve data."""

async def perp_market_snapshot(
    base: str, quote: str = "USD", venues=("gmx_v2", "gns"),
) -> dict[str, PerpMarket]:
    """Open interest, funding rate, mark, index — one row per venue."""
```

Composition: each intent function fans out across the contracts/ wrappers, returns a dataclass. Caller never sees an address or ABI.

**`indexer.py`** — placeholder. Implements an `Indexer` Protocol with `query_logs(filter)` and `query_state(call)`. Today: backed by direct `eth_getLogs` against the RPC. When a subgraph ships for any major protocol, swap the backend without touching call sites.

### 3.3 How this composes with PRs #527 / #529 / #530

- **PR #529 (`MegaETHClient` / `MegaETHWSClient`)** is the transport layer. Every wrapper above takes a `MegaETHClient` instance — no new HTTP machinery. The read-method allowlist in `_RPC_READ_METHODS` already covers everything we need (`eth_call`, `eth_getLogs`, etc.).
- **PR #530 (`services/megaeth-ingest`)** is the WS subscription service. Its forwarder POSTs enriched events to `signal-logger:18081`. The protocol wrappers' `stream_*_events()` async generators sit downstream — the ingest service does the WSS heavy lifting, the wrappers do typed decoding.
- **PR #527 (`megaeth_executor.py` scaffold)** is the only writer. Wave C wires `protocols.swap()`, `protocols.supply()`, `protocols.create_perp_order()` to call into the executor's `_sign_and_send()` path. **Until then, every public function in `protocols.py` is read-only.** A defense-in-depth assertion in the facade rejects any request with `dry_run=False` while `policy.signing_verified is False`.
- **PR #528 (docs + integration test harness)** — the new `docs/integrations/megaeth-protocol-map.md` (this file) cross-links to `docs/integrations/megaeth.md`. The `tests/integration/megaeth/` harness gains a `test_registry_addresses_have_code` check (gated by `SAPPHIRE_MEGAETH_INTEGRATION=1`) once Wave A registers anything.

