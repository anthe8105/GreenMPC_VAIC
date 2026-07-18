# Project Scope

GreenMPC Twin is an AI energy digital twin for industrial-park electricity and renewable-energy management. The MVP models five scenario tenants, one aggregated rooftop-solar portfolio, one battery energy storage system, one grid connection, one DPPA renewable source, and one shared transformer constraint.

## Target Users

- Industrial-park energy managers evaluating operating decisions.
- Sustainability and procurement teams reviewing renewable-energy allocation.
- Challenge evaluators who need an offline, stable live demonstration.
- Technical reviewers who need clear provenance, controls, and module boundaries.

## MVP Capabilities

- Hourly tenant-level electricity-load data.
- Hourly Vietnam weather and solar-resource data.
- One-to-six-hour P10, P50, and P90 forecasts for load and solar.
- One-hour simulation steps with six-hour receding-horizon control.
- Rule-based control, deterministic MPC, and conservative GreenMPC.
- Runtime cloud, production-shift, and combined-stress event injection.
- Investment analysis for battery, solar, and DPPA assumptions.
- Tenant-level renewable-energy ledger.
- Offline Streamlit live demonstration.

## Non-Goals

- Reinforcement learning.
- Graph neural networks.
- Large language models as a control component.
- Multi-agent systems.
- AC optimal power flow.
- Detailed voltage or reactive-power simulation.
- Stochastic scenario trees or CVaR optimization.
- Binary MPC variables.
- Blockchain.
- Automatic official certificate issuance.
- Autonomous physical-equipment control.

These topics may be noted as future extensions only where they are clearly outside the MVP.

## Challenge Boundaries

This repository covers industrial-park electricity operations, renewable-energy purchasing, storage dispatch, forecasting, control, evaluation, and reporting. It does not cover other utility domains or non-energy challenge statements.

## Approved Terminology

- Scenario tenant.
- Public measured source data.
- Derived data.
- Rescaled data.
- Scenario assumption.
- Simulation output.
- Renewable-energy ledger.
- Audit-ready evidence report.

## Prohibited Claims

- Actual VRG operational data is used.
- Actual VRG tenant data is used.
- Actual confidential DPPA contracts are used.
- Actual VRG battery specifications are used.
- Actual VRG transformer topology is used.
- Any report produced by the demo is an official certificate.
