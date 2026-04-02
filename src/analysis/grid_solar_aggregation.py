from pathlib import Path
import logging
import matplotlib.pyplot as plt

import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import box


INPUT_PATH = Path("data/processed/buildings_changsha_urban_core_solar_baseline.geojson")
OUTPUT_DIR = Path("data/processed")
FIGURE_DIR = Path("figure")

GRID_SIZE_M = 500  # 500m grid for aggregation

GRID_SUMMARY_CSV_PATH = Path("data/processed/grid_solar_baseline_summary.csv")
TOP10_MEAN_CSV_PATH = Path("data/processed/top10_grids_by_mean_score.csv")
TOP10_COUNT_CSV_PATH = Path("data/processed/top10_grids_by_building_count.csv")
TOP10_RATIO_CSV_PATH = Path("data/processed/top10_grids_by_high_potential_ratio.csv")


def get_output_paths(output_dir: Path = OUTPUT_DIR, figure_dir: Path = FIGURE_DIR):
    return {
        "grid_output_path": output_dir / "grid_changsha_urban_core_solar_baseline.geojson",
        "summary_output_path": output_dir / "grid_changsha_urban_core_solar_baseline_summary.txt",
        "fig_mean_score_path": figure_dir / "grid_solar_baseline_mean_score_map.png",
        "fig_high_ratio_path": figure_dir / "grid_solar_baseline_high_potential_ratio_map.png",
        "fig_building_count_path": figure_dir / "grid_solar_baseline_building_count_map.png",
    }


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)


def make_grid(bounds, cell_size: float, crs) -> gpd.GeoDataFrame:
    minx, miny, maxx, maxy = bounds
    xs = list(range(int(minx), int(maxx) + int(cell_size), int(cell_size)))
    ys = list(range(int(miny), int(maxy) + int(cell_size), int(cell_size)))

    cells = []
    for x in xs[:-1]:
        for y in ys[:-1]:
            cells.append(box(x, y, x + cell_size, y + cell_size))

    return gpd.GeoDataFrame({"geometry": cells}, crs=crs)


def save_grid_map(gdf, value_col, title, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 8))
    gdf.plot(
        column=value_col,
        ax=ax,
        legend=True,
        cmap="OrRd",
        linewidth=0.2,
        edgecolor="grey",
        missing_kwds={"color": "lightgrey", "label": "No data"},
    )
    ax.set_title(title)
    ax.set_axis_off()
    plt.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

    logging.info("Saved figure: %s", output_path)


def export_grid_tables(grid: gpd.GeoDataFrame) -> None:
    """Export thesis-ready grid summary and ranking tables."""
    logging.info("Entered export_grid_tables")

    table = grid.copy()

    cols = [
        "grid_id",
        "building_count",
        "mean_score",
        "median_solar_score",
        "std_solar_score",
        "min_solar_score",
        "max_solar_score",
        "high_potential_building_count",
        "total_footprint_area_m2",
        "mean_height_proxy_m",
        "building_density_per_km2",
        "footprint_density_m2_per_km2",
        "solar_class",
        "high_potential_ratio",
    ]

    table[cols].to_csv(GRID_SUMMARY_CSV_PATH, index=False)
    logging.info("Saved CSV: %s", GRID_SUMMARY_CSV_PATH)

    occupied = table.loc[table["building_count"] > 0].copy()

    occupied.sort_values("mean_score", ascending=False).head(10)[cols].to_csv(
        TOP10_MEAN_CSV_PATH, index=False
    )
    logging.info("Saved CSV: %s", TOP10_MEAN_CSV_PATH)

    occupied.sort_values("building_count", ascending=False).head(10)[cols].to_csv(
        TOP10_COUNT_CSV_PATH, index=False
    )
    logging.info("Saved CSV: %s", TOP10_COUNT_CSV_PATH)

    occupied.sort_values("high_potential_ratio", ascending=False).head(10)[cols].to_csv(
        TOP10_RATIO_CSV_PATH, index=False
    )
    logging.info("Saved CSV: %s", TOP10_RATIO_CSV_PATH)


