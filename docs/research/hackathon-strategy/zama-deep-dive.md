# Zama Deep Dive — Programs, Winner Patterns, Sentinel Extensions

**Date:** 2026-05-02
**Author:** Sapphire research lane
**Branch:** `research/zama-deep-dive`
**Audience:** Sapphire core (decision-makers for hackathon dispatch)

---

## Table of Contents

1. [Programs available](#1-programs-available--2026-season-2-live)
2. [Pattern analysis from the winners corpus](#2-pattern-analysis-from-the-winners-corpus)
3. [Sapphire Sentinel-specific recommendations](#3-sapphire-sentinel-specific-recommendations)
4. [New Zama-flavored extensions worth considering](#4-new-zama-flavored-extensions-worth-considering)
5. [Bounty / grant application drafts](#5-bounty--grant-application-drafts)

---

## 1. Programs available — 2026 Season 2 (live)

The headline funding vehicle is **Zama Developer Program — Mainnet Season 2**, announced on the Zama blog and the developer hub. Total prize pool **15,000+ cUSDT** (confidential USDT, ERC-7984, settled on the Zama Protocol). Submission deadline: **May 10, 2026 (23:59 AOE)** for the timed tracks.

Source pages:
- Developer Hub: <https://www.zama.org/developer-hub#developer-program>
- Season 2 launch post: <https://www.zama.org/post/zama-developer-program-mainnet-season-2-confidential-finance-is-the-next-frontier>
- Community announcement: <https://community.zama.org/t/zama-developer-program-mainnet-season-2-is-live/4379>

### 1.1 Tracks (Season 2)

| Track | Prize pool | Splits | Deadline | Form |
|---|---|---|---|---|
| **Builder** | 7,000 cUSDT | 7 × 1,000 | 2026-05-10 23:59 AOE | <https://forms.zama.org/developer-program-mainnet-season2-builder-track> |
| **Bounty** (AI Agent Skills) | 3,000 cUSDT | 1,500 / 1,000 / 500 | 2026-05-10 23:59 AOE | <https://forms.zama.org/developer-program-mainnet-season2-bounty-track> |
| **APAC × OpenBuild** | 5,000 cUSDT | 5 × 1,000 | 2026-05-10 23:59 AOE | <https://openbuild.xyz/learn/challenges/2095330503> |
| **Developer Bootcamp** | Certificate only | n/a | 4-week cohort, rolling | <https://forms.zama.org/developer-program-mainnet-season2-bootcamp> |
| **Startup Track** | Custom (rolling) | n/a | rolling | <https://forms.zama.org/developer-program-startup-track> |

Deliverables (Builder / APAC): confidential dApp with smart contract + frontend, clear documentation, **3-minute video pitch**, deployed on Sepolia testnet or Ethereum mainnet.

Deliverables (Bounty — AI Agent Skills): production-ready `SKILL.md` covering encrypted types, FHE operations, access control, input proofs, decryption patterns, frontend integration, testing, and anti-patterns. Plus a 3-minute demo video. Evaluation criteria: accuracy, completeness, agent effectiveness, code quality, error prevention. Theme is enabling Claude Code, Cursor, and Windsurf to write confidential smart contracts. (Source: Season 2 launch post, linked above.)

### 1.2 Continuous program: zama-ai/bounty-program

A separate, perpetual GitHub-issue-based bounty stream lives at <https://github.com/zama-ai/bounty-program>. Per-bounty rewards are listed inline on each issue — these target FHE library contributions (TFHE-rs, Concrete, Concrete ML) rather than fhEVM dApps. Worth tracking if our Pi cluster work or `lib.analytics.forecast` ever needs an FHE building-block contribution.

### 1.3 Hackathon partnerships and external sponsorships

OpenBuild APAC Special Track is the only currently-listed external partnership at $5,000. Earlier independent special bounty (also via OpenBuild, $5,000) is documented at <https://community.zama.org/t/zama-developer-program-special-bounty-track/4296>. Outside of OpenBuild, the "Zama at ETHGlobal" sponsorships have historically appeared in event-specific prize stacks but no live event listing was confirmed for the May 2026 cycle as of this writing.

### 1.4 What Zama doesn't have (worth knowing)

- **No standalone Grants page.** Grant-shaped funding flows through the Builder Track (7k) and Startup Track (custom). There is no `zama.org/grants` URL — we should stop describing this as a separate program.
- **No persistent "Champions" benefits page.** The developer hub copy mentions "Premium support & training," "Funding & resources," "Marketing & recognition," "Exclusive opportunities" — but these are program benefits, not a separate Champions tier.

---

## 2. Pattern analysis from the winners corpus

The corpus Ari handed me (~60 prior projects) plus the **Mainnet Season 1 winners** post (<https://www.zama.org/post/announcing-the-developer-program-mainnet-season-1-winners>) plus the MARC Protocol writeup (<https://community.zama.org/t/marc-protocol-the-privacy-layer-for-agent-payments/4370>) gave me enough to triangulate what actually wins.

### 2.1 Top 3 categories by count, and why each cluster works

**(a) Confidential payments / payroll / agent payments — easily the largest cluster.**
DripPay, BlindPay, Paychain, PayProof, FHESplit, OBOL, z-payment, Aruvi, Cibon, Senza, **MARC Protocol** (Season 1 Builder winner). Why it works: ERC-7984 has a clear standards story (OpenZeppelin docs at <https://docs.openzeppelin.com/confidential-contracts/token>), the demo is intuitive ("here is my balance, you cannot see it"), and the FHE primitives needed are minimal (encrypted balance, encrypted transfer amount, `FHE.select` for the silent-failure pattern when a transfer would overdraw). Judges visibly understand the value within 30 seconds.

**(b) Confidential DeFi / lending / dark pools / Uniswap hooks.**
null402, AlphaEngine (Uniswap v4 hook), Universal Privacy Hook, Private Uniswap Intents, CAMM, Privacy Pool Monorepo, Pendex, Siphon, plus the early `omurovec/fhe-darkpools` ethCC submission (<https://github.com/omurovec/fhe-darkpools>). Why it works: dark pools are a well-known TradFi concept that mathematically requires confidential order size + price; FHE genuinely unlocks something that wasn't possible on a public EVM. Failure mode: the dark-pools project explicitly notes that off-chain solver matching needs a decryption round-trip via the validator set, so the naive design "cannot be filled with this implementation" — winners need to design around that latency.

**(c) Identity / KYC / voting / reputation.**
Zentity, Uniquity, CipherMint (Season 1 Builder winner), Shadow Confidential Voting, Confidential Vote, Agora, Zamabelief. Why it works: encrypted credentials + verifiable claims is a category Ethereum has been chasing for a decade; FHE removes the awkward "publish anonymized hash" step. Voting in particular maps cleanly to the ConfidentialGovernorAlpha template that ships in `fhevm-contracts` (<https://github.com/zama-ai/fhevm-contracts>).

Smaller but punching above their weight: educational tooling (FHEVM Bootcamp, FHElings, ZamaSchool — Season 1 Bounty winners) and games (FHE GeoGuessr, UpDown60, Hush). Niche real-world projects (Apu, RescueDao, Graze, Legacy Vault, Contracks — Season 1 Builder winner) do well when the privacy story is *unique to the use case* rather than a generic "encrypt the balance."

### 2.2 Production-readiness signals — the bar judges actually score on

Pulled from MARC Protocol (the cleanest Season 1 case study):

- **Test count** — MARC reports **"1100+ tests passing (305 contract + 328 Sepolia on-chain + 173 SDK + 210 plugins + 107 MPP + existing plugins)"**. The 800+/1100+ tests claim is now the production-grade bar; expect the next wave to push 1500+.
- **Deployed on Sepolia** with a documented contract address list, not just a Hardhat test. Mainnet plans noted but not required.
- **Multiple integration surfaces** — MARC ships *seven* contracts plus *six* framework plugins (x402, MCP Server, MPP, AgentKit, Virtuals GAME, OpenClaw) plus a TypeScript SDK on npm (`marc-protocol-sdk`). Judges reward demonstrating the protocol actually plugs into the rest of the agentic stack.
- **A 3-minute video pitch** is now a *required* deliverable for Builder + APAC tracks (per the Season 2 launch post). Submissions without a clean demo video lose by default.
- **Documented architecture diagram** — judges keep mentioning this in writeups; "payment frameworks → MARC encryption layer → fhEVM → Sepolia" is one sentence but it's enough.

### 2.3 Common technical primitives — what the SDK looks like in practice

Based on the canonical Quick Start tutorial (<https://docs.zama.org/protocol/solidity-guides/getting-started/quick-start-tutorial/turn_it_into_fhevm>) and the Zama Protocol litepaper (<https://docs.zama.org/protocol/zama-protocol-litepaper>):

**Imports + config (verbatim from the tutorial):**

```solidity
// SPDX-License-Identifier: BSD-3-Clause-Clear
pragma solidity ^0.8.24;

import { FHE, euint32, euint64, externalEuint64 } from "@fhevm/solidity/lib/FHE.sol";
import { ZamaEthereumConfig } from "@fhevm/solidity/config/ZamaConfig.sol";
```

**Encrypted types from the litepaper:** `ebool`, `euint8…256`, `eint8…256`, `eaddress`, `ebytes1…256`.

**Operations the corpus exercises most:**

| Operation | Use case in winning projects |
|---|---|
| `FHE.add`, `FHE.sub` | Confidential balance accounting (every payment project) |
| `FHE.mul` | Weighted sums, basket aggregates, vesting math |
| `FHE.lt`, `FHE.le`, `FHE.gt`, `FHE.ge`, `FHE.eq`, `FHE.ne` | Threshold checks — auctions, lending solvency, vote tallying |
| `FHE.select(cond, a, b)` | The "silent failure" pattern: transfer succeeds with `0` instead of reverting when balance < amount. MARC uses this explicitly. |
| `FHE.fromExternal(handle, proof)` | Accepting an encrypted input with its KMS-issued input proof |
| `FHE.allow(value, addr)` + `FHE.allowThis(value)` | ACL — letting the caller decrypt later, letting the contract reuse the ciphertext on the next call |
| `FHE.requestDecryption(...)` | Async unwrap via KMS for "reveal the result later" UX |

**Stack underneath:** Host Chain (Sepolia today, Ethereum mainnet imminent, EVM L2s in H1 2026) → Coprocessors (verify proofs, run FHE) → Gateway (Arbitrum rollup orchestrating decryption requests) → KMS (13-node MPC, AWS Nitro Enclaves, 2/3 majority, post-quantum 128-bit security).

### 2.4 Honest take — saturated, underexplored, where the next winner comes from

**Saturated:** generic confidential ERC-20 / payroll. There are now 10+ near-identical "encrypted balance + encrypted transfer" projects. Judges have seen this; you have to bring something else (compliance hooks, x402 plug, agent-aware identity).

**Saturated-ish:** confidential voting / governance. ConfidentialGovernorAlpha already ships as a template, so re-implementing it is a non-event.

**Underexplored:**
1. **Confidential trading-strategy results.** Nobody in the corpus publishes encrypted PnL with selective decryption for LPs / auditors. The closest analog is Pendex (FHE dark pool for pre-IPO).
2. **FHE-paywalled alpha / signal markets.** A few projects ape "private signals" but none combine x402 + ERC-7984 + a real signal source.
3. **Cross-protocol risk attestations.** No project commits encrypted on-chain risk metrics (Aave reserve health, USDM peg deviation, GMX OI imbalance) and lets a verifier check thresholds without revealing the underlying values.
4. **Confidential agent-to-agent reputation.** ERC-8004 exists; nobody has wired a privacy-preserving variant where reputation deltas are encrypted at submission and only aggregate stats decrypt.
5. **Confidential backtest leaderboards** — encrypted Sortino / Calmar with public threshold proofs ("strategy beats 1.5 Sortino without revealing the curve").

The next-winner pattern is "MARC, but for a different vertical." Take a category where (a) the privacy story is *causally necessary* (not nice-to-have), (b) there's a clean ERC standard to lean on or invent, and (c) the dApp slots into a well-known agentic / DeFi flow that everyone in the audience already understands.

---

## 3. Sapphire Sentinel-specific recommendations

[written next]

