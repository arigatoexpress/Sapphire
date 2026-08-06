---
source: grok-web
date: 2026-08-06
type: alpha-scour
topics: [trading, automation, bridge, sapphire-merge]
title: Alpha scour → Sapphire merge (most recent first)
---

# Alpha scour → Sapphire merge

**Scoured:** 2026-08-06T13:45:00Z  
**Authority:** inert knowledge / research only — not order authority  
**Target:** `arigatoexpress/Sapphire`

## What we mined (newest first)

| Source | Kind | Recency |
|---|---|---|
| operator-feeds-20260806 | drive | 2026-08-06 |
| Fleet + Win recovery handoff | drive+github | 2026-08-05 |
| MASTER HANDOFF — Claude Opus | drive+github | 2026-08-05 |
| Alpha learnings — AXTI + L2 dens | github | 2026-08-05 |
| Plant alpha status + TG OSS mine | github | 2026-08-05 |
| Sapphire Overnight Control Brief — 2026-07-27 | notion | 2026-07-28 |
| Mark Walter Probe Quant Analysis | notion | 2026-07-28 |
| AUTONOMOUS-TRADING-EDGE-PLAN | drive | 2026-07-28 |
| 2026-07-23 rebuild / fund-factory session | drive | 2026-07-23 |
| arigatoexpress/Sapphire data/grok-web-exports | github | 2026-08-05 |

## Invariants (encode, do not dilute)

- Designated rails only: RH Agentic ••••8144, RH L2, MOSS/MegaETH (grant-gated), paper
- Models propose only — coordinator + first-party receipts authorize; no ambient spend/trade authority
- No THO / Project-Go-Forward money · Hermes messaging send · keys in model/git
- Dust-sleeve placer refuses; do not re-buy IBIT/HOOD/PLTR/NVDA dust; dens stay (SONNY/BINGBONG class)
- Paper/research/docs may advance; money paths refuse without exact gate / free-reign mandate
- Never archive paths named RETIRED without readlink / LaunchAgent WorkingDirectory check
- Never git add -A; report paths + diffs only

## Best alpha by domain

### Trading systems

#### OP-01 · Operator feed: free-reign L2 $10; MOSS grant expired · critical

Plant SHIPPED. Free-reign L2 cap $10. MOSS armed=false with hours_left negative (~−11h) — grant must renew before any MegaETH sessions. Denylist includes SONNY/BINGBONG + short 0x prefixes + IBIT/HOOD/PLTR as free-reign spam block. Open bag empty; four dust exit proposals still the live equity plan.

- **Status:** active
- **Action:** Renew MOSS passkey grant; do not cancel dust exit sells
- **Paths:** data/grok-web-exports/, docs/ops/
- **Tags:** free-reign, moss, dens, operator-feed

#### OP-03 · Mac→Win decisions sync is the fill path · high

Fills execute on Win. Mac free_reign must sync decisions.jsonl → Win (sync_decisions_to_win.sh). max_on_chain_open=1 + open bag blocks new L2 BUYs. Four dust sleeve exits remain approved_open with multi-hour expiry windows.

- **Status:** ops_debt
- **Action:** Verify decisions sync before assuming Win filled
- **Paths:** services/, data/live_portfolio/
- **Tags:** mac-win, executor, sync

#### TR-AXTI · AXTI playbook: defined-risk options + gamma scale-out · critical

Broker-backed win: buy 2 AXTI Aug-7 $80c @ $0.70 ($140 risk) → sell 1 @ $2.25 (+$155) → sell 1 @ $0.90 (+$20) = +$175 (~+125%). Rules: defined risk first; catalyst window; gamma > theta; scale out on spikes; never hold through worthless decay; automate TP half at 2× / trail / hard SL −40% premium.

- **Status:** accepted
- **Action:** After dust exits fill, stage 1–2 AXTI-class option probes (defined risk, ≤$35)
- **Paths:** data/grok-web-exports/2026-08-05_alpha-learnings-axti-l2.md, lib/trading/
- **Tags:** AXTI, options, playbook, agentic

#### TR-DENS · L2 dens: SONNY/BINGBONG class permanent · critical

