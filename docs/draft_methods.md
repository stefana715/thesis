# Methods

## 3. Methodology

This study presents a rapid, open-data screening framework for assessing rooftop solar potential at the urban scale. The framework is explicitly designed for low-data conditions, relying entirely on publicly available geospatial data and reproducible computational tools. It is intended as a planning-support instrument rather than an engineering simulation: the objective is to reveal relative spatial differences in baseline solar suitability across the Changsha urban core, not to predict precise photovoltaic yields at individual buildings.

The pipeline comprises six sequential stages: (1) open-data acquisition, (2) building height proxy construction, (3) urban core extraction, (4) building-level baseline solar scoring, (5) high-potential classification, and (6) grid-level spatial aggregation. Each stage is implemented as a modular Python script, with parameters stored in configuration files to ensure reproducibility. All intermediate and final outputs are versioned and stored in a structured directory hierarchy. Figure 8 illustrates the complete workflow.

### 3.1 Open-Data Acquisition

Building footprints for Changsha municipality were obtained from OpenStreetMap (OSM) via the `osmnx` Python library (Boeing, 2017). OSM provides crowd-sourced, freely available building geometry data that, while incomplete in attribute richness, offers sufficient spatial coverage for a first-pass urban screening exercise. The raw dataset comprised polygon geometries with associated attribute fields, including `building` (functional type tag), `height` (direct height measurement where tagged), and `building:levels` (number of floors where tagged).

All data were retrieved programmatically using the administrative boundary of Changsha as the spatial query extent. The raw building dataset was stored in GeoJSON format using the WGS84 geographic coordinate reference system (EPSG:4326). No commercial or restricted datasets were used at any stage of this study, ensuring that the workflow can be replicated by any researcher with internet access and standard open-source software.

### 3.2 Building Height Proxy Construction

Direct height measurements in OSM are sparse and inconsistently tagged. To overcome this limitation, a hierarchical height proxy inference procedure was applied to every building in the dataset.

The inference followed a priority cascade:
1. **Raw height tag**: If the `height` field contained a parseable numeric value greater than zero, that value was used directly as the building height proxy (in metres).
2. **Floor count tag**: If the `building:levels` field contained a parseable positive integer, the height was estimated by multiplying the floor count by a category-specific floor height assumption: 3.0 m per floor for residential buildings, 3.5 m per floor for commercial buildings, and 3.2 m per floor for buildings of mixed or unknown type.
3. **Type-based default**: If neither height nor floor count was available, a type-specific default was applied: 9.0 m (three residential floors) for residential buildings and 10.5 m (three commercial floors) for commercial buildings.
4. **Fallback default**: For buildings whose type could not be determined, a fallback default of 10.0 m was assigned.

Building functional type was inferred from the OSM `building` tag value. Tags belonging to the set {residential, house, apartments, detached, semidetached\_house, terrace, hut, dormitory, bungalow, farm, cabin} were classified as residential. Tags belonging to the set {commercial, retail, office, hotel, industrial, warehouse, supermarket, kiosk, mall, shop, hospital, school, college, university, public, government, civic, transportation, station, terminal} were classified as commercial. All other tags, or the absence of a recognisable tag, were classified as mixed\_unknown.

This proxy construction strategy acknowledges that the resulting height values are estimates rather than observations. The sensitivity of downstream results to height proxy uncertainty was assessed explicitly in Section 3.6.3. The transparency of the inference cascade means that the limitations and assumptions of the proxy are fully auditable.

### 3.3 Urban Core Extraction

The full Changsha municipal building dataset encompasses a large administrative area that includes extensive peri-urban and rural zones. These peripheral zones have lower building density, greater attribute incompleteness, and weaker relevance to the planning questions of interest. To focus the analysis on the most policy-relevant area, an automated urban core extraction procedure was applied.

The extraction algorithm operates as follows. Building centroid coordinates were calculated from footprint polygons. A regular 1 km × 1 km grid was overlaid on the full study area, and the number of building centroids falling within each grid cell was computed. Grid cells with building counts at or above the 75th percentile of all non-empty cells (subject to a minimum threshold of 20 buildings per cell) were designated as dense cells. The dense cells were dissolved into a contiguous polygon, from which the largest connected component was retained. The resulting boundary was smoothed by applying a positive buffer of 250 m followed by a negative buffer of 250 m (a morphological closing operation), eliminating narrow peninsulas and small gaps. Finally, the smoothed boundary was clipped to the full Changsha administrative boundary to ensure spatial validity.

