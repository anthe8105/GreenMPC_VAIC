from __future__ import annotations

import pandas as pd

from greenmpc.data.dataset_builder import load_dataset_build_config
from greenmpc.data.events import build_event_catalog


def test_events_are_deterministic_and_separate() -> None:
    cfg = load_dataset_build_config("configs/dataset_build.yaml")
    idx = pd.date_range("2013-01-01", periods=24 * 20, freq="1h", tz="Asia/Ho_Chi_Minh")
    events = build_event_catalog(idx, ["Electronics_A", "Semiconductor_B"], cfg.event_catalog)
    assert events["event_id"].is_unique
    assert not events["applied_to_baseline_dataset"].any()
    assert "combined_stress_event" in set(events["event_type"])
