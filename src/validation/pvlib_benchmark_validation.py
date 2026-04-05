#!/usr/bin/env python3
"""
pvlib_benchmark_validation.py

Validates the Changsha urban core solar screening baseline against a
pvlib physical benchmark for three representative 500 m grid zones.

Design
------
- Zone A  high-density / high-score  grid_id = 317
- Zone B  low-density  / low-score   grid_id = 34
- Zone C  medium                     grid_id = 1606

Per-building pvlib reference yield
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. Clear-sky Ineichen model  (lat=28.228, lon=112.939)
2. Flat roof: tilt=0°, azimuth=180°
3. Available roof area = footprint_area_m2 × 0.65
4. Simplified shading: for each neighbour within 50 m that is taller,
       shading_factor = max(0.5,  1.0 − 0.1 × Δh / distance)
   Multiple neighbours: multiply factors (floored at 0.5 overall).
5. Annual yield  = roof_area × shading_factor × 0.20 × annual_POA × 0.80
   (0.20 = panel efficiency, 0.80 = system performance ratio)

Validation metric
~~~~~~~~~~~~~~~~~
Spearman ρ and Kendall τ between pvlib yield rank and solar_potential_score
rank, per zone and combined, with two-sided p-values.

Usage
-----
    python src/validation/pvlib_benchmark_validation.py \
        --input  data/processed/buildings_changsha_urban_core_solar_baseline.geojson \
        --grid   data/processed/grid_changsha_urban_core_solar_baseline.geojson \
        --output_dir  outputs/validation/ \
        --figure_dir  figure/
"""

import argparse
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import pvlib
from scipy import stats

# ── Constants ────────────────────────────────────────────────────────────────

LATITUDE  = 28.228
LONGITUDE = 112.939
ALTITUDE  = 50.0
TIMEZONE  = "Asia/Shanghai"

ZONE_GRID_IDS = {
    "A_high":   317,
    "B_low":    34,
    "C_medium": 1606,
}

ROOF_COVERAGE   = 0.65   # fraction of footprint usable for panels
PANEL_EFF       = 0.20   # module efficiency
PERFORMANCE_RATIO = 0.80  # system PR (wiring, inverter, soiling)
SHADING_RADIUS  = 50.0   # metres — neighbour search radius
SHADING_COEFF   = 0.1    # reduction per unit Δh/distance
SHADING_FLOOR   = 0.5    # minimum shading factor


# ── Logging ──────────────────────────────────────────────────────────────────

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


# ── pvlib irradiance ─────────────────────────────────────────────────────────

def annual_clearsky_poa() -> float:
    """
    Annual plane-of-array irradiance (Wh/m²) for a flat roof at Changsha.
    Tilt=0 → POA equals GHI, so we just sum annual GHI from Ineichen.
    Cached as a module-level constant after first call.
    """
    times = pd.date_range(
        start="2019-01-01 00:00",
        end="2019-12-31 23:00",
        freq="h",
        tz=TIMEZONE,
    )
    location = pvlib.location.Location(
        latitude=LATITUDE,
        longitude=LONGITUDE,
        altitude=ALTITUDE,
        tz=TIMEZONE,
    )
    clearsky = location.get_clearsky(times, model="ineichen")
    # tilt=0 → POA global = GHI
    annual_poa = float(clearsky["ghi"].fillna(0).sum())
    logging.info("Annual clear-sky POA (flat roof, Changsha 2019): %.1f Wh/m²", annual_poa)
    return annual_poa


# ── Shading ──────────────────────────────────────────────────────────────────

