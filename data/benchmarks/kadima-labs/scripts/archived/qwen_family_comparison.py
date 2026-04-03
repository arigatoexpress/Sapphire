#!/usr/bin/env python3
"""
Qwen Family Deep Comparison
Comprehensive analysis of Qwen 2.5 vs Qwen 3.0
With framework ready for Qwen 3.5 testing
"""

import json
import time
import subprocess
import sys
import gc
from datetime import datetime
from typing import Dict, List, Any
import statistics

try:
    import pynvml as nvml
    HAS_NVML = True
except ImportError:
    HAS_NVML = False

class QwenFamilyBenchmark:
    """Benchmark suite focused on Qwen family comparison"""
    
    def __init__(self):
        self.results = {}
        if HAS_NVML:
            try:
                nvml.nvmlInit()
                self.gpu_handle = nvml.nvmlDeviceGetHandleByIndex(0)
                print(f"GPU: {nvml.nvmlDeviceGetName(self.gpu_handle).decode()}")
            except:
                self.gpu_handle = None
        else:
            self.gpu_handle = None
    
    def _get_gpu_memory(self) -> int:
        """Get GPU memory in MB"""
        if self.gpu_handle:
            try:
                mem = nvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
                return mem.used // 1024 // 1024
            except:
                pass
        return 0
    
    def _clear_gpu(self):
        """Clear GPU memory"""
        gc.collect()
        time.sleep(3)
    
    def _run_test(self, model: str, prompt: str, timeout: int = 180) -> Dict:
        """Run single test with GPU isolation"""
        self._clear_gpu()
        mem_before = self._get_gpu_memory()
        start = time.time()
        
        try:
            result = subprocess.run(
                ["ollama", "run", model, prompt],
                capture_output=True, text=True, timeout=timeout,
                encoding='utf-8', errors='ignore'
            )
            
            duration = time.time() - start
            time.sleep(2)
            mem_after = self._get_gpu_memory()
            
            output = result.stdout if result.returncode == 0 else ""
            tokens = (len(prompt) + len(output)) // 4
            
            return {
                "success": result.returncode == 0,
                "output": output[:2000],
                "duration": round(duration, 2),
                "tokens_per_sec": round(tokens / duration, 2) if duration > 0 else 0,
                "gpu_mem_before": mem_before,
                "gpu_mem_after": mem_after,
                "gpu_mem_delta": mem_after - mem_before
            }
        except Exception as e:
            return {"success": False, "error": str(e), "duration": timeout}
    
    def test_reasoning_quality(self, model: str) -> Dict:
        """Test multi-step reasoning"""
        prompt = """Solve this step-by-step:
A farmer has 17 sheep. All but 9 die. How many sheep does the farmer have left?

Explain your reasoning clearly."""
        
        result = self._run_test(model, prompt)
        
        # Quality scoring
        output = result.get("output", "")
        score = 0
        feedback = []
        
        if "9" in output and ("left" in output.lower() or "have" in output.lower()):
            score += 5
            feedback.append("Correct answer identified")
        
        if "all but" in output.lower() or "survive" in output.lower() or "remain" in output.lower():
            score += 3
            feedback.append("Understood 'all but' logic")
        
        if len(output.split('.')) >= 2:
            score += 2
            feedback.append("Clear explanation")
        
        result["quality_score"] = score
        result["quality_max"] = 10
        result["quality_feedback"] = feedback
        
        return result
    
    def test_code_quality(self, model: str) -> Dict:
        """Test code generation quality"""
        prompt = """Write a Python function `is_prime(n)` that checks if a number is prime.

Requirements:
1. Handle edge cases (n < 2)
2. Optimize for large numbers
3. Include docstring
4. Include 3 test cases

Provide only the code."""
        
        result = self._run_test(model, prompt)
        output = result.get("output", "")
        
        score = 0
        feedback = []
        
        if "def is_prime" in output:
            score += 3
            feedback.append("Function defined correctly")
        
        if "n < 2" in output or "n<=1" in output or "n < 2" in output:
            score += 2
            feedback.append("Edge case handled")
        
        if "sqrt" in output or "** 0.5" in output or "int(n" in output:
            score += 2
            feedback.append("Optimization implemented")
        
        if '"""' in output or "'''" in output:
            score += 2
            feedback.append("Documentation included")
        
        if output.count("assert") >= 2 or output.count("print") >= 2 or output.count("test") >= 1:
            score += 1
            feedback.append("Test cases included")
        
        result["quality_score"] = score
        result["quality_max"] = 10
        result["quality_feedback"] = feedback
        
        return result
    
    def test_instruction_following(self, model: str) -> Dict:
        """Test precise instruction following"""
        prompt = """Follow these instructions EXACTLY:

1. Start your response with "ANSWER:"
2. Write exactly 2 sentences about machine learning
3. End with "[END]"
4. Do NOT include any other text

Your response:"""
        
        result = self._run_test(model, prompt)
        output = result.get("output", "")
        
        score = 0
        feedback = []
        
        if output.strip().startswith("ANSWER:"):
            score += 4
            feedback.append("Correct start marker")
        else:
            feedback.append("Missing start marker")
        
        sentences = [s.strip() for s in output.replace("ANSWER:", "").replace("[END]", "").split('.') if s.strip()]
        if len(sentences) == 2:
            score += 4
            feedback.append("Exactly 2 sentences")
        elif len(sentences) > 0:
            score += 2
            feedback.append(f"{len(sentences)} sentences (expected 2)")
        
        if "[END]" in output:
            score += 2
            feedback.append("Correct end marker")
        else:
            feedback.append("Missing end marker")
        
        result["quality_score"] = score
        result["quality_max"] = 10
        result["quality_feedback"] = feedback
        
        return result
    
    def test_creativity(self, model: str) -> Dict:
        """Test creative writing"""
        prompt = """Write a creative story (exactly 50 words) about an AI learning to paint.
Must include: the color blue, the number 7, and a moment of surprise."""
        
        result = self._run_test(model, prompt)
        output = result.get("output", "")
        
        score = 0
        feedback = []
        words = output.split()
        
        # Word count check
        if 45 <= len(words) <= 55:
            score += 3
            feedback.append("Word count approximately correct")
        elif len(words) > 0:
            score += 1
            feedback.append(f"Word count: {len(words)} (expected ~50)")
        
        # Required elements
        if "blue" in output.lower():
            score += 2
            feedback.append("Color blue included")
        
        if "7" in output or "seven" in output.lower():
            score += 2
            feedback.append("Number 7 included")
        
        surprise_words = ["surprise", "shocked", "amazed", "wonder", "unexpected", "gasp"]
        if any(w in output.lower() for w in surprise_words):
            score += 2
            feedback.append("Surprise element included")
        
        if "paint" in output.lower() or "art" in output.lower() or "canvas" in output.lower():
            score += 1
            feedback.append("Painting theme present")
        
        result["quality_score"] = score
        result["quality_max"] = 10
        result["quality_feedback"] = feedback
        
        return result
    
    def run_full_comparison(self, models: List[str]) -> Dict:
        """Run complete comparison"""
        print("="*70)
        print("QWEN FAMILY COMPREHENSIVE COMPARISON")
        print("="*70)
        print(f"Models to test: {', '.join(models)}\n")
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "hardware": "RTX 5070 Ti 16GB",
            "models": {}
        }
        
        tests = [
            ("reasoning", self.test_reasoning_quality),
            ("code_quality", self.test_code_quality),
            ("instruction_following", self.test_instruction_following),
            ("creativity", self.test_creativity)
        ]
        
        for model in models:
            print(f"\n{'='*70}")
            print(f"Testing: {model}")
            print(f"{'='*70}")
            
            model_results = {
                "tests": {},
                "speed_scores": [],
                "quality_scores": []
            }
            
            # Warmup
            print("  Warmup...")
            self._run_test(model, "Hello")
            
            for test_name, test_func in tests:
                print(f"  Running {test_name}...", end=" ")
                result = test_func(model)
                model_results["tests"][test_name] = result
                
                if result["success"]:
                    model_results["speed_scores"].append(result["tokens_per_sec"])
                    model_results["quality_scores"].append(result["quality_score"])
                    print(f"Speed: {result['tokens_per_sec']:.1f} t/s | Quality: {result['quality_score']}/10")
                else:
                    print("FAILED")
            
            # Calculate averages
            if model_results["speed_scores"]:
                model_results["avg_speed"] = round(statistics.mean(model_results["speed_scores"]), 2)
            if model_results["quality_scores"]:
                model_results["avg_quality"] = round(statistics.mean(model_results["quality_scores"]), 2)
                model_results["total_quality"] = sum(model_results["quality_scores"])
                model_results["max_quality"] = len(model_results["quality_scores"]) * 10
            
            results["models"][model] = model_results
            
            print(f"\n  Summary for {model}:")
            print(f"    Average Speed: {model_results.get('avg_speed', 0):.1f} t/s")
            print(f"    Average Quality: {model_results.get('avg_quality', 0):.1f}/10")
            print(f"    Total Quality: {model_results.get('total_quality', 0)}/{model_results.get('max_quality', 0)}")
        
        return results
    
    def save_and_report(self, results: Dict, filename: str = None):
        """Save results and generate report"""
        if not filename:
            filename = f"qwen_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n\n{'='*70}")
        print("FINAL COMPARISON REPORT")
        print(f"{'='*70}\n")
        
        # Sort by quality score
        sorted_models = sorted(
            results["models"].items(),
            key=lambda x: x[1].get("avg_quality", 0),
            reverse=True
        )
        
        print("Quality Ranking (Higher is Better):")
        print("-" * 70)
        for i, (model, data) in enumerate(sorted_models, 1):
            quality = data.get("avg_quality", 0)
            speed = data.get("avg_speed", 0)
            total = data.get("total_quality", 0)
            max_q = data.get("max_quality", 0)
            print(f"{i}. {model}")
            print(f"   Quality: {quality:.1f}/10 | Speed: {speed:.1f} t/s | Total: {total}/{max_q}")
            print()
        
        print(f"Results saved to: {filename}")
        return filename


def main():
    """Run Qwen family comparison"""
    # Models available now
    models_to_test = [
        "qwen2.5:14b",
        "qwen3:14b",
    ]
    
    # Check available models
    print("Checking available models...")
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=30)
        installed = result.stdout
        print("\nInstalled models:")
        print(installed)
    except:
        print("Could not list models")
    
    # Run benchmark
    benchmark = QwenFamilyBenchmark()
    results = benchmark.run_full_comparison(models_to_test)
    benchmark.save_and_report(results)
    
    print("\n" + "="*70)
    print("QWEN 3.5 TESTING FRAMEWORK READY")
    print("="*70)
    print("""
To test Qwen 3.5 when available:

1. Update Ollama to latest version:
   - Download from: https://ollama.com/download
   - Or run: winget upgrade Ollama.Ollama

2. Pull Qwen 3.5:
   ollama pull qwen3.5:14b  (or desired size)

3. Add to models list in this script:
   models_to_test = [
       "qwen2.5:14b",
       "qwen3:14b",
       "qwen3.5:14b",  # Add this
   ]

4. Re-run this script for full comparison
    """)


if __name__ == "__main__":
    main()
