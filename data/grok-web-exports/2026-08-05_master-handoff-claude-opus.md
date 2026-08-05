# MASTER HANDOFF — Claude Opus

**Generated:** 2026-08-05T23:05Z (MDT evening) by Grok 4.5 (local Grok Build session)  
**Audience:** Claude Opus (or any senior agent resuming after Claude/Codex credit exhaustion)  
**Owner:** Ari (@arigatoexpress)  
**Doctrine:** Local-first plant truth > Grok web UI. Read this whole file before acting.

---

## 0) One-screen status (NOW)

| Domain | State |
|---|---|
| **Agentic brokerage** RH `703758144` ••••8144 | **EXITS_QUEUED** — 4 market sells of boring dust for next RTH open |
| **Mandate** | `asymmetric_only` — defined-risk options preferred; no dust sleeve; no L2 memes |
| **Plant** | SHIPPED=True · deck http://127.0.0.1:8100/ · API :8099 · goldens ~432 pass (telegram-bot) |
| **Win desk** | **OFFLINE** ~10h+ (`192.168.1.61` / TS) — L2 executor not verifiable |
| **Grok web bridge** | **LIVE** on Sapphire `main` + MCP **write verified** (`21dfb864`) |
| **Overnight loops** | Keep-alive green · `all_done=true` under exit-armed plan |
| **Free-reign** | Just **re-hardened** in this handoff (had regressed to L2 $10 / allow_on_chain=true via ship_health) |

### Exit orders (live at broker — do not re-place)

| Sym | Qty | Side | State | order_id |
|---|---:|---|---|---|
| IBIT | 0.551267 | sell market GFD regular_hours | queued | `6a73b7da-1101-406f-9660-ff252e899336` |
| HOOD | 0.212833 | sell | queued | `6a73b7da-bcbf-41ae-9bf3-b91ebe2ca552` |
| PLTR | 0.123350 | sell | queued | `6a73b7da-41be-464a-ac03-b4b5d9bb62cf` |
| NVDA | 0.092140 | sell | queued | `6a73b7da-df71-44ca-bfa4-d567215cc7af` |

Fill cost basis (entry): IBIT @36.28 · HOOD @93.97 · PLTR @162.14 · NVDA @217.06 (~$80 sleeve).  
AH marks earlier were ~$79.4–80.4 (slight red).

**Plan file:** `~/ops-state/sovereign-desk/state/AGENTIC-TRADE-PLAN-LATEST.json`

---

## 1) Who is who (multi-agent fleet)

| Agent | Role | Notes |
|---|---|---|
| **Grok 4.5** (this session + Super Heavy orchestrator) | Primary cloud/ops brain post credit-out | Session continued from overnight compaction |
| **Claude / Codex** | Previously primary; **credits exhausted** | Resume from this handoff + `resume-claude` / `resume-codex` skills |
| **aider** | Local coder `codestral:22b` via :8800 gateway | `~/.aider.conf.yml` |
| **Hermes CLI** | Local general agent `deepseek-r1:8b` | Messaging **gateway FENCED** |
| **Ollama** (M4 Pro 24GB) | Local models | codestral, qwen coder, deepseek-r1, gemma3 weak, mxbai embed |
| **Ralph / densify / day-finish / overnight** | Cron + LaunchAgent plant loops | Self-heal :8099, mine artifacts, free-reign tick |
| **Win sovereign desk** | L2 executor + free-reign SSH | **Down** — Mac RH MCP path independent |

Standing rules: `~/Agents.md` (and repo AGENTS.md). **Karpathy charter:** evals-as-spec, delete>add, surgical diffs, no `git add -A`.

---

## 2) Absolute fences (never violate)

1. **Rails only:** RH Agentic `703758144` / ••••8144 · L2 `0xc2B59C45d188862659B3b9a51ad04BA07f55c9EB` · MOSS session · paper.  
2. **Never:** THO / Project-Go-Forward client money · Hermes **messaging** outward send · auto DNS/prod deploy · private keys in model/git/logs.  
3. **Hedge-fund carve-out (Ari 2026-07-20):** full trade autonomy **only** on designated test/agentic wallets under caps + killswitch.  
4. **Telegram:** per-trade approval cards **retired** (2026-07-28). At most one idempotent notify + Open secure review.  
5. **git:** never `git add .` / `git add -A` — explicit paths only.  
6. **Hostile Darwin process tests:** not on shared Mac.  
7. Killswitch / pause files always win.

---

## 3) Narrative timeline (this arc)

