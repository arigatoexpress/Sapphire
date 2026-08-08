# X Nuclear Delete Toolkit

Automates as much of the **nuclear** brand cleanup as X allows from outside the official app.

## Hard limit

Grok **cannot** delete posts for you. X requires **your** OAuth user tokens (or manual clicks).  
This toolkit is the max automation path:

| Path | Automation | Needs |
|---|---|---|
| `nuke.py --execute` | Full auto delete of listed IDs | X API app with **Read+Write** + user tokens |
| `nuke.py --scan --execute` | Timeline pull → pattern score → delete | Same |
| `open-checklist.html` | One-click open-all links | Browser logged into X |
| Manual ⋯ → Delete | Zero setup | Phone/desktop |

> X write API is **not free** on most tiers (Basic+). If you get `403` / `402`, use the checklist path.

## 60-second start

```bash
cd x-nuke
cp .env.example .env
# fill X_RARI_* keys for @rariwrldd
# fill X_0GUARD_* keys for @0guard_ (if separate account)

# 1) Always dry-run first
python3 nuke.py

# 2) Optional: pull more posts + auto-score hate patterns
python3 nuke.py --scan

# 3) Nuclear delete curated list (P0+P1+P2)
python3 nuke.py --execute

# Only P0+P1:
python3 nuke.py --priority P0,P1 --execute

# One account:
python3 nuke.py --account rariwrldd --execute
python3 nuke.py --account 0guard_ --execute

# No API? generate checklist and open in browser
python3 nuke.py --checklist
open open-checklist.html   # or double-click
```

## Get X API credentials

1. Go to [developer.x.com](https://developer.x.com/)
2. Create a Project + App
3. **User authentication** settings: Read **and Write**
4. Callback can be `http://127.0.0.1` (not used for pin-based if you generate tokens in portal)
5. Keys and tokens → generate:
   - API Key + Secret  
   - Access Token + Secret **for each account** you control  
6. Paste into `.env` (never commit)

For a second account (`@0guard_`): log into that account in the portal (or use “generate for this user”) and put those access tokens under `X_0GUARD_*`.

## What’s preloaded

`nuclear-list.json` includes the kill list for:

- **@rariwrldd** — self-harm post, Mysten/Sui hate dunks, scam/midwit/hate-account posts  
- **@0guard_** — `ur a dumbass`, optional `cracked dev`

Builder/ship posts are **not** listed (keep 0guard launches).

## Safety

- Default is **dry-run** (prints what would die).
- `--execute` is irreversible on your side of X (archives/screenshots may remain).
- Logs land in `results/delete-*.jsonl`.
- `--scan` may append more IDs to `nuclear-list.json` — review before second execute.
- Rate limit: ~1 delete/sec built in.

## Multi-account order (recommended)

1. `@rariwrldd` P0 only → verify gone  
2. `@rariwrldd` full nuclear  
3. `@0guard_` cleanup  
4. Manual bio/pin update on both  

## After nuke (manual, 2 min)

| Account | Action |
|---|---|
| @rariwrldd | Bio → builder-first; pin a ship post |
| @0guard_ | Pin intro/hackathon; no dunks |

## Dependencies

```bash
pip install requests requests-oauthlib
```
