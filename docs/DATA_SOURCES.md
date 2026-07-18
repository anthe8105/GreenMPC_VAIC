# Data Sources

Stage 1 acquires public raw sources and provenance only. It does not select final tenant profiles, align timestamps, derive PV output, train models, simulate operations, or implement control.

Stage 2 uses these cached sources to build a processed hybrid dataset. It preserves the distinction between measured public profile shapes, satellite/model-based weather, derived PV availability, and scenario assumptions.

## UCI Electricity Load Diagrams 2011-2014

- Publisher: UCI Machine Learning Repository.
- Purpose: provide real measured anonymous electricity-consumption profile shapes for later candidate-profile analysis.
- Official source: https://archive.ics.uci.edu/dataset/321/electricityloaddiagrams20112014
- Raw format: compressed ZIP containing a large text or CSV-like load table.
- Temporal resolution: source-specific load diagram intervals over 2011-2014.
- Geographic context: Portuguese source timestamps and clients.
- License status: recorded from UCI metadata and marked for manual review where not explicit.
- Known limitations: anonymous clients, Portuguese timestamps, not industry-labeled, not Vietnamese, not VRG.
- Intended use: later candidate profile-shape source after separate Stage 2 selection and transformation.
- Prohibited interpretation: do not describe columns as electronics, semiconductor, textile, warehouse, Vietnamese, or VRG tenants.
- Citation: UCI Machine Learning Repository, ElectricityLoadDiagrams20112014.

## UCI Steel Industry Energy Consumption

- Publisher: UCI Machine Learning Repository.
- Purpose: provide a measured industrial electricity dataset that can later serve as an industrial anchor or external validation source.
- Official source: https://archive.ics.uci.edu/dataset/851/steel%2Bindustry%2Benergy%2Bconsumption
- Raw format: compressed ZIP containing the published CSV.
- Temporal resolution: as published by the source dataset.
- Geographic context: South Korean steel-industry facility.
- License status: recorded from UCI metadata and marked for manual review where not explicit.
- Known limitations: one steel-industry source, cannot represent all tenant industries, not Vietnamese, not VRG.
- Intended use: later industrial-reference source after separate Stage 2 decisions.
- Prohibited interpretation: do not relabel it as electronics, semiconductor, Vietnam, or VRG data.
- Citation: UCI Machine Learning Repository, Steel Industry Energy Consumption.

## NASA POWER Hourly Weather and Solar Resource

- Publisher: NASA POWER.
- Purpose: provide hourly solar-resource and meteorological data for configurable southern-Vietnam demonstration coordinates.
- Official source: https://power.larc.nasa.gov/docs/services/api/temporal/hourly/
- Raw format: CSV API response with NASA metadata/header preserved.
- Temporal resolution: hourly.
- Geographic context: configurable demonstration coordinates, default latitude `11.0`, longitude `106.65`.
- License status: NASA POWER access terms, recorded in source configuration.
- Known limitations: not an on-site SCADA weather sensor, spatial resolution is not plant-level, UTC retained in raw data, coordinates are assumptions.
- Intended use: later solar forecasting and PV derivation input after separate Stage 2 processing.
- Prohibited interpretation: do not present it as a physical weather station at an industrial park or actual VRG site.
- Citation: NASA POWER Project, Hourly API.

## Vietnam Retail Electricity Tariff Reference

- Publisher: Vietnam Ministry of Industry and Trade / EVN.
- Purpose: establish provenance for Vietnam electricity-tariff references.
- Official sources: https://chinhphu.vn/?docid=213617&pageid=27160 and https://en.evn.com.vn/d/en-US/news/RETAIL-ELECTRICITY-TARIFF-Decision-No-1279QD-BCT-dated-9-May-2025-of-Ministry-of-Industry-and-Trade-60-28-252
- Raw format: curated YAML metadata, with optional downloaded official source page when reachable.
- Temporal resolution: regulatory reference metadata, not a time series.
- Geographic context: Vietnam retail electricity tariff reference.
- License status: public government and EVN reference pages; usage status marked for manual review.
- Known limitations: customer category and voltage level are not selected, values are not imported into operational config, future regulatory review may be required.
- Intended use: later tariff-configuration review and citation.
- Prohibited interpretation: do not claim the tariff exactly matches a future pilot contract or silently infer an industrial-park voltage category.
- Citation: Decision No. 1279/QD-BCT dated 9 May 2025 and EVN retail-tariff reference page.
