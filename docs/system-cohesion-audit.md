# Sapphire OS — System Cohesion Audit
**Date:** 2026-04-14  
**Author:** Claude (overnight session)  
**Status:** Living document — update after each major sprint  

---

## Executive Summary

Sapphire OS is architecturally sound and technically impressive. The hardware stack is calibrated, the inference proxy is production-grade, and the signal pipeline has real financial engineering in it (Kelly sizing, confirmation firewall, risk kernel). But the system suffers from a specific class of problem: **the advanced components exist but nothing calls them**.

`trading_brain.py` — a unified GO/WAIT/EXIT decision engine combining TA + Kronos + FRED macro + paper trader track record — already exists. Nobody runs it on a schedule. `kronos_predict.py` — a foundation model wrapper — already exists. It's not wired into the signal pipeline. `lead_engine.py` — an AI outbound sales engine reading Regional Intel data — already exists. It's never been called from a scheduled task or hermes skill.

The gap isn't missing features. It's **missing wiring**. This document maps the wires.

---

## Part A — Current State Assessment

### Tier 1: Production-Ready (works reliably)

| Component | Evidence |
|-----------|----------|
| Inference proxy (4-tier failover) | Benchmark-calibrated, circuit breakers, sensitivity gate, /metrics |
| Signal pipeline | HardRiskKernel, Kelly sizing, confirmation firewall, JSONL audit trail |
| Hermes bot | 12 skills, gateway process, Telegram DM working since April |
| Trading signal flow | TradingView → webhook → signal-logger → Telegram |
| Pi cluster | rari1 + rari2 Ollama healthy, llama-rpc deployed |
| Dashboard (core pages) | overview, system, signals, agents — fresh data, no broken calls |
| Regional Intel workbench | 30+ API endpoints, collections/bundles/monitors, intel graph |
| OpenBB API | 32 providers, crypto + equity + macro data |

### Tier 2: Built but Idle (exists, not called)

| Component | What It Does | Why Idle |
|-----------|-------------|---------|
| `trading_brain.py` | GO/WAIT/EXIT decision from 5 signal sources | No hermes skill, no scheduled task, no dashboard page |
| `kronos_predict.py` | 24h OHLCV forecast via Kronos-base | Model weights may not be downloaded; not wired into predict.py |
| `lead_engine.py` | Analyze ICPs, discover leads from Regional Intel, generate outreach | No scheduled task, no campaign trigger |
| `tho_intel.py` | THO operations plugin | Hermes skill exists (tho-operations), but no scheduled analysis |
| `macro_data.py` / `macro-data` skill | FRED GDP, CPI, rates, housing | Not in morning briefing, not in trading context |
| `lumo.py` | External Sapphire Alpha strategy fetch | No scheduled call, not wired to dashboard |
| Confirmation firewall | Requires Telegram confirmation for high-confidence signals | Wired in signal_pipeline, but paper trader doesn't read confirmed status |
| Redis | Running healthy | Zero actual usage — health-checked but never read/written |

### Tier 3: Stubs / Incomplete

| Component | Issue |
|-----------|-------|
| `signal_stats()` — win rate | Always returns `win_rate: null` — `outcome` field never written back |
| Paper trader positions | `paper-trading` skill.md has hardcoded positions (BTC @$72K, ETH @$2.2K) — may be stale |
| Kimi relay group | `KIMI_RELAY_CHAT_ID` empty — no shared Telegram group created yet |
| Kronos weights | `NeoQuasar/Kronos-base` not confirmed downloaded on Windows GPU |
| world_knowledge | 2 files (architecture + runbooks). Should be a rich KB: model roster, signal spec, skill catalog, data dictionaries |
| health.html iframe | Embeds `sapphire-health-dashboard-s77j6bxyra-uc.a.run.app` — stale Cloud Run URL |
| command_deck.html iframe | Embeds `sapphire-command-deck-267358751314.us-central1.run.app` — stale Cloud Run URL |

### Tier 4: Broken / Dead Weight

