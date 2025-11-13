# 🚀 Sapphire HFT Platform – GCP Deployment Playbook (Nov 2025)

## Quick Start Commands
```bash
# Build & deploy trading service
gcloud builds submit --config=cloudbuild.yaml --project=sapphireinfinite --async

# Deploy dashboard
gcloud builds submit --config=infra/dashboard/cloudbuild.yaml --project=sapphireinfinite --async

# List active Cloud Run revisions
gcloud run services list --project=sapphireinfinite --region=us-central1
```

## Architecture Snapshot
- **Cloud Run** for stateless trading API + dashboard
- **Vertex AI Endpoints** for agent inference (DeepSeek, Qwen, FinGPT, Lag-Llama)
- **Vertex AI Custom Jobs** for fine-tuning pipelines (one per agent)
- **Artifact Registry** (repos: `vertex-ai`, `vertex-ai-training`)
- **Pub/Sub + Secret Manager + Redis** for messaging and secrets
- **Prometheus / Cloud Monitoring** for metrics & alerting

## Vertex AI Inference Containers
GPU-ready Dockerfiles live in `models/<agent>/Dockerfile` (CUDA 12.1 + uvicorn). Build/push via:
```bash
gcloud builds submit --config=infra/llm_serving/cloudbuild.yaml         # DeepSeek
gcloud builds submit --config=infra/llm_serving/cloudbuild-qwen.yaml     # Qwen
gcloud builds submit --config=infra/llm_serving/cloudbuild-fingpt.yaml   # FinGPT
gcloud builds submit --config=infra/llm_serving/cloudbuild-lagllama.yaml # Lag-Llama
```
Each config tags `us-central1-docker.pkg.dev/$PROJECT_ID/vertex-ai/<agent>:latest`. Attach endpoints with Terraform (`terraform/vertex_ai.tf`) or manual `gcloud ai endpoints deploy-model`.

## Vertex AI Training Pipelines
Reusable scripts in `cloud_trader/training/` handle dataset loading (JSON or BigQuery) and `transformers` fine-tuning. A shared training image is built from `infra/training/Dockerfile`.

Launch a training job:
```bash
gcloud builds submit --config=infra/training/cloudbuild-deepseek.yaml \
  --substitutions=_DATA_PATH=gs://sapphireinfinite/training/deepseek.jsonl \
  --project=sapphireinfinite --async
```
The Cloud Build config builds `vertex-ai-training/deepseek-trainer` and immediately starts a Vertex AI custom job on `a2-highgpu-1g`. Mirror configs exist for Qwen/FinGPT/Lag-Llama.

## Margin & Risk Controls
- Each agent now operates with **$1,000 margin allocation** (`AGENT_DEFINITIONS` in `cloud_trader/service.py`).
- Metrics exported:
  - `agent_margin_remaining_usd{agent_id}`
  - `agent_margin_utilization_ratio{agent_id}`
  - `risk_limits_breached_total{limit_type="agent_margin"}`
  - `portfolio_drawdown_pct`

## Monitoring & Alerting
- **CI Pipeline Protection**: Added startup/import test in `cloudbuild.yaml` to catch SQLAlchemy issues early
- **SQLAlchemy Rule**: Never use `metadata` as column name (see `docs/SQLALCHEMY_METADATA_RULE.md`)
- **Alert Policies** (setup via Cloud Console):
  - Cloud Run revision failures → immediate notification
  - Cloud Build failures → immediate notification
  - Agent margin utilization >95% → warning
  - Portfolio drawdown >25% → critical alert
- Drawdown tracking starts at service initialization (`_peak_balance`).

### Alerts
- **Cloud Monitoring** policies (`infra/monitoring/cloud-alert-policies.yaml`) trigger when:
  - Agent margin utilization > 95%
  - Portfolio drawdown > 25%
- **Prometheus** rules (`infra/monitoring/prometheus-alerts.yaml`) mirror these triggers for Grafana/Slack.

## Deploy Workflow
1. **Build** – Submit Cloud Build jobs (service + dashboard + agent images)
2. **Migrate** – Apply Terraform (`terraform plan/apply`) to refresh Vertex AI pipelines/endpoints
3. **Verify** – Hit `/healthz`, check `/metrics`, inspect Cloud Monitoring alerts
4. **Observe** – Grafana dashboards (import `infra/monitoring/trading-dashboard.json`)

## Local Development
```bash
# Builder cache
docker build --target builder -t trader-builder .
# Runtime image
docker build --cache-from trader-builder -t trader-app .
# Smoke test
docker run -p 8080:8080 trader-app
curl http://localhost:8080/healthz
```

## Environment Variables (Key Additions)
```
ENABLE_VERTEX_AI=true
MAX_SYMBOLS_PER_AGENT=50
AGENT_CACHE_TTL_SECONDS=10
ENABLE_PAPER_TRADING=false
```

## Monitoring Cheat Sheet
| Endpoint | Purpose |
|----------|---------|
| `/metrics` | Prometheus exposition (margin, drawdown, latency) |
| `/dashboard` | Portfolio snapshot consumed by frontend |
| Cloud Logging | `gcloud logging read --freshness=1h "resource.type=cloud_run_revision"` |

## Troubleshooting
- **Margin rejections**: Look for `agent_margin_exceeded` in Cloud Run logs, check gauge values.
- **Vertex custom job fails**: Inspect `gcloud ai custom-jobs describe JOB_ID` for container errors. Ensure training dataset path accessible.
- **Slow builds**: Confirm `cloudbuild.yaml` options use `N2_HIGHCPU_32`, BuildKit is enabled.
- **Alerts firing**: Validate market volatility, consider reducing exposure or adjusting `margin_allocation`.

## Next Objectives
- Populate GCS training datasets for all assets
- Run first-pass fine-tuning jobs and register Vertex AI models
- Wire inference endpoints back into `cloud_trader/vertex_ai_client.py`
- Extend Grafana with new margin/drawdown panels

> **Status:** Feature-complete for Vertex AI deployment & risk guardrails. Awaiting dataset ingestion and fine-tuning execution.
