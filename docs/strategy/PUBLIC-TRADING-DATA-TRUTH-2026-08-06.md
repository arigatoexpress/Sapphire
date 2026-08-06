# Public trading data truth — why the site looks empty / wrong

**Date:** 2026-08-06  
**Live probe:** sapphirealpha.xyz revision `00092-haw`

---

## 1) The paradox

| Surface | Reality |
|---|---|
| `/api/v1/live` | **Rich** (~8KB): 10 nodes, 6 agents, markets feed ~615 epm, 12 events, status=live |
| `/api/v1/widgets` | **Sparse**: gate unavailable, wallet withheld, research clips=[], signals=[] |
| `/api/v1/transparency` | **Empty** ledger |
| UI feel | “No trading data” / scarce / maybe wrong |

So we are **not** “disconnected from the plant.” We are **showing the wrong layer** and **under-publishing desk intelligence**.

---

## 2) Root causes (ranked)

### P0 — Desk block is stale / null-filled

Live `desk.updated_at` was **~11h older** than `observed_at` in probe:

- `posture`, `execution`, `risk.*`, `epistemics.thesis`, `decisions.*` → `unknown` / null  
- UI correctly refuses to invent numbers → **looks empty**  
- Markets still show high `events_per_min` while `decision_gate`/`execution` unknown → **feels inaccurate**

**Fix owner:** plant telemetry publisher (Mac/Win collectors) must refresh **desk** every cycle with real sovereign-desk fields — or mark desk `stale` explicitly so UI labels “stale”, not silence.

### P0 — Widgets path cannot see ops-state on Cloud Run

`gate`, pause files, skin book, local research files are **plant filesystem** sources.  
Public Cloud Run is `PUBLIC_READ_ONLY` with **no** `~/ops-state` → `gate.state=unavailable` is **correct fail-closed**, not a random bug.

**Fix:** publish gate/pause as **signed fields inside live telemetry** (or a dedicated signed projection), not via local file reads on the server.

### P1 — Wallet/positions withheld (intentional)

`wallet.disclosure=withheld` is **policy**, not missing code.  
Public must never show exact balances/positions. Use **bands** (MOSS already does USDm $100–$249).

### P1 — Research clips empty

Widgets research requires an admitted public research cycle. Empty clips → no conjecture published to public path today.

### P1 — UI under-uses live richness

Frontend has excellent honesty (`not observed` doctrine) but operator-visible trading story is dominated by empty widgets gate/research rather than:

- markets.events_per_min  
- agents (free-reign-easy working, moss offline, …)  
- events timeline  
- MOSS bands  
- **static operating rules** (dens, L2 $10, AXTI) from monorepo  

### P2 — Transparency ledger empty on cloud

No explanations.jsonl outcomes projected → transparency pane zero.

### Info — Capability route active ≠ fills

Agent cards saying “Capability route active” are **process health**, not “we are printing money.” Label accordingly or users read false alpha.

---

## 3) What “best in world” looks like (honest)

```text
PUBLIC SITE
  ├── Machine room (live telemetry) — nodes/agents/events  [WORKS]
  ├── Markets pulse — epm, feed age, status                 [PARTIAL]
  ├── Desk intelligence — posture, regime, safety floor     [STALE → FIX]
  ├── Operating rules — dens/L2/AXTI/day caps (static)      [SHIP from monorepo]
  ├── MOSS bands — capital band only                        [WORKS]
  ├── Research clips — when published                       [EMPTY]
  └── NEVER: wallets, exact PnL, positions, order ids
```

Plant private / operator auth can show more later; public stays fail-closed.

---

## 4) Split of work

| Owner | Work |
|---|---|
| **Gemini** | UI: prioritize live desk/markets/events; honest stale labels; render public operating rules; empty-state craft; MC paint |
| **Plant Claude** | Refresh desk in telemetry publisher; research cycle; gate projection; executor reload when quota up |
| **Grok monorepo** | `public_surface` rules + audit script + this doc + Gemini data-truth prompt |
| **Never** | Fake KPIs, invent PnL, leak wallets |

---

## 5) Verify anytime

```bash
python3 scripts/ops/public_surface_audit.py --base https://sapphirealpha.xyz
curl -sS https://sapphirealpha.xyz/api/v1/live | python3 -m json.tool | head
curl -sS https://sapphirealpha.xyz/api/v1/widgets | python3 -m json.tool | head
```

P0 clear when: desk.updated_at within publisher SLA, posture≠unknown OR explicit stale, UI shows pulse without implying false fills.
