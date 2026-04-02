# Discussion

## 5. Discussion

### 5.1 Planning Support Value of the Screening Framework

This study demonstrates that a rapid, open-data screening framework can produce spatially differentiated, planning-actionable assessments of rooftop solar potential at the urban scale without requiring the lidar surveys, detailed radiation simulations, or commercial datasets that characterise high-fidelity engineering models. The framework delivers three types of output directly useful to urban planners and policymakers.

First, the building-level high-potential classification (6,411 high-potential buildings out of 18,855) provides a prioritised list of candidate structures for deeper assessment or targeted incentive programmes. This list can be delivered to building owners, local authorities, or solar developers as a first-pass screening product, directing attention toward the buildings most likely to offer favourable economics and technical conditions for rooftop deployment.

Second, the grid-level spatial aggregation at 500 m resolution converts building-level heterogeneity into a meso-scale map of solar opportunity that aligns naturally with the spatial resolution of district planning instruments, urban master plans, and neighbourhood-level subsidy schemes. Planners working at the district or sub-district scale can directly overlay the high-potential ratio map (Figure 5) with land-use zoning maps, infrastructure plans, or administrative boundaries to identify spatial priorities without additional data processing.

Third, the planning metrics estimated in Section 4.6 — 8.48 km² of deployable rooftop area, 1,764 GWh/year of generation potential, and approximately 1,006 kt CO₂/year of reduction potential — provide order-of-magnitude anchors for urban climate policy targets. Chinese cities are under increasing pressure to incorporate distributed renewable energy targets into their urban energy plans as part of the national carbon neutrality agenda. A rapid, reproducible framework that translates building stock characteristics into aggregate energy and emissions figures at the neighbourhood scale fills a genuine gap in the planning toolkit.

### 5.2 Contribution Under Low-Data Conditions

A central motivation for this study is the observation that the data environments available to planners in Chinese cities — particularly for older urban cores and secondary cities — frequently preclude the use of high-fidelity solar simulation approaches. Lidar point clouds, cadastral databases with verified floor counts, measured roof tilt and material data, and high-resolution solar radiation maps with obstruction correction are either unavailable, restricted, costly, or prohibitively time-consuming to compile at the full urban scale.

This framework demonstrates that meaningful spatial differentiation of rooftop solar potential is achievable using only freely available OSM building footprint data, a hierarchical height proxy inference procedure, and standard geospatial processing operations. The entire workflow runs on a standard laptop in under one hour and requires no licensed software, no field survey data, and no institutional data-sharing agreements.

The approach is therefore positioned as a complementary tool that operates at the beginning of the urban solar planning decision chain. It answers the question "where should we look first?" rather than "what precisely will a given system generate?" — a distinction that is fundamental to the responsible communication of uncertainty in planning contexts. The rapid screening step enables planners to prioritise their more resource-intensive data collection activities (site surveys, structural assessments, irradiance measurements) toward the highest-opportunity buildings and zones, rather than applying them uniformly across the full building stock.

The reproducibility of the framework is a further contribution. All data sources are open, all processing steps are documented and scripted, and all parameters are externally configurable. The pipeline can be re-executed with different input parameters (study area boundary, grid size, threshold level, height assumptions) without modifying source code. This supports both methodological transparency and adaptation to other cities or study areas where OSM data coverage is adequate.

### 5.3 Distinction from Engineering-Grade Simulation

It is important to situate this framework clearly relative to the more physically rigorous solar potential assessment methods found in the literature. High-fidelity approaches, including 3D city model-based irradiance simulation (e.g., using CitySim or RADIANCE), lidar-derived roof plane extraction with tilt and aspect correction, and pvlib-based yield modelling with hourly meteorological inputs, are capable of producing building-specific annual yield estimates with uncertainties of the order of ±5–15%. These methods are appropriate for project feasibility studies, grid integration planning, and financial modelling.

The framework presented here does not produce yield estimates at individual buildings. The solar potential score is a dimensionless composite of structural proxies (footprint area and height) scaled by functional type, and it captures relative differences in solar opportunity rather than absolute physical quantities. The planning metrics reported in Section 4.6 are aggregate order-of-magnitude estimates derived from simplified assumptions about panel efficiency, irradiance, and utilisation; they are appropriate for strategic planning purposes but not for project-level investment decisions.

