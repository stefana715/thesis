#!/usr/bin/env python3
"""
benchmark_robustness.py

Stratified spatial robustness test for the pvlib benchmark validation.

Design
------
- From all occupied 500 m grid cells, filter to those with 15–50 buildings
  (fallback: 10–80 if too few eligible grids).
- Rank eligible grids by mean solar_potential_score and divide into 5 equal
  strata (Q1 = lowest scores … Q5 = highest scores).
- Randomly sample 4 grid cells per stratum (seed=42) → 20 grids total.
- For each grid: spatial join buildings, compute pvlib reference yield using
  the same parameters as the primary benchmark, compute Spearman ρ between
  pvlib yield rank and proxy solar_potential_score rank.
- Report: per-grid ρ, stratum summary statistics (mean, min, max, std),
  overall summary.
- Output: CSV + strip/box plot.

Usage
-----
    python src/validation/benchmark_robustness.py \
        --input      data/processed/buildings_changsha_urban_core_solar_baseline.geojson \
        --grid       data/processed/grid_changsha_urban_core_solar_baseline.geojson \
        --output_dir outputs/validation/ \
        --figure_dir figure/
"""

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pvlib
from scipy import stats

# ── Constants (identical to primary benchmark) ────────────────────────────────

LATITUDE        = 28.228
LONGITUDE       = 112.939
ALTITUDE        = 50.0
TIMEZONE        = "Asia/Shanghai"

ROOF_COVERAGE     = 0.65
PANEL_EFF         = 0.20
PERFORMANCE_RATIO = 0.80
SHADING_RADIUS    = 50.0
SHADING_COEFF     = 0.1
SHADING_FLOOR     = 0.5

BLDG_MIN, BLDG_MAX   = 15, 50
BLDG_MIN_FB, BLDG_MAX_FB = 10, 80   # fallback range
N_STRATA             = 5
SAMPLE_PER_STRATUM   = 4
RANDOM_SEED          = 42

STRATUM_LABELS = {1: "Q1 (low)", 2: "Q2", 3: "Q3", 4: "Q4", 5: "Q5 (high)"}
STRATUM_COLORS = ["#2166ac", "#74add1", "#fee08b", "#f46d43", "#d73027"]


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


# ── pvlib ─────────────────────────────────────────────────────────────────────

def annual_clearsky_poa() -> float:
    times = pd.date_range(
        start="2019-01-01 00:00", end="2019-12-31 23:00", freq="h", tz=TIMEZONE
    )
    location = pvlib.location.Location(
        latitude=LATITUDE, longitude=LONGITUDE, altitude=ALTITUDE, tz=TIMEZONE
    )
    clearsky = location.get_clearsky(times, model="ineichen")
    annual_poa = float(clearsky["ghi"].fillna(0).sum())
    logging.info("Annual clear-sky POA (flat roof): %.1f Wh/m²", annual_poa)
    return annual_poa


# ── Shading ───────────────────────────────────────────────────────────────────

def compute_shading_factors(
    gdf_zone: gpd.GeoDataFrame,
    radius: float = SHADING_RADIUS,
    coeff: float = SHADING_COEFF,
    floor: float = SHADING_FLOOR,
) -> pd.Series:
    gdf_proj = gdf_zone.to_crs(gdf_zone.estimate_utm_crs()).copy()
    gdf_proj["height"] = pd.to_numeric(
        gdf_proj["height_proxy_m"], errors="coerce"
    ).fillna(6.0)
    centroids = gdf_proj.geometry.centroid
    heights = gdf_proj["height"].values
    idx_list = list(gdf_proj.index)
    shading_factors = []

    for i in range(len(idx_list)):
        cx, cy = centroids.iloc[i].x, centroids.iloc[i].y
        own_h = heights[i]
        factor = 1.0
        for j in range(len(idx_list)):
            if i == j:
                continue
            nx, ny = centroids.iloc[j].x, centroids.iloc[j].y
            dist = ((cx - nx) ** 2 + (cy - ny) ** 2) ** 0.5
            if dist > radius:
                continue
            delta_h = heights[j] - own_h
            if delta_h <= 0:
                continue
            reduction = coeff * delta_h / max(dist, 0.1)
            factor *= max(floor, 1.0 - reduction)
        shading_factors.append(max(floor, factor))

    return pd.Series(shading_factors, index=gdf_zone.index, name="shading_factor")


# ── Yield ─────────────────────────────────────────────────────────────────────

