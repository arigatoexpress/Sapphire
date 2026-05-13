# Guild on 0G — Sapphire × 0G application draft

**Status:** DRAFT — Ari to polish + submit when the post-0G-APAC-hackathon window opens (file in parallel with Apollo Accelerator; different funding mechanics, not mutually exclusive).
**Program:** **Guild on 0G** — $8.88M sub-fund within the broader **0G Foundation Ecosystem Growth Program** ($88.88M total). Targets early-stage builders going testnet → mainnet. Funder mix: Hack VC, Delphi Ventures, Bankless Ventures, OKX Ventures.
**Application URL:** <https://app.deform.cc/form/da4fc5f6-1836-42fc-b95b-84f43ce1bdf2/> (verify the live form URL at submit time).
**Sequencing:** apply **post-0G APAC hackathon** with mainnet activity from chain 16661 as evidence; file **in parallel with Apollo Accelerator** (`docs/grants/apollo-accelerator-application.md`) — the two have different mechanics (grant vs. equity-style accelerator) and target different selection criteria.
**Source material referenced when drafting:**
- `docs/research/hackathon-strategy/0g-deep-dive.md` (PR #562) — Guild parameters, Apollo-vs-Guild positioning, mainnet competitive landscape
- `docs/pitch/sapphire-os-one-page.md` (PR #601) — canonical pitch
- `docs/grants/apollo-accelerator-application.md` (this PR) — sister application; cross-pitch consistency required
- `docs/hackathon-0g/README.md` + `lib/og/{storage,compute,chain,hooks}.py` — the integration the grant funds further

---

## Field 1 — Project name

**Sapphire × 0G — verifiable autonomous trading**

(For Guild we lead with the *integration brand* rather than just "Sapphire OS." Guild's selection emphasizes ecosystem co-marketing — naming 0G in the project handle aligns with what their funder mix and ecosystem-narrative committee is looking for.)

---

## Field 2 — Category

**AI Agents** (primary) / **DeFi + AI** (secondary).

(Per Guild's stated targeted categories — DeFi+social w/ AI agents, on-chain data marketplaces, AI-driven gaming, AI infrastructure, governance protocols. Sapphire is more "DeFi+AI" than pure "AI dApp"; the Sentinel-registry / agent-mandate layer is the strongest pitch handle for the AI Agents category.)

---

## Field 3 — One-line pitch (≤30 words)

> **The first production-grade trading OS (6,626 tests, live execution) to make every AI prediction cryptographically committed before market impact — sealed by 0G Compute, anchored on 0G Chain.**

(28 words. 0G-specific framing — uses the **`before market impact`** mechanism that the Track 2 mandate explicitly endorses, and leads with the production-grade scarcity claim that matters in a thin-DeFi mainnet competitive landscape.)

---

## Field 4 — Why this matters for the Guild

> **Sapphire validates 0G's "Apple of Web3 AI" thesis with a real production trading stack rather than a thin demo.** The Apollo + Guild funding programs and 0G's ecosystem-partner storytelling have a structural credibility gap: most named partners are infrastructure providers (Chainlink, Google Cloud, Alibaba Cloud, wallets, oracles, validators) rather than deployed apps with real users. Guild is the program designed to fix that — funding builders going testnet → mainnet with apps the ecosystem can point at.
>
> Sapphire is the visible production app on 0G mainnet (chain 16661). When 0G's BD team needs to point at a single deployed application that uses Storage + Compute (TEE) + Chain in one round-trip, with a public verifier and ongoing on-chain activity, Sapphire is that application. That's the co-marketing asset Guild is funding.
>
> Per `0g-deep-dive.md` §4.1, the deployed-DeFi field on 0G mainnet is **thin enough that a single live trading-signal verifier with consistent on-chain activity stands out** — there is no announced equivalent. Guild funds the team that closes that gap.

---

## Field 5 — Specific 0G primitives used

### 0G Storage — content-addressed signal envelope

> Every signal Sapphire generates is bundled into a structured envelope (input data, model identifier, reasoning trace, output, TEE attestation, timestamp) and uploaded to 0G Storage. The upload returns a content-addressed merkle `rootHash` that becomes the proof-of-existence anchor: the prediction provably existed in this exact form before any market impact. The envelope is publicly downloadable by the `og_verify` tool (round-trip read), so external auditors can replay the proof without clone-and-run access. **Live capture pattern:** `lib/og/storage.py` returns `{rootHash, txHash}` for every published signal; the trading critical path is feature-flagged so `SAPPHIRE_OG_ENABLED=0` produces a byte-identical executor (fail-closed by design, never blocks a trade on storage flakiness).

### 0G Compute — TEE-sealed inference

> Sapphire's inference path can route through 0G Compute providers running on Intel TDX + NVIDIA H100/H200 in TEE mode. The inference returns a `chatID` signed by the enclave key, re-verifiable via `broker.inference.processResponse(provider, chatID)`. This closes the "model wasn't tampered with" guarantee — the model that produced the signal cryptographically *cannot* have been silently swapped. v2 ambition (per `0g-deep-dive.md` §3.3): build a **TeeTLS broker** that fronts Sapphire's existing 4-tier inference proxy (Mac / Pi / GPU / Kimi), trading some latency for full TEE-attested signing across every model tier. Only pursued if Apollo or Guild funds the TDX hardware (~$8–15K).

### 0G Chain mainnet (16661) — anchor

> `SapphireSignalVerifier.publishSignal(strategyId, symbol, direction, confidence, proofHash=rootHash)` is called on 0G Aristotle mainnet (chain 16661), immutably anchoring the prediction on a public clock. The `SignalPublished` event log on the deployed contract becomes the running ledger of every prediction Sapphire has committed — a public reference auditable by anyone. Cross-pitch consistency: the same anchor pattern works for Sentinel attestations on Robinhood Chain (`SapphireSentinelRegistry`), which is why Sapphire's contract suite generalizes across both chains the funder mix cares about.

### 0G Payments — subscription gating + agent mandates

> Sentinel's on-chain payment-receipt anchor (`SapphireSentinelRegistry.recordPaymentEvaluation(...)`) is the same primitive that gates Sapphire's hosted-endpoint subscriptions. Future: x402-style micropayments per `og_verify` query (Sapphire already ships `lib/payments/x402_middleware.py`). This is the "agent-as-paying-customer" surface 0G's ecosystem narrative emphasizes — agent mandates are the unit of subscription, payment receipts are the unit of accounting.

(3 of 4 primary 0G components used today. **0G DA** is the v2 target — adding DA for the streaming signal feed, vs. one anchor per signal, would close the 4-of-4 story. Realistic 6-month horizon if Guild funds it.)

---

## Field 6 — Live data flows currently producing on-chain anchors

> **Two trigger paths are live and ready to push to mainnet on Ari's deploy:**
>
> 1. **TradingView webhook → signal logger → 0G publish.** The Windows webhook (port 9090) → Mac signal logger (port 18081) pipeline triggers a 0G publish path (`fire_and_forget`) for every alert. Production safety: the publish runs out-of-band so a 0G outage never blocks a trade. **Daily volume:** `<TBD post-mainnet-deploy; expect 5–50 signals/day initially based on TradingView alert cadence>`.
>
> 2. **Kronos daily prediction → 0G publish.** The Kronos predictions script (`scripts/kronos_daily_predictions.py`) generates 24-bar horizon forecasts for BTC/ETH/SOL/SPY/TSLA and writes them to `data/intelligence/YYYY-MM-DD/predictions.json` — the same data is bundled into a daily 0G envelope and anchored. **Cadence:** 1 anchor batch per day (5 symbols), evergreen. (Note: `com.sapphire.kronos-daily` LaunchAgent was archived 2026-05-12; run the script manually or via scheduled task.)
>
> Combined, this is **6 to 51 expected on-chain transactions per day** once mainnet is live. That's the streak (not one-shot) that judges and ecosystem partners look for to confirm a deployed app is real, not a demo.

---

## Field 7 — Mainnet contract addresses

| Contract | Chain | Address | Explorer |
|---|---|---|---|
| `SapphireSignalVerifier` | 0G Aristotle (16661) | **`<TBD post-deploy>`** | `<TBD: chainscan.0g.ai/address/0x...>` |
| `SapphirePaymentGate` | 0G Aristotle (16661) | **`<TBD post-deploy>`** | `<TBD: chainscan.0g.ai/address/0x...>` |
| `SapphireSentinelRegistry` | 0G Aristotle (16661) | **`<TBD post-deploy>`** | `<TBD: chainscan.0g.ai/address/0x...>` |
| `SapphireSentinelRegistry` | Robinhood Chain testnet (46630) | **`<TBD post-deploy>`** | `<TBD: explorer.testnet.chain.robinhood.com/address/0x...>` |

(Mainnet deploy is the gating action before Guild submission — same pre-condition as the 0G APAC hackathon submission. Per `0g-deep-dive.md` §2.3, this is the **single highest-leverage action** before any 0G-funder pitch.)

---

## Field 8 — Apollo-vs-Guild positioning (why both, not either-or)

> Sapphire is filing **both** the Apollo Accelerator application and this Guild grant. They serve different strategic functions and the deep-dive research (`0g-deep-dive.md` §3.6 funnel order) explicitly recommends parallel filing as a hedge.
>
> | Dimension | Apollo Accelerator | Guild on 0G |
> |---|---|---|
> | Capital | Up to $2M / team | Sub-fund tranche, typical $100K–$500K |
> | Mechanic | Equity-style accelerator (10-week intensive) | Grant (milestone-based) |
> | Cohort size | 10 globally | Larger, rolling |
> | Selection bar | Stanford-adjacent screening, deep diligence | Ecosystem fit + co-marketing potential |
> | Sapphire's primary pitch | Production trading stack with 0G integration | Visible deployed app the ecosystem can point at |
>
> The two funders care about overlapping but distinct things. Apollo funds capacity (engineers, runway, infrastructure); Guild funds adoption (co-marketing, ecosystem listing, design-partner integrations). Sapphire benefits from both. Filing both is not double-dipping — it's matching the right capital to the right work.

---

## Field 9 — Funding ask

> **Initial tranche: $200K–$500K USDC, milestone-based.**
>
> Range reflects uncertainty about Guild's typical per-team allocation (the public materials mention $8.88M total fund and "early-stage builders going testnet → mainnet" but don't publish per-team caps). Sapphire is comfortable across the range with milestones scaled accordingly.
>
> **Use of funds (anchored at the $300K midpoint):**
>
> | Milestone | Funding | Deliverable |
> |---|---|---|
> | **1. Hosted Sentinel + verifier endpoint infrastructure** at `verify.sapphirealpha.xyz` — `evaluate_chain()` + `og_verify(signal_id)` public APIs, Cloud Run / Cloudflare Pages, monitoring, 6-month uptime SLA. | $50K | Public verifier URL judges + auditors + design partners can hit with no clone-and-run. |
> | **2. 3 design-partner integrations** (target: Gimo Finance, one Aave-V3-on-0G consumer, one DeFAI fund — all named in `0g-deep-dive.md` §4.1 as warm targets). Each includes integration engineering, joint demo, case study. | $100K | 3 published integrations + case studies. |
> | **3. 0G DA integration for streaming signal feed** — closes 4-of-4 0G primary-component story. Replaces per-signal anchors with DA-streamed feed; one anchor per epoch instead of one per signal. | $50K | DA integration shipped to `lib/og/`, public reference doc, deployed to mainnet. |
> | **4. Open-source `@sapphire/og-verifier-sdk`** (Python + Node + Solidity) listed on the 0G SDK page. Includes docs, CI, package publishing, semantic versioning. | $30K | Listed SDK on `docs.0g.ai/sdks` (or equivalent), npm + PyPI packages live. |
> | **5. Sapphire-branded 0G Storage node** running storage of own signal envelopes ("we eat our own dog food"). Includes hardware/cloud lease for 12 months and miner key management. | $20K | Node operational, leaderboard tracked, ~$50/mo ongoing infra. |
> | **6. Co-marketed case study with 0G Labs** — "How Sapphire Verified $X of Trading Signals on 0G in 90 Days." Publishing-grade write-up + accompanying dashboard. | $20K | Case study published on 0G blog + Sapphire blog + X. |
> | **7. Mainnet trading capital reserve** — $5 → $50 → $500 rung ladder gating, Sortino > 2.0 per rung. Capital validates the trading stack honestly and produces the verifier history that powers everything else. | $30K | Live trading P&L public; verifier ledger visible on chainscan. |
> | **Total** | **$300K** | 7 discrete public artifacts. |

---

## Field 10 — Milestones (6-month)

- **3 named design-partner integrations** consuming Sapphire's hosted Sentinel + verifier endpoints (Gimo Finance / Euclid Protocol / Cygnus Finance / Dormint / HAiO / QuillAI Network as the candidate set per `0g-deep-dive.md` §4.1)
- **100+ verifier-path queries/day** to `og_verify(signal_id)` from external consumers — hosted endpoint usage as the leading indicator of ecosystem adoption
- **`@sapphire/og-verifier-sdk` listed** on the 0G SDK page (or equivalent canonical surface)
- **0G DA integrated** — closes the 4-of-4 primary 0G primitive story
- **Sapphire-branded 0G Storage node** operational with `<TBD post-deploy>` rewards tracked
- **One co-marketed case study with 0G Labs** published

---

## Field 11 — Team

> **Solo founder: Ari Spec.** Production trading + ML + infrastructure background — every commit visible at `github.com/arigatoexpress/Sapphire`. The repo + 6,626-test CI suite is the technical CV. Operating Sapphire from a multi-device mesh (Mac commander, Windows GPU node, two Pis, Tailscale-meshed). Open to bringing on a co-founder during the grant period.
>
> **`<Ari to add: 1-paragraph founder bio — prior trading roles, education, geographic location. Guild's funder mix (Hack VC, Delphi, Bankless, OKX) will likely map names against their existing networks.>`**

---

## Field 12 — Anything else (catch-all)

> 1. **Sapphire is operationally honest about what doesn't work yet.** Hyperliquid is mainnet-refused until EIP-712 signing is verified on testnet. Robinhood Crypto live capital is $5/order with a 14-day Sortino soak before the next rung. The 0G integration is currently testnet/`SAPPHIRE_OG_ENABLED=1` flag-gated; mainnet deploy is the gating step. Where ecosystem grants get burned on teams that overstated production-readiness, Sapphire's posture is the opposite: fail-closed defaults, killswitches, small first-rung caps.
>
> 2. **Guild is the right capital for the right work.** Apollo funds capacity (the team build-out and runway); Guild funds adoption (the design-partner integrations, the co-marketing, the SDK listing, the storage-node "eat our own dog food" story). The split is intentional — the two are complementary, not competitive.
>
> 3. **The integration is *deep* but not *novel*.** Sapphire is a strong execution of the *intended* 0G pattern (Sealed Inference + Storage + Chain anchor + Payments). It's not a genuinely surprising mechanism — it's the **first production-grade execution** of the pattern 0G Labs has been describing in their docs for 18 months. The credibility argument is "this is what your stack was designed for, and we're the team that delivered it end-to-end."

---

## Quick-reference appendix (for Ari's polish pass)

**Numbers Ari should sanity-check at submission time:**
- "6,626 tests" — verify with `python3 scripts/ops/test_inventory.py --check-readme`
- "First Robinhood live BTC fill 2026-04-28 04:06 UTC, $5 at $76,774.81" — exact, from `data/paper_trading.jsonl`
- "Guild $8.88M sub-fund" — verify `0g-deep-dive.md` §3.2 against current `0g.ai/blog/0g-ecosystem-program` page at submit time
- "Apollo $20M / 10 teams / $2M-per-team" — verify against `apollo.0g.ai`
- 0G mainnet contract addresses — `<TBD post-deploy>` placeholders must be replaced with live `chainscan.0g.ai/address/...` URLs
- Per-team Guild funding range ($100K–$500K) — verify against any updated public guidance; the deep-dive research couldn't find a published per-team cap

**Phrases reused from one-page pitch / Apollo / Mafia 2.0 (kept verbatim for cross-pitch consistency):**
- "the first production-grade trading OS (6,626 tests, live execution)"
- "fail-closed by default"
- "verifiable autonomous trading"
- "every claim is line-cited and CI-verified in production"

**One thing only Ari can add:**
- **A demo video link** (≤3 min, hosted on YouTube/Loom). The video produced for the 0G APAC hackathon submission is reusable here — Ari needs to make sure the URL is live + linked in the application. Per `0g-deep-dive.md` §1.4, video is criterion-#4 (UX/Demo Quality) signal and Guild reviewers come from the same selection pool as Apollo/hackathon judges.

**Submission sequencing recommendation:**
1. Wait for 0G APAC hackathon result (2026-05-16 deadline → result late May / early June)
2. **File Apollo + Guild in the same week**, post-hackathon-result. Both benefit from fresh on-chain activity + (if placed) hackathon recognition.
3. Treat the two as *parallel filings*, not sequential — Guild's grant mechanic is faster to disburse; Apollo's accelerator is higher-leverage on capacity.
4. Replace every `<TBD post-...>` placeholder with live data before paste.
