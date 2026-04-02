from pathlib import Path
import logging

import geopandas as gpd
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


INPUT_PATH = Path("data/processed/buildings_changsha_urban_core.geojson")
OUTPUT_DIR = Path("data/processed")
FIGURE_DIR = Path("figure")

OUTPUT_GEOJSON = OUTPUT_DIR / "buildings_changsha_urban_core_solar_baseline.geojson"
OUTPUT_SUMMARY = OUTPUT_DIR / "buildings_changsha_urban_core_solar_baseline_summary.txt"
HISTOGRAM_PATH = FIGURE_DIR / "solar_baseline_histogram.png"
MAP_PATH = FIGURE_DIR / "solar_baseline_map.png"

REQUIRED_FIELDS = [
    "geometry",
    "height_proxy_m",
    "building_category",
    "height_proxy_source",
]


CATEGORY_MULTIPLIERS = {
    "commercial": 1.10,
    "residential": 1.00,
    "mixed_unknown": 0.95,
}


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)


def validate_input_fields(gdf: gpd.GeoDataFrame) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in gdf.columns]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")


def minmax_normalize(series: pd.Series) -> pd.Series:
    s_min = series.min()
    s_max = series.max()
    if pd.isna(s_min) or pd.isna(s_max):
        return pd.Series(np.zeros(len(series)), index=series.index)
    if s_max == s_min:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return (series - s_min) / (s_max - s_min)


def classify_score(score: float, q33: float, q66: float) -> str:
    if score <= q33:
        return "low"
    if score <= q66:
        return "medium"
    return "high"


def summarize_counts(series: pd.Series) -> str:
    counts = series.value_counts(dropna=False)
    total = counts.sum()
    lines = []
    for key, value in counts.items():
        pct = (value / total * 100) if total else 0
        lines.append(f"- {key}: {value} ({pct:.2f}%)")
    return "\n".join(lines)


def build_summary(gdf: gpd.GeoDataFrame, q33: float, q66: float) -> str:
    total = len(gdf)
    desc = gdf["solar_potential_score"].describe()

    class_counts_text = summarize_counts(gdf["solar_potential_class"])

    avg_by_category = (
        gdf.groupby("building_category")["solar_potential_score"]
        .mean()
        .sort_values(ascending=False)
    )

    avg_by_category_lines = []
    for cat, value in avg_by_category.items():
        avg_by_category_lines.append(f"- {cat}: {value:.3f}")

    summary = f"""Changsha Urban Core Solar Baseline Summary

Input file:
- {INPUT_PATH}

Output file:
- {OUTPUT_GEOJSON}

Total buildings:
- {total}

Scoring formula:
- area_score = minmax(log1p(footprint_area_m2))
- height_score = minmax(log1p(height_proxy_m))
- base_score = 0.65 * area_score + 0.35 * height_score
- solar_potential_score = clip(base_score * category_multiplier * 100, 0, 100)

Category multipliers:
- commercial: {CATEGORY_MULTIPLIERS['commercial']}
- residential: {CATEGORY_MULTIPLIERS['residential']}
- mixed_unknown: {CATEGORY_MULTIPLIERS['mixed_unknown']}

Class thresholds:
- q33 = {q33:.3f}
- q66 = {q66:.3f}

Solar potential score descriptive statistics:
- count: {desc['count']:.0f}
- mean: {desc['mean']:.3f}
- std: {desc['std']:.3f}
- min: {desc['min']:.3f}
- 25%: {desc['25%']:.3f}
- 50%: {desc['50%']:.3f}
- 75%: {desc['75%']:.3f}
- max: {desc['max']:.3f}

Counts by solar_potential_class:
{class_counts_text}

Average score by building_category:
{chr(10).join(avg_by_category_lines)}

Baseline logic explanation:
- This Phase 1 baseline uses only local, currently available inputs.
- It combines building footprint area and height proxy as simple structural indicators of solar opportunity.
- A light category multiplier is applied to reflect broad differences in likely solar suitability.

Limitations:
- This is not a radiation simulation.
- No weather, shading, facade segmentation, or ray tracing is included.
- Height proxy values still depend partly on inferred defaults.

Why this is still useful for Phase 1:
- It provides a transparent and reproducible low-data baseline.
- It supports spatial screening and prioritization within the Changsha urban core.
- It establishes a first interpretable benchmark before adding more advanced inputs.
"""
    return summary


