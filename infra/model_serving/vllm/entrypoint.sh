#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH=${MODEL_PATH:-/models}
TOKENIZER_PATH=${TOKENIZER_PATH:-}
HOST=${HOST:-0.0.0.0}
PORT=${PORT:-8000}
CONTEXT_LENGTH=${CONTEXT_LENGTH:-4096}
TENSOR_PARALLEL_SIZE=${TENSOR_PARALLEL_SIZE:-1}
GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION:-0.90}
VLLM_EXTRA_ARGS=${VLLM_EXTRA_ARGS:-}

if [[ -n "${HF_MODEL_ID:-}" ]]; then
  echo "Downloading model ${HF_MODEL_ID} via vLLM"
  MODEL_PATH=${HF_MODEL_ID}
fi

CMD=("python3" "-m" "vllm.entrypoints.openai.api_server"
  "--model" "$MODEL_PATH"
  "--host" "$HOST"
  "--port" "$PORT"
  "--max-model-len" "$CONTEXT_LENGTH"
  "--tensor-parallel-size" "$TENSOR_PARALLEL_SIZE"
  "--gpu-memory-utilization" "$GPU_MEMORY_UTILIZATION"
)

if [[ -n "$TOKENIZER_PATH" ]]; then
  CMD+=("--tokenizer" "$TOKENIZER_PATH")
fi

if [[ -n "$VLLM_EXTRA_ARGS" ]]; then
  # shellcheck disable=SC2206
  EXTRA_ARGS=($VLLM_EXTRA_ARGS)
  CMD+=("${EXTRA_ARGS[@]}")
fi

echo "Launching vLLM: ${CMD[*]}"
exec "${CMD[@]}"

