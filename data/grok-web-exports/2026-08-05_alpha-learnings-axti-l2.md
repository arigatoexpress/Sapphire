# Alpha learnings — AXTI win + L2/chain losses

**Updated:** 2026-08-05T23:15Z  
**Ticker note:** User said “AXIT”; broker chain is **AXTI** (American Axle) Aug-7-2026 **$80 calls**.

## The win (actionable alpha — repeatable)

| Leg | When | Action | Price | Premium | Agent |
|---|---|---|---:|---:|---|
| Open | 2026-07-31 | Buy **2** AXTI 8/7 **80c** | $0.70 | $140 | **agentic** |
| Scale-out | 2026-08-03 | Sell **1** (close) | $2.25 | $225 | user |
| Scale-out | 2026-08-04 | Sell **1** (close) | $0.90 | $90 | user |

**Realized (broker PnL hub):** +$155 + +$20 = **+$175** on $140 risk (~**+125%**).  
**Expired:** 2026-08-07 — **sold both before expiry** (theta avoided).

### Playbook rules (encode into free-reign / risk)

1. **Defined risk first** — long options (premium is max loss), not dust equity sleeves.
2. **Event / catalyst window** — short-dated OTM calls with a thesis, not “hold forever.”
3. **Gamma > theta** — take profits on **spikes** (here 0.70 → 2.25 ≈ **3.2×** on first lot).
4. **Scale out** — sell partials into strength; don’t need 100% top-tick.
5. **Never hold through worthless decay** — exit before expiry when edge is gone.
6. **Agentic open + human/agent scale-out** is a valid hybrid; automate scale-out next (TP ladder: half at **2×**, trail rest, hard SL **−40%** premium).

## The losses (L2 / meme / chain) — never again

| Failure | Lesson |
|---|---|
| **SONNY / BINGBONG** honeypot dens | Permanent denylist tickers **+ full + short `0x` addrs**; free_reign prefix match |
| Exit-illiquid bags | `block_exit_liquidity_fails=true` |
| Assassin / no flow-truth | Apex genome: min_apex 0.68, dens blocked_addrs, max stages/day |
| Paper L2 stop_loss churn (CATE, HOODSDAY, Nongwan) | Tight stops on illiquid memes = death by a thousand cuts; prefer dens + higher bar |
| Genome outcomes wins=0 losses=0 drains=0 | **Self-learn not wired** — now seed lessons[] from AXTI + dens |

### Genome / dens (live)

- Blocked addrs: BINGBONG, SONNY, + `0x9763…` (genome)
- `min_apex_score` 0.68 · `max_stages_per_day` 3 · size dust defaults small

## What free-reign multi-rail means now

| Rail | Policy |
|---|---|
| RH Agentic ••••8144 | Free-reign easy · options-first · dust sleeve placer **refuses** |
| RH Chain L2 | ON · **≤$10**/trade · max 1 open · dens enforced |
| MOSS / MegaETH | Session grant armed when hours_left > 0 · **renew grant ~1.5h** |

## Self-learning hooks to implement next

1. After every closed option/L2 trade → append genome.lessons + outcomes win/loss.
2. Risk loop: options half at 2× premium, trail, SL −40%.
3. Telegram `/summary` surfaces last AXTI-class wins + dens hits.

## Source truth

- RH MCP option orders + pnl_trade_history on `703758144` (2026-08-05 query)
- `rh-chain/paper-state.json` closed_recent stop_loss/take_profit
- `magnum-opus/state/genome.json`
