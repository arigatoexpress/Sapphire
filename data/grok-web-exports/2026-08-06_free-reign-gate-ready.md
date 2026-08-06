---
source: grok-web
date: 2026-08-06
type: ops
topics: [free-reign, policy, plant-wire, genome]
title: Free-reign gate ready for plant sole-writer
---

# Free-reign gate ready (Claude plant)

Monorepo now has a sole-writer pre-check:

```python
from lib.grok.free_reign_gate import GateRequest, gate_order
from lib.grok.plant_outcomes import record_closed_trade
```

Docs: `projects/grok/PLANT_WIRE_POLICY.md`  
Smoke: `python3 scripts/ops/grok_paper_proposal_smoke.py`  
Streamline: `make grok-streamline`

## Wire checklist

1. Import `gate_order` in free-reign / easy_mode / rh-chain decision path  
2. Deny when `not result.allowed` (log code)  
3. On closed trades call `record_closed_trade`  
4. Do not ARM L2 until Win P0 green  

## Dashboard

Parallel fix in `sapphire-alpha-dashboard`: Vite `base: '/dashboard/'` + serve real static under `/dashboard/{path}` so Mission Control JS is not HTML 404.
