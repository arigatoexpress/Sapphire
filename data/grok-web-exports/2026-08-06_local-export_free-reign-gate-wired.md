---
source: local-export
date: 2026-08-06
type: plant-status
topics: [free-reign, gate_order, policy, plant-wire, P0-A]
title: local-export: free-reign gate_order wired
---

# Free-reign gate_order wired (P0-A)

Per `docs/handoffs/CLAUDE-CODE-ULTIMATE-DISPATCH-2026-08-06.md` P0-A and
`projects/grok/PLANT_WIRE_POLICY.md`.

## Sole-writer, found by reading source (not guessed)

Traced the actual order-submission path before touching anything — several
files that looked plausible from names/docs turned out NOT to be it:

- `~/ops-state/rh-chain/rh_orderflow.py` — its own docstring: "READ-ONLY +
  ADVISORY-ONLY by construction... never places an order; there is no order
  path anywhere in this process." Ruled out.
- `~/ops-state/finish-line/scripts/place_agentic_rth.py` — a legacy
  dust-sleeve placer that the current `free_reign_multi_rail` mandate already
  refuses to run (`--dust-legacy` only), and even then only prints
  MCP-call instructions for a human/agent — never submits itself. Ruled out.
- `~/ops-state/telegram-bot/onchain.py` `execute()` — genuinely signs and
  sends the on-chain L2 swap (`Account.sign_transaction` /
  `send_raw_transaction`). Real, but only half the picture (on-chain only).
- `~/ops-state/telegram-bot/executor.py` `process_once()` — **the actual
  unified sole-writer**: single-instance-locked, schtask-driven (`rh-executor`
  on Windows), consumes `decisions.jsonl`, and dispatches to **both**
  `onchain.execute()` (L2) and `brokerage.execute()` (RH Agentic) from one
  choke point. This is where the gate is wired.

## What's wired

`executor.py`:
- New `order_gate_check(p, usd, v, book)` — calls
  `lib.grok.free_reign_gate.gate_order` (imported via `sys.path` injection of
  `SAPPHIRE_DIR`, default `~/Code/Sapphire`). Fails **closed**: if the
  monorepo module can't be imported, in-scope proposals are refused, never
  traded ungated.
- Called in `process_once()` right after `venue.classify()`, before the
  existing "CLAIM the proposal" / dispatch-to-`try_onchain`-or-`brokerage`
  block — i.e. strictly before any sole-writer submit, on both rails.
- Denial recorded exactly like the pre-existing `order_allowed` veto pattern:
  `state["consumed"][pid] = {"outcome": f"gate-denied: {code}", ...}`, a
  Telegram "🛡 GATE DENIED" message, never retried.

## Scope decision (the one real judgment call — documented, not silent)

Initial wire applied the gate to **every** proposal reaching the executor and
broke 10 of 46 existing tests — all using the suite's default `MSTR:USD`
equity BUY fixture, refused under `OPTIONS_FIRST`. Investigating *why*
revealed `executor.py` is shared by two different authorization lanes funneled
into the same `decisions.jsonl` "approved" queue:

1. **Human Telegram approval** — `executor.py`'s own docstring: *"Telegram is
   the ONLY gate."* A person reviewed and clicked Approve.
2. **Free-reign auto-approval** — `free_reign.py:530` calls
   `decisions.decide(pid, "approved", chat_id="free-reign-policy",
   via="free_reign", ...)` with no human in the loop.

The free-reign multi-rail policy (dens/dust/options-first/caps) is the
**autonomous-lane** policy — CLAUDE.md's trading carve-out is explicitly about
agent autonomy, not about overriding a human's own Telegram approval. So the
gate is scoped to `via == "free_reign"` only (threaded through
`approved_trades()` as an internal `p["_via"]` marker). A human's approved
`MSTR:USD` buy is untouched; the identical instrument submitted via free-reign
now correctly hits `OPTIONS_FIRST`.

**This is the one decision in this wire that's a judgment call rather than a
mechanical fact** — flagging it explicitly for Ari to correct if the intent
was actually to gate *all* auto-executor trades regardless of approval origin.

## Verified

- `python3 scripts/ops/grok_paper_proposal_smoke.py` → 7/7 expected
  codes (DENS_BLOCK, DUST_NO_REBUY, L2_NOTIONAL_CAP, MOSS_GRANT, 3× ALLOW).
- `test_executor.py`: 56/56 passing — 46 pre-existing (all still green,
  confirming human-approval lane is untouched) + 10 new, covering:
  `DENS_BLOCK`, `DUST_NO_REBUY`, `OPTIONS_FIRST`, `L2_NOTIONAL_CAP` denials on
  the free-reign lane; an in-cap free-reign L2 buy passing the gate and
  reaching `onchain.execute` (mocked); a human-approved dens-symbol trade
  confirmed NOT gate-denied (scope proof); and fail-closed behavior when the
  gate module can't be imported.
- Bridge (`:19998/health`) and `grok_bridge_status.py --check` both still
  green — untouched by this work.

## NOT touched (hard fences honored)

- `~/ops-state/rh-chain/rh_orderflow.py` / `rh_rpc_guard.py` — live processes,
  never restarted or killed.
- No L2 schtask ARM, no Windows `launchctl`/`schtasks` action. This is a
  **source edit on the Mac's copy** of `executor.py`; the live Windows
  `rh-executor` schtask runs its own copy and will not see this change until
  Ari (or a separate, explicitly-scoped sync step) deploys it there — that
  deploy is intentionally out of scope for this session (P2 fence: "probes
  only, NO L2 ARM").
- No live orders placed. No secrets read, printed, or touched (wallet
  key/RH session live only in `wallet-config.json`/`robin_stocks` pickle,
  neither opened).
- Free-reign mandate values (dens list, caps, MOSS gate) — read only, never
  edited; `lib.grok.policy` remains sole source of truth as instructed.

## Known follow-up (not done, don't assume it)

- `day_realized_pnl_usd` / `day_options_premium_usd` are not yet threaded from
  the skin-book into `GateRequest` — `DAY_LOSS_HALT`/`OPTIONS_DAY_CAP` exist in
  policy but are inert from this call site until wired (matches the
  `TR-PRESERVE` blindspot already tracked in
  `docs/strategy/HOLISTIC-BLINDSPOTS-AND-LEVERAGE-2026-08-06.md`).
- `regime` / `signal_source_count` / `hyperliquid_signing_gate_armed` /
  `dte_days` / `has_catalyst_tag` are left at safe defaults for the same
  reason — the plant doesn't have that telemetry on the proposal object yet.
- This executor never classifies an `asset_class="option"` proposal (options
  flow through a separate manual/agent RH-MCP path per `TR-AXTI`), so
  `AXTI_DEFINED_RISK`/`AXTI_DTE` never fire from here today — expected, not a
  bug.
