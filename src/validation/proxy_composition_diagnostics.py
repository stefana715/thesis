#!/usr/bin/env python3
"""
proxy_composition_diagnostics.py

Read-only diagnostics supporting the revision of the screening-framework paper.

Part A — Height-proxy and score-composition statistics on the urban-core subset
         (18,855 buildings), plus per-zone height diversity for the 20 stratified
         benchmark grids and a detailed profile of grid 807 (the failure case).

Part B — Area-only counterfactual: replace the 0.65/0.35 composite score with a
         1.00/0.00 (area-only) score and quantify how much of the screening
         outcome actually changes, at building / grid / priority-grid level.

Nothing is written except one CSV bundle under --output_dir; no existing file is
modified. Zone selection reuses `benchmark_robustness.select_stratified_grids`
(seed=42) so the 20 zones are identical to the published robustness run.

Notes on comparability
----------------------
* The official grid product (`grid_solar_aggregation.py`) assigns buildings to
  cells by BUILDING CENTROID with predicate="within". `weight_sensitivity.py`
  instead joins the full building POLYGON with predicate="within", which silently
  drops every building straddling a cell boundary. Part B reports the grid-level
  correlation under BOTH conventions so the published number is reproducible and
  the discrepancy is visible.
* `weight_sensitivity.py` compares tier membership against a FIXED absolute
  cutoff (Q66_THRESHOLD = 45.513) even for variants whose score distribution
  shifts. Part B reports that number for reproducibility, and alongside it the
  tier comparison a screening framework actually implies (re-derived q66, and a
  rank-matched top-N set).

Usage
-----
    python src/validation/proxy_composition_diagnostics.py \
        --input      data/processed/buildings_changsha_urban_core_solar_baseline.geojson \
        --grid       data/processed/grid_changsha_urban_core_solar_baseline.geojson \
        --priority   outputs/priority_grids.csv \
        --output_dir outputs/validation/
"""

import argparse
import importlib.util
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import stats

# ── Reuse the published benchmark module (src/ has no __init__.py) ────────────

_ROBUSTNESS_PATH = Path(__file__).resolve().parent / "benchmark_robustness.py"
_spec = importlib.util.spec_from_file_location("benchmark_robustness", _ROBUSTNESS_PATH)
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)

# Constants mirrored from the published scoring / sensitivity code
CATEGORY_MULTIPLIERS = {"commercial": 1.10, "residential": 1.00, "mixed_unknown": 0.95}
Q66_FIXED = 45.513          # weight_sensitivity.py:55 — rounded, fixed
PRIORITY_TOP_FRACTION = 0.20  # planning_metrics.py:78
GRID_SIZE_M = 500

FAILURE_GRID_ID = 807


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s"
    )


def rule(char="=", n=92):
    return char * n


# ══════════════════════════════════════════════════════════════════════════════
# PART A — height proxy & score composition
# ══════════════════════════════════════════════════════════════════════════════

def a1_height_source(bldg: pd.DataFrame) -> pd.DataFrame:
    n = len(bldg)
    vc = bldg["height_proxy_source"].value_counts(dropna=False)
    order = ["raw_height", "building_levels", "building_type_default", "fallback_default"]
    rows = []
    for src in order:
        c = int(vc.get(src, 0))
        rows.append({"height_proxy_source": src, "count": c, "pct": 100.0 * c / n})
    for src in vc.index:
        if src not in order:
            c = int(vc[src])
            rows.append({"height_proxy_source": str(src), "count": c, "pct": 100.0 * c / n})
    rows.append({"height_proxy_source": "TOTAL", "count": n, "pct": 100.0})
    return pd.DataFrame(rows)


def a2_height_values(bldg: pd.DataFrame) -> tuple:
    h = pd.to_numeric(bldg["height_proxy_m"], errors="coerce")
    n = len(h)
    vc = h.value_counts(dropna=False).sort_values(ascending=False)
    top = vc.head(10).reset_index()
    top.columns = ["height_m", "count"]
    top["pct"] = 100.0 * top["count"] / n
    top["cum_pct"] = top["pct"].cumsum()
    q = {
        "n": n,
        "n_unique": int(h.nunique(dropna=True)),
        "min": float(h.min()),
        "q25": float(h.quantile(0.25)),
        "median": float(h.median()),
        "q75": float(h.quantile(0.75)),
        "q95": float(h.quantile(0.95)),
        "max": float(h.max()),
        "mean": float(h.mean()),
        "std": float(h.std()),
    }
    return top, q