def compute_shading_factors(gdf_zone: gpd.GeoDataFrame) -> pd.Series:
    """
    For every building, find neighbours within SHADING_RADIUS m that are
    taller and apply the shading formula from the design spec.

    Works in a projected CRS so distances are in metres.
    """
    gdf_proj = gdf_zone.to_crs(gdf_zone.estimate_utm_crs()).copy()
    gdf_proj["height"] = pd.to_numeric(gdf_proj["height_proxy_m"], errors="coerce").fillna(6.0)
    centroids = gdf_proj.geometry.centroid

    shading_factors = []
    heights  = gdf_proj["height"].values
    idx_list = list(gdf_proj.index)

    for i, (own_idx, own_h) in enumerate(zip(idx_list, heights)):
        cx, cy = centroids.iloc[i].x, centroids.iloc[i].y
        factor = 1.0

        for j, (nb_idx, nb_h) in enumerate(zip(idx_list, heights)):
            if i == j:
                continue
            nx, ny = centroids.iloc[j].x, centroids.iloc[j].y
            dist = ((cx - nx) ** 2 + (cy - ny) ** 2) ** 0.5
            if dist > SHADING_RADIUS:
                continue
            delta_h = nb_h - own_h
            if delta_h <= 0:
                continue
            # Taller neighbour within radius
            reduction = SHADING_COEFF * delta_h / max(dist, 0.1)
            factor *= max(SHADING_FLOOR, 1.0 - reduction)

        shading_factors.append(max(SHADING_FLOOR, factor))

    return pd.Series(shading_factors, index=gdf_zone.index, name="shading_factor")


# ── Yield computation ────────────────────────────────────────────────────────

def compute_pvlib_yield(gdf_zone: gpd.GeoDataFrame, annual_poa: float) -> gpd.GeoDataFrame:
    """Add pvlib_yield_kwh and shading_factor columns to the zone GeoDataFrame."""
    gdf = gdf_zone.copy()

    if "footprint_area_m2" not in gdf.columns or gdf["footprint_area_m2"].isna().all():
        proj_crs = gdf.estimate_utm_crs()
        gdf["footprint_area_m2"] = gdf.to_crs(proj_crs).geometry.area

    gdf["footprint_area_m2"] = pd.to_numeric(gdf["footprint_area_m2"], errors="coerce").fillna(50.0)

    logging.info("  Computing shading factors (%d buildings)…", len(gdf))
    gdf["shading_factor"] = compute_shading_factors(gdf)

    roof_area = gdf["footprint_area_m2"] * ROOF_COVERAGE
    gdf["pvlib_yield_kwh"] = (
        roof_area
        * gdf["shading_factor"]
        * PANEL_EFF
        * annual_poa          # Wh/m²
        * PERFORMANCE_RATIO
        / 1000.0              # → kWh
    )
    return gdf


# ── Rank correlation ──────────────────────────────────────────────────────────

def rank_correlation(x: pd.Series, y: pd.Series) -> dict:
    """Spearman ρ and Kendall τ with two-sided p-values."""
    spearman_rho, spearman_p = stats.spearmanr(x, y)
    kendall_tau,  kendall_p  = stats.kendalltau(x, y)
    return {
        "n":           len(x),
        "spearman_rho": float(spearman_rho),
        "spearman_p":   float(spearman_p),
        "kendall_tau":  float(kendall_tau),
        "kendall_p":    float(kendall_p),
    }


# ── Plotting ──────────────────────────────────────────────────────────────────

ZONE_COLORS = {
    "A_high":   "#e6550d",
    "B_low":    "#3182bd",
    "C_medium": "#31a354",
}


def plot_scatter_per_zone(zone_gdfs: dict, figure_dir: Path) -> None:
    """One scatter panel per zone: proxy score vs pvlib yield."""
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    fig.suptitle(
        "Proxy solar_potential_score vs. pvlib reference yield\nChangsha urban core — 3 representative 500 m zones",
        fontsize=12,
    )

    for ax, (zone_name, gdf) in zip(axes, zone_gdfs.items()):
        color = ZONE_COLORS.get(zone_name, "gray")
        ax.scatter(
            gdf["solar_potential_score"],
            gdf["pvlib_yield_kwh"],
            alpha=0.7,
            s=40,
            color=color,
            edgecolors="white",
            linewidths=0.4,
        )
        # Annotate with correlation
        r, p = stats.spearmanr(gdf["solar_potential_score"], gdf["pvlib_yield_kwh"])
        ax.set_title(f"Zone {zone_name}  (n={len(gdf)})\nSpearman ρ = {r:+.3f}  p = {p:.3f}", fontsize=10)
        ax.set_xlabel("Proxy solar_potential_score", fontsize=9)
        ax.set_ylabel("pvlib yield  (kWh/yr)", fontsize=9)
        ax.grid(True, linewidth=0.4, alpha=0.5)

    plt.tight_layout()
    out = figure_dir / "pvlib_benchmark_scatter_zones.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()
    logging.info("Saved zone scatter: %s", out)


