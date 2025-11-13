# Deployment Checklist & Verification (November 2025)

## ✅ Latest Build Snapshot
- **Backend Build**: `gcloud builds describe dd5d923e-5811-4657-b0c1-12407162f155`
- **Dashboard Build**: `gcloud builds describe 52215adb-22d7-42b3-acb7-268c07e7f1d0`
- **Vertex AI Images**: `vertex-ai/deepseek-trader`, `vertex-ai/qwen-trader`, `vertex-ai/fingpt-trader`, `vertex-ai/lagllama-trader`
- **Training Images**: `vertex-ai-training/*-trainer`

## 🎯 Release Highlights
- Per-agent **$1,000 margin allocation** enforced in `cloud_trader/service.py`
- GPU-ready **Vertex AI inference containers** for all four agents (CUDA 12.1 / PyTorch base)
- Reusable **Vertex AI custom job** configs for agent fine-tuning (`infra/training/cloudbuild-*.yaml`)
- New Prometheus metrics: `agent_margin_remaining_usd`, `agent_margin_utilization_ratio`, `portfolio_drawdown_pct`
- Cloud Monitoring + Prometheus alerts for margin exhaustion and deep drawdown

## 🔍 Verification Steps

### 1. Cloud Run Health
```bash
curl https://cloud-trader-cfxefrvooa-uc.a.run.app/healthz
curl https://cloud-trader-dashboard-cfxefrvooa-uc.a.run.app/
```
Expected: 200 with healthy payload.

### 2. Vertex AI Inference Images
```bash
gcloud artifacts docker images list us-central1-docker.pkg.dev/sapphireinfinite/vertex-ai
```
Ensure latest tags exist for `deepseek-trader`, `qwen-trader`, `fingpt-trader`, `lagllama-trader`.

### 3. Training Pipeline Templates
```bash
gcloud builds submit --config=infra/training/cloudbuild-deepseek.yaml --no-source --dry-run
```
Repeat for Qwen/FinGPT/Lag-Llama. Confirm spec references correct training script and GPU `a2-highgpu-1g`.

### 4. Margin Guardrails
- Open `/metrics` and confirm gauges `agent_margin_remaining_usd{agent_id=...}` report ~1000 initially.
- Execute a paper trade via `/simulate` (or wait for live trade) and ensure remaining margin drops accordingly.
- Verify `risk_limits_breached_total{limit_type="agent_margin"}` increments when utilization > 100%.

### 5. Drawdown Telemetry
```bash
curl -s https://cloud-trader-cfxefrvooa-uc.a.run.app/dashboard | jq '.portfolio.balance'
```
- Track peak vs current balance; verify Prometheus metric `portfolio_drawdown_pct` updates (<0.25 under normal conditions).

### 6. Alert Policies
```bash
gcloud alpha monitoring policies list --filter="display_name:Sapphire Trade"
```
Confirm policies:
- `Sapphire Trade – Agent Margin Utilization`
- `Sapphire Trade – Portfolio Drawdown`

## 📦 What Changed

### Backend
- `cloud_trader/service.py`: agent margin enforcement, drawdown gauge updates
- `cloud_trader/metrics.py`: new gauges for margin/drawdown
- `tests/test_multi_agent_thesis.py`: unit test covering margin guard

### Inference Containers
- `models/*/Dockerfile`: CUDA-enabled, uvicorn entrypoints
- `models/lagllama/*`: new lag-llama inference service
- `infra/llm_serving/cloudbuild*.yaml`: push images to `vertex-ai/*`

### Training Pipelines
- `cloud_trader/training/`: reusable dataset loader & trainer scripts
- `infra/training/`: Dockerfile + Cloud Build launchers for custom jobs
- `terraform/vertex_ai.tf`: training pipelines now reference `vertex-ai-training/*`

### Monitoring
- `infra/monitoring/cloud-alert-policies.yaml`: margin + drawdown alerts
- `infra/monitoring/prometheus-alerts.yaml`: Prometheus rules for same signals

## 🛠️ Post-Deploy Sanity
1. Monitor Cloud Run logs for `agent_margin_exceeded` messages (should be rare).
2. Verify Vertex AI endpoints respond after redeploy (list via `gcloud ai endpoints list`).
3. Run a smoke training job (dry-run) to validate container entrypoint:
   ```bash
   gcloud builds submit --config infra/training/cloudbuild-deepseek.yaml \
     --substitutions=_DATA_PATH=gs://your-bucket/deepseek.jsonl --async
   ```
4. Ensure Grafana dashboards include the new margin/drawdown metrics.

## 📊 Metrics Reference
| Metric | Description | Alert |
| ------ | ----------- | ----- |
| `agent_margin_remaining_usd{agent_id}` | Dollar margin left per agent | Margin Utilization |
| `agent_margin_utilization_ratio{agent_id}` | Utilization ratio 0-1 | Margin Utilization |
| `portfolio_drawdown_pct` | Peak-to-current drawdown | Portfolio Drawdown |
| `risk_limits_breached_total{limit_type="agent_margin"}` | Count of margin rejections | Prometheus warning |

## 🚀 Next Steps
- [ ] Populate training datasets in GCS (`gs://sapphireinfinite/training/*.jsonl`)
- [ ] Execute initial fine-tuning job for DeepSeek via Cloud Build
- [ ] Populate Vertex AI endpoints once models trained
- [ ] Extend Grafana dashboards with new gauges and alert panels

✅ **Status**: Deployment complete & guardrails active. Continue with Vertex AI fine-tuning.
