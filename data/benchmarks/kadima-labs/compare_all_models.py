#!/usr/bin/env python3
"""
Comprehensive Model Comparison Benchmark
Tests all locally available models on identical tasks
Generates comparison rankings by category
"""

import json
import time
import subprocess
import sys
import os
from datetime import datetime

# Fix Windows encoding
os.environ["PYTHONIOENCODING"] = "utf-8"
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Models to test - grouped by size tier
# Only include models that fit in 16GB VRAM
MODELS = {
    # --- Nemotron family (NVIDIA) ---
    "nemotron-3-nano:4b": {"tier": "small", "family": "Nemotron", "params": "4B"},
    "nemotron-3-nano:4b-q8_0": {"tier": "small", "family": "Nemotron", "params": "4B-q8"},
    "nemotron-3-nano:4b-bf16": {"tier": "medium", "family": "Nemotron", "params": "4B-bf16"},
    "nemotron-mini:4b": {"tier": "small", "family": "Nemotron", "params": "4B"},

    # --- Microsoft Phi family ---
    "phi4-mini": {"tier": "small", "family": "Phi", "params": "3.8B"},
    "phi4": {"tier": "medium", "family": "Phi", "params": "14B"},

    # --- Qwen family (Alibaba) ---
    "qwen3.5:4b": {"tier": "small", "family": "Qwen", "params": "4B"},
    "qwen3.5:9b": {"tier": "medium", "family": "Qwen", "params": "9B"},
    "qwen2.5:14b": {"tier": "medium", "family": "Qwen", "params": "14B"},
    "qwen2.5-coder:14b": {"tier": "medium", "family": "Qwen", "params": "14B"},
    "qwen3:14b": {"tier": "medium", "family": "Qwen", "params": "14B"},

    # --- DeepSeek ---
    "deepseek-r1:14b": {"tier": "medium", "family": "DeepSeek", "params": "14B"},

    # --- Zhipu AI GLM ---
    "glm4:9b": {"tier": "medium", "family": "GLM", "params": "9B"},

    # --- Google Gemma ---
    "gemma3:27b": {"tier": "large", "family": "Gemma", "params": "27B"},
}

TESTS = {
    "math": {
        "prompt": "Solve step-by-step: A store has 30% off sale. Item costs $85, plus 8% tax after discount. What is the final price? Give the numerical answer.",
        "expected_contains": "64.26",
        "category": "reasoning",
    },
    "logic": {
        "prompt": "Three friends Alice, Bob, Carol have professions: doctor, engineer, teacher. Alice is not doctor. Engineer is not Bob. Carol is older than teacher. Who has which job? Give direct answers.",
        "expected_contains": "engineer",  # Alice is engineer
        "category": "reasoning",
    },
    "code": {
        "prompt": "Write a Python function to check if a string is a valid palindrome, ignoring spaces and case. Include type hints. Just the function, no explanation.",
        "expected_contains": "def",
        "category": "coding",
    },
    "context": {
        "prompt": "Sarah ordered 50 books, 10 damaged (returned). Sold 15 Wednesday. Got 30 new Friday, sold 8 more. How many in stock? Just the number and brief calculation.",
        "expected_contains": "47",
        "category": "reasoning",
    },
    "creative": {
        "prompt": "Write a haiku about artificial intelligence. Exactly 3 lines, 5-7-5 syllable pattern.",
        "expected_contains": None,  # subjective
        "category": "creative",
    },
}


def run_test(model, prompt, timeout=120):
    """Run a single test and return timing + output"""
    start = time.time()
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True, text=True, timeout=timeout,
            encoding='utf-8', errors='ignore'
        )
        elapsed = time.time() - start
        output = result.stdout.strip() if result.returncode == 0 else ""
        tokens_est = len(output) // 4
        tps = tokens_est / elapsed if elapsed > 0 else 0
        return {
            "success": result.returncode == 0,
            "output": output[:500],
            "time": round(elapsed, 2),
            "tokens": tokens_est,
            "tps": round(tps, 1),
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "output": "", "time": timeout, "tokens": 0, "tps": 0}
    except Exception as e:
        return {"success": False, "output": str(e), "time": 0, "tokens": 0, "tps": 0}