| Component | Issue |
|-----------|-------|
| Redis (homebrew.mxcl.redis) | Consuming ~50 MB RAM, checked in 3 health endpoints, not used for anything |
| 7 orphaned dashboard templates | health, command_deck, production_readiness, logs, platform, infrastructure, settings — no nav links |
| architecture.md model aliases | Stale — still shows `code → qwen2.5-coder:14b` (real: `gemma4:latest`); three places now diverged |
| Pi RPC sidecar | Setup script deployed, servers running on both Pis, but GPU→Pi WiFi bottleneck makes it useless for 32B models |
| Aster/Hyperliquid services | Listed in module map, `[paused, needs Pi]` / `[stub, needs Pi]` — no progress path defined |

---

## Part B — Architecture Cohesion Plan

### What ONE System Looks Like

Right now, information flows like this:

```
TradingView → signal_pipeline → JSONL → Telegram (dead end)
OpenBB → market.py → on-demand only
Kronos → kronos_predict.py → never called
FRED → macro_data.py → never in trading context
paper_trader → positions → never feeds back into signal scoring
threat-intel → CLI → Telegram (no pipeline output)
Regional Intel → :8787 → no connection to anything else
```

It should flow like this:

```
 ┌─────────────── INTELLIGENCE LAYER ────────────────┐
 │  OpenBB OHLCV + FRED macro + TradingView CDP       │
 │  → trading_brain.py  (GO/WAIT/EXIT, confidence)    │
 │  → threat_intel      (CISA KEV, NVD, infra risk)   │
 │  → regional_intel    (leads, permits, news)         │
 └────────────────────┬───────────────────────────────┘
                      │ unified signals + decisions
 ┌────────────────────▼───────────────────────────────┐
 │            PROCESSING LAYER                        │
 │  signal_pipeline  (risk kernel, Kelly, firewall)   │
 │  paper_trader     (execute, track, close)          │
 │  lead_engine      (discover, score, outreach)      │
 └────────────────────┬───────────────────────────────┘
                      │ audit trail + events
 ┌────────────────────▼───────────────────────────────┐
 │              OUTPUT LAYER                          │
 │  data/signals/   data/intelligence/  data/leads/   │
 │  Telegram alerts (hermes → user)                   │
 │  Dashboard pages (overview, trading, intel, ops)   │
 └────────────────────────────────────────────────────┘
```

### The Missing Layer: data/intelligence/

Every component writes to its own silo. The one missing convention is a shared intelligence directory at `~/Code/Sapphire/data/intelligence/` with a predictable schema:

```
data/intelligence/
├── YYYY-MM-DD/
│   ├── trading.json        ← trading_brain daily decision
│   ├── threats.json        ← threat-intel sweep results  
│   ├── macro.json          ← FRED macro snapshot
│   ├── regional.json       ← regional intel highlights
│   └── summary.json        ← cross-source synthesis for morning briefing
```

The morning-briefing task reads `data/intelligence/YYYY-MM-DD/summary.json`. Everything else writes to it. This is a pure convention — no new code, just discipline.

### The Missing Bridge: trading_brain as daily gate

`trading_brain.py` aggregates 5 sources into a single trading decision. It should run:
1. As part of `market-pulse` scheduled task (currently just scans RSI/MACD)
2. As the entry point before signal_pipeline.process() for autonomous signals
3. Exposed via a hermes skill (`/brain BTC` → GO/WAIT/EXIT with full reasoning)

This transforms signal generation from "TradingView fired an alert" to "5 independent systems agree".

---

## Part C — Top 10 Highest-Impact Changes

Ranked by: (cohesion impact × implementation effort⁻¹). Not new features — integration and quality.

### 1. Create data/intelligence/ convention + wire morning-briefing
**Effort:** 1 hour | **Impact:** every scheduled task becomes additive  
The morning briefing currently runs in isolation. If each of the 6 data-generating tasks (threat-intel-sweep, trading-research, macro-data, regional-intel, vote-monitor, github-discovery) writes a structured JSON to `data/intelligence/YYYY-MM-DD/`, the morning-briefing becomes a genuine synthesis document instead of reruns of each task.  
**Implementation:** Create directory, add one `write_intel_snapshot()` call to each task's end, update morning-briefing to read + synthesize.

