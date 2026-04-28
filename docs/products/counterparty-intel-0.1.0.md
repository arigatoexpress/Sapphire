# Counterparty Intel 0.1.0

**Status:** Tranche 4, Lane 8.  
**As of:** 2026-04-28.  
**Surface:** `lib/counterparty/`, `services/counterparty/run.py`, and the `counterparty_intel` plugin.

## What This Enables

Hyperliquid exposes unusually rich public trader and position data. That
does not mean Sapphire should deanonymize traders, scrape private keys, or
copy trades. It means Sapphire can observe public market structure: which
publicly visible high-PnL accounts are positioned in an asset, whether
several of them add to the same side in a short window, and whether that
public consensus corroborates or contradicts the rest of the Sapphire
signal stack.

Counterparty Intel 0.1.0 turns that into a small, bounded signal surface.
It ranks public traders by 30-day realized PnL, 90-day realized PnL, and
30-day Sharpe. It keeps the watchlist capped, ignores small noisy accounts
below the configured 30-day PnL floor, tracks open positions over time,
and emits a `CounterpartySignal` when material position changes agree by
asset and side.

The output shape is designed for the Tranche 3 correlator:

```json
{
  "asset": "BTC",
  "side": "long",
  "magnitude": 0.45,
  "traders_corroborating": 4,
  "smart_money_consensus": 0.62,
  "notional_delta_usd": 830000.0,
  "source": "hyperliquid-counterparty-intel"
}
```

This is an intelligence signal only. It is not a trade recommendation and
it is never connected to execution in this PR.

## Safety Posture

The surface is public-data-only and read-only. Live Hyperliquid API calls
require `SAPPHIRE_HYPERLIQUID_LIVE=1`, the same opt-in posture used by
the earlier Hyperliquid public-feed lane. Dry-run mode returns deterministic
mock leaderboard and position data without touching the network.

No wallet keys are loaded. No authenticated exchange endpoints are called.
No orders are created. No trader is deanonymized beyond the public address
or display handle the leaderboard already exposes.

Runtime caps:

- `MAX_TRADERS_TRACKED = 100`
- `MAX_REFRESH_PER_HOUR = 12`
- `MIN_TRADER_30D_PNL_USD = 50_000`
- `POSITION_CHANGE_SIGNAL_THRESHOLD_PCT = 15`

Refresh counters live under `~/.cache/sapphire/counterparty_intel/`. The
service writes local provenance-stamped snapshots under
`data/counterparty/<date>/counterparty_signals.json` when run.

## Why Buyers Care

Smart-money tracking is a known institutional crypto-intelligence pattern.
Nansen, Arkham-style dashboards, Whale Alert, and internal quant desks all
derive value from observing where large or historically successful public
participants are positioned. Sapphire’s differentiator is not that it
invented this idea. The differentiator is that this signal becomes one
bounded input among many: Telegram intel, macro context, on-chain regimes,
cross-asset regimes, event-impact priors, and adversarial detectors.

That compound context matters. A public trader adding BTC longs is weak
alone. A public trader cohort adding BTC longs while cross-asset regime
labels are risk-on, on-chain accumulation is improving, and macro-event
risk is quiet is a stronger narrative. Conversely, if the same move appears
during a suspected wash-trade or prompt-injected narrative window, the
adversarial layer can flag it.

## Implementation

`lib/counterparty/tracker.py` owns pure ranking and position-change logic.
The tracker accepts plain dicts so tests and future adapters can pass
fixture data without depending on Hyperliquid response stability. Position
changes are calculated from signed notional where available, or from
side plus notional otherwise. A flip from long to short is treated as a
large material change, not a small resize.

`lib/counterparty/signal_generator.py` groups position changes by asset and
side, counts unique corroborating traders, estimates a bounded magnitude,
and emits `CounterpartySignal` records.

`lib/counterparty/sources.py` is the live-gated public API client. It uses
stdlib HTTP only, returns dry-run mocks by default, and rate-limits live
refreshes locally.

`services/counterparty/run.py` is a one-shot daemon entry point. It refreshes
leaderboard and positions, writes a provenance-stamped snapshot, and can
optionally publish `counterparty.smart_money.move` events when called with
`--publish`. Publishing is not automatic.

## Limits

Public trader data can be noisy. A visible account can be hedged elsewhere,
can split positions across venues, or can deliberately bait copy-traders.
Sapphire should treat the signal as corroboration, not truth. The Lane 5
adversarial defense layer is the right companion: if public position moves
look coordinated, repetitive, or inconsistent with broader market data,
they should be downgraded.

The first version also does not persist a long-term trader reputation
database. It ranks the current leaderboard and compares current positions
against a caller-provided previous snapshot. A later version can add a
state store with rolling decay and trader-level reliability scores.

## Verification

The lane ships focused tests for ranking, position-change detection,
source dry-run/live gating, signal generation, and the plugin wrapper.
All tests mock external behavior. No live Hyperliquid call is required.

## Worked Example

Imagine the public leaderboard has three eligible accounts. Two increase
BTC long exposure by more than 15 percent, while one trims ETH shorts. The
tracker first converts the raw position payloads into normalized
`TraderPosition` rows. The position-change pass then compares old and new
signed notional by `(trader, asset)`. For BTC, both accounts produce
`PositionChange` records with `side="long"`. The signal generator groups
those changes and emits one BTC long consensus signal with two corroborating
traders. The ETH short trim becomes a separate context signal because it
has a different asset and side.

That grouping is important. Sapphire should not treat "one trader did
something" as the same kind of evidence as "several profitable public
traders moved in the same direction." The first is weak context. The
second is a candidate corroborating signal. Both still remain downstream
inputs, not orders.

## Integration Contract

The intended event topic is `counterparty.smart_money.move`. A payload
should include the normalized fields from `CounterpartySignal`, plus any
service-level provenance wrapper added during the integration pass. The
correlator can treat the signal as a source with configurable weight. The
narrative engine can render it as plain language, for example: "2 of the
top public Hyperliquid traders increased BTC long exposure in the latest
window." The adversarial layer can monitor the same topic for suspicious
coordination or bait patterns.

The integration pass should not change the safety posture. Publishing
events is fine after tests exist. Trading is not part of this surface.

## Future Version

A stronger 0.2.0 would add a persisted reputation ledger: trader-level
history, realized follow-through after position changes, decay for stale
performance, and demotion when a trader repeatedly creates false-positive
signals. It could also join cross-venue observations, but only if those
venues expose public data cleanly. Private exchange keys or deanonymization
would be out of scope.
