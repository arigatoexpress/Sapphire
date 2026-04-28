# Narrative Eval Runbook

## Run Once

```bash
python3 services/narrative_evaluation/run.py run-once
```

Optional horizon override:

```bash
python3 services/narrative_evaluation/run.py run-once --horizon 6 --horizon 24
```

## Plugin Actions

```bash
echo '{"action":"status"}' | python3 plugins/claw-sapphire/tools/narrative_eval.py
echo '{"action":"aggregates","group_by":"symbol"}' | python3 plugins/claw-sapphire/tools/narrative_eval.py
echo '{"action":"diagnostics"}' | python3 plugins/claw-sapphire/tools/narrative_eval.py
echo '{"action":"calibration"}' | python3 plugins/claw-sapphire/tools/narrative_eval.py
```

Pure inline scoring:

```bash
echo '{"action":"score-thesis","thesis":{"symbol":"BTC","timeframe":"1h","generated_at":"2026-04-28T00:00:00+00:00","implied_position":"long_mild","confidence":0.62},"outcome":{"symbol":"BTC","timeframe":"1h","observed_at":"2026-04-29T00:00:00+00:00","actual_return_pct":1.2},"horizon_hours":24}' | python3 plugins/claw-sapphire/tools/narrative_eval.py
```

## Dashboard

Run the dashboard with a non-default password and open `/narrative-eval`.

```bash
AUTH_PASSWORD='use-a-local-non-default-password' python3 services/dashboard/app.py
```

## Artifact Contract

Scores are append-only:

- `data/narrative_evaluation/<YYYY-MM-DD>/scores.jsonl`
- `data/narrative_evaluation/<YYYY-MM-DD>/scores.jsonl.envelope.json`

The service is idempotent by `score_id`, so repeated `run-once` calls do not duplicate an already scored thesis/horizon pair.

## Interpretation

- `pending_horizon`: the evaluation horizon has not elapsed.
- `no_outcome`: the horizon elapsed, but no local matching outcome row was found.
- `false_positive_directional_thesis`: the thesis had a long/short posture and the realized direction disagreed.
- `overconfident_miss`: confidence was at least 0.75 and the thesis was wrong.

Do not treat unscored rows as accuracy evidence. If outcomes are missing, first repair or backfill the local outcome stream, then rerun the scorer.
