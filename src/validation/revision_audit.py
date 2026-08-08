#!/usr/bin/env python3
"""
revision_audit.py

Read-only audit supporting the paper revision. Two jobs:

PART 1 — Provenance hunt for two figures quoted in Section 4.4.6 that do not
         reproduce: building-level rho = 0.983 and priority-grid overlap > 90%.
         Every plausible alternative operationalisation is computed and screened
         against the quoted targets, so the answer is "here is the definition
         that yields it" or "no definition tested yields it".

PART 2 — Recomputation of the audit items that are not already sitting in a CSV:
         the priority-grid share of generation potential, the GSA intra-urban
         irradiance spread, and an independence check on the Overture footprint
         comparison.

Nothing existing is modified; results print to stdout and go to one CSV.

Usage
-----
    python src/validation/revision_audit.py \
        --input      data/processed/buildings_changsha_urban_core_solar_baseline.geojson \
        --grid       data/processed/grid_changsha_urban_core_solar_baseline.geojson \
        --output_dir outputs/validation/
"""

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import stats

CATEGORY_MULTIPLIERS = {"commercial": 1.10, "residential": 1.00, "mixed_unknown": 0.95}
Q66_FIXED = 45.513
PRIORITY_TOP_FRACTION = 0.20
GRID_SIZE_M = 500

# Targets we are trying to reproduce
TARGET_RHO = 0.983
RHO_TOL = 0.0015          # accept 0.9815 .. 0.9845
TARGET_OVERLAP_PCT = 90.0  # "> 90%"

# planning_metrics.py CONFIG
UTIL, ETA, GHI, PR, EF = 0.65, 0.20, 1300.0, 0.80, 0.5703


def setup_logging():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(message)s")


def minmax(s: pd.Series) -> pd.Series:
    lo, hi = s.min(), s.max()
    if pd.isna(lo) or pd.isna(hi) or hi == lo:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - lo) / (hi - lo)


def score_from(area_component, height_component, cat, w_a, w_h, use_mult=True):
    base = w_a * area_component + w_h * height_component
    if use_mult:
        m = cat.map(CATEGORY_MULTIPLIERS).fillna(CATEGORY_MULTIPLIERS["mixed_unknown"])
        return (base * m * 100).clip(0, 100)
    return (base * 100).clip(0, 100)


def centroid_join(bldg, grid, cols):
    utm = bldg.estimate_utm_crs()
    cent = bldg.to_crs(utm).copy()
    cent["geometry"] = cent.geometry.centroid
    g = grid.to_crs(utm)
    j = gpd.sjoin(cent[["geometry"] + cols], g[["grid_id", "geometry"]],
                  how="left", predicate="within").drop(columns=["index_right"], errors="ignore")
    j = j.dropna(subset=["grid_id"])
    j["grid_id"] = j["grid_id"].astype(int)
    return j


def polygon_join(bldg, grid, cols):
    j = gpd.sjoin(bldg[["geometry"] + cols], grid[["grid_id", "geometry"]],
                  how="left", predicate="within").drop(columns=["index_right"], errors="ignore")
    j = j.dropna(subset=["grid_id"])
    j["grid_id"] = j["grid_id"].astype(int)
    return j


# ══════════════════════════════════════════════════════════════════════════════
# PART 1a — candidate definitions for the building-level rho
# ══════════════════════════════════════════════════════════════════════════════

