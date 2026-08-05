# MASTER HANDOFF — Claude Opus

**Generated:** 2026-08-05T23:20Z · **Author:** Grok 4.5 (local) after Claude/Codex credit exhaustion  
**Owner:** Ari (@arigatoexpress)  
**Doctrine:** Local plant truth > Grok web UI. Read this file end-to-end before acting.

---

## 0) NOW board (single screen)

| Domain | State |
|---|---|
| **Mandate** | `free_reign_multi_rail` — free-reign ON all **designated** rails |
| **Agentic RH** `703758144` ••••8144 | **EXITS_QUEUED** — 4 market sells IBIT/HOOD/PLTR/NVDA for next RTH open |
| **Free-reign** | enabled · easy · **allow_on_chain=true** · L2 **≤$10** · dens SONNY/BINGBONG |
| **Alpha doctrine** | Options-first (**AXTI playbook**); no dust-sleeve program; dens on L2 |
| **MOSS / MegaETH** | LIVE armed · **~1.5h grant left** — **renew passkey ASAP** |
| **Win desk** | **OFFLINE** — L2 executor schtasks not verifiable from Mac |
| **Plant** | SHIPPED · deck `:8100` · API `:8099` · goldens green |
| **Grok web bridge** | LIVE on Sapphire `main` · MCP write verified |
| **Telegram** | **Central Terminal** (menu/commands pruned for away-from-home) |

### Exit orders (broker — do not re-place)

| Sym | Qty | order_id |
|---|---:|---|
| IBIT | 0.551267 | `6a73b7da-1101-406f-9660-ff252e899336` |
| HOOD | 0.212833 | `6a73b7da-bcbf-41ae-9bf3-b91ebe2ca552` |
| PLTR | 0.123350 | `6a73b7da-41be-464a-ac03-b4b5d9bb62cf` |
| NVDA | 0.092140 | `6a73b7da-df71-44ca-bfa4-d567215cc7af` |

Plan: `~/ops-state/sovereign-desk/state/AGENTIC-TRADE-PLAN-LATEST.json`

---

## 1) Why this handoff exists

Claude and Codex ran out of credits mid-fleet. Grok (local + web) continued overnight → day → evening:

1. Overnight OSS plant + agentic dust sleeve fill  
2. Day keep-alive (Ralph, densify, day-finish, 8099 self-heal)  
3. Evening pivot off boring equities / memes → options-first  
4. GitHub bridge for Grok web exports  
5. Free-reign re-armed multi-rail + AXTI alpha mining + MegaETH status  
6. Telegram as central away terminal  

---

## 2) Fleet map

| Agent | Role |
|---|---|
| **Grok 4.5** | Primary post-credit ops brain (this arc) |
| **Claude Opus** | Resume target — use this handoff |
| **Codex** | Pre-credit tool traces in `~/.codex/sessions` |
| **aider** | Local coder codestral:22b via :8800 |
| **Hermes CLI** | Local agent; **messaging gateway FENCED** |
| **Ollama** | Local models on M4 Pro 24GB |
| **Ralph / densify / overnight** | Plant loops LaunchAgents |
| **Win sovereign desk** | L2 schtasks traders — currently down |

Standing rules: `~/Agents.md` · Karpathy charter · never `git add -A`.

---

## 3) Absolute fences

1. Designated rails only: RH Agentic `703758144`, L2 `0xc2B5…c9EB`, MOSS `0xeeba…`, paper.  
2. Never THO / Project-Go-Forward money · Hermes messaging send · auto DNS/prod · keys in model/git.  
3. Hedge-fund carve-out: full trade autonomy **only** on designated test/agentic wallets under caps + killswitch.  
4. Telegram per-trade approval cards **retired** (2026-07-28).  
5. Hostile Darwin process tests not on shared Mac.

---

## 4) Full narrative (compressed)

