from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from greenmpc.config import load_config
from greenmpc.simulation.actions import ParkAction
from greenmpc.simulation.state import BatteryState, CumulativeMetrics, ExogenousState, ParkState


TENANTS = ["Electronics_A", "Semiconductor_B", "Textile_C", "Warehouse_D", "Electronics_E"]


def config():
    return load_config("configs/demo.yaml")


def state(load_kw: float = 100.0, pv_kw: float = 150.0, dppa_kw: float = 500.0, battery_energy: float | None = None) -> ParkState:
    cfg = config()
    timestamp = datetime(2013, 1, 2, 8, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    loads = {tenant: load_kw for tenant in TENANTS}
    battery = BatteryState.from_config(cfg.battery)
    if battery_energy is not None:
        battery = BatteryState.from_energy(
            energy_kwh=battery_energy,
            renewable_energy_kwh=min(battery_energy, battery.renewable_energy_kwh),
            energy_capacity_kwh=cfg.battery.energy_capacity_kwh,
            minimum_soc_fraction=cfg.battery.minimum_soc_fraction,
            maximum_soc_fraction=cfg.battery.maximum_soc_fraction,
            max_charge_power_kw=cfg.battery.max_charge_power_kw,
            max_discharge_power_kw=cfg.battery.max_discharge_power_kw,
        )
    exogenous = ExogenousState(
        timestamp_local=timestamp,
        timestamp_utc=timestamp.astimezone(timezone.utc),
        baseline_tenant_load_kw=loads,
        effective_tenant_load_kw=loads,
        baseline_pv_available_kw=pv_kw,
        effective_pv_available_kw=pv_kw,
        grid_price_vnd_per_kwh=1000.0,
        tariff_period="normal",
        dppa_available_kw=dppa_kw,
        dppa_price_vnd_per_kwh=900.0,
        transformer_capacity_kw=1000.0,
        data_quality_flags={"dataset": "ok"},
    )
    zeros = {tenant: 0.0 for tenant in TENANTS}
    return ParkState(
        step_index=0,
        timestamp_local=timestamp,
        timestamp_utc=timestamp.astimezone(timezone.utc),
        battery=battery,
        exogenous=exogenous,
        cumulative=CumulativeMetrics(),
        cumulative_load_by_tenant_kwh=zeros,
        cumulative_renewable_by_tenant_kwh=zeros,
        cumulative_grid_by_tenant_kwh=zeros,
        cumulative_pv_by_tenant_kwh=zeros,
        cumulative_dppa_by_tenant_kwh=zeros,
        cumulative_battery_by_tenant_kwh=zeros,
    )


def balanced_action(s: ParkState) -> ParkAction:
    pv_each = s.exogenous.effective_pv_available_kw / len(TENANTS)
    return ParkAction(
        action_id="A1",
        timestamp_local=s.timestamp_local,
        controller_name="test_external_controller",
        controller_mode="unit_test",
        created_at_utc=datetime.now(timezone.utc),
        pv_to_tenant_kw={tenant: pv_each for tenant in TENANTS},
        battery_to_tenant_kw={tenant: 0.0 for tenant in TENANTS},
        dppa_to_tenant_kw={tenant: 0.0 for tenant in TENANTS},
        grid_to_tenant_kw={tenant: s.exogenous.effective_tenant_load_kw[tenant] - pv_each for tenant in TENANTS},
        pv_curtailment_kw=0.0,
    )
