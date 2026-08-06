## Claude prompts (while Gemini deploys)

Paste-ready: [`docs/handoffs/CLAUDE-PLANT-PROMPTS-2026-08-06.md`](../../docs/handoffs/CLAUDE-PLANT-PROMPTS-2026-08-06.md)

# What next (2026-08-06 — post free-reign gate + dashboard fix)

## Just completed (monorepo + dashboard code)

| Item | Status |
|---|---|
| Free-reign `gate_order` | **main** Sapphire `570b9e6` |
| Genome `record_closed_trade` | **main** |
| Dashboard SPA asset fix | **main** dashboard `5ed4058` — **needs Cloud Run deploy** |
| System streamline 6/6 | green |

## Immediate parallel

1. **Gemini Cloud Shell** — pull dashboard `5ed4058`, build, **`--no-traffic` tag deploy**, verify `/dashboard/assets/*.js` is `application/javascript`, then owner traffic shift.  
2. **Claude plant** — import `gate_order` in free-reign sole-writer path per `PLANT_WIRE_POLICY.md`; `record_closed_trade` on closes.  
3. **Win P0** — post-boot acceptance before ARM.  
4. **GCP cost** — still do min-instances / Vertex idle inventory when free.

## Commands

```bash
# Sapphire
make grok-streamline && make grok-loop
python3 scripts/ops/grok_paper_proposal_smoke.py

# Dashboard (Cloud Shell)
cd ~/sapphire-alpha-dashboard && git pull
# follow deploy.sh / cloudbuild with --no-traffic first
```
