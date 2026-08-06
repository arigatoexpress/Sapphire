# Claude plant prompts — while Gemini finishes the website

**Date:** 2026-08-06  
**Context:** Gemini Cloud Shell is shipping sapphirealpha.xyz / GCP.  
**You (Claude):** Mac plant only — free-reign gate wire, genome closes, bridge health.  
**Do not:** redeploy public dashboard, thrash Cloud Run, ARM L2, live money, Hermes sends.

**Monorepo HEAD to pull first:**

```bash
cd ~/Code/Sapphire   # or E:\Sapphire\Code\Sapphire
git pull --ff-only origin main
# expect free-reign gate: lib/grok/free_reign_gate.py
# plant recipe: projects/grok/PLANT_WIRE_POLICY.md
# smoke: python3 scripts/ops/grok_paper_proposal_smoke.py
```

---

## Prompt A — Primary (paste first): free-reign sole-writer gate

```text
You are Claude on the Mac plant for Sapphire (local-first control tower).

MISSION (this turn only):
Wire the monorepo free-reign pre-check into the plant sole-writer path so every
designated-rail proposal is evaluated BEFORE order submit. Paper-safe integration
first; do not ARM L2; do not place live orders from this session unless already
armed by the operator with an attended gate.

READ FIRST:
- projects/grok/PLANT_WIRE_POLICY.md
- lib/grok/free_reign_gate.py
- lib/grok/policy.py (reference only)
- data/grok-web-exports/2026-08-06_free-reign-gate-ready.md
- data/grok-web-exports/2026-08-06_plant-wire-receipt.md (bridge already green)

DO:
1. git pull --ff-only origin main
2. Run: python3 scripts/ops/grok_paper_proposal_smoke.py  (must pass)
3. Find the free-reign / easy_mode / rh-chain / agentic decision path that is the
   sole writer for designated rails (search ops-state finish-line, agents,
   services — prefer the path that already respects dens/killswitch).
4. Import and call:

   from lib.grok.free_reign_gate import GateRequest, gate_order
   result = gate_order(GateRequest(
       symbol=..., side=..., rail=...,  # rh_agentic|rh_l2|moss|paper
       asset_class=..., notional_usd=...,
       open_positions_on_rail=...,
       contract_address=...,  # L2
       moss_grant_hours_left=...,
       is_defined_risk_option=...,  # long premium options
   ))
   if not result.allowed:
       log structured denial (code, reason); return NO_TRADE
   # else existing confirmation_firewall / sole writer continues

5. Map plant rail names → GateRequest.rail exactly as above.
6. Permanent dens (SONNY/BINGBONG class), dust no-rebuy, L2 ≤$10 / max 1 open,
   MOSS grant hours_left > 0, AXTI defined-risk options — already encoded; do not
   re-implement in plant JSON only.
7. Add a tiny plant-local unit/smoke if you have a harness; otherwise document
   the call site path in a local-export markdown under data/grok-web-exports/:
   YYYY-MM-DD_local-export_free-reign-gate-wired.md
8. Commit plant-side + monorepo export with explicit paths (no git add -A).
   Message: local-export: free-reign gate_order wired [2026-08-06]

FENCES:
- No live order placement from this wire session
- No L2 schtask ARM
- No Telegram/Hermes sends
- No secret dumps
- No sapphire-alpha-dashboard / Cloud Run work (Gemini owns that)
- Models still only propose; gate is pre-check only

DONE WHEN:
- Call site exists and denials log code (DENS_BLOCK, L2_NOTIONAL_CAP, etc.)
- Smoke suite still passes
- local-export receipt on main or plant ops-state + monorepo export
- Short report: file paths touched + example denial codes observed in dry-run
```

---

## Prompt B — Genome closes (after A, or parallel agent)

