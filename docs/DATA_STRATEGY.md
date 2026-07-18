# Data Strategy

GreenMPC Twin uses a hybrid real-data and synthetic-assumption strategy. The final live demo must run offline using cached local data and configuration files.

## Public Data Categories

- Public measured electricity-consumption profiles.
- Hourly Vietnam weather and irradiance data.
- Published electricity-tariff reference data.

## Data Categories

- Measured source data: externally sourced records retained with source URL or citation, retrieval timestamp, license or usage notes, time zone, units, and raw-file checksum where practical.
- Derived data: transformations from measured records, including rooftop-PV output from irradiance, timestamp alignment, feature tables, and park-level aggregation.
- Rescaled data: measured profiles scaled to scenario industrial-park capacities, with scale factors and rationale recorded.
- Scenario assumptions: tenant industry labels, production schedules, battery parameters, transformer capacity, DPPA price and capacity, event scenarios, and renewable targets.
- Simulation outputs: controller actions, state transitions, costs, renewable-energy allocation records, ledger rows, and evaluation summaries.

## Provenance Requirements

Every dataset used after Stage 0 must be traceable to one of the categories above. Processed files must record their upstream inputs, transformation code version, units, time zone, and creation timestamp. The demo must distinguish externally sourced facts from assumptions in documentation and UI copy.

## Offline Caching

All data needed for the live demonstration must be available from local files before the demo starts. No online service, cloud database, or network fetch may be required during live operation.

## Stage 1 Raw Source Foundation

Stage 1 adds a separate source registry in `configs/data_sources.yaml` so acquisition settings do not mix with operational demo assumptions in `configs/demo.yaml`. Raw public sources are cached below `data/raw/`, while reviewable provenance records are stored below `data/provenance/`.

Stage 1 validation is structural. It confirms file existence, ZIP integrity, safe extraction where permitted, small in-archive samples, expected NASA parameters, raw UTC retention, and tariff metadata guardrails. It does not perform full statistical validation, profile selection, timestamp alignment, resampling, scaling, PV derivation, forecasting, simulation, or control.

The UCI Electricity Load Diagrams archive is intentionally not extracted by default because it is large. Validation reads a small sample directly from the ZIP.

## Stage 2 Hybrid Dataset

Stage 2 constructs hourly processed datasets from cached raw files only. It reads the UCI load archive directly from ZIP, analyzes anonymous profile shapes, selects five source clients deterministically, rescales them to scenario tenant sizes, processes NASA POWER weather in UTC and Vietnam-local time, derives PV availability with a unit-aware formula, adds demo tariff and DPPA assumptions, and writes a separate synthetic event catalog.

NASA POWER `ALLSKY_SFC_SW_DWN` is preserved as a raw `Wh/m^2` field in the cached CSV. The processed PV derivation normalizes this hourly irradiation to a one-sun equivalent before applying installed capacity and performance ratio. This remains derived availability, not measured inverter output.

A pre-Stage 5 correction fixed an earlier unit parser defect that had treated `Wh/m^2` as `kWh/m^2` and caused excessive capacity clipping. The correction history is documented in `docs/PV_DERIVATION.md`.

Stage 2 does not implement forecasting features, train models, simulate dispatch, optimize controls, allocate renewable energy, or calculate investment results.

## VRG Data Disclaimer

The Stage 0 project does not use actual VRG operational records, actual VRG tenant records, actual confidential DPPA contracts, actual VRG battery specifications, or actual VRG transformer topology.
