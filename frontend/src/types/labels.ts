import type { ControllerId, OperationMode, ScenarioId, ControlPhase } from "./api";

export function controllerLabel(value: ControllerId) {
  return {
    rule_based: "Conventional Rule-Based Control",
    deterministic_mpc: "Cost & Peak Optimizer",
    greenmpc_conservative: "Risk-Aware GreenMPC"
  }[value];
}

export function scenarioLabel(value: ScenarioId) {
  return {
    normal: "Normal Operations",
    cloudy: "Solar Drop",
    production_shift: "Production Demand Surge",
    combined_stress: "Combined Stress Event"
  }[value];
}

export function modeLabel(value: OperationMode) {
  return {
    manual: "Operator Approval",
    auto: "Live Autonomous Demo",
    shadow: "Recommendation Only"
  }[value];
}

export function phaseLabel(value: ControlPhase) {
  return {
    READY: "Ready",
    FORECASTING: "Forecasting six-hour demand and solar generation",
    OPTIMIZING: "Optimizing PV, BESS, DPPA, and grid dispatch",
    REVIEWING_DECISION: "Reviewing next-hour decision",
    EXECUTING: "Validating and executing one simulated hour",
    UPDATED: "Digital twin updated",
    WAITING: "Waiting for next control cycle",
    PAUSED: "Paused",
    ERROR: "Paused on error"
  }[value];
}
