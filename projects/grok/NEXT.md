# What next (2026-08-06 — post streamline)

## Streamline status

**Score 6/6** monorepo composition green (`make grok-streamline`).

Alpha ledger ↔ policy fences ↔ genome seeds ↔ automations catalog ↔ bridge exports are **one brief**:

- `projects/grok/SYSTEM_BRIEF.md`
- `data/grok-web-exports/YYYY-MM-DD_system-brief.md`

## Parallel tracks (do not block each other)

| # | Track | Seat | Action |
|---|---|---|---|
| 1 | **Website** | Gemini Cloud Shell | Fix `/dashboard` ~700B shell (prompt already sent) |
| 2 | **Plant policy wire** | Claude / Mac | Follow `PLANT_WIRE_POLICY.md` — `evaluate_proposal` before sole writer |
| 3 | **Genome closes** | Claude / Mac | `LessonBook.append` on broker-reconciled closes |
| 4 | **Win P0** | Desk / Win | Post-boot acceptance before ARM L2 |
| 5 | **GCP cost** | Gemini Cloud Shell | min-instances 0, Vertex idle, BQ freshness |

## Grok chat loop (every turn)

```bash
git pull --ff-only
make grok-streamline    # or python3 scripts/ops/grok_system_streamline.py --write --export --check
make grok-loop
# read projects/grok/SYSTEM_BRIEF.md + TASKBOARD.md
```

## Do not

- Live orders from Cloud Shell / this sandbox  
- ARM L2 before Win P0  
- Thrash Gemini’s website PR surface without need  
