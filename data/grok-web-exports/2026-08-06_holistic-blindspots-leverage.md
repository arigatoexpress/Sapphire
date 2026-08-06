---
source: grok-web
date: 2026-08-06
type: research
topics: [blindspots, trading, ta, onchain, gcp, playbooks]
title: Holistic blindspots + trading/TA/onchain + GCP leverage
---

# Holistic research dump (Mac rest / Gemini cook)

**Canonical strategy doc:**  
`docs/strategy/HOLISTIC-BLINDSPOTS-AND-LEVERAGE-2026-08-06.md`

**Code:**
- `lib/grok/blindspots.py` — P0–P2 registry
- `lib/grok/playbooks.py` — AXTI, L2, MOSS, HL, regime RSI, TV spine, late-cycle
- `lib/grok/policy.py` — DAY_LOSS_HALT, OPTIONS_DAY_CAP, AXTI_DTE, HL_SIGNING_GATE, REGIME_BLOCK_L2

**Plant (when clean):** wire GateRequest fields  
`day_realized_pnl_usd`, `day_options_premium_usd`, `dte_days`, `regime`, `hyperliquid_signing_gate_armed`

**GCP top 3:** deploy SPA fix · min-instances 0 · BQ paper outcomes batch
