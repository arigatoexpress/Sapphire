#!/usr/bin/env python3
import requests
import time

model = 'qwen3.5:9b'
prompt = 'Say hello'

print(f'Testing {model} with 5 min timeout...')
payload = {'model': model, 'prompt': prompt, 'stream': False}

start = time.time()
resp = requests.post('http://localhost:11434/api/generate', json=payload, timeout=300)
duration = time.time() - start

if resp.status_code == 200:
    data = resp.json()
    tokens = data.get('eval_count', 0)
    tps = tokens / duration if duration > 0 else 0
    print(f'Success: {tps:.1f} t/s ({duration:.1f}s)')
    print(f'Output: {data.get("response", "")[:100]}')
else:
    print(f'Error: {resp.status_code}')
