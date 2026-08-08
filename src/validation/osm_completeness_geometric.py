#!/usr/bin/env python3
"""
osm_completeness_geometric.py

Corrects and extends the OSM completeness assessment on two points.

1. GEOMETRIC COVERAGE, not a ratio of totals
   `osm_completeness.py` computed, per cell, the sum of OSM polygon areas
   divided by the sum of Overture polygon areas. That is a ratio of two
   independent totals: two datasets could each hold 30 km2 of roof in entirely
   different places and still score 1.0. It also double-counts wherever polygons
   within one dataset overlap, and it can exceed 1.0.

   This script reports both, clearly separated:

     ratio_area   (a)  sum(OSM area) / sum(Overture area)          — comparable
                       to the earlier figure, not a coverage measure
     coverage_geo (b)  area(OSM_dissolved ∩ REF_dissolved)
                       / area(REF_dissolved)                        — true
                       geometric coverage, bounded to [0, 1]

   Both datasets are clipped to the cell first, then dissolved (unary_union) so
   internal overlaps are counted once, and only then intersected.

   Also reported: agreement in the other direction,
     osm_in_ref = area(intersection) / area(OSM_dissolved)
   which shows how much of the OSM stock the comparator confirms.

2. AN ACTUALLY INDEPENDENT COMPARATOR
   About 19.6% of Overture's urban-core buildings are OSM-sourced. Including
   them makes the comparator partly the thing being measured. Buildings are
   fetched with their `sources` and the whole analysis is run twice: once
   against all Overture buildings, once against the non-OSM-sourced subset only.

Outputs (all new; nothing existing is modified)
-----------------------------------------------
outputs/validation/completeness_geometric_per_grid.csv
outputs/validation/completeness_geometric_summary.csv

Usage
-----
    python src/validation/osm_completeness_geometric.py \
        --osm_core   data/processed/buildings_changsha_urban_core_solar_baseline.geojson \
        --core_area  data/processed/study_area_changsha_urban_core.geojson \
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
from shapely.ops import unary_union

OSM_SOURCE_NAME = "OpenStreetMap"


def setup_logging():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(message)s")


# ── Fetch Overture with provenance ────────────────────────────────────────────

def fetch_overture_with_sources(bbox, release):
    """Read geometry + sources for the bbox straight from Overture's S3."""
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    import pyarrow.fs as fs
    from shapely import wkb as shapely_wkb

    spec = importlib.util.spec_from_file_location(
        "oqv", Path(__file__).resolve().parents[2] / "osm_quality_validation.py")
    oqv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oqv)
    paths = oqv._find_building_parquet_files(release, bbox)

    xmin, ymin, xmax, ymax = bbox
    filt = ((pc.field("bbox", "xmin") < xmax) & (pc.field("bbox", "xmax") > xmin) &
            (pc.field("bbox", "ymin") < ymax) & (pc.field("bbox", "ymax") > ymin))
    s3 = fs.S3FileSystem(anonymous=True, region="us-west-2")

    geoms, osm_flag = [], []
    for p in paths:
        dataset = ds.dataset(p, filesystem=s3)
        cols = [c for c in ["geometry", "bbox", "sources"] if c in dataset.schema.names]
        for batch in dataset.to_batches(filter=filt, columns=cols):
            gcol = batch.column("geometry").to_pylist()
            scol = batch.column("sources").to_pylist() if "sources" in cols else [None] * len(gcol)
            for raw, srcs in zip(gcol, scol):
                if raw is None:
                    continue
                try:
                    geom = shapely_wkb.loads(raw) if isinstance(raw, (bytes, bytearray)) else None
                except Exception:
                    continue
                if geom is None or geom.is_empty:
                    continue
                names = {str((s or {}).get("dataset")) for s in (srcs or []) if (s or {}).get("dataset")}
                geoms.append(geom)
                osm_flag.append(OSM_SOURCE_NAME in names)

    gdf = gpd.GeoDataFrame({"is_osm_sourced": osm_flag}, geometry=geoms, crs="EPSG:4326")
    logging.info("Overture fetched: %d buildings (%d OSM-sourced, %.2f%%)",
                 len(gdf), int(gdf.is_osm_sourced.sum()),
                 100.0 * gdf.is_osm_sourced.mean() if len(gdf) else 0.0)
    return gdf


