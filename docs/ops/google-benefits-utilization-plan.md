# Google Benefits Utilization Plan

Last updated: 2026-04-27

This is the Sapphire operating map for Ari's Google Developer Program, Google AI/Gemini membership, Google One storage, Gmail/Drive, YouTube Premium, Google Cloud, Gemini API, Vertex AI, and Veo benefits. The stance is aggressive but economical: use included benefits and free tiers first, keep Sapphire as the command system, and require explicit caps before paid compute, account actions, or destructive cleanup.

Run the local inventory:

```bash
python3 scripts/ops/google_benefits_inventory.py \
  --membership google_developer_premium \
  --membership google_ai_plus \
  --project tho-ai-agent
```

For a no-network/no-CLI control-tower view:

```bash
python3 scripts/ops/google_benefits_inventory.py --no-external --membership google_ai_plus
```

Generate a Gmail/Drive cleanup plan without touching Google APIs:

```bash
python3 scripts/ops/google_workspace_threat_hygiene.py --days 30
```

Generate the full production-testing readiness view:

```bash
python3 scripts/ops/google_production_test_readiness.py \
  --membership google_developer_premium \
  --membership google_ai_plus \
  --project tho-ai-agent \
  --region us-central1
```

See [`docs/ops/google-production-testing-runbook.md`](google-production-testing-runbook.md)
for the one-command harness, live gates, and economical test ladder.

## Benefit Map

| Benefit Lane | What It Unlocks | Sapphire Use | Gate |
|---|---|---|---|
| Google Developer Program | Gemini Code Assist, Gemini CLI, Firebase Studio, Skills, Cloud/GenAI credits depending on plan | Operator-side development, bounded labs, education, prototype credits | No purchases, credit redemption, billing changes, or project creation by automation |
| Google AI membership | Gemini app, Flow/Whisk credits, NotebookLM, Google One storage by plan | Manual research, media concepting, non-secret artifact storage | Do not automate consumer sessions; verify production API entitlements separately |
| Gemini Developer API | Free-tier and paid-tier Gemini API through AI Studio | Local dry-run prototypes and prompt evals | Explicit API key, project, and token/spend cap before calls |
| Vertex AI / Veo | Gemini/Imagen/Veo, embeddings, batch prediction, tuning, endpoints | Batch OODA, evals, retrieval, media work-order readiness | No job, endpoint, tuning, or Veo generation without budget and rollback |
| Google Cloud Free Tier | Cloud Storage, BigQuery, Cloud Run, Pub/Sub, Secret Manager, Firestore and other limited usage | Cheap data plane for summaries, manifests, telemetry, evals | Labels, lifecycle, retention, and quota budget before writes |
| Gmail / Drive | Gmail labels/search/metadata/modify/trash APIs; Drive metadata/labels/permissions/trash APIs | Threat hygiene, phishing triage, inbox/Drive cleanup proposals | Metadata-only first; human approval before label mutation, trash, or delete |
| YouTube Premium | Ad-free/manual research ergonomics, Music, downloads, background play | Manual research only; optional transcript/intel adapter via proper APIs | No account automation or terms bypass |

## What To Do First

1. Confirm the exact plan names in Google dashboards: Developer Program tier, Google AI tier, Google One storage amount, AI credits, and YouTube membership. Do not paste secrets or payment details.
2. Use `scripts/ops/google_benefits_inventory.py` and `scripts/ops/gcp_ai_inventory.py` after each account or GCP change.
3. Run `scripts/ops/google_production_test_readiness.py` before any live Gemini, Vertex, GCS, BigQuery, Gmail, Drive, or Veo experiment.
4. Keep Google Cloud writes inside `tho-ai-agent` unless a runbook explicitly says otherwise.
5. Use Cloud Storage free-tier-aware buckets for summarized artifacts only. Do not put secrets, raw Gmail, raw Drive files, private keys, or trading credentials in consumer Drive or GCS.
6. Use BigQuery's free monthly storage/query posture for summaries and eval metrics before any custom storage/index service.
7. Use Gemini API free-tier prototypes before Vertex AI; use Vertex batch before online endpoints; use evals before tuning/training.
8. Build Gmail/Drive threat hygiene as dry-run findings first: label proposal, risk score, evidence snippets, and reversible actions.

## Gmail / Drive Threat Hygiene Ladder

1. **Inventory only**: label counts, storage pressure, OAuth scopes present, and candidate query list. No content reads.
2. **Metadata scan**: sender domains, headers, attachment metadata, Drive file owners/permissions, and URL extraction from message metadata where allowed.
3. **Risk scoring**: Safe Browsing/Web Risk checks for URLs, sender/domain reputation from local allow/deny lists, attachment extension heuristics, and Drive sharing exposure.
4. **Quarantine proposal**: write a local JSON/Markdown report with message/file IDs hashed or shortened, recommended Gmail label, Drive label, or archive action.
5. **Reversible action**: apply a label such as `Sapphire/Review/Suspicious` only after explicit approval.
6. **Trash/delete**: disabled by default. Prefer Gmail `trash` over permanent delete; never use permanent Gmail/Drive delete from autonomy.

The starter planner in `scripts/ops/google_workspace_threat_hygiene.py` emits
candidate Gmail search queries, Drive metadata review lanes, approval steps,
and blocked actions. It does not access Gmail or Drive.

## Economic Production Pattern

| Workload | First Runtime | Why |
|---|---|---|
| Mission digests and OODA packets | Local dry-run, then Vertex/Gemini batch | Non-urgent, auditable, cheaper than online endpoints |
| Regional intel retrieval | BigQuery vector/search tables | Uses existing data plane before dedicated vector infra |
| Media factory | Local work orders, then human-triggered Flow/Whisk/Veo or Vertex Veo | Uses included creative credits before paid API jobs |
| Gmail/Drive cleanup | Local reports, then Gmail/Drive labels | Human-verifiable and reversible |
| Training new models | Eval harness first; smallest Vertex custom job only after proof | Avoid training before proving a measurable gap |

## Official Sources

- Google Developer Program plans and benefits: <https://developers.google.com/program/plans-and-pricing>, <https://developers.google.com/profile/help/benefits>
- Google AI plans and storage/AI credits: <https://one.google.com/about/google-ai-plans/?hl=en>
- Gemini API pricing/rate limits: <https://ai.google.dev/gemini-api/docs/pricing>, <https://ai.google.dev/gemini-api/docs/rate-limits>
- Google Cloud free tier, Cloud Storage, and BigQuery pricing: <https://docs.cloud.google.com/free/docs/free-cloud-features>, <https://cloud.google.com/storage/pricing>, <https://cloud.google.com/bigquery/pricing>
- Gmail API scopes, methods, and push notifications: <https://developers.google.com/workspace/gmail/api/auth/scopes>, <https://developers.google.com/workspace/gmail/api/reference/rest>, <https://developers.google.com/gmail/api/guides/push>
- Drive API and Safe Browsing: <https://developers.google.com/drive/api/reference/rest/v3>, <https://developers.google.com/safe-browsing/v4>
- Vertex AI/Veo pricing and APIs: <https://cloud.google.com/vertex-ai/generative-ai/pricing>, <https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/veo-video-generation>
- YouTube Premium benefits: <https://support.google.com/youtube/answer/6308116>
