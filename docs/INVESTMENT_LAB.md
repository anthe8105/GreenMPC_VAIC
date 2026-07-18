# Investment Scenario Lab

Stage 8 adds an offline scenario-analysis tool to the React/FastAPI command center. It compares the approved baseline infrastructure with one proposed configuration using cloned simulator/controller runs.

## Purpose

The lab answers how rooftop PV capacity, BESS size, DPPA volume/price, and renewable targets affect realized grid import, curtailment, renewable share, operating cost, peak import, and tenant renewable allocation.

It is not a financial recommendation, supplier quotation, official renewable certificate, legal DPPA settlement tool, or actual VRG operational-data system.

## Method

Baseline and proposal runs use the same start timestamp, scenario events, controller, duration, processed dataset, forecasting resources, and MPC configuration. Candidate changes are applied only to isolated simulator/controller instances.

PV capacity uses a capacity-scaling approximation:

```text
candidate_pv_kw = baseline_pv_kw * candidate_capacity_kw / baseline_capacity_kw
```

The same weather-resource profile is used. This is not a site-layout, shading, or engineering design study.

BESS, DPPA, transformer, and renewable-target values are analysis-specific overrides. Global configuration files and Stage 6 benchmark outputs are not mutated.

## Financial Assumptions

`configs/investment.yaml` contains editable demonstration assumptions:

- PV CAPEX per kWp;
- BESS energy CAPEX per kWh;
- BESS power CAPEX per kW;
- fixed implementation cost;
- annual O&M rates;
- annual operating days;
- project life;
- terminal battery valuation prices.

Annualized savings are a linear extrapolation from the selected analysis window:

```text
annualized_savings = period_savings * annual_operating_hours / analysis_hours
```

Simple payback is shown only when incremental CAPEX and net annual savings are both positive.

## Tenant Evidence

Tenant evidence is computed from realized simulator source-level accounting. It includes direct PV, DPPA, renewable battery delivery, grid energy, achieved renewable share, target, and shortfall. Renewable battery delivery uses the simulator-tracked renewable battery inventory and is not inferred from aggregate park share.

## Exports

Completed analyses produce:

- `analysis_summary.json`
- `baseline_configuration.json`
- `proposal_configuration.json`
- `technical_metrics.csv`
- `financial_assumptions.json`
- `financial_metrics.csv`
- `tenant_hourly_ledger.csv`
- `tenant_summary.csv`
- `provenance.json`
- `manifest.json` with SHA-256 checksums

The ZIP excludes raw public datasets, model binaries, local absolute paths, unrelated Stage 6 histories, and temporary files.

## Cache Identity

Cache identity includes dataset/model fingerprints, controller/simulator version, scenario, start timestamp, duration, physical proposal values, renewable target, transformer capacity, and financial-assumption version. Partial, failed, cancelled, or duration-mismatched jobs are not accepted as completed evidence.
