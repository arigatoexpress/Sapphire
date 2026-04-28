# Standalone Tool Surface Audit — 2026-04-19

## Method

- Scope: the tool surface under `plugins/claw-sapphire/tools/`, with special attention to the 20 non-registered scripts (the 32 on-disk scripts minus the 12 tools now declared in `plugins/claw-sapphire/plugin.json`).
- Search method: exact filename and subprocess/cross-tool caller searches with `rg`, focusing on runtime code paths (`services/`, `infra/`, `lib/`, `tests/`), and separating docs/self-reference from executable callers.
- Standard for "used": an exact repo-local caller, downstream runtime consumer, or tool-to-tool dependency. If no exact caller was found, this memo says so explicitly instead of inferring off-repo usage.

## High-confidence runtime-wired tools

| Tool | Repo-grounded evidence | Recommendation |
|------|------------------------|----------------|
| `predict_kronos.py` | Dashboard `/api/predictions/kronos` and `/api/predictions/status` shell out to it in [services/dashboard/app.py](/Users/aribs/Code/Sapphire/services/dashboard/app.py:1700) and [services/dashboard/app.py](/Users/aribs/Code/Sapphire/services/dashboard/app.py:1781). The daily runner shells out to it in [infra/scripts/kronos_daily.py](/Users/aribs/Code/Sapphire/infra/scripts/kronos_daily.py:21). `trading_brain.py` also delegates to it in [plugins/claw-sapphire/tools/trading_brain.py](/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/trading_brain.py:155). | Kept as the canonical Kronos entrypoint and promoted into `plugin.json` in this pass. |
| `health_check.py` | Called by control-plane ecosystem health in [services/control-plane/app/main.py](/Users/aribs/Code/Sapphire/services/control-plane/app/main.py:1130), daily brief generation in [services/intelligence/daily_brief.py](/Users/aribs/Code/Sapphire/services/intelligence/daily_brief.py:345), and Telegram `/health` in [services/telegram-bot/app.py](/Users/aribs/Code/Sapphire/services/telegram-bot/app.py:175). `watchdog.py` also shells out to it. | Promoted into `plugin.json` in this pass; keep as the unified operator health entrypoint. |
| `threat_intel.py` | Telegram `/threats`, `/threat`, and `/offers` dispatch to it in [services/telegram-bot/app.py](/Users/aribs/Code/Sapphire/services/telegram-bot/app.py:154). Its output directory is also read by content/pipeline code. | Promoted into `plugin.json` in this pass; keep as the primary structured threat-intel entrypoint. |
| `lumo_research.py` | Dashboard SOC routes proxy to it in [services/dashboard/app.py](/Users/aribs/Code/Sapphire/services/dashboard/app.py:1816) and [services/dashboard/app.py](/Users/aribs/Code/Sapphire/services/dashboard/app.py:1858). | Promoted into `plugin.json` in this pass; keep as the operator-facing cyber research bridge. |
| `starred_repos.py` | Telegram `/repos` shells out to it in [services/telegram-bot/app.py](/Users/aribs/Code/Sapphire/services/telegram-bot/app.py:190). | Promoted into `plugin.json` in this pass; keep as the GitHub-synergy entrypoint. |

## Tool-graph dependencies that are not true repo-local orphans

| Tool | Repo-grounded evidence | Recommendation |
|------|------------------------|----------------|
| `macro_data.py` | `trading_brain.py` calls it for the dashboard macro sentiment path in [plugins/claw-sapphire/tools/trading_brain.py](/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/trading_brain.py:58), and `tho_intel.py` calls it for housing/rates in [plugins/claw-sapphire/tools/tho_intel.py](/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/tho_intel.py:41). | Do not call this an orphan. Keep unregistered. Also do not register it separately unless the plugin surface is intentionally expanding, because `sapphire_market` already exposes a `fred` action in [plugins/claw-sapphire/plugin.json](/Users/aribs/Code/Sapphire/plugins/claw-sapphire/plugin.json:61). |
| `lead_engine.py` | `lead_enrich.py` shells out to it in [plugins/claw-sapphire/tools/lead_enrich.py](/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/lead_enrich.py:253). Its `pipeline_*.json` output shape is still consumed by `transform_leads()` in [services/pipeline/gcp_sync.py](/Users/aribs/Code/Sapphire/services/pipeline/gcp_sync.py:357). | Do not delete as "dead." Keep unregistered unless lead-gen becomes a deliberate Claude Code surface. |
| `signal_generator.py` | `trading_brain.py` shells out to it in [plugins/claw-sapphire/tools/trading_brain.py](/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/trading_brain.py:145). | Keep unregistered for now. |
| `paper_trader.py` | `trading_brain.py` shells out to it in [plugins/claw-sapphire/tools/trading_brain.py](/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tools/trading_brain.py:107). | Keep unregistered for now. |

