# Results

## 4. Results

### 4.1 Urban Core Extraction

Application of the density-based urban core extraction algorithm to the full Changsha municipal building dataset yielded a spatially coherent urban core that captures the dense central districts of the city. The raw OSM download encompassed 33,374 building footprints across the full administrative extent of Changsha. After filtering to retain only buildings whose centroids fell within the extracted urban core boundary, 18,855 buildings were retained, corresponding to a retention rate of 56.50%.

The extracted urban core polygon is shown in Figure 1 overlaid on the full Changsha study area boundary. The core region captures the contiguous high-density urban fabric of the Furong, Tianxin, Yuelu, and Kaifu districts, excluding the sparser peri-urban and rural zones to the north and south. The smoothed boundary exhibits a broadly compact shape consistent with the spatial structure of a Chinese prefectural-level city.

The urban core building set represents the primary analytical domain for all subsequent scoring, classification, and aggregation steps.

### 4.2 Building-Level Solar Potential Score Distribution

The solar potential scoring model was applied to all 18,855 buildings in the urban core dataset. The resulting score distribution is approximately unimodal and moderately right-skewed, centred around a mean of 43.885 (on a scale of 0–100). Descriptive statistics for the building-level score distribution are summarised below.

The 33rd and 66th percentile thresholds used for ternary classification were q33 = 41.797 and q66 = 45.513. The relatively narrow interquartile range (IQR ≈ 3.72 score units, spanning 42.0–45.7 across the middle 50% of buildings) reflects the fact that the composite score is driven primarily by log-transformed area and height values that vary continuously across a large, internally heterogeneous building stock. Figure 2 shows the full score distribution with the q33 and q66 threshold lines annotated, illustrating the three classification zones.

Buildings assigned to the commercial functional category received a multiplier of 1.10 and accordingly achieved higher mean scores than residential buildings (multiplier 1.00) or mixed/unknown buildings (multiplier 0.95). The score distribution therefore reflects both structural size differences and functional type composition within the urban core.

### 4.3 High-Potential Building Classification

Application of the q66 threshold to the solar potential score distribution yielded 6,411 high-potential buildings, representing 34.00% of the urban core building stock. The three classification tiers contain approximately equal shares of the dataset by construction: low-potential buildings (score ≤ q33) account for 33.33% of the stock; medium-potential buildings (q33 < score ≤ q66) account for 32.67%; and high-potential buildings (score > q66) account for 34.00%.

The spatial distribution of the three building classes is shown in Figure 3. High-potential buildings are not uniformly distributed across the urban core: they tend to cluster in areas characterised by large commercial and mixed-use footprints, consistent with the known concentration of major commercial developments in the central business districts and along primary arterial corridors. Low-potential buildings predominate in denser residential neighbourhoods where smaller, older building footprints are more common.

The geographic concentration of high-potential buildings in commercially dominated sub-areas reinforces the planning relevance of the classification: targeted policy interventions in a relatively small number of spatial clusters could engage a disproportionately large share of deployable rooftop area.

### 4.4 Grid-Level Spatial Aggregation

Building-level results were aggregated to a 500 m × 500 m grid to support meso-scale spatial analysis. The grid covered the bounding box of the urban core dataset, generating 1,722 total grid cells. Of these, 671 cells (38.97%) contained at least one building and were designated as occupied. The remaining 1,051 cells correspond to open water bodies, major infrastructure corridors, green spaces, and peri-urban areas intersecting the grid bounding box.

#### 4.4.1 Mean Solar Score Distribution across Grid Cells

The mean solar potential score for occupied grid cells ranged from 13.0 to 72.6 across the urban core (Figure 4). The distribution of cell-level mean scores had a mean of 45.80 and a standard deviation of 6.11, indicating moderate spatial heterogeneity. The 25th, 50th, and 75th percentiles of the grid-level mean score were 43.01, 44.88, and 48.02, respectively.

Cells with elevated mean scores (above approximately 55) correspond to areas dominated by large commercial developments, including major retail complexes, government buildings, and industrial facilities. Cells with lower mean scores correspond to densely subdivided residential areas where individual building footprints are small and heights are modest. The spatial pattern is broadly consistent with the land-use structure of the Changsha urban core, with a concentration of high-scoring cells along the riverside commercial corridor and primary commercial nodes.

