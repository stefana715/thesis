#!/usr/bin/env python3
"""
osm_completeness.py

Quantifies how complete the OSM building stock is relative to Overture Maps,
and — more importantly — whether the missing stock is spatially structured in a
way that would compromise the screening framework's priority grids.

Motivation
----------
The framework scores 33,374 OSM buildings municipality-wide and 18,855 in the
urban core. The Overture extract for the same region holds 1,076,716 buildings.
If OSM coverage is both low and spatially biased — in particular if it
correlates with which cells become priority grids — then the priority map would
be tracking survey density rather than solar potential.

What this script does
---------------------
1. Establishes the comparable region. The OSM extract follows the Changsha
   administrative boundary; the Overture extract used a bbox that does NOT
   contain it. Municipality-wide counts are therefore not comparable as-is, and
   are reported only over the intersection. The urban core lies entirely inside
   the Overture bbox, so urban-core figures are directly comparable.
2. Counts both datasets over the comparable regions.
3. Per 500 m cell: OSM and Overture building counts and rooftop areas, coverage
   by count and — more robustly — by area, since count ratios are distorted by
   whether a structure is mapped as one polygon or several.
4. Tests whether coverage is spatially structured: correlation with mean score
   and high-potential ratio, priority vs non-priority distributions with a
   Mann-Whitney U test, and correlation with distance from the urban centre.
5. Reads Overture `sources` directly from S3 to establish provenance. If the
   Changsha stock is overwhelmingly OSM-derived, Overture is not an independent
   completeness reference and the coverage ratio means something different.

Outputs (all new; nothing existing is modified)
-----------------------------------------------
outputs/validation/completeness_per_grid.csv
outputs/validation/completeness_summary.csv
outputs/validation/completeness_provenance.csv

Usage
-----
    python src/validation/osm_completeness.py \
        --osm_raw    data/raw/buildings_changsha.geojson \
        --osm_core   data/processed/buildings_changsha_urban_core_solar_baseline.geojson \
        --study_area data/raw/study_area_changsha.geojson \
        --core_area  data/processed/study_area_changsha_urban_core.geojson \
        --grid       data/processed/grid_changsha_urban_core_solar_baseline.geojson \
        --overture   data/external/overture_buildings_changsha.geojsonl \
        --priority   outputs/priority_grids.csv \
        --output_dir outputs/validation/
"""

import argparse
import json
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import stats
from shapely.geometry import box

# bbox used for the Overture extraction (osm_quality_validation.CHANGSHA_BBOX)
OVERTURE_BBOX = (111.8, 27.8, 113.2, 28.6)
GRID_SIZE_M = 500


def setup_logging():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(message)s")


# ── Loading ───────────────────────────────────────────────────────────────────

def load_overture(path: Path, clip_bounds=None) -> gpd.GeoDataFrame:
    """Stream the GeoJSONL, optionally keeping only features whose centroid
    falls inside clip_bounds (minx, miny, maxx, maxy) to bound memory."""
    feats = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                feats.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    gdf = gpd.GeoDataFrame.from_features(
        {"type": "FeatureCollection", "features": feats}, crs="EPSG:4326")
    logging.info("Overture features loaded: %d", len(gdf))
    if clip_bounds is not None:
        minx, miny, maxx, maxy = clip_bounds
        gdf = gdf.cx[minx:maxx, miny:maxy]
        logging.info("  after bbox pre-filter: %d", len(gdf))
    return gdf


def count_within(points: gpd.GeoDataFrame, polygon_gdf: gpd.GeoDataFrame) -> int:
    """Count point features falling inside a (possibly multi-part) polygon."""
    poly = polygon_gdf.to_crs(points.crs).union_all()
    return int(points.geometry.within(poly).sum())


# ── Per-grid table ────────────────────────────────────────────────────────────

def per_grid_table(osm_core, overture, grid, utm):
    """OSM and Overture counts + rooftop areas per 500 m cell."""
    g = grid.to_crs(utm)[["grid_id", "geometry"]].copy()

    def summarise(gdf, prefix):
        p = gdf.to_crs(utm).copy()
        p["_area"] = p.geometry.area
        cent = p.copy()
        cent["geometry"] = cent.geometry.centroid
        j = gpd.sjoin(cent[["geometry", "_area"]], g, how="left", predicate="within")
        j = j.dropna(subset=["grid_id"])
        j["grid_id"] = j["grid_id"].astype(int)
        out = j.groupby("grid_id")["_area"].agg(["size", "sum"])
        out.columns = [f"n_{prefix}", f"area_{prefix}_m2"]
        return out

    osm_s = summarise(osm_core, "osm")
    ovt_s = summarise(overture, "overture")

    t = g.set_index("grid_id")[[]].join(osm_s, how="left").join(ovt_s, how="left")
    for c in t.columns:
        t[c] = t[c].fillna(0)
    t["coverage_count"] = np.where(t["n_overture"] > 0, t["n_osm"] / t["n_overture"], np.nan)
    t["coverage_area"] = np.where(t["area_overture_m2"] > 0,
                                  t["area_osm_m2"] / t["area_overture_m2"], np.nan)
    return t.reset_index()


