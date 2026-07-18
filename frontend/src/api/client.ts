import type { ApiResponse, ControllerId, OperationMode, ScenarioId, SessionResponse } from "../types/api";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export async function createSession(scenario_id: ScenarioId, controller_id: ControllerId): Promise<SessionResponse> {
  return post("/api/v1/sessions", { scenario_id, controller_id });
}

export async function resetSession(sessionId: string, scenario_id: ScenarioId, controller_id: ControllerId): Promise<SessionResponse> {
  return post(`/api/v1/sessions/${sessionId}/reset`, { scenario_id, controller_id });
}

export async function getState(sessionId: string): Promise<ApiResponse> {
  return get(`/api/v1/sessions/${sessionId}/state`);
}

export async function forecast(sessionId: string, runId: string, timestamp: string, requestId: string): Promise<ApiResponse> {
  return post(`/api/v1/sessions/${sessionId}/forecast`, envelope(runId, timestamp, requestId));
}

export async function plan(sessionId: string, runId: string, timestamp: string, requestId: string, controllerId: ControllerId): Promise<ApiResponse> {
  return post(`/api/v1/sessions/${sessionId}/plan`, { ...envelope(runId, timestamp, requestId), controller_id: controllerId, generate_forecast_if_missing: true });
}

export async function execute(sessionId: string, runId: string, timestamp: string, requestId: string): Promise<ApiResponse> {
  return post(`/api/v1/sessions/${sessionId}/execute`, envelope(runId, timestamp, requestId));
}

export async function controlCycle(
  sessionId: string,
  runId: string,
  timestamp: string,
  requestId: string,
  operationMode: OperationMode,
  controllerId: ControllerId
): Promise<ApiResponse> {
  return post(`/api/v1/sessions/${sessionId}/control-cycle`, {
    ...envelope(runId, timestamp, requestId),
    operation_mode: operationMode,
    controller_id: controllerId
  });
}

export async function loadBenchmark(valuationPrice: number): Promise<Record<string, unknown>> {
  return get(`/api/v1/benchmark?valuation_price_vnd_per_kwh=${valuationPrice}`);
}

export async function loadProvenance(): Promise<Record<string, unknown>> {
  return get("/api/v1/provenance");
}

function envelope(run_id: string, expected_timestamp: string, request_id: string) {
  return { run_id, expected_timestamp, request_id };
}

async function get(path: string) {
  const response = await fetch(`${API_BASE}${path}`);
  return parse(response);
}

async function post(path: string, body: unknown) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  return parse(response);
}

async function parse(response: Response) {
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data?.detail?.message ?? data?.detail ?? response.statusText);
  }
  return data;
}
