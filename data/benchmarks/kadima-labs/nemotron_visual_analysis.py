#!/usr/bin/env python3
"""
Visual Data Analysis: Nemotron vs Other Open Source Models
Generates comprehensive comparison charts
"""

import json
import os

os.environ["PYTHONIOENCODING"] = "utf-8"

import matplotlib

matplotlib.use('Agg')
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

# Load benchmark data
with open("D:/Dev/01_AI/AI_Benchmark/model_comparison_20260323_202328.json") as f:
    data = json.load(f)

results = data["results"]

# Color palette by family
FAMILY_COLORS = {
    "Nemotron": "#76B900",  # NVIDIA green
    "Qwen": "#FF6B35",     # Alibaba orange
    "DeepSeek": "#4A90D9",  # DeepSeek blue
    "Phi": "#9B59B6",      # Microsoft purple
    "GLM": "#E74C3C",      # Zhipu red
    "Gemma": "#F39C12",    # Google gold
}

FAMILY_COLORS_LIGHT = {
    "Nemotron": "#A8D94E",
    "Qwen": "#FF9B6B",
    "DeepSeek": "#7AB3E8",
    "Phi": "#C39BD3",
    "GLM": "#F1948A",
    "Gemma": "#F7DC6F",
}

# Extract data
models = list(results.keys())
model_short = [m.replace(":latest", "") for m in models]
families = [results[m]["info"]["family"] for m in models]
params = [results[m]["info"]["params"] for m in models]
tiers = [results[m]["info"]["tier"] for m in models]
avg_tps = [results[m]["summary"]["avg_tps"] for m in models]
avg_time = [results[m]["summary"]["avg_time"] for m in models]
total_tokens = [results[m]["summary"]["total_tokens"] for m in models]
accuracy_str = [results[m]["summary"]["accuracy"] for m in models]
accuracy_num = [int(a.split("/")[0]) for a in accuracy_str]
colors = [FAMILY_COLORS[f] for f in families]
colors_light = [FAMILY_COLORS_LIGHT[f] for f in families]

test_names = ["math", "logic", "code", "context", "creative"]

# ============================================================
# CHART 1: Speed vs Accuracy Scatter (Hero Chart)
# ============================================================
fig, ax = plt.subplots(figsize=(14, 9))
fig.patch.set_facecolor('#1a1a2e')
ax.set_facecolor('#16213e')

for i, model in enumerate(models):
    size = 200 + total_tokens[i] / 8
    marker = 's' if families[i] == "Nemotron" else 'o'
    edge = '#ffffff' if families[i] == "Nemotron" else '#888888'
    ax.scatter(avg_tps[i], accuracy_num[i], s=size, c=colors[i],
              marker=marker, edgecolors=edge, linewidth=2.5, zorder=5, alpha=0.9)

    # Label
    offset_x = 3
    offset_y = 0.08
    if "qwen3.5:4b" in model:
        offset_y = -0.15
    elif "qwen3:14b" in model:
        offset_x = -5
        offset_y = 0.1

    ax.annotate(model_short[i], (avg_tps[i], accuracy_num[i]),
               textcoords="offset points", xytext=(offset_x + 8, offset_y * 100),
               fontsize=9, color='#e0e0e0', fontweight='bold',
               arrowprops=dict(arrowstyle='-', color='#555555', lw=0.5))

# Highlight Nemotron zone
nemotron_tps = [avg_tps[i] for i in range(len(models)) if families[i] == "Nemotron"]
nemotron_acc = [accuracy_num[i] for i in range(len(models)) if families[i] == "Nemotron"]
if nemotron_tps:
    ax.axvspan(min(nemotron_tps) - 10, max(nemotron_tps) + 10,
              alpha=0.08, color='#76B900', zorder=0)
    ax.text(max(nemotron_tps) - 5, 0.3, 'NEMOTRON\nZONE', fontsize=10,
           color='#76B900', alpha=0.4, fontweight='bold', ha='center')

ax.set_xlabel('Average Speed (tokens/sec)', fontsize=13, color='#cccccc', fontweight='bold')
ax.set_ylabel('Accuracy (correct answers out of 5)', fontsize=13, color='#cccccc', fontweight='bold')
ax.set_title('Nemotron vs Open Source Models: Speed vs Accuracy\n'
            'RTX 5070 Ti 16GB | Ollama Local Inference',
            fontsize=16, color='#ffffff', fontweight='bold', pad=20)
