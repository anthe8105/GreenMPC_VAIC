from __future__ import annotations

import pandas as pd
from dataclasses import replace

from greenmpc.config import load_config
from greenmpc.evaluation.history_adapter import ObservedHistoryAdapter
from greenmpc.evaluation.metrics import paired_comparisons
from greenmpc.evaluation.rule_based import build_rule_based_action, build_rule_based_action_with_trace
from greenmpc.evaluation.runner import _is_cache_compatible
from greenmpc.simulation.park import IndustrialParkSimulator


def test_rule_based_is_distinct_valid_current_observation_policy():
    cfg = load_config("configs/demo.yaml")
    sim = IndustrialParkSimulator.from_processed_files(start_timestamp="2013-11-01T17:00:00+07:00")
    action = build_rule_based_action(sim.get_state(), cfg)
    assert action.controller_name == "rule_based"
    assert action.metadata["uses_forecast"] is False
    assert action.metadata["uses_optimization"] is False
    assert action.metadata["stage5_fallback"] is False
    assert sim.validate_action(action).valid


def test_rule_based_uses_battery_for_peak_and_pv_surplus():
    cfg = load_config("configs/demo.yaml")
    sim = IndustrialParkSimulator.from_processed_files(start_timestamp="2013-11-01T17:00:00+07:00")
    action, trace = build_rule_based_action_with_trace(sim.get_state(), cfg)
    assert action.total_battery_discharge_kw > 0
    assert trace["decision_branch"] == "discharge_for_peak_tariff"

    state = sim.get_state()
    low_loads = {tenant_id: 10.0 for tenant_id in sim.tenant_ids}
    surplus_state = replace(
        state,
        exogenous=replace(
            state.exogenous,
            effective_tenant_load_kw=low_loads,
            baseline_tenant_load_kw=low_loads,
            effective_pv_available_kw=1000.0,
            baseline_pv_available_kw=1000.0,
            tariff_period="normal",
        ),
    )
    surplus_action, surplus_trace = build_rule_based_action_with_trace(surplus_state, cfg)
    assert surplus_action.pv_to_battery_kw > 0
    assert surplus_trace["decision_branch"] == "charge_excess_pv"


def test_observed_history_replaces_current_effective_values_without_mutating_sources():
    tenant = pd.read_csv("data/processed/tenant_hourly.csv")
    park = pd.read_csv("data/processed/park_hourly.csv")
    original_tenant = tenant.copy(deep=True)
    original_park = park.copy(deep=True)
    sim = IndustrialParkSimulator.from_processed_files(start_timestamp="2013-11-01T17:00:00+07:00")
    adapter = ObservedHistoryAdapter(tenant, park, tuple(sim.tenant_ids))
    exogenous = sim.get_effective_exogenous()
    adapter.record_observation(exogenous)
    tenant_hist, park_hist, audit = adapter.histories_through(pd.Timestamp(exogenous.timestamp_local))
    assert audit["future_observations_used"] is False
    assert audit["all_five_tenants_aligned"] is True
    assert tenant.equals(original_tenant)
    assert park.equals(original_park)
    ts = pd.Timestamp(exogenous.timestamp_local)
    assert park_hist.loc[pd.to_datetime(park_hist["timestamp_local"]) == ts, "pv_available_kw"].iloc[0] == exogenous.effective_pv_available_kw


def test_paired_comparison_handles_zero_denominator():
    metrics = pd.DataFrame([
        {"scenario_id": "s", "controller_id": "rule_based", "total_realized_operating_cost_proxy_vnd": 0.0, "park_renewable_share": 0.2, "peak_grid_import_kw": 1.0, "peak_external_import_kw": 1.0, "pv_curtailment_kwh": 0.0, "battery_throughput_kwh": 0.0, "renewable_shortfall_total_kwh": 0.0, "fallback_count": 0},
        {"scenario_id": "s", "controller_id": "deterministic_mpc", "total_realized_operating_cost_proxy_vnd": 10.0, "park_renewable_share": 0.3, "peak_grid_import_kw": 2.0, "peak_external_import_kw": 2.0, "pv_curtailment_kwh": 1.0, "battery_throughput_kwh": 1.0, "renewable_shortfall_total_kwh": 0.0, "fallback_count": 1},
    ])
    result = paired_comparisons(metrics)
    assert result["operating_cost_percentage_difference"].isna().any()


def test_benchmark_outputs_exist_without_mutating_duration_cache():
    metrics = pd.read_csv("data/outputs/stage6_benchmark/controller_scenario_metrics.csv")
    assert metrics["completed_steps"].min() >= 24
    assert set(metrics["controller_id"]) == {"rule_based", "deterministic_mpc", "greenmpc_conservative"}


def test_cache_rejects_24_hour_output_for_72_hour_request():
    expected = {
        "cache_fingerprint": "full",
        "requested_duration_hours": 72,
        "run_mode": "full",
        "scenario_ids": ["normal"],
        "controller_ids": ["rule_based"],
    }
    existing = {
        "cache_fingerprint": "quick",
        "requested_hours": 24,
        "completed_hours": 24,
        "run_mode": "quick",
        "requested_scenarios": ["normal"],
        "requested_controllers": ["rule_based"],
        "completed_successfully": True,
    }
    assert not _is_cache_compatible(existing, expected)


def test_cache_rejects_changed_event_or_controller_identity():
    expected = {
        "cache_fingerprint": "same",
        "requested_duration_hours": 24,
        "run_mode": "quick",
        "scenario_ids": ["normal"],
        "controller_ids": ["rule_based", "deterministic_mpc"],
    }
    changed_event = {
        "cache_fingerprint": "different-event",
        "requested_hours": 24,
        "completed_hours": 24,
        "run_mode": "quick",
        "requested_scenarios": ["normal"],
        "requested_controllers": ["rule_based", "deterministic_mpc"],
        "completed_successfully": True,
    }
    changed_controller = {
        "cache_fingerprint": "same",
        "requested_hours": 24,
        "completed_hours": 24,
        "run_mode": "quick",
        "requested_scenarios": ["normal"],
        "requested_controllers": ["rule_based"],
        "completed_successfully": True,
    }
    assert not _is_cache_compatible(changed_event, expected)
    assert not _is_cache_compatible(changed_controller, expected)


def test_cache_reuses_only_identical_completed_request():
    expected = {
        "cache_fingerprint": "same",
        "requested_duration_hours": 24,
        "run_mode": "quick",
        "scenario_ids": ["normal"],
        "controller_ids": ["rule_based"],
    }
    existing = {
        "cache_fingerprint": "same",
        "requested_hours": 24,
        "completed_hours": 24,
        "run_mode": "quick",
        "requested_scenarios": ["normal"],
        "requested_controllers": ["rule_based"],
        "completed_successfully": True,
    }
    partial = {**existing, "completed_hours": 23}
    assert _is_cache_compatible(existing, expected)
    assert not _is_cache_compatible(partial, expected)
