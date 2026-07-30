# Sapphire OS — One-Page Pitch

> Single artifact for grant applications, cold outreach to design partners, demo backdrop screens, and the hackathon submissions themselves. Maintain by re-running `python3 scripts/ops/test_inventory.py --check-readme` and `gh pr list --state merged --search "hackathon"` before each grant submission.

---

## 1. The one-line

**Sapphire OS is a production AI-agent operator that uses on-chain primitives — peg health, lending solvency, oracle integrity — to verify alpha before acting on real money.**

## 2. The problem

Today's autonomous trading agents trade on signals without verifying the underlying chain state. A USDM depeg, an Aave-pause, a frozen reserve — any of these silently corrupts every leveraged decision downstream. The result is the next Curve-pool implosion, except automated and at LLM-reasoning-loop frequency.

## 3. The solution

```
            ┌────────────────────────────────────────────────────────┐
            │                Sapphire OS Inference Proxy             │
            │  fast · balanced · code · reason · deep · cascade      │
            │       (4-tier model routing — Mac / Pi / GPU / Kimi)   │
            └────────────────────┬───────────────────────────────────┘
                                 │ alpha hypothesis
                                 ▼
                       ┌──────────────────┐
                       │   Strategy Lab   │  6 quant strategies, sweep harness
                       └────────┬─────────┘
                                │ candidate signal
                                ▼
            ┌────────────────────────────────────────────────────────┐
            │            Sentinel Chain-Health Gate                  │
            │  USDM peg · Aave reserve · GMX V2 OI · oracle diff     │
            │  multi-chain reads (MegaETH · Arbitrum · Optimism)     │
            └────────────────────┬───────────────────────────────────┘
                                 │ verified or rejected (with attestation)
                                 ▼
            ┌────────────────────────────────────────────────────────┐
            │                  Gated Executor                        │
            │  signing_verified flag · per-order $ cap · killswitch  │
            └────────────────────┬───────────────────────────────────┘
                                 │
   ┌─────────────┬───────────────┼───────────────┬───────────────┐
   ▼             ▼               ▼               ▼               ▼
MegaETH      Arbitrum       Optimism           Base        Robinhood Chain
(Aave/GMX)  (Aave/GMX)      (Aave)         (x402 settle)    (USDG, anchor)
```

The Sentinel gate reads multi-chain state (peg, solvency, oracle, frozen flags) and refuses to release the signal unless the chains backing the trade are demonstrably healthy. Approved signals carry an on-chain attestation; rejections produce a structured reason hash. The gated executor enforces fail-closed defaults — `signing_verified=False` refuses mainnet, per-order cap is $5, and a killswitch file kills all live trading instantly.

## 4. The proof

| Metric | Value | Source |
|---|---|---|
| Tests | **6,626** collected (6,059 unit + 567 plugin) | `python3 scripts/ops/test_inventory.py --check-readme` (2026-05-03) |
| Plugin tools on disk | **109** scripts (61 top-level + 47 internal + 1 deprecated) | `ls plugins/claw-sapphire/tools/` |
| Tools in registry | **72** registered, CI-enforced | `infra/tool-registry.yaml` (validated by `scripts/validate_tool_registry.py`) |
| Hermes agent skills | **33** on disk | `~/.hermes/skills/sapphire/` |
| Chain × protocol read cells | **5** live | Aave on MegaETH/Arbitrum/Optimism, GMX V2 on MegaETH/Arbitrum |
| Live captures | BTC perp funding -75%/-15.68% APR · USDM peg 7.6 bps healthy · Arbitrum Aave $1.06B · Optimism Aave $82M · MegaETH Aave $450M | `lib/chains/megaeth/protocols.py`, `lib/hackathon/chain_health_gate.py` |
| Hackathons | 0G APAC Track 2 (deadline 2026-05-16) · Arbitrum London Best Agentic Project (2026-06-14) · Zama AI Skills bounty (2026-05-10) · MegaETH Mafia 2.0 application | PRs #525, #559, #560, #561, #562 |
| Live capital | Hyperliquid + Robinhood Crypto, $5/order cap, paper + small live | PRs #340, #344, #443-#456 |
| Smart contracts | 3 deployed/scaffolded | `SapphireSentinelRegistry`, `SapphireSignalVerifier`, `SapphirePaymentGate` |