def a3_score_components(bldg: pd.DataFrame) -> dict:
    a = pd.to_numeric(bldg["area_score"], errors="coerce")
    hs = pd.to_numeric(bldg["height_score"], errors="coerce")
    base = 0.65 * a + 0.35 * hs
    ca, ch = 0.65 * a, 0.35 * hs
    rho, _ = stats.spearmanr(a, hs)
    return {
        "n": len(a),
        "std_area_score": float(a.std()),
        "std_height_score": float(hs.std()),
        "mean_area_score": float(a.mean()),
        "mean_height_score": float(hs.mean()),
        "std_ratio_height_over_area": float(hs.std() / a.std()),
        "std_weighted_area_term": float(ca.std()),
        "std_weighted_height_term": float(ch.std()),
        "std_ratio_weighted": float(ch.std() / ca.std()),
        "var_base_score": float(base.var()),
        "var_share_area_term": float(ca.var() / base.var()),
        "var_share_height_term": float(ch.var() / base.var()),
        "var_share_covariance": float(
            (base.var() - ca.var() - ch.var()) / base.var()
        ),
        "spearman_area_vs_height_score": float(rho),
    }


def zone_buildings(bldg, grid, gid):
    cell = grid[grid["grid_id"] == gid]
    return gpd.sjoin(
        bldg, cell[["grid_id", "geometry"]], how="inner", predicate="intersects"
    ).drop(columns=["index_right"], errors="ignore")


def a4_zone_heights(bldg, grid, selected) -> pd.DataFrame:
    rows = []
    for _, r in selected.iterrows():
        gid = int(r["grid_id"])
        z = zone_buildings(bldg, grid, gid)
        h = pd.to_numeric(z["height_proxy_m"], errors="coerce").fillna(6.0)
        vc = h.value_counts(normalize=True)
        rows.append({
            "grid_id": gid,
            "stratum": int(r["stratum"]),
            "n": len(z),
            "n_unique_height": int(h.nunique()),
            "modal_height_m": float(vc.index[0]),
            "modal_height_share_pct": float(100.0 * vc.iloc[0]),
            "height_min": float(h.min()),
            "height_max": float(h.max()),
        })
    return pd.DataFrame(rows).sort_values(["stratum", "grid_id"]).reset_index(drop=True)


def a5_failure_grid(bldg, grid, gid, annual_poa) -> tuple:
    z = zone_buildings(bldg, grid, gid)
    z = bench.compute_pvlib_yield(z, annual_poa)
    area = pd.to_numeric(z["footprint_area_m2"], errors="coerce")
    h = pd.to_numeric(z["height_proxy_m"], errors="coerce").fillna(6.0)
    shade = z["shading_factor"].astype(float)
    score = z["solar_potential_score"].astype(float)

    cell_area_km2 = (GRID_SIZE_M / 1000.0) ** 2
    profile = {
        "grid_id": gid,
        "n_buildings": len(z),
        "building_density_per_km2": len(z) / cell_area_km2,
        "total_footprint_m2": float(area.sum()),
        "footprint_density_m2_per_km2": float(area.sum()) / cell_area_km2,
        "area_min": float(area.min()),
        "area_q25": float(area.quantile(0.25)),
        "area_median": float(area.median()),
        "area_q75": float(area.quantile(0.75)),
        "area_max": float(area.max()),
        "area_mean": float(area.mean()),
        "area_std": float(area.std()),
        "area_cv": float(area.std() / area.mean()),
        "area_max_over_min": float(area.max() / area.min()),
        "n_unique_height": int(h.nunique()),
        "height_min": float(h.min()),
        "height_median": float(h.median()),
        "height_max": float(h.max()),
        "n_shaded": int((shade < 1.0).sum()),
        "pct_shaded": float(100.0 * (shade < 1.0).mean()),
        "min_shading_factor": float(shade.min()),
        "score_min": float(score.min()),
        "score_median": float(score.median()),
        "score_max": float(score.max()),
        "score_std": float(score.std()),
        "n_unique_score": int(score.round(6).nunique()),
        "n_unique_category": int(z["building_category"].nunique()),
    }
    height_tab = (
        h.value_counts().rename_axis("height_m").reset_index(name="count")
        .sort_values("height_m").reset_index(drop=True)
    )
    height_tab["pct"] = 100.0 * height_tab["count"] / len(z)
    cat_tab = (
        z["building_category"].value_counts().rename_axis("building_category")
        .reset_index(name="count")
    )
    cat_tab["pct"] = 100.0 * cat_tab["count"] / len(z)
    return profile, height_tab, cat_tab