# ── Provenance ────────────────────────────────────────────────────────────────

def overture_provenance(core_bounds, release):
    """
    Read Overture `sources` for buildings in the urban-core bbox straight from
    S3 and tally which datasets they come from. Uses a targeted read so the
    cached extract is left untouched.
    """
    try:
        import pyarrow.compute as pc
        import pyarrow.dataset as ds
        import pyarrow.fs as fs
    except ImportError:
        logging.warning("pyarrow unavailable — skipping provenance")
        return None

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "oqv", Path(__file__).resolve().parents[2] / "osm_quality_validation.py")
    oqv = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oqv)

    try:
        paths = oqv._find_building_parquet_files(release, core_bounds)
    except Exception as e:
        logging.error("STAC lookup failed: %s", e)
        return None

    xmin, ymin, xmax, ymax = core_bounds
    filt = ((pc.field("bbox", "xmin") < xmax) & (pc.field("bbox", "xmax") > xmin) &
            (pc.field("bbox", "ymin") < ymax) & (pc.field("bbox", "ymax") > ymin))
    s3 = fs.S3FileSystem(anonymous=True, region="us-west-2")

    tally, total = {}, 0
    for p in paths:
        try:
            dataset = ds.dataset(p, filesystem=s3)
            cols = [c for c in ["sources", "bbox"] if c in dataset.schema.names]
            if "sources" not in cols:
                logging.warning("no 'sources' column in %s", p)
                continue
            for batch in dataset.to_batches(filter=filt, columns=cols):
                for rec in batch.column("sources").to_pylist():
                    total += 1
                    names = set()
                    for s in (rec or []):
                        d = (s or {}).get("dataset")
                        if d:
                            names.add(str(d))
                    key = " + ".join(sorted(names)) if names else "(unknown)"
                    tally[key] = tally.get(key, 0) + 1
        except Exception as e:
            logging.error("provenance read failed for %s: %s", p, e)

    if not total:
        return None
    rows = [{"dataset_combination": k, "n_buildings": v, "pct": 100.0 * v / total}
            for k, v in sorted(tally.items(), key=lambda kv: -kv[1])]
    rows.append({"dataset_combination": "TOTAL", "n_buildings": total, "pct": 100.0})
    return pd.DataFrame(rows)


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--osm_raw", required=True)
    p.add_argument("--osm_core", required=True)
    p.add_argument("--study_area", required=True)
    p.add_argument("--core_area", required=True)
    p.add_argument("--grid", required=True)
    p.add_argument("--overture", required=True)
    p.add_argument("--priority", default="outputs/priority_grids.csv")
    p.add_argument("--release", default="2026-07-22.0")
    p.add_argument("--output_dir", default="outputs/validation/")
    p.add_argument("--skip_provenance", action="store_true")
    return p.parse_args()


