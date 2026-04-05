#!/usr/bin/env python3
"""
weight_sensitivity.py

Scoring weight sensitivity analysis for the Changsha solar screening baseline.

Tests whether the spatial screening outcome is sensitive to the area/height
weight choice. Recomputes solar_potential_score for all 18,855 buildings under
four weight variants, keeping everything else (log transform, min-max
normalisation, category adjustment, clip) identical to the baseline.

Weight variants
---------------
  W1: area=0.50, height=0.50  (equal weight)
  W2: area=0.65, height=0.35  (baseline — current)
  W3: area=0.70, height=0.30  (stronger area dominance)
  W4: area=1.00, height=0.00  (area only)

Metrics
-------
- Building-level Spearman ρ vs baseline (W2) for each variant
- Mean score, std, high-potential count (threshold = q66 = 45.513)
- Grid-level (500 m) Spearman ρ of grid mean rankings vs baseline
- Full 4×4 pairwise Spearman ρ matrix

Outputs
-------
  outputs/sensitivity/weight_sensitivity_results.csv
  figure/fig_weight_sensitivity.png  (300 dpi, 2-panel)

Usage
-----
    python src/sensitivity/weight_sensitivity.py \
        --input     data/processed/buildings_changsha_urban_core_solar_baseline.geojson \
        --grid      data/processed/grid_changsha_urban_core_solar_baseline.geojson \
        --output_dir outputs/sensitivity/ \
        --figure_dir figure/
"""

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import gaussian_kde

# ── Constants ─────────────────────────────────────────────────────────────────

CATEGORY_MULTIPLIERS = {"commercial": 1.10, "residential": 1.00, "mixed_unknown": 0.95}
Q66_THRESHOLD = 45.513   # from baseline run (fixed — do not recompute)

WEIGHT_VARIANTS = [
    ("W1: 0.50/0.50", 0.50, 0.50),
    ("W2: 0.65/0.35 ✓", 0.65, 0.35),
    ("W3: 0.70/0.30", 0.70, 0.30),
    ("W4: 1.00/0.00", 1.00, 0.00),
]

VARIANT_COLORS = ["#3182bd", "#e6550d", "#31a354", "#756bb1"]
BASELINE_LABEL = "W2: 0.65/0.35 ✓"


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
    )


# ── Scoring ───────────────────────────────────────────────────────────────────

def recompute_score(gdf: gpd.GeoDataFrame, w_area: float, w_height: float) -> pd.Series:
    """Recompute solar_potential_score using stored area_score / height_score."""
    base = w_area * gdf["area_score"] + w_height * gdf["height_score"]
    multiplier = gdf["building_category"].map(CATEGORY_MULTIPLIERS).fillna(
        CATEGORY_MULTIPLIERS["mixed_unknown"]
    )
    score = (base * multiplier * 100).clip(0, 100)
    return score


# ── Grid aggregation ──────────────────────────────────────────────────────────

def build_grid_scores(
    gdf: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
    score_cols: list,
) -> pd.DataFrame:
    """
    Spatial-join buildings to grid cells and return per-grid mean scores
    for each score column. Only occupied grids returned.
    """
    logging.info("  Spatial joining buildings → grid cells…")
    joined = gpd.sjoin(
        gdf[["geometry"] + score_cols],
        grid[["grid_id", "geometry"]],
        how="left",
        predicate="within",
    ).drop(columns=["index_right"], errors="ignore")
    joined = joined.dropna(subset=["grid_id"])
    joined["grid_id"] = joined["grid_id"].astype(int)
    grid_means = joined.groupby("grid_id")[score_cols].mean()
    return grid_means


# ── Analysis ──────────────────────────────────────────────────────────────────

