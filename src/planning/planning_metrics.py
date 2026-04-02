"""
planning_metrics.py

Phase 3 — Planning Metrics Conversion Layer.

Translates the building-level and grid-level solar screening outputs into
actionable planning indicators:

  1. Deployable rooftop area per building and in aggregate.
  2. Estimated annual electricity generation (kWh/year).
  3. Estimated annual CO₂ equivalent reduction (tonnes/year).
  4. Priority grid identification (top N% by high_potential_ratio).

All physical parameters are kept in a single CONFIG dict so they can be
reviewed or overridden without touching the logic.

Physical parameter rationale
-----------------------------
utilisation_factor (0.65):
    Fraction of rooftop footprint that can practically be covered by PV
    panels, accounting for structural setbacks, shading obstructions,
    access paths, and HVAC equipment.  Typical range: 0.50–0.70.
    Reference: IEA-PVPS Task 15 urban PV guidelines.

panel_efficiency (0.20):
    Commercial mono-crystalline silicon efficiency (PERC / TOPCon).
    Conservative mid-range value for 2024 mainstream panels (18–22 %).

irradiance_kwh_per_m2_year (1300):
    Changsha annual global horizontal irradiance (GHI), derived from
    ERA5 climatological mean and cross-checked against NASA POWER
    (station lat ≈ 28.2°N, lon ≈ 112.9°E).
    Range: 1,200–1,400 kWh/m²/year depending on source and year.

performance_ratio (0.80):
    System-level efficiency factor covering inverter losses, wiring,
    soiling, and temperature de-rating.  Standard value for grid-tied
    rooftop PV in Chinese climate zone IIIb.

grid_emission_factor_kg_per_kwh (0.5703):
    China Southern / Central Grid average CO₂ emission factor
    (kg CO₂eq / kWh) published by China's Ministry of Ecology and
    Environment, 2022 baseline.

priority_top_fraction (0.20):
    Grids in the top 20% by high_potential_ratio are flagged as
    priority deployment zones.

Inputs
------
data/processed/buildings_changsha_urban_core_solar_baseline.geojson
data/processed/grid_changsha_urban_core_solar_baseline.geojson

Outputs
-------
outputs/planning_metrics_summary.csv     — building-level detail (HP only)
outputs/planning_metrics_aggregate.csv   — single-row aggregate summary
outputs/priority_grids.csv               — priority grids with metrics
"""

from pathlib import Path
import logging

import geopandas as gpd
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Physical & planning parameters
# ---------------------------------------------------------------------------
CONFIG = {
    "utilisation_factor":            0.65,    # fraction of rooftop usable
    "panel_efficiency":              0.20,    # (dimensionless)
    "irradiance_kwh_per_m2_year":    1300.0,  # kWh/m²/year (Changsha GHI)
    "performance_ratio":             0.80,    # system PR
    "grid_emission_factor_kg_per_kwh": 0.5703,  # kg CO₂eq/kWh
    "priority_top_fraction":         0.20,   # top 20 % grids by HP ratio
}

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BUILDINGS_PATH = Path("data/processed/buildings_changsha_urban_core_solar_baseline.geojson")
GRID_PATH      = Path("data/processed/grid_changsha_urban_core_solar_baseline.geojson")

OUTPUT_DIR     = Path("outputs")
SUMMARY_CSV    = OUTPUT_DIR / "planning_metrics_summary.csv"
AGGREGATE_CSV  = OUTPUT_DIR / "planning_metrics_aggregate.csv"
PRIORITY_CSV   = OUTPUT_DIR / "priority_grids.csv"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )


def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def compute_deployable_area(footprint_m2: pd.Series, factor: float) -> pd.Series:
    """Return deployable rooftop area (m²) given footprint and utilisation factor."""
    return footprint_m2 * factor


def compute_annual_generation(deployable_m2: pd.Series, cfg: dict) -> pd.Series:
    """
    Annual PV yield in kWh/year.

    Formula:
        E = A_deploy × η_panel × G_annual × PR
    where:
        A_deploy = deployable area (m²)
        η_panel  = panel efficiency
        G_annual = annual irradiance (kWh/m²/year)
        PR       = performance ratio
    """
    return (
        deployable_m2
        * cfg["panel_efficiency"]
        * cfg["irradiance_kwh_per_m2_year"]
        * cfg["performance_ratio"]
    )


