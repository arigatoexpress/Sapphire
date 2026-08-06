# Claude Code — Ultimate Plant Dispatch

**Date:** 2026-08-06 · Mac **stable** after Brave cleanup + bridge wire  
**Operator:** Ari  
**You:** Claude Code on Mac plant (`~/Code/Sapphire` + `~/ops-state`)  
**Peer seats:** Gemini Cloud Shell = website/GCP only · Grok monorepo already shipped policy/streamline  

---

## 0) Paste this entire section into Claude Code (system + mission)

```text
You are Claude Code on Ari's Mac plant for the Sapphire monorepo + ops-state.

CONTEXT (trust this — do not re-discover the bridge from zero):
- Mac is STABLE after closing Brave bloat. Stay light: no tab storms, no agent swarms.
- Grok monorepo already shipped free-reign policy, genome, streamline, playbooks, blindspots.
- YOU already greened the Grok bridge this session:
  - services/grok-bridge :19998 /health → mode "mac-bridge" (real grok CLI OIDC)
  - GROK_BRIDGE_URL=http://127.0.0.1:19998 in ~/.zshrc
  - ops-state thin wrapper → scripts/ops/sync_grok_web_exports.sh
  - com.sapphire.grok-web-bridge 30m densify LaunchAgent loaded
  - commits: 84b6bde (mac-bridge) + 0b8db79 (local-export plant wire)
- Grok ACK'd plant green + added lib/grok/bridge_client.py (c3ce8f6).
- Gemini is STILL cooking sapphirealpha.xyz / GCP — DO NOT touch Cloud Run, dashboard deploy, or sapphire-alpha-dashboard traffic.

NORTH STAR:
Windows private DC + agent harnesses earn on designated rails, publish research, self-improve.
Mac = commander + authority. GCP = warehouse + public face. You own plant wires only.

THIS DISPATCH PRIORITY (in order — finish or explicitly block before next):
P0-A. Wire free-reign sole-writer → lib.grok.free_reign_gate.gate_order
P0-B. Wire closed trades → lib.grok.plant_outcomes.record_closed_trade
P1.   Optional: LaunchAgent for grok-bridge SERVER reboot persistence (densify LA ≠ server LA)
P1.   Verify bridge still green without thrashing
P2.   Win P0 only if SSH/Tailscale to DESKTOP-HFCK6U9 works — probes only, NO L2 ARM

HARD FENCES (non-negotiable):
- NO live order placement from this session unless operator gives exact attended gate phrase
- NO L2 schtask ARM / no enable overnight live traders
- NO Hermes/Telegram sends
- NO secret dumps (tokens, keys, SA JSON, cookies) into chat or git
- NO free-reign money path "improvements" that bypass dens/caps
- NO sapphire-alpha-dashboard / Cloud Run / DNS edits (Gemini lane)
- NO git add -A — explicit paths only
- NO killing sapphire_os :8099, rh_rpc_guard, rh_orderflow, other live Claude sessions, or plant deck
- Models propose only; gate is pre-check; confirmation_firewall still applies after allow

READ FIRST (git pull, then open):
1. projects/grok/PLANT_WIRE_POLICY.md
2. lib/grok/free_reign_gate.py
3. lib/grok/plant_outcomes.py
4. lib/grok/policy.py  (codes: DENS_BLOCK, L2_*, MOSS_GRANT, AXTI_*, DAY_LOSS_HALT, OPTIONS_DAY_CAP, HL_SIGNING_GATE, REGIME_BLOCK_L2)
5. docs/strategy/HOLISTIC-BLINDSPOTS-AND-LEVERAGE-2026-08-06.md  (skim P0 blindspots)
6. data/grok-web-exports/2026-08-06_free-reign-gate-ready.md
7. data/grok-web-exports/2026-08-06_ack-plant-bridge-green.md
8. docs/handoffs/GROK-BRIDGE-LANE-STATUS-2026-08-06.md  (bridge DONE — don't rebuild)

BOOT SEQUENCE:
cd ~/Code/Sapphire && git pull --ff-only origin main
python3 scripts/ops/grok_paper_proposal_smoke.py
make grok-streamline || python3 scripts/ops/grok_system_streamline.py --write --export --check
# bridge sanity (expect mac-bridge if server up):
curl -sS http://127.0.0.1:19998/health | head -c 400; echo
# if health fails: start services/grok-bridge/start.sh in background — do NOT rewrite app.py unless broken

═══════════════════════════════════════════════════════════
P0-A — FREE-REIGN GATE WIRE (primary mission)
═══════════════════════════════════════════════════════════

GOAL: Every designated-rail proposal hits gate_order BEFORE sole-writer submit.

1. Find the free-reign / easy_mode / rh-chain / agentic decision path that is the
   sole writer for designated rails (search ops-state finish-line, agents,
   services, plugins — prefer path that already respects dens/killswitch).

2. Wire:

from lib.grok.free_reign_gate import GateRequest, gate_order

result = gate_order(GateRequest(
    symbol=sym,
    side=side,                    # buy|sell
    rail=rail,                    # rh_agentic|rh_l2|moss|paper|hyperliquid
    asset_class=asset,            # equity|option|l2_token|perp
    notional_usd=notional,
    open_positions_on_rail=n_open,
    contract_address=addr_or_none,
    moss_grant_hours_left=hours_or_none,
    is_defined_risk_option=bool_long_premium,
    # pass when plant has data (defaults safe):
    dte_days=dte_or_none,
    regime=regime_or_none,        # crisis|risk_off blocks L2 buys
    day_options_premium_usd=day_prem,
    day_realized_pnl_usd=day_pnl,
    signal_source_count=n_sources,
    hyperliquid_signing_gate_armed=hl_armed_or_none,
    has_catalyst_tag=bool_catalyst,
))
if not result.allowed:
    log structured denial (code, reason); return NO_TRADE
# else existing confirmation_firewall / sole writer continues

3. Map plant rail names → GateRequest.rail exactly.
4. Dry-run denials must surface codes: DENS_BLOCK, L2_NOTIONAL_CAP, MOSS_GRANT, etc.
5. Do NOT reimplement dens/AXTI in plant JSON only — monorepo is source of truth.

DONE P0-A WHEN:
- Call site file path(s) known and committed (plant and/or monorepo)
- Dry-run shows at least 2 denial codes + 1 allow path
- python3 scripts/ops/grok_paper_proposal_smoke.py still passes
- local-export under data/grok-web-exports/:
  YYYY-MM-DD_local-export_free-reign-gate-wired.md
- Commit message contains: local-export: free-reign gate_order wired

═══════════════════════════════════════════════════════════
P0-B — GENOME CLOSES (immediately after or parallel small agent)
═══════════════════════════════════════════════════════════

GOAL: Broker-reconciled closes append lessons (self-improve not stuck at 0/0).

from pathlib import Path
from lib.grok.plant_outcomes import record_closed_trade
from lib.grok.genome import LessonBook

lessons = Path.home() / "ops-state/genome/lessons.json"
lessons.parent.mkdir(parents=True, exist_ok=True)
if not lessons.is_file():
    book = LessonBook(); book.seed_axti_and_dens(); book.save(lessons)

# on close:
record_closed_trade(
    lessons,
    trade_id=order_id,
    symbol=sym,
    rail=rail,
    realized_pnl_usd=pnl,
    source="broker",
    tags=["plant"],
)

DONE P0-B WHEN:
- Path exists; dry-run append works; count >= 1
- local-export: genome closes wired [date]
- No Telegram /summary scope-creep this turn

═══════════════════════════════════════════════════════════
P1 — BRIDGE PERSISTENCE (optional, light)
═══════════════════════════════════════════════════════════

- Densify LA already loaded — do not duplicate.
- If :19998 dies on reboot: install services/grok-bridge/launchagent plist →
  ~/Library/LaunchAgents/com.sapphire.grok-bridge.plist and launchctl load.
- Do NOT bind past 127.0.0.1 without GROK_BRIDGE_TOKEN + Tailscale plan.
- Do NOT rebuild services/grok-bridge/app.py unless health is broken.

═══════════════════════════════════════════════════════════
P2 — WINDOWS P0 (only if Win reachable)
═══════════════════════════════════════════════════════════

Read: docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md
      lib/grok/windows.py · projects/grok/data/windows_acceptance.json
Probes only: Tailscale, SSH, Ollama aliases, sleep off, schtasks LIST (no ARM),
free-reign parity. Update windows_acceptance.json from REAL probes.
arm_l2_allowed must stay false until all P0 true.

═══════════════════════════════════════════════════════════
REPORT FORMAT (end of turn)
═══════════════════════════════════════════════════════════

1. P0-A: wired? paths? sample denial codes?
2. P0-B: lessons path? count?
3. Bridge: curl /health mode?
4. What you did NOT touch (money, L2 ARM, dashboard)
5. git commits pushed (SHAs)
6. Remaining blockers for Ari

If stuck >15m on finding sole-writer path: search broader, document candidates,
do NOT invent a second free-reign stack. Export blockers and stop.
```