def main() -> None:
    setup_logging()
    ensure_dirs()

    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_PATH}")

    logging.info("Reading solar baseline dataset...")
    buildings = gpd.read_file(INPUT_PATH)

    if buildings.empty:
        raise RuntimeError("Input dataset is empty.")

    if "is_high_potential" not in buildings.columns:
        raise KeyError(
            "Missing required upstream field 'is_high_potential'. "
            "Fix src/models/baseline_solar_potential.py first."
        )

    projected_crs = buildings.estimate_utm_crs()
    gdf_proj = buildings.to_crs(projected_crs)

    logging.info("Creating building centroids...")
    centroids = gdf_proj.copy()
    centroids["geometry"] = centroids.geometry.centroid

    logging.info("Building %d m aggregation grid...", GRID_SIZE_M)
    grid = make_grid(gdf_proj.total_bounds, GRID_SIZE_M, projected_crs)
    grid["grid_id"] = grid.index

    logging.info("Spatial join: assigning buildings to grid cells...")
    joined = gpd.sjoin(centroids, grid, how="left", predicate="within")

    logging.info("Aggregating solar potential by grid cell...")
    agg = joined.groupby("grid_id").agg(
        building_count=("solar_potential_score", "count"),
        mean_score=("solar_potential_score", "mean"),
        high_potential_building_count=("is_high_potential", "sum"),
        median_solar_score=("solar_potential_score", "median"),
        std_solar_score=("solar_potential_score", "std"),
        min_solar_score=("solar_potential_score", "min"),
        max_solar_score=("solar_potential_score", "max"),
        total_footprint_area_m2=("footprint_area_m2", "sum"),
        mean_height_proxy_m=("height_proxy_m", "mean"),
    ).reset_index()

    agg["high_potential_ratio"] = (
        agg["high_potential_building_count"] / agg["building_count"]
    )

    # Merge back to grid geometry
    grid_agg = grid.merge(agg, on="grid_id", how="left")

    # Explicit handling for empty cells only
    empty_cells = grid_agg["building_count"].isna()

    grid_agg.loc[empty_cells, "building_count"] = 0
    grid_agg.loc[empty_cells, "total_footprint_area_m2"] = 0
    grid_agg.loc[empty_cells, "high_potential_building_count"] = 0
    grid_agg.loc[empty_cells, "high_potential_ratio"] = 0

    grid_agg["building_count"] = grid_agg["building_count"].astype(int)
    grid_agg["high_potential_building_count"] = grid_agg["high_potential_building_count"].astype(int)

    # Fail loudly if occupied cells still contain NaN
    occupied_cells = grid_agg["building_count"] > 0
    if grid_agg.loc[occupied_cells, "high_potential_ratio"].isna().any():
        raise ValueError(
            "Occupied cells contain NaN in high_potential_ratio; check upstream aggregation."
        )

    # Calculate density metrics
    grid_agg["building_density_per_km2"] = (
        grid_agg["building_count"] / (GRID_SIZE_M / 1000) ** 2
    )
    grid_agg["footprint_density_m2_per_km2"] = (
        grid_agg["total_footprint_area_m2"] / (GRID_SIZE_M / 1000) ** 2
    )

    # Classify grid cells
    grid_agg["solar_class"] = pd.cut(
        grid_agg["mean_score"],
        bins=[0, 33, 66, 100],
        labels=["low", "medium", "high"],
        include_lowest=True
    )

    # Convert back to WGS84
    grid_agg_wgs84 = grid_agg.to_crs("EPSG:4326")

    paths = get_output_paths()
    grid_output_path = paths["grid_output_path"]
    summary_output_path = paths["summary_output_path"]

    logging.info("Saving grid aggregation GeoJSON...")
    grid_agg_wgs84.to_file(grid_output_path, driver="GeoJSON")

    # Summary statistics
    total_cells = len(grid_agg)
    occupied_cells = (grid_agg["building_count"] > 0).sum()
    occupancy_rate = occupied_cells / total_cells * 100

    summary_text = f"""Grid Solar Aggregation Summary

Input file:
- {INPUT_PATH}

Output file:
- {grid_output_path}

Grid configuration:
- Cell size: {GRID_SIZE_M} m
- Total grid cells: {total_cells}
- Occupied cells (with buildings): {occupied_cells} ({occupancy_rate:.1f}%)

Aggregation metrics per cell:
- building_count: number of buildings
- mean_score: average solar potential score
- median_solar_score: median solar potential score
- std_solar_score: standard deviation of scores
- min_solar_score: minimum score in cell
- max_solar_score: maximum score in cell
- high_potential_building_count: count of high-potential buildings in cell
- high_potential_ratio: high_potential_building_count / building_count
- total_footprint_area_m2: total building footprint area
- mean_height_proxy_m: average building height
- building_density_per_km2: buildings per km²
- footprint_density_m2_per_km2: footprint area per km²
- solar_class: low/medium/high based on mean score

Descriptive statistics for occupied cells:
{grid_agg[grid_agg["building_count"] > 0][["mean_score", "building_density_per_km2", "footprint_density_m2_per_km2", "high_potential_ratio"]].describe().to_string()}
"""

    summary_output_path.parent.mkdir(parents=True, exist_ok=True)
    grid_output_path.parent.mkdir(parents=True, exist_ok=True)
    paths = get_output_paths()
    fig_mean_score_path = paths["fig_mean_score_path"]
    fig_high_ratio_path = paths["fig_high_ratio_path"]
    fig_building_count_path = paths["fig_building_count_path"]
    fig_mean_score_path.parent.mkdir(parents=True, exist_ok=True)

    logging.info("Exporting GeoJSON to: %s", grid_output_path)
    grid_agg_wgs84.to_file(grid_output_path, driver="GeoJSON")

    logging.info("Exporting summary to: %s", summary_output_path)
    summary_output_path.write_text(summary_text, encoding="utf-8")
    print(summary_text)

    logging.info("About to export grid tables")
    export_grid_tables(grid_agg_wgs84)

    occupied = grid_agg_wgs84[grid_agg_wgs84["building_count"] > 0].copy()

    save_grid_map(
        occupied,
        "mean_score",
        "Grid Mean Solar Potential Score",
        fig_mean_score_path,
    )

    save_grid_map(
        occupied,
        "high_potential_ratio",
        "Grid High-Potential Ratio",
        fig_high_ratio_path,
    )

    save_grid_map(
        occupied,
        "building_count",
        "Grid Building Count",
        fig_building_count_path,
    )

    logging.info("Saved outputs:")
    logging.info("- %s", grid_output_path)
    logging.info("- %s", summary_output_path)
    logging.info("- %s", fig_mean_score_path)
    logging.info("- %s", fig_high_ratio_path)
    logging.info("- %s", fig_building_count_path)
    logging.info("Done.")


if __name__ == "__main__":
    main()