### A. Overnight → morning (pre–asymmetric pivot)
- Mission: plant alpha + free OSS overnight + agentic sleeve after settle.
- **Dust sleeve placed overnight** as GFD market buys regular_hours: IBIT/HOOD/PLTR/NVDA **$20 each**.
- Filled ~09:30 ET open · sticky **FILLED** · residual cash $9.94 → $0.
- Overnight stack: goldens 74→432 surface, OSS models, bridge_sync, LaunchAgents.
- Plant issues: `:8099` hang / `acceptance_stale` thrash · soft refresh preferred · single-owner `kickstart -k` for wedged listener · watchdog soft-first + 15m throttle restart.
- Win offline all day (L2 not required for RH MCP fills).
- Morning GO: hold sleeve, no re-place (BP gate <$40).

### B. Day keep-alive (scheduled subagents)
Loops every 15–60m: overnight supervisor, Ralph n76–n104, night all-hands, day-finish, night goals.
- Pattern: plant self-heals; occasional healthz timeout / stale; **FILLED sticky** after keep-alive fix.
- Dependabot: merged **#1021** fast-uri (green CI); majors HOLD.
- MOSS grant was counting down (~9h → ~2h across day) — re-check on resume.
- Desk mode later: defend / reduce_aggression.

### C. User pivot (evening): “not boring equities / not L2 memes”
Ari rejected dust sleeve + L2 memes → want **asymmetric bets** + **automated PT/risk**.

**Executed:**
1. Closed **160** Brave tabs (job spam + plant dupe thrash).
2. **Queued full market sells** of IBIT/HOOD/PLTR/NVDA for next RTH open (fractional → market+regular_hours only).
3. Free-reign: L2 OFF, dust denylist, asymmetric_policy (had **regressed** via ship_health → **restored in this handoff**).
4. Built mandate + risk loop + RTH pipeline + night_goals sticky status + dust placer refuse.
5. Retrospective: fixed first-ship gaps (see §6).

### D. Grok web bridge (GitHub)
- MCP write initially **403** (read-only).
- Local agent committed + pushed: `f6879d40` then remote rewrite `7c858ff1`.
- Ari re-authed → MCP write **verified** with probe commit `21dfb864`.
- Path: `Sapphire/data/grok-web-exports/` → `sync_grok_web_exports.sh` → `~/Knowledge/0-Inbox/grok-web/` → feeds → `:8100`.

---

## 4) Code / scripts shipped (paths)

### Trading / asymmetric
| Path | Purpose |
|---|---|
| `~/ops-state/finish-line/scripts/agentic_asymmetric_risk.py` | TP **+75%** / SL **−40%** book; writes exit intents; LaunchAgent `com.ari.asymmetric-risk` (15m) |
| `~/ops-state/finish-line/scripts/agentic_asymmetric_rth.py` | Post-exit / RTH stage seeds (TSLA/COIN); refuse dust; LaunchAgent `com.ari.asymmetric-rth` |
| `~/ops-state/finish-line/scripts/night_goals_and_trades.py` | Sticky status: EXITS_QUEUED → EXITS_FILLED → ASYMMETRIC_READY; never READY_TO_PLACE dust under asymmetric |
| `~/ops-state/finish-line/scripts/place_agentic_rth.py` | **Hard refuse** if `mandate=asymmetric_only` or `exit_orders` present; bans dust symbol buys |
| `~/ops-state/finish-line/scripts/overnight_agentic_system.py` | exit_orders count as valid plan; money_done true while exits queued; inline keep-alive (no all_done flap) |
| `~/ops-state/finish-line/scripts/test_asymmetric_pivot.py` | 5 goldens for status machine + risk decide + refuse |
| `~/ops-state/telegram-bot/free_reign.py` | Permanent SONNY/BINGBONG dens; equity bans live in **JSON policy** (tests stay green) |
| `~/ops-state/telegram-bot/free-reign.json` | Production policy (keep in sync with sovereign-desk copy) |
| `~/ops-state/finish-line/scripts/watchdog_8099.sh` | Soft refresh first; hung listener → throttled `kickstart -k` |

### Bridge
| Path | Purpose |
|---|---|
| `~/Code/Sapphire/data/grok-web-exports/` | Shared MD store on git main |
| `~/ops-state/finish-line/scripts/sync_grok_web_exports.sh` | pull + rsync → Knowledge inbox + publish feeds |
| Hooks | densify, Ralph, overnight, night all-hands |

