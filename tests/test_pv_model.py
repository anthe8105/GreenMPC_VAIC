from __future__ import annotations

import pandas as pd
import pytest
from dataclasses import replace

from greenmpc.data.dataset_builder import load_dataset_build_config
from greenmpc.data.pv_model import build_pv_frame


def test_pv_is_capped_and_not_measured() -> None:
    cfg = load_dataset_build_config("configs/dataset_build.yaml")
    ts = pd.date_range("2013-01-01", periods=2, freq="1h", tz="Asia/Ho_Chi_Minh")
    weather = pd.DataFrame({"timestamp_local": ts, "timestamp_utc": ts.tz_convert("UTC"), "ALLSKY_SFC_SW_DWN": [0.0, 99.0]})
    weather.attrs["units"] = {"ALLSKY_SFC_SW_DWN": "Wh/m^2"}

    pv = build_pv_frame(weather, cfg.pv)

    assert pv["park_pv_available_kw"].iloc[0] == 0
    assert pv["park_pv_available_kw"].max() <= cfg.pv.installed_capacity_kw
    assert not pv["pv_is_measured"].any()


def test_wh_per_m2_conversion_divides_by_1000() -> None:
    cfg = load_dataset_build_config("configs/dataset_build.yaml")
    ts = pd.date_range("2013-01-01", periods=1, freq="1h", tz="Asia/Ho_Chi_Minh")
    weather = pd.DataFrame({"timestamp_local": ts, "timestamp_utc": ts.tz_convert("UTC"), "ALLSKY_SFC_SW_DWN": [500.0]})
    weather.attrs["units"] = {"ALLSKY_SFC_SW_DWN": "Wh/m^2"}
    pv = build_pv_frame(weather, cfg.pv)
    assert pv["solar_resource_normalized"].iloc[0] == 0.5
    assert pv["park_pv_available_kw"].iloc[0] == cfg.pv.installed_capacity_kw * 0.5 * cfg.pv.performance_ratio
    assert pv["park_pv_available_kwh"].iloc[0] == pv["park_pv_available_kw"].iloc[0]
    assert pv["pv_formula_version"].iloc[0] == "simple_capacity_factor_v2"


def test_w_per_m2_conversion_divides_by_reference_irradiance() -> None:
    cfg = load_dataset_build_config("configs/dataset_build.yaml")
    pv_cfg = replace(cfg.pv, expected_raw_unit="W/m^2")
    ts = pd.date_range("2013-01-01", periods=1, freq="1h", tz="Asia/Ho_Chi_Minh")
    weather = pd.DataFrame({"timestamp_local": ts, "timestamp_utc": ts.tz_convert("UTC"), "ALLSKY_SFC_SW_DWN": [750.0]})
    weather.attrs["units"] = {"ALLSKY_SFC_SW_DWN": "W/m^2"}
    pv = build_pv_frame(weather, pv_cfg)
    assert pv["solar_resource_normalized"].iloc[0] == 0.75


def test_kwh_per_m2_conversion_uses_hourly_reference() -> None:
    cfg = load_dataset_build_config("configs/dataset_build.yaml")
    pv_cfg = replace(cfg.pv, expected_raw_unit="kWh/m^2")
    ts = pd.date_range("2013-01-01", periods=1, freq="1h", tz="Asia/Ho_Chi_Minh")
    weather = pd.DataFrame({"timestamp_local": ts, "timestamp_utc": ts.tz_convert("UTC"), "ALLSKY_SFC_SW_DWN": [0.75]})
    weather.attrs["units"] = {"ALLSKY_SFC_SW_DWN": "kWh/m^2"}
    pv = build_pv_frame(weather, pv_cfg)
    assert pv["solar_resource_normalized"].iloc[0] == 0.75


def test_unsupported_and_ambiguous_units_fail() -> None:
    cfg = load_dataset_build_config("configs/dataset_build.yaml")
    ts = pd.date_range("2013-01-01", periods=1, freq="1h", tz="Asia/Ho_Chi_Minh")
    weather = pd.DataFrame({"timestamp_local": ts, "timestamp_utc": ts.tz_convert("UTC"), "ALLSKY_SFC_SW_DWN": [500.0]})
    weather.attrs["units"] = {"ALLSKY_SFC_SW_DWN": "kWh"}
    with pytest.raises(ValueError, match="unsupported or ambiguous"):
        build_pv_frame(weather, cfg.pv)


def test_capacity_clipping_occurs_after_conversion() -> None:
    cfg = load_dataset_build_config("configs/dataset_build.yaml")
    ts = pd.date_range("2013-01-01", periods=1, freq="1h", tz="Asia/Ho_Chi_Minh")
    weather = pd.DataFrame({"timestamp_local": ts, "timestamp_utc": ts.tz_convert("UTC"), "ALLSKY_SFC_SW_DWN": [2000.0]})
    weather.attrs["units"] = {"ALLSKY_SFC_SW_DWN": "Wh/m^2"}
    pv = build_pv_frame(weather, cfg.pv)
    assert pv["park_pv_available_kw"].iloc[0] == cfg.pv.installed_capacity_kw
    assert pv["pv_clipped_to_capacity"].iloc[0]
