"""Live Control Room workflow functions independent of Streamlit widgets."""

from __future__ import annotations

import time
import sys
from dataclasses import replace
from typing import Any
from uuid import uuid4

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd

from greenmpc.control.types import MPCMode
from greenmpc.evaluation.rule_based import build_rule_based_action
from greenmpc.ui.state import ControlRoomResources, LiveControlSession, invalidate_plan


CONTROLLER_OPTIONS = ("rule_based", "deterministic_mpc", "greenmpc_conservative")
OPERATION_MODES = ("Manual Approval", "Auto Pilot Demo", "Shadow Mode")
PLAYBACK_INTERVALS_SECONDS = (2.0, 5.0, 10.0)


def forecast_and_plan(session: LiveControlSession, resources: ControlRoomResources) -> LiveControlSession:
    """Generate one shared forecast bundle and a current-step action candidate."""

    session.last_error = None
    session.latest_status = "Planning"
    start_total = time.perf_counter()
    state = session.simulator.get_state()
    effective = session.simulator.get_effective_exogenous()
    session.history_adapter.record_observation(effective)
    origin = pd.Timestamp(state.timestamp_local)

    forecast_start = time.perf_counter()
    tenant_history, park_history, audit = session.history_adapter.histories_through(origin)
    load_forecast, solar_forecast = resources.forecast_service.forecast_all(tenant_history, park_history, origin, horizon_hours=6)
    forecast_seconds = time.perf_counter() - forecast_start

    plan_start = time.perf_counter()
    if session.controller_id == "rule_based":
        action_state = replace(state, exogenous=effective)
        action = build_rule_based_action(action_state, resources.project_config, action_id=f"UI-RB-{state.step_index:06d}")
        validation_start = time.perf_counter()
        validation = session.simulator.validate_action(action)
        validation_seconds = time.perf_counter() - validation_start
        plan = None
        fallback_visible = False
        fallback_reason = None
    else:
        mode = MPCMode.EXPECTED if session.controller_id == "deterministic_mpc" else MPCMode.CONSERVATIVE
        plan = resources.controller.plan_with_fallback(session.simulator.clone(), load_forecast, solar_forecast, mode)
        action = plan.first_action
        validation_start = time.perf_counter()
        validation = session.simulator.validate_action(action)
        validation_seconds = time.perf_counter() - validation_start
        fallback_visible = bool(plan.solver_diagnostics.fallback_used or plan.fallback_reason)
        fallback_reason = plan.fallback_reason
    plan_seconds = time.perf_counter() - plan_start

    session.latest_load_forecast = load_forecast
    session.latest_solar_forecast = solar_forecast
    session.latest_plan = plan
    session.latest_action = action
    session.latest_validation = validation
    session.plan_timestamp = origin.isoformat()
    session.plan_is_stale = False
    session.fallback_visible = fallback_visible
    session.fallback_reason = fallback_reason
    session.timings.update(
        {
            "forecast_seconds": forecast_seconds,
            "planning_seconds": plan_seconds,
            "validation_seconds": validation_seconds,
            "last_interaction_seconds": time.perf_counter() - start_total,
            "future_observations_used": bool(audit.get("future_observations_used")),
        }
    )
    if not validation.valid:
        session.last_error = _validation_message(validation)
        session.latest_status = "Invalid Action"
    elif fallback_visible:
        session.latest_status = "Fallback"
    elif session.operation_mode == "Shadow Mode":
        session.latest_status = "Shadow Recommendation"
    elif session.live_mode_enabled:
        session.latest_status = "Running"
    else:
        session.latest_status = "Plan Ready"
    return session


def can_execute_latest_plan(session: LiveControlSession) -> tuple[bool, str]:
    """Return whether the latest action can be executed safely."""

    if session.latest_action is None or session.latest_validation is None:
        return False, "No validated action is available."
    state = session.simulator.get_state()
    if session.plan_timestamp != pd.Timestamp(state.timestamp_local).isoformat():
        return False, "The plan timestamp is stale."
    if session.plan_is_stale:
        return False, "The current plan has been invalidated."
    if not session.latest_validation.valid:
        return False, "The current action failed simulator validation."
    return True, "Ready to execute one simulated hour."


