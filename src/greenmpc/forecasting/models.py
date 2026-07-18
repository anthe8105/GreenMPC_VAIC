"""Scikit-learn quantile model construction."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from greenmpc.forecasting.config import ForecastingConfig


@dataclass(frozen=True)
class EstimatorChoice:
    name: str
    estimator_class: str
    parameters: dict[str, Any]
    sklearn_version: str


def choose_estimator(cfg: ForecastingConfig, quantile: float):
    params = dict(cfg.load_forecasting.model_hyperparameters)
    if "loss" in inspect.signature(HistGradientBoostingRegressor).parameters:
        estimator = HistGradientBoostingRegressor(
            loss="quantile",
            quantile=quantile,
            random_state=cfg.general.random_seed,
            **params,
        )
        return estimator, EstimatorChoice(
            name="hist_gradient_boosting_quantile",
            estimator_class="HistGradientBoostingRegressor",
            parameters=estimator.get_params(),
            sklearn_version=sklearn.__version__,
        )
    fallback = GradientBoostingRegressor(
        loss="quantile",
        alpha=quantile,
        random_state=cfg.general.random_seed,
        n_estimators=int(params.get("max_iter", 35)),
        learning_rate=float(params.get("learning_rate", 0.08)),
        max_depth=3,
    )
    return fallback, EstimatorChoice(
        name="gradient_boosting_quantile",
        estimator_class="GradientBoostingRegressor",
        parameters=fallback.get_params(),
        sklearn_version=sklearn.__version__,
    )


def build_pipeline(feature_columns: list[str], categorical_columns: list[str], cfg: ForecastingConfig, quantile: float) -> tuple[Pipeline, EstimatorChoice]:
    missing = [col for col in categorical_columns if col not in feature_columns]
    if missing:
        raise ValueError(f"categorical feature missing from feature columns: {missing}")
    numeric_columns = [col for col in feature_columns if col not in categorical_columns]
    try:
        encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:  # pragma: no cover - old sklearn compatibility
        encoder = OneHotEncoder(handle_unknown="ignore", sparse=False)
    preprocessor = ColumnTransformer(
        transformers=[
            ("numeric", SimpleImputer(strategy=cfg.load_forecasting.numeric_imputation_strategy), numeric_columns),
            (
                "categorical",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy=cfg.load_forecasting.categorical_imputation_strategy)),
                        ("onehot", encoder),
                    ]
                ),
                categorical_columns,
            ),
        ],
        remainder="drop",
        verbose_feature_names_out=False,
    )
    estimator, choice = choose_estimator(cfg, quantile)
    return Pipeline(steps=[("preprocess", preprocessor), ("model", estimator)]), choice
