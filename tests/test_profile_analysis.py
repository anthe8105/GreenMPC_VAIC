from __future__ import annotations

import pandas as pd

from greenmpc.data.dataset_builder import load_dataset_build_config
from greenmpc.data.profile_analysis import analyze_profiles


def test_profile_metrics_and_eligibility() -> None:
    cfg = load_dataset_build_config("configs/dataset_build.yaml")
    index = pd.date_range("2013-01-01", periods=48, freq="1h", tz="Asia/Ho_Chi_Minh")
    hourly = pd.DataFrame({"MT_001": [1.0] * 48, "MT_002": [0.0] * 48}, index=index)

    metrics = analyze_profiles(hourly, cfg)

    assert "coefficient_of_variation" in metrics.columns
    assert metrics.loc[metrics.source_client_id == "MT_002", "eligible"].iloc[0] == False
