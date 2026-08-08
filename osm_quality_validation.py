"""
Validation B: OSM Footprint Quality Assessment (Automated)
===========================================================
Compares OSM building footprint areas against Overture Maps building footprints
as an independent reference dataset derived from satellite/aerial imagery.

Strategy:
  Overture Maps buildings are aggregated from multiple authoritative sources
  (including Microsoft ML footprints, government cadastre, and others),
  completely independent of OSM. By spatially matching OSM buildings to Overture
  buildings and comparing their footprint areas, we can assess the reliability
  of the primary input data without manual measurement.

Matching logic:
  For each sampled OSM building, find the Overture building whose centroid is
  nearest to the OSM centroid AND whose intersection-over-union (IoU) exceeds
  a threshold. This avoids false matches in dense areas.

Usage:
  1. Download Overture Maps building footprints for Changsha:
       python osm_quality_validation.py --download-only

     This reads the two ~5M-row parquet files on Overture's S3, filters to
     the Changsha bbox, and saves as:
       data/external/overture_buildings_changsha.geojsonl

  2. Run the full validation:
       python osm_quality_validation.py

  3. Outputs:
     - outputs/validation/osm_quality_results.csv  (per-building comparison)
     - outputs/validation/osm_quality_summary.csv  (aggregate statistics)
     - figure/osm_quality_scatter.png              (scatter plot)

Requirements: geopandas, pandas, numpy, scipy, matplotlib, shapely, pyarrow,
              overturemaps (pip install overturemaps)
"""

from pathlib import Path
import logging
import argparse
import json
import io
from urllib.request import urlopen

import os

import numpy as np
import pandas as pd
import geopandas as gpd
from scipy.stats import spearmanr, pearsonr
from shapely.geometry import shape
from shapely import wkb as shapely_wkb
import matplotlib.pyplot as plt

# ============================================================
# CONFIGURATION
# ============================================================

OSM_BUILDINGS_PATH = Path("data/processed/buildings_changsha_urban_core_solar_baseline.geojson")

# Overture Maps output path
OVERTURE_PATH = Path("data/external/overture_buildings_changsha.geojsonl")

OUTPUT_DIR = Path("outputs/validation")
OUTPUT_CSV = OUTPUT_DIR / "osm_quality_results.csv"
OUTPUT_SUMMARY = OUTPUT_DIR / "osm_quality_summary.csv"
OUTPUT_FIG = Path("figure/osm_quality_scatter.png")

# Sampling
N_SAMPLE = 100
N_STRATA = 5  # quintiles by solar_potential_score
RANDOM_SEED = 42

# Matching parameters
MAX_CENTROID_DISTANCE_M = 30  # max distance between centroids for a match
MIN_IOU = 0.3                 # minimum intersection-over-union for a valid match

# Changsha bounding box (minx, miny, maxx, maxy)
CHANGSHA_BBOX = (111.8, 27.8, 113.2, 28.6)

# Overture release (None = auto-detect latest)
OVERTURE_RELEASE = None


# ============================================================
# LOGGING
# ============================================================

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


# ============================================================
# OVERTURE MAPS DOWNLOAD
# ============================================================

def _get_latest_release():
    """Fetch the latest Overture release tag from the STAC catalog."""
    try:
        from overturemaps.core import get_latest_release
        return get_latest_release()
    except Exception:
        # Fallback: read catalog directly
        url = "https://stac.overturemaps.org/catalog.json"
        with urlopen(url, timeout=20) as r:
            catalog = json.load(r)
        return catalog.get("latest", "2026-03-18.0")


