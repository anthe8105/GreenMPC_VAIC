"""Thin service adapter over the approved GreenMPC Python core."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from typing import Any
from uuid import uuid4

import pandas as pd
from fastapi import HTTPException

from backend.schemas import OperationMode
from backend.session_store import StoredSession
from greenmpc.control.types import MPCMode
from greenmpc.evaluation.rule_based import build_rule_based_action
from greenmpc.ui.session import can_execute_latest_plan, execute_next_hour, switch_controller
from greenmpc.ui.state import PROJECT_ROOT, ControlRoomResources, LiveControlSession, initialize_live_session, invalidate_plan
from greenmpc.ui.view_models import (
    action_preview,
    aggregate_forecast_frame,
    alert_cards,
    benchmark_view,
    current_kpis,
    energy_topology,
    objective_breakdown,
    plan_frames,
    provenance_summary,
    recommended_action_card,
    rolling_history_frame,
    solver_diagnostics,
)

logger = logging.getLogger(__name__)


def create_live_session(resources: ControlRoomResources, scenario_id: str, controller_id: str, start_timestamp: str | None) -> LiveControlSession:
    return initialize_live_session(resources, scenario_id=scenario_id, controller_id=controller_id, start_timestamp=start_timestamp)


def serialize_state(stored: StoredSession) -> dict[str, Any]:
    session = stored.live
    state = session.simulator.get_state()
    effective = session.simulator.get_effective_exogenous()
    nodes, edges = energy_topology(session)
    return {
        "session_id": stored.session_id,
        "run_id": session.run_identifier,
        "timestamp": state.timestamp_local.isoformat(),
        "status": session.latest_status,
        "operation_mode": session.operation_mode,
        "controller_id": session.controller_id,
        "scenario_id": session.scenario_id,
        "compatibility_status": "compatible",
        "kpis": current_kpis(session),
        "tenant_load_kw_by_tenant": {str(tenant): float(load_kw) for tenant, load_kw in effective.effective_tenant_load_kw.items()},
        "topology": {"nodes": nodes.to_dict("records"), "edges": edges.to_dict("records")},
        "alerts": alert_cards(session) or [{"severity": "ok", "title": "Within limits", "message": "System operating within configured limits."}],
        "history": rolling_history_frame(session).to_dict("records"),
        "timings": session.timings,
        "completed_hours": session.simulated_hours_completed,
        "maximum_hours": session.maximum_simulated_hours,
        "fallback_active": session.fallback_visible,
        "fallback_reason": session.fallback_reason,
        "last_error": session.last_error,
    }


def generate_forecast(stored: StoredSession, resources: ControlRoomResources) -> dict[str, Any]:
    session = stored.live
    start = time.perf_counter()
    state = session.simulator.get_state()
    effective = session.simulator.get_effective_exogenous()
    session.history_adapter.record_observation(effective)
    origin = pd.Timestamp(state.timestamp_local)
    tenant_history, park_history, audit = session.history_adapter.histories_through(origin)
    load_forecast, solar_forecast = resources.forecast_service.forecast_all(tenant_history, park_history, origin, horizon_hours=6)
    session.latest_load_forecast = load_forecast
    session.latest_solar_forecast = solar_forecast
    session.timings["forecast_seconds"] = time.perf_counter() - start
    session.timings["future_observations_used"] = bool(audit.get("future_observations_used"))
    session.latest_status = "Forecast Ready"
    return serialize_forecast(session)


def build_plan(stored: StoredSession, resources: ControlRoomResources, controller_id: str | None = None, generate_if_missing: bool = True) -> dict[str, Any]:
    session = stored.live
    if controller_id:
        switch_controller(session, controller_id)
    if (session.latest_load_forecast is None or session.latest_solar_forecast is None) and generate_if_missing:
        generate_forecast(stored, resources)
    if session.latest_load_forecast is None or session.latest_solar_forecast is None:
        raise_conflict("FORECAST_MISSING", "Generate a forecast before planning.")
    session.latest_status = "Planning"
    start = time.perf_counter()
    state = session.simulator.get_state()
    if session.controller_id == "rule_based":
        effective = session.simulator.get_effective_exogenous()
        action_state = replace(state, exogenous=effective)
        action = build_rule_based_action(action_state, resources.project_config, action_id=f"API-RB-{state.step_index:06d}")
        validation = session.simulator.validate_action(action)
        plan = None
        fallback_visible = False
        fallback_reason = None
    else:
        mode = MPCMode.EXPECTED if session.controller_id == "deterministic_mpc" else MPCMode.CONSERVATIVE
        plan = resources.controller.plan_with_fallback(session.simulator.clone(), session.latest_load_forecast, session.latest_solar_forecast, mode)
        action = plan.first_action
        validation = session.simulator.validate_action(action)
        fallback_visible = bool(plan.solver_diagnostics.fallback_used or plan.fallback_reason)
        fallback_reason = plan.fallback_reason
    session.timings["planning_seconds"] = time.perf_counter() - start
    session.latest_plan = plan
    session.latest_action = action
    session.latest_validation = validation
    session.plan_timestamp = pd.Timestamp(state.timestamp_local).isoformat()
    session.plan_is_stale = False
    session.fallback_visible = fallback_visible
    session.fallback_reason = fallback_reason
    if not validation.valid:
        session.latest_status = "Invalid Action"
        session.last_error = "Action validation failed."
    elif fallback_visible:
        session.latest_status = "Fallback"
    else:
        session.latest_status = "Plan Ready"
    return serialize_plan(session, resources)


def execute_current_action(stored: StoredSession) -> dict[str, Any]:
    session = stored.live
    action = session.latest_action
    if action is None:
        raise_conflict("ACTION_MISSING", "No action is available to execute.")
    if action.action_id in stored.executed_action_ids:
        raise_conflict("DUPLICATE_ACTION", "This action was already executed.")
    ok, reason = can_execute_latest_plan(session)
    if not ok:
        raise_conflict("ACTION_NOT_EXECUTABLE", reason)
    pre_timestamp = session.simulator.get_state().timestamp_local
    try:
        execute_next_hour(session)
    except Exception as exc:
        logger.exception("execution failed")
        if session.simulator.get_state().timestamp_local != pre_timestamp:
            raise_conflict("EXECUTION_PARTIAL_FAILURE", f"Execution failed after timestamp changed: {exc}")
        raise_conflict("EXECUTION_FAILED", str(exc))
    stored.executed_action_ids.add(action.action_id)
    return {"state": serialize_state(stored), "executed_action_id": action.action_id}


def run_control_cycle(stored: StoredSession, resources: ControlRoomResources, operation_mode: OperationMode, controller_id: str | None = None) -> dict[str, Any]:
    if controller_id:
        switch_controller(stored.live, controller_id)
    generate_forecast(stored, resources)
    plan = build_plan(stored, resources, controller_id=None, generate_if_missing=False)
    executed = None
    if operation_mode == "auto":
        executed = execute_current_action(stored)
    elif operation_mode == "shadow":
        stored.live.latest_status = "Shadow Recommendation"
    else:
        stored.live.latest_status = "Plan Ready"
    return {"forecast": serialize_forecast(stored.live), "plan": plan, "execution": executed, "state": serialize_state(stored)}


def serialize_forecast(session: LiveControlSession) -> dict[str, Any]:
    load = session.latest_load_forecast.to_dataframe() if session.latest_load_forecast else pd.DataFrame()
    solar = session.latest_solar_forecast.to_dataframe() if session.latest_solar_forecast else pd.DataFrame()
    return {
        "load": load.to_dict("records"),
        "solar": solar.to_dict("records"),
        "aggregate": aggregate_forecast_frame(session).to_dict("records"),
        "metadata": {
            "load_forecast_id": session.latest_load_forecast.metadata.forecast_id if session.latest_load_forecast else None,
            "solar_forecast_id": session.latest_solar_forecast.metadata.forecast_id if session.latest_solar_forecast else None,
        },
    }


def serialize_plan(session: LiveControlSession, resources: ControlRoomResources | None = None) -> dict[str, Any]:
    tenant_plan, park_plan = plan_frames(session)
    return {
        "tenant_plan": tenant_plan.to_dict("records"),
        "park_plan": park_plan.to_dict("records"),
        "action": action_preview(session).to_dict("records"),
        "recommended_action": recommended_action_card(session),
        "solver": solver_diagnostics(session),
        "objective": objective_breakdown(session).to_dict("records"),
        "decision_comparison": _decision_comparison(session, resources) if resources is not None else {},
        "fallback_active": session.fallback_visible,
        "fallback_reason": session.fallback_reason,
        "valid_for_execution": bool(session.latest_validation.valid) if session.latest_validation else False,
    }


def _decision_comparison(session: LiveControlSession, resources: ControlRoomResources | None) -> dict[str, Any]:
    if resources is None or session.latest_action is None:
        return {}
    state = session.simulator.get_state()
    effective = session.simulator.get_effective_exogenous()
    action_state = replace(state, exogenous=effective)
    rule_action = build_rule_based_action(action_state, resources.project_config, action_id=f"API-COMPARE-RB-{state.step_index:06d}")
    green = _action_one_hour_metrics(session.latest_action, effective, resources)
    rule = _action_one_hour_metrics(rule_action, effective, resources)
    return {
        "label": "NEXT-HOUR DECISION COMPARISON",
        "greenmpc": green,
        "rule_based": rule,
        "notes": "One-hour comparison from the same current state. It is not a long-term savings claim.",
    }


def _action_one_hour_metrics(action: Any, effective: Any, resources: ControlRoomResources) -> dict[str, float]:
    grid_import = sum(action.grid_to_tenant_kw.values())
    dppa_import = sum(action.dppa_to_tenant_kw.values()) + action.dppa_to_battery_kw
    pv_use = sum(action.pv_to_tenant_kw.values()) + action.pv_to_battery_kw
    battery_discharge = sum(action.battery_to_tenant_kw.values())
    throughput = battery_discharge + action.pv_to_battery_kw + action.dppa_to_battery_kw
    cost = (
        grid_import * effective.grid_price_vnd_per_kwh
        + dppa_import * effective.dppa_price_vnd_per_kwh
        + throughput * resources.project_config.battery.degradation_cost_vnd_per_kwh_throughput
    )
    load = sum(effective.effective_tenant_load_kw.values())
    renewable = sum(action.pv_to_tenant_kw.values()) + sum(action.dppa_to_tenant_kw.values()) + battery_discharge
    return {
        "planned_cost_vnd": float(cost),
        "grid_peak_kw": float(grid_import),
        "external_import_kw": float(grid_import + dppa_import),
        "renewable_share_fraction": 0.0 if load <= 0 else float(renewable / load),
        "pv_use_kw": float(pv_use),
        "battery_discharge_kw": float(battery_discharge),
    }


def validate_envelope(stored: StoredSession, request_id: str, run_id: str, expected_timestamp: str) -> dict[str, Any] | None:
    if request_id in stored.request_cache:
        return stored.request_cache[request_id]
    session = stored.live
    if run_id != session.run_identifier:
        raise_conflict("RUN_ID_MISMATCH", "Request run_id is no longer active.")
    current = pd.Timestamp(session.simulator.get_state().timestamp_local).isoformat()
    if expected_timestamp != current:
        raise_conflict("TIMESTAMP_MISMATCH", f"Expected timestamp {expected_timestamp}, current timestamp {current}.")
    return None


def cache_response(stored: StoredSession, request_id: str, response: dict[str, Any]) -> dict[str, Any]:
    stored.request_cache[request_id] = response
    return response


def reset_session_in_place(stored: StoredSession, resources: ControlRoomResources, scenario_id: str, controller_id: str, start_timestamp: str | None) -> None:
    stored.live = create_live_session(resources, scenario_id, controller_id, start_timestamp)
    stored.request_cache.clear()
    stored.executed_action_ids.clear()


def benchmark_rows(resources: ControlRoomResources, valuation_price: float) -> list[dict[str, Any]]:
    return benchmark_view(resources, valuation_price).to_dict("records")


def provenance_data(resources: ControlRoomResources) -> dict[str, Any]:
    summary = provenance_summary(resources, "normal")
    return {
        **summary,
        "stage6_manifest": _safe_json("data/outputs/stage6_benchmark/benchmark_manifest.json"),
        "offline_runtime": True,
        "prohibited_claims": [
            "No actual VRG operational data is claimed.",
            "PV is derived, not measured inverter output.",
            "Tariff and DPPA values are scenario assumptions.",
        ],
    }


def raise_conflict(code: str, message: str) -> None:
    raise HTTPException(status_code=409, detail={"code": code, "message": message})


def request_id() -> str:
    return uuid4().hex


def _safe_json(path: str) -> dict[str, Any]:
    from pathlib import Path

    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))
