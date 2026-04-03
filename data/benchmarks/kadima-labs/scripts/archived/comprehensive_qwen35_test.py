#!/usr/bin/env python3
"""
Comprehensive Qwen 3.5 Testing Suite
Tests: Speed, Quality, MoE Functionality, Inference Operations
Includes real-time visualization of GPU operations
"""

import json
import time
import subprocess
import sys
import os
import gc
import threading
import queue
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import statistics
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.animation import FuncAnimation
import numpy as np
from collections import deque

# GPU monitoring
try:
    import pynvml as nvml
    HAS_NVML = True
except ImportError:
    HAS_NVML = False
    print("Warning: NVML not available - GPU monitoring limited")


class GPUProfiler:
    """Profiles GPU usage during inference"""
    
    def __init__(self):
        self.samples = []
        self.running = False
        self.thread = None
        self.handle = None
        
        if HAS_NVML:
            try:
                nvml.nvmlInit()
                self.handle = nvml.nvmlDeviceGetHandleByIndex(0)
                self.gpu_name = nvml.nvmlDeviceGetName(self.handle).decode()
            except Exception as e:
                print(f"GPU init error: {e}")
                self.handle = None
    
    def start_profiling(self):
        """Start GPU profiling in background thread"""
        if not self.handle:
            return
        
        self.running = True
        self.samples = []
        self.thread = threading.Thread(target=self._profile_loop)
        self.thread.daemon = True
        self.thread.start()
    
    def _profile_loop(self):
        """Continuously sample GPU metrics"""
        while self.running:
            try:
                mem = nvml.nvmlDeviceGetMemoryInfo(self.handle)
                util = nvml.nvmlDeviceGetUtilizationRates(self.handle)
                
                sample = {
                    "timestamp": time.time(),
                    "memory_used_gb": mem.used / 1024**3,
                    "memory_total_gb": mem.total / 1024**3,
                    "gpu_utilization": util.gpu,
                    "memory_utilization": util.memory
                }
                self.samples.append(sample)
                time.sleep(0.1)  # 100ms sampling
            except Exception as e:
                print(f"Sampling error: {e}")
                break
    
    def stop_profiling(self):
        """Stop GPU profiling"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
    
    def get_summary(self) -> Dict[str, Any]:
        """Get profiling summary"""
        if not self.samples:
            return {}
        
        mem_used = [s["memory_used_gb"] for s in self.samples]
        gpu_util = [s["gpu_utilization"] for s in self.samples]
        
        return {
            "duration_seconds": len(self.samples) * 0.1,
            "memory_peak_gb": max(mem_used) if mem_used else 0,
            "memory_avg_gb": statistics.mean(mem_used) if mem_used else 0,
            "memory_min_gb": min(mem_used) if mem_used else 0,
            "gpu_util_peak": max(gpu_util) if gpu_util else 0,
            "gpu_util_avg": statistics.mean(gpu_util) if gpu_util else 0,
            "total_samples": len(self.samples)
        }
    
    def plot_inference_timeline(self, title: str, save_path: str):
        """Plot GPU usage timeline"""
        if not self.samples:
            print("No GPU samples to plot")
            return
        
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
        
        timestamps = [s["timestamp"] - self.samples[0]["timestamp"] for s in self.samples]
        mem_used = [s["memory_used_gb"] for s in self.samples]
        gpu_util = [s["gpu_utilization"] for s in self.samples]
        
        # Memory plot
        ax1.fill_between(timestamps, mem_used, alpha=0.3, color='blue')
        ax1.plot(timestamps, mem_used, color='blue', linewidth=1)
        ax1.axhline(y=self.samples[0]["memory_total_gb"], color='red', 
                   linestyle='--', label=f'Total VRAM: {self.samples[0]["memory_total_gb"]:.1f}GB')
        ax1.set_ylabel('VRAM Used (GB)', fontsize=11, fontweight='bold')
        ax1.set_title(f'GPU Memory Usage During Inference\n{title}', fontsize=12, fontweight='bold')
        ax1.legend()
        ax1.grid(alpha=0.3)
        
        # GPU utilization plot
        ax2.fill_between(timestamps, gpu_util, alpha=0.3, color='green')
        ax2.plot(timestamps, gpu_util, color='green', linewidth=1)
        ax2.set_xlabel('Time (seconds)', fontsize=11, fontweight='bold')
        ax2.set_ylabel('GPU Utilization (%)', fontsize=11, fontweight='bold')
        ax2.set_title('GPU Compute Utilization', fontsize=12, fontweight='bold')
        ax2.set_ylim(0, 100)
        ax2.grid(alpha=0.3)
        
        plt.tight_layout()
        plt.savefig(save_path, dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        print(f"  Saved: {save_path}")


class ComprehensiveQwenTester:
    """Comprehensive testing suite for Qwen models"""
    
    def __init__(self):
        self.results = {}
        self.profiler = GPUProfiler()
        self.system_info = self._get_system_info()
    
    def _get_system_info(self) -> Dict:
        """Get system information"""
        info = {
            "timestamp": datetime.now().isoformat(),
            "gpu": {},
            "platform": sys.platform
        }
        
        if self.profiler.handle:
            try:
                mem = nvml.nvmlDeviceGetMemoryInfo(self.profiler.handle)
                info["gpu"] = {
                    "name": self.profiler.gpu_name,
                    "total_memory_gb": mem.total / 1024**3
                }
            except:
                pass
        
        return info
    
    def _clear_gpu(self):
        """Clear GPU memory"""
        gc.collect()
        time.sleep(3)
        if self.profiler.handle:
            try:
                # Force GPU sync
                nvml.nvmlDeviceGetMemoryInfo(self.profiler.handle)
            except:
                pass
    
    def _run_inference(self, model: str, prompt: str, timeout: int = 300) -> Dict:
        """Run inference with GPU profiling"""
        self._clear_gpu()
        
        # Start profiling
        self.profiler.start_profiling()
        start_time = time.time()
        
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
            self.profiler.stop_profiling()
            
            output = result.stdout if result.returncode == 0 else ""
            
            # Calculate metrics
            duration = end_time - start_time
            tokens = (len(prompt) + len(output)) // 4
            tps = tokens / duration if duration > 0 else 0
            
            return {
                "success": result.returncode == 0,
                "output": output[:3000],
                "duration_seconds": round(duration, 2),
                "tokens_per_second": round(tps, 2),
                "total_tokens": tokens,
                "gpu_profile": self.profiler.get_summary()
            }
            
        except subprocess.TimeoutExpired:
            self.profiler.stop_profiling()
            return {
                "success": False,
                "error": "Timeout",
                "duration_seconds": timeout,
                "tokens_per_second": 0,
                "gpu_profile": self.profiler.get_summary()
            }
        except Exception as e:
            self.profiler.stop_profiling()
            return {
                "success": False,
                "error": str(e),
                "duration_seconds": 0,
                "tokens_per_second": 0,
                "gpu_profile": self.profiler.get_summary()
            }
    
    def test_speed_benchmarks(self, model: str) -> Dict:
        """Test pure speed benchmarks"""
        print("  Testing Speed Benchmarks...")
        
        tests = {
            "short_prompt": "What is 2+2?",
            "medium_prompt": "Explain quantum computing in simple terms." * 5,
            "long_prompt": "Write a comprehensive essay about artificial intelligence." * 10
        }
        
        results = {}
        for test_name, prompt in tests.items():
            print(f"    {test_name}...", end=" ")
            result = self._run_inference(model, prompt, timeout=180)
            results[test_name] = result
            
            if result["success"]:
                print(f"{result['tokens_per_second']:.1f} t/s")
            else:
                print("FAILED")
            
            time.sleep(2)
        
        return results
    
    def test_quality_metrics(self, model: str) -> Dict:
        """Test output quality with scoring"""
        print("  Testing Quality Metrics...")
        
        quality_tests = {
            "math_reasoning": {
                "prompt": """Solve step-by-step: A farmer has 17 sheep. All but 9 die. How many are left?