def main():
    setup_logging()
    args = parse_args()
    out = Path(args.output_dir); out.mkdir(parents=True, exist_ok=True)
    R = lambda c="=", n=94: c * n

    study = gpd.read_file(args.study_area).to_crs(4326)
    core = gpd.read_file(args.core_area).to_crs(4326)
    grid = gpd.read_file(args.grid).to_crs(4326)
    osm_core = gpd.read_file(args.osm_core)
    priority_ids = set(pd.read_csv(args.priority)["grid_id"].astype(int))

    utm = osm_core.estimate_utm_crs()

    # ── 1. comparable extent ─────────────────────────────────────────────────
    bbox_poly = gpd.GeoDataFrame(geometry=[box(*OVERTURE_BBOX)], crs=4326)
    inter = gpd.overlay(study[["geometry"]], bbox_poly, how="intersection")
    study_area_km2 = study.to_crs(utm).area.sum() / 1e6
    inter_area_km2 = inter.to_crs(utm).area.sum() / 1e6
    core_area_km2 = core.to_crs(utm).area.sum() / 1e6

    print("\n" + R())
    print("  1. SPATIAL EXTENTS")
    print(R())
    sb, cb = study.total_bounds, core.total_bounds
    print(f"  OSM extract boundary : Changsha administrative (osmnx place query)")
    print(f"    bounds  ({sb[0]:.4f}, {sb[1]:.4f}, {sb[2]:.4f}, {sb[3]:.4f})   area {study_area_km2:,.1f} km2")
    print(f"  Overture extract     : bbox {OVERTURE_BBOX}")
    print(f"  Urban core           : bounds ({cb[0]:.4f}, {cb[1]:.4f}, {cb[2]:.4f}, {cb[3]:.4f})   area {core_area_km2:,.1f} km2")
    print(f"\n  Admin boundary inside Overture bbox : "
          f"{sb[0]>=OVERTURE_BBOX[0] and sb[1]>=OVERTURE_BBOX[1] and sb[2]<=OVERTURE_BBOX[2] and sb[3]<=OVERTURE_BBOX[3]}")
    print(f"  Urban core inside Overture bbox     : "
          f"{cb[0]>=OVERTURE_BBOX[0] and cb[1]>=OVERTURE_BBOX[1] and cb[2]<=OVERTURE_BBOX[2] and cb[3]<=OVERTURE_BBOX[3]}")
    print(f"  Intersection (admin AND bbox)       : {inter_area_km2:,.1f} km2 "
          f"({100*inter_area_km2/study_area_km2:.1f}% of the municipality)")

    # ── 2. counts over comparable regions ────────────────────────────────────
    ovt_all = load_overture(Path(args.overture))
    ovt_cent = ovt_all.copy()
    ovt_cent["geometry"] = ovt_cent.geometry.centroid

    osm_raw = gpd.read_file(args.osm_raw, columns=["geometry"]) \
        if "columns" in gpd.read_file.__code__.co_varnames else gpd.read_file(args.osm_raw)
    osm_raw = osm_raw[osm_raw.geometry.notnull()]
    osm_raw_cent = osm_raw.to_crs(4326).copy()
    osm_raw_cent["geometry"] = osm_raw_cent.geometry.centroid

    n_osm_inter = count_within(osm_raw_cent, inter)
    n_ovt_inter = count_within(ovt_cent, inter)
    n_osm_core = len(osm_core)
    n_ovt_core = count_within(ovt_cent, core)

    print("\n" + R())
    print("  2. BUILDING COUNTS OVER COMPARABLE REGIONS")
    print(R())
    print(f"  {'region':<44} {'OSM':>10} {'Overture':>12} {'coverage':>10}")
    print(R("-"))
    print(f"  {'municipality (NOT comparable — bbox clips it)':<44} "
          f"{len(osm_raw):>10,} {'n/a':>12} {'n/a':>10}")
    print(f"  {'admin boundary AND Overture bbox':<44} "
          f"{n_osm_inter:>10,} {n_ovt_inter:>12,} {100*n_osm_inter/max(n_ovt_inter,1):>9.2f}%")
    print(f"  {'urban core':<44} {n_osm_core:>10,} {n_ovt_core:>12,} "
          f"{100*n_osm_core/max(n_ovt_core,1):>9.2f}%")

    # ── 3-5. per-grid coverage ───────────────────────────────────────────────
    ovt_core = ovt_all[ovt_all.geometry.centroid.within(core.union_all())]
    logging.info("Overture buildings inside urban core: %d", len(ovt_core))

    t = per_grid_table(osm_core, ovt_core, grid, utm)
    gsum = pd.read_csv("data/processed/grid_solar_baseline_summary.csv")
    t = t.merge(gsum[["grid_id", "mean_score", "high_potential_ratio", "building_count"]],
                on="grid_id", how="left")
    t["is_priority"] = t["grid_id"].isin(priority_ids)
    t["is_occupied"] = t["n_osm"] > 0

    # distance from urban centre
    centre = core.to_crs(utm).union_all().centroid
    cent_grid = grid.to_crs(utm).copy()
    cent_grid["dist_km"] = cent_grid.geometry.centroid.distance(centre) / 1000.0
    t = t.merge(cent_grid[["grid_id", "dist_km"]], on="grid_id", how="left")

    occ = t[t["is_occupied"]].copy()

    print("\n" + R())
    print(f"  3. PER-CELL COVERAGE  ({len(occ)} occupied cells of {len(t)})")
    print(R())
    for col, label in [("coverage_count", "coverage by BUILDING COUNT"),
                       ("coverage_area", "coverage by ROOFTOP AREA")]:
        v = occ[col].dropna()
        print(f"\n  {label}  (n={len(v)})")
        print(f"    min {v.min():.4f} | q25 {v.quantile(.25):.4f} | median {v.median():.4f} "
              f"| q75 {v.quantile(.75):.4f} | max {v.max():.4f} | mean {v.mean():.4f}")
        print(f"    cells < 20% : {int((v<0.20).sum()):>4} ({100*(v<0.20).mean():.2f}%)")
        print(f"    cells < 50% : {int((v<0.50).sum()):>4} ({100*(v<0.50).mean():.2f}%)")
        print(f"    cells > 100%: {int((v>1.0).sum()):>4} ({100*(v>1.0).mean():.2f}%)")

    n_empty_osm = int(((t["n_osm"] == 0) & (t["n_overture"] > 0)).sum())
    print(f"\n  cells with Overture buildings but ZERO OSM buildings: {n_empty_osm} "
          f"of {int((t['n_overture']>0).sum())} Overture-occupied cells")

    print("\n" + R())
    print("  4-5. IS THE MISSING STOCK SPATIALLY STRUCTURED?")
    print(R())
    rows = []
    for col in ["coverage_count", "coverage_area"]:
        for other, lbl in [("mean_score", "mean screening score"),
                           ("high_potential_ratio", "high-potential ratio"),
                           ("dist_km", "distance from urban centre")]:
            sub = occ[[col, other]].dropna()
            rho, p = stats.spearmanr(sub[col], sub[other])
            rows.append({"coverage_metric": col, "vs": other, "n": len(sub),
                         "spearman_rho": rho, "p_value": p})
            print(f"  Spearman({col:<15}, {lbl:<28}) = {rho:+.4f}   p = {p:.4e}   n={len(sub)}")
        print()

    print(R("-"))
    print("  Priority (146) vs non-priority cells — coverage_area")
    print(R("-"))
    a = occ.loc[occ["is_priority"], "coverage_area"].dropna()
    b = occ.loc[~occ["is_priority"], "coverage_area"].dropna()
    print(f"  {'group':<16} {'n':>5} {'min':>8} {'q25':>8} {'median':>8} {'q75':>8} {'max':>8} {'mean':>8}")
    for lbl, v in [("priority", a), ("non-priority", b)]:
        print(f"  {lbl:<16} {len(v):>5} {v.min():>8.4f} {v.quantile(.25):>8.4f} "
              f"{v.median():>8.4f} {v.quantile(.75):>8.4f} {v.max():>8.4f} {v.mean():>8.4f}")
    u, pu = stats.mannwhitneyu(a, b, alternative="two-sided")
    n1, n2 = len(a), len(b)
    auc = u / (n1 * n2)
    print(f"\n  Mann-Whitney U = {u:.1f}   p = {pu:.4e}   "
          f"rank-biserial r = {2*auc-1:+.4f}   (AUC = {auc:.4f})")
    print("  AUC 0.5 means the two groups' coverage distributions are indistinguishable.")

    stats_rows = pd.DataFrame(rows)
    stats_rows.loc[len(stats_rows)] = {"coverage_metric": "coverage_area",
                                       "vs": "priority_vs_rest_mannwhitney_p",
                                       "n": n1 + n2, "spearman_rho": 2 * auc - 1, "p_value": pu}

    # ── 6. provenance ────────────────────────────────────────────────────────
    prov = None
    if not args.skip_provenance:
        print("\n" + R())
        print("  6. OVERTURE PROVENANCE IN THE URBAN CORE")
        print(R())
        prov = overture_provenance(tuple(core.total_bounds), args.release)
        if prov is None:
            print("  provenance read unavailable")
        else:
            print(f"  {'source dataset(s)':<52} {'buildings':>12} {'pct':>8}")
            print(R("-"))
            for _, r in prov.head(15).iterrows():
                print(f"  {r['dataset_combination'][:50]:<52} {int(r['n_buildings']):>12,} {r['pct']:>7.2f}%")

    # ── save ─────────────────────────────────────────────────────────────────
    t.to_csv(out / "completeness_per_grid.csv", index=False, float_format="%.6f")
    stats_rows.to_csv(out / "completeness_summary.csv", index=False, float_format="%.6f")
    if prov is not None:
        prov.to_csv(out / "completeness_provenance.csv", index=False, float_format="%.4f")
    logging.info("Saved completeness CSVs to %s", out)


if __name__ == "__main__":
    main()
