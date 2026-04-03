#!/usr/bin/env python3
import requests
import time
from datetime import datetime

models = ['qwen3.5:9b', 'qwen3:14b', 'qwen2.5:14b']
prompt = 'What is 2+2? Answer briefly.'

print('='*60)
print('QUICK QWEN 3.5 BENCHMARK')
print('='*60)

results = {}

for model in models:
    print(f'\nTesting {model}...')
    payload = {'model': model, 'prompt': prompt, 'stream': False}
    
    start = time.time()
    try:
        resp = requests.post('http://localhost:11434/api/generate', json=payload, timeout=120)
        duration = time.time() - start
        
        if resp.status_code == 200:
            data = resp.json()
            tokens = data.get('eval_count', 0)
            tps = tokens / duration if duration > 0 else 0
            results[model] = {'tps': tps, 'duration': duration, 'tokens': tokens}
            print(f'  {tps:.1f} t/s ({duration:.1f}s, {tokens} tokens)')
            out = data.get('response', '')[:60]
            print(f'  Output: {out}...')
        else:
            print(f'  Error: HTTP {resp.status_code}')
    except Exception as e:
        print(f'  Error: {e}')
    time.sleep(2)

print('\n' + '='*60)
print('SUMMARY')
print('='*60)
for model, r in results.items():
    print(f'{model:<20} {r["tps"]:>6.1f} t/s  ({r["duration"]:.1f}s)')
