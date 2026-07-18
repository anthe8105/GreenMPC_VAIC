"""Typed Stage 4 forecasting configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from greenmpc.config import load_config
from greenmpc.forecasting.exceptions import ForecastConfigError


@dataclass(frozen=True)
class GeneralForecastConfig:
    random_seed: int
    forecast_horizons_hours: list[int]
    quantiles: list[float]
    output_timezone: str
    frequency: str
    minimum_history_hours: int
    quantile_reconciliation_enabled: bool
    reject_dataset_fingerprint_mismatch: bool


@dataclass(frozen=True)
class ChronologicalSplitConfig:
    method: str
    train_fraction: float
    validation_fraction: float
    test_fraction: float
    enforce_common_timestamp_boundaries: bool
    minimum_test_days: int


@dataclass(frozen=True)
class LoadForecastConfig:
    model_scope: str
    direct_multi_horizon: bool
    include_tenant_id: bool
    include_archetype: bool
    include_scenario_industry: bool
    include_future_actual_weather: bool
    include_runtime_event_catalog: bool
    estimator_preference: list[str]
    model_hyperparameters: dict[str, Any]
    categorical_encoding: str
    numeric_imputation_strategy: str
    categorical_imputation_strategy: str


@dataclass(frozen=True)
class SolarForecastConfig:
    model_scope: str
    direct_multi_horizon: bool
    include_future_actual_weather: bool
    force_nighttime_zero: bool
    estimator_preference: list[str]
    model_hyperparameters: dict[str, Any]


@dataclass(frozen=True)
class FeatureConfig:
    load_lags_hours: list[int]
    load_rolling_mean_hours: list[int]
    load_rolling_std_hours: list[int]
    weather_lags_hours: list[int]
    solar_lags_hours: list[int]
    solar_rolling_mean_hours: list[int]
    solar_rolling_std_hours: list[int]
    include_current_observation: bool
    include_target_calendar_features: bool


@dataclass(frozen=True)
class BaselineConfig:
    load: list[str]
    solar: list[str]


@dataclass(frozen=True)
class EvaluationConfig:
    primary_point_metric: str
    interval_lower_quantile: float
    interval_upper_quantile: float
    interval_nominal_coverage: float
    zero_denominator_tolerance: float
    save_raw_quantile_predictions: bool
    save_reconciled_quantile_predictions: bool


@dataclass(frozen=True)
class ForecastOutputConfig:
    model_root: str
    metrics_path: str
    prediction_sample_path: str
    model_manifest_path: str
    split_manifest_path: str
    feature_manifest_path: str
    evaluation_summary_path: str
    artifact_directory: str


@dataclass(frozen=True)
class ForecastingConfig:
    schema_version: int
    general: GeneralForecastConfig
    split: ChronologicalSplitConfig
    load_forecasting: LoadForecastConfig
    solar_forecasting: SolarForecastConfig
    features: FeatureConfig
    baselines: BaselineConfig
    evaluation: EvaluationConfig
    outputs: ForecastOutputConfig


def load_forecasting_config(path: str | Path, demo_config_path: str | Path = "configs/demo.yaml") -> ForecastingConfig:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    cfg = ForecastingConfig(
        schema_version=int(raw["schema_version"]),
        general=_build(GeneralForecastConfig, raw["general"]),
        split=_build(ChronologicalSplitConfig, raw["split"]),
        load_forecasting=_build(LoadForecastConfig, raw["load_forecasting"]),
        solar_forecasting=_build(SolarForecastConfig, raw["solar_forecasting"]),
        features=_build(FeatureConfig, raw["features"]),
        baselines=_build(BaselineConfig, raw["baselines"]),
        evaluation=_build(EvaluationConfig, raw["evaluation"]),
        outputs=_build(ForecastOutputConfig, raw["outputs"]),
    )
    _validate(cfg, demo_config_path)
    return cfg


def _build(cls: type[Any], data: Any) -> Any:
    if not isinstance(data, dict):
        raise ForecastConfigError(f"{cls.__name__} must be a mapping")
    required = {field.name for field in cls.__dataclass_fields__.values()}
    missing = required.difference(data)
    if missing:
        raise ForecastConfigError(f"{cls.__name__} missing field(s): {', '.join(sorted(missing))}")
    return cls(**{field: data[field] for field in required})


def _validate(cfg: ForecastingConfig, demo_config_path: str | Path) -> None:
    if cfg.general.forecast_horizons_hours != [1, 2, 3, 4, 5, 6]:
        raise ForecastConfigError("general.forecast_horizons_hours must equal [1, 2, 3, 4, 5, 6]")
    if cfg.general.quantiles != sorted(cfg.general.quantiles):
        raise ForecastConfigError("general.quantiles must be ordered")
    if any(q <= 0 or q >= 1 for q in cfg.general.quantiles):
        raise ForecastConfigError("general.quantiles must be between zero and one")
    if not {0.1, 0.5, 0.9}.issubset({round(float(q), 10) for q in cfg.general.quantiles}):
        raise ForecastConfigError("general.quantiles must include 0.1, 0.5, and 0.9")
    split_total = cfg.split.train_fraction + cfg.split.validation_fraction + cfg.split.test_fraction
    if abs(split_total - 1.0) > 1e-9:
        raise ForecastConfigError("split fractions must sum to one")
    if cfg.split.method != "chronological_target_timestamp":
        raise ForecastConfigError("split.method must be chronological_target_timestamp")
    if cfg.load_forecasting.include_future_actual_weather:
        raise ForecastConfigError("load_forecasting.include_future_actual_weather must be false")
    if cfg.solar_forecasting.include_future_actual_weather:
        raise ForecastConfigError("solar_forecasting.include_future_actual_weather must be false")
    if cfg.load_forecasting.include_runtime_event_catalog:
        raise ForecastConfigError("load_forecasting.include_runtime_event_catalog must be false")
    max_lag = max(cfg.features.load_lags_hours + cfg.features.weather_lags_hours + cfg.features.solar_lags_hours)
    if cfg.general.minimum_history_hours < max_lag:
        raise ForecastConfigError("general.minimum_history_hours must be at least the maximum configured lag")
    for field in (
        cfg.features.load_rolling_mean_hours
        + cfg.features.load_rolling_std_hours
        + cfg.features.solar_rolling_mean_hours
        + cfg.features.solar_rolling_std_hours
    ):
        if field <= 0:
            raise ForecastConfigError("all rolling windows must be positive")
    for value in cfg.outputs.__dict__.values():
        path = PurePosixPath(str(value))
        if path.is_absolute() or ".." in path.parts:
            raise ForecastConfigError(f"output path must be relative project path: {value}")
    demo = load_config(demo_config_path)
    if cfg.general.output_timezone != demo.project.timezone:
        raise ForecastConfigError("general.output_timezone must match processed dataset timezone")
    if not cfg.load_forecasting.direct_multi_horizon:
        raise ForecastConfigError("load_forecasting.direct_multi_horizon must be true")
    if not cfg.solar_forecasting.direct_multi_horizon:
        raise ForecastConfigError("solar_forecasting.direct_multi_horizon must be true")
    if cfg.load_forecasting.model_scope != "global_multi_tenant":
        raise ForecastConfigError("load_forecasting.model_scope must be global_multi_tenant")
    if cfg.solar_forecasting.model_scope != "park_level":
        raise ForecastConfigError("solar_forecasting.model_scope must be park_level")