All buildings whose footprint centroids fell within the resulting urban core boundary were retained for subsequent analysis. This filtering step reduced the dataset from 33,374 buildings across the full municipal extent to 18,855 buildings (56.50% retention rate) concentrated in the dense urban core. The extracted urban core encompasses the central districts of Changsha, where building density, commercial activity, and rooftop solar deployment potential are highest. Figure 1 illustrates the study area and the extracted urban core boundary.

### 3.4 Building-Level Baseline Solar Scoring

A composite solar potential score was calculated for each building in the urban core dataset. The score combines three building-level attributes: footprint area, height proxy, and functional category. These attributes serve as structural proxies for rooftop solar opportunity in the absence of radiation simulations, lidar data, or shadow modelling.

**Step 1: Feature computation.** Building footprint areas were computed in square metres by projecting geometries to the local UTM coordinate reference system prior to area calculation, then converting back to WGS84 for storage. Log-transformed values of footprint area and height proxy were computed to compress the right-skewed distributions characteristic of urban building datasets:

```
log_area  = log(1 + footprint_area_m²)
log_height = log(1 + height_proxy_m)
```

**Step 2: Min-max normalisation.** Both log-transformed features were normalised to the [0, 1] interval across the full urban core building set:

```
area_score   = (log_area  − min) / (max − min)
height_score = (log_height − min) / (max − min)
```

**Step 3: Weighted combination.** A linear combination of the two normalised scores was computed using empirically motivated weights that reflect the greater relevance of roof area to PV capacity:

```
base_score = 0.65 × area_score + 0.35 × height_score
```

**Step 4: Category adjustment.** A multiplicative category factor was applied to reflect broad differences in likely solar suitability across building types. Commercial buildings received a factor of 1.10, acknowledging their larger flat-roof proportions and lower residential shading concerns. Residential buildings received a factor of 1.00 (no adjustment). Mixed or unknown buildings received a factor of 0.95, reflecting greater attribute uncertainty.

**Step 5: Final score.** The solar potential score was computed and clipped to the [0, 100] range:

```
solar_potential_score = clip(base_score × category_factor × 100, 0, 100)
```

This composite score is explicitly a structural proxy for relative solar opportunity. It does not incorporate solar radiation, shading, panel tilt, or system configuration. Its utility lies in enabling rapid spatial differentiation and prioritisation across large building stocks in the absence of detailed physical data.

### 3.5 High-Potential Classification

To support planning-oriented decision-making, each building was classified into one of three solar potential tiers — low, medium, and high — based on quantile thresholds applied to the composite score distribution.

Two thresholds were used: the 33rd percentile (q33) and the 66th percentile (q66) of the urban core score distribution. Buildings scoring at or below q33 were classified as low potential; those between q33 and q66 were classified as medium; and those above q66 were classified as high potential. This equal-thirds partitioning provides a transparent, data-driven, and threshold-free classification that is readily replicable and interpretable by urban planners.

The computed thresholds were: q33 = 41.797 and q66 = 45.513. These values bracket the central mass of the score distribution and were stable across the sensitivity analyses described in Section 3.6.

The high-potential classification (q66 cut-off) identifies the upper third of the urban core building stock as priority candidates for rooftop solar deployment. This definition is deliberately conservative: requiring a building to exceed the 66th percentile score means that only those buildings combining relatively large footprints, taller height proxies, and advantageous functional categories are flagged, thereby reducing the risk of prioritising structurally marginal targets.

### 3.6 Grid-Level Spatial Aggregation

Building-level results were aggregated to a regular 500 m × 500 m grid to support meso-scale spatial analysis and planning application. Grid-level indicators are better suited to neighbourhood or district planning instruments than individual building scores, and they are robust to local attribute noise in the building-level data.

