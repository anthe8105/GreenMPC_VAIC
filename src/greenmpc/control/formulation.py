"""Continuous linear MPC formulation."""

from __future__ import annotations

from dataclasses import dataclass

import cvxpy as cp
import numpy as np

from greenmpc.control.config import GreenMPCControlConfig
from greenmpc.control.types import MPCPlanningInput


@dataclass
class MPCVariables:
    pv_to_tenant_kw: cp.Variable
    battery_to_tenant_kw: cp.Variable
    dppa_to_tenant_kw: cp.Variable
    grid_to_tenant_kw: cp.Variable
    pv_to_battery_kw: cp.Variable
    dppa_to_battery_kw: cp.Variable
    pv_curtailment_kw: cp.Variable
    battery_energy_kwh: cp.Variable
    grid_peak_kw: cp.Variable
    renewable_shortfall_kwh: cp.Variable
    terminal_reserve_shortfall_kwh: cp.Variable


@dataclass
class MPCFormulation:
    problem: cp.Problem
    variables: MPCVariables
    expressions: dict[str, object]
    constraints: list[cp.Constraint]


def build_mpc_problem(
    planning: MPCPlanningInput,
    cfg: GreenMPCControlConfig,
    fixed_charge_zero: set[int] | None = None,
    fixed_discharge_zero: set[int] | None = None,
) -> MPCFormulation:
    planning.validate()
    fixed_charge_zero = fixed_charge_zero or set()
    fixed_discharge_zero = fixed_discharge_zero or set()
    tenants = list(planning.tenant_ids)
    tenant_count = len(tenants)
    horizon = planning.horizon_hours
    dt = planning.time_step_hours
    load = np.array([[planning.load_forecast_kw[tenant][k] for k in range(horizon)] for tenant in tenants], dtype=float)
    pv_available = np.array(planning.pv_available_kw, dtype=float)
    dppa_available = np.array(planning.dppa_available_kw, dtype=float)
    grid_price = np.array(planning.grid_price_vnd_per_kwh, dtype=float)
    dppa_price = np.array(planning.dppa_price_vnd_per_kwh, dtype=float)
    transformer = np.array(planning.transformer_capacity_kw, dtype=float)

    var = MPCVariables(
        pv_to_tenant_kw=cp.Variable((tenant_count, horizon), nonneg=True, name="pv_to_tenant_kw"),
        battery_to_tenant_kw=cp.Variable((tenant_count, horizon), nonneg=True, name="battery_to_tenant_kw"),
        dppa_to_tenant_kw=cp.Variable((tenant_count, horizon), nonneg=True, name="dppa_to_tenant_kw"),
        grid_to_tenant_kw=cp.Variable((tenant_count, horizon), nonneg=True, name="grid_to_tenant_kw"),
        pv_to_battery_kw=cp.Variable(horizon, nonneg=True, name="pv_to_battery_kw"),
        dppa_to_battery_kw=cp.Variable(horizon, nonneg=True, name="dppa_to_battery_kw"),
        pv_curtailment_kw=cp.Variable(horizon, nonneg=True, name="pv_curtailment_kw"),
        battery_energy_kwh=cp.Variable(horizon + 1, name="battery_energy_kwh"),
        grid_peak_kw=cp.Variable(nonneg=True, name="grid_peak_kw"),
        renewable_shortfall_kwh=cp.Variable(tenant_count, nonneg=True, name="renewable_shortfall_kwh"),
        terminal_reserve_shortfall_kwh=cp.Variable(nonneg=True, name="terminal_reserve_shortfall_kwh"),
    )

    battery_charge_kw = var.pv_to_battery_kw + var.dppa_to_battery_kw
    battery_discharge_kw = cp.sum(var.battery_to_tenant_kw, axis=0)
    grid_import_kw = cp.sum(var.grid_to_tenant_kw, axis=0)
    dppa_import_kw = cp.sum(var.dppa_to_tenant_kw, axis=0) + var.dppa_to_battery_kw
    external_import_kw = grid_import_kw + dppa_import_kw
    renewable_delivery_kw = var.pv_to_tenant_kw + var.dppa_to_tenant_kw + var.battery_to_tenant_kw

    constraints: list[cp.Constraint] = []
    constraints.append(var.pv_to_tenant_kw + var.battery_to_tenant_kw + var.dppa_to_tenant_kw + var.grid_to_tenant_kw == load)
    constraints.append(cp.sum(var.pv_to_tenant_kw, axis=0) + var.pv_to_battery_kw + var.pv_curtailment_kw == pv_available)
    constraints.append(dppa_import_kw <= dppa_available)
    constraints.append(var.battery_energy_kwh[0] == planning.initial_energy_kwh)
    for k in range(horizon):
        constraints.append(
            var.battery_energy_kwh[k + 1]
            == var.battery_energy_kwh[k]
            + planning.charge_efficiency * battery_charge_kw[k] * dt
            - battery_discharge_kw[k] * dt / planning.discharge_efficiency
        )
    constraints.append(var.battery_energy_kwh >= planning.minimum_energy_kwh)
    constraints.append(var.battery_energy_kwh <= planning.maximum_energy_kwh)
    constraints.append(battery_charge_kw <= planning.maximum_charge_power_kw)
    constraints.append(battery_discharge_kw <= planning.maximum_discharge_power_kw)
    constraints.append(external_import_kw <= transformer)
    constraints.append(var.grid_peak_kw >= grid_import_kw)
    for interval in fixed_charge_zero:
        constraints.append(battery_charge_kw[interval] == 0)
    for interval in fixed_discharge_zero:
        constraints.append(battery_discharge_kw[interval] == 0)

    if cfg.renewable_targets.enabled:
        cumulative_load = np.array([planning.cumulative_load_kwh[tenant] for tenant in tenants], dtype=float)
        cumulative_renewable = np.array([planning.cumulative_renewable_delivery_kwh[tenant] for tenant in tenants], dtype=float)
        targets = np.array([planning.renewable_target_fraction[tenant] for tenant in tenants], dtype=float)
        planned_load = cp.sum(load, axis=1) * dt
        planned_renewable = cp.sum(renewable_delivery_kw, axis=1) * dt
        constraints.append(cumulative_renewable + planned_renewable + var.renewable_shortfall_kwh >= cp.multiply(targets, cumulative_load + planned_load))

    if cfg.battery.terminal_reserve_enabled:
        terminal_target = planning.energy_capacity_kwh * cfg.battery.terminal_soc_target_fraction
        constraints.append(var.battery_energy_kwh[horizon] + var.terminal_reserve_shortfall_kwh >= terminal_target)

    w = cfg.objective.weights
    grid_cost = cp.sum(cp.multiply(grid_import_kw, grid_price)) * dt
    dppa_cost = cp.sum(cp.multiply(dppa_import_kw, dppa_price)) * dt
    degradation = cp.sum(battery_charge_kw + battery_discharge_kw) * dt * planning.degradation_cost_vnd_per_kwh_throughput * w.battery_throughput_multiplier
    grid_peak_penalty = var.grid_peak_kw * w.grid_peak_penalty_vnd_per_kw
    curtailment_penalty = cp.sum(var.pv_curtailment_kw) * dt * w.pv_curtailment_penalty_vnd_per_kwh
    renewable_penalty = cp.sum(var.renewable_shortfall_kwh) * w.renewable_shortfall_penalty_vnd_per_kwh
    terminal_penalty = var.terminal_reserve_shortfall_kwh * w.terminal_reserve_shortfall_penalty_vnd_per_kwh
    objective = grid_cost + dppa_cost + degradation + grid_peak_penalty + curtailment_penalty + renewable_penalty + terminal_penalty

    problem = cp.Problem(cp.Minimize(objective), constraints)
    expressions = {
        "load": load,
        "battery_charge_kw": battery_charge_kw,
        "battery_discharge_kw": battery_discharge_kw,
        "grid_import_kw": grid_import_kw,
        "dppa_import_kw": dppa_import_kw,
        "external_import_kw": external_import_kw,
        "renewable_delivery_kw": renewable_delivery_kw,
        "grid_cost": grid_cost,
        "dppa_cost": dppa_cost,
        "degradation": degradation,
        "grid_peak_penalty": grid_peak_penalty,
        "curtailment_penalty": curtailment_penalty,
        "renewable_penalty": renewable_penalty,
        "terminal_penalty": terminal_penalty,
    }
    return MPCFormulation(problem=problem, variables=var, expressions=expressions, constraints=constraints)


def assert_continuous_lp(formulation: MPCFormulation) -> None:
    if not formulation.problem.is_dcp():
        raise ValueError("MPC problem must be DCP")
    for variable in formulation.problem.variables():
        if variable.attributes.get("boolean") or variable.attributes.get("integer"):
            raise ValueError(f"MPC variable {variable.name()} must be continuous")
