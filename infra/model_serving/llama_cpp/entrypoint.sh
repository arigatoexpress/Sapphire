#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH=${MODEL_PATH:-/models/model.gguf}
HOST=${HOST:-0.0.0.0}
PORT=${HOST_PORT:-8081}
CONTEXT=${CONTEXT_SIZE:-4096}
THREADS=${LLAMA_THREADS:-$(nproc)}

if [[ ! -f "$MODEL_PATH" ]]; then
  echo "Model not found at $MODEL_PATH" >&2
  exit 1
fi

echo "Launching llama.cpp server"
CMD=("./build/bin/llama-server"
  "--model" "$MODEL_PATH"
  "--host" "$HOST"
  "--port" "$PORT"
  "--ctx-size" "$CONTEXT"
  "--threads" "$THREADS"
  "--embedding"
)

if [[ -n "${LLAMA_API_KEY:-}" ]]; then
  CMD+=("--api-key" "$LLAMA_API_KEY")
fi

exec "${CMD[@]}"

