# Sapphire OS — Architecture Review
**Date:** 2026-04-19 (Sunday experiment, fresh-eyes pass)
**Reviewer:** creative-experimenter scheduled task

---

## Summary

Reviewed the full Sapphire monorepo with fresh eyes across: plugin tools, services,
inference routing, test coverage, and data layout. Found one critical structural issue,
two important fragilities, and several genuine architectural strengths.

---

## What's Brilliant

### 1. Keyword classification fallback (`lib/router.py:_keyword_classify`)
If Nemotron is down, dispatch falls back to deterministic keyword matching. Zero LLM
dependency for basic routing. This is exactly the right defensive design — the fast path
is free GPU inference, the safe path is pure Python. No single point of failure.

### 2. 4-tier inference-proxy failover chain
GPU (Windows 5070Ti) → Pi rari1/rari2 → Mac CPU → Kimi Cloud. The T4 Kimi Cloud
fallback means hermes-agent survives a full Mac+GPU outage. Recent upgrade from brittle
Kimi CLI subprocess to HTTP API (no auth expiry) was the right call.

### 3. Dispatch → Router → Executor layering (`dispatch.py` → `router.py`)
Clean separation: dispatch.py handles policy + fallback chain orchestration, router.py
handles per-tier execution. A new tier needs one function in router.py plus a dict entry.

### 4. T0 free tier (Nemotron at 232 tok/s)
Read-only analysis tasks (explain, scan, summarize, status) hit Nemotron for free before
any paid tier is touched. With 19 scheduled tasks running daily, this is meaningful
cost avoidance.

### 5. paper_trader.py isolation (565 lines, self-contained)
Paper trading simulator is completely isolated from live signals. PAPER_TRADING=1 env
flag gates the whole pipeline. No risk of live order bleed.

---

## What's Fragile

### CRITICAL: 25 of 32 tools are unregistered in plugin.json

**plugin.json registers 7 tools:** dispatch, verify, budget, state, status, notify, market

**Unregistered (accessible only via direct subprocess or scheduled tasks):**
backtest, crypto_portfolio, digest, events, health_check, kronos_predict,
lead_engine, lead_enrich, lumo, lumo_research, macro_data, market_sentiment,
paper_trader, predict, predict_kronos, qa_aware_factory, research, signal_generator,
solana_wallet, starred_repos, tho_intel, threat_intel, trading_brain, vote_monitor, watchdog

This means claw-code can't call these tools by name — they must be invoked as raw
subprocess commands by scheduled tasks. Any refactor that moves a file breaks the
scheduled task path silently. **The 19-tool count in memory is wrong — the registered
tool count is 7.** The rest are CLI scripts, not plugin tools.

**Recommendation:** Either register them in plugin.json or document them clearly as
"scheduled-task-only scripts" with a different directory (`scripts/` instead of `tools/`).

### Three overlapping Kronos/predict tools

| File | Description | LOC |
|------|-------------|-----|
| `predict.py` | TA-based (RSI/MACD/BB) predictions via OpenBB | 348 |
| `predict_kronos.py` | Kronos ML model via OpenBB, `import requests` | 477 |
| `kronos_predict.py` | Another Kronos wrapper, simpler, `urllib` | 169 |

`predict_kronos.py` uses `import requests` (not installed in most envs) while all
other tools use stdlib `urllib`. This will silently fail if `requests` isn't available.
`kronos_predict.py` and `predict_kronos.py` are ~80% overlapping in purpose.

**Recommendation:** Consolidate to `predict.py` (TA) + `kronos.py` (ML). Delete
`kronos_predict.py` (older, simpler, missing features).

### Misleading lumo naming

`lumo.py` = Sapphire platform API reader (fetches strategy-ops, intel-summary from sapphirealpha.xyz)
`lumo_research.py` = Proton Lumo AI (privacy-first LLM for security research via localhost:3333)

These are completely different systems. Any dev seeing `lumo.py` next to `lumo_research.py`
will be confused. The Proton Lumo tool would be better named `proton_ai.py` or `security_ai.py`.

---

## What's Redundant / Could Be Pruned

### 1. HTTP utility fragmentation (15+ tools rolling their own urllib)
Every tool has its own `_get_json(url, timeout)` pattern. This is copy-paste across
tools, making it hard to add auth headers, retry logic, or a timeout policy globally.
A `lib/http.py` with `get_json(url, timeout, headers={})` would unify this — but it's
low urgency since the current pattern works.

### 2. Control-plane monolith risk
`main.py` (1456 lines) + `control_plane.py` (2880 lines) + `project_board.py` (1511 lines)
= **5847 lines** in 3 tightly coupled files. This is manageable now but will resist
refactoring as features compound. No immediate action needed but worth watching.

### 3. `data/experiments/` didn't exist before this run
The creative-experimenter task has been running but writing nowhere. This is the first
file in this directory. Either prior runs wrote elsewhere or the task was never
completing successfully.

### 4. plugin.json version still v0.3.0 (memory says v0.4.0)
Minor version drift — update the manifest version to match system state.

---

## Plugin.json Tools vs Actual Tool Files

| Status | Tools |
|--------|-------|
| Registered in plugin.json | dispatch, verify, budget, state, status, notify, market |
| Exist as CLI scripts only | backtest, crypto_portfolio, digest, events, health_check, kronos_predict, lead_engine, lead_enrich, lumo, lumo_research, macro_data, market_sentiment, paper_trader, predict, predict_kronos, qa_aware_factory, research, signal_generator, solana_wallet, starred_repos, tho_intel, threat_intel, trading_brain, vote_monitor, watchdog |

---

## Recommended Actions (Prioritized)

1. **[HIGH]** Fix `predict_kronos.py` `import requests` — replace with `urllib.request`
   to match all other tools and avoid silent import failures.

2. **[HIGH]** Clarify tool vs script: rename `tools/` files that are scheduled-task-only
   to `scripts/` or document the distinction in CLAUDE.md.

3. **[MEDIUM]** Consolidate `kronos_predict.py` + `predict_kronos.py` → single `kronos.py`.

4. **[MEDIUM]** Rename `lumo_research.py` → `proton_ai.py` to eliminate naming confusion.

5. **[LOW]** Bump `plugin.json` version to `0.4.0`.

6. **[LOW]** Create `lib/http.py` shared utility when adding the 4th tool that needs
   retry logic or auth headers — not yet.

---

## Architecture Verdict

The inference routing layer (proxy + dispatch + router) is **well-designed** — resilient,
tiered, and cost-conscious. The weak point is the plugin registration gap: most tools
exist as loose Python scripts with no formal claw-code integration, making the system
harder to introspect and easier to break silently. The fix is documentation or
consolidation, not a rewrite.
