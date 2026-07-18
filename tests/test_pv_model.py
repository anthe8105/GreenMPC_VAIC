from __future__ import annotations

import pandas as pd

from greenmpc.data.dataset_builder import load_dataset_build_config
from greenmpc.data.pv_model import build_pv_frame


def test_pv_is_capped_and_not_measured() -> None:
    cfg = load_dataset_build_config("configs/dataset_build.yaml")
    ts = pd.date_range("2013-01-01", periods=2, freq="1h", tz="Asia/Ho_Chi_Minh")
    weather = pd.DataFrame({"timestamp_local": ts, "timestamp_utc": ts.tz_convert("UTC"), "ALLSKY_SFC_SW_DWN": [0.0, 99.0]})

    pv = build_pv_frame(weather, cfg.pv)

    assert pv["park_pv_available_kw"].iloc[0] == 0
    assert pv["park_pv_available_kw"].max() <= cfg.pv.installed_capacity_kw
    assert not pv["pv_is_measured"].any()
