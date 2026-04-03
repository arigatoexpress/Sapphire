"""
Kadima Digital Laboratories - Publication Visualizations
=========================================================
Generates LinkedIn-ready charts from benchmark results.
Clean, professional design with proper branding.
"""

import glob
import json
import os
import sys

import matplotlib

matplotlib.use('Agg')
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec

# ── Kadima Brand Colors ──────────────────────────────────────────────────

COLORS = {
    "bg":           "#0D1117",
    "card_bg":      "#161B22",
    "text":         "#E6EDF3",
    "text_dim":     "#8B949E",
    "accent":       "#58A6FF",
    "accent2":      "#3FB950",
    "accent3":      "#D2A8FF",
    "accent4":      "#F0883E",
    "accent5":      "#FF7B72",
    "grid":         "#21262D",
    "border":       "#30363D",
}

FAMILY_COLORS = {
    "NVIDIA":     "#76B900",   # NVIDIA green
    "Google":     "#4285F4",   # Google blue
    "Meta":       "#0668E1",   # Meta blue
    "Microsoft":  "#00BCF2",   # Microsoft cyan
    "IBM":        "#BE95FF",   # IBM purple
    "Alibaba":    "#FF6A00",   # Alibaba orange
    "DeepSeek":   "#8B5CF6",   # Purple
    "Zhipu":      "#EF4444",   # Red
    # Legacy mappings
    "NVIDIA Nemotron":  "#76B900",
    "Alibaba Qwen":     "#FF6A00",
    "Microsoft Phi":    "#00BCF2",
    "Zhipu GLM":        "#EF4444",
}

FAMILY_MARKERS = {
    "NVIDIA":     "D",
    "Google":     "o",
    "Meta":       "^",
    "Microsoft":  "s",
    "IBM":        "P",
    "Alibaba":    "h",
    "DeepSeek":   "v",
    "Zhipu":      "X",
    "NVIDIA Nemotron":  "D",
    "Alibaba Qwen":     "h",
    "Microsoft Phi":    "s",
    "Zhipu GLM":        "X",
}


def load_latest_results(directory="D:/Dev/01_AI/AI_Benchmark"):
    """Load the most recent kadima_benchmark results file."""
    pattern = os.path.join(directory, "kadima_benchmark_*.json")
    files = sorted(glob.glob(pattern), reverse=True)
    if not files:
        print("ERROR: No kadima_benchmark_*.json files found!")
        sys.exit(1)
    print(f"Loading: {files[0]}")
    with open(files[0], 'r', encoding='utf-8') as f:
        return json.load(f), files[0]


def setup_style():
    """Configure matplotlib for dark publication style."""
    plt.rcParams.update({
        'figure.facecolor': COLORS["bg"],
        'axes.facecolor': COLORS["card_bg"],
        'axes.edgecolor': COLORS["border"],
        'axes.labelcolor': COLORS["text"],
        'text.color': COLORS["text"],
        'xtick.color': COLORS["text_dim"],
        'ytick.color': COLORS["text_dim"],
        'grid.color': COLORS["grid"],
        'grid.alpha': 0.5,
        'font.family': 'sans-serif',
        'font.sans-serif': ['Segoe UI', 'Arial', 'Helvetica', 'DejaVu Sans'],
        'font.size': 11,
        'axes.titlesize': 14,
        'axes.labelsize': 12,
    })


def add_branding(fig, hardware):
    """Add Kadima Digital Laboratories branding to figure."""
    fig.text(0.02, 0.01,
             f"Kadima Digital Laboratories  |  {hardware['gpu']}  |  {hardware['cpu']}  |  {hardware['ram']} DDR5",
             fontsize=8, color=COLORS["text_dim"], alpha=0.7,
             fontstyle='italic')
    fig.text(0.98, 0.01,
             f"Inference: {hardware['inference_engine']}  |  {hardware['os']}",
             fontsize=8, color=COLORS["text_dim"], alpha=0.7,
             ha='right', fontstyle='italic')


