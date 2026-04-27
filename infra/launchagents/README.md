# LaunchAgents

macOS LaunchAgent definitions for Sapphire background services and schedulers.

Current inventory: 20 active plists in this directory, plus 1 disabled template (`com.sapphire.lumo-api.plist.disabled`). The 2026-04-21 audit folded in the production plists that had been running un-versioned on Ari's Mac — see `docs/launchagents-audit-2026-04-21.md`. Some service-owned LaunchAgents live with their service code under `services/*/launchagent/`; this currently includes `services/dashboard/launchagent/com.sapphire.dashboard.plist`, `services/inference-proxy/launchagent/com.sapphire.inference-proxy.plist`, `services/pm_bot/launchagent/com.sapphire.pm-bot.plist`, and `services/service_supervisor/launchagent/com.sapphire.service-supervisor.plist`. The remaining Mac-only plists (cloudflare-tunnel, kronos-daily, regional-intel, hermes) are intentionally not versioned here; see the audit for why.

## Active Plists

| Label | Purpose | Schedule |
|------|---------|----------|
| `com.sapphire.alpha-agent.plist` | Paper-only AlphaAgent cycle runner (`lib.agents.runner --agent alpha --interval 300`) with heartbeat output in `data/agents/alpha.heartbeat`. | KeepAlive |
| `com.sapphire.backtest-weekly.plist` | Weekly strategy sweep artifact generation. | weekly |
| `com.sapphire.chain-refresh.plist` | Chain intelligence snapshot (`services.pipeline.chain_refresh`). | every 15 min |
| `com.sapphire.content-engine.plist` | Scheduled content generation. | weekly |
| `com.sapphire.content-publisher.plist` | Scheduled content publishing. | on-demand |
| `com.sapphire.control-plane.plist` | FastAPI control plane (uvicorn on `:8082`). | KeepAlive |
| `com.sapphire.correlation-refresh.plist` | Cross-asset correlation refresh. | hourly at :17 |
| `com.sapphire.foundry-sync.plist` | Foundry sync daemon. | every 15 min |
| `com.sapphire.gcp-sync.plist` | GCP → BigQuery event pipeline. | hourly at :05 |
| `com.sapphire.heartbeat.plist` | Platform heartbeat daemon. | KeepAlive |
| `com.sapphire.logrotate.plist` | Compress + rotate `~/autonomy-status/logs/`. | 03:30 daily |
| `com.sapphire.market-intel.plist` | Market intelligence refresh. | scheduled |
| `com.sapphire.morning-brief.plist` | Canonical morning briefing run (`services/intelligence/daily_brief.py`). | 06:00 local / 07:00 CT daily |
| `com.sapphire.openbb-api.plist` | OpenBB REST server on `:6900`. | KeepAlive |
| `com.sapphire.security-pipeline.plist` | Security scan pipeline. | 03:00 daily |
| `com.sapphire.self-optimization.plist` | Self-improvement review loop. | daily |
| `com.sapphire.signal-logger.plist` | TradingView webhook receiver / uvicorn on `:18081`. | KeepAlive |
| `com.sapphire.telemetry-collector.plist` | Metric roll-up (`services/pipeline/telemetry_collector.py`). | every 5 min |
| `com.sapphire.threat-refresh.plist` | Threat-intel feed refresh (`services/dashboard/refresh_threats.py`). | every 4 h |
| `com.sapphire.tradingview-cdp.plist` | TradingView CDP bridge. | KeepAlive |

## Alpha Agent

The AlphaAgent LaunchAgent is paper-only. It evaluates paper portfolio positions, writes `data/agents/alpha.heartbeat`, and emits `agent.cycle.completed` events so `/agents/autonomous` stays populated.

Before loading it, make sure the user log directory exists:

```bash
mkdir -p ~/Library/Logs/sapphire
cp infra/launchagents/com.sapphire.alpha-agent.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.sapphire.alpha-agent.plist
launchctl kickstart -k gui/$(id -u)/com.sapphire.alpha-agent
```

Quick local status:

```bash
make alpha-agent-status
```