## Focused orphan-tool reality

| Tool | Repo-grounded status | Recommendation |
|------|----------------------|----------------|
| `trading_brain.py` | No exact non-test runtime callers were found. It is not wired from a service, dashboard, or scheduled script. It does now have targeted coverage in [plugins/claw-sapphire/tests/test_trading_brain.py](/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tests/test_trading_brain.py:1), so it is tested but still not surfaced. | Treat as a repo-local orphan entrypoint, not dead code. Do not register yet. First decide whether it belongs in dashboard/Telegram/operator workflows. |
| `lead_engine.py` | Not a top-level orphan: it is invoked by `lead_enrich.py`, and its pipeline output schema is still consumed by GCP sync. No direct service/scheduler caller was found in-repo. | Keep on disk. No registration change in this pass. |
| `tho_intel.py` | No exact non-test callers found in-repo. It consumes `macro_data.py` and external THO/Regional Intel endpoints, but nothing in the repo invokes it. | True repo-local orphan entrypoint. Needs a product decision: either wire it into a THO surface or archive/delete it. |
| `macro_data.py` | Not a true orphan because it is still called by `trading_brain.py` and `tho_intel.py`. | Keep. No registration change. |
| `lumo.py` | No exact non-test callers found in-repo. The dashboard uses `lumo_research.py`, and the disabled LaunchAgent points at external `~/Code/lumo-api/lumo.js`, not this script. No in-repo consumer of `data/lumo/` was found. | Strongest cleanup candidate among the five, but deletion/rename should still be a deliberate product decision because of the naming overlap with `lumo_research.py`. |

## Other standalone scripts with no exact repo-local caller found in this audit

These may still be run manually or by out-of-repo schedulers, but this audit found no exact in-repo caller beyond self-reference/docs/tests:

- `backtest.py`
- `crypto_portfolio.py`
- `digest.py`
- `events.py`
- `lead_enrich.py`
- `market_sentiment.py`
- `predict.py`
- `qa_aware_factory.py`
- `research.py`
- `solana_wallet.py`
- `vote_monitor.py`
- `watchdog.py`

## Legacy alias

| Tool | Repo-grounded status | Recommendation |
|------|----------------------|----------------|
| `kronos_predict.py` | Compatibility wrapper only. No exact non-test callers were found in-repo, but it now has targeted compatibility coverage in [plugins/claw-sapphire/tests/test_kronos_predict_legacy.py](/Users/aribs/Code/Sapphire/plugins/claw-sapphire/tests/test_kronos_predict_legacy.py:1). | Keep unregistered as a legacy alias until any off-repo callers are confirmed migrated. |

## Registration recommendation

Promoted in the 2026-04-19 follow-on passes:

1. `predict_kronos`
2. `health_check`
3. `threat_intel`
4. `lumo_research`

No additional remaining companion has equally clear evidence for promotion in this audit. The remaining gap is less registration and more deciding whether to wire, archive, or leave niche tools as direct-entry companions.

I would still not register `macro_data`, `lead_engine`, `tho_intel`, `trading_brain`, or `lumo`:

- `macro_data` overlaps the existing `sapphire_market` `fred` action.
- `lead_engine` and `tho_intel` are domain-specific and currently lack direct repo-local operator surfaces.
- `trading_brain` is tested but not yet wired anywhere user-facing.
- `lumo` has zero repo-local callers and collides conceptually with `lumo_research`.
