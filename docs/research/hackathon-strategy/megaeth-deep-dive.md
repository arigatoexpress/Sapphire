# MegaETH developer ecosystem — deep dive for Sapphire

**Authored:** 2026-05-02 · **Branch:** `research/megaeth-deep-dive` · **Status:** research draft
**Scope:** Sapphire is a multi-protocol *read consumer* of MegaETH (Aave V3 + Kumbaya + USDM + GMX V2, chain 4326) with a chain-health gate primitive (`lib/hackathon/chain_health_gate.py`) and a fail-closed executor scaffold. This document maps which MegaETH programs Sapphire qualifies for and which to file first.

---

## Table of contents

1. [Programs available](#1-programs-available)
   1.1 [Wave 1 mainnet incentives (Season 1)](#11-wave-1-mainnet-incentives-season-1)
   1.2 [Mega Mafia 2.0 accelerator](#12-mega-mafia-20-accelerator)
   1.3 [KPI staking / MEGA emissions](#13-kpi-staking--mega-emissions)
   1.4 [Discretionary / `awesome-megaeth-ai` listing](#14-discretionary--awesome-megaeth-ai-listing)
2. [Sapphire-specific opportunities](#2-sapphire-specific-opportunities)
3. [Ecosystem partnerships worth pursuing](#3-ecosystem-partnerships-worth-pursuing)
4. [Past hackathon winners on MegaETH](#4-past-hackathon-winners-on-megaeth)
5. [Calendar of upcoming MegaETH events / deadlines](#5-calendar-of-upcoming-megaeth-events--deadlines)
6. [Sources](#sources)

---

## 1. Programs available

### 1.1 Wave 1 mainnet incentives (Season 1)

- **Window:** 2026-04-28 → 2026-06-23 (8 weeks, weekly cutoff Tuesday 00:00 UTC). [airdrops.io/megaeth](https://airdrops.io/megaeth/)
- **Allocation:** ≥ 5% of $MEGA supply to Fluffle NFT holders + an **additional 2.5% of supply** for "users who participate in mainnet campaigns and interact with ecosystem applications" (i.e. Wave 1). On a 10B fixed supply at TGE-day mcap ≈ $194M ([source](https://www.megaeth.com/token)), 2.5% ≈ $4.85M of MEGA at fully-diluted spot — actual claimable depends on points conversion (formula not yet disclosed).
- **Mechanic:** users connect wallet + X to MegaETH Terminal, acquire USDm, interact with up to **3 featured apps per week** (boosted), pledge to NFT clans for multipliers. Activity tracked weekly, KYC + sanctions screening on claim. ([airdrops.io](https://airdrops.io/megaeth/), [PlayToEarn](https://playtoearn.com/news/megaeth-launches-terminal-points-platform-as-season-1-kicks-off-ahead-of-april-30-mega-tge))
- **App-side qualification:** Wave 1 rewards **users**, not apps directly. Sapphire-the-product cannot claim from Wave 1 by being deployed; only the wallets we operate (or end-user wallets routed through us) earn points by using listed apps. The leverage is *App Wave 2* (opens 2026-04-30, same day as TGE) — a separate **app submission** path at [forms.gle/m6HSvpZ2Q24fB9Cc6](https://forms.gle/m6HSvpZ2Q24fB9Cc6) which is the Mega Mafia application form (see §1.2). There is no separate "list my dApp on Rabbithole" public form found in this research; the same Google Form gates both.
- **Sapphire fit:** Marginal as an *app*. Useful as an *operator* — if Sapphire's `services/megaeth-ingest` Mac wallet routes Aave V3 supply / Kumbaya swaps / GMX trades through the integration, that wallet earns points, and the points are claimable to a treasury address. Worth a 1-day spike to wire wallet activity through Rabbithole-listed protocols before 2026-06-23. EV: low five figures of MEGA, not strategy-defining.

### 1.2 Mega Mafia 2.0 accelerator

- **Cohort 2.0 size:** 15 teams, year-long, in-person offsites required ([blocmates 11-projects writeup](https://www.blocmates.com/articles/11-future-proof-projects-coming-out-of-megamafia-2-0); [The Defiant Mafia coverage](https://thedefiant.io/news/blockchains/seven-day-countdown-to-mega-begins-as-megaeth-clears-first-kpi))
- **Backing:** ABCDE, Anagram, Figment, GSR, Kraken Ventures, Maven11, Robot Ventures, Wintermute + angels Kain Warwick, Santiago Santos, Vitalik Buterin. Mafia 1.0 raised $40M+ across cohort. ([megaeth.com/builder via WebFetch](https://www.megaeth.com/builder))
- **Apply:** [forms.gle/m6HSvpZ2Q24fB9Cc6](https://forms.gle/m6HSvpZ2Q24fB9Cc6). Application open since 2026-04-23; rolling admission; deadline reported variously as 2026-06-01 (original) and 2026-03-15 (extended). Resolve by emailing the form contact before applying.
- **Selection bias (from Mafia 2.0 manifesto, "[The Harder Second Act](https://www.megaeth.com/blog-news/the-harder-second-act)"):** team explicitly **rejects** "Spot DEX, Lending Protocol, Perp DEX, Prediction Market." They want "0-to-1 apps only possible on MegaETH." Cohort 2.0 cherry-picks: Cilium (real-time motion graph for drones/robots), Ubitel (TEE-based decentralized telecom), Hunch (culture-trading prediction markets), Blitzo (gamified payments). The pattern is **consumer/AI/infra novelty** — not generic DeFi clones.
- **What's offered:** weekly workshop, weekly fireside, ad-hoc 1:1 office hours, immersive offsite. Funding *is* available via the backing syndicate but not guaranteed (Mafia 1.0 averaged ~$1.3M per team; Mafia 2.0 reportedly bigger checks, source-undisclosed).

### 1.3 KPI staking / MEGA emissions

- **Allocation:** **53.3% of fixed 10B MEGA supply** is gated to KPI achievement (no time vesting). ([megaeth.com/token](https://www.megaeth.com/token), [Unchained](https://unchainedcrypto.com/megaeths-mega-token-goes-live-on-13-exchanges-at-1-6b-fdv-after-kpi-milestone/))
- **KPI categories:** Reliability, Performance, Adoption, Decentralization. Specific metrics: uptime, block times, finality, gas used, transaction count, **revenue, USDM adoption**, Ethereum alignment, validator safety, fairness. ([megaeth.com/token](https://www.megaeth.com/token))
- **Concrete numeric thresholds publicly disclosed:**
  - **KPI-1 (cleared 2026-04-23):** 10 Mega Mafia apps live + >100k tx + >25k unique wallets in 73 days post-mainnet → triggered TGE 2026-04-30. ([castlelabs research](https://research.castlelabs.io/p/megaeth-and-the-bet-on-consumer-apps))
  - **KPI-2 (open):** USDm circulating supply ≥ **$500M with ≥ 25% deposited in smart contracts**. As of 2026-04-30 USDm = ~$167M (≈33% of target); grew from $62.9M → $300M+ in weeks of incentive launch. ([castlelabs](https://research.castlelabs.io/p/megaeth-and-the-bet-on-consumer-apps), [coincentral](https://coincentral.com/megaeth-activates-mega-token-after-kpi-milestone/))
  - **KPI-3 (open):** ≥ **3 apps generating $50k in daily fees consistently for 30 days**. ([castlelabs](https://research.castlelabs.io/p/megaeth-and-the-bet-on-consumer-apps), [unchained](https://unchainedcrypto.com/megaeths-mega-token-goes-live-on-13-exchanges-at-1-6b-fdv-after-kpi-milestone/))
- **Who collects unlocked MEGA:** **stakers**, not app developers directly. The 53.3% bucket flows to MEGA stakers when KPIs trip; apps benefit indirectly via (a) USDM yield revenue → MEGA buybacks ([yahoo finance reporting](https://finance.yahoo.com/news/megaeth-foundation-usdm-stablecoin-revenue-193413927.html)) and (b) being listed in Rabbithole / Wave 2 to earn user-side incentive flow.
- **Sapphire fit:** As a **read consumer**, Sapphire's Aave V3 / Kumbaya / GMX V2 wrappers do not originate USDm supply or fee revenue, so we do **not** push KPI-2 or KPI-3 forward. We can stake any MEGA we hold in the treasury and collect emissions when KPIs trip — purely passive yield, identical for any holder. There is no app-developer-specific KPI emission carve-out per published docs.

### 1.4 Discretionary / `awesome-megaeth-ai` listing

- **Repo:** [github.com/megaeth-labs/awesome-megaeth-ai](https://github.com/megaeth-labs/awesome-megaeth-ai) — community-maintained "Public repo of AI tooling to help build on MegaETH"
- **Submission criteria** ([CONTRIBUTING.md](https://github.com/megaeth-labs/awesome-megaeth-ai/blob/main/CONTRIBUTING.md)):
  - Active maintenance + docs
  - Clear value to MegaETH developers (chain ID 4326 / 6343)
  - Open source or publicly accessible API
  - Excluded: token promotions, paid ads, incomplete projects, faucet bots
- **Categories that match Sapphire:** General (skills), DeFi (multi-protocol read), Developer Tools, Agents.
- **Existing analog:** [`0xBreadguy/megaeth-ai-developer-skills`](https://github.com/0xBreadguy/megaeth-ai-developer-skills) — a skill pack for Claude Code / OpenClaw / Codex covering real-time APIs, gas modeling, USDm, Kumbaya DEX, x402 payments, ERC-8004 trustless agents. **Sapphire's `lib/chain/megaeth.py` + `plugins/claw-sapphire/tools/megaeth.py` is structurally the same artifact, with broader protocol coverage** (Aave + GMX + chain-health gate) and an executor scaffold the existing skill packs lack.
- **No grant attached** — listing is reputational. But it's the canonical entry point for the Mafia / Foundation team to discover non-cohort builders, and it's PR-mergeable in 1 hour.

---

## 2. Sapphire-specific opportunities

Given Sapphire's posture (read consumer + chain-health gate + planned mainnet integration, *not* a TVL originator), the program fit ranks:

| Program | Fit | Action | EV (rough) |
|---|---|---|---|
| `awesome-megaeth-ai` PR-listing | **High** | 1 PR adding Sapphire's MegaETH skill pack to the Agents + Developer Tools + DeFi categories | Reputational; surfaces to Mafia/Foundation team |
| Mega Mafia 2.0 application | **Medium-high** | File the Google Form positioning Sapphire as **"AI-agent operator across MegaETH multi-protocol surface" + "chain-health gate primitive"** | If admitted: ~$1M+ check from syndicate, year-long mentorship, demo-day visibility. Selection bias is against generic DeFi — angle is Sentinel + agent novelty, not the Aave wrapper. |
| Wave 1 (Season 1) — operator side | **Medium** | Route a Sapphire treasury wallet through Rabbithole-listed protocols (Aave, Kumbaya, USDm, GMX) for 8 weeks; earn points; claim before 2026-06-23 | Low five figures of MEGA, no strategic moat |
| Wave 1 — app-side via App Wave 2 listing | **Low-medium** | Same submission form as Mafia 2.0; non-Mafia apps can be listed in Rabbithole featured apps and absorb user-side points flow | Marginal unless we ship a user-facing surface; Sapphire is primarily an internal trading agent |
| KPI staking | **Passive** | Stake any treasury MEGA, collect emissions on KPI-2 / KPI-3 trips | Identical to any MEGA holder, no app-side carve-out |

### Concrete next actions, in order

1. **`awesome-megaeth-ai` PR (this week).** Self-contained, 1-hour effort. Submit Sapphire to:
   - **DeFi:** `sapphire-megaeth-protocols` — read-only Aave V3 + Kumbaya + USDM + GMX V2 wrapper
   - **Agents:** `sapphire-chain-health-gate` — cross-chain alpha-verification primitive using MegaETH peg + lending health
   - **Developer Tools:** `sapphire-megaeth-sdk` — Python SDK (effectively the only Python wrapper on the chain; existing skill packs are TypeScript/Solidity-leaning)
   - **Evidence to attach in PR description:** link `docs/integrations/megaeth.md`, `docs/integrations/megaeth-protocol-map.md`, `lib/hackathon/chain_health_gate.py`, the 5,995+ test count, and the existing Hyperliquid analog as proof of operational maturity.

2. **Mega Mafia 2.0 form (this week, before 2026-06-01).** The Google Form is the single funnel. Position Sapphire as:
   - "**Real-time AI trading agent** with multi-chain risk kernel — MegaETH is our latency-critical execution layer because the alpha-decay window on our signals is sub-second"
   - Highlight Sentinel's chain-health gate as a *primitive other Mafia teams can compose with* (Cilium for drone trust scoring, Hunch for market-integrity oracles, Benchmark for credit-risk underwrite)
   - Avoid framing as "lending wrapper" or "DEX wrapper" — that gets auto-rejected per the manifesto.

3. **Wave 1 operator wallet (parallel, 1-week sprint).** Spin up a treasury subwallet → `services/megaeth-ingest` writes deposits/swaps to Aave V3 / Kumbaya / GMX over 6 remaining weeks of Season 1 → claim Wave 1 points before 2026-06-23 cutoff. Cap at $5k notional per the existing fail-closed executor gates.

---

## 3. Ecosystem partnerships worth pursuing

### 3.1 Protocol-side (would benefit from Sapphire integration)

| Protocol | Sapphire angle | Channel |
|---|---|---|
| **Aave V3 (MegaETH instance)** | We're the only Python read wrapper for `Pool` + UI Pool Data Provider on chain 4326. Aave Grants DAO has historically funded chain-specific tooling (see [aave-dao/aave-address-book](https://github.com/aave-dao/aave-address-book) maintainers). Pitch a co-marketed "MegaETH Aave health dashboard" feature in Sapphire's `/showcase`. | Aave Governance forum + AGD application |
| **Kumbaya** | Kumbaya already publishes `@kumbaya_xyz/smart-order-router` (TypeScript). A Python quoter wrapper is structurally missing. Co-maintainer offer; their integrator-kit repo accepts PRs. | [github.com/zgos/Kumbaya-xyz-integrator-kit](https://github.com/zgos/Kumbaya-xyz-integrator-kit) |
| **GMX V2** | GMX Synthetics on MegaETH is the only mature on-chain perps surface. Sapphire's Hyperliquid bot pattern (`services/hyperliquid/`) ports here cleanly; a GMX-on-MegaETH community-maintained Python adapter would land in the GMX dev forum. | GMX Telegram, GMX governance forum |
| **MegaETH Foundation** | Chain-health gate (`lib/hackathon/chain_health_gate.py`) is exactly the kind of upstream-mergeable primitive a foundation would want to own — it currently uses MegaETH as the truth source for cross-chain alpha verification. Open an issue against `megaeth-labs/documentation` proposing a "chain-health primitive" doc page; let that surface to the team naturally. | [github.com/megaeth-labs/documentation](https://github.com/megaeth-labs/documentation) |

### 3.2 Cross-chain partnerships (where MegaETH SDK status earns co-marketing)

- **LayerZero V2** — USDm is a LayerZero V2 OFT (token at `0xFAfDdbb…`). Our peg monitor (PR #537) consumes the OFT contract directly; LayerZero's developer relations team historically promotes OFT-aware tooling. ([LayerZero V2 OFT spec](https://docs.layerzero.network/v2/concepts/applications/oft-standard))
- **Alchemy / dRPC** — neither lists MegaETH as a supported chain in their public catalogs as of the integration map (PR #530). Building a public Sapphire-branded MegaETH RPC quality benchmark (we already health-poll) would be co-marketable; either of them adopting MegaETH support would link our benchmark.
- **Chainlink** — MegaETH has Chainlink-style aggregator price feeds live (16+ feeds enumerated in the protocol map). Chainlink's Build program funds aggregator consumers; the chain-health gate is a textbook consumer.

---

## 4. Past hackathon winners on MegaETH

**No dedicated MegaETH-sponsored hackathon track has been identified** in this research across ETHGlobal NYC 2025, Buenos Aires 2025, New Delhi 2025, or upcoming ETHMumbai / ETHTokyo 2026 calendars ([ETHGlobal showcase](https://ethglobal.com/showcase), [ETHMumbai](https://www.ethmumbai.in/), [ETHTokyo'26](https://www.ethtokyo.org/)). MegaETH ran no public hackathon track around mainnet launch (2026-02-09) or TGE (2026-04-30); the ecosystem playbook to date has been **direct accelerator (Mafia)** and **point-based user incentives (Wave 1)**, not bounty-style hackathons.

**Implication for Sapphire:** the MegaETH integration space is **uncrowded**. Existing AI-skill packs in `awesome-megaeth-ai` are single-protocol (one for Kumbaya, one for USDm, one for x402 payments) maintained by individual contributors (`0xBreadguy`, `planetai87`, `n1n4du`). There is no incumbent multi-protocol Python SDK or AI-agent integration on the chain. Sapphire's `lib/chain/megaeth.py` + chain-health gate has clear right-of-first-claim if we publish soon.

If a MegaETH-sponsored ETHGlobal track materializes (likely candidate: ETHTokyo 2026 in September given the chain's Asia-heavy investor base — Robot Ventures, ABCDE, Maven11), being already-listed on `awesome-megaeth-ai` and / or in the Mafia 2.0 cohort would put Sapphire in pole position for prize-track judging.

---

## 5. Calendar of upcoming MegaETH events / deadlines

| Date | Event | Sapphire relevance |
|---|---|---|
| **2026-04-28 → 2026-06-23** | Wave 1 / Season 1 user incentives (8 weeks) | Operator wallet activity earns points; cutoff is hard |
| **2026-04-30** | MEGA TGE; App Wave 2 opens (Rabbithole listing) | App submission via [forms.gle/m6HSvpZ2Q24fB9Cc6](https://forms.gle/m6HSvpZ2Q24fB9Cc6) |
| **2026-06-01 (or 2026-03-15 — verify)** | Mega Mafia 2.0 application closes | File this week to avoid deadline ambiguity |
| **Tuesday 00:00 UTC weekly** | Wave 1 weekly point cutoff | Treasury wallet must hit 3-app threshold each week |
| **Open / undated** | KPI-2 ($500M USDm) trip | Passive — stake MEGA in treasury to collect |
| **Open / undated** | KPI-3 (3 apps × $50k daily fees × 30d) | Passive |
| **2026-09-19 → 2026-09-27** | ETHTokyo 2026 ([ethtokyo.org](https://www.ethtokyo.org/)) | Likely candidate venue for first MegaETH-sponsored track; pre-position via `awesome-megaeth-ai` listing |

**Map against Sapphire roadmap:**
- The `awesome-megaeth-ai` PR + Mafia 2.0 application + Wave 1 operator wallet sprint can all run in parallel inside the next 7 days.
- Mainnet executor activation is gated by the 5-step activation flow in `docs/integrations/megaeth.md` (signing-verified flag, mainnet chain-id constant, operator confirmation, $5 first-rung cap). None of that work is blocked by the MegaETH program calendar — programs run independently.
- The chain-health gate PR (`lib/hackathon/chain_health_gate.py`) should be referenced directly in both the Mafia application and the `awesome-megaeth-ai` PR as proof-of-concept for "MegaETH as cross-chain truth source."

---

## Sources

- [airdrops.io/megaeth — Wave 1 mechanics](https://airdrops.io/megaeth/)
- [megaeth.com/token — token allocation + KPI categories](https://www.megaeth.com/token)
- [megaeth.com/builder — builder programs entry point](https://www.megaeth.com/builder)
- [Mega Mafia application form](https://forms.gle/m6HSvpZ2Q24fB9Cc6)
- ["The Harder Second Act" — Mafia 2.0 selection criteria](https://www.megaeth.com/blog-news/the-harder-second-act)
- [blocmates — 11 Mafia 2.0 projects](https://www.blocmates.com/articles/11-future-proof-projects-coming-out-of-megamafia-2-0)
- [castlelabs — KPI thresholds + USDm progress](https://research.castlelabs.io/p/megaeth-and-the-bet-on-consumer-apps)
- [Unchained — TGE coverage, KPI structure](https://unchainedcrypto.com/megaeths-mega-token-goes-live-on-13-exchanges-at-1-6b-fdv-after-kpi-milestone/)
- [The Defiant — KPI-1 clearance + 10-app list](https://thedefiant.io/news/blockchains/seven-day-countdown-to-mega-begins-as-megaeth-clears-first-kpi)
- [The Block — KPI-1 + TGE countdown](https://www.theblock.co/post/398651/megaeth-first-kpi-10-apps-live-seven-day-tge-countdown)
- [coincentral — KPI activation](https://coincentral.com/megaeth-activates-mega-token-after-kpi-milestone/)
- [yahoo finance — USDm yield → MEGA buybacks](https://finance.yahoo.com/news/megaeth-foundation-usdm-stablecoin-revenue-193413927.html)
- [PlayToEarn — Terminal Points Platform launch](https://playtoearn.com/news/megaeth-launches-terminal-points-platform-as-season-1-kicks-off-ahead-of-april-30-mega-tge)
- [github.com/megaeth-labs — org index](https://github.com/megaeth-labs)
- [github.com/megaeth-labs/awesome-megaeth-ai — community AI tooling registry](https://github.com/megaeth-labs/awesome-megaeth-ai)
- [awesome-megaeth-ai CONTRIBUTING.md](https://github.com/megaeth-labs/awesome-megaeth-ai/blob/main/CONTRIBUTING.md)
- [0xBreadguy/megaeth-ai-developer-skills — existing skill pack analog](https://github.com/0xBreadguy/megaeth-ai-developer-skills)
- [LayerZero V2 OFT spec — USDm is a bridged OFT](https://docs.layerzero.network/v2/concepts/applications/oft-standard)
- [github.com/zgos/Kumbaya-xyz-integrator-kit](https://github.com/zgos/Kumbaya-xyz-integrator-kit)
- [ETHTokyo'26 calendar](https://www.ethtokyo.org/)
- [ETHMumbai 2026 calendar](https://www.ethmumbai.in/)
- Internal: `docs/integrations/megaeth.md`, `docs/integrations/megaeth-protocol-map.md`, `lib/hackathon/chain_health_gate.py` (referenced for Sapphire-side primitives)