def hunt_rho(bldg, grid):
    cat = bldg["building_category"]
    a_sc = pd.to_numeric(bldg["area_score"], errors="coerce")
    h_sc = pd.to_numeric(bldg["height_score"], errors="coerce")
    area = pd.to_numeric(bldg["footprint_area_m2"], errors="coerce")
    hgt = pd.to_numeric(bldg["height_proxy_m"], errors="coerce")
    hp = pd.to_numeric(bldg["is_high_potential"], errors="coerce").fillna(0).astype(int)

    composite = score_from(a_sc, h_sc, cat, 0.65, 0.35, True)
    area_only = score_from(a_sc, h_sc, cat, 1.00, 0.00, True)

    # Variants of the underlying components
    a_nolog = minmax(area)                     # no log1p transform
    h_nolog = minmax(hgt.fillna(0).clip(lower=0))
    comp_nolog = score_from(a_nolog, h_nolog, cat, 0.65, 0.35, True)
    area_only_nolog = score_from(a_nolog, h_nolog, cat, 1.00, 0.00, True)

    comp_nomult = score_from(a_sc, h_sc, cat, 0.65, 0.35, False)
    area_only_nomult = score_from(a_sc, h_sc, cat, 1.00, 0.00, False)

    cands = []

    def add(label, x, y, method="spearman", subset=None):
        if subset is not None:
            x, y = x[subset], y[subset]
        if method == "spearman":
            r, p = stats.spearmanr(x, y)
        elif method == "pearson":
            r, p = stats.pearsonr(x, y)
        else:
            r, p = stats.kendalltau(x, y)
        cands.append({"family": "building", "definition": label, "method": method,
                      "n": len(x), "value": float(r)})

    hp_mask = hp == 1
    nonhp_mask = hp == 0

    add("area-only vs composite (final score)", area_only, composite, "spearman")
    add("area-only vs composite (final score)", area_only, composite, "pearson")
    add("area-only vs composite (final score)", area_only, composite, "kendall")
    add("area-only vs composite (base_score, no category mult)", area_only_nomult, comp_nomult, "spearman")
    add("area-only vs composite (base_score, no category mult)", area_only_nomult, comp_nomult, "pearson")
    add("area-only vs composite (no log transform)", area_only_nolog, comp_nolog, "spearman")
    add("area-only vs composite (no log transform)", area_only_nolog, comp_nolog, "pearson")
    add("area-only vs composite, HIGH-POTENTIAL subset", area_only, composite, "spearman", hp_mask)
    add("area-only vs composite, HIGH-POTENTIAL subset", area_only, composite, "pearson", hp_mask)
    add("area-only vs composite, HIGH-POTENTIAL subset", area_only, composite, "kendall", hp_mask)
    add("area-only vs composite, NON-high-potential subset", area_only, composite, "spearman", nonhp_mask)
    add("area-only vs composite, NON-high-potential subset", area_only, composite, "pearson", nonhp_mask)
    add("raw footprint area vs composite score", area, composite, "spearman")
    add("raw footprint area vs composite score", area, composite, "pearson")
    add("log area vs composite score", np.log1p(area), composite, "pearson")
    add("area_score vs base_score", a_sc, comp_nomult, "spearman")
    add("area_score vs base_score", a_sc, comp_nomult, "pearson")

    # Pairwise across the four published weight variants
    variants = {"W1 0.50/0.50": score_from(a_sc, h_sc, cat, 0.50, 0.50, True),
                "W2 0.65/0.35": composite,
                "W3 0.70/0.30": score_from(a_sc, h_sc, cat, 0.70, 0.30, True),
                "W4 1.00/0.00": area_only}
    keys = list(variants)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            add(f"{keys[i]} vs {keys[j]}", variants[keys[i]], variants[keys[j]], "spearman")
            add(f"{keys[i]} vs {keys[j]}", variants[keys[i]], variants[keys[j]], "pearson")

    # ── Grid-level variants ─────────────────────────────────────────────────
    work = bldg[["geometry"]].copy()
    work["composite"] = composite.values
    work["area_only"] = area_only.values
    work["hp_base"] = hp.values
    cols = ["composite", "area_only", "hp_base"]

    for jname, jfun in [("centroid-within", centroid_join), ("polygon-within", polygon_join)]:
        j = jfun(work, grid, cols)
        for agg in ["mean", "median"]:
            gm = j.groupby("grid_id")[cols].agg(agg)
            for method in ["spearman", "pearson"]:
                if method == "spearman":
                    r, _ = stats.spearmanr(gm["area_only"], gm["composite"])
                else:
                    r, _ = stats.pearsonr(gm["area_only"], gm["composite"])
                cands.append({"family": "grid", "n": len(gm), "method": method,
                              "definition": f"grid {agg} score, {jname}", "value": float(r)})
        # HP-ratio based grid correlation
        gm = j.groupby("grid_id")[cols].mean()
        r, _ = stats.spearmanr(gm["area_only"], gm["hp_base"])
        cands.append({"family": "grid", "n": len(gm), "method": "spearman",
                      "definition": f"grid mean area-only vs HP ratio, {jname}", "value": float(r)})

    return pd.DataFrame(cands)


# ══════════════════════════════════════════════════════════════════════════════
# PART 1b — candidate definitions for the priority-grid overlap
# ══════════════════════════════════════════════════════════════════════════════

