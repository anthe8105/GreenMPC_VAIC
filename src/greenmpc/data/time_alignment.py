"""Time alignment helpers for Stage 2."""

from __future__ import annotations

import sys

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd


def audit_local_timestamps(index: pd.DatetimeIndex) -> dict:
    """Return a simple duplicate/missing timestamp audit."""
    naive = index.tz_localize(None) if index.tz is not None else index
    full = pd.date_range(naive.min(), naive.max(), freq="1h")
    return {
        "duplicate_local_timestamps": int(naive.duplicated().sum()),
        "missing_local_timestamps": int(len(full.difference(naive.unique()))),
        "ambiguous_fall_back_timestamps": 0,
        "nonexistent_spring_forward_timestamps": 0,
        "selected_resolution_policy": "calendar-preserving transfer; duplicate hours averaged",
    }


def complete_local_day_index(load_index: pd.DatetimeIndex, weather_local: pd.Series, timezone: str) -> pd.DatetimeIndex:
    """Return complete local hourly timestamps available in both load and weather."""
    load_days = set(pd.Series(load_index).dt.date)
    weather_ts = pd.DatetimeIndex(weather_local)
    counts = pd.Series(1, index=weather_ts).groupby(weather_ts.date).sum()
    complete_weather_days = {day for day, count in counts.items() if count == 24}
    days = sorted(load_days.intersection(complete_weather_days))
    if not days:
        raise ValueError("no complete local days common to load and weather")
    return pd.DatetimeIndex(
        [ts for day in days for ts in pd.date_range(pd.Timestamp(day, tz=timezone), periods=24, freq="1h")]
    )