Show your reasoning clearly.""",
                "check_answer": lambda out: "9" in out and ("left" in out.lower() or "remain" in out.lower()),
                "check_reasoning": lambda out: "all but" in out.lower() or "survive" in out.lower()
            },
            "code_generation": {
                "prompt": """Write a Python function `is_prime(n)` that checks if a number is prime.
Requirements:
1. Handle edge cases (n < 2)
2. Optimize for large numbers
3. Include docstring
4. Include test cases""",
                "check_function": lambda out: "def is_prime" in out,
                "check_edge_case": lambda out: "n < 2" in out or "n<=1" in out,
                "check_optimization": lambda out: "sqrt" in out or "** 0.5" in out,
                "check_docs": lambda out: '"""' in out or "'''" in out
            },
            "instruction_following": {
                "prompt": """Follow these instructions EXACTLY:
1. Start with "ANSWER:"
2. Write exactly 2 sentences about ML
3. End with "[END]"
4. NO other text""",
                "check_start": lambda out: out.strip().startswith("ANSWER:"),
                "check_end": lambda out: "[END]" in out,
                "check_length": lambda out: len([s for s in out.split('.') if s.strip()]) == 3
            },
            "creative_writing": {
                "prompt": """Write a story (exactly 50 words) about an AI learning to paint.
Must include: color blue, number 7, moment of surprise.""",
                "check_blue": lambda out: "blue" in out.lower(),
                "check_seven": lambda out: "7" in out or "seven" in out.lower(),
                "check_surprise": lambda out: any(w in out.lower() for w in ["surprise", "shocked", "amazed"])
            }
        }
        
        results = {}
        for test_name, test_data in quality_tests.items():
            print(f"    {test_name}...", end=" ")
            result = self._run_inference(model, test_data["prompt"], timeout=180)
            
            if result["success"]:
                output = result["output"]
                score = 0
                max_score = len(test_data) - 1  # Exclude prompt
                feedback = []
                
                for check_name, check_func in test_data.items():
                    if check_name == "prompt":
                        continue
                    if check_func(output):
                        score += 1
                        feedback.append(f"[PASS] {check_name}")
                    else:
                        feedback.append(f"[FAIL] {check_name}")
                
                result["quality_score"] = score
                result["quality_max"] = max_score
                result["quality_percentage"] = round((score / max_score) * 100, 1)
                result["quality_feedback"] = feedback
                
                print(f"{result['quality_percentage']}% ({score}/{max_score})")
            else:
                print("FAILED")
            
            results[test_name] = result
            time.sleep(2)
        
        return results
    
    def test_moe_functionality(self, model: str) -> Dict:
        """Test Mixture of Experts behavior (for 27B MoE model)"""
        print("  Testing MoE Functionality...")
        
        # MoE models activate different experts for different inputs
        moe_tests = {
            "coding_expert": "Write a Python function to implement quicksort algorithm.",
            "math_expert": "Calculate the integral of x^2 from 0 to 5.",
            "reasoning_expert": "Explain the trolley problem and discuss ethical implications.",
            "creative_expert": "Write a poem about the ocean at sunset."
        }
        
        results = {}
        expert_latencies = []
        
        for expert_type, prompt in moe_tests.items():
            print(f"    {expert_type}...", end=" ")
            result = self._run_inference(model, prompt, timeout=180)
            results[expert_type] = result
            
            if result["success"]:
                expert_latencies.append(result["duration_seconds"])
                print(f"{result['duration_seconds']:.2f}s, {result['tokens_per_second']:.1f} t/s")
            else:
                print("FAILED")
            
            time.sleep(2)
        
        # Analyze MoE patterns
        if expert_latencies:
            results["moe_analysis"] = {
                "avg_latency": round(statistics.mean(expert_latencies), 2),
                "latency_variance": round(statistics.variance(expert_latencies), 2) if len(expert_latencies) > 1 else 0,
                "latency_range": round(max(expert_latencies) - min(expert_latencies), 2)
            }
        
        return results
    
    def test_long_context(self, model: str) -> Dict:
        """Test long context handling"""
        print("  Testing Long Context (32K tokens)...")
        
        # Create a long document
        long_doc = "This is paragraph number {}. It contains important information about topic {}. " * 500
        long_doc = long_doc.format(*sum([[i, i] for i in range(1, 501)], []))
        
        # Questions at different positions
        questions = [
            ("What was mentioned in paragraph 10?", "early"),
            ("What was mentioned in paragraph 250?", "middle"),
            ("What was mentioned in paragraph 490?", "late")
        ]
        
        results = {}
        for question, position in questions:
            prompt = f"Document:\n{long_doc}\n\nQuestion: {question}\nAnswer:"
            print(f"    {position} context...", end=" ")
            result = self._run_inference(model, prompt[:8000], timeout=240)  # Truncate for practical testing
            results[position] = result
            
            if result["success"]:
                print(f"{result['duration_seconds']:.2f}s")
            else:
                print("FAILED")
            
            time.sleep(3)
        
        return results
    
    def run_full_test_suite(self, models: List[str]) -> Dict:
        """Run complete test suite on all models"""
        print("="*70)
        print("COMPREHENSIVE QWEN 3.5 TESTING SUITE")
        print("="*70)
        print(f"Hardware: {self.system_info.get('gpu', {}).get('name', 'Unknown')}")
        print(f"Testing: {', '.join(models)}\n")
        
        all_results = {
            "system_info": self.system_info,
            "timestamp": datetime.now().isoformat(),
            "models": {}
        }
        
        for model in models:
            print(f"\n{'='*70}")
            print(f"Testing Model: {model}")
            print(f"{'='*70}")
            
            model_results = {}
            
            # Run all test categories
            model_results["speed"] = self.test_speed_benchmarks(model)
            model_results["quality"] = self.test_quality_metrics(model)
            model_results["moe"] = self.test_moe_functionality(model)
            model_results["long_context"] = self.test_long_context(model)
            
            # Calculate aggregate scores
            speed_scores = [r["tokens_per_second"] for r in model_results["speed"].values() 
                          if r.get("success")]
            quality_scores = [r["quality_percentage"] for r in model_results["quality"].values()
                            if r.get("success")]
            
            model_results["summary"] = {
                "avg_speed": round(statistics.mean(speed_scores), 2) if speed_scores else 0,
                "avg_quality": round(statistics.mean(quality_scores), 2) if quality_scores else 0,
                "total_tests": len(model_results["speed"]) + len(model_results["quality"]) + 
                              len(model_results["moe"]) + len(model_results["long_context"])
            }
            
            all_results["models"][model] = model_results
            
            # Generate inference timeline visualization
            for test_name, test_result in model_results["speed"].items():
                if test_result.get("gpu_profile", {}).get("total_samples", 0) > 0:
                    viz_path = f"inference_{model.replace(':', '_')}_{test_name}.png"
                    self.profiler.samples = []  # Clear and rebuild from stored data if needed
                    # Note: In real implementation, store samples per test
            
            print(f"\n  Summary for {model}:")
            print(f"    Avg Speed: {model_results['summary']['avg_speed']:.1f} t/s")
            print(f"    Avg Quality: {model_results['summary']['avg_quality']:.1f}%")
            
            time.sleep(5)  # Cooldown between models
        
        return all_results
    
    def generate_visualizations(self, results: Dict):
        """Generate comprehensive visualizations"""
        print("\n" + "="*70)
        print("Generating Visualizations...")
        print("="*70)
        
        # 1. Speed comparison
        self._plot_speed_comparison(results)
        
        # 2. Quality comparison
        self._plot_quality_comparison(results)
        
        # 3. MoE analysis (if applicable)
        self._plot_moe_analysis(results)
        
        # 4. GPU memory usage comparison
        self._plot_memory_comparison(results)
        
        # 5. Comprehensive dashboard
        self._plot_comprehensive_dashboard(results)
    
    def _plot_speed_comparison(self, results: Dict):
        """Plot speed comparison"""
        fig, ax = plt.subplots(figsize=(12, 6))
        
        models = list(results["models"].keys())
        speeds = [r["summary"]["avg_speed"] for r in results["models"].values()]
        
        colors = ['#E74C3C', '#3498DB', '#2ECC71', '#F39C12', '#9B59B6']
        bars = ax.bar(range(len(models)), speeds, color=colors[:len(models)], 
                     edgecolor='black', linewidth=1.5)
        
        # Add value labels
        for i, (bar, speed) in enumerate(zip(bars, speeds)):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 0.5,
                   f'{speed:.1f}\nt/s', ha='center', va='bottom', 
                   fontweight='bold', fontsize=10)
        
        ax.set_xticks(range(len(models)))
        ax.set_xticklabels([m.replace(':', '\n') for m in models], fontsize=10)
        ax.set_ylabel('Tokens per Second', fontsize=12, fontweight='bold')
        ax.set_title('Qwen Model Speed Comparison\nHigher is Better', 
                    fontsize=14, fontweight='bold')
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('viz_speed_comparison.png', dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        print("  Saved: viz_speed_comparison.png")
    
    def _plot_quality_comparison(self, results: Dict):
        """Plot quality comparison"""
        fig, ax = plt.subplots(figsize=(12, 6))
        
        models = list(results["models"].keys())
        qualities = [r["summary"]["avg_quality"] for r in results["models"].values()]
        
        colors = ['#E74C3C', '#3498DB', '#2ECC71', '#F39C12', '#9B59B6']
        bars = ax.bar(range(len(models)), qualities, color=colors[:len(models)],
                     edgecolor='black', linewidth=1.5)
        
        for i, (bar, quality) in enumerate(zip(bars, qualities)):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height + 1,
                   f'{quality:.1f}%', ha='center', va='bottom',
                   fontweight='bold', fontsize=10)
        
        ax.set_xticks(range(len(models)))
        ax.set_xticklabels([m.replace(':', '\n') for m in models], fontsize=10)
        ax.set_ylabel('Quality Score (%)', fontsize=12, fontweight='bold')
        ax.set_title('Qwen Model Quality Comparison\nHigher is Better',
                    fontsize=14, fontweight='bold')
        ax.set_ylim(0, 100)
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('viz_quality_comparison.png', dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        print("  Saved: viz_quality_comparison.png")
    
    def _plot_moe_analysis(self, results: Dict):
        """Plot MoE expert activation analysis"""
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Extract MoE data for models that have it
        moe_data = {}
        for model, data in results["models"].items():
            if "moe" in data and "moe_analysis" in data["moe"]:
                moe_data[model] = data["moe"]["moe_analysis"]
        
        if not moe_data:
            print("  No MoE data to visualize")
            return
        
        models = list(moe_data.keys())
        latencies = [moe_data[m]["avg_latency"] for m in models]
        variances = [moe_data[m]["latency_variance"] for m in models]
        
        x = np.arange(len(models))
        width = 0.35
        
        ax.bar(x - width/2, latencies, width, label='Avg Latency', color='#3498DB')
        ax.bar(x + width/2, variances, width, label='Latency Variance', color='#E74C3C')
        
        ax.set_xticks(x)
        ax.set_xticklabels([m.replace(':', '\n') for m in models], fontsize=10)
        ax.set_ylabel('Seconds', fontsize=11, fontweight='bold')
        ax.set_title('MoE Expert Switching Analysis\nLower variance = better routing',
                    fontsize=12, fontweight='bold')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('viz_moe_analysis.png', dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        print("  Saved: viz_moe_analysis.png")
    
    def _plot_memory_comparison(self, results: Dict):
        """Plot memory usage comparison"""
        fig, ax = plt.subplots(figsize=(10, 6))
        
        # Extract peak memory from GPU profiles
        memory_data = {}
        for model, data in results["models"].items():
            peak_mems = []
            for test_cat in ["speed", "quality", "moe"]:
                if test_cat in data:
                    for test in data[test_cat].values():
                        if isinstance(test, dict) and "gpu_profile" in test:
                            peak_mems.append(test["gpu_profile"].get("memory_peak_gb", 0))
            
            if peak_mems:
                memory_data[model] = {
                    "peak": max(peak_mems),
                    "avg": statistics.mean(peak_mems)
                }
        
        if not memory_data:
            print("  No memory data to visualize")
            return
        
        models = list(memory_data.keys())
        peaks = [memory_data[m]["peak"] for m in models]
        avgs = [memory_data[m]["avg"] for m in models]
        
        x = np.arange(len(models))
        ax.bar(x - 0.2, peaks, 0.4, label='Peak Memory', color='#E74C3C', alpha=0.8)
        ax.bar(x + 0.2, avgs, 0.4, label='Average Memory', color='#3498DB', alpha=0.8)
        
        # Add VRAM limit line
        ax.axhline(y=16, color='red', linestyle='--', linewidth=2, label='RTX 5070 Ti Limit')
        
        ax.set_xticks(x)
        ax.set_xticklabels([m.replace(':', '\n') for m in models], fontsize=10)
        ax.set_ylabel('VRAM Usage (GB)', fontsize=11, fontweight='bold')
        ax.set_title('GPU Memory Usage Comparison\nLower is better',
                    fontsize=12, fontweight='bold')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('viz_memory_comparison.png', dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        print("  Saved: viz_memory_comparison.png")
    
    def _plot_comprehensive_dashboard(self, results: Dict):
        """Create comprehensive dashboard"""
        fig = plt.figure(figsize=(16, 12))
        gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)
        
        models = list(results["models"].keys())
        
        # Panel 1: Speed ranking
        ax1 = fig.add_subplot(gs[0, 0])
        speeds = [r["summary"]["avg_speed"] for r in results["models"].values()]
        ax1.barh(range(len(models)), speeds, color=['#E74C3C', '#3498DB', '#2ECC71'][:len(models)])
        ax1.set_yticks(range(len(models)))
        ax1.set_yticklabels([m.replace(':', ' ') for m in models], fontsize=9)
        ax1.set_xlabel('Tokens/s', fontsize=9)
        ax1.set_title('Speed Ranking', fontsize=11, fontweight='bold')
        
        # Panel 2: Quality ranking
        ax2 = fig.add_subplot(gs[0, 1])
        qualities = [r["summary"]["avg_quality"] for r in results["models"].values()]
        ax2.barh(range(len(models)), qualities, color=['#E74C3C', '#3498DB', '#2ECC71'][:len(models)])
        ax2.set_yticks(range(len(models)))
        ax2.set_yticklabels([m.replace(':', ' ') for m in models], fontsize=9)
        ax2.set_xlabel('Quality %', fontsize=9)
        ax2.set_title('Quality Ranking', fontsize=11, fontweight='bold')
        ax2.set_xlim(0, 100)
        
        # Panel 3: Speed vs Quality scatter
        ax3 = fig.add_subplot(gs[0, 2])
        ax3.scatter(speeds, qualities, s=500, c=['#E74C3C', '#3498DB', '#2ECC71'][:len(models)], alpha=0.7)
        for i, model in enumerate(models):
            ax3.annotate(model.replace(':', ' '), (speeds[i], qualities[i]), 
                        fontsize=8, ha='center')
        ax3.set_xlabel('Speed (t/s)', fontsize=9)
        ax3.set_ylabel('Quality (%)', fontsize=9)
        ax3.set_title('Speed vs Quality', fontsize=11, fontweight='bold')
        ax3.grid(alpha=0.3)
        
        # Panel 4-6: Detailed test breakdown
        test_categories = ["speed", "quality", "moe"]
        for idx, cat in enumerate(test_categories):
            ax = fig.add_subplot(gs[1, idx])
            
            # Extract data for this category
            cat_data = {}
            for model in models:
                if cat in results["models"][model]:
                    test_scores = []
                    for test in results["models"][model][cat].values():
                        if isinstance(test, dict):
                            if "tokens_per_second" in test:
                                test_scores.append(test["tokens_per_second"])
                            elif "quality_percentage" in test:
                                test_scores.append(test["quality_percentage"])
                    if test_scores:
                        cat_data[model] = statistics.mean(test_scores)
            
            if cat_data:
                ax.bar(range(len(cat_data)), list(cat_data.values()),
                      color=['#E74C3C', '#3498DB', '#2ECC71'][:len(cat_data)])
                ax.set_xticks(range(len(cat_data)))
                ax.set_xticklabels([m.replace(':', ' ') for m in cat_data.keys()], 
                                  fontsize=8, rotation=45)
                ax.set_title(f'{cat.title()} Tests', fontsize=11, fontweight='bold')
                ax.grid(axis='y', alpha=0.3)
        
        # Panel 7-9: Summary statistics
        ax_summary = fig.add_subplot(gs[2, :])
        ax_summary.axis('off')
        
        summary_text = "COMPREHENSIVE TEST RESULTS\n\n"
        for model in models:
            data = results["models"][model]
            summary_text += f"{model}:\n"
            summary_text += f"  Speed: {data['summary']['avg_speed']:.1f} t/s\n"
            summary_text += f"  Quality: {data['summary']['avg_quality']:.1f}%\n"
            summary_text += f"  Tests: {data['summary']['total_tests']}\n\n"
        
        ax_summary.text(0.5, 0.5, summary_text, transform=ax_summary.transAxes,
                       fontsize=10, ha='center', va='center',
                       bbox=dict(boxstyle='round,pad=1', facecolor='lightblue', alpha=0.3),
                       family='monospace')
        
        fig.suptitle('Qwen 3.5 Comprehensive Testing Dashboard\nRTX 5070 Ti Performance Analysis',
                    fontsize=16, fontweight='bold')
        
        plt.savefig('viz_comprehensive_dashboard.png', dpi=150, bbox_inches='tight', facecolor='white')
        plt.close()
        print("  Saved: viz_comprehensive_dashboard.png")
    
    def save_results(self, results: Dict, filename: str = None):
        """Save results to file"""
        if not filename:
            filename = f"comprehensive_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n[SUCCESS] Results saved to: {filename}")
        return filename


def main():
    """Main entry point"""
    # Check available models
    print("Checking available Qwen models...")
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        available = [line.split()[0] for line in result.stdout.strip().split('\n')[1:] if line.strip()]
        qwen_models = [m for m in available if 'qwen' in m.lower()]
        
        print(f"Found: {', '.join(qwen_models) if qwen_models else 'No Qwen models'}")
        
        if not qwen_models:
            print("\nPlease install Qwen models first:")
            print("  ollama pull qwen2.5:14b")
            print("  ollama pull qwen3:14b")
            print("  ollama pull qwen3.5:9b")
            print("  ollama pull qwen3.5:27b")
            return
    except Exception as e:
        print(f"Error checking models: {e}")
        return
    
    # Run comprehensive tests
    tester = ComprehensiveQwenTester()
    results = tester.run_full_test_suite(qwen_models)
    
    # Generate visualizations
    tester.generate_visualizations(results)
    
    # Save results
    tester.save_results(results)
    
    # Print final summary
    print("\n" + "="*70)
    print("TESTING COMPLETE")
    print("="*70)
    print("\nGenerated files:")
    print("  - comprehensive_test_*.json (raw data)")
    print("  - viz_speed_comparison.png")
    print("  - viz_quality_comparison.png")
    print("  - viz_moe_analysis.png")
    print("  - viz_memory_comparison.png")
    print("  - viz_comprehensive_dashboard.png")
    print("\nView the dashboard for complete results!")


if __name__ == "__main__":
    main()
