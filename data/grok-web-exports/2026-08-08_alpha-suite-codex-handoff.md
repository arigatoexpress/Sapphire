---
source: grok-web
date: 2026-08-08
type: handoff
topics: [alpha-suite, quant, robinhood, rh-chain, codex, sapphire, grok-bridge, knowledge-forge, cors, whales, ui]
title: Alpha Suite — ultimate Codex handoff (world-class, collision-free)
priority: P1
money: false
free_reign: false
requires_human: false
---

# Alpha Suite → Codex / Plant — Ultimate Handoff

**From:** Grok Build (web App Builder) · SuperGrok Pro  
**For:** Codex (and Claude plant) merging into Sapphire / DevBox **without collision**  
**Operator:** Ari (rari / @rariwrldd)  
**Date:** 2026-08-08T21:55Z  

> **This packet is additive research glass + ticket schema.**  
> It does **not** compete with plant free-reign, genome, or RH executor.  
> **Do not** rewrite it into unattended place_* paths.

---

## 0. Why Codex should care (one screen)

| Need | What this drop gives you |
|---|---|
| ADHD single path | **Today** tab: cycle · 3 actions · RH vol bars · HL heat · one cycle-scaled ticket |
| RH Chain culture | Multi-seed DexScreener index (cash/SOME/CAT/PEPE culture) — not CEX-only |
| Whale proxies (free) | HL OI×move×funding heat + Ethplorer ETH volume leaders (honest: not labeled wallets) |
| CORS research | Allowlist proxy `/api/cors` + dedicated `/api/ethplorer`, `/api/dex`, `/api/cg`, `/api/hl`, `/api/llama`, `/api/news` |
| Risk laws | 1% risk × cycle multiplier · allowlist · BP · circuit · ≥2 strategy families |
| Life / Forge | External surplus · debt→capital→agency · supervised autonomy · AXTI options doctrine |
| Merge safety | Empty books · no keys · no silent place · dens forever · paper/research first |

**Publish = cockpit. 24/7 = DevBox/GCP workers + plant gates.**

---

## 1. Knowledge Forge / life direction (mined)

Sources: this lab thread · plant exports (`system-brief`, AXTI learnings, master handoff, alpha scour) · operator profile.

| Principle | Code implication |
|---|---|
| **External surplus** | Research publish path later; X teardown is separate plant P0 — not this UI |
| **Out of debt · capital · agency** | Asymmetric sleeves A/B/C · win C/B carefully → fund A + debt · never reverse |
| **Late-bear → expansion** | `cycle.riskMultiplier` scales ticket risk % |
| **ADHD single path** | Default **Today** · hide More tabs · MagBars / ScoreDonut / RankBars |
| **Frontier lab** | MegaETH · 0G · RH Chain · HL rails as data, not free-reign theater |
| **Supervised autonomy** | Confirm phrase · plant TG gate · killswitch culture · site never places |
| **No fake portfolio** | Empty tracker · RH snapshot real or blank · no invented marks on locked bags |
| **AXTI class edge** | Defined-risk options + gamma scale-out; dens (SONNY/BINGBONG) permanent |
| **Process holds** | Ika (2PC-MPC), Supernova/Blackhole ve(3,3), Depth — research/hold only |

**Capital path (UI copy):** *Win carefully in C/B → fund A + debt. Process bags track only.*

Encoded in: `src/lib/rari-profile.ts` → `FORGE_PRINCIPLES`, `PLAY_LAWS`, `THESIS_GRAPH`, `PROFILE`.

---

## 2. What shipped (this lab — demo-ready)

### Product surface
| Tab | Role |
|---|---|
| **Today** (default) | Regime donut · dual heat/opp meter · RH RankBars · 3 actions · HL MagBars · Forge strip · one ticket draft |
| **Command** | Personal rank board · briefing · cycle-scaled drafts |
| **Flow** | Architecture map (OKX/Dex/HL/Ethplorer/Llama → plane → TA/Command/Lab → risk → co-pilot → you) · RH index · HL whale proxy · Ethplorer leaders · CG trending · Sol hot · source stack |
| **Co-pilot** | RH book snapshot · allowlist · 1% risk · confirm phrase · **no place_*** |
| **Lab** | Cycle · data QA · backtests on real OKX bars |
| More | Charts · Strategies · Scanner · TV · Data · Tracker · Pairs · Mega·0G · Signals · Risk · System |

### Visual system (anti-slop)
- Near-black neutrals · one cool accent · semantic up/down/warn only on badges/bars  
- Concentric radii · MagBar · ScoreDonut · RankBars · DualMeter · HeatCells · SegmentBar · ChgPill · PulseDot  
- Quiet sticky header · ADHD Today path · no purple/neon/emoji chrome  

### Data plane (`scripts/data-plane-plugin.mjs` + `src/lib/data/fetch.ts`)
| Route | Upstream |
|---|---|
| `/api/health` | local |
| `/api/dex/*` | DexScreener |
| `/api/cg/*` | CoinGecko |
| `/api/llama/*` | DefiLlama |
| `/api/hl` POST | Hyperliquid info |
| `/api/rhj/*` | RH stock tokens |
| `/api/rpc/{mega,rh,eth,sol}` | public RPCs |
| `/api/news` | RSS (CT, CoinDesk, Defiant, Decrypt, Blockworks) |
| `/api/ethplorer/*` | Ethplorer freekey |
| `/api/cors?url=` | **allowlist hosts only** (dex, cg, llama, ethplorer, news, github raw, …) |

