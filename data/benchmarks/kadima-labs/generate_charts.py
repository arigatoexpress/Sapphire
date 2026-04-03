#!/usr/bin/env python3
"""Generate visualization charts from benchmark results"""

import json
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

# Load data
with open('final_qwen_results.json', 'r') as f:
    data = json.load(f)

models = list(data['models'].keys())
test_names = ['reasoning', 'code', 'math', 'creative']

# Set style
plt.rcParams['font.size'] = 10
plt.rcParams['axes.titlesize'] = 14
plt.rcParams['axes.labelsize'] = 11

# Colors
COLORS = {
    'qwen2.5:14b': '#E74C3C',
    'qwen2.5-coder:14b': '#3498DB', 
    'qwen3:14b': '#2ECC71',
    'qwen2.5:32b': '#9B59B6'
}

# Chart 1: Speed Comparison
fig, ax = plt.subplots(figsize=(12, 6))

model_names = [m.replace(':', '\n') for m in models]
avg_speeds = [data['models'][m]['avg'] for m in models]
colors = [COLORS[m] for m in models]

bars = ax.bar(model_names, avg_speeds, color=colors, edgecolor='white', linewidth=2, width=0.6)

# Add value labels
for bar, speed in zip(bars, avg_speeds):
    height = bar.get_height()
    ax.text(bar.get_x() + bar.get_width()/2., height + 2,
            f'{speed:.1f}\nt/s', ha='center', va='bottom', fontweight='bold', fontsize=11)

ax.set_ylabel('Tokens per Second', fontsize=12, fontweight='bold')
ax.set_title('Qwen Model Speed Comparison\nRTX 5070 Ti 16GB', fontsize=14, fontweight='bold')
ax.set_ylim(0, max(avg_speeds) * 1.15)
ax.grid(axis='y', alpha=0.3)

# Add medals
for i, (bar, speed) in enumerate(zip(bars, avg_speeds)):
    if i == 0:
        ax.text(bar.get_x() + bar.get_width()/2., height/2, '1st', 
                ha='center', va='center', fontsize=12, fontweight='bold', color='white')

plt.tight_layout()
plt.savefig('chart_speed_comparison.png', dpi=150, bbox_inches='tight', facecolor='white')
plt.close()
print("Saved: chart_speed_comparison.png")

# Chart 2: Test Breakdown
fig, ax = plt.subplots(figsize=(14, 7))

x = np.arange(len(test_names))
width = 0.2

for i, model in enumerate(models):
    speeds = [data['models'][model][t] for t in test_names]
    offset = (i - len(models)/2 + 0.5) * width
    bars = ax.bar(x + offset, speeds, width, label=model, color=COLORS[model], 
                  edgecolor='white', linewidth=1)

ax.set_xlabel('Test Category', fontsize=12, fontweight='bold')
ax.set_ylabel('Tokens per Second', fontsize=12, fontweight='bold')
ax.set_title('Performance by Test Category', fontsize=14, fontweight='bold')
ax.set_xticks(x)
ax.set_xticklabels([t.title() for t in test_names])
ax.legend(loc='upper right', fontsize=9)
ax.grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.savefig('chart_test_breakdown.png', dpi=150, bbox_inches='tight', facecolor='white')
plt.close()
print("Saved: chart_test_breakdown.png")

# Chart 3: Qwen3 vs Qwen2.5 Comparison
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

# Left: 14B models only
models_14b = ['qwen2.5:14b', 'qwen2.5-coder:14b', 'qwen3:14b']
speeds_14b = [data['models'][m]['avg'] for m in models_14b]
colors_14b = [COLORS[m] for m in models_14b]

bars = ax1.bar([m.replace(':', '\n') for m in models_14b], speeds_14b, 
               color=colors_14b, edgecolor='white', linewidth=2)
for bar, speed in zip(bars, speeds_14b):
    height = bar.get_height()
    ax1.text(bar.get_x() + bar.get_width()/2., height + 1,
             f'{speed:.1f}', ha='center', va='bottom', fontweight='bold')

ax1.set_ylabel('Tokens per Second', fontsize=11, fontweight='bold')
ax1.set_title('14B Models Comparison', fontsize=13, fontweight='bold')
ax1.set_ylim(0, 100)
ax1.grid(axis='y', alpha=0.3)

# Right: Comparison table
ax2.axis('off')
table_data = [
    ['Model', 'Speed (t/s)', 'vs Qwen2.5'],
    ['Qwen2.5:14b', f"{data['models']['qwen2.5:14b']['avg']:.1f}", 'baseline'],
    ['Qwen2.5-Coder', f"{data['models']['qwen2.5-coder:14b']['avg']:.1f}", 
     f"+{data['models']['qwen2.5-coder:14b']['avg'] - data['models']['qwen2.5:14b']['avg']:.1f}"],
    ['Qwen3:14b (NEW)', f"{data['models']['qwen3:14b']['avg']:.1f}", 
     f"{data['models']['qwen3:14b']['avg'] - data['models']['qwen2.5:14b']['avg']:+.1f}"],
]

table = ax2.table(cellText=table_data, cellLoc='center', loc='center',
                  colWidths=[0.4, 0.3, 0.3])
table.auto_set_font_size(False)
table.set_fontsize(10)
table.scale(1, 2)

# Style header
for i in range(3):
    table[(0, i)].set_facecolor('#34495E')
    table[(0, i)].set_text_props(weight='bold', color='white')

