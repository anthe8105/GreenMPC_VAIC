from __future__ import annotations

from greenmpc.forecasting.config import load_forecasting_config
from greenmpc.forecasting.features import build_load_features
from greenmpc.forecasting.splits import assign_chronological_splits
from tests._forecasting_helpers import tiny_history


def test_chronological_split_boundaries_do_not_overlap() -> None:
    tenant, park = tiny_history(hours=5200)
    cfg = load_forecasting_config("configs/forecasting.yaml")
    features = build_load_features(tenant, park, cfg).frame
    split, boundaries, _ = assign_chronological_splits(features, cfg)
    assert boundaries.train_end < boundaries.validation_start
    assert boundaries.validation_end < boundaries.test_start
    assert split.groupby("target_timestamp_local")["split"].nunique().max() == 1
