---
source: grok-web
date: 2026-08-08
type: architecture
topics: [genome, broker, plant-outcomes, BS-GENOME-BROKER-PX, learning]
title: Genome broker-reconcile contract — upgrade auto_estimate → broker
---

# Genome broker-reconcile contract

**Date:** 2026-08-08  
**Blindspot:** BS-GENOME-BROKER-PX  
**Status:** Monorepo contract ready; plant upgrade blocked until RH session healthy  
**Non-colliding:** pure learning telemetry — no free-reign / L2 ARM / money paths

## Current plant truth (from 2026-08-06 local-export)

`executor.py::_record_skin_fill` on full lot close calls:

```text
lib.grok.plant_outcomes.record_closed_trade(
  ...,
  realized_pnl_usd = (exit_price - entry_price) * qty_closed,  # snapshot prices
  source = "auto_estimate",
)
```

Honest: notional bookkeeping against `memes-state.json` snapshot prices, **not**
broker-confirmed fills. Slippage / partials / fees not captured.

## Source taxonomy (canonical)

| source | Meaning | Trust for learning |
|---|---|---|
| `broker` | Realized PnL from broker/on-chain **confirmed** fill prices | High |
| `auto_estimate` | Plant snapshot / notional estimate | Medium — provisional |
| `axti` / `dens` / `manual` / `paper` | Seeded or research lessons | Context-specific |

Rules:
1. Prefer **one lesson per `trade_id`**. If a later `broker` row arrives for the same id, **replace or supersede** the `auto_estimate` row (do not double-count wins/losses).
2. `record_closed_trade` remains **fail-open** on the fill path — lesson write never blocks money.
3. Never invent PnL. If broker prices missing, keep `auto_estimate` or skip.

## Monorepo API (already present)

```python
from lib.grok.plant_outcomes import record_closed_trade

record_closed_trade(
    book_path,                    # e.g. Path("~/ops-state/genome/lessons.json")
    trade_id="rh-...",
    symbol="AXTI",
    rail="rh_agentic",            # rh_agentic | rh_l2 | moss | paper | hyperliquid
    realized_pnl_usd=175.0,       # REQUIRED when known
    thesis="...",
    tags=["options-first", "scale-out"],
    source="broker",              # ← upgrade target
    meta={
        "entry_price": 0.70,
        "exit_price": 2.25,
        "qty": 1,
        "instrument": "option",
        "multiplier": 100,        # equity options
        "fees_usd": 0.0,
        "fill_ids": ["..."],
        "reconcile": "rh_mcp",    # rh_mcp | onchain | skin_book
    },
)
```

Helpers added 2026-08-08:
- `lib.grok.genome.SOURCE_*` constants
- `lib.grok.genome.realized_pnl_long(...)` pure helper for long equity/premium
- `lib.grok.plant_outcomes.record_closed_trade` validates source ∈ taxonomy

## Plant upgrade plan (after RH re-auth)

### Phase A — RH Agentic options / equities
1. On full close, if RH MCP / pnl hub has confirmed fill prices, compute:
   - options: `(exit_prem - entry_prem) * multiplier * contracts - fees`
   - equity: `(exit - entry) * shares - fees`
2. Call `record_closed_trade(..., source="broker", meta={...})`.
3. If MCP unavailable, keep `auto_estimate` path unchanged.

### Phase B — L2 / chain
1. Prefer on-chain fill receipt / explorer price over memes-state mid.
2. Tag `meta.reconcile="onchain"`.

### Phase C — Dedupe
1. Before append, if `lesson-{trade_id}` exists with `source=auto_estimate` and new source is `broker`, replace that lesson in-place.
2. Summary wins/losses recompute from remaining lessons only.

### Tests (plant)
- Full close with broker prices → `source=broker`, correct PnL
- Full close without broker → still `auto_estimate`
- Broker supersedes estimate for same trade_id (no double count)
- `record_closed_trade` exception still never breaks fill

## Success criteria

- [ ] At least one live RH full-close writes `source=broker` with fees-aware PnL
- [ ] LessonBook summary matches broker PnL hub for that trade within $0.01
- [ ] auto_estimate path still works offline
- [ ] BS-GENOME-BROKER-PX → `partial` then `resolved_plant`

## Out of scope

- Champion/challenger ladder (BS-CHAMPION)
- Live order placement / L2 ARM
- Changing free-reign gate_order

## Related

- `lib/grok/genome.py`, `lib/grok/plant_outcomes.py`
- `data/grok-web-exports/2026-08-06_local-export_genome-closes-wired.md`
- AXTI playbook: half at ~2×, SL −40% (`lib/grok/playbooks.py` axti_options)
