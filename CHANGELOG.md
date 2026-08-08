# Changelog

All notable changes to this repository are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.6.0] — 2026-08-09

### Fixed — affects Supplementary Table S3

#### Height-sensitivity threshold is derived, not hard-coded

`height_proxy_sensitivity.py` carried `BASELINE_Q66 = 45.513`, a rounded literal.
The true q66 is 45.51261227233157, so the rounded value sat *above* the real
boundary and excluded the two buildings scoring inside that gap. The baseline
high-potential count came out as 6,409 against the 6,411 reported everywhere
else in the paper.

The threshold is now derived at runtime from the pipeline's stored
`solar_potential_score`, using the same rule as `baseline_solar_potential.py`
(`valid_scores.quantile(0.66)`). It is no longer hard-coded anywhere, so the two
cannot drift apart again. The figure caption picks up the derived value as well.

Rebuilt Table S3 (mean scores are unaffected — the threshold does not enter
them):

| Perturbation | Factor | Mean score | Change | HP count | HP change | HP fraction |
|---:|---:|---:|---:|---:|---:|---:|
| −30% | 0.7 | 43.578590 | −0.6986% | 5,960 | **−7.0348%** | 0.316097 |
| −20% | 0.8 | 43.701964 | −0.4175% | 6,132 | **−4.3519%** | 0.325219 |
| −10% | 0.9 | 43.802166 | −0.1892% | 6,281 | **−2.0278%** | 0.333121 |
| **0%** | 1.0 | 43.885185 | 0.0000% | **6,411** | 0.0000% | 0.340016 |
| +10% | 1.1 | 43.955104 | +0.1593% | 6,508 | **+1.5130%** | 0.345160 |
| +20% | 1.2 | 44.014805 | +0.2954% | **6,601** | **+2.9637%** | 0.350093 |
| +30% | 1.3 | 44.066380 | +0.4129% | 6,680 | **+4.1959%** | 0.354283 |

Only two absolute counts move: the baseline (6,409 → 6,411) and the +20% row
(6,599 → 6,601). The other five are unchanged; the two boundary buildings fall
inside the band only at those factors. Every percentage change shifts slightly
because the denominator changed.

Revised ranges for the manuscript:

    mean score      −0.6986% to +0.4129%   (unchanged)
    HP count        −7.0348% to +4.1959%   (was −7.0058% to +4.2284%)

This supersedes the "Correction — Supplementary Table S3 range" note in 1.5.0,
which reported the ranges as computed against the 6,409 baseline. The correction
recorded there — that the previously published upper bound of +7.0% was
wrong — still stands; only the exact figures are updated.

---

## [1.5.0] — 2026-08-09

### Documentation — Section 4.7 renumbering

A new subsection **4.7.5 Area confounding in the benchmark** was inserted, so
the following subsections shift by one:

| Content | Was | Now |
|---|---|---|
| Area confounding in the benchmark | — (new) | **4.7.5** |
| OSM–Overture footprint comparison | 4.7.5 | **4.7.6** |
| Cross-study comparison | 4.7.6 | **4.7.7** |

All references in this repository are updated to the new numbering. Earlier
notes referring to the OSM–Overture check as "Section 4.8" were wrong under any
numbering and are corrected to 4.7.6. Files touched: `README.md`, `CHANGELOG.md`,
`osm_quality_validation.py`, `src/validation/benchmark_area_confound.py`.
`random_baseline_validation_v2.py` cites 4.7.3, which is unaffected.

### Corrected — stale statements in `osm_quality_validation.py`

Adopting release 2026-07-22.0 (see 1.4.0) left three contradictions in the same
file, now fixed:

- the module docstring and the `OVERTURE_RELEASE` comment both still said the
  release was pinned to 2026-03-18.0;
- the `_get_latest_release()` fallback still defaulted to the retired
  2026-03-18.0 tag, and now falls back to `OVERTURE_RELEASE`.

