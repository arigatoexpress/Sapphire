# Sapphire — Working with AI Coding Agents

This file is the single source of truth for any AI coding agent (Claude Code, Codex, Kimi Code, or future) working in this repo. Read it first.

## What this repo is

Sapphire OS is Ari's personal factory / agent runtime. It orchestrates:

- A 4-tier inference mesh (Windows RTX 5070 Ti → Pi cluster → Mac Ollama → Kimi cloud)
- A `claw-sapphire` plugin with 19 tools exposed to the `claw-code` runtime
- 19 scheduled tasks running 24/7 on the Mac (morning briefing, threat intel, factory, trading research, etc.)
- A Telegram-first PM bot (`services/pm_bot/`) for operational commands on the go
- Production-grade trading + research flows with paper-trading + Kronos daily predictions

It talks to sibling repos — `Project-Go-Forward` (THO app), `cyber-threat-bot`, `regional-intel-workbench`, `claw-code`, `tradingview-mcp-v2` — and to the live Firestore database in the `tho-ai-agent` GCP project.

## Production state

- Mac services run as LaunchAgents (`~/Library/LaunchAgents/com.sapphire.*.plist`, `ai.hermes.gateway.plist`).
- Windows services run as Scheduled Tasks (OllamaServe, SapphireWebhook, SapphireDashboard).
- Cloud Run service `project-go-forward` in project `tho-ai-agent` serves the THO app at `https://sapphirealpha.xyz` and `https://project-go-forward-trgi34bxuq-uc.a.run.app`.
- Cloud DNS zone for `sapphirealpha.xyz` lives in `sapphire-479610` — **do not delete that project**; the E-pool NS delegation is locked to it.
- Firestore `(default)` in `tho-ai-agent` has delete protection enabled.

## Workflow for any AI agent

### Branching

- **Always branch off `origin/main`, not local `main`.** Local `main` can drift. Use:
  ```bash
  git fetch origin && git switch -c feat/<name> origin/main
  ```
- Branch naming: `feat/*`, `fix/*`, `chore/*`, `docs/*`, `test/*`.
- Match the existing commit-message style in `git log`.

### PRs

- Open a **draft** PR unless the task is an exploratory throwaway branch.
- **Never merge your own PR without the human approving.** Production-adjacent repos (this one, THO, cyber-threat-bot) require human in the loop.
- Run touched-file lint (`ruff check <files>`) before push. Full-repo sweeps go in their own `chore/` PRs.
- If a test fails, fix it or mark it skip-with-reason — don't ignore.

### Conflict avoidance

When multiple agents are active:

- Check `gh pr list` across Sapphire + THO + cyber-threat-bot before starting.
- `git worktree list` to see what other agents are doing locally.
- Prefer stacking PRs over parallel branches on the same files.
- `main.py` files tend to be hot — the later branch rebases.

## File-level ownership

| Area | Rule |
|-----|-----|
| `plugins/claw-sapphire/tools/` | Open. Add new tools freely; register in `infra/tool-registry.yaml`. |
| `plugins/claw-sapphire/hooks/` | Shared telemetry. Read before you edit. |
| `services/*/launchagent/*.plist` | Don't `launchctl load/unload` from agent scripts. Ship the plist; tell the human to load it. |
| `agents/config/*.yaml` | Config for running workflows. Changes hot-reload; test before committing. |
| `infra/tool-registry.yaml` | Required entry for every tool. Missing → lint fails. |
| `data/intelligence/`, `data/paper_trading.jsonl`, `data/signals/`, `data/enrich/*` | Live operational data. Never delete, never commit. |

## Division of labor — when to pick which agent

Rough guidance; the human will override when needed:

- **Codex** — primary production-autonomy lead for Sapphire OS. Owns repo hygiene, operational triage, architecture decisions, multi-step implementation, PR coordination, CI follow-through, deployment notes, and cross-repo handoffs unless Ari explicitly assigns another lead.
- **Claude Code** — constrained reviewer/helper. Useful for second opinions, prose-heavy docs, or isolated review passes, but should not drive production-autonomy, broaden local permissions, merge PRs, or take over operations unless Ari explicitly asks.
- **Kimi Code / long-context agents** — large code surveys, cross-repo pattern extraction, research-heavy writing.
- **Local models via inference proxy** (hermes3, deepseek-r1, qwen3) — small, frequent, latency-sensitive tasks (form extraction, quick summaries, classification). Free tier on the mesh.

When a task involves real money, production credentials, or shared infrastructure — always loop in the human.

## Codex lead operating model

