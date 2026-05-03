# Sapphire × 0G — 5-Slide Pitch Deck

**Hackathon:** 0G APAC Hackathon · Track 2 — Agentic Trading Arena (Verifiable Finance)
**Deadline:** 2026-05-16 23:59 UTC+8
**Prize pool:** $150K · 1st $45K, 2nd $35K, 3rd $20K
**Submission anchor:** PR [#525](https://github.com/arigatoexpress/Sapphire/pull/525)

---

## Slide 1 — The 1-line pitch

# Trading agents must prove their predictions before market impact.

Sapphire makes every signal cryptographically provable on 0G — sealed
inference, content-addressed envelope, on-chain anchor — *before anyone
sees the trade*.

**Why now:** AI trading is a $T market. The bottleneck isn't predictions.
It's *trust in predictions*. 0G is the only stack that ships sealed inference
+ storage + chain in one place. We use all three.

---

## Slide 2 — The technical novelty

**What makes this impossible to copy in a weekend:**

| Layer | What it proves | What's required |
|---|---|---|
| **0G Compute** | Inference happened in a TEE we don't control | `broker.inference.processResponse(provider, chatID)` round-trip |
| **0G Storage** | Signal envelope hasn't been mutated | Merkle rootHash from real upload |
| **0G Chain (16661)** | Hash existed at block N | `SapphireSignalVerifier.publishSignal(...)` mainnet tx |
| **`og_verify` round-trip** | Anyone can re-derive | 4 independent checks against live network |

**The asset isn't the contract. It's the round-trip.** Anyone with a 0G
RPC and our public verifier address can re-derive the audit trail with
one CLI call. That's what "verifiable" means — not promised, *re-derivable*.

**What we ship that nobody else does:**
- Fire-and-forget hook into a 5,995-test live trading critical path
- Subprocess isolation (`OG_PRIVATE_KEY` never crosses into Python memory)
- Feature-flagged (`SAPPHIRE_OG_ENABLED=1`) — opt-in, byte-identical critical
  path with flag unset
- 56 unit tests covering envelope determinism, hook safety, subprocess
  contract — they ran in CI before the deploy script existed

---

## Slide 3 — Live demo · contracts · code

| Asset | Link |
|---|---|
| **Live demo** | [hack.sapphirealpha.xyz](https://hack.sapphirealpha.xyz) — expand the 0G card |
| **3-min recorded demo** | [docs/hackathon-0g/demo-script-v2.md](https://github.com/arigatoexpress/Sapphire/blob/main/docs/hackathon-0g/demo-script-v2.md) |
| **60s judging-room cut** | [docs/hackathon/0g/video-script.md](https://github.com/arigatoexpress/Sapphire/blob/main/docs/hackathon/0g/video-script.md) |
| **GitHub PR** | [arigatoexpress/Sapphire#525](https://github.com/arigatoexpress/Sapphire/pull/525) (merged) — `feat(0g): verifiable trading layer` |
| **Smoke script PR** | [#547](https://github.com/arigatoexpress/Sapphire/pull/547) — one-shot `deploy → publish → verify` |
| **Demo recording PR** | [#572](https://github.com/arigatoexpress/Sapphire/pull/572) |
| **Contract** | `SapphireSignalVerifier` on 0G Chain mainnet · chainId **16661** · [chainscan.0g.ai](https://chainscan.0g.ai) |
| **Source contracts** | [`contracts/SapphireSignalVerifier.sol`](https://github.com/arigatoexpress/Sapphire/blob/main/contracts/SapphireSignalVerifier.sol) |

**Live JSON probe (against the live verifier on chain 16661):**

```bash
curl -X POST https://evmrpc.0g.ai \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_getCode",
       "params":["<verifier_addr>","latest"],"id":1}'
```

→ returns deployed bytecode. Frontend embeds this probe live.

---

## Slide 4 — Judging-criteria match (verbatim from HackQuest)

| 0G criterion | Verbatim sponsor wording | Our specific implementation |
|---|---|---|
| **0G Technical Integration Depth & Innovation** | "Extent of adoption of 0G components, and innovative solutions to AI / on-chain pain points." | All three primitives wired (Compute + Storage + Chain). The novelty is the **round-trip verifier** — most projects use one primitive; we cycle all three and prove the chain ties them together. |
| **Technical Implementation & Completeness** | "Functional integrity, code quality, and mandatory on-chain deployment" | Mainnet 16661 deploy + 56 unit tests for the integration alone + 6,567 repo-wide + ruff/CI green + `validate_tool_registry.py` invariants pass. |
| **Product Value & Market Potential** | "Market fit, problem-solving capability, user value, and growth roadmap." | Trading-agent provability is a $T market gap. Roadmap: integrate into `services/alpha/` critical path (already wired, feature-flagged) → Apollo Accelerator → Guild on 0G. |
| **User Experience & Demo Quality** | "Intuitiveness and user-friendliness of UI/UX; clarity and persuasiveness of pitch and demo" | One-CLI-call verify (`og_verify.py`). One-page judge view at `hack.sapphirealpha.xyz`. 60s pitch + 3-min deep-dive. |
| **Team Capability & Documentation** | "Team background, quality of open‑source code and README." | Solo founder, public repo. README + design doc + operator runbook + submission checklist + handoff doc all under `docs/hackathon-0g/`. 6 supporting docs total. |
| **Critical requirement: ≥1 0G component integrated** | "Projects failing this face point deductions or disqualification." | Three integrated. |

---

## Slide 5 — Roadmap post-hackathon

**Week 1:** Apollo Accelerator application (post-mainnet activity proof).
**Week 2:** Sentinel + 0G — the chain-health gate (already shipped for
MegaETH/Arbitrum/Optimism in PRs #546/#557/#569) gets a 0G chain dimension.
**Month 1:** `og_verify` published as a standalone npm/PyPI package — turn
the round-trip into a primitive other 0G builders can drop into their
agents.
**Month 3:** Hardware wallet flow for `OG_PRIVATE_KEY` (today subprocess
isolated, tomorrow Ledger-signed). Removes the last "operator could go
rogue" attack surface.
**Quarter 2:** Guild on 0G — Sapphire as a Guild operator running
verifiable trading strategies for non-technical capital. The provability
layer is the *product*, not just the engineering.

**The integration is the asset. The hackathon is the distribution event.**

---

**Sources:**
- HackQuest hackathon page: https://www.hackquest.io/hackathons/0G-APAC-Hackathon
- 0G docs: https://docs.0g.ai
- Internal research: `docs/research/hackathon-strategy/0g-deep-dive.md`
