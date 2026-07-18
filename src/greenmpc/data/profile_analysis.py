"""Candidate anonymous profile metrics."""

from __future__ import annotations

import math
import sys

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd


def analyze_profiles(hourly: pd.DataFrame, cfg: object) -> pd.DataFrame:
    """Calculate scale-independent quality and behavior metrics for each client."""
    rows = []
    hours = pd.Series(hourly.index.hour, index=hourly.index)
    weekday = pd.Series(hourly.index.dayofweek < 5, index=hourly.index)
    for col in hourly.columns:
        s = hourly[col].astype(float)
        valid = s.dropna()
        if valid.empty:
            continue
        nonzero_fraction = float((valid > 0).mean())
        valid_fraction = float(s.notna().mean())
        p95 = float(valid.quantile(0.95))
        mean = float(valid.mean())
        median = float(valid.median())
        std = float(valid.std() or 0)
        daytime = valid[(hours.loc[valid.index] >= 8) & (hours.loc[valid.index] < 18)]
        nighttime = valid[(hours.loc[valid.index] < 6) | (hours.loc[valid.index] >= 22)]
        morning = valid[(hours.loc[valid.index] >= 6) & (hours.loc[valid.index] < 12)]
        afternoon = valid[(hours.loc[valid.index] >= 12) & (hours.loc[valid.index] < 18)]
        evening = valid[(hours.loc[valid.index] >= 18) & (hours.loc[valid.index] < 22)]
        wk = valid[weekday.loc[valid.index]]
        we = valid[~weekday.loc[valid.index]]
        daily_peak_hours = valid.groupby(valid.index.date).idxmax().map(lambda x: x.hour)
        counts = daily_peak_hours.value_counts(normalize=True)
        entropy = float(-(counts * counts.map(lambda x: math.log(x))).sum()) if not counts.empty else 0.0
        missing = s.isna()
        rows.append({
            "source_client_id": col,
            "valid_fraction": valid_fraction,
            "nonzero_fraction": nonzero_fraction,
            "missing_hour_count": int(missing.sum()),
            "longest_missing_run_hours": _longest_run(missing.tolist()),
            "active_day_count": int((valid.groupby(valid.index.date).sum() > 0).sum()),
            "mean_load": mean,
            "median_load": median,
            "standard_deviation": std,
            "coefficient_of_variation": std / mean if mean > 0 else 999,
            "p05": float(valid.quantile(0.05)),
            "p25": float(valid.quantile(0.25)),
            "p75": float(valid.quantile(0.75)),
            "p95": p95,
            "p99": float(valid.quantile(0.99)),
            "maximum": float(valid.max()),
            "load_factor_mean_over_p95": mean / p95 if p95 > 0 else 0,
            "peak_to_mean_ratio": float(valid.max()) / mean if mean > 0 else 999,
            "p99_to_median_ratio": float(valid.quantile(0.99)) / median if median > 0 else 999,
            "weekday_mean": float(wk.mean()) if not wk.empty else 0,
            "weekend_mean": float(we.mean()) if not we.empty else 0,
            "weekday_to_weekend_ratio": float(wk.mean() / we.mean()) if not we.empty and we.mean() else 999,
            "daytime_mean": float(daytime.mean()) if not daytime.empty else 0,
            "nighttime_mean": float(nighttime.mean()) if not nighttime.empty else 0,
            "daytime_to_nighttime_ratio": float(daytime.mean() / nighttime.mean()) if not nighttime.empty and nighttime.mean() else 999,
            "overnight_baseload_ratio": float(nighttime.mean() / p95) if p95 > 0 and not nighttime.empty else 0,
            "morning_mean": float(morning.mean()) if not morning.empty else 0,
            "afternoon_mean": float(afternoon.mean()) if not afternoon.empty else 0,
            "evening_mean": float(evening.mean()) if not evening.empty else 0,
            "two_shift_score": float((morning.mean() + afternoon.mean()) / (2 * p95)) if p95 > 0 else 0,
            "business_hour_concentration": float(daytime.sum() / valid.sum()) if valid.sum() > 0 and not daytime.empty else 0,
            "weekend_reduction_fraction": float(1 - we.mean() / wk.mean()) if not wk.empty and not we.empty and wk.mean() else 0,
            "hourly_ramp_p95": float(valid.diff().abs().quantile(0.95)),
            "daily_peak_hour_mode": int(daily_peak_hours.mode().iloc[0]) if not daily_peak_hours.empty else -1,
            "daily_peak_hour_entropy": entropy,
            "lag_24_autocorrelation": float(valid.autocorr(24)) if len(valid) > 24 else 0,
            "lag_168_autocorrelation": float(valid.autocorr(168)) if len(valid) > 168 else 0,
        })
    out = pd.DataFrame(rows).fillna(0)
    out["eligible"] = (
        (out["valid_fraction"] >= cfg.uci_load.minimum_valid_fraction)
        & (out["nonzero_fraction"] >= cfg.uci_load.minimum_nonzero_fraction)
        & (out["p95"] > 0)
    )
    out["exclusion_reason"] = out["eligible"].map(lambda x: "" if x else "quality_threshold")
    return out


def _longest_run(flags: list[bool]) -> int:
    longest = current = 0
    for flag in flags:
        current = current + 1 if flag else 0
        longest = max(longest, current)
    return longest
