"""Deterministic point-forecast baselines."""

from __future__ import annotations

import sys

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import numpy as np
import pandas as pd


def add_load_baseline_predictions(features: pd.DataFrame, tenant_hourly: pd.DataFrame) -> pd.DataFrame:
    data = features.copy()
    history = tenant_hourly.copy()
    history["timestamp_local"] = pd.to_datetime(history["timestamp_local"])
    lookup = history.set_index(["tenant_id", "timestamp_local"])["load_kw"]
    data["baseline_current_value"] = data["current_load_kw"]
    data["baseline_previous_day_same_hour"] = [
        lookup.get((tenant, ts - pd.Timedelta(hours=24)), np.nan)
        for tenant, ts in zip(data["tenant_id"], pd.to_datetime(data["target_timestamp_local"]))
    ]
    data["baseline_previous_week_same_hour"] = [
        lookup.get((tenant, ts - pd.Timedelta(hours=168)), np.nan)
        for tenant, ts in zip(data["tenant_id"], pd.to_datetime(data["target_timestamp_local"]))
    ]
    return data


def add_solar_baseline_predictions(features: pd.DataFrame, park_hourly: pd.DataFrame) -> pd.DataFrame:
    data = features.copy()
    history = park_hourly.copy()
    history["timestamp_local"] = pd.to_datetime(history["timestamp_local"])
    lookup = history.set_index("timestamp_local")["pv_available_kw"]
    capacity = float(history["installed_pv_capacity_kw"].iloc[0])
    data["baseline_current_value"] = data["current_pv_available_kw"]
    data["baseline_previous_day_same_hour"] = [lookup.get(ts - pd.Timedelta(hours=24), np.nan) for ts in pd.to_datetime(data["target_timestamp_local"])]
    data["baseline_previous_week_same_hour"] = [lookup.get(ts - pd.Timedelta(hours=168), np.nan) for ts in pd.to_datetime(data["target_timestamp_local"])]
    for col in ["baseline_current_value", "baseline_previous_day_same_hour", "baseline_previous_week_same_hour"]:
        data[col] = data[col].clip(lower=0.0, upper=capacity)
        if "target_is_daylight" in data:
            data.loc[~data["target_is_daylight"].astype(bool), col] = 0.0
    return data
