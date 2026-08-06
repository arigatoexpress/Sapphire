# Claude Code — RESUME executor reload (after usage limit)

**When:** 2026-08-06 ~20:00Z  
**Why:** Prior Claude session hit **usage limit** mid-probe.  
**Do not restart P0-A/B** — source already wired and **operator-accepted**.

---

## Paste this whole block into Claude Code when limit resets

```text
You are Claude Code on Ari's Mac plant. RESUME only — do not re-wire free-reign or genome.

## Already DONE (do not redo)
- P0-A: gate_order in ~/ops-state/telegram-bot/executor.py (via=free_reign only)
  commit 43f1cc9 — operator ACCEPTED free_reign-only scope
- P0-B: genome closes in _record_skin_fill (source=auto_estimate) commit 7a2dea1
- Bridge :19998 mac-bridge green; densify 30m LA green
- Decision: docs/handoffs/OPERATOR-DECISION-GATE-SCOPE-2026-08-06.md = ACCEPT

## Prior session (interrupted by usage limit)
- Had pulled CLAUDE-EXECUTOR-RELOAD-PROMPT
- Confirmed Windows DESKTOP-HFCK6U9 is Tailscale-reachable
- Was about to probe whether Win hosts live rh-executor schtask
- DID NOT restart anything yet — good

## YOUR MISSION NOW (narrow)

1. git pull --ff-only origin main in ~/Code/Sapphire

2. Locate who runs executor.py LIVE (probe only first):
   MAC:
     ps aux | rg -i 'executor|rh-executor|telegram-bot' || true
     launchctl list | rg -i 'rh|executor|telegram|sapphire' || true
     ls ~/ops-state/telegram-bot/executor.py
     rg -n "order_gate_check|gate_order|free_reign" ~/ops-state/telegram-bot/executor.py | head

   WIN (Tailscale — SSH BatchMode if works):
     schtasks /Query /TN "rh-executor" 2>nul
     schtasks /Query /FO LIST /V | findstr /i executor
     # Do NOT /Change /Enable anything that is L2 or overnight live traders
     # Only identify path + state of the executor that runs telegram-bot/executor.py

3. Decision tree:
   A) Mac process runs executor → graceful restart THAT process only
      (prefer the plant's normal restart script if one exists; else stop/start
       the specific service — NEVER kill sapphire_os :8099, plant deck :8100,
       rh_rpc_guard, rh_orderflow, other Claude sessions, or densify LA)
   B) Win schtask runs executor → if schtask is already enabled and is the
      free-reign executor (NOT L2 ARM tasks):
        - Sync latest ops-state/executor.py to Win if that is the copy used
        - End then Run the EXISTING rh-executor task only (not create new ARM)
      If Win path unclear or L2-adjacent: STOP, export blocker, no ARM
   C) Neither live: document "source wired, no live executor process" + stop

4. After reload, verify WITHOUT live money:
   - python3 ~/Code/Sapphire/scripts/ops/grok_paper_proposal_smoke.py
   - If plant has unit tests: test_executor.py gate tests still green
   - Prefer a dry log path showing GATE DENIED / DENS_BLOCK for free_reign
     (do not place real orders)

5. Export + commit (explicit paths only):
   data/grok-web-exports/2026-08-06_local-export_executor-reloaded.md
   Message: local-export: rh-executor reloaded with gate_order [2026-08-06]

## HARD FENCES
- NO L2 schtask ARM / enable overnight live traders
- NO live order placement
- NO Hermes/Telegram spam
- NO secret dumps
- NO dashboard/Cloud Run (Gemini)
- NO re-implement free-reign gate
- NO kill plant deck / sapphire_os / bridge :19998

## REPORT
1. Where does live executor run? (Mac / Win / both / none)
2. What you restarted (exact name)
3. Verify evidence (smoke / log line)
4. Export SHA
5. Still blocked? (Win P0 / path ambiguity)
```

---

## Ultra-short paste (if context already warm)

```text
RESUME executor reload only — usage limit interrupted mid Win probe.
Win is Tailscale up. Do NOT re-wire P0-A/B. Find live rh-executor host,
graceful restart that process only, export local-export: rh-executor reloaded.
No L2 ARM, no money. Full: docs/handoffs/CLAUDE-RESUME-EXECUTOR-RELOAD-2026-08-06.md
```

---

## If Claude still limited — Ari manual 5-min check

```bash
# Mac
ps aux | rg -i 'executor|rh-executor' || true
rg -n "order_gate_check" ~/ops-state/telegram-bot/executor.py | head
curl -sS http://127.0.0.1:19998/health | head -c 200

# Win via Tailscale (from Mac) — adjust host/task name
# ssh DESKTOP-HFCK6U9 "schtasks /Query /TN rh-executor"
```

Only restart the process you are sure runs `executor.py`. If unsure, wait for Claude.
