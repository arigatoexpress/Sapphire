---
source: grok-web
date: 2026-08-08
type: handoff
topics: [x-twitter, brand-reset, browser, playwright, plant-dispatch, new-chapter]
title: P0 — Deactivate @rariwrldd + @0guard_ via browser (no X API)
priority: P0
requires_human: true
money: false
free_reign: false
---

# P0 DISPATCH — X account teardown (new chapter)

**From:** Grok web (SuperGrok) → Sapphire grok-bridge  
**For:** Claude Code / Codex / Grok CLI on **Mac plant** (headed browser)  
**Operator:** Ari (password + 2FA when prompted)  
**Constraint:** **No X API.** Browser only.  
**Money rails:** do **not** touch free-reign, RH, L2, MOSS.

## Intent (operator words)

> Accounts are cooked. Nuclear cleanup. Start a new chapter.  
> Prefer **deactivate/delete whole accounts** over endless post deletes.

## Targets

| Handle | Action |
|---|---|
| `@rariwrldd` (0xRari) | Deactivate account |
| `@0guard_` | Deactivate account |

Optional pre-clean (only if deactivate blocked): delete posts in  
`data/grok-web-exports/x-nuke-nuclear-list.json` (22 curated IDs).

## Success criteria

1. Both profiles show deactivated / login fails as active public identity  
2. Direct links to worst posts 404 or unreachable as live posts  
3. Receipt written: `~/ops-state/agent-reports/X-TEARDOWN-RECEIPT-2026-08-08.md`  
4. Mirror receipt → `data/grok-web-exports/2026-08-08_x-teardown-receipt.md` with commit  
   `local-export: X teardown receipt [2026-08-08]`

## Plant boot (Mac)

```bash
cd ~/Code/Sapphire || cd ~/Sapphire
git pull origin main
bash scripts/ops/sync_grok_web_exports.sh --pull 2>/dev/null || true
# read this file:
less data/grok-web-exports/2026-08-08_x-account-teardown-dispatch.md
less docs/handoffs/X-ACCOUNT-TEARDOWN-BROWSER-2026-08-08.md
```

## Execute path A — semi-auto Playwright (preferred)

```bash
cd ~/Code/Sapphire || cd ~/Sapphire
# deps if needed
python3 -m pip install --user playwright
python3 -m playwright install chromium

# Headed browser; Ari logs in once per account when script pauses
python3 scripts/ops/x_account_teardown_playwright.py --account rariwrldd
python3 scripts/ops/x_account_teardown_playwright.py --account 0guard_
```

Script opens X settings → Deactivate flow. **Human confirms** final deactivate click if UI demands it.

## Execute path B — agent + browser tools (Claude/Codex)

1. Open headed Chromium/Chrome with user profile if available  
2. Navigate `https://x.com/i/flow/login` — Ari completes login + 2FA  
3. Go to `https://x.com/settings/deactivate` (or Settings → Your account → Deactivate)  
4. Complete deactivation for `@rariwrldd`  
5. Log out / switch to `@0guard_` → repeat  
6. Write receipt

## Execute path C — pure manual (5 min)

1. Phone or Mac browser logged in as `@rariwrldd`  
2. Settings → Your account → **Deactivate your account** → confirm  
3. Switch to `@0guard_` → same  
4. Done

## Hard fences

- Do **not** use free-reign, trading bots, or Hermes outward messaging  
- Do **not** post new dunks "one last time"  
- Do **not** delete GitHub repos or Sapphire plant as part of this task  
- Do **not** burn email if it is recovery for other systems — only X accounts  
- If 2FA phone needed: **stop and ping Ari** — do not invent bypasses

## After teardown (new chapter seeds — do not block deactivation)

- Ops-AI-Library + Sapphire stay on GitHub (`arigatoexpress`)  
- Public X presence = **none** until a clean builder handle is created later  
- Knowledge Forge v1.0 still applies: external surplus, not hate accounts  

## Kill criteria for this mission

- If Ari revokes consent mid-flow → stop, leave accounts as-is, write partial receipt  
- If X UI changed and path unknown → fall back to Path C with Ari driving clicks  

## Paste-ready agent prompt (Claude / Codex / Grok CLI)

```
You are on Ari's Mac plant. P0 non-money task.

Read:
- data/grok-web-exports/2026-08-08_x-account-teardown-dispatch.md
- docs/handoffs/X-ACCOUNT-TEARDOWN-BROWSER-2026-08-08.md
- scripts/ops/x_account_teardown_playwright.py

Goal: Deactivate X accounts @rariwrldd and @0guard_ via browser (no X API).
Use headed Playwright or browser tools. Pause for Ari on password/2FA/final confirm.
Write receipt to ~/ops-state/agent-reports/X-TEARDOWN-RECEIPT-2026-08-08.md
Do not touch trading rails, free-reign, or GitHub deletions.
Execute now.
```
