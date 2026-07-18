from __future__ import annotations

import pytest

from tests._simulation_helpers import TENANTS, config, state


def test_initial_energy_and_soc_match_config() -> None:
    cfg = config()
    s = state()
    assert s.battery.energy_kwh == cfg.battery.energy_capacity_kwh * cfg.battery.initial_soc_fraction
    assert s.battery.soc_fraction == cfg.battery.initial_soc_fraction


def test_renewable_inventory_initialization() -> None:
    cfg = config()
    s = state()
    assert s.battery.renewable_energy_kwh == s.battery.energy_kwh * cfg.battery.initial_renewable_fraction


def test_state_maps_are_not_externally_mutable() -> None:
    s = state()
    with pytest.raises(TypeError):
        s.exogenous.effective_tenant_load_kw[TENANTS[0]] = 1.0


def test_all_tenant_dictionaries_are_complete() -> None:
    s = state()
    assert set(s.cumulative_load_by_tenant_kwh) == set(TENANTS)
