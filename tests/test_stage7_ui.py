from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest

import greenmpc.ui.session as ui_session
from greenmpc.evaluation.rule_based import build_rule_based_action
from greenmpc.ui.session import (
    can_execute_latest_plan,
    configure_live_operation,
    control_tick_due,
    execute_next_hour,
    forecast_and_plan,
    pause_live_demo,
    process_control_tick,
    reset_live_run_state,
    start_live_demo,
    switch_controller,
)
from greenmpc.ui.state import initialize_live_session, load_control_room_resources
from greenmpc.ui.view_models import (
    benchmark_view,
    current_kpis,
    energy_topology,
    forecast_frames,
    objective_breakdown,
    primary_kpi_cards,
    rolling_history_frame,
    secondary_kpi_cards,
    tenant_summary,
)


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


def test_stage7_default_state_is_paused(resources):
    session = initialize_live_session(resources, scenario_id="normal", controller_id="deterministic_mpc", start_timestamp=resources.evaluation_config.start_timestamp)
    assert session.operation_mode == "Manual Approval"
    assert session.live_mode_enabled is False
    assert session.latest_status == "Paused"
    assert session.playback_interval_seconds == 5.0


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


def test_stage7_start_pause_and_tick_schedule(resources, monkeypatch):
    monkeypatch.setattr(ui_session, "forecast_and_plan", _fast_rule_plan)
    session = initialize_live_session(resources, scenario_id="normal", controller_id="rule_based", start_timestamp=resources.evaluation_config.start_timestamp)
    configure_live_operation(session, operation_mode="Auto Pilot Demo", playback_interval_seconds=5.0, maximum_simulated_hours=24)
    start_live_demo(session, now=100.0)
    assert session.live_mode_enabled
    assert session.next_control_tick == 105.0
    assert not control_tick_due(session, now=104.0)
    timestamp = session.simulator.get_state().timestamp_local
    process_control_tick(session, resources, now=104.0)
    assert session.simulator.get_state().timestamp_local == timestamp
    pause_live_demo(session)
    assert not session.live_mode_enabled
    assert session.latest_status == "Paused"


def test_stage7_expired_auto_tick_advances_exactly_once(resources, monkeypatch):
    monkeypatch.setattr(ui_session, "forecast_and_plan", _fast_rule_plan)
    session = initialize_live_session(resources, scenario_id="normal", controller_id="rule_based", start_timestamp=resources.evaluation_config.start_timestamp)
    configure_live_operation(session, operation_mode="Auto Pilot Demo", playback_interval_seconds=5.0, maximum_simulated_hours=24)
    start_live_demo(session, now=100.0)
    initial_timestamp = session.simulator.get_state().timestamp_local
    process_control_tick(session, resources, now=105.0)
    assert str(session.simulator.get_state().timestamp_local - initial_timestamp) == "1:00:00"
    assert len(session.execution_history) == 1
    assert len(rolling_history_frame(session)) == 1
    process_control_tick(session, resources, now=105.0)
    assert len(session.execution_history) == 1


def test_stage7_auto_pilot_replans_before_every_executed_hour(resources, monkeypatch):
    calls = {"count": 0}

    def counted_plan(session, resources):
        calls["count"] += 1
        return _fast_rule_plan(session, resources)

    monkeypatch.setattr(ui_session, "forecast_and_plan", counted_plan)
    session = initialize_live_session(resources, scenario_id="normal", controller_id="rule_based", start_timestamp=resources.evaluation_config.start_timestamp)
    configure_live_operation(session, operation_mode="Auto Pilot Demo", playback_interval_seconds=2.0, maximum_simulated_hours=24)
    start_live_demo(session, now=10.0)
    process_control_tick(session, resources, now=12.0)
    process_control_tick(session, resources, now=14.0)
    assert calls["count"] == 2
    assert len(session.execution_history) == 2


def test_stage7_shadow_mode_plans_but_never_executes(resources, monkeypatch):
    monkeypatch.setattr(ui_session, "forecast_and_plan", _fast_rule_plan)
    session = initialize_live_session(resources, scenario_id="normal", controller_id="rule_based", start_timestamp=resources.evaluation_config.start_timestamp)
    configure_live_operation(session, operation_mode="Shadow Mode", playback_interval_seconds=2.0, maximum_simulated_hours=24)
    start_live_demo(session, now=10.0)
    initial_timestamp = session.simulator.get_state().timestamp_local
    process_control_tick(session, resources, now=12.0)
    assert session.latest_action is not None
    assert session.simulator.get_state().timestamp_local == initial_timestamp
    assert len(session.execution_history) == 0
    assert session.latest_status == "Shadow Recommendation"