def hunt_overlap(bldg, grid, published_ids):
    cat = bldg["building_category"]
    a_sc = pd.to_numeric(bldg["area_score"], errors="coerce")
    h_sc = pd.to_numeric(bldg["height_score"], errors="coerce")
    hp_base = pd.to_numeric(bldg["is_high_potential"], errors="coerce").fillna(0).astype(int)

    composite = score_from(a_sc, h_sc, cat, 0.65, 0.35, True)
    area_only = score_from(a_sc, h_sc, cat, 1.00, 0.00, True)

    # Three ways of defining the area-only HP tier
    tiers = {
        "q66 of own distribution": (area_only >= area_only.quantile(0.66)).astype(int),
        "fixed cutoff 45.513":     (area_only > Q66_FIXED).astype(int),
        "rank-matched top-6411":   (area_only >= area_only.nlargest(int(hp_base.sum())).min()).astype(int),
    }

    work = bldg[["geometry"]].copy()
    work["hp_base"] = hp_base.values
    for k, v in tiers.items():
        work[f"tier::{k}"] = v.values
    cols = ["hp_base"] + [f"tier::{k}" for k in tiers]

    rows = []
    for jname, jfun in [("centroid-within", centroid_join), ("polygon-within", polygon_join)]:
        j = jfun(work, grid, cols)
        gm = j.groupby("grid_id")[cols].mean()
        base_ratio = gm["hp_base"]

        for selname, select in [
            ("quantile cutoff >= q80", lambda s: set(s[s >= s.quantile(0.8)].index)),
            ("strict top-146 by rank", lambda s: set(s.nlargest(146).index)),
            ("ratio == 1.0 only",      lambda s: set(s[s >= 1.0].index)),
        ]:
            base_set = select(base_ratio)
            for k in tiers:
                var_set = select(gm[f"tier::{k}"])
                inter = len(var_set & base_set)
                union = len(var_set | base_set)
                rows.append({
                    "join": jname, "selection": selname, "area_only_tier": k,
                    "n_base": len(base_set), "n_variant": len(var_set),
                    "overlap": inter,
                    "pct_of_base": 100.0 * inter / max(len(base_set), 1),
                    "pct_of_min": 100.0 * inter / max(min(len(base_set), len(var_set)), 1),
                    "jaccard": inter / union if union else float("nan"),
                    "overlap_vs_published": len(var_set & published_ids),
                    "pct_of_published": 100.0 * len(var_set & published_ids) / max(len(published_ids), 1),
                })
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
# PART 2 — recomputed audit items
# ══════════════════════════════════════════════════════════════════════════════

def priority_generation_share(bldg, grid, published_ids):
    """Share of total HP generation potential falling inside the 146 priority grids."""
    hp = pd.to_numeric(bldg["is_high_potential"], errors="coerce").fillna(0).astype(int)
    area = pd.to_numeric(bldg["footprint_area_m2"], errors="coerce").fillna(0)
    kwh = area * UTIL * ETA * GHI * PR

    work = bldg[["geometry"]].copy()
    work["kwh"] = (kwh * hp).values          # HP buildings only, as planning_metrics does
    work["kwh_all"] = kwh.values             # all buildings, alternative denominator
    work["hp"] = hp.values
    j = centroid_join(work, grid, ["kwh", "kwh_all", "hp"])
    per_grid = j.groupby("grid_id")[["kwh", "kwh_all", "hp"]].sum()

    inside = per_grid.loc[per_grid.index.isin(published_ids)]
    total_hp_kwh = per_grid["kwh"].sum()
    total_all_kwh = per_grid["kwh_all"].sum()
    return {
        "n_priority_grids": len(inside),
        "priority_share_of_HP_generation_pct": 100.0 * inside["kwh"].sum() / total_hp_kwh,
        "priority_share_of_ALL_building_generation_pct": 100.0 * inside["kwh_all"].sum() / total_all_kwh,
        "priority_share_of_HP_buildings_pct": 100.0 * inside["hp"].sum() / per_grid["hp"].sum(),
        "total_HP_generation_gwh": total_hp_kwh / 1e6,
        "priority_HP_generation_gwh": inside["kwh"].sum() / 1e6,
    }


def gsa_stats(path="outputs/validation/gsa_comparison.csv"):
    d = pd.read_csv(path)
    rho, p = stats.spearmanr(d["mean_score"], d["mean_ghi"])
    r, _ = stats.pearsonr(d["mean_score"], d["mean_ghi"])
    g = d["mean_ghi"]
    return {
        "n_cells": len(d),
        "spearman_rho": float(rho), "spearman_p": float(p), "pearson_r": float(r),
        "ghi_min_kwh_m2_day": float(g.min()), "ghi_max_kwh_m2_day": float(g.max()),
        "ghi_mean_kwh_m2_day": float(g.mean()),
        "spread_pct_of_mean": 100.0 * (g.max() - g.min()) / g.mean(),
        "spread_pct_of_min": 100.0 * (g.max() - g.min()) / g.min(),
        "cv_pct": 100.0 * g.std() / g.mean(),
    }