# ── Geometric coverage ────────────────────────────────────────────────────────

def clip_dissolve_by_cell(gdf, grid, utm):
    """
    Clip polygons to cell boundaries, then dissolve per cell so internal
    overlaps are counted once. Returns {grid_id: (geometry, area)}.
    """
    g = grid.to_crs(utm)[["grid_id", "geometry"]]
    p = gdf.to_crs(utm)[["geometry"]].copy()
    p["geometry"] = p.geometry.buffer(0)          # repair self-intersections
    p = p[p.geometry.notna() & ~p.geometry.is_empty]

    parts = gpd.overlay(p, g, how="intersection", keep_geom_type=True)
    out = {}
    for gid, sub in parts.groupby("grid_id"):
        u = unary_union(sub.geometry.values)
        out[int(gid)] = (u, float(u.area))
    return out


def build_table(osm_core, ref, grid, utm, label):
    logging.info("[%s] clipping + dissolving OSM …", label)
    osm_d = clip_dissolve_by_cell(osm_core, grid, utm)
    logging.info("[%s] clipping + dissolving comparator …", label)
    ref_d = clip_dissolve_by_cell(ref, grid, utm)

    # raw (undissolved, centroid-assigned) sums for the ratio_area metric
    def centroid_sums(gdf, name):
        g = grid.to_crs(utm)[["grid_id", "geometry"]]
        p = gdf.to_crs(utm).copy()
        p["_a"] = p.geometry.area
        c = p.copy(); c["geometry"] = c.geometry.centroid
        j = gpd.sjoin(c[["geometry", "_a"]], g, how="left", predicate="within").dropna(subset=["grid_id"])
        j["grid_id"] = j["grid_id"].astype(int)
        r = j.groupby("grid_id")["_a"].agg(["size", "sum"])
        r.columns = [f"n_{name}", f"rawarea_{name}_m2"]
        return r

    raw = centroid_sums(osm_core, "osm").join(centroid_sums(ref, "ref"), how="outer").fillna(0)

    rows = []
    for gid in sorted(set(osm_d) | set(ref_d) | set(raw.index)):
        og, oa = osm_d.get(gid, (None, 0.0))
        rg, ra = ref_d.get(gid, (None, 0.0))
        inter = 0.0
        if og is not None and rg is not None:
            try:
                inter = float(og.intersection(rg).area)
            except Exception:
                inter = float(og.buffer(0).intersection(rg.buffer(0)).area)
        r = raw.loc[gid] if gid in raw.index else None
        rows.append({
            "grid_id": gid,
            "n_osm": int(r["n_osm"]) if r is not None else 0,
            "n_ref": int(r["n_ref"]) if r is not None else 0,
            "rawarea_osm_m2": float(r["rawarea_osm_m2"]) if r is not None else 0.0,
            "rawarea_ref_m2": float(r["rawarea_ref_m2"]) if r is not None else 0.0,
            "dissolved_osm_m2": oa,
            "dissolved_ref_m2": ra,
            "intersection_m2": inter,
            "ratio_area": (float(r["rawarea_osm_m2"]) / float(r["rawarea_ref_m2"])
                           if r is not None and r["rawarea_ref_m2"] > 0 else np.nan),
            "coverage_geo": inter / ra if ra > 0 else np.nan,
            "osm_in_ref": inter / oa if oa > 0 else np.nan,
        })
    return pd.DataFrame(rows)


# ── Reporting ─────────────────────────────────────────────────────────────────

