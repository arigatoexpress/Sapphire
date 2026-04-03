"""
Kadima Digital Laboratories - Local LLM Benchmark Suite
========================================================
Publication-quality benchmark testing individual models with GPU isolation.
Tests each model one at a time, clearing VRAM between runs for accurate results.

Hardware: AMD Ryzen 9 9900X3D | NVIDIA RTX 5070 Ti 16GB | 64GB DDR5
Platform: ASUS ROG STRIX B850-A | Windows 11 Pro | Ollama
"""

import datetime
import json
import subprocess
import time
import urllib.error
import urllib.request

# ── Configuration ──────────────────────────────────────────────────────────

HARDWARE_SPEC = {
    "lab": "Kadima Digital Laboratories",
    "cpu": "AMD Ryzen 9 9900X3D 12-Core Processor",
    "gpu": "NVIDIA GeForce RTX 5070 Ti (16GB GDDR7)",
    "ram": "64GB DDR5",
    "motherboard": "ASUS ROG STRIX B850-A GAMING WIFI",
    "storage": [
        "Samsung SSD 990 EVO Plus 2TB (Primary)",
        "Samsung SSD 970 EVO 1TB",
        "Seagate IronWolf 4TB HDD"
    ],
    "os": "Windows 11 Pro (Build 26200)",
    "inference_engine": "Ollama",
    "driver": "NVIDIA 32.0.15.9579"
}

# Models to benchmark (excluding Gemma 27B - different weight class)
MODELS = [
    # Nemotron Family (NVIDIA)
    {"name": "nemotron-3-nano:4b",       "label": "Nemotron 3 Nano 4B (Q4)",     "family": "NVIDIA Nemotron",  "params": "4B",  "quant": "Q4_K_M"},
    {"name": "nemotron-3-nano:4b-q8_0",  "label": "Nemotron 3 Nano 4B (Q8)",     "family": "NVIDIA Nemotron",  "params": "4B",  "quant": "Q8_0"},
    {"name": "nemotron-3-nano:4b-bf16",  "label": "Nemotron 3 Nano 4B (BF16)",   "family": "NVIDIA Nemotron",  "params": "4B",  "quant": "BF16"},
    {"name": "nemotron-mini:4b",         "label": "Nemotron Mini 4B",             "family": "NVIDIA Nemotron",  "params": "4B",  "quant": "Q4_K_M"},
    # Qwen Family (Alibaba) — NOTE: Qwen 3.5 uses thinking mode, needs /no_think or API think=false
    {"name": "qwen3.5:4b",              "label": "Qwen 3.5 4B",                  "family": "Alibaba Qwen",     "params": "4B",  "quant": "Q4_K_M", "think": False},
    {"name": "qwen3.5:9b",              "label": "Qwen 3.5 9B",                  "family": "Alibaba Qwen",     "params": "9B",  "quant": "Q4_K_M", "think": False},
    {"name": "qwen3:14b",               "label": "Qwen 3 14B",                   "family": "Alibaba Qwen",     "params": "14B", "quant": "Q4_K_M"},
    {"name": "qwen2.5:14b",             "label": "Qwen 2.5 14B",                 "family": "Alibaba Qwen",     "params": "14B", "quant": "Q4_K_M"},
    {"name": "qwen2.5-coder:14b",       "label": "Qwen 2.5 Coder 14B",           "family": "Alibaba Qwen",     "params": "14B", "quant": "Q4_K_M"},
    # Microsoft Phi
    {"name": "phi4-mini:latest",         "label": "Phi-4 Mini 3.8B",              "family": "Microsoft Phi",    "params": "3.8B","quant": "Q4_K_M"},
    {"name": "phi4:latest",              "label": "Phi-4 14B",                    "family": "Microsoft Phi",    "params": "14B", "quant": "Q4_K_M"},
    # DeepSeek
    {"name": "deepseek-r1:14b",          "label": "DeepSeek-R1 14B",              "family": "DeepSeek",         "params": "14B", "quant": "Q4_K_M"},
    # GLM (Tsinghua/Zhipu)
    {"name": "glm4:9b",                  "label": "GLM-4 9B",                     "family": "Zhipu GLM",        "params": "9B",  "quant": "Q4_K_M"},
]

