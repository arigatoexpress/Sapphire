#!/usr/bin/env python3
"""
Qwen 3.5 Benchmark using SGLang Framework
SGLang is the recommended framework for running Qwen 3.5 models
"""

import json
import time
import subprocess
import sys
from datetime import datetime
from typing import Dict, List, Any
import statistics

# Try to import sglang
try:
    import sglang as sgl
    from sglang import function, system, user, assistant, gen
    HAS_SGLANG = True
except ImportError as e:
    print(f"SGLang not available: {e}")
    HAS_SGLANG = False


class SGLangBenchmark:
    """Benchmark Qwen 3.5 using SGLang framework"""
    
    def __init__(self, backend_type="ollama", model_name="qwen3.5:9b"):
        self.backend_type = backend_type
        self.model_name = model_name
        self.results = []
        
        if not HAS_SGLANG:
            raise ImportError("SGLang is not installed. Run: pip install sglang")
        
        # Set up SGLang backend
        self._setup_backend()
    
    def _setup_backend(self):
        """Configure SGLang backend"""
        if self.backend_type == "ollama":
            # Use Ollama's OpenAI-compatible API
            sgl.set_default_backend(sgl.OpenAI(
                base_url="http://localhost:11434/v1",
                api_key="ollama",
                model=self.model_name
            ))
            print(f"Using Ollama backend with model: {self.model_name}")
        else:
            # Native SGLang backend (requires model in SGLang format)
            sgl.set_default_backend(sgl.RuntimeEndpoint(
                f"http://localhost:30000"
            ))
            print(f"Using native SGLang backend")
    
    def benchmark_prompt(self, prompt: str, num_runs: int = 3) -> Dict[str, Any]:
        """Benchmark a single prompt"""
        times = []
        token_counts = []
        outputs = []
        
        for i in range(num_runs):
            try:
                start = time.time()
                # Run prompt using SGLang
                from sglang import function, system, user, assistant, gen
                
                @function
                def run_prompt(s, p):
                    s += system("You are a helpful assistant.")
                    s += user(p)
                    s += assistant(gen("response", max_tokens=512))
                
                state = run_prompt.run(prompt)
                duration = time.time() - start
                
                output = state["response"]
                # Estimate tokens (rough approximation)
                tokens = len(output) // 3.5
                
                times.append(duration)
                token_counts.append(tokens)
                outputs.append(output)
                
                print(f"  Run {i+1}: {duration:.2f}s, {tokens/duration:.1f} t/s")
                
            except Exception as e:
                print(f"  Run {i+1}: Error - {e}")
                return {"success": False, "error": str(e)}
        
        if times:
            avg_time = statistics.mean(times)
            avg_tokens = statistics.mean(token_counts)
            avg_tps = avg_tokens / avg_time if avg_time > 0 else 0
            
            return {
                "success": True,
                "avg_duration": round(avg_time, 2),
                "avg_tokens": round(avg_tokens, 0),
                "tokens_per_sec": round(avg_tps, 2),
                "output": outputs[0][:300] if outputs else ""
            }
        
        return {"success": False, "error": "All runs failed"}
    
    def run_full_benchmark(self) -> Dict[str, Any]:
        """Run complete benchmark suite"""
        print(f"\n{'='*70}")
        print(f"QWEN 3.5 SGLang BENCHMARK")
        print(f"Model: {self.model_name}")
        print(f"Backend: {self.backend_type}")
        print(f"{'='*70}\n")
        
        tests = {
            "hello": "Say hello and introduce yourself briefly in one sentence.",
            "math": "What is 15 * 23? Show your work.",
            "code": "Write a Python function is_prime(n) with docstring.",
            "reasoning": "A farmer has 17 sheep. All but 9 die. How many remain? Explain.",
            "creative": "Write a haiku about AI."
        }
        
        results = {
            "model": self.model_name,
            "backend": self.backend_type,
            "timestamp": datetime.now().isoformat(),
            "tests": {}
        }
        
        for test_name, prompt in tests.items():
            print(f"\n{test_name.upper()}:")
            print(f"Prompt: {prompt}")
            result = self.benchmark_prompt(prompt, num_runs=2)
            results["tests"][test_name] = result
            
            if result["success"]:
                print(f"✅ {result['tokens_per_sec']:.1f} t/s, {result['avg_duration']:.1f}s")
            else:
                print(f"❌ {result.get('error', 'Failed')}")
        
        # Calculate summary
        successful = [t for t in results["tests"].values() if t["success"]]
        if successful:
            results["summary"] = {
                "avg_tokens_per_sec": round(statistics.mean([t["tokens_per_sec"] for t in successful]), 2),
                "total_tests": len(tests),
                "successful_tests": len(successful)
            }
        
        return results
    
    def save_results(self, results: Dict, filename: str = None):
        """Save benchmark results"""
        if filename is None:
            filename = f"qwen35_sglang_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Results saved to: {filename}")
        return filename