def compute_pvlib_yield(
    gdf_zone: gpd.GeoDataFrame,
    annual_poa: float,
    roof_coverage: float = ROOF_COVERAGE,
    radius: float = SHADING_RADIUS,
    coeff: float = SHADING_COEFF,
) -> gpd.GeoDataFrame:
    gdf = gdf_zone.copy()
    if "footprint_area_m2" not in gdf.columns or gdf["footprint_area_m2"].isna().all():
        gdf["footprint_area_m2"] = gdf.to_crs(gdf.estimate_utm_crs()).geometry.area
    gdf["footprint_area_m2"] = pd.to_numeric(
        gdf["footprint_area_m2"], errors="coerce"
    ).fillna(50.0)
    gdf["shading_factor"] = compute_shading_factors(gdf, radius=radius, coeff=coeff)
    roof_area = gdf["footprint_area_m2"] * roof_coverage
    gdf["pvlib_yield_kwh"] = (
        roof_area * gdf["shading_factor"] * PANEL_EFF * annual_poa * PERFORMANCE_RATIO / 1000.0
    )
    return gdf


# ── Grid selection ────────────────────────────────────────────────────────────

def select_stratified_grids(grid: gpd.GeoDataFrame) -> pd.DataFrame:
    """Return a DataFrame of 20 selected grid rows with stratum labels."""
    for lo, hi in [(BLDG_MIN, BLDG_MAX), (BLDG_MIN_FB, BLDG_MAX_FB)]:
        eligible = grid[
            (grid["building_count"] >= lo) & (grid["building_count"] <= hi)
        ].copy()
        if len(eligible) >= N_STRATA * SAMPLE_PER_STRATUM:
            logging.info(
                "Eligible grids (%d–%d buildings): %d", lo, hi, len(eligible)
            )
            break
    else:
        raise RuntimeError("Not enough eligible grids even with relaxed thresholds.")

    # Quintile strata by mean score
    eligible["stratum"] = pd.qcut(
        eligible["mean_score"], q=N_STRATA, labels=list(range(1, N_STRATA + 1))
    ).astype(int)

    rng = np.random.default_rng(RANDOM_SEED)
    selected_parts = []
    for s in range(1, N_STRATA + 1):
        pool = eligible[eligible["stratum"] == s]
        n = min(SAMPLE_PER_STRATUM, len(pool))
        chosen_idx = rng.choice(len(pool), size=n, replace=False)
        selected_parts.append(pool.iloc[chosen_idx])

    selected = pd.concat(selected_parts).reset_index(drop=True)
    logging.info("Selected %d grids across %d strata", len(selected), N_STRATA)
    return selected


# ── Per-grid correlation ──────────────────────────────────────────────────────

def process_grid(
    grid_row: pd.Series,
    bldg: gpd.GeoDataFrame,
    grid_geom: gpd.GeoDataFrame,
    annual_poa: float,
):
    gid = int(grid_row["grid_id"])
    cell = grid_geom[grid_geom["grid_id"] == gid]
    zone_bldg = gpd.sjoin(
        bldg, cell[["grid_id", "geometry"]], how="inner", predicate="intersects"
    ).drop(columns=["index_right"], errors="ignore")

    n = len(zone_bldg)
    if n < 3:
        logging.warning("  grid_id=%d: only %d buildings — skipping", gid, n)
        return None

    zone_bldg = compute_pvlib_yield(zone_bldg, annual_poa)
    rho, p = stats.spearmanr(
        zone_bldg["solar_potential_score"], zone_bldg["pvlib_yield_kwh"]
    )
    return {
        "grid_id":   gid,
        "stratum":   int(grid_row["stratum"]),
        "n":         n,
        "mean_score": float(grid_row["mean_score"]),
        "spearman_rho": float(rho),
        "spearman_p":   float(p),
    }


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_robustness(results_df: pd.DataFrame, figure_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))

    # Boxplot per stratum
    strata = sorted(results_df["stratum"].unique())
    data_by_stratum = [
        results_df[results_df["stratum"] == s]["spearman_rho"].values for s in strata
    ]
    bp = ax.boxplot(
        data_by_stratum,
        positions=strata,
        widths=0.4,
        patch_artist=True,
        medianprops=dict(color="black", linewidth=1.5),
        flierprops=dict(marker="o", markersize=4),
        zorder=2,
    )
    for patch, color in zip(bp["boxes"], STRATUM_COLORS):
        patch.set_facecolor(color)
        patch.set_alpha(0.5)

    # Strip plot (individual points with jitter)
    rng = np.random.default_rng(0)
    for s, color in zip(strata, STRATUM_COLORS):
        sub = results_df[results_df["stratum"] == s]["spearman_rho"].values
        jitter = rng.uniform(-0.15, 0.15, size=len(sub))
        ax.scatter(
            np.full(len(sub), s) + jitter,
            sub,
            color=color,
            edgecolors="white",
            linewidths=0.5,
            s=55,
            zorder=3,
            label=STRATUM_LABELS[s],
        )

    ax.axhline(0, color="gray", linewidth=0.6, linestyle="--")
    ax.set_xticks(strata)
    ax.set_xticklabels([STRATUM_LABELS[s] for s in strata], fontsize=9)
    ax.set_xlabel("Score stratum (mean solar_potential_score quintile)", fontsize=10)
    ax.set_ylabel("Spearman ρ  (proxy vs. pvlib yield)", fontsize=10)
    ax.set_title(
        f"Benchmark robustness: Spearman ρ across 20 stratified 500 m grids\n"
        f"(4 grids per quintile, seed=42, n={len(results_df)} grids total)",
        fontsize=11,
    )
    ax.set_ylim(-0.1, 1.15)
    ax.grid(axis="y", linewidth=0.4, alpha=0.5)
    plt.tight_layout()
    out = figure_dir / "fig_benchmark_robustness.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()
    logging.info("Saved robustness plot: %s", out)


