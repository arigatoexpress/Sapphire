---
source: grok-web
date: 2026-08-06
type: ops
topics: [bridge, densify, ralph, monorepo-tools]
title: Grok bridge monorepo tools + Claude plant checklist
---

# Grok bridge lane — monorepo tools (for Claude densify)

## Shipped on main (this session)

| Path | Role |
|---|---|
| `scripts/ops/sync_grok_web_exports.sh` | Canonical sync → `~/Knowledge/0-Inbox/grok-web/` |
| `scripts/ops/grok_bridge_status.py` | Inventory + frontmatter + MANIFEST |
| `tests/unit/test_grok_bridge_status.py` | Unit tests |
| `data/grok-web-exports/MANIFEST.json` | Machine index |
| `docs/handoffs/GROK-BRIDGE-LANE-STATUS-2026-08-06.md` | Coordination |

## Plant wire (Claude)

```bash
# Preferred wrapper body for ops-state finish-line script:
#!/usr/bin/env bash
exec bash "$HOME/Code/Sapphire/scripts/ops/sync_grok_web_exports.sh" "$@"
```

Then schedule densify/Ralph to call the wrapper with `--pull` on a 15–60m beat.

## Verify

```bash
python3 ~/Code/Sapphire/scripts/ops/grok_bridge_status.py
bash ~/ops-state/finish-line/scripts/sync_grok_web_exports.sh --dry-run
```

Fences unchanged: no live trading, no Hermes send, no secrets, no `git add -A`.