A regular grid of 500 m cells was constructed over the bounding box of the urban core building dataset, using the projected UTM coordinate system. Building centroids were assigned to grid cells via a spatial join. For each occupied grid cell, the following metrics were computed: mean solar potential score, high-potential building count, total building count, high-potential ratio (high-potential count divided by total count), total footprint area, mean height proxy, building density per km², and footprint density per km².

The 500 m cell size was selected to balance spatial resolution (sufficient to distinguish neighbourhood-scale heterogeneity) against statistical stability (sufficient buildings per cell to produce robust averages). The sensitivity of grid-level results to cell size is assessed in Section 3.6.1.

### 3.6.1 Grid Size Sensitivity Analysis

To evaluate the robustness of grid-level results to the choice of spatial resolution, the aggregation was repeated using four alternative cell sizes: 250 m, 500 m, 750 m, and 1000 m. For each configuration, the number of total and occupied grid cells, mean solar score distribution, and high-potential ratio distribution were recorded. Results are compared in Figure 6.

### 3.6.2 Classification Threshold Sensitivity Analysis

To assess the sensitivity of high-potential building counts to the choice of classification threshold, the q66 cut-off was varied systematically across seven quantile levels: q50, q55, q60, q66, q70, q75, and q80. For each threshold, the number and fraction of high-potential buildings, and the mean grid-level high-potential ratio, were computed. Results are summarised in Figure 7.

### 3.6.3 Height Proxy Perturbation Analysis

To evaluate the sensitivity of the solar potential score and high-potential classification to errors in the height proxy, a systematic perturbation analysis was conducted. The height proxy values for all buildings were multiplied by scaling factors of 0.70, 0.80, 0.90, 1.00, 1.10, 1.20, and 1.30 (corresponding to perturbations of −30%, −20%, −10%, 0%, +10%, +20%, +30% relative to the baseline). For each perturbation level, the solar scoring and high-potential classification pipeline was re-run in full. The resulting mean score, median score, and high-potential building count were compared against the unperturbed baseline.

### 3.7 Planning Metrics Estimation

To translate the screening results into actionable planning indicators, a set of first-order planning metrics was derived from the high-potential building subset. These metrics provide order-of-magnitude estimates suitable for strategic planning purposes; they are not engineering-grade yield forecasts.

**Deployable rooftop area**: The footprint area of each high-potential building was multiplied by a utilisation factor of 0.65 to account for rooftop obstacles (HVAC equipment, elevator shafts, parapets, and setback requirements). This conservative factor is consistent with values reported in the urban rooftop PV literature for Chinese cities (e.g., 0.60–0.70).

**Annual electricity generation**: Deployable area was multiplied by a panel efficiency of 20%, the annual horizontal irradiance for Changsha (approximately 1,300 kWh/m²/year, derived from long-term ERA5 reanalysis data), and a system performance ratio of 0.80:

```
Annual generation (kWh) = deployable_area_m² × 0.20 × 1,300 × 0.80
```

**CO₂ reduction**: Annual generation was multiplied by the provincial grid emission factor of 0.5703 kg CO₂/kWh (China's national average emission factor for 2022, sourced from the Ministry of Ecology and Environment):

```
Annual CO₂ reduction (t) = annual_generation_kWh × 0.5703 / 1,000
```

**Priority grid identification**: Grid cells were ranked by their high-potential ratio. The top-ranked cells (high-potential ratio = 1.0) were designated as tier-1 priority zones for targeted deployment policy.

All planning metric calculations were performed at the individual building level and subsequently aggregated. The assumptions embedded in these calculations are acknowledged as simplifications; their purpose is to provide a planning-relevant order of magnitude, not a bankable energy yield.

### 3.8 Software and Reproducibility

The entire workflow was implemented in Python 3.x using the following open-source libraries: `osmnx` (OSM data retrieval), `geopandas` and `shapely` (geospatial processing), `pyproj` (coordinate reference system management), `pandas` and `numpy` (tabular data handling), and `matplotlib` (visualisation). All scripts are parameterised through YAML configuration files and follow a modular, single-responsibility design. Intermediate outputs are persisted to disk at each pipeline stage, enabling inspection and partial re-execution. The complete codebase is archived and publicly available to support replication of all results reported in this study.
