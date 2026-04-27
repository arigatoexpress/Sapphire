# Google Production-Testing Runbook

Last updated: 2026-04-27

This runbook turns Ari's Google Developer Program, Google AI/Gemini, Google
Cloud, Gmail/Drive, YouTube, Vertex AI, and Veo surface into a production
testing lane for Sapphire without letting Google take over the system. Sapphire
remains the command authority; Google is a complement for operator assistance,
cheap storage, metadata, batch intelligence, evals, and carefully capped model
experiments.

## Current Baseline

- Gemini CLI package installed locally: `@google/gemini-cli`, observed version
  `0.39.1`.
- Active `gcloud` account/project observed during readiness work:
  `aristotlespec@gmail.com` / `tho-ai-agent`.
- `tho-ai-agent` has Cloud Storage buckets, a `sapphire` BigQuery dataset, and
  the AI/data services needed for dry-run complement testing.
- Vertex AI in `us-central1` had no observed custom jobs, models, endpoints,
  indexes, or index endpoints during the 2026-04-27 inventory.
- `RELAY_READER_TOKEN` is still not rotated. Do not retarget LaunchAgents or
  implement sanitized service-owned wrappers until that token is rotated and
  tested.

## One Command Readiness

Run the harness from the Sapphire repo root:

```bash
python3 scripts/ops/google_production_test_readiness.py \
  --project tho-ai-agent \
  --region us-central1 \
  --membership google_developer_premium \
  --membership google_ai_plus \
  --format markdown
```

Write a local ignored artifact for comparison over time:

```bash
python3 scripts/ops/google_production_test_readiness.py \
  --project tho-ai-agent \
  --region us-central1 \
  --membership google_developer_premium \
  --membership google_ai_plus \
  --output data/google/production-readiness/latest.md
```

Include read-only billing, Cloud Run, warning-log taxonomy, and local retention
posture when deciding whether to start a capped live experiment:

```bash
python3 scripts/ops/google_production_test_readiness.py \
  --project tho-ai-agent \
  --region us-central1 \
  --membership google_developer_premium \
  --membership google_ai_plus \
  --include-cost \
  --cost-hours 24 \
  --cost-log-limit 25
```

For offline/no-CLI planning:

```bash
python3 scripts/ops/google_production_test_readiness.py --no-external
```

## Production-Test Ladder

| Stage | What Runs | Default State | Why |
|---|---|---|---|
| Tooling inventory | `google_benefits_inventory.py` and `gemini --version` | Read-only | Confirms local Google and Gemini operator surface. |
| GCP/Vertex inventory | `gcp_ai_inventory.py` | Read-only | Confirms APIs, BigQuery, GCS, and idle Vertex posture. |
| Workspace hygiene plan | `google_workspace_threat_hygiene.py` | Dry-run plan | Stages Gmail/Drive threat queries without reading or mutating content. |
| Cost posture | `cost_posture_report.py` via `--include-cost` | Read-only | Checks Cloud Run cost risks and warning categories before adding jobs. |
| OODA local artifacts | Local files under `data/google/production-readiness/` | Dry-run | Proves prompts, samples, and outputs before any Gemini/Vertex call. |
| Gemini API / Vertex batch | Explicit model call or batch job | Manual gate | Requires token cap, spend cap, sample cap, output path, and rollback. |
| BigQuery/GCS promotion | Summary writes only | Manual gate | Requires schema, lifecycle, labels, retention, and free-tier budget. |
| Training/tuning | Vertex job | Blocked until evals | Only after evals prove a repeated, measurable gap. |

## Live Gates

These are still outside autonomous default behavior:

- Real trading or money movement.
- Production Telegram sends.
- Gmail labels, archive, trash, delete, message-body reads, or attachment
  downloads.
- Drive labels, permission changes, trash, delete, or file downloads.
- GCS or BigQuery writes.
- Foundry writes.
- Vertex batch prediction, endpoint deployment, tuning, training, or Veo jobs.
- Workflow dispatches or GitHub billing changes.
- Secret value reads, secret rotations, credit redemptions, billing changes, API
  enablement, project creation, and LaunchAgent retargeting.

For any one of those, the next prompt must specify the exact live action, target
resource, budget or blast-radius cap, output path, and rollback.

## Safety Review

The readiness harness is safe to run as a production-test preflight because it
only composes existing read-only or dry-run surfaces:

- `google_benefits_inventory.py` lists local CLI/account metadata, asserted
  memberships, GCS bucket names, and BigQuery dataset names.
- `gcp_ai_inventory.py` lists enabled service names, BigQuery datasets/tables,
  and Vertex resource counts/display names.
- `google_workspace_threat_hygiene.py` builds Gmail and Drive query templates
  locally; it does not call Workspace APIs.
- `cost_posture_report.py` is only invoked with `--include-cost` and performs
  read-only billing, Cloud Run, logging, and local retention checks.

The harness does not read secret values, Gmail bodies, Drive file contents,
attachments, Secret Manager payloads, GCS object contents, BigQuery table rows,
or model prompts. It also does not create, update, delete, dispatch, publish,
retarget, rotate, redeem, or deploy anything. Use `--no-external` when drafting
plans without local CLI/GCP metadata.

## Economical Use Pattern

- Use Gemini CLI as an operator-side reviewer and local assistant; do not paste
  secrets or raw private mail into prompts.
- Use Google AI Plus and YouTube Premium manually for research, storage
  convenience, NotebookLM/Flow/Whisk-style exploration, and media concepts.
- Use Gemini Developer API for small, capped prototypes before Vertex AI.
- Use Vertex AI batch and evals before custom training or deployed endpoints.
- Keep retrieval in BigQuery first; only add Vertex Vector Search or endpoints
  after BigQuery cannot satisfy the job.
- Use GCS/BigQuery for summarized artifacts, manifests, scorecards, and audit
  tables, not raw secrets or personal data.

## Verification

```bash
pytest tests/unit/test_google_production_test_readiness.py \
  tests/unit/test_google_benefits_inventory.py \
  tests/unit/test_gcp_ai_inventory.py \
  tests/unit/test_google_workspace_threat_hygiene.py -q

ruff check scripts/ops/google_production_test_readiness.py \
  tests/unit/test_google_production_test_readiness.py

git diff --check
```
