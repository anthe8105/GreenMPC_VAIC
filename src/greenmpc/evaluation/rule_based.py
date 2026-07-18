"""Production rule-based evaluation baseline for Stage 6."""

from __future__ import annotations

from datetime import datetime, timezone

from greenmpc.config import GreenMPCConfig
from greenmpc.simulation.actions import ParkAction
from greenmpc.simulation.exceptions import SimulationError
from greenmpc.simulation.state import ParkState


def build_rule_based_action(state: ParkState, config: GreenMPCConfig, action_id: str | None = None) -> ParkAction:
    """Create a deterministic current-observation-only baseline action.

    Rule order: direct PV to load, excess PV to battery, DPPA to remaining
    load, peak/transformer battery discharge, then grid. It uses no forecasts
    and no optimization and is intentionally distinct from Stage 5 fallback.
    """

    tenant_ids = list(state.exogenous.effective_tenant_load_kw.keys())
    remaining = dict(state.exogenous.effective_tenant_load_kw)
    pv_to_tenant = {tenant: 0.0 for tenant in tenant_ids}
    battery_to_tenant = {tenant: 0.0 for tenant in tenant_ids}
    dppa_to_tenant = {tenant: 0.0 for tenant in tenant_ids}
    grid_to_tenant = {tenant: 0.0 for tenant in tenant_ids}

    pv_remaining = float(state.exogenous.effective_pv_available_kw)
    for tenant in tenant_ids:
        amount = min(remaining[tenant], pv_remaining)
        pv_to_tenant[tenant] = amount
        remaining[tenant] -= amount
        pv_remaining -= amount

    total_remaining = sum(remaining.values())
    required_for_transformer = max(0.0, total_remaining - state.exogenous.transformer_capacity_kw)
    desired_discharge = required_for_transformer
    discharge_possible = max(
        0.0,
        min(
            state.battery.max_discharge_power_kw,
            (state.battery.energy_kwh - state.battery.minimum_energy_kwh)
            * config.battery.discharge_efficiency
            / config.simulation.time_step_hours,
        ),
    )
    discharge_remaining = min(desired_discharge, discharge_possible)
    pv_to_battery = 0.0
    for tenant in tenant_ids:
        amount = min(remaining[tenant], discharge_remaining)
        battery_to_tenant[tenant] = amount
        remaining[tenant] -= amount
        discharge_remaining -= amount

    # Only charge excess PV when this hour does not need meaningful battery discharge.
    if sum(battery_to_tenant.values()) <= config.battery.simultaneous_power_tolerance_kw:
        charge_headroom = max(
            0.0,
            min(
                state.battery.max_charge_power_kw,
                (state.battery.maximum_energy_kwh - state.battery.energy_kwh)
                / max(config.battery.charge_efficiency * config.simulation.time_step_hours, 1e-12),
            ),
        )
        pv_to_battery = min(pv_remaining, charge_headroom)
        pv_remaining -= pv_to_battery

    external_used = 0.0
    dppa_remaining = float(state.exogenous.dppa_available_kw)
    for tenant in tenant_ids:
        amount = min(remaining[tenant], dppa_remaining, state.exogenous.transformer_capacity_kw - external_used)
        dppa_to_tenant[tenant] = amount
        remaining[tenant] -= amount
        dppa_remaining -= amount
        external_used += amount

    for tenant in tenant_ids:
        amount = min(remaining[tenant], state.exogenous.transformer_capacity_kw - external_used)
        grid_to_tenant[tenant] = amount
        remaining[tenant] -= amount
        external_used += amount

    if sum(remaining.values()) > config.simulation.action_tolerance_kw:
        raise SimulationError(f"rule_based cannot serve {sum(remaining.values()):.6f} kW at {state.timestamp_local}")

    return ParkAction(
        action_id=action_id or f"RB-{state.step_index:06d}",
        timestamp_local=state.timestamp_local,
        controller_name="rule_based",
        controller_mode="current_observation_policy",
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
        notes="Stage 6 rule-based evaluation baseline; no forecasts and no optimization.",
        metadata={"uses_forecast": False, "uses_optimization": False, "stage5_fallback": False},
    )
