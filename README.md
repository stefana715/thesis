# Thesis

PhD thesis project repository for a low-data urban solar potential assessment framework in Changsha, China.

## Project goal
This project develops a reproducible workflow for urban solar potential assessment under low-data conditions, using open-source building, weather, and geospatial datasets.

## Study area
Changsha, Hunan, China.

## Planned workflow
1. Data collection
2. Data preprocessing
3. Baseline solar potential model
4. Dataset building
5. Machine learning model
6. Mapping and spatial analysis

## Repository structure
- `data/`: raw, interim, and processed datasets
- `src/`: scripts for data, features, models, and visualization
- `outputs/`: figures and tables
- `docs/`: project notes and overview
- `configs/`: configuration files
- `logs/`: run logs

## Environment setup
Create a Python environment and install dependencies from:

```bash
pip install -r requirements.txt
```

Core packages: geopandas, shapely, pyproj, osmnx, rasterio, pvlib, pandas,
numpy, scipy, matplotlib, scikit-learn, pyyaml, jupyter.

---

## Data availability

### Tracked in this repository

Everything needed to reproduce the published results is committed:

| File | Size | Role |
|---|---:|---|
| `data/processed/buildings_changsha_urban_core_solar_baseline.geojson` | 68 MB | 18,855 scored urban-core buildings — input to every analysis |
| `data/processed/grid_changsha_urban_core_solar_baseline.geojson` | 1.2 MB | 500 m grid product — required `--grid` input for nearly every script |
| `data/external/osm_quality_match_archive.geojson` | 142 kB | Matched OSM/Overture geometries for the footprint-quality check |
| `outputs/`, `figure/` | — | All reported tables, CSVs and figures |

### Not tracked — obtain separately

Two inputs are too large for version control. Neither is needed to reproduce any
published number; both are needed only to regenerate the tracked products from
scratch.

**`data/raw/buildings_changsha.geojson`** (105 MB) — raw OpenStreetMap building
extract for the Changsha municipal extent.

```bash
python src/data/download_osm_buildings.py
```

Re-downloading fetches current OSM, which has changed since the original
extract; the tracked `data/processed/` products are the frozen state the paper
reports. Use them rather than regenerating if you want the published numbers.

**`data/external/overture_buildings_changsha.geojsonl`** (291 MB) — Overture
Maps building footprints for the Changsha bounding box, used as the reference
dataset in the footprint-quality check.

```bash
python osm_quality_validation.py --download-only     # release pinned to 2026-07-22.0
```

**This download is not required.** The full footprint-quality analysis
(Section 4.7.6) reproduces from the committed 142 kB archive with no network
access:

```bash
python osm_quality_validation.py --from-archive
```

which returns the reported statistics exactly — 100/100 matched, mean IoU 0.989,
r = 0.998, ρ = 0.999, MAPE 1.1%, 2 buildings beyond ±20%. The archive holds the
geometries of the 100 sampled OSM buildings and their matched Overture
counterparts, with GERS identifiers and provenance fields.

Keeping that archive matters because Overture retains only its two most recent
releases: the release originally cited in the manuscript (2026-03-18.0) has
already been retired and returns HTTP 404. The pinned 2026-07-22.0 snapshot will
age out the same way. The archive is what makes the check reproducible after
that happens — a pinned release tag alone is not enough.

### Archiving

For a Zenodo deposit, the git snapshot is self-sufficient: it contains every
input required to re-run the pipeline end to end. The two untracked extracts
above may be attached separately if byte-level provenance of the raw inputs is
wanted, but no published figure depends on them.

---

## Manuscript mapping

Which script produces which reported number, table, or figure. Section numbers
follow the working manuscript and should be re-checked against the final
version before submission.

### Pipeline

| Script | Manuscript section | Produces |
|---|---|---|
| `src/data/download_osm_buildings.py` | Methods — data acquisition | 33,374 raw OSM buildings |
| `src/features/building_height_proxy.py` | Methods — height proxy | Four-level height cascade; urban-core split 654 / 562 / 17,587 / 52 |
| `src/features/extract_phase1_urban_core.py` | Methods — study area | 18,855 urban-core buildings (56.50% of 33,374) |
| `src/models/baseline_solar_potential.py` | Methods — scoring; Results 4.1–4.2 | `solar_potential_score`; mean 43.885; q33 = 41.797, q66 = 45.513; 6,411 high-potential (34.002%) |
| `src/analysis/grid_solar_aggregation.py` | Results 4.3 | 500 m grid; 671 occupied of 1,722; grid mean score 13.017–72.571 |
| `src/planning/planning_metrics.py` | 3.9, Results 4.4 | 8.4829 km² deployable; 1,633.9024 GWh/yr; 931.8146 kt CO₂/yr; 146 priority grids (21.759% of occupied) |
| `src/planning/planning_metrics.py` (priority subset) | Table 10 | 2.0879 km²; 402.1525 GWh/yr; 229.3476 kt CO₂/yr; 24.613% of both deployable area and generation |
| `src/visualization/fig01–fig08_*.py` | Figures 1–8 | Study-area, distribution, classification, grid and flowchart figures |