### State / reports (read these)
| Path | What |
|---|---|
| `sovereign-desk/state/AGENTIC-TRADE-PLAN-LATEST.json` | Live plan + exit_orders + candidates |
| `sovereign-desk/state/asymmetric-book.json` | Open asymmetric positions for risk loop |
| `sovereign-desk/state/asymmetric-candidates.json` | Staged TSLA/COIN seeds |
| `finish-line/reports/ASYMMETRIC-MANDATE-LATEST.md` | Mandate |
| `finish-line/reports/ASYMMETRIC-PIVOT-LATEST.md` | Exit receipt |
| `finish-line/reports/ASYMMETRIC-RETROSPECTIVE-LATEST.md` | What we fixed second pass |
| `finish-line/reports/ASYMMETRIC-RTH-LATEST.md` | Stage report |
| `finish-line/reports/GROK-WEB-BRIDGE-LATEST.md` | Bridge status |
| `finish-line/reports/MORNING-GO-LATEST.md` | Morning board (pre-pivot FILLED hold) |
| `agent-reports/ARTIFACT-MINE-LATEST.md` | Periodic mine |
| `agent-reports/GROK-DAY-FINISH-STATUS.md` | Day-finish board |
| `finish-line/state/overnight-agentic/overnight-done.json` | Done gates |

### Sapphire commits (bridge)
- `21dfb864` web-export: connector write-probe + bridge live confirm [2026-08-05]
- `7c858ff1` / `f6879d40` web-export: initialize grok-web-exports bridge folder + README [2026-08-05]

---

## 5) Plant ops map (Mac)

| Surface | URL / ID |
|---|---|
| Command deck | http://127.0.0.1:8100/ |
| Operator API | http://127.0.0.1:8099/healthz (`ok` or soft-heal stale) |
| **Not** UI | :8098 / :8085 |
| Controller | LaunchAgent `com.ari.sapphire-controller` |
| Overnight | `com.ari.overnight-agentic` |
| Watchdog 8099 | `com.ari.watchdog-8099` |
| Asymmetric risk/RTH | `com.ari.asymmetric-risk` · `com.ari.asymmetric-rth` |

**Known plant footgun:** densify / `ship_health` free_reign_harden has been rewriting free-reign back to **L2 $10 + allow_on_chain** and stripping dust denylist. **Just re-hardened at handoff.** Opus should either:
- make ship_health respect `asymmetric_policy` / L2=0, or  
- re-assert free-reign after every densify until fixed.

---

## 6) What Grok would do differently (done) vs still open

### Done (second pass)
- Sticky exit status machine (no dust re-arm).
- Dust placer refuse.
- Overnight gates understand EXITS_QUEUED.
- RTH stage pipeline + LaunchAgents.
- Pivot self-tests + 432 telegram goldens.

### Still open (Opus priority list)

1. **RTH open (next session ~09:30 ET)**  
   - Confirm 4 sells **filled** via RH MCP (`get_equity_orders` / positions empty).  
   - Inject BP: `RH_AGENTIC_BP=… python3 night_goals_and_trades.py` → expect `EXITS_FILLED` / `ASYMMETRIC_READY`.  
   - Update exit_orders states in plan JSON (or `agentic_asymmetric_rth.py mark-exits-filled` only if broker confirms).

2. **Place asymmetric probes (MCP)**  
   - Seeds: **TSLA** call ≤$30 premium · **COIN** call ≤$25 · 1 contract · defined max loss = premium.  
   - Workflow: chains → instruments → quotes → `review_option_order` → `place_option_order`.  
   - Then: `agentic_asymmetric_risk.py register SYM option 1 ENTRY RISK_USD [option_id]`.  
   - Prefer broker-side stop_market / take-profit after fill (risk loop still intent-first).

3. **Risk loop → real exits**  
   - Wire mark feed (quotes) into cycle.  
   - On TP/SL intent: place close via RH MCP (options sell-to-close).  
   - Do not leave intents as pure theater.

4. **Durable free-reign asymmetric policy**  
   - Stop ship_health / densify from re-enabling L2 memes.  
   - Keep Mac+Win free-reign in sync when Win returns (scp policy).

5. **Win host return**  
   - Census L2 bag · dump residual memes · leave `allow_on_chain=false` until Ari re-arms.  
   - Executor heartbeat verification.

6. **MOSS grant**  
   - Check hours_left / renew if expired.

7. **8099 thrash root cause**  
   - acceptance_stale / hang under densify load — soft heal works; reduce densify thrash if possible.

8. **Bridge content**  
   - Web Grok can push `web-export:` MD into `data/grok-web-exports/`; densify ingests.

---

## 7) Asymmetric mandate (authoritative)

