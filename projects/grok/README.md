# Grok Project — Sapphire

**Dedicated home for everything Grok owns in the Sapphire monorepo:** knowledge bridge, paper policy kernel, genome seeds, Windows DC acceptance, research-worker invariants, automation catalog, and the steering loop.

| | |
|---|---|
| **Mission** | Windows private DC + agent harnesses that earn / publish / self-improve |
| **Code** | [`lib/grok/`](../../lib/grok/) |
| **Data** | [`data/`](./data/) · fixtures in [`fixtures/`](./fixtures/) |
| **Bridge store** | [`data/grok-web-exports/`](../../data/grok-web-exports/) |
| **Loop** | [`LOOP.md`](./LOOP.md) · `python3 scripts/ops/grok_loop_tick.py` |
| **Taskboard** | [`TASKBOARD.md`](./TASKBOARD.md) (generated) · `data/taskboard.json` |
| **Automations** | [`AUTOMATIONS.md`](./AUTOMATIONS.md) |

## Quick commands

```bash
# Full project status (bridge + policy + win + genome + board)
python3 scripts/ops/grok_project_status.py

# Steering tick — updates TASKBOARD from signals
python3 scripts/ops/grok_loop_tick.py
python3 scripts/ops/grok_loop_tick.py --write

# Bridge only
python3 scripts/ops/grok_bridge_status.py --write-manifest
bash scripts/ops/sync_grok_web_exports.sh --dry-run

# Unit tests (policy / genome / research / windows / loop / bridge)
python3 -m pytest tests/unit/test_grok_*.py -q
```

## Layout

```text
projects/grok/          ← you are here (hub)
lib/grok/               ← pure Python (no broker I/O)
  policy.py             dens + free-reign multi-rail + AXTI scale-out
  genome.py             lessons + seed from AXTI/dens
  research_worker.py    paper_only manifest validator
  windows.py            P0/P1 acceptance (ARM only if P0 green)
  loop.py               taskboard steering
  automations.py        automation inventory
scripts/ops/grok_*.py   status + loop tick + bridge tools
data/grok-web-exports/  git knowledge plane
```

## Fences

- Paper / research / docs / tests: **yes**
- Live orders, THO money, Hermes send, secret dumps: **never from this project alone**
- Plant wires `evaluate_proposal` before sole writer; models still only propose

## Related mission docs

- `docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md`
- `docs/handoffs/GEMINI-CLOUDSHELL-MASTER-PROMPT-2026-08-06.md`
- `docs/handoffs/GROK-BRIDGE-LANE-STATUS-2026-08-06.md`
