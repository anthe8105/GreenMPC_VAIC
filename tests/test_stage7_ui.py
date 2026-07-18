from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from greenmpc.ui.session import can_execute_latest_plan, execute_next_hour, forecast_and_plan, switch_controller
from greenmpc.ui.state import initialize_live_session, load_control_room_resources
from greenmpc.ui.view_models import benchmark_view, current_kpis, forecast_frames, objective_breakdown, tenant_summary


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def resources():
    return load_control_room_resources(PROJECT_ROOT)


def test_stage7_switching_controller_invalidates_plan_without_advancing(resources):
    session = initialize_live_session(resources, scenario_id="normal", controller_id="deterministic_mpc", start_timestamp=resources.evaluation_config.start_timestamp)
    timestamp = session.simulator.get_state().timestamp_local
    session = switch_controller(session, "rule_based")
    assert session.controller_id == "rule_based"
    assert session.latest_action is None
    assert session.plan_is_stale
    assert session.simulator.get_state().timestamp_local == timestamp


def test_stage7_deterministic_mpc_forecast_plan_execute_one_hour(resources):
    session = initialize_live_session(resources, scenario_id="normal", controller_id="deterministic_mpc", start_timestamp=resources.evaluation_config.start_timestamp)
    initial_timestamp = session.simulator.get_state().timestamp_local
    session = forecast_and_plan(session, resources)
    ready, reason = can_execute_latest_plan(session)
    assert ready, reason
    load, solar = forecast_frames(session)
    assert {"p10_kw", "p50_kw", "p90_kw"}.issubset(load.columns)
    assert {"p10_kw", "p50_kw", "p90_kw"}.issubset(solar.columns)
    assert not objective_breakdown(session).empty
    session = execute_next_hour(session)
    assert str(session.simulator.get_state().timestamp_local - initial_timestamp) == "1:00:00"
    ready_after, reason_after = can_execute_latest_plan(session)
    assert not ready_after
    assert "No validated action" in reason_after


def test_stage7_rule_based_live_step_uses_no_forecast_for_action(resources):
    session = initialize_live_session(resources, scenario_id="normal", controller_id="rule_based", start_timestamp=resources.evaluation_config.start_timestamp)
    session = forecast_and_plan(session, resources)
    assert session.latest_plan is None
    assert session.latest_action.metadata["uses_forecast"] is False
    ready, reason = can_execute_latest_plan(session)
    assert ready, reason


def test_stage7_view_models_reconcile_current_state(resources):
    session = initialize_live_session(resources, scenario_id="normal", controller_id="deterministic_mpc", start_timestamp=resources.evaluation_config.start_timestamp)
    kpis = current_kpis(session)
    state = session.simulator.get_state()
    assert kpis["battery_soc_fraction"] == state.battery.soc_fraction
    tenant = tenant_summary(session, "Electronics_A")
    assert tenant["tenant_id"] == "Electronics_A"
    assert tenant["renewable_target_fraction"] >= 0


def test_stage7_benchmark_adjusted_cost_recalculates_without_simulation(resources):
    frame = benchmark_view(resources, 2000.0)
    assert not frame.empty
    assert "inventory_adjusted_operating_cost_vnd" in frame.columns
    assert set(frame["scenario_id"]) == {"normal", "cloudy", "production_shift", "combined_stress"}


def test_stage7_core_packages_do_not_import_streamlit():
    paths = [str(PROJECT_ROOT / "src/greenmpc" / package) for package in ("simulation", "forecasting", "control", "evaluation")]
    result = subprocess.run(["rg", "-n", "-i", "streamlit", *paths], text=True, capture_output=True, timeout=10)
    assert result.returncode == 1, result.stdout
