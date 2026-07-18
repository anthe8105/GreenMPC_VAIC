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