### A. Overnight → morning
- Built overnight agentic system (plant + goldens + OSS + bridge gates).  
- Placed **$20×4** dust sleeve IBIT/HOOD/PLTR/NVDA GFD RTH → filled ~open.  
- Sticky FILLED · cash→0 · hold all day (BP gate).  
- 8099 thrash: soft refresh preferred; hung listener → throttled kickstart.  
- Keep-alive fix: no re-pend gates without inline verify.

### B. Day loops
- Ralph n76–n104, supervisor 15m, all-hands 45m, day-finish 60m.  
- Win offline all day. Dependabot #1021 merged (fast-uri).  
- MOSS grant clock ran down.

### C. Evening pivot (Ari: not dust / not L2 memes → later free-reign all rails)
1. Queued full **sells** of dust sleeve for next open.  
2. Built options-first + risk automation (TP+75% / SL−40%).  
3. Fixed desk cycle wiping free-reign (`easy_mode.free_reign_payload` sticky).  
4. Ari: free-reign ON all traders/wallets → mandate **`free_reign_multi_rail`** (L2 $10, dens, not hard-off).

### D. Bridge
- Local push then MCP write after re-auth.  
- `data/grok-web-exports/` → Knowledge inbox → densify/Ralph → `:8100`.

### E. Alpha truth (broker-backed)
**AXTI** (user said AXIT) Aug-7 **$80 calls**:  
agentic buy 2@0.70 → sell 1@2.25 (+$155) → sell 1@0.90 (+$20) = **+$175** before expiry.  
→ Playbook: defined-risk options, gamma scale-out, no theta death.

**L2 losses:** SONNY/BINGBONG dens, exit-illiquid, paper stop churn → dens + assassin bar.

---

## 5) Code shipped (paths)

| Path | Role |
|---|---|
| `finish-line/scripts/agentic_asymmetric_risk.py` | TP/SL book + intents · LA `com.ari.asymmetric-risk` |
| `finish-line/scripts/agentic_asymmetric_rth.py` | Stage option seeds post-exit · LA `com.ari.asymmetric-rth` |
| `finish-line/scripts/night_goals_and_trades.py` | Sticky plan status (exits / free-reign) |
| `finish-line/scripts/place_agentic_rth.py` | **Refuses dust sleeve** under multi-rail / exits |
| `finish-line/scripts/overnight_agentic_system.py` | Exit-aware done gates · inline keep-alive |
| `finish-line/scripts/sync_grok_web_exports.sh` | Web→Knowledge bridge |
| `finish-line/scripts/moss_megaeth_status.py` | MegaETH/MOSS status |
| `finish-line/scripts/watchdog_8099.sh` | Soft + throttled hard heal |
| `finish-line/scripts/test_asymmetric_pivot.py` | Pivot goldens |
| `sovereign-desk/desk/easy_mode.py` | Free-reign mirrors respect plan mandate |
| `telegram-bot/menu.py` + `sovereign_bot.py` | **Central Terminal** UX |
| `telegram-bot/free-reign.json` (+ rh-chain + desk mirrors) | Multi-rail policy |

### Reports / memory
- `agent-reports/MASTER-HANDOFF-CLAUDE-OPUS-LATEST.md` (this file)  
- `agent-reports/SESSION-WRAP-GROK-2026-08-05-LATEST.md`  
- `finish-line/reports/ALPHA-LEARNINGS-AXTI-L2-LATEST.md`  
- `finish-line/reports/ASYMMETRIC-*` · `GROK-WEB-BRIDGE-LATEST.md` · `MEGAETH-MOSS-STATUS-LATEST.md`  
- `ops-state/memory/2026-08-05-asymmetric-pivot-and-handoff.md`  
- Sapphire: `data/grok-web-exports/*` on `main`

---

## 6) Free-reign multi-rail (authoritative)

| Rail | Policy |
|---|---|
| RH Agentic | Free-reign easy · options-first · **no dust placer** |
| RH L2 | ON · **≤$10** · max 1 open · dens |
| MOSS/MegaETH | trade=true · grant-gated · **renew ~1.5h** |

**Dens:** SONNY, BINGBONG, short/full addrs, genome addrs, IBIT/HOOD/PLTR as free-reign spam block.  
**Alpha policy:** long options, gamma exit, AXTI playbook, auto TP/SL.

