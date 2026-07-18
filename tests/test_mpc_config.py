from __future__ import annotations

import pytest

from greenmpc.control.config import load_mpc_config
from greenmpc.control.exceptions import MPCConfigError


def test_valid_mpc_config_loads():
    cfg = load_mpc_config("configs/mpc.yaml")
    assert cfg.general.planning_horizon_hours == 6
    assert cfg.solver.name == "HIGHS"
    assert cfg.modes["expected"].load_quantile == 0.5


def test_fallback_mislabeled_as_baseline_fails(tmp_path):
    text = open("configs/mpc.yaml", encoding="utf-8").read()
    path = tmp_path / "mpc.yaml"
    path.write_text(text.replace("fallback_is_evaluation_baseline: false", "fallback_is_evaluation_baseline: true"), encoding="utf-8")
    with pytest.raises(MPCConfigError, match="fallback_is_evaluation_baseline"):
        load_mpc_config(path)
