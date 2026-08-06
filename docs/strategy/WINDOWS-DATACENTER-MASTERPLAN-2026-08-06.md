# Sapphire Master Plan — Windows as Private Datacenter

**Document ID:** `SAPPHIRE-WIN-DC-MASTERPLAN-2026-08-06`  
**Status:** AUTHORITATIVE NORTH STAR (supersedes scattered “workbench” framing)  
**Owner:** Ari (@arigatoexpress)  
**Generated:** 2026-08-06 · Grok Build  
**Companions:**  
- Gemini Cloud Shell paste prompt → [`docs/handoffs/GEMINI-CLOUDSHELL-MASTER-PROMPT-2026-08-06.md`](../handoffs/GEMINI-CLOUDSHELL-MASTER-PROMPT-2026-08-06.md)  
- Cloud Shell ops handoff → [`docs/handoffs/GCP-CLOUD-SHELL-ULTIMATE-HANDOFF-2026-08-06.md`](../handoffs/GCP-CLOUD-SHELL-ULTIMATE-HANDOFF-2026-08-06.md)  
- Alpha ledger → [`docs/alpha/GROK-CHAT-ALPHA-2026-08-06.md`](../alpha/GROK-CHAT-ALPHA-2026-08-06.md) · [`data/alpha/alpha_ledger.json`](../../data/alpha/alpha_ledger.json)

---

## 0) One sentence

**Make the Windows desktop a dedicated, always-on private datacenter that runs agent harnesses over all assets, intel, infra, and best-of-breed open source — so the plant earns on designated rails, publishes real research, and continuously improves — while Mac remains mobile commander and GCP remains warehouse + remote coding seat.**

---

## 1) Why this is the whole point

| Old framing (partial) | Correct framing (this plan) |
|---|---|
| Windows = “GPU workbench / optional desk” | Windows = **always-on private DC** (compute, research, learning, scheduled execution workers) |
| Mac runs everything | Mac = **commander + authority surface** (killswitch, broker MCP when present, densify, human UX) |
| Agents as chat sessions | Agents as **harnesses** with receipts, budgets, promotion ladders, and fail-closed writers |
| Random OSS installs | **Surgical extraction** of schemas/adapters from best systems into Sapphire contracts |
| “Autonomous” = ambient money | Autonomous = **bounded loops on designated rails** under caps, dens, killswitch, proof-carrying sole writer |

You already have chassis, free-reign multi-rail, AXTI-class alpha, knowledge bridge, GCP data plane, Telegram Central Terminal. The gap is **role clarity + harness density + learning loop closed on Windows**.

---

## 2) Mission outcomes (what “best” means)

| # | Outcome | Measurable |
|---|---|---|
| M1 | **Earn** on designated experimental capital | Realized after-cost PnL + drawdown on agentic RH / L2 / MOSS only; never THO |
| M2 | **Publish** real research | Content engine drafts → reviewed publish; weekly brief + alpha post-mortems |
| M3 | **Self-improve** | Closed trades → genome.lessons + outcomes; challenger beats champion on live evidence |
| M4 | **Always-on plant** | Win DC uptime + schtasks HB + Mac reconnect <15m to green inventory |
| M5 | **Ever-evolving stack** | OSS mine → adapter PR → paper shadow → promote; archive zombies |

Non-goals: hedge-fund AUM cosplay, ambient LLM order authority, merging THO into the fleet, unbounded meme snipes.

---

## 3) Fleet roles (authoritative)

```text
                    ┌─────────────────────────────┐
                    │   Ari (owner authority)     │
                    │   exact gates / passkeys    │
                    └──────────────┬──────────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
┌─────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│ MAC COMMANDER   │     │ WINDOWS PRIVATE DC  │     │ GCP CLOUD       │
│ laptop / mobile │     │ DESKTOP-HFCK6U9     │     │ warehouse+shell │
│ authority, MCP  │     │ always-on harnesses │     │ BQ/GCS/CR/Vertex│
│ densify, TG UX  │     │ GPU + research +    │     │ remote code seat│
│ killswitch home │     │ paper/live workers* │     │ public site     │
└────────┬────────┘     └──────────┬──────────┘     └────────┬────────┘
         │                         │                         │
         └──────────── Tailscale mesh + git bridge ──────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │  Pi mesh (collectors / lite  │
                    │  inference) when inventoryed │
                    └─────────────────────────────┘
```

\* Live workers on Win only on **designated rails**, after post-boot green, with dens + caps + killswitch parity to Mac.

| Node | Always-on jobs | Never |
|---|---|---|
| **Windows DC** | Ollama GPU tiers · research worker · TV agent/CDP · backtests/walk-forward · L2 executor schtasks (when armed) · MegaETH verifier · local feature/bronze collectors · genome update jobs · free-reign tick consumers | THO money · Hermes send · secret print · ambient re-buy dust · archive RETIRED paths blindly |
| **Mac commander** | Control plane · plant deck :8100 / API :8099 · densify/Ralph · gcp_sync · broker MCP when home · Telegram Central Terminal · killswitch owner files | Assume Win is down forever; run heavy GPU overnight if Win is healthy |
| **GCP** | BQ/GCS lake · scheduled SQL · public Mission Control · Cloud Shell invent/PR · Vertex **batch** only | Live orders · sole writer · LaunchAgent authority |
| **Pis** | RSS/collectors · heartbeat · optional lite Ollama | Keys, broker authority, sole writer |

