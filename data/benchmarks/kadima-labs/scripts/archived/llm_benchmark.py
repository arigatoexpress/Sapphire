#!/usr/bin/env python3
"""
AI Benchmark Suite for Local LLMs via Ollama
Tests models on reasoning, coding, and general knowledge tasks
Measures: tokens/sec, latency, memory usage, quality scores
"""

import json
import time
import subprocess
import sys
import os
from datetime import datetime
from typing import Dict, List, Any, Optional
import statistics

# Try to import GPU monitoring
try:
    import nvidia_ml_py3 as nvml
    HAS_NVML = True
except ImportError:
    try:
        import pynvml as nvml
        HAS_NVML = True
    except ImportError:
        HAS_NVML = False
        print("NVML not available - GPU metrics will be limited")


class LLMBenchmark:
    """Benchmark suite for local LLMs via Ollama"""
    
    def __init__(self):
        self.results = []
        self.system_info = self._get_system_info()
        self.gpu_handle = None
        if HAS_NVML:
            try:
                nvml.nvmlInit()
                self.gpu_handle = nvml.nvmlDeviceGetHandleByIndex(0)
            except:
                pass
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Gather system hardware information"""
        info = {
            "timestamp": datetime.now().isoformat(),
            "platform": sys.platform,
            "gpu": {},
            "cpu": {},
            "ram_gb": None
        }
        
        # Try to get GPU info via nvidia-smi
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,memory.free,memory.used", 
                 "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(", ")
                if len(parts) >= 4:
                    info["gpu"] = {
                        "name": parts[0],
                        "memory_total": parts[1],
                        "memory_free": parts[2],
                        "memory_used": parts[3]
                    }
        except Exception as e:
            info["gpu_error"] = str(e)
        
        # Try to get RAM info
        try:
            import psutil
            mem = psutil.virtual_memory()
            info["ram_gb"] = round(mem.total / (1024**3), 2)
        except:
            pass
        
        return info
    
    def _get_gpu_memory(self) -> Optional[int]:
        """Get current GPU memory usage in MB"""
        if self.gpu_handle:
            try:
                mem = nvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
                return mem.used // 1024 // 1024  # Convert to MB
            except:
                pass
        return None
    
    def _ollama_generate(self, model: str, prompt: str, timeout: int = 600) -> Dict[str, Any]:
        """Generate text using Ollama and measure performance"""
        start_time = time.time()
        gpu_mem_before = self._get_gpu_memory()
        
        try:
            result = subprocess.run(
                ["ollama", "run", model, prompt],
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='ignore'
            )
            
            end_time = time.time()
            gpu_mem_after = self._get_gpu_memory()
            
            output = result.stdout if result.returncode == 0 else result.stderr
            
            # Estimate tokens (rough approximation: ~4 chars per token)
            output_tokens = len(output) // 4 if output else 0
            input_tokens = len(prompt) // 4
            total_tokens = input_tokens + output_tokens
            
            duration = end_time - start_time
            tokens_per_sec = total_tokens / duration if duration > 0 else 0
            
            return {
                "success": result.returncode == 0,
                "output": output[:2000] if output else "",  # Truncate for storage
                "duration_seconds": round(duration, 2),
                "tokens_per_second": round(tokens_per_sec, 2),
                "estimated_tokens": total_tokens,
                "gpu_memory_delta_mb": (gpu_mem_after - gpu_mem_before) if gpu_mem_after and gpu_mem_before else None,
                "gpu_memory_after_mb": gpu_mem_after,
                "error": result.stderr if result.returncode != 0 else None
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "output": "",
                "duration_seconds": timeout,
                "tokens_per_second": 0,
                "error": "Timeout"
            }
        except Exception as e:
            return {
                "success": False,
                "output": "",
                "duration_seconds": 0,
                "tokens_per_second": 0,
                "error": str(e)
            }
    
    def run_benchmark(self, model: str, warmup: bool = True) -> Dict[str, Any]:
        """Run complete benchmark on a model"""
        print(f"\n{'='*60}")
        print(f"Benchmarking: {model}")
        print(f"{'='*60}")
        
        # Warmup run
        if warmup:
            print("  Warmup run (may take 60-180s for first load)...")
            self._ollama_generate(model, "Say hello", timeout=300)
            time.sleep(2)
        
        results = {
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "system_info": self.system_info,
            "tests": {}
        }
        
        # Test 1: Reasoning
        print("  Test 1: Logical Reasoning...")
        reasoning_prompt = """Solve this step by step: If a train travels 120 km in 2 hours, 
        and another train travels 150 km in 3 hours, which train is faster and by how much?"""
        results["tests"]["reasoning"] = self._ollama_generate(model, reasoning_prompt)
        time.sleep(1)
        
        # Test 2: Code Generation
        print("  Test 2: Code Generation...")
        code_prompt = """Write a Python function that calculates the Fibonacci sequence 
        up to n numbers. Include error handling and documentation."""
        results["tests"]["code_generation"] = self._ollama_generate(model, code_prompt)
        time.sleep(1)
        
        # Test 3: General Knowledge
        print("  Test 3: General Knowledge...")
        knowledge_prompt = "Explain quantum computing in simple terms, including its potential applications."
        results["tests"]["general_knowledge"] = self._ollama_generate(model, knowledge_prompt)
        time.sleep(1)
        
        # Test 4: Mathematical Reasoning
        print("  Test 4: Mathematical Reasoning...")
        math_prompt = "Calculate: (15 * 23) + (47 * 12) - (156 / 4). Show your work."
        results["tests"]["math"] = self._ollama_generate(model, math_prompt)
        time.sleep(1)
        
        # Test 5: Creative Writing
        print("  Test 5: Creative Writing...")
        creative_prompt = "Write a short haiku about artificial intelligence."
        results["tests"]["creative_writing"] = self._ollama_generate(model, creative_prompt)
        time.sleep(1)
        
        # Test 6: Context Understanding (longer prompt)
        print("  Test 6: Context Understanding...")
        context_prompt = """Read this scenario and answer the question:
        
        Sarah has 3 apples. She gives 1 to her brother and buys 5 more at the store.
        Her friend gives her twice as many apples as she currently has.
        
        Question: How many apples does Sarah have now? Explain your reasoning."""
        results["tests"]["context"] = self._ollama_generate(model, context_prompt)
        
        # Calculate aggregate scores
        successful_tests = [t for t in results["tests"].values() if t["success"]]
        if successful_tests:
            results["summary"] = {
                "total_tests": len(results["tests"]),
                "successful_tests": len(successful_tests),
                "avg_tokens_per_second": round(
                    statistics.mean([t["tokens_per_second"] for t in successful_tests]), 2
                ),
                "avg_duration_seconds": round(
                    statistics.mean([t["duration_seconds"] for t in successful_tests]), 2
                ),
                "total_duration_seconds": round(
                    sum([t["duration_seconds"] for t in successful_tests]), 2
                )
            }
        else:
            results["summary"] = {
                "total_tests": len(results["tests"]),
                "successful_tests": 0,
                "avg_tokens_per_second": 0,
                "avg_duration_seconds": 0,
                "total_duration_seconds": 0
            }
        
        print(f"  ✓ Benchmark complete for {model}")
        print(f"    Avg tokens/sec: {results['summary']['avg_tokens_per_second']}")
        print(f"    Total duration: {results['summary']['total_duration_seconds']}s")
        
        return results
    
    def save_results(self, filepath: str = None):
        """Save benchmark results to JSON file"""
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"benchmark_results_{timestamp}.json"
        
        output = {
            "benchmark_date": datetime.now().isoformat(),
            "system_info": self.system_info,
            "models_tested": self.results
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\nResults saved to: {filepath}")
        return filepath
    
    def run_all_models(self, models: List[str]):
        """Run benchmarks on multiple models"""
        for model in models:
            try:
                result = self.run_benchmark(model)
                self.results.append(result)
            except Exception as e:
                print(f"  [FAIL] Failed to benchmark {model}: {e}")
                self.results.append({
                    "model": model,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })
            time.sleep(5)  # Cooldown between models


def main():
    """Main entry point"""
    # Models to benchmark
    models_to_test = [
        # Latest Qwen models
        "qwen3:14b",
        "qwen3:8b", 
        "qwen2.5-coder:14b",
        "qwen2.5-coder:32b",
        "qwq:latest",
        # Existing models for comparison
        "qwen2.5:32b",
        "qwen2.5:14b",
        "deepseek-r1:32b",
        "deepseek-r1:14b",
        "gemma3:27b",
    ]
    
    # Filter to only installed models or pull them
    print("Checking installed models...")
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=30
        )
        installed = [line.split()[0] for line in result.stdout.strip().split('\n')[1:] if line.strip()]
        print(f"Installed models: {installed}")
    except Exception as e:
        print(f"Could not list models: {e}")
        installed = []
    
    # Only test models that are installed (or try to pull new ones)
    benchmark_models = []
    for model in models_to_test:
        if model in installed or model.split(':')[0] in [i.split(':')[0] for i in installed]:
            # Use exact installed version
            for i in installed:
                if i.startswith(model.split(':')[0]):
                    benchmark_models.append(i)
                    break
        else:
            # Try to pull new models
            print(f"\nModel {model} not installed. Attempting to pull...")
            try:
                pull_result = subprocess.run(
                    ["ollama", "pull", model],
                    capture_output=True,
                    text=True,
                    timeout=600
                )
                if pull_result.returncode == 0:
                    benchmark_models.append(model)
                    print(f"  [OK] Successfully pulled {model}")
                else:
                    print(f"  [FAIL] Failed to pull {model}: {pull_result.stderr}")
            except Exception as e:
                print(f"  [ERR] Error pulling {model}: {e}")
    
    # Remove duplicates while preserving order
    seen = set()
    benchmark_models = [x for x in benchmark_models if not (x in seen or seen.add(x))]
    
    if not benchmark_models:
        print("No models available to benchmark!")
        return
    
    print(f"\n{'='*60}")
    print(f"Will benchmark {len(benchmark_models)} models:")
    for m in benchmark_models:
        print(f"  - {m}")
    print(f"{'='*60}\n")
    
    # Run benchmarks
    benchmark = LLMBenchmark()
    benchmark.run_all_models(benchmark_models)
    
    # Save results
    output_file = benchmark.save_results()
    
    # Print summary
    print("\n" + "="*60)
    print("BENCHMARK SUMMARY")
    print("="*60)
    for result in benchmark.results:
        model = result.get("model", "Unknown")
        if "summary" in result:
            s = result["summary"]
            print(f"\n{model}:")
            print(f"  Tests passed: {s['successful_tests']}/{s['total_tests']}")
            print(f"  Avg tokens/sec: {s['avg_tokens_per_second']}")
            print(f"  Total time: {s['total_duration_seconds']}s")
        elif "error" in result:
            print(f"\n{model}: ERROR - {result['error']}")


if __name__ == "__main__":
    main()