def run_analysis(gdf: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> tuple:
    """
    Returns (scores_df, building_stats_df, pairwise_rho, grid_rho_df).
    scores_df: one column per variant, one row per building.
    """
    scores = {}
    for label, w_area, w_height in WEIGHT_VARIANTS:
        scores[label] = recompute_score(gdf, w_area, w_height)
        logging.info("  Computed scores for %s", label)
    scores_df = pd.DataFrame(scores, index=gdf.index)

    # Building-level stats
    baseline = scores_df[BASELINE_LABEL]
    rows = []
    for label in scores_df.columns:
        s = scores_df[label]
        rho, p = stats.spearmanr(s, baseline)
        n_hp = int((s > Q66_THRESHOLD).sum())
        rows.append({
            "variant":         label,
            "mean_score":      float(s.mean()),
            "std_score":       float(s.std()),
            "n_high_potential": n_hp,
            "spearman_rho_vs_baseline": float(rho),
            "spearman_p_vs_baseline":   float(p),
        })
    bldg_stats = pd.DataFrame(rows)

    # Pairwise ρ matrix
    labels = list(scores_df.columns)
    pairwise = pd.DataFrame(index=labels, columns=labels, dtype=float)
    for l1 in labels:
        for l2 in labels:
            rho, _ = stats.spearmanr(scores_df[l1], scores_df[l2])
            pairwise.loc[l1, l2] = rho

    # Grid-level ρ vs baseline
    logging.info("  Computing grid-level scores…")
    score_cols = list(scores_df.columns)
    # Attach variant scores to gdf temporarily
    gdf_tmp = gdf[["geometry"]].copy()
    for col in score_cols:
        gdf_tmp[col] = scores_df[col].values
    grid_means = build_grid_scores(gdf_tmp, grid, score_cols)

    baseline_grid = grid_means[BASELINE_LABEL]
    grid_rows = []
    for label in score_cols:
        rho, p = stats.spearmanr(grid_means[label], baseline_grid)
        grid_rows.append({
            "variant": label,
            "grid_spearman_rho_vs_baseline": float(rho),
            "grid_spearman_p_vs_baseline":   float(p),
        })
    grid_rho_df = pd.DataFrame(grid_rows)

    return scores_df, bldg_stats, pairwise, grid_rho_df


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_results(
    scores_df: pd.DataFrame,
    pairwise: pd.DataFrame,
    figure_dir: Path,
) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # ── Panel (a): KDE distributions ─────────────────────────────────────────
    ax = axes[0]
    x_grid = np.linspace(0, 100, 500)
    for (label, *_), color in zip(WEIGHT_VARIANTS, VARIANT_COLORS):
        # find matching column (label may have ✓ appended)
        col = [c for c in scores_df.columns if c.startswith(label.split(":")[0])][0]
        vals = scores_df[col].dropna().values
        kde = gaussian_kde(vals, bw_method=0.08)
        lw = 2.5 if col == BASELINE_LABEL else 1.5
        ls = "-" if col == BASELINE_LABEL else "--"
        ax.plot(x_grid, kde(x_grid), color=color, linewidth=lw, linestyle=ls,
                label=col.replace(" ✓", " (baseline)"))
    ax.axvline(Q66_THRESHOLD, color="gray", linewidth=1.0, linestyle=":", label=f"q66 = {Q66_THRESHOLD:.1f}")
    ax.set_xlabel("solar_potential_score", fontsize=10)
    ax.set_ylabel("Density", fontsize=10)
    ax.set_title("(a) Score distributions by weight variant\n(n = 18,855 buildings)", fontsize=11)
    ax.legend(fontsize=8)
    ax.grid(axis="y", linewidth=0.4, alpha=0.4)

    # ── Panel (b): Pairwise ρ heatmap ─────────────────────────────────────────
    ax = axes[1]
    labels = list(pairwise.index)
    mat = pairwise.values.astype(float)
    norm = mcolors.Normalize(vmin=0.95, vmax=1.0)
    im = ax.imshow(mat, aspect="auto", cmap="YlOrRd", norm=norm)
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    short = [l.split(":")[0] + l[l.index(":")+1:] for l in labels]
    ax.set_xticklabels(short, rotation=25, ha="right", fontsize=8)
    ax.set_yticklabels(short, fontsize=8)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, f"{mat[i,j]:.4f}", ha="center", va="center",
                    fontsize=8.5, fontweight="bold" if i == j else "normal")
    plt.colorbar(im, ax=ax, label="Spearman ρ", shrink=0.8)
    ax.set_title("(b) Pairwise rank correlation matrix\n(building-level scores)", fontsize=11)

    plt.suptitle(
        "Weight sensitivity analysis — Changsha urban core solar screening",
        fontsize=12, y=1.02,
    )
    plt.tight_layout()
    out = figure_dir / "fig_weight_sensitivity.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()
    logging.info("Saved figure: %s", out)


