from __future__ import annotations

import pandas as pd
import numpy as np

from greenmpc.forecasting.baselines import add_load_baseline_predictions, add_solar_baseline_predictions
from greenmpc.forecasting.config import load_forecasting_config
from greenmpc.forecasting.features import build_load_features, build_solar_features
from greenmpc.forecasting.metrics import point_metrics
from tests._forecasting_helpers import tiny_history


def test_previous_day_load_baseline() -> None:
    tenant, park = tiny_history()
    cfg = load_forecasting_config("configs/forecasting.yaml")
    features = build_load_features(tenant, park, cfg).frame
    enriched = add_load_baseline_predictions(features, tenant)
    assert "baseline_previous_day_same_hour" in enriched
    assert enriched["baseline_previous_day_same_hour"].notna().any()
    row = enriched[enriched["baseline_previous_day_same_hour"].notna()].iloc[0]
    assert row["baseline_previous_day_source_timestamp"] == pd.Timestamp(row["target_timestamp_local"]) - pd.Timedelta(hours=24)
    assert row["baseline_previous_day_source_timestamp"] != pd.Timestamp(row["target_timestamp_local"])


def test_nighttime_solar_baseline_zeroed() -> None:
    _, park = tiny_history()
    cfg = load_forecasting_config("configs/forecasting.yaml")
    features = build_solar_features(park, cfg).frame
    enriched = add_solar_baseline_predictions(features, park)
    night = ~enriched["target_is_daylight"]
    assert (enriched.loc[night, "baseline_current_value"] == 0).all()


def test_solar_previous_day_and_week_use_lagged_target_timestamps() -> None:
    _, park = tiny_history()
    cfg = load_forecasting_config("configs/forecasting.yaml")
    features = build_solar_features(park, cfg).frame
    enriched = add_solar_baseline_predictions(features, park)
    row = enriched[enriched["baseline_previous_week_same_hour"].notna()].iloc[0]
    target = pd.Timestamp(row["target_timestamp_local"])
    assert row["baseline_previous_day_source_timestamp"] == target - pd.Timedelta(hours=24)
    assert row["baseline_previous_week_source_timestamp"] == target - pd.Timedelta(hours=168)
    assert row["baseline_previous_day_source_timestamp"] != target
    assert row["baseline_previous_week_source_timestamp"] != target


def test_solar_baseline_does_not_equal_target_by_construction() -> None:
    _, park = tiny_history(hours=220)
    park = park.copy()
    park["timestamp_local"] = pd.to_datetime(park["timestamp_local"])
    park.loc[park["timestamp_local"].dt.hour == 12, "pv_available_kw"] = np.arange(
        (park["timestamp_local"].dt.hour == 12).sum(), dtype=float
    ) * 10.0
    cfg = load_forecasting_config("configs/forecasting.yaml")
    features = build_solar_features(park, cfg).frame
    enriched = add_solar_baseline_predictions(features, park)
    noon = enriched[(pd.to_datetime(enriched["target_timestamp_local"]).dt.hour == 12) & enriched["baseline_previous_day_same_hour"].notna()]
    assert (noon["baseline_previous_day_same_hour"] != noon["target_pv_available_kw"]).any()


def test_baseline_horizon_handling_uses_target_not_origin() -> None:
    _, park = tiny_history(hours=220)
    park = park.copy()
    park["timestamp_local"] = pd.to_datetime(park["timestamp_local"])
    park["pv_available_kw"] = np.arange(len(park), dtype=float)
    cfg = load_forecasting_config("configs/forecasting.yaml")
    features = build_solar_features(park, cfg).frame
    enriched = add_solar_baseline_predictions(features, park)
    row = enriched[(enriched["horizon_hours"] == 6) & enriched["baseline_previous_day_same_hour"].notna()].iloc[0]
    lookup = park.set_index("timestamp_local")["pv_available_kw"]
    assert row["baseline_previous_day_same_hour"] == lookup[pd.Timestamp(row["target_timestamp_local"]) - pd.Timedelta(hours=24)]


def test_metrics_are_calculated_from_aligned_rows() -> None:
    rows = pd.DataFrame({"actual": [10.0, 20.0, 30.0], "predicted": [9.0, 19.0, 35.0]})
    metrics = point_metrics(rows["actual"], rows["predicted"])
    assert metrics["MAE"] == 7.0 / 3.0
    assert metrics["WAPE"] == 7.0 / 60.0


def test_daylight_only_wape_is_calculated_on_daylight_rows() -> None:
    rows = pd.DataFrame({
        "actual_pv_kw": [0.0, 100.0, 100.0],
        "baseline_pv_kw": [50.0, 90.0, 80.0],
        "target_is_daylight": [False, True, True],
    })
    daylight = rows[rows["target_is_daylight"]]
    assert point_metrics(daylight["actual_pv_kw"], daylight["baseline_pv_kw"])["WAPE"] == 30.0 / 200.0


def test_load_baseline_lookup_includes_tenant_id() -> None:
    ts = pd.date_range("2013-01-01 00:00:00+07:00", periods=180, freq="h")
    tenant = pd.DataFrame(
        [
            {"tenant_id": tenant_id, "timestamp_local": stamp, "load_kw": (1000 if tenant_id == "A" else 2000) + i}
            for i, stamp in enumerate(ts)
            for tenant_id in ["A", "B"]
        ]
    )
    features = pd.DataFrame({
        "tenant_id": ["A", "B"],
        "target_timestamp_local": [ts[170], ts[170]],
        "current_load_kw": [1.0, 2.0],
    })
    enriched = add_load_baseline_predictions(features, tenant)
    assert enriched.loc[0, "baseline_previous_week_same_hour"] == 1002.0
    assert enriched.loc[1, "baseline_previous_week_same_hour"] == 2002.0
