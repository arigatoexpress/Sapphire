# Claude — Remote Robinhood session re-auth (Ari away from home)

**Date:** 2026-08-07  
**Why:** `rh-executor` on Windows hangs on expired `robin_stocks` pickle → interactive  
`Robinhood username:` prompt in a **headless** schtask. Gate code is live (`dbfb54d`);  
polling cannot start until session pickle is valid again.  
**Ari:** away from home desk — **has phone** (Telegram + SMS/app 2FA).  
**You:** Claude Code on Mac plant with Tailscale/SSH to `DESKTOP-HFCK6U9`.

---

## Paste into Claude Code

```text
You are Claude Code on Ari's Mac. Ari is AWAY FROM HOME and cannot sit at the Windows console.
Mission: restore a non-interactive Robinhood session pickle on Windows so rh-executor can
poll again — using remote SSH/Tailscale + Telegram for human approval / MFA codes.

## Context (trust this)
- Live executor = Windows only, schtask `rh-executor`
  C:\Users\aribs\telegram-bot\run_executor.bat → executor.py
- Gate_order already deployed; 56/56 tests passed on Win
- Failure mode: robin_stocks pickle expired → process blocks on interactive login
- Mac brokerage copy intends: interactive login FORBIDDEN in executor; remediation is
  rh_login_pickle_only.py (or equivalent) on Win — find the real script/path by reading
  plant sources, do not invent
- Free-reign / L2 ARM / live orders: NOT this mission

## Absolute fences
1. NEVER print, log, commit, or Telegram: RH password, pickle bytes, API keys, full session tokens
2. NEVER paste secrets into git, densify exports, or Grok bridge
3. NEVER place orders, ARM L2, enable overnight live traders
4. NEVER disable executor safety / single-instance lock for convenience
5. If MFA/SMS is required, ONLY accept codes Ari sends via Telegram in this session —
   do not scrape SMS apps or email without explicit Ari approval
6. Prefer existing plant secret locations over asking Ari to type password into chat:
   check Windows/Mac conventions (wallet-config paths, env, Windows Credential Manager,
   existing docs) WITHOUT dumping contents to chat — report only "found/missing"
7. If remote re-auth is impossible without desktop GUI, stop with a clear blocker list —
   do not half-break the pickle

## Architecture of the remote re-auth (intended)

```
Ari (phone)
  │  Telegram: "approve re-auth" + MFA code when prompted
  ▼
Claude Mac
  │  SSH Tailscale → DESKTOP-HFCK6U9
  │  stop rh-executor cleanly (or leave hung PID after documenting)
  │  run pickle-only login helper (non-schtask, attended-by-agent)
  │  feed MFA from Telegram if needed (ephemeral; do not log code after use)
  │  verify pickle loads non-interactively
  │  restart rh-executor schtask
  ▼
