"""Testable data preparation for the Streamlit Control Room."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import Any

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd

from greenmpc.evaluation.metrics import rank_inventory_adjusted_costs, terminal_inventory_adjusted_costs_from_histories
from greenmpc.ui.state import ControlRoomResources, LiveControlSession, PROJECT_ROOT


def current_kpis(session: LiveControlSession) -> dict[str, float | str]:
    """Build the current operational KPI card values."""

    state = session.simulator.get_state()
    ex = session.simulator.get_effective_exogenous()
    cumulative = state.cumulative
    total_load = sum(ex.effective_tenant_load_kw.values())
    external_import = cumulative.peak_external_import_kw
    renewable_share = 0.0 if cumulative.total_load_energy_kwh <= 0 else cumulative.renewable_energy_to_tenants_kwh / cumulative.total_load_energy_kwh
    return {
        "timestamp_local": state.timestamp_local.isoformat(),
        "park_load_kw": total_load,
        "pv_available_kw": ex.effective_pv_available_kw,
        "battery_soc_fraction": state.battery.soc_fraction,
        "grid_import_kw_last_peak": cumulative.peak_grid_import_kw,
        "external_import_kw_last_peak": external_import,
        "transformer_utilization_fraction": 0.0 if ex.transformer_capacity_kw <= 0 else external_import / ex.transformer_capacity_kw,
        "renewable_share_fraction": renewable_share,
        "operating_cost_vnd": cumulative.total_operating_cost_vnd,
        "tariff_period": ex.tariff_period,
        "dppa_available_kw": ex.dppa_available_kw,
    }


def current_energy_flow(session: LiveControlSession) -> pd.DataFrame:
    """Return current or latest-executed source-flow rows for plotting."""

    park = session.simulator.get_park_energy_history()
    if park.empty:
        ex = session.simulator.get_effective_exogenous()
        return pd.DataFrame(
            [
                {"source": "Load", "sink": "tenants", "kw": sum(ex.effective_tenant_load_kw.values())},
                {"source": "PV available", "sink": "onsite", "kw": ex.effective_pv_available_kw},
                {"source": "DPPA available", "sink": "external", "kw": ex.dppa_available_kw},
            ]
        )
    last = park.iloc[-1]
    return pd.DataFrame(
        [
            {"source": "PV", "sink": "tenants", "kw": float(last["total_pv_to_tenants_kwh"])},
            {"source": "Battery", "sink": "tenants", "kw": float(last["total_battery_to_tenants_kwh"])},
            {"source": "DPPA", "sink": "tenants", "kw": float(last["total_dppa_to_tenants_kwh"])},
            {"source": "Grid", "sink": "tenants", "kw": float(last["total_grid_to_tenants_kwh"])},
            {"source": "PV", "sink": "battery", "kw": float(last["pv_to_battery_kwh"])},
            {"source": "PV", "sink": "curtailment", "kw": float(last["pv_curtailment_kwh"])},
        ]
    )


def forecast_frames(session: LiveControlSession) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return load and solar forecast frames for charts."""

    load = session.latest_load_forecast.to_dataframe() if session.latest_load_forecast else pd.DataFrame()
    solar = session.latest_solar_forecast.to_dataframe() if session.latest_solar_forecast else pd.DataFrame()
    return load, solar