---

## 4) Agent harness architecture

A **harness** is not a chat persona. It is a process with: goal, budget, tools, receipt schema, promote/demote rule, and a hard fence.

### 4.1 Core harnesses (ship / keep / densify)

| Harness | Home | Cadence | Output | Promote when |
|---|---|---|---|---|
| **Plant supervisor** | Mac | 15m | heal + gates | always (non-money) |
| **Ralph / densify** | Mac | 30–60m | code/docs from inbox | tests green |
| **Night goals & trades** | Mac→Win | 2h | sticky plan / free-reign | plan hash matches |
| **Research worker** | **Win** | daily | backtest + walk-forward manifest | paper_only + fresh <36h |
| **TV agent** | **Win** | always | CDP intake paper path | read-only until mutate gate |
| **Free-reign multi-rail** | Mac+Win | continuous | proposals under dens/caps | sole writer + receipts |
| **Asymmetric risk (AXTI)** | Mac/Win | RTH | TP+75% / SL−40% options | closed trade evidence |
| **Content / research publish** | Mac | slots | drafts/ready | `SAPPHIRE_PUBLISH_LIVE=1` + review |
| **Gemini OODA (dry)** | Mac / Cloud Shell design | daily | OODA packet | never auto-executes |
| **Genome learner** | **Win+Mac** | post-trade | lessons[] + outcomes | broker-reconciled only |
| **Knowledge bridge** | Git | continuous | `data/grok-web-exports/` | densify on Mac |
| **GCP sync / BQ** | Mac→GCP | scheduled | lake freshness | pause-safe |

### 4.2 Harness contracts (non-negotiable)

1. **Models propose; writers authorize** — LLM never is the sole writer.  
2. **Proof-carrying decisions** — feature hash, arm, size, dens check, killswitch stamp, receipt.  
3. **`NO_TRADE` is an arm** — measurable reward; activity ≠ learning.  
4. **Capital ladder** — replay → shadow → paper → min live → scale from after-cost evidence.  
5. **Fault isolation** — stale data / unreconciled exposure kills that writer path only.  
6. **Never `git add -A`** — explicit paths.  
7. **Designated rails only** — RH Agentic ••••8144, L2 `0xc2B5…c9EB`, MOSS grant-gated, paper.

### 4.3 Best-of-breed OSS (mine, don’t install as the fund)

| System | Extract | Reject |
|---|---|---|
| NautilusTrader | Event time, venue adapters, order state | Chassis rewrite |
| LEAN | Algo interface, brokerage models | Cloud control plane |
| Qlib | PIT data, experiment recorder | Whole platform runtime |
| Freqtrade | Bias probes, dry/live parity | Hyperopt-as-strategy |
| Hummingbot | Controller/executor split | Second sole writer |
| River / VW | Drift, contextual bandits | Opaque RL order policy |
| TradingAgents / AI Hedge Fund | Debate scaffolds, research UI | Persona votes as evidence |
| Pengu/Bonk TG UX | Dual surface, position cards | Keys in chat |

Rule: extract schema/adapter/UI **only when ≥2 Sapphire consumers** exist (or one consumer + test).

---

## 5) Money path (earn)

```text
intel + market + chain + thesis
        → event_bus (typed)
        → strategy arms (+ NO_TRADE)
        → portfolio / risk transforms
        → free-reign dens + caps + killswitch
        → sole writer (paper | designated live)
        → broker reconciliation
        → reward + attribution
        → genome / champion-challenger
```

### 5.1 Mandate (sticky)

`free_reign_multi_rail`

| Rail | Policy |
|---|---|
| RH Agentic ••••8144 | Free-reign easy · **options-first (AXTI)** · dust placer **refuses** |
| RH Chain L2 | ON · **≤$10** · max 1 open · dens (SONNY/BINGBONG class permanent) |
| MOSS / MegaETH | trade only if **grant hours_left > 0** · renew passkey is human |
| Paper | Always allowed for research workers |

### 5.2 AXTI playbook (only proven +125% pattern to date)

1. Defined-risk long options (premium = max loss).  
2. Catalyst window — short-dated with thesis.  
3. Scale-out: half near **2×**, trail rest; hard SL **−40%** premium.  
4. Never hold to worthless.  
5. Wire closed trades into genome.lessons automatically.

### 5.3 Explicit stop list

- Do not re-place dust sleeve buys (IBIT/HOOD/PLTR/NVDA).  
- Do not cancel exit sells unless owner killswitch.  
- No THO / Project-Go-Forward money.  
- No Hermes messaging send.  
- No unbounded L2 meme campaigns.

---

## 6) Research + publish path

