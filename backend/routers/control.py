"""Forecast, planning, execution, and control-cycle routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.dependencies import get_resources
from backend.schemas import ApiResponse, ControlCycleRequest, ExecuteRequest, ForecastRequest, PlanRequest
from backend.services import (
    build_plan,
    cache_response,
    execute_current_action,
    generate_forecast,
    run_control_cycle,
    serialize_forecast,
    serialize_plan,
    serialize_state,
    validate_envelope,
)
from backend.session_store import STORE
from greenmpc.ui.state import ControlRoomResources

router = APIRouter(prefix="/api/v1/sessions/{session_id}", tags=["control"])


@router.post("/forecast", response_model=ApiResponse)
def forecast(session_id: str, payload: ForecastRequest, resources: ControlRoomResources = Depends(get_resources)) -> ApiResponse:
    stored = _stored(session_id)
    with stored.lock:
        cached = validate_envelope(stored, payload.request_id, payload.run_id, payload.expected_timestamp)
        if cached:
            return ApiResponse(**cached)
        forecast_payload = generate_forecast(stored, resources)
        response = _response(stored, forecast=forecast_payload, message="forecast generated")
        return ApiResponse(**cache_response(stored, payload.request_id, response))


@router.post("/plan", response_model=ApiResponse)
def plan(session_id: str, payload: PlanRequest, resources: ControlRoomResources = Depends(get_resources)) -> ApiResponse:
    stored = _stored(session_id)
    with stored.lock:
        cached = validate_envelope(stored, payload.request_id, payload.run_id, payload.expected_timestamp)
        if cached:
            return ApiResponse(**cached)
        plan_payload = build_plan(stored, resources, payload.controller_id, payload.generate_forecast_if_missing)
        response = _response(stored, forecast=serialize_forecast(stored.live), plan=plan_payload, action=plan_payload.get("recommended_action"), message="plan generated")
        return ApiResponse(**cache_response(stored, payload.request_id, response))


@router.post("/execute", response_model=ApiResponse)
def execute(session_id: str, payload: ExecuteRequest) -> ApiResponse:
    stored = _stored(session_id)
    with stored.lock:
        cached = validate_envelope(stored, payload.request_id, payload.run_id, payload.expected_timestamp)
        if cached:
            return ApiResponse(**cached)
        execution = execute_current_action(stored)
        response = _response(stored, message=f"executed {execution['executed_action_id']}")
        return ApiResponse(**cache_response(stored, payload.request_id, response))


@router.post("/control-cycle", response_model=ApiResponse)
def control_cycle(session_id: str, payload: ControlCycleRequest, resources: ControlRoomResources = Depends(get_resources)) -> ApiResponse:
    stored = _stored(session_id)
    with stored.lock:
        cached = validate_envelope(stored, payload.request_id, payload.run_id, payload.expected_timestamp)
        if cached:
            return ApiResponse(**cached)
        cycle = run_control_cycle(stored, resources, payload.operation_mode, payload.controller_id)
        response = _response(
            stored,
            forecast=cycle.get("forecast"),
            plan=cycle.get("plan"),
            action=(cycle.get("plan") or {}).get("recommended_action"),
            message=f"{payload.operation_mode} control cycle complete",
        )
        return ApiResponse(**cache_response(stored, payload.request_id, response))


def _stored(session_id: str):
    try:
        return STORE.get(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"code": "SESSION_NOT_FOUND", "message": str(exc)}) from exc


def _response(stored, *, forecast=None, plan=None, action=None, message: str) -> dict:
    state = serialize_state(stored)
    return {
        "session_id": stored.session_id,
        "run_id": stored.live.run_identifier,
        "state": state,
        "forecast": forecast,
        "plan": plan,
        "action": action,
        "alerts": state.get("alerts", []),
        "history": state.get("history", []),
        "timings": stored.live.timings,
        "fallback_active": stored.live.fallback_visible,
        "fallback_reason": stored.live.fallback_reason,
        "message": message,
    }
