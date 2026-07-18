"""Demo tariff period construction."""

from __future__ import annotations

import sys

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd


def build_tariff_frame(times: pd.DataFrame, cfg: object, grid: object) -> pd.DataFrame:
    _validate_hours(cfg.weekday_peak_hours + cfg.weekday_off_peak_hours + cfg.saturday_peak_hours + cfg.saturday_off_peak_hours + cfg.sunday_peak_hours + cfg.sunday_off_peak_hours)
    rows = []
    for ts in pd.DatetimeIndex(times["timestamp_local"]):
        period = period_for_timestamp(ts, cfg)
        price = {"off_peak": grid.off_peak_price_vnd_per_kwh, "normal": grid.normal_price_vnd_per_kwh, "peak": grid.peak_price_vnd_per_kwh}[period]
        rows.append({
            "timestamp_local": ts,
            "timestamp_utc": ts.tz_convert("UTC"),
            "tariff_period": period,
            "grid_price_vnd_per_kwh": price,
            "tariff_source_status": cfg.source_status,
            "tariff_category_selected": False,
            "tariff_voltage_level_selected": False,
            "tariff_schedule_is_demo_assumption": True,
        })
    return pd.DataFrame(rows)


def period_for_timestamp(ts: pd.Timestamp, cfg: object) -> str:
    hour = ts.hour
    dow = ts.dayofweek
    if dow < 5:
        peak, off = cfg.weekday_peak_hours, cfg.weekday_off_peak_hours
    elif dow == 5:
        peak, off = cfg.saturday_peak_hours, cfg.saturday_off_peak_hours
    else:
        peak, off = cfg.sunday_peak_hours, cfg.sunday_off_peak_hours
    if set(peak).intersection(off):
        raise ValueError("tariff period hours overlap")
    if hour in peak:
        return "peak"
    if hour in off:
        return "off_peak"
    return cfg.default_period


def _validate_hours(hours: list[int]) -> None:
    invalid = [hour for hour in hours if hour < 0 or hour > 23]
    if invalid:
        raise ValueError(f"invalid tariff hour values: {invalid}")