Honeypot dens, exit-illiquid bags, assassin/no flow-truth, paper stop-loss churn on illiquid memes. Permanent denylist tickers + full + short 0x addrs; block_exit_liquidity_fails; min_apex_score 0.68; max_stages_per_day 3; no unbounded meme snipes.

- **Status:** accepted
- **Action:** —
- **Paths:** data/grok-web-exports/2026-08-05_alpha-learnings-axti-l2.md, data/shannon-production-denylist.txt
- **Tags:** dens, L2, SONNY, BINGBONG

#### TR-DUST · Dust sleeve exits queued — do not re-place · critical

Four market sells for next RTH on RH Agentic ••••8144: IBIT, HOOD, PLTR, NVDA (sub-share dust from overnight $20×4 fill). place_agentic_rth must refuse dust under multi-rail/exits mandate. Do not cancel unless owner killswitches.

- **Status:** active
- **Action:** Confirm fills at RTH; then options-first only
- **Paths:** data/live_portfolio/, docs/ops/
- **Tags:** exits, RTH, agentic

#### SV-04 · Trading / mints / OAuth / prod cutovers at attended gates · critical

Overnight brief: Trading, token launches, mints, liquidity, public posts, OAuth grants, and production cutovers stay at exact attended gates. Reversible build/test/review continues autonomously. Free-reign multi-rail (Aug 5+) is a bounded exception on designated test rails under caps — not a blank check on all capital.

- **Status:** accepted
- **Action:** —
- **Paths:** lib/core/, lib/autonomy/
- **Tags:** killswitch, gates

#### TR-01 · Signal spine: TV/OHLCV/chain → bus → surfaces · high

Analytics + chain intel emit typed events on event_bus; dashboard SSE, Telegram drafts, and paper/live executors consume — never skip the bus.

- **Status:** accepted
- **Action:** —
- **Paths:** lib/analytics/, lib/core/, services/
- **Tags:** pipeline

#### AU-05 · Hyperliquid hard caps + signing gate · critical

$5/order, 3x lev, 5 positions, $25/day loss; mainnet refused until EIP-712 signing verified on testnet.

- **Status:** accepted
- **Action:** —
- **Paths:** lib/perps/, services/
- **Tags:** live-policy, HL

#### TR-08 · Sentiment fake-neutral on provider fail · medium

Silent 50/neutral default when upstream fails is not a real reading — treat as null/unknown.

- **Status:** bug_memory
- **Action:** —
- **Paths:** lib/analytics/
- **Tags:** gotcha


### Automations

#### AU-FR · Mandate free_reign_multi_rail (sticky) · high

Free-reign ON designated rails: RH Agentic easy + options-first + no dust placer; RH L2 ON ≤$10 max 1 open + dens; MOSS trade=true when grant hours_left > 0. Desk cycle must not wipe free-reign (easy_mode.free_reign_payload sticky). Per-trade Telegram approval cards stay dead.

- **Status:** accepted
- **Action:** —
- **Paths:** lib/autonomy/, data/agent_runtime_policy.json

#### AU-TG · Telegram dual surface: Trade Terminal + Command Center · high

Mine PenguBot/BonkBot/OctoBot/Freqtrade patterns. Ship: position cards one-tap TP/SL/close; risk loop marks → RH option close; paste-thesis → /do; CC live JSON over Tailscale without trade buttons; Freqtrade-style strategy row in /tracks. Reject custody of keys in chat.

- **Status:** partial
- **Action:** Ship P1 position cards only after fleet green
- **Paths:** data/grok-web-exports/2026-08-05_tg-terminal-oss-mine.md, lib/telegram/

#### AU-FLEET · Fleet recovery order before new alpha · high

Win desktop back online post-crash — finish post-boot (bugcheck, dumps, schtasks, Ollama VRAM, free-reign/killswitch parity Mac↔Win) before feature work. Find Win laptop (prior probe signal 9). Pi A/B mesh 10.77.4.x role inventory. One owner for post-boot until green.

- **Status:** ops_debt
- **Action:** Write WIN-POST-BOOT report before ARM Win traders
- **Paths:** data/device_topology.json, docs/ops/

#### AU-BUNDLE · Exact one-click approval bundles (task 053) · high

Immutable hash, expiry, exact actions and accounts, preconditions, limits, rollback, independent review, fail-closed partial execution. One approval covers one frozen bundle — never an evergreen blank check. Aligns with free-reign mandate + AXTI risk automation.

