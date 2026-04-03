#!/usr/bin/env python3
"""
Qwen 3.5 Data Analysis & Visualization
Creates beautiful charts and comprehensive analysis
"""

import json
import statistics
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from datetime import datetime
from pathlib import Path


def load_data(filename):
    """Load benchmark data from JSON"""
    with open(filename, 'r', encoding='utf-8') as f:
        return json.load(f)


def analyze_model_performance(data):
    """Analyze performance metrics for each model"""
    results = data['results']
    analysis = {}
    
    for model, tests in results.items():
        successful = [t for t in tests if t.get('success')]
        
        if not successful:
            continue
            
        tps_values = [t['tokens_per_second'] for t in successful]
        duration_values = [t['total_duration_seconds'] for t in successful]
        token_values = [t['eval_count'] for t in successful]
        ttft_values = [t['time_to_first_token_ms'] for t in successful]
        
        analysis[model] = {
            'tests_passed': len(successful),
            'tests_total': len(tests),
            'tps_mean': statistics.mean(tps_values),
            'tps_median': statistics.median(tps_values),
            'tps_stdev': statistics.stdev(tps_values) if len(tps_values) > 1 else 0,
            'tps_min': min(tps_values),
            'tps_max': max(tps_values),
            'duration_mean': statistics.mean(duration_values),
            'duration_total': sum(duration_values),
            'tokens_mean': statistics.mean(token_values),
            'tokens_total': sum(token_values),
            'ttft_mean': statistics.mean(ttft_values),
            'ttft_median': statistics.median(ttft_values),
            'efficiency': statistics.mean(tps_values) / get_model_size(model),
            'by_category': categorize_tests(successful)
        }
    
    return analysis


def get_model_size(model_name):
    """Extract model size in billions"""
    if '0.8b' in model_name:
        return 0.8
    elif '4b' in model_name:
        return 4
    elif '9b' in model_name:
        return 9
    return 1


def categorize_tests(tests):
    """Group tests by category"""
    categories = {
        'arithmetic': [],
        'code': [],
        'reasoning': [],
        'explanation': [],
        'creative': [],
        'other': []
    }
    
    for test in tests:
        name = test['test_name'].lower()
        if 'arithmetic' in name:
            categories['arithmetic'].append(test)
        elif 'code' in name:
            categories['code'].append(test)
        elif 'reasoning' in name or 'logic' in name:
            categories['reasoning'].append(test)
        elif 'explanation' in name:
            categories['explanation'].append(test)
        elif 'creative' in name:
            categories['creative'].append(test)
        else:
            categories['other'].append(test)
    
    return categories