### 2. Wire trading_brain.py into market-pulse scheduled task
**Effort:** 2 hours | **Impact:** signals become multi-source consensus, not single-source noise  
`trading_brain.py` already aggregates TA + Kronos + macro + paper tracker. `market-pulse` currently just calls `signal_generator.py`. Replace with `trading_brain.decide(symbol)` → if GO with ≥ 70% confidence → generate signal → signal_pipeline.  
**Implementation:** Edit the market-pulse task prompt to call trading_brain first. The tool already exists.

### 3. Add trading_brain hermes skill
**Effort:** 30 min | **Impact:** user gets unified intelligence at `/brain BTC`  
Currently hermes has `trading-analysis` AND `trading-signals` — overlapping skills. Replace both with one `/brain` skill that calls `trading_brain.dashboard()` for overview or `trading_brain.decide(symbol)` for specific symbol. Returns GO/WAIT/EXIT with full reasoning chain.  
**Implementation:** Write one skill.md. Retire/consolidate the two overlapping skills.

### 4. Fix signal outcome tracking (close the feedback loop)
**Effort:** 2 hours | **Impact:** win_rate goes from always-None to real data  
The paper trader closes positions when stops/TPs hit (`check_stops` action). When it closes a position, write `{"outcome": "win", "pnl_usd": N}` back to that day's signal JSONL. `signal_stats()` then returns real numbers.  
**Implementation:** Add `_write_outcome_to_audit()` in `paper_trader.py` when position closes.

### 5. Consolidate hermes skills: 12 → 7
**Effort:** 1 hour | **Impact:** Hermes routes correctly, no ambiguous trigger matches  
Current overlaps:
- `trading-analysis` + `trading-signals` → **`trading`** (one skill, covers prices + signals + paper portfolio)
- `system-ops` + `inference-tier` → **`system`** (one skill, covers all status)
- `regional-intel` stays (unique domain)
- `threat-intel` stays (unique domain)
- `tho-operations` stays (unique domain)
- `repo-discovery` + `kimi-delegate` → low usage, fold into `system`
- `paper-trading` → absorbed into unified `trading` skill  
**Result:** 7 focused skills with clean trigger separation.

### 6. Replace Redis with actual usage or remove it
**Effort:** 1 hour | **Impact:** clarity + 50 MB RAM freed  
Redis is checked in 3 health endpoints and listed in 2 service tables, but never used. Two options:  
**Option A (use it):** Wire signal pipeline to use Redis for confirmation token storage (currently uses in-memory dict — loses tokens on restart) and signal deduplication (same symbol/direction within 5 min). This makes the confirmation firewall crash-safe.  
**Option B (remove it):** Stop the service, remove from health checks and service tables. Be honest about what the system needs.  
**Recommendation:** Option A — the confirmation firewall's in-memory state is a real reliability gap; Redis solves it cleanly.

### 7. Update world_knowledge to be a living system KB
**Effort:** 1 hour | **Impact:** hermes and claw-code have accurate context about the system  
`world_knowledge/` has 2 files, both partially stale. Should have: model roster (currently accurate), skill catalog (what each skill does and when to use it), data dictionary (what each JSONL schema looks like), signal spec (how scores are calculated), campaign data index. The search_index.py already exists — populate it.