def chart1_leaderboard(data, hardware, output_dir):
    """Horizontal bar chart: Overall ranking by accuracy + speed."""
    results = data["results"]
    setup_style()

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 10), gridspec_kw={'width_ratios': [1.2, 1]})
    fig.suptitle("Local LLM Benchmark — Overall Leaderboard",
                 fontsize=20, fontweight='bold', color=COLORS["text"], y=0.96)
    fig.text(0.5, 0.925,
             f"13 Models  |  7 Tests Each  |  GPU-Isolated  |  {data['metadata']['date'][:10]}",
             fontsize=11, color=COLORS["text_dim"], ha='center')

    # Left: Accuracy bars
    labels = [r["label"] for r in results]
    accuracies = [r["accuracy_pct"] for r in results]
    families = [r["family"] for r in results]
    bar_colors = [FAMILY_COLORS.get(f, COLORS["accent"]) for f in families]

    y_pos = np.arange(len(labels))
    bars = ax1.barh(y_pos, accuracies, color=bar_colors, alpha=0.85, height=0.7, edgecolor='none')

    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(labels, fontsize=10)
    ax1.set_xlabel("Accuracy (%)", fontsize=12)
    ax1.set_title("Accuracy (% Tests Passed)", fontsize=14, fontweight='bold', pad=15)
    ax1.set_xlim(0, 110)
    ax1.invert_yaxis()
    ax1.grid(axis='x', alpha=0.3)

    for i, (bar, acc) in enumerate(zip(bars, accuracies)):
        ax1.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height()/2,
                f"{acc:.0f}%", va='center', fontsize=10, fontweight='bold',
                color=COLORS["text"])

    # Right: Speed bars
    speeds = [r["avg_tokens_per_second"] for r in results]
    bars2 = ax2.barh(y_pos, speeds, color=bar_colors, alpha=0.85, height=0.7, edgecolor='none')

    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(labels, fontsize=10)
    ax2.set_xlabel("Tokens/Second", fontsize=12)
    ax2.set_title("Inference Speed (tokens/s)", fontsize=14, fontweight='bold', pad=15)
    ax2.invert_yaxis()
    ax2.grid(axis='x', alpha=0.3)

    for i, (bar, spd) in enumerate(zip(bars2, speeds)):
        ax2.text(bar.get_width() + 1, bar.get_y() + bar.get_height()/2,
                f"{spd:.0f}", va='center', fontsize=10, fontweight='bold',
                color=COLORS["text"])

    # Legend
    handles = [mpatches.Patch(color=c, label=f) for f, c in FAMILY_COLORS.items()]
    fig.legend(handles=handles, loc='upper center', ncol=len(FAMILY_COLORS),
              bbox_to_anchor=(0.5, 0.905), fontsize=10, framealpha=0.3,
              edgecolor=COLORS["border"])

    add_branding(fig, hardware)
    plt.tight_layout(rect=[0, 0.03, 1, 0.89])
    path = os.path.join(output_dir, "kadima_1_leaderboard.png")
    fig.savefig(path, dpi=200, bbox_inches='tight', facecolor=COLORS["bg"])
    plt.close()
    print(f"  Saved: {path}")


