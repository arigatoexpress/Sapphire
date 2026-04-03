#!/usr/bin/env python3
"""
Qwen 3.5 Comprehensive Data Collection
Collects detailed metrics for all model sizes
"""

import requests
import time
import json
import statistics
from datetime import datetime
from typing import Dict, List, Any

API_URL = "http://localhost:11434/api/generate"


def run_test(model: str, prompt: str, test_name: str, timeout: int = 300) -> Dict[str, Any]:
    """Run a single test and collect detailed metrics"""
    payload = {
        'model': model,
        'prompt': prompt,
 'stream': False,
        'options': {
            'temperature': 0.7,
            'top_p': 0.9
        }
    }
    
    start_time = time.time()
    wall_start = datetime.now().isoformat()
    
    try:
        resp = requests.post(API_URL, json=payload, timeout=timeout)
        wall_end = datetime.now().isoformat()
        total_duration = time.time() - start_time
        
        if resp.status_code == 200:
            data = resp.json()
            
            # Extract all available metrics
            result = {
                'success': True,
                'test_name': test_name,
                'prompt': prompt,
                'wall_start': wall_start,
                'wall_end': wall_end,
                'total_duration_seconds': round(total_duration, 3),
                'model': data.get('model'),
                'response': data.get('response', '')[:500],  # Truncate for storage
                'eval_count': data.get('eval_count', 0),
                'eval_duration_ns': data.get('eval_duration', 0),
                'prompt_eval_count': data.get('prompt_eval_count', 0),
                'prompt_eval_duration_ns': data.get('prompt_eval_duration', 0),
                'load_duration_ns': data.get('load_duration', 0),
                'total_duration_ns': data.get('total_duration', 0),
                'done_reason': data.get('done_reason'),
                'context_length': len(data.get('context', []))
            }
            
            # Calculate derived metrics
            if result['eval_duration_ns'] > 0:
                result['tokens_per_second'] = round(
                    result['eval_count'] / (result['eval_duration_ns'] / 1e9), 2
                )
            else:
                result['tokens_per_second'] = 0
                
            if result['prompt_eval_duration_ns'] > 0:
                result['prompt_tokens_per_second'] = round(
                    result['prompt_eval_count'] / (result['prompt_eval_duration_ns'] / 1e9), 2
                )
            else:
                result['prompt_tokens_per_second'] = 0
            
            # Time to first token approximation
            result['time_to_first_token_ms'] = round(
                (result['load_duration_ns'] + result['prompt_eval_duration_ns']) / 1e6, 2
            )
            
            return result
        else:
            return {
                'success': False,
                'test_name': test_name,
                'error': f'HTTP {resp.status_code}',
                'response': resp.text[:200]
            }
            
    except requests.Timeout:
        return {
            'success': False,
            'test_name': test_name,
            'error': f'Timeout after {timeout}s'
        }
    except Exception as e:
        return {
            'success': False,
            'test_name': test_name,
            'error': str(e)
        }


def main():
    print("=" * 80)
    print("QWEN 3.5 COMPREHENSIVE DATA COLLECTION")
    print("=" * 80)
    print(f"Start Time: {datetime.now().isoformat()}")
    print()
    
    # Models to test (smallest to largest)
    models = ['qwen3.5:0.8b', 'qwen3.5:4b', 'qwen3.5:9b']
    
    # Comprehensive test suite
    test_suite = {
        'arithmetic_simple': 'What is 2+2?',
        'arithmetic_complex': 'Calculate: (15 * 23) + (47 * 12) - (156 / 4)',
        'code_simple': 'Write a Python function hello_world() that prints "Hello World".',
        'code_complex': 'Write a Python function is_prime(n) that checks if n is prime. Include docstring and error handling.',
        'reasoning_logic': 'If a train travels 120 km in 2 hours, and another travels 150 km in 3 hours, which is faster?',
        'reasoning_math': 'A farmer has 17 sheep. All but 9 die. How many are left? Explain.',
        'explanation_simple': 'Explain what machine learning is in one sentence.',
        'explanation_complex': 'Explain quantum computing including superposition and entanglement.',
        'creative_short': 'Write a haiku about AI.',
        'creative_long': 'Write a short poem (4 lines) about the future of technology.',
        'translation': 'Translate "Hello, how are you?" to French, Spanish, and German.',
        'summarization': 'Summarize this: The quick brown fox jumps over the lazy dog. The dog was very lazy and slept all day.',
        'factual': 'What is the capital of France? Who painted the Mona Lisa?',
        'comparison': 'Compare Python and JavaScript for web development.',
        'brainstorming': 'List 3 ideas for a mobile app that helps people learn languages.'
    }
    
    all_results = {}
    system_info = {
        'timestamp': datetime.now().isoformat(),
        'hardware': 'RTX 5070 Ti 16GB',
        'api_endpoint': API_URL,
        'total_tests': len(test_suite),
        'models_tested': len(models)
    }
    
    # Run tests
    for model in models:
        print(f"\n{'='*80}")
        print(f"MODEL: {model}")
        print(f"{'='*80}")
        
        model_results = []
        
        for idx, (test_name, prompt) in enumerate(test_suite.items(), 1):
            print(f"\n[{idx}/{len(test_suite)}] {test_name}...", end=" ", flush=True)
            
            result = run_test(model, prompt, test_name)
            model_results.append(result)
            
            if result['success']:
                print(f"OK {result['tokens_per_second']:.1f} t/s "
                      f"({result['total_duration_seconds']:.1f}s, "
                      f"{result['eval_count']} tokens)")
            else:
                print(f"FAIL {result.get('error', 'Failed')}")
            
            # Adaptive cooldown based on model size
            if '0.8b' in model:
                time.sleep(1)
            elif '4b' in model:
                time.sleep(2)
            else:
                time.sleep(3)
        
        all_results[model] = model_results
        
        # Print model summary
        successful = [r for r in model_results if r['success']]
        if successful:
            avg_tps = statistics.mean([r['tokens_per_second'] for r in successful])
            avg_duration = statistics.mean([r['total_duration_seconds'] for r in successful])
            print(f"\n  Summary: {len(successful)}/{len(test_suite)} tests passed")
            print(f"  Average Speed: {avg_tps:.1f} t/s")
            print(f"  Average Duration: {avg_duration:.1f}s")
        
        # Longer cooldown between models
        time.sleep(10)
    
    # Save all data
    output = {
        'system_info': system_info,
        'test_suite': test_suite,
        'results': all_results,
        'collection_end': datetime.now().isoformat()
    }
    
    filename = f'qwen35_complete_data_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n\n{'='*80}")
    print(f"DATA COLLECTION COMPLETE")
    print(f"{'='*80}")
    print(f"Results saved to: {filename}")
    print(f"End Time: {datetime.now().isoformat()}")


if __name__ == "__main__":
    main()
