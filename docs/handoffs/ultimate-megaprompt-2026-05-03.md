# Ultimate Handoff Megaprompt — 2026-05-03 (refreshed)

**Authoritative timestamp:** 2026-05-03. Sapphire `main` HEAD: verify with `git -C ~/Code/Sapphire log --oneline -1`.
**Scope:** any session — Mac, Windows, cloud routine — opening this file gets a complete current-state briefing AND the explicit next-mission charter.

---

## Section A — what's already shipped (this overnight run)

**16 commits, 13 PRs admin-merged across 7 dispatch tranches** (tranches 0–6 + handoff). HEAD trail:

```
628 docs(handoff): ultimate megaprompt + outstanding TODOs
626 chore: Pine analyzer — screener rules + --strict mode
624 feat: Hermes skill stub for tradingview-orchestrator
622 feat: /performance system readiness SLO panel + 15min cache LaunchAgent
620 docs(CLAUDE.md): refresh after 2026-04-30 → 2026-05-03 TV orchestrator + Pine analyzer + plugin tool
619 chore: Pine static analyzer tests + pre-commit + CI hook
618 fix(test): bump manifest registered-tool count to 17 for sapphire_tradingview
616 test: cover sapphire_tradingview plugin tool actions + read-only invariants
615 chore: salvage tranche-4 work after parallel agents hit rate limit
513 feat: TA capture scoring + dashboard surfacing
511 feat: SSE auto-refresh for TradingView orchestrator dashboard panel
510 feat: add Pine strategy + multi-symbol screener templates
509 docs: ADR 0012 — TradingView orchestrator architecture
508 chore: audit + annotate readiness sweep WARNs
507 docs: add TradingView orchestrator runbook
506 test: pin Pine ↔ webhook payload contract
505 feat: pine-promote action (set+compile+save in TV editor, gated)
```

**Surface delivered:** TradingView orchestrator (read-only by default, mutation-gated by `SAPPHIRE_TV_MUTATION_ENABLED=1`), 3 Pine generators (indicator/strategy/screener), Pine static analyzer with pre-commit + CI hooks, plugin tool `sapphire_tradingview`, 7 dashboard endpoints + System Readiness SLO panel, live SSE auto-refresh, 3 LaunchAgents (4-hourly capture / daily Pine batch / 15-min readiness cache), Hermes skill stub, ADR 0012, runbook, threat-intel auto-supersede rule, agent_only Windows TV agent state, 207 tests pass (was 110), sweep at 47 PASS / 9 WARN / 0 FAIL.

**Quality:** ruff clean, contract pinned by `tests/unit/test_pine_to_webhook_contract.py`, registry validates 73/0.

---

## Section B — NEXT-MISSION CHARTER (the user's 2026-05-03 ask)

> *"debug all of the errors and issues looking at the entire stack to make our trading system actually deepen the breadth and depth of analysis and work out the issues on our brain silo system and make the data more broad in depth and actually interesting as a consumer grade site, make it very readable and professional with simple explanations and then the deeper technical explanations, make our forecasting and prediction system more interesting, usable for consumers and show reasoning behind things."*

This breaks into **5 concrete workstreams**. Future sessions: pick one or parallelize.

### B1. Stack-wide error scan + fix

**Goal:** zero unexplained errors across signal pipeline → correlation → strategy lab → brain → dashboard.

Read first:
- `data/system_events.jsonl` (last 1000 events): `tail -1000 ~/Code/Sapphire/data/system_events.jsonl | grep -i "error\|fail\|exception" | tail -50`
- LaunchAgent stderr logs: `ls -lt ~/autonomy-status/logs/ | head -20`
- Sweep WARNs (9 currently): `python3 ~/Code/Sapphire/scripts/ops/production_readiness_sweep.py --json | jq '.checks[] | select(.status=="WARN")'`
- The 27 missing-envelope artifacts: `jq '.checks[] | select(.name=="artifact_envelopes")'` from the sweep cache

Fix or document each:
- Real bug → fix it, add test, ship PR.
- Environmental (machine offline, etc.) → note in the operator runbook.
- Drift (counts, schemas) → backfill or update assertions.

### B2. Brain silo system

**Goal:** identify what's failing in `lib/agents/`, `src/sapphire_core/cognitive_agent.py`, `src/sapphire_core/memory/`, and the inference proxy's brain routing.

Read:
- `services/inference-proxy/app.py` — 4-tier failover; check `/metrics` for tier-flap rate
- `lib/agents/alpha_agent.py` and `lib/agents/runner.py` — paper-only autonomous harness
- `src/sapphire_core/` — cognitive agent, executor, gateway, memory, telegram_bot
- Recent issues: any thread that says "brain" or "silo" in the last 200 system events

Likely failure modes to look for: tier flapping (windows-gpu degraded), kill switch trips (Class A WARN already known), memory file corruption, signal-routing dead letters in `data/events/bus.jsonl`.

### B3. Consumer-grade dashboard

**Goal:** the dashboard reads as a polished consumer product, not an internal debug tool. Each panel needs:
- A **plain-English headline** ("BTC is trending up — 3 signals fired today")
- An **inline expandable "How does this work?"** disclosing the technical detail
- **Clear safety status** (paper / live / dry-run / killswitch state)
- **Mobile-readable** (the analytics + performance pages are dense; some panels need responsive grid)

Touch points: `services/dashboard/templates/pages/{analytics,performance,index,showcase}.html` and the macros under `services/dashboard/templates/macros/`. Check existing styling tokens in `services/dashboard/static/`.

Don't refactor data layer; only the rendering layer.

### B4. Forecasting + prediction interpretability

**Goal:** when the dashboard shows a forecast, the user sees WHY.