ax.set_yticks([0, 1, 2, 3, 4, 5])
ax.set_ylim(-0.3, 5.5)
ax.grid(True, alpha=0.15, color='#ffffff')
ax.tick_params(colors='#aaaaaa')

# Legend
legend_elements = [
    mpatches.Patch(facecolor=FAMILY_COLORS["Nemotron"], label='Nemotron (NVIDIA)', edgecolor='white', linewidth=1.5),
    mpatches.Patch(facecolor=FAMILY_COLORS["Phi"], label='Phi (Microsoft)', edgecolor='#888', linewidth=1),
    mpatches.Patch(facecolor=FAMILY_COLORS["Qwen"], label='Qwen (Alibaba)', edgecolor='#888', linewidth=1),
    mpatches.Patch(facecolor=FAMILY_COLORS["DeepSeek"], label='DeepSeek', edgecolor='#888', linewidth=1),
    mpatches.Patch(facecolor=FAMILY_COLORS["GLM"], label='GLM (Zhipu)', edgecolor='#888', linewidth=1),
    mpatches.Patch(facecolor=FAMILY_COLORS["Gemma"], label='Gemma (Google)', edgecolor='#888', linewidth=1),
]
ax.legend(handles=legend_elements, loc='upper right', fontsize=11,
         facecolor='#1a1a2e', edgecolor='#555555', labelcolor='#cccccc')

# Annotations
ax.annotate('Ideal: Fast + Accurate', xy=(150, 5), fontsize=10,
           color='#888888', fontstyle='italic',
           arrowprops=dict(arrowstyle='->', color='#555555'),
           xytext=(100, 5.3))

plt.tight_layout()
plt.savefig('D:/Dev/01_AI/AI_Benchmark/chart_nemotron_speed_vs_accuracy.png', dpi=180, bbox_inches='tight',
           facecolor=fig.get_facecolor())
print("[1/5] Speed vs Accuracy scatter saved")
plt.close()

# ============================================================
# CHART 2: Per-Test Speed Heatmap
# ============================================================
fig, ax = plt.subplots(figsize=(14, 8))
fig.patch.set_facecolor('#1a1a2e')
ax.set_facecolor('#16213e')

# Build heatmap data
heatmap_data = []
correctness_data = []
for model in models:
    row = []
    correct_row = []
    for test in test_names:
        t = results[model]["tests"][test]
        row.append(t["tps"])
        correct_row.append(t.get("correct", False))
    heatmap_data.append(row)
    correctness_data.append(correct_row)

heatmap_arr = np.array(heatmap_data)

# Custom colormap
from matplotlib.colors import LinearSegmentedColormap

cmap = LinearSegmentedColormap.from_list('custom', ['#1a1a2e', '#76B900', '#FFD700'], N=256)

im = ax.imshow(heatmap_arr, cmap=cmap, aspect='auto', interpolation='nearest')

# Annotate cells
for i in range(len(models)):
    for j in range(len(test_names)):
        val = heatmap_arr[i, j]
        correct = correctness_data[i][j]
        color = '#ffffff' if val < 120 else '#000000'
        mark = '' if correct else ' X'
        text = f"{val:.0f}{mark}"
        ax.text(j, i, text, ha='center', va='center', fontsize=10,
               color=color, fontweight='bold')

# Highlight Nemotron rows
for i, fam in enumerate(families):
    if fam == "Nemotron":
        ax.add_patch(plt.Rectangle((-0.5, i - 0.5), len(test_names), 1,
                     fill=False, edgecolor='#76B900', linewidth=2.5, zorder=10))

ax.set_xticks(range(len(test_names)))
ax.set_xticklabels([t.upper() for t in test_names], fontsize=12, color='#cccccc', fontweight='bold')
ax.set_yticks(range(len(models)))
ax.set_yticklabels(model_short, fontsize=11, color='#cccccc')
ax.set_title('Per-Test Speed Heatmap (tokens/sec)\n'
            'Green borders = Nemotron | X = incorrect answer',
            fontsize=14, color='#ffffff', fontweight='bold', pad=15)