The header also described Overture as "completely independent of OSM" and framed
the script as assessing OSM footprint reliability. This repository's own results
contradict that: 96 of 100 sampled pairs are geometrically identical on both
snapshots. The header now states plainly that this is a consistency check rather
than an independent accuracy test, and records the four genuinely independent
pairs (mean IoU 0.715, mean absolute area error 27.6%).

### Added

#### 500 m grid product is now tracked

`data/processed/grid_changsha_urban_core_solar_baseline.geojson` (1.23 MB) was
excluded by the blanket `data/processed/*` ignore rule, yet it is a required
`--grid` input for eleven scripts across planning, sensitivity and validation.
A repository snapshot without it — including any Zenodo deposit — could not be
run at all. Added via a targeted negation so the rest of `data/processed`
remains ignored.

#### Supplementary Table S8 — priority-grid threshold scenarios

`src/planning/priority_threshold_scenarios.py` and
`outputs/planning/priority_threshold_scenarios.csv` sweep the priority-grid
cutoff over HP-ratio thresholds 0.60/0.70/0.75/0.80/0.90:

| HP ratio | Grids | HP buildings | km² | GWh/yr | kt CO₂ | Share of area = share of generation |
|---:|---:|---:|---:|---:|---:|---:|
| 0.60 | 216 | 2,190 | 3.3559 | 646.3754 | 368.6279 | 39.5602% |
| 0.70 | 165 | 1,669 | 2.4564 | 473.1303 | 269.8262 | 28.9571% |
| **0.75** | **146** | **1,314** | **2.0879** | **402.1525** | **229.3476** | **24.6130%** |
| 0.80 | 120 | 938 | 1.6402 | 315.9301 | 180.1749 | 19.3359% |
| 0.90 | 90 | 595 | 1.1871 | 228.6439 | 130.3956 | 13.9937% |

0.75 is the cutoff the main analysis resolves to (top 20% of occupied cells);
that row reproduces Table 10 exactly, which cross-checks the two code paths.
Parameters and the grid-assignment rule are imported from `planning_metrics.py`
rather than restated. Area and generation shares are reported separately even
though identical by construction, so the table is self-checking; measured
divergence is 5.6×10⁻¹⁵ pp.

### Documentation

`README.md` gains a **Data availability** section recording what is tracked,
how to obtain the two untracked extracts (`data/raw` 105 MB OSM,
`data/external` 291 MB Overture), and the fact that neither is needed to
reproduce a published number — the footprint-quality statistics come from the
committed 142 kB archive via `--from-archive`.

### Clarification — two grid statistics that look contradictory

The mean high-potential ratio is reported as 0.175 in the main text and 0.450 in
Supplementary S1/S2. Both are correct; they differ only in denominator, and the
relationship is exact because `grid_solar_aggregation.py` assigns
`high_potential_ratio = 0` to empty cells:

    mean over all 1,722 grid cells        0.175490    (main text)
    mean over 671 occupied cells          0.450364    (Supplementary S1/S2)
    0.450364 x 671/1722                 = 0.175490

`grid_solar_baseline_summary.csv` contains all 1,722 rows, so a plain `.mean()`
on it yields 0.175490. `grid_size_comparison.csv` and `threshold_comparison.csv`
both filter to occupied cells (`grid_size_sensitivity.py:92`,
`threshold_sensitivity.py:104`) and yield 0.450364. Each figure should state its
denominator.

### Correction — Supplementary Table S3 range

The height-perturbation range was quoted as −7.0% to +7.0%. The upper bound is
wrong; the actual range of the high-potential count is **−7.0058% to +4.2284%**,
and the mean-score range is −0.6986% to +0.4129%. The asymmetry follows from the
`log1p` transform, which compresses upward perturbations more than downward ones.

