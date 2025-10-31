# TPU v5e Deployment Cheat Sheet

This addendum captures the high-level steps for running the same models on Google Cloud TPUs (v5e).
See the main README for Docker-based workflows.

## Hardware Recommendation

- **Slice**: `v5litepod-4` (4 chips) – balanced for ≤16B models.
- **VM**: `ct5lp-hightpu-4t` (112 vCPUs / 192 GB RAM).
- **Storage**: 100 GB SSD + Cloud Storage bucket for model artifacts.

## Provisioning

```bash
gcloud alpha compute tpus queued-resources create trading-tpu \
  --node-id=trading-tpu-vm \
  --project=${PROJECT_ID} \
  --zone=us-central1-a \
  --accelerator-type=v5litepod-4 \
  --runtime-version=v2-alpha-tpuv5e \
  --service-account=tpu-sa@${PROJECT_ID}.iam.gserviceaccount.com \
  --preemptible

gcloud compute tpus tpu-vm ssh trading-tpu-vm --zone=us-central1-a
```

## Environment Setup

```bash
conda create -n vllm python=3.12 -y
conda activate vllm
git clone https://github.com/vllm-project/vllm
cd vllm
pip install -r requirements/tpu.txt
VLLM_TARGET_DEVICE=tpu pip install -e .
```

Upload models to Cloud Storage (Hugging Face format, not GGUF), then mount or pass `HF_MODEL_ID` to vLLM.

## Serving Command

```bash
python -m vllm.entrypoints.openai.api_server \
  --model deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct \
  --tensor-parallel-size 4 \
  --device tpu \
  --host 0.0.0.0 --port 8000
```

Expose the endpoint via Cloud Run tunnels or an internal load balancer and hook into the risk orchestrator the same way as GPU/CPU endpoints.

For complete cost modelling see the project wiki or the Grok research brief.

