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

### 3.1 Graduating `lib/hackathon/privacy_mock.py` to real fhEVM

Today the mock is HMAC-SHA256 over canonical-encoded weights, returning a 32-byte commitment. The interface (`compute_basket_aggregate(weights, salt) -> bytes`) is good — it should not change. What needs to happen for the production swap-in:

**Solidity side — new contract `contracts/SapphireSentinelBasket.sol`:**

```solidity
// SPDX-License-Identifier: BSD-3-Clause-Clear
pragma solidity ^0.8.24;

import { FHE, euint64, externalEuint64 } from "@fhevm/solidity/lib/FHE.sol";
import { ZamaEthereumConfig } from "@fhevm/solidity/config/ZamaConfig.sol";

contract SapphireSentinelBasket is ZamaEthereumConfig {
    // basketId => encrypted weighted sum (Σ wᵢ)
    mapping(bytes32 => euint64) public encryptedWeightSum;
    // basketId => encrypted Σ wᵢ²  (Herfindahl proxy)
    mapping(bytes32 => euint64) public encryptedRiskSum;

    function submitBasket(
        bytes32 basketId,
        externalEuint64[] calldata weights,
        bytes calldata inputProof
    ) external {
        euint64 sum = FHE.asEuint64(0);
        euint64 risk = FHE.asEuint64(0);
        for (uint256 i = 0; i < weights.length; i++) {
            euint64 w = FHE.fromExternal(weights[i], inputProof);
            sum = FHE.add(sum, w);
            risk = FHE.add(risk, FHE.mul(w, w));
        }
        encryptedWeightSum[basketId] = sum;
        encryptedRiskSum[basketId] = risk;
        FHE.allowThis(sum);
        FHE.allowThis(risk);
        FHE.allow(sum, msg.sender);
        FHE.allow(risk, msg.sender);
    }
}
```

This *actually* computes the basket aggregate inside the EVM under encryption — the result is a real ciphertext handle the dashboard can request decryption of via the relayer SDK. The SHA-256 commitment we publish today becomes obsolete; we publish handles instead, and the relayer (or a permissioned verifier) requests decryption when it needs the cleartext.

**Python/TS client side:** the mock's `from zama_fhevm import FhevmClient` swap-in note is technically wrong — there is no `zama_fhevm` Python package. The canonical SDK is the **TypeScript Relayer SDK** under `@zama-fhe/relayer-sdk` (referenced from <https://docs.zama.org/protocol/relayer-sdk-guides>). For Python, there is no first-party client today; the practical options are (a) shell out to a Node helper that uses `@zama-fhe/relayer-sdk`, or (b) hand-roll the EIP-712 input-proof encoding against the Gateway contract directly. Update the docstring in `privacy_mock.py` to reflect this.

**Hardhat boilerplate to add:** `@fhevm/solidity` (npm), `hardhat-fhevm` plugin, the Sepolia RPC + a funded Sepolia key. Quick Start at <https://docs.zama.org/protocol/solidity-guides/getting-started/quick-start-tutorial>.

