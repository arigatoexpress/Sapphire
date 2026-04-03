#!/usr/bin/env python3
"""Final Qwen Benchmark - All Models"""

import subprocess
import json
import time
from datetime import datetime

models = ['qwen2.5:14b', 'qwen2.5-coder:14b', 'qwen3:14b', 'qwen2.5:32b']
prompts = {
    'reasoning': 'Solve: A farmer has 17 sheep. All but 9 die. How many left?',
    'code': 'Write Python function is_prime(n) with docstring.',
    'math': 'Calculate: (15 * 23) + (47 * 12) - (156 / 4)',
    'creative': 'Write a haiku about AI.'
}

results = {}

for model in models:
    print(f'Testing {model}...')
    results[model] = {}
    
    # Warmup
    subprocess.run(['curl', '-s', 'http://localhost:11434/api/generate', 
                   '-H', 'Content-Type: application/json', 
                   '-d', json.dumps({'model': model, 'prompt': 'Hi', 'stream': False})], 
                  capture_output=True, timeout=60)
    time.sleep(2)
    
    for test_name, prompt in prompts.items():
        try:
            result = subprocess.run(
                ['curl', '-s', 'http://localhost:11434/api/generate', 
                 '-H', 'Content-Type: application/json',
                 '-d', json.dumps({'model': model, 'prompt': prompt, 'stream': False})],
                capture_output=True, timeout=90
            )
            r = json.loads(result.stdout.decode('utf-8', errors='ignore'))
            tps = r.get('eval_count', 0) / (r.get('eval_duration', 1) / 1e9) if r.get('eval_duration') else 0
            results[model][test_name] = round(tps, 1)
            print(f'  {test_name}: {tps:.1f} t/s')
        except Exception as e:
            results[model][test_name] = 0
            print(f'  {test_name}: FAILED - {e}')
        time.sleep(1)
    
    # Calculate avg
    speeds = [v for v in results[model].values() if isinstance(v, (int, float)) and v > 0]
    if speeds:
        results[model]['avg'] = round(sum(speeds) / len(speeds), 1)
        print(f'  AVERAGE: {results[model]["avg"]:.1f} t/s')
    print()
    time.sleep(3)

# Save results
output = {
    'timestamp': datetime.now().isoformat(),
    'models': results
}
with open('final_qwen_results.json', 'w') as f:
    json.dump(output, f, indent=2)

print('='*60)
print('FINAL RANKINGS')
print('='*60)
sorted_models = sorted(results.items(), key=lambda x: x[1].get('avg', 0), reverse=True)
for i, (model, data) in enumerate(sorted_models, 1):
    avg = data.get('avg', 0)
    print(f'{i}. {model:<25} {avg:>6.1f} t/s')