### Sensitivity analyses

| Script | Manuscript section | Produces |
|---|---|---|
| `src/sensitivity/grid_size_sensitivity.py` | 4.5.1 | Grid mean score 44.343–46.207 across 250/500/750/1000 m (spread 4.204% of minimum) |
| `src/sensitivity/threshold_sensitivity.py` | 4.5.2 | High-potential count vs quantile cutoff, q50–q80 |
| `src/sensitivity/height_proxy_sensitivity.py` | 4.5.3, Table S3 | ±30% height perturbation: mean score −0.6986% / +0.4129%; HP count −7.0348% / +4.1959% (baseline 6,411; q66 derived at runtime, not hard-coded) |
| `src/sensitivity/category_ablation.py` | 4.5.4 | Building ρ = 0.992377, grid ρ = 0.990315, 160 buildings changed (0.849%), mean abs diff 0.280; baseline 6,411 HP → 6,277 ablated (q66 derived at runtime) |
| `src/sensitivity/weight_sensitivity.py` | 4.4.4, 4.4.6 | Weight variants W1–W4; minimum pairwise ρ = 0.958726; area-only vs baseline: building ρ = 0.971907, grid ρ = 0.941782, 702 buildings change tier (94.53% retained, Jaccard 0.8962) |

### Validation

| Script | Manuscript section | Produces |
|---|---|---|
| `src/analysis/gsa_external_validation.py` | 4.6 | Grid score vs Global Solar Atlas GHI, ρ = 0.2033; intra-urban GHI spread 2.736% |
| `src/validation/pvlib_benchmark_validation.py` | 4.7 | Three initial zones, per-zone ρ ≥ 0.965217 (pooled ρ = 0.584897) |
| `src/validation/benchmark_robustness.py` | 4.7 | 20 stratified zones, mean ρ = 0.950000; grid 807 ρ = 0.431304 |
| `src/validation/benchmark_param_sensitivity.py` | 4.7 | Shading radius / roof factor / shading coefficient variants |
| `random_baseline_validation_v2.py` | 4.7 | Permutation null, 95% CI [−0.0878, +0.0837], p < 0.001 |
| `osm_quality_validation.py` | 3.11, 4.7.6 | OSM vs Overture, release **2026-07-22.0**: 100/100 matched, mean IoU 0.989, r = 0.998, ρ = 0.999, MAPE 1.1%, 2 buildings beyond ±20% |
| `osm_quality_validation.py --from-archive` | 4.7.6 | Same statistics recomputed from `data/external/osm_quality_match_archive.geojson`, no network required |

### Revision audit → Supplementary Material

| Script | Output | Produces |
|---|---|---|
| `src/validation/benchmark_area_confound.py` | 4.7.5, SI Table A | Partial and unit-area correlations controlling for footprint area |
| `src/validation/proxy_composition_diagnostics.py` | SI text | Height-proxy composition, score-component variance, area-only counterfactual |
| `src/validation/revision_audit.py` | audit CSVs | Provenance hunt across 39 correlation and 18 overlap definitions; priority-grid generation share; Overture independence check |
| `src/validation/si_tables_and_shading_scope.py` | SI Tables A–B, Figure S4 | Height degeneracy vs benchmark agreement (ρ = +0.9769, p = 1.66×10⁻¹³); shading scope by density quintile |
| `src/validation/osm_completeness.py` | completeness CSVs | OSM vs Overture: counts, extents, provenance, and `ratio_area` (a ratio of totals, 61.44%) — not a coverage measure |
| `src/validation/osm_completeness_geometric.py` | 4.7.7, completeness CSVs | **Metric of record**: `coverage_geo` = 60.11% over the 671 occupied cells (dissolve + intersect, bounded [0,1]); `osm_in_ref` = 98.08%; coverage uncorrelated with score (p = 0.247), high-potential ratio (p = 0.133) and priority selection (Mann-Whitney p = 0.138) |

---

## Known limitations

These are properties of the method and the input data, established by the
scripts under `src/validation/`. They constrain how the outputs may be read.

**Height proxy is largely a constant.** 93.275% of the 18,855 urban-core
buildings take a building-type default height rather than an observed one, and
89.764% take the single value 9.0 m (residential default, 3 storeys × 3.0 m).
The 25th, 50th and 75th percentiles of `height_proxy_m` are all 9.0. The
0.35-weighted height term therefore contributes 12.437% of the variance in
`base_score`, against 80.366% for the area term — the nominal weight overstates
the height component's real influence.

