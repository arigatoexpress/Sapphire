#!/usr/bin/env python3
"""
Comprehensive Qwen Model Benchmark
Tests all 4 Qwen models one by one
"""

import json
import time
import subprocess
import sys
from datetime import datetime
import statistics

# GPU monitoring
try:
    import pynvml as nvml
    HAS_NVML = True
except ImportError:
    HAS_NVML = False
    print("Warning: NVML not available - GPU monitoring limited")


class QwenBenchmark:
    """Benchmark suite for Qwen models"""
    
    def __init__(self):
        self.results = []
        self.system_info = self._get_system_info()
        if HAS_NVML:
            try:
                nvml.nvmlInit()
                self.gpu_handle = nvml.nvmlDeviceGetHandleByIndex(0)
                gpu_name = nvml.nvmlDeviceGetName(self.gpu_handle).decode()
                print(f"GPU: {gpu_name}")
            except Exception as e:
                print(f"GPU init error: {e}")
                self.gpu_handle = None
        else:
            self.gpu_handle = None
    
    def _get_system_info(self):
        """Gather system info"""
        info = {"timestamp": datetime.now().isoformat(), "platform": sys.platform}
        try:
            import psutil
            mem = psutil.virtual_memory()
            info["ram_gb"] = round(mem.total / (1024**3), 2)
        except:
            pass
        return info
    
    def _get_gpu_memory(self):
        """Get GPU memory in MB"""
        if self.gpu_handle:
            try:
                mem = nvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
                return mem.used // 1024 // 1024
            except:
                pass
        return 0
    
    def _run_test(self, model, prompt, timeout=180):
        """Run single inference test"""
        mem_before = self._get_gpu_memory()
        start = time.time()
        
        try:
            result = subprocess.run(
                ["ollama", "run", model, prompt],
                capture_output=True, text=True, timeout=timeout,
                encoding='utf-8', errors='ignore'
            )
            
            duration = time.time() - start
            time.sleep(2)  # Cooldown
            mem_after = self._get_gpu_memory()
            
            output = result.stdout if result.returncode == 0 else ""
            tokens = (len(prompt) + len(output)) // 4
            
            return {
                "success": result.returncode == 0,
                "duration": round(duration, 2),
                "tokens_per_sec": round(tokens / duration, 2) if duration > 0 else 0,
                "gpu_mem_before_mb": mem_before,
                "gpu_mem_after_mb": mem_after,
                "output_preview": output[:500]
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout", "duration": timeout}
        except Exception as e:
            return {"success": False, "error": str(e), "duration": 0}
    
    def benchmark_model(self, model):
        """Run full benchmark on a model"""
        print(f"\n{'='*70}")
        print(f"BENCHMARKING: {model}")
        print(f"{'='*70}")
        
        # Warmup
        print("  Warmup...", end=" ")
        self._run_test(model, "Hello", timeout=60)
        print("OK")
        time.sleep(2)
        
        # Test suite
        tests = {
            "reasoning": {
                "prompt": "Solve step by step: A farmer has 17 sheep. All but 9 die. How many are left?",
                "category": "reasoning"
            },
            "code_gen": {
                "prompt": "Write a Python function `is_prime(n)` that checks if a number is prime with docstring.",
                "category": "coding"
            },
            "knowledge": {
                "prompt": "Explain quantum computing in simple terms with applications.",
                "category": "knowledge"
            },
            "math": {
                "prompt": "Calculate: (15 * 23) + (47 * 12) - (156 / 4). Show work.",
                "category": "math"
            },
            "creative": {
                "prompt": "Write a haiku about artificial intelligence.",
                "category": "creative"
            },
            "context": {
                "prompt": "Sarah has 3 apples, gives 1 to her brother, buys 5 more. Her friend gives her twice as many as she has. How many apples? Explain.",
                "category": "context"
            }
        }
        
        results = {
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "tests": {}
        }
        
        for test_name, test_data in tests.items():
            print(f"  Test: {test_name}...", end=" ", flush=True)
            result = self._run_test(model, test_data["prompt"], timeout=180)
            results["tests"][test_name] = result
            
            if result["success"]:
                print(f"{result['tokens_per_sec']:.1f} t/s, {result['duration']:.1f}s")
            else:
                print(f"FAILED - {result.get('error', 'Unknown')}")
        
        # Calculate summary
        successful = [t for t in results["tests"].values() if t["success"]]
        if successful:
            speeds = [t["tokens_per_sec"] for t in successful]
            durations = [t["duration"] for t in successful]
            
            results["summary"] = {
                "avg_tokens_per_sec": round(statistics.mean(speeds), 2),
                "min_tokens_per_sec": round(min(speeds), 2),
                "max_tokens_per_sec": round(max(speeds), 2),
                "avg_duration": round(statistics.mean(durations), 2),
                "total_duration": round(sum(durations), 2),
                "successful_tests": len(successful),
                "total_tests": len(tests)
            }
            
            print(f"\n  Summary: {results['summary']['avg_tokens_per_sec']:.1f} t/s avg | "
                  f"{results['summary']['successful_tests']}/{results['summary']['total_tests']} tests passed")
        
        return results
    
    def run_all_benchmarks(self, models):
        """Run benchmarks on all models"""
        all_results = []
        
        print(f"\n{'='*70}")
        print("QWEN MODEL BENCHMARK SUITE")
        print(f"{'='*70}")
        print(f"Models to test: {', '.join(models)}\n")
        
        for i, model in enumerate(models, 1):
            print(f"\n[{i}/{len(models)}] Starting {model}...")
            try:
                result = self.benchmark_model(model)
                all_results.append(result)
            except Exception as e:
                print(f"ERROR benchmarking {model}: {e}")
                all_results.append({"model": model, "error": str(e)})
            
            if i < len(models):
                print(f"\n  Cooling down before next model...")
                time.sleep(10)
        
        return all_results
    
    def save_results(self, results, filename=None):
        """Save results to JSON"""
        if not filename:
            filename = f"qwen_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        output = {
            "benchmark_date": datetime.now().isoformat(),
            "system_info": self.system_info,
            "models_tested": results
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        return filename
    
    def print_final_report(self, results):
        """Print final comparison report"""
        print(f"\n{'='*70}")
        print("FINAL BENCHMARK REPORT")
        print(f"{'='*70}\n")
        
        # Sort by speed
        successful = [r for r in results if "summary" in r]
        sorted_results = sorted(successful, key=lambda x: x["summary"]["avg_tokens_per_sec"], reverse=True)
        
        print("SPEED RANKING:")
        print("-" * 50)
        for i, r in enumerate(sorted_results, 1):
            medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else "  "
            print(f"{medal} {i}. {r['model']:<20} {r['summary']['avg_tokens_per_sec']:>6.1f} t/s")
        
        print("\nDETAILED RESULTS:")
        print("-" * 70)
        for r in sorted_results:
            s = r["summary"]
            print(f"\n{r['model']}:")
            print(f"  Speed: {s['avg_tokens_per_sec']:.1f} t/s (min: {s['min_tokens_per_sec']:.1f}, max: {s['max_tokens_per_sec']:.1f})")
            print(f"  Tests: {s['successful_tests']}/{s['total_tests']} passed")
            print(f"  Total time: {s['total_duration']:.1f}s")


def main():
    # Models to benchmark
    models = ["qwen3:14b", "qwen2.5-coder:14b", "qwen2.5:32b", "qwen2.5:14b"]
    
    # Run benchmarks
    benchmark = QwenBenchmark()
    results = benchmark.run_all_benchmarks(models)
    
    # Save results
    filename = benchmark.save_results(results)
    print(f"\nResults saved to: {filename}")
    
    # Print report
    benchmark.print_final_report(results)


if __name__ == "__main__":
    main()
