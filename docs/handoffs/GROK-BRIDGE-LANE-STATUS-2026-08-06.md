# Grok Bridge Lane Status — 2026-08-06

**Lane owner (web / monorepo):** Grok Build  
**Lane owner (plant densify / LaunchAgents):** Claude agents (dispatch in progress)  
**Mission context:** Windows private DC master plan remains north star; this lane is the **knowledge plane** that keeps agents aligned while Claude configures the rest of the bridge.

---

## 1) What “done” means for this lane

| Layer | Done when |
|---|---|
| **Git store** | `data/grok-web-exports/` has dated MDs + README + MANIFEST |
| **Monorepo tools** | `sync_grok_web_exports.sh` + `grok_bridge_status.py` + unit tests on `main` |
| **Plant wrapper** | `~/ops-state/finish-line/scripts/sync_grok_web_exports.sh` exists and calls monorepo or mirrors it |
| **Inbox** | `~/Knowledge/0-Inbox/grok-web/` receives copies; never deletes git sources |
| **Densify beat** | Ralph / densify / overnight invokes sync on a schedule |
| **Deck** | Operator feeds surface new exports on `:8100` |
| **Web write** | GitHub connector / MCP can land `web-export:` commits (already verified 2026-08-05) |

---

## 2) Monorepo side — shipped this turn

| Item | Path | Status |
|---|---|---|
| Status inventory | `scripts/ops/grok_bridge_status.py` | shipped |
| Sync script (canonical) | `scripts/ops/sync_grok_web_exports.sh` | shipped |
| Unit tests | `tests/unit/test_grok_bridge_status.py` | shipped |
| Manifest | `data/grok-web-exports/MANIFEST.json` | generated |
| README contract | `data/grok-web-exports/README.md` | expanded |
| CI README bullet | `README.md` (`7,836+ passing tests across 469 files`) | restored (fixes `test_inventory --check-readme`) |
| Mission docs | Win DC plan + Gemini Cloud Shell prompt | already on main (`795e373`) |

Claude agents: **do not re-author** the monorepo sync script unless improving it; **wire plant wrapper + LaunchAgent** to call it.

---

## 3) Plant side — Claude checklist (do not block on Cloud Shell)

```text
[ ] Confirm ~/Code/Sapphire is on main + git pull
[ ] Ensure ~/ops-state/finish-line/scripts/sync_grok_web_exports.sh exists
      → prefer: bash ~/Code/Sapphire/scripts/ops/sync_grok_web_exports.sh "$@"
[ ] mkdir -p ~/Knowledge/0-Inbox/grok-web ~/ops-state/logs
[ ] Dry-run: bash …/sync_grok_web_exports.sh --dry-run
[ ] Live sync once; confirm files in inbox
[ ] Register densify/Ralph/overnight hook (15–60m)
[ ] Optional LaunchAgent com.sapphire.grok-web-bridge or com.ari densify step
[ ] publish_operator_feeds.py after sync (if not already chained)
[ ] Log path: ~/ops-state/logs/grok-web-bridge.log
[ ] Smoke: plant deck :8100 shows new export titles
[ ] Write local-export note back to data/grok-web-exports/ when plant config lands
```

**Fences for Claude (unchanged):** no live order spam, no Hermes send, no secret print, no archive of RETIRED telegram-bot without readlink check, no `git add -A`.

---

## 4) Coordination rules (avoid thrash)

1. **Monorepo tools** → Grok/web agents own; PRs to `scripts/ops/*bridge*` and `data/grok-web-exports/`.  
2. **Plant LaunchAgents / ops-state** → Claude owns; densify this handoff + call monorepo scripts.  
3. If both edit the same export MD: prefer **append section** + new dated file over silent rewrite.  
4. After plant wire-up, Claude should push:

   ```text
   local-export: plant grok-bridge sync wired [2026-08-06]
   ```

   into `data/grok-web-exports/`.

---

## 5) Monitor commands

```bash
# Monorepo / Cloud Shell
cd ~/Sapphire && git pull --ff-only
python3 scripts/ops/grok_bridge_status.py
python3 scripts/ops/grok_bridge_status.py --check

# Plant
bash ~/ops-state/finish-line/scripts/sync_grok_web_exports.sh --dry-run
tail -20 ~/ops-state/logs/grok-web-bridge.log
ls -lt ~/Knowledge/0-Inbox/grok-web/ | head
curl -sf -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8100/
curl -sf http://127.0.0.1:8099/healthz || true
```

---

## 6) Related mission docs

- `docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md`
- `docs/handoffs/GEMINI-CLOUDSHELL-MASTER-PROMPT-2026-08-06.md`
- `docs/handoffs/GCP-CLOUD-SHELL-ULTIMATE-HANDOFF-2026-08-06.md`
- `data/grok-web-exports/2026-08-05_master-handoff-claude-opus.md`
- `data/alpha/alpha_ledger.json` (BR-* bridge items)

---

## 7) Snapshot

| Signal | 2026-08-06 |
|---|---|
| Web MCP write | OK (2026-08-05 probe) |
| Export count | see `MANIFEST.json` |
| Claude plant wire | **in progress** (monitor for `local-export:` commits) |
| CI inventory bullet | restored this turn |

*Update this file when plant side reports green or when Claude lands the local-export receipt.*

## Update 2026-08-06 later — PLANT GREEN
Claude: mac-bridge live + densify LA + local-export receipt. Grok: bridge_client + ACK export.
