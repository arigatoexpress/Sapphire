#!/usr/bin/env python3
"""
Test GPU utilization during inference
"""

import subprocess
import time
import threading
import json

gpu_readings = []

def monitor_gpu(duration=60):
    """Monitor GPU in background"""
    start = time.time()
    while time.time() - start < duration:
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used", 
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            gpu, mem = result.stdout.strip().split(", ")
            gpu_readings.append((time.time(), float(gpu.strip()), float(mem.strip())))
        except Exception as e:
            pass
        time.sleep(0.5)

def test_inference():
    """Run inference via Ollama API"""
    print("="*60)
    print("GPU Utilization Test - Qwen 2.5 14B")
    print("="*60)
    
    # Start GPU monitoring
    print("\nStarting GPU monitor...")
    monitor = threading.Thread(target=monitor_gpu, args=(60,))
    monitor.daemon = True
    monitor.start()
    time.sleep(1)
    
    # Run inference
    print("Running inference...")
    print("Prompt: 'Write a python function to calculate fibonacci'")
    
    payload = {
        "model": "qwen2.5:14b",
        "prompt": "Write a python function to calculate fibonacci numbers. Include docstring.",
        "stream": False
    }
    
    start = time.time()
    result = subprocess.run(
        ["curl", "-s", "http://localhost:11434/api/generate",
         "-H", "Content-Type: application/json",
         "-d", json.dumps(payload)],
        capture_output=True, text=True, timeout=120
    )
    duration = time.time() - start
    
    # Wait for monitor to catch up
    time.sleep(2)
    
    # Parse response
    try:
        response = json.loads(result.stdout)
        print(f"\nInference Results:")
        print(f"  Duration: {duration:.1f}s")
        print(f"  Model load time: {response.get('load_duration', 0)/1e9:.1f}s")
        print(f"  Prompt eval: {response.get('prompt_eval_duration', 0)/1e9:.1f}s")
        print(f"  Generation: {response.get('eval_duration', 0)/1e9:.1f}s")
        print(f"  Tokens generated: {response.get('eval_count', 0)}")
        
        tps = response.get('eval_count', 0) / (response.get('eval_duration', 1) / 1e9)
        print(f"  Tokens/sec: {tps:.1f}")
    except:
        print(f"Raw response: {result.stdout[:500]}")
    
    # Analyze GPU readings
    print(f"\nGPU Utilization during inference:")
    print("-" * 50)
    print(f"{'Time':<8} {'GPU%':<10} {'VRAM MB':<12} {'Status'}")
    print("-" * 50)
    
    if gpu_readings:
        inference_start = gpu_readings[0][0]
        for t, gpu, mem in gpu_readings[:40]:  # Show first 40 readings
            rel_time = t - inference_start
            status = "HIGH" if gpu > 70 else ("MED" if gpu > 30 else "LOW")
            print(f"{rel_time:<8.1f} {gpu:<10.1f} {mem:<12.0f} {status}")
        
        # Summary stats
        avg_gpu = sum(r[1] for r in gpu_readings) / len(gpu_readings)
        max_gpu = max(r[1] for r in gpu_readings)
        avg_mem = sum(r[2] for r in gpu_readings) / len(gpu_readings)
        max_mem = max(r[2] for r in gpu_readings)
        
        print("-" * 50)
        print(f"\nSummary:")
        print(f"  Avg GPU utilization: {avg_gpu:.1f}%")
        print(f"  Max GPU utilization: {max_gpu:.1f}%")
        print(f"  Avg VRAM: {avg_mem:.0f} MB")
        print(f"  Max VRAM: {max_mem:.0f} MB")
        
        if max_gpu < 50:
            print(f"\nWARNING: Low GPU utilization detected!")
            print(f"   GPU may not be properly utilized for inference.")
        else:
            print(f"\nGPU is being utilized correctly!")

if __name__ == "__main__":
    test_inference()
