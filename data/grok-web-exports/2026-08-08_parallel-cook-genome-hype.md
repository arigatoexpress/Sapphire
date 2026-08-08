---
source: grok-web
date: 2026-08-08
type: status
topics: [parallel, genome, HYPE, LIT, monorepo]
title: Parallel cook — genome broker contract + HYPE/LIT refresh
---

# Parallel cook receipt (non-colliding with plant RH re-auth)

**Seat:** Grok web monorepo  
**Plant seat:** Grok CLI (RH re-auth / bridge LaunchAgent / Tailscale)

## Shipped this pass

| Artifact | Commit theme |
|---|---|
| `data/grok-web-exports/2026-08-08_hype-lit-unlock-refresh.md` | TH-02/TH-03 calendar re-run; no size-up |
| `data/grok-web-exports/2026-08-08_genome-broker-reconcile-contract.md` | Plant upgrade plan auto_estimate → broker |
| `lib/grok/genome.py` | Source taxonomy, `realized_pnl_long`, broker supersedes estimate |
| `lib/grok/plant_outcomes.py` | `record_long_close_from_fills` helper |
| `lib/grok/blindspots.py` | BS-GENOME-BROKER-PX → encoded; BS-HYPE-LIT → research_refresh |

## Extracted from older research (still valid)

- AXTI playbook: defined-risk, half @ ~2×, SL −40%, never hold to worthless (in genome seed + playbooks)
- TG dual surface: position cards with one-tap TP/SL still open P1 after fleet green
- Thesis filter from Mark Walter loop redesign still governs opportunity scoring
- Knowledge embed integrity (AU-KNOW) still blocked — untouched this pass

## Still plant-only (do not touch from web)

- RH pickle re-auth / schtasks
- Live desk publisher cycle
- LaunchAgent load / Tailscale Serve apply

## Next monorepo options

1. AXTI automated scale-out risk loop design (TP half / trail / −40% SL) for free-reign manage path
2. TG position-card schema (BonkBot-class) — design only until RH green
3. Public signed gate projection for Cloud Run widgets.gate
