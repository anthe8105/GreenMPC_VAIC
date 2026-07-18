from __future__ import annotations

import pytest

from greenmpc.simulation.exceptions import InvalidActionError, SimulationFinishedError
from greenmpc.simulation.park import IndustrialParkSimulator
from greenmpc.simulation.reference_action import build_reference_action


def test_valid_step_advances_one_hour() -> None:
    sim = IndustrialParkSimulator.from_processed_files()
    before = sim.get_state()
    sim.step(build_reference_action(before, sim.config))
    after = sim.get_state()
    assert (after.timestamp_local - before.timestamp_local).total_seconds() == 3600


def test_invalid_step_does_not_mutate_state() -> None:
    sim = IndustrialParkSimulator.from_processed_files()
    before = sim.get_state()
    action = build_reference_action(before, sim.config)
    bad = action.copy_with(pv_curtailment_kw=9999.0)
    with pytest.raises(InvalidActionError):
        sim.step(bad)
    after = sim.get_state()
    assert after.timestamp_local == before.timestamp_local
    assert after.battery.energy_kwh == before.battery.energy_kwh


def test_run_actions_stops_on_invalid_action() -> None:
    sim = IndustrialParkSimulator.from_processed_files()
    valid = build_reference_action(sim.get_state(), sim.config)
    invalid = valid.copy_with(pv_curtailment_kw=9999.0)
    with pytest.raises(InvalidActionError):
        sim.run_actions([valid, invalid])


def test_dataset_end_behavior() -> None:
    sim = IndustrialParkSimulator.from_processed_files()
    sim.reset(sim._timestamps[-2])
    sim.step(build_reference_action(sim.get_state(), sim.config))
    with pytest.raises(SimulationFinishedError):
        sim.step(build_reference_action(sim.get_state(), sim.config))
