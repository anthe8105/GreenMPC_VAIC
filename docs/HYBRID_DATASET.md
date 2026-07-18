# Hybrid Dataset

The industrial-park dataset combines measured public load-profile shapes with Vietnam weather data and transparent scenario assumptions.

Stage 2 outputs are analysis-ready inputs for later forecasting, simulation, control, reporting, and UI stages. They are not simulation outputs and contain no dispatch decisions.

## Outputs

- `data/processed/tenant_hourly.csv`: five scenario tenant rows per Vietnam-local hour.
- `data/processed/park_hourly.csv`: park-level aggregation and shared weather, PV, tariff, DPPA context.
- `data/processed/selected_tenant_profiles.csv`: deterministic anonymous-client selection rationale.
- `data/processed/candidate_profile_metrics.csv`: scale-independent anonymous-client metrics.
- `data/processed/scenario_events.csv`: synthetic event catalog, not applied to the baseline.
- `data/processed/steel_hourly_reference.csv`: separate South Korean steel-industry reference.
- `data/processed/dataset_manifest.json`: build manifest, fingerprints, assumptions, and warnings.
- `data/processed/data_quality_report.json`: validation and quality summary.
- `data/provenance/processed_lineage.json`: field-level processed lineage.

## Classification

- Real measured shapes: UCI anonymous electricity clients and UCI steel reference data.
- Satellite/model-based data: NASA POWER hourly solar and meteorological variables.
- Derived data: hourly aggregation, rescaled tenant loads, park load, local timestamps, tariff labels, and PV availability.
- Scenario assumptions: tenant labels, target sizes, tariff schedule, DPPA availability/price, transformer capacity, and events.
- Simulation outputs: none in Stage 2.

## Prohibited Interpretations

The processed dataset is not actual VRG data, not co-located source measurements, and not a confirmed pilot tariff or DPPA contract. Derived PV is not measured inverter output. Tenant industries are scenario labels only.