Note also that this table's baseline high-potential count is 6,409, not the
6,411 reported elsewhere. `height_proxy_sensitivity.py:61` uses the rounded
threshold 45.513 while the pipeline uses the exact q66 of 45.51261227233157;
exactly two buildings fall in between. Both use `>=`, so the difference is
threshold rounding alone.

---

## [1.4.0] — 2026-08-09

### Changed — affects reported numbers

#### OSM quality check re-run against Overture release 2026-07-22.0

The release cited in Section 3.11 (2026-03-18.0) has been retired upstream and
cannot be downloaded (see 1.3.0). The check is re-run against a currently
available snapshot; `OVERTURE_RELEASE` is now `2026-07-22.0`.

| Metric | 2026-03-18.0 (previous) | 2026-07-22.0 (new) |
|---|---:|---:|
| Matched | 100/100 = 100.0% | 100/100 = 100.0% |
| Pearson r | 0.998 | 0.998 |
| Spearman ρ | 0.997 | **0.999** |
| MAPE | 1.1% | 1.1% |
| Beyond ±20% | 3 | **2** |
| Mean IoU | 0.978 | **0.989** |

Independence check:

| Metric | 2026-03-18.0 | 2026-07-22.0 |
|---|---:|---:|
| Geometrically identical pairs (IoU = 1.0) | 96/100 | **96/100** |
| Genuinely independent pairs | 4 | 4 |
| Mean IoU across those 4 | 0.4580 | 0.7149 |
| Mean absolute area error across those 4 | 28.25% | 27.63% |

The shared-provenance finding is unchanged and now confirmed on two snapshots
four months apart: 96 of 100 sampled OSM buildings have a byte-identical
counterpart in Overture. The aggregate figures describe self-comparison, not
accuracy.

**2026-07-22.0 is now the release of record.** Section 3.11 should cite it, and
the canonical outputs (`osm_quality_results.csv`, `osm_quality_summary.csv`,
`figure/osm_quality_scatter.png`) now hold this run. The superseded
2026-03-18.0 outputs remain retrievable from commit `5e0fc09`; the comparison
table above preserves their values. The interim `_r2026-07-22` and `_archive`
copies used for that comparison have been removed as redundant.

#### GERS identifiers preserved during extraction

The downloader requested only `["geometry", "bbox"]` and wrote
`"properties": {}`, discarding the stable Overture identifier for every
building. It now also requests `id`, so matched buildings remain citable after
a release is retired.

### Added

#### Minimal reproducible archive

`data/external/osm_quality_match_archive.geojson` (142 kB, committed) stores the
only Overture data this analysis depends on: the geometries matched to the 100
sampled OSM footprints. 200 features, two per `sample_id`
(`role="osm"` / `role="overture"`), with `osm_id`, `overture_id` (GERS uuid),
`overture_release`, `osm_source` and `provenance` fields. Geometries are in
EPSG:4326; areas and IoU are recomputed in the local UTM CRS on read.

New `--from-archive` mode recomputes every statistic from this file with no
network access and no 246 MB extract. Verified to reproduce the live run
exactly at reported precision (matched 100, r 0.998, ρ 0.999, MAPE 1.1%,
>±20% 2, mean IoU 0.989); largest per-building deviation is 3.2×10⁻⁸ m² on area
and 7.8×10⁻¹¹ on IoU, from the EPSG:4326 round trip.

This closes the archival gap identified in 1.3.0: a pinned release tag alone
cannot survive Overture's two-release retention policy.

Also adds `--tag` to suffix output filenames, so alternative runs can be
compared without overwriting committed results.

### Known issue — one diagnostic is float-path dependent

The count of sampled pairs whose area difference is *exactly* zero is 79 on the
live path but 96 when recomputed from the archive: the round trip puts both
geometries through the same transform and collapses last-bit differences. This
statistic should not be quoted. The robust indicator of shared provenance is
IoU = 1.0, which is 96/100 on both paths and on both releases. Earlier revision
notes cited "78 of 100 match to exactly zero area difference" — that figure is
an artefact of the computation path, not a property of the data.