cbar = plt.colorbar(im, ax=ax, shrink=0.8)
cbar.set_label('Tokens/sec', color='#cccccc', fontsize=11)
cbar.ax.tick_params(colors='#aaaaaa')

plt.tight_layout()
plt.savefig('D:/Dev/01_AI/AI_Benchmark/chart_nemotron_heatmap.png', dpi=180, bbox_inches='tight',
           facecolor=fig.get_facecolor())
print("[2/5] Per-test heatmap saved")
plt.close()

# ============================================================
# CHART 3: Nemotron vs Best-in-Class Radar
# ============================================================
fig, axes = plt.subplots(1, 2, figsize=(16, 8), subplot_kw=dict(polar=True))
fig.patch.set_facecolor('#1a1a2e')

categories = ['Math', 'Logic', 'Code', 'Context', 'Creative']
N = len(categories)
angles = [n / float(N) * 2 * np.pi for n in range(N)]
angles += angles[:1]

# Normalize TPS values (0-1 scale based on max per test)
max_per_test = {}
for test in test_names:
    max_per_test[test] = max(results[m]["tests"][test]["tps"] for m in models)

def get_normalized(model_name):
    vals = []
    for test in test_names:
        tps = results[model_name]["tests"][test]["tps"]
        vals.append(tps / max_per_test[test] if max_per_test[test] > 0 else 0)
    vals += vals[:1]
    return vals

# Left: Nemotron Nano vs best Qwen (2.5:14b) and DeepSeek
compare_models = [
    ("nemotron-3-nano:4b-q8_0", "#76B900", "Nemotron Nano q8 (BEST)"),
    ("phi4", "#9B59B6", "Phi-4 14B"),
    ("qwen2.5:14b", "#FF6B35", "Qwen 2.5 14B"),
    ("gemma3:27b", "#F39C12", "Gemma 3 27B"),
]

for ax_idx, (title, compare_set) in enumerate([
    ("Best-in-Class Comparison", compare_models),
    ("Small Model Shootout (< 5GB)", [
        ("nemotron-3-nano:4b-q8_0", "#76B900", "Nemotron q8_0"),
        ("phi4-mini", "#9B59B6", "Phi-4 Mini"),
        ("nemotron-mini:4b", "#A8D94E", "Nemotron Mini"),
    ])
]):
    ax = axes[ax_idx]
    ax.set_facecolor('#16213e')

    for model_name, color, label in compare_set:
        vals = get_normalized(model_name)
        ax.plot(angles, vals, 'o-', linewidth=2, color=color, label=label, markersize=5)
        ax.fill(angles, vals, alpha=0.15, color=color)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=10, color='#cccccc', fontweight='bold')
    ax.set_ylim(0, 1.15)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(['25%', '50%', '75%', '100%'], fontsize=8, color='#888888')
    ax.grid(True, alpha=0.2, color='#ffffff')
    ax.set_title(title, fontsize=12, color='#ffffff', fontweight='bold', pad=20)
    ax.legend(loc='lower right', fontsize=9, facecolor='#1a1a2e',
             edgecolor='#555555', labelcolor='#cccccc',
             bbox_to_anchor=(1.15, -0.1))
    ax.tick_params(colors='#aaaaaa')

fig.suptitle('Nemotron Radar Analysis: Strengths by Task Category',
            fontsize=15, color='#ffffff', fontweight='bold', y=1.02)
plt.tight_layout()
plt.savefig('D:/Dev/01_AI/AI_Benchmark/chart_nemotron_radar.png', dpi=180, bbox_inches='tight',
           facecolor=fig.get_facecolor())
print("[3/5] Radar comparison saved")
plt.close()

# ============================================================
# CHART 4: Response Time Distribution (Bar + Grouped)
# ============================================================
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
fig.patch.set_facecolor('#1a1a2e')

# Left: Average speed bar chart
sorted_indices = np.argsort(avg_tps)[::-1]
sorted_models = [model_short[i] for i in sorted_indices]
sorted_tps = [avg_tps[i] for i in sorted_indices]
sorted_colors = [colors[i] for i in sorted_indices]
sorted_acc = [accuracy_num[i] for i in sorted_indices]
sorted_families = [families[i] for i in sorted_indices]

