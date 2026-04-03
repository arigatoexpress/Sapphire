# Qwen 3.5 Benchmark Fix Summary

## Problem Identified

**Qwen 3.5 models are NOT working properly with Ollama** despite being listed in the library. The model:
- Downloads successfully (6.6 GB for 9B model)
- Times out during inference (even with 4+ minute timeouts)
- Never generates the first token

## Root Cause

Based on research, there are **known compatibility issues** between Qwen 3.5's architecture and Ollama:

1. **MoE Architecture**: Qwen 3.5 uses Mixture-of-Experts (MoE) with separate mmproj vision files
2. **Ollama Limitation**: According to Unsloth documentation: 
   > "Currently no Qwen3.5 GGUF works in Ollama due to separate mmproj vision files"
3. **Slow Loading**: First-load can take 60-180 seconds on consumer GPUs

## Solutions Implemented

### 1. Extended Timeouts (Partial Fix)
Updated all benchmark scripts with extended timeouts:
- Warmup: 300s (5 minutes)
- Test runs: 300s (5 minutes)
- Cooldown: 5s between tests

**Files Updated:**
- `llm_benchmark.py`
- `full_qwen_benchmark.py`
- `qwen35_comparison.py`
- `test_qwen35_fixed.py` (new file)
- `benchmark_qwen35_sglang.py` (new file)

### 2. SGLang Framework Setup
SGLang is the **recommended framework** by Qwen 3.5's documentation:
- Installed SGLang: `pip install sglang`
- Created SGLang-based benchmark script
- Supports both native and Ollama-API backends

### 3. Alternative: llama.cpp
For direct GGUF model loading (bypassing Ollama issues):
```bash
# Download Qwen 3.5 GGUF from HuggingFace
# Use llama.cpp for inference
./llama.cpp/llama-cli -m qwen3.5-9b.gguf
```

## Current Status

| Model | Status | Notes |
|-------|--------|-------|
| qwen2.5:14b | ✅ Working | Baseline comparison |
| qwen3:14b | ✅ Working | Available in Ollama |
| qwen3.5:9b | ❌ Not Working | Times out on inference |
| qwen3.5:27b | ❌ Not Working | Expected same issue |

## Recommended Actions

### Option 1: Wait for Ollama Update
- Ollama team is likely working on Qwen 3.5 support
- Check https://ollama.com/library/qwen3.5 for updates
- Current Ollama version: 0.17.7

### Option 2: Use SGLang Server (Recommended)
```bash
# Install SGLang with server support
pip install sglang[serving]

# Start SGLang server with Qwen 3.5
python -m sglang.launch_server \
    --model-path qwen3.5:9b \
    --port 30000

# Run benchmark
python benchmark_qwen35_sglang.py
```

### Option 3: Use llama.cpp Directly
Download GGUF from HuggingFace and run directly:
```bash
# From Unsloth's GGUF repository
huggingface-cli download unsloth/Qwen3.5-9B-GGUF

# Run with llama.cpp
./llama-cli -m Qwen3.5-9B-Q4_K_M.gguf
```

### Option 4: Use Qwen 3.0 Instead
Qwen 3.0 (qwen3:14b) works perfectly and is available now:
```bash
ollama run qwen3:14b
```

## Benchmark Scripts Ready

| Script | Purpose | Status |
|--------|---------|--------|
| `test_qwen35_fixed.py` | Simple Qwen 3.5 test with long timeouts | Ready |
| `benchmark_qwen35_sglang.py` | SGLang-based benchmark | Ready |
| `qwen35_comparison.py` | Compare Qwen 2.5/3.0/3.5 | Updated |
| `full_qwen_benchmark.py` | Full benchmark suite | Updated |

## Test Results from Available Models

From previous runs (qwen3:14b and qwen2.5:14b):

```
Model              | Avg Tokens/sec | VRAM Usage
-------------------|----------------|------------
qwen3:14b         | ~79.5 t/s      | ~11.5 GB
qwen2.5:14b       | ~83.5 t/s      | ~10 GB
qwen2.5-coder:14b | ~82.8 t/s      | ~10 GB
```

## Next Steps

1. **Monitor Ollama Updates**: Check for Qwen 3.5 compatibility fixes
2. **Try SGLang Server**: May provide better MoE model support
3. **Use llama.cpp**: Most reliable for bleeding-edge models
4. **Compare with Qwen 3.0**: Benchmark qwen3:14b as baseline

## References

- Qwen 3.5 GitHub: https://github.com/QwenLM/Qwen3.5
- Ollama Library: https://ollama.com/library/qwen3.5
- SGLang: https://github.com/sgl-project/sglang
- Unsloth GGUFs: https://huggingface.co/unsloth

---

*Last Updated: 2026-03-07*
*Ollama Version: 0.17.7*