# Style rows
for i in range(1, 4):
    table[(i, 0)].set_facecolor('#ECF0F1')
    table[(i, 1)].set_facecolor('#EBF5FB')
    val = table_data[i][2]
    if val == 'baseline':
        table[(i, 2)].set_facecolor('#F8F9F9')
    elif val.startswith('+'):
        table[(i, 2)].set_facecolor('#E8F8F5')  # Green for positive
    else:
        table[(i, 2)].set_facecolor('#FDEDEC')  # Red for negative

ax2.set_title('Qwen3 vs Qwen2.5 Analysis', fontsize=13, fontweight='bold', pad=20)

plt.tight_layout()
plt.savefig('chart_qwen_comparison.png', dpi=150, bbox_inches='tight', facecolor='white')
plt.close()
print("Saved: chart_qwen_comparison.png")

# Chart 4: Dashboard
fig = plt.figure(figsize=(16, 10))
gs = fig.add_gridspec(3, 2, hspace=0.3, wspace=0.3)

# Title
fig.suptitle('Qwen Model Benchmark Dashboard\nRTX 5070 Ti Performance Analysis', 
             fontsize=16, fontweight='bold', y=0.98)

# Panel 1: Speed ranking
ax1 = fig.add_subplot(gs[0, 0])
sorted_models = sorted(models, key=lambda x: data['models'][x]['avg'], reverse=True)
speeds_sorted = [data['models'][m]['avg'] for m in sorted_models]
colors_sorted = [COLORS[m] for m in sorted_models]

bars = ax1.barh(range(len(sorted_models)), speeds_sorted, color=colors_sorted, 
                edgecolor='white', linewidth=2)
ax1.set_yticks(range(len(sorted_models)))
ax1.set_yticklabels([m.replace(':', ' ') for m in sorted_models])
ax1.set_xlabel('Tokens/s', fontsize=10)
ax1.set_title('Speed Ranking', fontsize=12, fontweight='bold')
ax1.grid(axis='x', alpha=0.3)

for i, (bar, speed) in enumerate(zip(bars, speeds_sorted)):
    ax1.text(speed + 1, i, f'{speed:.1f}', va='center', fontweight='bold')

# Panel 2: Size comparison
ax2 = fig.add_subplot(gs[0, 1])
sizes = [14, 14, 14, 32]  # Parameter counts
efficiency = [data['models'][m]['avg'] / s for m, s in zip(models, sizes)]

bars = ax2.bar([m.replace(':', '\n') for m in models], efficiency, 
               color=[COLORS[m] for m in models], edgecolor='white', linewidth=2)
ax2.set_ylabel('Tokens/s per Billion Params', fontsize=10)
ax2.set_title('Efficiency (Speed/Size)', fontsize=12, fontweight='bold')
ax2.grid(axis='y', alpha=0.3)

# Panel 3: Test comparison heatmap
ax3 = fig.add_subplot(gs[1, :])
heatmap_data = [[data['models'][m][t] for t in test_names] for m in models]
im = ax3.imshow(heatmap_data, cmap='RdYlGn', aspect='auto')

ax3.set_xticks(range(len(test_names)))
ax3.set_xticklabels([t.title() for t in test_names])
ax3.set_yticks(range(len(models)))
ax3.set_yticklabels([m.replace(':', ' ') for m in models])
ax3.set_title('Performance Heatmap by Test', fontsize=12, fontweight='bold')

# Add text annotations
for i in range(len(models)):
    for j in range(len(test_names)):
        text = ax3.text(j, i, f'{heatmap_data[i][j]:.0f}',
                       ha="center", va="center", color="black", fontsize=9)

plt.colorbar(im, ax=ax3, label='Tokens/s')

# Panel 4: Summary text
ax4 = fig.add_subplot(gs[2, :])
ax4.axis('off')

summary_text = """
QWEN MODEL BENCHMARK SUMMARY

Winner: Qwen2.5-Coder:14b (85.6 t/s) - Best overall performance

Key Findings:
• Qwen3:14b (NEW) is 8.6% slower than Qwen2.5:14b but may offer quality improvements
• Qwen2.5-Coder:14b is fastest for all task types
• Qwen2.5:32b is 15.8x slower than 14B models but offers larger context

Recommendations:
• For speed: Use Qwen2.5-Coder:14b (85.6 t/s)
• For new features: Try Qwen3:14b (77.2 t/s) - the newest model
• For large context: Qwen2.5:32b (5.4 t/s) - trade speed for capacity

Hardware: RTX 5070 Ti 16GB | All models fit in VRAM comfortably
"""

ax4.text(0.5, 0.5, summary_text, transform=ax4.transAxes, fontsize=10,
         verticalalignment='center', horizontalalignment='center',
         bbox=dict(boxstyle='round,pad=1', facecolor='lightblue', alpha=0.3),
         family='monospace')

plt.savefig('chart_dashboard.png', dpi=150, bbox_inches='tight', facecolor='white')
plt.close()
print("Saved: chart_dashboard.png")

print("\n" + "="*60)
print("VISUALIZATION COMPLETE")
print("="*60)
print("\nGenerated charts:")
print("  1. chart_speed_comparison.png - Overall speed ranking")
print("  2. chart_test_breakdown.png - Performance by test type")
print("  3. chart_qwen_comparison.png - Qwen3 vs Qwen2.5 analysis")
print("  4. chart_dashboard.png - Complete dashboard")
