# Grok project steering loop

This is the **recurring loop** for Grok chat turns (and optional plant cron).

## Every turn (this chat)

1. `git pull --ff-only` on Sapphire (or fetch latest).
2. Run `python3 scripts/ops/grok_loop_tick.py --write`.
3. Read `projects/grok/TASKBOARD.md` → **Next actions**.
4. Execute the highest-priority item that **does not thrash Claude plant work**.
5. Push web-exports / code with explicit paths.
6. Re-tick so the board reflects new signals.

## Signal sources

| Signal | True when |
|---|---|
| `monorepo_bridge_tools_ok` | sync + status scripts exist |
| `bridge_local_export_seen` | git log has recent `local-export:` from plant |
| `policy_tests_ok` | policy unit tests import + evaluate dens/AXTI |
| `genome_seeded` | seed lessons file has AXTI + dens |
| `windows_module_ok` | acceptance eval loads |
| `research_validator_ok` | good manifest ok / bad fails |
| `automations_catalog_ok` | AUTOMATIONS.md + automations.py present |

## Priority when Claude owns plant

1. Monorepo pure modules & tests  
2. Docs / exports / taskboard  
3. **Do not** edit `ops-state` LaunchAgents Claude is debugging  
4. When plant receipt lands → mark bridge done → pick `T-wire-policy-plant`

## Cron (optional, plant)

```bash
# every 30m — status only
*/30 * * * * cd ~/Code/Sapphire && python3 scripts/ops/grok_loop_tick.py --write >>~/ops-state/logs/grok-loop.log 2>&1
```
