"""Strict action validation for one simulator timestep."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from greenmpc.config import GreenMPCConfig
from greenmpc.simulation.actions import ParkAction
from greenmpc.simulation.state import ParkState


@dataclass(frozen=True)
class ConstraintViolation:
    code: str
    category: str
    severity: str
    timestamp: datetime
    tenant_id: str | None
    expected: float | str | None
    actual: float | str | None
    difference: float | None
    tolerance: float | None
    message: str


@dataclass(frozen=True)
class ActionValidationResult:
    valid: bool
    violations: list[ConstraintViolation]
    warnings: list[str] = field(default_factory=list)
    calculated_values: dict[str, Any] = field(default_factory=dict)
    checked_at_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


def validate_action(state: ParkState, action: ParkAction, config: GreenMPCConfig) -> ActionValidationResult:
    violations: list[ConstraintViolation] = []
    warnings: list[str] = []
    exogenous = state.exogenous
    tenant_ids = list(exogenous.effective_tenant_load_kw.keys())
    tolerance_kw = config.simulation.action_tolerance_kw

    if action.timestamp_local != state.timestamp_local:
        violations.append(_violation("timestamp_mismatch", "action_schema", state, None, state.timestamp_local.isoformat(), action.timestamp_local.isoformat(), None, None, "action timestamp must match simulator timestamp"))

    for name in ("pv_to_tenant_kw", "battery_to_tenant_kw", "dppa_to_tenant_kw", "grid_to_tenant_kw"):
        values = getattr(action, name)
        if set(values) != set(tenant_ids):
            violations.append(_violation("tenant_set_mismatch", "action_schema", state, None, ",".join(tenant_ids), ",".join(sorted(values)), None, None, f"{name} must contain all and only configured tenants"))
        for tenant_id, value in values.items():
            if tenant_id not in tenant_ids:
                continue
            if not isfinite(value):
                violations.append(_violation("nonfinite_allocation", "action_schema", state, tenant_id, None, value, None, None, f"{name}[{tenant_id}] must be finite"))
            if isfinite(value) and value < -tolerance_kw:
                violations.append(_violation("negative_allocation", "action_schema", state, tenant_id, 0.0, value, value, tolerance_kw, f"{name}[{tenant_id}] must be nonnegative"))

    for name in ("pv_to_battery_kw", "dppa_to_battery_kw", "pv_curtailment_kw"):
        value = getattr(action, name)
        if not isfinite(value):
            violations.append(_violation("nonfinite_allocation", "action_schema", state, None, None, value, None, None, f"{name} must be finite"))
        if isfinite(value) and value < -tolerance_kw:
            violations.append(_violation("negative_allocation", "action_schema", state, None, 0.0, value, value, tolerance_kw, f"{name} must be nonnegative"))

    if violations:
        return _result(violations, warnings, state, action, config)

    for tenant_id in tenant_ids:
        supplied = (
            action.pv_to_tenant_kw[tenant_id]
            + action.battery_to_tenant_kw[tenant_id]
            + action.dppa_to_tenant_kw[tenant_id]
            + action.grid_to_tenant_kw[tenant_id]
        )
        required = exogenous.effective_tenant_load_kw[tenant_id]
        difference = supplied - required
        if abs(difference) > tolerance_kw:
            violations.append(_violation("tenant_power_balance", "power_balance", state, tenant_id, required, supplied, difference, tolerance_kw, f"Tenant {tenant_id} supply mismatch at {state.timestamp_local}: supplied {supplied:.6f} kW, required {required:.6f} kW, difference {difference:.6f} kW."))

    pv_used = action.total_pv_to_tenants_kw + action.pv_to_battery_kw + action.pv_curtailment_kw
    pv_diff = pv_used - exogenous.effective_pv_available_kw
    if abs(pv_diff) > tolerance_kw:
        violations.append(_violation("pv_balance", "pv", state, None, exogenous.effective_pv_available_kw, pv_used, pv_diff, tolerance_kw, f"PV balance mismatch at {state.timestamp_local}: used plus curtailed {pv_used:.6f} kW, available {exogenous.effective_pv_available_kw:.6f} kW."))

    dppa_used = action.total_dppa_to_tenants_kw + action.dppa_to_battery_kw
    if dppa_used - exogenous.dppa_available_kw > tolerance_kw:
        violations.append(_violation("dppa_availability", "dppa", state, None, exogenous.dppa_available_kw, dppa_used, dppa_used - exogenous.dppa_available_kw, tolerance_kw, f"DPPA use exceeds availability at {state.timestamp_local}."))

    charge_power = action.total_battery_charge_kw
    discharge_power = action.total_battery_discharge_kw
    if charge_power - state.battery.max_charge_power_kw > tolerance_kw:
        violations.append(_violation("battery_charge_power", "battery", state, None, state.battery.max_charge_power_kw, charge_power, charge_power - state.battery.max_charge_power_kw, tolerance_kw, "battery charge power exceeds maximum"))
    if discharge_power - state.battery.max_discharge_power_kw > tolerance_kw:
        violations.append(_violation("battery_discharge_power", "battery", state, None, state.battery.max_discharge_power_kw, discharge_power, discharge_power - state.battery.max_discharge_power_kw, tolerance_kw, "battery discharge power exceeds maximum"))
    if (
        not config.battery.allow_simultaneous_charge_discharge
        and charge_power > config.battery.simultaneous_power_tolerance_kw
        and discharge_power > config.battery.simultaneous_power_tolerance_kw
    ):
        violations.append(_violation("battery_simultaneous_charge_discharge", "battery", state, None, 0.0, min(charge_power, discharge_power), None, config.battery.simultaneous_power_tolerance_kw, "simultaneous meaningful charge and discharge is not allowed"))

    dt = config.simulation.time_step_hours
    next_energy = state.battery.energy_kwh + config.battery.charge_efficiency * charge_power * dt - discharge_power * dt / config.battery.discharge_efficiency
    if next_energy < state.battery.minimum_energy_kwh - config.simulation.energy_tolerance_kwh:
        violations.append(_violation("battery_min_energy", "battery", state, None, state.battery.minimum_energy_kwh, next_energy, next_energy - state.battery.minimum_energy_kwh, config.simulation.energy_tolerance_kwh, "battery next energy is below minimum"))
    if next_energy > state.battery.maximum_energy_kwh + config.simulation.energy_tolerance_kwh:
        violations.append(_violation("battery_max_energy", "battery", state, None, state.battery.maximum_energy_kwh, next_energy, next_energy - state.battery.maximum_energy_kwh, config.simulation.energy_tolerance_kwh, "battery next energy is above maximum"))

    external_import = action.total_external_import_kw
    if external_import - exogenous.transformer_capacity_kw > tolerance_kw:
        violations.append(_violation("transformer_capacity", "transformer", state, None, exogenous.transformer_capacity_kw, external_import, external_import - exogenous.transformer_capacity_kw, tolerance_kw, "external import exceeds transformer capacity"))

    return _result(violations, warnings, state, action, config)


def _result(violations: list[ConstraintViolation], warnings: list[str], state: ParkState, action: ParkAction, config: GreenMPCConfig) -> ActionValidationResult:
    charge = action.total_battery_charge_kw
    discharge = action.total_battery_discharge_kw
    next_energy = state.battery.energy_kwh + config.battery.charge_efficiency * charge * config.simulation.time_step_hours - discharge * config.simulation.time_step_hours / config.battery.discharge_efficiency
    return ActionValidationResult(
        valid=not violations,
        violations=violations,
        warnings=warnings,
        calculated_values={
            "total_pv_to_tenants_kw": action.total_pv_to_tenants_kw,
            "total_battery_charge_kw": charge,
            "total_battery_discharge_kw": discharge,
            "total_dppa_kw": action.total_dppa_to_tenants_kw + action.dppa_to_battery_kw,
            "total_grid_kw": action.total_grid_to_tenants_kw,
            "external_import_kw": action.total_external_import_kw,
            "battery_next_energy_kwh": next_energy,
        },
    )


def _violation(code: str, category: str, state: ParkState, tenant_id: str | None, expected: Any, actual: Any, difference: float | None, tolerance: float | None, message: str) -> ConstraintViolation:
    return ConstraintViolation(
        code=code,
        category=category,
        severity="error",
        timestamp=state.timestamp_local,
        tenant_id=tenant_id,
        expected=expected,
        actual=actual,
        difference=difference,
        tolerance=tolerance,
        message=message,
    )
