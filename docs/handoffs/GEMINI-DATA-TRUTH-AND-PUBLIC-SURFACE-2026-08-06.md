# Gemini — Data truth + public trading surface (with Phase 3)

**Paste after or with Phase 3 masterplan.**  
**Date:** 2026-08-06  

You already own website + GCP. This adds the **data honesty / density** mission.

Read first (Sapphire monorepo):

```text
docs/strategy/PUBLIC-TRADING-DATA-TRUTH-2026-08-06.md
docs/handoffs/GEMINI-PHASE3-WEBSITE-GCP-MASTERPLAN-2026-08-06.md
lib/grok/public_surface.py
```

Run:

```bash
cd $SAPPHIRE_DIR && git pull --ff-only
python3 scripts/ops/public_surface_audit.py --base https://sapphirealpha.xyz \
  --write /tmp/public-surface-audit.json
```

## Diagnosis you must accept (do not “fix” by inventing numbers)

1. `/api/v1/live` is **live and rich** (machine room, agents, markets epm, events).  
2. `desk.*` is **stale/unknown** — plant publisher problem; UI must label **stale / not observed**.  
3. `/api/v1/widgets` gate **unavailable** on Cloud Run is **expected** without signed gate projection.  
4. Wallet **withheld** is intentional.  
5. Never display fake balances, synthetic PnL, or “markets are up.”

## Your implementation jobs (dashboard repo)

### A. Mission Control data hierarchy (P0 UI)

Render, in order of trust:

1. **Live pulse** from `/api/v1/live`: summary, markets.events_per_min, feed_age, agents states, recent events  
2. **Desk block** only if fresh; if `desk.updated_at` old or posture unknown → big **STALE / NOT OBSERVED** banner — do not hide and do not zero-fill  
3. **MOSS** bands from `/api/v1/moss`  
4. **Operating rules** panel — static public rules (dens symbols, L2 ≤$10, AXTI 2×/−40%, day caps). Source: bake from Sapphire `lib.grok.public_surface.public_operating_rules()` JSON committed into dashboard `shared/` or fetch a static export you add under `web/public/operating-rules.json` generated in build from monorepo copy  
5. Widgets research clips only when non-empty  

### B. Copy / honesty (P0)

| Bad | Good |
|---|---|
| Blank panels | “Not observed” / “Stale since {time}” |
| $0 because missing | Never show $0 for missing |
| “Free-reign working” as profit | “Process healthy — not a fill” |
| Unavailable gate as system death | “Pause files not on public edge (fail-closed)” |

### C. Evidence Observatory (P1)

- Architecture proof using live node health counts (observed).  
- Link Mission Control.  
- Show operating rules strip.  
- No fake KPI tiles.

### D. Optional API (P1)

Add `GET /api/v1/operating-rules` serving the public rules JSON (static file in image) so MC and marketing share one source. **No secrets. No plant file reads.**

### E. Out of scope

- Fixing Mac telemetry publisher desk fields (Claude plant)  
- Executor reload / free-reign money  
- Showing exact RH positions  

## Done when

- [ ] Audit still may show DESK_STALE (plant) but UI **explains** it  
- [ ] Markets epm + agents + events visible on MC  
- [ ] Operating rules visible  
- [ ] No invented PnL  
- [ ] Session note + densify export on Sapphire: `gemini-data-truth-*.md`  
- [ ] Dashboard commits with explicit paths  

## Ultra-short

```text
Data truth: docs/handoffs/GEMINI-DATA-TRUTH-AND-PUBLIC-SURFACE-2026-08-06.md
Live is rich; desk/widgets sparse by architecture. UI must show live pulse +
honest stale + public operating rules. Never invent trading PnL. No plant money paths.
```