def compute_co2_reduction(kwh_per_year: pd.Series, cfg: dict) -> pd.Series:
    """
    Annual CO₂ reduction in tonnes CO₂eq/year.

    CO₂_reduced = E_annual (kWh) × EF (kg CO₂/kWh) / 1000
    """
    return kwh_per_year * cfg["grid_emission_factor_kg_per_kwh"] / 1000.0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    setup_logging()
    ensure_dirs()

    if not BUILDINGS_PATH.exists():
        raise FileNotFoundError(f"Missing: {BUILDINGS_PATH}")
    if not GRID_PATH.exists():
        raise FileNotFoundError(f"Missing: {GRID_PATH}")

    cfg = CONFIG

    # ------------------------------------------------------------------
    # Load buildings
    # ------------------------------------------------------------------
    logging.info("Loading buildings from %s", BUILDINGS_PATH)
    buildings = gpd.read_file(BUILDINGS_PATH)

    buildings["is_high_potential"] = pd.to_numeric(
        buildings["is_high_potential"], errors="coerce"
    ).fillna(0).astype(int)

    # Recompute footprint area if not stored
    if "footprint_area_m2" not in buildings.columns:
        logging.info("Computing footprint area from projected geometry…")
        utm_crs = buildings.estimate_utm_crs()
        buildings_proj = buildings.to_crs(utm_crs)
        buildings["footprint_area_m2"] = buildings_proj.geometry.area
    else:
        buildings["footprint_area_m2"] = pd.to_numeric(
            buildings["footprint_area_m2"], errors="coerce"
        ).fillna(0)

    # Work only on high-potential buildings
    hp = buildings[buildings["is_high_potential"] == 1].copy()
    logging.info("High-potential buildings: %d", len(hp))

    hp["deployable_area_m2"] = compute_deployable_area(
        hp["footprint_area_m2"], cfg["utilisation_factor"]
    )
    hp["annual_kwh"] = compute_annual_generation(hp["deployable_area_m2"], cfg)
    hp["annual_co2_t"] = compute_co2_reduction(hp["annual_kwh"], cfg)

    # Output building-level CSV (keep key columns only)
    keep_cols = [
        "footprint_area_m2",
        "deployable_area_m2",
        "annual_kwh",
        "annual_co2_t",
        "solar_potential_score",
        "solar_potential_class",
        "building_category",
        "height_proxy_m",
    ]
    keep_cols = [c for c in keep_cols if c in hp.columns]
    hp_out = hp[keep_cols].reset_index(drop=True)
    hp_out.to_csv(SUMMARY_CSV, index=False)
    logging.info("Saved building-level metrics: %s", SUMMARY_CSV)

    # ------------------------------------------------------------------
    # Aggregate summary
    # ------------------------------------------------------------------
    total_buildings   = len(buildings)
    hp_count          = len(hp)
    total_deploy_m2   = hp["deployable_area_m2"].sum()
    total_kwh_year    = hp["annual_kwh"].sum()
    total_co2_t_year  = hp["annual_co2_t"].sum()

    agg_row = {
        "total_urban_core_buildings":    total_buildings,
        "high_potential_buildings":      hp_count,
        "hp_fraction":                   hp_count / total_buildings,
        "utilisation_factor":            cfg["utilisation_factor"],
        "panel_efficiency":              cfg["panel_efficiency"],
        "irradiance_kwh_m2_year":        cfg["irradiance_kwh_per_m2_year"],
        "performance_ratio":             cfg["performance_ratio"],
        "emission_factor_kg_kwh":        cfg["grid_emission_factor_kg_per_kwh"],
        "total_deployable_area_m2":      total_deploy_m2,
        "total_deployable_area_km2":     total_deploy_m2 / 1e6,
        "total_annual_generation_kwh":   total_kwh_year,
        "total_annual_generation_gwh":   total_kwh_year / 1e6,
        "total_annual_co2_reduction_t":  total_co2_t_year,
        "total_annual_co2_reduction_kt": total_co2_t_year / 1000,
    }
    pd.DataFrame([agg_row]).to_csv(AGGREGATE_CSV, index=False)
    logging.info("Saved aggregate summary: %s", AGGREGATE_CSV)

    logging.info("--- Aggregate Planning Metrics ---")
    logging.info("  High-potential buildings:       %d (%.1f%%)",
                 hp_count, hp_count / total_buildings * 100)
    logging.info("  Total deployable rooftop area:  %.1f km²",
                 total_deploy_m2 / 1e6)
    logging.info("  Estimated annual generation:    %.1f GWh/year",
                 total_kwh_year / 1e6)
    logging.info("  Estimated annual CO₂ reduction: %.1f kt CO₂eq/year",
                 total_co2_t_year / 1000)

    # ------------------------------------------------------------------
    # Priority grids
    # ------------------------------------------------------------------
    logging.info("Loading grid from %s", GRID_PATH)
    grid = gpd.read_file(GRID_PATH)

    grid["building_count"] = pd.to_numeric(
        grid["building_count"], errors="coerce"
    ).fillna(0)
    grid["high_potential_ratio"] = pd.to_numeric(
        grid["high_potential_ratio"], errors="coerce"
    ).fillna(0)
    grid["mean_score"] = pd.to_numeric(
        grid["mean_score"], errors="coerce"
    )

    occupied = grid[grid["building_count"] > 0].copy()
    cutoff = occupied["high_potential_ratio"].quantile(
        1.0 - cfg["priority_top_fraction"]
    )
    priority = occupied[occupied["high_potential_ratio"] >= cutoff].copy()
    priority = priority.sort_values("high_potential_ratio", ascending=False)

    logging.info(
        "Priority grids (top %.0f%% by HP ratio, cutoff ≥ %.3f): %d",
        cfg["priority_top_fraction"] * 100,
        cutoff,
        len(priority),
    )

    priority_cols = [
        "grid_id",
        "building_count",
        "mean_score",
        "high_potential_ratio",
        "high_potential_building_count",
        "total_footprint_area_m2",
        "mean_height_proxy_m",
        "building_density_per_km2",
        "footprint_density_m2_per_km2",
    ]
    priority_cols = [c for c in priority_cols if c in priority.columns]

    priority[priority_cols].to_csv(PRIORITY_CSV, index=False)
    logging.info("Saved priority grids: %s", PRIORITY_CSV)
    logging.info("Done.")


if __name__ == "__main__":
    main()