def _find_building_parquet_files(release, bbox):
    """
    Use the Overture STAC-geoparquet index to find which parquet files
    contain buildings overlapping the given bbox.

    Returns list of S3 paths (without s3:// prefix).
    """
    import pyarrow.parquet as pq
    import pyarrow.compute as pc

    stac_url = f"https://stac.overturemaps.org/{release}/collections.parquet"
    logging.info("Fetching STAC index from %s", stac_url)
    with urlopen(stac_url, timeout=60) as r:
        data = r.read()

    table = pq.read_table(io.BytesIO(data))
    xmin, ymin, xmax, ymax = bbox

    filt = (
        (pc.field("collection") == "building") &
        (pc.field("type") == "Feature") &
        (pc.field("bbox", "xmin") < xmax) &
        (pc.field("bbox", "xmax") > xmin) &
        (pc.field("bbox", "ymin") < ymax) &
        (pc.field("bbox", "ymax") > ymin)
    )
    matching = table.filter(filt).to_pandas()
    logging.info("STAC index: %d parquet file(s) overlap Changsha bbox", len(matching))

    s3_paths = []
    for _, row in matching.iterrows():
        assets = row["assets"]
        # Overture 2026 asset structure: assets['aws']['alternate']['s3']['href']
        try:
            href = assets["aws"]["alternate"]["s3"]["href"]
        except (KeyError, TypeError):
            try:
                href = assets["aws"]["href"]
            except (KeyError, TypeError):
                # Legacy: assets['aws-s3']['href']
                href = assets.get("aws-s3", {}).get("href", "")
        if href.startswith("s3://"):
            href = href[len("s3://"):]
        if href:
            s3_paths.append(href)
            logging.info("  file: %s  rows: %s", href.split("/")[-1], row.get("num_rows", "?"))

    return s3_paths


def download_overture_buildings(output_path=None, bbox=None, release=None):
    """
    Download Overture Maps building footprints for the Changsha bbox.

    Uses the STAC-geoparquet index to locate relevant parquet shards, then
    reads them from S3 with predicate-pushdown filtering to the bbox.
    Saves the result as GeoJSONL.
    """
    try:
        import pyarrow as pa
        import pyarrow.compute as pc
        import pyarrow.fs as fs
        import pyarrow.dataset as ds
    except ImportError:
        print("ERROR: pyarrow required. Run: pip install overturemaps")
        return False

    if output_path is None:
        output_path = OVERTURE_PATH
    if bbox is None:
        bbox = CHANGSHA_BBOX
    if release is None:
        release = _get_latest_release()

    output_path = Path(output_path)
    os.makedirs(output_path.parent, exist_ok=True)

    print(f"Overture release: {release}")
    print(f"Changsha bbox:    {bbox}")
    print()

    # Step 1: find which parquet files overlap our bbox
    try:
        s3_paths = _find_building_parquet_files(release, bbox)
    except Exception as e:
        logging.error("STAC index lookup failed: %s — falling back to full path scan", e)
        theme = "buildings"
        s3_paths = [f"overturemaps-us-west-2/release/{release}/theme={theme}/type=building/"]

    if not s3_paths:
        print("No Overture parquet files found for this bbox.")
        return False

    # Step 2: read from S3 with bbox filter
    xmin, ymin, xmax, ymax = bbox
    filter_expr = (
        (pc.field("bbox", "xmin") < xmax) &
        (pc.field("bbox", "xmax") > xmin) &
        (pc.field("bbox", "ymin") < ymax) &
        (pc.field("bbox", "ymax") > ymin)
    )

    s3 = fs.S3FileSystem(anonymous=True, region="us-west-2")

    all_batches = []
    for path in s3_paths:
        print(f"Reading {path.split('/')[-1]} from S3...")
        try:
            dataset = ds.dataset(path, filesystem=s3)
            # read only geometry + bbox columns to save memory
            cols = ["geometry", "bbox"]
            available = [f.name for f in dataset.schema]
            cols = [c for c in cols if c in available]
            batches = dataset.to_batches(filter=filter_expr, columns=cols)
            n = 0
            for batch in batches:
                if batch.num_rows > 0:
                    all_batches.append(batch)
                    n += batch.num_rows
            print(f"  → {n:,} buildings in bbox")
        except Exception as e:
            print(f"  ERROR reading {path}: {e}")

    if not all_batches:
        print("No buildings retrieved from Overture.")
        return False

    # Step 3: assemble table and convert WKB geometry to GeoJSON features
    schema = all_batches[0].schema
    table = pa.Table.from_batches(all_batches, schema=schema)
    total = table.num_rows
    print(f"\nTotal Overture buildings in Changsha area: {total:,}")
    print(f"Writing GeoJSONL to {output_path} ...")

    geom_col = table.column("geometry")

    written = 0
    skipped = 0
    with open(output_path, "w") as fout:
        for i in range(total):
            raw = geom_col[i].as_py()
            if raw is None:
                skipped += 1
                continue
            try:
                if isinstance(raw, (bytes, bytearray)):
                    geom = shapely_wkb.loads(raw)
                else:
                    geom = shape(raw)
                # Final bbox clip
                cx, cy = geom.centroid.x, geom.centroid.y
                if not (xmin <= cx <= xmax and ymin <= cy <= ymax):
                    skipped += 1
                    continue
                feat = {
                    "type": "Feature",
                    "geometry": geom.__geo_interface__,
                    "properties": {}
                }
                fout.write(json.dumps(feat) + "\n")
                written += 1
            except Exception:
                skipped += 1

    print(f"Written: {written:,}  skipped/invalid: {skipped:,}")
    print(f"Saved: {output_path}")
    return True


