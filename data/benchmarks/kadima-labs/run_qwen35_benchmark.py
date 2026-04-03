#!/usr/bin/env python3
"""
Qwen 3.5 Benchmark - Terminal Version
"""

import json
import time
import subprocess
import sys
from datetime import datetime


def run_test(model, prompt, timeout=600):
    """Run a single test"""
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
            tokens = len(output) // 3.5
            tps = tokens / duration if duration > 0 else 0
            return {
                'success': True,
                'tokens_per_sec': round(tps, 2),
                'duration': round(duration, 2),
                'output': output[:100]
            }
        else:
            return {'success': False, 'error': result.stderr[:100]}
    except subprocess.TimeoutExpired:
        return {'success': False, 'error': f'Timeout after {timeout}s'}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def main():
    print("=" * 70)
    print("QWEN 3.5 BENCHMARK")
    print("=" * 70)
    print()
    
    # Check available models
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
    lines = result.stdout.strip().split('\n')[1:]
    
    qwen_models = []
    for line in lines:
        if line.strip() and 'qwen' in line.lower():
            model_name = line.split()[0]
            qwen_models.append(model_name)
    
    print(f"Found Qwen models: {qwen_models}")
    print()
    
    if not qwen_models:
        print("No Qwen models found!")
        return
    
    # Test prompts
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
    
    for model in qwen_models:
        print(f"\nTesting: {model}")
        print("-" * 40)
        
        model_results = {}
        
        for test_name, prompt in tests.items():
            print(f"  {test_name}... ", end='', flush=True)
            
            result = run_test(model, prompt)
            model_results[test_name] = result
            
            if result['success']:
                print(f"OK - {result['tokens_per_sec']:.1f} t/s ({result['duration']:.1f}s)")
            else:
                print(f"FAILED - {result.get('error', 'Unknown')}")
            
            time.sleep(3)
        
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
    
    # Save results
    output = {
        'timestamp': datetime.now().isoformat(),
        'hardware': 'RTX 5070 Ti 16GB',
        'results': results
    }
    
    filename = f'qwen35_terminal_results_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\nResults saved to: {filename}")


if __name__ == "__main__":
    main()
