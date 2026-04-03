#!/usr/bin/env python3
"""
Qwen Model Benchmark Suite - Using Ollama API
Reliable GPU-accelerated inference
"""

import json
import time
import subprocess
import sys
import threading
from datetime import datetime
from typing import Dict, List, Any
import statistics

# GPU monitoring
try:
    import pynvml as nvml
    HAS_NVML = True
except ImportError:
    HAS_NVML = False


class OllamaAPIBenchmark:
    """Benchmark using Ollama REST API for reliable GPU inference"""
    
    def __init__(self):
        self.results = []
        self.system_info = self._get_system_info()
        self.gpu_handle = None
        
        if HAS_NVML:
            try:
                nvml.nvmlInit()
                self.gpu_handle = nvml.nvmlDeviceGetHandleByIndex(0)
                name = nvml.nvmlDeviceGetName(self.gpu_handle)
                if isinstance(name, bytes):
                    name = name.decode()
                print(f"GPU: {name}")
            except Exception as e:
                print(f"GPU monitoring: {e}")
    
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
    
    def _run_inference(self, model: str, prompt: str, timeout: int = 120) -> Dict:
        """Run inference via Ollama API"""
        mem_before = self._get_gpu_memory()
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        
        start = time.time()
        try:
            result = subprocess.run(
                ["curl", "-s", "http://localhost:11434/api/generate",
                 "-H", "Content-Type: application/json",
                 "-d", json.dumps(payload)],
                capture_output=True, text=True, timeout=timeout
            )
            duration = time.time() - start
            
            if result.returncode != 0:
                return {"success": False, "error": result.stderr, "duration": duration}
            
            response = json.loads(result.stdout)
            mem_after = self._get_gpu_memory()
            
            return {
                "success": True,
                "duration": round(duration, 2),
                "load_duration": response.get("load_duration", 0) / 1e9,
                "prompt_eval_duration": response.get("prompt_eval_duration", 0) / 1e9,
                "eval_duration": response.get("eval_duration", 0) / 1e9,
                "tokens_generated": response.get("eval_count", 0),
                "tokens_per_sec": round(response.get("eval_count", 0) / (response.get("eval_duration", 1) / 1e9), 2),
                "gpu_memory_mb": mem_after,
                "output_preview": response.get("response", "")[:300]
            }
        except json.JSONDecodeError:
            return {"success": False, "error": "Invalid JSON response", "duration": time.time() - start}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout", "duration": timeout}
        except Exception as e:
            return {"success": False, "error": str(e), "duration": 0}
    
    def benchmark_model(self, model: str) -> Dict:
        """Run comprehensive benchmark on a model"""
        print(f"\n{'='*70}")
        print(f"BENCHMARKING: {model}")
        print(f"{'='*70}")
        
        # Warmup
        print("  Warmup...", end=" ")
        warmup = self._run_inference(model, "Hello", timeout=60)
        if not warmup["success"]:
            print(f"FAILED: {warmup.get('error')}")
            return {"model": model, "error": warmup.get('error')}
        print(f"OK ({warmup['duration']:.1f}s, {warmup['tokens_per_sec']:.1f} t/s)")
        time.sleep(2)
        
        # Test suite
        tests = {
            "reasoning": "A farmer has 17 sheep. All but 9 die. How many are left? Explain.",
            "code": "Write a Python function is_prime(n) with docstring and error handling.",
            "knowledge": "Explain quantum computing in simple terms with 2 applications.",
            "math": "Calculate: (15 * 23) + (47 * 12) - (156 / 4). Show work.",
            "creative": "Write a haiku about artificial intelligence.",
            "context": "Sarah has 3 apples, gives 1 away, buys 5 more. Friend gives her twice as many. How many?"
        }
        
        results = {"model": model, "tests": {}, "timestamp": datetime.now().isoformat()}
        
        for test_name, prompt in tests.items():
            print(f"  {test_name}...", end=" ", flush=True)
            result = self._run_inference(model, prompt, timeout=120)
            results["tests"][test_name] = result
            
            if result["success"]:
                print(f"{result['tokens_per_sec']:.1f} t/s, {result['duration']:.1f}s")
            else:
                print(f"FAILED - {result.get('error', 'Unknown')}")
        
        # Summary
        successful = [t for t in results["tests"].values() if t["success"]]
        if successful:
            speeds = [t["tokens_per_sec"] for t in successful]
            results["summary"] = {
                "avg_tokens_per_sec": round(statistics.mean(speeds), 2),
                "min_tokens_per_sec": round(min(speeds), 2),
                "max_tokens_per_sec": round(max(speeds), 2),
                "successful_tests": len(successful),
                "total_tests": len(tests),
                "total_duration": round(sum(t["duration"] for t in successful), 2),
                "avg_gpu_memory_mb": round(statistics.mean([t["gpu_memory_mb"] for t in successful]), 0)
            }
            print(f"\n  Summary: {results['summary']['avg_tokens_per_sec']:.1f} t/s avg | "
                  f"{results['summary']['successful_tests']}/{results['summary']['total_tests']} tests")
        
        return results
    
    def run_all(self, models: List[str]) -> List[Dict]:
        """Run benchmarks on all models"""
        print(f"\n{'='*70}")
        print("QWEN MODEL BENCHMARK SUITE (API Mode)")
        print(f"{'='*70}")
        print(f"Testing {len(models)} models...")
        print("Models: " + ", ".join(models) + "\n")
        
        all_results = []
        for i, model in enumerate(models, 1):
            print(f"[{i}/{len(models)}] Starting {model}...")
            result = self.benchmark_model(model)
            all_results.append(result)
            
            if i < len(models):
                print("\n  Cooldown...")
                time.sleep(5)
        
        return all_results
    
    def save_results(self, results: List[Dict]) -> str:
        filename = f"benchmark_api_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output = {
            "benchmark_date": datetime.now().isoformat(),
            "system_info": self.system_info,
            "models_tested": results
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to: {filename}")
        return filename
    
    def print_report(self, results: List[Dict]):
        print(f"\n{'='*70}")
        print("BENCHMARK REPORT")
        print(f"{'='*70}\n")
        
        successful = [r for r in results if "summary" in r]
        if not successful:
            print("No successful benchmarks!")
            return
        
        sorted_models = sorted(successful, key=lambda x: x["summary"]["avg_tokens_per_sec"], reverse=True)
        
        print("SPEED RANKING:")
        print("-" * 50)
        for i, r in enumerate(sorted_models, 1):
            s = r["summary"]
            print(f"{i}. {r['model']:<25} {s['avg_tokens_per_sec']:>6.1f} t/s")
        
        print("\n\nDETAILED RESULTS:")
        print("-" * 70)
        for r in sorted_models:
            s = r["summary"]
            print(f"\n{r['model']}:")
            print(f"  Speed: {s['avg_tokens_per_sec']:.1f} t/s (range: {s['min_tokens_per_sec']:.1f} - {s['max_tokens_per_sec']:.1f})")
            print(f"  Tests: {s['successful_tests']}/{s['total_tests']} passed")
            print(f"  VRAM:  {s['avg_gpu_memory_mb']:.0f} MB avg")


def main():
    models = ["qwen3:14b", "qwen2.5-coder:14b", "qwen2.5:32b", "qwen2.5:14b"]
    
    benchmark = OllamaAPIBenchmark()
    results = benchmark.run_all(models)
    filename = benchmark.save_results(results)
    benchmark.print_report(results)
    
    print(f"\n\nFull results saved to: {filename}")


if __name__ == "__main__":
    main()
