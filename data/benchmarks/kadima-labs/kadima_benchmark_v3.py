"""
Kadima Digital Laboratories - Local LLM Benchmark Suite v3
============================================================
Publication-quality benchmark for small open-source models on consumer GPU.
GPU-isolated testing with real token counts from Ollama API.

Hardware: AMD Ryzen 9 9900X3D | NVIDIA RTX 5070 Ti 16GB | 64GB DDR5
Platform: ASUS ROG STRIX B850-A | Windows 11 Pro | Ollama
"""

import json
import time
import datetime
import subprocess
import sys
import os
import urllib.request
import urllib.error

# Fix Windows console encoding
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# -- Configuration ----------------------------------------------------------

HARDWARE_SPEC = {
    "lab": "Kadima Digital Laboratories",
    "cpu": "AMD Ryzen 9 9900X3D 12-Core",
    "gpu": "NVIDIA GeForce RTX 5070 Ti (16GB GDDR7)",
    "ram": "64GB DDR5",
    "motherboard": "ASUS ROG STRIX B850-A GAMING WIFI",
    "storage": "Samsung 990 EVO Plus 2TB NVMe",
    "os": "Windows 11 Pro",
    "inference_engine": "Ollama",
}

# Models: Only GPU-bound models that achieve 20+ t/s on RTX 5070 Ti 16GB
MODELS = [
    # NVIDIA Nemotron
    {"name": "nemotron-3-nano:4b",       "label": "Nemotron 3 Nano 4B",  "family": "NVIDIA",     "params": "4B",   "quant": "Q4_K_M", "size_gb": 2.8},
    {"name": "nemotron-3-nano:4b-q8_0",  "label": "Nemotron 3 Nano Q8",  "family": "NVIDIA",     "params": "4B",   "quant": "Q8_0",   "size_gb": 4.2},
    {"name": "nemotron-mini:4b",         "label": "Nemotron Mini 4B",    "family": "NVIDIA",     "params": "4B",   "quant": "Q4_K_M", "size_gb": 2.7},
    # Google Gemma
    {"name": "gemma3:4b",                "label": "Gemma 3 4B",          "family": "Google",     "params": "4B",   "quant": "Q4_K_M", "size_gb": 3.3},
    {"name": "gemma3n:e4b",              "label": "Gemma 3n E4B",        "family": "Google",     "params": "~4B",  "quant": "F16",    "size_gb": 7.5},
    # Meta Llama
    {"name": "llama3.2:3b",              "label": "Llama 3.2 3B",        "family": "Meta",       "params": "3B",   "quant": "Q4_K_M", "size_gb": 2.0},
    # Microsoft Phi
    {"name": "phi4-mini:latest",         "label": "Phi-4 Mini 3.8B",     "family": "Microsoft",  "params": "3.8B", "quant": "Q4_K_M", "size_gb": 2.5},
    {"name": "phi4:latest",              "label": "Phi-4 14B",           "family": "Microsoft",  "params": "14B",  "quant": "Q4_K_M", "size_gb": 9.1},
    # IBM Granite
    {"name": "granite3.3:2b",            "label": "Granite 3.3 2B",      "family": "IBM",        "params": "2B",   "quant": "Q4_K_M", "size_gb": 1.5},
    # Alibaba Qwen (non-thinking only)
    {"name": "qwen3.5:4b",              "label": "Qwen 3.5 4B",         "family": "Alibaba",    "params": "4B",   "quant": "Q4_K_M", "size_gb": 3.4, "chat_api": True, "think_off": True},
]

# Expanded test suite: 8 diverse, verifiable tests
TESTS = [
    {
        "id": "code_gen",
        "category": "Code Generation",
        "prompt": "Write a Python function called `fibonacci(n)` that returns the nth Fibonacci number using dynamic programming. Include a docstring. Only output the code, no explanation.",
        "verify": lambda r: "def fibonacci" in r and "for" in r,
    },
    {
        "id": "reasoning",
        "category": "Logical Reasoning",
        "prompt": "A farmer has 17 sheep. All but 9 die. How many sheep are left? Answer with just the number.",
        "verify": lambda r: "9" in r.strip().split('\n')[-1],
    },
    {
        "id": "math",
        "category": "Arithmetic",
        "prompt": "What is 247 * 83? Show your work, then give the final answer on the last line.",
        "verify": lambda r: "20501" in r.replace(",", "").replace(" ", ""),
    },
    {
        "id": "summarization",
        "category": "Summarization",
        "prompt": "Summarize blockchain technology in exactly 3 sentences. Be precise and technical.",
        "verify": lambda r: len([s for s in r.replace('...', '.').split('.') if s.strip()]) >= 2 and any(w in r.lower() for w in ["block", "chain", "ledger", "decentrali", "hash", "distributed"]),
    },
    {
        "id": "instruction",
        "category": "Instruction Following",
        "prompt": "List exactly 5 programming languages that start with the letter P. Format: numbered 1-5, one per line. No other text.",
        "verify": lambda r: sum(1 for line in r.strip().split('\n') if line.strip() and any(c.isalpha() for c in line)) >= 4 and any(w in r.lower() for w in ["python", "perl", "php", "pascal", "prolog"]),
    },
    {
        "id": "json_output",
        "category": "Structured Output",
        "prompt": 'Return a valid JSON object with keys "name", "age", and "city" for a fictional person. Output ONLY the JSON, nothing else.',
        "verify": lambda r: "{" in r and "}" in r and '"name"' in r and '"age"' in r and '"city"' in r,
    },
    {
        "id": "translation",
        "category": "Translation",
        "prompt": "Translate 'The quick brown fox jumps over the lazy dog' into Spanish. Output only the translation.",
        "verify": lambda r: any(w in r.lower() for w in ["zorro", "rapido", "perro", "perezoso", "salta"]),
    },
    {
        "id": "creative",
        "category": "Creative Writing",
        "prompt": "Write a haiku about artificial intelligence. Follow the 5-7-5 syllable structure.",
        "verify": lambda r: len(r.strip().split('\n')) >= 3 and len(r.strip()) > 20,
    },
]


