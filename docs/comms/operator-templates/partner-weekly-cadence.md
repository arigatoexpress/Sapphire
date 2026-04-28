---
name: Partner weekly cadence — Monday morning rollup
audience: Private partner group
when_to_use: Monday morning every week. Summarizes what shipped in the business app last week + what's planned this week. Mirrors the dev_pulse plugin tool's structure.
placeholders: ["{{operator_name}}", "{{business_app_name}}", "{{week_of}}", "{{cloud_run_revision}}", "{{customer_count}}", "{{shipped_bullets}}", "{{planned_bullets}}", "{{blocked_bullets}}", "{{questions_for_partners}}"]
last_updated: 2026-04-28
provenance_sha: baeedc4f
---

# {{business_app_name}} weekly — week of {{week_of}}

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

—{{operator_name}}

## Notes for the operator (NOT in the sent message)

- Why this works: mirrors the operator's own dev_pulse tool's mental model (shipped / planned / blocked / questions), sets a one-line tone of "push back if wrong" that invites correction without demanding it. Partner-business voice — warm but specific.
- Common edits:
  - The {{shipped_bullets}} should be 3-5 bullets max. If you can't fill 3, write "quiet week, no major shipped items" and explain why.
  - The {{questions_for_partners}} section is the highest-leverage. Use it for concrete owner-and-choice questions, not status updates phrased as questions.
- Tone calibration: this is partner mail. Warmer than corp-dev mail. First-person plural ("we") is fine for business topics; first-person singular ("I") for code/deployment topics — keep the boundary clear.
- Pull data from `dev_pulse` tool output if available; don't reconstruct from memory. Hardcoding stale customer counts in a partner email is a credibility leak.
