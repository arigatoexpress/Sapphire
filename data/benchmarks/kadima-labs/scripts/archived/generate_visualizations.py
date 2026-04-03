#!/usr/bin/env python3
"""
Generate visualizations from available data
"""

import json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from datetime import datetime

# Data from our tests
data = {
    'qwen3.5:0.8b': {
        'speeds': [86.7, 312.5, 310.1, 85.5, 116.2, 307.9, 307.1],
        'ttft': [500, 600, 550, 520, 580, 560, 540],  # ms
        'size': 0.8,
        'tests_passed': 7,
        'color': '#2ecc71'
    },
    'qwen3.5:4b': {
        'speeds': [4.6, 4.5, 4.8, 4.4, 4.7],
        'ttft': [2500, 2600, 2400, 2550, 2450],
        'size': 4,
        'tests_passed': 5,
        'color': '#3498db'
    },
    'qwen3.5:9b': {
        'speeds': [5.3, 2.3, 3.7, 5.5],
        'ttft': [6700, 6800, 6500, 6600],
        'size': 9,
        'tests_passed': 4,
        'color': '#e74c3c'
    }
}

import statistics

# Calculate statistics
analysis = {}
for model, d in data.items():
    speeds = d['speeds']
    analysis[model] = {
        'mean': statistics.mean(speeds),
        'median': statistics.median(speeds),
        'stdev': statistics.stdev(speeds) if len(speeds) > 1 else 0,
        'min': min(speeds),
        'max': max(speeds),
        'efficiency': statistics.mean(speeds) / d['size'],
        'ttft_mean': statistics.mean(d['ttft']),
        'size': d['size'],
        'tests_passed': d['tests_passed'],
        'color': d['color']
    }

models = list(data.keys())
model_labels = [m.replace('qwen3.5:', '') for m in models]
colors = [data[m]['color'] for m in models]

plt.style.use('seaborn-v0_8-whitegrid')

# Create output directory
import os
os.makedirs('qwen35_visualizations', exist_ok=True)

# 1. Speed Comparison
fig, ax = plt.subplots(figsize=(12, 7))
x = np.arange(len(models))
means = [analysis[m]['mean'] for m in models]
stdevs = [analysis[m]['stdev'] for m in models]

bars = ax.bar(x, means, yerr=stdevs, capsize=5, color=colors, 
              edgecolor='black', linewidth=2, alpha=0.8)

for i, (bar, mean) in enumerate(zip(bars, means)):
    height = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2., height,
            f'{mean:.1f}',
            ha='center', va='bottom', fontsize=14, fontweight='bold')

ax.set_ylabel('Tokens per Second', fontsize=13, fontweight='bold')
ax.set_xlabel('Model Size', fontsize=13, fontweight='bold')
ax.set_title('Qwen 3.5: Average Generation Speed\n(Error bars show standard deviation)', 
             fontsize=15, fontweight='bold', pad=20)
ax.set_xticks(x)
ax.set_xticklabels(model_labels, fontsize=12)
ax.set_ylim(0, max(means) * 1.2)
ax.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('qwen35_visualizations/01_speed_comparison.png', dpi=300, bbox_inches='tight')
plt.close()

# 2. Efficiency (tps per billion params)
fig, ax = plt.subplots(figsize=(12, 7))
efficiencies = [analysis[m]['efficiency'] for m in models]

bars = ax.bar(x, efficiencies, color=colors, edgecolor='black', linewidth=2, alpha=0.8)

for i, (bar, eff) in enumerate(zip(bars, efficiencies)):
    height = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2., height,
            f'{eff:.1f}',
            ha='center', va='bottom', fontsize=14, fontweight='bold')
    # Add efficiency ratio text
    if i == 0:
        ax.text(bar.get_x() + bar.get_width()/2., height/2,
                'BEST\nEFFICIENCY',
                ha='center', va='center', fontsize=10, 
                color='white', fontweight='bold')

ax.set_ylabel('Tokens/sec per Billion Parameters', fontsize=13, fontweight='bold')
ax.set_xlabel('Model Size', fontsize=13, fontweight='bold')
ax.set_title('Qwen 3.5: Efficiency Comparison\n(Higher is better - shows speed per parameter)', 
             fontsize=15, fontweight='bold', pad=20)
ax.set_xticks(x)
ax.set_xticklabels(model_labels, fontsize=12)
ax.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('qwen35_visualizations/02_efficiency.png', dpi=300, bbox_inches='tight')
plt.close()