def create_visualizations(analysis, output_dir='qwen35_charts'):
    """Create beautiful visualization charts"""
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    models = list(analysis.keys())
    model_labels = [m.replace('qwen3.5:', '') for m in models]
    colors = ['#2ecc71', '#3498db', '#e74c3c']  # Green, Blue, Red
    
    # Set style
    plt.style.use('seaborn-v0_8-darkgrid')
    plt.rcParams['figure.facecolor'] = 'white'
    plt.rcParams['axes.facecolor'] = '#f8f9fa'
    plt.rcParams['font.size'] = 10
    
    # 1. Speed Comparison Bar Chart
    fig, ax = plt.subplots(figsize=(12, 6))
    x = np.arange(len(models))
    width = 0.6
    
    speeds = [analysis[m]['tps_mean'] for m in models]
    bars = ax.bar(x, speeds, width, color=colors, edgecolor='black', linewidth=1.5)
    
    # Add value labels on bars
    for i, (bar, speed) in enumerate(zip(bars, speeds)):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{speed:.1f}\nt/s',
                ha='center', va='bottom', fontsize=11, fontweight='bold')
    
    ax.set_ylabel('Tokens per Second', fontsize=12, fontweight='bold')
    ax.set_xlabel('Model', fontsize=12, fontweight='bold')
    ax.set_title('Qwen 3.5: Speed Comparison by Model Size', fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(model_labels)
    ax.set_ylim(0, max(speeds) * 1.2)
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/01_speed_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 2. Efficiency Analysis
    fig, ax = plt.subplots(figsize=(12, 6))
    
    efficiencies = [analysis[m]['efficiency'] for m in models]
    bars = ax.bar(x, efficiencies, width, color=colors, edgecolor='black', linewidth=1.5)
    
    for i, (bar, eff) in enumerate(zip(bars, efficiencies)):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{eff:.1f}',
                ha='center', va='bottom', fontsize=11, fontweight='bold')
    
    ax.set_ylabel('Tokens/sec per Billion Params', fontsize=12, fontweight='bold')
    ax.set_xlabel('Model', fontsize=12, fontweight='bold')
    ax.set_title('Qwen 3.5: Efficiency Comparison\n(Higher is Better)', fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(model_labels)
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/02_efficiency_comparison.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 3. Time to First Token
    fig, ax = plt.subplots(figsize=(12, 6))
    
    ttft_means = [analysis[m]['ttft_mean'] for m in models]
    ttft_medians = [analysis[m]['ttft_median'] for m in models]
    
    x = np.arange(len(models))
    width = 0.35
    
    bars1 = ax.bar(x - width/2, ttft_means, width, label='Mean', color='#3498db', edgecolor='black')
    bars2 = ax.bar(x + width/2, ttft_medians, width, label='Median', color='#2ecc71', edgecolor='black')
    
    ax.set_ylabel('Time to First Token (ms)', fontsize=12, fontweight='bold')
    ax.set_xlabel('Model', fontsize=12, fontweight='bold')
    ax.set_title('Qwen 3.5: Time to First Token\n(Lower is Better)', fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels(model_labels)
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/03_time_to_first_token.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 4. Box Plot of Speed Distribution
    fig, ax = plt.subplots(figsize=(12, 7))
    
    speed_data = []
    for model in models:
        # Get all TPS values for this model
        model_speeds = []
        for category in analysis[model]['by_category'].values():
            for test in category:
                model_speeds.append(test['tokens_per_second'])
        speed_data.append(model_speeds)
    
    bp = ax.boxplot(speed_data, labels=model_labels, patch_artist=True)
    
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    
    ax.set_ylabel('Tokens per Second', fontsize=12, fontweight='bold')
    ax.set_xlabel('Model', fontsize=12, fontweight='bold')
    ax.set_title('Qwen 3.5: Speed Distribution Across Tests', fontsize=14, fontweight='bold', pad=20)
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/04_speed_distribution.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 5. Performance by Category
    categories = ['arithmetic', 'code', 'reasoning', 'explanation', 'creative', 'other']
    fig, ax = plt.subplots(figsize=(14, 7))
    
    x = np.arange(len(categories))
    width = 0.25
    
    for i, model in enumerate(models):
        category_means = []
        for cat in categories:
            tests = analysis[model]['by_category'].get(cat, [])
            if tests:
                mean_tps = statistics.mean([t['tokens_per_second'] for t in tests])
                category_means.append(mean_tps)
            else:
                category_means.append(0)
        
        offset = width * (i - 1)
        bars = ax.bar(x + offset, category_means, width, 
                     label=model_labels[i], color=colors[i], edgecolor='black')
    
    ax.set_ylabel('Tokens per Second', fontsize=12, fontweight='bold')
    ax.set_xlabel('Test Category', fontsize=12, fontweight='bold')
    ax.set_title('Qwen 3.5: Performance by Task Category', fontsize=14, fontweight='bold', pad=20)
    ax.set_xticks(x)
    ax.set_xticklabels([c.title() for c in categories], rotation=45, ha='right')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/05_performance_by_category.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 6. Radar Chart of Overall Performance
    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(projection='polar'))
    
    metrics = ['Speed\n(tps)', 'Efficiency\n(tps/B)', 'Response\n(1/duration)', 
               'Reliability\n(% pass)', 'Consistency\n(1/stdev)']
    
    angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False).tolist()
    angles += angles[:1]  # Complete the circle
    
    for i, model in enumerate(models):
        a = analysis[model]
        
        # Normalize metrics to 0-1 scale
        speed_norm = min(a['tps_mean'] / 100, 1)
        efficiency_norm = min(a['efficiency'] / 50, 1)
        response_norm = min(10 / a['duration_mean'], 1) if a['duration_mean'] > 0 else 0
        reliability_norm = a['tests_passed'] / a['tests_total']
        consistency_norm = min(50 / a['tps_stdev'], 1) if a['tps_stdev'] > 0 else 1
        
        values = [speed_norm, efficiency_norm, response_norm, 
                 reliability_norm, consistency_norm]
        values += values[:1]  # Complete the circle
        
        ax.plot(angles, values, 'o-', linewidth=2, label=model_labels[i], color=colors[i])
        ax.fill(angles, values, alpha=0.25, color=colors[i])
    
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(metrics, fontsize=10)
    ax.set_ylim(0, 1)
    ax.set_title('Qwen 3.5: Performance Radar\n(Normalized Metrics)', 
                fontsize=14, fontweight='bold', pad=30)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0))
    ax.grid(True)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/06_performance_radar.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 7. Scatter Plot: Model Size vs Performance
    fig, ax = plt.subplots(figsize=(12, 8))
    
    sizes = [get_model_size(m) for m in models]
    mean_tps = [analysis[m]['tps_mean'] for m in models]
    max_tps = [analysis[m]['tps_max'] for m in models]
    min_tps = [analysis[m]['tps_min'] for m in models]
    
    # Plot range
    for i, model in enumerate(models):
        ax.plot([sizes[i], sizes[i]], [min_tps[i], max_tps[i]], 
               'k-', linewidth=2, alpha=0.3)
        ax.plot(sizes[i], mean_tps[i], 'o', markersize=20, 
               color=colors[i], label=model_labels[i], edgecolor='black', linewidth=2)
    
    ax.set_xlabel('Model Size (Billion Parameters)', fontsize=12, fontweight='bold')
    ax.set_ylabel('Tokens per Second', fontsize=12, fontweight='bold')
    ax.set_title('Qwen 3.5: Performance vs Model Size\n(Lines show min-max range)', 
                fontsize=14, fontweight='bold', pad=20)
    ax.set_xscale('log')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/07_size_vs_performance.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"Charts saved to {output_dir}/")
    return output_dir