Sources:
- `lib/analytics/forecast.py` — Kronos OHLCV + TA-scanner consensus, emits `consensus` (AGREE_BULL / AGREE_BEAR / etc.) and `edge_score`
- `lib/analytics/strategies/SapphireComposite.py` and friends — 7 quant strategies
- `lib/trading/tradingview_orchestrator.py::compute_quick_signal_score` — the deterministic scorer (RSI + MACD + EMA + change_pct + 5-bar trend, regime-bucketed)
- `data/intelligence/<date>/predictions.json` — Kronos daily output

Each forecast surface (analytics page Forecast card, performance page TA Score panel, signal Telegram alerts) should expose:
- **The score** (already does)
- **The components** (RSI: -0.3, MACD: +0.1, EMA: +0.4, ...) with sign
- **The regime** bucket (BULL / TRANSITION / BEAR with thresholds)
- **A 1-sentence rationale** in plain English
- **A "show math"** disclosure for the deep-tech view

Add as a new endpoint `/api/forecast/explain/<symbol>` that returns the structured rationale, then render on the dashboard.

### B5. Cross-repo documentation consistency

**Goal:** every satellite repo's README is current; CLAUDE.md is the single source of live wiring; ADRs cover irreversible decisions.

Repos: `Sapphire`, `claw-code` (upstream — read-only), `Project-Go-Forward`, `cyber-threat-bot`, `regional-intel-workbench`, `Cointracker`, `hermes-agent` (upstream — read-only), `tradingview-mcp-v2` (upstream — read-only).

For each owned repo (`Sapphire`, `Project-Go-Forward`, `cyber-threat-bot`, `regional-intel-workbench`, `Cointracker`):
- Verify README test counts match `python3 scripts/ops/test_inventory.py 2>&1` (Sapphire) or equivalent.
- Verify HEAD reference and feature list match current main.
- Add a "Last verified: YYYY-MM-DD" line if missing.

---

## Section C — operating envelope (do not violate)

**Trading critical path** — needs explicit user approval, never auto-merged:
- `services/hyperliquid/`, `services/alpha/`, `lib/portfolio/robinhood.py`
- Hyperliquid `policy.signing_verified=False` — keep mainnet refused until operator flips manually
- Robinhood live-capital posture — $5/order cap, manual-only, crypto-only, 14-day Sortino soak ticking

**Read-only by default:**
- All scheduled LaunchAgents
- Hermes skill (plugin tool dispatcher refuses mutation regardless of env)
- Pine `pine-promote` action requires `--mutate` AND `SAPPHIRE_TV_MUTATION_ENABLED=1`

**Safety primitives — never refactor in one PR:**
- `lib/core/kill_switch.py`
- `lib/core/confirmation_firewall.py`
- `lib/security/`

---

## Section D — quality gates the next agent must hit

Every PR before admin-merge:
- `ruff check .` clean (or only on changed files for surgical PRs)
- `pytest` on the relevant suite passes
- `python3 scripts/validate_tool_registry.py` exits 0 if plugin manifest changed
- For UI PRs: load the dashboard locally and `curl` the affected endpoint with auth
- For Pine PRs: `python3 scripts/lint_pine.py pine/standalone/*.pine` exits 0; if `tv` CLI is available, server-side `tv pine check` shows `compiled=True`

---

## Section E — known WARNs (don't re-investigate; they're documented)

9 sweep WARNs as of 2026-05-03 14:30 UTC:
1. `org/satellite_merge_posture` — Class A, admin-squash policy
2. `local/inference_proxy_health` — Pi tiers disabled, Windows GPU degraded marker
3. `local/tradingview_cdp_version` — Mac TV Desktop needs `--remote-debugging-port=9222` (operator action)
4. `windows/research_worker_freshness` — sha 22b243e from 2026-05-02, will refresh on next scheduled run
5. `windows/telemetry_dashboard_tcp` — Windows :3001 unreachable, restart Scheduled Task
6. `provenance/artifact_envelopes` — 27 missing from parallel-workstream PRs
7. `routines/backtest-weekly` — Class A, soak collector cutover ~2026-05-24
8. `routines/content-engine` — Class A, soak collector cutover ~2026-05-04
9. `gcp/gate_gemini_api_or_vertex_live_calls` — Class A, manual_gate is steady state

Block-comments + classification doc: `docs/ops/readiness-warn-state-2026-04-30.md` and `scripts/ops/production_readiness_sweep.py`.

---

## Section F — authoritative docs (read before changing things)

- `CLAUDE.md` (live "what's where" — refreshed 2026-05-03 by PR #620)
- `docs/ops/tradingview-orchestrator-runbook.md` (operator playbook)
- `docs/adr/0012-tradingview-orchestrator-architecture.md` (7 ADRs with rationale)
- `docs/ops/threat-intel-sweep-runbook.md` (auto-supersede rule)
- `docs/ops/readiness-warn-state-2026-04-30.md` (WARN classification)
- `docs/handoffs/outstanding-todos-2026-05-03.md` (operator action items)
- Memory: `~/.claude/projects/-Users-aribs/memory/` (durable patterns, autonomous-dispatch hooks)

---

## Section G — resume protocol

```bash
cd ~/Code/Sapphire
git fetch origin main && git checkout main && git pull --ff-only
git log --oneline -10                                                    # current state
python3 scripts/ops/production_readiness_sweep.py --json | jq '.summary'  # live PASS/WARN
ls -t data/tradingview_ta/ | head -3                                     # last captures
ls -t pine/generated/ | head -10                                         # last Pine batch
gh pr list --state open --limit 30                                       # parallel workstream backlog
```

Then pick a B1–B5 workstream and dispatch.

---

End of megaprompt. Companion file: `outstanding-todos-2026-05-03.md`.
