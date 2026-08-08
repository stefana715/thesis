#!/usr/bin/env python3
"""
priority_threshold_scenarios.py

Priority-grid threshold scenarios for Supplementary Table S8.

The main analysis defines priority grids as the top 20% of occupied cells by
high-potential ratio, which for the 500 m grid resolves to a cutoff of
HP ratio >= 0.75 and yields 146 cells. This script sweeps the cutoff over a
range of explicit HP-ratio thresholds and reports, for each, how many cells
qualify and how much deployable rooftop area and generation potential they
capture.

Conventions are inherited from planning_metrics.py so the numbers are directly
comparable with Table 10:

  * physical parameters come from planning_metrics.CONFIG (utilisation 0.65,
    panel efficiency 0.20, irradiance 1203.8211 kWh/m2/yr, PR 0.80)
  * high-potential buildings only, using the pipeline's is_high_potential flag
  * buildings assigned to cells by CENTROID (grid_solar_aggregation convention)

Because generation is exactly proportional to deployable area in this model
(E = A_deploy x eta x G x PR, with eta/G/PR global constants), the area share
and the generation share are identical by construction. Both are reported so
the table is self-checking; a divergence would indicate the model no longer
scales linearly.

Usage
-----
    python src/planning/priority_threshold_scenarios.py \
        --input      data/processed/buildings_changsha_urban_core_solar_baseline.geojson \
        --grid       data/processed/grid_changsha_urban_core_solar_baseline.geojson \
        --output_dir outputs/planning/
"""

import argparse
import importlib.util
import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

# ── Reuse planning_metrics for parameters and the grid-assignment rule ────────

_PM_PATH = Path(__file__).resolve().parent / "planning_metrics.py"
_spec = importlib.util.spec_from_file_location("planning_metrics", _PM_PATH)
pm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pm)

# Scenario cutoffs on the per-cell high-potential ratio
HP_RATIO_THRESHOLDS = [0.60, 0.70, 0.75, 0.80, 0.90]

# The cutoff the main analysis actually uses (top 20% of occupied cells)
MAIN_ANALYSIS_CUTOFF = 0.75


def setup_logging():
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(message)s")


def build_cell_table(bldg: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> pd.DataFrame:
    """Per-cell HP ratio plus the deployable area / generation of its HP stock."""
    cfg = pm.CONFIG
    hp_flag = pd.to_numeric(bldg["is_high_potential"], errors="coerce").fillna(0).astype(int)
    area = pd.to_numeric(bldg["footprint_area_m2"], errors="coerce").fillna(0)

    work = bldg[["geometry"]].copy()
    work["hp"] = hp_flag.values
    work["deployable_m2"] = (area * cfg["utilisation_factor"] * hp_flag).values
    work["kwh"] = (
        work["deployable_m2"]
        * cfg["panel_efficiency"]
        * cfg["irradiance_kwh_per_m2_year"]
        * cfg["performance_ratio"]
    )

    work["grid_id"] = pm.assign_to_grid(bldg, grid).values
    work = work.dropna(subset=["grid_id"])
    work["grid_id"] = work["grid_id"].astype(int)

    cells = work.groupby("grid_id").agg(
        n_buildings=("hp", "size"),
        n_hp=("hp", "sum"),
        deployable_m2=("deployable_m2", "sum"),
        kwh=("kwh", "sum"),
    )
    cells["hp_ratio"] = cells["n_hp"] / cells["n_buildings"]
    return cells


def run_scenarios(cells: pd.DataFrame, thresholds) -> pd.DataFrame:
    total_deploy = cells["deployable_m2"].sum()
    total_kwh = cells["kwh"].sum()
    total_hp = cells["n_hp"].sum()
    n_occupied = len(cells)
    cfg = pm.CONFIG

    rows = []
    for t in thresholds:
        sel = cells[cells["hp_ratio"] >= t]
        deploy = sel["deployable_m2"].sum()
        kwh = sel["kwh"].sum()
        rows.append({
            "hp_ratio_threshold": t,
            "is_main_analysis_cutoff": bool(np.isclose(t, MAIN_ANALYSIS_CUTOFF)),
            "n_priority_grids": len(sel),
            "pct_of_occupied_grids": 100.0 * len(sel) / n_occupied,
            "n_hp_buildings": int(sel["n_hp"].sum()),
            "pct_of_hp_buildings": 100.0 * sel["n_hp"].sum() / total_hp,
            "deployable_area_m2": deploy,
            "deployable_area_km2": deploy / 1e6,
            "annual_generation_gwh": kwh / 1e6,
            "annual_co2_kt": kwh * cfg["grid_emission_factor_kg_per_kwh"] / 1000.0 / 1000.0,
            "share_of_deployable_area_pct": 100.0 * deploy / total_deploy,
            "share_of_generation_pct": 100.0 * kwh / total_kwh,
            "share_discrepancy_pp": 100.0 * (kwh / total_kwh - deploy / total_deploy),
        })
    return pd.DataFrame(rows)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--grid", required=True)
    p.add_argument("--output_dir", default="outputs/planning/")
    return p.parse_args()


def main():
    setup_logging()
    args = parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    bldg = gpd.read_file(args.input)
    grid = gpd.read_file(args.grid)
    if bldg.crs != grid.crs:
        grid = grid.to_crs(bldg.crs)

    cells = build_cell_table(bldg, grid)
    logging.info("Occupied cells: %d | HP buildings: %d | deployable %.4f km2 | %.4f GWh/yr",
                 len(cells), int(cells["n_hp"].sum()),
                 cells["deployable_m2"].sum() / 1e6, cells["kwh"].sum() / 1e6)

    df = run_scenarios(cells, HP_RATIO_THRESHOLDS)

    print("\n" + "=" * 108)
    print("  Supplementary Table S8 — priority-grid threshold scenarios")
    print(f"  Irradiance {pm.CONFIG['irradiance_kwh_per_m2_year']} kWh/m2/yr | "
          f"totals: {cells['deployable_m2'].sum()/1e6:.4f} km2, "
          f"{cells['kwh'].sum()/1e6:.4f} GWh/yr, {int(cells['n_hp'].sum())} HP buildings")
    print("=" * 108)
    print(f"  {'HP ratio':>9} {'grids':>7} {'% occ':>7} {'HP bldgs':>9} {'km2':>9} "
          f"{'GWh/yr':>10} {'kt CO2':>9} {'% area':>8} {'% gen':>8}")
    print("-" * 108)
    for _, r in df.iterrows():
        mark = " *" if r["is_main_analysis_cutoff"] else "  "
        print(f"  {r['hp_ratio_threshold']:>7.2f}{mark} {int(r['n_priority_grids']):>7} "
              f"{r['pct_of_occupied_grids']:>6.2f}% {int(r['n_hp_buildings']):>9} "
              f"{r['deployable_area_km2']:>9.4f} {r['annual_generation_gwh']:>10.4f} "
              f"{r['annual_co2_kt']:>9.4f} {r['share_of_deployable_area_pct']:>7.4f}% "
              f"{r['share_of_generation_pct']:>7.4f}%")
    print("-" * 108)
    print("  * cutoff used by the main analysis (top 20% of occupied cells)")
    worst = df["share_discrepancy_pp"].abs().max()
    print(f"  max |area share - generation share| = {worst:.3e} pp "
          f"(zero by construction; floating point only)")
    print("=" * 108 + "\n")

    csv_out = out_dir / "priority_threshold_scenarios.csv"
    df.to_csv(csv_out, index=False, float_format="%.6f")
    logging.info("Saved: %s", csv_out)


if __name__ == "__main__":
    main()
