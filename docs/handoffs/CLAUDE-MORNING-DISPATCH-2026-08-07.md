# Claude Code — Morning dispatch (Gemini out of credits)

**Date:** 2026-08-07  
**Gemini:** **blocked (credits)** — do not wait on website work; do not thrash Cloud Run.  
**MC:** revision `00100-lok` already serves `/dashboard/assets/*.js` as real JS — leave dashboard alone unless Ari says otherwise.

---

## Already DONE (do not redo)

| Item | Evidence |
|---|---|
| free-reign `gate_order` wire | `43f1cc9` · `via=free_reign` only · operator accepted |
| genome closes | `7a2dea1` · `auto_estimate` |
| **rh-executor reload on Windows** | `dbfb54d` · schtask `rh-executor` · 56/56 tests on Win 3.13 |
| Bridge densify + mac-bridge | green earlier |
| Drive folder tree | Sapphire/Grok Bridge lanes on Drive |
| Desk `updated_at` advancing | live ~fresh timestamps — but **fields still unknown** |

---

## Paste this into Claude Code

```text
You are Claude Code on Ari's Mac plant. Gemini is OUT OF CREDITS — no Cloud Run / dashboard deploys.

ALREADY DONE — do not redo:
- gate_order + genome closes in executor
- Windows rh-executor reloaded with wired file (dbfb54d)
- Free-reign scope free_reign-only accepted

BLOCKER FOR ARI (document only; do not handle RH credentials):
- Live rh-executor hangs at Robinhood interactive login because robin_stocks session pickle expired.
- Needs Ari at Windows console: re-auth RH attended. Not a code bug from the gate wire.

YOUR MISSION (priority order):

════════════════════════════════════════
P0 — TELEMETRY DESK QUALITY (public trading looks empty)
════════════════════════════════════════
Live https://sapphirealpha.xyz/api/v1/live has:
- status=live, markets epm ~600, nodes/agents OK
- desk.updated_at is FRESH but posture/execution/epistemics still "unknown"
  → publisher is cycling empty desk, not missing entirely

1. git pull --ff-only origin main in ~/Code/Sapphire
2. Read:
   - docs/handoffs/CLAUDE-TELEMETRY-DESK-REFRESH-2026-08-06.md
   - lib/grok/desk_projection.py
   - projects/grok/data/desk_projection_example.json
   - projects/grok/data/telemetry_publisher_checklist.json
   - docs/strategy/PUBLIC-TRADING-DATA-TRUTH-2026-08-06.md
3. Find alpha-telemetry-publisher / merged_collector (dashboard repo telemetry/
   + Mac LaunchAgent com.sapphire.alpha-telemetry-publisher.plist).
4. Each publish cycle:
   - desk = build_desk_projection(...) with REAL local observations where known
   - ALWAYS set updated_at = now
   - If truly unknown, keep explicit "unknown" — never invent PnL/wallets/positions
   - Prefer: posture capital_preservation (late cycle), execution gated/halted from
     pause/killswitch truth if readable, safety_floor.pause_clear from pause files
   - markets.decision_gate / execution from free-reign + pause if available
   - Merge plant facts via observed_extras; do not zero-fill money
5. Verify:
   curl -sS https://sapphirealpha.xyz/api/v1/live | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['desk'].get('posture'), d['desk'].get('execution'), d['desk'].get('updated_at'))"
   Goal: posture and/or execution not both stuck "unknown" when plant knows better;
   OR document exact missing local source files.
6. Export: data/grok-web-exports/YYYY-MM-DD_local-export_telemetry-desk-refresh.md
   Commit: local-export: telemetry desk refresh [date]

════════════════════════════════════════
P1 — Drive densify pack sync (optional, high leverage)
════════════════════════════════════════
1. python3 scripts/ops/grok_drive_pack.py --write
2. If rclone or Drive desktop available, sync data/grok-drive-pack/ into:
   Drive: Sapphire/Grok Bridge/ (folder IDs in projects/grok/data/drive_bridge_folders.json)
3. Export note if synced: local-export: grok-drive-pack synced [date]
4. No secrets in pack (packer already skips secretish)

════════════════════════════════════════
P1 — Confirm Win executor still alive (probe only)
════════════════════════════════════════
- schtasks /Query /TN rh-executor (via Tailscale SSH)
- Note if still hung on RH login prompt
- Do NOT place live orders; do NOT ARM L2
- Do NOT paste RH password into chat/logs

════════════════════════════════════════
P2 — only if P0 green and Win SSH free
════════════════════════════════════════
- Windows P0 acceptance probes (docs/strategy/WINDOWS-DATACENTER-MASTERPLAN…)
- arm_l2_allowed stays false
- Update projects/grok/data/windows_acceptance.json from REAL probes

HARD FENCES:
- NO L2 ARM / overnight live traders enable
- NO live order placement
- NO RH credential handling / no password in git or chat
- NO Cloud Run / sapphire-alpha-dashboard deploys (Gemini credits dead; MC already paints)
- NO kill sapphire_os, plant deck, densify LA, other Claude sessions
- NO secret dumps
- git: explicit paths only

REPORT:
1. Desk before/after posture+execution+updated_at
2. Publisher path(s) edited
3. Drive sync done?
4. Win executor RH-login status
5. Commits/SHAs
6. What Ari must do (RH re-auth)
```

---

## Ultra-short paste

```text
Gemini out of credits — no dashboard work. Executor reload already done (dbfb54d).
Next: docs/handoffs/CLAUDE-MORNING-DISPATCH-2026-08-07.md — P0 telemetry desk quality
(lib.grok.desk_projection), P1 Drive pack sync. RH session expired = Ari re-auth only.
No L2 ARM, no money, no secrets.
```

---

## Ari (you) — 5 minutes when at Win desk

1. Open Windows console on DESKTOP-HFCK6U9  
2. Re-authenticate Robinhood for `robin_stocks` (interactive login the schtask needs)  
3. Confirm `rh-executor` stops hanging at "Robinhood username:"  
4. Do **not** ARM L2  

Without this, free-reign gate is loaded but **cannot poll** (pre-existing session expiry).