def clear_gpu():
    """Unload all models from Ollama to clear VRAM."""
    try:
        result = subprocess.run(["ollama", "ps"], capture_output=True, encoding='utf-8', errors='replace', timeout=10)
        for line in result.stdout.strip().split('\n')[1:]:
            model_name = line.split()[0] if line.strip() else None
            if model_name:
                subprocess.run(["ollama", "stop", model_name], capture_output=True, encoding='utf-8', errors='replace', timeout=30)
        time.sleep(3)
    except Exception as e:
        print(f"  [WARN] GPU clear: {e}")


def warmup_model(model_name, use_chat=False):
    """Load model into VRAM with a trivial prompt via API."""
    try:
        if use_chat:
            payload = json.dumps({"model": model_name, "messages": [{"role": "user", "content": "Hi"}], "stream": False, "think": False, "options": {"num_predict": 16}}).encode('utf-8')
            url = "http://localhost:11434/api/chat"
        else:
            payload = json.dumps({"model": model_name, "prompt": "Hi", "stream": False, "options": {"num_predict": 16}}).encode('utf-8')
            url = "http://localhost:11434/api/generate"
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req, timeout=120)
        time.sleep(1)
    except Exception:
        pass


def run_test(model_name, prompt, timeout=120, use_chat=False, think_off=False):
    """Run a single test via Ollama API."""
    start = time.perf_counter()
    try:
        if use_chat:
            body = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"num_predict": 512},
            }
            if think_off:
                body["think"] = False
            url = "http://localhost:11434/api/chat"
        else:
            body = {
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 512},
            }
            url = "http://localhost:11434/api/generate"

        payload = json.dumps(body).encode('utf-8')
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        elapsed = time.perf_counter() - start
        response = data.get("message", {}).get("content", "").strip() if use_chat else data.get("response", "").strip()

        eval_count = data.get("eval_count", 0)
        eval_duration_ns = data.get("eval_duration", 0)

        if eval_duration_ns > 0 and eval_count > 0:
            tps = eval_count / (eval_duration_ns / 1e9)
        elif elapsed > 0:
            tps = max(len(response) // 4, 1) / elapsed
            eval_count = max(len(response) // 4, 1)
        else:
            tps = 0

        return {
            "response": response,
            "time_seconds": round(elapsed, 2),
            "tokens": eval_count,
            "tokens_per_second": round(tps, 1),
            "success": True,
            "error": None,
        }
    except Exception as e:
        return {
            "response": "",
            "time_seconds": round(time.perf_counter() - start, 2),
            "tokens": 0,
            "tokens_per_second": 0,
            "success": False,
            "error": str(e)[:100],
        }


def benchmark_model(model_info, tests):
    """Benchmark a single model across all tests with GPU isolation."""
    model_name = model_info["name"]
    label = model_info["label"]
    use_chat = model_info.get("chat_api", False)
    think_off = model_info.get("think_off", False)

    print(f"\n{'='*60}")
    print(f"  {label}  ({model_info['params']} | {model_info['quant']} | {model_info['size_gb']}GB)")
    print(f"  Family: {model_info['family']}  |  Model: {model_name}")
    print(f"{'='*60}")

    print(f"  Clearing VRAM...", end=" ", flush=True)
    clear_gpu()
    print("done.")

    print(f"  Loading model...", end=" ", flush=True)
    warmup_model(model_name, use_chat=use_chat)
    print("done.")

    results = []
    correct = 0
    total_time = 0
    total_tokens = 0
    tps_values = []

    for i, test in enumerate(tests):
        print(f"  [{i+1}/{len(tests)}] {test['category']:.<25s}", end=" ", flush=True)
        result = run_test(model_name, test["prompt"], use_chat=use_chat, think_off=think_off)

        passed = False
        if result["success"] and result["response"]:
            try:
                passed = test["verify"](result["response"])
            except Exception:
                passed = False

        if passed:
            correct += 1

        total_time += result["time_seconds"]
        total_tokens += result["tokens"]
        if result["tokens_per_second"] > 0:
            tps_values.append(result["tokens_per_second"])

        status = "PASS" if passed else "FAIL"
        print(f"{status}  {result['time_seconds']:>5.1f}s  {result['tokens_per_second']:>6.1f} t/s")

        results.append({
            "test_id": test["id"],
            "category": test["category"],
            "passed": passed,
            "time_seconds": result["time_seconds"],
            "tokens": result["tokens"],
            "tokens_per_second": result["tokens_per_second"],
        })

    avg_tps = sum(tps_values) / len(tps_values) if tps_values else 0
    acc = round(correct / len(tests) * 100, 1)

    print(f"  {'-'*50}")
    print(f"  Score: {correct}/{len(tests)} ({acc}%)  |  Avg: {avg_tps:.0f} t/s  |  Total: {total_time:.1f}s")

    return {
        "model": model_name,
        "label": label,
        "family": model_info["family"],
        "params": model_info["params"],
        "quantization": model_info["quant"],
        "model_size_gb": model_info["size_gb"],
        "tests_passed": correct,
        "tests_total": len(tests),
        "accuracy_pct": acc,
        "total_time_seconds": round(total_time, 2),
        "avg_tokens_per_second": round(avg_tps, 1),
        "avg_response_time": round(total_time / len(tests), 2),
        "test_results": results,
    }


def main():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = "D:/Dev/01_AI/AI_Benchmark"
    output_file = f"{output_dir}/kadima_benchmark_{timestamp}.json"

    # Filter to models that are actually available
    available_models = []
    print("Checking model availability...")
    result = subprocess.run(["ollama", "list"], capture_output=True, encoding='utf-8', errors='replace', timeout=10)
    installed = result.stdout.lower() if result.stdout else ""

    for m in MODELS:
        tag = m["name"].split(":")[0]
        if tag in installed:
            available_models.append(m)
            print(f"  [OK] {m['label']}")
        else:
            print(f"  [--] {m['label']} (not installed, skipping)")

    if not available_models:
        print("ERROR: No models available!")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  KADIMA DIGITAL LABORATORIES")
    print(f"  Local LLM Benchmark Suite v3.0")
    print(f"{'='*60}")
    print(f"  {HARDWARE_SPEC['cpu']}  |  {HARDWARE_SPEC['gpu']}")
    print(f"  {HARDWARE_SPEC['ram']}  |  {HARDWARE_SPEC['motherboard']}")
    print(f"  {HARDWARE_SPEC['os']}  |  {HARDWARE_SPEC['inference_engine']}")
    print(f"  {datetime.datetime.now().strftime('%B %d, %Y %I:%M %p')}")
    print(f"  Models: {len(available_models)}  |  Tests: {len(TESTS)}")
    print(f"  Method: GPU-isolated, VRAM cleared between models")
    print(f"{'='*60}")

    all_results = []
    for i, model in enumerate(available_models):
        print(f"\n>>> [{i+1}/{len(available_models)}]")
        try:
            result = benchmark_model(model, TESTS)
            all_results.append(result)
        except Exception as e:
            print(f"  [ERROR] {model['label']}: {e}")

    clear_gpu()

    output = {
        "metadata": {
            "lab": "Kadima Digital Laboratories",
            "hardware": HARDWARE_SPEC,
            "version": "3.0",
            "timestamp": timestamp,
            "date": datetime.datetime.now().isoformat(),
            "models_tested": len(all_results),
            "tests_per_model": len(TESTS),
            "categories": [t["category"] for t in TESTS],
            "methodology": "GPU-isolated: VRAM cleared between models. Only GPU-bound models (20+ t/s). Real token counts via Ollama API. 512 token output cap.",
        },
        "results": sorted(all_results, key=lambda x: (-x["accuracy_pct"], -x["avg_tokens_per_second"]))
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print leaderboard
    print(f"\n{'='*60}")
    print(f"  LEADERBOARD")
    print(f"{'='*60}")
    print(f"  {'#':<3} {'Model':<25} {'Score':>7} {'Speed':>8} {'Size':>6}")
    print(f"  {'-'*3} {'-'*25} {'-'*7} {'-'*8} {'-'*6}")

    for rank, r in enumerate(output["results"], 1):
        medal = {1: ">>", 2: "> ", 3: "> "}.get(rank, "  ")
        print(f"  {medal}{rank:<1} {r['label']:<25} {r['accuracy_pct']:>5.0f}%  {r['avg_tokens_per_second']:>5.0f} t/s  {r['model_size_gb']:>4.1f}GB")

    print(f"{'='*60}")
    print(f"  Saved: {output_file}")

    return output_file


if __name__ == "__main__":
    main()
