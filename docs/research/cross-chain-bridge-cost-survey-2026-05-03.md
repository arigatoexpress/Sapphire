# Cross-Chain Bridge Cost Survey — USDC L2-L2 (2026-05-03)

**Status:** baseline calibration for `lib/trading/cross_chain_arb_backtest.py`
**Re-survey cadence:** monthly (refresh `BRIDGE_COST_TIERS` if any tier shifts > 0.5 bps)
**Next re-survey due:** 2026-06-03
**Generator:** `scripts/research/bridge_cost_survey.py`
**Raw quotes:** `data/research/bridge_quotes_2026-05-03.json`

## Why this exists

PR #606 (`lib/trading/cross_chain_arb_backtest.py`) hardcoded a **5 bps** round-trip
bridge cost assumption when projecting cross-chain Aave APY arb PnL. That number
came from a back-of-envelope guess against the Across docs. Live quotes show it
was ~3x too high for typical L2-L2 USDC sizes — which materially changes the
viability conclusion the backtest reports.

This document captures the baseline survey. The numbers feed the
`BRIDGE_COST_TIERS` constant in `lib/trading/cross_chain_arb_backtest.py`.

## Methodology

- **Pair:** USDC native (Arbitrum 0xaf88...5831 ↔ Optimism 0x0b2C...Ff85)
- **Notionals:** $1k, $10k, $100k
- **Directions:** ARB→OP and OP→ARB (both quoted; spreads ≤ 0.1 bps between dirs)
- **Mode:** read-only — quote APIs only, no actual bridging
- **Providers:** Across, Hop, Stargate, CCTP

For each (provider × notional × direction) we record:
- Fee in USD (computed from `amountIn - amountOut`)
- Fee in bps of notional
- Quoted finality time (from API or modeled from docs)

## Live quote table (2026-05-03 03:30 UTC)

| Provider | Direction | Notional | Fee USD | Fee bps | Finality (s) | Note |
|----------|-----------|----------|---------|---------|--------------|------|
| Across   | ARB→OP    | $1,000   | $0.1483 | 1.48    | 2            | one-way |
| Across   | ARB→OP    | $10,000  | $1.4842 | 1.48    | 2            | one-way |
| Across   | ARB→OP    | $100,000 | $15.19  | 1.52    | 120          | LP fee creep at size |
| Across   | OP→ARB    | $1,000   | $0.1546 | 1.55    | 2            | |
| Across   | OP→ARB    | $10,000  | $1.4907 | 1.49    | 2            | |
| Across   | OP→ARB    | $100,000 | $15.19  | 1.52    | 120          | |
| Hop      | ARB→OP    | $1,000   | $0.0100 | 0.10    | 120          | bonderFee only — see caveat |
| Hop      | ARB→OP    | $10,000  | $0.0100 | 0.01    | 120          | flat $0.01 across all sizes |
| Hop      | ARB→OP    | $100,000 | $0.0100 | 0.00    | 120          | |
| Stargate | (modeled) | all      | ~6 bps  | 6.00    | ~90          | ~6 bps protocol + ~$1 LZ gas |
| CCTP-v1  | both      | all      | ~$0.30  | varies  | ~900         | Circle native; near-zero fee, slow |

### Per-leg → round-trip

The backtest models a *round trip* (rebalance: bridge out, then bridge back at next
rebalance). Round-trip cost ≈ 2 × per-leg cost.

Across one-way at $10k = ~1.5 bps → round-trip ≈ **3.0 bps**.

### Caveats

- **Hop's $0.01 bonder fee is suspicious.** Their public quote API returns only the
  bonder reward, not the full hAMM destination-swap slippage on the destination
  chain's hToken pool. Real hAMM execution can add 1-3 bps under thin liquidity.
  We do **not** default to Hop's headline number — Across is the operational pick.
- **Stargate has no public quote-fees REST API.** Their on-chain `feeLibrary.getFees()`
  returns a precise number but requires a web3 call. We model their published
  v1 USDC pool fee schedule (6 bps protocol + ~$1 LZ gas).
- **CCTP is excluded from "fast economical" picks** despite its near-zero fee,
  because 13-19 minute finality is incompatible with daily rebalance cadence.
  Worth re-evaluating when Fast CCTP v2 is GA and battle-tested.