ax1.set_facecolor('#16213e')
bars = ax1.barh(range(len(sorted_models)), sorted_tps, color=sorted_colors,
               edgecolor='#333333', linewidth=0.5, height=0.7)

# Add Nemotron glow
for i, bar in enumerate(bars):
    if sorted_families[i] == "Nemotron":
        bar.set_edgecolor('#76B900')
        bar.set_linewidth(2)

# Labels on bars
for i, (tps, acc) in enumerate(zip(sorted_tps, sorted_acc)):
    ax1.text(tps + 2, i, f'{tps:.0f} t/s  ({acc}/5)',
            va='center', fontsize=10, color='#e0e0e0', fontweight='bold')

ax1.set_yticks(range(len(sorted_models)))
ax1.set_yticklabels(sorted_models, fontsize=11, color='#cccccc')
ax1.set_xlabel('Average Tokens/sec', fontsize=12, color='#cccccc', fontweight='bold')
ax1.set_title('Speed Rankings\n(higher = faster)', fontsize=13, color='#ffffff', fontweight='bold')
ax1.grid(axis='x', alpha=0.15, color='#ffffff')
ax1.tick_params(colors='#aaaaaa')
ax1.set_xlim(0, max(sorted_tps) * 1.35)
ax1.invert_yaxis()

# Right: Grouped bar chart - Nemotron vs Others by test
ax2.set_facecolor('#16213e')

x = np.arange(len(test_names))
width = 0.18

# Best of each family
family_list = ["Nemotron", "Phi", "Qwen", "DeepSeek", "GLM"]
family_best = {}
for fam in family_list:
    family_best[fam] = []
    for test in test_names:
        fam_models = [m for m in models if results[m]["info"]["family"] == fam]
        if fam_models:
            family_best[fam].append(max([results[m]["tests"][test]["tps"] for m in fam_models]))
        else:
            family_best[fam].append(0)

for i, fam in enumerate(family_list):
    offset = (i - len(family_list)/2 + 0.5) * width
    ax2.bar(x + offset, family_best[fam], width, label=f'{fam} (best)',
           color=FAMILY_COLORS[fam], edgecolor='#555', linewidth=0.5)

ax2.set_xticks(x)
ax2.set_xticklabels([t.upper() for t in test_names], fontsize=11, color='#cccccc', fontweight='bold')
ax2.set_ylabel('Tokens/sec', fontsize=12, color='#cccccc', fontweight='bold')
ax2.set_title('Nemotron vs Best Qwen vs DeepSeek\nPer-Task Comparison',
             fontsize=13, color='#ffffff', fontweight='bold')
ax2.legend(fontsize=10, facecolor='#1a1a2e', edgecolor='#555555', labelcolor='#cccccc')
ax2.grid(axis='y', alpha=0.15, color='#ffffff')
ax2.tick_params(colors='#aaaaaa')

plt.tight_layout()
plt.savefig('D:/Dev/01_AI/AI_Benchmark/chart_nemotron_speed_bars.png', dpi=180, bbox_inches='tight',
           facecolor=fig.get_facecolor())
print("[4/5] Speed bar charts saved")
plt.close()

# ============================================================
# CHART 5: Executive Dashboard
# ============================================================
fig = plt.figure(figsize=(18, 12))
fig.patch.set_facecolor('#1a1a2e')

# Title
fig.suptitle('NEMOTRON vs OPEN SOURCE MODELS - EXECUTIVE DASHBOARD\n'
            'RTX 5070 Ti 16GB | Ollama Local Inference | March 2026',
            fontsize=18, color='#ffffff', fontweight='bold', y=0.98)

# Panel 1: Speed vs Accuracy (top left)
ax1 = fig.add_subplot(2, 3, 1)
ax1.set_facecolor('#16213e')
for i in range(len(models)):
    marker = 's' if families[i] == "Nemotron" else 'o'
    ax1.scatter(avg_tps[i], accuracy_num[i], s=120, c=colors[i],
               marker=marker, edgecolors='white' if families[i] == "Nemotron" else '#666',
               linewidth=1.5, zorder=5)
