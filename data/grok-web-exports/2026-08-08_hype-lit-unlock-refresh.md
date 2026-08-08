---
source: grok-web
date: 2026-08-08
type: research
topics: [HYPE, LIT, unlocks, cluster-a, thesis, TH-02, TH-03]
title: HYPE + LIT unlock calendar refresh (no size-up)
---

# HYPE / LIT unlock refresh — 2026-08-08

**Status:** Research only. **No size-up** on crypto_risk_perp (HYPE+LIT) until re-underwrite complete.
**Sources:** Tokenomist, DefiLlama unlocks, Hyperliquid docs, secondary market notes (as of ~2026-08-08).

## Invariants (still hold)

- Cluster rule: HYPE + LIT sized as **one** crypto_risk_perp bet (OP-02).
- Thesis filter: real usage + value accrual + verifiability + Sapphire fit.
- Gate: free-reign L2 ≤$10 · HL signing disarmed by default · MOSS grant-gated.
- Do **not** treat unlock calendars as trade signals alone — use as risk calendar.

---

## HYPE (Hyperliquid) — TH-02

### Mechanics

| Fact | Detail |
|---|---|
| Total supply | 1B HYPE |
| Contributor vesting | ~1y cliff then ~24m linear; monthly cadence often on the **6th** |
| Unstaking (spot transfer) | **7-day** unstaking queue (staking → spot); separate from vesting |
| Delegation lock | 1-day lock on delegations before undelegate |

### Observed cadence (2026)

DefiLlama-style core-contributor prints (illustrative, verify live):

| Approx date | HYPE amount | Notes |
|---|---:|---|
| 2026-06-06 | ~202k | Core contributors |
| 2026-07-06 | ~452k | Core contributors |
| 2026-08-05 | ~433k | Core contributors (~$23–24M class prints at then-prices) |

Tokenomist (2026-08-08): **next scheduled unlock ~2026-09-06**, order of **~9.92M HYPE** (verify before acting — third-party trackers disagree on exact notional).

### Unstake vs unlock (critical distinction)

- **Vesting unlock** = tokens leave lock contracts / contributor schedule.
- **Unstaking queue** = already-circulating or unlocked tokens moving staking → spot (7d). Large unstake queues can hit float without a “vesting event” label.
- July 2026 saw separate large **unstake** headlines (~$150–200M class) — treat queue depth as a live risk feed, not only the 6th-of-month vesting calendar.

### Re-underwrite checklist (before any size-up)

1. Confirm next 30/60/90d unlock **amounts + wallets** on a primary tracker (DefiLlama + Tokenomist + on-chain).
2. Read **7d unstaking queue** depth vs ADV.
3. Check fee → burn / HIP-3 / product narrative still intact.
4. Cluster cap: HYPE + LIT one risk unit; no stacked max size on both.
5. No free-reign ambient HL signing (AU-05 / HL_SIGNING_GATE stays disarmed).

**Verdict (2026-08-08):** Monthly supply pressure is **routine and ongoing** into 2027. Overhang risk is **managed calendar risk**, not a one-shot cliff. Still **no size-up** until checklist passes after RH session is healthy and desk is honest.

---

## LIT (Lighter) — TH-03

### Mechanics (consensus of trackers)

| Allocation | Approx share | Vesting |
|---|---:|---|
| Airdrop | ~25% (250M) | Mostly at TGE (~2025-12-30) |
| Team | ~26% (260M) | 1y cliff → **~3y linear** |
| Investors | ~24% (240M) | 1y cliff → **~3y linear** |
| Other / remaining | remainder | verify primary docs |

### The Dec 2026 cliff (the old “LIT Dec cliff”)

- **~2026-12-28 → 2026-12-30**: insider cliff end; linear unlocks **begin** (team + investors).
- After cliff: trackers show **~hundreds of thousands LIT/day** combined team+investor linear (~$1M/day class at mid-2026 prices — **price-dependent**, recompute live).
- Linear runs multi-year into **~2029**.

This is the opposite of a single-day dump of full team supply: it is a **multi-year grind** that **starts** late Dec 2026.

### Re-underwrite checklist

1. Primary vesting doc vs DefiLlama/Tokenomist (amounts, start date).
2. Buyback / burn / fee-share health after the 2026 fee compression notes (Milk Road-class commentary: buybacks can weaken if fees drop).
3. Robinhood distribution / RWA collateral narrative still valid?
4. Cluster with HYPE — do not double-count perp-DEX beta.

**Verdict (2026-08-08):** Dec 2026 remains the **start of insider linear**, not a full unlock day. Still research-only; size-up blocked until cliff approach (~T-30) re-underwrite.

---

## Plant / monorepo actions (non-money)

| Action | Owner | Notes |
|---|---|---|
| Keep TH-02/TH-03 calendars in densify knowledge | plant densify | This export |
| Blindspot BS-HYPE-LIT → research_refresh | monorepo | Partial until checklists done |
| No free-reign size-up on HYPE/LIT cluster | policy | Already correct |
| Optional: research worker watchlist row | Win research_worker | After Win P0 |

## Falsifiers (kill narrative size-up)

- Unlock/unstake prints >> ADV for multiple sessions without absorption
- Protocol fee collapse + buyback failure (LIT)
- HL signing armed ambiently (policy breach)
- Correlated perp-DEX drawdown without hedges

## Sources (re-run dates)

- Tokenomist Hyperliquid page (2026-08-08)
- DefiLlama unlocks/hyperliquid + unlocks/lighter (2026-08-08)
- Hyperliquid staking docs (7d unstaking queue)
- Secondary: June–Aug 2026 unlock/unstake market notes

**Not investment advice. Research artifact for Sapphire risk calendar only.**