---

## [1.3.0] — 2026-08-09

### Changed

#### Overture release pinned to 2026-03-18.0

`osm_quality_validation.py` resolved the Overture Maps release at runtime via
`_get_latest_release()`, so re-running it would silently re-point the reference
dataset at whatever snapshot happened to be current. The release is now pinned:

    OVERTURE_RELEASE = "2026-03-18.0"

matching the snapshot cited in Section 3.11 of the manuscript. Auto-detection is
retained as an opt-in fallback, reachable only via `--release latest`, which
logs a warning that Section 4.7.6 may not reproduce. `--release <tag>` selects an
explicit alternative.

### Known issue — Section 4.7.6 inputs are no longer retrievable

The pinned snapshot **cannot be re-downloaded**. Overture retains only recent
releases, and 2026-03-18.0 has been aged out upstream:

    https://stac.overturemaps.org/catalog.json
      latest: 2026-07-22.0; only 2026-06-17.0 and latest listed as children
    https://stac.overturemaps.org/2026-03-18.0/collections.parquet
      HTTP 404
    s3://overturemaps-us-west-2/release/
      only release/2026-06-17.0/ and release/2026-07-22.0/ remain

The local extract (`data/external/overture_buildings_changsha.geojsonl`, 298 MB)
was also lost during the 1.1.0 merge: `data/external` was tracked as a
placeholder *file* and had become a *directory*, and checking out the
pre-merge branch state replaced the directory, removing its untracked contents.
The file was never in git history, so it cannot be restored from the repository,
and no copy survives on disk.

Consequences:

- The Section 4.7.6 results remain available and are committed
  (`outputs/validation/osm_quality_results.csv`,
  `osm_quality_summary.csv`, `figure/osm_quality_scatter.png`):
  100/100 matched, mean IoU 0.978, r = 0.998, ρ = 0.997, MAPE 1.1%,
  3 buildings beyond ±20%.
- Those numbers **cannot be independently re-derived** by us or by a reviewer,
  because the input snapshot no longer exists at the source.
- Re-running against a currently available release (2026-06-17.0 or
  2026-07-22.0) would produce a different reference dataset and would require
  changing the release tag stated in Section 3.11.

No committed output was overwritten. Deciding how to resolve this in the
manuscript — re-run against a current release and update Section 3.11, or retain
the existing figures with an explicit availability caveat — is deferred.

Note that this limitation is partly independent of the file loss: the snapshot
would have aged out upstream regardless, so the archival gap was latent from the
start. Archiving the input extract alongside the results (e.g. with the Zenodo
deposit) would prevent a recurrence.

---

## [1.2.0] — 2026-08-09

### Changed — affects reported numbers

#### Annual irradiance switched to the Global Solar Atlas value

`planning_metrics.py` applied a hard-coded 1,300 kWh/m²/yr whose provenance
could not be established (see 1.1.0). It now uses **1,203.8211 kWh/m²/yr**,
computed from `outputs/validation/gsa_comparison.csv` as the mean of `mean_ghi`
over the 671 occupied 500 m cells (3.298140 kWh/m²/day × 365). This is
reproducible from `src/analysis/gsa_external_validation.py`.

Cross-check quoted in the source comment: NASA POWER 2001–2020 climatology at
28.228 N, 112.939 E gives 3.2678 kWh/m²/day = 1,192.7 kWh/m²/yr, 0.9% below the
GSA figure. That value is supplied externally; this repository contains no NASA
POWER retrieval code, so it cannot be re-derived here.

Generation and CO₂ scale by 0.926016. Deployable area is unchanged — it does not
depend on irradiance.

