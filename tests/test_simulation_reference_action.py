from __future__ import annotations

import pytest

from greenmpc.simulation.exceptions import SimulationError
from greenmpc.simulation.reference_action import build_reference_action
from greenmpc.simulation.validation import validate_action
from tests._simulation_helpers import state


def test_reference_action_produces_valid_action(sim_config) -> None:
    s = state()
    action = build_reference_action(s, sim_config)
    assert validate_action(s, action, sim_config).valid
    assert action.metadata["uses_forecast"] is False
    assert action.metadata["uses_optimization"] is False


def test_reference_action_raises_when_infeasible(sim_config) -> None:
    with pytest.raises(SimulationError):
        build_reference_action(state(load_kw=3000.0, pv_kw=0.0, dppa_kw=0.0, battery_energy=1500.0), sim_config)
