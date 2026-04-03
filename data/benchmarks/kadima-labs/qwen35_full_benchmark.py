#!/usr/bin/env python3
"""
Qwen 3.5 Full Benchmark - Smallest to Largest
Tests: 0.8b -> 4b -> 9b
"""

import requests
import time
import json
import statistics
from datetime import datetime

OLLAMA_API = "http://localhost:11434/api/generate"


def benchmark_model(model, prompt, timeout=300):
    """Benchmark a single model"""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    
    start = time.time()
    try:
        resp = requests.post(OLLAMA_API, json=payload, timeout=timeout)
        duration = time.time() - start
        
        if resp.status_code == 200:
            data = resp.json()
            output = data.get('response', '')
            tokens = data.get('eval_count', 0)
            tps = tokens / duration if duration > 0 else 0
            
            return {
                'success': True,
                'duration': round(duration, 2),
                'tokens': tokens,
                'tps': round(tps, 2),
                'output': output[:150]
            }
        else:
            return {'success': False, 'error': f'HTTP {resp.status_code}'}
    except requests.Timeout:
        return {'success': False, 'error': f'Timeout after {timeout}s'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def run_test_suite(model, tests):
    """Run a suite of tests on a model"""
    print(f"\n{'='*60}")
    print(f"Testing: {model}")
    print(f"{'='*60}")
    
    results = {}
    for test_name, prompt in tests.items():
        print(f"\n  {test_name}...", end=" ", flush=True)
        result = benchmark_model(model, prompt)
        results[test_name] = result
        
        if result['success']:
            print(f"OK - {result['tps']:.1f} t/s ({result['duration']:.1f}s)")
        else:
            print(f"FAILED - {result.get('error', 'Unknown')}")
        time.sleep(2)
    
    return results


def main():
    print("=" * 70)
    print("QWEN 3.5 BENCHMARK - Smallest to Largest")
    print("=" * 70)
    print("Testing: 0.8b -> 4b -> 9b")
    print()
    
    # Test from smallest to largest
    models = ['qwen3.5:0.8b', 'qwen3.5:4b', 'qwen3.5:9b']
    
    # Test prompts
    tests = {
        'hello': 'Say hello briefly.',
        'math': 'What is 15 * 23?',
        'code': 'Write a Python function is_prime(n).',
        'reasoning': 'A farmer has 17 sheep. All but 9 die. How many remain?',
        'creative': 'Write a haiku about AI.'
    }
    
    all_results = {}
    
    for model in models:
        results = run_test_suite(model, tests)
        all_results[model] = results
        time.sleep(5)  # Cooldown between models
    
    # Summary
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    
    print("\nTokens/Second by Model:")
    print("-" * 70)
    print(f"{'Model':<15} {'Hello':>8} {'Math':>8} {'Code':>8} {'Reason':>8} {'Creative':>8} {'Avg':>8}")
    print("-" * 70)
    
    for model, data in all_results.items():
        speeds = []
        speed_strs = []
        for test in tests.keys():
            tps = data.get(test, {}).get('tps', 0)
            speeds.append(tps)
            speed_strs.append(f"{tps:.1f}" if tps > 0 else "N/A")
        
        avg_speed = statistics.mean([s for s in speeds if s > 0]) if speeds else 0
        print(f"{model:<15} {speed_strs[0]:>8} {speed_strs[1]:>8} {speed_strs[2]:>8} {speed_strs[3]:>8} {speed_strs[4]:>8} {avg_speed:>8.1f}")
    
    # Performance scaling analysis
    print("\n" + "=" * 70)
    print("PERFORMANCE SCALING ANALYSIS")
    print("=" * 70)
    
    model_sizes = {'qwen3.5:0.8b': 0.8, 'qwen3.5:4b': 4, 'qwen3.5:9b': 9}
    
    for test in tests.keys():
        print(f"\n{test.upper()}:")
        for model in models:
            result = all_results[model].get(test, {})
            if result.get('success'):
                size = model_sizes.get(model, 0)
                tps = result['tps']
                print(f"  {model:<15} {tps:>6.1f} t/s  ({size}B params)")
    
    # Save results
    output = {
        'timestamp': datetime.now().isoformat(),
        'hardware': 'RTX 5070 Ti 16GB',
        'results': all_results
    }
    
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'qwen35_full_benchmark_{ts}.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n\nResults saved to: {filename}")


if __name__ == "__main__":
    main()