def chart2_scatter(data, hardware, output_dir):
    """Scatter plot: Speed vs Accuracy — fixed label placement using adjustText."""
    results = data["results"]
    setup_style()

    fig, ax = plt.subplots(figsize=(16, 10))
    fig.suptitle("Speed vs. Accuracy — Efficiency Frontier",
                 fontsize=20, fontweight='bold', color=COLORS["text"], y=0.96)
    fig.text(0.5, 0.92,
             "Top-right = best (fast AND accurate)  |  Bubble size = model disk size",
             fontsize=11, color=COLORS["text_dim"], ha='center')

    for r in results:
        family = r["family"]
        color = FAMILY_COLORS.get(family, COLORS["accent"])
        marker = FAMILY_MARKERS.get(family, "o")
        size_gb = r.get("model_size_gb", 3)
        bubble = max(size_gb * 60, 100)

        ax.scatter(r["avg_tokens_per_second"], r["accuracy_pct"],
                  s=bubble, c=color, marker=marker, alpha=0.85,
                  edgecolors='white', linewidth=1.5, zorder=5)

    # Smart label placement: manually offset overlapping labels
    placed = []
    for r in results:
        x, y = r["avg_tokens_per_second"], r["accuracy_pct"]
        label = r["label"]
        ox, oy = 10, 0  # default offset

        # Check for nearby labels and adjust
        for px, py, _, _ in placed:
            if abs(x - px) < 30 and abs(y - py) < 8:
                oy -= 12  # push down

        # Special adjustments for known overlaps
        if "Qwen" in label or "Alibaba" in r.get("family", ""):
            ox, oy = -10, -15
            ha = 'right'
        elif "Phi-4 Mini" in label:
            ox, oy = -10, 8
            ha = 'right'
        elif "Mini 4B" in label:
            ox, oy = 10, -12
            ha = 'left'
        else:
            ha = 'left'

        ax.annotate(label, (x, y),
                   xytext=(ox, oy), textcoords='offset points',
                   fontsize=9, color=COLORS["text"], alpha=0.95,
                   ha=ha, fontweight='bold',
                   arrowprops=dict(arrowstyle='-', color=COLORS["text_dim"],
                                  alpha=0.3, lw=0.5) if abs(ox) > 8 or abs(oy) > 8 else None)
        placed.append((x, y, ox, oy))

    ax.set_xlabel("Inference Speed (tokens/second)", fontsize=13, labelpad=10)
    ax.set_ylabel("Accuracy (% tests passed)", fontsize=13, labelpad=10)
    ax.grid(True, alpha=0.3)
    ax.set_xlim(-10, max(r["avg_tokens_per_second"] for r in results) + 30)

    # Quadrant lines
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    mid_x = (xlim[0] + xlim[1]) / 2
    mid_y = (ylim[0] + ylim[1]) / 2
    ax.axhline(y=mid_y, color=COLORS["grid"], linestyle='--', alpha=0.3)
    ax.axvline(x=mid_x, color=COLORS["grid"], linestyle='--', alpha=0.3)
    ax.text(xlim[1] * 0.95, ylim[1] * 0.98, "IDEAL", fontsize=12,
            color=COLORS["accent2"], alpha=0.4, ha='right', va='top', fontweight='bold')
    ax.text(xlim[0] + 5, ylim[0] + 2, "AVOID", fontsize=12,
            color=COLORS["accent5"], alpha=0.4, ha='left', va='bottom', fontweight='bold')

    # Legend: only families present in data
    seen = set()
    handles = []
    for r in results:
        f = r["family"]
        if f not in seen:
            seen.add(f)
            handles.append(mpatches.Patch(color=FAMILY_COLORS.get(f, COLORS["accent"]), label=f))
    ax.legend(handles=handles, loc='lower right', fontsize=10,
             framealpha=0.3, edgecolor=COLORS["border"])

    add_branding(fig, hardware)
    plt.tight_layout(rect=[0, 0.03, 1, 0.90])
    path = os.path.join(output_dir, "kadima_2_efficiency.png")
    fig.savefig(path, dpi=200, bbox_inches='tight', facecolor=COLORS["bg"])
    plt.close()
    print(f"  Saved: {path}")


def chart3_category_heatmap(data, hardware, output_dir):
    """Heatmap: Model x Test Category performance."""
    results = data["results"]
    setup_style()

    # Build matrix
    models = [r["label"] for r in results]
    categories = [t["category"] for t in results[0]["test_results"]] if results[0].get("test_results") else []

    if not categories:
        print("  [SKIP] No test_results detail for heatmap")
        return

    matrix = []
    for r in results:
        row = []
        for tr in r.get("test_results", []):
            row.append(1 if tr["passed"] else 0)
        matrix.append(row)

    matrix = np.array(matrix)

    fig, ax = plt.subplots(figsize=(14, 10))
    fig.suptitle("Test Category Breakdown — Pass/Fail Matrix",
                 fontsize=20, fontweight='bold', color=COLORS["text"], y=0.96)
    fig.text(0.5, 0.92,
             "Green = Pass  |  Red = Fail  |  Each model tested in GPU isolation",
             fontsize=11, color=COLORS["text_dim"], ha='center')

    # Custom colormap: red for fail, green for pass
    from matplotlib.colors import ListedColormap
    cmap = ListedColormap(['#FF4444', '#3FB950'])

    im = ax.imshow(matrix, cmap=cmap, aspect='auto', vmin=0, vmax=1)

    ax.set_xticks(np.arange(len(categories)))
    ax.set_yticks(np.arange(len(models)))
    ax.set_xticklabels(categories, rotation=30, ha='right', fontsize=10)
    ax.set_yticklabels(models, fontsize=10)

    # Add text annotations
    for i in range(len(models)):
        for j in range(len(categories)):
            text = "PASS" if matrix[i, j] == 1 else "FAIL"
            color = "white" if matrix[i, j] == 0 else "#0D1117"
            ax.text(j, i, text, ha="center", va="center",
                   fontsize=9, fontweight='bold', color=color)

    # Add accuracy column on right
    for i, r in enumerate(results):
        ax.text(len(categories) + 0.3, i, f"{r['accuracy_pct']:.0f}%",
               ha='left', va='center', fontsize=11, fontweight='bold',
               color=COLORS["accent2"] if r['accuracy_pct'] >= 70 else COLORS["accent5"])

    ax.set_title("", pad=5)
    ax.grid(False)

    # Add cell borders
    for i in range(len(models) + 1):
        ax.axhline(i - 0.5, color=COLORS["bg"], linewidth=2)
    for j in range(len(categories) + 1):
        ax.axvline(j - 0.5, color=COLORS["bg"], linewidth=2)

    add_branding(fig, hardware)
    plt.tight_layout(rect=[0, 0.03, 1, 0.90])
    path = os.path.join(output_dir, "kadima_3_heatmap.png")
    fig.savefig(path, dpi=200, bbox_inches='tight', facecolor=COLORS["bg"])
    plt.close()
    print(f"  Saved: {path}")


