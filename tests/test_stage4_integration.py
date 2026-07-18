from __future__ import annotations

import subprocess
import sys


def test_stage4_verification_passes() -> None:
    result = subprocess.run([sys.executable, "scripts/verify_stage4.py"], text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_simulator_has_no_forecasting_import() -> None:
    from pathlib import Path
    text = "\n".join(path.read_text(encoding="utf-8") for path in Path("src/greenmpc/simulation").glob("*.py"))
    assert "greenmpc.forecasting" not in text
