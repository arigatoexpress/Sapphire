#!/usr/bin/env python3
"""
Quick GPU verification test - runs a model and monitors GPU utilization
"""

import subprocess
import time
import sys

def monitor_gpu(duration=30):
    """Monitor GPU during inference"""
    print("Monitoring GPU... (Ctrl+C to stop)")
    print("-" * 60)
    print(f"{'Time':<8} {'GPU%':<8} {'Mem%':<8} {'VRAM Used':<12} {'Status'}")
    print("-" * 60)
    
    start = time.time()
    try:
        while time.time() - start < duration:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu,utilization.memory,memory.used",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            gpu_pct, mem_pct, vram = result.stdout.strip().split(", ")
            elapsed = time.time() - start
            
            status = "🟢 HIGH" if float(gpu_pct) > 70 else ("🟡 MED" if float(gpu_pct) > 30 else "🔴 LOW")
            print(f"{elapsed:<8.1f} {gpu_pct.strip():<8} {mem_pct.strip():<8} {vram.strip():<12} MB {status}")
            time.sleep(2)
    except KeyboardInterrupt:
        pass
    print("-" * 60)

def test_model(model_name="qwen2.5:14b"):
    """Test a model and monitor GPU"""
    print(f"\n{'='*60}")
    print(f"GPU Verification Test: {model_name}")
    print(f"{'='*60}")
    print("\n1. Starting GPU monitor in background...")
    
    # Start GPU monitoring in separate process
    import threading
    monitor_thread = threading.Thread(target=monitor_gpu, args=(60,))
    monitor_thread.daemon = True
    
    print("\n2. Running inference test...")
    print(f"   Prompt: 'What is 2+2? Answer in one word.'")
    print("   (Watch GPU utilization above)")
    print("-" * 60)
    
    start = time.time()
    try:
        result = subprocess.run(
            ["ollama", "run", model_name, "What is 2+2? Answer in one word."],
            capture_output=True, text=True, timeout=120,
            encoding='utf-8', errors='ignore'
        )
        duration = time.time() - start
        
        print(f"\n3. Results:")
        print(f"   Duration: {duration:.1f}s")
        print(f"   Return code: {result.returncode}")
        print(f"   Output: {result.stdout.strip()[:100]}")
        
        if result.returncode == 0:
            print(f"\n   ✓ Model responded successfully!")
            tokens = len(result.stdout) // 4
            tps = tokens / duration if duration > 0 else 0
            print(f"   ✓ Speed: ~{tps:.1f} tokens/sec")
        else:
            print(f"\n   ✗ Error: {result.stderr[:200]}")
            
    except subprocess.TimeoutExpired:
        print("\n   ✗ TIMEOUT - Model took too long to respond")
        print("   This may indicate GPU loading issues")
    except Exception as e:
        print(f"\n   ✗ Error: {e}")

if __name__ == "__main__":
    model = sys.argv[1] if len(sys.argv) > 1 else "qwen2.5:14b"
    test_model(model)
