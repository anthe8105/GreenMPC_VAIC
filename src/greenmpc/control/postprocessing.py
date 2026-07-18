"""Post-solve MPC plan extraction and validation."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
import pandas as pd

from greenmpc.control.config import GreenMPCControlConfig
from greenmpc.control.exceptions import MPCPostprocessingError
from greenmpc.control.formulation import MPCFormulation
from greenmpc.control.types import (
    MPCConstraintDiagnostics,
    MPCMode,
    MPCObjectiveBreakdown,
    MPCPlanningInput,
    MPCPlanResult,
    MPCSolverDiagnostics,
)
from greenmpc.simulation.actions import ParkAction
from greenmpc.simulation.park import IndustrialParkSimulator


def extract_plan_result(
    *,
    formulation: MPCFormulation,
    planning: MPCPlanningInput,
    cfg: GreenMPCControlConfig,
    simulator: IndustrialParkSimulator | None,
    solver_diagnostics: MPCSolverDiagnostics,
    direction_repair_applied: bool,
    fallback_action: ParkAction | None = None,
    fallback_reason: str | None = None,
) -> MPCPlanResult:
    plan_id = f"MPC-{uuid4().hex[:12]}"
    values = _values(formulation)
    tenant_plan = _tenant_plan(plan_id, planning, values)
    park_plan = _park_plan(plan_id, planning, values)
    objective = _objective_breakdown(formulation)
    constraints = _constraint_diagnostics(planning, values, cfg, direction_repair_applied)
    first_action = _first_action(plan_id, planning, values, cfg, solver_diagnostics)
    validation = simulator.validate_action(first_action) if simulator is not None else None
    valid = validation.valid if validation is not None else True
    if validation is not None and not validation.valid:
        raise MPCPostprocessingError(f"extracted first action failed simulator validation: {validation.violations[0].message}")
    return MPCPlanResult(
        plan_id=plan_id,
        controller_name=cfg.general.controller_name,
        controller_mode=planning.controller_mode,
        created_at_utc=datetime.now(timezone.utc),
        planning_input=planning,
        objective_breakdown=objective,
        solver_diagnostics=solver_diagnostics,
        constraint_diagnostics=constraints,
        tenant_plan=tenant_plan,
        park_plan=park_plan,
        first_action=first_action,
        valid_for_execution=valid,
        simulator_validation_result=validation,
        fallback_action=fallback_action,
        fallback_reason=fallback_reason,
        warnings=tuple(constraints.active_constraint_codes),
        metadata={"continuous_lp": True, "dispatch_intervals": 6},
    )


def _values(formulation: MPCFormulation) -> dict[str, np.ndarray | float]:
    var = formulation.variables
    result = {
        "pv_to_tenant_kw": _clean(var.pv_to_tenant_kw.value),
        "battery_to_tenant_kw": _clean(var.battery_to_tenant_kw.value),
        "dppa_to_tenant_kw": _clean(var.dppa_to_tenant_kw.value),
        "grid_to_tenant_kw": _clean(var.grid_to_tenant_kw.value),
        "pv_to_battery_kw": _clean(var.pv_to_battery_kw.value),
        "dppa_to_battery_kw": _clean(var.dppa_to_battery_kw.value),
        "pv_curtailment_kw": _clean(var.pv_curtailment_kw.value),
        "battery_energy_kwh": _clean(var.battery_energy_kwh.value),
        "grid_peak_kw": float(_clean(var.grid_peak_kw.value)),
        "renewable_shortfall_kwh": _clean(var.renewable_shortfall_kwh.value),
        "terminal_reserve_shortfall_kwh": float(_clean(var.terminal_reserve_shortfall_kwh.value)),
    }
    for name, value in result.items():
        arr = np.asarray(value)
        if not np.isfinite(arr).all():
            raise MPCPostprocessingError(f"nonfinite solved value for {name}")
    return result


def _clean(value):
    arr = np.asarray(value, dtype=float)
    arr[np.abs(arr) < 1e-8] = 0.0
    return arr


def _tenant_plan(plan_id: str, planning: MPCPlanningInput, values: dict) -> pd.DataFrame:
    rows = []
    tenants = list(planning.tenant_ids)
    for k, timestamp in enumerate(planning.planning_timestamps_local):
        for i, tenant in enumerate(tenants):
            renewable = values["pv_to_tenant_kw"][i, k] + values["dppa_to_tenant_kw"][i, k] + values["battery_to_tenant_kw"][i, k]
            rows.append({
                "plan_id": plan_id,
                "timestamp_local": pd.Timestamp(timestamp).isoformat(),
                "timestamp_utc": pd.Timestamp(planning.planning_timestamps_utc[k]).isoformat(),
                "interval_index": k,
                "tenant_id": tenant,
                "forecast_load_kw": planning.load_forecast_kw[tenant][k],
                "pv_to_tenant_kw": values["pv_to_tenant_kw"][i, k],
                "battery_to_tenant_kw": values["battery_to_tenant_kw"][i, k],
                "dppa_to_tenant_kw": values["dppa_to_tenant_kw"][i, k],
                "grid_to_tenant_kw": values["grid_to_tenant_kw"][i, k],
                "renewable_delivery_kw": renewable,
                "renewable_target_fraction": planning.renewable_target_fraction[tenant],
                "cumulative_target_shortfall_kwh": values["renewable_shortfall_kwh"][i],
            })
    return pd.DataFrame(rows)


def _park_plan(plan_id: str, planning: MPCPlanningInput, values: dict) -> pd.DataFrame:
    rows = []
    for k, timestamp in enumerate(planning.planning_timestamps_local):
        pv_to_tenants = float(values["pv_to_tenant_kw"][:, k].sum())
        dppa_import = float(values["dppa_to_tenant_kw"][:, k].sum() + values["dppa_to_battery_kw"][k])
        grid_import = float(values["grid_to_tenant_kw"][:, k].sum())
        external = grid_import + dppa_import
        charge = float(values["pv_to_battery_kw"][k] + values["dppa_to_battery_kw"][k])
        discharge = float(values["battery_to_tenant_kw"][:, k].sum())
        rows.append({
            "plan_id": plan_id,
            "timestamp_local": pd.Timestamp(timestamp).isoformat(),
            "timestamp_utc": pd.Timestamp(planning.planning_timestamps_utc[k]).isoformat(),
            "interval_index": k,
            "pv_available_kw": planning.pv_available_kw[k],
            "pv_to_tenants_kw": pv_to_tenants,
            "pv_to_battery_kw": values["pv_to_battery_kw"][k],
            "pv_curtailment_kw": values["pv_curtailment_kw"][k],
            "battery_charge_kw": charge,
            "battery_discharge_kw": discharge,
            "battery_energy_start_kwh": values["battery_energy_kwh"][k],
            "battery_energy_end_kwh": values["battery_energy_kwh"][k + 1],
            "battery_soc_start": values["battery_energy_kwh"][k] / planning.energy_capacity_kwh,
            "battery_soc_end": values["battery_energy_kwh"][k + 1] / planning.energy_capacity_kwh,
            "dppa_available_kw": planning.dppa_available_kw[k],
            "dppa_import_kw": dppa_import,
            "dppa_to_battery_kw": values["dppa_to_battery_kw"][k],
            "grid_import_kw": grid_import,
            "external_import_kw": external,
            "transformer_capacity_kw": planning.transformer_capacity_kw[k],
            "transformer_utilization_fraction": external / planning.transformer_capacity_kw[k],
            "grid_price_vnd_per_kwh": planning.grid_price_vnd_per_kwh[k],
            "dppa_price_vnd_per_kwh": planning.dppa_price_vnd_per_kwh[k],
            "tariff_period": planning.tariff_period[k],
        })
    return pd.DataFrame(rows)


def _objective_breakdown(formulation: MPCFormulation) -> MPCObjectiveBreakdown:
    e = formulation.expressions
    grid = float(e["grid_cost"].value)
    dppa = float(e["dppa_cost"].value)
    degradation = float(e["degradation"].value)
    peak = float(e["grid_peak_penalty"].value)
    curtail = float(e["curtailment_penalty"].value)
    renewable = float(e["renewable_penalty"].value)
    terminal = float(e["terminal_penalty"].value)
    operating = grid + dppa + degradation
    return MPCObjectiveBreakdown(grid, dppa, degradation, operating, peak, curtail, renewable, terminal, operating + peak + curtail + renewable + terminal)


def _constraint_diagnostics(planning: MPCPlanningInput, values: dict, cfg: GreenMPCControlConfig, repair: bool) -> MPCConstraintDiagnostics:
    tenant_balance = values["pv_to_tenant_kw"] + values["battery_to_tenant_kw"] + values["dppa_to_tenant_kw"] + values["grid_to_tenant_kw"]
    load = np.array([[planning.load_forecast_kw[tenant][k] for k in range(6)] for tenant in planning.tenant_ids])
    pv_balance = values["pv_to_tenant_kw"].sum(axis=0) + values["pv_to_battery_kw"] + values["pv_curtailment_kw"] - np.array(planning.pv_available_kw)
    dppa_margin = np.array(planning.dppa_available_kw) - (values["dppa_to_tenant_kw"].sum(axis=0) + values["dppa_to_battery_kw"])
    external = values["grid_to_tenant_kw"].sum(axis=0) + values["dppa_to_tenant_kw"].sum(axis=0) + values["dppa_to_battery_kw"]
    transformer_margin = np.array(planning.transformer_capacity_kw) - external
    charge = values["pv_to_battery_kw"] + values["dppa_to_battery_kw"]
    discharge = values["battery_to_tenant_kw"].sum(axis=0)
    conflicts = tuple(int(i) for i, (c, d) in enumerate(zip(charge, discharge)) if c > cfg.battery.simultaneous_power_tolerance_kw and d > cfg.battery.simultaneous_power_tolerance_kw)
    codes = []
    tol = cfg.general.numerical_tolerance_kw
    if np.any(values["pv_curtailment_kw"] > tol):
        codes.append("PV_CURTAILMENT_PRESENT")
    if np.any(transformer_margin <= tol):
        codes.append("TRANSFORMER_LIMIT_ACTIVE")
    if np.any(dppa_margin <= tol):
        codes.append("DPPA_LIMIT_ACTIVE")
    if np.any(values["renewable_shortfall_kwh"] > tol):
        codes.append("RENEWABLE_TARGET_SHORTFALL")
    if float(values["terminal_reserve_shortfall_kwh"]) > tol:
        codes.append("TERMINAL_RESERVE_SHORTFALL")
    if repair:
        codes.append("DIRECTION_REPAIR_APPLIED")
    return MPCConstraintDiagnostics(
        minimum_battery_energy_margin_kwh=float((values["battery_energy_kwh"] - planning.minimum_energy_kwh).min()),
        maximum_battery_energy_margin_kwh=float((planning.maximum_energy_kwh - values["battery_energy_kwh"]).min()),
        maximum_transformer_margin_kw=float(transformer_margin.min()),
        maximum_dppa_margin_kw=float(dppa_margin.min()),
        maximum_pv_balance_residual_kw=float(np.abs(pv_balance).max()),
        maximum_tenant_balance_residual_kw=float(np.abs(tenant_balance - load).max()),
        simultaneous_conflict_intervals=conflicts,
        active_constraint_codes=tuple(codes),
        renewable_shortfall_by_tenant_kwh={tenant: float(values["renewable_shortfall_kwh"][i]) for i, tenant in enumerate(planning.tenant_ids)},
        terminal_reserve_shortfall_kwh=float(values["terminal_reserve_shortfall_kwh"]),
    )


def _first_action(plan_id: str, planning: MPCPlanningInput, values: dict, cfg: GreenMPCControlConfig, diag: MPCSolverDiagnostics) -> ParkAction:
    tenants = list(planning.tenant_ids)
    return ParkAction(
        action_id=f"{plan_id}-A0",
        timestamp_local=planning.decision_timestamp_local,
        controller_name=cfg.general.controller_name,
        controller_mode=planning.controller_mode.value,
        created_at_utc=datetime.now(timezone.utc),
        pv_to_tenant_kw={tenant: float(values["pv_to_tenant_kw"][i, 0]) for i, tenant in enumerate(tenants)},
        battery_to_tenant_kw={tenant: float(values["battery_to_tenant_kw"][i, 0]) for i, tenant in enumerate(tenants)},
        dppa_to_tenant_kw={tenant: float(values["dppa_to_tenant_kw"][i, 0]) for i, tenant in enumerate(tenants)},
        grid_to_tenant_kw={tenant: float(values["grid_to_tenant_kw"][i, 0]) for i, tenant in enumerate(tenants)},
        pv_to_battery_kw=float(values["pv_to_battery_kw"][0]),
        dppa_to_battery_kw=float(values["dppa_to_battery_kw"][0]),
        pv_curtailment_kw=float(values["pv_curtailment_kw"][0]),
        forecast_origin=planning.forecast_origin_local.isoformat(),
        planning_horizon_hours=planning.horizon_hours,
        source_plan_id=plan_id,
        notes="GreenMPC continuous-LP first action; controller does not execute simulator step.",
        metadata={
            "mode": planning.controller_mode.value,
            "load_quantile": planning.forecast_quantiles_used["load"],
            "solar_quantile": planning.forecast_quantiles_used["solar"],
            "solver": diag.solver_name,
            "solver_status": diag.solver_status,
            "solve_time_seconds": diag.solve_time_seconds,
            "direction_repair_applied": diag.direction_repair_applied,
            "load_forecast_id": planning.load_forecast_id,
            "solar_forecast_id": planning.solar_forecast_id,
            "tenant_dataset_fingerprint": planning.tenant_dataset_fingerprint,
            "park_dataset_fingerprint": planning.park_dataset_fingerprint,
            "fallback_used": diag.fallback_used,
        },
    )
