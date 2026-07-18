from __future__ import annotations

import pandas as pd

from greenmpc.forecasting.baselines import add_load_baseline_predictions, add_solar_baseline_predictions
from greenmpc.forecasting.config import load_forecasting_config
from greenmpc.forecasting.features import build_load_features, build_solar_features
from tests._forecasting_helpers import tiny_history


def test_previous_day_load_baseline() -> None:
    tenant, park = tiny_history()
    cfg = load_forecasting_config("configs/forecasting.yaml")
    features = build_load_features(tenant, park, cfg).frame
    enriched = add_load_baseline_predictions(features, tenant)
    assert "baseline_previous_day_same_hour" in enriched
    assert enriched["baseline_previous_day_same_hour"].notna().any()


def test_nighttime_solar_baseline_zeroed() -> None:
    _, park = tiny_history()
    cfg = load_forecasting_config("configs/forecasting.yaml")
    features = build_solar_features(park, cfg).frame
    enriched = add_solar_baseline_predictions(features, park)
    night = ~enriched["target_is_daylight"]
    assert (enriched.loc[night, "baseline_current_value"] == 0).all()
