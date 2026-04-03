#!/usr/bin/env python3
"""
Qwen 3.5 Comprehensive Testing & Comparison
Compare Qwen 2.5 vs 3.0 vs 3.5
"""

import json
import time
import subprocess
import sys
import gc
from datetime import datetime
import statistics

# Test if Qwen 3.5 is available
def check_qwen35_available():
    """Check if Qwen 3.5 models are available"""
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        if "qwen3.5" in result.stdout.lower():
            return True
    except:
        pass
    return False


def get_available_models():
    """Get list of available Qwen models"""
    models = []
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        lines = result.stdout.strip().split('\n')[1:]  # Skip header
        for line in lines:
            if line.strip():
                model_name = line.split()[0]
                if 'qwen' in model_name.lower():
                    models.append(model_name)
    except:
        pass
    return models


def run_speed_test(model, prompt="Explain quantum computing in simple terms.", timeout=600):
    """Run speed test on a model"""
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
            tokens = len(output) // 4
            tps = tokens / duration if duration > 0 else 0
            return {
                "success": True,
                "duration": round(duration, 2),
                "tokens_per_sec": round(tps, 2),
                "output_length": len(output)
            }
    except Exception as e:
        return {"success": False, "error": str(e)}
    
    return {"success": False, "error": "Unknown error"}


def main():
    print("="*70)
    print("QWEN 3.5 COMPREHENSIVE TESTING FRAMEWORK")
    print("="*70)
    print()
    
    # Check availability
    print("Checking for Qwen models...")
    available_models = get_available_models()
    
    if not available_models:
        print("No Qwen models found! Please pull models first:")
        print("  ollama pull qwen2.5:14b")
        print("  ollama pull qwen3:14b")
        print("  ollama pull qwen3.5:9b  (requires Ollama 0.17.5+)")
        return
    
    # Also check for qwen3.5 specifically
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
    all_models = [line.split()[0] for line in result.stdout.strip().split('\n')[1:] if line.strip()]
    qwen35_models = [m for m in all_models if 'qwen3.5' in m.lower()]
    
    available_models = list(dict.fromkeys(available_models + qwen35_models))  # Remove duplicates
    
    print(f"\nFound models: {', '.join(available_models)}")
    
    has_qwen35 = any('qwen3.5' in m for m in available_models)
    
    if has_qwen35:
        print("\n✅ Qwen 3.5 detected! Running comprehensive comparison...")
    else:
        print("\n⚠️ Qwen 3.5 not found. Testing available models only.")
        print("To get Qwen 3.5:")
        print("  1. Update Ollama: https://ollama.com/download")
        print("  2. Run: ollama pull qwen3.5:9b")
    
    # Define test prompts
    tests = {
        "speed": "What is machine learning?",
        "reasoning": "If a train travels 120 km in 2 hours, how fast is it going?",
        "code": "Write a Python function to check if a number is prime.",
        "creative": "Write a haiku about artificial intelligence."
    }
    
    results = {}
    
    print("\n" + "="*70)
    print("RUNNING TESTS")
    print("="*70)
    
    for model in available_models:
        print(f"\nTesting: {model}")
        print("-" * 40)
        
        model_results = {}
        
        for test_name, prompt in tests.items():
            print(f"  {test_name}...", end=" ")
            result = run_speed_test(model, prompt)
            model_results[test_name] = result
            
            if result["success"]:
                print(f"{result['tokens_per_sec']:.1f} t/s")
            else:
                print("FAILED")
            
            time.sleep(5)  # Cooldown - longer for MoE models
        
        results[model] = model_results
    
    # Generate report
    print("\n" + "="*70)
    print("RESULTS SUMMARY")
    print("="*70)
    
    # Speed comparison table
    print("\nSpeed Comparison (Tokens/Second):")
    print("-" * 70)
    print(f"{'Model':<25} {'Speed Test':<12} {'Reasoning':<12} {'Code':<12} {'Creative':<12}")
    print("-" * 70)
    
    for model, data in results.items():
        speeds = []
        for test in tests.keys():
            tps = data.get(test, {}).get("tokens_per_sec", 0)
            speeds.append(f"{tps:.1f}" if tps > 0 else "N/A")
        print(f"{model:<25} {speeds[0]:<12} {speeds[1]:<12} {speeds[2]:<12} {speeds[3]:<12}")
    
    # Save results
    output = {
        "timestamp": datetime.now().isoformat(),
        "hardware": "RTX 5070 Ti 16GB",
        "results": results
    }
    
    filename = f"qwen_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n✅ Results saved to: {filename}")
    
    # Comparison with Qwen 3.5
    if has_qwen35:
        print("\n" + "="*70)
        print("QWEN 3.5 ANALYSIS")
        print("="*70)
        
        # Extract 3.5 results
        qwen35_models = {k: v for k, v in results.items() if 'qwen3.5' in k}
        qwen3_models = {k: v for k, v in results.items() if 'qwen3:' in k or 'qwen3-' in k}
        qwen25_models = {k: v for k, v in results.items() if 'qwen2.5' in k}
        
        print("\nQwen 3.5 shows improvements in:")
        print("  - Vision-Language understanding (unified foundation)")
        print("  - Hybrid architecture (Dense + MoE)")
        print("  - 201 languages support (vs ~100 in Qwen 3)")
        print("  - 256K context length (vs 128K in Qwen 3)")
        print("  - Better reasoning with RL scaling")


if __name__ == "__main__":
    main()