# Test prompts - diverse, deterministic, verifiable
TESTS = [
    {
        "id": "code_gen",
        "category": "Code Generation",
        "prompt": "Write a Python function called `fibonacci(n)` that returns the nth Fibonacci number using dynamic programming. Include a docstring. Only output the code, no explanation.",
        "verify": lambda r: "def fibonacci" in r and ("dp" in r.lower() or "memo" in r.lower() or "[0]" in r or "prev" in r.lower() or "for" in r),
        "description": "Generate a DP-based Fibonacci function"
    },
    {
        "id": "reasoning",
        "category": "Logical Reasoning",
        "prompt": "A farmer has 17 sheep. All but 9 die. How many sheep are left? Think step by step, then give your final answer as just a number on the last line.",
        "verify": lambda r: "9" in r.split('\n')[-1] or "9" in r.split('\n')[-2] if r.strip() else False,
        "description": "Classic logic puzzle requiring careful reading"
    },
    {
        "id": "math",
        "category": "Mathematics",
        "prompt": "What is 247 * 83? Show your work step by step, then give the final answer on the last line.",
        "verify": lambda r: "20501" in r.replace(",", "").replace(" ", ""),
        "description": "Multi-digit multiplication with verification"
    },
    {
        "id": "summarization",
        "category": "Summarization",
        "prompt": "Summarize the concept of blockchain technology in exactly 3 sentences. Be precise and technical.",
        "verify": lambda r: len([s for s in r.replace('...', '.').split('.') if s.strip()]) >= 2 and any(w in r.lower() for w in ["block", "chain", "ledger", "decentrali", "hash", "distributed"]),
        "description": "Concise technical summarization"
    },
    {
        "id": "instruction_follow",
        "category": "Instruction Following",
        "prompt": "List exactly 5 programming languages that start with the letter P. Format each on its own line, numbered 1-5. Do not include any other text.",
        "verify": lambda r: sum(1 for line in r.strip().split('\n') if line.strip() and any(c.isalpha() for c in line)) >= 4 and any(w in r.lower() for w in ["python", "perl", "php", "pascal", "prolog", "powershell"]),
        "description": "Precise instruction following with formatting"
    },
    {
        "id": "analysis",
        "category": "Data Analysis",
        "prompt": "Given the numbers [23, 45, 12, 67, 34, 89, 5, 56], what is the mean, median, and standard deviation? Show your calculations.",
        "verify": lambda r: "41" in r.replace(" ", "") and ("34" in r or "39" in r or "39.5" in r),
        "description": "Statistical analysis requiring calculation"
    },
    {
        "id": "creative",
        "category": "Creative Writing",
        "prompt": "Write a haiku about artificial intelligence. Follow the traditional 5-7-5 syllable structure.",
        "verify": lambda r: len(r.strip().split('\n')) >= 3 and len(r.strip()) > 20,
        "description": "Creative output within structural constraints"
    },
]