**Deploy targets:** Sepolia is canonical today (`SepoliaConfig` / `ZamaEthereumConfig`). Ethereum mainnet was announced to launch by end-of-2025 per the Zama Protocol litepaper (<https://docs.zama.org/protocol/zama-protocol-litepaper>) — verify the cutover state at submission time. Other EVMs (Base, Arbitrum) flagged for H1 2026.

### 3.2 Three Sentinel features the mock currently fakes that real FHE actually delivers

1. **Encrypted basket weights → encrypted aggregate computed on-chain.** Today: HMAC commitment, the dashboard can't prove anything to the verifier without revealing the weights. Tomorrow: the contract above computes Σwᵢ and Σwᵢ² inside the EVM under encryption; a verifier can request `FHE.lt(weightSum, MAX_TOTAL)` style threshold proofs without anyone seeing the individual weights.

2. **Encrypted policy-rule evaluation.** The current `evaluate_attempt` computes risk_flags in cleartext Python. With fhEVM, the budget check (`encryptedSpendRemaining ≥ encryptedAmount`) and the issuer-concentration check (`encryptedRiskSum ≤ encryptedHerfindahlCap`) can both run as `FHE.le` / `FHE.ge` comparisons on-chain, returning an `ebool` that the contract `FHE.select`s on to gate the receipt anchor. This is the killer demo: the on-chain gate makes the policy decision *without ever decrypting* the basket.

3. **Encrypted budget remaining.** The mandate's `max_spend_usdc` and `spent_usdc` (today: `Decimal` in Python) become `euint64` state variables. Each approved x402 settlement runs `FHE.sub(encryptedRemaining, encryptedAmount)` inside the contract. The mandate owner gets `FHE.allow`'d to decrypt; nobody else sees how much budget is left or how much has been spent. This pairs naturally with ERC-7984 cUSDC (the same token Zama itself uses for prize payouts).

### 3.3 Zama bounties Sentinel could win as-is (or with a small extension)

- **Builder Track (7 × 1,000 cUSDT).** Sentinel + the contract above + a 3-min video showing approved-vs-blocked flow + Sepolia deployment is a credible Builder submission. Risk: the demo needs to be *visibly* about confidential basket evaluation — not just "we mocked FHE." With ~8 days to the May 10 deadline this is tight but doable.

- **Bounty Track — AI Agent Skills (1,500 / 1,000 / 500 cUSDT).** Strong fit. Sapphire already runs claw-code + Claude Code agents; we have skills infrastructure (`skills/`, `~/.hermes/skills/sapphire/`, 14 hermes skills already). Authoring a `SKILL.md` that teaches Claude / Cursor / Windsurf to write fhEVM contracts (encrypted types, FHE ops, ACL, input proofs, decryption patterns, frontend integration, testing, anti-patterns) is *exactly* in our wheelhouse. We can also dogfood the skill against our own Sentinel contract while writing it. **This is the highest-leverage target.**

- **APAC × OpenBuild Track (5 × 1,000 cUSDT).** Same artifact as Builder, different gate. Submit to both.

---

## 4. New Zama-flavored extensions worth considering

### 4.1 Confidential strategy backtest leaderboard
Publish encrypted Sortino / Calmar / total-return per strategy; let the public verify "strategy X passes the 1.5-Sortino threshold" via `FHE.ge` without revealing the curve. Hooks into our existing `lib.analytics.backtest_results` + `data/backtests/strategies/`. **Feasibility: high.** We already have the underlying numbers; we'd add a thin contract layer.

### 4.2 FHE-paywalled alpha (signal-as-a-service via x402 + ERC-7984)
Subscriber pays in cUSDC via x402; signal payload is encrypted to the subscriber's public key via the relayer; the contract attests "this signal was delivered" with a tamper-evident receipt. Extends the *exact* MARC pattern but for the producer (signal) side rather than the consumer (agent payment) side. **Feasibility: high.** Reuses `services/inference-proxy/` x402 gate work.

### 4.3 Confidential agent-to-agent payments wired to Sentinel
Direct extension of MARC Protocol's pattern. Sentinel becomes the policy gate that evaluates encrypted spend caps before authorizing a confidential cUSDC transfer between two ERC-8004 agents. Slot into the agentic-economy narrative cleanly; differentiates from MARC by adding the *policy* layer (mandate, allow-list, prompt-injection screen). **Feasibility: medium.** Needs ERC-8004 / ERC-8183 wiring we haven't done.

### 4.4 Multi-chain confidential risk attestation
USDM peg health, Aave reserve liquidity, GMX OI — fed in as encrypted inputs (oracle-side), evaluated on-chain by `FHE.le` / `FHE.ge`, output is a public `ebool`-derived "chain healthy" attestation. Genuinely novel: the underlying values stay confidential (advantageous for institutional oracles that don't want to leak proprietary metrics), only the binary attestation is published. **Feasibility: medium.** Needs an oracle relay we don't have.

### 4.5 Confidential mandate marketplace
Mandates (spend cap, allowed actions, expiry) are sold as ERC-721s with encrypted parameters; only the mandate buyer can decrypt their own limits; the contract enforces them via FHE comparisons. Pairs with a "rent-an-agent" UX. **Feasibility: low (right now).** Interesting for a future round.

### 4.6 Honest ranking
**4.1 (backtest leaderboard) and 4.2 (FHE-paywalled alpha) are the two we should actually build.** They reuse 80% of code we already have. 4.3 is the obvious follow-on for the next cycle.

---

## 5. Bounty / grant application drafts

### 5.1 Bounty Track — AI Agent Skills (top target)

> **Project name:** Sapphire fhEVM SKILL.md — Production patterns for agent-authored confidential contracts
>
> **What we'll build:** A production-ready `SKILL.md` (≤ 5,000 tokens) that teaches Claude Code, Cursor, and Windsurf to write fhEVM contracts correctly on the first try. Coverage: encrypted types (`ebool`, `euint*`, `eaddress`, `ebytes*`); the canonical import + `ZamaEthereumConfig` inheritance pattern; `FHE.add/sub/mul/lt/le/eq/select` with realistic expression chains; ACL discipline (`FHE.allowThis` *and* `FHE.allow(value, msg.sender)`); the `FHE.fromExternal(handle, proof)` input-proof flow against the relayer; async decryption via `FHE.requestDecryption` + the callback pattern; frontend integration via `@zama-fhe/relayer-sdk`; Hardhat `hardhat-fhevm` testing patterns (Sepolia + local mock); and the ten anti-patterns that bite first-timers (forgetting `allowThis`, mixing cleartext + ciphertext arithmetic, using `require` on an `ebool`, comparing handles instead of values, etc.).
>
> **Why us:** Sapphire already runs 14 hermes skills, a 109-tool plugin registry, and authors agent skills as a daily activity; we'll dogfood the SKILL by having Claude Code re-author our own `SapphireSentinelBasket.sol` from scratch and capture the failure-mode telemetry as evidence in the demo video. Built by Sapphire core + claw-code maintainers.

### 5.2 Builder Track — Sapphire Sentinel (real fhEVM swap-in)

> **Project name:** Sapphire Sentinel — Confidential policy gate for autonomous-agent payments
>
> **What we'll build:** A non-custodial mandate + receipt registry on Sepolia that evaluates confidential basket weights, encrypted spend caps, and encrypted issuer-concentration limits *inside the EVM under FHE* — the policy decision is rendered as an on-chain `ebool` without ever decrypting the underlying portfolio. Pairs with an x402 paywall on Base Sepolia for paid-intel settlement and a Robinhood Chain testnet anchor for the receipt. Agents can buy private RWA signals through a budget-bounded mandate; Sentinel screens for prompt injection, secret egress, domain allow-list violation, and on-chain risk *before* approving payment. Built on `@fhevm/solidity` v0.12+ with `ZamaEthereumConfig` inheritance, `FHE.fromExternal` input proofs, and `FHE.allow` / `FHE.allowThis` ACL.
>
> **Why us:** Sapphire has an existing Lane A privacy mock (`lib/hackathon/privacy_mock.py`) that ships the exact interface today; the production swap is a contract addition + a TS client wrapper, not a redesign. The pitch deck, dashboard page (`/chain/sentinel`), and `SapphireSentinelRegistry.sol` are already in main. The 3-minute video shows: human authors mandate → agent attempts paid call → Sentinel rejects an injection attempt → Sentinel approves a clean call → on-chain ciphertext receipt → mandate owner decrypts remaining budget. Sapphire core + the London buildathon team.

---

## Appendix — sources

- <https://www.zama.org/developer-hub#developer-program>
- <https://www.zama.org/post/zama-developer-program-mainnet-season-2-confidential-finance-is-the-next-frontier>
- <https://community.zama.org/t/zama-developer-program-mainnet-season-2-is-live/4379>
- <https://www.zama.org/post/announcing-the-developer-program-mainnet-season-1-winners>
- <https://community.zama.org/t/marc-protocol-the-privacy-layer-for-agent-payments/4370>
- <https://github.com/Himess/marc-protocol>
- <https://docs.zama.org/protocol/zama-protocol-litepaper>
- <https://docs.zama.org/protocol/solidity-guides>
- <https://docs.zama.org/protocol/solidity-guides/smart-contract/configure>
- <https://docs.zama.org/protocol/solidity-guides/getting-started/quick-start-tutorial/turn_it_into_fhevm>
- <https://docs.zama.org/protocol/relayer-sdk-guides>
- <https://github.com/zama-ai/fhevm>
- <https://github.com/zama-ai/fhevm-contracts>
- <https://github.com/zama-ai/bounty-program>
- <https://github.com/zama-ai/awesome-zama>
- <https://github.com/omurovec/fhe-darkpools>
- <https://docs.openzeppelin.com/confidential-contracts/token>
- <https://forms.zama.org/developer-program-mainnet-season2-builder-track>
- <https://forms.zama.org/developer-program-mainnet-season2-bounty-track>
- <https://forms.zama.org/developer-program-mainnet-season2-bootcamp>
- <https://forms.zama.org/developer-program-startup-track>
- <https://openbuild.xyz/learn/challenges/2095330503>

