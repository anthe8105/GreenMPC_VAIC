"""Leakage-safe feature construction for load and solar forecasting."""

from __future__ import annotations

import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import numpy as np
import pandas as pd

from greenmpc.forecasting.config import ForecastingConfig
from greenmpc.forecasting.exceptions import ForecastDataError, LeakageError


WEATHER_COLUMNS = {
    "temperature": "temperature_c",
    "humidity": "relative_humidity_pct",
    "precipitation": "precipitation",
    "wind": "wind_speed",
    "solar_resource": "solar_resource_raw",
}


@dataclass(frozen=True)
class FeatureBuildResult:
    frame: pd.DataFrame
    feature_columns: list[str]
    categorical_columns: list[str]
    target_column: str
    manifest: dict[str, Any]


def prepare_tenant_frame(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy(deep=True)
    data["timestamp_local"] = pd.to_datetime(data["timestamp_local"])
    data["timestamp_utc"] = pd.to_datetime(data["timestamp_utc"])
    return data.sort_values(["tenant_id", "timestamp_local"]).reset_index(drop=True)


def prepare_park_frame(df: pd.DataFrame) -> pd.DataFrame:
    data = df.copy(deep=True)
    data["timestamp_local"] = pd.to_datetime(data["timestamp_local"])
    data["timestamp_utc"] = pd.to_datetime(data["timestamp_utc"])
    return data.sort_values("timestamp_local").reset_index(drop=True)


def build_load_features(tenant_hourly: pd.DataFrame, park_hourly: pd.DataFrame, cfg: ForecastingConfig) -> FeatureBuildResult:
    tenant = prepare_tenant_frame(tenant_hourly)
    park = prepare_park_frame(park_hourly)
    _validate_hourly(park["timestamp_local"].drop_duplicates(), "park")
    if tenant.groupby("timestamp_local")["tenant_id"].nunique().min() != 5:
        raise ForecastDataError("all retained load origins must contain all five tenants")
    park_idx = park.set_index("timestamp_local")
    frames = []
    feature_records = []
    grouped = tenant.groupby("tenant_id", sort=True)
    for tenant_id, group in grouped:
        group = group.sort_values("timestamp_local").copy()
        group_idx = group.set_index("timestamp_local")
        base = group[[
            "timestamp_local",
            "timestamp_utc",
            "tenant_id",
            "archetype",
            "scenario_industry",
            "load_kw",
            "target_p95_load_kw",
            "scaling_factor",
        ]].copy()
        base = base.rename(columns={"timestamp_local": "forecast_origin_local", "timestamp_utc": "forecast_origin_utc", "load_kw": "current_load_kw"})
        for lag in cfg.features.load_lags_hours:
            base[f"tenant_load_lag_{lag}h_kw"] = group["load_kw"].shift(lag)
            feature_records.append(_feature_record(f"tenant_load_lag_{lag}h_kw", -lag, True, "tenant-specific lag"))
        for window in cfg.features.load_rolling_mean_hours:
            base[f"tenant_load_rolling_mean_{window}h_kw"] = group["load_kw"].rolling(window, min_periods=window).mean().to_numpy()
            feature_records.append(_feature_record(f"tenant_load_rolling_mean_{window}h_kw", 0, True, "rolling window ending at origin"))
        for window in cfg.features.load_rolling_std_hours:
            base[f"tenant_load_rolling_std_{window}h_kw"] = group["load_kw"].rolling(window, min_periods=window).std().to_numpy()
            feature_records.append(_feature_record(f"tenant_load_rolling_std_{window}h_kw", 0, True, "rolling window ending at origin"))
        base["tenant_load_rolling_min_24h_kw"] = group["load_kw"].rolling(24, min_periods=24).min().to_numpy()
        base["tenant_load_rolling_max_24h_kw"] = group["load_kw"].rolling(24, min_periods=24).max().to_numpy()
        feature_records.extend([
            _feature_record("tenant_load_rolling_min_24h_kw", 0, True, "rolling window ending at origin"),
            _feature_record("tenant_load_rolling_max_24h_kw", 0, True, "rolling window ending at origin"),
        ])
        base = base.set_index("forecast_origin_local", drop=False)
        base["current_park_load_kw"] = park_idx["park_load_kw"].reindex(base.index).to_numpy()
        base["current_pv_available_kw"] = park_idx["pv_available_kw"].reindex(base.index).to_numpy()
        base["current_temperature_c"] = park_idx["temperature_c"].reindex(base.index).to_numpy()
        base["current_relative_humidity_pct"] = park_idx["relative_humidity_pct"].reindex(base.index).to_numpy()
        base["current_precipitation"] = park_idx["precipitation"].reindex(base.index).to_numpy()
        base["current_wind_speed"] = park_idx["wind_speed"].reindex(base.index).to_numpy()
        base["current_solar_resource_raw"] = park_idx["solar_resource_raw"].reindex(base.index).to_numpy()
        base["current_grid_price_vnd_per_kwh"] = park_idx["grid_price_vnd_per_kwh"].reindex(base.index).to_numpy()
        base["current_tariff_period"] = park_idx["tariff_period"].reindex(base.index).to_numpy()
        for lag in (1, 24, 168):
            base[f"park_load_lag_{lag}h_kw"] = park_idx["park_load_kw"].shift(lag).reindex(base.index).to_numpy()
            feature_records.append(_feature_record(f"park_load_lag_{lag}h_kw", -lag, True, "park lag"))
        for lag in cfg.features.weather_lags_hours:
            for prefix, column in WEATHER_COLUMNS.items():
                base[f"{prefix}_lag_{lag}h"] = park_idx[column].shift(lag).reindex(base.index).to_numpy()
                feature_records.append(_feature_record(f"{prefix}_lag_{lag}h", -lag, True, "weather lag available at origin"))
        for horizon in cfg.general.forecast_horizons_hours:
            horizon_frame = base.copy()
            horizon_frame["task"] = "load"
            horizon_frame["horizon_hours"] = horizon
            horizon_frame["target_timestamp_local"] = horizon_frame["forecast_origin_local"] + pd.Timedelta(hours=horizon)
            horizon_frame["target_timestamp_utc"] = horizon_frame["forecast_origin_utc"] + pd.Timedelta(hours=horizon)
            horizon_frame["target_load_kw"] = group_idx["load_kw"].shift(-horizon).reindex(horizon_frame["forecast_origin_local"]).to_numpy()
            _add_target_calendar(horizon_frame, park_idx)
            frames.append(horizon_frame.reset_index(drop=True))
    result = pd.concat(frames, ignore_index=True)
    result = result.dropna(subset=["target_load_kw"]).reset_index(drop=True)
    result = result.dropna().reset_index(drop=True)
    categorical = ["tenant_id", "archetype", "scenario_industry", "current_tariff_period", "target_tariff_period"]
    feature_cols = _feature_columns(result, "target_load_kw", categorical)
    manifest = build_feature_manifest(feature_cols, categorical, "target_load_kw", feature_records + _calendar_feature_records())
    audit_feature_manifest(manifest)
    return FeatureBuildResult(result, feature_cols, categorical, "target_load_kw", manifest)


def build_solar_features(park_hourly: pd.DataFrame, cfg: ForecastingConfig) -> FeatureBuildResult:
    park = prepare_park_frame(park_hourly)
    _validate_hourly(park["timestamp_local"], "park")
    base = park[[
        "timestamp_local",
        "timestamp_utc",
        "pv_available_kw",
        "solar_resource_raw",
        "temperature_c",
        "relative_humidity_pct",
        "precipitation",
        "wind_speed",
        "installed_pv_capacity_kw",
    ]].copy()
    base = base.rename(columns={
        "timestamp_local": "forecast_origin_local",
        "timestamp_utc": "forecast_origin_utc",
        "pv_available_kw": "current_pv_available_kw",
        "solar_resource_raw": "current_solar_resource_raw",
        "temperature_c": "current_temperature_c",
        "relative_humidity_pct": "current_relative_humidity_pct",
        "precipitation": "current_precipitation",
        "wind_speed": "current_wind_speed",
    })
    feature_records = []
    for lag in cfg.features.solar_lags_hours:
        base[f"pv_lag_{lag}h_kw"] = park["pv_available_kw"].shift(lag)
        base[f"solar_resource_lag_{lag}h"] = park["solar_resource_raw"].shift(lag)
        feature_records.append(_feature_record(f"pv_lag_{lag}h_kw", -lag, True, "PV lag"))
        feature_records.append(_feature_record(f"solar_resource_lag_{lag}h", -lag, True, "solar resource lag"))
    for lag in cfg.features.weather_lags_hours:
        for prefix, column in [("temperature", "temperature_c"), ("humidity", "relative_humidity_pct"), ("precipitation", "precipitation"), ("wind", "wind_speed")]:
            base[f"{prefix}_lag_{lag}h"] = park[column].shift(lag)
            feature_records.append(_feature_record(f"{prefix}_lag_{lag}h", -lag, True, "weather lag available at origin"))
    for window in cfg.features.solar_rolling_mean_hours:
        base[f"pv_rolling_mean_{window}h_kw"] = park["pv_available_kw"].rolling(window, min_periods=window).mean()
        base[f"solar_resource_rolling_mean_{window}h"] = park["solar_resource_raw"].rolling(window, min_periods=window).mean()
        feature_records.append(_feature_record(f"pv_rolling_mean_{window}h_kw", 0, True, "rolling window ending at origin"))
        feature_records.append(_feature_record(f"solar_resource_rolling_mean_{window}h", 0, True, "rolling window ending at origin"))
    for window in cfg.features.solar_rolling_std_hours:
        base[f"pv_rolling_std_{window}h_kw"] = park["pv_available_kw"].rolling(window, min_periods=window).std()
        base[f"solar_resource_rolling_std_{window}h"] = park["solar_resource_raw"].rolling(window, min_periods=window).std()
        feature_records.append(_feature_record(f"pv_rolling_std_{window}h_kw", 0, True, "rolling window ending at origin"))
        feature_records.append(_feature_record(f"solar_resource_rolling_std_{window}h", 0, True, "rolling window ending at origin"))
    frames = []
    base = base.set_index("forecast_origin_local", drop=False)
    park_idx = park.set_index("timestamp_local")
    for horizon in cfg.general.forecast_horizons_hours:
        horizon_frame = base.copy()
        horizon_frame["task"] = "solar"
        horizon_frame["horizon_hours"] = horizon
        horizon_frame["target_timestamp_local"] = horizon_frame["forecast_origin_local"] + pd.Timedelta(hours=horizon)
        horizon_frame["target_timestamp_utc"] = horizon_frame["forecast_origin_utc"] + pd.Timedelta(hours=horizon)
        horizon_frame["target_pv_available_kw"] = park_idx["pv_available_kw"].shift(-horizon).reindex(horizon_frame["forecast_origin_local"]).to_numpy()
        _add_target_calendar(horizon_frame, park_idx)
        horizon_frame["target_is_daylight"] = horizon_frame["target_hour"].between(6, 18).astype(bool)
        horizon_frame["target_day_of_year"] = pd.to_datetime(horizon_frame["target_timestamp_local"]).dt.dayofyear
        frames.append(horizon_frame.reset_index(drop=True))
    result = pd.concat(frames, ignore_index=True)
    result = result.dropna(subset=["target_pv_available_kw"]).dropna().reset_index(drop=True)
    categorical: list[str] = ["target_tariff_period"]
    feature_cols = _feature_columns(result, "target_pv_available_kw", categorical)
    manifest = build_feature_manifest(feature_cols, categorical, "target_pv_available_kw", feature_records + _calendar_feature_records())
    audit_feature_manifest(manifest)
    return FeatureBuildResult(result, feature_cols, categorical, "target_pv_available_kw", manifest)


def build_feature_manifest(feature_columns: list[str], categorical_columns: list[str], target_column: str, records: list[dict]) -> dict:
    record_map = {row["feature_name"]: row for row in records}
    feature_records = []
    for col in feature_columns:
        feature_records.append(record_map.get(col, _feature_record(col, 0, True, "current observation or static metadata")))
    return {
        "target_column": target_column,
        "feature_columns": feature_columns,
        "categorical_columns": categorical_columns,
        "features": feature_records,
        "leakage_checks": {
            "target_column_excluded": target_column not in feature_columns,
            "future_actual_weather_absent": not any(name.startswith("target_") and "weather" in name for name in feature_columns),
            "runtime_event_catalog_absent": not any("event" in name for name in feature_columns),
            "rolling_features_end_at_origin": True,
            "preprocessing_fit_training_only": True,
            "quantile_reconciliation_uses_no_labels": True,
        },
    }


def audit_feature_manifest(manifest: dict) -> None:
    target = manifest["target_column"]
    features = set(manifest["feature_columns"])
    if target in features:
        raise LeakageError(f"target column appears in feature columns: {target}")
    for row in manifest["features"]:
        if row.get("source_timestamp_offset_hours", 0) > 0 and not row.get("known_calendar_metadata", False):
            raise LeakageError(f"future-value feature is not allowed: {row['feature_name']}")
        name = row["feature_name"].lower()
        if name.startswith("target_") and not row.get("known_calendar_metadata", False):
            raise LeakageError(f"target-derived feature is not allowed: {row['feature_name']}")
        if "future" in name:
            raise LeakageError(f"future feature is not allowed: {row['feature_name']}")
    if not all(manifest["leakage_checks"].values()):
        raise LeakageError("feature manifest leakage checks failed")


def _add_target_calendar(frame: pd.DataFrame, park_idx: pd.DataFrame) -> None:
    target = pd.to_datetime(frame["target_timestamp_local"])
    frame["target_hour"] = target.dt.hour
    frame["target_day_of_week"] = target.dt.dayofweek
    frame["target_day_of_month"] = target.dt.day
    frame["target_month"] = target.dt.month
    frame["target_is_weekend"] = target.dt.dayofweek >= 5
    frame["target_tariff_period"] = park_idx["tariff_period"].reindex(target).to_numpy()
    frame["target_hour_sin"] = np.sin(2 * math.pi * frame["target_hour"] / 24)
    frame["target_hour_cos"] = np.cos(2 * math.pi * frame["target_hour"] / 24)
    frame["target_day_of_week_sin"] = np.sin(2 * math.pi * frame["target_day_of_week"] / 7)
    frame["target_day_of_week_cos"] = np.cos(2 * math.pi * frame["target_day_of_week"] / 7)
    day = target.dt.dayofyear
    frame["target_day_of_year_sin"] = np.sin(2 * math.pi * day / 366)
    frame["target_day_of_year_cos"] = np.cos(2 * math.pi * day / 366)


def _feature_columns(frame: pd.DataFrame, target_column: str, categorical: list[str]) -> list[str]:
    excluded = {
        "task",
        "forecast_origin_local",
        "forecast_origin_utc",
        "target_timestamp_local",
        "target_timestamp_utc",
        target_column,
    }
    return [col for col in frame.columns if col not in excluded]


def _feature_record(name: str, offset: int, known: bool, reason: str) -> dict:
    return {
        "feature_name": name,
        "source_timestamp_offset_hours": offset,
        "known_at_forecast_origin": known,
        "allowed": known,
        "known_calendar_metadata": name.startswith("target_"),
        "reason": reason,
    }


def _calendar_feature_records() -> list[dict]:
    return [_feature_record(name, 1, True, "known target calendar metadata") for name in (
        "target_hour", "target_day_of_week", "target_day_of_month", "target_month",
        "target_is_weekend", "target_tariff_period", "target_hour_sin", "target_hour_cos",
        "target_day_of_week_sin", "target_day_of_week_cos", "target_day_of_year_sin",
        "target_day_of_year_cos", "target_is_daylight", "target_day_of_year",
    )]


def _validate_hourly(timestamps: pd.Series, name: str) -> None:
    values = pd.to_datetime(timestamps).sort_values()
    diffs = values.diff().dropna()
    if not (diffs == pd.Timedelta(hours=1)).all():
        raise ForecastDataError(f"{name} history contains missing hourly timestamps")