# ============================================================
# LOAD DATA
# ============================================================

def load_overture_data():
    """Load Overture building footprints from the cached GeoJSONL file."""
    if not OVERTURE_PATH.exists():
        return None

    logging.info("Loading Overture data from: %s", OVERTURE_PATH)
    features = []
    with open(OVERTURE_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    features.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    if not features:
        logging.warning("No features parsed from %s", OVERTURE_PATH)
        return None

    gdf = gpd.GeoDataFrame.from_features(
        {"type": "FeatureCollection", "features": features},
        crs="EPSG:4326"
    )
    logging.info("Loaded %d Overture buildings", len(gdf))
    return gdf


# ============================================================
# STRATIFIED SAMPLING
# ============================================================

def stratified_sample(buildings, n_total=N_SAMPLE, n_strata=N_STRATA, seed=RANDOM_SEED):
    """Sample buildings stratified by solar_potential_score quintiles."""
    buildings = buildings.copy()
    buildings["score_quintile"] = pd.qcut(
        buildings["solar_potential_score"], q=n_strata,
        labels=[f"Q{i+1}" for i in range(n_strata)]
    )

    per_stratum = n_total // n_strata
    rng = np.random.RandomState(seed)

    sampled = []
    for q in [f"Q{i+1}" for i in range(n_strata)]:
        stratum = buildings[buildings["score_quintile"] == q]
        n = min(per_stratum, len(stratum))
        sampled.append(stratum.sample(n=n, random_state=rng))

    return pd.concat(sampled)


# ============================================================
# SPATIAL MATCHING
# ============================================================

def compute_iou(geom_a, geom_b):
    """Compute intersection-over-union between two geometries."""
    try:
        intersection = geom_a.intersection(geom_b).area
        union = geom_a.union(geom_b).area
        return intersection / union if union > 0 else 0
    except Exception:
        return 0


def match_buildings(osm_sample, ref_buildings, max_dist_m=MAX_CENTROID_DISTANCE_M, min_iou=MIN_IOU):
    """
    For each OSM building in the sample, find the best matching Overture building.

    Matching criteria:
      1. Centroid-to-centroid distance ≤ max_dist_m (in projected metres)
      2. IoU ≥ min_iou

    Returns DataFrame with matched pairs and area comparisons.
    """
    utm_crs = osm_sample.estimate_utm_crs()
    osm_proj = osm_sample.to_crs(utm_crs)
    ref_proj = ref_buildings.to_crs(utm_crs)

    osm_proj["centroid"] = osm_proj.geometry.centroid
    ref_proj["centroid"] = ref_proj.geometry.centroid

    ref_sindex = ref_proj.sindex

    results = []
    for idx, osm_row in osm_proj.iterrows():
        osm_centroid = osm_row["centroid"]
        osm_area = osm_row.geometry.area

        buffer = osm_centroid.buffer(max_dist_m)
        candidates_idx = list(ref_sindex.intersection(buffer.bounds))

        if not candidates_idx:
            results.append({
                "osm_index": idx,
                "matched": False,
                "osm_area_m2": osm_area,
                "ref_area_m2": np.nan,
                "area_diff_pct": np.nan,
                "iou": np.nan,
                "centroid_dist_m": np.nan,
            })
            continue

        best_iou = 0
        best_match = None
        best_dist = np.nan

        for ci in candidates_idx:
            ref_row = ref_proj.iloc[ci]
            dist = osm_centroid.distance(ref_row["centroid"])
            if dist > max_dist_m:
                continue
            iou = compute_iou(osm_row.geometry, ref_row.geometry)
            if iou > best_iou:
                best_iou = iou
                best_match = ref_row
                best_dist = dist

        if best_match is not None and best_iou >= min_iou:
            ref_area = best_match.geometry.area
            area_diff = (osm_area - ref_area) / ref_area * 100 if ref_area > 0 else np.nan
            results.append({
                "osm_index": idx,
                "matched": True,
                "osm_area_m2": osm_area,
                "ref_area_m2": ref_area,
                "area_diff_pct": area_diff,
                "iou": best_iou,
                "centroid_dist_m": best_dist,
            })
        else:
            results.append({
                "osm_index": idx,
                "matched": False,
                "osm_area_m2": osm_area,
                "ref_area_m2": np.nan,
                "area_diff_pct": np.nan,
                "iou": best_iou if best_iou > 0 else np.nan,
                "centroid_dist_m": best_dist,
            })

    return pd.DataFrame(results)


# ============================================================
# ANALYSIS AND OUTPUT
# ============================================================

def compute_statistics(results):
    """Compute summary statistics from matched building pairs."""
    matched = results[results["matched"]].copy()
    n_matched = len(matched)
    n_total = len(results)
    match_rate = n_matched / n_total * 100

    if n_matched < 10:
        logging.error("Too few matches (%d). Check Overture data coverage.", n_matched)
        return None

    r_pearson, p_pearson = pearsonr(matched["osm_area_m2"], matched["ref_area_m2"])
    r_spearman, p_spearman = spearmanr(matched["osm_area_m2"], matched["ref_area_m2"])

    mape = matched["area_diff_pct"].abs().mean()
    exceed_20pct = (matched["area_diff_pct"].abs() > 20).sum()
    exceed_20pct_pct = exceed_20pct / n_matched * 100

    mean_iou = matched["iou"].mean()

    return {
        "n_sampled": n_total,
        "n_matched": n_matched,
        "match_rate_pct": round(match_rate, 1),
        "pearson_r": round(r_pearson, 3),
        "pearson_p": p_pearson,
        "spearman_rho": round(r_spearman, 3),
        "spearman_p": p_spearman,
        "mape_pct": round(mape, 1),
        "exceed_20pct_count": exceed_20pct,
        "exceed_20pct_pct": round(exceed_20pct_pct, 1),
        "mean_iou": round(mean_iou, 3),
        "mean_osm_area": round(matched["osm_area_m2"].mean(), 1),
        "mean_ref_area": round(matched["ref_area_m2"].mean(), 1),
    }


def make_scatter(results, summary, output_path):
    """Scatter plot: OSM footprint area vs Overture footprint area."""
    os.makedirs(output_path.parent, exist_ok=True)
    matched = results[results["matched"]].copy()

    fig, ax = plt.subplots(figsize=(7, 6))

    ax.scatter(matched["ref_area_m2"], matched["osm_area_m2"],
               alpha=0.6, s=30, c="#4C72B0", edgecolors="white", linewidth=0.5)

    max_val = max(matched["osm_area_m2"].max(), matched["ref_area_m2"].max()) * 1.1
    ax.plot([0, max_val], [0, max_val], "k--", linewidth=1, alpha=0.5, label="1:1 line")

    x_line = np.linspace(0, max_val, 100)
    ax.fill_between(x_line, x_line * 0.8, x_line * 1.2,
                    alpha=0.1, color="green", label="±20% band")

    ax.text(0.04, 0.96,
            f"n = {summary['n_matched']}\n"
            f"Pearson r = {summary['pearson_r']:.3f}\n"
            f"Spearman ρ = {summary['spearman_rho']:.3f}\n"
            f"MAPE = {summary['mape_pct']:.1f}%\n"
            f">{'>'}20% error: {summary['exceed_20pct_pct']:.1f}%\n"
            f"Mean IoU = {summary['mean_iou']:.3f}",
            transform=ax.transAxes, va="top", ha="left", fontsize=9,
            bbox=dict(boxstyle="round,pad=0.4", fc="white", ec="0.7", alpha=0.9))

    ax.set_xlabel("Overture Maps building footprint area (m²)", fontsize=11)
    ax.set_ylabel("OSM building footprint area (m²)", fontsize=11)
    ax.set_title("OSM Footprint Quality: Comparison with Overture Maps Buildings", fontsize=11)
    ax.legend(loc="lower right", fontsize=9)
    ax.set_xlim(0, max_val)
    ax.set_ylim(0, max_val)
    ax.set_aspect("equal")

    plt.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    logging.info("Saved figure: %s", output_path)


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="OSM footprint quality assessment vs Overture Maps"
    )
    parser.add_argument("--download-only", action="store_true",
                        help="Download Overture buildings for Changsha and exit")
    parser.add_argument("--release", default=None,
                        help="Overture release tag (default: auto-detect latest)")
    args = parser.parse_args()

    setup_logging()

    release = args.release or OVERTURE_RELEASE

    if args.download_only:
        if release is None:
            release = _get_latest_release()
        ok = download_overture_buildings(release=release)
        if ok:
            print("\nDownload complete. Now run: python osm_quality_validation.py")
        return

    # ---- Load OSM buildings ----
    logging.info("Loading OSM buildings from %s", OSM_BUILDINGS_PATH)
    osm = gpd.read_file(OSM_BUILDINGS_PATH)
    osm["solar_potential_score"] = pd.to_numeric(osm["solar_potential_score"], errors="coerce")
    logging.info("OSM buildings loaded: %d", len(osm))

    # ---- Load Overture reference ----
    ref = load_overture_data()
    if ref is None:
        print()
        print("=" * 60)
        print("Overture Maps data not found.")
        print("=" * 60)
        print()
        print("Run first:")
        print("  python osm_quality_validation.py --download-only")
        print()
        print(f"Expected: {OVERTURE_PATH}")
        return

    # ---- Filter reference to study area ----
    logging.info("Filtering Overture to study bbox...")
    ref_filtered = ref.cx[
        CHANGSHA_BBOX[0]:CHANGSHA_BBOX[2],
        CHANGSHA_BBOX[1]:CHANGSHA_BBOX[3]
    ]
    logging.info("Overture buildings in study area: %d", len(ref_filtered))

    if len(ref_filtered) < 100:
        logging.error("Too few Overture buildings. Check data coverage.")
        return

    # ---- Stratified sample ----
    logging.info("Sampling %d OSM buildings (stratified by score quintile)...", N_SAMPLE)
    sample = stratified_sample(osm, N_SAMPLE)
    logging.info("Sampled %d buildings", len(sample))

    # ---- Match ----
    logging.info("Matching OSM buildings to Overture footprints...")
    results = match_buildings(sample, ref_filtered)
    n_matched = results["matched"].sum()
    logging.info(
        "Matched: %d / %d (%.1f%%)",
        n_matched, len(results), n_matched / len(results) * 100
    )

    # ---- Statistics ----
    summary = compute_statistics(results)
    if summary is None:
        return

    # ---- Save outputs ----
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results.to_csv(OUTPUT_CSV, index=False)
    pd.DataFrame([summary]).to_csv(OUTPUT_SUMMARY, index=False)
    logging.info("Saved: %s", OUTPUT_CSV)
    logging.info("Saved: %s", OUTPUT_SUMMARY)

    # ---- Print summary ----
    print()
    print("=" * 60)
    print("OSM FOOTPRINT QUALITY ASSESSMENT RESULTS")
    print("(Reference: Overture Maps Buildings)")
    print("=" * 60)
    print(f"Buildings sampled:     {summary['n_sampled']}")
    print(f"Successfully matched:  {summary['n_matched']} ({summary['match_rate_pct']}%)")
    print(f"Pearson r:             {summary['pearson_r']}")
    print(f"Spearman ρ:            {summary['spearman_rho']}")
    print(f"MAPE:                  {summary['mape_pct']}%")
    print(f">20% error:            {summary['exceed_20pct_count']} ({summary['exceed_20pct_pct']}%)")
    print(f"Mean IoU:              {summary['mean_iou']}")
    print()

    # ---- Figure ----
    make_scatter(results, summary, OUTPUT_FIG)

    logging.info("Done.")


if __name__ == "__main__":
    main()
