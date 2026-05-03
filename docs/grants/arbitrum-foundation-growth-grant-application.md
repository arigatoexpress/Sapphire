# Arbitrum Foundation Growth Grant — Sapphire Sentinel application draft

**Status:** DRAFT — Ari to polish + submit when the post-London-buildathon window opens (rolling-basis program; submit ~1 week after London Buildathon results regardless of placement).
**Program:** Arbitrum Foundation Grants — **Growth Grants up to $50,000 USDC**, milestone-based, rolling-basis review by community-elected domain allocators.
**Track:** **Infrastructure & Tools** (less-crowded lane than dApps; Sentinel is an agent-safety primitive, not a consumer app).
**Application URL:** <https://arbitrum.foundation/grants> (also `arbitrumhub.io/grant-hub`; verify the live form at submit time).
**Sequencing:** apply **post-Arbitrum London Buildathon** (submission deadline 2026-06-14, results 2026-06-17). The Buildathon submission is the strongest possible track-record signal — even non-winning, the deployed contract + demo video + threat model becomes the application portfolio.
**Source material referenced when drafting:**
- `docs/research/hackathon-strategy/robinhood-arbitrum-deep-dive.md` (PR #560) — grant program parameters, Sentinel positioning
- `docs/hackathon/sapphire-sentinel-london-2026.md` — Sentinel hackathon pitch
- `docs/pitch/sapphire-os-one-page.md` (PR #601) — canonical pitch
- `lib/hackathon/sentinel.py` + `lib/hackathon/chain_health_gate.py` + `contracts/SapphireSentinelRegistry.sol` — the implementation under the grant ask

---

## Field 1 — Project name

**Sapphire Sentinel**

(Not "Sapphire OS." For this grant we're submitting the *primitive*, not the platform — Sentinel is the on-chain agent-safety + chain-health-gate library that lives on Arbitrum-family chains. Sapphire OS is the parent project and operator; Sentinel is the public-good infrastructure component the grant funds.)

---

## Field 2 — Category

**Infrastructure & Tools** — agent-safety primitive consumed by other Arbitrum-deployed apps, not a consumer-facing dApp.

---

## Field 3 — One-line pitch (≤30 words)

> **Sapphire Sentinel is an open-source agent-safety primitive on Arbitrum-family chains: pre-trade chain-health gate + on-chain payment-receipt anchor that lets autonomous agents transact without becoming the next Curve-pool implosion.**

(29 words. Frames Sentinel as a *primitive other agents depend on* — exactly what Infrastructure & Tools funds.)

---

## Field 4 — Problem statement

> Autonomous AI agents on Arbitrum-family chains (Arbitrum One, Robinhood Chain, future Orbit chains) are starting to transact with real capital — paying for compute via x402, executing tokenized-stock trades, settling A2A payments. The ecosystem currently lacks a **standardized pre-trade safety check**: agents trade on signals without verifying the underlying chain state hasn't broken (USDM depeg, Aave-pause, frozen reserve, oracle drift), and there's no canonical place to anchor a tamper-evident receipt of *why* an agent action was approved or refused.
>
> Without this primitive, every autonomous-agent project either (a) reinvents the wheel privately and ships their own brittle policy layer, or (b) ships nothing and crosses fingers. The result is exactly the systemic risk profile the EVM ecosystem was supposed to outgrow: opaque, unauditable, and one prompt-injection away from a $1.99 → $1M misdirection.

---

## Field 5 — Solution

> **Sapphire Sentinel is two things in one repo:**
>
> 1. **A chain-health gate primitive (open-source Python library)** — `evaluate_chain(chain_id)` reads multi-chain state (peg deviation, lending-pool freeze flags, oracle staleness, GMX V2 OI, Aave reserve health) in sub-second from the chain itself, and returns a structured verdict with a tamper-evident reason hash. Currently covers MegaETH, Arbitrum, Optimism (5 chain × protocol read cells live as of 2026-05-03; see `lib/chains/`).
>
> 2. **An on-chain agent-mandate + payment-receipt anchor (`SapphireSentinelRegistry.sol`)** — non-custodial Solidity contract on Arbitrum Orbit chains. Operator-only writes, no withdraw path, fail-closed on every revert path. `recordPaymentEvaluation(mandate, payment, riskFlags, decision)` anchors the gate's verdict — including rejected attempts (e.g., prompt-injection blocks) — so attack attempts are cryptographically anchored evidence, not just log lines.
>
> The two compose: an agent calls the chain-health gate, gets a verdict, anchors the receipt, and (if approved) proceeds. Other Arbitrum-deployed apps consume both as a hosted service (`sentinel.sapphirealpha.xyz`) or self-host the library — they don't have to rebuild policy layers from scratch.

---

## Field 6 — Why Arbitrum specifically

> **Robinhood Chain sits on Arbitrum Orbit (chain ID 46630).** Sapphire already ships Sentinel + chain-health gate + the `SapphireSentinelRegistry` contract targeted at the Orbit deploy. The London Buildathon explicitly carves out "at minimum, 1 of 3 prizes is reserved for a project building on Robinhood Chain" — Sentinel is purpose-built for that lane and ships standard Arbitrum precompile awareness (ArbSys, ArbGasInfo) plus Orbit bridge ABIs day-one.
>
> **Tokenized-RWA story is already wired.** The Robinhood Chain testnet ships 5 tokenized stocks (TSLA, AMZN, PLTR, NFLX, AMD) plus USDG; Sentinel's policy evaluator already enumerates these (`ROBINHOOD_STOCK_TOKENS` in `lib/hackathon/sentinel.py:26-32`). When a stock-trading agent on Robinhood Chain wants pre-trade safety, Sentinel is the only library that already speaks the contract addresses.
>
> **Cross-Orbit reusability.** A primitive that ships on one Arbitrum-family chain ships on all of them with minimal adapter work — the chain-health gate is chain-agnostic by design (the `evaluate_chain(chain_id)` signature is the entire surface). Funding Sentinel on Arbitrum is funding agent-safety infra for the entire Orbit ecosystem, not a single chain.
>
> **No competing primitive exists today.** Per the deep-dive research (`robinhood-arbitrum-deep-dive.md` §4), no announced equivalent ships on any Arbitrum-family chain. Sentinel can become the canonical agent-safety library before competitors arrive — the same window-of-opportunity logic that drove the Foundation's earlier dApp-track grants.

---

## Field 7 — Use of funds (capped at $50K USDC, milestone-based)

| # | Milestone | Funding | Rationale |
|---|---|---|---|
| 1 | **Hosted Sentinel endpoint infrastructure** — `evaluate_chain()` + `recordPaymentEvaluation()` API at `sentinel.sapphirealpha.xyz` with rate limits, monitoring, multi-chain RPC quotas (Alchemy/QuickNode). Includes Cloudflare front, dashboard, and 6-month uptime SLA. | **$15K** | Lets other Arbitrum-deployed apps consume Sentinel without standing up their own RPC stack; required before realistic 5+ design-partner adoption. |
| 2 | **One named design-partner integration** end-to-end (target: an autonomous-agent project on Robinhood Chain or Arbitrum One — `<TBD: Ari to name 1–2 candidates from outreach>`). Includes integration engineering, joint demo, and case-study write-up. | **$10K** | Closes the "no design partner named publicly" gap from the Buildathon pitch (per `robinhood-arbitrum-deep-dive.md` §3.4 PMF row). PMF claim becomes evidenced. |
| 3 | **Halmos formal verification of `SapphireSentinelRegistry.sol`'s spend-cap accumulator** — invariants on `recordPaymentEvaluation`'s spend-limit check and 2-step operator transfer. Public Halmos report committed to repo. | **$10K** | Smart-contract-quality grant criterion #1 from the Buildathon (and grants criterion #1 generally). Formal verification of the one mutable accumulator path is the highest-leverage hardening for the cost. |
| 4 | **Audit pass on 3 Sapphire contracts** — `SapphireSentinelRegistry.sol`, `SapphireSignalVerifier.sol`, `SapphirePaymentGate.sol`. Single-firm engagement (target: ChainSecurity, Spearbit, or zellic at $5K/contract for a focused review). | **$15K** | Required for production credibility. The contracts are small (188 LoC for Sentinel), so a focused audit at this budget is realistic — full audit-firm engagements typically start at $50K+ but the surface here is narrow. |
| **Total** | | **$50K** | At grant cap. |

(Each milestone is a discrete deliverable with a public artifact — auditor report, Halmos output, design-partner case study, hosted endpoint URL. The Foundation's domain allocators can verify completion before releasing each tranche.)

---

## Field 8 — Milestones

### 6 months (Q1–Q2 2026)
- **5+ Arbitrum/Robinhood-deployed apps** integrating Sentinel as their pre-trade safety check (open-source library + hosted endpoint with the same `evaluate_chain(chain_id)` API surface)
- `SapphireSentinelRegistry` deployed on **both Robinhood Chain and Arbitrum One** — two-chain deployment is "now you're an Arbitrum-native protocol" signal per `robinhood-arbitrum-deep-dive.md` §5.1
- Halmos verification + audit reports public on the repo
- One design-partner case study published

### 12 months (Q2–Q4 2026)
- **50+ Arbitrum/Robinhood-deployed apps** integrating Sentinel
- **$1M+ TVL gated by Sentinel attestations** across design-partner integrations
- Sentinel listed in canonical Arbitrum ecosystem directories (`arbitrumhub.io`, Foundation ecosystem page) as the agent-safety primitive
- **Stylus port of the policy evaluator** (Rust → WASM) — credible second-grant pitch under Stylus adoption incentives, per `robinhood-arbitrum-deep-dive.md` §5.1 path 5
- Sentinel-as-a-SaaS hosted tier graduated to paid (x402 micropayments per check; Sapphire already ships `lib/payments/x402_middleware.py`)

---

## Field 9 — London Buildathon outcome (evidence attached)

> **Arbitrum London Open House Buildathon — Best Agentic Project track + Robinhood Chain reserved-prize lane.**
>
> Submission: **`<placement TBD post-2026-06-17>`**.
>
> Submission portfolio is the strongest evidence Sentinel is real:
> - Live Robinhood Chain testnet deploy of `SapphireSentinelRegistry.sol` (address: **`<TBD post-deploy — chain ID 46630, explorer.testnet.chain.robinhood.com/address/0x...>`**)
> - 90-second demo video (3 deterministic modes: happy path, prompt-injection block, MegaETH chain-health depeg block; each in <5 seconds)
> - `forge test` coverage report ≥95% on the Registry contract
> - Slither CI output committed
> - Threat-model section enumerating the 6 attack vectors Sentinel addresses (mandate expiry, domain spoofing, action escalation, budget exhaustion, prompt injection, secret egress)

(Even if Sentinel doesn't place at the Buildathon, the deployed contract + demo + threat model is the application portfolio for this grant, per `robinhood-arbitrum-deep-dive.md` §5.2 path 1.)

---

## Field 10 — Existing on-chain footprint

- **`SapphireSentinelRegistry`** — Solidity 0.8.13, 188 LoC, non-custodial, operator-only writes, 2-step operator transfer.
  - Deployed on **Robinhood Chain testnet (chain 46630)** — address: **`<TBD post-deploy>`** (target: pre-funded operator key via `faucet.testnet.chain.robinhood.com/`, deploy via `scripts/deploy_robinhood_chain.py`)
  - Explorer: **`<TBD: explorer.testnet.chain.robinhood.com/address/0x...>`**
- **`SapphireSignalVerifier`** — companion contract anchoring trading signals; deployed on 0G Aristotle mainnet (chain 16661) — address: **`<TBD post-0G-deploy; cross-pitch consistency with Apollo + Guild applications>`**
- **`SapphirePaymentGate`** — micropayment gate complementing the agent-mandate flow; testnet-deployed, mainnet pending.

(All three contracts are under `contracts/`; deployment scripts at `scripts/deploy_robinhood_chain.py`. Bytecode + ABIs publicly verifiable on Blockscout.)

---

## Field 11 — Production credibility (parent project)

> Sentinel is a public-good extraction from **Sapphire OS** — a 18-month production trading OS with:
>
> - **6,626 collected tests** (6,059 unit + 567 plugin per `python3 scripts/ops/test_inventory.py --check-readme`, 2026-05-03)
> - 109 plugin tools on disk · 16 registered agent-facing tools · 14 hermes-agent skills
> - 50 dashboard pages · 20 active LaunchAgents · 22 scheduled tasks
> - **Live execution:** Robinhood Crypto $5/order pilot rung (first live BTC fill 2026-04-28 04:06 UTC at $76,774.81), Hyperliquid testnet (mainnet refused until EIP-712 signing verified)
> - Repo: `github.com/arigatoexpress/Sapphire` (public)
>
> The Foundation isn't funding a v0 build — it's funding the public-good extraction of a primitive that's already being dogfooded inside a production system.

---

## Field 12 — Team

> **Solo founder: Ari Spec.** Production trading + ML + infrastructure background — every commit visible at `github.com/arigatoexpress/Sapphire`. Operating Sapphire from a multi-device mesh (Mac commander, Windows GPU node, two Pis, Tailscale-meshed). Open to bringing on a co-founder during the grant period — specifically someone with cross-chain protocol-engineering experience.
>
> **`<Ari to add: 1-paragraph founder bio — prior trading roles, education, geographic location. Useful for the Foundation's domain-allocator review even if the form doesn't explicitly require it.>`**

---

## Field 13 — Anything else (catch-all)

> 1. **Sentinel is fail-closed for live capital, fail-open for demo flows.** During buildathon demos we let the gate fall through on RPC flake (`allow_when_unavailable=True`) so judges don't see a phantom-block. In the live executor path it's the inverse — observed distress blocks the trade and a stale RPC blocks the trade. This split is intentional and documented; it's the right posture for a public-good safety primitive.
>
> 2. **The grant is for the *primitive*, not Sapphire's trading P&L.** Sapphire's trading capital ladder is funded separately by the trading OS itself — this grant funds the *open-source library + audit + endpoint infrastructure* that other Arbitrum apps depend on. The deliverables are public goods.
>
> 3. **Buildathon win is not required.** The submission portfolio (deployed contract + demo + threat model) is the application portfolio either way. Per `robinhood-arbitrum-deep-dive.md` §5.2, "conversion rate on rolling-basis grants for credible submissions is meaningfully higher than for cold applications" — the Foundation's grant program is the natural funnel after the Buildathon regardless of placement.

---

## Quick-reference appendix (for Ari's polish pass)

**Numbers Ari should sanity-check at submission time:**
- "6,626 tests" — verify with `python3 scripts/ops/test_inventory.py --check-readme`
- "188 LoC for `SapphireSentinelRegistry.sol`" — verify with `wc -l contracts/SapphireSentinelRegistry.sol`
- "5 chain × protocol read cells live" — verify against `lib/chains/megaeth/protocols.py`, `lib/chains/arbitrum/`, `lib/chains/optimism/`
- "First Robinhood live BTC fill 2026-04-28 04:06 UTC, $5 at $76,774.81" — exact, from `data/paper_trading.jsonl`
- All `<TBD post-...>` placeholders — replace with live addresses + explorer URLs before paste

**Phrases reused from one-page pitch / Mafia 2.0 (kept verbatim for cross-pitch consistency):**
- "fail-closed by default"
- "the next Curve-pool implosion"
- "every claim is line-cited and CI-verified in production"

**One thing only Ari can add:**
- **A named design partner for milestone #2.** The grant ask anticipates one named integration partner (~$10K of the $50K). Ari should slot in 1–2 candidates from outreach (e.g., a specific autonomous-agent team on Robinhood Chain or Arbitrum One) before submit. Without a named partner, the milestone reads as theoretical.

**Submission sequencing recommendation:**
1. Wait for London Buildathon result (2026-06-17)
2. Within 1 week of result, file this grant — fresh submission portfolio is the strongest single piece of evidence
3. Rolling-basis review means timing flexibility, but earlier = first-mover among Buildathon alumni
4. File **independently** of the Apollo + Guild applications (different ecosystems, different funding mechanics, not mutually exclusive)
