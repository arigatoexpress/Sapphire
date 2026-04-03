#!/usr/bin/env python3
"""Quick Qwen 3.5 test - all sizes"""
import requests
import time
import json
from datetime import datetime

models = ['qwen3.5:0.8b', 'qwen3.5:4b', 'qwen3.5:9b']
prompt = 'What is 2+2? Answer briefly.'

print("QWEN 3.5 QUICK TEST - All Sizes")
print("=" * 60)

results = {}

for model in models:
    print(f"\n{model}:")
    payload = {'model': model, 'prompt': prompt, 'stream': False}
    
    start = time.time()
    try:
        resp = requests.post('http://localhost:11434/api/generate', 
                           json=payload, timeout=180)
        duration = time.time() - start
        
        if resp.status_code == 200:
            data = resp.json()
            tokens = data.get('eval_count', 0)
            tps = tokens / duration if duration > 0 else 0
            results[model] = {'tps': tps, 'duration': duration, 'tokens': tokens}
            print(f"  Speed: {tps:.1f} t/s")
            print(f"  Time: {duration:.1f}s")
            print(f"  Tokens: {tokens}")
        else:
            print(f"  Error: HTTP {resp.status_code}")
    except Exception as e:
        print(f"  Error: {e}")
    time.sleep(3)

print("\n" + "=" * 60)
print("SUMMARY")
print("=" * 60)
print(f"{'Model':<15} {'Speed (t/s)':>12} {'Time (s)':>10}")
print("-" * 60)
for model, r in results.items():
    print(f"{model:<15} {r['tps']:>12.1f} {r['duration']:>10.1f}")

# Save
ts = datetime.now().strftime('%Y%m%d_%H%M%S')
with open(f'qwen35_quick_{ts}.json', 'w') as f:
    json.dump(results, f, indent=2)
