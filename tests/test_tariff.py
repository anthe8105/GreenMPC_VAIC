from __future__ import annotations

import pandas as pd
import pytest

from greenmpc.config import load_config
from greenmpc.data.dataset_builder import load_dataset_build_config
from greenmpc.data.tariff import build_tariff_frame, period_for_timestamp


def test_tariff_period_and_flags() -> None:
    cfg = load_dataset_build_config("configs/dataset_build.yaml")
    demo = load_config("configs/demo.yaml")
    ts = pd.date_range("2013-01-07 09:00", periods=1, freq="1h", tz="Asia/Ho_Chi_Minh")
    frame = build_tariff_frame(pd.DataFrame({"timestamp_local": ts, "timestamp_utc": ts.tz_convert("UTC")}), cfg.tariff, demo.grid)
    assert frame["tariff_period"].iloc[0] == "peak"
    assert not frame["tariff_category_selected"].any()


def test_tariff_overlap_fails() -> None:
    cfg = load_dataset_build_config("configs/dataset_build.yaml").tariff
    object.__setattr__(cfg, "weekday_off_peak_hours", [9])
    with pytest.raises(ValueError):
        period_for_timestamp(pd.Timestamp("2013-01-07 09:00", tz="Asia/Ho_Chi_Minh"), cfg)
