"""
fig08_methodology_flowchart.py

Figure 8 — Methodology Flowchart.

Renders a clean linear flowchart illustrating the full pipeline:
    OSM Data → Height Proxy → Urban-Core Extraction → Building Scoring
    → q66 Classification → Grid Aggregation → Planning Metrics

Drawn entirely with matplotlib rectangles, arrows, and text — no
external diagram libraries required.

Output
------
figure/fig08_methodology_flowchart.png  (300 dpi)
"""

from pathlib import Path
import logging

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUTPUT_PATH = Path("figure/fig08_methodology_flowchart.png")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def draw_box(ax, cx, cy, width, height, text, subtitle="",
             facecolor="#aec7e8", edgecolor="#1f77b4", fontsize=11,
             subfontsize=9, radius=0.03):
    """Draw a rounded-corner box centred at (cx, cy)."""
    x = cx - width / 2
    y = cy - height / 2
    box = FancyBboxPatch(
        (x, y), width, height,
        boxstyle=f"round,pad=0.01,rounding_size={radius}",
        facecolor=facecolor,
        edgecolor=edgecolor,
        linewidth=1.5,
        zorder=2,
    )
    ax.add_patch(box)
    if subtitle:
        ax.text(cx, cy + height * 0.12, text,
                ha="center", va="center", fontsize=fontsize,
                fontweight="bold", zorder=3)
        ax.text(cx, cy - height * 0.20, subtitle,
                ha="center", va="center", fontsize=subfontsize,
                color="#444444", style="italic", zorder=3)
    else:
        ax.text(cx, cy, text,
                ha="center", va="center", fontsize=fontsize,
                fontweight="bold", zorder=3)


def draw_arrow(ax, x0, y0, x1, y1):
    """Draw a downward arrow between two boxes."""
    ax.annotate(
        "",
        xy=(x1, y1),
        xytext=(x0, y0),
        arrowprops=dict(
            arrowstyle="-|>",
            color="#333333",
            lw=1.5,
            mutation_scale=14,
        ),
        zorder=1,
    )


def draw_side_label(ax, cx, cy, text, fontsize=8.5, color="#555555"):
    ax.text(cx, cy, text, ha="left", va="center",
            fontsize=fontsize, color=color, style="italic")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

STEPS = [
    {
        "text":     "① OSM Building Data",
        "subtitle": "osmnx download · 33,374 raw buildings",
        "color":    "#c6dbef",
        "edge":     "#2171b5",
    },
    {
        "text":     "② Height Proxy Construction",
        "subtitle": "OSM tags · floor-count rules · default fallback",
        "color":    "#c7e9c0",
        "edge":     "#238b45",
    },
    {
        "text":     "③ Urban-Core Extraction",
        "subtitle": "Bounding-box filter → 18,855 buildings retained",
        "color":    "#c7e9c0",
        "edge":     "#238b45",
    },
    {
        "text":     "④ Building-Level Solar Scoring",
        "subtitle": "0.65 × area_score + 0.35 × height_score × category_mult × 100",
        "color":    "#fdd0a2",
        "edge":     "#d94801",
    },
    {
        "text":     "⑤ High-Potential Classification",
        "subtitle": "q66 threshold (score ≥ 45.51) → 6,411 high-potential buildings",
        "color":    "#fdd0a2",
        "edge":     "#d94801",
    },
    {
        "text":     "⑥ 500 m Grid Aggregation",
        "subtitle": "mean_score · high_potential_ratio · building_count per cell",
        "color":    "#dadaeb",
        "edge":     "#6a51a3",
    },
    {
        "text":     "⑦ Planning Metrics",
        "subtitle": "Deployable area · Annual kWh estimate · CO₂ reduction · Priority grids",
        "color":    "#fcbba1",
        "edge":     "#a50f15",
    },
]

BOX_W = 3.8
BOX_H = 0.62
GAP   = 0.32   # vertical gap between boxes
CX    = 2.4    # horizontal centre


def main() -> None:
    setup_logging()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    n = len(STEPS)
    total_h = n * BOX_H + (n - 1) * GAP
    fig_h = total_h + 1.4

    fig, ax = plt.subplots(figsize=(7, fig_h))

    # Y positions from top to bottom
    y_positions = [
        total_h + 0.5 - i * (BOX_H + GAP) - BOX_H / 2
        for i in range(n)
    ]

    for i, (step, cy) in enumerate(zip(STEPS, y_positions)):
        draw_box(
            ax, CX, cy, BOX_W, BOX_H,
            step["text"], step.get("subtitle", ""),
            facecolor=step["color"], edgecolor=step["edge"],
        )
        if i < n - 1:
            draw_arrow(ax, CX, cy - BOX_H / 2, CX, y_positions[i + 1] + BOX_H / 2)

    # Side labels for data types
    side_labels = [
        (0, "Input: OpenStreetMap"),
        (1, "Intermediate: GeoJSON"),
        (2, "Processed: GeoJSON"),
        (3, "Output: Score (0–100)"),
        (4, "Output: Class label"),
        (5, "Output: Grid GeoJSON"),
        (6, "Output: CSV summary"),
    ]
    for idx, label in side_labels:
        draw_side_label(ax, CX + BOX_W / 2 + 0.12, y_positions[idx], label)

    ax.set_xlim(0, 7.5)
    ax.set_ylim(-0.3, total_h + 1.0)
    ax.set_aspect("equal")
    ax.axis("off")

    ax.set_title(
        "Methodology Flowchart: Rapid Urban Rooftop Solar Screening\n"
        "(Low-Data, Open-Data Framework — Changsha Urban Core)",
        fontsize=13,
        pad=10,
    )

    fig.tight_layout()
    fig.savefig(OUTPUT_PATH, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logging.info("Saved: %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()
