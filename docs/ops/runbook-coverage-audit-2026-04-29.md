# Runbook coverage audit — 2026-04-29

This audit scores every Sapphire operational surface (services,
LaunchAgents, cloud routines) against the runbook that documents how
to operate it. The intent is honest grading: if a runbook is missing,
score it 1; if a runbook is comprehensive, score it 5.

**Scoring rubric** (1-5 integer):

- **5** — comprehensive: bring-up, daily ops, common failures, recovery
  steps, escalation path, last-reviewed date. Operator-readable cold.
- **4** — good: bring-up + daily ops + common failures. Recovery steps
  present but partial.
- **3** — adequate: covers bring-up and at least one operational
  scenario. Missing common failures or recovery.
- **2** — sparse: a runbook exists but it is incomplete (1-page note,
  outdated examples, command snippets without context).
- **1** — missing: no runbook found at the conventional path.

Scores **< 4** must have a concrete `Gap action` describing what would
move the score upward.

The 19 services count is from `services/` (excluding deprecated /
infra-only directories: `aster` paused, `telegram-bot` legacy,
`scout-sandbox` external-collaborator, plus a handful of pure-build
directories). The 23 LaunchAgents count is from `infra/launchagents/`
(22 active `.plist` files, ignoring `.disabled` and `.template`) plus
service-local plists at `services/<name>/launchagent/`. Cloud routines
are the 8 from `claude.ai/code/routines` per CLAUDE.md.

---

## Services (19)

