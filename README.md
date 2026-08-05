<div align="center">

<img src="docs/brand/kadima-mark-b-quadrilemniscate-300.png" width="118" alt="Sapphire mark"/>

# Sapphire OS

</div>

[![CI](https://github.com/arigatoexpress/Sapphire/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/arigatoexpress/Sapphire/actions/workflows/ci.yml)
[![Security](https://github.com/arigatoexpress/Sapphire/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/arigatoexpress/Sapphire/actions/workflows/security.yml)
[![Tests](https://img.shields.io/badge/tests-7%2C836%2B%20passing-2ea44f)](scripts/ops/test_inventory.py)
[![License](https://img.shields.io/badge/license-proprietary-0A2540)](LICENSE)

**Self-sovereign capital intelligence OS** — trading, research, threat intel, and operator surfaces on a local-first plant (Mac + optional Windows desk), with a privacy-preserving public face.

> **Not financial advice.** Designated test/agentic wallets only for live automation. Fail-closed killswitches. Paper first.

---

## What ships in this monorepo

| Surface | Purpose |
|---|---|
| **Plant deck** | Local command UI — prefer ops-state deck `http://127.0.0.1:8100/` (API `:8099`) |
| **Grok web bridge** | `data/grok-web-exports/` — markdown knowledge plane for Grok web ↔ local densify/Ralph |
| **Services** | Alpha, dashboard, control-plane, inference proxy, content, security pipelines |
| **Trading adapters** | Paper · RH crypto client · confirmation firewall · auto-executor paper lane |
| **Agent charter** | [AGENTS.md](AGENTS.md) — safety boundaries for multi-agent collaborators |

Related public Mission Control: [sapphire-alpha-dashboard](https://github.com/arigatoexpress/sapphire-alpha-dashboard) · [sapphirealpha.xyz](https://sapphirealpha.xyz)

---

## Live plant (Ari desk — ops-state)

The **day-to-day trading plant** (free-reign, RH Agentic MCP, RH Chain L2, MOSS/MegaETH, Telegram Central Terminal, overnight loops) lives primarily under:

```text
~/ops-state/          # state, finish-line scripts, telegram-bot, rh-chain, moss
~/Knowledge/          # local vault + 0-Inbox/grok-web
```

| Component | Location / note |
|---|---|
| Free-reign policy | `ops-state/telegram-bot/free-reign.json` (+ mirrors) |
| Agentic trade plan | `ops-state/sovereign-desk/state/AGENTIC-TRADE-PLAN-LATEST.json` |
| Overnight / Ralph / densify | LaunchAgents `com.ari.*` / `com.sapphire.*` |
| Master agent handoff | `ops-state/agent-reports/MASTER-HANDOFF-CLAUDE-OPUS-LATEST.md` |
| Alpha learnings (AXTI) | `ops-state/finish-line/reports/ALPHA-LEARNINGS-AXTI-L2-LATEST.md` |

**Designated rails only:** RH Agentic ••••8144 · L2 `0xc2B5…c9EB` · MOSS MegaETH grant · paper.  
**Never auto:** THO/client money · Hermes messaging outward · DNS/prod without human gate.

---

## Grok web ↔ local bridge

```text
data/grok-web-exports/*.md
        ↓  sync_grok_web_exports.sh  (densify / Ralph / overnight)
~/Knowledge/0-Inbox/grok-web/
        ↓  publish_operator_feeds.py
http://127.0.0.1:8100/   plant deck
```

| Convention | Rule |
|---|---|
| Filename | `YYYY-MM-DD_topic-slug.md` |
| Web → plant commit | `web-export: <desc> [YYYY-MM-DD]` |
| Plant → web commit | `local-export: <desc> [YYYY-MM-DD]` |

```bash
bash ~/ops-state/finish-line/scripts/sync_grok_web_exports.sh
```

---

## Quick start (monorepo services)

```bash
# Requirements: Python 3.11+, Redis (optional), Ollama (optional)
pip install -r services/alpha/requirements.txt
pip install -r services/dashboard/requirements.txt

cp env.example .env
cp .env.integrations.example .env.integrations

# Core services (example)
python3 services/inference-proxy/app.py &
(cd services/alpha && python3 -m uvicorn src.signal_logger:app --port 18081) &
(cd services/dashboard && python3 app.py) &

curl -s http://127.0.0.1:11435/health | python3 -m json.tool
```

For the **operator plant** (trading desk), follow `ops-state` handoffs and LaunchAgents — not only this monorepo’s service ports.

---

## Architecture (monorepo)

Event-bus-mediated concerns (Redis Streams + JSONL fallback):

- **Trading** — TradingView / signals → risk kernel → confirmation firewall → paper or broker adapters  
- **Intelligence** — on-chain, macro, threat, regime silos  
- **Synthesis** — brain health score + narrative  
- **Content** — research-to-publish with quality rubric  
- **Security** — SBOM, model verify, network mapper, global kill switch  
- **Control** — Telegram, dashboards, inference proxy  

### Operator plant (2026-08)

- Free-reign multi-rail on designated wallets (caps + dens)  
- Options-first alpha (AXTI-class: open defined-risk, scale out on gamma, never hold to worthless)  
- Overnight agentic coding + plant heal loops  
- Telegram as **away-from-home Central Terminal**  

---

## Tech stack

Python · FastAPI · Flask · Redis · Ollama · DuckDB · Solidity · Tailscale · GCP · Playwright

---

## Safety

- Research/prototype software. **Not financial advice.**  
- Paper trading first. Live automation is **capped**, dens-listed, and kill-switched.  
- Fail-closed: gate/killswitch failure stops trading rather than proceeding.  
- See [LICENSE](LICENSE).

---

## Agent collaborators

See **[AGENTS.md](AGENTS.md)** for multi-agent charter and commands.  
Resume after Claude/Codex credit gaps:  
`ops-state/agent-reports/MASTER-HANDOFF-CLAUDE-OPUS-LATEST.md` (also mirrored under `data/grok-web-exports/`).

---

## Repo map (do not re-fork)

| Keep canonical | Avoid forking into Sapphire |
|---|---|
| This monorepo + `ops-state` plant | `ops-server-task*`, `fleet-lease-task*`, `quant-perps-*` clones |
| `sapphire-alpha-dashboard` (public) | One-off deploy-candidates without ≥2 call-sites |
| `Project-Go-Forward` (THO — **separate fence**) | Bulk automation into THO main |

Debt inventory: `ops-state/agent-reports/REPO-CONSOLIDATION-2026-08-05.md`