def main() -> None:
    setup_logging()
    ensure_dirs()

    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Missing input file: {INPUT_PATH}")

    logging.info("Reading urban-core building dataset...")
    gdf = gpd.read_file(INPUT_PATH)

    if gdf.empty:
        raise RuntimeError("Input dataset is empty.")

    validate_input_fields(gdf)

    logging.info("Projecting to metric CRS for area calculation...")
    projected_crs = gdf.estimate_utm_crs()
    gdf_proj = gdf.to_crs(projected_crs)

    logging.info("Computing footprint area...")
    gdf["footprint_area_m2"] = gdf_proj.geometry.area

    gdf["log_area"] = np.log1p(gdf["footprint_area_m2"].clip(lower=0))
    gdf["log_height"] = np.log1p(pd.to_numeric(gdf["height_proxy_m"], errors="coerce").fillna(0).clip(lower=0))

    logging.info("Normalizing area and height...")
    gdf["area_score"] = minmax_normalize(gdf["log_area"])
    gdf["height_score"] = minmax_normalize(gdf["log_height"])

    logging.info("Applying category multipliers...")
    gdf["category_multiplier"] = gdf["building_category"].map(CATEGORY_MULTIPLIERS).fillna(
        CATEGORY_MULTIPLIERS["mixed_unknown"]
    )

    gdf["base_score"] = 0.65 * gdf["area_score"] + 0.35 * gdf["height_score"]
    gdf["solar_potential_score"] = (gdf["base_score"] * gdf["category_multiplier"] * 100).clip(0, 100)

    q33 = gdf["solar_potential_score"].quantile(0.33)
    gdf["solar_potential_score_num"] = pd.to_numeric(
        gdf["solar_potential_score"], errors="coerce"
    )

    valid_scores = gdf["solar_potential_score_num"].dropna()
    if valid_scores.empty:
        raise ValueError("No valid numeric solar_potential_score values found.")

    q66 = valid_scores.quantile(0.66)

    gdf["is_high_potential"] = (
        gdf["solar_potential_score_num"] >= q66
    ).astype(int)

    logging.info("Class thresholds: q33=%.3f, q66=%.3f", q33, q66)

    gdf["solar_potential_class"] = gdf["solar_potential_score"].apply(
        lambda x: classify_score(x, q33, q66)
    )

    required_output_fields = [
        "solar_potential_score",
        "solar_potential_class",
        "is_high_potential",
    ]
    missing_output_fields = [
        field for field in required_output_fields if field not in gdf.columns
    ]
    if missing_output_fields:
        raise ValueError(f"Missing required output fields: {missing_output_fields}")

    logging.info("Saving processed baseline GeoJSON...")
    gdf.to_file(OUTPUT_GEOJSON, driver="GeoJSON")

    summary_text = build_summary(gdf, q33, q66)
    OUTPUT_SUMMARY.write_text(summary_text, encoding="utf-8")
    print(summary_text)

    logging.info("Creating histogram...")
    plt.figure(figsize=(8, 5))
    plt.hist(gdf["solar_potential_score"], bins=30)
    plt.title("Solar Potential Score Histogram")
    plt.xlabel("solar_potential_score")
    plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(HISTOGRAM_PATH, dpi=300, bbox_inches="tight")
    plt.close()

    logging.info("Creating map...")
    plot_gdf = gdf.to_crs("EPSG:3857")

    fig, ax = plt.subplots(figsize=(10, 10))

    for cls in ["low", "medium", "high"]:
        subset = plot_gdf[plot_gdf["solar_potential_class"] == cls]
        if not subset.empty:
            subset.plot(ax=ax, linewidth=0.1, label=cls)

    ax.set_title("Changsha Urban Core Solar Baseline Classes")
    ax.set_axis_off()
    ax.legend(title="solar_potential_class")
    plt.tight_layout()
    plt.savefig(MAP_PATH, dpi=300, bbox_inches="tight")
    plt.close()

    logging.info("Saved outputs:")
    logging.info("- %s", OUTPUT_GEOJSON)
    logging.info("- %s", OUTPUT_SUMMARY)
    logging.info("- %s", HISTOGRAM_PATH)
    logging.info("- %s", MAP_PATH)
    logging.info("Done.")


if __name__ == "__main__":
    main()