def overture_independence(path="outputs/validation/osm_quality_results.csv"):
    d = pd.read_csv(path)
    iou1 = (d["iou"] >= 0.999999).sum()
    diff0 = (d["area_diff_pct"].abs() < 1e-9).sum()
    cent0 = (d["centroid_dist_m"] < 1e-6).sum()
    return {
        "n": len(d),
        "n_iou_exactly_1": int(iou1), "pct_iou_exactly_1": 100.0 * iou1 / len(d),
        "n_area_diff_exactly_0": int(diff0), "pct_area_diff_exactly_0": 100.0 * diff0 / len(d),
        "n_centroid_dist_below_1um": int(cent0), "pct_centroid_dist_below_1um": 100.0 * cent0 / len(d),
        "mean_iou": float(d["iou"].mean()),
        "mean_iou_excluding_identical": float(d.loc[d["iou"] < 0.999999, "iou"].mean()),
        "n_nonidentical": int((d["iou"] < 0.999999).sum()),
        "mape_pct_all": float(d["area_diff_pct"].abs().mean()),
        "mape_pct_nonidentical": float(d.loc[d["iou"] < 0.999999, "area_diff_pct"].abs().mean()),
    }


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
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)

    bldg = gpd.read_file(args.input)
    grid = gpd.read_file(args.grid)
    if bldg.crs != grid.crs:
        grid = grid.to_crs(bldg.crs)
    published = set(pd.read_csv(args.priority)["grid_id"].astype(int).tolist())
    logging.info("%d buildings, %d grid cells, %d published priority grids",
                 len(bldg), len(grid), len(published))

    print("\n" + "=" * 100)
    print("  PART 1a — hunting building-level rho = 0.983")
    print("=" * 100)
    rho_df = hunt_rho(bldg, grid).sort_values("value", ascending=False).reset_index(drop=True)
    print(f"  {'family':<9} {'method':<9} {'n':>6}  {'value':>10}  definition")
    print("-" * 100)
    for _, r in rho_df.iterrows():
        flag = "  <== MATCH" if abs(r["value"] - TARGET_RHO) <= RHO_TOL else ""
        print(f"  {r['family']:<9} {r['method']:<9} {int(r['n']):>6}  {r['value']:>+10.6f}  {r['definition']}{flag}")
    n_match = int((rho_df["value"].sub(TARGET_RHO).abs() <= RHO_TOL).sum())
    print("-" * 100)
    print(f"  definitions tested: {len(rho_df)}   landing in [{TARGET_RHO-RHO_TOL:.4f}, {TARGET_RHO+RHO_TOL:.4f}]: {n_match}")

    print("\n" + "=" * 100)
    print("  PART 1b — hunting priority-grid overlap > 90%")
    print("=" * 100)
    ov = hunt_overlap(bldg, grid, published)
    print(f"  {'join':<16} {'selection':<24} {'area-only tier':<24} {'base':>5} {'var':>5} "
          f"{'ovl':>5} {'%base':>7} {'%min':>7} {'Jacc':>6}")
    print("-" * 100)
    for _, r in ov.iterrows():
        flag = "  <==" if r["pct_of_base"] > TARGET_OVERLAP_PCT else ""
        print(f"  {r['join']:<16} {r['selection']:<24} {r['area_only_tier']:<24} "
              f"{int(r['n_base']):>5} {int(r['n_variant']):>5} {int(r['overlap']):>5} "
              f"{r['pct_of_base']:>6.2f}% {r['pct_of_min']:>6.2f}% {r['jaccard']:>6.4f}{flag}")
    n_ov = int((ov["pct_of_base"] > TARGET_OVERLAP_PCT).sum())
    print("-" * 100)
    print(f"  definitions tested: {len(ov)}   exceeding {TARGET_OVERLAP_PCT:.0f}% of base: {n_ov}")

    print("\n" + "=" * 100)
    print("  PART 2 — recomputed audit items")
    print("=" * 100)
    pg = priority_generation_share(bldg, grid, published)
    print("\n  Priority-grid share of generation potential:")
    for k, v in pg.items():
        print(f"    {k:<48} {v:>12.4f}" if isinstance(v, float) else f"    {k:<48} {v:>12}")

    gs = gsa_stats()
    print("\n  Global Solar Atlas comparison:")
    for k, v in gs.items():
        print(f"    {k:<48} {v:>12.4f}" if isinstance(v, float) else f"    {k:<48} {v:>12}")

    ot = overture_independence()
    print("\n  Overture footprint comparison — independence check:")
    for k, v in ot.items():
        print(f"    {k:<48} {v:>12.4f}" if isinstance(v, float) else f"    {k:<48} {v:>12}")

    rho_df.to_csv(out / "audit_rho_definition_hunt.csv", index=False, float_format="%.8f")
    ov.to_csv(out / "audit_overlap_definition_hunt.csv", index=False, float_format="%.6f")
    pd.DataFrame([{**{"item": "priority_generation"}, **pg}]).to_csv(
        out / "audit_priority_generation_share.csv", index=False, float_format="%.6f")
    pd.DataFrame([gs]).to_csv(out / "audit_gsa_stats.csv", index=False, float_format="%.6f")
    pd.DataFrame([ot]).to_csv(out / "audit_overture_independence.csv", index=False, float_format="%.6f")
    logging.info("Saved 5 audit CSVs to %s", out)


if __name__ == "__main__":
    main()
