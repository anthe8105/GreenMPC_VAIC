"""Realized KPI calculation for closed-loop benchmarks."""

from __future__ import annotations

import itertools

import pandas as pd


def controller_metrics(simulator, scenario_id: str, controller_id: str, fallback_count: int, planning_failures: int, runtime: dict) -> dict:
    summary = simulator.summary()
    park = simulator.get_park_energy_history()
    tenant = simulator.get_tenant_energy_history()
    final_state = simulator.get_state()
    fallback_reasons = runtime.get("fallback_reasons", [])
    shortfalls = {}
    for tenant_id, load in final_state.cumulative_load_by_tenant_kwh.items():
        target = simulator.tenant_targets[tenant_id]
        renewable = final_state.cumulative_renewable_by_tenant_kwh[tenant_id]
        shortfalls[tenant_id] = max(0.0, target * load - renewable)
    return {
        "scenario_id": scenario_id,
        "controller_id": controller_id,
        "completed_steps": summary["steps_executed"],
        "total_load_served_kwh": summary["total_load_served_kwh"],
        "realized_grid_energy_kwh": summary["grid_energy_kwh"],
        "realized_dppa_energy_kwh": summary["dppa_energy_kwh"],
        "direct_pv_delivery_kwh": summary["pv_direct_use_kwh"],
        "battery_delivery_kwh": summary["battery_discharge_kwh"],
        "pv_curtailment_kwh": summary["pv_curtailment_kwh"],
        "battery_throughput_kwh": summary["battery_throughput_kwh"],
        "realized_grid_cost_vnd": summary["total_grid_cost_vnd"],
        "realized_dppa_cost_vnd": summary["total_dppa_cost_vnd"],
        "realized_battery_degradation_proxy_vnd": summary["degradation_proxy_cost_vnd"],
        "total_realized_operating_cost_proxy_vnd": summary["total_operating_cost_vnd"],
        "total_renewable_delivery_kwh": summary["total_renewable_delivery_kwh"],
        "park_renewable_share": summary["renewable_share"],
        "peak_grid_import_kw": summary["peak_grid_import_kw"],
        "peak_external_import_kw": summary["peak_external_import_kw"],
        "maximum_transformer_utilization": summary["transformer_utilization_maximum"],
        "minimum_transformer_headroom_kw": _min_headroom(park),
        "initial_soc": summary["initial_soc"],
        "final_soc": summary["final_soc"],
        "minimum_soc": summary["minimum_soc"],
        "maximum_soc": summary["maximum_soc"],
        "hours_near_minimum_soc": int((park["battery_soc_after"] <= 0.101).sum()) if not park.empty else 0,
        "fallback_count": fallback_count,
        "fallback_reasons": ";".join(fallback_reasons),
        "solver_failure_count": planning_failures,
        "invalid_action_count": summary["invalid_action_count"],
        "hard_constraint_violations": 0,
        "event_affected_steps": summary["event_affected_steps"],
        "forecast_time_seconds": runtime.get("forecast_time_seconds", 0.0),
        "planning_time_seconds": runtime.get("planning_time_seconds", 0.0),
        "validation_time_seconds": runtime.get("validation_time_seconds", 0.0),
        "step_time_seconds": runtime.get("step_time_seconds", 0.0),
        "benchmark_time_seconds": runtime.get("benchmark_time_seconds", 0.0),
        "renewable_shortfall_total_kwh": sum(shortfalls.values()),
        **{f"renewable_shortfall_{k}_kwh": v for k, v in shortfalls.items()},
        **_tenant_shares(tenant),
    }


def paired_comparisons(metrics: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scenario_id, group in metrics.groupby("scenario_id"):
        lookup = group.set_index("controller_id")
        pairs = [("rule_based", "deterministic_mpc"), ("rule_based", "greenmpc_conservative"), ("deterministic_mpc", "greenmpc_conservative")]
        for a, b in pairs:
            if a not in lookup.index or b not in lookup.index:
                continue
            left = lookup.loc[a]
            right = lookup.loc[b]
            cost_diff = right["total_realized_operating_cost_proxy_vnd"] - left["total_realized_operating_cost_proxy_vnd"]
            rows.append({
                "scenario_id": scenario_id,
                "reference_controller": a,
                "comparison_controller": b,
                "operating_cost_difference_vnd": cost_diff,
                "operating_cost_percentage_difference": _safe_pct(cost_diff, left["total_realized_operating_cost_proxy_vnd"]),
                "renewable_share_difference": right["park_renewable_share"] - left["park_renewable_share"],
                "grid_peak_difference_kw": right["peak_grid_import_kw"] - left["peak_grid_import_kw"],
                "external_peak_difference_kw": right["peak_external_import_kw"] - left["peak_external_import_kw"],
                "curtailment_difference_kwh": right["pv_curtailment_kwh"] - left["pv_curtailment_kwh"],
                "battery_throughput_difference_kwh": right["battery_throughput_kwh"] - left["battery_throughput_kwh"],
                "renewable_shortfall_difference_kwh": right["renewable_shortfall_total_kwh"] - left["renewable_shortfall_total_kwh"],
                "fallback_count_difference": right["fallback_count"] - left["fallback_count"],
            })
    return pd.DataFrame(rows)


def _min_headroom(park: pd.DataFrame) -> float:
    if park.empty:
        return 0.0
    external_kw = park["external_import_kwh"]
    capacity = external_kw / park["transformer_utilization_fraction"].replace(0, pd.NA)
    return float((capacity - external_kw).min())


def _tenant_shares(tenant: pd.DataFrame) -> dict:
    if tenant.empty:
        return {}
    rows = {}
    grouped = tenant.groupby("tenant_id")
    for tenant_id, group in grouped:
        load = group["effective_load_kwh"].sum()
        renewable = group["total_renewable_delivery_kwh"].sum()
        rows[f"renewable_share_{tenant_id}"] = 0.0 if load <= 0 else renewable / load
    return rows


def _safe_pct(diff: float, base: float) -> float | None:
    if abs(base) < 1e-9:
        return None
    return diff / base