```text
You are Claude on the Mac plant for Sapphire.

MISSION: Wire closed-trade → genome lessons so self-improve is not wins=0/losses=0.

READ:
- lib/grok/plant_outcomes.py
- lib/grok/genome.py
- projects/grok/data/genome_seed_lessons.json (seed shape)
- projects/grok/PLANT_WIRE_POLICY.md (Closed trade section)

DO:
1. git pull --ff-only
2. Choose a durable plant path for lessons, e.g.
   ~/ops-state/genome/lessons.json  (create dir; do not put secrets in it)
3. On broker-reconciled close (RH agentic options, L2 paper/live closes, dust
   exits), call:

   from pathlib import Path
   from lib.grok.plant_outcomes import record_closed_trade
   record_closed_trade(
       Path.home() / "ops-state/genome/lessons.json",
       trade_id=..., symbol=..., rail=...,
       realized_pnl_usd=..., source="broker",
       tags=[...], thesis=optional,
   )

4. Seed once if file missing: LessonBook.seed_axti_and_dens() then save
   (AXTI +$175 + dens permanent lesson already in monorepo seed).
5. Optional: Telegram /summary later — NOT this turn.
6. local-export: genome closes wired [date] under data/grok-web-exports/

FENCES: no live orders; no ARM; no dashboard deploy.

DONE WHEN: one dry-run append works; file has count>=1; export committed.
```

---

## Prompt C — Bridge health only (if A/B blocked)

```text
You are Claude on the Mac plant.

MISSION: Verify Grok bridge stays green; do not rewrite monorepo sync tools.

CHECK:
1. launchctl list | grep grok-web-bridge   (or your LaunchAgent name)
2. bash ~/Code/Sapphire/scripts/ops/sync_grok_web_exports.sh --dry-run
   then one live sync if dry-run ok
3. curl -sS http://127.0.0.1:19998/health   # mac-bridge :19998
4. python3 ~/Code/Sapphire/scripts/ops/grok_bridge_status.py --write-manifest
5. make -C ~/Code/Sapphire grok-streamline

If broken: fix plant wrapper only (thin wrapper to scripts/ops/sync_grok_web_exports.sh).
Do not reimplement densify; do not touch free-reign money paths.
Export receipt: data/grok-web-exports/YYYY-MM-DD_local-export_bridge-health.md
```

---

## Prompt D — Windows P0 assist (only if operator is at Win or SSH works)

```text
You are Claude assisting Windows private DC P0 acceptance.

READ:
- docs/strategy/WINDOWS-DATACENTER-MASTERPLAN-2026-08-06.md
- lib/grok/windows.py
- projects/grok/data/windows_acceptance.json

DO:
1. Probe only: Tailscale, SSH BatchMode, Ollama aliases, sleep disabled,
   schtasks inventory (list, do not ARM), free-reign parity flags.
2. Write WIN-POST-BOOT style report under ops-state or monorepo web-export.
3. Update projects/grok/data/windows_acceptance.json booleans from REAL probes.
4. Evaluate: python3 -c "from lib.grok.windows import evaluate_windows_acceptance; ..."
5. arm_l2_allowed must stay false until ALL p0 true.

FENCES: do not enable L2 live schtasks; no money paths.
```

---

## Prompt E — Short “stay in your lane” for multi-agent Claude

```text
Lane split 2026-08-06:
- Gemini Cloud Shell = sapphirealpha.xyz + GCP cost (do not compete)
- Claude plant = free-reign gate_order + genome closes + bridge LaunchAgent health
- Grok web monorepo = policy/streamline already shipped (pull, don't rewrite)

Pull main. Prefer Prompt A. Report paths + denial codes. No L2 ARM.
```

---

## Operator cheat sheet

| Order | Prompt | Outcome |
|---|---|---|
| 1 | **A** | free-reign uses monorepo dens/AXTI/L2/MOSS gate |
| 2 | **B** | genome lessons on closes |
| 3 | **C** | bridge stays green while Gemini deploys site |
| 4 | **D** | Win P0 only if machine reachable |

Verify anytime:

```bash
python3 scripts/ops/grok_paper_proposal_smoke.py
make grok-streamline
make grok-loop
```