# ── Results table ─────────────────────────────────────────────────────────────

def print_results(bldg_stats: pd.DataFrame, pairwise: pd.DataFrame, grid_rho_df: pd.DataFrame) -> None:
    print("\n" + "=" * 76)
    print("  Weight Sensitivity — Building-level Stats")
    print("=" * 76)
    print(f"  {'Variant':<22} {'Mean':>7} {'Std':>6} {'N high-pot':>11} "
          f"{'ρ vs W2':>9} {'p':>12}")
    print("-" * 76)
    for _, row in bldg_stats.iterrows():
        print(f"  {row['variant']:<22} {row['mean_score']:>7.3f} {row['std_score']:>6.3f} "
              f"{int(row['n_high_potential']):>11} {row['spearman_rho_vs_baseline']:>+9.4f} "
              f"{row['spearman_p_vs_baseline']:>12.4e}")
    print("=" * 76)

    print("\n  Grid-level Spearman ρ vs baseline (W2):")
    for _, row in grid_rho_df.iterrows():
        print(f"    {row['variant']:<24} ρ = {row['grid_spearman_rho_vs_baseline']:+.4f}  "
              f"p = {row['grid_spearman_p_vs_baseline']:.4e}")

    print("\n  Pairwise ρ matrix (building-level):")
    labels = list(pairwise.index)
    header = "  " + " " * 22 + "  ".join(f"{'W'+l.split('W')[1].split(':')[0]:>8}" for l in labels)
    print(header)
    for i, l1 in enumerate(labels):
        row_str = f"  {l1:<22} "
        row_str += "  ".join(f"{pairwise.loc[l1, l2]:>8.4f}" for l2 in labels)
        print(row_str)
    print()


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input",      required=True)
    p.add_argument("--grid",       required=True)
    p.add_argument("--output_dir", default="outputs/sensitivity/")
    p.add_argument("--figure_dir", default="figure/")
    return p.parse_args()


def main():
    setup_logging()
    args = parse_args()
    output_dir = Path(args.output_dir)
    figure_dir = Path(args.figure_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    logging.info("Loading buildings: %s", args.input)
    gdf = gpd.read_file(args.input)
    logging.info("  %d buildings", len(gdf))

    logging.info("Loading grid: %s", args.grid)
    grid = gpd.read_file(args.grid)
    if gdf.crs != grid.crs:
        grid = grid.to_crs(gdf.crs)

    scores_df, bldg_stats, pairwise, grid_rho_df = run_analysis(gdf, grid)

    print_results(bldg_stats, pairwise, grid_rho_df)

    # Merge stats + grid ρ for CSV output
    merged = bldg_stats.merge(grid_rho_df, on="variant")
    out_csv = output_dir / "weight_sensitivity_results.csv"
    merged.to_csv(out_csv, index=False, float_format="%.6f")
    logging.info("Saved CSV: %s", out_csv)

    # Pairwise matrix CSV
    pairwise_csv = output_dir / "weight_sensitivity_pairwise_rho.csv"
    pairwise.to_csv(pairwise_csv, float_format="%.6f")
    logging.info("Saved pairwise CSV: %s", pairwise_csv)

    plot_results(scores_df, pairwise, figure_dir)
    logging.info("Done.")


if __name__ == "__main__":
    main()