| Quantity | Before (1,300) | After (1,203.8211) |
|---|---:|---:|
| Deployable rooftop area | 8.482897 km² | **8.482897 km² (unchanged)** |
| Annual generation | 1,764.4426 GWh/yr | **1,633.9024 GWh/yr** |
| Annual CO₂ reduction | 1,006.2616 kt/yr | **931.8146 kt/yr** |
| Share of Changsha 2022 demand | 3.4142% | **3.1616%** |

### Fixed — manuscript Table 10 was internally inconsistent

Table 10 reported the priority-grid subset as 2.12 km² and 459 GWh. Those two
cells cannot both be right: in this model generation is exactly proportional to
deployable area, so a subset's share of generation must equal its share of area.
The published pair implies 25.0% by area but 26.0% by generation, i.e. two
different irradiance values (2.12 → 459 implies 1,353 kWh/m²/yr, while
8.48 → 1,764 implies 1,300).

Neither cell is reproducible. Seven priority-set definitions were tested
(quantile cutoff, strict top-146, ratio == 1.0, top-20%-by-count, and three
fixed ratio thresholds), under both centroid and polygon joins, and for both
high-potential-only and all-building bases. The closest values are 2.0879 km²
(HP only) and 2.1529 km² (all buildings in the 146 cells); nothing yields 2.12
or 459.

Corrected values, now emitted by the pipeline rather than computed by hand:

| Quantity | Table 10 | Corrected |
|---|---:|---:|
| Priority deployable area | 2.12 km² | **2.0879 km²** |
| Priority annual generation | 459 GWh/yr | **402.1525 GWh/yr** |
| Priority annual CO₂ | — | **229.3476 kt/yr** |
| Share of deployable area | 25.0% | **24.6130%** |
| Share of generation | 26.0% | **24.6130%** (identical, as required) |
| HP buildings in priority grids | — | 1,314 of 6,411 |

Note the generation figure changes for two independent reasons: the corrected
subset basis and the new irradiance constant. At the old 1,300 constant the
corrected subset would have been 434.2823 GWh.

### Added

- `planning_metrics.py` now computes the priority-grid subset internally and
  writes `outputs/planning_metrics_priority_aggregate.csv`, including both share
  measures and a `share_discrepancy_pp` column that must be zero. A runtime
  warning fires if the two shares ever diverge, so this class of inconsistency
  cannot recur silently.
- `CITY_ANNUAL_CONSUMPTION_GWH = 51679.0` (Changsha 2022, external reference)
  to express generation as a share of demand: total 3.1616%, priority subset
  0.7782%.

---

## [1.1.0] — 2026-08-09

Revision release. A pre-revision audit of the analysis code found one
methodological defect that propagated into reported results, three places where
documentation contradicted the code, and two reported figures that cannot be
reproduced from this repository. All of these are disclosed below, including the
ones that change published numbers.

No pipeline stage was re-run with different parameters, and no input data
changed. Every number that moved did so because a defective statistic was
corrected, not because the underlying screening changed.

### Fixed — affects reported numbers

#### Tier membership was judged against a fixed absolute cutoff (`weight_sensitivity.py`)

The weight-sensitivity analysis assigned high-potential tier membership for
every weight variant using one absolute score cutoff, `q66 = 45.513`, carried
over from the baseline run. That is valid only when a variant reorders buildings
without shifting the score distribution. The area-only variant (W4) shifts it —
mean score 43.885 → 56.330 — so nearly the whole stock clears the cutoff.

| Quantity | Superseded (fixed cutoff) | Corrected (q66 re-derived per variant) |
|---|---:|---:|
| W4 high-potential buildings | 16,876 of 18,855 (89.5%) | 6,411 of 18,855 (34.0%) |
| W4 derived priority grids | 383 of 671 | 146 of 671 |
| W4 vs baseline tier overlap | 93.84% | **85.62%** |
| Jaccard of the two priority sets | 0.3495 | **0.8013** |
| Buildings changing tier | — | 702 (3.724% of stock) |
| Baseline tier retained | — | 94.53% |

