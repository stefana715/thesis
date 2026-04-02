"""
grid_size_sensitivity.py

Re-run the 500 m grid aggregation pipeline at four grid sizes
(250 m / 500 m / 750 m / 1000 m) to assess how the choice of spatial
resolution affects key planning metrics.

Inputs
------
data/processed/buildings_changsha_urban_core_solar_baseline.geojson
    Buildings with pre-computed solar_potential_score and is_high_potential.

Outputs
-------
outputs/sensitivity/grid_size_comparison.csv
    One row per grid-size × statistic combination (summary table).
figure/fig06_grid_size_sensitivity.png
    Side-by-side box-plots for mean_solar_score and high_potential_ratio.
"""

from pathlib import Path
import logging

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from shapely.geometry import box


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
INPUT_PATH = Path("data/processed/buildings_changsha_urban_core_solar_baseline.geojson")
OUTPUT_CSV = Path("outputs/sensitivity/grid_size_comparison.csv")
OUTPUT_FIG = Path("figure/fig06_grid_size_sensitivity.png")

GRID_SIZES_M = [250, 500, 750, 1000]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def ensure_dirs() -> None:
    OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FIG.parent.mkdir(parents=True, exist_ok=True)


def make_grid(bounds, cell_size: float, crs) -> gpd.GeoDataFrame:
    """Create a regular rectangular grid over *bounds* with *cell_size* metres."""
    minx, miny, maxx, maxy = bounds
    xs = list(range(int(minx), int(maxx) + int(cell_size), int(cell_size)))
    ys = list(range(int(miny), int(maxy) + int(cell_size), int(cell_size)))
    cells = [
        box(x, y, x + cell_size, y + cell_size)
        for x in xs[:-1]
        for y in ys[:-1]
    ]
    return gpd.GeoDataFrame({"geometry": cells}, crs=crs)


def aggregate_at_grid_size(buildings_proj: gpd.GeoDataFrame, cell_size: int) -> dict:
    """
    Aggregate building-level metrics onto a grid of *cell_size* metres.

    Returns a dict with summary statistics for occupied grid cells.
    """
    grid = make_grid(buildings_proj.total_bounds, cell_size, buildings_proj.crs)
    grid["grid_id"] = grid.index

    centroids = buildings_proj.copy()
    centroids["geometry"] = centroids.geometry.centroid

    joined = gpd.sjoin(centroids, grid, how="left", predicate="within")

    agg = joined.groupby("grid_id").agg(
        building_count=("solar_potential_score", "count"),
        mean_score=("solar_potential_score", "mean"),
        high_potential_count=("is_high_potential", "sum"),
    ).reset_index()

    agg["high_potential_ratio"] = agg["high_potential_count"] / agg["building_count"]

    occupied = agg[agg["building_count"] > 0].copy()
    total_grids = len(grid)
    occupied_grids = len(occupied)

    stats = {
        "grid_size_m": cell_size,
        "total_grids": total_grids,
        "occupied_grids": occupied_grids,
        "occupancy_rate": occupied_grids / total_grids,
        # mean_score statistics
        "mean_score_mean": occupied["mean_score"].mean(),
        "mean_score_std": occupied["mean_score"].std(),
        "mean_score_p25": occupied["mean_score"].quantile(0.25),
        "mean_score_median": occupied["mean_score"].median(),
        "mean_score_p75": occupied["mean_score"].quantile(0.75),
        # high_potential_ratio statistics
        "hp_ratio_mean": occupied["high_potential_ratio"].mean(),
        "hp_ratio_std": occupied["high_potential_ratio"].std(),
        "hp_ratio_p25": occupied["high_potential_ratio"].quantile(0.25),
        "hp_ratio_median": occupied["high_potential_ratio"].median(),
        "hp_ratio_p75": occupied["high_potential_ratio"].quantile(0.75),
        # raw distributions for box-plot
        "_score_values": occupied["mean_score"].values,
        "_ratio_values": occupied["high_potential_ratio"].values,
    }
    return stats


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def make_boxplots(results: list[dict], output_path: Path) -> None:
    """Create side-by-side box-plots comparing grid sizes."""
    labels = [f"{r['grid_size_m']} m" for r in results]
    score_data = [r["_score_values"] for r in results]
    ratio_data = [r["_ratio_values"] for r in results]

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # --- Mean solar score ---
    bp1 = axes[0].boxplot(score_data, labels=labels, patch_artist=True,
                          medianprops={"color": "black", "linewidth": 1.5})
    colors = ["#4393c3", "#f4a582", "#d6604d", "#92c5de"]
    for patch, color in zip(bp1["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)
    axes[0].set_title("Grid Mean Solar Potential Score", fontsize=14)
    axes[0].set_xlabel("Grid Size", fontsize=12)
    axes[0].set_ylabel("Mean Solar Score (0–100)", fontsize=12)
    axes[0].tick_params(axis="both", labelsize=10)
    axes[0].grid(axis="y", linestyle="--", alpha=0.5)

    # --- High-potential ratio ---
    bp2 = axes[1].boxplot(ratio_data, labels=labels, patch_artist=True,
                          medianprops={"color": "black", "linewidth": 1.5})
    for patch, color in zip(bp2["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)
    axes[1].set_title("Grid High-Potential Ratio", fontsize=14)
    axes[1].set_xlabel("Grid Size", fontsize=12)
    axes[1].set_ylabel("High-Potential Ratio (0–1)", fontsize=12)
    axes[1].tick_params(axis="both", labelsize=10)
    axes[1].grid(axis="y", linestyle="--", alpha=0.5)

    fig.suptitle(
        "Grid-Size Sensitivity: Effect on Aggregated Solar Metrics\n(Changsha Urban Core)",
        fontsize=14,
        y=1.02,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logging.info("Saved figure: %s", output_path)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    setup_logging()
    ensure_dirs()

    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Missing input: {INPUT_PATH}")

    logging.info("Loading buildings from %s", INPUT_PATH)
    buildings = gpd.read_file(INPUT_PATH)

    required = {"solar_potential_score", "is_high_potential"}
    missing = required - set(buildings.columns)
    if missing:
        raise ValueError(f"Missing columns in input: {missing}")

    logging.info("Projecting to metric CRS…")
    projected_crs = buildings.estimate_utm_crs()
    buildings_proj = buildings.to_crs(projected_crs)
    buildings_proj["solar_potential_score"] = pd.to_numeric(
        buildings_proj["solar_potential_score"], errors="coerce"
    )
    buildings_proj["is_high_potential"] = pd.to_numeric(
        buildings_proj["is_high_potential"], errors="coerce"
    ).fillna(0).astype(int)

    results = []
    for size in GRID_SIZES_M:
        logging.info("Running grid aggregation at %d m …", size)
        stats = aggregate_at_grid_size(buildings_proj, size)
        logging.info(
            "  %d m → occupied grids: %d, mean score mean: %.3f, hp_ratio mean: %.3f",
            size,
            stats["occupied_grids"],
            stats["mean_score_mean"],
            stats["hp_ratio_mean"],
        )
        results.append(stats)

    # Build summary CSV (drop raw arrays)
    summary_cols = [k for k in results[0] if not k.startswith("_")]
    df_summary = pd.DataFrame([{k: r[k] for k in summary_cols} for r in results])
    df_summary.to_csv(OUTPUT_CSV, index=False)
    logging.info("Saved summary CSV: %s", OUTPUT_CSV)
    print(df_summary.to_string(index=False))

    make_boxplots(results, OUTPUT_FIG)
    logging.info("Done.")


if __name__ == "__main__":
    main()
