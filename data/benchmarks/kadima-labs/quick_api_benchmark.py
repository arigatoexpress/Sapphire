#!/usr/bin/env python3
"""Quick benchmark of 14B Qwen models"""

import json
import time
import subprocess
from datetime import datetime
import statistics

def run_inference(model, prompt, timeout=60):
    payload = {"model": model, "prompt": prompt, "stream": False}
    start = time.time()
    try:
        result = subprocess.run(
            ["curl", "-s", "http://localhost:11434/api/generate",
             "-H", "Content-Type: application/json",
             "-d", json.dumps(payload)],
            capture_output=True, timeout=timeout
        )
        duration = time.time() - start
        if result.returncode == 0:
            response = json.loads(result.stdout.decode('utf-8', errors='ignore'))
            tokens = response.get("eval_count", 0)
            eval_dur = response.get("eval_duration", 1) / 1e9
            return {
                "success": True,
                "duration": round(duration, 2),
                "tokens_per_sec": round(tokens / eval_dur, 2) if eval_dur > 0 else 0,
                "tokens": tokens
            }
        return {"success": False, "error": "curl failed", "duration": duration}
    except Exception as e:
        return {"success": False, "error": str(e), "duration": timeout}

def benchmark_model(model):
    print(f"\n{'='*60}")
    print(f"Testing: {model}")
    print(f"{'='*60}")
    
    # Warmup
    print("  Warmup...", end=" ")
    w = run_inference(model, "Hi", timeout=30)
    print(f"OK ({w.get('tokens_per_sec', 0):.0f} t/s)")
    time.sleep(2)
    
    tests = {
        "reasoning": "What is 15 + 27? Explain.",
        "code": "Write a Python function to add two numbers.",
        "math": "Calculate 25 * 4.",
        "creative": "Write a haiku about AI."
    }
    
    results = {"model": model, "tests": {}}
    for name, prompt in tests.items():
        print(f"  {name}...", end=" ")
        r = run_inference(model, prompt, timeout=45)
        results["tests"][name] = r
        if r["success"]:
            print(f"{r['tokens_per_sec']:.0f} t/s")
        else:
            print(f"FAIL: {r.get('error', 'Unknown')}")
        time.sleep(1)
    
    successful = [t for t in results["tests"].values() if t["success"]]
    if successful:
        results["summary"] = {
            "avg_tps": round(statistics.mean([t["tokens_per_sec"] for t in successful]), 1),
            "min_tps": round(min([t["tokens_per_sec"] for t in successful]), 1),
            "max_tps": round(max([t["tokens_per_sec"] for t in successful]), 1),
            "tests_passed": f"{len(successful)}/{len(tests)}"
        }
        print(f"\n  Avg: {results['summary']['avg_tps']:.1f} t/s")
    
    return results

def main():
    models = ["qwen3:14b", "qwen2.5-coder:14b", "qwen2.5:14b"]
    
    print("="*60)
    print("QUICK QWEN BENCHMARK (14B Models)")
    print("="*60)
    
    all_results = []
    for model in models:
        try:
            result = benchmark_model(model)
            all_results.append(result)
        except Exception as e:
            print(f"Error: {e}")
            all_results.append({"model": model, "error": str(e)})
        time.sleep(3)
    
    # Save
    filename = f"quick_qwen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump({"models": all_results, "timestamp": datetime.now().isoformat()}, f, indent=2)
    
    # Report
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")
    
    successful = [r for r in all_results if "summary" in r]
    sorted_results = sorted(successful, key=lambda x: x["summary"]["avg_tps"], reverse=True)
    
    for i, r in enumerate(sorted_results, 1):
        s = r["summary"]
        print(f"{i}. {r['model']:<20} {s['avg_tps']:>6.1f} t/s  ({s['tests_passed']})")
    
    print(f"\nSaved to: {filename}")

if __name__ == "__main__":
    main()