# ── Summary table ─────────────────────────────────────────────────────────────

def format_summary(results_df: pd.DataFrame) -> str:
    lines = [
        "",
        "=" * 72,
        "  Benchmark Robustness — Spearman ρ Summary by Stratum",
        "=" * 72,
        f"  {'Stratum':<18} {'N grids':>8}  {'Mean ρ':>8}  {'Min ρ':>7}  {'Max ρ':>7}  {'Std ρ':>7}",
        "-" * 72,
    ]
    for s in sorted(results_df["stratum"].unique()):
        sub = results_df[results_df["stratum"] == s]["spearman_rho"]
        lines.append(
            f"  {STRATUM_LABELS[s]:<18} {len(sub):>8}  "
            f"{sub.mean():>+8.4f}  {sub.min():>+7.4f}  {sub.max():>+7.4f}  {sub.std():>7.4f}"
        )
    lines.append("-" * 72)
    all_rho = results_df["spearman_rho"]
    lines.append(
        f"  {'OVERALL':<18} {len(all_rho):>8}  "
        f"{all_rho.mean():>+8.4f}  {all_rho.min():>+7.4f}  {all_rho.max():>+7.4f}  {all_rho.std():>7.4f}"
    )
    lines += ["=" * 72, ""]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input",      required=True)
    p.add_argument("--grid",       required=True)
    p.add_argument("--output_dir", default="outputs/validation/")
    p.add_argument("--figure_dir", default="figure/")
    return p.parse_args()


def main():
    setup_logging()
    args = parse_args()
    output_dir = Path(args.output_dir)
    figure_dir = Path(args.figure_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    logging.info("Loading buildings…")
    bldg = gpd.read_file(args.input)
    logging.info("Loading grid…")
    grid = gpd.read_file(args.grid)
    if bldg.crs != grid.crs:
        grid = grid.to_crs(bldg.crs)

    annual_poa = annual_clearsky_poa()
    selected   = select_stratified_grids(grid)

    results = []
    for _, row in selected.iterrows():
        logging.info(
            "  Processing grid_id=%d  stratum=Q%d  n_bldg=%d  mean_score=%.2f",
            row["grid_id"], row["stratum"], row["building_count"], row["mean_score"],
        )
        res = process_grid(row, bldg, grid, annual_poa)
        if res:
            results.append(res)

    results_df = pd.DataFrame(results)

    print(format_summary(results_df))

    # Per-grid table
    print("\nPer-grid results:")
    print(results_df[["stratum", "grid_id", "n", "mean_score", "spearman_rho", "spearman_p"]]
          .sort_values(["stratum", "grid_id"])
          .to_string(index=False, float_format=lambda x: f"{x:+.4f}"))

    csv_out = output_dir / "benchmark_robustness_results.csv"
    results_df.to_csv(csv_out, index=False, float_format="%.6f")
    logging.info("Saved CSV: %s", csv_out)

    plot_robustness(results_df, figure_dir)
    logging.info("Done.")


if __name__ == "__main__":
    main()