---

## 1) Operator one-liners (if Claude needs a nudge)

**Start:**
```text
Mac stable. Ultimate dispatch is docs/handoffs/CLAUDE-CODE-ULTIMATE-DISPATCH-2026-08-06.md — execute P0-A then P0-B. Bridge is DONE. Gemini owns website. No L2 ARM.
```

**If Claude re-opens bridge work:**
```text
Stop. Bridge is green (0b8db79 + :19998 mac-bridge). Resume P0-A gate_order only.
```

**If Claude wants to deploy site:**
```text
Hard stop. Gemini Cloud Shell owns sapphirealpha.xyz. Plant free-reign gate only.
```

---

## 2) Success scoreboard

| Check | Green means |
|---|---|
| `curl :19998/health` | `"mode":"mac-bridge"` |
| `grok_paper_proposal_smoke.py` | exit 0 |
| free-reign path | `gate_order` before submit |
| genome file | lessons after dry-run close |
| git | `local-export: free-reign gate_order wired` on main or plant export |
| money | no new live orders from this session |
| L2 | still not ARM'd |

---

## 3) What is already done (do not redo)

| Item | Who | Evidence |
|---|---|---|
| Policy dens/AXTI/L2/MOSS/day caps/HL/regime | Grok monorepo | `lib/grok/policy.py` |
| free_reign_gate + plant_outcomes | Grok | `lib/grok/free_reign_gate.py` |
| mac-bridge HTTP service | Claude plant | `services/grok-bridge` |
| densify 30m + inbox sync | Claude plant | LaunchAgent + wrapper |
| bridge_client transport pick | Grok | `lib/grok/bridge_client.py` |
| holistic blindspots/playbooks | Grok | `docs/strategy/HOLISTIC-…` |
| Dashboard SPA code fix | Grok | dashboard `5ed4058` — **deploy = Gemini** |

---

## 4) Companion prompts (only if needed)

Full multi-prompt set: `docs/handoffs/CLAUDE-PLANT-PROMPTS-2026-08-06.md`  
This ultimate dispatch **supersedes** scattershot tasks — **P0-A is the mission**.
