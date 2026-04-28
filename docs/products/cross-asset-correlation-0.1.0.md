# Cross-Asset Correlation Matrix + Regime Detection 0.1.0

As of 2026-04-28, Sapphire can correlate signals across feeds, but the market
view also needs to correlate assets across venues and macro proxies. This
product surface adds an offline-safe, cache-first cross-asset intelligence layer
for crypto, equities, defensive assets, dollar proxies, volatility, and
Hyperliquid-derived assets. It answers a practical operator question: are the
assets moving together, are the usual relationships breaking, and what regime
label should downstream intelligence use?

## Surface

The 0.1.0 release ships four connected surfaces:

- A pure stdlib analytics package at `lib/cross_asset/`.
- A cache-first daemon entrypoint at `services/cross_asset/run.py`.
- An authenticated dashboard page at `/cross-asset`.
- A plugin tool pair at `plugins/claw-sapphire/tools/internal/cross_asset_intel.py`
  and `plugins/claw-sapphire/tools/cross_asset_intel.py`.

The analytics layer computes rolling Pearson, Spearman, and Kendall matrices
without numpy, pandas, scipy, or network access. Inputs are plain Python OHLCV
rows or close series. This keeps tests deterministic and makes the engine usable
from the daemon, dashboard, and plugin without importing trading-critical code.

## Universe

The default universe is intentionally broad but capped:

- Crypto: BTC, ETH, SOL.
- Equities: SPY, QQQ.
- Defensive and macro proxies: XAUUSD, DXY, CNY, JPY, VIX.
- Hyperliquid-derived assets: HYPE plus supported public-feed symbols.

`MAX_ASSETS_HARD` is 24, `MAX_WINDOW_DAYS` is 365, and long windows require at
least 30 observations. The default labels are `24h`, `7d`, and `30d`, expressed
internally as observation windows so the same engine works with hourly caches or
fixture rows.

## Matrix Methods

Pearson captures linear co-movement, Spearman captures monotonic co-movement
after rank transformation, and Kendall captures pairwise ordering agreement with
tie handling. Exposing all three matters because market data often changes
shape across regimes. Pearson may drop when beta compresses, while Spearman can
stay high if the directional ordering is intact. Kendall provides a more
conservative signal when the data is sparse or tied.

The dashboard defaults to the 7d Pearson matrix because it is the easiest
operator read: green cells represent positive co-movement, red cells represent
inverse co-movement, and neutral cells represent low or unavailable correlation.
The selectors expose the other windows and methods without recomputing through
live APIs.

## Breakdown Events

The engine also emits correlation breakdown events. A breakdown event compares a
pair's current rolling Pearson correlation against a trailing baseline. If the
current value moves more than the configured sigma threshold from its baseline
mean, the engine emits a deterministic event with:

- pair
- timestamp
- current correlation
- baseline mean
- baseline standard deviation
- z-score
- severity
- direction
- note

The default daemon writes these rows to `data/cross_asset/<date>/breakdowns.jsonl`.
Dashboard users see the active table on `/cross-asset`, and plugin callers can
query them through the `breakdowns` action.

## Regime Labels

The regime detector is deliberately deterministic in 0.1.0. It does not train a
model, does not depend on scikit-learn, and does not invent hidden states from
small samples. Instead, it computes interpretable metrics from the correlation
matrix and emits one of five labels:

- `risk_on_correlated`
- `risk_on_decorrelated`
- `risk_off_flight_to_dollar`
- `crisis_correlation_spike`
- `regime_uncertain`

`risk_on_correlated` means risk assets are moving together and dollar pressure
is not dominating. `risk_on_decorrelated` means risk assets retain some positive
relationship but dispersion is high enough that single-asset narratives matter.
`risk_off_flight_to_dollar` means risk assets remain connected but are moving
against the dollar bloc. `crisis_correlation_spike` means broad absolute
correlation is unusually high. `regime_uncertain` is the honest fallback for
mixed evidence, insufficient samples, or unavailable matrices.

Each label includes confidence, drivers, and metrics. Downstream tools should
consume the driver list rather than treating the label as a black box.

## Lead/Lag

The lead/lag view computes lagged Pearson correlations across pairs. Positive
lags mean the first asset leads the second by that many observations; negative
lags mean the second asset leads. The first release keeps this intentionally
simple and deterministic. It is not a predictive trading signal by itself. Its
job is to identify relationships worth deeper inspection, such as a public-feed
asset leading spot proxies or dollar proxies leading equity/crypto correlation
changes.