- **Status:** in_progress
- **Action:** —
- **Paths:** lib/autonomy/, docs/process/

#### AU-KNOW · Knowledge embed integrity blockers (task 050) · high

NO-SHIP despite 238 tests: (1) 1,024-d all-zero embedding could persist; (2) missing/empty vector store with matching incremental hashes could be mislabeled healthy. Repair in isolated worktree only — live Knowledge/cron/vector store untouched until fixed.

- **Status:** blocked
- **Action:** —
- **Paths:** lib/intel/bq_vector_store.py, lib/intel/embedders.py

#### AU-01 · Fund factory loops no-op under killswitch / paper · medium

T12/T15 services can stay live while paused; journals stamp refused actions. Fund-factory Phase-1 paper rails built (RH-agentic, RH-L2, MegaETH) on feat branch — not live money.

- **Status:** verified
- **Action:** —
- **Paths:** lib/trading/, services/

#### AU-02 · Few scheduled tasks actually installed · high

Docs list many tasks; Mac may only have a handful. Don’t assume market-pulse exists from docs alone. Magnum-night-watch disabled (auto-resurrection hazard on disarmed gate).

- **Status:** ops_debt
- **Action:** —
- **Paths:** infra/, docs/routines-manifest.md


### Bridge

#### BR-05 · Grok web ↔ local knowledge bridge is LIVE · high

Canonical path arigatoexpress/Sapphire data/grok-web-exports/. Web MCP write verified. Local loop: git pull → Knowledge/0-Inbox/grok-web/ → densify/Ralph → plant. sync_grok_web_exports.sh. Prefer structured trade ideas: instrument/venue/size/thesis/falsifier/confidence/horizon/risk notes.

- **Status:** verified
- **Paths:** data/grok-web-exports/README.md, data/grok-web-exports/

#### BR-01 · SuperGrok OIDC transport is live · high

Grok CLI session reaches api.x.ai with grok-4.5. Agents can call SuperGrok without a separate metered API key while the session is valid. Research workers only.

- **Status:** verified
- **Paths:** lib/intel/, data/grok-web-exports/

#### BR-02 · Transport priority: Mac → OIDC → API key → sim · high

Prefer Safari bridge when GROK_BRIDGE_URL is healthy; fall back to SuperGrok OIDC, then XAI_API_KEY, then away-sim for offline tests.

- **Status:** verified
- **Paths:** data/grok-web-exports/2026-08-05_bridge-setup.md

#### BR-04 · Mac Safari bridge unreachable remotely · medium

Port 19998 / host Mac not reachable from remote sandboxes. Expected while away — set GROK_BRIDGE_URL + tunnel when home. Plant deck stays :8100; API :8099.

- **Status:** known
- **Paths:** data/grok-web-exports/2026-08-05_bridge-setup.md


### Thesis

#### OP-02 · Active clusters: crypto_risk_perp · ai_narrative · space · sound_money · high

Cluster sizing rule: size as one bet per cluster. crypto_risk_perp = HYPE+LIT (perp volume + BTC risk appetite). ai_narrative = BOT/PLTR/VVV. space = SPCX/DXYZ/ARKX. sound_money = GLD/IBIT. Weakest held vibe BOT → trim_or_hedge_cluster bias.

- **Status:** research
- **Action:** —

#### TR-PROBE · Probe quant module archived as reference (Walter/CVNA/BHF) · medium

Local deterministic package: long_put, put_spread, position_size, deal_spread, stake_sensitivity + monitor rules (CVNA ≥8% day, vol ≥2×, IVR ≥75, BHF discount ≥15%, tagged events). No live brokerage. Archived from primary 24h loop; prefer thesis-aligned surfaces (tokenized equities, perps infra, verifiable AI).

- **Status:** archived_module
- **Action:** —

#### TH-THESIS · Core thesis filter for opportunity scoring · high

Prioritize asymmetric upside with: real product usage, clean value accrual, verifiability edge (ZK/TEE/on-chain proofs), regulatory/structural tailwinds, fit with Sapphire self-sovereign AI + RWA + agentic trading. Domains: Ondo/RWA rails, Lighter/HL perps, 0G verifiable compute, MegaETH/MOSS, RH Chain natives (INDEX/VEX/WAY).