def check_model_available(model):
    """Check if model is available in ollama"""
    try:
        result = subprocess.run(
            ["ollama", "show", model], capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except:
        return False


def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Filter to available models
    available = {}
    print("Checking model availability...")
    for model, info in MODELS.items():
        if check_model_available(model):
            available[model] = info
            print(f"  [OK] {model}")
        else:
            print(f"  [SKIP] {model} - not installed")

    print(f"\n{'='*70}")
    print(f"COMPREHENSIVE MODEL COMPARISON BENCHMARK")
    print(f"Models: {len(available)} | Tests: {len(TESTS)} | Total runs: {len(available) * len(TESTS)}")
    print(f"{'='*70}\n")

    all_results = {}

    for model, info in available.items():
        print(f"\n{'-'*50}")
        print(f"Model: {model} ({info['family']} {info['params']}, {info['tier']} tier)")
        print(f"{'-'*50}")

        # Warmup
        print("  Warming up...", end=" ", flush=True)
        run_test(model, "Hello", timeout=60)
        print("done")
        time.sleep(2)

        model_results = {"info": info, "tests": {}}

        for test_name, test_config in TESTS.items():
            print(f"  [{test_name}]...", end=" ", flush=True)
            result = run_test(model, test_config["prompt"])

            # Check correctness
            if test_config["expected_contains"]:
                result["correct"] = test_config["expected_contains"].lower() in result["output"].lower()
            else:
                result["correct"] = result["success"]

            result["category"] = test_config["category"]
            model_results["tests"][test_name] = result

            status = "OK" if result["correct"] else "WRONG"
            print(f"{result['time']:.1f}s | {result['tps']:.0f} t/s | {status}")

        # Model summary
        tests = model_results["tests"]
        ok_tests = [t for t in tests.values() if t["success"]]
        correct_tests = [t for t in tests.values() if t.get("correct")]

        model_results["summary"] = {
            "avg_tps": round(sum(t["tps"] for t in ok_tests) / len(ok_tests), 1) if ok_tests else 0,
            "avg_time": round(sum(t["time"] for t in ok_tests) / len(ok_tests), 1) if ok_tests else 0,
            "total_tokens": sum(t["tokens"] for t in ok_tests),
            "accuracy": f"{len(correct_tests)}/{len(tests)}",
            "success_rate": f"{len(ok_tests)}/{len(tests)}",
        }

        all_results[model] = model_results
        print(f"  Summary: {model_results['summary']['avg_tps']} t/s avg | {model_results['summary']['accuracy']} correct")
        time.sleep(3)  # GPU cooldown

    # Final comparison
    print(f"\n\n{'='*70}")
    print("FINAL RANKINGS")
    print(f"{'='*70}")

    # Sort by average TPS
    ranked_speed = sorted(all_results.items(), key=lambda x: x[1]["summary"]["avg_tps"], reverse=True)
    print(f"\n{'Speed Rankings (tokens/sec)':}")
    print(f"{'Model':<25} {'Tier':<8} {'Avg t/s':<10} {'Accuracy':<10} {'Avg Time':<10}")
    print(f"{'-'*63}")
    for i, (model, data) in enumerate(ranked_speed, 1):
        s = data["summary"]
        info = data["info"]
        print(f"{i}. {model:<22} {info['tier']:<8} {s['avg_tps']:<10} {s['accuracy']:<10} {s['avg_time']:<10}")

    # Accuracy ranking
    ranked_accuracy = sorted(all_results.items(),
        key=lambda x: (
            int(x[1]["summary"]["accuracy"].split("/")[0]),
            x[1]["summary"]["avg_tps"]
        ), reverse=True)
    print(f"\n{'Accuracy Rankings':}")
    print(f"{'Model':<25} {'Tier':<8} {'Accuracy':<10} {'Avg t/s':<10}")
    print(f"{'-'*53}")
    for i, (model, data) in enumerate(ranked_accuracy, 1):
        s = data["summary"]
        info = data["info"]
        print(f"{i}. {model:<22} {info['tier']:<8} {s['accuracy']:<10} {s['avg_tps']:<10}")

    # Per-test breakdown
    print(f"\n{'Per-Test Speed Comparison (t/s)':}")
    header = f"{'Model':<25}"
    for test in TESTS:
        header += f" {test:<10}"
    print(header)
    print("─" * (25 + 11 * len(TESTS)))
    for model, data in ranked_speed:
        row = f"{model:<25}"
        for test in TESTS:
            t = data["tests"].get(test, {})
            tps = t.get("tps", 0)
            correct = t.get("correct", False)
            mark = f"{tps:.0f}" + ("*" if not correct else "")
            row += f" {mark:<10}"
        print(row)
    print("(* = incorrect answer)")

    # Save results
    outfile = f"D:/Dev/01_AI/AI_Benchmark/model_comparison_{timestamp}.json"
    with open(outfile, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "models_tested": len(available),
            "tests_per_model": len(TESTS),
            "results": {k: v for k, v in all_results.items()},
        }, f, indent=2)
    print(f"\nResults saved to: {outfile}")

    return outfile


if __name__ == "__main__":
    main()
