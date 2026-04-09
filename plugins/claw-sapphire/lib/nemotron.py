"""Ollama API client with real token counting.

Routes to GPU (Windows) first, falls back to local Mac.
Returns actual eval_count and prompt_eval_count from Ollama responses.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

ENDPOINTS = [
    ("gpu", "http://100.71.10.48:11434"),
    ("local", "http://localhost:11434"),
]

# Benchmarked model selection
# Models are pulled on both Mac (local) and Windows GPU
MODELS = {
    "classify": "nemotron-mini",  # 2.7B, fast classifier, on both endpoints
    "analyze": "hermes3:8b",  # 8B, tool calling + reasoning, on both endpoints
    "quick": "nemotron-mini",  # Alias for classify
    "accurate": "hermes3:8b",  # Best available on both
    "tiny": "llama3.2:3b",  # Small, fast, on both endpoints
}


@dataclass
class InferenceResult:
    """Result from an Ollama inference call with real token counts."""

    response: str
    endpoint: str
    model: str
    prompt_tokens: int
    eval_tokens: int
    total_tokens: int
    eval_duration_ms: float
    tokens_per_second: float
    success: bool
    error: str = ""


def generate(
    prompt: str,
    model: str = "nemotron-3-nano:4b",
    system: str | None = None,
    timeout: int = 120,
    max_tokens: int = 512,
) -> InferenceResult:
    """Send generate request to Ollama with real token tracking."""
    for ep_name, base_url in ENDPOINTS:
        try:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": max_tokens},
            }
            if system:
                payload["system"] = system

            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                f"{base_url}/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
            )

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read())

            prompt_tokens = result.get("prompt_eval_count", 0)
            eval_tokens = result.get("eval_count", 0)
            eval_duration = result.get("eval_duration", 1) / 1e9  # ns → s
            tps = eval_tokens / eval_duration if eval_duration > 0 else 0

            return InferenceResult(
                response=result.get("response", ""),
                endpoint=ep_name,
                model=model,
                prompt_tokens=prompt_tokens,
                eval_tokens=eval_tokens,
                total_tokens=prompt_tokens + eval_tokens,
                eval_duration_ms=eval_duration * 1000,
                tokens_per_second=round(tps, 1),
                success=True,
            )
        except Exception:
            continue

    return InferenceResult(
        response="",
        endpoint="none",
        model=model,
        prompt_tokens=0,
        eval_tokens=0,
        total_tokens=0,
        eval_duration_ms=0,
        tokens_per_second=0,
        success=False,
        error="All Ollama endpoints unavailable",
    )


def list_models(endpoint: str = "gpu") -> list[dict]:
    """List available models on an endpoint."""
    base = dict(ENDPOINTS).get(endpoint, ENDPOINTS[0][1])
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=5) as resp:
            data = json.loads(resp.read())
            return [
                {
                    "name": m["name"],
                    "size": m["details"]["parameter_size"],
                    "quant": m["details"]["quantization_level"],
                }
                for m in data.get("models", [])
            ]
    except Exception:
        return []
