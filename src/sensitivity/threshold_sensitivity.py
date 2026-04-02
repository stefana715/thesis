"""
threshold_sensitivity.py

Re-classify high-potential buildings using multiple quantile thresholds
(q50, q55, q60, q66, q70, q75, q80) to assess how the choice of
classification cut-off affects screening outcomes.

Inputs
------
data/processed/buildings_changsha_urban_core_solar_baseline.geojson
    Buildings with pre-computed solar_potential_score (values 0–100).

data/processed/grid_changsha_urban_core_solar_baseline.geojson
    Pre-built 500 m grid (geometry only needed for spatial join).

Outputs
-------
outputs/sensitivity/threshold_comparison.csv
    One row per quantile threshold with building- and grid-level metrics.
figure/fig07_threshold_sensitivity.png
    Dual-axis line chart: high-potential count / ratio vs. threshold.
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
BUILDINGS_PATH = Path("data/processed/buildings_changsha_urban_core_solar_baseline.geojson")
OUTPUT_CSV = Path("outputs/sensitivity/threshold_comparison.csv")
OUTPUT_FIG = Path("figure/fig07_threshold_sensitivity.png")

QUANTILE_THRESHOLDS = [0.50, 0.55, 0.60, 0.66, 0.70, 0.75, 0.80]
GRID_SIZE_M = 500  # fixed at standard 500 m grid


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


def evaluate_threshold(
    buildings_proj: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
    quantile: float,
    scores: pd.Series,
) -> dict:
    """
    Classify buildings as high-potential using *quantile* cut-off,
    then aggregate to the 500 m grid and return summary metrics.
    """
    threshold_value = scores.quantile(quantile)
    is_high = (scores >= threshold_value).astype(int)

    total = len(buildings_proj)
    hp_count = int(is_high.sum())
    hp_fraction = hp_count / total

    # Grid-level aggregation
    centroids = buildings_proj.copy()
    centroids["geometry"] = centroids.geometry.centroid
    centroids["_is_high"] = is_high.values

    joined = gpd.sjoin(centroids, grid, how="left", predicate="within")

    agg = joined.groupby("grid_id").agg(
        building_count=("solar_potential_score", "count"),
        hp_count=("_is_high", "sum"),
    ).reset_index()
    agg["hp_ratio"] = agg["hp_count"] / agg["building_count"]

    occupied = agg[agg["building_count"] > 0]

    return {
        "quantile": quantile,
        "threshold_score": threshold_value,
        "hp_building_count": hp_count,
        "hp_building_fraction": hp_fraction,
        "grids_with_hp_ratio_gt0": int((occupied["hp_ratio"] > 0).sum()),
        "mean_grid_hp_ratio": occupied["hp_ratio"].mean(),
        "median_grid_hp_ratio": occupied["hp_ratio"].median(),
        "std_grid_hp_ratio": occupied["hp_ratio"].std(),
    }


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def make_threshold_plot(df: pd.DataFrame, output_path: Path) -> None:
    """Dual-axis line chart: HP count and HP fraction vs. quantile threshold."""
    quantile_pct = (df["quantile"] * 100).astype(int)

    fig, ax1 = plt.subplots(figsize=(9, 5))

    color_count = "#d6604d"
    color_frac = "#4393c3"
    color_grid = "#4dac26"

    ax1.plot(quantile_pct, df["hp_building_count"], "o-",
             color=color_count, linewidth=2, markersize=6, label="HP building count")
    ax1.set_xlabel("Quantile Threshold (%)", fontsize=12)
    ax1.set_ylabel("High-Potential Building Count", fontsize=12, color=color_count)
    ax1.tick_params(axis="y", labelcolor=color_count, labelsize=10)
    ax1.tick_params(axis="x", labelsize=10)

    ax2 = ax1.twinx()
    ax2.plot(quantile_pct, df["hp_building_fraction"] * 100, "s--",
             color=color_frac, linewidth=2, markersize=6, label="HP building fraction (%)")
    ax2.plot(quantile_pct, df["mean_grid_hp_ratio"] * 100, "^:",
             color=color_grid, linewidth=2, markersize=6, label="Mean grid HP ratio (%)")
    ax2.set_ylabel("Percentage (%)", fontsize=12, color=color_frac)
    ax2.tick_params(axis="y", labelcolor=color_frac, labelsize=10)

    # Mark the baseline q66 threshold
    ax1.axvline(x=66, color="grey", linestyle="--", linewidth=1, alpha=0.7)
    ax1.text(66.5, ax1.get_ylim()[1] * 0.95, "q66 (baseline)",
             color="grey", fontsize=9, va="top")

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper right", fontsize=9)

    ax1.set_title(
        "Threshold Sensitivity: High-Potential Classification vs. Quantile Cut-off\n"
        "(Changsha Urban Core, 500 m grid)",
        fontsize=14,
    )
    ax1.grid(axis="y", linestyle="--", alpha=0.4)

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

    if not BUILDINGS_PATH.exists():
        raise FileNotFoundError(f"Missing input: {BUILDINGS_PATH}")

    logging.info("Loading buildings from %s", BUILDINGS_PATH)
    buildings = gpd.read_file(BUILDINGS_PATH)

    if "solar_potential_score" not in buildings.columns:
        raise ValueError("Missing 'solar_potential_score' column.")

    logging.info("Projecting to metric CRS…")
    projected_crs = buildings.estimate_utm_crs()
    buildings_proj = buildings.to_crs(projected_crs)
    scores = pd.to_numeric(
        buildings_proj["solar_potential_score"], errors="coerce"
    ).fillna(0)
    buildings_proj = buildings_proj.copy()
    buildings_proj["solar_potential_score"] = scores

    logging.info("Building 500 m grid…")
    grid = make_grid(buildings_proj.total_bounds, GRID_SIZE_M, buildings_proj.crs)
    grid["grid_id"] = grid.index

    rows = []
    for q in QUANTILE_THRESHOLDS:
        logging.info("Evaluating threshold q%.0f (%.2f)…", q * 100, q)
        row = evaluate_threshold(buildings_proj, grid, q, scores)
        logging.info(
            "  q%.0f → threshold=%.3f, HP count=%d (%.1f%%), "
            "mean grid HP ratio=%.3f",
            q * 100,
            row["threshold_score"],
            row["hp_building_count"],
            row["hp_building_fraction"] * 100,
            row["mean_grid_hp_ratio"],
        )
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)
    logging.info("Saved summary CSV: %s", OUTPUT_CSV)
    print(df.to_string(index=False))

    make_threshold_plot(df, OUTPUT_FIG)
    logging.info("Done.")


if __name__ == "__main__":
    main()
