from __future__ import annotations

from greenmpc.simulation.accounting import compute_step_accounting
from tests._simulation_helpers import TENANTS, balanced_action, state


def test_cost_components_sum(sim_config) -> None:
    s = state(pv_kw=0.0)
    action = balanced_action(s)
    accounting = _accounting(s, action, sim_config)
    park = accounting.park_record
    assert park.step_operating_cost_vnd == park.grid_cost_vnd + park.dppa_cost_vnd + park.battery_degradation_proxy_cost_vnd


def test_renewable_battery_delivery_uses_proportional_mixing(sim_config) -> None:
    s = state(pv_kw=0.0)
    action = balanced_action(s).copy_with(
        battery_to_tenant_kw={TENANTS[0]: 10.0, TENANTS[1]: 0.0, TENANTS[2]: 0.0, TENANTS[3]: 0.0, TENANTS[4]: 0.0},
        grid_to_tenant_kw={TENANTS[0]: 90.0, TENANTS[1]: 100.0, TENANTS[2]: 100.0, TENANTS[3]: 100.0, TENANTS[4]: 100.0},
    )
    record = _accounting(s, action, sim_config).tenant_records[0]
    assert record.renewable_battery_delivery_kwh == 10.0
    assert record.total_renewable_delivery_kwh == 10.0


def test_dppa_to_battery_cost_charged(sim_config) -> None:
    s = state(load_kw=0.0, pv_kw=0.0)
    action = balanced_action(s).copy_with(dppa_to_battery_kw=10.0)
    accounting = _accounting(s, action, sim_config)
    assert accounting.park_record.dppa_cost_vnd == 9000.0


def _accounting(s, action, cfg):
    return compute_step_accounting(
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
        config=cfg,
    )
