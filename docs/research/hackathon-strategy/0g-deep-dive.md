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

