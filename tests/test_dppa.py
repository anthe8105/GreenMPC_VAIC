from __future__ import annotations

import pandas as pd

from greenmpc.data.dataset_builder import load_dataset_build_config
from greenmpc.data.dppa import build_dppa_frame


def test_dppa_assumption_flags() -> None:
    cfg = load_dataset_build_config("configs/dataset_build.yaml")
    ts = pd.date_range("2013-01-01", periods=1, freq="1h", tz="Asia/Ho_Chi_Minh")
    frame = build_dppa_frame(pd.DataFrame({"timestamp_local": ts, "timestamp_utc": ts.tz_convert("UTC")}), cfg.dppa)
    assert frame["dppa_available_kw"].iloc[0] >= 0
    assert frame["dppa_availability_is_assumption"].iloc[0]
