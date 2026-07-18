from __future__ import annotations

from greenmpc.simulation.history import SimulationHistory
from greenmpc.simulation.reference_action import build_reference_action
from greenmpc.simulation.park import IndustrialParkSimulator


def test_history_export(tmp_path) -> None:
    sim = IndustrialParkSimulator.from_processed_files()
    sim.step(build_reference_action(sim.get_state(), sim.config))
    paths = sim.export_history(tmp_path)
    assert paths["states"].exists()
    assert paths["actions"].exists()
    assert paths["simulation_summary"].exists()


def test_empty_history_frames() -> None:
    frames = SimulationHistory().to_frames()
    assert set(frames) == {"states", "actions", "tenant_energy", "park_energy", "event_effects", "violations"}
