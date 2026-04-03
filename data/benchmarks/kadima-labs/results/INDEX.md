# Kadima Digital Laboratories - Benchmark Results Index

## Hardware
- **GPU:** NVIDIA GeForce RTX 5070 Ti (16GB GDDR7)
- **CPU:** AMD Ryzen 9 9900X3D 12-Core
- **RAM:** 64GB DDR5
- **Board:** ASUS ROG STRIX B850-A GAMING WIFI
- **Inference:** Ollama | Windows 11 Pro

---

## Result Batches

### `legacy_20260226/` — Early Exploration
- **Date:** February 26, 2026
- **Models:** Gemma3 27B, Qwen2.5 14B/32B, DeepSeek-R1 14B/32B
- **Tests:** Initial model comparison, 3D benchmarks
- **Notes:** First round of testing, basic methodology

### `v1_initial_20260307/` — Multi-Model Benchmark v1
- **Date:** March 7, 2026
- **Models:** Qwen2.5 14B, DeepSeek-R1 14B, Gemma3 27B, Llama3.3 70B, Qwen3 14B
- **Tests:** Speed, VRAM, quality comparison (5 test categories)
- **Charts:** 13 visualizations (original + v2 improved versions)
- **Key Finding:** Qwen2.5:14b fastest at 33.1 t/s, 14B models fit optimally in 16GB VRAM

### `v1.1_qwen35_20260307/` — Qwen 3.5 Deep Dive
- **Date:** March 7, 2026 (later session)
- **Models:** Qwen 3.5 (0.8B, 4B, 9B variants)
- **Tests:** Comprehensive quality + API benchmarks
- **Notes:** Focused testing of newly released Qwen 3.5 family

### `v2_comparison_20260323/` — Nemotron + Expanded Comparison
- **Date:** March 23, 2026
- **Models:** 14 models including Nemotron 3 Nano, Nemotron Mini, Phi-4, GLM-4
- **Tests:** 5-test suite, 8-model then 14-model comparison
- **Charts:** Nemotron-focused analysis (radar, heatmap, dashboard)
- **Key Finding:** Nemotron 3 Nano Q8_0 = best accuracy+speed combo

### `v3_kadima_20260324/` — Publication-Quality Benchmark
- **Date:** March 24, 2026
- **Models:** 13 models (GPU-isolated, individual testing)
- **Tests:** 7-test suite (code, reasoning, math, summarization, instructions, analysis, creative)
- **Charts:** 6 publication-ready visualizations with Kadima branding
- **Methodology:** VRAM cleared between each model, warmup + scoring
- **Purpose:** LinkedIn publication

---

## Scripts

### Active
- `kadima_benchmark.py` — Publication-quality benchmark (v3)
- `kadima_visualize.py` — Publication chart generator

### `scripts/archived/`
- Legacy benchmark scripts from v1/v1.1 development