def execute_next_hour(session: LiveControlSession) -> LiveControlSession:
    """Execute exactly one validated action and invalidate the old plan."""

    ok, reason = can_execute_latest_plan(session)
    if not ok:
        session.last_error = reason
        session.latest_status = "Invalid Action"
        return session
    start = time.perf_counter()
    session.latest_status = "Executing"
    previous_timestamp = session.simulator.get_state().timestamp_local
    result = session.simulator.step(session.latest_action)
    session.execution_history.append(
        {
            "previous_timestamp": previous_timestamp.isoformat(),
            "next_timestamp": result.next_state.timestamp_local.isoformat(),
            "action_id": session.latest_action.action_id,
            "controller_id": session.controller_id,
            "fallback_used": session.fallback_visible,
        }
    )
    _append_rolling_history(session)
    session.timings["execution_seconds"] = time.perf_counter() - start
    session.latest_latency["execution_seconds"] = session.timings["execution_seconds"]
    invalidate_plan(session)
    session.last_error = None
    session.simulated_hours_completed += 1
    session.latest_status = "Running" if session.live_mode_enabled else "Paused"
    return session


def run_next_hours(session: LiveControlSession, resources: ControlRoomResources, hours: int = 3) -> LiveControlSession:
    """Reforecast, replan, and execute one action at a time for a bounded run."""

    for _ in range(hours):
        session = forecast_and_plan(session, resources)
        ok, reason = can_execute_latest_plan(session)
        if not ok:
            session.last_error = reason
            break
        session = execute_next_hour(session)
    return session


def configure_live_operation(
    session: LiveControlSession,
    *,
    operation_mode: str,
    playback_interval_seconds: float,
    maximum_simulated_hours: int = 24,
) -> LiveControlSession:
    """Update live demo controls without solving or executing."""

    if operation_mode not in OPERATION_MODES:
        raise ValueError(f"unknown operation mode: {operation_mode}")
    if float(playback_interval_seconds) not in PLAYBACK_INTERVALS_SECONDS:
        raise ValueError("playback interval must be 2, 5, or 10 seconds")
    session.operation_mode = operation_mode
    session.playback_interval_seconds = float(playback_interval_seconds)
    session.maximum_simulated_hours = int(maximum_simulated_hours)
    if operation_mode == "Manual Approval" and session.live_mode_enabled:
        pause_live_demo(session)
    return session


def start_live_demo(session: LiveControlSession, now: float | None = None) -> LiveControlSession:
    """Enable scheduled live control ticks."""

    current = time.monotonic() if now is None else float(now)
    if session.operation_mode == "Manual Approval":
        session.last_error = "Auto progression is disabled in Manual Approval mode."
        session.latest_status = "Paused"
        return session
    session.live_mode_enabled = True
    session.latest_status = "Running"
    session.last_error = None
    session.last_control_tick = current
    session.next_control_tick = current + session.playback_interval_seconds
    session.last_processed_tick_key = None
    return session


def pause_live_demo(session: LiveControlSession) -> LiveControlSession:
    """Pause scheduled live control ticks without changing simulator state."""

    session.live_mode_enabled = False
    session.latest_status = "Paused"
    return session


def reset_live_run_state(session: LiveControlSession) -> LiveControlSession:
    """Cancel an active run identifier and reset live counters."""

    session.live_mode_enabled = False
    session.latest_status = "Paused"
    session.last_control_tick = None
    session.next_control_tick = None
    session.simulated_hours_completed = 0
    session.step_in_progress = False
    session.run_identifier = uuid4().hex
    session.last_processed_tick_key = None
    session.rolling_history.clear()
    invalidate_plan(session)
    return session


