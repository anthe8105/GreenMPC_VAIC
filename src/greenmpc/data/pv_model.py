"""Unit-aware simple PV availability derivation."""

from __future__ import annotations

import sys

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd


SUPPORTED_SOLAR_UNITS = {
    "W/m^2": "mean_irradiance_wm2",
    "W/m2": "mean_irradiance_wm2",
    "Wh/m^2": "hourly_irradiation_wh_m2",
    "Wh/m2": "hourly_irradiation_wh_m2",
    "kWh/m^2": "hourly_irradiation_kwh_m2",
    "kWh/m2": "hourly_irradiation_kwh_m2",
}


def build_pv_frame(weather: pd.DataFrame, cfg: object) -> pd.DataFrame:
    """Derive PV availability using explicit solar-resource units."""
    unit = _canonical_unit(str(weather.attrs.get("units", {}).get(cfg.irradiance_parameter, "")))
    expected = _canonical_unit(str(cfg.expected_raw_unit))
    if unit != expected:
        raise ValueError(f"NASA solar unit mismatch for {cfg.irradiance_parameter}: expected {expected}, got {unit}")
    branch = SUPPORTED_SOLAR_UNITS[unit]
    raw_resource = pd.to_numeric(weather[cfg.irradiance_parameter], errors="coerce")
    negative_input = raw_resource < 0
    resource = raw_resource.fillna(0.0).clip(lower=0.0)
    normalized = _normalized_solar_input(resource, branch, cfg)
    pv_kw = cfg.installed_capacity_kw * normalized * cfg.performance_ratio
    cap = cfg.installed_capacity_kw * cfg.maximum_output_fraction
    clipped = pv_kw > cap
    pv_kw = pv_kw.clip(upper=cap)
    pv_kw[resource <= cfg.nighttime_threshold] = 0.0
    pv_kwh = pv_kw
    flag = pd.Series("ok", index=weather.index)
    flag[negative_input] = "negative_input_clipped_to_zero"
    flag[clipped] = "clipped_to_capacity"
    return pd.DataFrame({
        "timestamp_local": weather["timestamp_local"],
        "timestamp_utc": weather["timestamp_utc"],
        "solar_resource_raw": raw_resource,
        "solar_resource_unit": unit,
        "solar_resource_normalized": normalized,
        "park_pv_available_kw": pv_kw,
        "park_pv_available_kwh": pv_kwh,
        "pv_conversion_branch": branch,
        "pv_formula_version": cfg.formula_version,
        "pv_clipped_to_capacity": clipped,
        "installed_pv_capacity_kw": cfg.installed_capacity_kw,
        "performance_ratio": cfg.performance_ratio,
        "pv_model_name": cfg.model_name,
        "pv_is_derived": True,
        "pv_is_measured": False,
        "pv_quality_flag": flag,
    })


def _canonical_unit(unit: str) -> str:
    explicit_aliases = {
        "W/m^2": "W/m^2",
        "W/m2": "W/m^2",
        "Wh/m^2": "Wh/m^2",
        "Wh/m2": "Wh/m^2",
        "kWh/m^2": "kWh/m^2",
        "kWh/m2": "kWh/m^2",
    }
    if unit not in explicit_aliases:
        raise ValueError(f"unsupported or ambiguous solar resource unit: {unit}")
    return explicit_aliases[unit]


def _normalized_solar_input(resource: pd.Series, branch: str, cfg: object) -> pd.Series:
    if branch == "mean_irradiance_wm2":
        return resource / cfg.reference_irradiance_wm2
    if branch == "hourly_irradiation_wh_m2":
        return (resource / 1000.0) / cfg.reference_hourly_irradiation_kwh_m2
    if branch == "hourly_irradiation_kwh_m2":
        return resource / cfg.reference_hourly_irradiation_kwh_m2
    raise ValueError(f"unsupported PV conversion branch: {branch}")
