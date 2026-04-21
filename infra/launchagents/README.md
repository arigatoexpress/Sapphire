# LaunchAgents

macOS LaunchAgent definitions for Sapphire background services and schedulers.

Current inventory: 11 active plists in this directory, plus 1 disabled template (`com.sapphire.lumo-api.plist.disabled`).

## Active Plists

| Label | Purpose |
|------|---------|
| `com.sapphire.alpha-agent.plist` | Paper-only AlphaAgent cycle runner (`lib.agents.runner --agent alpha --interval 300`) with heartbeat output in `data/agents/alpha.heartbeat`. |
| `com.sapphire.backtest-weekly.plist` | Weekly strategy sweep artifact generation. |
| `com.sapphire.content-engine.plist` | Scheduled content generation. |
| `com.sapphire.content-publisher.plist` | Scheduled content publishing. |
| `com.sapphire.foundry-sync.plist` | Foundry sync daemon. |
| `com.sapphire.heartbeat.plist` | Platform heartbeat daemon. |
| `com.sapphire.market-intel.plist` | Market intelligence refresh. |
| `com.sapphire.morning-brief.plist` | Morning briefing run. |
| `com.sapphire.security-pipeline.plist` | Security scan pipeline. |
| `com.sapphire.self-optimization.plist` | Self-improvement review loop. |
| `com.sapphire.tradingview-cdp.plist` | TradingView CDP bridge. |

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
