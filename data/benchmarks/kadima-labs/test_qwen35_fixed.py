#!/usr/bin/env python3
"""
Fixed Qwen 3.5 Benchmark - Handles slow first-load times
"""

import json
import time
import subprocess
import sys
from datetime import datetime


def run_with_long_timeout(model, prompt, timeout=300):
    """Run model with extended timeout for MoE model loading"""
    start = time.time()
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True, text=True, timeout=timeout,
            encoding='utf-8', errors='ignore'
        )
        duration = time.time() - start
        
        if result.returncode == 0:
            output = result.stdout
            # Better token estimation for Qwen 3.5
            tokens = len(output) // 3.5  # Qwen uses ~3.5 chars/token
            return {
                "success": True,
                "duration": round(duration, 2),
                "tokens_per_sec": round(tokens / duration, 2) if duration > 0 else 0,
                "output_length": len(output),
                "output": output[:500]
            }
        else:
            return {"success": False, "error": result.stderr[:200]}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    print("="*70)
    print("QWEN 3.5 BENCHMARK (Fixed for slow first-load)")
    print("="*70)
    print()
    
    # Check available models
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    qwen35_models = [line.split()[0] for line in result.stdout.split('\n')[1:] 
                     if 'qwen3.5' in line.lower()]
    
    if not qwen35_models:
        print("❌ No Qwen 3.5 models found!")
        print("Run: ollama pull qwen3.5:9b")
        return
    
    print(f"Found Qwen 3.5 models: {qwen35_models}")
    print()
    
    # Test prompts
    tests = {
        "hello": "Say hello and introduce yourself briefly.",
        "math": "What is 15 * 23? Show your work.",
        "code": "Write a Python function is_prime(n).",
        "reasoning": "A farmer has 17 sheep. All but 9 die. How many remain?"
    }
    
    all_results = {}
    
    for model in qwen35_models:
        print(f"\n{'='*70}")
        print(f"Testing: {model}")
        print(f"{'='*70}")
        
        model_results = {}
        
        for test_name, prompt in tests.items():
            print(f"\n{test_name.upper()} TEST:")
            print(f"Prompt: {prompt[:50]}...")
            print(f"Running (timeout: 5 min for first load)...")
            
            result = run_with_long_timeout(model, prompt, timeout=300)
            model_results[test_name] = result
            
            if result["success"]:
                print(f"✅ SUCCESS - {result['duration']:.1f}s, {result['tokens_per_sec']:.1f} t/s")
                print(f"   Preview: {result['output'][:100]}...")
            else:
                print(f"❌ FAILED - {result.get('error', 'Unknown error')}")
            
            time.sleep(3)  # Cooldown between tests
        
        all_results[model] = model_results
    
    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    
    for model, results in all_results.items():
        print(f"\n{model}:")
        for test_name, result in results.items():
            if result["success"]:
                print(f"  ✅ {test_name}: {result['duration']:.1f}s, {result['tokens_per_sec']:.1f} t/s")
            else:
                print(f"  ❌ {test_name}: {result.get('error', 'Failed')}")
    
    # Save results
    filename = f"qwen35_fixed_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "results": all_results
        }, f, indent=2)
    
    print(f"\n✅ Results saved to: {filename}")


if __name__ == "__main__":
    main()
