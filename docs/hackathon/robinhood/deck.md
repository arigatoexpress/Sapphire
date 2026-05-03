# Sapphire Sentinel · Robinhood London — 5-Slide Pitch Deck

**Hackathon:** Arbitrum Open House London Buildathon
**Categories targeted:**
- AI Agentic Category — $15K total (Robinhood Chain reserved slot)
- Robinhood Chain Innovation Award — $30K (Founder House, exclusive to Robinhood Chain projects)
**Timeline:** Buildathon starts 2026-05-25 · Founder House 2026-07-10 → 2026-07-12
**Submission anchors:** PRs [#544](https://github.com/arigatoexpress/Sapphire/pull/544), [#546](https://github.com/arigatoexpress/Sapphire/pull/546), [#547](https://github.com/arigatoexpress/Sapphire/pull/547), [#553](https://github.com/arigatoexpress/Sapphire/pull/553), [#555](https://github.com/arigatoexpress/Sapphire/pull/555), [#556](https://github.com/arigatoexpress/Sapphire/pull/556), [#567](https://github.com/arigatoexpress/Sapphire/pull/567), [#568](https://github.com/arigatoexpress/Sapphire/pull/568)

---

## Slide 1 — The 1-line pitch

# Agent safety on the chain Robinhood operates.

Sentinel is the policy + privacy + payment gate that screens every
intelligence request an autonomous agent makes — prompt injection, secret
exfiltration, mandate violation, **and chain-state degradation** — and
anchors every decision (including rejected attacks) on Robinhood Chain
testnet (46630).

**Why now:** Robinhood is launching a chain. The first agents that run on
it will define the safety norms for everything that follows. We built the
gate. Robinhood operates the rails. Match made.

---

## Slide 2 — The technical novelty

**What makes this impossible to copy in a weekend:**

| Layer | What it proves | Implementation |
|---|---|---|
| **Policy gate** | Prompt injection / secret egress / mandate violation are caught *before* tx | `lib/hackathon/sentinel.py` — 18-test Forge suite (PR #567) |
| **Privacy gate (Zama mock)** | Hidden basket weights never leave the enclave-mock; result + risk hashes are deterministic | `lib/hackathon/privacy_mock.py` (PR #544 — fhEVM mock) |
| **Chain-health gate** | Alpha that references degraded chains is refused | `lib/hackathon/chain_health_gate.py` reads MegaETH USDM peg + Aave V3 reserves on chain 4326 (PR #546) |
| **On-chain anchor** | Every decision (approval *and* rejection) is committed to chain 46630 | `SapphireSentinelRegistry.recordPaymentEvaluation(...)` |
| **Payment gate** | $5/order cap, mandate hash, allowed-domains list — all on chain | `SapphirePaymentGate.sol` |
| **Multi-chain composition** | One agent runs across MegaETH (4326) + Arbitrum (42161) + Optimism (10) + Robinhood Chain (46630) | Same primitive, ported in <1 day per chain (PRs #557, #569) |

**The novelty isn't agent safety — it's *attestation of attempted attacks*.**
Most safety systems silently drop bad requests. We anchor them on chain so
the auditor a year later can prove the attack happened *and* was caught.

**Demo toggles (operationally clever):**
- `SENTINEL_DEMO_FORCE_INJECTION=1` (PR #568) — flips the gate into "demo
  mode" where an injection payload always trips. Lets us record a clean
  "BLOCKED" frame without hand-crafting an attack.
- `SENTINEL_DEMO_FORCE_DEPEG=1` (PR #555) — flips the chain-health side.
- Both together — the 3-flag stack from the 90s cut.

---

## Slide 3 — Live demo · contracts · code

| Asset | Link |
|---|---|
| **Live demo** | [hack.sapphirealpha.xyz](https://hack.sapphirealpha.xyz) — expand the Robinhood card |
| **60s pitch video** | [docs/hackathon/robinhood/video-script.md](https://github.com/arigatoexpress/Sapphire/blob/main/docs/hackathon/robinhood/video-script.md) |
| **90s deep-dive demo** | [docs/hackathon/london-demo-script.md](https://github.com/arigatoexpress/Sapphire/blob/main/docs/hackathon/london-demo-script.md) |
| **Source pitch doc** | [docs/hackathon/sapphire-sentinel-london-2026.md](https://github.com/arigatoexpress/Sapphire/blob/main/docs/hackathon/sapphire-sentinel-london-2026.md) |
| **PR — Sentinel core** | [#498](https://github.com/arigatoexpress/Sapphire/pull/498) (merged) |
| **PR — Forge test suite (18 cases)** | [#567](https://github.com/arigatoexpress/Sapphire/pull/567) (merged) |
| **PR — Zama privacy mock** | [#544](https://github.com/arigatoexpress/Sapphire/pull/544) (merged) |
| **PR — chain-health gate** | [#546](https://github.com/arigatoexpress/Sapphire/pull/546) (merged) |
| **PR — chain-health dashboard panel** | [#555](https://github.com/arigatoexpress/Sapphire/pull/555) (merged) |
| **PR — smoke `--target robinhood`** | [#556](https://github.com/arigatoexpress/Sapphire/pull/556) (merged) |
| **PR — prompt-injection demo toggle** | [#568](https://github.com/arigatoexpress/Sapphire/pull/568) (merged) |
| **PR — integration tests** | [#553](https://github.com/arigatoexpress/Sapphire/pull/553) (merged) |
| **Contract — SapphireSentinelRegistry** | Robinhood Chain testnet · chainId **46630** · [explorer.testnet.chain.robinhood.com](https://explorer.testnet.chain.robinhood.com) |
| **Contract — SapphirePaymentGate** | Robinhood Chain testnet · chainId **46630** |
| **Source contracts** | [`contracts/SapphireSentinelRegistry.sol`](https://github.com/arigatoexpress/Sapphire/blob/main/contracts/SapphireSentinelRegistry.sol) · [`SapphirePaymentGate.sol`](https://github.com/arigatoexpress/Sapphire/blob/main/contracts/SapphirePaymentGate.sol) |

**Live JSON probe (against the deployed Sentinel Registry):**

```bash
curl -X POST https://rpc.testnet.chain.robinhood.com \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_getCode",
       "params":["<sentinel_registry_addr>","latest"],"id":1}'
```

→ returns deployed bytecode. Frontend embeds this probe live.

---

## Slide 4 — Judging-criteria match

**Open House London Buildathon prize categories (verbatim from Arbitrum
Foundation announcement):**

| Category | Verbatim wording | Our match |
|---|---|---|
| **AI Agentic Category — $15K** | "A special category has been reserved for AI agents building on Arbitrum and the Robinhood Chain, with the top three winners sharing $15K in prizes, and at least one out of the top three spots reserved for projects building on the Robinhood Chain." | Sentinel runs on Robinhood Chain (46630) *and* Arbitrum (42161). Multi-chain agent. |
| **Robinhood Chain Innovation Award — $30K** | "Teams exhibiting outstanding innovation are eligible for the Robinhood Chain Innovation Award worth $30K, reserved for projects building on the Robinhood Chain only and fully sponsored by the Robinhood team." | We deploy Sentinel + Payment Gate on chain 46630, not just integrate — and the privacy-mock + chain-health twist *are* the innovation. |
| **Open Category — $70K (1st $40K)** | "A minimum of one of the top three spots will be reserved for a project" on Robinhood Chain. | Sentinel is a Robinhood-Chain-anchored project; we qualify. |

**Devfolio judging criteria (standard):**

| Standard category | Our match |
|---|---|
| **Technical complexity** | 4 gates compose into one severity verdict; 18-case Forge suite + Slither CI; multi-chain port in <1 day per chain |
| **Innovation** | Attestation of *rejected* attacks is novel; privacy-mock + chain-health composition is novel |
| **Practical impact** | Robinhood is launching agents on the chain; we built the gate they need |
| **UX / demo** | Two demo toggles (`SENTINEL_DEMO_FORCE_INJECTION/DEPEG`) make the gate visible in 1 click; one-page judge view at `hack.sapphirealpha.xyz` |
| **Code quality** | 5,995+ unit tests in core, 134+ integration tests for chain layer, ruff + Slither CI green |

---

## Slide 5 — Roadmap post-hackathon

**Week 1:** Mainnet contracts on Robinhood Chain (chain 46630 mainnet
when it launches). Today's deploy is testnet.
**Week 2:** Replace the Zama fhEVM mock with the real fhEVM.
This is the natural cross-pollination with our Zama submission — once
the skill ships (PR #564) we use it to write the real contract.
**Month 1:** First non-Sapphire integrator. Sentinel published as
`pip install sapphire-sentinel` so Robinhood Chain agents can drop the
gate in. Today the Sapphire repo is the only consumer.
**Month 3:** ML-driven anomaly layer on the gate (same as MegaETH
roadmap — same primitive, same evolution).
**Quarter 2:** Robinhood Chain mainnet launches → Sentinel becomes the
default agent-safety primitive on it. We'd like the relationship.

**The on-chain attestation is the asset. Robinhood Chain is the rails.**

---

**Sources:**
- Open House London announcement: https://blog.arbitrum.foundation/open-house-london-registration-is-now-open/
- Devfolio judging guide: https://guide.devfolio.co/docs/guide/judging
- Internal: `docs/research/hackathon-strategy/robinhood-arbitrum-deep-dive.md`