# 3. Speed Range (Min-Max)
fig, ax = plt.subplots(figsize=(12, 7))
mins = [analysis[m]['min'] for m in models]
maxs = [analysis[m]['max'] for m in models]
means = [analysis[m]['mean'] for m in models]

# Plot ranges
for i, model in enumerate(models):
    ax.plot([i, i], [mins[i], maxs[i]], 'k-', linewidth=3, alpha=0.3)
    ax.plot(i, means[i], 'o', markersize=15, color=colors[i], 
           label=model_labels[i], markeredgecolor='black', markeredgewidth=2)

ax.set_ylabel('Tokens per Second', fontsize=13, fontweight='bold')
ax.set_xlabel('Model Size', fontsize=13, fontweight='bold')
ax.set_title('Qwen 3.5: Speed Range Across Tests\n(Lines show min-max, dots show mean)', 
             fontsize=15, fontweight='bold', pad=20)
ax.set_xticks(x)
ax.set_xticklabels(model_labels, fontsize=12)
ax.legend(fontsize=11)
ax.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('qwen35_visualizations/03_speed_range.png', dpi=300, bbox_inches='tight')
plt.close()

# 4. Time to First Token
fig, ax = plt.subplots(figsize=(12, 7))
ttfts = [analysis[m]['ttft_mean'] for m in models]

bars = ax.bar(x, ttfts, color=colors, edgecolor='black', linewidth=2, alpha=0.8)

for i, (bar, ttft) in enumerate(zip(bars, ttfts)):
    height = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2., height,
            f'{ttft:.0f}ms',
            ha='center', va='bottom', fontsize=12, fontweight='bold')

ax.set_ylabel('Time to First Token (milliseconds)', fontsize=13, fontweight='bold')
ax.set_xlabel('Model Size', fontsize=13, fontweight='bold')
ax.set_title('Qwen 3.5: Latency (Time to First Token)\n(Lower is better)', 
             fontsize=15, fontweight='bold', pad=20)
ax.set_xticks(x)
ax.set_xticklabels(model_labels, fontsize=12)
ax.grid(axis='y', alpha=0.3)

# Add note about scaling
ax.text(0.5, 0.95, 'Note: 9B model takes ~13x longer to start than 0.8B', 
        transform=ax.transAxes, ha='center', va='top',
        bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5),
        fontsize=10)

plt.tight_layout()
plt.savefig('qwen35_visualizations/04_latency.png', dpi=300, bbox_inches='tight')
plt.close()

# 5. Radar Chart
fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(projection='polar'))

categories = ['Speed', 'Efficiency', 'Low Latency', 'Consistency']
N = len(categories)

# Compute metric values (normalized 0-1)
angles = [n / float(N) * 2 * np.pi for n in range(N)]
angles += angles[:1]

for model in models:
    a = analysis[model]
    # Normalize metrics
    speed_norm = min(a['mean'] / 100, 1)
    eff_norm = min(a['efficiency'] / 50, 1)
    latency_norm = min(1000 / a['ttft_mean'], 1)  # Inverse, lower is better
    consistency_norm = min(50 / (a['stdev'] + 1), 1)
    
    values = [speed_norm, eff_norm, latency_norm, consistency_norm]
    values += values[:1]
    
    ax.plot(angles, values, 'o-', linewidth=2.5, label=model_labels[models.index(model)],
           color=colors[models.index(model)])
    ax.fill(angles, values, alpha=0.25, color=colors[models.index(model)])

ax.set_xticks(angles[:-1])
ax.set_xticklabels(categories, fontsize=12)
ax.set_ylim(0, 1)
ax.set_title('Qwen 3.5: Multi-Dimensional Performance\n(Normalized scores)', 
             fontsize=15, fontweight='bold', pad=30)
ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0), fontsize=11)
ax.grid(True)

plt.tight_layout()
plt.savefig('qwen35_visualizations/05_radar.png', dpi=300, bbox_inches='tight')
plt.close()

# 6. Size vs Performance Scatter
fig, ax = plt.subplots(figsize=(12, 8))

sizes = [analysis[m]['size'] for m in models]
means = [analysis[m]['mean'] for m in models]

# Create bubble chart (bubble size = tests passed)
tests_passed = [analysis[m]['tests_passed'] * 100 for m in models]

scatter = ax.scatter(sizes, means, s=tests_passed, c=colors, 
                    alpha=0.6, edgecolors='black', linewidths=2)

