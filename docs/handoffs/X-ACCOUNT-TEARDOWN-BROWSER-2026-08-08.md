# X Account Teardown — Browser Runbook (2026-08-08)

**Status:** READY FOR PLANT  
**API:** none  
**Human:** required for login / 2FA / final confirm  

## Why deactivate (not post-nuke only)

Operator decision: accounts are cooked; new chapter.  
Deactivation is faster than deleting dozens of posts and removes the hate-account brand surface.

X typically **deactivates** first (grace period ~30 days) then purges. That is acceptable.

## Accounts

1. `rariwrldd` — https://x.com/rariwrldd  
2. `0guard_` — https://x.com/0guard_  

## UI path (2026 — may shift slightly)

1. Login as target account  
2. More (…) → Settings and privacy  
3. Your account → **Deactivate your account**  
   - Direct attempt: https://x.com/settings/deactivate  
4. Read warnings → Continue → password → Deactivate  
5. Confirm logged out / profile dead  

## Playwright

```bash
python3 scripts/ops/x_account_teardown_playwright.py --account rariwrldd
python3 scripts/ops/x_account_teardown_playwright.py --account 0guard_
```

Uses persistent context dir `~/ops-state/browser/x-teardown-<account>/` so login cookies survive between runs.

## Optional post purge only

If deactivate impossible (e.g. need to keep handle):

```bash
# open curated kill list checklist (no API)
# nuclear list: data/grok-web-exports/x-nuke-nuclear-list.json
```

Priority P0 post on rariwrldd: `2085505182457299251`  
Priority P0 on 0guard_: `2073130190612681204`

## Receipt template

```markdown
# X Teardown Receipt 2026-08-08
- rariwrldd: deactivated | failed | skipped — notes:
- 0guard_: deactivated | failed | skipped — notes:
- method: playwright | manual | agent-browser
- operator present: yes/no
- timestamp UTC:
```
