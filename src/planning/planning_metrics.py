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

irradiance_kwh_per_m2_year (1203.8211):
    Annual global horizontal irradiance for the Changsha urban core,
    in kWh/m²/year. Applied uniformly to every building.

    Source: Global Solar Atlas v2, computed from
    outputs/validation/gsa_comparison.csv as the mean of `mean_ghi` over
    the 671 occupied 500 m grid cells (3.298140 kWh/m²/day) × 365.
    This is reproducible from this repository via
    src/analysis/gsa_external_validation.py.

    Cross-check: NASA POWER 2001–2020 climatology at 28.228 N, 112.939 E
    gives 3.2678 kWh/m²/day = 1,192.7 kWh/m²/yr, i.e. 0.9% below the GSA
    figure. NOTE: the NASA POWER value is supplied externally — this
    repository contains no NASA POWER retrieval code or dataset, so that
    cross-check cannot be re-derived here.

    Supersedes a hard-coded 1300.0 whose provenance could not be
    established. Generation and CO₂ scale linearly with this constant
    (factor 0.926016); deployable area does not depend on it at all.

    For contrast, the pvlib Ineichen clear-sky value at the study-area
    centroid is 2,158.8 kWh/m²/yr — an upper bound with no cloud cover,
    used only inside the benchmark script. It does not feed these metrics.

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
outputs/planning_metrics_priority_aggregate.csv
                                         — priority-grid subset totals and
                                           shares (manuscript Table 10)
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
    "irradiance_kwh_per_m2_year":    1203.8211,  # kWh/m²/yr — GSA v2, see docstring
    "performance_ratio":             0.80,    # system PR
    "grid_emission_factor_kg_per_kwh": 0.5703,  # kg CO₂eq/kWh
    "priority_top_fraction":         0.20,   # top 20 % grids by HP ratio
}

# External reference figure, not derived here: Changsha total societal
# electricity consumption in 2022, GWh. Used only to express the estimated
# generation as a share of demand.
CITY_ANNUAL_CONSUMPTION_GWH = 51679.0

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BUILDINGS_PATH = Path("data/processed/buildings_changsha_urban_core_solar_baseline.geojson")
GRID_PATH      = Path("data/processed/grid_changsha_urban_core_solar_baseline.geojson")

OUTPUT_DIR     = Path("outputs")
SUMMARY_CSV    = OUTPUT_DIR / "planning_metrics_summary.csv"
AGGREGATE_CSV  = OUTPUT_DIR / "planning_metrics_aggregate.csv"
PRIORITY_CSV   = OUTPUT_DIR / "priority_grids.csv"
PRIORITY_AGG_CSV = OUTPUT_DIR / "planning_metrics_priority_aggregate.csv"


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


def assign_to_grid(hp: gpd.GeoDataFrame, grid: gpd.GeoDataFrame) -> pd.Series:
    """
    Return a grid_id per high-potential building.

    Buildings are assigned by CENTROID with predicate="within", matching
    grid_solar_aggregation.py — the same convention that produced the
    grid_id values in priority_grids.csv. Joining the full polygon instead
    would drop every building straddling a cell boundary.
    """
    utm = hp.estimate_utm_crs()
    cent = hp[["geometry"]].to_crs(utm)
    cent["geometry"] = cent.geometry.centroid

    joined = gpd.sjoin(
        cent,
        grid[["grid_id", "geometry"]].to_crs(utm),
        how="left",
        predicate="within",
    ).drop(columns=["index_right"], errors="ignore")
    # sjoin can emit duplicates if grid cells overlap; keep the first match
    joined = joined[~joined.index.duplicated(keep="first")]
    return joined.reindex(hp.index)["grid_id"]


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

    # ------------------------------------------------------------------
    # Priority-grid subset aggregate (manuscript Table 10)
    #
    # Computed here rather than by hand, because generation is exactly
    # proportional to deployable area in this model:
    #     E = A_deploy × η × G × PR
    # with η, G and PR global constants. The share of generation falling in
    # the priority grids therefore EQUALS the share of deployable area, by
    # construction. Any table reporting two different shares is internally
    # inconsistent.
    # ------------------------------------------------------------------
    hp = hp.copy()
    hp["grid_id"] = assign_to_grid(hp, grid).values
    priority_ids = set(priority["grid_id"].astype(int))
    in_priority = hp["grid_id"].notna() & hp["grid_id"].astype("Int64").isin(priority_ids)

    hp_pri = hp[in_priority]
    pri_deploy_m2 = hp_pri["deployable_area_m2"].sum()
    pri_kwh       = hp_pri["annual_kwh"].sum()
    pri_co2_t     = hp_pri["annual_co2_t"].sum()

    share_area = pri_deploy_m2 / total_deploy_m2
    share_gen  = pri_kwh / total_kwh_year
    kwh_per_km2_deploy = (
        cfg["panel_efficiency"] * cfg["irradiance_kwh_per_m2_year"] * cfg["performance_ratio"]
    )

    pri_row = {
        "n_priority_grids":               len(priority),
        "priority_cutoff_hp_ratio":       float(cutoff),
        "hp_buildings_in_priority":       int(len(hp_pri)),
        "hp_buildings_total":             int(len(hp)),
        "priority_deployable_area_m2":    pri_deploy_m2,
        "priority_deployable_area_km2":   pri_deploy_m2 / 1e6,
        "priority_annual_generation_gwh": pri_kwh / 1e6,
        "priority_annual_co2_kt":         pri_co2_t / 1000.0,
        "share_of_deployable_area_pct":   100.0 * share_area,
        "share_of_generation_pct":        100.0 * share_gen,
        "share_discrepancy_pp":           100.0 * (share_gen - share_area),
        "gwh_per_km2_deployable":         kwh_per_km2_deploy,
        "city_consumption_2022_gwh":      CITY_ANNUAL_CONSUMPTION_GWH,
        "total_share_of_city_demand_pct": 100.0 * (total_kwh_year / 1e6) / CITY_ANNUAL_CONSUMPTION_GWH,
        "priority_share_of_city_demand_pct": 100.0 * (pri_kwh / 1e6) / CITY_ANNUAL_CONSUMPTION_GWH,
    }
    pd.DataFrame([pri_row]).to_csv(PRIORITY_AGG_CSV, index=False)
    logging.info("Saved priority subset aggregate: %s", PRIORITY_AGG_CSV)

    logging.info("--- Priority-grid subset (%d grids) ---", len(priority))
    logging.info("  HP buildings inside priority grids: %d of %d", len(hp_pri), len(hp))
    logging.info("  Deployable rooftop area:  %.4f km²", pri_deploy_m2 / 1e6)
    logging.info("  Annual generation:        %.4f GWh/year", pri_kwh / 1e6)
    logging.info("  Annual CO₂ reduction:     %.4f kt CO₂eq/year", pri_co2_t / 1000.0)
    logging.info("  Share of deployable area: %.4f %%", 100.0 * share_area)
    logging.info("  Share of generation:      %.4f %%  (must equal the line above)",
                 100.0 * share_gen)
    if abs(share_gen - share_area) > 1e-12:
        logging.warning("  Shares differ by %.3e pp — the model no longer scales linearly.",
                        100.0 * (share_gen - share_area))
    logging.info("Done.")


if __name__ == "__main__":
    main()
