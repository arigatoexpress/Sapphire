# Event-Impact Modeling 0.1.0

**Status:** Tranche 4, Lane 7.  
**As of:** 2026-04-28.  
**Surface:** `lib/event_impact/`, `services/event_impact/build.py`, and the `event_impact` plugin tool.

## What This Enables

Sapphire already knows how to collect signals. The missing question was
empirical context: when a known class of event hits the tape, what has
usually happened to BTC, ETH, SOL, SPY, and gold in the next 1 hour, 6
hours, 24 hours, and 7 days? Event-Impact Modeling 0.1.0 turns that
question into a reproducible lookup table. It is not a trading system,
and it does not claim that the future will match the past. It gives the
narrative engine and the operator a grounded prior, with a visible
sample size and a deliberately wide confidence band when history is thin.

The core design is simple enough to audit. A curated JSONL corpus at
`data/event_corpus/events.jsonl` lists historical events with timestamps,
categories, affected assets, and source URLs. `lib/event_impact.impact_modeler`
takes that corpus plus OHLCV bars and computes close-to-close reaction
windows. The output is an `ImpactModel` containing one `ImpactProfile`
per `(category, sub_category, asset, horizon_hours)`, plus category-level
fallback profiles where `sub_category="*"`. `lib/event_impact.lookup`
then maps a new MacroEvent-like object to the best available profile.

That means Lane 3's macro daemon can emit "FOMC rate hike, BTC likely
affected" and Lane 7 can answer: historically, for this event class and
asset, the mean and median reactions were this wide, the sample size was
this small or large, and the model should be treated with this confidence.
The result is a context card, not an order ticket.

## Why It Matters For Acquisition Diligence

An acquirer will ask whether Sapphire is merely narrating market news or
whether it can connect events to market behavior. This lane makes the
answer concrete. The corpus is inspectable, the model is deterministic,
the sidecar provenance is written at build time, and every lookup reports
how much evidence it has. That is a materially better story than a hand
written playbook or a black-box model that cannot explain its priors.

The value is especially strong when paired with the Tranche 4 narrative
synthesis engine. A narrative that says "the next macro event is FOMC"
is useful. A narrative that says "the next macro event is FOMC; the
historical BTC 24-hour profile for comparable hikes has low confidence
because n is small and the 95% band is wide" is safer, more honest, and
more useful to a diligence reader. It helps the system sound like a
careful analyst rather than a momentum bot.

## Corpus Shape

Each event row has:

- `event_id`: stable id used for dedupe and sample traceability.
- `timestamp`: ISO-8601 UTC timestamp anchored to the public event time
  where possible.
- `category`: one of `fomc_decision`, `etf_approval`, `exchange_hack`,
  `regulatory_enforcement`, or `macro_shock`.
- `sub_category`: more specific bucket such as `rate_hike`,
  `spot_btc_etf_approval`, `bridge_exploit`, or `bank_failure`.
- `assets`: affected assets in normalized uppercase symbols.
- `magnitude`: optional scalar when the event has an obvious magnitude,
  such as basis points or approximate dollar amount.
- `metadata.source_url`: citation URL. Rows without an HTTP citation are
  rejected by `load_events`.

The initial corpus includes more than 80 events. FOMC events are anchored
to Federal Reserve calendars and press releases. ETF entries include
futures launches, the Grayscale court decision, U.S. spot Bitcoin ETF
approval, and U.S. spot Ether ETP approval milestones. Exchange and DeFi
incidents include Mt. Gox, Bitfinex, Coincheck, Binance, KuCoin, Poly
Network, Cream, Wormhole, Ronin, Nomad, FTX, Euler, Atomic Wallet, HTX,
and DMM Bitcoin. Regulatory entries include SEC, CFTC, DOJ, and Treasury
actions. Macro shocks include Brexit, COVID liquidity stress, Russia's
2022 invasion of Ukraine, hot CPI prints, Terra, SVB, and Bitcoin's
2024 halving.

The corpus is intentionally conservative. It excludes assets that ceased
to be liquid benchmarks unless an event explicitly annotates survivorship
risk. For example, FTX is retained as an exchange-failure event affecting
BTC, ETH, SOL, and broad market stress, but FTT is not used as a benchmark
reaction asset. That avoids an easy but misleading result: measuring a
failed exchange token after the failure is not the same as measuring
Bitcoin or ETH market response.

## Model Methodology

The modeler uses close prices. For a given event and horizon, it finds
the first bar at or after the event timestamp and the first bar at or
after `timestamp + horizon_hours`. The reaction is:

```text
(end.close - start.close) / start.close * 100
```

That decision is not perfect, but it is transparent. It works for hourly
bars, daily bars, and mocked unit-test bars without making assumptions
about exchange sessions. The build script can fetch local OpenBB bars,
but tests mock this path. No test depends on live network access.

For each bucket, the model reports:

- `mean_return_pct`
- `median_return_pct`
- `n`
- `stdev`
- `confidence_interval_95`
- `direction_consensus` between `-1` and `+1`
- `sample_event_ids`
- `notes`

