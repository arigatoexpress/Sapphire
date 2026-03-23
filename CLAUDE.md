# Sapphire OS

Autonomous trading + project management + intelligence system. Telegram-first, agent-driven.

## Module Map

| Path | Type | Description |
|------|------|-------------|
| `lib/core/` | library | Shared: risk kernel, circuit breaker, position sizing, models, logging |
| `lib/telegram/` | library | Telegram bot framework + handlers |
| `lib/agents/` | library | OpenClaw/NemoClaw dispatch, orchestrator, runtime policy |
| `services/aster/` | service | Aster DEX trading bot (rari2) — Solana perps, 231 symbols, Shield HFT strategy |
| `services/hyperliquid/` | service | Hyperliquid L1 trading bot (rari2) — 150+ assets, EIP-712 signed orders |
| `services/alpha/` | service | Trading engine: signals, risk, execution, self-improvement |
| `services/dashboard/` | service | sapphirealpha.xyz Flask dashboard |
| `services/control-plane/` | service | PM hub: projects, tasks, scoring, events, Telegram |
| `services/webhook/` | service | TradingView webhook receiver |
| `clients/blanga/` | client | BIS: brokerage intelligence for Joseph Blanga |
| `pine/` | pine | TradingView indicators and strategies (v1-v3 Ultra) |
| `skills/` | skills | Agent-executable capabilities (10 skills) |
| `tools/claude-analytics/` | tool | MCP server for Claude Code usage metrics (TypeScript) |
| `tools/pm-commander/` | tool | macOS Swift companion app |
| `infra/terraform/` | infra | GCP infrastructure-as-code |
| `infra/pi/` | infra | Raspberry Pi deployment configs |

## Devices

| Device | Tailscale IP | Role |
|--------|-------------|------|
| Mac | 100.67.171.79 | Commander, dev, git |
| Windows PC | 100.71.10.48 | RTX 5070 Ti, NemoClaw inference |
| rari1 | 100.120.191.1 | Controller Pi, Telegram bot, Kimi agent |
| rari2 | 100.87.225.89 | Trading Pi, Aster + Hyperliquid, ProtonVPN |

## Agent Coordination

- **Claude Code** (Mac): Architecture, refactors, planning
- **Kimi Claw** (rari1): Telegram ops, monitoring, quick tasks
- **NemoClaw** (Windows): GPU compute, backtesting, inference
- **OpenClaw workers** (Mac): Background automation via LaunchAgents

## Code Style

- Python: ruff format, type hints, Google-style docstrings
- TypeScript: strict mode, no `any`
- Every module has a SKILL.md — read it before working on that module
- Services never import from other services — only from lib/
- PnL is king. Sortino/Calmar over Sharpe. 80%+ win rate target.

## Exchanges

| Service | Exchange | Chain | Status | Deploy |
|---------|----------|-------|--------|--------|
| `services/aster/` | Aster DEX | Solana | Active | rari2 |
| `services/hyperliquid/` | Hyperliquid L1 | Hyperliquid L1 | Stub | rari2 |

All bots receive signals from `services/alpha/` via pubsub and execute independently.

## Event System

Control-plane publishes events tagged with: `project:`, `agent:`, `priority:`, `type:`
Tag namespaces: `project:` `agent:` `priority:` `type:` `service:` `device:`
Agents subscribe to relevant tags. Telegram notifications filtered by subscription.
`data/connectors.json` — registry of all connectors, MCPs, LaunchAgents, exchanges.
