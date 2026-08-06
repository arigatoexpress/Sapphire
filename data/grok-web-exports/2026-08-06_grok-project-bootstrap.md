---
source: grok-web
date: 2026-08-06
type: ops
topics: [grok-project, policy, genome, windows, bridge, loop]
title: Dedicated Grok project bootstrap
---

# Dedicated Grok project — bootstrap

All Grok monorepo work now lives under:

- **Hub:** `projects/grok/`
- **Code:** `lib/grok/` (policy, genome, windows acceptance, research-worker validator, loop, automations)
- **Scripts:** `scripts/ops/grok_*.py` + `sync_grok_web_exports.sh`
- **Bridge store:** `data/grok-web-exports/`
- **Loop:** `python3 scripts/ops/grok_loop_tick.py --write` → `projects/grok/TASKBOARD.md`

## Claude plant

Keep wiring densify to monorepo sync. When green, touch:

```bash
# optional marker Claude can create after plant green
# projects/grok/data/BRIDGE_PLANT_GREEN
```

Or push `local-export:` commit; loop detects recent local-export in git log.

## Fences

Policy kernel is paper-safe evaluate-only. No live orders from Grok project alone.