def describe(v, label, width=30):
    v = pd.Series(v).dropna()
    if not len(v):
        print(f"  {label:<{width}} (no data)"); return
    print(f"  {label:<{width}} n={len(v):>4}  min {v.min():.4f} | q25 {v.quantile(.25):.4f} | "
          f"median {v.median():.4f} | q75 {v.quantile(.75):.4f} | max {v.max():.4f} | mean {v.mean():.4f}")


def run_stats(t, priority_ids, centre_dist, label, out_rows):
    occ = t[t["n_osm"] > 0].copy()
    occ = occ.merge(centre_dist, on="grid_id", how="left")
    gsum = pd.read_csv("data/processed/grid_solar_baseline_summary.csv")
    occ = occ.merge(gsum[["grid_id", "mean_score", "high_potential_ratio"]], on="grid_id", how="left")
    occ["is_priority"] = occ["grid_id"].isin(priority_ids)

    print(f"\n  --- correlations [{label}] ---")
    for metric in ["coverage_geo", "ratio_area"]:
        for other, lbl in [("mean_score", "mean screening score"),
                           ("high_potential_ratio", "high-potential ratio"),
                           ("dist_km", "distance from centre")]:
            sub = occ[[metric, other]].dropna()
            rho, p = stats.spearmanr(sub[metric], sub[other])
            sig = "" if p >= 0.05 else "  *"
            print(f"    Spearman({metric:<13}, {lbl:<22}) = {rho:+.4f}  p = {p:.4e}  n={len(sub)}{sig}")
            out_rows.append({"variant": label, "metric": metric, "vs": other,
                             "n": len(sub), "spearman_rho": rho, "p_value": p})
        print()

    a = occ.loc[occ.is_priority, "coverage_geo"].dropna()
    b = occ.loc[~occ.is_priority, "coverage_geo"].dropna()
    print(f"  --- priority vs rest, coverage_geo [{label}] ---")
    print(f"    {'group':<14} {'n':>4} {'min':>8} {'q25':>8} {'median':>8} {'q75':>8} {'max':>8} {'mean':>8}")
    for lb, v in [("priority", a), ("non-priority", b)]:
        print(f"    {lb:<14} {len(v):>4} {v.min():>8.4f} {v.quantile(.25):>8.4f} {v.median():>8.4f} "
              f"{v.quantile(.75):>8.4f} {v.max():>8.4f} {v.mean():>8.4f}")
    u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    auc = u / (len(a) * len(b))
    print(f"    Mann-Whitney U = {u:.1f}  p = {p:.4e}  AUC = {auc:.4f}  "
          f"rank-biserial r = {2*auc-1:+.4f}"
          f"{'   NOT significant' if p >= 0.05 else '   SIGNIFICANT'}")
    out_rows.append({"variant": label, "metric": "coverage_geo",
                     "vs": "priority_vs_rest_mannwhitney", "n": len(a) + len(b),
                     "spearman_rho": 2 * auc - 1, "p_value": p})
    return occ


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--osm_core", required=True)
    p.add_argument("--core_area", required=True)
    p.add_argument("--grid", required=True)
    p.add_argument("--priority", default="outputs/priority_grids.csv")
    p.add_argument("--release", default="2026-07-22.0")
    p.add_argument("--output_dir", default="outputs/validation/")
    return p.parse_args()


