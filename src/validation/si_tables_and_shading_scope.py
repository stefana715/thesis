#!/usr/bin/env python3
"""
si_tables_and_shading_scope.py

Produces the two Supplementary Material tables, SI Figure S4, and the
density-stratified shading-scope analysis used in the Limitations section.

Outputs
-------
outputs/validation/SI_tableA_area_confound.csv
outputs/validation/SI_tableB_height_degeneracy.csv
outputs/validation/SI_shading_scope_by_density.csv
outputs/validation/SI_shading_scope_per_grid.csv
figure/figS4_modal_height_share_vs_benchmark_rho.png   (300 dpi)

Table A and Table B are assembled from the CSVs written by
`benchmark_area_confound.py` and `proxy_composition_diagnostics.py`; run those
first. The shading-scope analysis is computed here from the building layer.

Shading scope
-------------
The benchmark's shading term fires for building i only if some neighbour j
satisfies  d_ij <= 50 m  AND  h_j > h_i  (benchmark_robustness.py:112-119).
This script evaluates that trigger condition over ALL 18,855 urban-core
buildings under two neighbour definitions:

  * global      — true nearest neighbours, ignoring grid boundaries
  * within-grid — only buildings sharing the same 500 m cell, which is what the
                  benchmark actually does (it spatially joins one cell at a time)

The gap between the two is the benchmark's edge-effect bias.

Usage
-----
    python src/validation/si_tables_and_shading_scope.py \
        --input      data/processed/buildings_changsha_urban_core_solar_baseline.geojson \
        --grid       data/processed/grid_changsha_urban_core_solar_baseline.geojson \
        --output_dir outputs/validation/ \
        --figure_dir figure/
"""

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from scipy.spatial import cKDTree

SHADING_RADIUS = 50.0     # benchmark_robustness.py:51
GRID_SIZE_M = 500
N_DENSITY_BINS = 5

# Single-series ink for the SI scatter (print, light surface only)
MARK = "#1f4e79"
MARK_HI = "#b03a2e"
INK = "#1a1a1a"
INK_MUTED = "#6b6b6b"
GRIDLINE = "#d9d9d9"


def setup_logging():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(message)s")


# ══════════════════════════════════════════════════════════════════════════════
# SI tables
# ══════════════════════════════════════════════════════════════════════════════

def build_table_a(confound_csv: Path) -> pd.DataFrame:
    c = pd.read_csv(confound_csv)
    out = pd.DataFrame({
        "grid_id":        c["grid_id"].astype(int),
        "stratum":        c["stratum"].astype(int),
        "n":              c["n"].astype(int),
        "headline_rho":   c["rho_headline"],
        "unit_area_rho":  c["rho_a_unit_area"],
        "unit_area_p":    c["p_a_unit_area"],
        "partial_rho":    c["rho_b_partial"],
        "partial_p":      c["p_b_partial"],
        "area_only_rho":  c["rho_c_area_only"],
        "score_area_rho": c["rho_score_vs_area"],
        "shaded_count":   c["n_shaded"].astype(int),
        "shaded_pct":     100.0 * c["frac_shaded"],
    })
    return out.sort_values(["stratum", "grid_id"]).reset_index(drop=True)


def build_table_b(zone_csv: Path, confound_csv: Path) -> pd.DataFrame:
    z = pd.read_csv(zone_csv)
    c = pd.read_csv(confound_csv)[["grid_id", "rho_headline", "frac_shaded"]]
    m = z.merge(c, on="grid_id", how="left")
    out = pd.DataFrame({
        "grid_id":        m["grid_id"].astype(int),
        "stratum":        m["stratum"].astype(int),
        "n":              m["n"].astype(int),
        "unique_heights": m["n_unique_height"].astype(int),
        "modal_height":   m["modal_height_m"],
        "modal_share":    m["modal_height_share_pct"],
        "h_min":          m["height_min"],
        "h_max":          m["height_max"],
        "shaded_pct":     100.0 * m["frac_shaded"],
        "benchmark_rho":  m["rho_headline"],
    })
    return out.sort_values(["stratum", "grid_id"]).reset_index(drop=True)


