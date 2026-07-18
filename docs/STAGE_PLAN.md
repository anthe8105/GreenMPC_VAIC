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

Run receding-horizon benchmarks for `rule_based`, `deterministic_mpc`, and `greenmpc_conservative`, calculate realized KPIs from simulator histories, and evaluate normal plus synthetic stress scenarios. Stage 6 does not implement the Streamlit Control Room.

## Stage 7: Live Control Room

Implemented the offline Live Control Room. The primary competition interface is a React + FastAPI industrial command center, while Streamlit remains available as a technical fallback. Stage 7 includes cached resources, isolated mutable sessions, deterministic reset, Manual Approval, bounded Auto Pilot Demo, Shadow Mode, forecast/replan/execute workflow, controller selection, scenario events, current KPIs, topology, plan diagnostics, read-only benchmark evidence, terminal inventory-adjusted cost diagnostics, and provenance disclosures. Stage 7 does not implement investment simulation or final tenant reports.

## Stage 8: Investment Lab and Tenant Renewable Ledger

Add cloned-state investment scenarios, tenant renewable-energy allocation, CSV export, summaries, and audit-ready HTML evidence reports.

## Stage 9: Safety Hardening and Submission Package

Harden validation, logging, offline operation, failure modes, demo packaging, documentation, and challenge-submission assets.
