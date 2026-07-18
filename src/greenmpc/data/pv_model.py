"""Unit-aware simple PV availability derivation."""

from __future__ import annotations

import sys

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd


def build_pv_frame(weather: pd.DataFrame, cfg: object) -> pd.DataFrame:
    resource = weather[cfg.irradiance_parameter].fillna(0).clip(lower=0)
    unit = "kWh/m^2"
    if "kwh" in unit.lower():
        pv_kwh = cfg.installed_capacity_kw * resource * cfg.performance_ratio
        pv_kw = pv_kwh
    elif "w/m" in unit.lower():
        pv_kw = cfg.installed_capacity_kw * resource / 1000.0 * cfg.performance_ratio
        pv_kwh = pv_kw
    else:
        raise ValueError(f"unknown solar resource unit: {unit}")
    cap = cfg.installed_capacity_kw * cfg.maximum_output_fraction
    flag = pd.Series("ok", index=weather.index)
    flag[pv_kw > cap] = "clipped_to_capacity"
    pv_kw = pv_kw.clip(upper=cap)
    pv_kw[resource <= cfg.nighttime_threshold] = 0.0
    pv_kwh = pv_kw
    return pd.DataFrame({
        "timestamp_local": weather["timestamp_local"],
        "timestamp_utc": weather["timestamp_utc"],
        "solar_resource_raw": resource,
        "solar_resource_unit": unit,
        "park_pv_available_kw": pv_kw,
        "park_pv_available_kwh": pv_kwh,
        "installed_pv_capacity_kw": cfg.installed_capacity_kw,
        "performance_ratio": cfg.performance_ratio,
        "pv_model_name": cfg.model_name,
        "pv_is_derived": True,
        "pv_is_measured": False,
        "pv_quality_flag": flag,
    })
