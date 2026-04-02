"""
fig03_building_classification.py

Figure 3 — Spatial Distribution of Solar Potential Classes.

Map of the Changsha urban core with building footprints coloured by
solar_potential_class (low / medium / high).

Input
-----
data/processed/buildings_changsha_urban_core_solar_baseline.geojson

Output
------
figure/fig03_building_classification.png  (300 dpi)
"""

from pathlib import Path
import logging

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

OUTPUT_PATH = Path("figure/fig03_building_classification.png")
INPUT_PATH = Path("data/processed/buildings_changsha_urban_core_solar_baseline.geojson")

CLASS_COLORS = {
    "low":    "#74c476",   # green
    "medium": "#fd8d3c",   # orange
    "high":   "#d62728",   # red
}
CLASS_ORDER = ["low", "medium", "high"]


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def add_north_arrow(ax, x=0.96, y=0.94, size=0.06):
    ax.annotate(
        "",
        xy=(x, y + size * 0.6),
        xytext=(x, y),
        xycoords="axes fraction",
        textcoords="axes fraction",
        arrowprops=dict(arrowstyle="-|>", color="black", lw=1.5),
    )
    ax.text(x, y - 0.01, "N",
            transform=ax.transAxes,
            ha="center", va="top", fontsize=10, fontweight="bold")


def add_scale_bar(ax, gdf_proj, bar_km=2):
    bounds = gdf_proj.total_bounds
    width  = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    bar_m  = bar_km * 1000
    x0 = bounds[0] + 0.05 * width
    y0 = bounds[1] + 0.04 * height
    ax.plot([x0, x0 + bar_m], [y0, y0], color="black", linewidth=2.5)
    for xp in [x0, x0 + bar_m]:
        ax.plot([xp, xp], [y0 - height * 0.004, y0 + height * 0.004],
                color="black", linewidth=1.5)
    ax.text(x0 + bar_m / 2, y0 - height * 0.018,
            f"{bar_km} km", ha="center", va="top", fontsize=9)


def main() -> None:
    setup_logging()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    logging.info("Loading buildings…")
    gdf = gpd.read_file(INPUT_PATH)

    utm_crs = gdf.estimate_utm_crs()
    gdf_p = gdf.to_crs(utm_crs)

    fig, ax = plt.subplots(figsize=(10, 10))

    # Plot low → medium → high so high is rendered on top
    for cls in CLASS_ORDER:
        subset = gdf_p[gdf_p["solar_potential_class"] == cls]
        if subset.empty:
            continue
        subset.plot(
            ax=ax,
            color=CLASS_COLORS[cls],
            linewidth=0,
            alpha=0.75,
            zorder=CLASS_ORDER.index(cls) + 1,
        )
        logging.info("  %s: %d buildings", cls, len(subset))

    add_north_arrow(ax)
    add_scale_bar(ax, gdf_p, bar_km=2)

    ax.set_title(
        "Solar Potential Classification of Urban-Core Buildings\n"
        "(Changsha, 18,855 buildings)",
        fontsize=14,
        pad=10,
    )
    ax.set_axis_off()

    legend_patches = [
        mpatches.Patch(color=CLASS_COLORS[cls], label=f"{cls.capitalize()} potential")
        for cls in CLASS_ORDER
    ]
    ax.legend(handles=legend_patches, loc="lower right", fontsize=10,
              framealpha=0.9, edgecolor="grey", title="Solar Potential Class",
              title_fontsize=10)

    fig.tight_layout()
    fig.savefig(OUTPUT_PATH, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logging.info("Saved: %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()
