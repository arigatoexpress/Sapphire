#!/usr/bin/env python3
"""
Full Qwen Benchmark Suite - Comprehensive testing with visualizations
"""

import json
import time
import subprocess
import sys
import os
from datetime import datetime
from typing import Dict, List, Any
import statistics

# Try importing GPU monitoring
try:
    import pynvml as nvml
    HAS_NVML = True
except ImportError:
    HAS_NVML = False


class ComprehensiveBenchmark:
    """Full benchmark suite for Qwen models"""
    
    def __init__(self):
        self.results = []
        self.system_info = self._get_system_info()
        self.gpu_handle = None
        
        if HAS_NVML:
            try:
                nvml.nvmlInit()
                self.gpu_handle = nvml.nvmlDeviceGetHandleByIndex(0)
                name = nvml.nvmlDeviceGetName(self.gpu_handle)
                # Handle both bytes and str
                if isinstance(name, bytes):
                    name = name.decode()
                print(f"GPU: {name}")
            except Exception as e:
                print(f"GPU monitoring not available: {e}")
    
    def _get_system_info(self) -> Dict:
        info = {"timestamp": datetime.now().isoformat(), "platform": sys.platform}
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(", ")
                info["gpu"] = {"name": parts[0], "memory": parts[1] if len(parts) > 1 else "Unknown"}
        except:
            pass
        return info
    
    def _get_gpu_memory(self) -> int:
        if self.gpu_handle:
            try:
                mem = nvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
                return mem.used // 1024 // 1024
            except:
                pass
        return 0
    
    def _run_inference(self, model: str, prompt: str, timeout: int = 240) -> Dict:
        """Run inference with extended timeout for model loading"""
        mem_before = self._get_gpu_memory()
        start = time.time()
        
        try:
            result = subprocess.run(
                ["ollama", "run", model, prompt],
                capture_output=True, text=True, timeout=timeout,
                encoding='utf-8', errors='ignore'
            )
            
            duration = time.time() - start
            time.sleep(1)  # Brief cooldown
            mem_after = self._get_gpu_memory()
            
            output = result.stdout if result.returncode == 0 else ""
            tokens = (len(prompt) + len(output)) // 4
            
            return {
                "success": result.returncode == 0,
                "duration_seconds": round(duration, 2),
                "tokens_per_second": round(tokens / duration, 2) if duration > 0 else 0,
                "estimated_tokens": tokens,
                "gpu_memory_mb": mem_after,
                "output_preview": output[:300]
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout", "duration_seconds": timeout}
        except Exception as e:
            return {"success": False, "error": str(e), "duration_seconds": 0}
    
    def benchmark_model(self, model: str) -> Dict:
        """Run complete benchmark on a single model"""
        print(f"\n{'='*70}")
        print(f"BENCHMARKING: {model}")
        print(f"{'='*70}")
        
        # Warmup (allow time for model loading)
        print("  Loading model and warmup...")
        warmup = self._run_inference(model, "Hello", timeout=300)
        if not warmup["success"]:
            print(f"  Warmup failed: {warmup.get('error', 'Unknown')}")
            return {"model": model, "error": "Warmup failed"}
        print(f"  Model loaded ({warmup['duration_seconds']:.1f}s)")
        time.sleep(2)
        
        # Test suite
        tests = {
            "reasoning": "Solve step by step: A farmer has 17 sheep. All but 9 die. How many are left?",
            "code": "Write a Python function is_prime(n) with docstring and error handling.",
            "knowledge": "Explain quantum computing in simple terms with 2 applications.",
            "math": "Calculate: (15 * 23) + (47 * 12) - (156 / 4). Show your work.",
            "creative": "Write a haiku about artificial intelligence.",
            "context": "Sarah has 3 apples, gives 1 away, buys 5 more. Friend gives her twice as many. How many? Explain."
        }
        
        results = {"model": model, "tests": {}, "timestamp": datetime.now().isoformat()}
        
        for test_name, prompt in tests.items():
            print(f"  Running {test_name}...", end=" ", flush=True)
            result = self._run_inference(model, prompt, timeout=300)
            results["tests"][test_name] = result
            
            if result["success"]:
                print(f"✓ {result['tokens_per_second']:.1f} t/s")
            else:
                print(f"✗ {result.get('error', 'Failed')}")
            time.sleep(1)
        
        # Calculate summary
        successful = [t for t in results["tests"].values() if t["success"]]
        if successful:
            speeds = [t["tokens_per_second"] for t in successful]
            results["summary"] = {
                "avg_tokens_per_second": round(statistics.mean(speeds), 2),
                "min_tokens_per_second": round(min(speeds), 2),
                "max_tokens_per_second": round(max(speeds), 2),
                "successful_tests": len(successful),
                "total_tests": len(tests),
                "total_duration": round(sum(t["duration_seconds"] for t in successful), 2)
            }
            print(f"\n  Summary: {results['summary']['avg_tokens_per_second']:.1f} t/s avg")
        
        return results
    
    def run_benchmarks(self, models: List[str]) -> List[Dict]:
        """Run benchmarks on all models"""
        all_results = []
        
        print(f"\n{'='*70}")
        print("QWEN COMPREHENSIVE BENCHMARK SUITE")
        print(f"{'='*70}")
        print(f"Testing {len(models)} models...\n")
        
        for i, model in enumerate(models, 1):
            print(f"\n[{i}/{len(models)}] {model}")
            try:
                result = self.benchmark_model(model)
                all_results.append(result)
            except Exception as e:
                print(f"Error: {e}")
                all_results.append({"model": model, "error": str(e)})
            
            if i < len(models):
                print("\n  Cooldown...")
                time.sleep(5)
        
        return all_results
    
    def save_results(self, results: List[Dict]) -> str:
        """Save results to JSON"""
        filename = f"benchmark_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        output = {
            "benchmark_date": datetime.now().isoformat(),
            "system_info": self.system_info,
            "models_tested": results
        }
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\nResults saved to: {filename}")
        return filename
    
    def generate_report(self, results: List[Dict]):
        """Generate and print final report"""
        print(f"\n{'='*70}")
        print("BENCHMARK REPORT")
        print(f"{'='*70}\n")
        
        successful = [r for r in results if "summary" in r]
        if not successful:
            print("No successful benchmarks!")
            return
        
        # Speed ranking
        sorted_models = sorted(successful, key=lambda x: x["summary"]["avg_tokens_per_second"], reverse=True)
        
        print("SPEED RANKING:")
        print("-" * 50)
        for i, r in enumerate(sorted_models, 1):
            medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else "  "
            s = r["summary"]
            print(f"{medal} {i}. {r['model']:<25} {s['avg_tokens_per_second']:>6.1f} t/s")
        
        print("\n\nDETAILED RESULTS:")
        print("-" * 70)
        for r in sorted_models:
            s = r["summary"]
            print(f"\n{r['model']}:")
            print(f"  Average Speed:  {s['avg_tokens_per_second']:.1f} tokens/sec")
            print(f"  Range:          {s['min_tokens_per_second']:.1f} - {s['max_tokens_per_second']:.1f} tokens/sec")
            print(f"  Tests Passed:   {s['successful_tests']}/{s['total_tests']}")
            print(f"  Total Time:     {s['total_duration']:.1f}s")


def main():
    # Available Qwen models
    models = ["qwen3.5:9b", "qwen3:14b", "qwen2.5-coder:14b", "qwen2.5:32b", "qwen2.5:14b"]
    
    benchmark = ComprehensiveBenchmark()
    results = benchmark.run_benchmarks(models)
    filename = benchmark.save_results(results)
    benchmark.generate_report(results)
    
    print(f"\n\nFull results saved to: {filename}")


if __name__ == "__main__":
    main()
