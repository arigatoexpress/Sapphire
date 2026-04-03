#!/usr/bin/env python3
"""
AI Benchmark Results Analyzer
Analyzes model performance and generates comparison reports
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


class BenchmarkAnalyzer:
    """Analyze and compare benchmark results"""
    
    def __init__(self, results_file: str):
        with open(results_file, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        self.results = self.data.get("models_tested", [])
        self.system_info = self.data.get("system_info", {})
    
    def generate_report(self) -> str:
        """Generate a comprehensive analysis report"""
        lines = []
        
        # Header
        lines.append("="*80)
        lines.append("AI BENCHMARK ANALYSIS REPORT")
        lines.append("="*80)
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"Benchmark Date: {self.data.get('benchmark_date', 'Unknown')}")
        lines.append("")
        
        # System Information
        lines.append("-"*80)
        lines.append("SYSTEM INFORMATION")
        lines.append("-"*80)
        gpu_info = self.system_info.get("gpu", {})
        if gpu_info:
            lines.append(f"GPU: {gpu_info.get('name', 'Unknown')}")
            lines.append(f"GPU Memory: {gpu_info.get('memory_total', 'Unknown')}")
        lines.append(f"System RAM: {self.system_info.get('ram_gb', 'Unknown')} GB")
        lines.append("")
        
        # Performance Rankings
        lines.append("-"*80)
        lines.append("PERFORMANCE RANKINGS")
        lines.append("-"*80)
        
        # Filter successful benchmarks
        successful = [r for r in self.results if "summary" in r and r["summary"]["successful_tests"] > 0]
        
        if not successful:
            lines.append("No successful benchmarks found!")
            return "\n".join(lines)
        
        # Sort by tokens per second
        by_speed = sorted(successful, key=lambda x: x["summary"]["avg_tokens_per_second"], reverse=True)
        
        lines.append("\n🏆 SPEED RANKING (Tokens/Second):")
        lines.append("-"*40)
        for i, result in enumerate(by_speed, 1):
            model = result["model"]
            tps = result["summary"]["avg_tokens_per_second"]
            duration = result["summary"]["total_duration_seconds"]
            lines.append(f"  {i}. {model}")
            lines.append(f"     {tps} tokens/sec | {duration}s total")
        
        # Sort by test success rate
        by_reliability = sorted(successful, 
            key=lambda x: (x["summary"]["successful_tests"], -x["summary"]["total_duration_seconds"]), 
            reverse=True)
        
        lines.append("\n✅ RELIABILITY RANKING (Tests Passed):")
        lines.append("-"*40)
        for i, result in enumerate(by_reliability, 1):
            model = result["model"]
            passed = result["summary"]["successful_tests"]
            total = result["summary"]["total_tests"]
            lines.append(f"  {i}. {model}: {passed}/{total} tests passed")
        
        # Detailed Model Analysis
        lines.append("\n" + "-"*80)
        lines.append("DETAILED MODEL ANALYSIS")
        lines.append("-"*80)
        
        for result in successful:
            model = result["model"]
            summary = result["summary"]
            tests = result.get("tests", {})
            
            lines.append(f"\n📊 {model}")
            lines.append("="*40)
            lines.append(f"  Overall Performance:")
            lines.append(f"    • Average Speed: {summary['avg_tokens_per_second']} tokens/sec")
            lines.append(f"    • Average Response Time: {summary['avg_duration_seconds']}s")
            lines.append(f"    • Total Test Time: {summary['total_duration_seconds']}s")
            lines.append(f"    • Success Rate: {summary['successful_tests']}/{summary['total_tests']}")
            
            lines.append(f"\n  Individual Test Results:")
            for test_name, test_result in tests.items():
                status = "✓" if test_result["success"] else "✗"
                tps = test_result.get("tokens_per_second", 0)
                duration = test_result.get("duration_seconds", 0)
                lines.append(f"    {status} {test_name}: {tps} t/s, {duration}s")
        
        # Comparative Analysis
        lines.append("\n" + "-"*80)
        lines.append("COMPARATIVE ANALYSIS")
        lines.append("-"*80)
        
        if len(successful) > 1:
            fastest = by_speed[0]
            slowest = by_speed[-1]
            speed_ratio = fastest["summary"]["avg_tokens_per_second"] / max(slowest["summary"]["avg_tokens_per_second"], 0.001)
            
            lines.append(f"\n🚀 Speed Comparison:")
            lines.append(f"    Fastest: {fastest['model']} ({fastest['summary']['avg_tokens_per_second']} t/s)")
            lines.append(f"    Slowest: {slowest['model']} ({slowest['summary']['avg_tokens_per_second']} t/s)")
            lines.append(f"    Speed Ratio: {speed_ratio:.1f}x faster")
            
            # Qwen-specific analysis
            qwen_models = [r for r in successful if "qwen" in r["model"].lower()]
            if qwen_models:
                lines.append(f"\n🤖 Qwen Models Analysis:")
                for qm in qwen_models:
                    lines.append(f"    • {qm['model']}: {qm['summary']['avg_tokens_per_second']} t/s")
        
        # Hardware efficiency
        lines.append("\n" + "-"*80)
        lines.append("HARDWARE EFFICIENCY ASSESSMENT")
        lines.append("-"*80)
        
        gpu_name = self.system_info.get("gpu", {}).get("name", "Unknown")
        lines.append(f"\n💻 Hardware: {gpu_name}")
        lines.append(f"   VRAM: {self.system_info.get('gpu', {}).get('memory_total', 'Unknown')}")
        
        for result in successful:
            model = result["model"]
            tps = result["summary"]["avg_tokens_per_second"]
            
            # Simple efficiency rating
            if tps > 50:
                rating = "Excellent"
            elif tps > 30:
                rating = "Very Good"
            elif tps > 15:
                rating = "Good"
            elif tps > 8:
                rating = "Fair"
            else:
                rating = "Slow"
            
            lines.append(f"\n   {model}:")
            lines.append(f"     Performance Rating: {rating} ({tps} t/s)")
            
            # Check if model size fits VRAM
            model_size = self._estimate_model_size(model)
            if model_size:
                lines.append(f"     Estimated Size: ~{model_size}GB")
                if model_size > 16:
                    lines.append(f"     ⚠️ Model requires offloading to system RAM")
        
        # Recommendations
        lines.append("\n" + "-"*80)
        lines.append("RECOMMENDATIONS")
        lines.append("-"*80)
        
        if successful:
            best_overall = by_speed[0]
            lines.append(f"\n⭐ Best Overall Performance: {best_overall['model']}")
            lines.append(f"   With {best_overall['summary']['avg_tokens_per_second']} tokens/sec average")
            
            # Best for specific use cases
            coding_models = [r for r in successful if "coder" in r["model"].lower()]
            if coding_models:
                best_coder = max(coding_models, key=lambda x: x["summary"]["avg_tokens_per_second"])
                lines.append(f"\n💻 Best for Coding: {best_coder['model']}")
            
            reasoning_models = [r for r in successful if any(x in r["model"].lower() for x in ["r1", "qwq", "reason"])]
            if reasoning_models:
                best_reasoning = max(reasoning_models, key=lambda x: x["summary"]["avg_tokens_per_second"])
                lines.append(f"\n🧠 Best for Reasoning: {best_reasoning['model']}")
        
        lines.append("\n" + "="*80)
        
        return "\n".join(lines)
    
    def _estimate_model_size(self, model_name: str) -> float:
        """Estimate model size in GB based on name"""
        model_lower = model_name.lower()
        
        # Extract parameter count from model name
        if ":" in model_name:
            size_part = model_name.split(":")[1]
            if "b" in size_part:
                try:
                    params = float(size_part.replace("b", ""))
                    # Rough estimate: ~0.5GB per 1B parameters for 4-bit quantized models
                    return round(params * 0.6, 1)
                except:
                    pass
        
        # Common mappings
        size_map = {
            "0.5b": 0.4, "1b": 0.8, "1.5b": 1.2, "3b": 2.0,
            "4b": 2.5, "7b": 4.5, "8b": 5.0, "14b": 9.0,
            "27b": 17.0, "30b": 19.0, "32b": 20.0, "70b": 43.0,
            "72b": 44.0, "110b": 67.0, "235b": 142.0
        }
        
        for key, val in size_map.items():
            if key in model_lower:
                return val
        
        return None
    
    def export_comparison_table(self, output_file: str = "comparison_table.txt"):
        """Export a simple comparison table"""
        lines = []
        lines.append(f"{'Model':<25} {'Tokens/s':<12} {'Avg Time':<12} {'Success':<10} {'Size(GB)':<10}")
        lines.append("-"*75)
        
        for result in self.results:
            if "summary" in result:
                model = result["model"][:24]
                summary = result["summary"]
                tps = f"{summary['avg_tokens_per_second']:.1f}"
                time = f"{summary['avg_duration_seconds']:.1f}s"
                success = f"{summary['successful_tests']}/{summary['total_tests']}"
                size = self._estimate_model_size(model) or "?"
                size_str = f"{size}" if size != "?" else "?"
                
                lines.append(f"{model:<25} {tps:<12} {time:<12} {success:<10} {size_str:<10}")
        
        content = "\n".join(lines)
        with open(output_file, 'w') as f:
            f.write(content)
        print(f"Comparison table saved to: {output_file}")
        return content


def main():
    if len(sys.argv) < 2:
        # Find most recent benchmark results
        result_files = list(Path(".").glob("benchmark_results_*.json"))
        if not result_files:
            print("No benchmark result files found!")
            print("Usage: python analyze_results.py <benchmark_results_file.json>")
            sys.exit(1)
        results_file = max(result_files, key=lambda p: p.stat().st_mtime)
        print(f"Using most recent results file: {results_file}")
    else:
        results_file = sys.argv[1]
    
    analyzer = BenchmarkAnalyzer(str(results_file))
    
    # Generate and print report
    report = analyzer.generate_report()
    print("\n" + report)
    
    # Save report to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = f"benchmark_analysis_{timestamp}.txt"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"\n✓ Full analysis saved to: {report_file}")
    
    # Export comparison table
    analyzer.export_comparison_table(f"comparison_table_{timestamp}.txt")


if __name__ == "__main__":
    main()
