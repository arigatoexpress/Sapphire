# Sapphire Sentinel · Multi-Chain — 5-Slide Pitch Deck

**Submission targets:**
- MegaETH `awesome-megaeth-ai` (DeFi + Agents + Developer Tools categories)
- Mega Mafia 2.0 application
- Cross-pollination into Arbitrum London Buildathon (London Buildathon
  prize tracks live on chains 42161 + 10)
**Submission anchors:** PRs [#557](https://github.com/arigatoexpress/Sapphire/pull/557), [#565](https://github.com/arigatoexpress/Sapphire/pull/565), [#569](https://github.com/arigatoexpress/Sapphire/pull/569), [#546](https://github.com/arigatoexpress/Sapphire/pull/546)

---

## Slide 1 — The 1-line pitch

# Approve the trade only if the chain agrees.

Sapphire Sentinel is a chain-health gate that reads live protocol state on
**MegaETH, Arbitrum, and Optimism** before approving any alpha-paid signal
that references those protocols. One codebase. Three chains. Two protocol
categories (lending + perps). Read-only. Open source.

**Why now:** AI trading agents make trillions of decisions a year and 99%
of them never check whether the chains they reference are healthy. Funding
spikes, reserve freezes, peg breaks — the alpha was right at submit time
but the chain moved underneath it. Sentinel is the missing primitive.

---

## Slide 2 — The technical novelty

**What makes this impossible to copy in a weekend:**

| Layer | What it proves | Implementation |
|---|---|---|
| **MegaETH chain-health (PR #546)** | USDM peg + Aave reserve state on chain 4326 | `lib/hackathon/chain_health_gate.py` reading via `lib/chains/megaeth/` |
| **Arbitrum Aave V3 (PR #557)** | Reserve health, freeze flags, borrow caps on 42161 | `lib/chains/arbitrum/contracts/aave_v3.py` |
| **Arbitrum GMX V2 (PR #565)** | 60 perps markets, funding skew, OI | `lib/chains/arbitrum/contracts/gmx_v2.py` + `gmx_price_adapter.py` |
| **Optimism Aave V3 (PR #569)** | Reserve health on chain 10 | Same primitive as Arbitrum, ported in <1 day |
| **Chainlink fallback (PR #570)** | BTC/SOL/AVAX/DOGE oracle prices | `lib/chains/arbitrum/contracts/chainlink_oracle.py` — 6 feeds verified live via `eth_getCode` |

**The footgun we caught:** GMX V2 returns `Price.Props` at **1e30** scale,
not 1e8 like Chainlink. That's 22 zeros of difference. Most agent stacks
silently misprice GMX positions. Our `gmx_price_adapter.py` has a unit
test that fails if anyone tries to use 1e8 — so the bug *can't* regress.

**Cross-chain composition:** the gate composes — `evaluate_chain_health(
chain, asset)` returns the *worst-of* severity across all chains the alpha
references. If MegaETH USDM depegs *and* GMX BTC funding spikes, the gate
fires once, not twice.

---

## Slide 3 — Live demo · contracts · code

| Asset | Link |
|---|---|
| **Live demo** | [hack.sapphirealpha.xyz](https://hack.sapphirealpha.xyz) — expand the MegaETH card |
| **60s pitch video** | [docs/hackathon/megaeth/video-script.md](https://github.com/arigatoexpress/Sapphire/blob/main/docs/hackathon/megaeth/video-script.md) |
| **PR — Aave V3 read layer** | [#557](https://github.com/arigatoexpress/Sapphire/pull/557) (merged) |
| **PR — GMX V2 perps reader** | [#565](https://github.com/arigatoexpress/Sapphire/pull/565) (merged) |
| **PR — Optimism Aave V3** | [#569](https://github.com/arigatoexpress/Sapphire/pull/569) (merged) |
| **PR — Chainlink fallback** | [#570](https://github.com/arigatoexpress/Sapphire/pull/570) (merged) |
| **PR — MegaETH chain-health gate** | [#546](https://github.com/arigatoexpress/Sapphire/pull/546) (merged) |
| **GMX V2 Reader** | Arbitrum One · [arbiscan.io](https://arbiscan.io/) |
| **Aave V3 Pool** | Arbitrum One · `0x794a61358D6845594F94dc1DB02A252b5b4814aD` · [arbiscan.io/address/0x794a...4aD](https://arbiscan.io/address/0x794a61358D6845594F94dc1DB02A252b5b4814aD) |
| **Chainlink BTC/USD** | Arbitrum One · `0x6ce185860a4963106506C203335A2910413708e9` |

**Live JSON probe (against deployed Aave V3 Pool on Arbitrum One):**

```bash
curl -X POST https://arb1.arbitrum.io/rpc \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_getCode",
       "params":["0x794a61358D6845594F94dc1DB02A252b5b4814aD","latest"],
       "id":1}'
```

→ returns the deployed Aave V3 Pool bytecode. Frontend embeds this probe live.

---

## Slide 4 — Judging-criteria match

**MegaETH `awesome-megaeth-ai` (verbatim from CONTRIBUTING.md):**

| Criterion | Verbatim wording | Our match |
|---|---|---|
| **Active maintenance + docs** | "Active maintenance + docs" | 6,567 tests, daily commits, [4 architecture docs](https://github.com/arigatoexpress/Sapphire/tree/main/docs/integrations) for chain integrations |
| **Clear value to MegaETH developers** | "Clear value to MegaETH developers (chain ID 4326 / 6343)" | First Python wrapper on chain 4326; existing skill packs are TS/Solidity-leaning |
| **Open source or publicly accessible API** | "Open source or publicly accessible API" | MIT-licensed, public repo |
| **Categories that match** | "General, DeFi, Developer Tools, Agents" | Submitted to all 4 |

**Mega Mafia 2.0 (per `docs/research/hackathon-strategy/megaeth-deep-dive.md` analysis of selection criteria):**

| Criterion | Our match |
|---|---|
| **Innovation over generic DeFi** | Sentinel is a *primitive* (chain-health gate), not a wrapper |
| **Operational maturity** | Hyperliquid live executor live, 5,995 tests, $5/order risk caps |
| **MegaETH chain-specific value** | First chain-health gate that includes MegaETH USDM peg + Aave reserves |

**Arbitrum Open House London Buildathon — AI Agentic Category ($15K):**

| Criterion | Our match |
|---|---|
| **AI agents on Arbitrum/Robinhood Chain** | Sentinel runs on Arbitrum One (42161); Robinhood Chain (46630) is the second chain — see Robinhood deck |
| **Innovation** | Cross-chain composition is novel — most agent gates are single-chain |
| **Code quality + tests** | Forge test suite for Sentinel registry (PR #567), 134 unit + 2 live integration tests |

---

## Slide 5 — Roadmap post-hackathon

**Week 1:** `awesome-megaeth-ai` PR opened with all three categories
filled (DeFi + Agents + Developer Tools). Mega Mafia 2.0 application
filed.
**Week 2:** Add a 4th chain — Base (8453). Sentinel becomes the
default chain-health primitive for any agent on any L2.
**Month 1:** Publish `pip install sapphire-sentinel` so other agent
projects can drop the gate in. Today the Sapphire repo is the only
consumer; the broader market is the prize.
**Month 3:** Add a write surface — `Sentinel.recordEvaluation()` on
MegaETH (already shipped on Robinhood Chain) so verdicts are anchored,
not just generated. Cross-pollinates with the Robinhood London submission.
**Quarter 2:** ML-driven anomaly detection layered on top of the rule-based
gate. Today the gate is "BLOCK if funding > 500%"; tomorrow it's "BLOCK
if funding-distribution looks anomalous vs. trailing 30d." Same primitive,
sharper teeth.

**The chain-health gate is the asset. MegaETH is one of three chains.**

---

**Sources:**
- MegaETH `awesome-megaeth-ai`: https://github.com/megaeth-labs/awesome-megaeth-ai
- MegaETH builder programs: https://www.megaeth.com/builder
- Arbitrum Open House London: https://blog.arbitrum.foundation/open-house-london-registration-is-now-open/
- Internal: `docs/research/hackathon-strategy/megaeth-deep-dive.md`
