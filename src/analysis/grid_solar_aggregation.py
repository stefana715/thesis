from pathlib import Path
import logging

import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import box


INPUT_PATH = Path("data/processed/buildings_changsha_urban_core_solar_baseline.geojson")
OUTPUT_DIR = Path("data/processed")
FIGURE_DIR = Path("figure")

GRID_AGGREGATION_PATH = OUTPUT_DIR / "grid_solar_aggregation_changsha.geojson"
GRID_SUMMARY_PATH = OUTPUT_DIR / "grid_solar_aggregation_summary.txt"

GRID_SIZE_M = 500  # 500m grid for aggregation


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


def main() -> None:
    setup_logging()
    ensure_dirs()

    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_PATH}")

    logging.info("Reading solar baseline dataset...")
    gdf = gpd.read_file(INPUT_PATH)

    if gdf.empty:
        raise RuntimeError("Input dataset is empty.")

    projected_crs = gdf.estimate_utm_crs()
    gdf_proj = gdf.to_crs(projected_crs)

    logging.info("Creating building centroids...")
    centroids = gdf_proj.copy()
    centroids["geometry"] = centroids.geometry.centroid

    logging.info("Building %d m aggregation grid...", GRID_SIZE_M)
    grid = make_grid(gdf_proj.total_bounds, GRID_SIZE_M, projected_crs)

    logging.info("Spatial join: assigning buildings to grid cells...")
    joined = gpd.sjoin(centroids, grid, how="left", predicate="within")

    logging.info("Aggregating solar potential by grid cell...")
    agg = joined.groupby("index_right").agg(
        building_count=("solar_potential_score", "size"),
        mean_solar_score=("solar_potential_score", "mean"),
        median_solar_score=("solar_potential_score", "median"),
        std_solar_score=("solar_potential_score", "std"),
        min_solar_score=("solar_potential_score", "min"),
        max_solar_score=("solar_potential_score", "max"),
        total_footprint_area_m2=("footprint_area_m2", "sum"),
        mean_height_proxy_m=("height_proxy_m", "mean"),
    ).reset_index()

    # Merge back to grid geometry
    grid_agg = grid.merge(agg, left_index=True, right_on="index_right", how="left")

    # Fill NaN with 0 for empty cells
    grid_agg["building_count"] = grid_agg["building_count"].fillna(0).astype(int)
    grid_agg["total_footprint_area_m2"] = grid_agg["total_footprint_area_m2"].fillna(0)

    # Calculate density metrics
    grid_agg["building_density_per_km2"] = grid_agg["building_count"] / (GRID_SIZE_M / 1000) ** 2
    grid_agg["footprint_density_m2_per_km2"] = grid_agg["total_footprint_area_m2"] / (GRID_SIZE_M / 1000) ** 2

    # Classify grid cells
    grid_agg["solar_class"] = pd.cut(
        grid_agg["mean_solar_score"],
        bins=[0, 33, 66, 100],
        labels=["low", "medium", "high"],
        include_lowest=True
    )

    # Convert back to WGS84
    grid_agg_wgs84 = grid_agg.to_crs("EPSG:4326")

    logging.info("Saving grid aggregation GeoJSON...")
    grid_agg_wgs84.to_file(GRID_AGGREGATION_PATH, driver="GeoJSON")

    # Summary statistics
    total_cells = len(grid_agg)
    occupied_cells = (grid_agg["building_count"] > 0).sum()
    occupancy_rate = occupied_cells / total_cells * 100

    summary_text = f"""Grid Solar Aggregation Summary

Input file:
- {INPUT_PATH}

Output file:
- {GRID_AGGREGATION_PATH}

Grid configuration:
- Cell size: {GRID_SIZE_M} m
- Total grid cells: {total_cells}
- Occupied cells (with buildings): {occupied_cells} ({occupancy_rate:.1f}%)

Aggregation metrics per cell:
- building_count: number of buildings
- mean_solar_score: average solar potential score
- median_solar_score: median solar potential score
- std_solar_score: standard deviation of scores
- min_solar_score: minimum score in cell
- max_solar_score: maximum score in cell
- total_footprint_area_m2: total building footprint area
- mean_height_proxy_m: average building height
- building_density_per_km2: buildings per km²
- footprint_density_m2_per_km2: footprint area per km²
- solar_class: low/medium/high based on mean score

Descriptive statistics for occupied cells:
{grid_agg[grid_agg["building_count"] > 0][["mean_solar_score", "building_density_per_km2", "footprint_density_m2_per_km2"]].describe().to_string()}
"""

    GRID_SUMMARY_PATH.write_text(summary_text, encoding="utf-8")
    print(summary_text)

    logging.info("Saved outputs:")
    logging.info("- %s", GRID_AGGREGATION_PATH)
    logging.info("- %s", GRID_SUMMARY_PATH)
    logging.info("Done.")


if __name__ == "__main__":
    main()
