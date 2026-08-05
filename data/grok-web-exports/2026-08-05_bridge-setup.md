---
source: grok-web
date: 2026-08-05
type: architecture
topics: [bridge, knowledge-plane, plant-deck, densify, ralph, github-connector]
---

# Bridge setup — Grok web ↔ local Sapphire plant (2026-08-05)

This file is the **web-export** contract for the shared knowledge plane.

## Goal

Automate knowledge exchange so Grok web and Grok CLI share trade ideas, research,
and plant status without manual file drops.

## Paths

| Role | Path |
|---|---|
| Repo | `arigatoexpress/Sapphire` |
| Shared store | `data/grok-web-exports/` |
| Local inbox | `~/Knowledge/0-Inbox/grok-web/` |
| Deck | `http://127.0.0.1:8100/` |
| API | `http://127.0.0.1:8099/` (not the trading UI) |
| Sync | `~/ops-state/finish-line/scripts/sync_grok_web_exports.sh` |

## Local loop contract (live)

1. `git pull --ff-only` on Sapphire (best-effort; non-fatal)
2. Copy new/changed `*.md` into Knowledge inbox (**never** delete source)
3. Run `publish_operator_feeds.py` → operator feeds → plant deck
4. Log: `~/ops-state/logs/grok-web-bridge.log`

Hooked from: `densify_dream_plant.sh`, `ralph_plant_loop.sh`, overnight agentic, night all-hands.

## Naming

| Direction | Filename | Commit prefix |
|---|---|---|
| web → local | `YYYY-MM-DD_topic-slug.md` | `web-export: … [YYYY-MM-DD]` |
| local → web | same | `local-export: … [YYYY-MM-DD]` |

## GitHub connector note (2026-08-05)

Grok GitHub MCP currently returns `403 Resource not accessible by integration`
on `create_or_update_file` / `push_files` — **read-only** scope. Until re-auth
with **contents:write** (or full `repo`) on `arigatoexpress/Sapphire`:

- Web agents: drop exports via local free-reign / CLI agent into this folder, **or**
- Human: reconnect GitHub connector with write, then reply “try again”

Local commit + push (this path) keeps the bridge live without waiting.

## Plant posture (same day)

- Agentic sleeve: boring equities **exiting** (IBIT/HOOD/PLTR/NVDA sells queued)
- Mandate: **asymmetric_only** — defined-risk options preferred; L2 memes OFF
- Risk automation: TP +75% / SL −40% (`agentic_asymmetric_risk.py`)

## Next for web side

Package high-value web content as `web-export:` commits into this folder.
Local densify/Ralph will pick them up on the next beat.
