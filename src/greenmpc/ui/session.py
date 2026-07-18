"""Live Control Room workflow functions independent of Streamlit widgets."""

from __future__ import annotations

import time
import sys
from dataclasses import replace
from typing import Any

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd

from greenmpc.control.types import MPCMode
from greenmpc.evaluation.rule_based import build_rule_based_action
from greenmpc.ui.state import ControlRoomResources, LiveControlSession, invalidate_plan


CONTROLLER_OPTIONS = ("rule_based", "deterministic_mpc", "greenmpc_conservative")


def forecast_and_plan(session: LiveControlSession, resources: ControlRoomResources) -> LiveControlSession:
    """Generate one shared forecast bundle and a current-step action candidate."""

    session.last_error = None
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
        return session
    start = time.perf_counter()
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
    session.timings["execution_seconds"] = time.perf_counter() - start
    invalidate_plan(session)
    session.last_error = None
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


def switch_controller(session: LiveControlSession, controller_id: str) -> LiveControlSession:
    """Change the selected controller without solving or mutating simulator state."""

    if controller_id not in CONTROLLER_OPTIONS:
        raise ValueError(f"unknown controller_id: {controller_id}")
    if controller_id != session.controller_id:
        session.controller_id = controller_id
        invalidate_plan(session)
    return session


def _validation_message(validation: Any) -> str:
    violations = getattr(validation, "violations", [])
    if not violations:
        return "action validation failed"
    return "; ".join(getattr(item, "message", str(item)) for item in violations[:3])
