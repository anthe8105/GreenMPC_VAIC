"""Chronological target-timestamp splits for forecasting."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd

from greenmpc.forecasting.config import ForecastingConfig
from greenmpc.forecasting.exceptions import ForecastDataError


@dataclass(frozen=True)
class SplitBoundaries:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def assign_chronological_splits(features: pd.DataFrame, cfg: ForecastingConfig) -> tuple[pd.DataFrame, SplitBoundaries, dict]:
    if "target_timestamp_local" not in features:
        raise ForecastDataError("features must include target_timestamp_local")
    data = features.copy()
    data["target_timestamp_local"] = pd.to_datetime(data["target_timestamp_local"])
    unique_targets = sorted(data["target_timestamp_local"].unique())
    if not unique_targets:
        raise ForecastDataError("no target timestamps available for splitting")
    n = len(unique_targets)
    train_n = int(n * cfg.split.train_fraction)
    validation_n = int(n * cfg.split.validation_fraction)
    if n - train_n - validation_n < cfg.split.minimum_test_days * 24:
        raise ForecastDataError("test split does not contain the configured minimum number of days")
    train_targets = set(unique_targets[:train_n])
    validation_targets = set(unique_targets[train_n : train_n + validation_n])
    test_targets = set(unique_targets[train_n + validation_n :])
    data["split"] = data["target_timestamp_local"].map(
        lambda ts: "train" if ts in train_targets else "validation" if ts in validation_targets else "test"
    )
    if data.groupby("target_timestamp_local")["split"].nunique().max() != 1:
        raise ForecastDataError("one target timestamp appears in multiple splits")
    boundaries = SplitBoundaries(
        train_start=pd.Timestamp(min(train_targets)),
        train_end=pd.Timestamp(max(train_targets)),
        validation_start=pd.Timestamp(min(validation_targets)),
        validation_end=pd.Timestamp(max(validation_targets)),
        test_start=pd.Timestamp(min(test_targets)),
        test_end=pd.Timestamp(max(test_targets)),
    )
    manifest = {
        "first_usable_origin": str(data["forecast_origin_local"].min()),
        "last_usable_origin": str(data["forecast_origin_local"].max()),
        "train_target_start": str(boundaries.train_start),
        "train_target_end": str(boundaries.train_end),
        "validation_target_start": str(boundaries.validation_start),
        "validation_target_end": str(boundaries.validation_end),
        "test_target_start": str(boundaries.test_start),
        "test_target_end": str(boundaries.test_end),
        "sample_counts_by_task": data.groupby(["task", "split"]).size().to_dict() if "task" in data else {},
        "sample_counts_by_horizon": data.groupby(["horizon_hours", "split"]).size().to_dict(),
        "excluded_warm_up_hours": cfg.general.minimum_history_hours,
        "excluded_boundary_hours": max(cfg.general.forecast_horizons_hours),
    }
    return data, boundaries, manifest


def write_split_manifest(path: str | Path, manifest: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(_stringify_keys(manifest), indent=2), encoding="utf-8")


def _stringify_keys(value):
    if isinstance(value, dict):
        return {str(key): _stringify_keys(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stringify_keys(item) for item in value]
    return value
