# Sapphire — Creative Agent Charter

This file is the single source of truth for any AI coding agent (Claude Code, Codex, Kimi Code, or future) working in this repo. Read it first.

## What This Repo Is Now

Sapphire is the current command repo for Ari's evolving autonomous system. It is
not a fixed product brief. Treat the repo as a live collection of useful parts,
runtime surfaces, experiments, and control-plane assets that can be composed
into something stronger.

The current useful materials include:

- A Kimi/Gemini-first agent runtime with Mac Ollama fallback for sensitive/offline work
- A `claw-sapphire` plugin with 19 tools (formerly also exposed to the now-archived `claw-code` Rust runtime; agent dispatch is now handled inside Sapphire)
- 19 scheduled tasks running 24/7 on the Mac (morning briefing, threat intel, factory, trading research, etc.)
- A Telegram-first PM bot (`services/pm_bot/`) for operational commands on the go
- Production-grade trading + research flows with paper-trading + Kronos daily predictions

It also talks to sibling repos and local services. Those relationships are
inputs, not walls. If a better product direction emerges from the current
assets, build toward it.

## Creative Mandate

Do not preserve old scaffolding just because it exists. Build the coolest,
clearest, most useful system the current assets make possible.

Good directions include:

- intelligence dashboards that explain current state and recommend action;
- regional, cyber, market, and business-intel loops that create durable
  artifacts;
- operator controls that make risky actions explicit, reversible, and auditable;
- unified local command surfaces across Sapphire and satellites;
- demos that are legible to judges, clients, and operators without pretending
  paper-only systems are live.

When the repo's old docs imply a narrow mission, treat that as history. Ari's
latest instruction and verified current state win.

## Production state

- Mac services run as LaunchAgents (`~/Library/LaunchAgents/com.sapphire.*.plist`). Note: `ai.hermes.gateway.plist` must remain disabled — `hermes-agent` was archived 2026-05-12.
- Windows services were part of the old inference and Telegram support path. Treat them as deprecated for new agentic Telegram work unless a fresh live audit explicitly re-enables them.
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

### PRs and merges

- Open ready-to-merge PRs by default once local verification passes. Use draft
  PRs only for exploratory work, unclear blast radius, or intentionally blocked
  production behavior.
- Codex may push branches and merge its own green, non-draft Sapphire PRs
  without waiting for human review when the change is reversible, CI or
  documented local verification is clean, the rollback path is clear, and no
  high-risk surface below is being activated.
- Human approval is required before real money movement, live trade execution,
  production Telegram sends, secret exposure/rotation, destructive data or
  infrastructure deletion, workflow/branch-protection disabling, force-pushing
  shared protected branches, or broadening permissions on sensitive systems.
- Sibling repos keep their own `AGENTS.md` rules unless Ari explicitly grants a
  separate autonomy window for that repo.
- Run touched-file lint (`ruff check <files>`) before push. Full-repo sweeps go in their own `chore/` PRs.
- If a test fails, fix it or mark it skip-with-reason; do not ignore it.

### Deletion, replacement, and cleanup

- Deletion is allowed and encouraged when it removes dead code, duplicate
  surfaces, stale docs, misleading scaffolds, or generated clutter.
- Delete tracked code in focused PRs when tests and rollback prove the
  replacement is better.
- Delete ignored/generated artifacts directly when they are reproducible.
- Quarantine or stash unknown WIP first when it may contain evidence or user
  work.
- Prefer one coherent path over several half-maintained alternatives.
- If a route, script, dashboard, workflow, or doc is stale and actively
  confusing agents, either fix it or remove it.

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

Rough guidance; Ari can override when needed:

- **Codex** — primary production-autonomy lead for Sapphire OS. Owns repo hygiene, operational triage, architecture decisions, multi-step implementation, PR coordination, CI follow-through, deployment notes, and cross-repo handoffs unless Ari explicitly assigns another lead.
- **Claude Code** — constrained reviewer/helper. Useful for second opinions, prose-heavy docs, or isolated review passes, but should not drive production-autonomy, broaden local permissions, merge PRs, or take over operations unless Ari explicitly asks.
- **Kimi Code / long-context agents** — large code surveys, cross-repo pattern extraction, research-heavy writing.
- **Hosted Kimi/Gemini lanes** — default for new agentic Telegram work, structured triage, source ranking, research synthesis, and evals.
- **Local models via inference proxy** (`gemma4:latest`, `qwen3.6:27b`) — fallback-only for sensitive/offline work. Nemotron and Hermes are compatibility paths, not defaults.

When a task involves real money, production credentials, destructive shared
infrastructure changes, or live external messaging, stop at the safest
prepared artifact unless Ari has explicitly authorized that exact live step.
Everywhere else, act boldly with tests and a rollback path.

## Codex lead operating model

