"""Pydantic contracts for the GreenMPC web command center API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ControllerId = Literal["rule_based", "deterministic_mpc", "greenmpc_conservative"]
ScenarioId = Literal["normal", "cloudy", "production_shift", "combined_stress"]
OperationMode = Literal["manual", "auto", "shadow"]


class SessionCreateRequest(BaseModel):
    scenario_id: ScenarioId = "normal"
    controller_id: ControllerId = "deterministic_mpc"
    start_timestamp: str | None = None


class SessionResetRequest(SessionCreateRequest):
    run_id: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    run_id: str
    state: dict[str, Any]


class RequestEnvelope(BaseModel):
    request_id: str
    run_id: str
    expected_timestamp: str


class ForecastRequest(RequestEnvelope):
    pass


class PlanRequest(RequestEnvelope):
    controller_id: ControllerId | None = None
    generate_forecast_if_missing: bool = True


class ExecuteRequest(RequestEnvelope):
    pass


class ControlCycleRequest(RequestEnvelope):
    operation_mode: OperationMode
    controller_id: ControllerId | None = None


class ApiResponse(BaseModel):
    session_id: str | None = None
    run_id: str | None = None
    state: dict[str, Any] | None = None
    forecast: dict[str, Any] | None = None
    plan: dict[str, Any] | None = None
    action: dict[str, Any] | None = None
    alerts: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    timings: dict[str, Any] = Field(default_factory=dict)
    fallback_active: bool = False
    fallback_reason: str | None = None
    message: str = "ok"


class BenchmarkResponse(BaseModel):
    valuation_price_vnd_per_kwh: float
    rows: list[dict[str, Any]]
    explanation: str


class ProvenanceResponse(BaseModel):
    data: dict[str, Any]
