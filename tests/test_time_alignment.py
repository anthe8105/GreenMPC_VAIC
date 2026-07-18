from __future__ import annotations

import pandas as pd

from greenmpc.data.time_alignment import audit_local_timestamps, complete_local_day_index


def test_audit_detects_duplicates_and_intersection() -> None:
    idx = pd.DatetimeIndex([pd.Timestamp("2013-01-01 00:00"), pd.Timestamp("2013-01-01 00:00")])
    assert audit_local_timestamps(idx)["duplicate_local_timestamps"] == 1
    load = pd.date_range("2013-01-02", periods=24, freq="1h", tz="Asia/Ho_Chi_Minh")
    weather = pd.Series(load)
    assert len(complete_local_day_index(load, weather, "Asia/Ho_Chi_Minh")) == 24
