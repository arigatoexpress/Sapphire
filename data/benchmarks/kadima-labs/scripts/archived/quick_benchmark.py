#!/usr/bin/env python3
"""
Quick AI Benchmark for Local LLMs via Ollama
Tests key models with shorter prompts for faster results
"""

import json
import time
import subprocess
import sys
from datetime import datetime

def run_model_test(model, prompt, timeout=120):
    """Test a single model with a prompt"""
    start = time.time()
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='utf-8',
            errors='ignore'
        )
        duration = time.time() - start
        output = result.stdout if result.returncode == 0 else ""
        
        # Estimate tokens (rough: ~4 chars per token)
        tokens = (len(prompt) + len(output)) // 4
        tps = tokens / duration if duration > 0 else 0
        
        return {
            "success": result.returncode == 0,
            "duration": round(duration, 2),
            "tokens_per_sec": round(tps, 2),
            "tokens": tokens,
            "output_preview": output[:500] if output else ""
        }
    except Exception as e:
        return {"success": False, "error": str(e), "duration": timeout, "tokens_per_sec": 0}

def main():
    # Models to test (prioritizing Qwen and comparison models)
    models = [
        "qwen3:14b",           # Latest Qwen
        "qwen2.5:14b",         # Previous Qwen generation
        "deepseek-r1:14b",     # Reasoning model comparison
        "gemma3:27b",          # Google model comparison
    ]
    
    # Shorter test prompts
    tests = {
        "reasoning": "What is 15 + 27? Explain.",
        "coding": "Write a Python function to add two numbers.",
        "knowledge": "What is machine learning in one sentence?"
    }
    
    results = {
        "timestamp": datetime.now().isoformat(),
        "hardware": {
            "gpu": "NVIDIA GeForce RTX 5070 Ti 16GB",
            "cpu": "AMD Ryzen 9 9900X3D",
            "ram": "64GB"
        },
        "models": {}
    }
    
    print("="*60)
    print("QUICK AI BENCHMARK")
    print("="*60)
    print(f"Testing {len(models)} models with {len(tests)} prompts each\n")
    
    for model in models:
        print(f"\nTesting: {model}")
        print("-"*40)
        results["models"][model] = {}
        
        for test_name, prompt in tests.items():
            print(f"  {test_name}...", end=" ")
            result = run_model_test(model, prompt)
            results["models"][model][test_name] = result
            
            if result["success"]:
                print(f"{result['tokens_per_sec']:.1f} t/s, {result['duration']:.1f}s")
            else:
                print("FAILED")
        
        # Calculate average
        successes = [r for r in results["models"][model].values() if r.get("success")]
        if successes:
            avg_tps = sum(r["tokens_per_sec"] for r in successes) / len(successes)
            avg_time = sum(r["duration"] for r in successes) / len(successes)
            results["models"][model]["summary"] = {
                "avg_tokens_per_sec": round(avg_tps, 2),
                "avg_duration": round(avg_time, 2),
                "tests_passed": f"{len(successes)}/{len(tests)}"
            }
            print(f"  Average: {avg_tps:.1f} tokens/sec")
        
        time.sleep(2)  # Cooldown
    
    # Save results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"quick_benchmark_{timestamp}.json"
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    # Print summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for model, data in results["models"].items():
        if "summary" in data:
            s = data["summary"]
            print(f"{model}:")
            print(f"  Avg Speed: {s['avg_tokens_per_sec']:.1f} tokens/sec")
            print(f"  Avg Time: {s['avg_duration']:.1f}s")
            print(f"  Tests: {s['tests_passed']}")
    
    print(f"\nResults saved to: {filename}")
    return results

if __name__ == "__main__":
    main()
