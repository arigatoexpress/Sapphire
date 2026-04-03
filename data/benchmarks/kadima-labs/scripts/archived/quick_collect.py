#!/usr/bin/env python3
"""Quick data collection for Qwen 3.5"""
import requests
import time
import json
from datetime import datetime

API_URL = "http://localhost:11434/api/generate"

models = ['qwen3.5:0.8b', 'qwen3.5:4b', 'qwen3.5:9b']
tests = {
    'arithmetic_simple': 'What is 2+2?',
    'arithmetic_complex': 'Calculate 15 * 23',
    'code_simple': 'Write hello world in Python',
    'code_complex': 'Write is_prime function',
    'reasoning_logic': 'Train 120km in 2h, speed?',
    'reasoning_math': '17 sheep, 9 die, how many left?',
    'explanation_simple': 'Explain ML in one sentence',
    'explanation_complex': 'Explain quantum computing',
    'creative_short': 'Write a haiku about AI',
    'creative_long': 'Write poem about technology',
}

results = {}
print("Collecting data...")

for model in models:
    print(f"\n{model}:")
    model_results = []
    
    for test_name, prompt in tests.items():
        print(f"  {test_name}...", end=" ", flush=True)
        
        payload = {'model': model, 'prompt': prompt, 'stream': False}
        start = time.time()
        
        try:
            resp = requests.post(API_URL, json=payload, timeout=120)
            duration = time.time() - start
            
            if resp.status_code == 200:
                data = resp.json()
                result = {
                    'success': True,
                    'test_name': test_name,
                    'tokens_per_second': data.get('eval_count', 0) / (data.get('eval_duration', 1) / 1e9),
                    'total_duration_seconds': duration,
                    'eval_count': data.get('eval_count', 0),
                    'time_to_first_token_ms': (data.get('load_duration', 0) + data.get('prompt_eval_duration', 0)) / 1e6
                }
                model_results.append(result)
                print(f"OK ({result['tokens_per_second']:.1f} t/s)")
            else:
                model_results.append({'success': False, 'test_name': test_name})
                print("FAIL")
        except Exception as e:
            model_results.append({'success': False, 'test_name': test_name, 'error': str(e)})
            print("ERROR")
        
        time.sleep(2)
    
    results[model] = model_results
    time.sleep(5)

# Save
output = {
    'system_info': {
        'timestamp': datetime.now().isoformat(),
        'hardware': 'RTX 5070 Ti 16GB',
        'api_endpoint': API_URL,
        'total_tests': len(tests),
        'models_tested': len(models)
    },
    'test_suite': tests,
    'results': results
}

ts = datetime.now().strftime('%Y%m%d_%H%M%S')
filename = f'qwen35_complete_data_{ts}.json'
with open(filename, 'w') as f:
    json.dump(output, f, indent=2)

print(f"\n\nSaved to: {filename}")