**The shading heuristic almost never fires.** Across all 671 occupied cells,
the inter-building shading term is triggered for only 3.87% of buildings; the
figure rises from 0.84% to 4.50% between the lowest and highest building-density
quintile, so it is low everywhere. The binding constraint is height degeneracy,
not spatial density: the trigger requires a *taller* neighbour within 50 m, and
89.764% of buildings share one height value. Even in the densest quintile
(mean nearest neighbour 29.8 m, ~5 neighbours within 50 m) the trigger rate is
4.50%. Shading is consequently not an effective discriminator between buildings
in this framework, and the benchmark's rank correlations are insensitive to the
shading radius and coefficient because the code path is rarely reached.

**The pvlib benchmark is an internal consistency check, not independent
validation.** It uses a single-point Ineichen clear-sky irradiance
(2,158.8 kWh/m²/yr, roughly 79% above the Global Solar Atlas value of
1,203.8 kWh/m²/yr for the same area), tilt = 0° with no transposition, no
azimuth, and no time series. Building-level yield reduces to
`footprint_area × shading × constant`, so once footprint area is controlled the
agreement disappears: mean per-zone partial Spearman ρ = −0.0219, and in 17 of
20 zones the partial correlation is undefined because `rank(yield)` is fully
determined by `rank(area)`. The headline mean ρ of 0.950 is numerically almost
identical to ρ(score, area) = 0.951. Agreement per zone tracks height
degeneracy closely (ρ = +0.977 against the modal-height share, p = 1.7×10⁻¹³).

**The OSM–Overture comparison is largely a self-comparison.** Of 100 sampled
pairs, 96 are geometrically identical (IoU = 1.0, centroid distance < 1 µm),
reflecting Overture's OSM provenance for this region. Only 4 pairs are genuinely
independent; across those the mean IoU is 0.715 and the mean absolute area error
is 27.6%. The reported aggregate figures (mean IoU 0.989, MAPE 1.1%) are
dominated by the identical pairs and should not be read as an accuracy estimate.
This holds on two Overture snapshots four months apart (2026-03-18.0 and
2026-07-22.0), both giving 96/100 identical.

**Overture inputs are archived, not re-downloadable.** Overture retains only its
two most recent releases, so a pinned release tag does not survive long term —
the release originally cited has already been retired. The matched geometries
are therefore committed as `data/external/osm_quality_match_archive.geojson`
(142 kB); `python osm_quality_validation.py --from-archive` reproduces every
statistic with no network access.

**Generation is exactly proportional to deployable area.** With uniform
irradiance, panel efficiency and performance ratio, `E = A_deploy × η × G × PR`
reduces to a constant 192.611 GWh per km² of deployable area. Any subset's share
of generation therefore *equals* its share of deployable area by construction —
a table reporting two different shares for the same subset is internally
inconsistent, not a rounding artefact. `planning_metrics.py` now computes the
priority-grid subset itself and asserts the two shares agree.

**OSM covers about 60% of the mapped rooftop area, and the totals are scoped
accordingly.** The metric of record is geometric coverage — each dataset clipped
to the cell, dissolved, then intersected — giving **60.11%** across the 671
occupied cells. Two independent estimates agree: the ratio of rooftop-area
totals gives 61.44%, and treating the non-OSM-sourced Overture stock as the
missing remainder gives 61.75%. They coincide because 98.08% of OSM rooftop area
falls inside comparator footprints. Against Overture Maps — a valid reference here, since 94.88% of
its Changsha stock comes from a non-OSM source — the urban core holds 18,855 OSM
buildings against 65,487 Overture buildings, and 18.6745 km² of OSM rooftop
against 30.3951 km². The reported 8.4829 km² deployable area and
1,633.9024 GWh/yr therefore describe the **OSM-mapped stock**, not the total
potential of the Changsha urban core. Crucially the shortfall is not spatially
structured: per-cell coverage by area is uncorrelated with mean score
(ρ = +0.0385, p = 0.321), with high-potential ratio (ρ = +0.0558, p = 0.150) and
with priority selection (Mann-Whitney p = 0.226), so the relative screening and
the priority grids are not artefacts of survey density. A separate omission:
92 cells contain Overture buildings but no OSM buildings at all (4,102
buildings, 1.2096 km²) and are invisible to the framework.

**The annual irradiance constant is uniform in space.** `planning_metrics.py`
applies 1,203.8211 kWh/m²/yr (Global Solar Atlas, mean over the 671 occupied
cells) to every building. That is defensible here because the intra-urban GHI
spread is only 2.736%, but it means irradiance contributes no between-building
variation. The NASA POWER cross-check quoted in the source comment
(1,192.7 kWh/m²/yr) is supplied externally and cannot be re-derived from this
repository.

**Two reported figures could not be reproduced.** A building-level
ρ = 0.983 does not arise from any of 39 correlation definitions tested
(the reproducible value is 0.971907), and a priority-grid overlap above 90%
arises only from a superseded fixed-threshold tier definition that inflates the
comparison set from 146 to 383 cells (the corrected value is 85.62%,
Jaccard 0.8013). See `CHANGELOG.md`.