#### 4.4.2 High-Potential Ratio Distribution

The high-potential ratio (proportion of buildings within each occupied grid cell that exceed the q66 threshold) was computed for all occupied cells. Of the 671 occupied cells, 612 (91.2%) contained at least one high-potential building and therefore had a high-potential ratio greater than zero.

The mean high-potential ratio across all occupied cells was 0.175, with a median of 0.410 and a standard deviation of 0.313. The substantial gap between the mean and median reflects the influence of a large number of cells with low ratios (where high-potential buildings are sparse) on the distribution average. Figure 5 shows the spatial distribution of high-potential ratio across the urban core.

Grid cells with high-potential ratios approaching 1.0 represent areas where virtually all buildings are classified as high-potential; these cells constitute the most promising targets for district-scale deployment programmes. Cells with ratios below 0.20 contain predominantly residential stock with smaller footprints and lower height proxies, requiring more selective building-by-building appraisal before deployment decisions are made.

### 4.5 Sensitivity Analysis

Three sensitivity analyses were conducted to assess the robustness of the screening results to key methodological choices: grid cell size, classification threshold, and height proxy uncertainty.

#### 4.5.1 Grid Size Sensitivity

The grid aggregation was repeated using cell sizes of 250 m, 500 m, 750 m, and 1000 m. Results are summarised in Table 1 and illustrated in Figure 6.

**Table 1. Grid size sensitivity: key aggregation statistics.**

| Grid size (m) | Total cells | Occupied cells | Occupancy rate | Mean score (mean) | HP ratio (mean) |
|---|---|---|---|---|---|
| 250 | 6,723 | 1,979 | 29.4% | 46.21 | 0.471 |
| 500 | 1,722 | 671 | 39.0% | 45.80 | 0.450 |
| 750 | 756 | 375 | 49.6% | 45.73 | 0.451 |
| 1000 | 441 | 194 | 44.0% | 44.34 | 0.398 |

The mean solar score at grid level is highly consistent across the four cell sizes, ranging from 44.34 (1000 m) to 46.21 (250 m), a difference of less than two score points on the 0–100 scale. The mean high-potential ratio also remains broadly stable, varying between 0.398 (1000 m) and 0.471 (250 m). These results indicate that the grid-level characterisation is not sensitive to reasonable choices of spatial resolution, and that the 500 m default provides a good balance between spatial detail and statistical stability.

The primary difference across resolutions is in the number of occupied cells and the occupancy rate: finer grids produce more cells but with lower average occupancy, while coarser grids produce fewer, better-filled cells. Spatial patterns of solar heterogeneity are preserved across all four resolutions.

#### 4.5.2 Classification Threshold Sensitivity

The classification threshold was systematically varied from q50 to q80 in five steps. Results are presented in Table 2 and Figure 7.

**Table 2. Threshold sensitivity: high-potential building counts and grid-level ratios.**

| Quantile threshold | Score threshold | HP buildings | HP fraction | Grids with HP ratio > 0 | Mean grid HP ratio |
|---|---|---|---|---|---|
| q50 | 43.74 | 9,428 | 50.0% | 630 | 0.596 |
| q55 | 44.25 | 8,485 | 45.0% | 627 | 0.552 |
| q60 | 44.78 | 7,542 | 40.0% | 621 | 0.505 |
| q66 | 45.51 | 6,411 | 34.0% | 612 | 0.450 |
| q70 | 46.03 | 5,657 | 30.0% | 597 | 0.406 |
| q75 | 46.79 | 4,714 | 25.0% | 582 | 0.357 |
| q80 | 47.82 | 3,771 | 20.0% | 560 | 0.303 |

As expected, the number of high-potential buildings decreases monotonically from 9,428 (q50) to 3,771 (q80) as the threshold becomes more stringent. The number of grid cells containing at least one high-potential building remains largely stable across the full threshold range (560–630), confirming that high-potential buildings are spatially distributed across nearly all occupied grid cells regardless of the threshold choice. The mean grid-level high-potential ratio decreases smoothly from 0.596 (q50) to 0.303 (q80), a range of approximately 0.3 ratio units.

