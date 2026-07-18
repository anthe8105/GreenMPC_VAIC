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

    action, _ = build_rule_based_action_with_trace(state, config, action_id)
    return action


def build_rule_based_action_with_trace(
    state: ParkState,
    config: GreenMPCConfig,
    action_id: str | None = None,
) -> tuple[ParkAction, dict[str, float | str | bool]]:
    """Create a rule-based action and a battery-decision audit trace."""

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

    load_after_pv = sum(remaining.values())
    pv_surplus_before_charge = max(0.0, pv_remaining)
    charge_headroom = _charge_headroom_kw(state, config)
    discharge_possible = _discharge_possible_kw(state, config)

    pv_to_battery = 0.0
    if pv_remaining > config.simulation.action_tolerance_kw and charge_headroom > config.battery.simultaneous_power_tolerance_kw:
        pv_to_battery = min(pv_remaining, charge_headroom)
        pv_remaining -= pv_to_battery

    dppa_remaining = float(state.exogenous.dppa_available_kw)
    external_used = 0.0
    for tenant in tenant_ids:
        amount = min(remaining[tenant], dppa_remaining, state.exogenous.transformer_capacity_kw - external_used)
        dppa_to_tenant[tenant] = amount
        remaining[tenant] -= amount
        dppa_remaining -= amount
        external_used += amount

    remaining_after_dppa = sum(remaining.values())
    tariff_is_peak = state.exogenous.tariff_period == "peak"
    required_for_transformer = max(0.0, external_used + remaining_after_dppa - state.exogenous.transformer_capacity_kw)
    peak_grid_discharge = remaining_after_dppa if tariff_is_peak else 0.0
    desired_discharge = max(required_for_transformer, peak_grid_discharge)
    discharge_possible = max(
        0.0,
        min(
            state.battery.max_discharge_power_kw,
            (state.battery.energy_kwh - state.battery.minimum_energy_kwh)
            * config.battery.discharge_efficiency
            / config.simulation.time_step_hours,
        ),
    )
    # The simulator rejects meaningful simultaneous charge and discharge. Prefer
    # using surplus PV to charge; otherwise discharge for peak or transformer pressure.
    if pv_to_battery > config.battery.simultaneous_power_tolerance_kw:
        discharge_remaining = 0.0
        branch = "charge_excess_pv"
    else:
        discharge_remaining = min(desired_discharge, discharge_possible)
        if required_for_transformer > config.simulation.action_tolerance_kw:
            branch = "discharge_for_transformer"
        elif tariff_is_peak and discharge_remaining > config.battery.simultaneous_power_tolerance_kw:
            branch = "discharge_for_peak_tariff"
        else:
            branch = "no_battery_condition"
    for tenant in tenant_ids:
        amount = min(remaining[tenant], discharge_remaining)
        battery_to_tenant[tenant] = amount
        remaining[tenant] -= amount
        discharge_remaining -= amount

    for tenant in tenant_ids:
        amount = min(remaining[tenant], state.exogenous.transformer_capacity_kw - external_used)
        grid_to_tenant[tenant] = amount
        remaining[tenant] -= amount
        external_used += amount

    if sum(remaining.values()) > config.simulation.action_tolerance_kw:
        raise SimulationError(f"rule_based cannot serve {sum(remaining.values()):.6f} kW at {state.timestamp_local}")

    trace = {
        "timestamp": state.timestamp_local.isoformat(),
        "tariff_period": state.exogenous.tariff_period,
        "grid_price": state.exogenous.grid_price_vnd_per_kwh,
        "battery_soc": state.battery.soc_fraction,
        "available_discharge_energy_kwh": max(0.0, state.battery.energy_kwh - state.battery.minimum_energy_kwh),
        "available_charge_headroom_kwh": max(0.0, state.battery.maximum_energy_kwh - state.battery.energy_kwh),
        "effective_load_kw": sum(state.exogenous.effective_tenant_load_kw.values()),
        "pv_available_kw": state.exogenous.effective_pv_available_kw,
        "pv_surplus_kw": pv_surplus_before_charge,
        "dppa_available_kw": state.exogenous.dppa_available_kw,
        "transformer_headroom_kw": state.exogenous.transformer_capacity_kw - external_used,
        "decision_branch": branch,
        "charge_power_kw": pv_to_battery,
        "discharge_power_kw": sum(battery_to_tenant.values()),
        "required_for_transformer_kw": required_for_transformer,
        "peak_grid_condition": tariff_is_peak,
        "reason": _trace_reason(branch, pv_surplus_before_charge, charge_headroom, discharge_possible, required_for_transformer, tariff_is_peak),
        "uses_forecast": False,
        "uses_optimization": False,
    }

    action = ParkAction(
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
    return action, trace


def _charge_headroom_kw(state: ParkState, config: GreenMPCConfig) -> float:
    return max(
        0.0,
        min(
            state.battery.max_charge_power_kw,
            (state.battery.maximum_energy_kwh - state.battery.energy_kwh)
            / max(config.battery.charge_efficiency * config.simulation.time_step_hours, 1e-12),
        ),
    )


def _discharge_possible_kw(state: ParkState, config: GreenMPCConfig) -> float:
    return max(
        0.0,
        min(
            state.battery.max_discharge_power_kw,
            (state.battery.energy_kwh - state.battery.minimum_energy_kwh)
            * config.battery.discharge_efficiency
            / config.simulation.time_step_hours,
        ),
    )


def _trace_reason(
    branch: str,
    pv_surplus_kw: float,
    charge_headroom_kw: float,
    discharge_possible_kw: float,
    required_for_transformer_kw: float,
    tariff_is_peak: bool,
) -> str:
    if branch == "charge_excess_pv":
        return f"excess PV {pv_surplus_kw:.3f} kW and charge headroom {charge_headroom_kw:.3f} kW"
    if branch == "discharge_for_transformer":
        return f"external import would exceed transformer by {required_for_transformer_kw:.3f} kW"
    if branch == "discharge_for_peak_tariff":
        return f"peak tariff with usable discharge power {discharge_possible_kw:.3f} kW"
    if pv_surplus_kw <= 0 and not tariff_is_peak and required_for_transformer_kw <= 0:
        return "no PV surplus, non-peak tariff, and no transformer pressure"
    if charge_headroom_kw <= 0:
        return "battery has no charge headroom"
    if discharge_possible_kw <= 0:
        return "battery has no usable discharge energy"
    return "battery use not selected by deterministic rule order"