The superseded overlap figure was high only because the inflated set swallowed
the smaller one, which the Jaccard index of 0.3495 makes plain.

**Impact on the manuscript.** The claim of a priority-grid overlap above 90%
(Section 4.4.6) originates from this defect and does not survive it. The
corrected value is 85.62%.

Tier membership is now defined as a fixed *share* of the stock, with q66
re-derived from each variant's own distribution. The superseded counts are
retained in the output under `fixed_threshold_*` column names alongside the
corrected `quantile_recomputed_*` columns, so the difference remains inspectable
rather than being silently overwritten.

Rank correlations are unaffected by this fix — they do not depend on a cutoff.

#### Grid join dropped boundary-straddling buildings (`weight_sensitivity.py`)

`build_grid_scores` joined the full building polygon to the 500 m grid with
`predicate="within"`, so any building crossing a cell boundary matched no cell
and was dropped without warning. The official grid product
(`grid_solar_aggregation.py`) assigns buildings by centroid. The two disagreed
on both cell population and cell means.

| Quantity | Before (polygon-within) | After (centroid-within) |
|---|---:|---:|
| Occupied cells | 644 | **671** (matches the grid product) |
| Grid ρ, W1 vs baseline | +0.995472 | +0.994912 |
| Grid ρ, W3 vs baseline | +0.999380 | +0.999237 |
| Grid ρ, W4 vs baseline | +0.947480 | **+0.941782** |

**Impact on the manuscript.** The grid-level correlation for the area-only
variant should read +0.9418, not +0.9475.

### Documentation corrected

- **`CLAUDE.md`** described the composite score as combining "footprint area,
  height proxy, and orientation". No orientation term exists anywhere in the
  pipeline. Replaced with the actual formula. If the manuscript states that
  orientation enters the score, that statement is wrong.
- **`pvlib_benchmark_validation.py`** docstring read "Flat roof: tilt=0°,
  azimuth=180°", implying a transposition onto an oriented plane. Because tilt is
  zero the code takes POA = GHI directly; `pvlib.irradiance` is never called and
  `surface_tilt` / `surface_azimuth` are never passed anywhere. The azimuth was
  inert text.
- **`planning_metrics.py`** claimed the 1,300 kWh/m²/yr irradiance constant was
  "derived from ERA5 climatological mean and cross-checked against NASA POWER".
  No retrieval code, API call, or source dataset for either exists in this
  repository. Restated as an externally sourced constant whose provenance belongs
  in the manuscript. The value itself was unchanged at this release, so all
  planning outputs were unchanged: 8.4829 km², 1,764.4426 GWh/yr,
  1,006.2616 kt CO₂/yr. (Superseded in 1.2.0, which replaces the constant.)

### Disclosed — could not be reproduced

Two figures quoted in Section 4.4.6 do not follow from this code.

- **Building-level ρ = 0.983.** Thirty-nine correlation definitions were tested —
  Spearman, Pearson and Kendall; final score and `base_score` without the
  category multiplier; with and without the log transform; on the full stock, the
  high-potential subset and its complement; all six pairwise weight-variant
  combinations; grid-level means and medians under both join conventions. None
  lands in [0.9815, 0.9845]. The nearest values are 0.976598 (W3 vs W4) and
  0.992627 (non-high-potential subset). The reproducible figure for the area-only
  comparison is **0.971907**. Git history contains no prior version of the output
  file carrying 0.983, and no such value appears anywhere under `outputs/`.
  **The source of 0.983 could not be located.**
- **Priority-grid overlap > 90%.** Reproducible only under the superseded
  fixed-threshold tier definition described above (93.84%). The corrected value
  is **85.62%**.

### Disclosed — validation independence

Three results presented as validation are wholly or partly circular. None is a
code defect; all affect interpretation.

