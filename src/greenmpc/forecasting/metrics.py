"""Forecast metrics and quantile post-processing."""

from __future__ import annotations

import math
import sys
from typing import Iterable

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import numpy as np
import pandas as pd


def reconcile_quantiles(df: pd.DataFrame, task: str, capacity_kw: float | None = None) -> pd.DataFrame:
    data = df.copy()
    raw_cols = ["raw_p10_kw", "raw_p50_kw", "raw_p90_kw"]
    corrected = np.sort(data[raw_cols].to_numpy(dtype=float), axis=1)
    data["quantile_corrected"] = (data[raw_cols].to_numpy(dtype=float) != corrected).any(axis=1)
    data["p10_kw"], data["p50_kw"], data["p90_kw"] = corrected[:, 0], corrected[:, 1], corrected[:, 2]
    data["clipped_to_zero"] = (data[["p10_kw", "p50_kw", "p90_kw"]] < 0).any(axis=1)
    data[["p10_kw", "p50_kw", "p90_kw"]] = data[["p10_kw", "p50_kw", "p90_kw"]].clip(lower=0.0)
    if task == "solar":
        cap = float(capacity_kw or data.get("installed_pv_capacity_kw", pd.Series([0])).max())
        data["clipped_to_capacity"] = (data[["p10_kw", "p50_kw", "p90_kw"]] > cap).any(axis=1)
        data[["p10_kw", "p50_kw", "p90_kw"]] = data[["p10_kw", "p50_kw", "p90_kw"]].clip(upper=cap)
        nighttime = ~data.get("target_is_daylight", pd.Series([True] * len(data))).astype(bool)
        data["forced_nighttime_zero"] = nighttime & (data[["p10_kw", "p50_kw", "p90_kw"]].abs().sum(axis=1) > 0)
        data.loc[nighttime, ["p10_kw", "p50_kw", "p90_kw"]] = 0.0
    else:
        data["clipped_to_capacity"] = False
        data["forced_nighttime_zero"] = False
    return data


def point_metrics(y_true: Iterable[float], y_pred: Iterable[float], zero_tol: float = 1e-9) -> dict[str, float | None]:
    y = np.asarray(list(y_true), dtype=float)
    p = np.asarray(list(y_pred), dtype=float)
    err = p - y
    mae = float(np.mean(np.abs(err)))
    rmse = float(math.sqrt(np.mean(err**2)))
    denom = float(np.sum(np.abs(y)))
    wape = None if denom <= zero_tol else float(np.sum(np.abs(err)) / denom)
    mean_target = float(np.mean(np.abs(y)))
    return {
        "MAE": mae,
        "RMSE": rmse,
        "WAPE": wape,
        "normalized_MAE_by_mean_target": None if mean_target <= zero_tol else mae / mean_target,
        "bias": float(np.mean(err)),
        "maximum_absolute_error": float(np.max(np.abs(err))),
    }


def pinball_loss(y_true: Iterable[float], y_pred: Iterable[float], quantile: float) -> float:
    y = np.asarray(list(y_true), dtype=float)
    p = np.asarray(list(y_pred), dtype=float)
    diff = y - p
    return float(np.mean(np.maximum(quantile * diff, (quantile - 1) * diff)))


def interval_metrics(y_true: Iterable[float], lower: Iterable[float], upper: Iterable[float], nominal: float, zero_tol: float = 1e-9) -> dict[str, float | None]:
    y = np.asarray(list(y_true), dtype=float)
    lo = np.asarray(list(lower), dtype=float)
    hi = np.asarray(list(upper), dtype=float)
    covered = (y >= lo) & (y <= hi)
    width = hi - lo
    mean_target = float(np.mean(np.abs(y)))
    return {
        "empirical_coverage": float(np.mean(covered)),
        "nominal_coverage": nominal,
        "coverage_error": float(np.mean(covered) - nominal),
        "average_interval_width": float(np.mean(width)),
        "normalized_interval_width": None if mean_target <= zero_tol else float(np.mean(width) / mean_target),
        "below_interval_frequency": float(np.mean(y < lo)),
        "above_interval_frequency": float(np.mean(y > hi)),
    }


def crossing_frequency(df: pd.DataFrame, prefix: str = "raw") -> float:
    a, b, c = df[f"{prefix}_p10_kw"], df[f"{prefix}_p50_kw"], df[f"{prefix}_p90_kw"]
    return float(((a > b) | (b > c)).mean())


def skill_score(model_error: float | None, baseline_error: float | None) -> float | None:
    if model_error is None or baseline_error is None or baseline_error == 0:
        return None
    return 1.0 - model_error / baseline_error
