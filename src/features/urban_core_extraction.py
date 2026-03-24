from pathlib import Path
import logging

import geopandas as gpd
import pandas as pd
import matplotlib.pyplot as plt
from shapely.geometry import box


STUDY_AREA_PATH = Path("data/raw/study_area_changsha.geojson")
BUILDINGS_PATH = Path("data/processed/buildings_changsha_height_proxy.geojson")

OUTPUT_DIR = Path("data/processed")
FIGURE_DIR = Path("figure")

URBAN_CORE_BOUNDARY_PATH = OUTPUT_DIR / "study_area_changsha_urban_core.geojson"
URBAN_CORE_BUILDINGS_PATH = OUTPUT_DIR / "buildings_changsha_urban_core.geojson"
SUMMARY_PATH = OUTPUT_DIR / "phase1_urban_core_summary.txt"
MAP_PATH = FIGURE_DIR / "phase1_urban_core_map.png"

GRID_SIZE_M = 1000
MIN_DENSE_CELL_COUNT = 20
SMOOTH_BUFFER_M = 250


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)


def largest_polygon(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf

    exploded = gdf.explode(index_parts=False).reset_index(drop=True)
    exploded["area_tmp"] = exploded.geometry.area
    exploded = exploded.sort_values("area_tmp", ascending=False).head(1).copy()
    exploded = exploded.drop(columns=["area_tmp"])
    return exploded


def make_grid(bounds, cell_size: float, crs) -> gpd.GeoDataFrame:
    minx, miny, maxx, maxy = bounds
    xs = list(range(int(minx), int(maxx) + int(cell_size), int(cell_size)))
    ys = list(range(int(miny), int(maxy) + int(cell_size), int(cell_size)))

    cells = []
    for x in xs[:-1]:
        for y in ys[:-1]:
            cells.append(box(x, y, x + cell_size, y + cell_size))

    return gpd.GeoDataFrame({"geometry": cells}, crs=crs)


def summarize_counts(series: pd.Series) -> str:
    counts = series.value_counts(dropna=False)
    total = counts.sum()
    lines = []
    for key, value in counts.items():
        pct = (value / total * 100) if total else 0
        lines.append(f"- {key}: {value} ({pct:.2f}%)")
    return "\n".join(lines)


def main() -> None:
    setup_logging()
    ensure_dirs()

    if not STUDY_AREA_PATH.exists():
        raise FileNotFoundError(f"Missing study area file: {STUDY_AREA_PATH}")
    if not BUILDINGS_PATH.exists():
        raise FileNotFoundError(f"Missing building proxy file: {BUILDINGS_PATH}")

    logging.info("Reading study area boundary...")
    study_area = gpd.read_file(STUDY_AREA_PATH)
    logging.info("Reading building height proxy dataset...")
    buildings = gpd.read_file(BUILDINGS_PATH)

    if study_area.empty:
        raise RuntimeError("Study area file is empty.")
    if buildings.empty:
        raise RuntimeError("Building dataset is empty.")

    projected_crs = buildings.estimate_utm_crs()
    study_area_proj = study_area.to_crs(projected_crs)
    buildings_proj = buildings.to_crs(projected_crs)

    logging.info("Creating building centroids...")
    centroids = buildings_proj.copy()
    centroids["geometry"] = centroids.geometry.centroid

    logging.info("Building 1 km density grid...")
    grid = make_grid(study_area_proj.total_bounds, GRID_SIZE_M, projected_crs)

    joined = gpd.sjoin(centroids[["geometry"]], grid, how="left", predicate="within")
    counts = joined.groupby("index_right").size()
    grid["building_count"] = grid.index.map(counts).fillna(0).astype(int)

    positive_counts = grid.loc[grid["building_count"] > 0, "building_count"]
    if positive_counts.empty:
        raise RuntimeError("No buildings were assigned to the density grid.")

    percentile_threshold = positive_counts.quantile(0.75)
    dense_threshold = max(int(percentile_threshold), MIN_DENSE_CELL_COUNT)

    logging.info("Dense cell threshold = %s", dense_threshold)
    dense_cells = grid[grid["building_count"] >= dense_threshold].copy()

    if dense_cells.empty:
        raise RuntimeError("No dense cells identified. Try lowering the threshold.")

    logging.info("Dissolving dense cells to urban-core candidate...")
    dense_union = dense_cells.dissolve()

    urban_core = largest_polygon(dense_union)
    if urban_core.empty:
        raise RuntimeError("Failed to derive largest contiguous dense cluster.")

    logging.info("Smoothing urban-core boundary...")
    urban_core["geometry"] = urban_core.buffer(SMOOTH_BUFFER_M).buffer(-SMOOTH_BUFFER_M)

    logging.info("Clipping urban-core boundary to full Changsha study area...")
    study_area_union = study_area_proj.dissolve()
    urban_core = gpd.overlay(urban_core, study_area_union, how="intersection")

    urban_core = largest_polygon(urban_core)
    if urban_core.empty:
        raise RuntimeError("Urban core became empty after clipping.")

    logging.info("Extracting urban-core buildings...")
    urban_core_buildings = gpd.overlay(buildings_proj, urban_core, how="intersection")

    if urban_core_buildings.empty:
        raise RuntimeError("No buildings intersect the extracted urban core.")

    total_full = len(buildings_proj)
    total_core = len(urban_core_buildings)
    retained_pct = total_core / total_full * 100

    urban_core_wgs84 = urban_core.to_crs("EPSG:4326")
    urban_core_buildings_wgs84 = urban_core_buildings.to_crs("EPSG:4326")

    logging.info("Saving urban-core boundary...")
    urban_core_wgs84.to_file(URBAN_CORE_BOUNDARY_PATH, driver="GeoJSON")

    logging.info("Saving urban-core building subset...")
    urban_core_buildings_wgs84.to_file(URBAN_CORE_BUILDINGS_PATH, driver="GeoJSON")

    height_source_summary = summarize_counts(urban_core_buildings["height_proxy_source"])
    category_summary = summarize_counts(urban_core_buildings["building_category"])

    summary_text = f"""Phase 1 Urban Core Summary

Input study area:
- {STUDY_AREA_PATH}

Input buildings:
- {BUILDINGS_PATH}

Output urban core boundary:
- {URBAN_CORE_BOUNDARY_PATH}

Output urban core buildings:
- {URBAN_CORE_BUILDINGS_PATH}

Urban-core extraction rule:
Dense-building grid rule:
1 km centroid density grid -> dense cells using 75th percentile threshold with minimum threshold {MIN_DENSE_CELL_COUNT} -> largest contiguous dense cluster -> smoothing buffer in/out ({SMOOTH_BUFFER_M} m) -> clip to full study-area boundary.

Buildings retained:
- Full Changsha processed buildings: {total_full}
- Urban core buildings: {total_core}
- Percentage retained: {retained_pct:.2f}%

Height proxy source distribution in urban core:
{height_source_summary}

Building category distribution in urban core:
{category_summary}

Why this urban core is suitable for Phase 1:
- It focuses on the densest contiguous built-up area.
- It reduces the influence of sparse peripheral zones with weaker proxy reliability.
- It keeps the workflow open-data based, reproducible, interpretable, and thesis-friendly.
- It is a practical intermediate scope between a tiny pilot area and the full municipal extent.
"""

    SUMMARY_PATH.write_text(summary_text, encoding="utf-8")
    print(summary_text)

    logging.info("Creating figure...")
    study_area_plot = study_area_proj.to_crs("EPSG:3857")
    urban_core_plot = urban_core.to_crs("EPSG:3857")
    buildings_plot = urban_core_buildings.to_crs("EPSG:3857")

    fig, ax = plt.subplots(figsize=(10, 10))
    study_area_plot.boundary.plot(ax=ax, linewidth=1, label="Full Changsha boundary")
    buildings_plot.plot(ax=ax, markersize=0.5, alpha=0.5, label="Urban-core buildings")
    urban_core_plot.boundary.plot(ax=ax, linewidth=2, label="Urban-core boundary")

    ax.set_title("Phase 1 Urban Core Extraction for Changsha")
    ax.set_axis_off()
    plt.tight_layout()
    plt.savefig(MAP_PATH, dpi=300, bbox_inches="tight")
    plt.close()

    logging.info("Saved figure to %s", MAP_PATH)
    logging.info("Saved summary to %s", SUMMARY_PATH)
    logging.info("Done.")


if __name__ == "__main__":
    main()