- **pvlib benchmark.** Building-level yield reduces to
  `footprint_area × shading × constant`, since irradiance is a single scalar,
  tilt is zero, azimuth is absent, and the shading term fires for 1.69% of
  buildings in the benchmark zones. Controlling for footprint area removes the
  agreement: mean per-zone partial Spearman ρ = −0.0219, undefined in 17 of 20
  zones because `rank(yield)` is fully determined by `rank(area)`. The headline
  mean ρ of 0.950 is numerically almost identical to ρ(score, area) = 0.951.
  Per-zone agreement tracks height degeneracy at ρ = +0.977 (p = 1.7×10⁻¹³).
- **OSM–Overture comparison.** 96 of 100 sampled pairs are geometrically
  identical (IoU = 1.0, centroid distance < 1 µm) and 78 match to exactly zero
  area difference, reflecting Overture's OSM provenance in this region. Only 4
  pairs are independent; across those, mean IoU is 0.458 and mean absolute area
  error 28.2%.
- **Pooled benchmark correlation.** The three-zone benchmark reports per-zone
  ρ ≥ 0.965; pooling the same three zones gives ρ = 0.584897. Only the per-zone
  figures appear to have been reported.

### Corrected in supporting records

Values verified against the code that differ from figures quoted during
revision:

| Quantity | Quoted | Actual |
|---|---:|---:|
| Priority grids' share of generation potential | 26% | **24.613%** (see 1.2.0) |
| Category ablation, grid-level ρ | ≈0.999 | **0.990315** |
| Weight sensitivity, minimum pairwise ρ | ≥0.959 | **0.958726** |
| Permutation null 95% CI | [−0.09, +0.09] | **[−0.0878, +0.0837]** |
| Height perturbation, HP count change at −30% | ±7% | **−7.006%** |

The last three are rounding-boundary cases rather than errors.

### Added

- `src/validation/benchmark_area_confound.py` — tests whether proxy-versus-pvlib
  agreement survives controlling for footprint area (partial Spearman via rank
  residuals).
- `src/validation/proxy_composition_diagnostics.py` — height-proxy composition,
  score-component variance decomposition, area-only counterfactual.
- `src/validation/revision_audit.py` — provenance hunt across 39 correlation and
  18 overlap definitions; priority-grid generation share; Global Solar Atlas
  spread; Overture independence check.
- `src/validation/si_tables_and_shading_scope.py` — Supplementary Tables A and B,
  Figure S4, and shading-trigger analysis across all 671 occupied cells by
  building-density quintile.
- `README.md` — manuscript mapping and known-limitations sections.
- `CHANGELOG.md` — this file.
- Tracked three previously untracked scripts that produce reported numbers:
  `random_baseline_validation.py`, `random_baseline_validation_v2.py`,
  `osm_quality_validation.py`, with their outputs and figures.

### Repository hygiene

- `data/external` was tracked as an empty placeholder *file* but had become a
  *directory* holding a 298 MB Overture extract that was not ignored. Replaced
  with `data/external/.gitkeep` and an ignore rule, matching the pattern used for
  `data/raw`, `data/interim` and `data/processed`.
- Closed an unterminated code fence in `README.md`.
- Added `writing/` to `.gitignore`.

### Known issues

- `.gitignore` contains a corrupted entry, `!outputs/tables/.gitkeepwriting /`,
  left from an earlier edit that lost a newline. Fixing it would change ignore
  semantics for `outputs/tables/.gitkeep`, so it is left for a separate decision.
- The three validation scripts listed under Added remain at the repository root
  rather than under `src/validation/`, to avoid changing paths that may be
  referenced elsewhere.

---

## [1.0.0] — 2026-04-05

Initial state at the close of the analysis phase: OSM acquisition, height proxy,
urban-core extraction, building-level scoring, 500 m grid aggregation, planning
metrics, four sensitivity analyses, and external validation against the Global
Solar Atlas and a pvlib benchmark.