## Safety Posture

The system is cache-first and dry-run by default. Live adapters require both an
explicit live request and `SAPPHIRE_CROSS_ASSET_LIVE=1`. Tests do not make live
network calls. When cache rows are unavailable, adapters generate deterministic
synthetic OHLCV rows so the dashboard and plugin remain operational without
pretending the data is live.

This lane does not touch `lib/correlator`, the trading critical path,
Robinhood, order execution, or live Telegram delivery. It is an intelligence
surface only. The daemon can publish local event-bus events when asked, but the
default CLI path is safe for one-shot cache/dry-run operation.

## Operator Value

This product gives Sapphire an asset-relationship layer above feed-level signal
correlation. It makes the dashboard more useful during fast market transitions:
the operator can see when BTC/SPY correlation is stable, when ETH/SOL are
splitting from broader risk, when DXY pressure is dominating, and when broad
asset correlations are compressing into a crisis-like spike.

The product is also buyer-legible. It demonstrates that Sapphire can move from
raw signal ingestion to a portfolio-aware market map with provenance,
determinism, and clear safety gates. That is the right 0.1.0 shape: useful now,
bounded enough to trust, and structured for later integration with Tranche 3
correlated signal outputs.

## Worked Example

Suppose BTC, ETH, SOL, SPY, and QQQ are all positively correlated over the 7d
window, while DXY is near neutral. The regime detector labels the state
`risk_on_correlated`. In that environment, a BTC signal is less likely to be an
isolated BTC story and more likely to be part of a broader risk-asset move. The
dashboard heatmap makes that visible in a few seconds: risk cells cluster
green, dollar cells stay muted, and the regime driver says risk assets are
positively correlated.

Now suppose BTC/SPY drops from a +0.70 trailing relationship to +0.05 while
ETH/SOL remain correlated. The breakdown detector emits a BTC/SPY event with a
z-score and a severity. The dashboard does not tell the operator to trade. It
does something more useful: it says the usual macro beta relationship has
changed enough to deserve investigation. The operator can then compare the
breakdown against sovereign thesis, macro data, and signal-correlator outputs.

Finally, suppose most absolute correlations spike at once. That can happen when
markets sell everything liquid, when volatility dominates, or when a macro shock
compresses normal asset relationships. The detector labels this
`crisis_correlation_spike`. The correct product behavior is not aggressive
execution; it is escalation context. Sapphire should know when diversification
is failing and when the current narrative should be framed as a broad market
stress event.

## Buyer Questions This Answers

A diligence team will ask whether Sapphire understands market context or only
aggregates signals. This lane helps answer that question. It shows that the
system can distinguish feed agreement from asset agreement, and it can preserve
that distinction in a dashboard, daemon artifact, and plugin response.

A technical buyer will ask whether the result is reproducible. The answer is
yes. The core calculations are deterministic pure functions. Given the same
inputs and timestamp, the output is stable. No stochastic model is hiding inside
0.1.0 regime detection. That is a deliberate product choice: the first release
optimizes for operator trust and testability.

A risk buyer will ask whether this touches execution. The answer is no. It is
not in the trading critical path, does not place orders, does not change
position sizing, does not talk to Robinhood, and does not send operator
messages. It creates context that other surfaces can consume later.

An operations buyer will ask whether the data path can run without brittle
services. The answer is yes for baseline operation. Cache rows are preferred,
live mode is gated, and deterministic dry-run rows keep the UI honest when
market data is unavailable. The page should degrade to "unavailable" or
cache-derived context rather than failing closed with a stack trace.

## Future Direction

The obvious next step is to join this asset layer with the Tranche 3
signal-correlator output. That integration should happen in a separate pass so
the ownership boundary stays clean. A later release can ask whether
cross-source signal agreement is stronger or weaker under each asset regime,
whether certain feeds lead correlation breakdowns, and whether narrative
synthesis should change tone when `crisis_correlation_spike` is active.

Another future step is model-based regime detection. The current deterministic
labels are intentionally simple. A Gaussian mixture model or hidden Markov model
could be useful once there are enough local artifacts to backtest transitions.
That should be additive, not a replacement for the transparent heuristic label.
The heuristic can remain the fallback and the explanation layer even if a model
eventually supplies a second opinion.
