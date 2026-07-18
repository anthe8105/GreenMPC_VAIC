from __future__ import annotations

from pathlib import Path

import pandas as pd

from greenmpc.data.dataset_builder import load_dataset_build_config
from greenmpc.data.profile_selection import select_profiles


def test_selects_five_unique_profiles(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    root = Path(__file__).resolve().parents[1]
    cfg = load_dataset_build_config(root / "configs/dataset_build.yaml", root / "configs/demo.yaml")
    rows = []
    for i in range(1, 8):
        rows.append({"source_client_id": f"MT_{i:03d}", "eligible": True, "p95": 1.0, "mean_load": 1.0, "maximum": 2.0, "load_factor_mean_over_p95": .8, "coefficient_of_variation": .2+i/100, "overnight_baseload_ratio": .5, "weekend_reduction_fraction": .1, "p99_to_median_ratio": 1+i/10, "business_hour_concentration": .5, "daytime_to_nighttime_ratio": 2, "hourly_ramp_p95": i, "two_shift_score": .5, "evening_mean": i})
    metrics = pd.DataFrame(rows)
    hourly = pd.DataFrame({r["source_client_id"]: range(24) for r in rows})

    selected = select_profiles(metrics, hourly, cfg, "abc", force=True, reselect=True)

    assert len(selected) == 5
    assert selected["source_client_id"].nunique() == 5