| Prefer | Ban |
|---|---|
| Long options (L2 single-leg), defined max loss = premium | Boring large-cap dust sleeves (IBIT/HOOD/PLTR/NVDA style) |
| Event/catalyst 0–21 DTE, R:R ≥ 2:1 | L2 memes (SONNY/BINGBONG + free-reign denylist) |
| Auto TP **+75%** / SL **−40%** | Unbounded spot lottery |

**Sizing:** ≤$35 risk/idea · ≤$80 open · ≥$10 cash reserve.

**Account:** only `703758144` agentic_allowed. Option level 2.

---

## 8) Quick operator commands

```bash
# Plant
curl -sS -m 3 http://127.0.0.1:8099/healthz
open http://127.0.0.1:8100/

# Plan / goals
cat ~/ops-state/sovereign-desk/state/AGENTIC-TRADE-PLAN-LATEST.json | head -80
python3 ~/ops-state/finish-line/scripts/night_goals_and_trades.py
python3 ~/ops-state/finish-line/scripts/place_agentic_rth.py   # must REFUSE asymmetric

# Asymmetric
python3 ~/ops-state/finish-line/scripts/agentic_asymmetric_rth.py status
python3 ~/ops-state/finish-line/scripts/agentic_asymmetric_rth.py stage
python3 ~/ops-state/finish-line/scripts/agentic_asymmetric_risk.py status
python3 ~/ops-state/finish-line/scripts/test_asymmetric_pivot.py

# Bridge
bash ~/ops-state/finish-line/scripts/sync_grok_web_exports.sh
git -C ~/Code/Sapphire log -3 --oneline -- data/grok-web-exports

# Mine
python3 ~/ops-state/finish-line/scripts/mine_artifacts.py --days 2 --skip-win

# Goldens
cd ~/ops-state/telegram-bot && python3 -m pytest -q
```

### Soft-heal :8099
```bash
python3 ~/ops-state/sapphire-local-dashboard/refresh_snapshot.py
# if hung timeout >2m and throttle allows:
launchctl kickstart -k "gui/$(id -u)/com.ari.sapphire-controller"
```

---

## 9) Multi-agent continuity sources

| Source | Use |
|---|---|
| This file | **Primary resume** |
| `~/Agents.md` | Standing rules |
| `~/ops-state/MACHINE.md` | Living plant map (regenerate via machine_doc) |
| `~/.grok/sessions/**` + compaction segments | Full Grok tool traces (this session continued from compaction) |
| `~/.codex/sessions/**/rollout-*.jsonl` | Pre-credit Codex traces |
| `agent-reports/ARTIFACT-MINE-LATEST.md` | Distilled mines every ~30m |
| Skills | `sovereign-trading-stack`, `agentic-trading-rails`, `artifact-mine`, `resume-claude`, `resume-codex` |

Do **not** scrape Grok web UI for plant truth.

---

## 10) First 15 minutes for Claude Opus

1. Read this handoff + `AGENTIC-TRADE-PLAN-LATEST.json` + free-reign.json (confirm L2=0 / allow_on_chain=false).  
2. RH MCP: `get_accounts` / `get_equity_positions` / `get_equity_orders` on `703758144` — confirm sells still queued or filled.  
3. `curl` :8099 healthz · open :8100.  
4. If free-reign drifted again → re-apply asymmetric harden (or fix ship_health).  
5. Do **not** re-buy IBIT/HOOD/PLTR/NVDA. Do **not** place L2 memes.  
6. If market open and sells filled → proceed §6 step 2 (option probes under caps).  
7. Write a short `agent-reports/OPUS-RESUME-<stamp>.md` receipt after first beat.

---

## 11) Explicit non-goals right now

- THO / Project-Go-Forward deploy or DNS  
- Hermes messaging send  
- Reviving Telegram per-trade approval cards  
- Speculative platform extraction  
- Funding non-agentic RH accounts from agents  

---

## 12) Contact surface for Ari

- Prefer short status boards (like morning GO).  
- Autonomous on agentic rails under mandate; irreversible outward still gated.  
- If confused about money: **hold / exit-only / no new dust**.

---

*End master handoff. Ship receipt: Grok restored free-reign asymmetric harden at generation time because densify had regressed L2=$10.*


---

## 13) Post-handoff durable fix (Grok wrap 23:10Z)

`desk/easy_mode.py` **`free_reign_payload`** now reads sticky plan mandate:
- if `mandate=asymmetric_only` or exit_orders or `l2_memes_banned` → L2 cap **$0**, `allow_on_chain=false`, max_open **0**, dust denylist.
- Desk cycle can no longer wipe the pivot every ~few minutes.
- `ship_health` accepts max_open≤1 (0 is OK).

Verify after densify: `rg allow_on_chain ~/ops-state/rh-chain/free-reign.json` → false.