This distinction is not a limitation of the current framework relative to its design purpose — it is a deliberate design choice. A rapid screening tool that is transparent about its limitations and communicates relative rather than absolute outputs is more appropriate for the planning context than a more precise model whose input data requirements cannot be met without substantial additional investment. The appropriate comparison is not between this framework and engineering simulation, but between this framework and the absence of any systematic spatial prioritisation — a situation that remains common in many Chinese cities.

### 5.4 Interpretation of Sensitivity Analysis Results

The three sensitivity analyses conducted in this study provide empirical evidence for the robustness of the framework's outputs to the primary sources of methodological uncertainty.

The grid size sensitivity analysis (Section 4.5.1) shows that the mean grid-level solar score varies by less than two points across a four-fold range of spatial resolution (250 m to 1000 m). The high-potential ratio also remains broadly consistent across resolutions. This finding confirms that the spatial signal captured by the framework — the concentration of high-scoring buildings in commercially dominated central areas — is a genuine feature of the urban building stock rather than an artefact of the chosen grid resolution. Planners can apply alternative grid sizes appropriate to their specific planning instruments without materially changing the conclusions.

The threshold sensitivity analysis (Section 4.5.2) reveals smooth, monotonic behaviour of all key metrics across the full range of tested quantile thresholds. The number of high-potential buildings decreases by approximately 150 buildings per 5-percentile increase in the threshold. The number of grid cells containing at least one high-potential building remains nearly constant at 560–630 across all tested thresholds, indicating that high-potential buildings are spatially distributed broadly even when the definition of "high" is made more stringent. This robustness to threshold choice is a desirable property: it means that the spatial pattern of priority zones is stable even if the precise definition of "high potential" is adjusted in response to policy objectives (e.g., targeting the top 20% rather than the top 34% of buildings).

The height proxy perturbation analysis (Section 4.5.3) is particularly important given that height estimation is the most uncertain step in the pipeline. The result — that a ±30% perturbation of all height values produces a mean score change of less than 0.5 points and a high-potential count change of less than ±6% — demonstrates that the composite score is dominated by the footprint area component, which is directly measured from OSM polygon geometry and carries no estimation uncertainty. Height proxy error, while real and unverifiable for the majority of buildings, does not substantially alter the relative ranking of buildings or the spatial pattern of priority zones. This finding provides an empirical basis for confidence in the screening results even under the acknowledged limitations of the height proxy method.

Collectively, the sensitivity analyses support the claim that the framework produces spatially robust outputs that are not dependent on precise values of any single uncertain parameter. This robustness is a key property for a tool intended to support planning decisions under data scarcity.

### 5.5 Application Prospects and Planning Integration

The planning metrics and priority grid outputs of this framework are designed to integrate directly into several types of urban planning and policy instruments currently active in China.

**District-level solar development plans.** Several Chinese cities have introduced district-specific rooftop solar targets as part of their post-2020 urban energy transition programmes. The priority grid map produced by this framework provides a spatial foundation for disaggregating such targets by neighbourhood, directing subsidy allocation, and sequencing development zones.

**Building stock audit prioritisation.** Physical solar audit surveys, structural assessments, and detailed engineering studies are resource-intensive. The high-potential building list generated by this framework can directly inform the selection of candidate buildings for audit, replacing ad hoc or anecdotally based selection with a systematic, data-driven prioritisation.

**Urban master plan revisions.** As Chinese cities revise their urban master plans in compliance with the national carbon peak and carbon neutrality timelines, rooftop solar potential maps at the grid level can inform decisions about building height regulations, setback requirements, and urban form standards that influence solar accessibility in new development areas.

**Community-level renewable energy programmes.** The 500 m grid scale aligns well with the spatial resolution of Chinese residential committee (居委会) and community governance units. High-potential ratio maps at this scale can support community-level engagement and awareness campaigns.

The aggregate generation potential estimated in this study (1,764 GWh/year) corresponds to approximately the annual electricity consumption of several hundred thousand urban households in Changsha (based on an average annual residential electricity consumption of approximately 3,000–4,000 kWh per household for a Hunan context). While this comparison is illustrative rather than precise, it demonstrates that the rooftop solar resource of the Changsha urban core is substantive relative to local energy demand — a finding that strengthens the policy case for systematic deployment.

### 5.6 Limitations

This study has several limitations that should be acknowledged and that inform the interpretation of results.

