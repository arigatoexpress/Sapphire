# Event-Impact Modeling Runbook

**Surface:** `event_impact` plugin and `services/event_impact/build.py`  
**Version:** 0.1.0  
**Default posture:** read-only lookup; rebuild is operator-gated.

## Purpose

Event-Impact Modeling turns a curated corpus of historical events into a
lookup table of empirical market reactions. Operators use it to answer:
"when this kind of event happened before, what did BTC, ETH, SOL, SPY,
or gold usually do over the next 1 hour, 6 hours, 24 hours, and 7 days?"

The answer is context, not a trade. Sapphire should never route these
results directly to execution. The model exists to improve narrative
quality, macro awareness, and diligence evidence.

## Files

- `data/event_corpus/events.jsonl`: committed, cited corpus.
- `lib/event_impact/event_corpus.py`: loader, validation, dedupe.
- `lib/event_impact/impact_modeler.py`: reaction-window model.
- `lib/event_impact/lookup.py`: MacroEvent compatibility and fallback.
- `services/event_impact/build.py`: one-shot model builder.
- `plugins/claw-sapphire/tools/internal/event_impact.py`: stdin JSON tool.
- `docs/products/event-impact-modeling-0.1.0.md`: product narrative.

## Quick Status

List corpus coverage:

```bash
echo '{"action":"corpus"}' \
  | /usr/local/bin/python3 plugins/claw-sapphire/tools/internal/event_impact.py
```

Expected shape:

```json
{
  "ok": true,
  "count": 80,
  "categories": {
    "fomc_decision": 30,
    "etf_approval": 9
  }
}
```

Counts will change as the corpus grows. The important invariants are
that every required category is present and every event has a citation.

## Lookup

Lookup requires a built model file:

```bash
echo '{
  "action": "lookup",
  "model_path": "data/event_impact/model_2026-04-28.json",
  "event": {
    "title": "FOMC raises target range",
    "category": "fomc_decision",
    "sub_category": "rate_hike"
  },
  "asset": "BTC",
  "horizon_hours": 24
}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/internal/event_impact.py
```

If no exact profile exists, the lookup falls back to the category profile
where `sub_category="*"`. If no category profile exists, it returns
`matched_level="no_data"`, `n=0`, and a deliberately wide confidence
band. Do not suppress this. A no-data result is valuable evidence that
Sapphire is not fabricating precision.

## Rebuild

Rebuilds are disabled by default. To run one locally:

```bash
SAPPHIRE_EVENT_IMPACT_REBUILD=1 \
  /usr/local/bin/python3 services/event_impact/build.py \
  --asset BTC --asset ETH --asset SOL --asset SPY --asset GLD
```

The builder contacts the local OpenBB-compatible API at
`http://127.0.0.1:6900`. It does not contact broker APIs, wallets, or
trading venues. If OpenBB is unavailable, fix that runtime first or pass
a mocked fetcher in tests. The output lands under `data/event_impact/`
as `model_<date>.json` with a sibling `.envelope.json` provenance sidecar.

The plugin rebuild action also requires the env flag:

```bash
SAPPHIRE_EVENT_IMPACT_REBUILD=1 \
  echo '{"action":"rebuild","assets":["BTC","ETH"]}' \
  | /usr/local/bin/python3 plugins/claw-sapphire/tools/internal/event_impact.py
```

Prefer the script for operator rebuilds because it is easier to inspect
the command-line arguments and resulting path.

## Post-Corpus Audit

Use `services/event_impact/audit.py` to compare a fitted model snapshot
against held-out events that happened after the model cutoff. The helper
is deterministic and offline: it reads a model JSON file, a held-out event
JSONL file using the same corpus schema, and a local OHLCV JSON file keyed
by asset. It does not call OpenBB, brokers, wallets, trading venues, or
external APIs.

```bash
/usr/local/bin/python3 services/event_impact/audit.py \
  --model data/event_impact/model_2026-04-28.json \
  --events scratch/event_impact/post_corpus_events.jsonl \
  --bars-json scratch/event_impact/post_corpus_bars.json \
  --horizon 6 \
  --horizon 24 \
  --output scratch/event_impact/post_corpus_audit.json
```

Expected `bars-json` shape:

```json
{
  "BTC": [
    {"timestamp": "2026-05-01T18:00:00+00:00", "close": 64000.0},
    {"timestamp": "2026-05-02T18:00:00+00:00", "close": 65200.0}
  ]
}
```

The report includes row-level expected reaction fields, realized return,
sign correctness, confidence-interval containment, and unscored reasons
such as `missing_price_window`, `no_model_profile`, or
`neutral_prediction_or_actual`. Treat low accuracy as a calibration signal,
not a trade instruction. True live validation still requires operator-curated
post-corpus events, locally captured OHLCV, and a separate review that the
events were not used in the fitted model.

The same helper is exposed through the plugin for Hermes/scheduled-task
integration without adding network access:

```bash
echo '{
  "action": "post-corpus-audit",
  "model_path": "data/event_impact/model_2026-04-28.json",
  "events_path": "scratch/event_impact/post_corpus_events.jsonl",
  "bars_json": "scratch/event_impact/post_corpus_bars.json",
  "horizons_hours": [6, 24]
}' | /usr/local/bin/python3 plugins/claw-sapphire/tools/internal/event_impact.py
```

The plugin path delegates to `services.event_impact.audit`; it does not rebuild
models, fetch OHLCV, or publish events. Use it when an operator wants the same
offline audit report through the plugin contract instead of a direct script
call.

