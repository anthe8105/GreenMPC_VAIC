"""Reference feasible-action constructor for simulator verification, not the final operational controller."""

from __future__ import annotations

from datetime import datetime, timezone

from greenmpc.config import GreenMPCConfig
from greenmpc.simulation.actions import ParkAction
from greenmpc.simulation.exceptions import SimulationError
from greenmpc.simulation.state import ParkState


def build_reference_action(state: ParkState, config: GreenMPCConfig, action_id: str | None = None) -> ParkAction:
    """Construct a deterministic feasible action without forecasts or optimization."""

    tenant_ids = list(state.exogenous.effective_tenant_load_kw.keys())
    remaining = dict(state.exogenous.effective_tenant_load_kw)
    pv_to_tenant = {tenant_id: 0.0 for tenant_id in tenant_ids}
    battery_to_tenant = {tenant_id: 0.0 for tenant_id in tenant_ids}
    dppa_to_tenant = {tenant_id: 0.0 for tenant_id in tenant_ids}
    grid_to_tenant = {tenant_id: 0.0 for tenant_id in tenant_ids}

    pv_remaining = state.exogenous.effective_pv_available_kw
    for tenant_id in tenant_ids:
        amount = min(remaining[tenant_id], pv_remaining)
        pv_to_tenant[tenant_id] = amount
        remaining[tenant_id] -= amount
        pv_remaining -= amount

    battery_headroom_charge_kw = max(
        0.0,
        min(
            state.battery.max_charge_power_kw,
            (state.battery.maximum_energy_kwh - state.battery.energy_kwh)
            / max(config.battery.charge_efficiency * config.simulation.time_step_hours, 1e-12),
        ),
    )
    pv_to_battery = min(pv_remaining, battery_headroom_charge_kw)
    pv_remaining -= pv_to_battery

    total_remaining = sum(remaining.values())
    external_limit = state.exogenous.transformer_capacity_kw
    required_discharge = max(0.0, total_remaining - external_limit)
    discharge_possible = max(
        0.0,
        min(
            state.battery.max_discharge_power_kw,
            (state.battery.energy_kwh - state.battery.minimum_energy_kwh)
            * config.battery.discharge_efficiency
            / config.simulation.time_step_hours,
        ),
    )
    discharge = min(required_discharge, discharge_possible)
    for tenant_id in tenant_ids:
        amount = min(remaining[tenant_id], discharge)
        battery_to_tenant[tenant_id] = amount
        remaining[tenant_id] -= amount
        discharge -= amount

    external_used = 0.0
    dppa_available = state.exogenous.dppa_available_kw
    for tenant_id in tenant_ids:
        amount = min(remaining[tenant_id], dppa_available, external_limit - external_used)
        dppa_to_tenant[tenant_id] = amount
        remaining[tenant_id] -= amount
        dppa_available -= amount
        external_used += amount

    for tenant_id in tenant_ids:
        amount = min(remaining[tenant_id], external_limit - external_used)
        grid_to_tenant[tenant_id] = amount
        remaining[tenant_id] -= amount
        external_used += amount

    if sum(remaining.values()) > config.simulation.action_tolerance_kw:
        raise SimulationError(
            f"reference feasible action cannot serve load at {state.timestamp_local}; "
            f"unserved demand would be {sum(remaining.values()):.6f} kW"
        )

    return ParkAction(
        action_id=action_id or f"REF-{state.step_index:06d}",
        timestamp_local=state.timestamp_local,
        controller_name="reference_feasible_action",
        controller_mode="simulator_verification_not_operational_controller",
        created_at_utc=datetime.now(timezone.utc),
        pv_to_tenant_kw=pv_to_tenant,
        battery_to_tenant_kw=battery_to_tenant,
        dppa_to_tenant_kw=dppa_to_tenant,
        grid_to_tenant_kw=grid_to_tenant,
        pv_to_battery_kw=pv_to_battery,
        dppa_to_battery_kw=0.0,
        pv_curtailment_kw=pv_remaining,
        forecast_origin=None,
        planning_horizon_hours=None,
        source_plan_id=None,
        notes="Reference feasible-action constructor for simulator verification, not the final operational controller.",
        metadata={"uses_forecast": False, "uses_optimization": False},
    )