**Prod note:** middleware is Vite `apply: "serve"`. Production falls back via `data/fetch.ts` DIRECT map (no secrets). News needs a server or plant worker on pure static.

### Whale board honesty
- **HL:** OI × move × funding extremes = *perp size proxy*, not named wallets  
- **Ethplorer:** token volume/cap leaders on ETH — not Arkham clusters  
- Labeled whales → DevBox stage (Nansen/Arkham) — **gap, not fake**

### Safety fences (non-negotiable)
1. No wallet private keys in agent / site  
2. No silent 24/7 broker place from published site  
3. No fake balances / fake portfolio weights  
4. Tickets blocked: allowlist, BP, circuit, strategy families, max open units  
5. Cycle multiplies risk %  
6. Dens forever; dust rebuys refuse (plant policy alignment)  

### Tests / build
- `npm test` (alpha self-test)  
- `npm run typecheck`  
- `npm run build` (Vercel/nitro)  

### Key paths
```
src/components/quant/{suite,today-board,flow-desk,command-center,copilot-desk,lab-desk,architecture-map,viz}.tsx
src/lib/{copilot,command-engine,cycle,backtest,strategies,demark,rari-profile,ticket-from-command}.ts
src/lib/data/{plane,signals,rh-chain,whales,fetch}.ts
scripts/data-plane-plugin.mjs
scripts/alpha-selftest.mjs
public/rh-book.json
public/codex-alpha-packet.md
CODEX_HANDOFF.md
```

---

## 3. Alignment with plant free-reign (collision map)

| Plant rail | This suite | Merge rule |
|---|---|---|
| RH Agentic ••••8144 free-reign | Co-pilot tickets + confirm phrase | **Port schema**; execution stays plant/MCP gated |
| RH L2 ≤$10 dens | RH Chain index as *research culture* | Research feed only — dens still plant-side |
| MOSS / MegaETH grant | Mega·0G desk + RPC | Research; grant renew is plant ops |
| Genome / AXTI | PLAY_LAWS axti + dens | Encode lessons; no auto option place from site |
| TG terminal | Today briefing → optional TG card | **Approve-only** research card |
| fund-factory / deskos | Lab backtests + command rank | Paper first; walkforward later |

**DO NOT:** port place_* into unattended free-reign without killswitch · overwrite paper books with demo positions · drop RH culture for CEX-only · purple neon UI.

---

## 4. Ordered Codex tasks (worktree; explicit paths)

1. **Sync:** `bash scripts/ops/sync_grok_web_exports.sh --pull`  
2. **Gap analysis:** vs fund-factory · deskos · telegram · genome · free-reign policy  
3. **Port types:** risk mandate + TradeTicket (TDD, **no broker place**)  
4. **Workers (read-only):** nightly OKX + RH multi-query index + HL heat + Ethplorer top → `ops-state` JSON  
5. **Optional TG:** Today briefing card fields matching confirm phrase (approve-only)  
6. **Dashboard:** read-only Research tab candidate (reuse Today hierarchy)  
7. **deskos:** walkforward on ensemble strategies when ready  
8. **Receipt:** `~/ops-state/agent-reports/ALPHA-SUITE-MERGE-RECEIPT-2026-08-08.md` + local-export mirror  

---

## 5. Paste-ready Codex prompt

```
You are Codex on Ari plant (Sapphire monorepo).
Read:
  data/grok-web-exports/2026-08-08_alpha-suite-codex-handoff.md
  data/grok-web-exports/README.md
  (optional) 2026-08-06_system-brief.md, 2026-08-05_alpha-learnings-axti-l2.md

Mission: Merge Alpha Suite RESEARCH into plant WITHOUT free-reign live money paths and WITHOUT technical debt collisions.

1) Sync exports. Diff vs fund-factory / deskos / telegram / genome / free-reign policy.
2) Port risk mandate + TradeTicket with tests (no place_*).
3) Read-only workers: RH DexScreener multi-query + HL heat + Ethplorer volume leaders.
4) Optional TG research card from Today briefing (approve-only).
5) Respect dens, dust-no-rebuy, AXTI options-first doctrine, cycle risk scaling.
6) Do not fund, arm, or place. Killswitch intact.
7) Receipt: ~/ops-state/agent-reports/ALPHA-SUITE-MERGE-RECEIPT-2026-08-08.md + local-export mirror.

Worktree only. Explicit path commits. Never git add -A.
```

---

## 6. Honest gaps (do not paper over)

| Gap | Reality |
|---|---|
| Labeled whales | Need Arkham/Nansen on DevBox |
| News on static Vercel | Needs server worker or RSS CORS plant proxy |
| Agentic BP often 0 | Fund ••••8144 before live phrase |
| 24/7 | Plant LaunchAgents / GCP — not publish site |
| Backtests | Not walk-forward yet |
| RH culture ≠ equity tickets | Memes/index are research; tickets are allowlisted equities/crypto |

---

## 7. Session receipt (2026-08-08 final polish)

- UI polish: Today hero · RankBars · DualMeter · Forge strip · ChgPill · narrative MagBars · architecture Ethplorer node  
- CORS allowlist expanded (dexscreener, coingecko, llama, ethplorer, news, github raw, …)  
- Ethplorer + whale board wired · health lists routes  
- rari-profile FORGE_PRINCIPLES + AXTI/dens play laws  
- typecheck green · data plane live · bridge export this file  

**Status:** Research desk demo-ready · Execution supervised · Plant merge ready for Codex · **no collision** with free-reign money paths