# ══════════════════════════════════════════════════════════════════════════════
# PART B — area-only counterfactual
# ══════════════════════════════════════════════════════════════════════════════

def recompute_score(gdf, w_area, w_height):
    """Identical to weight_sensitivity.recompute_score (weight_sensitivity.py:76-83)."""
    base = w_area * gdf["area_score"] + w_height * gdf["height_score"]
    mult = gdf["building_category"].map(CATEGORY_MULTIPLIERS).fillna(
        CATEGORY_MULTIPLIERS["mixed_unknown"]
    )
    return (base * mult * 100).clip(0, 100)


def grid_means_centroid(bldg, grid, cols):
    """Official convention: building CENTROID within cell (grid_solar_aggregation.py)."""
    utm = bldg.estimate_utm_crs()
    cent = bldg.to_crs(utm).copy()
    cent["geometry"] = cent.geometry.centroid
    g = grid.to_crs(utm)
    joined = gpd.sjoin(
        cent[["geometry"] + cols], g[["grid_id", "geometry"]], how="left", predicate="within"
    ).drop(columns=["index_right"], errors="ignore")
    joined = joined.dropna(subset=["grid_id"])
    joined["grid_id"] = joined["grid_id"].astype(int)
    return joined


def grid_means_polygon(bldg, grid, cols):
    """weight_sensitivity convention: full building POLYGON within cell."""
    joined = gpd.sjoin(
        bldg[["geometry"] + cols], grid[["grid_id", "geometry"]], how="left", predicate="within"
    ).drop(columns=["index_right"], errors="ignore")
    joined = joined.dropna(subset=["grid_id"])
    joined["grid_id"] = joined["grid_id"].astype(int)
    return joined.groupby("grid_id")[cols].mean()


def priority_set(ratio_by_grid: pd.Series, top_fraction: float) -> set:
    """Replicates planning_metrics.py:258-263 (cutoff = quantile, inclusive >=)."""
    cutoff = ratio_by_grid.quantile(1.0 - top_fraction)
    return set(ratio_by_grid[ratio_by_grid >= cutoff].index), float(cutoff)