def chart4_nemotron_and_size(data, hardware, output_dir):
    """Two panels: Left = Nemotron quantization comparison, Right = all models size vs perf."""
    results = data["results"]
    setup_style()

    fig = plt.figure(figsize=(20, 10))
    fig.suptitle("Nemotron Quantization Analysis & Model Size Efficiency",
                 fontsize=20, fontweight='bold', color=COLORS["text"], y=0.96)

    gs = GridSpec(1, 2, figure=fig, width_ratios=[1, 1.2], wspace=0.3)

    # LEFT: Nemotron variants comparison
    ax1 = fig.add_subplot(gs[0])
    nemotron = [r for r in results if "NVIDIA" in r.get("family", "") or "Nemotron" in r.get("family", "")]
    nemotron = sorted(nemotron, key=lambda x: -x["avg_tokens_per_second"])

    if nemotron:
        labels = [r["label"] for r in nemotron]
        acc = [r["accuracy_pct"] for r in nemotron]
        spd = [r["avg_tokens_per_second"] for r in nemotron]
        sizes = [r.get("model_size_gb", 3) for r in nemotron]

        x = np.arange(len(labels))
        width = 0.3

        bars1 = ax1.bar(x - width, acc, width, label='Accuracy %',
                       color=FAMILY_COLORS.get("NVIDIA", "#76B900"), alpha=0.85)
        bars2 = ax1.bar(x, spd, width, label='Tokens/s',
                       color=COLORS["accent"], alpha=0.85)
        bars3 = ax1.bar(x + width, [s * 10 for s in sizes], width, label='Size (GB x10)',
                       color=COLORS["accent4"], alpha=0.7)

        ax1.set_xticks(x)
        ax1.set_xticklabels(labels, rotation=20, ha='right', fontsize=9)
        ax1.set_ylabel("Value", fontsize=11)
        ax1.set_title("NVIDIA Nemotron Family\nQuantization Impact", fontsize=13, pad=15, fontweight='bold')
        ax1.grid(axis='y', alpha=0.3)
        ax1.legend(fontsize=9, framealpha=0.3, loc='upper right')

        # Value labels
        for bar, val in zip(bars1, acc):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                    f"{val:.0f}%", ha='center', fontsize=8, fontweight='bold',
                    color=FAMILY_COLORS.get("NVIDIA", "#76B900"))
        for bar, val in zip(bars2, spd):
            ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 2,
                    f"{val:.0f}", ha='center', fontsize=8, fontweight='bold',
                    color=COLORS["accent"])

    # RIGHT: All models — size vs accuracy with speed as bubble
    ax2 = fig.add_subplot(gs[1])
    all_sizes = [r["model_size_gb"] for r in results]
    all_accs = [r["accuracy_pct"] for r in results]
    all_speeds = [r["avg_tokens_per_second"] for r in results]
    all_families = [r["family"] for r in results]
    all_labels = [r["label"] for r in results]
    all_colors = [FAMILY_COLORS.get(f, COLORS["accent"]) for f in all_families]

    max_spd = max(all_speeds) if all_speeds else 1
    bubble_sizes = [max(s / max_spd * 600, 60) for s in all_speeds]

    for i in range(len(results)):
        ax2.scatter(all_sizes[i], all_accs[i], s=bubble_sizes[i], c=all_colors[i],
                   alpha=0.85, edgecolors='white', linewidth=1.2, zorder=5)
        ax2.annotate(f"{all_labels[i]}\n{all_speeds[i]:.0f} t/s",
                    (all_sizes[i], all_accs[i]),
                    xytext=(8, -3), textcoords='offset points',
                    fontsize=7.5, color=COLORS["text"], alpha=0.9)

    ax2.set_xlabel("Model Size (GB)", fontsize=11, labelpad=8)
    ax2.set_ylabel("Accuracy (%)", fontsize=11, labelpad=8)
    ax2.set_title("All Models: Size vs. Accuracy\nBubble = inference speed", fontsize=13, pad=15, fontweight='bold')
    ax2.grid(True, alpha=0.3)
    ax2.set_ylim(30, 108)

    seen = set()
    handles = []
    for r in results:
        f = r["family"]
        if f not in seen:
            seen.add(f)
            handles.append(mpatches.Patch(color=FAMILY_COLORS.get(f, COLORS["accent"]), label=f))
    ax2.legend(handles=handles, loc='lower right', fontsize=9, framealpha=0.3)

    add_branding(fig, hardware)
    plt.tight_layout(rect=[0, 0.03, 1, 0.90])
    path = os.path.join(output_dir, "kadima_4_nemotron_and_size.png")
    fig.savefig(path, dpi=200, bbox_inches='tight', facecolor=COLORS["bg"])
    plt.close()
    print(f"  Saved: {path}")


