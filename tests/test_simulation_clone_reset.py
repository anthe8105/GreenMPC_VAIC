from __future__ import annotations

from greenmpc.simulation.park import IndustrialParkSimulator
from greenmpc.simulation.reference_action import build_reference_action


def test_reset_clears_history_and_restores_timestamp() -> None:
    sim = IndustrialParkSimulator.from_processed_files()
    start = sim.get_state().timestamp_local
    sim.step(build_reference_action(sim.get_state(), sim.config))
    sim.reset()
    assert sim.get_state().timestamp_local == start
    assert sim.get_action_history().empty


def test_clone_is_independent() -> None:
    sim = IndustrialParkSimulator.from_processed_files()
    cloned = sim.clone()
    cloned.step(build_reference_action(cloned.get_state(), cloned.config))
    assert sim.get_state().timestamp_local != cloned.get_state().timestamp_local
    assert sim.get_action_history().empty
