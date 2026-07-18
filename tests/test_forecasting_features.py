from __future__ import annotations

import pandas as pd

from greenmpc.forecasting.config import load_forecasting_config
from greenmpc.forecasting.features import build_load_features, build_solar_features
from tests._forecasting_helpers import TENANTS, tiny_history


def test_load_lags_and_target_calendar_are_correct() -> None:
    tenant, park = tiny_history()
    cfg = load_forecasting_config("configs/forecasting.yaml")
    result = build_load_features(tenant, park, cfg).frame
    row = result[(result["tenant_id"] == TENANTS[0]) & (result["horizon_hours"] == 1)].iloc[0]
    origin = pd.Timestamp(row["forecast_origin_local"])
    hist = tenant[(tenant["tenant_id"] == TENANTS[0])].copy()
    hist["timestamp_local"] = pd.to_datetime(hist["timestamp_local"])
    expected = hist.loc[hist["timestamp_local"] == origin - pd.Timedelta(hours=1), "load_kw"].iloc[0]
    assert row["tenant_load_lag_1h_kw"] == expected
    assert row["target_hour"] == (origin + pd.Timedelta(hours=1)).hour
    assert "target_load_kw" not in build_load_features(tenant, park, cfg).feature_columns


def test_solar_features_exclude_target_pv() -> None:
    _, park = tiny_history()
    cfg = load_forecasting_config("configs/forecasting.yaml")
    result = build_solar_features(park, cfg)
    assert "target_pv_available_kw" not in result.feature_columns
    assert "pv_lag_1h_kw" in result.feature_columns