def chart5_family_comparison(data, hardware, output_dir):
    """Radar/grouped chart: Best model from each family."""
    results = data["results"]
    setup_style()

    fig, ax = plt.subplots(figsize=(16, 9))
    fig.suptitle("Best-in-Family Comparison",
                 fontsize=20, fontweight='bold', color=COLORS["text"], y=0.96)
    fig.text(0.5, 0.92,
             "Top performer from each model family  |  Fair cross-vendor comparison",
             fontsize=11, color=COLORS["text_dim"], ha='center')

    # Get best from each family
    families = {}
    for r in results:
        fam = r["family"]
        if fam not in families or (r["accuracy_pct"], r["avg_tokens_per_second"]) > \
           (families[fam]["accuracy_pct"], families[fam]["avg_tokens_per_second"]):
            families[fam] = r

    best = sorted(families.values(), key=lambda x: (-x["accuracy_pct"], -x["avg_tokens_per_second"]))

    labels = [f"{r['label']}\n({r['family']})" for r in best]
    acc = [r["accuracy_pct"] for r in best]
    spd = [r["avg_tokens_per_second"] for r in best]
    avg_time = [r["avg_response_time"] for r in best]
    colors = [FAMILY_COLORS.get(r["family"], COLORS["accent"]) for r in best]

    x = np.arange(len(labels))
    width = 0.25

    bars1 = ax.bar(x - width, acc, width, color=colors, alpha=0.9, label='Accuracy (%)')
    bars2 = ax.bar(x, [s / max(spd) * 100 for s in spd], width,
                  color=colors, alpha=0.5, hatch='///', label='Speed (normalized %)')
    # Composite score: 60% accuracy + 40% speed (normalized)
    max_spd = max(spd) if spd else 1
    composite = [0.6 * a + 0.4 * (s / max_spd * 100) for a, s in zip(acc, spd)]
    bars3 = ax.bar(x + width, composite, width, color=colors, alpha=0.7,
                  edgecolor='white', linewidth=1.5, label='Composite Score')

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("Score (%)", fontsize=12)
    ax.set_ylim(0, 115)
    ax.grid(axis='y', alpha=0.3)
    ax.legend(loc='upper right', fontsize=10, framealpha=0.3)

    # Value labels on composite
    for bar, val in zip(bars3, composite):
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 1.5,
               f"{val:.0f}", ha='center', fontsize=10, fontweight='bold',
               color=COLORS["accent2"])

    add_branding(fig, hardware)
    plt.tight_layout(rect=[0, 0.03, 1, 0.90])
    path = os.path.join(output_dir, "kadima_5_family_comparison.png")
    fig.savefig(path, dpi=200, bbox_inches='tight', facecolor=COLORS["bg"])
    plt.close()
    print(f"  Saved: {path}")


