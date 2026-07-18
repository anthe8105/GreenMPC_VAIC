export type ControllerId = "rule_based" | "deterministic_mpc" | "greenmpc_conservative";
export type ScenarioId = "normal" | "cloudy" | "production_shift" | "combined_stress";
export type OperationMode = "manual" | "auto" | "shadow";
export type ControlPhase = "READY" | "FORECASTING" | "OPTIMIZING" | "REVIEWING_DECISION" | "EXECUTING" | "UPDATED" | "WAITING" | "PAUSED" | "ERROR";

export interface CommandState {
  session_id: string;
  run_id: string;
  timestamp: string;
  status: string;
  operation_mode: string;
  controller_id: ControllerId;
  scenario_id: ScenarioId;
  compatibility_status: string;
  kpis: Record<string, number | string>;
  tenant_load_kw_by_tenant?: Record<string, number>;
  topology: { nodes: Array<Record<string, unknown>>; edges: TopologyEdge[] };
  alerts: Alert[];
  history: Array<Record<string, number | string>>;
  timings: Record<string, number | boolean>;
  completed_hours: number;
  maximum_hours: number;
  fallback_active: boolean;
  fallback_reason?: string | null;
  last_error?: string | null;
}

export interface Alert {
  severity: string;
  title?: string;
  message: string;
}

export interface TopologyEdge {
  source: string;
  target: string;
  kw: number;
  style: string;
  active: boolean;
  width?: number;
}

export interface SessionResponse {
  session_id: string;
  run_id: string;
  state: CommandState;
}

export interface ApiResponse {
  session_id: string;
  run_id: string;
  state: CommandState;
  forecast?: ForecastPayload;
  plan?: PlanPayload;
  action?: Record<string, unknown>;
  alerts: Alert[];
  history: Array<Record<string, unknown>>;
  timings: Record<string, number | boolean>;
  fallback_active: boolean;
  fallback_reason?: string | null;
  message: string;
}

export interface ForecastPayload {
  aggregate: ForecastRow[];
  load: ForecastRow[];
  solar: ForecastRow[];
  metadata: Record<string, unknown>;
}

export interface ForecastRow {
  timestamp_local: string;
  horizon_hours: number;
  series?: string;
  p10_kw: number;
  p50_kw: number;
  p90_kw: number;
  current_observed_kw?: number;
}

export interface PlanPayload {
  park_plan: PlanRow[];
  tenant_plan: Array<Record<string, unknown>>;
  recommended_action: Record<string, unknown>;
  solver: Record<string, unknown>;
  objective: Array<Record<string, unknown>>;
  decision_comparison?: Record<string, unknown>;
  fallback_active: boolean;
  fallback_reason?: string | null;
  valid_for_execution: boolean;
}

export interface PlanRow {
  timestamp_local: string;
  interval_index: number;
  pv_to_tenants_kw: number;
  dppa_import_kw: number;
  grid_import_kw: number;
  pv_to_battery_kw: number;
  dppa_to_battery_kw: number;
  battery_charge_kw: number;
  battery_discharge_kw: number;
  pv_curtailment_kw: number;
  transformer_capacity_kw: number;
  battery_soc_end: number;
}

export interface InvestmentCandidate {
  pv_capacity_kw: number;
  battery_energy_capacity_kwh: number;
  battery_power_kw: number;
  minimum_soc_fraction: number;
  initial_soc_fraction: number;
  dppa_available_kw: number;
  dppa_price_vnd_per_kwh: number;
  dppa_availability_multiplier: number;
  renewable_target_fraction: number;
  transformer_capacity_kw: number;
  terminal_inventory_valuation_vnd_per_kwh: number;
}

export interface InvestmentFinancial {
  pv_capex_vnd_per_kwp: number;
  bess_energy_capex_vnd_per_kwh: number;
  bess_power_capex_vnd_per_kw: number;
  fixed_implementation_cost_vnd: number;
  annual_pv_om_fraction: number;
  annual_bess_om_fraction: number;
  project_life_years: number;
  annual_operating_days: number;
  discount_rate: number;
  assumptions_version: string;
}

export interface InvestmentDefaults {
  baseline: InvestmentCandidate;
  proposal: InvestmentCandidate;
  financial: InvestmentFinancial;
  defaults: Record<string, number | string>;
  durations: Record<string, number>;
  valuation_prices: number[];
  disclosure: string;
}

export interface InvestmentJobStatus {
  analysis_id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress_percentage: number;
  current_phase: string;
  completed_hours: number;
  requested_hours: number;
  elapsed_seconds: number;
  eta_seconds?: number | null;
  error?: string | null;
  loaded_from_cache?: boolean;
  estimated_work_units?: number;
}

export interface InvestmentResult {
  analysis_id: string;
  scenario_id: ScenarioId;
  controller_id: ControllerId;
  duration_hours: number;
  completed_successfully: boolean;
  completed_hours: number;
  baseline_configuration: InvestmentCandidate;
  proposal_configuration: InvestmentCandidate;
  technical_metrics: Record<string, any>;
  financial_metrics: Record<string, any>;
  tenant_summary: Array<Record<string, any>>;
  evidence_zip_path: string;
  loaded_from_cache: boolean;
  runtime_seconds: number;
  assumptions: string[];
}
