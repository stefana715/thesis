from pathlib import Path
import logging
import re
from typing import Optional, Tuple

import geopandas as gpd
import pandas as pd


INPUT_PATH = Path("data/raw/buildings_changsha.geojson")
OUTPUT_DIR = Path("data/processed")
OUTPUT_GEOJSON = OUTPUT_DIR / "buildings_changsha_height_proxy.geojson"
OUTPUT_SUMMARY = OUTPUT_DIR / "buildings_changsha_height_proxy_summary.txt"

RESIDENTIAL_FLOOR_HEIGHT = 3.0
COMMERCIAL_FLOOR_HEIGHT = 3.5
MIXED_UNKNOWN_FLOOR_HEIGHT = 3.2
FALLBACK_DEFAULT_HEIGHT = 10.0


RESIDENTIAL_TAGS = {
    "residential",
    "house",
    "apartments",
    "detached",
    "semidetached_house",
    "terrace",
    "yes",
    "hut",
    "dormitory",
    "bungalow",
    "farm",
    "cabin",
}

COMMERCIAL_TAGS = {
    "commercial",
    "retail",
    "office",
    "hotel",
    "industrial",
    "warehouse",
    "supermarket",
    "kiosk",
    "mall",
    "shop",
    "hospital",
    "school",
    "college",
    "university",
    "public",
    "government",
    "civic",
    "transportation",
    "station",
    "terminal",
}


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def parse_numeric_value(value) -> Optional[float]:
    """
    Parse numeric values from OSM-like fields.
    Examples:
    - 12
    - "12"
    - "12.5"
    - "12 m"
    - "12;15" -> 12
    - None / invalid -> None
    """
    if pd.isna(value):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()
    if not text:
        return None

    match = re.search(r"-?\d+(\.\d+)?", text)
    if not match:
        return None

    try:
        return float(match.group())
    except ValueError:
        return None


def infer_building_category(building_value) -> str:
    """
    Infer broad category from OSM building tag.
    Returns one of:
    - residential
    - commercial
    - mixed_unknown
    """
    if pd.isna(building_value):
        return "mixed_unknown"

    value = str(building_value).strip().lower()

    if value in RESIDENTIAL_TAGS:
        return "residential"

    if value in COMMERCIAL_TAGS:
        return "commercial"

    return "mixed_unknown"


def height_from_levels(levels: float, category: str) -> float:
    if category == "residential":
        return levels * RESIDENTIAL_FLOOR_HEIGHT
    if category == "commercial":
        return levels * COMMERCIAL_FLOOR_HEIGHT
    return levels * MIXED_UNKNOWN_FLOOR_HEIGHT


def compute_height_proxy(row) -> Tuple[float, str, str]:
    """
    Returns:
    - height_proxy_m
    - height_proxy_source
    - building_category
    """
    category = infer_building_category(row.get("building"))

    raw_height = parse_numeric_value(row.get("height"))
    if raw_height is not None and raw_height > 0:
        return raw_height, "raw_height", category

    raw_levels = parse_numeric_value(row.get("building:levels"))
    if raw_levels is not None and raw_levels > 0:
        return height_from_levels(raw_levels, category), "building_levels", category

    if category == "residential":
        return 3 * RESIDENTIAL_FLOOR_HEIGHT, "building_type_default", category

    if category == "commercial":
        return 3 * COMMERCIAL_FLOOR_HEIGHT, "building_type_default", category

    return FALLBACK_DEFAULT_HEIGHT, "fallback_default", category


def build_summary(gdf: gpd.GeoDataFrame) -> str:
    total = len(gdf)

    source_counts = gdf["height_proxy_source"].value_counts(dropna=False).to_dict()

    raw_height_count = int(source_counts.get("raw_height", 0))
    building_levels_count = int(source_counts.get("building_levels", 0))
    type_default_count = int(source_counts.get("building_type_default", 0))
    fallback_count = int(source_counts.get("fallback_default", 0))

    desc = gdf["height_proxy_m"].describe()

    lines = [
        "Changsha Building Height Proxy Summary",
        f"Input file: {INPUT_PATH}",
        f"Output file: {OUTPUT_GEOJSON}",
        "",
        f"Total buildings: {total}",
        f"Count using raw 'height': {raw_height_count}",
        f"Count using 'building:levels': {building_levels_count}",
        f"Count using building-type default: {type_default_count}",
        f"Count using fallback default: {fallback_count}",
        "",
        "Height proxy descriptive statistics (meters):",
        f"count: {desc['count']:.0f}",
        f"mean: {desc['mean']:.3f}",
        f"std: {desc['std']:.3f}",
        f"min: {desc['min']:.3f}",
        f"25%: {desc['25%']:.3f}",
        f"50%: {desc['50%']:.3f}",
        f"75%: {desc['75%']:.3f}",
        f"max: {desc['max']:.3f}",
        "",
        "Default assumptions:",
        f"residential floor height: {RESIDENTIAL_FLOOR_HEIGHT} m",
        f"commercial floor height: {COMMERCIAL_FLOOR_HEIGHT} m",
        f"mixed/unknown floor height: {MIXED_UNKNOWN_FLOOR_HEIGHT} m",
        f"fallback default height: {FALLBACK_DEFAULT_HEIGHT} m",
    ]
    return "\n".join(lines)


def main() -> None:
    setup_logging()
    ensure_output_dir()

    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    logging.info("Reading raw building data from %s", INPUT_PATH)
    gdf = gpd.read_file(INPUT_PATH)

    if gdf.empty:
        raise RuntimeError("Input building dataset is empty.")

    logging.info("Constructing height_proxy_m ...")
    results = gdf.apply(compute_height_proxy, axis=1, result_type="expand")
    results.columns = ["height_proxy_m", "height_proxy_source", "building_category"]

    gdf["height_proxy_m"] = results["height_proxy_m"]
    gdf["height_proxy_source"] = results["height_proxy_source"]
    gdf["building_category"] = results["building_category"]

    logging.info("Saving processed GeoJSON to %s", OUTPUT_GEOJSON)
    gdf.to_file(OUTPUT_GEOJSON, driver="GeoJSON")

    summary_text = build_summary(gdf)
    OUTPUT_SUMMARY.write_text(summary_text, encoding="utf-8")

    print(summary_text)
    logging.info("Saved summary to %s", OUTPUT_SUMMARY)
    logging.info("Done.")


if __name__ == "__main__":
    main()
