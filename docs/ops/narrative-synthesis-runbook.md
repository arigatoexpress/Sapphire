# Narrative Synthesis Runbook

This runbook covers operation of Sapphire Narrative Synthesis 0.1.0. The service turns correlated signal rows into provenance-stamped research theses. It is safe to run locally because the default mode is deterministic dry-run, event-bus publishing is off unless explicitly enabled, and live Gemini calls require multiple gates. It does not place trades, does not send Telegram messages, and does not write back to upstream signal sources.

## Components

The implementation has four parts:

- `lib/synthesis/narrative_engine.py`: core thesis generator, dry-run baseline, live Gemini gate, cache, counters, and provenance.
- `lib/synthesis/prompts.py`: prompt version, system prompt, schema, redaction helpers, and deterministic prompt rendering.
- `lib/synthesis/rubric.py`: deterministic publish rubric.
- `services/synthesis/run.py`: daemon and one-shot service runner.
- `plugins/claw-sapphire/tools/internal/narrative_synthesis.py`: stdin JSON plugin tool.
- `services/synthesis/launchagent/com.sapphire.narrative-synthesis.plist.template`: dry-run LaunchAgent template. Do not install automatically from an agent run.

The daemon reads correlator output from `data/correlated_signals/<YYYY-MM-DD>/signals.jsonl`. It writes publishable rows to `data/narratives/<YYYY-MM-DD>/theses.jsonl` and stamps an envelope sidecar next to the JSONL. State is stored under `~/.cache/sapphire/narrative_synthesis_service/last_edges.json`, which lets the daemon avoid re-emitting a thesis unless the edge score changes by more than the configured threshold.

## Safety Defaults

Default runtime posture:

- `mode=dry-run`;
- `SAPPHIRE_NARRATIVE_LIVE` unset or `0`;
- `SAPPHIRE_NARRATIVE_LIVE_BUS` unset or `0`;
- no Gemini key read;
- no Google network call;
- no Telegram send;
- no trading execution;
- no write to `data/correlated_signals`;
- no LaunchAgent install or load operation.

Live model calls require all of the following:

1. The caller requests `mode=live`.
2. `SAPPHIRE_NARRATIVE_LIVE=1` is set.
3. `GEMINI_API_KEY` or `GOOGLE_API_KEY` exists in `~/.sapphire/secrets.env` or process env.
4. The prompt passes the sensitivity classifier.
5. The live-call counter has fewer than 6 calls in the last hour.
6. The projected monthly token count remains at or below 750000.
7. The model response parses as JSON and can be coerced into a `NarrativeThesis`.

If a gate fails, the engine returns a deterministic thesis with the actual mode recorded. Expected fallback labels include `dry-run-blocked-by-env`, `dry-run-no-key`, `dry-run-safety`, `dry-run-rate-limited`, `dry-run-live-error`, and `dry-run-live-unparseable`.

## Common Commands

Run the daemon once:

```bash
python3 services/synthesis/run.py run-once
```

Run a dry-run daemon loop:

```bash
python3 services/synthesis/run.py daemon --mode dry-run --poll-interval-seconds 1800
```

Check service state:

```bash
python3 services/synthesis/run.py status
```

Generate one thesis from an inline signal:

```bash
echo '{"action":"synthesize-once","signal":{"symbol":"BTC","timeframe":"1h","edge_score":0.72,"consensus":"AGREE_BULL","contributing":4,"corroborated_by":["tradingview"],"bull_sources":["tradingview"],"bear_sources":[],"neutral_sources":[],"freshness_seconds":90,"raw_score":0.64,"agreement_multiplier":1.2,"contradict_factor":1.0,"total_weight":3.4}}' \
  | python3 plugins/claw-sapphire/tools/narrative_synthesis.py
```

Read latest narratives:

```bash
echo '{"action":"latest","limit":5}' | python3 plugins/claw-sapphire/tools/narrative_synthesis.py
```

Score a thesis:

```bash
echo '{"action":"rubric-score","thesis":{"thesis_one_paragraph":"...","evidence_bullets":["..."],"counter_thesis_one_paragraph":"...","invalidators":["..."],"next_signal_to_watch":"...","implied_position":"neutral","confidence":0.5,"caveat_block":"Research-only dry-run narrative.","provenance_envelope":{}}}' \
  | python3 plugins/claw-sapphire/tools/narrative_synthesis.py
```

## Service Behavior

On each tick, the service:

1. Reads the latest correlated signal row per `(symbol, timeframe)` pair.
2. Compares the row's `edge_score` with the last published edge in cache.
3. Selects rows whose absolute edge delta is greater than `0.10`, or rows that have no cached prior edge.
4. Calls `synthesize_thesis` in dry-run mode unless `--mode live` is requested.
5. Scores the thesis with `score_narrative`.
6. Writes only rows whose rubric score is at least `0.70`.
7. Updates `last_edges.json` only for publishable rows.
8. Publishes `narrative.thesis.generated` only if event-bus publishing is requested and `SAPPHIRE_NARRATIVE_LIVE_BUS=1` is set.

The return object includes `signals_seen`, `signals_changed`, `published_rows`, `dropped_rows`, `event_bus_published`, `output_path`, `min_edge_delta`, and `min_rubric_score_to_publish`.

## LaunchAgent Template

The checked-in plist is a template only:

```text
services/synthesis/launchagent/com.sapphire.narrative-synthesis.plist.template
```

It runs:

```text
/usr/local/bin/python3 /Users/aribs/Code/Sapphire/services/synthesis/run.py daemon --mode dry-run --poll-interval-seconds 1800
```

It sets:

```text
SAPPHIRE_NARRATIVE_LIVE=0
SAPPHIRE_NARRATIVE_LIVE_BUS=0
```

Do not load or unload LaunchAgents from an autonomous coding session. If Ari wants this installed, copy the template to `~/Library/LaunchAgents/com.sapphire.narrative-synthesis.plist`, inspect it, then use the normal macOS launchctl flow from an operator shell. Keep the canonical checkout path `/Users/aribs/Code/Sapphire` in the plist because local services run from that path after merge.

## Live Mode Procedure

Live mode should be rare and deliberate. Before enabling it:

1. Confirm the exact prompt need. Dry-run is usually enough for tests and routine notes.
2. Confirm the signal payload is paste-safe. Do not include secrets, account identifiers, customer data, Telegram tokens, or raw private logs.
3. Verify the key is present without printing it:

```bash
test -f ~/.sapphire/secrets.env && grep -E '^(GEMINI_API_KEY|GOOGLE_API_KEY)=' ~/.sapphire/secrets.env >/dev/null && echo key-present
```

4. Run status:

```bash
echo '{"action":"status"}' | python3 plugins/claw-sapphire/tools/narrative_synthesis.py
```

5. Run one live call only:

```bash
SAPPHIRE_NARRATIVE_LIVE=1 \
echo '{"action":"synthesize-once","mode":"live","signal":{...}}' \
  | python3 plugins/claw-sapphire/tools/narrative_synthesis.py
```

6. Inspect `mode_actual`, `rubric.overall`, `provenance_envelope`, and `metadata.publishable`.
7. Turn the env gate off again when finished.

Do not enable live mode in the LaunchAgent template by default. Do not enable event-bus publishing at the same time as a first live model test. Keep live model evaluation and local publication as separate operational changes.

## Troubleshooting

No output rows:

- Check whether `data/correlated_signals/<date>/signals.jsonl` exists.
- Check whether the edge changed by more than `0.10`.
- Check whether the rubric dropped the row.
- Run `python3 services/synthesis/run.py status` to see tracked pairs.

Mode is `dry-run-blocked-by-env`:

- The caller requested live mode, but `SAPPHIRE_NARRATIVE_LIVE=1` was not set. This is expected unless live mode was intentional.

Mode is `dry-run-no-key`:

- The live env gate was set, but no Gemini key was found. Do not print secrets while debugging. Check for key presence only.

Mode is `dry-run-safety`:

- The sensitivity classifier saw sensitive content. Remove the sensitive input or stay in dry-run. Do not bypass this gate for secrets, PII, tokens, private keys, cookies, or account credentials.

Mode is `dry-run-rate-limited`:

- The cache counter already has 6 live calls in the last hour or the monthly cap would be exceeded. Wait, lower usage, or stay in dry-run.

Plugin returns `no signal provided and no latest correlated signal found`:

- Pass an inline `signal` object or run the signal correlator first.

Combined core and plugin pytest fails with `ImportPathMismatchError`:

- Run the core and plugin tests separately. This is a known Sapphire test harness behavior caused by both suites having their own `tests/conftest.py`.

## Verification

Use these focused checks after changes:

```bash
python3 -m compileall -q lib/synthesis services/synthesis plugins/claw-sapphire/tools/internal/narrative_synthesis.py plugins/claw-sapphire/tools/narrative_synthesis.py
python3 -m pytest tests/unit/test_synthesis_narrative_engine.py tests/unit/test_synthesis_rubric.py tests/unit/test_synthesis_prompts.py tests/unit/test_synthesis_run.py -q
python3 -m pytest plugins/claw-sapphire/tests/test_narrative_synthesis.py -q
python3 scripts/validate_tool_registry.py
ruff check lib/synthesis services/synthesis plugins/claw-sapphire/tools/internal/narrative_synthesis.py plugins/claw-sapphire/tools/narrative_synthesis.py tests/unit/test_synthesis_narrative_engine.py tests/unit/test_synthesis_rubric.py tests/unit/test_synthesis_prompts.py tests/unit/test_synthesis_run.py plugins/claw-sapphire/tests/test_narrative_synthesis.py
git diff --check
```

