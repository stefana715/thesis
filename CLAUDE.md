# CLAUDE.md — Project Context for Claude Code

## Project identity

**Title:** Low-data-condition rapid urban solar potential assessment model (Changsha version)

**Type:** PhD thesis — planning-oriented rapid screening framework

**Study area:** Changsha urban core, Hunan, China

**Methodological identity:** This is a **rapid screening and planning-support framework**, NOT a high-fidelity engineering simulation. Never overclaim physical accuracy or treat this as an engineering-grade PV yield model.

---

## Repository structure

```
thesis/
├── cache/          # cached intermediate data (OSM downloads, etc.)
├── code/           # standalone scripts (legacy or utility)
├── configs/        # YAML or JSON configuration files
├── data/           # raw, interim, and processed datasets
├── docs/           # project notes, milestone updates, writing drafts
├── figure/         # output figures for thesis
├── logs/           # run logs
├── notebooks/      # Jupyter notebooks for exploration
├── outputs/        # final CSV, GeoJSON, and table outputs
├── src/            # main source code (data, features, models, visualization)
├── requirements.txt
└── README.md
```

## Tech stack

- **Language:** Python 3.x
- **Core GIS:** geopandas, shapely, pyproj, osmnx, rasterio
- **Solar:** pvlib
- **Data:** pandas, numpy, xarray
- **Weather API:** cdsapi (ERA5 / Copernicus)
- **ML (planned):** scikit-learn
- **Viz:** matplotlib
- **Config:** pyyaml

Install: `pip install -r requirements.txt`

---

## Workflow pipeline (completed stages)

The pipeline runs in this order:

1. **OSM building download** — fetch Changsha buildings from OpenStreetMap via osmnx
2. **Building height proxy construction** — estimate building heights from OSM tags and proxy logic (no LiDAR)
3. **Urban core extraction (Phase 1)** — filter to the dense urban core area, reducing from full municipal extent
4. **Building-level baseline solar scoring** — compute a composite solar potential score per building using footprint area, height proxy, and orientation
5. **High-potential classification** — apply q33/q66 quantile thresholds to classify buildings as low/medium/high potential
6. **Grid aggregation (Phase 2)** — overlay 500m grid, compute per-grid mean score, building count, and high_potential_ratio
7. **CSV export** — export building-level and grid-level results

### Key verified numbers (as of 2026-04-01)

| Metric | Value |
|---|---|
| Processed buildings | 33,374 |
| Urban-core buildings retained | 18,855 (56.50%) |
| Mean solar_potential_score | 43.885 |
| q33 threshold | 41.797 |
| q66 threshold | 45.513 |
| High-potential buildings | 6,411 |
| Total grids | 1,722 |
| Occupied grids | 671 |
| Grids with high_potential_ratio > 0 | 612 |
| high_potential_ratio mean | 0.175 |

---

## Current project phase

**Status: writing-centered stage** — the pipeline is stable and verified. No more debugging.

### What is DONE

- Full building-to-grid screening pipeline
- Source-to-grid high-potential classification chain (verified, no false-zero artifacts)
- CSV exports working
- All key numbers verified

### What is MISSING (next development tasks)

#### 6.1 External validation
- Compare against a more detailed benchmark method
- Or create a limited-area high-fidelity validation subset

#### 6.2 Robustness / sensitivity analysis
- Grid size sensitivity (test 250m, 500m, 750m, 1000m)
- Threshold sensitivity (test different quantile cutoffs beyond q66)
- Height-proxy assumption sensitivity (perturb height estimates, measure score stability)

#### 6.3 Planning-metrics conversion layer
- Priority grid identification
- Deployable building share per grid
- Deployable rooftop area estimate
- Rough annual generation estimate (kWh)
- Rough CO₂ reduction estimate

#### 6.4 Thesis writing
- Methods section (journal-style)
- Results section (building classification, grid aggregation, spatial heterogeneity)
- Discussion section (planning relevance, low-data contribution, limitations)

---

## Coding conventions

- Keep scripts modular — one function per logical step
- Use `configs/` for parameters (grid size, quantile thresholds, study area bounds) rather than hardcoding
- Save intermediate outputs to `data/` with clear naming: `{stage}_{description}_{date}.{ext}`
- Save final outputs to `outputs/`
- Save figures to `figure/`
- Log key metrics to `logs/`
- Use docstrings for all functions
- Coordinate reference system: EPSG:4326 for storage, project to local CRS for area/distance calculations

## Writing tone guidance

When generating thesis text or comments:
- Frame as **rapid screening**, NOT engineering simulation
- Emphasize **reproducible open-data workflow**
- Emphasize **planning support** value
- Do NOT overclaim physical accuracy
- The safest framing: "a low-data, proxy-based, planning-oriented screening framework capable of revealing relative spatial differences in baseline rooftop solar suitability across the Changsha urban core"

---

## How to help

When working on this project, prioritize in this order:

1. **Don't break what works** — the pipeline is verified. Be cautious with core scoring logic.
2. **Build the missing analyses** — sensitivity, validation, planning metrics (Section 6 above)
3. **Generate figures** — publication-quality maps and charts for the thesis
4. **Support writing** — draft Methods/Results/Discussion sections following the tone guidance above