def plan_frames(session: LiveControlSession) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return normalized tenant and park plan frames."""

    plan = session.latest_plan
    if plan is None:
        return pd.DataFrame(), pd.DataFrame()
    return plan.tenant_plan.copy(deep=True), plan.park_plan.copy(deep=True)


def tenant_summary(session: LiveControlSession, tenant_id: str) -> dict[str, float | str | bool]:
    """Build tenant-level current and cumulative summary values."""

    state = session.simulator.get_state()
    ex = session.simulator.get_effective_exogenous()
    load = ex.effective_tenant_load_kw[tenant_id]
    cumulative_load = state.cumulative_load_by_tenant_kwh[tenant_id]
    renewable = state.cumulative_renewable_by_tenant_kwh[tenant_id]
    target = session.simulator.tenant_targets[tenant_id]
    shortfall = max(0.0, target * cumulative_load - renewable)
    share = 0.0 if cumulative_load <= 0 else renewable / cumulative_load
    return {
        "tenant_id": tenant_id,
        "current_load_kw": load,
        "cumulative_load_kwh": cumulative_load,
        "cumulative_renewable_kwh": renewable,
        "renewable_share_fraction": share,
        "renewable_target_fraction": target,
        "realized_shortfall_kwh": shortfall,
        "target_achieved": shortfall <= 1e-6,
        "grid_delivery_kwh": state.cumulative_grid_by_tenant_kwh[tenant_id],
        "direct_pv_kwh": state.cumulative_pv_by_tenant_kwh[tenant_id],
        "dppa_kwh": state.cumulative_dppa_by_tenant_kwh[tenant_id],
        "battery_delivery_kwh": state.cumulative_battery_by_tenant_kwh[tenant_id],
    }


def solver_diagnostics(session: LiveControlSession) -> dict[str, Any]:
    """Return solver and validation diagnostics for display."""

    plan = session.latest_plan
    validation = session.latest_validation
    if plan is None:
        return {
            "controller": session.controller_id,
            "solver_status": "not applicable",
            "fallback_used": session.fallback_visible,
            "fallback_reason": session.fallback_reason,
            "validation_valid": bool(getattr(validation, "valid", False)) if validation else False,
        }
    return {
        "controller": session.controller_id,
        "solver_status": plan.solver_diagnostics.solver_status,
        "solver_name": plan.solver_diagnostics.solver_name,
        "solve_time_seconds": plan.solver_diagnostics.solve_time_seconds,
        "direction_repair_applied": plan.solver_diagnostics.direction_repair_applied,
        "fallback_used": plan.solver_diagnostics.fallback_used,
        "fallback_reason": plan.fallback_reason,
        "validation_valid": bool(getattr(validation, "valid", False)) if validation else False,
        "active_constraints": ", ".join(plan.constraint_diagnostics.active_constraint_codes),
        "warnings": "; ".join(plan.warnings),
    }


def objective_breakdown(session: LiveControlSession) -> pd.DataFrame:
    """Separate actual operating-cost proxy from control penalties."""

    plan = session.latest_plan
    if plan is None:
        return pd.DataFrame()
    obj = asdict(plan.objective_breakdown)
    rows = [
        ("grid_energy_cost_vnd", "operating_cost_proxy"),
        ("dppa_energy_cost_vnd", "operating_cost_proxy"),
        ("battery_degradation_proxy_cost_vnd", "operating_cost_proxy"),
        ("operating_cost_proxy_vnd", "operating_cost_proxy_total"),
        ("grid_peak_penalty_vnd", "control_penalty"),
        ("pv_curtailment_penalty_vnd", "control_penalty"),
        ("renewable_shortfall_penalty_vnd", "control_penalty"),
        ("terminal_reserve_penalty_vnd", "control_penalty"),
        ("total_control_objective", "objective_total"),
    ]
    return pd.DataFrame([{"component": key, "category": category, "value_vnd": float(obj[key])} for key, category in rows])


def benchmark_view(resources: ControlRoomResources, valuation_price_vnd_per_kwh: float) -> pd.DataFrame:
    """Return read-only benchmark metrics with recalculated inventory-adjusted cost."""

    metrics = resources.benchmark_metrics.copy(deep=True)
    if metrics.empty:
        return metrics
    scenarios = tuple(metrics["scenario_id"].drop_duplicates())
    controllers = tuple(metrics["controller_id"].drop_duplicates())
    adjusted = terminal_inventory_adjusted_costs_from_histories(
        PROJECT_ROOT / resources.evaluation_config.output_directory,
        valuation_price_vnd_per_kwh,
        scenarios,
        controllers,
    )
    adjusted = rank_inventory_adjusted_costs(adjusted)
    merged = metrics.merge(
        adjusted[
            [
                "scenario_id",
                "controller_id",
                "terminal_inventory_adjustment_vnd",
                "inventory_adjusted_operating_cost_vnd",
                "inventory_adjusted_rank",
            ]
        ],
        on=["scenario_id", "controller_id"],
        how="left",
    )
    return merged


def provenance_summary(resources: ControlRoomResources, scenario_id: str) -> dict[str, Any]:
    """Build compact provenance and assumption display data without local paths."""

    manifest = resources.dataset_manifest
    model = resources.model_manifest
    fingerprints = manifest.get("output_fingerprints", manifest.get("fingerprints", {}))
    return {
        "dataset_version": manifest.get("dataset_version", "unknown"),
        "model_version": model.get("model_version", "unknown"),
        "controller_version": resources.mpc_config.general.controller_name,
        "scenario_id": scenario_id,
        "pv_formula_version": _find_lineage_value(resources.processed_lineage, "pv_available_kw", "pv_formula_version"),
        "tenant_dataset_fingerprint": model.get("tenant_dataset_fingerprint", fingerprints.get("tenant_hourly.csv", "unknown")),
        "park_dataset_fingerprint": model.get("park_dataset_fingerprint", fingerprints.get("park_hourly.csv", "unknown")),
        "disclosures": [
            "The industrial-park dataset combines measured public load-profile shapes with Vietnam weather data and transparent scenario assumptions.",
            "PV availability is physically derived from NASA POWER irradiance and is not measured inverter output.",
            "Tariff category, DPPA volume, DPPA price, tenant industry labels, and stress events are scenario assumptions.",
            "No actual VRG operational data or official renewable certificate claim is used.",
        ],
    }


def action_preview(session: LiveControlSession) -> pd.DataFrame:
    """Flatten the latest first action for review before execution."""

    action = session.latest_action
    if action is None:
        return pd.DataFrame()
    rows = []
    for tenant_id in action.pv_to_tenant_kw:
        rows.append(
            {
                "tenant_id": tenant_id,
                "pv_kw": action.pv_to_tenant_kw[tenant_id],
                "battery_kw": action.battery_to_tenant_kw[tenant_id],
                "dppa_kw": action.dppa_to_tenant_kw[tenant_id],
                "grid_kw": action.grid_to_tenant_kw[tenant_id],
            }
        )
    rows.append(
        {
            "tenant_id": "park",
            "pv_kw": action.pv_to_battery_kw,
            "battery_kw": 0.0,
            "dppa_kw": action.dppa_to_battery_kw,
            "grid_kw": 0.0,
            "notes": f"curtailment_kw={action.pv_curtailment_kw:.3f}",
        }
    )
    return pd.DataFrame(rows)


def _find_lineage_value(lineage: dict[str, Any], key: str, nested_key: str) -> str:
    raw = lineage.get(key, {})
    if isinstance(raw, dict):
        if nested_key in raw:
            return str(raw[nested_key])
        text = json.dumps(raw)
        if "simple_capacity_factor_v2" in text:
            return "simple_capacity_factor_v2"
    return "simple_capacity_factor_v2"
