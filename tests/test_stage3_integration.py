from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from greenmpc.simulation.park import IndustrialParkSimulator
from greenmpc.simulation.reference_action import build_reference_action


def test_full_processed_data_initializes_and_smoke_steps() -> None:
    sim = IndustrialParkSimulator.from_processed_files()
    for _ in range(24):
        result = sim.step(build_reference_action(sim.get_state(), sim.config))
        assert result.validation_result.valid
        assert len(result.tenant_energy_records) == 5
    assert sim.summary()["steps_executed"] == 24


def test_verify_stage3_script_passes() -> None:
    result = subprocess.run([sys.executable, "scripts/verify_stage3.py"], cwd=Path.cwd(), text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