def test_stage7_reset_cancels_run_identifier(resources):
    session = initialize_live_session(resources, scenario_id="normal", controller_id="rule_based", start_timestamp=resources.evaluation_config.start_timestamp)
    original = session.run_identifier
    configure_live_operation(session, operation_mode="Auto Pilot Demo", playback_interval_seconds=2.0, maximum_simulated_hours=24)
    start_live_demo(session, now=1.0)
    reset_live_run_state(session)
    assert session.run_identifier != original
    assert not session.live_mode_enabled
    assert session.simulated_hours_completed == 0


def test_stage7_automatic_run_stops_at_maximum_duration(resources, monkeypatch):
    monkeypatch.setattr(ui_session, "forecast_and_plan", _fast_rule_plan)
    session = initialize_live_session(resources, scenario_id="normal", controller_id="rule_based", start_timestamp=resources.evaluation_config.start_timestamp)
    configure_live_operation(session, operation_mode="Auto Pilot Demo", playback_interval_seconds=2.0, maximum_simulated_hours=1)
    start_live_demo(session, now=1.0)
    process_control_tick(session, resources, now=3.0)
    assert session.simulated_hours_completed == 1
    assert not session.live_mode_enabled


def test_stage7_failure_preserves_simulator_state(resources, monkeypatch):
    def broken_plan(session, resources):
        raise RuntimeError("planned failure")

    monkeypatch.setattr(ui_session, "forecast_and_plan", broken_plan)
    session = initialize_live_session(resources, scenario_id="normal", controller_id="rule_based", start_timestamp=resources.evaluation_config.start_timestamp)
    configure_live_operation(session, operation_mode="Auto Pilot Demo", playback_interval_seconds=2.0, maximum_simulated_hours=24)
    start_live_demo(session, now=1.0)
    initial_timestamp = session.simulator.get_state().timestamp_local
    process_control_tick(session, resources, now=3.0)
    assert session.simulator.get_state().timestamp_local == initial_timestamp
    assert session.last_error == "planned failure"
    assert not session.live_mode_enabled


def test_stage7_view_models_reconcile_current_state(resources):
    session = initialize_live_session(resources, scenario_id="normal", controller_id="deterministic_mpc", start_timestamp=resources.evaluation_config.start_timestamp)
    kpis = current_kpis(session)
    state = session.simulator.get_state()
    assert kpis["battery_soc_fraction"] == state.battery.soc_fraction
    tenant = tenant_summary(session, "Electronics_A")
    assert tenant["tenant_id"] == "Electronics_A"
    assert tenant["renewable_target_fraction"] >= 0


def test_stage7_no_kpi_labels_are_truncated_by_view_model(resources):
    session = initialize_live_session(resources, scenario_id="normal", controller_id="deterministic_mpc", start_timestamp=resources.evaluation_config.start_timestamp)
    labels = [card["label"] for card in primary_kpi_cards(session) + secondary_kpi_cards(session)]
    assert all("..." not in label and "…" not in label for label in labels)
    assert {"Renewable share", "Operating cost", "Battery SOC", "Transformer utilization"}.issubset(labels)


def test_stage7_topology_reconciles_with_action_allocations(resources):
    session = initialize_live_session(resources, scenario_id="normal", controller_id="rule_based", start_timestamp=resources.evaluation_config.start_timestamp)
    session = _fast_rule_plan(session, resources)
    _, edges = energy_topology(session)
    pv_edges = edges[(edges["source"] == "Rooftop PV") & (edges["target"].isin(session.simulator.tenant_ids))]
    assert abs(pv_edges["kw"].sum() - sum(session.latest_action.pv_to_tenant_kw.values())) < 1e-6


def test_stage7_benchmark_adjusted_cost_recalculates_without_simulation(resources):
    frame = benchmark_view(resources, 2000.0)
    assert not frame.empty
    assert "inventory_adjusted_operating_cost_vnd" in frame.columns
    assert set(frame["scenario_id"]) == {"normal", "cloudy", "production_shift", "combined_stress"}


def test_stage7_core_packages_do_not_import_streamlit():
    if shutil.which("rg") is None:
        pytest.skip("ripgrep (rg) not installed")
    paths = [str(PROJECT_ROOT / "src/greenmpc" / package) for package in ("simulation", "forecasting", "control", "evaluation")]
    result = subprocess.run(["rg", "-n", "-i", "streamlit", *paths], text=True, capture_output=True, timeout=10)
    assert result.returncode == 1, result.stdout


def _fast_rule_plan(session, resources):
    state = session.simulator.get_state()
    action = build_rule_based_action(state, resources.project_config, action_id=f"TEST-RB-{state.step_index:06d}")
    validation = session.simulator.validate_action(action)
    session.latest_action = action
    session.latest_validation = validation
    session.latest_plan = None
    session.plan_timestamp = state.timestamp_local.isoformat()
    session.plan_is_stale = False
    session.fallback_visible = False
    session.fallback_reason = None
    session.timings["forecast_seconds"] = 0.0
    session.timings["planning_seconds"] = 0.0
    session.timings["validation_seconds"] = 0.0
    session.latest_status = "Plan Ready"
    return session