---

## 7) Telegram Central Terminal

- Home: **Ari Central Terminal**  
- Reply KB: `/bots` `/pending` `/do` · `/skin` `/orch` `/health` · `/summary` `/machine` `/menu`  
- Bot commands reordered for away desk + coders  
- **Redeploy/restart** Win telegram poller for command list refresh  
- Per-trade TG approval cards stay **dead**

---

## 8) First 20 minutes for Opus

1. Read this handoff + plan JSON + free-reign.json (aoc true, l2=10).  
2. RH MCP: confirm sells queued/filled on `703758144`.  
3. `curl :8099/healthz` · open `:8100`.  
4. **MOSS:** if hours_left < 2 → Ari passkey grant → `ONE-CLICK-AFTER-GRANT.sh`.  
5. Do **not** re-buy dust sleeve.  
6. After exit fills → AXTI-class option probes (defined risk, scale out 2×).  
7. Win up → ARM schtasks traders via `/bots`, verify executor HB.  
8. Write `agent-reports/OPUS-RESUME-<stamp>.md`.

### Commands
```bash
python3 ~/ops-state/finish-line/scripts/moss_megaeth_status.py
python3 ~/ops-state/finish-line/scripts/night_goals_and_trades.py
python3 ~/ops-state/finish-line/scripts/place_agentic_rth.py   # expect refuse_dust
bash ~/ops-state/finish-line/scripts/sync_grok_web_exports.sh
cd ~/ops-state/telegram-bot && python3 -m pytest -q
```

---

## 9) Repo consolidation (see also Code/REPO-CONSOLIDATION.md)

**Canonical live:**
- `~/Code/Sapphire` — monorepo + grok-web-exports  
- `~/ops-state` — plant state, finish-line scripts, telegram-bot, rh-chain, moss  
- `~/Code/Project-Go-Forward` — **THO client (FENCED)**  
- `~/Knowledge` — vault  

**Do not merge into Sapphire without extraction ≥2 call-sites:**  
ops-server-task\*, fleet-lease-task\*, quant-perps-\*, task0\* review drops.

**Archive candidates:** `*.RETIRED-*`, `desk-orchestrator-directive.RETIRED-*`, ops-state `task0*-hostile-review.*` worktrees.

---

## 10) Open work (priority)

| P0 | Confirm dust sells fill at RTH · MOSS grant renew |
| P1 | AXTI-class option open + automated scale-out (2× / −40%) |
| P2 | Win traders ARM + free-reign tick from Mac/Win |
| P3 | Wire genome.outcomes win/loss from closed trades |
| P4 | 8099 thrash root cause under densify |
| P5 | Continue archive of Code task\* debt per consolidation map |

---

## 11) Non-goals

THO deploy/DNS · Hermes messaging send · revive TG trade approval cards · blind major dep bumps.

---

*Grok multi-agent arc complete enough for Opus takeover. Plant on free-reign multi-rail + exit-armed dust.*


## CRITICAL: telegram-bot path (2026-08-05)

Live Mac bot tree was **misnamed** `telegram-bot.RETIRED-20260728-MAC` with
`ops-state/telegram-bot` as a **symlink** to it. Archive-by-name would break the plant.

**Canonical now:** real directory `~/ops-state/telegram-bot/` (not a symlink, not RETIRED).
Never archive paths named RETIRED without checking `readlink` / LaunchAgent WorkingDirectory.


## 12) Dual-surface Telegram + OSS mine (post handoff)

- **Trade Terminal** (`menu:trade`) vs **Command Center** (`menu:cc`) — BonkBot/Pengu UX clarity.
- Research: `finish-line/reports/TG-TERMINAL-OSS-MINE-LATEST.md` (PenguBot, BonkBot, OctoBot, Freqtrade patterns).
- Mine: paste-CA speed UX + position TP/SL cards + dual control (TG trade / web telemetry).
- Reject: custody of keys in chat; dens-free snipes.
