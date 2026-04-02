"""
fig05_high_potential_ratio.py

Figure 5 — High-Potential Ratio by 500 m Grid Cell (choropleth).

Spatial distribution of high_potential_ratio across the 500 m grid.
Higher values indicate grids with a larger share of high-potential
buildings, signalling priority areas for rooftop PV deployment.

Input
-----
data/processed/grid_changsha_urban_core_solar_baseline.geojson

Output
------
figure/fig05_high_potential_ratio.png  (300 dpi)
"""

from pathlib import Path
import logging

import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.cm import ScalarMappable
from matplotlib.colors import Normalize

OUTPUT_PATH = Path("figure/fig05_high_potential_ratio.png")
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

    grid_p["building_count"] = pd.to_numeric(
        grid_p["building_count"], errors="coerce"
    ).fillna(0)
    grid_p["high_potential_ratio"] = pd.to_numeric(
        grid_p["high_potential_ratio"], errors="coerce"
    )

    empty    = grid_p[grid_p["building_count"] == 0]
    occupied = grid_p[grid_p["building_count"] > 0].copy()

    logging.info(
        "Occupied grids: %d  |  HP ratio range: %.3f – %.3f",
        len(occupied),
        occupied["high_potential_ratio"].min(),
        occupied["high_potential_ratio"].max(),
    )

    fig, ax = plt.subplots(figsize=(10, 9))

    if not empty.empty:
        empty.plot(ax=ax, color="#f0f0f0", edgecolor="#cccccc",
                   linewidth=0.3, zorder=1)

    occupied.plot(
        column="high_potential_ratio",
        ax=ax,
        cmap="YlOrRd",
        vmin=0,
        vmax=1,
        edgecolor="#aaaaaa",
        linewidth=0.3,
        legend=False,
        zorder=2,
    )

    norm = Normalize(vmin=0, vmax=1)
    sm = ScalarMappable(cmap="YlOrRd", norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.02, shrink=0.7)
    cbar.set_label("High-Potential Building Ratio (0–1)", fontsize=10)
    cbar.ax.tick_params(labelsize=9)

    add_north_arrow(ax)
    add_scale_bar(ax, grid_p, bar_km=5)

    ax.set_title(
        "High-Potential Building Ratio by 500 m Grid Cell\n(Changsha Urban Core)",
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
