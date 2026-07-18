from __future__ import annotations

from greenmpc.forecasting.config import load_forecasting_config
from greenmpc.forecasting.models import build_pipeline, choose_estimator
from tests._forecasting_helpers import tiny_history
from greenmpc.forecasting.features import build_solar_features


def test_estimator_selection_is_deterministic() -> None:
    cfg = load_forecasting_config("configs/forecasting.yaml")
    _, choice1 = choose_estimator(cfg, 0.5)
    _, choice2 = choose_estimator(cfg, 0.5)
    assert choice1.estimator_class == choice2.estimator_class


def test_pipeline_fits_small_fixture() -> None:
    _, park = tiny_history()
    cfg = load_forecasting_config("configs/forecasting.yaml")
    result = build_solar_features(park, cfg)
    rows = result.frame[result.frame["horizon_hours"] == 1].head(40)
    pipe, _ = build_pipeline(result.feature_columns, result.categorical_columns, cfg, 0.5)
    pipe.fit(rows[result.feature_columns], rows[result.target_column])
    assert len(pipe.predict(rows[result.feature_columns].head(3))) == 3