def chart6_speed_by_category(data, hardware, output_dir):
    """Heatmap-style: tokens/s per model per category — clear speed comparison."""
    results = data["results"]
    setup_style()

    fig, ax = plt.subplots(figsize=(18, 10))
    fig.suptitle("Inference Speed by Test Category (tokens/second)",
                 fontsize=20, fontweight='bold', color=COLORS["text"], y=0.96)
    fig.text(0.5, 0.92,
             "Higher = faster  |  Color intensity = speed  |  Each model tested in GPU isolation",
             fontsize=11, color=COLORS["text_dim"], ha='center')

    if not results[0].get("test_results"):
        return

    models = [r["label"] for r in results]
    categories = [tr["category"] for tr in results[0]["test_results"]]

    # Build speed matrix
    matrix = []
    for r in results:
        row = [tr.get("tokens_per_second", 0) for tr in r.get("test_results", [])]
        matrix.append(row)
    matrix = np.array(matrix)

    # Heatmap
    im = ax.imshow(matrix, cmap='YlGn', aspect='auto', vmin=0)

    ax.set_xticks(np.arange(len(categories)))
    ax.set_yticks(np.arange(len(models)))
    ax.set_xticklabels(categories, rotation=30, ha='right', fontsize=10)
    ax.set_yticklabels(models, fontsize=10)

    # Annotate cells with speed values
    for i in range(len(models)):
        for j in range(len(categories)):
            val = matrix[i, j]
            color = "#0D1117" if val > 100 else COLORS["text"]
            ax.text(j, i, f"{val:.0f}", ha="center", va="center",
                   fontsize=9, fontweight='bold', color=color)

    # Add avg speed column label on right
    for i, r in enumerate(results):
        avg = r["avg_tokens_per_second"]
        color = COLORS["accent2"] if avg >= 100 else COLORS["accent"] if avg >= 50 else COLORS["accent5"]
        ax.text(len(categories) + 0.3, i, f"avg: {avg:.0f} t/s",
               ha='left', va='center', fontsize=10, fontweight='bold', color=color)

    ax.grid(False)
    # Cell borders
    for i in range(len(models) + 1):
        ax.axhline(i - 0.5, color=COLORS["bg"], linewidth=2)
    for j in range(len(categories) + 1):
        ax.axvline(j - 0.5, color=COLORS["bg"], linewidth=2)

    # Colorbar
    cbar = fig.colorbar(im, ax=ax, shrink=0.6, pad=0.12)
    cbar.set_label('Tokens/second', color=COLORS["text"], fontsize=10)
    cbar.ax.yaxis.set_tick_params(color=COLORS["text_dim"])
    plt.setp(plt.getp(cbar.ax.axes, 'yticklabels'), color=COLORS["text_dim"])

    add_branding(fig, hardware)
    plt.tight_layout(rect=[0, 0.03, 1, 0.90])
    path = os.path.join(output_dir, "kadima_6_speed_by_category.png")
    fig.savefig(path, dpi=200, bbox_inches='tight', facecolor=COLORS["bg"])
    plt.close()
    print(f"  Saved: {path}")


def main():
    data, filepath = load_latest_results()
    hardware = data["metadata"]["hardware"]
    output_dir = os.path.dirname(filepath)

    print(f"\n{'='*60}")
    print("  KADIMA DIGITAL LABORATORIES")
    print("  Generating Publication Visualizations")
    print(f"{'='*60}")
    print(f"  Source: {filepath}")
    print(f"  Models: {len(data['results'])}")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}\n")

    chart1_leaderboard(data, hardware, output_dir)
    chart2_scatter(data, hardware, output_dir)
    chart3_category_heatmap(data, hardware, output_dir)
    chart4_nemotron_and_size(data, hardware, output_dir)
    chart5_family_comparison(data, hardware, output_dir)
    chart6_speed_by_category(data, hardware, output_dir)

    print(f"\n{'='*60}")
    print("  All 6 charts generated!")
    print(f"  Location: {output_dir}/kadima_*.png")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