## Verification

Focused tests:

```bash
/usr/local/bin/python3 -m pytest \
  tests/unit/test_event_corpus.py \
  tests/unit/test_impact_modeler.py \
  tests/unit/test_event_impact_lookup.py \
  tests/unit/test_event_impact_post_corpus_audit.py \
  plugins/claw-sapphire/tests/test_event_impact.py \
  -q --tb=short
```

Registry check:

```bash
/usr/local/bin/python3 scripts/validate_tool_registry.py
```

Full lane gate before PR:

```bash
ruff check .
/usr/local/bin/python3 -m pytest tests/unit/ -q --tb=short
/usr/local/bin/python3 -m pytest plugins/claw-sapphire/tests/ -q --tb=short
/usr/local/bin/python3 scripts/validate_tool_registry.py
/usr/local/bin/python3 scripts/ops/production_readiness_sweep.py --no-external | tail -5
```

Keep the unit and plugin pytest blocks separate. Sapphire has documented
test-tree import collisions when they are co-invoked.

## Corpus Maintenance

Add one JSON object per line. Required fields:

```json
{
  "event_id": "stable_snake_case_id",
  "timestamp": "2024-01-10T21:00:00+00:00",
  "category": "etf_approval",
  "sub_category": "spot_btc_etf_approval",
  "title": "SEC approves spot Bitcoin ETP exchange rule changes",
  "assets": ["BTC", "ETH"],
  "magnitude": null,
  "metadata": {
    "source_url": "https://www.sec.gov/...",
    "source_name": "SEC statement",
    "as_of": "2026-04-28"
  }
}
```

Rules:

- Use first-party or primary-ish sources whenever possible.
- Do not add uncited rows.
- Do not include failed venue tokens as benchmark assets unless you
  explicitly annotate survivorship risk in metadata.
- Prefer UTC timestamps.
- Keep `event_id` stable forever. If a title improves, edit the title
  but keep the id.

## Interpreting Output

`direction_consensus` is a sign agreement metric, not a probability.
`+1.0` means every sample return was positive. `-1.0` means every sample
return was negative. Values near zero mean the sample had mixed signs.

`confidence` in the lookup result is derived from sample size:

- `medium`: `n >= 20`
- `low`: `5 <= n < 20`
- `very_low`: `1 <= n < 5`
- `none`: no matched historical data

This is intentionally blunt. It keeps the model honest until there are
enough events to justify a richer calibration layer.

## Failure Modes

If lookup says no model exists, either pass `model_path` or run a rebuild.
Do not patch the plugin to invent defaults.

If model profiles are missing for an asset, inspect OpenBB data coverage
and the event corpus assets. Missing SOL history before the asset existed
is normal. Missing BTC history for major modern events is not.

If a confidence interval is very wide, check `n` and `notes`. Wide bands
are expected for ETF approvals and rare exchange failures. They are a
warning against overfitting, not a bug.

If the provenance sidecar is missing, re-run the builder and verify that
`lib/core/provenance.py` is importable from the worktree.

## Rollback

This lane is easy to roll back because it is additive. Remove the plugin
registry entry, stop calling the plugin, or revert the PR. No LaunchAgent
is installed and no live service is mutated by default.

## Integration Notes

The integration pass should wire `macro.event.detected` to this lookup
and emit `event.expected_reaction.published`. The payload should include
the original macro event id, asset, horizon, matched level, sample size,
and confidence interval. The narrative engine should consume that event
as supporting context only, with the no-data and small-sample notes
included in the caveat block.

## Operator Checklist Before Publishing A Model

Before a model is treated as the current Sapphire prior, run the focused
tests, run the registry validator, and inspect the corpus diff. The
corpus diff matters because a single timestamp error can change a reaction
window. For FOMC events, verify the timestamp is anchored to the statement
release time rather than the press conference. For ETF and regulatory
events, verify whether the event happened during or after U.S. market
hours. For crypto hacks, prefer the first public disclosure time when
available; if the exact time is unknown, make that uncertainty clear in
the title or metadata.

After the model file is produced, check that the sidecar exists:

```bash
ls data/event_impact/model_*.json.envelope.json
```

Then sample three lookups manually: one exact match, one category fallback,
and one no-data result. A healthy model should make all three states easy
to understand. If the no-data result is missing, add a test case before
publishing, because downstream narrative code depends on that fail-closed
shape.

## Data Hygiene Notes

Do not use social-media rumors as corpus rows. They can become separate
signal-source inputs, but the event-impact corpus is reserved for events
with durable public documentation. Do not add rows solely because the
market moved that day; that introduces look-ahead bias. Start with the
event, then measure the reaction.

Avoid duplicate rows for the same economic event unless each row represents
a distinct public milestone. For example, a spot ETF lifecycle can have a
filing, a court ruling, an approval order, and a first-trade date. Those
are distinct. Five news articles repeating the same approval are not.

When adding new assets, require enough OHLCV coverage before relying on
the result. It is acceptable for lookup to return no data for a new asset.
It is not acceptable to backfill synthetic history and present it as a
measured market reaction.

## Dashboard Guidance

If this surface is shown on a dashboard, render the sample size and
confidence band as first-class fields. Do not hide them behind a hover
state. The user should see immediately whether the number is a strong
historical prior or a thin contextual hint. In acquisition demos, this
honesty is a selling point: the system tells the buyer when it knows, and
just as importantly, when it does not.