Codex is expected to keep the project moving without waiting for Claude handoffs:

- Start from a current-state verification, not stale audit notes.
- Keep `/Users/aribs/Code/Sapphire` clean on `origin/main` whenever possible because LaunchAgents execute from that path.
- Use short-lived worktrees under `/Users/aribs/Code/_worktrees/` for PR work, then remove clean worktrees after merge or abandonment.
- Preserve local WIP before cleanup with a backup branch plus patch/stash when there is any risk of losing user work.
- Prefer non-draft PRs for low-risk docs/test/tooling changes after local checks pass; use draft PRs for risky production behavior until the blast radius is clear.
- Treat Claude-local settings as a safety surface: narrow allowlists when safe, and do not add broad service-control, workflow-disable, secret-read, or production-mutating permissions.

## Agent Runtime And Local Fallback

The agentic Telegram path is Kimi/Gemini first:

- Kimi K2.6 for long-context operator work.
- Gemini on Vertex for structured triage, clustering, cited synthesis, and evals.
- Sapphire PM bot owns Telegram ingress and sends only through explicit confirmation paths.

Call local fallback through the inference proxy at `http://127.0.0.1:11435` only when a task is sensitive, offline, or explicitly local:

| Alias | Upstream | Use for |
|-----|-----|-----|
| `auto` / `fast` / `quick` / `balanced` | `gemma4:latest` (Mac Ollama) | fresh local fallback |
| `code` / `fast-code` / `local-fallback` | `gemma4:latest` (Mac Ollama) | local coding and tool reasoning fallback |
| `qwen3.6` | `qwen3.6:27b` (Mac Ollama) | heavy local reasoning fallback |
| `kimi` / `cloud` / `research` | Kimi Cloud | non-sensitive cloud fallback only |

Deprecated local Telegram/gateway services (`ai.hermes.gateway`, `ai.openclaw.gateway`, `com.sapphire.healthz-watcher`, `com.sapphire.mac-to-windows-tunnel`) must remain disabled or quarantined; `hermes-agent` and `openclaw` repos were archived 2026-05-12 and these plists are no longer maintained.

## Common commands

```bash
# Run all Sapphire tests (fast — most are unit tests)
pytest plugins/claw-sapphire/tests/ -q

# Validate the tool registry
python scripts/validate_tool_registry.py

# Check scheduled tasks
launchctl list | grep sapphire

# Probe local fallback
curl -s http://127.0.0.1:11435/health | python -m json.tool

# Fresh agent runtime readiness
python3 scripts/ops/fresh_agent_runtime_status.py --json

# PM bot (when SAPPHIRE_PM_BOT_ALLOWED_USER_IDS is set + LaunchAgent loaded)
launchctl load ~/Library/LaunchAgents/com.sapphire.pm-bot.plist
launchctl list | grep pm-bot
```

## Hard Stops

- **Never** delete projects in GCP, drop Firestore collections, or force-push to `main`.
- **Never** commit contents of `data/paper_trading.jsonl`, `data/signals/`, `data/enrich/*`, or any `~/.config/sapphire-secrets/*` file.
- **Never** embed secrets inline in code — use env vars or `~/.config/sapphire-secrets/` files.
- **Never** change the inference-proxy's tier routing without running the mesh benchmark first.
- **Never** run `launchctl bootout` on a service other sibling services depend on.

These hard stops do not prohibit deleting local dead code, stale docs,
misleading prototypes, unused branches, broken routes, duplicate scripts, or
reproducible generated files. Clean those up when doing so makes the system
easier to understand and operate.

## Sibling repos you'll touch from here

| Repo | Where | Purpose |
|-----|-----|-----|
| `Project-Go-Forward` | `~/Code/Project-Go-Forward` | THO app — customer/deal/doc CRM, Cloud Run deployed |
| `claw-code` | archived to `_Archive_2026-05-12/` | Rust agent runtime (archived 2026-05-12; Sapphire now owns agent dispatch directly) |
| `cyber-threat-bot` | `~/Code/cyber-threat-bot` | CISA/NVD/MITRE threat intel bot |
| `regional-intel-workbench` | `~/Code/regional-intel-workbench` | Intelligence platform + ve vote monitor |
| `tradingview-mcp-v2` | `~/Code/tradingview-mcp-v2` | 78-tool TradingView MCP bridge |

Cross-repo changes should keep each repo's surface stable — prefer new endpoints / flags over breaking changes. The `dev_pulse` tool shows unified state across all of them.

## Related docs

- `plugins/claw-sapphire/README.md` — plugin authoring
- `infra/tool-registry.yaml` — all 19+ tool registrations
- `docs/DEPLOYMENT.md` (if present) — LaunchAgent install/unload
- THO's `AGENTS.md` — sister doc for the THO app specifically
