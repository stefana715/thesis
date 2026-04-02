"""
fig01_study_area.py

Figure 1 — Study Area Map.

Displays the full Changsha municipal boundary (raw study area) with the
extracted dense urban core overlay.  Includes a north arrow, scale bar,
and legend.

Inputs
------
data/raw/study_area_changsha.geojson           full municipal boundary
data/processed/study_area_changsha_urban_core.geojson  urban-core polygon

Output
------
figure/fig01_study_area.png  (300 dpi)
"""

from pathlib import Path
import logging

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrow
import matplotlib.patheffects as pe
import numpy as np

OUTPUT_PATH = Path("figure/fig01_study_area.png")
RAW_STUDY_AREA = Path("data/raw/study_area_changsha.geojson")
URBAN_CORE_PATH = Path("data/processed/study_area_changsha_urban_core.geojson")
BUILDINGS_PATH = Path("data/processed/buildings_changsha_urban_core.geojson")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def add_north_arrow(ax, x=0.93, y=0.92, size=0.07):
    """Add a simple north arrow in axes-fraction coordinates."""
    ax.annotate(
        "",
        xy=(x, y + size * 0.6),
        xytext=(x, y),
        xycoords="axes fraction",
        textcoords="axes fraction",
        arrowprops=dict(arrowstyle="-|>", color="black", lw=1.5),
    )
    ax.text(
        x, y - 0.01, "N",
        transform=ax.transAxes,
        ha="center", va="top",
        fontsize=11, fontweight="bold",
    )


def add_scale_bar(ax, gdf_proj, bar_km=10, x0_frac=0.07, y0_frac=0.06):
    """
    Draw a simple scale bar using projected coordinates.
    bar_km : length of the bar in kilometres.
    """
    bounds = gdf_proj.total_bounds  # minx, miny, maxx, maxy  (metres)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]

    bar_m = bar_km * 1000
    x0 = bounds[0] + x0_frac * width
    y0 = bounds[1] + y0_frac * height

    ax.plot([x0, x0 + bar_m], [y0, y0], color="black", linewidth=2.5)
    ax.plot([x0, x0], [y0 - height * 0.005, y0 + height * 0.005],
            color="black", linewidth=1.5)
    ax.plot([x0 + bar_m, x0 + bar_m],
            [y0 - height * 0.005, y0 + height * 0.005],
            color="black", linewidth=1.5)
    ax.text(
        x0 + bar_m / 2, y0 - height * 0.02,
        f"{bar_km} km",
        ha="center", va="top", fontsize=10,
    )


def main() -> None:
    setup_logging()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    logging.info("Loading datasets…")
    raw_area = gpd.read_file(RAW_STUDY_AREA)
    urban_core = gpd.read_file(URBAN_CORE_PATH)

    # Optional: building centroids for context
    buildings_available = BUILDINGS_PATH.exists()
    if buildings_available:
        buildings = gpd.read_file(BUILDINGS_PATH)

    # Project everything to the same metric CRS
    utm_crs = raw_area.estimate_utm_crs()
    raw_area_p = raw_area.to_crs(utm_crs)
    urban_core_p = urban_core.to_crs(utm_crs)

    fig, ax = plt.subplots(figsize=(9, 9))

    # 1. Full municipal boundary (light fill + border)
    raw_area_p.plot(
        ax=ax,
        color="#d0e8f0",
        edgecolor="#555555",
        linewidth=1.2,
        label="Changsha Municipality",
        zorder=1,
    )

    # 2. Urban core overlay
    urban_core_p.plot(
        ax=ax,
        color="#f4a582",
        edgecolor="#d6604d",
        linewidth=1.5,
        alpha=0.75,
        label="Urban Core Study Area",
        zorder=2,
    )

    # 3. Building footprints (very light, context only)
    if buildings_available:
        buildings_p = buildings.to_crs(utm_crs)
        buildings_p.plot(
            ax=ax,
            color="#636363",
            linewidth=0,
            alpha=0.35,
            label="Buildings (OSM)",
            zorder=3,
        )

    # Decorations
    add_north_arrow(ax)
    add_scale_bar(ax, raw_area_p, bar_km=10)

    ax.set_title(
        "Study Area: Changsha Urban Core\n(Hunan Province, China)",
        fontsize=14,
        pad=10,
    )
    ax.set_axis_off()

    legend_patches = [
        mpatches.Patch(color="#d0e8f0", edgecolor="#555555",
                       label="Changsha Municipality"),
        mpatches.Patch(color="#f4a582", edgecolor="#d6604d",
                       label="Urban Core Study Area"),
    ]
    if buildings_available:
        legend_patches.append(
            mpatches.Patch(color="#636363", alpha=0.6, label="OSM Buildings")
        )
    ax.legend(handles=legend_patches, loc="lower right", fontsize=10,
              framealpha=0.9, edgecolor="grey")

    plt.tight_layout()
    fig.savefig(OUTPUT_PATH, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logging.info("Saved: %s", OUTPUT_PATH)


if __name__ == "__main__":
    main()
