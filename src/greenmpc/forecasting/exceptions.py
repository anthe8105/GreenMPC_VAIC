"""Forecasting-layer exceptions."""

from __future__ import annotations


class ForecastingError(Exception):
    """Base forecasting error."""


class ForecastConfigError(ForecastingError):
    """Invalid forecasting configuration."""


class ForecastDataError(ForecastingError):
    """Invalid historical data for forecasting."""


class LeakageError(ForecastingError):
    """Feature leakage was detected."""


class ModelCompatibilityError(ForecastingError):
    """Persisted model artifacts are incompatible with current data/config."""


class ModelRegistryError(ForecastingError):
    """Model registry read/write failure."""