def control_tick_due(session: LiveControlSession, now: float | None = None) -> bool:
    """Return whether a scheduled control tick should execute."""

    current = time.monotonic() if now is None else float(now)
    return bool(
        session.live_mode_enabled
        and not session.step_in_progress
        and session.next_control_tick is not None
        and current >= session.next_control_tick
        and session.simulated_hours_completed < session.maximum_simulated_hours
    )


def seconds_until_next_tick(session: LiveControlSession, now: float | None = None) -> float | None:
    """Return countdown seconds until the next scheduled live tick."""

    if not session.live_mode_enabled or session.next_control_tick is None:
        return None
    current = time.monotonic() if now is None else float(now)
    return max(0.0, session.next_control_tick - current)


def process_control_tick(session: LiveControlSession, resources: ControlRoomResources, now: float | None = None) -> LiveControlSession:
    """Execute at most one due live control tick."""

    current = time.monotonic() if now is None else float(now)
    if not control_tick_due(session, current):
        return session
    tick_key = f"{session.run_identifier}:{session.next_control_tick:.6f}:{session.simulator.get_state().timestamp_local.isoformat()}"
    if session.last_processed_tick_key == tick_key:
        return session
    session.step_in_progress = True
    session.last_processed_tick_key = tick_key
    pre_timestamp = session.simulator.get_state().timestamp_local
    try:
        session = forecast_and_plan(session, resources)
        if session.operation_mode == "Shadow Mode":
            session.last_control_tick = current
            session.next_control_tick = current + session.playback_interval_seconds
            session.latest_status = "Shadow Recommendation"
            return session
        ok, reason = can_execute_latest_plan(session)
        if not ok:
            session.last_error = reason
            session.live_mode_enabled = False
            session.latest_status = "Invalid Action"
            return session
        session = execute_next_hour(session)
        session.last_control_tick = current
        session.next_control_tick = current + session.playback_interval_seconds
        if session.simulated_hours_completed >= session.maximum_simulated_hours:
            session.live_mode_enabled = False
            session.latest_status = "Paused"
        return session
    except Exception as exc:
        if session.simulator.get_state().timestamp_local != pre_timestamp:
            session.last_error = f"live tick failed after timestamp changed: {exc}"
        else:
            session.last_error = str(exc)
        session.live_mode_enabled = False
        session.latest_status = "Error"
        return session
    finally:
        session.step_in_progress = False


def switch_controller(session: LiveControlSession, controller_id: str) -> LiveControlSession:
    """Change the selected controller without solving or mutating simulator state."""

    if controller_id not in CONTROLLER_OPTIONS:
        raise ValueError(f"unknown controller_id: {controller_id}")
    if controller_id != session.controller_id:
        session.controller_id = controller_id
        invalidate_plan(session)
    return session


def _append_rolling_history(session: LiveControlSession) -> None:
    park = session.simulator.get_park_energy_history()
    if park.empty:
        return
    last = park.iloc[-1]
    session.rolling_history.append(
        {
            "timestamp_local": str(last["timestamp_local"]),
            "park_load_kw": float(last["total_effective_load_kwh"]),
            "pv_to_tenants_kw": float(last["total_pv_to_tenants_kwh"]),
            "grid_import_kw": float(last["total_grid_to_tenants_kwh"]),
            "dppa_import_kw": float(last["total_dppa_to_tenants_kwh"] + last["dppa_to_battery_kwh"]),
            "battery_power_kw": float(last["total_battery_to_tenants_kwh"] - last["pv_to_battery_kwh"] - last["dppa_to_battery_kwh"]),
            "soc_fraction": float(last["battery_soc_after"]),
            "transformer_utilization_fraction": float(last["transformer_utilization_fraction"]),
            "cumulative_cost_vnd": float(session.simulator.get_state().cumulative.total_operating_cost_vnd),
        }
    )
    session.rolling_history[:] = session.rolling_history[-24:]


def _validation_message(validation: Any) -> str:
    violations = getattr(validation, "violations", [])
    if not violations:
        return "action validation failed"
    return "; ".join(getattr(item, "message", str(item)) for item in violations[:3])