# Add labels
for i, model in enumerate(models):
    ax.annotate(model_labels[i], 
               (sizes[i], means[i]),
               xytext=(10, 10), textcoords='offset points',
               fontsize=12, fontweight='bold',
               bbox=dict(boxstyle='round,pad=0.3', facecolor=colors[i], alpha=0.3))

ax.set_xlabel('Model Size (Billion Parameters)', fontsize=13, fontweight='bold')
ax.set_ylabel('Average Speed (Tokens/sec)', fontsize=13, fontweight='bold')
ax.set_title('Qwen 3.5: Size vs Performance\n(Bubble size = number of tests passed)', 
             fontsize=15, fontweight='bold', pad=20)
ax.set_xscale('log')
ax.set_yscale('log')
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig('qwen35_visualizations/06_size_vs_performance.png', dpi=300, bbox_inches='tight')
plt.close()

# 7. Summary Dashboard
fig = plt.figure(figsize=(16, 10))
gs = fig.add_gridspec(3, 3, hspace=0.3, wspace=0.3)

# Title
fig.suptitle('Qwen 3.5 Benchmark Dashboard', fontsize=20, fontweight='bold', y=0.98)

# Speed bars
ax1 = fig.add_subplot(gs[0, :2])
bars = ax1.bar(model_labels, [analysis[m]['mean'] for m in models], 
               color=colors, edgecolor='black', linewidth=2)
ax1.set_ylabel('Tokens/sec', fontsize=11, fontweight='bold')
ax1.set_title('Generation Speed', fontsize=13, fontweight='bold')
for bar, mean in zip(bars, [analysis[m]['mean'] for m in models]):
    ax1.text(bar.get_x() + bar.get_width()/2., bar.get_height(),
            f'{mean:.1f}', ha='center', va='bottom', fontsize=11, fontweight='bold')

# Efficiency
ax2 = fig.add_subplot(gs[0, 2])
bars = ax2.bar(model_labels, [analysis[m]['efficiency'] for m in models], 
               color=colors, edgecolor='black', linewidth=2)
ax2.set_ylabel('TPS/B', fontsize=11, fontweight='bold')
ax2.set_title('Efficiency', fontsize=13, fontweight='bold')

# Speed distribution
ax3 = fig.add_subplot(gs[1, :2])
for i, model in enumerate(models):
    ax3.scatter([model_labels[i]] * len(data[model]['speeds']), 
               data[model]['speeds'], 
               s=100, color=colors[i], alpha=0.6, edgecolors='black', linewidth=1.5)
ax3.set_ylabel('Tokens/sec', fontsize=11, fontweight='bold')
ax3.set_title('Speed Distribution (Individual Tests)', fontsize=13, fontweight='bold')
ax3.grid(axis='y', alpha=0.3)

# TTFT
ax4 = fig.add_subplot(gs[1, 2])
bars = ax4.bar(model_labels, [analysis[m]['ttft_mean']/1000 for m in models], 
               color=colors, edgecolor='black', linewidth=2)
ax4.set_ylabel('Seconds', fontsize=11, fontweight='bold')
ax4.set_title('Time to First Token', fontsize=13, fontweight='bold')

# Comparison table
ax5 = fig.add_subplot(gs[2, :])
ax5.axis('off')
table_data = []
for model in models:
    a = analysis[model]
    table_data.append([
        model_labels[models.index(model)],
        f"{a['mean']:.1f} t/s",
        f"{a['efficiency']:.1f} t/s/B",
        f"{a['ttft_mean']/1000:.1f}s",
        f"{a['tests_passed']} tests"
    ])

table = ax5.table(cellText=table_data,
                 colLabels=['Model', 'Speed', 'Efficiency', 'Latency', 'Tests'],
                 cellLoc='center',
                 loc='center',
                 colColours=['#4472C4']*5)
table.auto_set_font_size(False)
table.set_fontsize(11)
table.scale(1.2, 2)
ax5.set_title('Summary Statistics', fontsize=13, fontweight='bold', pad=20)

plt.savefig('qwen35_visualizations/07_dashboard.png', dpi=300, bbox_inches='tight')
plt.close()

print("Visualizations created in qwen35_visualizations/:")
for i, name in enumerate([
    '01_speed_comparison.png',
    '02_efficiency.png', 
    '03_speed_range.png',
    '04_latency.png',
    '05_radar.png',
    '06_size_vs_performance.png',
    '07_dashboard.png'
], 1):
    print(f"  {i}. {name}")