```text
signals / post-mortems / thesis
  → lib/content drafts
  → review
  → ready/ (+ optional SAPPHIRE_PUBLISH_LIVE)
  → public Mission Control (read-only) + optional channels
```

Publish **after** attribution, not before. Prefer reconstructible decision hashes in research notes.

Windows DC produces **evidence packs** (backtests, walk-forwards, OODA inputs). Mac content engine and Cloud Shell docs turn evidence into narrative.

---

## 7) Self-improvement loop

```text
closed trade (broker truth)
  → outcomes win/loss + markout + fees
  → genome.lessons[]
  → arm weight update / dens hit
  → challenger experiments (Win research worker)
  → paper shadow → min live only if after-cost edge
  → champion demotion on drift / calibration fail
```

P0 engineering for learning:

1. Genome outcomes not stuck at 0/0/0 — wire from closed trades.  
2. Options risk loop automation (TP/SL).  
3. Research worker manifests feed densify inbox.  
4. Deflated Sharpe / trial-count penalties on backtests (no theater).

---

## 8) Windows DC build ladder (implementation order)

### P0 — Make the DC trustworthy (do first)

| Step | Action | Done when |
|---|---|---|
| W0.1 | Post-boot recovery | `WIN-POST-BOOT-*-LATEST.md` with crash hypothesis, dumps, Ollama VRAM, schtasks inventory |
| W0.2 | Free-reign / dens / killswitch **parity** Mac ↔ Win | mirrors match; dens live |
| W0.3 | Availability | no sleep/lock killing overnight; Tailscale up; SSH stable |
| W0.4 | GPU hygiene | expected Ollama aliases present; unload junk models |
| W0.5 | Do not ARM L2 traders until W0.1–W0.4 green | HB healthy |

### P1 — Research + learning density

| Step | Action |
|---|---|
| W1.1 | Daily `SapphireResearchWorker` after manual smoke (paper_only) |
| W1.2 | TV agent read-only + CDP |
| W1.3 | Backtest/walk-forward artifacts under `E:\Sapphire\research-worker\` → sync summary to git or Knowledge |
| W1.4 | Genome lessons seed from AXTI + dens failures |
| W1.5 | MegaETH stateless-validator (verify, not pretend RPC) |

### P2 — Execution workers (still designated rails)

| Step | Action |
|---|---|
| W2.1 | ARM L2 schtasks only with dens + ≤$10 + max 1 open |
| W2.2 | Mac→Win `sync_decisions_to_win` healthy |
| W2.3 | Options risk automation for AXTI-class after dust exits fill |
| W2.4 | Telegram dual surface: Trade Terminal vs Command Center (no keys in chat) |

### P3 — Evolution

| Step | Action |
|---|---|
| W3.1 | Continuous OSS mine → adapter PRs (≥2 consumers) |
| W3.2 | Contextual allocator with NO_TRADE arm (paper first) |
| W3.3 | Pi mesh roles documented; collectors only |
| W3.4 | Public research cadence from content engine |

---

## 9) Mac + GCP + Cloud Shell (how they support the DC)

| Surface | Job relative to Win DC |
|---|---|
| Mac | Authority, densify Ralph, plant deck, broker MCP, gcp_sync, TG |
| GCP lake | Long-term features, evals, freshness, Mission Control |
| **Cloud Shell + Gemini** | Away invent/PR/docs/data-plane; **never** sole writer; implement plan phases that are code/schema/docs |

When away: Gemini in Cloud Shell advances **PRs, BQ, docs, paper modules, harness specs**.  
When home: Mac densifies exports; Win runs heavy loops.

---

## 10) NOW board (2026-08-06) — plant critical path

1. Confirm dust **exits fill** at RTH — do not re-buy.  
2. **MOSS grant renew** (hours_left was ≤ 0).  
3. Finish **Win post-boot** → parity → then ARM.  
4. Stage **AXTI-class** probes after exits.  
5. Keep dens permanent.  
6. `git pull` + densify `data/grok-web-exports/` including this plan.

---

## 11) Success scoreboard (weekly)

| Metric | Target direction |
|---|---|
| Win uptime / schtasks HB | ↑ |
| Research worker freshness | <36h |
| Closed-trade genome coverage | → 100% of designated-rail closes |
| After-cost PnL on agentic rails | ≥0 rolling after costs; controlled DD |
| Dens hits blocked | logged, not silent |
| Published research artifacts | ≥1/week when plant green |
| Open zombie task* trees | ↓ archive |
| Cloud Shell session notes densified | every away day |

---

## 12) Document control

| Change | Rule |
|---|---|
| Role of Windows | Update this file + README + device_topology |
| Free-reign policy | Plant `free-reign.json` is runtime truth; mirror learnings here |
| Cloud Shell work | Must not contradict §3–§5 fences |
| Supersedes | “Windows = optional GPU only” language in older runbooks — those remain valid for **how**, this file owns **why / order / mission** |

---

**End of master plan.** Implement via Gemini Cloud Shell prompt + plant reconnect checklist; never via ambient LLM trading.
