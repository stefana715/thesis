#!/usr/bin/env python3
"""
benchmark_param_sensitivity.py

Parameter sensitivity analysis for the pvlib benchmark validation.

Design
------
Uses the same 3 benchmark zones (A_high=317, B_low=34, C_medium=1606).
Varies benchmark parameters one at a time (others held at default):

  Shading radius (m):         30 | 50* | 70
  Roof utilisation factor:  0.55 | 0.65* | 0.75
  Shading coefficient:      0.05 | 0.10* | 0.15

  * = default value

For each variant, recomputes pvlib yield and Spearman ρ per zone.
Reports a table of ρ values across all parameter variants and zones,
and saves a heatmap and grouped bar chart.

Usage
-----
    python src/validation/benchmark_param_sensitivity.py \
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
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
import pvlib
from scipy import stats

# ── Constants ─────────────────────────────────────────────────────────────────

LATITUDE        = 28.228
LONGITUDE       = 112.939
ALTITUDE        = 50.0
TIMEZONE        = "Asia/Shanghai"

PANEL_EFF         = 0.20
PERFORMANCE_RATIO = 0.80
SHADING_FLOOR     = 0.5

# Default values
DEFAULT_RADIUS    = 50.0
DEFAULT_ROOF      = 0.65
DEFAULT_COEFF     = 0.10

ZONE_GRID_IDS = {"A_high": 317, "B_low": 34, "C_medium": 1606}

# Parameter grid (one-at-a-time variation)
PARAM_VARIANTS = [
    # (label, radius, roof_coverage, shading_coeff, is_default)
    ("radius=30m",     30.0,  DEFAULT_ROOF,  DEFAULT_COEFF, False),
    ("radius=50m ✓",   50.0,  DEFAULT_ROOF,  DEFAULT_COEFF, True),
    ("radius=70m",     70.0,  DEFAULT_ROOF,  DEFAULT_COEFF, False),
    ("roof=0.55",      DEFAULT_RADIUS, 0.55, DEFAULT_COEFF, False),
    ("roof=0.65 ✓",    DEFAULT_RADIUS, 0.65, DEFAULT_COEFF, True),
    ("roof=0.75",      DEFAULT_RADIUS, 0.75, DEFAULT_COEFF, False),
    ("coeff=0.05",     DEFAULT_RADIUS, DEFAULT_ROOF, 0.05, False),
    ("coeff=0.10 ✓",   DEFAULT_RADIUS, DEFAULT_ROOF, 0.10, True),
    ("coeff=0.15",     DEFAULT_RADIUS, DEFAULT_ROOF, 0.15, False),
]

ZONE_COLORS = {"A_high": "#e6550d", "B_low": "#3182bd", "C_medium": "#31a354"}


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
    logging.info("Annual clear-sky POA: %.1f Wh/m²", annual_poa)
    return annual_poa


# ── Shading + yield ───────────────────────────────────────────────────────────

def compute_shading_factors(
    gdf_zone: gpd.GeoDataFrame,
    radius: float,
    coeff: float,
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
            factor *= max(SHADING_FLOOR, 1.0 - reduction)
        shading_factors.append(max(SHADING_FLOOR, factor))

    return pd.Series(shading_factors, index=gdf_zone.index, name="shading_factor")


def compute_spearman(
    zone_bldg: gpd.GeoDataFrame,
    annual_poa: float,
    roof_coverage: float,
    radius: float,
    coeff: float,
) -> float:
    gdf = zone_bldg.copy()
    if "footprint_area_m2" not in gdf.columns or gdf["footprint_area_m2"].isna().all():
        gdf["footprint_area_m2"] = gdf.to_crs(gdf.estimate_utm_crs()).geometry.area
    gdf["footprint_area_m2"] = pd.to_numeric(
        gdf["footprint_area_m2"], errors="coerce"
    ).fillna(50.0)
    shading = compute_shading_factors(gdf, radius=radius, coeff=coeff)
    pvlib_yield = (
        gdf["footprint_area_m2"] * roof_coverage
        * shading * PANEL_EFF * annual_poa * PERFORMANCE_RATIO / 1000.0
    )
    rho, _ = stats.spearmanr(gdf["solar_potential_score"], pvlib_yield)
    return float(rho)


# ── Plotting ──────────────────────────────────────────────────────────────────

def plot_heatmap(pivot: pd.DataFrame, is_default: pd.Series, figure_dir: Path) -> None:
    fig, ax = plt.subplots(figsize=(7, 6))

    vmin = max(0.0, pivot.values.min() - 0.05)
    norm = mcolors.Normalize(vmin=vmin, vmax=1.0)
    cmap = plt.cm.RdYlGn

    im = ax.imshow(pivot.values, aspect="auto", cmap=cmap, norm=norm)

    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, fontsize=10)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=9)

    # Annotate cells with ρ value; bold the default rows
    for i, variant in enumerate(pivot.index):
        for j, zone in enumerate(pivot.columns):
            val = pivot.loc[variant, zone]
            weight = "bold" if is_default[variant] else "normal"
            ax.text(j, i, f"{val:+.3f}", ha="center", va="center",
                    fontsize=9, fontweight=weight,
                    color="black" if val > 0.6 else "white")

    plt.colorbar(im, ax=ax, label="Spearman ρ")
    ax.set_title(
        "Parameter sensitivity: Spearman ρ (proxy vs. pvlib yield)\n"
        "Rows marked ✓ = default values",
        fontsize=11,
    )
    ax.set_xlabel("Benchmark zone", fontsize=10)
    ax.set_ylabel("Parameter variant", fontsize=10)
    plt.tight_layout()
    out = figure_dir / "fig_benchmark_param_sensitivity.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()
    logging.info("Saved heatmap: %s", out)


def plot_grouped_bars(pivot: pd.DataFrame, is_default: pd.Series, figure_dir: Path) -> None:
    """Grouped bar chart: one group per parameter variant, bars per zone."""
    n_variants = len(pivot.index)
    n_zones    = len(pivot.columns)
    x = np.arange(n_variants)
    width = 0.22

    fig, ax = plt.subplots(figsize=(13, 5))
    for k, (zone, color) in enumerate(ZONE_COLORS.items()):
        offsets = (k - (n_zones - 1) / 2) * width
        bars = ax.bar(
            x + offsets,
            pivot[zone].values,
            width=width,
            color=color,
            alpha=0.85,
            label=f"Zone {zone}",
            edgecolor="white",
            linewidth=0.5,
        )

    # Mark default rows with a grey background band
    for i, (variant, default) in enumerate(is_default.items()):
        if default:
            ax.axvspan(i - 0.45, i + 0.45, color="gray", alpha=0.08, zorder=0)

    ax.set_xticks(x)
    ax.set_xticklabels(pivot.index, rotation=25, ha="right", fontsize=8)
    ax.set_ylabel("Spearman ρ", fontsize=10)
    ax.set_ylim(0, 1.15)
    ax.axhline(1.0, color="gray", linewidth=0.5, linestyle="--")
    ax.set_title(
        "Parameter sensitivity: Spearman ρ by zone and parameter variant\n"
        "(grey bands = default values; ✓ = default)",
        fontsize=11,
    )
    ax.legend(fontsize=9)
    ax.grid(axis="y", linewidth=0.4, alpha=0.4)
    plt.tight_layout()
    out = figure_dir / "fig_benchmark_param_sensitivity_bars.png"
    plt.savefig(out, dpi=300, bbox_inches="tight")
    plt.close()
    logging.info("Saved bar chart: %s", out)


# ── Results table ─────────────────────────────────────────────────────────────

def format_sensitivity_table(pivot: pd.DataFrame, is_default: pd.Series) -> str:
    zones = list(pivot.columns)
    lines = [
        "",
        "=" * 68,
        "  Benchmark Parameter Sensitivity — Spearman ρ",
        "=" * 68,
        f"  {'Parameter variant':<22}  " + "  ".join(f"{z:>12}" for z in zones),
        "-" * 68,
    ]
    for variant in pivot.index:
        marker = " ✓" if is_default[variant] else "  "
        row = f"  {variant:<22}{marker} " + "  ".join(
            f"{pivot.loc[variant, z]:>+12.4f}" for z in zones
        )
        lines.append(row)
    lines += ["=" * 68, "  ✓ = default parameter value", ""]
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

    # Pre-extract zone buildings (same for all variants)
    zone_bldgs = {}
    for zone_name, gid in ZONE_GRID_IDS.items():
        cell = grid[grid["grid_id"] == gid]
        zone_bldg = gpd.sjoin(
            bldg, cell[["grid_id", "geometry"]], how="inner", predicate="intersects"
        ).drop(columns=["index_right"], errors="ignore")
        zone_bldgs[zone_name] = zone_bldg
        logging.info("Zone %s (grid_id=%d): %d buildings", zone_name, gid, len(zone_bldg))

    # Run all variants
    records = []
    for label, radius, roof, coeff, is_def in PARAM_VARIANTS:
        logging.info("Variant: %s", label)
        row = {"variant": label, "is_default": is_def,
               "radius": radius, "roof_coverage": roof, "shading_coeff": coeff}
        for zone_name, zone_bldg in zone_bldgs.items():
            rho = compute_spearman(zone_bldg, annual_poa, roof, radius, coeff)
            row[zone_name] = rho
            logging.info("  %s → ρ = %+.4f", zone_name, rho)
        records.append(row)

    results_df = pd.DataFrame(records)

    # Pivot for display
    pivot = results_df.set_index("variant")[list(ZONE_GRID_IDS.keys())]
    is_default = results_df.set_index("variant")["is_default"]

    print(format_sensitivity_table(pivot, is_default))

    # Save CSV
    csv_out = output_dir / "benchmark_parameter_sensitivity.csv"
    results_df.drop(columns=["is_default"]).to_csv(csv_out, index=False, float_format="%.6f")
    logging.info("Saved CSV: %s", csv_out)

    plot_heatmap(pivot, is_default, figure_dir)
    plot_grouped_bars(pivot, is_default, figure_dir)
    logging.info("Done.")


if __name__ == "__main__":
    main()
