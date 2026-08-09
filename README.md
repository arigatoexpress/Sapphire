<div align="center">

<img src="docs/brand/kadima-mark-b-quadrilemniscate-300.png" width="118" alt="Sapphire mark"/>

# Sapphire OS

</div>

[![CI](https://github.com/arigatoexpress/Sapphire/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/arigatoexpress/Sapphire/actions/workflows/ci.yml)
[![Security](https://github.com/arigatoexpress/Sapphire/actions/workflows/security.yml/badge.svg?branch=main)](https://github.com/arigatoexpress/Sapphire/actions/workflows/security.yml)
[![Tests](https://img.shields.io/badge/tests-7%2C968%2B%20passing-2ea44f)](scripts/ops/test_inventory.py)
[![License](https://img.shields.io/badge/license-proprietary-0A2540)](LICENSE)

**Self-sovereign capital intelligence OS** — a private plant that earns on designated rails, publishes real research, and self-improves through agent harnesses.

> **North star (2026-08-06):** the **Windows desktop is the always-on private datacenter**. Mac is the mobile commander. GCP is the warehouse + remote Cloud Shell seat. See the [Windows Datacenter Master Plan](docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md).

> **Not financial advice.** Designated test/agentic wallets only for live automation. Fail-closed killswitches. Paper first.

- 7,968+ passing tests across 487 files

---

## The point of this project

| Pillar | Meaning |
|---|---|
| **Windows private DC** | `DESKTOP-HFCK6U9` — GPU inference, research workers, TV agent, scheduled harnesses, L2 workers when armed |
| **Agent harnesses** | Supervisors, densify/Ralph, free-reign multi-rail, AXTI risk, genome learner, content engine — with receipts, budgets, promote/demote |
| **Earn** | Options-first + capped L2 + grant-gated MOSS on **designated rails only** |
| **Publish** | Reconstructible research via `lib/content` + public Mission Control |
| **Self-improve** | Closed trades → genome lessons → champion/challenger — not chat vibes |
| **Best OSS** | Surgical extract (Nautilus/LEAN/Qlib/Freqtrade/…) into Sapphire contracts — never four overlapping “AI funds” |

### Fleet roles

```text
Mac commander     → authority, killswitch, densify, broker MCP, plant deck :8100
Windows DC        → always-on compute + research + execution workers (designated rails)
GCP               → BQ/GCS lake, public site, Cloud Shell / Gemini invent+PR seat
Pi mesh           → collectors / lite inference (when inventoryed)
Telegram          → away Central Terminal (Trade vs Command Center)
```

---

## Start here (by seat)

| You are… | Open this |
|---|---|
| **Grok dedicated project** | [`projects/grok/`](projects/grok/) · `make grok-loop` · `make grok-status` |
| **Gemini in Google Cloud Shell** | [`docs/handoffs/GEMINI-CLOUDSHELL-MASTER-PROMPT-2026-08-06.md`](docs/handoffs/GEMINI-CLOUDSHELL-MASTER-PROMPT-2026-08-06.md) → `bash scripts/ops/gcp_cloudshell_bootstrap.sh` |
| **Any agent (Claude/Codex/Grok)** | [`AGENTS.md`](AGENTS.md) · [`SAPPHIRE_PROMPT.md`](SAPPHIRE_PROMPT.md) · master plan |
| **On the Mac plant** | `ops-state` free-reign + [`docs/alpha/GROK-CHAT-ALPHA-2026-08-06.md`](docs/alpha/GROK-CHAT-ALPHA-2026-08-06.md) |
| **Hardening Windows** | [`docs/ops/windows-desktop-server-runbook.md`](docs/ops/windows-desktop-server-runbook.md) + master plan §8 ladder |

```bash
# Cloud Shell one-liner
git clone https://github.com/arigatoexpress/Sapphire.git ~/Sapphire   # or pull
cd ~/Sapphire && bash scripts/ops/gcp_cloudshell_bootstrap.sh
less docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md
less docs/handoffs/GEMINI-CLOUDSHELL-MASTER-PROMPT-2026-08-06.md
```

---

## What ships in this monorepo

| Surface | Purpose |
|---|---|
| **Plant deck** | Local command UI — prefer ops-state deck `http://127.0.0.1:8100/` (API `:8099`) |
| **Grok web bridge** | `data/grok-web-exports/` — markdown knowledge plane for Grok web ↔ local densify/Ralph |
| **Alpha ledger** | `data/alpha/alpha_ledger.json` — ranked trading/automation/bridge alpha |
| **Services** | Alpha, dashboard, control-plane, inference proxy, content, security pipelines |
| **Trading adapters** | Paper · RH crypto client · confirmation firewall · auto-executor paper lane |
| **Windows setup** | `scripts/windows_setup/` — research worker, TV agent, availability |
| **Agent charter** | [AGENTS.md](AGENTS.md) — safety boundaries for multi-agent collaborators |

Related public Mission Control: [sapphire-alpha-dashboard](https://github.com/arigatoexpress/sapphire-alpha-dashboard) · [sapphirealpha.xyz](https://sapphirealpha.xyz)

---

## Live plant (Ari desk — ops-state)

The **day-to-day trading plant** (free-reign, RH Agentic MCP, RH Chain L2, MOSS/MegaETH, Telegram Central Terminal, overnight loops) lives primarily under:

```text
~/ops-state/          # state, finish-line scripts, telegram-bot, rh-chain, moss
~/Knowledge/          # local vault + 0-Inbox/grok-web
~/Code/Sapphire       # this monorepo (git truth)
```

| Component | Location / note |
|---|---|
| **Master plan** | `docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md` |
| Free-reign policy | `ops-state/telegram-bot/free-reign.json` (+ mirrors) |
| Agentic trade plan | `ops-state/sovereign-desk/state/AGENTIC-TRADE-PLAN-LATEST.json` |
| Overnight / Ralph / densify | LaunchAgents `com.ari.*` / `com.sapphire.*` |
| Master agent handoff | `ops-state/agent-reports/MASTER-HANDOFF-CLAUDE-OPUS-LATEST.md` |
| Alpha learnings (AXTI) | `ops-state/finish-line/reports/ALPHA-LEARNINGS-AXTI-L2-LATEST.md` · git mirror under `data/grok-web-exports/` |

**Designated rails only:** RH Agentic ••••8144 · L2 `0xc2B5…c9EB` · MOSS MegaETH grant · paper.  
**Never auto:** THO/client money · Hermes messaging outward · DNS/prod without human gate.

### Mandate snapshot

`free_reign_multi_rail` — options-first (AXTI playbook) · L2 ≤$10 dens · no dust re-buy · MOSS only if grant live.

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
# Prefer plant wrapper if present; monorepo canonical also works:
bash ~/ops-state/finish-line/scripts/sync_grok_web_exports.sh 2>/dev/null \
  || bash scripts/ops/sync_grok_web_exports.sh
python3 scripts/ops/grok_bridge_status.py
```

Lane status: [`docs/handoffs/GROK-BRIDGE-LANE-STATUS-2026-08-06.md`](docs/handoffs/GROK-BRIDGE-LANE-STATUS-2026-08-06.md)

---

## Quick start (monorepo services)

```bash
# Tests / lint
pytest tests/unit/ --tb=short -q
ruff check .
make doctor

# Control plane / dashboard (Mac)
# see CLAUDE.md for current port map — avoid colliding with OpenWebUI / control-plane

# Windows research worker (on the DC, paper only)
# powershell -File scripts/windows_setup/run_research_worker.ps1 -BacktestDays 7
```

Full command map: **[CLAUDE.md](CLAUDE.md)** · structure: **[STRUCTURE.md](STRUCTURE.md)** · GCP data: **[docs/gcp-data-engineering.md](docs/gcp-data-engineering.md)**.

---

## Active product threads

- Free-reign multi-rail on designated wallets (caps + dens)
- Options-first alpha (AXTI-class: open defined-risk, scale out on gamma, never hold to worthless)
- Windows DC harness ladder (post-boot → research worker → armed L2)
- Overnight agentic coding + plant heal loops
- Telegram as **away-from-home Central Terminal**
- Knowledge bridge + alpha ledger densify path
- GCP lake + Cloud Shell / Gemini remote advance

---

## Tech stack

Python · FastAPI · Flask · Redis · Ollama · DuckDB · Solidity · Tailscale · GCP · Playwright · Windows Task Scheduler · LaunchAgents

---

## Safety

- Research/prototype software. **Not financial advice.**
- Paper trading first. Live automation is **capped**, dens-listed, and kill-switched.
- Fail-closed: gate/killswitch failure stops trading rather than proceeding.
- See [LICENSE](LICENSE) · [SECURITY.md](SECURITY.md).

---

## Agent collaborators

| Doc | Use |
|---|---|
| **[AGENTS.md](AGENTS.md)** | Multi-agent charter |
| **[GEMINI.md](GEMINI.md)** | Gemini CLI / Cloud Shell posture |
| **[SAPPHIRE_PROMPT.md](SAPPHIRE_PROMPT.md)** | Session launcher |
| **Master plan** | Windows DC north star |
| **Gemini Cloud Shell prompt** | Paste into Gemini on Cloud Shell |

Resume after Claude/Codex credit gaps:  
`ops-state/agent-reports/MASTER-HANDOFF-CLAUDE-OPUS-LATEST.md` (also mirrored under `data/grok-web-exports/`).

---

## Repo map (do not re-fork)

| Keep canonical | Avoid forking into Sapphire |
|---|---|
| This monorepo + `ops-state` plant | `ops-server-task*`, `fleet-lease-task*`, `quant-perps-*` clones |
| `sapphire-alpha-dashboard` (public) | One-off deploy-candidates without ≥2 call-sites |
| `Project-Go-Forward` (THO — **separate fence**) | Bulk automation into THO main |

Debt inventory: `ops-state/agent-reports/REPO-CONSOLIDATION-2026-08-05.md` (git mirror under exports when present).
