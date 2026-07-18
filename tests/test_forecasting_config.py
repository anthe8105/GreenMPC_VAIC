from __future__ import annotations

import pytest

from greenmpc.forecasting.config import load_forecasting_config
from greenmpc.forecasting.exceptions import ForecastConfigError
from tests._forecasting_helpers import mutated_forecast_config


def test_valid_forecasting_config_loads() -> None:
    cfg = load_forecasting_config("configs/forecasting.yaml")
    assert cfg.general.forecast_horizons_hours == [1, 2, 3, 4, 5, 6]


def test_missing_quantile_fails(tmp_path) -> None:
    path = mutated_forecast_config(tmp_path, lambda data: data["general"].update({"quantiles": [0.1, 0.5]}))
    with pytest.raises(ForecastConfigError, match="quantiles"):
        load_forecasting_config(path)


def test_wrong_horizons_fail(tmp_path) -> None:
    path = mutated_forecast_config(tmp_path, lambda data: data["general"].update({"forecast_horizons_hours": [1, 2]}))
    with pytest.raises(ForecastConfigError, match="horizons"):
        load_forecasting_config(path)


def test_invalid_split_fractions_fail(tmp_path) -> None:
    path = mutated_forecast_config(tmp_path, lambda data: data["split"].update({"test_fraction": 0.2}))
    with pytest.raises(ForecastConfigError, match="sum"):
        load_forecasting_config(path)


def test_future_weather_and_events_fail(tmp_path) -> None:
    path = mutated_forecast_config(tmp_path, lambda data: data["load_forecasting"].update({"include_future_actual_weather": True}))
    with pytest.raises(ForecastConfigError, match="future_actual_weather"):
        load_forecasting_config(path)
    path = mutated_forecast_config(tmp_path, lambda data: data["load_forecasting"].update({"include_runtime_event_catalog": True}))
    with pytest.raises(ForecastConfigError, match="runtime_event_catalog"):
        load_forecasting_config(path)


def test_absolute_output_path_fails(tmp_path) -> None:
    path = mutated_forecast_config(tmp_path, lambda data: data["outputs"].update({"metrics_path": "/tmp/metrics.csv"}))
    with pytest.raises(ForecastConfigError, match="relative"):
        load_forecasting_config(path)
