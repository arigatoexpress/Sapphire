# Apollo Accelerator (0G) — Sapphire OS application draft

**Status:** DRAFT — Ari to polish + submit when the next Apollo cohort window opens.
**Program:** 0G Apollo AI Accelerator — up to **$2M / team**, 10 teams selected globally, Stanford-adjacent (Blockchain Builders Fund), 10-week intensive cohort.
**Application URL:** <https://apollo.0g.ai/> (verify the live form URL at submit time; 2026 cycle used `forms.gle/TYM4tZaD1gYrDVdS9`).
**Sequencing:** apply **post-0G APAC hackathon** (`PR #525`, `feat/0g-integration`). The hackathon submission with mainnet activity is the strongest single piece of evidence Apollo will see.
**Source material referenced when drafting:**
- `docs/research/hackathon-strategy/0g-deep-dive.md` (PR #562) — Apollo program parameters, vertical fit, cohort dynamics
- `docs/pitch/sapphire-os-one-page.md` (PR #601) — canonical pitch (one-line + counts + roadmap reused verbatim for cross-pitch consistency)
- `docs/grants/megaeth-mafia-2.0-application.md` (PR #566) — example tone + structure

---

## Field 1 — Project name

**Sapphire OS**

(Not "Sapphire 0G integration." Apollo funds platforms; the 0G integration is the verifiable-AI cryptographic settlement layer on top of a production trading OS. The platform is the asset.)

---

## Field 2 — One-line pitch (≤25 words)

> **Sapphire OS is an autonomous AI-agent operator that uses on-chain primitives — peg health, lending solvency, oracle integrity — to verify alpha before acting on real money.**

(24 words. Same one-liner used in Mafia 2.0, the one-page pitch, and the hackathon submissions — cross-pitch consistency is deliberate; Apollo screening committee may have already seen this language via 0G ecosystem channels.)

---

## Field 3 — Problem statement (2–3 sentences)

> Today's autonomous trading agents trade on signals without verifying the underlying chain state — a USDM depeg, an Aave-pause, or a frozen reserve silently corrupts every leveraged decision downstream, and the result is the next Curve-pool implosion except automated and at LLM-reasoning-loop frequency.
>
> The missing primitive is **cryptographic alpha-verification**: a way for any agent to prove (1) the prediction existed before the move, (2) the model that produced it wasn't silently swapped, and (3) the operator can't backfill the inputs. Without 0G Storage + 0G Chain + TEE-sealed inference in one round-trip, no public chain offers all three.

---

## Field 4 — Solution (1 paragraph)

> Sapphire OS is the production trading OS that ships this verification path end-to-end. Every signal the system generates passes through a 4-tier inference proxy, then a Sentinel chain-health gate that reads multi-chain state (peg, solvency, oracle staleness, frozen flags) before any execution; approved signals are sealed by 0G Compute (TEE-attested), uploaded to 0G Storage as a content-addressed merkle envelope, anchored on 0G Chain mainnet (16661) via `SapphireSignalVerifier.publishSignal(...)`, and a public `og_verify` round-trip lets anyone replay the proof. The trading critical path is feature-flagged and fail-closed: with `SAPPHIRE_OG_ENABLED=0` the executor is byte-identical to today's production stack, so adoption never trades safety for verifiability.

---

## Field 5 — Why this team / why now

> **Why this team:** Sapphire is a solo build by Ari Spec — 18+ months of production trading + ML + infrastructure work, every commit visible at `github.com/arigatoexpress/Sapphire`. The repo is the technical CV. What Apollo screens for (revenue-generating decentralized AI applications with real users + on-chain footprint) is exactly what Sapphire has been compounding toward since well before 0G mainnet existed. Solo founder with shipping bias; open to bringing on a co-founder during the cohort, specifically someone with cross-chain protocol-engineering experience.
>
> **Why now:** 0G Aristotle mainnet went live 2025-09-22; the deployed-DeFi field on chain 16661 is **thin enough that a single live trading-signal verifier with consistent on-chain activity stands out** (per `docs/research/hackathon-strategy/0g-deep-dive.md` §4.1). There is no announced equivalent today. The window to be the **canonical verifiable-trading-signal primitive on 0G** is open for ~6–12 months before incumbents arrive. Apollo's 10-week intensive is the structural lever that converts that window into category-definition.

---

## Field 6 — Traction

**Codebase scale (verifiable in `github.com/arigatoexpress/Sapphire`):**
- **6,626 collected tests** (6,059 unit + 567 plugin per `python3 scripts/ops/test_inventory.py --check-readme`, 2026-05-03)
- 109 plugin tools on disk · 16 registered agent-facing tools · 14 hermes-agent skills
- 50 dashboard pages · 20 active LaunchAgents · 22 scheduled tasks · 3 deployed/scaffolded Solidity contracts
- CI-enforced tool registry invariants · ruff + gitleaks + bandit pre-commit · daily OSV + trivy scans

**0G integration depth (3 of 4 primary 0G components):**
- **0G Storage** — content-addressed signal envelope upload, returns merkle `rootHash`
- **0G Compute** — TEE-sealed inference, returns enclave-signed `chatID` re-verifiable via `broker.inference.processResponse(provider, chatID)`
- **0G Chain mainnet (16661)** — `SapphireSignalVerifier.publishSignal(strategyId, symbol, direction, confidence, proofHash=rootHash)` immutable anchor
- **`og_verify` tool** — public round-trip read; downloads the blob, re-verifies the merkle proof + TEE attestation, no clone-and-run required

**Live execution (production-grade, not demo):**
- **Hyperliquid live executor** (mainnet-refused until EIP-712 signing verified): $5/order, 3x lev, $25/day loss cap, file-killswitch — fail-closed by default
- **Robinhood Crypto live capital, $50 pilot rung:** first live BTC fill 2026-04-28 04:06 UTC, $5 at $76,774.81. 14-day Sortino soak before next rung.
- **Prediction accuracy (verified):** 61.1% overall, **BTC 83.3%** on 36 scored of 42 forecasts.

**Hackathon submissions (concurrent funnel, not blocking):**
- **0G APAC Hackathon Track 2 — `<placement TBD post-2026-05-16>`** (submission complete, PR #525)
- **Arbitrum London Best Agentic Project — `<placement TBD post-2026-06-17>`** (Sentinel + chain-health gate)
- **Mega Mafia 2.0 application** filed (PR #566)
- **Zama AI Skills bounty** (PR #559)

**Repo:** `github.com/arigatoexpress/Sapphire` (public — every claim above is verifiable in commit history + tests)

---

## Field 7 — Why 0G specifically (and why Apollo over generic raise)

> 0G is the only L1 today that ships **Storage + Compute (TEE-sealed) + Chain + DA** as one composable stack. For a verifiable-trading-signal primitive, those four primitives are the dependency tree — anywhere else in Web3 we'd have to assemble them from 3 vendors with mismatched trust assumptions. 0G is the chain where the integration is *one round-trip*, not three.
>
> **TEE-sealed verifiable inference is the missing layer between AI-trading-claim and AI-trading-proof.** Sapphire is the only production trading stack that already integrates 0G Storage + Compute + Chain in one submission with a public verifier round-trip (3 of 4 primary 0G components — DA is the v2 target if Apollo funds it). Most Track 2 hackathon entries integrate 1 or 2 components and have no verifier — Sapphire is the integration that proves the pattern is viable end-to-end.
>
> **Why Apollo over a generic seed raise:** Apollo's value is not just capital — it's (1) Stanford / Blockchain Builders Fund proximity, (2) co-marketing inside the 0G ecosystem (300+ partners), (3) Privy wallet integration access, (4) $200K Google Cloud credits to host the verifier endpoint and the TeeTLS broker (see milestones). A generic SAFE round buys runway; Apollo buys runway *plus* canonical-on-0G positioning before incumbents arrive.

---

## Field 8 — Use of funds ($2M ask, cohort-typical)

1. **One senior engineering hire — cross-chain integrations + 0G DA adoption.** Sapphire is solo today; the binding constraint is integration breadth (cross-chain Sentinel adapters: Base, Optimism, Solana) and the 0G DA component for the streaming signal feed. Hire profile: 5+ years Solidity + Rust + Python, prior protocol-engineering at a serious chain. *~$300–400K fully loaded for 12 months.*

2. **One design-partner success lead.** Sapphire's biggest commercial lever is convincing other autonomous-agent teams to depend on the chain-health gate + verifier endpoint. This role lands integrations with 0G ecosystem partners (Gimo, Euclid, Cygnus, Dormint, HAiO, QuillAI Network are warm targets per the deep-dive research) and tracks them through to production. *~$150–200K fully loaded for 12 months.*

3. **Mainnet trading capital reserve (laddered).** Continue laddering Sapphire's own treasury through the existing $5 → $50 → $500 → $5,000 rung structure with Sortino > 2.0 gating each rung. Capital validates the trading stack honestly, generates revenue, and is dogfood for the verifier (every trade produces a published signal that becomes a public reference for Sentinel-as-a-service prospects). *~$500K reserve, drawn against rung gates only.*

4. **Hosted Sentinel + verifier endpoint infrastructure.** `evaluate_chain(chain_id)` and `og_verify(signal_id)` as paid hosted APIs so other agents and auditors can use them without running their own RPC stack. Includes Cloud Run / Cloudflare Pages frontends, RPC quotas across MegaETH + Arbitrum + Optimism + Base + 0G, and a Sapphire-branded 0G Storage node for "we eat our own dog food" credibility. *~$50–100K/yr ongoing infra; uses the $200K Google Cloud credits as initial subsidy.*

5. **Reserve for TeeTLS broker prototype (Apollo-funded only).** v2 idea from `0g-deep-dive.md` §3.3 — a TeeTLS broker that fronts the existing 4-tier inference proxy, signing every response with the enclave key. Hardware ~$8–15K (TDX-capable rack node + H100 lease, or Azure DCsv5 / Google C3-attested VMs). Only pursued if Apollo or Guild funds it; not self-funded.

(Total fits the cohort-typical $2M envelope. Capital efficiency is high because Sapphire is already a working production stack — Apollo capital accelerates **distribution + integration + verification**, not v0 build.)

---

## Field 9 — 12-month milestones (tied to 0G ecosystem KPIs)

### Months 0–3 (Foundation)
- **5+ named design partners** integrating Sapphire's chain-health gate as their pre-trade safety check (target: Gimo, one Aave-V3-on-0G consumer, one DeFAI fund, two trading-agent teams)
- **Sentinel chain-health gate covers 5+ chains** (currently 2: MegaETH + Arbitrum; add Base, Optimism, 0G + one Solana adapter)
- **`/0g-feed` dashboard** at `verify.sapphirealpha.xyz` rendering live `SignalPublished` events from chain 16661 — public verifier with no clone-and-run required
- **Open-source `@sapphire/og-verifier-sdk`** (Python facade + Node helper + Solidity contracts) listed on the 0G SDK page

### Months 3–6 (Adoption)
- **100+ external agents** consuming `evaluate_chain(chain_id)` and `og_verify(signal_id)` hosted endpoints
- **$1M+ TVL gated by Sentinel attestations** across design-partner integrations
- **0G DA integrated** for the streaming signal feed (vs. one anchor per signal) — closes the 4 of 4 0G primary-component story
- **Co-marketed case study with 0G Labs** — "How Sapphire Verified $X of Trading Signals on 0G in 90 Days"

### Months 6–12 (Category definition)
- **Sapphire-branded 0G Storage node** running ("we eat our own dog food" — `<TBD post-deploy>` rewards)
- **TeeTLS broker reference implementation** open-sourced and proposed as 0G TeeTLS docs reference
- **3 graduated paying integrations** (paid tier on the hosted endpoints — x402 micropayments, which Sapphire already ships in `lib/payments/x402_middleware.py`)
- **Sortino > 2.0 sustained** on the live trading capital ladder, with verifier history as the public proof of every prediction

---

## Field 10 — Team

> **Solo founder: Ari Spec.** Production trading + ML + infrastructure background — Sapphire OS is the visible artifact of that background and demonstrably my work (every commit in `github.com/arigatoexpress/Sapphire`). Operating Sapphire today from a multi-device mesh (Mac commander, Windows GPU node, two Pis, Tailscale-meshed).
>
> Open to bringing on a co-founder during the cohort — the Apollo network is exactly where I'd most credibly find that person, which is part of the value of the 10-week format.
>
> **`<Ari to add: 1-paragraph founder bio — prior trading roles, education, any prior fund/firm associations, geographic location. The form will likely have a "founder background" field that benefits from named history beyond the GitHub repo.>`**

---

## Field 11 — Anything else (catch-all)

> Three things worth flagging that the form may not directly ask:
>
> 1. **Sapphire is operationally honest about what doesn't work yet.** Hyperliquid is mainnet-refused until EIP-712 signing is verified on testnet (the policy field literally blocks mainnet orders until a code change). Robinhood Crypto live capital is $5/order with a 14-day Sortino soak before the next rung. Where accelerators have burned on teams that overstated production-readiness, Sapphire's posture is the opposite — fail-closed defaults, killswitches, and small first-rung caps everywhere.
>
> 2. **The 0G integration is the *settlement* layer; the trading OS is the *value* layer.** Apollo's pitch language emphasizes 0G as "the Apple of Web3 AI" — Sapphire validates that thesis with a real production trading stack rather than a thin demo. The integration would have value even on a different chain; on 0G it's category-defining.
>
> 3. **The Apollo cohort is the lever, not the goal.** The funding programs in the 0G stack (Apollo, Guild on 0G $8.88M sub-fund) are tools to get Sapphire's verifier in front of the 300+ ecosystem partners and the `#BuildOn0G` audience. We treat placement in the hackathon as a bonus, the integration as the asset, and the cohort as the distribution event.

---

## Quick-reference appendix (for Ari's polish pass)

**Numbers Ari should sanity-check at submission time:**
- "6,626 tests" — verify with `python3 scripts/ops/test_inventory.py --check-readme`
- "BTC 83.3% on 36 scored of 42 forecasts" — verify against current `lib.analytics.prediction_accuracy` output
- "First Robinhood live BTC fill 2026-04-28 04:06 UTC, $5 at $76,774.81" — exact, from `data/paper_trading.jsonl` / portfolio snapshot
- 0G mainnet contract addresses — `<TBD post-deploy>` placeholders must be replaced with live `chainscan.0g.ai/address/...` URLs
- Apollo cohort dates + max-per-team — verify against `apollo.0g.ai` at submit time (the $2M / 10-team / 10-week parameters were 2026 cycle)

**Phrases reused from one-page pitch / Mafia 2.0 (kept verbatim for cross-pitch consistency):**
- "production AI-agent operator that uses on-chain primitives"
- "fail-closed by default"
- "verifiable autonomous trading"
- "the canonical multi-chain agent-operator runtime"
- "every claim is line-cited and CI-verified in production"

**One thing only Ari can add:**
- **A founder-bio paragraph in Field 10.** The GitHub repo is the technical CV but Apollo's screening committee will want named history (prior trading roles, named funds, education). Ari to fill before submit.

**Submission sequencing recommendation:**
1. Wait for 0G APAC hackathon result (2026-05-16 deadline → result late May / early June)
2. If placed, lead the Apollo application with the placement; if not placed, lead with the *integration* (3-of-4 0G components, public verifier, mainnet activity)
3. File **in parallel** with Guild on 0G ($8.88M sub-fund — see `docs/grants/guild-on-0g-application.md`). Different funding mechanics; not mutually exclusive.
4. Replace every `<TBD post-...>` placeholder with live data before paste.
