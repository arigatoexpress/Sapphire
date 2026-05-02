# 0G Labs Deep Dive — APAC Hackathon Criteria, Sapphire Pitch Gaps, and Ecosystem Map

**Authored:** 2026-05-02 (T-14 days to 2026-05-16 23:59 UTC+8 submission deadline)
**Owner:** Ari Spec
**Inputs:** `docs/hackathon-0g/README.md`, `docs/hackathon-0g/submission-checklist.md`, `docs/hackathon-0g/design.md`, `lib/og/{storage,compute,chain,hooks}.py`, public 0G Labs sources cited inline.
**Companion PR:** Sapphire × 0G submission lives on `feat/0g-integration` (PR #525, merged).

## Table of Contents

1. [APAC Hackathon judging deep dive](#1-apac-hackathon-judging-deep-dive)
2. [Sapphire × 0G submission gap analysis](#2-sapphire--0g-submission-gap-analysis)
3. [Programs beyond the hackathon](#3-programs-beyond-the-hackathon)
4. [Mainnet competitive landscape](#4-mainnet-competitive-landscape)
5. [Post-submission narrative](#5-post-submission-narrative)
6. [Top 3 actionable items](#top-3-actionable-items)

---

## 1. APAC Hackathon judging deep dive

### 1.1 Track structure

The 0G APAC Hackathon (registration 2026-03-19, submission 2026-05-16 23:59 UTC+8) has **5 tracks** (HackQuest's earlier marketing said 4; the live track list is 5 — Sapphire's submission targets Track 2):

| # | Track | What 0G is hoping to see |
|---|-------|--------------------------|
| 1 | **Agentic Infrastructure & OpenClaw Lab** | Autonomous-intelligence backbone, orchestration layers. Encourages OpenClaw integration + 0G Compute fine-tuning + 0G Storage state persistence. |
| 2 | **Agentic Trading Arena (Verifiable Finance)** | "Transitioning from manual DeFi to fully autonomous, verifiable financial logic." Yield optimizers, risk-management bots, perpetual strategy agents. **Explicitly endorses Sealed Inference + TEE-based execution to mitigate front-running.** |
| 3 | **Agentic Economy & Autonomous Applications** | Financial protocols, AI commerce, SocialFi agents, Agent-as-a-Service, micropayments, automated billing, self-custodial agent wallets. |
| 4 | **Web 4.0 Open Innovation (Wildcard)** | High-performance scaling for SocialFi, Gaming, DePIN. Decentralized storage required. |
| 5 | **Privacy & Sovereign Infrastructure** | Privacy-preserving protocols, cross-chain solutions, MEV-resistant infrastructure. |

**Cross-track positioning for Sapphire:** Track 2 is the obvious primary. Track 3 (Agent Economy) is a credible secondary because Sapphire already ships `SapphirePaymentGate` + `SapphireSentinelRegistry` on the same submission — agent mandates and on-chain payment receipts are exactly what Track 3 calls for. **Hackathon rules typically allow a project to be considered for multiple tracks if the form lets you tag them; if HackQuest only allows one, stay on Track 2.** Track 5 has tangential overlap (TEE = privacy infrastructure) but is weaker positioning since Sapphire isn't a privacy protocol per se.

### 1.2 Prize pool

- **Total: $150,000 USDT + 0G Ecosystem Credits**
- Grand Prizes: 1st **$45,000**, 2nd **$35,000**, 3rd **$20,000** (cross-track — there is no announced track-specific prize split)
- Excellence Awards: 10 × **$3,700** = $37,000
- Community Awards: 10 × **$1,300** = $13,000

The prize structure is **cross-track**, meaning a single Track 2 entry competes against the strongest entries from all 5 tracks for grand prizes. There are 23 prize slots in total (3 grand + 10 excellence + 10 community), so roughly 1 in 5 reasonable submissions takes home cash if total entries land in the typical 100–150 range for hackathons of this prize size.

### 1.3 Judging criteria (verbatim from HackQuest)

1. **0G Technical Integration Depth & Innovation** — *most important; "at least one 0G component must be integrated" or face disqualification/deductions.*
2. **Technical Implementation & Completeness**
3. **Product Value & Market Potential**
4. **User Experience & Demo Quality**
5. **Team Capability & Documentation**

Source: https://www.hackquest.io/hackathons/0G-APAC-Hackathon

**Implication for Sapphire:** criterion #1 dominates. Judges will weigh *how many* 0G components you use and *how deeply* (mainnet activity > testnet > readme claims). Sapphire integrates **3 of 4** primary components (Storage, Compute/TEE, Chain) — that's strong, but missing 0G DA. See §2 for whether to add it.

### 1.4 Submission requirements (form fields)

| # | Required field | Sapphire status |
|---|----------------|-----------------|
| 1 | Project name + ≤30-word description + problem statement + 0G components list | DONE in `docs/hackathon-0g/submission-checklist.md` |
| 2 | Public GitHub repo with substantial dev | DONE — `arigatoexpress/Sapphire`, PR #525 merged |
| 3 | **0G Mainnet contract address + 0G Explorer link showing on-chain activity** | **MISSING — biggest gap** |
| 4 | Demo video ≤3 min (YouTube/Loom) showing functionality + 0G usage | MISSING |
| 5 | README/documentation (English or Chinese) including architecture, deployment steps, test account details | DONE |
| 6 | Public X post with project name, demo link, hashtags `#0GHackathon #BuildOn0G`, tags `@0G_labs @0g_CN @0g_Eco @HackQuest_` | DRAFT in `x-post.md`, not posted |
| 7 | Optional bonus: pitch deck, frontend link, user feedback, technical write-ups | OPPORTUNITY (see §2.4) |

### 1.5 Past 0G hackathon winners — pattern analysis

0G has been a sponsor (not solo host) at several recent hackathons before APAC:

| Event | Date | 0G prize pool | Pattern of winning entries |
|---|---|---|---|
| **ETHGlobal Cannes** | 2025-07-04→06 | $5,000 (3 bounty teams) | Part of broader $275K ETHGlobal pool. ([Chainwire](https://chainwire.org/2025/07/09/0g-labs-sponsors-ethglobal-cannes-hackathon-and-supports-275k-prize-pool/)) |
| **ETHGlobal Trifecta** | 2025 | $5,000 | 72-hour invite-only sprint among prior ETHGlobal winners; tight integrations of 0G Storage/Compute. |
| **HKWeb3 Hackathon** | 2025 | undisclosed | Multi-week marathon; 0G surfaced "elite student" entries from Seoul/Shenzhen/Shanghai per their own recap. ([0G blog mirror](https://www.choosen.systems/blog/0g-latest-hackathon-highlights.html)) |
| **OpenAgents (ETHGlobal)** | 2025 | undisclosed | Theme: hierarchical planning + reflection loops integrating **0G Compute sealed inference**. ([ETHGlobal OpenAgents](https://ethglobal.com/events/openagents/prizes)) |

**Public winner detail is sparse** — 0G's own recaps don't name the winning projects with deep technical breakdowns, which makes pattern analysis partial. From what *is* public:

- Winners consistently demo **mainnet activity, not testnet promises** — every recap blurb leads with "deployed live on …" or "X transactions anchored."
- Winners pair **at least 2 0G components** (Storage + Chain is the most common pair; Compute alone is rarer).
- Winners pitch **a real user/customer**, not just architecture. The OpenAgents winners typically had Discord communities or named pilot users.
- Winners produce **a live demo video that shows the on-chain footprint**, not just terminal logs.

### 1.6 Scoring rubric inferred (since 0G has not published exact weights)

Given criteria #1–#5 and the consistent pattern across 0G's prior sponsorships, a defensible weight estimate is:

- 0G Integration Depth: ~30%
- Technical Completeness: ~20%
- Product/Market Value: ~20%
- UX/Demo Quality: ~20%
- Team/Docs: ~10%

A submission that is 90% on integration but 30% on demo will score worse than a balanced 70% across the board.

---

## 2. Sapphire × 0G submission gap analysis

Sapphire's current pitch (`docs/hackathon-0g/README.md`) is **technically excellent and narratively under-tuned for hackathon judges.** The integration depth is real (3 of 4 0G primary components, 56 dedicated tests, fire-and-forget production safety, two live triggers — TradingView webhooks + Kronos daily). The risk is that judges scanning hundreds of submissions read the first 20 lines and don't reach the part where Sapphire is a 6,488-test production trading OS.

### 2.1 Where we're already strong

| Strength | Evidence |
|---|---|
| **Component breadth** | Storage + Compute + Chain in one submission, with a verifier round-trip flow that uses all three. Most hackathon entries integrate 1–2. |
| **Production credibility** | 6,488+ tests, 50 dashboard pages, 7 quant strategies, live Hyperliquid + Robinhood execution. Most hackathon entries are prototypes built that month. |
| **Safety story** | `SAPPHIRE_OG_ENABLED=1` flag → trading critical path is byte-identical without 0G. Fire-and-forget publish never blocks a trade. This is *exactly* the maturity narrative judges respect. |
| **Verifier path** | `og_verify` — the round-trip read tool — is what closes the loop and proves the system isn't write-only. Many hackathon entries write to chain but provide no public verifier. |
| **Track 2 alignment** | Sapphire's TEE-attested signal generation directly answers Track 2's explicit ask: "Sealed Inference and TEE-based execution to ensure execution privacy and mitigate front-running." |

### 2.2 Where we're underselling (text fixes)

These are line-level edits to `docs/hackathon-0g/README.md`. Each is a high-leverage, ≤30-minute change.

#### Edit A — TL;DR is too modest (current line 7–9)

**Before:**
```
## One-sentence pitch (≤30 words)

A production trading agent that publishes every signal to 0G Storage and anchors it on 0G Chain, giving traders, auditors, and counterparties on-chain proof of every prediction.
```

**After:**
```
## One-sentence pitch (≤30 words)

The first production-grade trading OS (6,488 tests, live execution) to make every AI prediction cryptographically committed before market impact — sealed by 0G Compute, anchored on 0G Chain.
```

**Why:** the current pitch reads as descriptive infrastructure. The replacement opens with two scarcity claims ("first," "production-grade with concrete test count") and one mechanism that judges associate with the Track 2 mandate ("before market impact"). Both stay under 30 words.

#### Edit B — Add a "Why this is hard" section directly above "What it does" (insert after line 5)

**Insert:**
```
## Why this is hard

Three things have to be true for a verifiable trading signal: (1) the prediction had to exist *before* the move; (2) the model that produced it can't be silently swapped; (3) the operator can't backfill the inputs. Without 0G Storage + 0G Chain + TEE-sealed inference, no public chain offers all three in one round-trip. Sapphire is the integration that proves it.
```

**Why:** judges' eyes glaze on "what it does" lists. A two-sentence problem statement up top makes the integration feel inevitable rather than additive. This also directly mirrors HackQuest's submission requirement: "problem statement."

#### Edit C — Reframe the "What it does" numbered list as **proofs**, not steps (current lines 13–18)

**Before** (paraphrased): four numbered process steps (Inference → Storage → Chain → Verifier).

**After:** keep the same four bullets but rename the section **"What 0G makes verifiable"** and prefix each bullet with the *property it proves*:

```
## What 0G makes verifiable

1. **The model wasn't tampered with** — `0G Compute` runs the inference inside a TEE; the returned `chatID` is signed by the enclave key and re-verifiable via `broker.inference.processResponse(provider, chatID)`.
2. **The prediction was committed before disclosure** — the full envelope (input, reasoning, output, attestation) is uploaded to `0G Storage` returning a content-addressed merkle `rootHash`.
3. **The timestamp is on a public clock** — `SapphireSignalVerifier.publishSignal(strategyId, symbol, direction, confidence, proofHash=rootHash)` is called on `0G Chain mainnet (16661)`, immutably anchoring the prediction.
4. **Anyone can replay the proof** — the `og_verify` tool reads the on-chain entry → downloads the blob from 0G Storage with merkle-proof check → re-verifies the TEE attestation. No special access required.
```

**Why:** the current text describes *mechanism*. The replacement asserts *guarantees* and ties each guarantee to one 0G component. This is what criterion #1 (Integration Depth) is grading.

#### Edit D — Open the "Mainnet contract addresses" section with a live-explorer screenshot reference (current lines 109–117)

**Add directly under the section header:**
```
> Live activity: see [chainscan.0g.ai/address/<addr>](https://chainscan.0g.ai/address/0x...) — the `SignalPublished` event log is the running ledger of every prediction this system has committed.
```

**Why:** judges click *one* link to confirm activity; that link should be the explorer, not the GitHub repo. The README currently buries this under a markdown table that reads as "TBD."

#### Edit E — Promote the test count + production claim into the first 200 words (currently buried under "See also" at line 145)

**Add as a closing line in the TL;DR or as a one-liner after the pitch:**

```
> **Why we're credible:** 6,488 tests passing, 50 dashboard pages, 7 quant strategies, live Hyperliquid + Robinhood Crypto execution as of 2026-04-30. The 0G integration is the cryptographic settlement layer on top — not a hackathon prototype.
```

**Why:** Sapphire's strongest non-0G signal is "this is a real working system." Judges grading criterion #5 (Team Capability & Documentation) and #3 (Product Value) should not have to scroll to find it.

### 2.3 What's missing entirely

| Gap | Why it matters | Effort to close |
|---|---|---|
| **Live mainnet `SignalPublished` event log** | Criterion #1 weights mainnet activity over testnet. The README has placeholder `0x...` addresses; explorers will show 0 transactions until you deploy + publish. | 1–2 hrs (deploy + 1 real publish) — this is the **single highest-leverage action** before submission. |
| **Public verifier endpoint (no clone-and-run required)** | Judges should not need to `git clone` + install Node deps to verify a signal. A static page (Cloudflare Pages or Vercel) at e.g. `verify.sapphirealpha.xyz` that takes a `signal_id` and renders the round-trip would dramatically improve UX score. | 4–8 hrs |
| **0G DA usage** | Sapphire uses Storage + Compute + Chain; **0G DA is unused**. Adding DA for streaming the live signal feed (vs. one anchor per signal) would be a credible "depth" win. Not required, but the only remaining 0G primary-component gap. | 1–2 days (likely too much before deadline) |
| **At least one named third-party using the verifier** | Even one signed quote ("we audited Sapphire's published signals") from a peer trading-tools team would lift criterion #3 (Market Value). | 1–3 days of outreach |
| **Pitch deck (optional bonus)** | Listed as optional but in a tied scoring scenario could be the differentiator. The Sapphire dashboard already has the visuals. | 2–4 hrs |
| **Frontend showing live anchored signals** | A `/0g-feed` dashboard page reading from `SignalPublished` events would be a "show, don't tell" win — judges click one link, see real activity. | 1 day |

### 2.4 The single highest-leverage addition (under 1 day)

**Build `/0g-feed` as a new dashboard page on the existing Flask dashboard that reads `SignalPublished` events from the deployed mainnet contract and renders them as a live table with explorer links + the `og_verify` round-trip output inline.**

Why this dominates other 1-day options:

- **Touches all 5 criteria in one artifact.** Integration (reads on-chain), Implementation (uses existing dashboard), Product Value (a usable consumer of the proof), UX (one URL judges click), Documentation (already a Sapphire pattern).
- **Replaces the "show me on chain" risk with a live demo URL** judges can hit without setup.
- **Compounds with Edit D** — instead of "explorer link," the README points to `sapphirealpha.xyz/0g-feed` which then links into the explorer.
- **Re-uses 90% existing code:** Sapphire already has 50 dashboard pages reading from JSONL/Redis; this just adds an `eth_filter` reader on `lib/og/chain.py` and a Jinja template.

If only one thing happens in the next 14 days beyond mainnet deploy + demo video, this is the thing.

