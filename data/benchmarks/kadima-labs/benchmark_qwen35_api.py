#!/usr/bin/env python3
"""
Qwen 3.5 Benchmark using Ollama API
Works with terminal-based Ollama
"""

import json
import time
import requests
from datetime import datetime
from typing import Dict, List, Any
import statistics

OLLAMA_API = "http://localhost:11434/api/generate"


def run_benchmark_api(model: str, prompt: str, timeout: int = 300) -> Dict[str, Any]:
    """Run benchmark using Ollama API"""
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    
    start = time.time()
    try:
        response = requests.post(OLLAMA_API, json=payload, timeout=timeout)
        duration = time.time() - start
        
        if response.status_code == 200:
            data = response.json()
            output = data.get('response', '')
            eval_count = data.get('eval_count', 0)
            eval_duration = data.get('eval_duration', 1) / 1e9  # Convert ns to seconds
            
            # Calculate tokens per second
            tps = eval_count / eval_duration if eval_duration > 0 else 0
            
            return {
                'success': True,
                'duration': round(duration, 2),
                'tokens': eval_count,
                'tokens_per_sec': round(tps, 2),
                'output': output[:200],
                'thinking': output.get('thinking', '')[:200] if isinstance(output, dict) else ''
            }
        else:
            return {'success': False, 'error': f'HTTP {response.status_code}'}
    except requests.Timeout:
        return {'success': False, 'error': f'Timeout after {timeout}s'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def main():
    print("=" * 70)
    print("QWEN 3.5 BENCHMARK (API Version)")
    print("=" * 70)
    print()
    
    # Test models
    models = ['qwen3.5:9b', 'qwen3:14b', 'qwen2.5:14b', 'qwen2.5-coder:14b']
    
    tests = {
        'hello': 'Say hello and introduce yourself briefly.',
        'math': 'What is 15 * 23? Show your work.',
        'code': 'Write a Python function is_prime(n).',
        'reasoning': 'A farmer has 17 sheep. All but 9 die. How many remain?'
    }
    
    results = {}
    
    print("=" * 70)
    print("RUNNING TESTS")
    print("=" * 70)
    
    for model in models:
        print(f"\nTesting: {model}")
        print("-" * 40)
        
        model_results = {}
        
        for test_name, prompt in tests.items():
            print(f"  {test_name}... ", end='', flush=True)
            
            result = run_benchmark_api(model, prompt)
            model_results[test_name] = result
            
            if result['success']:
                print(f"OK - {result['tokens_per_sec']:.1f} t/s ({result['duration']:.1f}s)")
            else:
                print(f"FAILED - {result.get('error', 'Unknown')}")
            
            time.sleep(2)
        
        results[model] = model_results
    
    # Summary
    print()
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    
    print("\nSpeed Comparison (Tokens/Second):")
    print("-" * 70)
    print(f"{'Model':<25} {'Hello':<10} {'Math':<10} {'Code':<10} {'Reasoning':<10}")
    print("-" * 70)
    
    for model, data in results.items():
        speeds = []
        for test in tests.keys():
            tps = data.get(test, {}).get('tokens_per_sec', 0)
            speeds.append(f"{tps:.1f}" if tps > 0 else "N/A")
        print(f"{model:<25} {speeds[0]:<10} {speeds[1]:<10} {speeds[2]:<10} {speeds[3]:<10}")
    
    # Calculate averages for successful tests
    print("\nAverage Tokens/Second (per model):")
    print("-" * 40)
    for model, data in results.items():
        speeds = [t.get('tokens_per_sec', 0) for t in data.values() if t.get('success')]
        if speeds:
            avg = statistics.mean(speeds)
            print(f"{model:<25} {avg:.1f} t/s")
    
    # Save results
    output = {
        'timestamp': datetime.now().isoformat(),
        'hardware': 'RTX 5070 Ti 16GB',
        'results': results
    }
    
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'qwen35_api_results_{ts}.json'
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults saved to: {filename}")


if __name__ == "__main__":
    main()
