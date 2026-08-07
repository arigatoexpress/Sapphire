# Grok CLI / Mac plant dispatch — RH re-auth + desk (Claude tokens out)

**Date:** 2026-08-07  
**Claude:** out of tokens — plant seat moves here.  
**Gemini Cloud Shell:** **wrong machine** for RH/Windows pickle (no home Tailscale). Use Gemini only for website/GCP when credits return.  
**You:** Grok CLI on Mac (`grok` CLI or mac-bridge operator session) with access to `~/Code/Sapphire`, `~/ops-state`, and Tailscale → `DESKTOP-HFCK6U9`.

---

## Seat map (do not confuse)

| Seat | Can do RH Win re-auth? | Can do desk telemetry? | Can do dashboard? |
|---|---|---|---|
| **Grok CLI on Mac** | **YES** (SSH) | **YES** | no need |
| **This Grok web chat** | NO (sandbox) | monorepo only | no |
| **Gemini Cloud Shell** | **NO** | NO | yes when credits |
| **Claude** | yes when tokens return | yes | no |

---

## Paste into Grok CLI on Mac (or `grok` in terminal)

```text
You are Grok CLI on Ari's Mac plant. Claude tokens are exhausted. Gemini is wrong seat for this job.

MISSION PRIORITY:
P0 — Remote Robinhood session re-auth on Windows (Ari approved Option A)
P1 — Finish desk_projection telemetry quality if not already exported
P2 — Optional: python3 scripts/ops/grok_drive_pack.py --write (+ rclone if configured)

READ FIRST:
  docs/handoffs/CLAUDE-REMOTE-RH-REAUTH-2026-08-07.md
  docs/handoffs/CLAUDE-TELEMETRY-DESK-REFRESH-2026-08-06.md
  lib/grok/desk_projection.py
  data/grok-web-exports/2026-08-06_local-export_executor-reloaded.md

ARI APPROVAL (already given in Grok web chat for Option A):
  Phrase: APPROVE RH REAUTH — treat as granted for this session unless Ari revokes.
  MFA: Ari will provide one-time code in chat/Telegram when you ask. Do not invent MFA.

HARD FENCES:
- No RH password in git, densify, bridge exports, or long-lived logs
- No live orders, no L2 ARM, no secret dumps
- No Cloud Run / dashboard deploys
- Do not kill sapphire_os, densify LA, unrelated plant processes

P0 STEPS (RH re-auth):
1. cd ~/Code/Sapphire && git pull --ff-only origin main
2. Probe Tailscale/SSH to DESKTOP-HFCK6U9
3. Locate rh-executor schtask, hung PID, pickle path, rh_login_pickle_only.py (or plant equivalent) by READING sources
4. Backup existing pickle if present
5. Stop hung executor (schtasks /End; taskkill orphan PID only if lock stuck — known from dbfb54d)
6. Run pickle-only login using credentials ALREADY on Win (env/secret store) — never echo password
7. If MFA needed: stop and ask Ari for code (one shot); do not log the code after use
8. Verify noninteractive pickle load OK
9. schtasks /Run /TN rh-executor — confirm past "Robinhood username:" hang
10. Export: data/grok-web-exports/YYYY-MM-DD_local-export_rh-session-reauth.md
    Commit: local-export: RH session re-auth remote [date]

P1 STEPS (desk — if live still incomplete or no local-export yet):
1. Wire/publish desk via lib.grok.desk_projection each telemetry cycle
2. Verify: curl -sS https://sapphirealpha.xyz/api/v1/live | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['desk'].get('posture'), d['desk'].get('execution'))"
3. Export local-export: telemetry desk refresh if not done

REPORT:
- SSH ok?
- Re-auth success?
- Executor past login?
- Desk posture/execution
- SHAs
- What Ari still must do
```

---

## Ultra-short (Grok CLI)

```text
Claude out of tokens. Plant mission: docs/handoffs/GROK-CLI-PLANT-DISPATCH-RH-REAUTH-2026-08-07.md
P0 remote RH re-auth (APPROVE RH REAUTH already granted in web chat). MFA ask Ari when needed.
P1 desk_projection if needed. No L2, no secrets in git, no dashboard.
```

---

## How Ari starts Grok CLI on Mac (if not already)

From Mac terminal (or any remote Mac shell you already use):

```bash
cd ~/Code/Sapphire && git pull --ff-only origin main
# if grok CLI installed:
grok   # then paste ultra-short / full mission
# OR if mac-bridge only:
# curl -sS http://127.0.0.1:19998/health
# use your normal grok CLI entrypoint that talks OIDC locally
```

If you only have **phone**: use Termius/SSH to **Mac first**, then run Grok CLI / the login scripts there — not to Cloud Shell.

---

## Gemini (only when credits return — different mission)

```text
Do NOT do RH re-auth. Website only when credits restore:
docs/handoffs/GEMINI-DATA-TRUTH-AND-PUBLIC-SURFACE-2026-08-06.md
MC already paints on 00100.
```

---

## Success

- [ ] Win pickle valid without interactive hang  
- [ ] rh-executor polling  
- [ ] local-export reauth on main  
- [ ] desk not stuck unknown (or export explaining residual)  
- [ ] no secrets in git  
