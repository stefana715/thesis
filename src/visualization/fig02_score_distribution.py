"""
fig02_score_distribution.py

Figure 2 — Solar Potential Score Distribution.

Frequency histogram of solar_potential_score for all 18,855 urban-core
buildings.  Vertical lines mark the q33 and q66 class-boundary thresholds
with shaded low / medium / high regions.

Input
-----
data/processed/buildings_changsha_urban_core_solar_baseline.geojson

Output
------
figure/fig02_score_distribution.png  (300 dpi)
"""

from pathlib import Path
import logging

import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

OUTPUT_PATH = Path("figure/fig02_score_distribution.png")
INPUT_PATH = Path("data/processed/buildings_changsha_urban_core_solar_baseline.geojson")

Q33 = 41.797
Q66 = 45.513


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def main() -> None:
    setup_logging()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    logging.info("Loading buildings…")
    gdf = gpd.read_file(INPUT_PATH)
    scores = pd.to_numeric(gdf["solar_potential_score"], errors="coerce").dropna()

    logging.info("Total buildings with valid scores: %d", len(scores))

    # Recompute thresholds from data (should match verified values)
    q33_actual = scores.quantile(0.33)
    q66_actual = scores.quantile(0.66)
    logging.info("Actual q33=%.3f (expected %.3f)", q33_actual, Q33)
    logging.info("Actual q66=%.3f (expected %.3f)", q66_actual, Q66)

    fig, ax = plt.subplots(figsize=(9, 5))

    # Histogram
    n, bins, patches = ax.hist(
        scores, bins=60, color="#aec7e8", edgecolor="white",
        linewidth=0.4, zorder=2
    )

    # Shade regions: low / medium / high
    ymax = n.max() * 1.08
    ax.axvspan(scores.min(), q33_actual, alpha=0.18, color="#74c476",
               label="Low potential", zorder=1)
    ax.axvspan(q33_actual, q66_actual, alpha=0.18, color="#fd8d3c",
               label="Medium potential", zorder=1)
    ax.axvspan(q66_actual, scores.max(), alpha=0.18, color="#d6604d",
               label="High potential", zorder=1)

    # Threshold lines
    ax.axvline(q33_actual, color="#2ca02c", linewidth=1.8, linestyle="--", zorder=3)
    ax.axvline(q66_actual, color="#d62728", linewidth=1.8, linestyle="--", zorder=3)

    # Threshold labels
    ax.text(q33_actual + 0.15, ymax * 0.96,
            f"q33 = {q33_actual:.2f}",
            color="#2ca02c", fontsize=9, va="top")
    ax.text(q66_actual + 0.15, ymax * 0.96,
            f"q66 = {q66_actual:.2f}",
            color="#d62728", fontsize=9, va="top")

    # Region labels inside chart
    mid_low = (scores.min() + q33_actual) / 2
    mid_med = (q33_actual + q66_actual) / 2
    mid_high = (q66_actual + scores.max()) / 2
    label_y = ymax * 0.60
    for xpos, label, color in [
        (mid_low,  "Low",    "#2ca02c"),
        (mid_med,  "Medium", "#fd8d3c"),
        (mid_high, "High",   "#d62728"),
    ]:
        ax.text(xpos, label_y, label, ha="center", va="center",
                fontsize=11, color=color, fontweight="bold", alpha=0.75)

    ax.set_xlim(scores.min() - 1, scores.max() + 1)
    ax.set_ylim(0, ymax)
    ax.set_xlabel("Solar Potential Score (0–100)", fontsize=12)
    ax.set_ylabel("Number of Buildings", fontsize=12)
    ax.set_title(
        f"Distribution of Solar Potential Scores\n"
        f"(n = {len(scores):,} buildings, Changsha Urban Core)",
        fontsize=14,
    )
    ax.tick_params(labelsize=10)
    ax.grid(axis="y", linestyle="--", alpha=0.4, zorder=0)

    legend_patches = [
        mpatches.Patch(color="#74c476", alpha=0.5, label=f"Low  (score ≤ {q33_actual:.2f})"),
        mpatches.Patch(color="#fd8d3c", alpha=0.5,
                       label=f"Medium  ({q33_actual:.2f} < score ≤ {q66_actual:.2f})"),
        mpatches.Patch(color="#d6604d", alpha=0.5, label=f"High  (score > {q66_actual:.2f})"),
    ]
    ax.legend(handles=legend_patches, loc="upper left", fontsize=9,
              framealpha=0.9, edgecolor="grey")

    fig.tight_layout()
    fig.savefig(OUTPUT_PATH, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logging.info("Saved: %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()
