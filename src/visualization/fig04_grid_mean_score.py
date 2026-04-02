"""
fig04_grid_mean_score.py

Figure 4 — Grid Mean Solar Potential Score (choropleth).

500 m grid cells coloured by mean_score using a continuous YlOrRd colour
ramp.  Empty cells are shown in light grey.

Input
-----
data/processed/grid_changsha_urban_core_solar_baseline.geojson

Output
------
figure/fig04_grid_mean_score.png  (300 dpi)
"""

from pathlib import Path
import logging

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

OUTPUT_PATH = Path("figure/fig04_grid_mean_score.png")
GRID_PATH   = Path("data/processed/grid_changsha_urban_core_solar_baseline.geojson")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def add_north_arrow(ax, x=0.95, y=0.93, size=0.06):
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


def add_scale_bar(ax, gdf_proj, bar_km=5):
    bounds = gdf_proj.total_bounds
    width  = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    bar_m  = bar_km * 1000
    x0 = bounds[0] + 0.05 * width
    y0 = bounds[1] + 0.04 * height
    ax.plot([x0, x0 + bar_m], [y0, y0], color="black", linewidth=2.5)
    for xp in [x0, x0 + bar_m]:
        ax.plot([xp, xp], [y0 - height * 0.005, y0 + height * 0.005],
                color="black", linewidth=1.5)
    ax.text(x0 + bar_m / 2, y0 - height * 0.02,
            f"{bar_km} km", ha="center", va="top", fontsize=9)


def main() -> None:
    setup_logging()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    logging.info("Loading grid…")
    grid = gpd.read_file(GRID_PATH)

    utm_crs = grid.estimate_utm_crs()
    grid_p = grid.to_crs(utm_crs)

    empty  = grid_p[grid_p["building_count"].fillna(0) == 0]
    occupied = grid_p[grid_p["building_count"].fillna(0) > 0].copy()

    import pandas as pd
    occupied["mean_score"] = pd.to_numeric(occupied["mean_score"], errors="coerce")

    vmin = occupied["mean_score"].quantile(0.02)
    vmax = occupied["mean_score"].quantile(0.98)

    fig, ax = plt.subplots(figsize=(10, 9))

    # Empty cells (background)
    if not empty.empty:
        empty.plot(ax=ax, color="#f0f0f0", edgecolor="#cccccc",
                   linewidth=0.3, zorder=1)

    # Occupied cells with choropleth
    occupied.plot(
        column="mean_score",
        ax=ax,
        cmap="YlOrRd",
        vmin=vmin,
        vmax=vmax,
        edgecolor="#aaaaaa",
        linewidth=0.3,
        legend=False,
        zorder=2,
    )

    # Colour bar
    norm = Normalize(vmin=vmin, vmax=vmax)
    sm = ScalarMappable(cmap="YlOrRd", norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.02, shrink=0.7)
    cbar.set_label("Mean Solar Potential Score (0–100)", fontsize=10)
    cbar.ax.tick_params(labelsize=9)

    add_north_arrow(ax)
    add_scale_bar(ax, grid_p, bar_km=5)

    ax.set_title(
        "Mean Solar Potential Score by 500 m Grid Cell\n(Changsha Urban Core)",
        fontsize=14,
        pad=10,
    )
    ax.set_axis_off()

    fig.tight_layout()
    fig.savefig(OUTPUT_PATH, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logging.info("Saved: %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()
