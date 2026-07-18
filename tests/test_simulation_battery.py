from __future__ import annotations

from greenmpc.simulation.accounting import compute_step_accounting
from greenmpc.simulation.validation import validate_action
from tests._simulation_helpers import TENANTS, balanced_action, state


def test_charging_transition_applies_efficiency(sim_config) -> None:
    s = state(load_kw=0.0, pv_kw=100.0)
    action = balanced_action(s).copy_with(pv_to_tenant_kw={tenant: 0.0 for tenant in TENANTS}, pv_to_battery_kw=100.0)
    accounting = compute_step_accounting(
        previous_battery=s.battery,
        previous_cumulative=s.cumulative,
        previous_load_by_tenant=dict(s.cumulative_load_by_tenant_kwh),
        previous_renewable_by_tenant=dict(s.cumulative_renewable_by_tenant_kwh),
        previous_grid_by_tenant=dict(s.cumulative_grid_by_tenant_kwh),
        previous_pv_by_tenant=dict(s.cumulative_pv_by_tenant_kwh),
        previous_dppa_by_tenant=dict(s.cumulative_dppa_by_tenant_kwh),
        previous_battery_by_tenant=dict(s.cumulative_battery_by_tenant_kwh),
        exogenous=s.exogenous,
        action=action,
        tenant_targets={tenant: 0.5 for tenant in TENANTS},
        config=sim_config,
    )
    assert accounting.next_battery.energy_kwh == s.battery.energy_kwh + 95.0


def test_simultaneous_charge_discharge_fails(sim_config) -> None:
    s = state()
    action = balanced_action(s).copy_with(pv_to_battery_kw=1.0, battery_to_tenant_kw={tenant: 1.0 for tenant in TENANTS}, pv_curtailment_kw=-1.0)
    assert not validate_action(s, action, sim_config).valid


def test_minimum_soc_enforced(sim_config) -> None:
    s = state(battery_energy=sim_config.battery.energy_capacity_kwh * sim_config.battery.minimum_soc_fraction)
    action = balanced_action(s).copy_with(battery_to_tenant_kw={tenant: 10.0 for tenant in TENANTS})
    assert not validate_action(s, action, sim_config).valid
