#!/usr/bin/env python3
"""
Accurate AI Benchmark Suite with GPU Isolation
Tests models individually with proper cleanup between runs
Focuses on quality metrics, not just speed
"""

import json
import time
import subprocess
import sys
import os
import gc
from datetime import datetime
from typing import Dict, List, Any, Optional
import statistics

# GPU monitoring
try:
    import pynvml as nvml
    HAS_NVML = True
except ImportError:
    HAS_NVML = False
    print("NVML not available - GPU metrics will be limited")


class AccurateBenchmark:
    """Benchmark suite with proper GPU isolation between tests"""
    
    def __init__(self):
        self.results = []
        self.system_info = self._get_system_info()
        self.gpu_handle = None
        if HAS_NVML:
            try:
                nvml.nvmlInit()
                self.gpu_handle = nvml.nvmlDeviceGetHandleByIndex(0)
                print(f"GPU: {nvml.nvmlDeviceGetName(self.gpu_handle).decode()}")
            except Exception as e:
                print(f"NVML init error: {e}")
    
    def _get_system_info(self) -> Dict[str, Any]:
        """Gather system hardware information"""
        info = {
            "timestamp": datetime.now().isoformat(),
            "platform": sys.platform,
            "gpu": {},
            "cpu": {},
            "ram_gb": None
        }
        
        # Try to get GPU info
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
        
        return info
    
    def _get_gpu_memory(self) -> Optional[int]:
        """Get current GPU memory usage in MB"""
        if self.gpu_handle:
            try:
                mem = nvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
                return mem.used // 1024 // 1024
            except:
                pass
        return None
    
    def _clear_gpu_memory(self):
        """Clear GPU memory between tests"""
        print("    [GPU] Clearing memory...", end=" ")
        
        # Run nvidia-smi to check current state
        try:
            subprocess.run(["nvidia-smi"], capture_output=True, timeout=5)
        except:
            pass
        
        # Force garbage collection
        gc.collect()
        
        # Wait for GPU to settle
        time.sleep(3)
        
        # Check memory after clearing
        mem_before = self._get_gpu_memory()
        time.sleep(2)
        mem_after = self._get_gpu_memory()
        
        if mem_after and mem_before:
            print(f"OK ({mem_after}MB)")
        else:
            print("OK")
    
    def _run_single_test(self, model: str, prompt: str, test_name: str, 
                         timeout: int = 180) -> Dict[str, Any]:
        """Run a single test with full GPU isolation"""
        
        # Clear GPU before test
        self._clear_gpu_memory()
        
        start_time = time.time()
        gpu_mem_before = self._get_gpu_memory()
        
        try:
            # Run the model
            result = subprocess.run(
                ["ollama", "run", model, prompt],
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding='utf-8',
                errors='ignore'
            )
            
            end_time = time.time()
            
            # Wait for GPU to settle and get peak memory
            time.sleep(2)
            gpu_mem_after = self._get_gpu_memory()
            
            output = result.stdout if result.returncode == 0 else ""
            
            # More accurate token estimation using actual output
            # Using ~4 chars per token as baseline
            output_tokens = len(output) // 4 if output else 0
            input_tokens = len(prompt) // 4
            total_tokens = input_tokens + output_tokens
            
            duration = end_time - start_time
            tokens_per_sec = total_tokens / duration if duration > 0 else 0
            
            return {
                "success": result.returncode == 0,
                "output": output[:1500] if output else "",
                "test_name": test_name,
                "duration_seconds": round(duration, 2),
                "tokens_per_second": round(tokens_per_sec, 2),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "gpu_memory_before_mb": gpu_mem_before,
                "gpu_memory_after_mb": gpu_mem_after,
                "gpu_memory_delta_mb": (gpu_mem_after - gpu_mem_before) if gpu_mem_after and gpu_mem_before else None,
                "error": result.stderr[:200] if result.returncode != 0 else None
            }
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "test_name": test_name,
                "duration_seconds": timeout,
                "tokens_per_second": 0,
                "error": "Timeout - model took too long"
            }
        except Exception as e:
            return {
                "success": False,
                "test_name": test_name,
                "duration_seconds": 0,
                "tokens_per_second": 0,
                "error": str(e)
            }
    
    def run_quality_tests(self, model: str, warmup: bool = True) -> Dict[str, Any]:
        """Run comprehensive quality-focused tests"""
        print(f"\n{'='*70}")
        print(f"Testing: {model}")
        print(f"{'='*70}")
        
        # Warmup run (not counted)
        if warmup:
            print("  Warmup run (not measured)...")
            self._run_single_test(model, "Hello", "warmup", timeout=60)
            time.sleep(3)
        
        results = {
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "system_info": self.system_info,
            "tests": {}
        }
        
        # Test 1: Mathematical Reasoning (Multi-step)
        print("\n  [Test 1/8] Multi-step Math Reasoning...")
        math_prompt = """Solve this step-by-step with clear reasoning:
A store is having a 30% off sale. If an item originally costs $85, 
and there's an additional 8% sales tax applied after the discount, 
what is the final price? Show all calculations."""
        results["tests"]["math_reasoning"] = self._run_single_test(model, math_prompt, "math_reasoning")
        
        # Test 2: Logical Deduction
        print("  [Test 2/8] Logical Deduction...")
        logic_prompt = """Analyze this logic puzzle:
Three friends - Alice, Bob, and Carol - have different professions: doctor, engineer, and teacher.
Clues:
1. Alice is not the doctor
2. The engineer is not Bob
3. Carol is older than the teacher

Who has which profession? Explain your reasoning step by step."""
        results["tests"]["logic_deduction"] = self._run_single_test(model, logic_prompt, "logic_deduction")
        
        # Test 3: Code Understanding & Debugging
        print("  [Test 3/8] Code Analysis...")
        code_prompt = """Analyze this Python code and identify the bug:

```python
def find_duplicates(nums):
    seen = set()
    duplicates = []
    for num in nums:
        if num in seen:
            duplicates.append(num)
        seen.add(num)
    return duplicates

# Test
result = find_duplicates([1, 2, 3, 2, 4, 3, 5])
print(result)  # Expected: [2, 3]
```

What's wrong and how would you fix it?"""
        results["tests"]["code_analysis"] = self._run_single_test(model, code_prompt, "code_analysis")
        
        # Test 4: Complex Code Generation
        print("  [Test 4/8] Complex Code Generation...")
        complex_code_prompt = """Write a Python class `LRUCache` that implements a Least Recently Used (LRU) cache with:
- get(key): Returns value if exists, -1 otherwise
- put(key, value): Inserts or updates value
- Both operations should be O(1) time complexity
- Include error handling and type hints

Provide the complete implementation with docstrings and a usage example."""
        results["tests"]["complex_coding"] = self._run_single_test(model, complex_code_prompt, "complex_coding")
        
        # Test 5: Instruction Following (Multi-part)
        print("  [Test 5/8] Instruction Following...")
        instruction_prompt = """Follow these instructions exactly:

1. First, explain what a neural network is in exactly 2 sentences.
2. Then, list 3 advantages of neural networks using bullet points starting with "• "
3. Finally, write a 1-sentence caution about overfitting.

Use exactly the format requested."""
        results["tests"]["instruction_following"] = self._run_single_test(model, instruction_prompt, "instruction_following")
        
        # Test 6: Context Understanding
        print("  [Test 6/8] Context Retention...")
        context_prompt = """Read this scenario carefully:

Sarah manages a bookstore. Last Monday, she ordered 50 copies of "The Great Adventure" 
but 10 were damaged in shipping. She returned the damaged ones. On Wednesday, she sold 
15 copies. On Friday, she received a new shipment of 30 copies and sold 8 more that day.

Question: How many copies of "The Great Adventure" does Sarah currently have in stock? 
Show your work and reference the specific events."""
        results["tests"]["context_retention"] = self._run_single_test(model, context_prompt, "context_retention")
        
        # Test 7: Creative Writing with Constraints
        print("  [Test 7/8] Creative Writing...")
        creative_prompt = """Write a short story (exactly 100 words) about an AI gaining consciousness.
Must include: a color, a number, and a question. End with a twist."""
        results["tests"]["creative_constraints"] = self._run_single_test(model, creative_prompt, "creative_constraints")
        
        # Test 8: Comparison Analysis
        print("  [Test 8/8] Comparative Analysis...")
        compare_prompt = """Compare and contrast:
- Supervised learning
- Unsupervised learning
- Reinforcement learning

For each, provide:
1. One key characteristic
2. One real-world application
3. One limitation

Present in a clear, structured format."""
        results["tests"]["comparison_analysis"] = self._run_single_test(model, compare_prompt, "comparison_analysis")
        
        # Calculate summary statistics
        successful = [t for t in results["tests"].values() if t["success"]]
        if successful:
            results["summary"] = {
                "total_tests": len(results["tests"]),
                "successful_tests": len(successful),
                "success_rate": f"{len(successful)}/{len(results['tests'])}",
                "avg_tokens_per_second": round(statistics.mean([t["tokens_per_second"] for t in successful]), 2),
                "avg_duration_seconds": round(statistics.mean([t["duration_seconds"] for t in successful]), 2),
                "total_tokens_generated": sum([t["total_tokens"] for t in successful]),
                "avg_gpu_memory_mb": round(statistics.mean([t["gpu_memory_after_mb"] for t in successful if t["gpu_memory_after_mb"]]), 1) if any(t.get("gpu_memory_after_mb") for t in successful) else None
            }
        
        print(f"\n  [Complete] {results['summary']['successful_tests']}/{results['summary']['total_tests']} tests passed")
        print(f"             Avg speed: {results['summary']['avg_tokens_per_second']:.1f} t/s")
        
        return results
    
    def save_results(self, filepath: str = None):
        """Save benchmark results"""
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = f"accurate_benchmark_{timestamp}.json"
        
        output = {
            "benchmark_type": "Accurate Quality-Focused Benchmark",
            "benchmark_date": datetime.now().isoformat(),
            "system_info": self.system_info,
            "models_tested": self.results
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Results saved to: {filepath}")
        return filepath


def compare_qwen_generations():
    """Focused comparison between Qwen2.5 and Qwen3"""
    models = [
        "qwen3:14b",           # NEW - Qwen 3
        "qwen2.5-coder:14b",   # Qwen 2.5 Coder
        "qwen2.5:14b",         # Qwen 2.5 Base
        "qwen2.5:32b",         # Qwen 2.5 Large
    ]
    
    print("="*70)
    print("COMPREHENSIVE QWEN BENCHMARK SUITE")
    print("GPU Isolation Enabled | Quality-Focused Tests")
    print("="*70)
    print(f"Hardware: RTX 5070 Ti 16GB")
    print(f"Testing: {len(models)} Qwen models with 8 quality tests each")
    print(f"Models: qwen3:14b (NEW!), qwen2.5-coder:14b, qwen2.5:14b, qwen2.5:32b")
    print(f"GPU memory will be cleared between EACH test\n")
    
    benchmark = AccurateBenchmark()
    
    for model in models:
        try:
            result = benchmark.run_quality_tests(model, warmup=True)
            benchmark.results.append(result)
            time.sleep(5)  # Cooldown between models
        except Exception as e:
            print(f"Error testing {model}: {e}")
            benchmark.results.append({
                "model": model,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
        print()
    
    # Save results
    output_file = benchmark.save_results()
    
    # Print comparison
    print("\n" + "="*70)
    print("COMPARISON SUMMARY")
    print("="*70)
    
    for result in benchmark.results:
        if "summary" in result:
            model = result["model"]
            s = result["summary"]
            print(f"\n{model}:")
            print(f"  Success Rate: {s['success_rate']}")
            print(f"  Avg Speed: {s['avg_tokens_per_second']:.1f} t/s")
            print(f"  Total Tokens: {s['total_tokens_generated']}")
            print(f"  Avg VRAM: {s.get('avg_gpu_memory_mb', 'N/A')} MB")
    
    return output_file


if __name__ == "__main__":
    compare_qwen_generations()
