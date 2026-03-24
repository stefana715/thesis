from pathlib import Path
import logging

import geopandas as gpd
import osmnx as ox


PLACE_NAME = "Changsha, Hunan, China"
RAW_DIR = Path("data/raw")
STUDY_AREA_PATH = RAW_DIR / "study_area_changsha.geojson"
BUILDINGS_PATH = RAW_DIR / "buildings_changsha.geojson"
SUMMARY_PATH = RAW_DIR / "buildings_changsha_summary.txt"


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def ensure_directories() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)


def get_projected_crs(gdf: gpd.GeoDataFrame) -> str:
    """
    Estimate a suitable projected CRS for local analysis.
    """
    return gdf.estimate_utm_crs()


def clean_polygon_geometries(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Keep only Polygon/MultiPolygon, remove empty geometries, and repair validity.
    """
    if gdf.empty:
        return gdf

    gdf = gdf[gdf.geometry.notnull()].copy()
    gdf = gdf[~gdf.geometry.is_empty].copy()
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()

    if gdf.empty:
        return gdf

    projected_crs = get_projected_crs(gdf)
    gdf = gdf.to_crs(projected_crs)
    gdf["geometry"] = gdf.buffer(0)
    gdf = gdf[gdf.geometry.notnull()].copy()
    gdf = gdf[~gdf.geometry.is_empty].copy()
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    gdf = gdf.to_crs("EPSG:4326")

    return gdf


def create_summary_text(buildings: gpd.GeoDataFrame) -> str:
    total_buildings = len(buildings)
    columns = list(buildings.columns)

    height_count = 0
    if "height" in buildings.columns:
        height_count = buildings["height"].notna().sum()

    levels_count = 0
    if "building:levels" in buildings.columns:
        levels_count = buildings["building:levels"].notna().sum()

    if height_count > 0 or levels_count > 0:
        proxy_note = (
            "Building height proxies appear feasible: at least some buildings "
            "contain height-related attributes."
        )
    else:
        proxy_note = (
            "Building height proxies appear limited in raw OSM attributes: "
            "fallback rules using building type/default levels may be needed."
        )

    lines = [
        "Changsha OSM Buildings Summary",
        f"Place name: {PLACE_NAME}",
        f"Total buildings: {total_buildings}",
        f"Available columns: {columns}",
        f"Buildings with 'height': {height_count}",
        f"Buildings with 'building:levels': {levels_count}",
        f"Next-step note: {proxy_note}",
    ]
    return "\n".join(lines)


def main() -> None:
    setup_logging()
    ensure_directories()

    logging.info("Downloading study area boundary for %s", PLACE_NAME)
    study_area = ox.geocode_to_gdf(PLACE_NAME)
    study_area = clean_polygon_geometries(study_area)

    if study_area.empty:
        raise RuntimeError("Study area boundary is empty after cleaning.")

    logging.info("Saving study area boundary to %s", STUDY_AREA_PATH)
    study_area.to_file(STUDY_AREA_PATH, driver="GeoJSON")

    logging.info("Downloading building data from OpenStreetMap for Changsha...")
    # Current OSMnx API uses features_from_place, not geometries_from_place
    buildings = ox.features_from_place(PLACE_NAME, tags={"building": True})

    if buildings.empty:
        raise RuntimeError("No building features were returned from OSM.")

    buildings = buildings.reset_index(drop=False)
    buildings = gpd.GeoDataFrame(buildings, geometry="geometry", crs="EPSG:4326")
    buildings = clean_polygon_geometries(buildings)

    if buildings.empty:
        raise RuntimeError("No valid polygon/multipolygon buildings remain after cleaning.")

    logging.info("Saving building layer to %s", BUILDINGS_PATH)
    buildings.to_file(BUILDINGS_PATH, driver="GeoJSON")

    summary_text = create_summary_text(buildings)
    SUMMARY_PATH.write_text(summary_text, encoding="utf-8")

    print(summary_text)
    logging.info("Saved summary to %s", SUMMARY_PATH)
    logging.info("Done.")


if __name__ == "__main__":
    main()