def clear_gpu():
    """Unload all models from Ollama to clear VRAM."""
    try:
        # Get loaded models
        result = subprocess.run(
            ["ollama", "ps"],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().split('\n')[1:]  # Skip header
        for line in lines:
            model_name = line.split()[0] if line.strip() else None
            if model_name:
                subprocess.run(
                    ["ollama", "stop", model_name],
                    capture_output=True, text=True, timeout=30
                )
        time.sleep(3)  # Let VRAM fully release
    except Exception as e:
        print(f"  [WARN] GPU clear: {e}")


def warmup_model(model_name):
    """Load model into VRAM with a trivial prompt."""
    try:
        subprocess.run(
            ["ollama", "run", model_name, "Hi"],
            capture_output=True, encoding='utf-8', errors='replace', timeout=120
        )
        time.sleep(1)
    except Exception:
        pass


def run_test(model_name, prompt, timeout=300, disable_think=False):
    """Run a single test via Ollama API (avoids encoding issues, gives real token counts)."""
    start = time.perf_counter()
    try:
        if disable_think:
            # Use chat API with think=false for Qwen 3.5 thinking models
            payload = json.dumps({
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "think": False,
                "options": {
                    "num_predict": 1024,
                }
            }).encode('utf-8')
        else:
            payload = json.dumps({
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": 1024,
                }
            }).encode('utf-8')

        api_endpoint = "http://localhost:11434/api/chat" if disable_think else "http://localhost:11434/api/generate"
        req = urllib.request.Request(
            api_endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        elapsed = time.perf_counter() - start
        if disable_think:
            response = data.get("message", {}).get("content", "").strip()
        else:
            response = data.get("response", "").strip()

        # Use real token counts from Ollama API
        eval_count = data.get("eval_count", 0)
        eval_duration_ns = data.get("eval_duration", 0)
        total_duration_ns = data.get("total_duration", 0)

        if eval_duration_ns > 0 and eval_count > 0:
            tokens_per_sec = eval_count / (eval_duration_ns / 1e9)
        elif elapsed > 0 and eval_count > 0:
            tokens_per_sec = eval_count / elapsed
        else:
            token_estimate = max(len(response) // 4, 1)
            tokens_per_sec = token_estimate / elapsed if elapsed > 0 else 0
            eval_count = token_estimate

        return {
            "response": response,
            "time_seconds": round(elapsed, 2),
            "tokens_generated": eval_count,
            "tokens_per_second": round(tokens_per_sec, 1),
            "prompt_tokens": data.get("prompt_eval_count", 0),
            "success": True,
            "error": None
        }
    except (urllib.error.URLError, TimeoutError) as e:
        return {
            "response": "",
            "time_seconds": round(time.perf_counter() - start, 2),
            "tokens_generated": 0,
            "tokens_per_second": 0,
            "prompt_tokens": 0,
            "success": False,
            "error": f"timeout or connection error: {e}"
        }
    except Exception as e:
        return {
            "response": "",
            "time_seconds": round(time.perf_counter() - start, 2),
            "tokens_generated": 0,
            "tokens_per_second": 0,
            "prompt_tokens": 0,
            "success": False,
            "error": str(e)
        }


def benchmark_model(model_info, tests):
    """Benchmark a single model across all tests with GPU isolation."""
    model_name = model_info["name"]
    label = model_info["label"]

    print(f"\n{'='*70}")
    print(f"  BENCHMARKING: {label}")
    print(f"  Model: {model_name} | Family: {model_info['family']}")
    print(f"{'='*70}")

    # Step 1: Clear GPU
    print("  [1/3] Clearing GPU VRAM...")
    clear_gpu()

    # Step 2: Warm up model
    print("  [2/3] Loading model into VRAM...")
    warmup_model(model_name)

    # Step 3: Run tests
    disable_think = model_info.get("think", None) is False
    if disable_think:
        print("  [!] Thinking mode disabled for this model")
    print(f"  [3/3] Running {len(tests)} tests...")
    results = []
    correct = 0
    total_time = 0
    total_tokens = 0

    for i, test in enumerate(tests):
        print(f"    Test {i+1}/{len(tests)}: {test['category']}...", end=" ", flush=True)
        result = run_test(model_name, test["prompt"], disable_think=disable_think)

        # Verify correctness
        passed = False
        if result["success"] and result["response"]:
            try:
                passed = test["verify"](result["response"])
            except Exception:
                passed = False

        if passed:
            correct += 1

        total_time += result["time_seconds"]
        total_tokens += result.get("tokens_generated", 0)

        status = "PASS" if passed else "FAIL"
        print(f"{status} ({result['time_seconds']:.1f}s, ~{result['tokens_per_second']:.0f} t/s)")

        results.append({
            "test_id": test["id"],
            "category": test["category"],
            "description": test["description"],
            "passed": passed,
            **result
        })

    avg_tps = total_tokens / total_time if total_time > 0 else 0

    summary = {
        "model": model_name,
        "label": label,
        "family": model_info["family"],
        "params": model_info["params"],
        "quantization": model_info["quant"],
        "tests_passed": correct,
        "tests_total": len(tests),
        "accuracy_pct": round(correct / len(tests) * 100, 1),
        "total_time_seconds": round(total_time, 2),
        "avg_tokens_per_second": round(avg_tps, 1),
        "avg_response_time": round(total_time / len(tests), 2),
        "test_results": results
    }

    print(f"\n  Result: {correct}/{len(tests)} passed ({summary['accuracy_pct']}%) | Avg: {avg_tps:.0f} t/s | Total: {total_time:.1f}s")

    return summary


def main():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = "D:/Dev/01_AI/AI_Benchmark"
    output_file = f"{output_dir}/kadima_benchmark_{timestamp}.json"

    print("=" * 70)
    print("  KADIMA DIGITAL LABORATORIES")
    print("  Local LLM Benchmark Suite v2.0")
    print("=" * 70)
    print(f"  CPU:  {HARDWARE_SPEC['cpu']}")
    print(f"  GPU:  {HARDWARE_SPEC['gpu']}")
    print(f"  RAM:  {HARDWARE_SPEC['ram']}")
    print(f"  Board: {HARDWARE_SPEC['motherboard']}")
    print(f"  OS:   {HARDWARE_SPEC['os']}")
    print(f"  Engine: {HARDWARE_SPEC['inference_engine']}")
    print(f"  Date: {datetime.datetime.now().strftime('%B %d, %Y at %I:%M %p')}")
    print(f"  Models: {len(MODELS)} | Tests per model: {len(TESTS)}")
    print("=" * 70)

    all_results = []

    for i, model in enumerate(MODELS):
        print(f"\n>>> Model {i+1}/{len(MODELS)}: {model['label']}")
        try:
            result = benchmark_model(model, TESTS)
            all_results.append(result)
        except Exception as e:
            print(f"  [ERROR] {model['label']}: {e}")
            all_results.append({
                "model": model["name"],
                "label": model["label"],
                "family": model["family"],
                "params": model["params"],
                "quantization": model["quant"],
                "tests_passed": 0,
                "tests_total": len(TESTS),
                "accuracy_pct": 0,
                "total_time_seconds": 0,
                "avg_tokens_per_second": 0,
                "avg_response_time": 0,
                "test_results": [],
                "error": str(e)
            })

    # Final cleanup
    clear_gpu()

    # Save results
    output = {
        "metadata": {
            "lab": HARDWARE_SPEC["lab"],
            "hardware": HARDWARE_SPEC,
            "benchmark_version": "2.0",
            "timestamp": timestamp,
            "date": datetime.datetime.now().isoformat(),
            "total_models": len(MODELS),
            "tests_per_model": len(TESTS),
            "test_categories": [t["category"] for t in TESTS],
            "methodology": "GPU-isolated testing: VRAM cleared between each model, warmup run before scoring"
        },
        "results": sorted(all_results, key=lambda x: (-x["accuracy_pct"], -x["avg_tokens_per_second"]))
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*70}")
    print("  BENCHMARK COMPLETE")
    print(f"  Results saved to: {output_file}")
    print(f"{'='*70}")

    # Print leaderboard
    print(f"\n{'='*70}")
    print("  KADIMA DIGITAL LABORATORIES - LEADERBOARD")
    print(f"{'='*70}")
    print(f"  {'Rank':<5} {'Model':<30} {'Acc':>6} {'Avg t/s':>8} {'Avg Time':>9}")
    print(f"  {'-'*5} {'-'*30} {'-'*6} {'-'*8} {'-'*9}")

    for rank, r in enumerate(output["results"], 1):
        acc = f"{r['accuracy_pct']}%"
        tps = f"{r['avg_tokens_per_second']:.0f}"
        avg_t = f"{r['avg_response_time']:.1f}s"
        print(f"  {rank:<5} {r['label']:<30} {acc:>6} {tps:>8} {avg_t:>9}")

    print(f"{'='*70}")

    return output_file


if __name__ == "__main__":
    output_file = main()