def part_b(bldg, grid, published_priority_ids):
    out = {}

    score_base = pd.to_numeric(bldg["solar_potential_score"], errors="coerce")
    score_area = recompute_score(bldg, 1.00, 0.00)
    hp_base = pd.to_numeric(bldg["is_high_potential"], errors="coerce").fillna(0).astype(int)

    n = len(bldg)
    out["n_buildings"] = n
    out["hp_base_count"] = int(hp_base.sum())

    # ── Building-level rank agreement ────────────────────────────────────────
    rho_b, p_b = stats.spearmanr(score_area, score_base)
    tau_b, _ = stats.kendalltau(score_area, score_base)
    out["bldg_spearman_rho"] = float(rho_b)
    out["bldg_spearman_p"] = float(p_b)
    out["bldg_kendall_tau"] = float(tau_b)

    # ── Tier membership under three conventions ──────────────────────────────
    # (i) fixed absolute cutoff, as published in weight_sensitivity.py
    hp_fixed = (score_area > Q66_FIXED).astype(int)
    hp_base_fixed = (score_base > Q66_FIXED).astype(int)
    out["hp_fixed_base_count"] = int(hp_base_fixed.sum())
    out["hp_fixed_area_count"] = int(hp_fixed.sum())

    # (ii) re-derived q66 on the area-only distribution (equal-size tier by rank)
    q66_area = float(score_area.quantile(0.66))
    hp_q66 = (score_area >= q66_area).astype(int)
    out["q66_area_only"] = q66_area
    out["hp_q66_area_count"] = int(hp_q66.sum())

    # (iii) rank-matched top-N, N = published HP count
    N = int(hp_base.sum())
    thresh_topn = float(score_area.nlargest(N).min())
    hp_topn = (score_area >= thresh_topn).astype(int)
    out["hp_topn_count"] = int(hp_topn.sum())

    for tag, hp_var in [("q66", hp_q66), ("topn", hp_topn), ("fixed", hp_fixed)]:
        lost = int(((hp_base == 1) & (hp_var == 0)).sum())
        gained = int(((hp_base == 0) & (hp_var == 1)).sum())
        out[f"tier_{tag}_lost"] = lost
        out[f"tier_{tag}_gained"] = gained
        out[f"tier_{tag}_changed"] = lost + gained
        out[f"tier_{tag}_change_pct"] = 100.0 * (lost + gained) / n
        inter = int(((hp_base == 1) & (hp_var == 1)).sum())
        union = int(((hp_base == 1) | (hp_var == 1)).sum())
        out[f"tier_{tag}_retained"] = inter
        out[f"tier_{tag}_retained_pct_of_base"] = 100.0 * inter / max(int(hp_base.sum()), 1)
        out[f"tier_{tag}_jaccard"] = inter / union if union else float("nan")

    # ── Grid-level rank agreement ────────────────────────────────────────────
    work = bldg[["geometry"]].copy()
    work["score_base"] = score_base.values
    work["score_area"] = score_area.values
    work["hp_base"] = hp_base.values
    work["hp_area_q66"] = hp_q66.values

    cols = ["score_base", "score_area", "hp_base", "hp_area_q66"]
    joined_c = grid_means_centroid(work, grid, cols)
    gm_c = joined_c.groupby("grid_id")[cols].mean()
    out["n_occupied_grids_centroid"] = int(len(gm_c))
    rho_gc, p_gc = stats.spearmanr(gm_c["score_area"], gm_c["score_base"])
    out["grid_spearman_rho_centroid"] = float(rho_gc)
    out["grid_spearman_p_centroid"] = float(p_gc)

    gm_p = grid_means_polygon(work, grid, cols)
    out["n_occupied_grids_polygon"] = int(len(gm_p))
    rho_gp, p_gp = stats.spearmanr(gm_p["score_area"], gm_p["score_base"])
    out["grid_spearman_rho_polygon"] = float(rho_gp)
    out["grid_spearman_p_polygon"] = float(p_gp)

    # ── Priority grids ───────────────────────────────────────────────────────
    # HP ratio per grid = mean of the per-building HP flag (centroid convention)
    ratio_base = gm_c["hp_base"]
    ratio_area = gm_c["hp_area_q66"]

    set_base, cut_base = priority_set(ratio_base, PRIORITY_TOP_FRACTION)
    set_area, cut_area = priority_set(ratio_area, PRIORITY_TOP_FRACTION)

    out["priority_cutoff_base"] = cut_base
    out["priority_cutoff_area"] = cut_area
    out["n_priority_base_recomputed"] = len(set_base)
    out["n_priority_area"] = len(set_area)
    out["n_priority_published"] = len(published_priority_ids)

    out["overlap_recomputed_vs_published"] = len(set_base & published_priority_ids)
    out["overlap_area_vs_published"] = len(set_area & published_priority_ids)
    out["overlap_area_vs_published_pct"] = (
        100.0 * len(set_area & published_priority_ids) / max(len(published_priority_ids), 1)
    )
    out["overlap_area_vs_recomputed"] = len(set_area & set_base)
    out["overlap_area_vs_recomputed_pct"] = (
        100.0 * len(set_area & set_base) / max(len(set_base), 1)
    )
    inter = len(set_area & set_base)
    union = len(set_area | set_base)
    out["priority_jaccard"] = inter / union if union else float("nan")

    return out, gm_c


# ══════════════════════════════════════════════════════════════════════════════

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--grid", required=True)
    p.add_argument("--priority", default="outputs/priority_grids.csv")
    p.add_argument("--output_dir", default="outputs/validation/")
    return p.parse_args()