def plot_combined_scatter(combined_gdf: gpd.GeoDataFrame, figure_dir: Path) -> None:
    """Single scatter with all three zones overlaid."""
    fig, ax = plt.subplots(figsize=(7, 6))

    for zone_name, color in ZONE_COLORS.items():
        subset = combined_gdf[combined_gdf["zone"] == zone_name]
        ax.scatter(
            subset["solar_potential_score"],
            subset["pvlib_yield_kwh"],
            alpha=0.75,
            s=35,
            color=color,
            edgecolors="white",
            linewidths=0.4,
            label=f"Zone {zone_name} (n={len(subset)})",
        )

    r, p = stats.spearmanr(combined_gdf["solar_potential_score"], combined_gdf["pvlib_yield_kwh"])
    ax.set_title(
        f"Combined — all three zones  (n={len(combined_gdf)})\nSpearman ρ = {r:+.3f}  p = {p:.3f}",
        fontsize=11,
    )
    ax.set_xlabel("Proxy solar_potential_score", fontsize=10)
    ax.set_ylabel("pvlib yield  (kWh/yr)", fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, linewidth=0.4, alpha=0.5)
    plt.tight_layout()
    out = figure_dir / "pvlib_benchmark_scatter_combined.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()
    logging.info("Saved combined scatter: %s", out)


# ── Results table ─────────────────────────────────────────────────────────────

def format_results_table(df: pd.DataFrame) -> str:
    def sig(p: float) -> str:
        if p < 0.001:
            return "***"
        if p < 0.01:
            return "**"
        if p < 0.05:
            return "*"
        return "n.s."

    lines = [
        "",
        "=" * 78,
        "  pvlib Benchmark Validation — Rank Correlation Results",
        "  Changsha Urban Core  |  3 representative 500 m grid zones",
        "=" * 78,
        f"  {'Zone':<18} {'N':>5}   {'Spearman ρ':>10}  {'p':>10}  {'sig':<5}  {'Kendall τ':>10}  {'p':>10}  {'sig':<5}",
        "-" * 78,
    ]
    for _, row in df.iterrows():
        lines.append(
            f"  {row['zone']:<18} {int(row['n']):>5}   "
            f"{row['spearman_rho']:>+10.4f}  {row['spearman_p']:>10.4e}  {sig(row['spearman_p']):<5}  "
            f"{row['kendall_tau']:>+10.4f}  {row['kendall_p']:>10.4e}  {sig(row['kendall_p']):<5}"
        )
    lines += [
        "=" * 78,
        "  Significance: *** p<0.001   ** p<0.01   * p<0.05   n.s. not significant",
        "",
    ]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="pvlib benchmark validation for Changsha solar screening"
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to buildings GeoJSON with solar_potential_score",
    )
    parser.add_argument(
        "--grid", required=True,
        help="Path to grid GeoJSON with grid_id",
    )
    parser.add_argument("--output_dir", default="outputs/validation/")
    parser.add_argument("--figure_dir", default="figure/")
    return parser.parse_args()


