from __future__ import annotations

from tests._simulation_helpers import TENANTS, balanced_action, state
from greenmpc.simulation.validation import validate_action


def test_exact_balance_passes(sim_config) -> None:
    assert validate_action(state(), balanced_action(state()), sim_config).valid


def test_under_supply_fails(sim_config) -> None:
    s = state()
    action = balanced_action(s)
    grid = dict(action.grid_to_tenant_kw)
    grid[TENANTS[0]] -= 10.0
    result = validate_action(s, action.copy_with(grid_to_tenant_kw=grid), sim_config)
    assert not result.valid
    assert any(v.code == "tenant_power_balance" for v in result.violations)


def test_pv_balance_requires_curtailment(sim_config) -> None:
    s = state(pv_kw=200.0)
    action = balanced_action(s).copy_with(pv_curtailment_kw=-20.0)
    assert not validate_action(s, action, sim_config).valid


def test_dppa_excess_fails(sim_config) -> None:
    s = state(dppa_kw=1.0)
    action = balanced_action(s).copy_with(dppa_to_battery_kw=2.0)
    assert not validate_action(s, action, sim_config).valid


def test_transformer_excess_fails(sim_config) -> None:
    s = state(load_kw=400.0, pv_kw=0.0)
    action = balanced_action(s)
    assert not validate_action(s, action, sim_config).valid