def main():
    setup_logging()
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    logging.info("Loading buildings…")
    bldg = gpd.read_file(args.input)
    logging.info("  %d buildings", len(bldg))
    logging.info("Loading grid…")
    grid = gpd.read_file(args.grid)
    if bldg.crs != grid.crs:
        grid = grid.to_crs(bldg.crs)

    published_priority = set(
        pd.read_csv(args.priority)["grid_id"].astype(int).tolist()
    )

    # ── PART A ───────────────────────────────────────────────────────────────
    print("\n" + rule())
    print("  PART A — Height proxy & score composition (urban core)")
    print(rule())

    src_tab = a1_height_source(bldg)
    print("\nA1. height_proxy cascade on the urban-core subset")
    print(f"  {'source':<26} {'count':>8} {'pct':>9}")
    print(rule("-", 46))
    for _, r in src_tab.iterrows():
        print(f"  {r['height_proxy_source']:<26} {int(r['count']):>8} {r['pct']:>8.3f}%")

    top, q = a2_height_values(bldg)
    print("\nA2. height_proxy_m value distribution (urban core)")
    print(f"  n = {q['n']}   distinct values = {q['n_unique']}")
    print(f"  min={q['min']:.3f}  q25={q['q25']:.3f}  median={q['median']:.3f}  "
          f"q75={q['q75']:.3f}  q95={q['q95']:.3f}  max={q['max']:.3f}")
    print(f"  mean={q['mean']:.4f}  std={q['std']:.4f}")
    print(f"\n  {'height (m)':>11} {'count':>8} {'pct':>9} {'cum pct':>9}")
    print(rule("-", 42))
    for _, r in top.iterrows():
        print(f"  {r['height_m']:>11.2f} {int(r['count']):>8} {r['pct']:>8.3f}% {r['cum_pct']:>8.3f}%")

    comp = a3_score_components(bldg)
    print("\nA3. Score-component dispersion (n = %d)" % comp["n"])
    print(f"  std(area_score)                = {comp['std_area_score']:.6f}")
    print(f"  std(height_score)              = {comp['std_height_score']:.6f}")
    print(f"  ratio height/area              = {comp['std_ratio_height_over_area']:.6f}")
    print(f"  std(0.65 x area_score)         = {comp['std_weighted_area_term']:.6f}")
    print(f"  std(0.35 x height_score)       = {comp['std_weighted_height_term']:.6f}")
    print(f"  ratio weighted height/area     = {comp['std_ratio_weighted']:.6f}")
    print(f"  var share of area term         = {100*comp['var_share_area_term']:.3f}%")
    print(f"  var share of height term       = {100*comp['var_share_height_term']:.3f}%")
    print(f"  var share of 2*cov term        = {100*comp['var_share_covariance']:.3f}%")
    print(f"  Spearman(area_score, height_score) = {comp['spearman_area_vs_height_score']:+.6f}")

    logging.info("Selecting the 20 stratified zones (seed=42)…")
    selected = bench.select_stratified_grids(grid)
    zone_tab = a4_zone_heights(bldg, grid, selected)
    print("\nA4. Height diversity within the 20 benchmark zones")
    print(f"  {'grid':>6} {'str':>4} {'n':>5} {'uniq h':>7} {'modal h':>9} {'modal share':>12} "
          f"{'h min':>7} {'h max':>8}")
    print(rule("-", 66))
    for _, r in zone_tab.iterrows():
        print(f"  {int(r['grid_id']):>6} {int(r['stratum']):>4} {int(r['n']):>5} "
              f"{int(r['n_unique_height']):>7} {r['modal_height_m']:>9.2f} "
              f"{r['modal_height_share_pct']:>11.1f}% {r['height_min']:>7.2f} {r['height_max']:>8.2f}")
    n_single = int((zone_tab["n_unique_height"] == 1).sum())
    print(rule("-", 66))
    print(f"  zones with a single distinct height value: {n_single}/{len(zone_tab)}")
    print(f"  median modal-height share: {zone_tab['modal_height_share_pct'].median():.1f}%")

    annual_poa = bench.annual_clearsky_poa()
    prof, htab, ctab = a5_failure_grid(bldg, grid, FAILURE_GRID_ID, annual_poa)
    print(f"\nA5. Failure-boundary profile — grid {FAILURE_GRID_ID}")
    for k, v in prof.items():
        if isinstance(v, float):
            print(f"  {k:<32} {v:>14.4f}")
        else:
            print(f"  {k:<32} {v:>14}")
    print(f"\n  height composition of grid {FAILURE_GRID_ID}:")
    print(f"  {'height (m)':>11} {'count':>7} {'pct':>9}")
    for _, r in htab.iterrows():
        print(f"  {r['height_m']:>11.2f} {int(r['count']):>7} {r['pct']:>8.2f}%")
    print(f"\n  building_category composition:")
    for _, r in ctab.iterrows():
        print(f"  {r['building_category']:<20} {int(r['count']):>5} {r['pct']:>8.2f}%")

    # ── PART B ───────────────────────────────────────────────────────────────
    print("\n" + rule())
    print("  PART B — Area-only counterfactual (weights 1.00 / 0.00)")
    print(rule())
    res, gm_c = part_b(bldg, grid, published_priority)

    print(f"\nB1. Building-level rank agreement (n = {res['n_buildings']})")
    print(f"  Spearman rho (area-only vs composite) = {res['bldg_spearman_rho']:+.6f}  "
          f"(p = {res['bldg_spearman_p']:.3e})")
    print(f"  Kendall  tau                          = {res['bldg_kendall_tau']:+.6f}")

    print(f"\nB2. High-potential tier membership (baseline HP = {res['hp_base_count']})")
    print(f"  {'convention':<40} {'HP n':>7} {'lost':>7} {'gained':>7} {'changed':>8} "
          f"{'retained':>9} {'Jaccard':>8}")
    print(rule("-", 92))
    labels = {
        "fixed": f"fixed cutoff {Q66_FIXED} (as published)",
        "q66":   f"re-derived q66 = {res['q66_area_only']:.4f}",
        "topn":  f"rank-matched top-{res['hp_base_count']}",
    }
    counts = {"fixed": res["hp_fixed_area_count"], "q66": res["hp_q66_area_count"],
              "topn": res["hp_topn_count"]}
    for tag in ["fixed", "q66", "topn"]:
        print(f"  {labels[tag]:<40} {counts[tag]:>7} {res[f'tier_{tag}_lost']:>7} "
              f"{res[f'tier_{tag}_gained']:>7} {res[f'tier_{tag}_changed']:>8} "
              f"{res[f'tier_{tag}_retained_pct_of_base']:>8.2f}% "
              f"{res[f'tier_{tag}_jaccard']:>8.4f}")
    print(f"\n  (baseline score under the same fixed cutoff yields "
          f"{res['hp_fixed_base_count']} buildings)")

    print(f"\nB3. Grid-level mean-score rank agreement")
    print(f"  centroid-within (official product convention): "
          f"rho = {res['grid_spearman_rho_centroid']:+.6f}  "
          f"(n = {res['n_occupied_grids_centroid']} occupied grids)")
    print(f"  polygon-within  (weight_sensitivity convention): "
          f"rho = {res['grid_spearman_rho_polygon']:+.6f}  "
          f"(n = {res['n_occupied_grids_polygon']} grids)")

    print(f"\nB4. Priority grids (top {int(PRIORITY_TOP_FRACTION*100)}% by HP ratio)")
    print(f"  published set (outputs/priority_grids.csv):  {res['n_priority_published']}")
    print(f"  recomputed baseline set:                     {res['n_priority_base_recomputed']} "
          f"(cutoff HP ratio >= {res['priority_cutoff_base']:.6f})")
    print(f"    overlap with published:                    {res['overlap_recomputed_vs_published']}"
          f"  <- replication check")
    print(f"  area-only set:                               {res['n_priority_area']} "
          f"(cutoff HP ratio >= {res['priority_cutoff_area']:.6f})")
    print(f"    overlap with published 146:                {res['overlap_area_vs_published']} "
          f"({res['overlap_area_vs_published_pct']:.2f}%)")
    print(f"    overlap with recomputed baseline:          {res['overlap_area_vs_recomputed']} "
          f"({res['overlap_area_vs_recomputed_pct']:.2f}%)")
    print(f"    Jaccard:                                   {res['priority_jaccard']:.4f}")

    # ── Save ─────────────────────────────────────────────────────────────────
    src_tab.to_csv(out_dir / "diag_height_source_urban_core.csv", index=False)
    top.to_csv(out_dir / "diag_height_value_distribution.csv", index=False)
    pd.DataFrame([comp]).to_csv(out_dir / "diag_score_components.csv", index=False)
    zone_tab.to_csv(out_dir / "diag_zone_height_diversity.csv", index=False)
    pd.DataFrame([prof]).to_csv(out_dir / "diag_grid807_profile.csv", index=False)
    htab.to_csv(out_dir / "diag_grid807_heights.csv", index=False)
    pd.DataFrame([res]).to_csv(out_dir / "diag_area_only_counterfactual.csv", index=False)
    logging.info("Saved 7 CSVs to %s", out_dir)
    logging.info("Done.")


if __name__ == "__main__":
    main()