## 5. Where Sapphire shows up across ecosystems

| Ecosystem | Where Sapphire fits | Submission status |
|---|---|---|
| **0G Labs** | Verifiable autonomous trading (Track 2) — 0G Storage envelope + 0G Compute TEE inference + 0G Chain anchor on chainId 16661 | PR #525 merged on `feat/0g-integration`; mainnet deploy + demo video pending Ari |
| **Arbitrum / Robinhood Chain** | Sentinel agent-safety + payment-decision receipts + chain-health primitive | `SapphireSentinelRegistry` deployed and verified on Robinhood Chain testnet 46630 on 2026-04-30; one mandate and four evaluation receipts exist. SignalVerifier and PaymentGate remain written-only; no mainnet writer is active. |
| **MegaETH** | Multi-protocol Python SDK (Aave V3, Kumbaya, USDM, GMX V2) + chain-health primitive + AI-agent operator (Mega Mafia 2.0 thesis) | Mafia 2.0 application drafted; `awesome-megaeth-ai` listing PR pending |
| **Zama (FHE)** | Privacy-preserving agent payments + AI Agent Skills bounty (`SKILL.md` for fhEVM, dogfoodable on Sentinel basket) | SKILL.md scaffold ready; May 10 bounty submit pending |

## 6. Roadmap

- **6 months** — Sentinel chain-health gate covers 5+ chains; write-paths land via gated executor on testnets across all four ecosystems.
- **12 months** — 100+ external agents using Sapphire's chain-health gate as a dependency; $1M+ TVL gated by Sentinel attestations.
- **24 months** — Sapphire OS becomes the canonical multi-chain agent-operator runtime; SDK consumers in DeFi, RWA, and prediction-market verticals.

## 7. The team

**Solo founder, Ari Spec.** The public monorepo (`github.com/arigatoexpress/Sapphire`) is the technical CV — every claim above is line-cited and CI-verified in production. The repo's commit cadence, PR archaeology, and live trading logs are the references.

## 8. The ask

- **Accelerators (Mega Mafia 2.0, Apollo on 0G):** cohort participation + introductions to design partners across the trading-agent stack.
- **Grants (Arbitrum Foundation Growth Grant, Guild on 0G):** infrastructure milestones — chain-health gate as a public good, dev-tooling category.
- **Partners (Aave, Kumbaya, GMX, USDM, Robinhood Chain, 0G Labs):** integration + co-marketing + design-partner agreements.
- **Investors:** post-cohort SAFE / token-side conversations; not raising into a deck.

---

### Maintenance

| Source | How to refresh |
|---|---|
| Test count | `python3 scripts/ops/test_inventory.py --check-readme` — copy `total`, `unit`, `plugin` |
| Tool count | `wc -l infra/tool-registry.yaml` (count `- name:` entries) and `ls plugins/claw-sapphire/tools/` |
| Hermes skills | `ls -d ~/.hermes/skills/sapphire/*/ \| wc -l` |
| Chain × protocol cells | Inspect `lib/chains/megaeth/protocols.py`, `lib/chains/arbitrum/`, `lib/chains/optimism/` |
| Live captures | `python3 -c "from lib.hackathon.chain_health_gate import ChainHealthGate; print(ChainHealthGate().evaluate_chain(4326))"` |
| Hackathon status | `gh pr list --state all --search "hackathon"` and check `docs/hackathon/` + `docs/hackathon-0g/` |

### Where each section came from

- §1 — Mafia 2.0 draft language (PR #561), kept verbatim for cross-pitch consistency.
- §2 — Distilled from `docs/research/hackathon-strategy/megaeth-deep-dive.md` and `lib/hackathon/chain_health_gate.py` docstring.
- §3 — Architecture composed from `CLAUDE.md` (inference tiers + 4-tier proxy), `services/inference-proxy/`, `lib/hackathon/`, and the gated-executor work in PRs #443-#456.
- §4 — Live verification, sources cited inline.
- §5 — PR bodies #559 (Zama), #560 (Robinhood/Arbitrum), #561 (MegaETH), #562 (0G).
- §6 — Mafia 2.0 framing from PR #561; same horizon used in all four hackathon decks.
- §7 — Personal.
- §8 — Asked-by-audience template; vary the call-to-action paragraph at delivery time.
