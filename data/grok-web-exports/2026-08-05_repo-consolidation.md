---
source: local-export
date: 2026-08-05
type: ops
topics: [repo, consolidation]
title: Repo consolidation
---

# Repo consolidation map — 2026-08-05

**Goal:** one brain (Sapphire + ops-state), fewer zombie clones, archive over delete.

## Canonical (keep / improve)

| Path | Role |
|---|---|
| `~/Code/Sapphire` | Monorepo OS + `data/grok-web-exports` bridge |
| `~/Code/sapphire-alpha-dashboard` | Public Mission Control |
| `~/ops-state` | Live plant state, finish-line, telegram-bot, rh-chain, moss, sovereign-desk |
| `~/Knowledge` | Local vault + grok-web inbox |
| `~/Code/Project-Go-Forward` | **THO client — FENCED from fleet bulk** |
| `~/Code/fedex-delivery-markets` | Work/governance |
| `~/Code/remote-gpu-gateway` | Ollama gateway for local coders |

## Archive candidates (do not delete; move to `~/Code/_Archive_2026-08/` or `~/_Archive_*`)

### Clearly retired
- `~/Code/desk-orchestrator-directive.RETIRED-20260728`
- `~/ops-state/desk-orchestrator.RETIRED-20260728`
- `~/ops-state/telegram-bot-deploy.RETIRED-20260728`
- `~/ops-state/telegram-bot.RETIRED-20260728-MAC` (if present)

### Task / mergeverify clones (extract only if ≥2 real consumers)
- `~/Code/ops-server-task*`
- `~/Code/fleet-lease-task*`
- `~/Code/ops-server-grok-*` / `ops-server-notification-only` (unless actively used)
- `~/ops-state/task0*-hostile-review.*` / `task0*-exact-merge.*`
- `~/ops-state/deploy-candidates/*` old sapphire-combined worktrees
- `~/ops-state/chassis-runtime-candidates/*`

### Quant perps forks
- Prefer **one** of `quant-perps` / `quant-perps-main` / thesis/advisory/bronze — archive the rest after confirming no LaunchAgent points at them.

## Consolidation rules (Karpathy)

1. **Extract at ≥2 call-sites** — no speculative platforms.  
2. **Archive > delete** for irreversible history.  
3. **Never** bulk-merge into THO Project-Go-Forward.  
4. **Never** `git add -A` when shipping plant scripts.  
5. Prefer ops-state finish-line scripts over duplicating into Sapphire services.

## Performed 2026-08-05 (this pass)

- Professional Sapphire README rewrite (plant + bridge + fences).  
- Master Opus handoff refreshed.  
- Report spam prune (overnight beats) already applied earlier.  
- Archive moves: see companion script log if `ARCHIVE-MOVES-*.log` exists.

## Recommended next archive command (human-gated if unsure)

```bash
mkdir -p ~/Code/_Archive_2026-08
# Only after confirming no LaunchAgent WorkingDirectory:
# mv ~/Code/desk-orchestrator-directive.RETIRED-20260728 ~/Code/_Archive_2026-08/
# mv ~/Code/ops-server-task083-* ~/Code/_Archive_2026-08/  # if unused
```


## CRITICAL: telegram-bot path (2026-08-05)

Live Mac bot tree was **misnamed** `telegram-bot.RETIRED-20260728-MAC` with
`ops-state/telegram-bot` as a **symlink** to it. Archive-by-name would break the plant.

**Canonical now:** real directory `~/ops-state/telegram-bot/` (not a symlink, not RETIRED).
Never archive paths named RETIRED without checking `readlink` / LaunchAgent WorkingDirectory.
