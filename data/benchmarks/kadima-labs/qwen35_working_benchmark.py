#!/usr/bin/env python3
"""
Qwen 3.5 Working Benchmark - Using Ollama API
"""

import requests
import time
import json
from datetime import datetime

OLLAMA_API = "http://localhost:11434/api/generate"


def benchmark_model(model, prompt, timeout=300):
    """Benchmark a single model"""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    
    print(f"  Prompt: {prompt[:50]}...")
    print(f"  Running (timeout: {timeout}s)...", end=" ", flush=True)
    
    start = time.time()
    try:
        resp = requests.post(OLLAMA_API, json=payload, timeout=timeout)
        duration = time.time() - start
        
        if resp.status_code == 200:
            data = resp.json()
            tokens = data.get('eval_count', 0)
            tps = tokens / duration if duration > 0 else 0
            
            print(f"OK")
            print(f"    Duration: {duration:.1f}s")
            print(f"    Tokens: {tokens}")
            print(f"    Speed: {tps:.1f} t/s")
            
            return {
                'success': True,
                'duration': round(duration, 2),
                'tokens': tokens,
                'tps': round(tps, 2)
            }
        else:
            print(f"FAILED - HTTP {resp.status_code}")
            return {'success': False, 'error': f'HTTP {resp.status_code}'}
    except requests.Timeout:
        print(f"TIMEOUT after {timeout}s")
        return {'success': False, 'error': 'Timeout'}
    except Exception as e:
        print(f"ERROR: {e}")
        return {'success': False, 'error': str(e)}


def main():
    print("=" * 70)
    print("QWEN 3.5 WORKING BENCHMARK")
    print("=" * 70)
    print()
    
    models = ['qwen3.5:9b', 'qwen3:14b', 'qwen2.5:14b']
    prompt = 'What is machine learning? Explain briefly.'
    
    results = {}
    
    for model in models:
        print(f"\nTesting: {model}")
        print("-" * 50)
        results[model] = benchmark_model(model, prompt, timeout=300)
        time.sleep(3)
    
    # Summary
    print()
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print()
    print(f"{'Model':<20} {'Speed (t/s)':>12} {'Duration (s)':>14} {'Status':>10}")
    print("-" * 70)
    
    for model, r in results.items():
        if r.get('success'):
            print(f"{model:<20} {r['tps']:>12.1f} {r['duration']:>14.1f} {'OK':>10}")
        else:
            print(f"{model:<20} {'N/A':>12} {'N/A':>14} {r.get('error', 'FAIL'):>10}")
    
    # Save results
    output = {
        'timestamp': datetime.now().isoformat(),
        'prompt': prompt,
        'results': results
    }
    
    filename = f'qwen35_final_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)
    
    print()
    print(f"Results saved to: {filename}")


if __name__ == "__main__":
    main()
