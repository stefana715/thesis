"""
height_proxy_sensitivity.py

Assess how robust the building-level solar potential scores are to
uncertainty in the height proxy estimates by applying systematic
multiplicative perturbations of ±10 %, ±20 %, and ±30 % to
height_proxy_m and re-running the scoring formula.

The baseline (0 % perturbation) is included as a reference row.

Scoring formula (mirrors baseline_solar_potential.py)
------------------------------------------------------
    area_score  = minmax(log1p(footprint_area_m2))          # unchanged
    height_score = minmax(log1p(height_proxy_m * factor))   # perturbed
    base_score  = 0.65 * area_score + 0.35 * height_score
    solar_potential_score = clip(base_score * category_multiplier * 100, 0, 100)

Classification uses the *baseline* q66 threshold (45.513) so that all
perturbation scenarios are compared against the same reference boundary.

Inputs
------
data/processed/buildings_changsha_urban_core_solar_baseline.geojson
    Buildings with height_proxy_m, footprint_area_m2, building_category,
    and the unperturbed solar_potential_score.

Outputs
-------
outputs/sensitivity/height_proxy_comparison.csv
    One row per perturbation factor with score and classification metrics.
figure/fig_height_sensitivity.png
    Line / bar chart showing score change and HP-count change vs. perturbation.
"""

from pathlib import Path
import logging

import geopandas as gpd
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
INPUT_PATH = Path("data/processed/buildings_changsha_urban_core_solar_baseline.geojson")
OUTPUT_CSV = Path("outputs/sensitivity/height_proxy_comparison.csv")
OUTPUT_FIG = Path("figure/fig_height_sensitivity.png")

# Perturbation factors: 0.70, 0.80, 0.90, 1.00 (baseline), 1.10, 1.20, 1.30
PERTURBATION_FACTORS = [-0.30, -0.20, -0.10, 0.00, +0.10, +0.20, +0.30]

CATEGORY_MULTIPLIERS = {
    "commercial": 1.10,
    "residential": 1.00,
    "mixed_unknown": 0.95,
}

# Baseline q66 threshold (verified pipeline value)
BASELINE_Q66 = 45.513


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


def minmax_normalize(series: pd.Series) -> pd.Series:
    """Min-max normalise a numeric series; returns zeros if constant."""
    s_min = series.min()
    s_max = series.max()
    if pd.isna(s_min) or pd.isna(s_max) or s_max == s_min:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return (series - s_min) / (s_max - s_min)


def score_with_perturbation(
    gdf: gpd.GeoDataFrame,
    perturbation: float,
    baseline_q66: float,
) -> dict:
    """
    Re-compute solar_potential_score with height_proxy_m multiplied by
    (1 + perturbation).  Returns summary statistics.
    """
    factor = 1.0 + perturbation
    perturbed_height = (
        pd.to_numeric(gdf["height_proxy_m"], errors="coerce")
        .fillna(0)
        .clip(lower=0) * factor
    )

    log_area = np.log1p(gdf["footprint_area_m2"].clip(lower=0))
    log_height = np.log1p(perturbed_height)

    area_score = minmax_normalize(log_area)
    height_score = minmax_normalize(log_height)

    cat_mult = gdf["building_category"].map(CATEGORY_MULTIPLIERS).fillna(
        CATEGORY_MULTIPLIERS["mixed_unknown"]
    )

    base_score = 0.65 * area_score + 0.35 * height_score
    score = (base_score * cat_mult * 100).clip(0, 100)

    is_high = (score >= baseline_q66).astype(int)
    hp_count = int(is_high.sum())
    total = len(gdf)

    return {
        "perturbation_pct": int(round(perturbation * 100)),
        "height_factor": round(factor, 2),
        "mean_score": score.mean(),
        "std_score": score.std(),
        "median_score": score.median(),
        "p25_score": score.quantile(0.25),
        "p75_score": score.quantile(0.75),
        "hp_count": hp_count,
        "hp_fraction": hp_count / total,
    }


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def make_sensitivity_plot(df: pd.DataFrame, baseline_row: pd.Series,
                          output_path: Path) -> None:
    """
    Three-panel figure:
      (a) Mean score vs. perturbation
      (b) HP count vs. perturbation
      (c) HP fraction vs. perturbation
    """
    pct = df["perturbation_pct"]

    fig, axes = plt.subplots(1, 3, figsize=(14, 5))

    def _panel(ax, y_col, ylabel, title, color, baseline_val):
        ax.plot(pct, df[y_col], "o-", color=color, linewidth=2, markersize=7)
        ax.fill_between(pct, df[y_col], baseline_val,
                        alpha=0.15, color=color)
        ax.axhline(y=baseline_val, color="grey", linestyle="--",
                   linewidth=1, label="Baseline (0 %)")
        ax.axvline(x=0, color="grey", linestyle=":", linewidth=1)
        ax.set_xlabel("Height Perturbation (%)", fontsize=12)
        ax.set_ylabel(ylabel, fontsize=12)
        ax.set_title(title, fontsize=13)
        ax.tick_params(labelsize=10)
        ax.grid(axis="y", linestyle="--", alpha=0.4)
        ax.legend(fontsize=9)

    _panel(axes[0], "mean_score", "Mean Solar Score (0–100)",
           "(a) Mean Solar Score", "#d6604d",
           float(baseline_row["mean_score"]))

    _panel(axes[1], "hp_count", "High-Potential Building Count",
           "(b) HP Building Count", "#4393c3",
           float(baseline_row["hp_count"]))

    _panel(axes[2], "hp_fraction", "HP Building Fraction",
           "(c) HP Building Fraction", "#4dac26",
           float(baseline_row["hp_fraction"]))

    fig.suptitle(
        "Height-Proxy Sensitivity: Effect of ±30 % Height Perturbation\n"
        "(Changsha Urban Core, baseline q66 = 45.513)",
        fontsize=14,
        y=1.03,
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

    required_cols = {"height_proxy_m", "building_category", "solar_potential_score"}
    missing = required_cols - set(buildings.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    # footprint_area_m2 may or may not be stored; recompute from projected geometry
    if "footprint_area_m2" not in buildings.columns:
        logging.info("footprint_area_m2 not found — computing from projected geometry…")
        projected_crs = buildings.estimate_utm_crs()
        buildings_proj = buildings.to_crs(projected_crs)
        buildings = buildings.copy()
        buildings["footprint_area_m2"] = buildings_proj.geometry.area
    else:
        buildings = buildings.copy()
        buildings["footprint_area_m2"] = pd.to_numeric(
            buildings["footprint_area_m2"], errors="coerce"
        ).fillna(0)

    rows = []
    for delta in PERTURBATION_FACTORS:
        logging.info("Evaluating perturbation %+.0f %% …", delta * 100)
        row = score_with_perturbation(buildings, delta, BASELINE_Q66)
        logging.info(
            "  factor=%.2f → mean_score=%.3f, HP count=%d (%.1f%%)",
            row["height_factor"],
            row["mean_score"],
            row["hp_count"],
            row["hp_fraction"] * 100,
        )
        rows.append(row)

    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_CSV, index=False)
    logging.info("Saved summary CSV: %s", OUTPUT_CSV)
    print(df.to_string(index=False))

    baseline_row = df[df["perturbation_pct"] == 0].iloc[0]
    make_sensitivity_plot(df, baseline_row, OUTPUT_FIG)
    logging.info("Done.")


if __name__ == "__main__":
    main()