The q66 threshold used in the main analysis lies in the middle of the explored range and produces a balanced classification that retains a meaningful but non-trivial share of buildings for priority consideration. The smooth monotonic behaviour of all metrics across thresholds indicates that the framework is not critically sensitive to the precise threshold value chosen.

#### 4.5.3 Height Proxy Perturbation Sensitivity

The height proxy values for all urban core buildings were perturbed by scaling factors ranging from 0.70 to 1.30 (i.e., ±10%, ±20%, ±30% relative to the baseline estimate). The full scoring and classification pipeline was re-run for each perturbation level. Results are summarised in Table 3.

**Table 3. Height proxy perturbation sensitivity: mean score and high-potential count.**

| Perturbation | Height factor | Mean score | Median score | HP count | HP fraction |
|---|---|---|---|---|---|
| −30% | 0.70 | 43.58 | 43.43 | 5,960 | 31.6% |
| −20% | 0.80 | 43.70 | 43.55 | 6,132 | 32.5% |
| −10% | 0.90 | 43.80 | 43.65 | 6,281 | 33.3% |
| Baseline | 1.00 | 43.89 | 43.74 | 6,409 | 34.0% |
| +10% | 1.10 | 43.96 | 43.81 | 6,508 | 34.5% |
| +20% | 1.20 | 44.01 | 43.87 | 6,599 | 35.0% |
| +30% | 1.30 | 44.07 | 43.92 | 6,680 | 35.4% |

Even a ±30% perturbation of all height proxy values produces a mean score change of less than 0.5 points (approximately 1.1% of the full score range). The high-potential building count changes by at most 720 buildings (from 5,960 at −30% to 6,680 at +30%), a variation of ±5.6% relative to the baseline count of 6,409. These results confirm that the composite score is dominated by the footprint area component (weight 0.65) and that height proxy uncertainty has a modest, predictable influence on results. The framework remains stable even under substantial height estimation errors, which is an important property for a low-data-condition application.

### 4.6 Planning Metrics

To translate the high-potential building classification into planning-relevant order-of-magnitude estimates, aggregate planning metrics were computed for the 6,411 high-potential buildings (Table 4).

**Table 4. Aggregate planning metrics for high-potential buildings.**

| Metric | Value |
|---|---|
| High-potential buildings | 6,411 |
| HP fraction of urban core | 34.0% |
| Total footprint area (km²) | ~13.05 |
| Deployable rooftop area (km²) | 8.48 |
| Annual electricity generation (GWh/year) | 1,764 |
| Annual CO₂ reduction (kt/year) | 1,006 |

Applying a rooftop utilisation factor of 0.65 to the combined footprint areas of the 6,411 high-potential buildings yielded a total deployable rooftop area of approximately 8.48 km². Using a panel efficiency of 20%, an annual horizontal irradiance of 1,300 kWh/m²/year for Changsha, and a system performance ratio of 0.80, the estimated annual electricity generation from full deployment across this rooftop area is approximately 1,764 GWh per year. Applying the provincial grid emission factor of 0.5703 kg CO₂/kWh, the corresponding annual CO₂ reduction potential is approximately 1,006 kt (approximately 1.0 Mt) per year.

These figures represent an upper bound on what is technically deployable across the identified high-potential buildings, assuming full rooftop coverage subject to the utilisation factor. Real deployment would be lower due to structural, regulatory, ownership, and economic constraints not captured in this screening framework.

**Priority grid identification.** Grid cells were ranked by high-potential ratio. The top tier of priority zones — comprising 146 grid cells with high-potential ratios of 1.0 (i.e., all buildings within the cell exceed the q66 threshold) — represents the most spatially concentrated areas for targeted policy intervention. These priority cells are geographically concentrated in the commercial core of the urban area and are identified in the accompanying spatial output files for direct use in district planning processes.

The planning metrics confirm that the rooftop solar potential of the Changsha urban core is substantial at the aggregate scale. However, the primary contribution of this study is not the aggregate number itself, but the ability to spatially differentiate priority zones at the meso-scale — an output that is directly actionable by district-level planners without requiring the extensive data collection and computational resources associated with building-by-building engineering simulations.