def plot_figs4(tb: pd.DataFrame, rho: float, p: float, out_path: Path) -> None:
    """Relationship scatter: height degeneracy vs benchmark agreement."""
    fig, ax = plt.subplots(figsize=(6.4, 4.6))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    x = tb["modal_share"].values
    y = tb["benchmark_rho"].values
    # The two zones the paper discusses as the failure boundary
    hi = tb["grid_id"].isin([807, 883]).values

    ax.scatter(x[~hi], y[~hi], s=58, color=MARK, alpha=0.85,
               edgecolors="white", linewidths=0.8, zorder=3)
    ax.scatter(x[hi], y[hi], s=78, color=MARK_HI, alpha=0.95,
               edgecolors="white", linewidths=0.8, zorder=4)

    for gid, xi, yi in zip(tb["grid_id"][hi], x[hi], y[hi]):
        ax.annotate(f"grid {int(gid)}", (xi, yi), textcoords="offset points",
                    xytext=(9, -3), fontsize=8.5, color=MARK_HI)

    ax.set_xlabel("Share of buildings at the modal height value (%)", fontsize=10, color=INK)
    ax.set_ylabel(r"Benchmark Spearman $\rho$", fontsize=10, color=INK)
    # pad clears the subtitle line placed just above the axes
    ax.set_title("Benchmark agreement tracks height-proxy degeneracy",
                 fontsize=11.5, color=INK, pad=26, loc="left")
    ax.text(0.0, 1.012,
            f"20 stratified 500 m zones   |   Spearman ρ = {rho:+.3f}, p = {p:.1e}",
            transform=ax.transAxes, fontsize=8.8, color=INK_MUTED, va="bottom")

    ax.set_xlim(38, 104)
    ax.set_ylim(0.35, 1.045)
    ax.grid(True, linewidth=0.5, color=GRIDLINE, alpha=0.9, zorder=0)
    ax.set_axisbelow(True)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color(GRIDLINE)
    ax.tick_params(colors=INK_MUTED, labelsize=9)

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close()
    logging.info("Saved SI Figure S4: %s", out_path)


# ══════════════════════════════════════════════════════════════════════════════
# Shading scope over all occupied grids
# ══════════════════════════════════════════════════════════════════════════════

