from __future__ import annotations

import math

import pytest

from tests._simulation_helpers import TENANTS, balanced_action, state


def test_action_schema_round_trip() -> None:
    action = balanced_action(state())
    assert action.from_dict(action.to_dict()).to_dict()["action_id"] == "A1"


def test_missing_tenant_fails_validation(sim_config) -> None:
    s = state()
    action = balanced_action(s)
    bad = action.copy_with(pv_to_tenant_kw={tenant: 0.0 for tenant in TENANTS[:-1]})
    assert not __import__("greenmpc.simulation.validation", fromlist=["validate_action"]).validate_action(s, bad, sim_config).valid


def test_unknown_tenant_fails_validation(sim_config) -> None:
    s = state()
    action = balanced_action(s)
    values = dict(action.grid_to_tenant_kw)
    values["Unknown"] = 1.0
    assert not __import__("greenmpc.simulation.validation", fromlist=["validate_action"]).validate_action(s, action.copy_with(grid_to_tenant_kw=values), sim_config).valid


@pytest.mark.parametrize("value", [-1.0, math.nan, math.inf])
def test_invalid_allocation_values_fail(value: float, sim_config) -> None:
    s = state()
    action = balanced_action(s)
    values = dict(action.grid_to_tenant_kw)
    values[TENANTS[0]] = value
    assert not __import__("greenmpc.simulation.validation", fromlist=["validate_action"]).validate_action(s, action.copy_with(grid_to_tenant_kw=values), sim_config).valid


def test_derived_totals_include_dppa_to_battery() -> None:
    action = balanced_action(state()).copy_with(dppa_to_battery_kw=5.0)
    assert action.total_external_import_kw == action.total_grid_to_tenants_kw + action.total_dppa_to_tenants_kw + 5.0
