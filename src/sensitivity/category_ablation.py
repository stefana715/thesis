#!/usr/bin/env python3
"""
category_ablation.py

Category factor ablation for the Changsha solar screening baseline.

Tests whether removing the building-category adjustment changes the
spatial screening pattern.

Conditions
----------
  Baseline  — with category adjustment
              commercial × 1.10, residential × 1.00, mixed_unknown × 0.95
  Ablated   — without category adjustment (all buildings × 1.00)

Both use the stored area_score / height_score and baseline weights (0.65/0.35).

Metrics
-------
- Building-level Spearman ρ between conditions
- Grid-level (500 m) Spearman ρ of grid mean rankings
- Buildings that change high-potential classification (using q66 = 45.513)
- Mean absolute score difference (overall and per category)

Outputs
-------
  outputs/sensitivity/category_ablation_results.csv
  figure/fig_category_ablation.png  (300 dpi, 2-panel)

Usage
-----
    python src/sensitivity/category_ablation.py \
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
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd
from scipy import stats

# ── Constants ─────────────────────────────────────────────────────────────────

W_AREA, W_HEIGHT = 0.65, 0.35
CATEGORY_MULTIPLIERS = {"commercial": 1.10, "residential": 1.00, "mixed_unknown": 0.95}
Q66_THRESHOLD = 45.513

CAT_COLORS  = {"commercial": "#e6550d", "residential": "#3182bd", "mixed_unknown": "#756bb1"}
CHANGE_COLORS = {
    "HP → non-HP": "#d73027",
    "non-HP → HP": "#1a9850",
    "unchanged HP": "#74add1",
    "unchanged non-HP": "#d9d9d9",
}


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
    )


# ── Scoring ───────────────────────────────────────────────────────────────────

def compute_score(gdf: gpd.GeoDataFrame, use_category: bool) -> pd.Series:
    base = W_AREA * gdf["area_score"] + W_HEIGHT * gdf["height_score"]
    if use_category:
        multiplier = gdf["building_category"].map(CATEGORY_MULTIPLIERS).fillna(
            CATEGORY_MULTIPLIERS["mixed_unknown"]
        )
    else:
        multiplier = 1.0
    return (base * multiplier * 100).clip(0, 100)


# ── Grid aggregation ──────────────────────────────────────────────────────────

def grid_mean_scores(
    gdf: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
    cols: list,
) -> pd.DataFrame:
    joined = gpd.sjoin(
        gdf[["geometry"] + cols],
        grid[["grid_id", "geometry"]],
        how="left",
        predicate="within",
    ).drop(columns=["index_right"], errors="ignore")
    joined = joined.dropna(subset=["grid_id"])
    joined["grid_id"] = joined["grid_id"].astype(int)
    return joined.groupby("grid_id")[cols].mean()


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_results(
    gdf: gpd.GeoDataFrame,
    score_with: pd.Series,
    score_without: pd.Series,
    change_label: pd.Series,
    figure_dir: Path,
) -> None:

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # ── Panel (a): Scatter with-category vs without-category ─────────────────
    ax = axes[0]
    for cat, color in CAT_COLORS.items():
        mask = gdf["building_category"] == cat
        n = mask.sum()
        ax.scatter(
            score_without[mask],
            score_with[mask],
            s=2,
            alpha=0.35,
            color=color,
            rasterized=True,
            label=f"{cat} (n={n:,})",
        )
    # Reference line y = x
    lims = [0, 100]
    ax.plot(lims, lims, color="gray", linewidth=0.8, linestyle="--", label="y = x")
    # Mark q66 threshold
    ax.axhline(Q66_THRESHOLD, color="black", linewidth=0.6, linestyle=":", alpha=0.6,
               label=f"q66 = {Q66_THRESHOLD:.1f}")
    ax.axvline(Q66_THRESHOLD, color="black", linewidth=0.6, linestyle=":", alpha=0.6)

    rho, _ = stats.spearmanr(score_with, score_without)
    ax.set_xlabel("Score without category adjustment", fontsize=10)
    ax.set_ylabel("Score with category adjustment (baseline)", fontsize=10)
    ax.set_title(
        f"(a) With vs. without category multiplier\n"
        f"Spearman ρ = {rho:+.4f}  (n = {len(score_with):,})",
        fontsize=11,
    )
    ax.legend(fontsize=8, markerscale=4)
    ax.set_xlim(0, 105)
    ax.set_ylim(0, 105)
    ax.grid(linewidth=0.3, alpha=0.4)

    # ── Panel (b): Classification change histogram by category ────────────────
    ax = axes[1]

    categories_order = ["commercial", "residential", "mixed_unknown"]
    change_types = list(CHANGE_COLORS.keys())
    x = np.arange(len(categories_order))
    width = 0.18

    for k, (ctype, color) in enumerate(CHANGE_COLORS.items()):
        counts = []
        for cat in categories_order:
            mask = (gdf["building_category"] == cat) & (change_label == ctype)
            counts.append(mask.sum())
        offset = (k - (len(change_types) - 1) / 2) * width
        bars = ax.bar(x + offset, counts, width=width, color=color,
                      label=ctype, edgecolor="white", linewidth=0.5)
        # Annotate non-zero bars
        for bar, count in zip(bars, counts):
            if count > 0:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 1,
                    str(count),
                    ha="center", va="bottom", fontsize=7.5,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(categories_order, fontsize=10)
    ax.set_xlabel("Building category", fontsize=10)
    ax.set_ylabel("Number of buildings", fontsize=10)
    ax.set_title(
        "(b) Classification changes by category\n"
        "(HP = score > q66; ablation removes category multiplier)",
        fontsize=11,
    )
    ax.legend(fontsize=8)
    ax.grid(axis="y", linewidth=0.4, alpha=0.4)

    plt.suptitle(
        "Category factor ablation — Changsha urban core solar screening",
        fontsize=12, y=1.02,
    )
    plt.tight_layout()
    out = figure_dir / "fig_category_ablation.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()
    logging.info("Saved figure: %s", out)


# ── Results table ─────────────────────────────────────────────────────────────

def print_results(results: dict) -> None:
    print("\n" + "=" * 60)
    print("  Category Factor Ablation Results")
    print("=" * 60)
    print(f"  Building-level Spearman ρ:          {results['bldg_spearman_rho']:+.4f}")
    print(f"  Building-level p-value:              {results['bldg_spearman_p']:.4e}")
    print(f"  Grid-level Spearman ρ:               {results['grid_spearman_rho']:+.4f}")
    print(f"  Grid-level p-value:                  {results['grid_spearman_p']:.4e}")
    print(f"  Mean absolute score difference:      {results['mean_abs_diff']:.4f}")
    print()
    print(f"  High-potential buildings (baseline): {results['n_hp_baseline']:,}")
    print(f"  High-potential buildings (ablated):  {results['n_hp_ablated']:,}")
    print(f"  HP → non-HP (lost):                  {results['n_hp_to_nonhp']:,}")
    print(f"  non-HP → HP (gained):                {results['n_nonhp_to_hp']:,}")
    print(f"  Total classification changes:        {results['n_changes']:,}")
    print(f"  Change rate:                         {results['change_rate_pct']:.2f}%")
    print()
    print("  Mean absolute score diff by category:")
    for cat, diff in results["mean_abs_diff_by_category"].items():
        print(f"    {cat:<18} {diff:.4f}")
    print("=" * 60)


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

    # ── Compute scores ────────────────────────────────────────────────────────
    score_with    = compute_score(gdf, use_category=True)
    score_without = compute_score(gdf, use_category=False)

    # ── Building-level correlation ────────────────────────────────────────────
    bldg_rho, bldg_p = stats.spearmanr(score_with, score_without)

    # ── Grid-level correlation ────────────────────────────────────────────────
    logging.info("Computing grid-level scores…")
    gdf_tmp = gdf[["geometry", "building_category"]].copy()
    gdf_tmp["score_with"]    = score_with.values
    gdf_tmp["score_without"] = score_without.values
    grid_scores = grid_mean_scores(gdf_tmp, grid, ["score_with", "score_without"])
    grid_rho, grid_p = stats.spearmanr(
        grid_scores["score_with"], grid_scores["score_without"]
    )

    # ── Classification changes ────────────────────────────────────────────────
    hp_with    = score_with    > Q66_THRESHOLD
    hp_without = score_without > Q66_THRESHOLD

    hp_to_nonhp  = (hp_with  & ~hp_without).sum()
    nonhp_to_hp  = (~hp_with &  hp_without).sum()
    n_changes    = int(hp_to_nonhp + nonhp_to_hp)
    change_rate  = n_changes / len(gdf) * 100

    # Change label per building
    def label_change(row):
        w, wo = row["hp_with"], row["hp_without"]
        if w and wo:     return "unchanged HP"
        if not w and not wo: return "unchanged non-HP"
        if w and not wo: return "HP → non-HP"
        return "non-HP → HP"

    change_df = pd.DataFrame({
        "hp_with":    hp_with.values,
        "hp_without": hp_without.values,
        "building_category": gdf["building_category"].values,
    })
    change_label = change_df.apply(label_change, axis=1)

    # ── Score differences ─────────────────────────────────────────────────────
    abs_diff = (score_with - score_without).abs()
    mean_abs_diff = float(abs_diff.mean())
    diff_by_cat = {}
    for cat in ["commercial", "residential", "mixed_unknown"]:
        mask = gdf["building_category"] == cat
        diff_by_cat[cat] = float(abs_diff[mask].mean())

    # ── Collect results ───────────────────────────────────────────────────────
    results = {
        "bldg_spearman_rho":       float(bldg_rho),
        "bldg_spearman_p":         float(bldg_p),
        "grid_spearman_rho":       float(grid_rho),
        "grid_spearman_p":         float(grid_p),
        "mean_abs_diff":           mean_abs_diff,
        "n_hp_baseline":           int(hp_with.sum()),
        "n_hp_ablated":            int(hp_without.sum()),
        "n_hp_to_nonhp":           int(hp_to_nonhp),
        "n_nonhp_to_hp":           int(nonhp_to_hp),
        "n_changes":               n_changes,
        "change_rate_pct":         float(change_rate),
        "mean_abs_diff_by_category": diff_by_cat,
    }

    print_results(results)

    # ── Save CSV ──────────────────────────────────────────────────────────────
    flat = {k: v for k, v in results.items() if not isinstance(v, dict)}
    for cat, val in diff_by_cat.items():
        flat[f"mean_abs_diff_{cat}"] = val
    csv_out = output_dir / "category_ablation_results.csv"
    pd.DataFrame([flat]).to_csv(csv_out, index=False, float_format="%.6f")
    logging.info("Saved CSV: %s", csv_out)

    # ── Plot ──────────────────────────────────────────────────────────────────
    plot_results(gdf, score_with, score_without, change_label, figure_dir)
    logging.info("Done.")


if __name__ == "__main__":
    main()