| Service | Runbook | Score | Gap action |
|---|---|---|---|
| `services/alpha/` (signal logger + trading) | `tranche5-live-soak-runbook.md`, `robinhood-real-funds-readiness.md` | 4 | Add a single canonical `alpha-runbook.md` consolidating bring-up, env vars, signal-logger restart, paper→live cutover. |
| `services/audit_panel/` | `audit-panel-runbook.md` | 5 | — |
| `services/control-plane/` | `control-plane-runbook.md` | 3 | Add endpoint-level smoke tests for token-gated task mutation and Kimi bridge denial paths. |
| `services/correlator/` | `signal-correlator-runbook.md` | 5 | — |
| `services/counterparty/` | `counterparty-intel-runbook.md` | 4 | Add explicit "what to do when counterparty source returns garbage" section. |
| `services/cross_asset/` | `cross-asset-runbook.md` | 5 | — |
| `services/customer_api/` | `customer-api-runbook.md` | 3 | Document the three live gates from ADR 0008 in detail (env flag, payment-verified, allowlist file). Sparse on failure modes. |
| `services/dashboard/` | `dashboard-product-pages-runbook.md`, `dashboard-public-demo-runbook.md`, `observability-dashboard-runbook.md` | 5 | — |
| `services/event_impact/` | `event-impact-runbook.md` | 5 | — |
| `services/foundry_sync/` | `foundry-sync-runbook.md` | 3 | Add fixture-backed smoke coverage for the first three dry-run/readiness commands and expand post-success incident drills. |
| `services/heartbeat/` | `heartbeat-runbook.md` | 3 | Add automated smoke coverage for one-shot mode and clarify overlap with `lib/core/heartbeat.py` self-heal monitor. |
| `services/hyperliquid/` | `hyperliquid-feed-runbook.md` | 4 | Public-feed side documented; live-executor side (signing verification, mainnet flip protocol, daily-loss auto-pause) needs a dedicated section. |
| `services/inference-proxy/` | `inference-proxy-runbook.md`, `inference-tenant-quotas.md`, `inference-mesh-telemetry-runbook.md` | 4 | Add command-level smoke automation for GET probes and LaunchAgent restart drills; current runbook now covers 4-tier failover, aliases, sensitivity gate, GPU-only fail-closed behavior, quotas, cache, and telemetry writer. |
| `services/intelligence/` | `intelligence-breadth-runbook.md` | 3 | Breadth roadmap exists but daily-brief generator + chain-refresh operations are not covered. |
| `services/macro_intel/` | `macro-intel-runbook.md` | 5 | — |
| `services/morning_digest/` | `morning-digest-runbook.md`, `mission-status-digest-runbook.md` (cloud); `evening-digest-runbook.md` (cloud) | 3 | Add an archive writer or align `/digest morning` docs with the current send-only LaunchAgent behavior. |
| `services/narrative_evaluation/` | `narrative-eval-runbook.md` | 4 | Sparse on regression-on-rubric path. |
| `services/onchain_intel/` | `onchain-intel-runbook.md` | 5 | — |
| `services/openbb_api/` | `openbb-api-runbook.md` | 3 | Add provider-route smoke tests that avoid external market-data calls and document the Python/OpenBB version pin once stabilized. |
| `services/pipeline/` | `gcp-pipeline-runbook.md` | 3 | Add dry-run fixture smoke coverage and a Cloud Function failure triage section once live logs are reviewed. |
| `services/pm_bot/` | `telegram-operator-console-runbook.md` | 4 | Operator-console runbook is comprehensive on Telegram safety; pm-bot daemon-side restart procedure is implicit. |
| `services/research_notes/` | `research-notes-runbook.md` | 3 | Sparse — needs operational sections (regen cadence, what to do when sources fail). |
| `services/security_pipeline/` | `security-pipeline-runbook.md` | 3 | Add a dry-run/no-notify CLI mode and fixture-backed report-to-downstream-consumer smoke coverage. |
| `services/synthesis/` | `narrative-synthesis-runbook.md` | 5 | — |
| `services/telegram_intel/` | `telegram-intel-reader-runbook.md` | 4 | Add explicit "channel curation went wrong" recovery (touches `telegram-channel-curation-runbook.md` but that's a separate concern). |
| `services/webhook/` | `webhook-runbook.md` | 3 | Add explicit `WEBHOOK_SECRET`/HMAC enforcement plus accepted/rejected request tests before public exposure. |

**Service tally**: 26 services audited (the lane spec said 19; the
canonical `services/` directory has more after Tranches 4-5 added
several. Counted services that are operationally meaningful — paused
`aster`, legacy `telegram-bot`, infra-only `scout-sandbox`,
`live_portfolio_daemon`, `service_supervisor` are listed under
LaunchAgents below since their runbook surface is the agent itself).

**Service average**: 3.88 (sum 101, n 26).

**Lowest-scored services** (need attention first): the newly lifted but
still-partial `control-plane`, `foundry_sync`, `security_pipeline`,
`heartbeat`, `openbb_api`, `pipeline`, and `webhook` (3).

---

## LaunchAgents (23)

| LaunchAgent label | Plist source | Runbook | Score | Gap action |
|---|---|---|---|---|
| `com.sapphire.alpha-agent` | `infra/launchagents/com.sapphire.alpha-agent.plist` | `tranche5-live-soak-runbook.md` (partial) | 3 | Document plist-level config (KeepAlive, StandardOutPath) explicitly. |
| `com.sapphire.backtest-weekly` | `infra/launchagents/com.sapphire.backtest-weekly.plist` | `backtest-weekly-runbook.md` | 3 | Add a freshness check to routine health and fixture coverage for noncanonical `--output-dir` smoke runs. |
| `com.sapphire.chain-refresh` | `infra/launchagents/com.sapphire.chain-refresh.plist` | `onchain-intel-runbook.md` (partial) | 3 | Add agent-level restart + log-path to onchain runbook. |
| `com.sapphire.content-engine` | `infra/launchagents/com.sapphire.content-engine.plist` | `content-engine-soak-runbook.md` | 4 | Soak runbook covers the cloud routine well; agent-side draft → publish flow could be more explicit. |
| `com.sapphire.content-publisher` | `infra/launchagents/com.sapphire.content-publisher.plist` | `content-publisher-runbook.md` | 3 | Add a no-write CLI dry-run mode and fixture coverage for duplicate-ledger recovery. |
| `com.sapphire.control-plane` | `infra/launchagents/com.sapphire.control-plane.plist` | `control-plane-runbook.md` | 3 | Add launchd-specific restart fixture checks and document durable-store cutover once it is used. |
| `com.sapphire.correlation-refresh` | `infra/launchagents/com.sapphire.correlation-refresh.plist` | `signal-correlator-runbook.md` | 4 | Correlator runbook is solid but agent restart procedure is implicit. |
| `com.sapphire.foundry-sync` | `infra/launchagents/com.sapphire.foundry-sync.plist` | `foundry-sync-runbook.md` | 3 | Add a fixture-backed smoke for pause behavior and a reviewed live-stack drill after Foundry provisioning. |
| `com.sapphire.gcp-sync` | `infra/launchagents/com.sapphire.gcp-sync.plist` | `gcp-pipeline-runbook.md` | 3 | Add launchd-specific last-run examples once live gcp-sync logs are sampled after the next scheduled fire. |
| `com.sapphire.gemini-ooda-daily` | `infra/launchagents/com.sapphire.gemini-ooda-daily.plist` | `gemini-ooda-daily-runbook.md`, `gemini-ooda-synthesizer-runbook.md` | 5 | — |
| `com.sapphire.heartbeat` | `infra/launchagents/com.sapphire.heartbeat.plist` | `heartbeat-runbook.md` | 3 | Add automated smoke coverage for one-shot mode and clarify overlap with `lib/core/heartbeat.py` self-heal monitor. |
| `com.sapphire.logrotate` | `infra/launchagents/com.sapphire.logrotate.plist` | `logrotate-runbook.md` | 3 | Add fixture-backed unit tests for rotate/prune behavior and a plist-specific cadence assertion. |
| `com.sapphire.market-intel` | `infra/launchagents/com.sapphire.market-intel.plist` | `market-intel-runbook.md` | 3 | Add a routine freshness check for `market_intel.json` and a plist-specific 30-minute cadence assertion. |
| `com.sapphire.morning-brief` | `infra/launchagents/com.sapphire.morning-brief.plist` | `morning-brief-runbook.md` | 3 | Align routine-health artifact tracking with dated `daily_brief.md` outputs or add a verified latest symlink/copy. |
| `com.sapphire.openbb-api` | `infra/launchagents/com.sapphire.openbb-api.plist` | `openbb-api-runbook.md` | 3 | Add provider-route smoke tests that avoid external market-data calls and document the Python/OpenBB version pin once stabilized. |
| `com.sapphire.security-pipeline` | `infra/launchagents/com.sapphire.security-pipeline.plist` | `security-pipeline-runbook.md` | 3 | Add a launchd stale-report check and a reviewed no-notify drill for manual reruns. |
| `com.sapphire.self-optimization` | `infra/launchagents/com.sapphire.self-optimization.plist` | `self-optimization-runbook.md` | 3 | Add fixture coverage for `optimize.py` dry-run/event side effects and a freshness check for optimization events. |
| `com.sapphire.signal-logger` | `infra/launchagents/com.sapphire.signal-logger.plist` | `tranche5-live-soak-runbook.md` (partial) | 3 | Same gap as `services/alpha/`. |
| `com.sapphire.telemetry-collector` | `infra/launchagents/com.sapphire.telemetry-collector.plist` | `telemetry-collector-runbook.md` | 3 | Add direct routine-freshness tracking and fixture coverage for metrics/health append contracts. |
| `com.sapphire.threat-refresh` | `infra/launchagents/com.sapphire.threat-refresh.plist` | `threat-intel-sweep-runbook.md` | 4 | Threat runbook covers the cloud routine; agent-side cadence + log path implicit. |
| `com.sapphire.trading-shadow-controller` | `infra/launchagents/com.sapphire.trading-shadow-controller.plist` | `trading-shadow-runbook.md` | 3 | Add stale-report alerting and fixture coverage for offline output/routine freshness. |
| `com.sapphire.tradingview-cdp` | `infra/launchagents/com.sapphire.tradingview-cdp.plist` | `tradingview-cdp-runbook.md` | 3 | Add a CDP-specific plist assertion and read-only MCP status smoke coverage. |
| `com.sapphire.dashboard` (service-local) | `services/dashboard/launchagent/com.sapphire.dashboard.plist` | `dashboard-product-pages-runbook.md`, `observability-dashboard-runbook.md` | 5 | — |
| `com.sapphire.inference-proxy` (service-local) | `services/inference-proxy/launchagent/com.sapphire.inference-proxy.plist` | `inference-proxy-runbook.md`, `inference-tenant-quotas.md` | 4 | Add fixture-backed restart/health smoke automation before scoring 5. |
| `com.sapphire.morning-digest` (service-local) | `services/morning_digest/launchagent/com.sapphire.morning-digest.plist` | `morning-digest-runbook.md` | 3 | Add archive support for `data/morning_digest/YYYY-MM-DD.md` or remove the stale archive expectation from `/digest morning`. |
| `com.sapphire.pm-bot` (service-local) | `services/pm_bot/launchagent/com.sapphire.pm-bot.plist` | `telegram-operator-console-runbook.md` | 4 | See `services/pm_bot/` gap. |
| `com.sapphire.service-supervisor` (service-local) | `services/service_supervisor/launchagent/com.sapphire.service-supervisor.plist` | `service-supervisor-runbook.md` | 3 | Add fixture-backed tests for the operator commands shown in the runbook and document a manual state-clear checklist. |
| `com.sapphire.telegram-intel-reader` (service-local) | `services/telegram_intel/launchagent/com.sapphire.telegram-intel-reader.plist` | `telegram-intel-reader-runbook.md` | 4 | See `services/telegram_intel/` gap. |

**LaunchAgent tally**: 28 plist files audited (22 in `infra/launchagents/`
plus 6 service-local). The original lane spec said 23 LaunchAgents;
the 28-count emerged because Tranches 4-5 added service-local plists
the prior counts missed.

**LaunchAgent average**: 3.36 (sum 94, n 28).

**Lowest-scored LaunchAgents** (priority): no score-1 or score-2
LaunchAgents remain. The lowest tier is now score 3: `alpha-agent`,
`backtest-weekly`, `chain-refresh`, `content-publisher`,
`control-plane`, `foundry-sync`, `gcp-sync`, `heartbeat`,
`logrotate`, `market-intel`, `morning-brief`, `openbb-api`,
`self-optimization`, `signal-logger`, `telemetry-collector`,
`trading-shadow-controller`, `tradingview-cdp`, plus service-local
`morning-digest` and `service-supervisor`.

---

## Cloud routines (8)

| Routine name | Runbook | Score | Gap action |
|---|---|---|---|
| Sapphire mission status digest | `mission-status-digest-runbook.md` | 5 | — |
| Sapphire content-engine soak collector | `content-engine-soak-runbook.md` | 5 | — |
| Sapphire factory test guardian | `factory-test-guardian-runbook.md` | 5 | — |
| Sapphire factory repo fixer | `factory-repo-fixer-runbook.md` | 5 | — |
| Sapphire dependency drift digest | `dependency-drift-digest-runbook.md` | 5 | — |
| Sapphire threat intel sweep | `threat-intel-sweep-runbook.md` | 5 | — |
| Sapphire github discovery | `github-discovery-runbook.md` | 5 | — |
| Sapphire evening digest | `evening-digest-runbook.md` | 5 | — |

**Cloud routine tally**: 8.

**Cloud routine average**: 5.0 (sum 40, n 8).

The cloud routines are the highest-coverage surface in Sapphire
because each was launched 2026-04-27 with a runbook-as-prompt
discipline (the routine reads its runbook every run; the runbook is
the full task spec). This is a working pattern worth replicating for
LaunchAgent-driven daemons.

---

## Aggregate

- **Total surfaces**: 62 (26 services + 28 LaunchAgents + 8 cloud
  routines).
- **Aggregate score**: 235 / 310 = **3.79 / 5**.
- **Score 5 surfaces**: 18 (29%).
- **Score < 4 surfaces requiring gap action**: 31 (50%).
- **Score 1 surfaces (no runbook)**: 0 (0%).

The asymmetry is still sharp: cloud routines and LLM-tool runbooks
(`gemini-ooda-*`, `narrative-synthesis`, `vertex-eval`) are
comprehensive; LaunchAgent-side daemons that quietly run in the
background are now documented at least to score 3, but still need more
fixture-backed smoke coverage and routine-freshness checks.
The pattern: when a runbook is required to bring a routine online
from a cold start, it gets written. When a daemon "just runs", the
runbook never lands.

---

## Recommended remediation order

1. **Backtest-weekly + telemetry-collector + Content-publisher +
   TradingView-CDP + Control-plane + Foundry-sync + Security pipeline +
   Heartbeat + logrotate + market-intel + morning-brief +
   morning-digest + self-optimization + trading-shadow-controller +
   service-supervisor + OpenBB API + webhook + pipeline**
   (now score 3) —
   these have adequate operator runbooks after the 2026-04-29 uplifts,
   but still need command-level smoke tests, freshness tracking,
   no-notify drills, read-only CDP status checks, and endpoint-specific
   recovery coverage.

---

## Audit metadata

- **Audit date**: 2026-04-29
- **Auditor**: Sapphire ops (Tranche 6 Lane 2)
- **Method**: filesystem inventory + grep against `docs/ops/*.md` for
  each surface name. Score is judgment from reading the runbook (when
  present) against the rubric above.
- **Provenance**: this audit is a deterministic artifact; running the
  same inventory + same rubric should produce the same scores within
  ± 1 per surface.
- **Next audit**: when Tranche 7 ships, or when ≥ 5 surfaces have had
  their runbooks rewritten.
