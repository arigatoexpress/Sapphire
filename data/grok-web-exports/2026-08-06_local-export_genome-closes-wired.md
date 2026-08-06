---
source: local-export
date: 2026-08-06
type: plant-status
topics: [genome, lessons, plant-outcomes, plant-wire, P0-B]
title: local-export: genome closes wired [2026-08-06]
---

# Genome closes wired (P0-B)

Per `docs/handoffs/CLAUDE-CODE-ULTIMATE-DISPATCH-2026-08-06.md` P0-B and
`projects/grok/PLANT_WIRE_POLICY.md`.

## Seeded

`~/ops-state/genome/lessons.json` created via
`LessonBook().seed_axti_and_dens()` — count=2 (AXTI win $175, SONNY/BINGBONG
dens block), matching the documented 2026-08-05 seed lessons exactly.

## Wired

`~/ops-state/telegram-bot/executor.py::_record_skin_fill` — the function that
already records every auto-fill into the skin-book — now calls
`lib.grok.plant_outcomes.record_closed_trade` whenever a SELL **fully closes**
a lot (not a partial reduce), using the entry price stored on the lot at BUY
time and the exit price from the same memes-state snapshot used for the SELL
fill: `realized_pnl_usd = (exit_price - entry_price) * qty_closed`.

**Honesty note on `source`:** the dispatch's example uses `source="broker"`
for a *reconciled* fill price. This executor's fill-tracking is
notional/quantity bookkeeping against `memes-state.json` snapshot prices, not
a true broker-confirmed fill price (real fills can slip). Tagged
`source="auto_estimate"` instead — accurate about what the number actually is.
Upgrading to real `source="broker"` reconciliation is a follow-up, not done
here (would need actual RH/on-chain fill-price data threaded back in, which
this codebase doesn't currently capture).

Fails **open**, opposite direction from the free-reign gate: a lesson-write
failure (import error or `record_closed_trade` exception) is swallowed and
must never affect the fill it's describing — this is best-effort telemetry,
not a safety control. Verified with a dedicated test that forces
`record_closed_trade` to raise and confirms the underlying fill still
succeeds correctly.

## Verified

- `LessonBook.load(~/ops-state/genome/lessons.json).summary()` →
  `{"count": 2, "wins": 1, "losses": 0, "blocked": 1, "realized_pnl_usd": 175.0}`
  immediately after seeding.
- New tests in `test_executor.py` (56/56 passing total):
  - `test_full_close_appends_genome_lesson` — BUY $20 @ $2.00 → SELL $20 @
    $3.00 fully closes the lot → one lesson, `outcome="win"`,
    `realized_pnl_usd=10.0`, `source="auto_estimate"`, `rail="rh_l2"`.
  - `test_partial_close_does_not_log_a_lesson` — a partial reduce (position
    still open) does not write a lesson file at all.
  - `test_genome_logging_failure_never_breaks_the_fill` — forced
    `record_closed_trade` exception; skin-book fill still recorded correctly.

## NOT touched

Free-reign / L2 ARM / money paths untouched — this is pure post-fill
telemetry on data already being written, not a new trading decision path. No
live orders. No secrets.
