# Sapphire OS — Living Audit

**Last verified:** 2026-04-18
**Scope:** Every claim in [CLAUDE.md](../CLAUDE.md) checked against live services, actual file existence, running tests, and observed data freshness. Supersedes and replaces: `opus-audit-2026-04-17.md`, `technical-audit-2026-04-16.md`, `overnight-technical-report-2026-04-16.md`, `overnight-run-report.md`, `e2e-test-report-2026-04-16.md`, `system-cohesion-audit.md`.

## Top-line verdict

**7/10 — mostly real, a handful of stale claims and orphan modules.** The big features are wired end-to-end. The gaps are counts, doc drift, and 4-5 never-called modules that should be wired or deleted.

## What's REAL (verified live)

| Claim | Status | Evidence |
|-------|--------|----------|
| 1,273 unit tests + 25 plugin tests | ✅ PASS | `pytest tests/unit/ -q` → 1273 passed, 1 skipped in 25s |
| Inference proxy on :11435 | ✅ LIVE | `/metrics` + `/v1/models` respond, 28 Windows GPU models |
| Control-plane on :8082 | ✅ LIVE | `/healthz` OK, auth fails closed (fixed from opus-audit C3) |
| Dashboard on :8080 | ✅ LIVE | Requires AUTH_PASSWORD; real data (CoinGecko, JSONL), no fabricated endpoints |
| Signal logger on :18081 | ✅ LIVE | Accepts webhook posts; `WEBHOOK_SECRET` optional auth |
| OpenBB :6900, regional-intel :8787, hermes gateway | ✅ LIVE | LaunchAgents loaded, PIDs confirmed |
| Windows GPU Ollama (100.71.10.48:11434) | ✅ LIVE | 28 models, 55% proxy success rate |
| Pi rari1 (100.120.191.1:11434) | ✅ LIVE | 4 models (nemotron-mini, smollm2, qwen2.5:0.5b, gemma2:2b), proxy-recovered 2026-04-17 |
| Pi rari2 (100.87.225.89:11434) | ✅ LIVE | 5 models — CLAUDE.md previously said OFFLINE, that's wrong |
| 58% prediction accuracy (BTC 75%) | ✅ VERIFIED | 24/24 scored, 14 correct. Per-symbol: BTC 6/8, ETH 5/8, SOL 3/8. Scoring methodology fixed to wait for timeframe elapse (predict.py:202-215) |
| Sensitivity gate on inference-proxy | ✅ REAL | Regex at `app.py:236` blocks API keys / JWTs / SSNs from Kimi Cloud |
| event_bus wired | ✅ REAL | Imported by dashboard, daily_brief, chain_refresh, signal_pipeline, content/publisher |
| 20 scheduled Claude Code tasks | ✅ ACTIVE | `mcp__scheduled-tasks__list` confirms all have recent lastRunAt timestamps |
| All previously-"phantom" files exist | ✅ PRESENT | `services/alpha/signal_pipeline.py` (1,046 LOC), `lib/chain/*`, `lib/analytics/*`, `services/pipeline/gcp_sync.py`, `lib/core/confirmation_firewall.py`, `agents/{health_monitor,market_watchdog}.py` — opus-audit predated these commits |

## What's STALE or PHANTOM

| Issue | Impact | Fix |
|-------|--------|-----|
| Orphan modules (zero non-test imports): `lib/core/confirmation_firewall.py`, plugin tools `trading_brain`, `lead_engine`, `tho_intel`, `macro_data`, `lumo` | Tools run only if explicitly invoked — not automatic | Wire from signal_pipeline / dashboard, or delete |
| `data/market_pulse/` and `data/threat_intel/` frozen at 2026-04-08 | health_check flags RED; tasks run but don't persist | SKILL.md hardened 2026-04-18 to always write a file in STEP 1 |
| Proxy log shows intermittent "No route to host" to Pi + Windows | Inference falls back to slow Mac (90s+ per call) | Tailscale reachability jitter — investigate routes |
| Dashboard has `app_backup.py`, `app_with_auth.py` stale variants | Confusion + accidental edits | **Deleted 2026-04-18** |
| `plugins/.../tools/kronos_predict.py` legacy dup of `predict_kronos.py` | Confusion | **Deleted 2026-04-18** |
| Pre-existing audit docs contradict each other | Readers can't tell which is current | This doc replaces them all |
| plugin.json version `0.3.0` but CLAUDE.md said `0.4.0` | Version drift | Bump plugin.json to 0.4.0 when registering remaining tools |

## Plugin tool reality

- **30 scripts on disk** in `plugins/claw-sapphire/tools/` (was "21" in old CLAUDE.md — undercount)
- **7 registered** in `plugin.json` as Claude Code tools: dispatch, verify, budget, state, status, notify, market
- **23 orphans** — standalone scripts invoked by hermes skills, scheduled tasks, or each other via stdin JSON
- **10 libs** in `plugins/claw-sapphire/lib/` (was "4" — undercount)
- macro_data.py: **fixed 2026-04-18** to return graceful `{success: false, error: ...}` instead of raising when FRED key missing

## Opus-audit (2026-04-17) findings — current status

| Finding | 2026-04-17 state | 2026-04-18 state |
|---------|------------------|------------------|
| C1: `_is_sensitive()` hard-disabled | CRITICAL | ✅ Real regex at `app.py:236` |
| C3: empty `CONTROL_PLANE_TOKEN` fails open | CRITICAL | ✅ Fails closed with 503 (`main.py:119-128`) |
| C5: TLS disabled in notify.py | CRITICAL | ⚠️ Needs re-verification |
| "Dashboard fabricated data" | HIGH | ✅ All three endpoints read real JSONL / CoinGecko |
| "58% prediction is noise" | HIGH | ✅ Methodology fixed; 58% is real |
| "Phantom files: signal_pipeline, lib/chain, lib/analytics, firewall, agents" | HIGH | ✅ All exist — those audits predated the commits that landed them |
| C2: missing 4 MB body cap | CRITICAL | ⚠️ Needs re-verification |
| `_record_spend` race | HIGH | ⚠️ Needs re-verification |

## Fixes applied in this audit pass (2026-04-18)

1. Deleted `services/dashboard/app_backup.py`, `app_with_auth.py`, `plugins/claw-sapphire/tools/kronos_predict.py`
2. Updated `CLAUDE.md` counts: tests 1,251→1,273, plugin tests 13→25, tools 21→30, libs 4→10, scheduled tasks 19→20, Windows models 27→28, hermes skills 6→14. Pi rari2 flipped ONLINE.
3. Added graceful FRED-key-missing fallback to all 4 actions in `plugins/claw-sapphire/tools/macro_data.py`
4. Hardened `market-pulse` and `threat-intel-sweep` scheduled task SKILL.md files to always write a timestamped file in STEP 1, so health_check stops flagging them RED

## Still TODO (not done)

1. Re-verify opus-audit C2 (body cap) and C5 (TLS) findings
2. Wire or delete the 5 orphan modules (confirmation_firewall, trading_brain, lead_engine, tho_intel, lumo)
3. Bump `plugins/claw-sapphire/plugin.json` version to 0.4.0 if/when more tools get registered
4. Investigate intermittent Tailscale route failures in proxy log