## Recommended defaults (BRIDGE_COST_TIERS)

```python
BRIDGE_COST_TIERS = (
    (10_000.0, 3.0),       # ≤ $10k:    Across ~1.5 bps × 2 legs
    (100_000.0, 3.5),      # ≤ $100k:   Across ~1.5-1.75 bps × 2 legs
    (1_000_000.0, 4.0),    # ≤ $1M:     Across ~2 bps × 2 legs
    (math.inf, 5.0),       # >  $1M:    legacy assumption (slippage dominates)
)
```

Per-tier picks chosen as:
- **Median fastest-economical** of providers with fee data + finality < 10 minutes
- Bias toward **Across** because of the cleanest public API + sub-2-min finality
- 0.5 bps headroom over the observed best to absorb typical per-snapshot variance

## Backtest viability — before vs after calibration

Two regimes shown. **Daily rebalance + 7-day decay** is the original
assumption from `_simulate_with_initial_spread`; **weekly rebalance, no decay** is
the operational regime where this strategy can actually work.

### Regime A: daily rebalance, 7-day decay, 30-day horizon, 232 bps initial spread

| Capital     | Legacy 5 bps net PnL | Calibrated net PnL | Conclusion          |
|-------------|----------------------|--------------------|---------------------|
| $10K        | -$222.78             | -$162.78           | unviable, less bad  |
| $100K       | -$1,552.75           | -$1,102.75         | unviable, less bad  |
| $1M         | -$14,852.53          | -$11,852.53        | unviable, less bad  |
| $10M        | -$147,850.34         | -$147,850.34       | unviable (whale tier same bps) |

Calibration **does not save daily rebalance + decay**. Costs still eat 50-70x
gross PnL. The structural problem is rebalancing 30 times into a spread that
decays to zero in 7 days.

### Regime B: weekly rebalance, no decay, 30-day horizon, 232 bps spread

| Capital  | Calibrated APR | Cost % gross | Verdict     |
|----------|----------------|--------------|-------------|
| $5K      | -1.85%         | 180%         | unviable    |
| $10K     | -0.55%         | 124%         | unviable    |
| $25K     | -0.03%         | 101%         | break-even  |
| $50K     | +0.23%         | 90%          | **VIABLE**  |
| $100K    | +0.36%         | 84%          | **VIABLE**  |
| $250K    | +0.18%         | 92%          | **VIABLE**  |
| $1M      | +0.22%         | 91%          | **VIABLE**  |

**This is the headline finding.** Under the legacy 5 bps assumption, weekly
rebalance + 232 bps spread + flat decay required >$1M to break even. Calibrated
costs drop the viability threshold to **~$50K**. At Sapphire's $10K operating
scale the strategy is still unviable, but the gap is now ~$40K of additional
capital, not ~$990K.

## Honest take

- Calibration moves the needle, but does not change the fundamental story: at
  Sapphire's $10K operating scale, USDC L2-L2 Aave APY arb does not pay for
  itself even with the cheapest available bridge.
- The viability threshold drops from "needs $1M+" to "needs ~$50K" under
  realistic operational assumptions (weekly rebal, persistent spread).
- The biggest viability lever remains rebalance frequency, not bridge cost.
  Daily rebalance amortizes 30+ round trips against an integral that depletes
  in 7 days; weekly rebalance keeps the integral mostly intact.
- For a grant readers' viability story: lead with the weekly-rebal regime, not
  the daily-rebal regime. The calibrated cost numbers (3-5 bps round-trip)
  reflect actual bridge-protocol economics — they are credible to anyone who
  has used Across or Hop in the last 6 months.

## Re-survey procedure

```bash
cd ~/Code/Sapphire
python3 scripts/research/bridge_cost_survey.py --json data/research/bridge_quotes_$(date +%Y-%m-%d).json
```

If any tier in the recommended defaults shifts more than **0.5 bps** versus the
prior month, update `BRIDGE_COST_TIERS` in `lib/trading/cross_chain_arb_backtest.py`
and re-run the existing test suite. The `test_calibrated_costs_lower_than_legacy_5bps_for_typical_capital`
test catches accidental regressions to or past the 5 bps legacy assumption.
