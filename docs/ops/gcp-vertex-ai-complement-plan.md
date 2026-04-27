# GCP / Vertex AI Complement Plan

Last updated: 2026-04-27

Sapphire remains the command system. GCP and Vertex AI are the data, batch intelligence, evaluation, and training support plane. They complement the local control tower; they do not own trading, Telegram dispatch, Foundry writes, LaunchAgent retargeting, workflow dispatches, or secret material.

## Current Posture

- Active `gcloud` account/project observed during the 2026-04-27 test: `aristotlespec@gmail.com` / `tho-ai-agent`.
- Local Sapphire control/secret readiness still reports against `sapphire-479610`; keep the two project roles explicit.
- `tho-ai-agent` has the `sapphire` BigQuery dataset and the core data/AI APIs enabled, including Vertex AI, BigQuery, Cloud Run, Pub/Sub, GCS, logging, monitoring, Cloud Build, Cloud Functions, and Secret Manager.
- Vertex AI in `us-central1` currently has no listed custom jobs, models, endpoints, indexes, or index endpoints. That means there is no observed always-on Vertex endpoint burn from this lane.
- `RELAY_READER_TOKEN` is not rotated yet. Do not implement sanitized service-owned plists/wrappers or retarget LaunchAgents until rotation is confirmed and tested.

Run the inventory at any point:

```bash
python3 scripts/ops/gcp_ai_inventory.py \
  --project tho-ai-agent \
  --region us-central1 \
  --format markdown
```

For a no-network control-tower view:

```bash
python3 scripts/ops/gcp_ai_inventory.py --no-external
```

## Guardrails

- No secret values are read, printed, copied, or rotated by this lane.
- No live trading, money movement, Telegram sends, workflow dispatches, Foundry writes, GCS/BigQuery writes, LaunchAgent retargets, Vertex training jobs, model tuning jobs, or endpoint deployments happen during inventory.
- Any live batch prediction, embedding generation, BigQuery write, or model training must have a reviewed budget cap, input sample cap, output path, rollback, and artifact-retention plan.
- Prefer ephemeral jobs and batch artifacts over always-on endpoints.
- Label future resources with `owner=sapphire`, `env`, `lane`, and `cost_center` before any mutating deployment.

## Test Ladder

1. Inventory and cost posture

   Run `python3 scripts/ops/cost_posture_report.py --format markdown --hours 24 --log-limit 10` and `python3 scripts/ops/gcp_ai_inventory.py --format markdown`. This is metadata-only and confirms API readiness, Cloud Run shape, BigQuery datasets, and Vertex idle/busy posture.

2. Batch Gemini OODA packets

   Use Vertex AI batch prediction for non-urgent summaries over regional intel, mission digests, threat packets, and media work orders. Google's Gemini batch prediction docs describe this path as asynchronous and cost-effective for large non-urgent work, with batch processing discounted versus real-time inference: <https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/batch-prediction-gemini>.

3. BigQuery retrieval layer

   Keep retrieval in BigQuery first. BigQuery vector search supports embeddings and SQL search functions, and Google documents autonomous embedding generation that can maintain embedding columns from source columns using Vertex AI embedding models: <https://cloud.google.com/bigquery/docs/vector-search-intro>.

4. Vertex eval harness

   Before training or tuning, score Sapphire prompts and command outputs against golden cases: Telegram command safety replies, OODA packet quality, media work-order readiness, Foundry regional summaries, and trading explanation quality. Store results as local artifacts first, then promote summarized metrics to BigQuery only after review.

5. Training or tuning

   Train only after evals prove a repeated gap that prompting, retrieval, and batch inference cannot fix. Vertex AI custom training supports common frameworks such as PyTorch, TensorFlow, scikit-learn, and XGBoost: <https://cloud.google.com/vertex-ai/docs/training/overview>. Start with the smallest dataset and shortest job; do not deploy an endpoint by default.

6. Cloud CLI AI helpers

   Use `gcloud ai` for read-only Vertex inventory and controlled job management, and keep Gemini CLI as an operator-side assistant only. Gemini CLI supports non-interactive/headless usage, token caching, sandboxing, trusted folders, and context files, which makes it useful for auxiliary review without replacing Sapphire's command authority: <https://google-gemini.github.io/gemini-cli/docs/cli/>.

## Production Shape

| Lane | First production artifact | Default runtime | Cost control | Ownership |
|---|---|---|---|---|
| Regional OODA | JSON packet with `observe`, `orient`, `decide`, `act` | Batch job | Sample caps and batch inference | Sapphire control tower |
| Mission digest | BigQuery/GCS prompt batch and local markdown digest | Batch job | Manual or scheduled batches only | Sapphire control tower |
| Retrieval | BigQuery vector/search tables over docs, events, incidents, and intel | BigQuery SQL | No deployed vector endpoint initially | Data plane |
| Eval harness | Golden-case scorecards and drift reports | Local first, then BigQuery | Fixed case set and token budget | QA/control tower |
| Training | Small supervised job or tuning experiment | Vertex custom training | Explicit spend cap, no endpoint by default | Human-approved AI lane |

## Do Next

1. Keep `RELAY_READER_TOKEN` work blocked until rotation is complete.
2. Run the read-only inventory and cost reports after each significant GCP change.
3. Add a dry-run batch prompt artifact for one regional OODA packet and one mission digest.
4. Build the eval harness before any custom model training.
5. Promote only reviewed summary metrics to BigQuery; keep raw prompts and runtime artifacts local or in governed GCS paths.