def main():
    setup_logging()
    args = parse_args()
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)

    osm_core = gpd.read_file(args.osm_core)[["geometry"]]
    core = gpd.read_file(args.core_area).to_crs(4326)
    grid = gpd.read_file(args.grid).to_crs(4326)
    priority_ids = set(pd.read_csv(args.priority)["grid_id"].astype(int))
    utm = osm_core.estimate_utm_crs()

    ovt = fetch_overture_with_sources(tuple(core.total_bounds), args.release)
    core_u = core.to_crs(utm).union_all()
    ovt_utm = ovt.to_crs(utm)
    ovt_core = ovt_utm[ovt_utm.geometry.centroid.within(core_u)]
    logging.info("Overture inside urban core: %d (%d OSM-sourced)",
                 len(ovt_core), int(ovt_core.is_osm_sourced.sum()))

    cent = grid.to_crs(utm).copy()
    centre = core_u.centroid
    cent["dist_km"] = cent.geometry.centroid.distance(centre) / 1000.0
    centre_dist = cent[["grid_id", "dist_km"]]

    variants = {
        "ALL Overture": ovt_core,
        "NON-OSM only": ovt_core[~ovt_core.is_osm_sourced],
    }

    R = "=" * 100
    all_tables, stat_rows = {}, []
    for label, ref in variants.items():
        print("\n" + R)
        print(f"  COMPARATOR: {label}   ({len(ref):,} buildings in the urban core)")
        print(R)
        t = build_table(osm_core, ref, grid, utm, label)
        all_tables[label] = t

        tot_osm_raw = t["rawarea_osm_m2"].sum()
        tot_ref_raw = t["rawarea_ref_m2"].sum()
        tot_osm_d = t["dissolved_osm_m2"].sum()
        tot_ref_d = t["dissolved_ref_m2"].sum()
        tot_int = t["intersection_m2"].sum()

        print(f"\n  aggregate over the urban core")
        print(f"    OSM   raw sum of polygon areas   {tot_osm_raw/1e6:8.4f} km2")
        print(f"    OSM   dissolved                  {tot_osm_d/1e6:8.4f} km2")
        print(f"    REF   raw sum of polygon areas   {tot_ref_raw/1e6:8.4f} km2")
        print(f"    REF   dissolved                  {tot_ref_d/1e6:8.4f} km2")
        print(f"    intersection (dissolved)         {tot_int/1e6:8.4f} km2")
        print()
        print(f"    (a) ratio of totals   OSM/REF          = {100*tot_osm_raw/tot_ref_raw:7.2f}%")
        print(f"    (b) GEOMETRIC COVERAGE  int/REF        = {100*tot_int/tot_ref_d:7.2f}%")
        print(f"        OSM area confirmed by REF int/OSM  = {100*tot_int/tot_osm_d:7.2f}%")

        occ = t[t["n_osm"] > 0]
        print(f"\n  per-cell distributions ({len(occ)} cells with OSM buildings)")
        describe(occ["ratio_area"], "(a) ratio_area")
        describe(occ["coverage_geo"], "(b) coverage_geo")
        describe(occ["osm_in_ref"], "    osm_in_ref")
        v = occ["coverage_geo"].dropna()
        print(f"    cells coverage_geo < 20% : {int((v<0.2).sum()):>4} ({100*(v<0.2).mean():.2f}%)")
        print(f"    cells coverage_geo < 50% : {int((v<0.5).sum()):>4} ({100*(v<0.5).mean():.2f}%)")
        ra = occ["ratio_area"].dropna()
        print(f"    cells ratio_area   > 1.0 : {int((ra>1.0).sum()):>4}   "
              f"(coverage_geo cannot exceed 1.0 by construction)")

        run_stats(t, priority_ids, centre_dist, label, stat_rows)

    merged = all_tables["ALL Overture"].add_suffix("_all").rename(columns={"grid_id_all": "grid_id"})
    nonosm = all_tables["NON-OSM only"].add_suffix("_nonosm").rename(columns={"grid_id_nonosm": "grid_id"})
    merged = merged.merge(nonosm, on="grid_id", how="outer")
    merged["is_priority"] = merged["grid_id"].isin(priority_ids)
    merged.to_csv(out / "completeness_geometric_per_grid.csv", index=False, float_format="%.6f")
    pd.DataFrame(stat_rows).to_csv(out / "completeness_geometric_summary.csv",
                                   index=False, float_format="%.6f")
    logging.info("Saved geometric completeness CSVs to %s", out)


if __name__ == "__main__":
    main()
