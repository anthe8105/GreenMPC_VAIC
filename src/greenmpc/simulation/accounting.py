"""Energy, cost, and renewable-inventory accounting for simulator steps."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from greenmpc.config import GreenMPCConfig
from greenmpc.simulation.actions import ParkAction
from greenmpc.simulation.state import BatteryState, CumulativeMetrics, ExogenousState


@dataclass(frozen=True)
class TenantEnergyRecord:
    record_id: str
    action_id: str
    timestamp_local: datetime
    timestamp_utc: datetime
    tenant_id: str
    effective_load_kwh: float
    rooftop_pv_kwh: float
    battery_delivery_kwh: float
    renewable_battery_delivery_kwh: float
    nonrenewable_or_unclassified_battery_delivery_kwh: float
    dppa_kwh: float
    grid_kwh: float
    direct_renewable_kwh: float
    total_renewable_delivery_kwh: float
    renewable_share_fraction: float
    renewable_target_fraction: float
    step_target_achieved: bool
    controller_name: str
    active_event_ids: tuple[str, ...]
    data_quality_flag: str


@dataclass(frozen=True)
class ParkEnergyRecord:
    timestamp_local: datetime
    total_effective_load_kwh: float
    total_pv_to_tenants_kwh: float
    pv_to_battery_kwh: float
    pv_curtailment_kwh: float
    total_battery_to_tenants_kwh: float
    total_dppa_to_tenants_kwh: float
    dppa_to_battery_kwh: float
    total_grid_to_tenants_kwh: float
    external_import_kwh: float
    transformer_utilization_fraction: float
    battery_energy_before_kwh: float
    battery_energy_after_kwh: float
    battery_soc_before: float
    battery_soc_after: float
    battery_renewable_energy_before_kwh: float
    battery_renewable_energy_after_kwh: float
    grid_cost_vnd: float
    dppa_cost_vnd: float
    battery_degradation_proxy_cost_vnd: float
    step_operating_cost_vnd: float
    active_event_ids: tuple[str, ...]


@dataclass(frozen=True)
class StepAccounting:
    next_battery: BatteryState
    tenant_records: list[TenantEnergyRecord]
    park_record: ParkEnergyRecord
    cumulative: CumulativeMetrics
    cumulative_load_by_tenant_kwh: dict[str, float]
    cumulative_renewable_by_tenant_kwh: dict[str, float]
    cumulative_grid_by_tenant_kwh: dict[str, float]
    cumulative_pv_by_tenant_kwh: dict[str, float]
    cumulative_dppa_by_tenant_kwh: dict[str, float]
    cumulative_battery_by_tenant_kwh: dict[str, float]


def compute_step_accounting(
    *,
    previous_battery: BatteryState,
    previous_cumulative: CumulativeMetrics,
    previous_load_by_tenant: dict[str, float],
    previous_renewable_by_tenant: dict[str, float],
    previous_grid_by_tenant: dict[str, float],
    previous_pv_by_tenant: dict[str, float],
    previous_dppa_by_tenant: dict[str, float],
    previous_battery_by_tenant: dict[str, float],
    exogenous: ExogenousState,
    action: ParkAction,
    tenant_targets: dict[str, float],
    config: GreenMPCConfig,
) -> StepAccounting:
    dt = config.simulation.time_step_hours
    charge_power_kw = action.pv_to_battery_kw + action.dppa_to_battery_kw
    discharge_power_kw = action.total_battery_to_tenants_kw
    charge_energy_into_battery = charge_power_kw * dt * config.battery.charge_efficiency
    discharge_energy_removed = discharge_power_kw * dt / config.battery.discharge_efficiency
    renewable_fraction_before = previous_battery.renewable_fraction if previous_battery.energy_kwh > 0 else 0.0
    dppa_charge_renewable_kw = action.dppa_to_battery_kw if config.dppa.renewable_eligible else 0.0
    renewable_charge_kw = action.pv_to_battery_kw + dppa_charge_renewable_kw
    renewable_added = renewable_charge_kw * dt * config.battery.charge_efficiency
    renewable_removed = discharge_energy_removed * renewable_fraction_before
    next_energy = previous_battery.energy_kwh + charge_energy_into_battery - discharge_energy_removed
    next_renewable = max(0.0, min(next_energy, previous_battery.renewable_energy_kwh + renewable_added - renewable_removed))
    next_battery = BatteryState.from_energy(
        energy_kwh=next_energy,
        renewable_energy_kwh=next_renewable,
        energy_capacity_kwh=config.battery.energy_capacity_kwh,
        minimum_soc_fraction=config.battery.minimum_soc_fraction,
        maximum_soc_fraction=config.battery.maximum_soc_fraction,
        max_charge_power_kw=config.battery.max_charge_power_kw,
        max_discharge_power_kw=config.battery.max_discharge_power_kw,
        last_charge_power_kw=charge_power_kw,
        last_discharge_power_kw=discharge_power_kw,
    )

    tenant_records: list[TenantEnergyRecord] = []
    new_load = dict(previous_load_by_tenant)
    new_renewable = dict(previous_renewable_by_tenant)
    new_grid = dict(previous_grid_by_tenant)
    new_pv = dict(previous_pv_by_tenant)
    new_dppa = dict(previous_dppa_by_tenant)
    new_battery = dict(previous_battery_by_tenant)

    for tenant_id, load_kw in exogenous.effective_tenant_load_kw.items():
        rooftop_pv = action.pv_to_tenant_kw[tenant_id] * dt
        battery_delivery = action.battery_to_tenant_kw[tenant_id] * dt
        renewable_battery_delivery = battery_delivery * renewable_fraction_before
        dppa_energy = action.dppa_to_tenant_kw[tenant_id] * dt
        grid_energy = action.grid_to_tenant_kw[tenant_id] * dt
        load_energy = load_kw * dt
        direct_renewable = rooftop_pv + (dppa_energy if config.dppa.renewable_eligible else 0.0)
        total_renewable = min(load_energy, direct_renewable + renewable_battery_delivery)
        share = 0.0 if load_energy <= 0 else total_renewable / load_energy
        target = tenant_targets[tenant_id]
        tenant_records.append(
            TenantEnergyRecord(
                record_id=f"{action.action_id}:{tenant_id}",
                action_id=action.action_id,
                timestamp_local=exogenous.timestamp_local,
                timestamp_utc=exogenous.timestamp_utc,
                tenant_id=tenant_id,
                effective_load_kwh=load_energy,
                rooftop_pv_kwh=rooftop_pv,
                battery_delivery_kwh=battery_delivery,
                renewable_battery_delivery_kwh=renewable_battery_delivery,
                nonrenewable_or_unclassified_battery_delivery_kwh=battery_delivery - renewable_battery_delivery,
                dppa_kwh=dppa_energy,
                grid_kwh=grid_energy,
                direct_renewable_kwh=direct_renewable,
                total_renewable_delivery_kwh=total_renewable,
                renewable_share_fraction=share,
                renewable_target_fraction=target,
                step_target_achieved=share >= target if load_energy > 0 else False,
                controller_name=action.controller_name,
                active_event_ids=exogenous.active_event_ids,
                data_quality_flag=str(exogenous.data_quality_flags.get("dataset", "ok")),
            )
        )
        new_load[tenant_id] += load_energy
        new_renewable[tenant_id] += total_renewable
        new_grid[tenant_id] += grid_energy
        new_pv[tenant_id] += rooftop_pv
        new_dppa[tenant_id] += dppa_energy
        new_battery[tenant_id] += battery_delivery

    grid_energy = action.total_grid_to_tenants_kw * dt
    dppa_energy = (action.total_dppa_to_tenants_kw + action.dppa_to_battery_kw) * dt
    throughput = (charge_power_kw + discharge_power_kw) * dt
    grid_cost = grid_energy * exogenous.grid_price_vnd_per_kwh
    dppa_cost = dppa_energy * exogenous.dppa_price_vnd_per_kwh
    degradation_cost = throughput * config.battery.degradation_cost_vnd_per_kwh_throughput
    step_cost = grid_cost + dppa_cost + degradation_cost
    total_load = sum(record.effective_load_kwh for record in tenant_records)
    renewable_to_tenants = sum(record.total_renewable_delivery_kwh for record in tenant_records)
    external_import = action.total_external_import_kw * dt
    transformer_utilization = action.total_external_import_kw / exogenous.transformer_capacity_kw

    park_record = ParkEnergyRecord(
        timestamp_local=exogenous.timestamp_local,
        total_effective_load_kwh=total_load,
        total_pv_to_tenants_kwh=action.total_pv_to_tenants_kw * dt,
        pv_to_battery_kwh=action.pv_to_battery_kw * dt,
        pv_curtailment_kwh=action.pv_curtailment_kw * dt,
        total_battery_to_tenants_kwh=discharge_power_kw * dt,
        total_dppa_to_tenants_kwh=action.total_dppa_to_tenants_kw * dt,
        dppa_to_battery_kwh=action.dppa_to_battery_kw * dt,
        total_grid_to_tenants_kwh=grid_energy,
        external_import_kwh=external_import,
        transformer_utilization_fraction=transformer_utilization,
        battery_energy_before_kwh=previous_battery.energy_kwh,
        battery_energy_after_kwh=next_battery.energy_kwh,
        battery_soc_before=previous_battery.soc_fraction,
        battery_soc_after=next_battery.soc_fraction,
        battery_renewable_energy_before_kwh=previous_battery.renewable_energy_kwh,
        battery_renewable_energy_after_kwh=next_battery.renewable_energy_kwh,
        grid_cost_vnd=grid_cost,
        dppa_cost_vnd=dppa_cost,
        battery_degradation_proxy_cost_vnd=degradation_cost,
        step_operating_cost_vnd=step_cost,
        active_event_ids=exogenous.active_event_ids,
    )
    cumulative = replace(
        previous_cumulative,
        elapsed_steps=previous_cumulative.elapsed_steps + 1,
        total_load_energy_kwh=previous_cumulative.total_load_energy_kwh + total_load,
        grid_energy_kwh=previous_cumulative.grid_energy_kwh + grid_energy,
        dppa_energy_kwh=previous_cumulative.dppa_energy_kwh + dppa_energy,
        direct_pv_energy_kwh=previous_cumulative.direct_pv_energy_kwh + action.total_pv_to_tenants_kw * dt,
        battery_discharge_energy_kwh=previous_cumulative.battery_discharge_energy_kwh + discharge_power_kw * dt,
        renewable_energy_to_tenants_kwh=previous_cumulative.renewable_energy_to_tenants_kwh + renewable_to_tenants,
        pv_curtailed_energy_kwh=previous_cumulative.pv_curtailed_energy_kwh + action.pv_curtailment_kw * dt,
        battery_charge_energy_kwh=previous_cumulative.battery_charge_energy_kwh + charge_power_kw * dt,
        battery_throughput_kwh=previous_cumulative.battery_throughput_kwh + throughput,
        grid_cost_vnd=previous_cumulative.grid_cost_vnd + grid_cost,
        dppa_cost_vnd=previous_cumulative.dppa_cost_vnd + dppa_cost,
        battery_degradation_proxy_cost_vnd=previous_cumulative.battery_degradation_proxy_cost_vnd + degradation_cost,
        total_operating_cost_vnd=previous_cumulative.total_operating_cost_vnd + step_cost,
        peak_grid_import_kw=max(previous_cumulative.peak_grid_import_kw, action.total_grid_to_tenants_kw),
        peak_external_import_kw=max(previous_cumulative.peak_external_import_kw, action.total_external_import_kw),
        event_affected_step_count=previous_cumulative.event_affected_step_count + (1 if exogenous.active_event_ids else 0),
    )
    return StepAccounting(
        next_battery=next_battery,
        tenant_records=tenant_records,
        park_record=park_record,
        cumulative=cumulative,
        cumulative_load_by_tenant_kwh=new_load,
        cumulative_renewable_by_tenant_kwh=new_renewable,
        cumulative_grid_by_tenant_kwh=new_grid,
        cumulative_pv_by_tenant_kwh=new_pv,
        cumulative_dppa_by_tenant_kwh=new_dppa,
        cumulative_battery_by_tenant_kwh=new_battery,
    )
