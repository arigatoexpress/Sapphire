---
source: grok-web
date: 2026-08-04
type: architecture
topics: [bridge, knowledge-plane, plant-deck, densify, ralph]
---

# Bridge setup — Grok web ↔ local Sapphire plant

This file is the first export demonstrating the bridge.

## Goal

Automate knowledge exchange so Grok web and Grok CLI share trade ideas, research,
and plant status without manual file drops.

## Local path

- Repo: `arigatoexpress/Sapphire`
- Folder: `data/grok-web-exports/`
- Inbox: `~/Knowledge/0-Inbox/grok-web/`
- Deck: `http://127.0.0.1:8100/`
- API: `http://127.0.0.1:8099/` (not the trading UI)

## Local loop contract

1. `git pull` on Sapphire (best-effort; non-fatal)
2. Copy new/changed `*.md` into Knowledge inbox (never delete source)
3. Run `publish_operator_feeds.py`
4. Log to `~/ops-state/logs/grok-web-bridge.log`

## Why this path

- STRUCTURE.md designates `data/` for tracked reference data
- Sparse-checkout friendly; single monorepo source of truth
- Densify/Ralph already publish operator feeds into the plant deck

## Next for web side

Package past high-value web content as `web-export:` commits into this folder.
Local side will pick them up on the next densify/Ralph beat.