Windows robin_stocks pickle valid → executor reaches process_once()
```

## Phase 0 — Probe (no secrets, no restarts yet)

1. git pull --ff-only origin main on Mac Sapphire
2. From Mac, Tailscale/SSH to Windows (BatchMode if possible):
   - schtasks /Query /TN rh-executor /v  (status, last run)
   - Find python process stuck on executor / login prompt
   - Locate pickle path + login helper by reading Win telegram-bot sources:
     brokerage.py, rh_login*.py, *pickle*, login helpers
   - Confirm whether Mac's _login_noninteractive safety exists on Win copy
3. Search plant for documented re-auth:
   rg -n "rh_login_pickle|pickle_only|_login_noninteractive|Robinhood username" \
     ~/ops-state ~/Code/Sapphire C:\Users\aribs\telegram-bot  (via SSH)
4. Report to Ari via short status (Telegram only if plant already has a safe notify path;
   else session report): paths found, whether password is already stored as opaque secret
   on disk (yes/no only), MFA method expected (SMS / app / device approve)

STOP if you cannot SSH to Win. Export blocker. Do not invent credentials.

## Phase 1 — Ari approval gate (Telegram)

Before any login attempt, send (or prepare for Ari) ONE approval message:

```
RH remote re-auth requested.
Host: DESKTOP-HFCK6U9 schtask rh-executor
Plan: stop hung executor → run pickle-only login → restart schtask
Will need: MFA/SMS code from you when prompted
No orders / no L2 ARM
Reply: APPROVE RH REAUTH
```

Wait for exact phrase **APPROVE RH REAUTH** from Ari (Telegram or this chat).
Without it, do not run login.

## Phase 2 — Stop hung executor safely

1. Prefer: schtasks /End /TN rh-executor
2. If orphan PID still holds single-instance lock (known issue from dbfb54d):
   document PID, then taskkill ONLY that executor PID (not other plant processes)
3. Confirm no executor holding lock
4. Do NOT delete the old pickle until new login succeeds (keep backup copy)

## Phase 3 — Pickle-only login (remote)

1. Use the plant's intended helper if present, e.g.:
   - rh_login_pickle_only.py
   - or documented noninteractive login CLI
2. Credentials source priority:
   a) Existing env/secret file already used by executor on Win (read by script, not by you into chat)
   b) Windows Credential Manager / plant secret store if scripts already support it
   c) ONLY if a/b missing: ask Ari to set password via secure one-shot on Win
      (e.g. temporary env var in SSH session he types — not Telegram password)
3. MFA:
   - When prompt needs code: message Ari on Telegram "send 6-digit RH code now"
   - Accept one code; use immediately; do not write code to logs/files/exports
   - If device-approve flow: tell Ari to approve in RH mobile app
4. On success: verify pickle file mtime updated + a dry noninteractive login call returns OK
5. On failure: restore backup pickle if any; leave executor stopped; report

## Phase 4 — Restart + verify (no money)

1. schtasks /Run /TN rh-executor
2. Confirm new PID, not hung on "Robinhood username:"
3. Tail recent log lines (REDACT any auth material) for:
   - reached process_once / gates / poll loop
   - OR still auth error
4. Optional: python dry import path that loads pickle without trading
5. Do NOT submit free-reign proposals as a test

## Phase 5 — Export + report

Write:
  data/grok-web-exports/YYYY-MM-DD_local-export_rh-session-reauth.md

Must include:
- paths used (no secrets)
- approval received? (yes/no)
- MFA method used (sms/app/device) — not the code
- success/fail
- executor PID + "past login prompt?" yes/no
- residual blockers

Commit message:
  local-export: RH session re-auth remote [date]

## If full remote auth is blocked

Common hard stops:
| Blocker | What to do |
|---|---|
| No SSH to Win | Stop; Ari enables Tailscale/SSH |
| Password nowhere + Ari won't type on SSH | Stop; schedule home visit |
| RH requires device biometrics only | Ari completes on phone; you only restart executor after pickle appears |
| Login helper missing on Win | Port Mac's noninteractive pattern; still no secrets in git |
| Pickle works but executor still hangs | Fix login call site to use pickle-only path (code fix), re-test |

## Success criteria

- [ ] Ari replied APPROVE RH REAUTH
- [ ] New/updated pickle loads without input()
- [ ] rh-executor running, past username prompt
- [ ] No secrets in git/Telegram history/exports
- [ ] No orders placed, no L2 ARM
- [ ] local-export committed
```

---

## Ultra-short paste

```text
Ari is away — remote RH re-auth on Win via Tailscale + Telegram approval/MFA.
Full: docs/handoffs/CLAUDE-REMOTE-RH-REAUTH-2026-08-07.md
Phrase to wait for: APPROVE RH REAUTH
No passwords in chat/git/Telegram. No orders. No L2 ARM.
Find rh_login_pickle_only (or plant equivalent), backup pickle, login, restart rh-executor.
```

---

## What Ari does from the phone

1. Paste ultra-short (or full) prompt to Claude on Mac  
2. When Claude asks: reply exactly **`APPROVE RH REAUTH`**  
3. When Claude asks for MFA: send the **current** RH SMS/app code in Telegram (one-time)  
4. If RH app shows device approve: tap approve  
5. Do **not** send your RH password over Telegram if Claude can use existing Win secret store  
6. If Claude reports password missing: either  
   - wait until home, or  
   - open a **direct SSH** session yourself and set env once (prefer over Telegram password)

## Reality check

| Possible remotely | Usually not |
|---|---|
| SSH stop/start executor | Completing biometrics-only RH flows without phone |
| Running pickle login script | Safe password-over-Telegram |
| MFA code relay from your phone | Skipping RH 2FA |
| Verifying poll loop after | "Just disable auth" |

Telegram is for **approval + MFA relay**, not a password vault.


---

## Dispatch / sandbox note (2026-08-07)

Claude **Dispatch** may not hold interactive SSH itself. **Option A (approved):**
spawn a **Mac code agent / Claude Code task** with Tailscale SSH to Windows.

Ari approval phrase (this chat or Telegram): **`APPROVE RH REAUTH`**

When MFA needed: agent pauses → Ari sends **one** 6-digit (or app) code → agent continues.
Never log password or MFA into git/densify. Desk P0 continues in parallel.