### 8. Kronos on Windows: verify weights, wire into predict.py
**Effort:** 3 hours | **Impact:** trading predictions go from heuristic to evidence-based  
`kronos_predict.py` already exists. But Kronos-base weights (NeoQuasar/Kronos-base) need to be downloaded to Windows GPU at `D:\models\kronos\`. Once confirmed:
1. Wire `kronos_predict.py` as a factor in `predict.py`'s 6-factor score (add as 7th factor, weight ~15%)
2. The integration plan document already has exact implementation steps.

### 9. Threat intel on dashboard overview page
**Effort:** 1 hour | **Impact:** security context visible without switching tools  
The threat-intel scheduled task runs 2x/day and writes to Telegram. But it produces no persistent output that the dashboard can read. Add:
1. A `data/intelligence/threats_latest.json` write step to threat-intel-sweep task
2. A small "CISA KEV Feed" card on the dashboard overview page reading that file

### 10. Navigation audit: add 3 pages, fix 2 stale iframes
**Effort:** 30 min | **Impact:** dashboard is complete and navigable  
Three pages (health, command_deck, production_readiness) have routes but no nav links. Two templates (health.html, command_deck.html) embed stale Cloud Run URLs via iframe. Fix the nav, replace iframes with local data panels.

---

## Part D — Dashboard Unification Plan

### Current State: 20+ routes, no information architecture
The dashboard grew organically. Routes were added to serve templates, templates were copied from other projects, APIs were added to serve templates. Many pages duplicate data that's already visible elsewhere. Some pages reference external URLs that no longer exist.

### Proposed: 8 pages with clear purpose hierarchy

| Page | URL | Source | Purpose |
|------|-----|--------|---------|
| **Overview** | `/` | `/api/system` + `/api/signals` | Health at a glance: services, active tier, 5 signals, paper PnL |
| **Trading** | `/trading` | signal pipeline + paper trader + trading_brain | Full trading view: signals, open positions, PnL, decision engine status |
| **Intelligence** | `/intelligence` | threat intel + regional intel highlights | Threat feed, CVE alerts, lead pipeline stats, macro context |
| **Infrastructure** | `/system` | `/api/system` | Inference tiers, Mac services, Pi cluster, CDP connection |
| **Pi Agents** | `/agents` | `/api/agents` | Pi vitals, agent health, deployment reference |
| **Operations** | `/operations` | control-plane `/api/frontend/ops-status` | Tasks, events, project board — embed from :8082 or proxy API |
| **Regional** | `/regional` | redirect to `:8787/intel/v2` | Elite Net campaign, intel graph, lead table |
| **Benchmarks** | `/benchmarks` | static HTML | GPU benchmark report (already correct) |

**What gets removed from nav:**
- `/health-status` — duplicate of overview health section
- `/command-deck` — stale Cloud Run iframe, no local replacement
- `/production-readiness` — useful for launch gates but not daily workflow; link from infrastructure page
- `/architecture`, `/activity`, `/sapphire-book`, `/organization` — move to `/operations` page or remove

**What stays but gets cleaned up:**
- `/settings` — system config (keep, but make it actually functional)

### Design consistency rules (non-negotiable)
1. No CDN dependencies except Leaflet (for maps only) — all CSS/JS is local
2. Every page auto-refreshes or has a visible "last updated" timestamp
3. Empty states are explicit and helpful ("No signals today — pipeline is healthy")
4. Font Awesome icons: load in base.html or replace with inline SVG
5. Grid: use `grid-2` or `grid-4`, never `grid-cols-*` (Tailwind class, not defined)

---

## Part E — Automation Opportunities

### Currently manual → should be automated

| Manual Action | Automation Approach | Priority |
|---------------|--------------------| ---------|
| Run trading_brain before a trade | Wire into market-pulse task | High |
| Update world_knowledge after system changes | Add to self-improvement task | Medium |
| Write intelligence snapshots from each task | Add `write_intel_snapshot()` to each task | High |
| Close paper trades and write outcomes | Add to market-pulse: call `check_stops` after each cycle | High |
| Download Kronos weights on Windows | One-time setup, add to Windows setup docs | Medium |
| Create Kimi relay Telegram group | Manual step — user must do this | Low |
| Update hermes skill model aliases after proxy update | Add to self-improvement task: diff proxy MODEL_TIERS vs skill.md | Medium |

### 19 Scheduled Tasks — cohesion gaps

The tasks fire independently. None reads output from another. The intelligence layer (data/intelligence/) proposal addresses this. Until then:

- **morning-briefing** reads no structured data → should read `data/intelligence/YYYY-MM-DD/*.json`
- **market-pulse** calls signal_generator directly → should call trading_brain first
- **trading-research** produces output → should write to `data/intelligence/`
- **threat-intel-sweep** → writes to Telegram, loses data → should write to `data/intelligence/threats_latest.json`

---

## Part F — Quality Scorecard

| Component | Complete | Tests | Docs | Integration | Total |
|-----------|---------|-------|------|-------------|-------|
| Inference proxy | 5/5 | 4/5 | 4/5 | 5/5 | 18/20 |
| Signal pipeline | 5/5 | 4/5 | 4/5 | 3/5 | 16/20 |
| Hermes bot (12 skills) | 4/5 | 2/5 | 3/5 | 3/5 | 12/20 |
| trading_brain.py | 4/5 | 2/5 | 3/5 | 1/5 | 10/20 |
| kronos_predict.py | 3/5 | 1/5 | 3/5 | 1/5 | 8/20 |
| lead_engine.py | 3/5 | 1/5 | 2/5 | 1/5 | 7/20 |
| Dashboard | 3/5 | 1/5 | 2/5 | 3/5 | 9/20 |
| Regional Intel | 5/5 | 3/5 | 4/5 | 2/5 | 14/20 |
| Paper trader | 4/5 | 2/5 | 3/5 | 2/5 | 11/20 |
| Control-plane | 5/5 | 3/5 | 3/5 | 1/5 | 12/20 |
| Cyber threat bot | 4/5 | 3/5 | 4/5 | 2/5 | 13/20 |
| world_knowledge | 2/5 | 1/5 | 3/5 | 2/5 | 8/20 |
| Redis | 0/5 | 0/5 | 0/5 | 0/5 | 0/20 |

**System cohesion score (before tonight's work):** 60/100  
**After tonight's work:** ~68/100 (dashboard fixes, Regional Intel theming, 3 new APIs, hermes skill updates, nav links)  
**After implementing Top 10 changes above:** ~82/100 estimated

---

## Part G — The Bigger Vision

At its best, Sapphire OS is not a collection of tools — it's an **autonomous intelligence operator** that runs while the user is away.

The model is: **observe → reason → act → record → learn**.

What that looks like in practice:
- At 5:42 AM, trading-research wakes up. It calls `trading_brain.decide()` for BTC/ETH/SOL. The brain consults TA, Kronos forecast, FRED macro, and paper trader track record. It writes structured findings to `data/intelligence/2026-04-15/trading.json`.
- At 6:30 AM, threat-intel-sweep scans CISA KEV and NVD. It finds 2 critical CVEs. It writes `data/intelligence/2026-04-15/threats.json` and sends a Telegram alert.
- At 8:00 AM, morning-briefing reads every `data/intelligence/2026-04-15/*.json` file, synthesizes them, and sends a single structured brief: "BTC: WAIT (Kronos forecasts 2% pullback, R1 holds). No system threats. 2 new ENS leads from Near Northside permits."
- When the user asks `/brain ETH` in Telegram, hermes calls `trading_brain.decide("ETH")` and returns the full reasoning chain in 3 seconds.
- When a signal fires with confidence ≥ 0.75, paper_trader executes it. When the stop hits 4 hours later, `outcome: "loss"` is written back to the signal JSONL. Win rate is now 58.3% (real number, not null).

None of this requires new infrastructure. It requires wiring what already exists.

The system is much closer to this vision than it looks. The gap is 10 targeted integration changes, not 10 new features.

---

## Quick Reference: Files to Change

| Change | Files |
|--------|-------|
| data/intelligence/ convention | Create dir, update each scheduled task |
| trading_brain in market-pulse | `~/.claude/scheduled-tasks/market-pulse.md` |
| trading_brain hermes skill | `~/.hermes/skills/sapphire/trading/skill.md` (new) |
| Signal outcome tracking | `plugins/claw-sapphire/tools/paper_trader.py` |
| Redis → confirmation token store | `lib/core/src/confirmation_firewall.py` |
| Dashboard nav: add 3 pages | `services/dashboard/templates/base.html` |
| Fix stale iframes | `templates/pages/health.html`, `command_deck.html` |
| world_knowledge update | `~/world_knowledge/sapphire/` |
| Threat intel snapshot write | Scheduled task: `threat-intel-sweep` |
| Hermes skill consolidation | `~/.hermes/skills/sapphire/` |
