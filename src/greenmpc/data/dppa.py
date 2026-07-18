"""DPPA scenario assumptions for Stage 2 datasets."""

from __future__ import annotations

import sys

sys.modules.setdefault("numexpr", None)
sys.modules.setdefault("bottleneck", None)
import pandas as pd


def build_dppa_frame(times: pd.DataFrame, cfg: object) -> pd.DataFrame:
    if cfg.base_available_capacity_kw < 0:
        raise ValueError("dppa availability must be nonnegative")
    if cfg.base_price_vnd_per_kwh < 0:
        raise ValueError("dppa price must be nonnegative")
    return pd.DataFrame({
        "timestamp_local": times["timestamp_local"],
        "timestamp_utc": times["timestamp_utc"],
        "dppa_enabled": cfg.enabled,
        "dppa_available_kw": cfg.base_available_capacity_kw,
        "dppa_price_vnd_per_kwh": cfg.base_price_vnd_per_kwh,
        "dppa_renewable_eligible": cfg.renewable_eligible,
        "dppa_availability_is_assumption": True,
        "dppa_price_is_assumption": True,
        "dppa_values_are_assumptions": True,
    })