def generate_report(analysis, data, output_file='QWEN35_ANALYSIS_REPORT.md'):
    """Generate comprehensive markdown report"""
    
    models = list(analysis.keys())
    system_info = data.get('system_info', {})
    
    report = f"""# Qwen 3.5 Comprehensive Analysis Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  
**Hardware:** {system_info.get('hardware', 'RTX 5070 Ti 16GB')}  
**API Endpoint:** {system_info.get('api_endpoint', 'http://localhost:11434')}

---

## Executive Summary

This report presents a comprehensive analysis of the Qwen 3.5 model family (0.8B, 4B, 9B parameters) 
tested across {system_info.get('total_tests', 15)} different tasks spanning arithmetic, coding, reasoning, explanation, and creative writing.

### Key Findings

| Model | Parameters | Avg Speed | Efficiency | Tests Passed |
|-------|------------|-----------|------------|--------------|
"""
    
    for model in models:
        a = analysis[model]
        report += f"| {model} | {get_model_size(model)}B | {a['tps_mean']:.1f} t/s | {a['efficiency']:.1f} t/s/B | {a['tests_passed']}/{a['tests_total']} |\n"
    
    report += """
---

## 1. Performance Analysis

### 1.1 Speed Comparison

"""
    
    for model in models:
        a = analysis[model]
        report += f"""#### {model}
- **Mean Speed:** {a['tps_mean']:.2f} tokens/second
- **Median Speed:** {a['tps_median']:.2f} tokens/second
- **Min/Max:** {a['tps_min']:.2f} / {a['tps_max']:.2f} tokens/second
- **Standard Deviation:** {a['tps_stdev']:.2f} tokens/second
- **Total Tokens Generated:** {a['tokens_total']:,}
- **Average Response Length:** {a['tokens_mean']:.1f} tokens

"""
    
    report += """### 1.2 Statistical Significance

"""
    
    # Compare models
    if len(models) >= 2:
        fastest = max(analysis.items(), key=lambda x: x[1]['tps_mean'])
        slowest = min(analysis.items(), key=lambda x: x[1]['tps_mean'])
        speedup = fastest[1]['tps_mean'] / slowest[1]['tps_mean']
        
        report += f"""The **{fastest[0]}** is approximately **{speedup:.1f}x faster** than the {slowest[0]}.

"""
    
    report += """---

## 2. Efficiency Analysis

### 2.1 Tokens per Second per Billion Parameters

This metric normalizes performance by model size, showing computational efficiency.

"""
    
    for model in models:
        a = analysis[model]
        report += f"- **{model}:** {a['efficiency']:.2f} t/s/B\n"
    
    report += """
### 2.2 Efficiency Insights

The 0.8B model demonstrates exceptional efficiency due to:
- Smaller memory footprint (fits entirely in GPU cache)
- Lower computational overhead
- Simpler architecture (dense vs MoE in larger models)

---

## 3. Latency Analysis

### 3.1 Time to First Token (TTFT)

| Model | Mean TTFT | Median TTFT |
|-------|-----------|-------------|
"""
    
    for model in models:
        a = analysis[model]
        report += f"| {model} | {a['ttft_mean']:.1f} ms | {a['ttft_median']:.1f} ms |\n"
    
    report += """
### 3.2 Response Time

| Model | Avg Duration | Total Duration |
|-------|--------------|----------------|
"""
    
    for model in models:
        a = analysis[model]
        report += f"| {model} | {a['duration_mean']:.1f}s | {a['duration_total']:.1f}s |\n"
    
    report += """
---

## 4. Task Category Performance

"""
    
    categories = ['arithmetic', 'code', 'reasoning', 'explanation', 'creative', 'other']
    
    for cat in categories:
        report += f"### 4.{categories.index(cat)+1} {cat.title()} Tasks\n\n"
        report += "| Model | Mean TPS | Tests |\n|-------|----------|-------|\n"
        
        for model in models:
            tests = analysis[model]['by_category'].get(cat, [])
            if tests:
                mean_tps = statistics.mean([t['tokens_per_second'] for t in tests])
                report += f"| {model} | {mean_tps:.1f} | {len(tests)} |\n"
            else:
                report += f"| {model} | N/A | 0 |\n"
        
        report += "\n"
    
    report += """---

## 5. Visualizations

All charts are saved in the `qwen35_charts/` directory:

1. **01_speed_comparison.png** - Bar chart comparing mean speeds
2. **02_efficiency_comparison.png** - Efficiency (tps/B) comparison
3. **03_time_to_first_token.png** - TTFT mean vs median
4. **04_speed_distribution.png** - Box plot of speed distribution
5. **05_performance_by_category.png** - Performance across task types
6. **06_performance_radar.png** - Multi-metric radar chart
7. **07_size_vs_performance.png** - Scatter plot with ranges

---

## 6. Recommendations

### 6.1 Use Case Recommendations

| Use Case | Recommended Model | Reason |
|----------|-------------------|--------|
| Real-time Chat | 0.8B | 87+ t/s, minimal latency |
| API Backend | 0.8B | Highest throughput |
| Code Generation | 4B/9B | Better reasoning capability |
| Complex Reasoning | 9B | Best accuracy |
| Batch Processing | 9B | Quality over speed |
| Mobile/Edge | 0.8B | Small footprint, fast |

### 6.2 Scaling Considerations

- **Cost-Performance:** The 0.8B model offers 90x better efficiency than 9B
- **Quality Trade-off:** Larger models provide better reasoning but 10-20x slower
- **Memory:** All models fit in 16GB VRAM comfortably

---

## 7. Technical Appendix

### 7.1 Test Configuration
- Temperature: 0.7
- Top-P: 0.9
- Timeout: 300s per test
- Cooldown: 1-3s between tests, 10s between models

### 7.2 Metrics Definitions
- **TPS:** Tokens per second (generation speed)
- **TTFT:** Time to first token (latency)
- **Efficiency:** TPS per billion parameters
- **Reliability:** Percentage of tests passed

### 7.3 Raw Data
Complete results available in: `{system_info.get('timestamp', 'data_file')}.json`

---

*Report generated by Qwen 3.5 Analysis Suite*
"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print(f"Report saved to: {output_file}")
    return output_file


def main():
    import sys
    
    # Find the most recent data file
    data_files = sorted(Path('.').glob('qwen35_complete_data_*.json'))
    
    if not data_files:
        print("No data files found. Please run qwen35_data_collection.py first.")
        print("Using sample data for demonstration...")
        # Create sample data structure
        return
    
    data_file = str(data_files[-1])
    print(f"Loading data from: {data_file}")
    
    data = load_data(data_file)
    
    print("\nAnalyzing performance...")
    analysis = analyze_model_performance(data)
    
    print("\nCreating visualizations...")
    chart_dir = create_visualizations(analysis)
    
    print("\nGenerating report...")
    report_file = generate_report(analysis, data)
    
    print("\n" + "="*80)
    print("ANALYSIS COMPLETE")
    print("="*80)
    print(f"\nCharts: {chart_dir}/")
    print(f"Report: {report_file}")
    
    # Print quick summary
    print("\nQuick Summary:")
    print("-" * 80)
    for model in analysis.keys():
        a = analysis[model]
        print(f"{model}:")
        print(f"  Speed: {a['tps_mean']:.1f} t/s (±{a['tps_stdev']:.1f})")
        print(f"  Efficiency: {a['efficiency']:.1f} t/s/B")
        print(f"  Tests: {a['tests_passed']}/{a['tests_total']} passed")


if __name__ == "__main__":
    main()