**OSM data completeness.** OpenStreetMap coverage of Chinese cities is extensive but uneven. Building footprint completeness is highest in dense urban areas and lower in peripheral zones; attribute completeness (height, levels, building type) varies considerably across the dataset. The urban core extraction step reduces but does not eliminate the influence of attribute incompleteness, since even within the dense core a significant fraction of buildings rely on type-based or fallback-default height estimates.

**Absence of radiation modelling.** The composite score does not incorporate any information about solar irradiance, roof tilt, azimuth, or inter-building shading. Two buildings with identical footprint areas and height proxies in the same functional category will receive the same solar potential score regardless of their orientation, aspect, or shadowing exposure. This means that the framework cannot distinguish between a south-facing, unobstructed flat-roof building and an identically sized building that is heavily shadowed by neighbouring high-rises.

**Static snapshot.** The analysis is based on the OSM building dataset as downloaded at a single point in time. Urban form in rapidly developing Chinese cities changes significantly over the planning horizon of a solar deployment programme. The framework would need to be re-executed periodically using updated OSM data to remain current.

**Planning metric assumptions.** The planning metric estimates in Section 4.6 rest on simplified assumptions about utilisation factor, panel efficiency, irradiance, and performance ratio. In particular, the horizontal irradiance value of 1,300 kWh/m²/year is a long-term average that does not account for roof tilt, azimuth, or local climate variability. The emission factor is a national average that does not reflect the specific generation mix of the Hunan provincial grid. These simplifications mean that the aggregate figures should be treated as order-of-magnitude planning references rather than bankable yield forecasts.

**Absence of external validation.** The screening results have not been validated against a more detailed benchmark method (e.g., pvlib-based building-by-building simulation for a sample sub-area). Validation was identified as a priority for future work but was not completed within the current study due to data availability constraints on high-resolution radiation and roof geometry data for the validation area.

### 5.7 Future Work

Several directions for future work emerge directly from the limitations identified above.

**External validation against a high-fidelity benchmark.** A natural next step is to select a small sub-area of the Changsha urban core (2–5 km², approximately 50–200 buildings) for detailed pvlib-based yield simulation using ERA5 hourly irradiance data and available OSM roof geometry. Comparison of the rapid-screening building rankings with the pvlib-derived rankings (via Spearman rank correlation) would provide a quantitative estimate of the screening accuracy and inform future refinements to the composite score weights.

**Incorporation of solar radiation and shading data.** The composite score could be enriched by incorporating global horizontal irradiance data at the building centroid (available from ERA5 or PVGIS at 1–5 km resolution) and a simplified urban shading correction derived from building height and inter-building spacing estimates. This would move the framework closer to a radiation-informed screening approach without requiring full 3D simulation.

**Adaptation to other Chinese cities.** The methodology is designed to be generalisable to any city with adequate OSM building footprint coverage. Applying the framework to a set of Chinese cities at different scales and climate zones would demonstrate the transferability of the approach and enable comparative analysis of urban solar potential across the Chinese urban system.

**Dynamic updating and monitoring.** Integrating the pipeline with an automated OSM data refresh and executing it on a regular schedule (e.g., annually) would enable tracking of the changing solar potential landscape as urban form evolves. This would be particularly valuable in rapidly urbanising secondary cities where the building stock is changing substantially over the planning horizon.

**Integration with economic and policy modelling.** The physical screening outputs of this framework could be linked to simplified economic models of rooftop PV adoption to produce spatial maps of expected deployment rates under alternative subsidy and regulatory scenarios. Such integration would make the framework directly useful for policy design and ex-ante evaluation.

### 5.8 Summary

This study presents and demonstrates a reproducible, open-data rapid screening framework for urban rooftop solar potential assessment under low-data conditions. Applied to the Changsha urban core, the framework identifies 6,411 high-potential buildings out of 18,855 (34.0%), estimates a deployable rooftop area of 8.48 km², and projects aggregate generation and CO₂ reduction potentials of 1,764 GWh/year and 1,006 kt/year, respectively. Systematic sensitivity analyses confirm that these outputs are robust to reasonable variations in grid resolution, classification threshold, and height proxy uncertainty. The framework is transparently limited in physical accuracy but is designed to deliver actionable spatial intelligence to urban planners operating under the data constraints that characterise the majority of Chinese cities and many urban contexts globally. The methodological contribution is not a more accurate model of any one city, but a more accessible, reproducible, and planning-aligned approach to a problem that affects many cities simultaneously.
