"""Build the Sapphire intelligence stack architecture diagram as PNG.

Style matches the deck: Midnight Executive palette (deep navy + sapphire blue + ice).
Output: /tmp/sapphire-deck-build/architecture.png at 1600x900 (16:9 friendly).
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

# Palette (from web/acquirer/assets/styles.css)
BG = "#0b1220"
BG_CARD = "#14213d"
BG_ELEV = "#111a2e"
FG = "#e6ecff"
FG_MUTED = "#aab4d4"
ACCENT = "#6da5ff"
ACCENT_2 = "#8edcff"
LINE = "#2a3a5e"


def draw_box(
    ax,
    x,
    y,
    w,
    h,
    label,
    sublabel=None,
    fill=BG_CARD,
    edge=LINE,
    label_color=FG,
    sub_color=FG_MUTED,
    fontsize=10,
    sub_fontsize=8,
    radius=0.04,
):
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.005,rounding_size={radius}",
        linewidth=1.2,
        edgecolor=edge,
        facecolor=fill,
    )
    ax.add_patch(box)
    if sublabel:
        ax.text(
            x + w / 2,
            y + h * 0.62,
            label,
            ha="center",
            va="center",
            fontsize=fontsize,
            color=label_color,
            weight="bold",
        )
        ax.text(
            x + w / 2,
            y + h * 0.30,
            sublabel,
            ha="center",
            va="center",
            fontsize=sub_fontsize,
            color=sub_color,
        )
    else:
        ax.text(
            x + w / 2,
            y + h / 2,
            label,
            ha="center",
            va="center",
            fontsize=fontsize,
            color=label_color,
            weight="bold",
        )


def draw_arrow(ax, x1, y1, x2, y2, color=ACCENT, width=1.2, style="-|>"):
    arrow = FancyArrowPatch(
        (x1, y1),
        (x2, y2),
        arrowstyle=style,
        mutation_scale=12,
        color=color,
        linewidth=width,
        alpha=0.85,
    )
    ax.add_patch(arrow)


def main():
    out_dir = Path(os.environ.get("OUT_DIR", "/tmp/sapphire-deck-build"))
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / "architecture.png"

    fig, ax = plt.subplots(figsize=(16, 9), dpi=140)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 16)
    ax.set_ylim(0.7, 9.1)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    # No internal title — the slide owns the title. Section column labels only.
    ax.text(
        2.0,
        8.5,
        "SIGNAL SOURCES",
        ha="center",
        va="center",
        fontsize=10,
        color=ACCENT_2,
        weight="bold",
    )
    ax.text(
        7.0,
        8.5,
        "CORRELATION + GOVERNANCE",
        ha="center",
        va="center",
        fontsize=10,
        color=ACCENT_2,
        weight="bold",
    )
    ax.text(
        13.8,
        8.5,
        "GOVERNED OUTPUTS",
        ha="center",
        va="center",
        fontsize=10,
        color=ACCENT_2,
        weight="bold",
    )

    # Section underlines
    for cx in (2.0, 7.0, 13.8):
        ax.plot([cx - 1.5, cx + 1.5], [8.25, 8.25], color=LINE, lw=1)

    # ---- Column 1: Signal sources (left) ----
    sources = [
        ("TradingView", "Pine strategies / webhooks"),
        ("Telegram intel", "Curated channel reader"),
        ("Hyperliquid", "Public microstructure feed"),
        ("Threat intel", "CISA KEV, NVD, MITRE"),
        ("On-chain", "Glassnode, Santiment, ETH/SOL"),
        ("Macro / Reg", "Fed, SEC, CFTC, Treasury"),
        ("Counterparty", "Public top-trader signals"),
    ]
    src_y_top = 7.6
    src_h = 0.7
    src_gap = 0.18
    src_x = 0.4
    src_w = 3.2
    for i, (name, sub) in enumerate(sources):
        y = src_y_top - i * (src_h + src_gap)
        draw_box(ax, src_x, y, src_w, src_h, name, sub, fontsize=11, sub_fontsize=8.5)

    # ---- Column 2: Correlator (middle) ----
    # Event bus
    draw_box(
        ax,
        4.6,
        7.0,
        4.8,
        0.85,
        "Event Bus",
        "Redis Streams + JSONL fallback",
        fill=BG_ELEV,
        fontsize=12,
        sub_fontsize=9,
    )

    # Correlator
    draw_box(
        ax,
        4.6,
        5.6,
        4.8,
        1.05,
        "Signal Correlator",
        "edge_score · consensus · corroborated_by",
        fill=BG_CARD,
        edge=ACCENT,
        fontsize=12,
        sub_fontsize=9,
    )

    # Narrative synthesis
    draw_box(
        ax,
        4.6,
        4.15,
        4.8,
        1.05,
        "Narrative Synthesis",
        "Bounded LLM thesis · invalidators · rubric gate",
        fill=BG_CARD,
        edge=ACCENT,
        fontsize=12,
        sub_fontsize=9,
    )

    # Risk Kernel + Provenance
    draw_box(
        ax,
        4.6,
        2.7,
        2.3,
        1.05,
        "Risk Kernel",
        "DecisionEnvelope → RiskVerdict\nfail-closed",
        fill=BG_CARD,
        edge=ACCENT_2,
        fontsize=11,
        sub_fontsize=8,
    )
    draw_box(
        ax,
        7.1,
        2.7,
        2.3,
        1.05,
        "Provenance",
        "envelope.json sidecar\nSHA-256 sources",
        fill=BG_CARD,
        edge=ACCENT_2,
        fontsize=11,
        sub_fontsize=8,
    )

    # Confirmation firewall
    draw_box(
        ax,
        4.6,
        1.25,
        4.8,
        1.05,
        "Confirmation Firewall + Kill Switches",
        "2-phase commit · operator confirm · drawdown halt",
        fill=BG_ELEV,
        edge=ACCENT_2,
        fontsize=11,
        sub_fontsize=9,
    )

    # ---- Column 3: Outputs (right) ----
    outputs = [
        ("Dashboard", "32 pages · auth gated"),
        ("Foundry sync", "13 ontology types · idempotent"),
        ("Telegram digest", "Read-only operator console"),
        ("Paper trading", "$100K paper portfolio"),
        ("Order draft", "Manual confirm · $5 → $50 → $500"),
        ("Content engine", "Drafts · approval gate"),
    ]
    out_y_top = 7.5
    out_h = 0.85
    out_gap = 0.21
    out_x = 11.9
    out_w = 3.8
    for i, (name, sub) in enumerate(outputs):
        y = out_y_top - i * (out_h + out_gap)
        draw_box(ax, out_x, y, out_w, out_h, name, sub, fontsize=11, sub_fontsize=8.5)

    # Arrows: sources → event bus
    for i in range(len(sources)):
        y = src_y_top + src_h / 2 - i * (src_h + src_gap)
        draw_arrow(ax, src_x + src_w + 0.05, y, 4.55, 7.4, color=ACCENT, width=0.8)

    # Event bus → correlator
    draw_arrow(ax, 7.0, 7.0, 7.0, 6.65, color=ACCENT_2, width=1.5)
    # correlator → narrative
    draw_arrow(ax, 7.0, 5.6, 7.0, 5.2, color=ACCENT_2, width=1.5)
    # narrative → risk kernel + provenance
    draw_arrow(ax, 6.0, 4.15, 5.7, 3.75, color=ACCENT, width=1.0)
    draw_arrow(ax, 8.0, 4.15, 8.3, 3.75, color=ACCENT, width=1.0)
    # risk + provenance → confirmation firewall
    draw_arrow(ax, 5.7, 2.7, 6.0, 2.3, color=ACCENT, width=1.0)
    draw_arrow(ax, 8.3, 2.7, 8.0, 2.3, color=ACCENT, width=1.0)

    # Confirmation firewall → outputs (single fan)
    for i in range(len(outputs)):
        y = out_y_top + out_h / 2 - i * (out_h + out_gap)
        draw_arrow(ax, 9.45, 1.78, out_x - 0.05, y, color=ACCENT, width=0.8)

    plt.tight_layout()
    plt.savefig(
        output_path, dpi=140, facecolor=BG, edgecolor="none", bbox_inches="tight", pad_inches=0.15
    )
    print(f"WROTE {output_path}")


if __name__ == "__main__":
    main()