Small samples are deliberately penalized. If the sample size is below
the configured tight-band threshold, the model forces a wide confidence
band and adds the note `small_sample_wide_band`. This prevents the system
from over-reading a tiny corpus. A sample of three ETF approvals can be
directionally interesting, but it cannot support a precise risk number.

## Worked Example: FOMC Rate Hike To BTC

Assume Lane 3 emits:

```json
{
  "title": "FOMC raises target range by 25 bps",
  "category": "fomc_decision",
  "sub_category": "rate_hike",
  "assets_likely_affected": ["BTC", "ETH", "SPY", "GLD"]
}
```

The plugin can look up BTC at a 24-hour horizon:

```bash
echo '{
  "action": "lookup",
  "event": {
    "category": "fomc_decision",
    "sub_category": "rate_hike",
    "title": "FOMC raises target range by 25 bps"
  },
  "asset": "BTC",
  "horizon_hours": 24,
  "model_path": "data/event_impact/model_2026-04-28.json"
}' | python3 plugins/claw-sapphire/tools/internal/event_impact.py
```

The response will say whether it matched the exact hike profile or fell
back to the broader FOMC category. If there is no model file yet, it
returns a clear error rather than inventing an answer. If no profile
exists for the asset or horizon, lookup returns a wide `[-100, 100]`
band, `n=0`, and `matched_level="no_data"`.

That wide no-data result is a feature. It tells the narrative engine not
to pretend that historical priors exist. The safest intelligence system
knows the difference between "history suggests" and "we do not know."

## Safety Posture

This lane is read-only with respect to trading. It writes model artifacts
under `data/event_impact/` only when the operator or automation explicitly
runs the build script. The plugin rebuild action is dry-run by default
and refuses to fetch OHLCV unless `SAPPHIRE_EVENT_IMPACT_REBUILD=1` is
set. There are no wallet keys, broker APIs, order paths, or live trading
flags in this surface.

The build script writes a provenance envelope sidecar via
`lib/core/provenance.py`. The sidecar includes the model artifact hash,
the source corpus hash, the generator, TTL, and metadata describing the
assets and lookback period used. Downstream dashboards can deep-link the
model file and verify that it was built from the committed corpus.

## Limits And Honest Caveats

The first limitation is event definition. A "rate hike" in 2022 does not
carry the same market context as a rate hike in 2018. The model does not
try to solve that with hidden features. It exposes the sample IDs so an
operator can inspect the set and decide whether the comparison is fair.

The second limitation is overlapping shocks. SVB, the March 2023 FOMC,
and emergency liquidity programs happened near one another. A close-to-close
reaction window cannot fully isolate causality. The model should be read
as "market reaction after event class" rather than "event caused exactly
this return."

The third limitation is data vendor coverage. The build script fetches
from a local OpenBB-compatible endpoint. If the local endpoint lacks SOL
history before a certain date, profiles for SOL will have smaller sample
sizes. The lookup layer is built to make that visible.

The fourth limitation is survivorship bias. Crypto venue failures and
token collapses are exactly where naive backtests lie. This corpus keeps
failed venue events but avoids fitting on failed venue tokens unless the
event explicitly annotates why that asset is a suitable benchmark.

## Cross-Lane Integration

Lane 3 will produce structured macro events. Lane 7 consumes the same
shape through `MacroEvent.from_any`, so the integration pass can wire the
macro daemon to event-impact lookup with minimal glue. Lane 1 can then
include the expected-reaction card in narrative theses. Lane 5 can monitor
event-impact outputs as another adversarial telemetry input, especially
when a claimed event lacks first-party provenance. Lane 2 can eventually
compare event reactions by regime, and Lane 8 can show whether smart-money
counterparties were already positioned before comparable historical events.

Version 0.1.0 is intentionally modest: a deterministic corpus, a plain
reaction model, and honest fallbacks. That is the right foundation for a
system whose first job is to explain the market without over-claiming.

## Buyer-Facing Reading Of The Result

The acquirer-relevant point is not that Sapphire has discovered a secret
law of markets. It has not, and this document should never imply that.
The point is that Sapphire now has a disciplined way to connect a live
event stream to historical priors while preserving uncertainty. That
discipline is what separates an intelligence product from a feed reader.
Every output can be traced back to a row in the corpus, a source URL, an
OHLCV slice, a model build timestamp, and a provenance sidecar. A diligence
team can reproduce the table, argue with the corpus, add events, or swap
the data vendor without changing the surrounding product contract.

That is also why the model avoids cleverness in 0.1.0. A machine learning
classifier would look more impressive in a demo, but it would be harder
to trust with a thin event set and overlapping market regimes. The first
version chooses auditability. Later versions can add regime conditioning,
volatility-normalized reactions, or Bayesian shrinkage once the corpus is
large enough to deserve them. Until then, the right product behavior is
to say, "this is the empirical prior, here is its sample size, and here is
how wide the uncertainty band is."
