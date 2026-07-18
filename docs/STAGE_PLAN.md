# Stage Plan

## Stage 0: Scope, Architecture, and Repository Bootstrap

Freeze MVP scope, module boundaries, data-provenance strategy, repository structure, typed configuration, initial tests, and documentation.

## Stage 1: Public Real-Data Acquisition and Provenance

Acquire public measured electricity profiles, Vietnam weather and irradiance data, and published tariff references. Cache raw data locally and document provenance.

## Stage 2: Hybrid Industrial-Park Dataset Construction

Select profiles, align timestamps, rescale anonymized measured profiles, derive rooftop-PV output, and build validated hourly datasets for the five scenario tenants.

## Stage 3: Digital-Twin Simulator

Implemented park state transitions, battery state, cost accounting, renewable allocation, event effects, history export, and strict action validation. Controllers remain a later-stage responsibility.

## Stage 4: AI Forecasting

Implemented chronological splits, leakage-safe features, quantile load and solar forecasts, inference interfaces, metrics, baselines, and a model registry.

## Stage 5: GreenMPC Controller

Implement the continuous linear GreenMPC control engine with expected P50/P50 mode, quantile-conservative P90/P10 mode, HIGHS solver execution, post-solve simulator validation, diagnostics, and clearly labeled current-step fallback behavior. Stage 5 does not run closed-loop benchmarks.

## Stage 6: Closed-Loop Evaluation

Run receding-horizon backtests, compare controllers, calculate KPIs, and evaluate event scenarios.

## Stage 7: Live Streamlit Demonstration

Create the offline interactive demo with session state, controls, event injection, charts, and recommendation displays.

## Stage 8: Investment Lab and Tenant Renewable Ledger

Add cloned-state investment scenarios, tenant renewable-energy allocation, CSV export, summaries, and audit-ready HTML evidence reports.

## Stage 9: Safety Hardening and Submission Package

Harden validation, logging, offline operation, failure modes, demo packaging, documentation, and challenge-submission assets.
