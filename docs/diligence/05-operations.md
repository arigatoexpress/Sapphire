# 05 - Operations

Sapphire is operated through macOS LaunchAgents, Hermes runtime guardrails, scheduled routine manifests, and local readiness sweeps. The repo currently contains 26 LaunchAgent plists across `/Users/aribs/Code/Sapphire/infra/launchagents/` and service-owned launchagent directories under `/Users/aribs/Code/Sapphire/services/`. The readiness sweep on 2026-04-28 observed the canonical checkout clean, the new provenance check passing, and the Gemini OODA LaunchAgent loaded after it was installed from `/Users/aribs/Code/Sapphire/infra/launchagents/com.sapphire.gemini-ooda-daily.plist`.

The LaunchAgent layer is intentionally explicit. Repo-side plists include dashboard, inference proxy, control plane, PM bot, signal logger, heartbeat, OpenBB, telemetry, Foundry sync, GCP sync, content engine, content publisher, threat refresh, morning brief, backtest weekly, security pipeline, TradingView CDP, and Gemini OODA daily. The repo also tracks service-owned plists at `/Users/aribs/Code/Sapphire/services/dashboard/launchagent/com.sapphire.dashboard.plist`, `/Users/aribs/Code/Sapphire/services/inference-proxy/launchagent/com.sapphire.inference-proxy.plist`, `/Users/aribs/Code/Sapphire/services/pm_bot/launchagent/com.sapphire.pm-bot.plist`, and related service directories.

The Hermes runtime is treated as a production component. `/Users/aribs/Code/Sapphire/scripts/ops/hermes_runtime_readiness.py` checks the runtime checkout, quick-exec guard, LaunchAgent path, and `SAPPHIRE_REPO_PATH`. `/Users/aribs/Code/Sapphire/infra/hermes-sapphire-skills.yaml` inventories the Hermes Sapphire skill surface and classifies side effects. This gives the operator a way to let Hermes assist without silently giving it unrestricted ownership of production behavior.

The scheduled-task side is documented through org and routine manifests. `/Users/aribs/Code/Sapphire/docs/routines-manifest.md` is the named source in `/Users/aribs/Code/Sapphire/README.md`; `/Users/aribs/Code/Sapphire/scripts/ops/routine_soak_status.py` reads routine state and reports remote-shadow progress. The repo has soak docs for backtest-weekly, content-engine, and threat-refresh under `/Users/aribs/Code/Sapphire/docs/org/`. The readiness sweep currently treats external-mode routine probes as warnings when `--no-external` is used, which is correct for no-spend local verification.

The monitoring surface is centralized in `/Users/aribs/Code/Sapphire/scripts/ops/production_readiness_sweep.py`. The sweep checks repo cleanliness, worktrees, no-spend CI gates, LaunchAgents, local HTTP endpoints, kill-switch state, confirmation firewall expirations, redaction, provenance, routine soaks, GitHub state, and GCP gates. `/Users/aribs/Code/Sapphire/scripts/ops/production_readiness_matrix.py` expands this into a broader production-readiness matrix while preserving the constraint that it does not trade, write GCP/Foundry/BigQuery/GCS, dispatch workflows, mutate Gmail/Drive, or retarget LaunchAgents.

The continuous-intelligence planner in `/Users/aribs/Code/Sapphire/lib/autonomy/continuous_intelligence.py` turns strategy performance, thesis, backtest, market-universe, and artifact state into claimable tasks. `/Users/aribs/Code/Sapphire/lib/autonomy/continuous_intelligence_artifacts.py` materializes snapshots, dry-run leases, and task results under `data/.autonomy/continuous_intelligence/` with provenance sidecars. The dashboard exposes this through `/api/autonomy/continuous-intelligence`, `/api/autonomy/continuous-intelligence/artifacts`, and `/api/autonomy/continuous-intelligence/lease-preview` in `/Users/aribs/Code/Sapphire/services/dashboard/app.py`.

Operationally, the key maturity signal is not that every routine is remote-canonical. It is that local routines remain canonical until soak evidence proves a replacement. The repo's current posture is therefore conservative: LaunchAgents are visible, remote shadows are tracked, readiness is measured locally, external spend is gated, and every new production cadence, including Gemini OODA daily, is implemented as a dry-run artifact path first.

## Diligence Readout

The operations diligence question is whether Sapphire can run tomorrow morning without Ari narrating it. The answer is partially yes. LaunchAgents encode local schedules, readiness sweeps encode health checks, Hermes runtime checks encode gateway assumptions, and routine soak docs encode migration gates. The remaining human dependency is interpretation: deciding which warning matters, when to cut over a shadow routine, and when to approve a live mutation.

The new Gemini OODA daily lane is a good operations pattern. It has a plist, wrapper, Python implementation, runbook, tests, dashboard diff, provenance sidecar, and event emission. That is the template future routines should follow. If a routine cannot answer "where is the LaunchAgent, where is the wrapper, where is the runbook, where is the artifact, where is the provenance, where is the dashboard surface, and where is the test," it is not production-cadence ready.

The production-readiness sweep is the buyer's first operational entry point. It should be run before demos, after merges, and before any claim that the system is healthy. The current no-external mode intentionally warns on external-only checks. That is good behavior: local verification should not pretend to know external state it did not probe. During acquisition diligence, the buyer can run both no-external and external modes with approved credentials and compare the delta.

The worktree policy is also part of operations. Sapphire keeps canonical main clean and uses `/Users/aribs/Code/_worktrees/` for PR work. That avoids the common agent failure mode where local WIP, production state, and PR diffs are mixed in one checkout. The only caveat is that other active worktrees may exist for parallel work; they should be treated as intentional until verified, not deleted as cleanup theatre.

The post-close operations plan should keep launchd rather than replacing it reflexively. LaunchAgents are visible on the operator Mac, cheap, debuggable, and already integrated into readiness checks. A future orchestrator can be introduced later, but only after it preserves the same properties: explicit labels, local logs, dry-run mode, provenance output, and a way for the readiness sweep to say pass, warn, or fail.

The operating cadence should be daily readiness, weekly cleanup, and per-PR local CI. Daily readiness catches runtime drift. Weekly cleanup catches stale worktrees and routine soak state. Per-PR CI catches code regressions before merge. That is enough process for a small autonomy platform without burying it under enterprise ceremony or slowing necessary repairs.

## Evidence

- `/Users/aribs/Code/Sapphire/infra/launchagents/`
- `/Users/aribs/Code/Sapphire/scripts/ops/production_readiness_sweep.py`
- `/Users/aribs/Code/Sapphire/scripts/ops/routine_soak_status.py`
- `/Users/aribs/Code/Sapphire/lib/autonomy/continuous_intelligence.py`
- `/Users/aribs/Code/Sapphire/lib/autonomy/continuous_intelligence_artifacts.py`