ax1.set_xlabel('Tokens/sec', fontsize=9, color='#aaa')
ax1.set_ylabel('Accuracy (/5)', fontsize=9, color='#aaa')
ax1.set_title('Speed vs Accuracy', fontsize=11, color='#fff', fontweight='bold')
ax1.grid(True, alpha=0.1, color='#fff')
ax1.tick_params(colors='#888', labelsize=8)

# Panel 2: Speed bars (top middle)
ax2 = fig.add_subplot(2, 3, 2)
ax2.set_facecolor('#16213e')
y_pos = range(len(sorted_models))
bars = ax2.barh(y_pos, sorted_tps, color=sorted_colors, height=0.6)
for i, bar in enumerate(bars):
    if sorted_families[i] == "Nemotron":
        bar.set_edgecolor('#76B900')
        bar.set_linewidth(2)
ax2.set_yticks(y_pos)
ax2.set_yticklabels(sorted_models, fontsize=8, color='#ccc')
ax2.set_title('Speed Ranking', fontsize=11, color='#fff', fontweight='bold')
ax2.tick_params(colors='#888', labelsize=8)
ax2.invert_yaxis()
ax2.grid(axis='x', alpha=0.1, color='#fff')

# Panel 3: Accuracy bars (top right)
ax3 = fig.add_subplot(2, 3, 3)
ax3.set_facecolor('#16213e')
acc_sorted_idx = np.argsort(accuracy_num)[::-1]
acc_sorted_models = [model_short[i] for i in acc_sorted_idx]
acc_sorted_vals = [accuracy_num[i] for i in acc_sorted_idx]
acc_sorted_colors = [colors[i] for i in acc_sorted_idx]
acc_sorted_fam = [families[i] for i in acc_sorted_idx]

bars = ax3.barh(range(len(acc_sorted_models)), acc_sorted_vals,
               color=acc_sorted_colors, height=0.6)
for i, bar in enumerate(bars):
    if acc_sorted_fam[i] == "Nemotron":
        bar.set_edgecolor('#76B900')
        bar.set_linewidth(2)
ax3.set_yticks(range(len(acc_sorted_models)))
ax3.set_yticklabels(acc_sorted_models, fontsize=8, color='#ccc')
ax3.set_title('Accuracy Ranking', fontsize=11, color='#fff', fontweight='bold')
ax3.set_xlim(0, 5.5)
ax3.tick_params(colors='#888', labelsize=8)
ax3.invert_yaxis()
ax3.grid(axis='x', alpha=0.1, color='#fff')

# Panel 4: Nemotron family breakdown (bottom left)
ax4 = fig.add_subplot(2, 3, 4)
ax4.set_facecolor('#16213e')
nem_models = [m for m in models if results[m]["info"]["family"] == "Nemotron"]
nem_names = [m.replace(":", "\n") for m in nem_models]
for j, test in enumerate(test_names):
    vals = [results[m]["tests"][test]["tps"] for m in nem_models]
    x = np.arange(len(nem_models)) + j * 0.15
    ax4.bar(x, vals, 0.14, label=test.upper(), alpha=0.85)
ax4.set_xticks(np.arange(len(nem_models)) + 0.3)
ax4.set_xticklabels(nem_names, fontsize=9, color='#ccc')
ax4.set_ylabel('t/s', fontsize=9, color='#aaa')
ax4.set_title('Nemotron Family Breakdown', fontsize=11, color='#76B900', fontweight='bold')
ax4.legend(fontsize=7, ncol=5, facecolor='#1a1a2e', edgecolor='#555', labelcolor='#ccc',
          loc='upper right')
ax4.tick_params(colors='#888', labelsize=8)
ax4.grid(axis='y', alpha=0.1, color='#fff')

# Panel 5: Efficiency score (bottom middle)
ax5 = fig.add_subplot(2, 3, 5)
ax5.set_facecolor('#16213e')

# Efficiency = speed * accuracy / param_count_billions
param_nums = {"4B": 4, "4B-q8": 4, "4B-bf16": 4, "3.8B": 3.8, "9B": 9, "14B": 14, "27B": 27}
efficiency = []
for i, m in enumerate(models):
    p = param_nums.get(params[i], 4)
    eff = (avg_tps[i] * accuracy_num[i]) / p
    efficiency.append(eff)