def shading_scope(bldg: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> tuple:
    utm = bldg.estimate_utm_crs()
    proj = bldg.to_crs(utm).copy()
    proj["geometry"] = proj.geometry.centroid
    g = grid.to_crs(utm)

    j = gpd.sjoin(proj[["geometry", "height_proxy_m"]], g[["grid_id", "geometry"]],
                  how="left", predicate="within").drop(columns=["index_right"], errors="ignore")
    j = j.dropna(subset=["grid_id"]).copy()
    j["grid_id"] = j["grid_id"].astype(int)
    j["h"] = pd.to_numeric(j["height_proxy_m"], errors="coerce").fillna(6.0)

    xy = np.c_[j.geometry.x.values, j.geometry.y.values]
    h = j["h"].values
    gid = j["grid_id"].values
    n = len(j)
    logging.info("Shading scope over %d buildings in %d occupied cells",
                 n, len(np.unique(gid)))

    tree = cKDTree(xy)

    # Nearest other building (k=2: self + nearest)
    dists, _ = tree.query(xy, k=2)
    nn_dist = dists[:, 1]

    # Trigger condition: any neighbour within radius that is strictly taller
    neigh = tree.query_ball_point(xy, r=SHADING_RADIUS)
    trig_global = np.zeros(n, dtype=bool)
    trig_within = np.zeros(n, dtype=bool)
    n_neigh = np.zeros(n, dtype=int)
    for i, idxs in enumerate(neigh):
        others = [k for k in idxs if k != i]
        n_neigh[i] = len(others)
        if not others:
            continue
        oth = np.asarray(others)
        taller = h[oth] > h[i]
        trig_global[i] = bool(taller.any())
        same = gid[oth] == gid[i]
        trig_within[i] = bool((taller & same).any())

    per_b = pd.DataFrame({
        "grid_id": gid, "h": h, "nn_dist": nn_dist,
        "n_neigh_50m": n_neigh,
        "trig_global": trig_global, "trig_within": trig_within,
    })

    cell_km2 = (GRID_SIZE_M / 1000.0) ** 2
    per_grid = per_b.groupby("grid_id").agg(
        n_buildings=("h", "size"),
        mean_nn_dist_m=("nn_dist", "mean"),
        median_nn_dist_m=("nn_dist", "median"),
        mean_neighbours_50m=("n_neigh_50m", "mean"),
        pct_trigger_global=("trig_global", lambda s: 100.0 * s.mean()),
        pct_trigger_within=("trig_within", lambda s: 100.0 * s.mean()),
        n_unique_height=("h", "nunique"),
    ).reset_index()
    per_grid["density_per_km2"] = per_grid["n_buildings"] / cell_km2

    # Quintiles of building density
    per_grid["density_bin"] = pd.qcut(
        per_grid["density_per_km2"].rank(method="first"),
        q=N_DENSITY_BINS, labels=list(range(1, N_DENSITY_BINS + 1))
    ).astype(int)

    rows = []
    for b in range(1, N_DENSITY_BINS + 1):
        sub = per_grid[per_grid["density_bin"] == b]
        gids = set(sub["grid_id"])
        bsub = per_b[per_b["grid_id"].isin(gids)]
        rows.append({
            "density_bin": b,
            "n_grids": len(sub),
            "n_buildings": len(bsub),
            "density_min_per_km2": float(sub["density_per_km2"].min()),
            "density_median_per_km2": float(sub["density_per_km2"].median()),
            "density_max_per_km2": float(sub["density_per_km2"].max()),
            "mean_nn_dist_m": float(bsub["nn_dist"].mean()),
            "median_nn_dist_m": float(bsub["nn_dist"].median()),
            "mean_neighbours_within_50m": float(bsub["n_neigh_50m"].mean()),
            "pct_buildings_trigger_global": 100.0 * float(bsub["trig_global"].mean()),
            "pct_buildings_trigger_within_grid": 100.0 * float(bsub["trig_within"].mean()),
            "median_unique_heights_per_grid": float(sub["n_unique_height"].median()),
            "pct_grids_single_height": 100.0 * float((sub["n_unique_height"] == 1).mean()),
        })
    by_bin = pd.DataFrame(rows)

    overall = {
        "n_buildings": n,
        "mean_nn_dist_m": float(per_b["nn_dist"].mean()),
        "median_nn_dist_m": float(per_b["nn_dist"].median()),
        "pct_trigger_global": 100.0 * float(per_b["trig_global"].mean()),
        "pct_trigger_within_grid": 100.0 * float(per_b["trig_within"].mean()),
        "edge_effect_gap_pp": 100.0 * float(per_b["trig_global"].mean() - per_b["trig_within"].mean()),
        "pct_no_neighbour_within_50m": 100.0 * float((per_b["n_neigh_50m"] == 0).mean()),
    }
    return by_bin, per_grid, overall


# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--grid", required=True)
    p.add_argument("--output_dir", default="outputs/validation/")
    p.add_argument("--figure_dir", default="figure/")
    return p.parse_args()


def main():
    setup_logging()
    args = parse_args()
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    figdir = Path(args.figure_dir)

    confound_csv = out / "benchmark_area_confound_results.csv"
    zone_csv = out / "diag_zone_height_diversity.csv"
    for f in [confound_csv, zone_csv]:
        if not f.exists():
            raise FileNotFoundError(f"Missing prerequisite: {f}")

    ta = build_table_a(confound_csv)
    tb = build_table_b(zone_csv, confound_csv)
    ta.to_csv(out / "SI_tableA_area_confound.csv", index=False, float_format="%.6f")
    tb.to_csv(out / "SI_tableB_height_degeneracy.csv", index=False, float_format="%.6f")

    print("\n" + "=" * 108)
    print("  SI TABLE A — area-confound analysis (20 stratified zones)")
    print("=" * 108)
    print(ta.to_string(index=False, na_rep="n/a",
                       float_format=lambda v: f"{v:.4f}"))

    print("\n" + "=" * 108)
    print("  SI TABLE B — height degeneracy vs benchmark agreement")
    print("=" * 108)
    print(tb.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    rho, p = stats.spearmanr(tb["modal_share"], tb["benchmark_rho"])
    rho2, p2 = stats.spearmanr(tb["unique_heights"], tb["benchmark_rho"])
    rho3, p3 = stats.spearmanr(tb["shaded_pct"], tb["benchmark_rho"])
    print(f"\n  Spearman(modal_share,    benchmark_rho) = {rho:+.6f}   p = {p:.6e}")
    print(f"  Spearman(unique_heights, benchmark_rho) = {rho2:+.6f}   p = {p2:.6e}")
    print(f"  Spearman(shaded_pct,     benchmark_rho) = {rho3:+.6f}   p = {p3:.6e}")

    plot_figs4(tb, float(rho), float(p),
               figdir / "figS4_modal_height_share_vs_benchmark_rho.png")

    # ── Shading scope ────────────────────────────────────────────────────────
    bldg = gpd.read_file(args.input)
    grid = gpd.read_file(args.grid)
    if bldg.crs != grid.crs:
        grid = grid.to_crs(bldg.crs)

    by_bin, per_grid, overall = shading_scope(bldg, grid)
    by_bin.to_csv(out / "SI_shading_scope_by_density.csv", index=False, float_format="%.6f")
    per_grid.to_csv(out / "SI_shading_scope_per_grid.csv", index=False, float_format="%.6f")

    print("\n" + "=" * 108)
    print("  SHADING SCOPE — all occupied 500 m cells, by building-density quintile")
    print("=" * 108)
    print(f"  {'bin':>4} {'grids':>6} {'bldgs':>7} {'density range /km2':>22} "
          f"{'mean NN':>9} {'nb<50m':>8} {'trig glob':>10} {'trig grid':>10} "
          f"{'med uniq h':>11} {'1-height grids':>15}")
    print("-" * 108)
    for _, r in by_bin.iterrows():
        rng = f"{r['density_min_per_km2']:.0f}-{r['density_max_per_km2']:.0f}"
        print(f"  {int(r['density_bin']):>4} {int(r['n_grids']):>6} {int(r['n_buildings']):>7} "
              f"{rng:>22} {r['mean_nn_dist_m']:>8.2f}m {r['mean_neighbours_within_50m']:>8.2f} "
              f"{r['pct_buildings_trigger_global']:>9.2f}% {r['pct_buildings_trigger_within_grid']:>9.2f}% "
              f"{r['median_unique_heights_per_grid']:>11.1f} {r['pct_grids_single_height']:>14.1f}%")
    print("-" * 108)
    print("  OVERALL (all 18,855 urban-core buildings):")
    for k, v in overall.items():
        print(f"    {k:<38} {v:>12.4f}")

    logging.info("Done.")


if __name__ == "__main__":
    main()
