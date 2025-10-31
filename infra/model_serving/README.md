# Model Serving Sandbox

This sandbox provides reference configurations for running compact foundation models
used by the lean autonomous trading system. Two targets are included:

1. **CPU-only** inference via `llama.cpp` (ideal for DeepSeek-Coder-V2 GGUF builds).
2. **GPU-accelerated** inference via `vLLM` (recommended for Qwen/DeepSeek AWQ/GPTQ weights).
3. Optional scripts for staging models on TPU v5e or HPC backends (see _Advanced Deployment_).

## Directory Layout

```
infra/model_serving/
├── README.md
├── Dockerfile.llamacpp
├── Dockerfile.vllm
├── docker-compose.yml
└── env.example
```

## Prerequisites

- Docker 24+
- Optional: NVIDIA Container Toolkit for GPU workflows
- Model weights mounted at runtime (`./models` by default)

## llama.cpp (CPU) Quickstart

```bash
docker build -f Dockerfile.llamacpp -t trader-llamacpp .
docker run --rm -p 8081:8081 \
  -v $(pwd)/models:/models \
  trader-llamacpp \
  ./server -m /models/deepseek-coder-7b.gguf --threads $(nproc) --port 8081
```

The container exposes an OpenAI-compatible endpoint at `http://localhost:8081/v1/chat/completions`.

## vLLM (GPU) Quickstart

```bash
docker build -f Dockerfile.vllm -t trader-vllm .
docker run --rm --gpus all -p 8000:8000 \
  -v $(pwd)/models:/models \
  --env-file env.example \
  trader-vllm
```

vLLM hosts an OpenAI-compatible server at `http://localhost:8000/v1/completions`.

## Docker Compose

`docker-compose.yml` orchestrates both services alongside Redis for local testing:

```bash
docker compose up --build
```

Services:

- `llamacpp`: CPU inference (`8081`)
- `vllm`: GPU inference (`8000`)
- `redis`: message bus (`6379`)

## Environment Variables

Copy `env.example` and update paths:

```
cp env.example .env
```

Required values:

- `MODEL_PATH` – absolute path to AWQ/GGUF weights
- `CONTEXT_LENGTH` – maximum tokens (defaults to 4096)
- `TENSOR_PARALLEL_SIZE` – set >1 for multi-GPU nodes
- `VLLM_EXTRA_ARGS` – appended directly to vLLM (e.g. `--dtype float16 --enforce-eager`) 

## Health Checks

- llama.cpp: `curl http://localhost:8081/healthz`
- vLLM: `curl http://localhost:8000/health`

## Advanced Deployment Notes

- **TPU Friendly Setup**: Convert GGUF → Hugging Face format and point `MODEL_PATH` at the HF repo. For TPU v5e, reuse the same container but swap the base image for Google's TPU runtime (see `README_tpu.md`).
- **Model Downloads**: Set `HF_MODEL_ID` when launching vLLM to stream weights automatically (e.g. `HF_MODEL_ID=deepseek-ai/DeepSeek-Coder-V2-Lite-Instruct`).
- **Health Probes**:
  - llama.cpp: `curl -f http://localhost:8081/healthz`
  - vLLM: `curl -f http://localhost:8000/health`
- **Performance Tips**:
  - Quantized GGUF (Q4_K_M) yields ~2x speedup vs. FP16 on modern CPUs.
  - Use `VLLM_EXTRA_ARGS="--gpu-memory-utilization 0.92 --swap-space 4"` to maximise GPU throughput.
  - When running on multi-GPU hosts, set `TENSOR_PARALLEL_SIZE` to the number of available devices.

## Production Integration

- Wire the chosen serving endpoint into the Risk Orchestrator via the `cloud_trader` messaging layer.
- Expose latency/error metrics via `curl /metrics` (vLLM) or by adding Prometheus exporters through a compose override.
- Use CI/CD to build images (`docker buildx bake`) and push to your registry before deployment to Cloud Run / GKE / TPU pods.