eff_sorted_idx = np.argsort(efficiency)[::-1]
eff_sorted_models = [model_short[i] for i in eff_sorted_idx]
eff_sorted_vals = [efficiency[i] for i in eff_sorted_idx]
eff_sorted_colors = [colors[i] for i in eff_sorted_idx]
eff_sorted_fam = [families[i] for i in eff_sorted_idx]

bars = ax5.barh(range(len(eff_sorted_models)), eff_sorted_vals,
               color=eff_sorted_colors, height=0.6)
for i, bar in enumerate(bars):
    if eff_sorted_fam[i] == "Nemotron":
        bar.set_edgecolor('#76B900')
        bar.set_linewidth(2)
    ax5.text(eff_sorted_vals[i] + 0.5, i, f'{eff_sorted_vals[i]:.1f}',
            va='center', fontsize=8, color='#e0e0e0')

ax5.set_yticks(range(len(eff_sorted_models)))
ax5.set_yticklabels(eff_sorted_models, fontsize=8, color='#ccc')
ax5.set_title('Efficiency Score\n(speed x accuracy / params)', fontsize=11, color='#fff', fontweight='bold')
ax5.tick_params(colors='#888', labelsize=8)
ax5.invert_yaxis()
ax5.grid(axis='x', alpha=0.1, color='#fff')

# Panel 6: Key findings text box (bottom right)
ax6 = fig.add_subplot(2, 3, 6)
ax6.set_facecolor('#16213e')
ax6.axis('off')

findings = [
    ("SPEED + ACCURACY", "Nemotron q8_0: 5/5 @ 101 t/s", "#76B900"),
    ("SPEED KING", "Nemotron Nano 4B @ 136 t/s", "#76B900"),
    ("BEST EFFICIENCY", f"{eff_sorted_models[0]} @ {eff_sorted_vals[0]:.1f}", "#FFD700"),
    ("NEW CONTENDER", "Phi-4 Mini: 4/5 @ 117 t/s", "#9B59B6"),
    ("PERFECT ACCURACY", "Gemma 27B + Nemotron q8: 5/5", "#F39C12"),
]

ax6.text(0.5, 0.95, 'KEY FINDINGS', fontsize=13, color='#ffffff',
        fontweight='bold', ha='center', va='top', transform=ax6.transAxes)

for idx, (label, value, color) in enumerate(findings):
    y = 0.82 - idx * 0.17
    ax6.text(0.05, y, label, fontsize=10, color=color,
            fontweight='bold', transform=ax6.transAxes)
    ax6.text(0.05, y - 0.07, value, fontsize=9, color='#cccccc',
            transform=ax6.transAxes)

# Legend at bottom
legend_elements = [
    mpatches.Patch(facecolor=FAMILY_COLORS["Nemotron"], label='Nemotron'),
    mpatches.Patch(facecolor=FAMILY_COLORS["Phi"], label='Phi'),
    mpatches.Patch(facecolor=FAMILY_COLORS["Qwen"], label='Qwen'),
    mpatches.Patch(facecolor=FAMILY_COLORS["DeepSeek"], label='DeepSeek'),
    mpatches.Patch(facecolor=FAMILY_COLORS["GLM"], label='GLM'),
    mpatches.Patch(facecolor=FAMILY_COLORS["Gemma"], label='Gemma'),
]
fig.legend(handles=legend_elements, loc='lower center', ncol=6,
          fontsize=11, facecolor='#1a1a2e', edgecolor='#555555',
          labelcolor='#cccccc', bbox_to_anchor=(0.5, 0.01))

plt.tight_layout(rect=[0, 0.04, 1, 0.95])
plt.savefig('D:/Dev/01_AI/AI_Benchmark/chart_nemotron_dashboard.png', dpi=180, bbox_inches='tight',
           facecolor=fig.get_facecolor())
print("[5/5] Executive dashboard saved")
plt.close()

print("\n" + "="*60)
print("ALL CHARTS GENERATED SUCCESSFULLY")
print("="*60)
print("Files saved to D:/Dev/01_AI/AI_Benchmark/:")
print("  1. chart_nemotron_speed_vs_accuracy.png")
print("  2. chart_nemotron_heatmap.png")
print("  3. chart_nemotron_radar.png")
print("  4. chart_nemotron_speed_bars.png")
print("  5. chart_nemotron_dashboard.png")