Codex is expected to keep the project moving without waiting for Claude handoffs:

- Start from a current-state verification, not stale audit notes.
- Keep `/Users/aribs/Code/Sapphire` clean on `origin/main` whenever possible because LaunchAgents execute from that path.
- Use short-lived worktrees under `/Users/aribs/Code/_worktrees/` for PR work, then remove clean worktrees after merge or abandonment.
- Preserve local WIP before cleanup with a backup branch plus patch/stash when there is any risk of losing user work.
- Prefer non-draft PRs for low-risk docs/test/tooling changes after local checks pass; use draft PRs for risky production behavior until the blast radius is clear.
- Treat Claude-local settings as a safety surface: narrow allowlists when safe, and do not add broad service-control, workflow-disable, secret-read, or production-mutating permissions.

## Mesh inference (tiers)

Call via the inference proxy at `http://127.0.0.1:11435` (Mac LaunchAgent `com.sapphire.inference-proxy`):

| Tier alias | Upstream | Use for |
|-----|-----|-----|
| `fast` / `quick` | `nemotron-mini:4b` (Windows, 232 tok/s) | classification, simple extraction |
| `balanced` | `hermes3:8b` (Windows, 118 tok/s) | tool calls, chat |
| `code` | `gemma4:latest` (Windows, 154 tok/s) | code-only tasks |
| `reason` | `deepseek-r1:14b` (Windows, 80 tok/s) | structured reasoning |
| `qwen-reason` | `qwen3.5:9b` (Windows) | faster reasoning |
| `deep` | `qwen3:14b` (Windows) | multi-step analysis |
| `cascade/moe` | `nemotron-cascade-2` (Windows, 16 tok/s) | MoE, fits 16 GB VRAM |
| `large` | `qwen2.5:32b` (Windows, background) | overnight / batch |
| `qwen3.6` | `qwen3.6:27b` (Windows primary, Mac exact fallback, ~7 tok/s) | latest Qwen generation; explicit alias only |
| Cloud fallback | Kimi K2 via moonshot.cn | when Windows is offline |

Windows PC (Tailscale `100.71.10.48`) must be online for tiers 1–5. The proxy falls back to Kimi automatically on timeout; you don't need to handle it.

## Common commands

```bash
# Run all Sapphire tests (fast — most are unit tests)
pytest plugins/claw-sapphire/tests/ -q

# Validate the tool registry
python scripts/validate_tool_registry.py

# Check scheduled tasks
launchctl list | grep sapphire

# Probe the mesh
curl -s http://127.0.0.1:11435/health | python -m json.tool

# PM bot (when SAPPHIRE_PM_BOT_ALLOWED_USER_IDS is set + LaunchAgent loaded)
launchctl load ~/Library/LaunchAgents/com.sapphire.pm-bot.plist
launchctl list | grep pm-bot
```

## What NOT to do

- **Never** delete projects in GCP, drop Firestore collections, or force-push to `main`.
- **Never** commit contents of `data/paper_trading.jsonl`, `data/signals/`, `data/enrich/*`, or any `~/.config/sapphire-secrets/*` file.
- **Never** embed secrets inline in code — use env vars or `~/.config/sapphire-secrets/` files.
- **Never** change the inference-proxy's tier routing without running the mesh benchmark first.
- **Never** run `launchctl bootout` on a service other sibling services depend on.

## Sibling repos you'll touch from here

| Repo | Where | Purpose |
|-----|-----|-----|
| `Project-Go-Forward` | `~/Code/Project-Go-Forward` | THO app — customer/deal/doc CRM, Cloud Run deployed |
| `claw-code` | `~/Code/claw-code` | Rust agent runtime that hosts `claw-sapphire` as a plugin |
| `cyber-threat-bot` | `~/Code/cyber-threat-bot` | CISA/NVD/MITRE threat intel bot |
| `regional-intel-workbench` | `~/Code/regional-intel-workbench` | Intelligence platform + ve vote monitor |
| `tradingview-mcp-v2` | `~/Code/tradingview-mcp-v2` | 78-tool TradingView MCP bridge |

Cross-repo changes should keep each repo's surface stable — prefer new endpoints / flags over breaking changes. The `dev_pulse` tool shows unified state across all of them.

## Related docs

- `plugins/claw-sapphire/README.md` — plugin authoring
- `infra/tool-registry.yaml` — all 19+ tool registrations
- `docs/DEPLOYMENT.md` (if present) — LaunchAgent install/unload
- THO's `AGENTS.md` — sister doc for the THO app specifically