def simple_ollama_benchmark(model: str = "qwen3.5:9b"):
    """Simple benchmark using direct Ollama calls with extended timeouts"""
    print(f"\n{'='*70}")
    print(f"QWEN 3.5 BENCHMARK (Direct Ollama with Extended Timeouts)")
    print(f"Model: {model}")
    print(f"{'='*70}\n")
    
    tests = {
        "hello": "Say hello and introduce yourself briefly.",
        "math": "What is 15 * 23? Show your work.",
        "code": "Write a Python function is_prime(n).",
        "reasoning": "A farmer has 17 sheep. All but 9 die. How many remain?",
        "creative": "Write a haiku about AI."
    }
    
    results = {"model": model, "tests": {}, "timestamp": datetime.now().isoformat()}
    
    for test_name, prompt in tests.items():
        print(f"\n{test_name.upper()}:")
        print(f"  Prompt: {prompt[:50]}...")
        print(f"  Running (may take 60-180s for first load)...")
        
        start = time.time()
        try:
            result = subprocess.run(
                ["ollama", "run", model, prompt],
                capture_output=True, text=True, timeout=300,
                encoding='utf-8', errors='ignore'
            )
            duration = time.time() - start
            
            if result.returncode == 0:
                output = result.stdout
                tokens = len(output) // 3.5
                tps = tokens / duration if duration > 0 else 0
                
                results["tests"][test_name] = {
                    "success": True,
                    "duration": round(duration, 2),
                    "tokens_per_sec": round(tps, 2),
                    "output_preview": output[:200]
                }
                print(f"  ✅ {duration:.1f}s, {tps:.1f} t/s")
            else:
                results["tests"][test_name] = {"success": False, "error": result.stderr[:100]}
                print(f"  ❌ Error: {result.stderr[:100]}")
        except subprocess.TimeoutExpired:
            results["tests"][test_name] = {"success": False, "error": "Timeout after 300s"}
            print(f"  ❌ Timeout after 300s")
        except Exception as e:
            results["tests"][test_name] = {"success": False, "error": str(e)}
            print(f"  ❌ Error: {e}")
    
    # Summary
    successful = [t for t in results["tests"].values() if t.get("success")]
    if successful:
        avg_tps = statistics.mean([t["tokens_per_sec"] for t in successful])
        print(f"\n{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}")
        print(f"Average tokens/sec: {avg_tps:.1f}")
        print(f"Tests passed: {len(successful)}/{len(tests)}")
    
    # Save results
    filename = f"qwen35_ollama_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n✅ Results saved to: {filename}")
    
    return results


def main():
    """Main entry point"""
    print("Qwen 3.5 Benchmark Tool")
    print("=======================\n")
    
    # Check available models
    result = subprocess.run(["ollama", "list"], capture_output=True, text=True)
    qwen35_models = [line.split()[0] for line in result.stdout.split('\n')[1:] 
                     if 'qwen3.5' in line.lower()]
    
    if not qwen35_models:
        print("No Qwen 3.5 models found!")
        print("Run: ollama pull qwen3.5:9b")
        return
    
    print(f"Found Qwen 3.5 models: {qwen35_models}")
    
    # Run benchmark with direct Ollama (most reliable)
    model = qwen35_models[0]
    results = simple_ollama_benchmark(model)
    
    # Optionally try SGLang if user wants
    print("\n" + "="*70)
    print("To use SGLang framework:")
    print("  1. Ensure Ollama is running with the model loaded")
    print("  2. Use the SGLang OpenAI-compatible API backend")
    print("="*70)


if __name__ == "__main__":
    main()