def main() -> None:
    setup_logging()
    args = parse_args()

    input_path  = Path(args.input)
    grid_path   = Path(args.grid)
    output_dir  = Path(args.output_dir)
    figure_dir  = Path(args.figure_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    # ── Load data ────────────────────────────────────────────────────────────
    logging.info("Loading buildings: %s", input_path)
    bldg = gpd.read_file(input_path)
    logging.info("  %d buildings total", len(bldg))

    logging.info("Loading grid: %s", grid_path)
    grid = gpd.read_file(grid_path)

    # Ensure consistent CRS
    if bldg.crs != grid.crs:
        grid = grid.to_crs(bldg.crs)

    # ── Compute annual POA once ───────────────────────────────────────────────
    annual_poa = annual_clearsky_poa()

    # ── Process each zone ────────────────────────────────────────────────────
    results   = []
    zone_gdfs = {}
    all_parts = []

    for zone_name, gid in ZONE_GRID_IDS.items():
        logging.info("── Zone %s  (grid_id=%d) ──────────────────────────────", zone_name, gid)

        grid_cell = grid[grid["grid_id"] == gid]
        if grid_cell.empty:
            logging.warning("  grid_id=%d not found — skipping", gid)
            continue

        # Spatial join: buildings within this grid cell
        zone_bldg = gpd.sjoin(bldg, grid_cell[["grid_id", "geometry"]], how="inner", predicate="intersects")
        zone_bldg = zone_bldg.drop(columns=["index_right"], errors="ignore").copy()
        logging.info("  %d buildings in zone", len(zone_bldg))

        if len(zone_bldg) < 5:
            logging.warning("  Too few buildings — skipping")
            continue

        # pvlib yield
        zone_bldg = compute_pvlib_yield(zone_bldg, annual_poa)

        # Rank correlation
        corr = rank_correlation(zone_bldg["solar_potential_score"], zone_bldg["pvlib_yield_kwh"])
        corr["zone"] = zone_name
        corr["grid_id"] = gid
        results.append(corr)

        logging.info(
            "  Spearman ρ = %+.4f  (p=%.4e)   Kendall τ = %+.4f  (p=%.4e)",
            corr["spearman_rho"], corr["spearman_p"],
            corr["kendall_tau"],  corr["kendall_p"],
        )

        zone_bldg["zone"] = zone_name
        zone_gdfs[zone_name] = zone_bldg
        all_parts.append(zone_bldg[["geometry", "zone", "solar_potential_score",
                                     "pvlib_yield_kwh", "shading_factor",
                                     "footprint_area_m2", "height_proxy_m",
                                     "building_category"]])

    if not results:
        logging.error("No zones processed — check grid_id values and input files.")
        return

    # ── Combined ─────────────────────────────────────────────────────────────
    combined = pd.concat([z for z in all_parts], ignore_index=True)
    combined_gdf = gpd.GeoDataFrame(combined, crs=bldg.crs)

    corr_combined = rank_correlation(combined_gdf["solar_potential_score"], combined_gdf["pvlib_yield_kwh"])
    corr_combined["zone"]    = "COMBINED"
    corr_combined["grid_id"] = -1
    results.append(corr_combined)

    # ── Results table ─────────────────────────────────────────────────────────
    results_df = pd.DataFrame(results)[
        ["zone", "grid_id", "n", "spearman_rho", "spearman_p", "kendall_tau", "kendall_p"]
    ]

    table_str = format_results_table(results_df)
    print(table_str)

    # ── Save outputs ─────────────────────────────────────────────────────────
    csv_path = output_dir / "pvlib_benchmark_validation_results.csv"
    results_df.to_csv(csv_path, index=False, float_format="%.6f")
    logging.info("Saved results CSV: %s", csv_path)

    bldg_out = output_dir / "buildings_pvlib_benchmark_zones.geojson"
    combined_gdf.to_file(bldg_out, driver="GeoJSON")
    logging.info("Saved building-level data: %s", bldg_out)

    # ── Figures ───────────────────────────────────────────────────────────────
    plot_scatter_per_zone(zone_gdfs, figure_dir)
    plot_combined_scatter(combined_gdf, figure_dir)

    logging.info("Done.")


if __name__ == "__main__":
    main()