Feasible broader Sapphire gates:

```bash
./scripts/check_required_secrets.sh
./scripts/autonomy_readiness_check.sh
python3 scripts/ops/org_status.py --no-external --markdown
python3 scripts/ops/safety_status_report.py --json
```

Those broader gates may report environment readiness rather than code failures. Treat missing local services, missing optional secrets, or protected external checks as operational status, not a reason to mutate secrets or production systems.

## Rollback

This feature is isolated. To rollback after merge, revert the PR commit. Before merge, delete the branch/worktree if abandoned. The runtime artifacts are append-only under `data/narratives/` and cache-only under `~/.cache/sapphire/narrative_synthesis*`; removing the LaunchAgent template from the repo reverts scheduled-service packaging. Because the default plist is only a template and live flags default to `0`, rollback does not require unloading a service unless an operator manually installed it outside the PR.

## Soak Plan

Use a staged soak before treating the narratives as a daily operating surface.

Day 1 should be manual only. Run the plugin with a known-good inline BTC signal and inspect the thesis. Confirm that the caveat is present, the implied position matches the edge, evidence bullets cite source names and numbers, and the rubric score is above 0.70. Then run `services/synthesis/run.py run-once` against local correlator data and verify that a JSONL row and envelope sidecar are created.

Day 2 should be daemon dry-run without event-bus publishing. Run the daemon with `--max-iterations` first, then a longer local session if needed. Inspect `~/.cache/sapphire/narrative_synthesis_service/last_edges.json` and confirm it is only tracking symbol/timeframe edge values. Confirm small edge moves do not create repeated rows. Confirm larger edge moves do create new rows.

Day 3 can enable event-bus publishing only if local JSONL behavior is clean. Set `SAPPHIRE_NARRATIVE_LIVE_BUS=1` for a controlled run and verify the event type is `narrative.thesis.generated`. Do not combine this with live Gemini mode. The goal is to validate local event plumbing, not model spend.

Live Gemini testing should be a separate soak. Run one inline signal with `SAPPHIRE_NARRATIVE_LIVE=1`, inspect `mode_actual`, check the cache counter, and turn the gate off. Do not put live mode in a LaunchAgent until the operator has reviewed cost, quality, and safety behavior over multiple manual runs.

## Operator Review Checklist

Before promoting a narrative into a report, check:

- Does the thesis name the symbol and timeframe?
- Does the implied position match the edge score and consensus?
- Are at least three evidence bullets tied to source names or numeric fields?
- Is the counter-thesis plausible rather than decorative?
- Are the invalidators observable in a future correlator tick?
- Does the caveat explicitly preserve research-only behavior?
- Is the provenance envelope present?
- Is `rubric.overall >= 0.70`?
- Is `mode_actual` expected for the run?

For live outputs, add:

- Did the response remain within the JSON schema?
- Did the prompt pass sensitivity without exposing secrets?
- Was the call count below 6/hour?
- Did the token counter update without exceeding the monthly cap?
- Was the live output materially better than the dry-run baseline?

If the answer to the final live question is "no", keep using dry-run. Live inference is only worth the operational cost when it improves the research product.

## Data Retention Notes

Narrative JSONL files are generated artifacts under `data/narratives/`. They are designed to be append-only local operational data, similar to correlated signal outputs. Do not commit generated narrative data unless a future fixture path is intentionally added for tests. The code in this PR writes test outputs only under pytest temporary directories.

Cache files under `~/.cache/sapphire/narrative_synthesis/` hold live-mode cache entries and counters. Cache files under `~/.cache/sapphire/narrative_synthesis_service/` hold daemon edge state. These are safe to delete if an operator wants to force regeneration, but deletion should be intentional because it can cause the daemon to treat all latest signals as changed on the next run.

## Future Enhancements

Likely next steps after 0.1.0:

- dashboard route showing latest thesis per symbol/timeframe;
- daily brief integration that includes only high-scoring rows;
- compare mode that shows dry-run versus live Gemini output side by side;
- historical narrative chain summaries;
- source-specific evidence explainers;
- operator feedback labels for useful, noisy, wrong, or stale theses;
- paper-trading outcome comparison for confidence calibration.

Keep each enhancement behind the same safety floor: dry-run first, no live trading, no Telegram sends, no secret printing, and provenance on generated artifacts.
