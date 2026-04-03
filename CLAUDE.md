# Sapphire OS

Autonomous trading + project management + intelligence system. Telegram-first, agent-driven.

## Module Map

| Path | Type | Description |
|------|------|-------------|
| `lib/core/` | library | Shared: risk kernel, circuit breaker, position sizing, models, logging |
| `lib/telegram/` | library | Telegram bot framework + handlers |
| `lib/agents/` | library | OpenClaw/NemoClaw dispatch, orchestrator, runtime policy |
| `services/aster/` | service | Aster DEX trading bot — Solana perps, Shield HFT strategy [rari2] |
| `services/hyperliquid/` | service | Hyperliquid L1 trading bot — EIP-712 signed orders [rari2, stub] |
| `services/alpha/` | service | Trading engine: signals, risk, execution [rari1+rari2:18081] |
| `services/dashboard/` | service | sapphirealpha.xyz Flask dashboard [rari1:8080] |
| `services/control-plane/` | service | PM hub: projects, tasks, events, Kimi bridge [rari1:8082] |
| `services/webhook/` | service | TradingView webhook receiver [windows-pc:9090 + Cloudflare Tunnel] |
| `clients/blanga/` | client | BIS: brokerage intelligence for Joseph Blanga |
| `pine/` | pine | TradingView indicators and strategies (v1-v3 Ultra) |
| `skills/` | skills | Agent-executable capabilities (10 skills) |
| `tools/claude-analytics/` | tool | MCP server for Claude Code usage metrics (TypeScript) |
| `tools/pm-commander/` | tool | Sapphire Command — SwiftUI desktop app (7-tab command center) |
| `services/telegram-bot/` | service | NemotronRariBot — thin Telegram webhook, delegates to plugin tools |
| `data/benchmarks/kadima-labs/` | data | Kadima Labs AI benchmark suite (v1-v3, 70 charts, 30 JSON results) |
| `infra/cloudflare/` | infra | Cloudflare Tunnel config — public ingress (no GCP) |
| `infra/pi/` | infra | Raspberry Pi systemd services + deploy scripts |

## Devices

| Device | Tailscale IP | Role |
|--------|-------------|------|
| Mac | 100.67.171.79 | Commander, dev, git |
| Windows PC | 100.71.10.48 | RTX 5070 Ti, NemoClaw inference |
| rari1 | 100.120.191.1 | Controller Pi, Telegram bot, Kimi agent |
| rari2 | 100.87.225.89 | Trading Pi, Aster + Hyperliquid, ProtonVPN |

## Agent Coordination

- **Claude Code** (Mac): Architecture, refactors, planning
- **Claude Dispatch** (Cloud): Scheduled tasks — daily briefing, CI monitor, weekly review, self-improvement loop
- **Claw Code** (All devices): Rust-based local agent runtime — per-device profiles in `~/.claw/profiles/`
- **Kimi Claw** (rari1): Telegram ops, monitoring, quick tasks [offline — Pis down since 2026-03-28]
- **NemoClaw** (Windows): GPU compute, backtesting, inference via Ollama over Tailscale
- **OpenClaw workers** (Mac): Background automation via LaunchAgents

## Satellite Repos (orchestrated, not absorbed)

| Repo | Path | GitHub | Role |
|------|------|--------|------|
| claw-code | `~/Code/claw-code` | instructkr/claw-code | Local coding agent runtime (all devices) |
| Project-Go-Forward | `~/Code/Project-Go-Forward` | arigatoexpress/Project-Go-Forward | Client PM system (THO) |
| kimi-tools | `~/Code/kimi-tools` | arigatoexpress/kimi-tools | Distributed agent infra, Nemotron |
| regional-intel-workbench | `~/Code/regional-intel-workbench` | arigatoexpress/regional-intel-workbench | Intelligence platform |
| tradingview-mcp | `~/Code/tradingview-mcp` | arigatoexpress/tradingview-mcp | TradingView MCP server |
| Cointracker | `~/Code/Cointracker` | arigatoexpress/crypto-tax-tracker | Crypto tax engine |

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

All bots receive signals from `services/alpha/` via direct HTTP over Tailscale (no GCP Pub/Sub).

## Infrastructure

**On-prem — no GCP Cloud Run:**
- rari1 (100.120.191.1): dashboard:8080, control-plane:8082, kimi-claw, openclaw-gateway:18789
- rari2 (100.87.225.89): aster, hyperliquid, kimi-claw-slave, alpha-engine:18081
- Windows PC (100.71.10.48): webhook:9090 (Cloudflare Tunnel → webhook.sapphirealpha.xyz), Ollama
- Mac (100.67.171.79): OpenClaw workers, Claude Code, git

**Public ingress**: Cloudflare Tunnel (see `infra/cloudflare/SETUP.md`) — no port forwarding needed.

## Event System

Control-plane publishes events tagged with: `project:`, `agent:`, `priority:`, `type:`
Tag namespaces: `project:` `agent:` `priority:` `type:` `service:` `device:`
Events stored in JSONL file at `SAPPHIRE_EVENTS_PATH` (default: `app/data/system_events.jsonl`).
Agents subscribe to relevant tags. Telegram notifications filtered by subscription.
`data/connectors.json` — registry of all connectors, MCPs, LaunchAgents, exchanges, satellite repos.
`data/device_topology.json` — canonical device mesh topology with status, tools, services.
`plugins/claw-sapphire/` — Sapphire integration plugin for claw-code (status, tasks, notify, inference, events).

## Inference Fallback Chain

1. **Windows PC GPU** (100.71.10.48:11434) — RTX 5070 Ti, Nemotron/llama3.3:70b
2. **Mac local Ollama** (localhost:11434) — llama3.3:70b, llama3.2:3b
3. **Cloud API** (Anthropic) — claude-sonnet-4

## Trading Intelligence Stack

| System | Port/CLI | Data |
|--------|----------|------|
| TradingView MCP (tradesdontlie) | `tv` CLI, 78 tools via CDP:9222 | Live chart, Pine Script, indicator levels, strategy tester |
| OpenBB | REST API :6900 | Equity, crypto, options, macro from 32 providers (yfinance, FRED, SEC...) |

**TradingView**: `tv status`, `tv quote`, `tv pine compile`, `tv stream all`, `tv data lines`
**OpenBB**: `curl http://localhost:6900/api/v1/equity/price/quote?symbol=AAPL&provider=yfinance`
**Sapphire Market Tool**: `echo '{"action":"quote","symbol":"AAPL"}' | python3 plugins/claw-sapphire/tools/market.py`

## Sapphire Plugin (v0.3.0)

Claw-code plugin at `plugins/claw-sapphire/` with hooks + 7 tools:
- `sapphire_dispatch` — multi-tier task routing (T0→T1→T3)
- `sapphire_verify` — post-fix lint + test verification
- `sapphire_budget` — real token tracking per tier
- `sapphire_state` — persistent factory memory (issue tracking + backoff)
- `sapphire_status` — mesh device + inference status
- `sapphire_notify` — Telegram via NemotronRariBot
- `sapphire_market` — unified OpenBB + TradingView data
