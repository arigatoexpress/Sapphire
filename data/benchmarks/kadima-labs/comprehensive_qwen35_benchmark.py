#!/usr/bin/env python3
"""
Comprehensive Qwen 3.5 Benchmark Suite
Tests all sizes with multiple scenarios
"""

import requests
import time
import json
import statistics
from datetime import datetime

API_URL = "http://localhost:11434/api/generate"


def test_model(model, prompt, timeout=180):
    """Test a single prompt"""
    payload = {'model': model, 'prompt': prompt, 'stream': False}
    
    start = time.time()
    try:
        resp = requests.post(API_URL, json=payload, timeout=timeout)
        duration = time.time() - start
        
        if resp.status_code == 200:
            data = resp.json()
            tokens = data.get('eval_count', 0)
            tps = tokens / duration if duration > 0 else 0
            return {
                'success': True,
                'tps': round(tps, 2),
                'duration': round(duration, 2),
                'tokens': tokens
            }
    except Exception as e:
        pass
    
    return {'success': False}


def main():
    print("=" * 70)
    print("COMPREHENSIVE QWEN 3.5 BENCHMARK")
    print("=" * 70)
    
    models = ['qwen3.5:0.8b', 'qwen3.5:4b', 'qwen3.5:9b']
    
    test_suite = {
        'simple_math': 'What is 2+2?',
        'complex_math': 'Calculate 15 * 23 + 47 * 12',
        'code': 'Write a Python function to check if a number is prime.',
        'reasoning': 'If a train travels 120 km in 2 hours, what is its speed?',
        'explanation': 'Explain quantum computing in simple terms.',
        'creative': 'Write a haiku about artificial intelligence.'
    }
    
    results = {model: {} for model in models}
    
    # Test from smallest to largest
    for model in models:
        print(f"\n{'='*70}")
        print(f"Testing: {model}")
        print(f"{'='*70}")
        
        for test_name, prompt in test_suite.items():
            print(f"\n  {test_name}...", end=" ", flush=True)
            result = test_model(model, prompt)
            results[model][test_name] = result
            
            if result['success']:
                print(f"OK - {result['tps']:.1f} t/s ({result['duration']:.1f}s)")
            else:
                print("FAILED")
            
            time.sleep(2)
        
        time.sleep(5)  # Cooldown between models
    
    # Generate Report
    print("\n" + "=" * 70)
    print("BENCHMARK REPORT")
    print("=" * 70)
    
    # Table 1: Speed Comparison
    print("\n1. SPEED COMPARISON (Tokens/Second)")
    print("-" * 70)
    
    headers = ['Model'] + list(test_suite.keys()) + ['Average']
    print(f"{headers[0]:<15}", end="")
    for h in headers[1:]:
        print(f"{h:>12}", end="")
    print()
    print("-" * 70)
    
    for model in models:
        print(f"{model:<15}", end="")
        speeds = []
        for test in test_suite.keys():
            tps = results[model].get(test, {}).get('tps', 0)
            speeds.append(tps)
            if tps > 0:
                print(f"{tps:>12.1f}", end="")
            else:
                print(f"{'N/A':>12}", end="")
        
        avg = statistics.mean([s for s in speeds if s > 0]) if speeds else 0
        print(f"{avg:>12.1f}")
    
    # Table 2: Response Time
    print("\n2. RESPONSE TIME (Seconds)")
    print("-" * 70)
    
    print(f"{headers[0]:<15}", end="")
    for h in headers[1:]:
        print(f"{h:>12}", end="")
    print()
    print("-" * 70)
    
    for model in models:
        print(f"{model:<15}", end="")
        durations = []
        for test in test_suite.keys():
            dur = results[model].get(test, {}).get('duration', 0)
            durations.append(dur)
            if dur > 0:
                print(f"{dur:>12.1f}", end="")
            else:
                print(f"{'N/A':>12}", end="")
        
        avg_dur = statistics.mean([d for d in durations if d > 0]) if durations else 0
        print(f"{avg_dur:>12.1f}")
    
    # Analysis
    print("\n3. PERFORMANCE ANALYSIS")
    print("-" * 70)
    
    model_info = {
        'qwen3.5:0.8b': {'size': 0.8, 'params': '0.8B'},
        'qwen3.5:4b': {'size': 4, 'params': '4B'},
        'qwen3.5:9b': {'size': 9, 'params': '9B'}
    }
    
    print("\nModel Size vs Performance:")
    for model in models:
        all_speeds = [r.get('tps', 0) for r in results[model].values() if r.get('success')]
        if all_speeds:
            avg_tps = statistics.mean(all_speeds)
            info = model_info[model]
            print(f"  {model:<15} {info['params']:>6} -> {avg_tps:>6.1f} t/s")
    
    # Efficiency (tps per billion params)
    print("\nEfficiency (Tokens/sec per Billion Parameters):")
    for model in models:
        all_speeds = [r.get('tps', 0) for r in results[model].values() if r.get('success')]
        if all_speeds:
            avg_tps = statistics.mean(all_speeds)
            info = model_info[model]
            efficiency = avg_tps / info['size']
            print(f"  {model:<15} {efficiency:>6.1f} t/s/B")
    
    # Save results
    output = {
        'timestamp': datetime.now().isoformat(),
        'hardware': 'RTX 5070 Ti 16GB',
        'ollama_version': '0.17.7',
        'results': results
    }
    
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'qwen35_comprehensive_{ts}.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n\nResults saved to: {filename}")


if __name__ == "__main__":
    main()