- **Status:** accepted
- **Action:** —

#### TH-02 · HYPE unlock drift + unstaking overhang · high

Unlock date trackers drifted; large 7d unstaking queue. Re-underwrite Cluster A (HYPE+LIT) before any size. Still in crypto_risk_perp cluster on 2026-08-06 feed.

- **Status:** research
- **Action:** Update unlock calendar; no size-up until re-underwrite

#### TH-03 · LIT Dec cliff multi-source · high

LIT framed as perp-DEX not privacy; cliff ~2026-12-27 multi-source confirm. Combined Cluster A cap with HYPE. Verifiability + burn/buyback lessons from Lighter interview still stack-relevant.

- **Status:** research
- **Action:** —


### Architecture

#### SV-REPO · Canonical live surfaces: Sapphire + ops-state · high

One brain: ~/Code/Sapphire monorepo + ~/ops-state plant state (finish-line, telegram-bot, rh-chain, moss). Project-Go-Forward is THO client FENCED. Do not merge task*/ops-server/fleet-lease/quant-perps trees into Sapphire without ≥2 call-site extraction. Archive candidates: *.RETIRED-* after symlink safety check.

- **Status:** accepted

#### SV-01 · Local-first authority boundary · critical

fleet-lease, local Knowledge, and Git remain canonical. Drive and Notion are projections. Models receive exact capability-scoped tasks and return hashes/tests/receipts; they do not own policy or task truth. Local Ollama/aider/Hermes is the 24/7 baseline; subscription CLIs are replaceable burst/review workers.

- **Status:** accepted

#### TR-EDGE · Adaptive trading lab hot path (not LLM-as-trader) · high

point-in-time events → deterministic features → strategy candidates → contextual allocator → portfolio/risk → proof-carrying execution → broker reconciliation → realized reward → online update. LLMs in slow research loop only. NO_TRADE is an arm. Capital ladder: historical → shadow → paper → min live → bounded scale from after-cost evidence.

- **Status:** accepted

#### SV-SP0 · Keep chassis; rebuild trading brain · high

Scorched-earth reframe: chassis healthy (~phases 0–3/5, verify-GREEN). Failure was alpha generation (alpha-zoo 0/27, sniper killed, ICE-MOM-17/Alpha42 retired, SONNY honeypot). Arena = RH Agentic + RH L2/Chain + MegaETH MOSS — Aster deprecated. Archive never blind-delete.

- **Status:** accepted


## Merge map

| Artifact | Path |
|---|---|
| This scour (human + machine) | `data/grok-web-exports/2026-08-06_alpha-scour-merge.md` |
| Chat alpha ledger (human) | `docs/alpha/GROK-CHAT-ALPHA-2026-08-06.md` |
| Machine-readable ledger | `data/alpha/alpha_ledger.json` |
| Grok web knowledge bridge | `data/grok-web-exports/` |
| AXTI + dens learnings | `data/grok-web-exports/2026-08-05_alpha-learnings-axti-l2.md` |
| Master Opus handoff | `data/grok-web-exports/2026-08-05_master-handoff-claude-opus.md` |
| Fleet recovery handoff | `data/grok-web-exports/2026-08-05_fleet-win-recovery-handoff.md` |
| Trading edge plan (source Drive) | `docs/trading-strategy-lab.md` |

## Priority actions for plant (not executed here)

1. Confirm dust sleeve sells fill at RTH (do not re-place / cancel).
2. Renew MOSS grant (hours_left was negative on 2026-08-06 feed).
3. Finish Win post-boot + free-reign/killswitch parity before ARM Win traders.
4. After exits: AXTI-class defined-risk option probes + automated TP half@2× / SL−40%.
5. Wire genome outcomes win/loss from closed trades; dens stay.
6. Keep Grok web exports flowing → densify → plant deck :8100.

## Explicit non-goals

- THO / Project-Go-Forward deploy or DNS
- Hermes messaging send
- Revive per-trade Telegram approval cards
- Blind merge of task* / ops-server / quant-perps trees into Sapphire
- Live orders from this web session

---

*Generated by Grok Build alpha scour for Codex / plant continuity.*
