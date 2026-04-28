---
name: THO weekly cadence — Monday morning rollup to Celeste, Mark, Ben
audience: Celeste (mom / founding partner), Mark Willcott, Ben — THO partners
when_to_use: Monday morning every week. Summarizes what shipped in Project-Go-Forward last week + what's planned this week. Mirrors the dev_pulse plugin tool's structure.
placeholders: ["{{week_of}}", "{{cloud_run_revision}}", "{{customer_count}}", "{{shipped_bullets}}", "{{planned_bullets}}", "{{blocked_bullets}}", "{{questions_for_partners}}"]
last_updated: 2026-04-29
provenance_sha: 1bcf221a
---

# THO weekly — week of {{week_of}}

Hey all,

Quick rollup so everyone's on the same page heading into the week.

## What shipped last week

{{shipped_bullets}}

(Cloud Run is on revision {{cloud_run_revision}}. Customer count: {{customer_count}}.)

## What's planned this week

{{planned_bullets}}

## What's blocked / needs you

{{blocked_bullets}}

## Questions for the partners

{{questions_for_partners}}

If anything in here is wrong or surprising, please push back — I'd rather know on Monday than Friday.

—Ari

## Notes for the operator (NOT in the sent message)

- Why this works: mirrors the operator's own dev_pulse tool's mental model (shipped / planned / blocked / questions), sets a one-line tone of "push back if wrong" that invites correction without demanding it. Family-business voice — warm but specific.
- Common edits:
  - The {{shipped_bullets}} should be 3-5 bullets max. If you can't fill 3, write "quiet week, no major shipped items" and explain why.
  - The {{questions_for_partners}} section is the highest-leverage. Use it for things like "Mark — should we default to 'all manufacturers' for the floorplan page?" not status updates phrased as questions.
- Tone calibration: this is family + partners. Warmer than corp-dev mail. First-person plural ("we") is fine for THO topics; first-person singular ("I") for code/Cloud Run topics — keep the boundary clear.
- Pull data from `dev_pulse` tool output if available; don't reconstruct from memory. Hardcoding stale customer counts in a partner email is a credibility leak.
