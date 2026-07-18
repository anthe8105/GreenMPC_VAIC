from __future__ import annotations

from pathlib import Path

from greenmpc.data.dataset_builder import load_dataset_build_config
from greenmpc.data.weather_processing import process_nasa_power


def test_weather_parses_utc_and_missing_sentinel(tmp_path: Path) -> None:
    path = tmp_path / "nasa.csv"
    path.write_text(
        "-BEGIN HEADER-\n"
        "Parameter(s): \n"
        "ALLSKY_SFC_SW_DWN     CERES SYN1deg All Sky Surface Shortwave Downward Irradiance (Wh/m^2) \n"
        "T2M                   MERRA-2 Temperature at 2 Meters (C) \n"
        "RH2M                  MERRA-2 Relative Humidity at 2 Meters (%) \n"
        "PRECTOTCORR           MERRA-2 Precipitation Corrected (mm/day) \n"
        "WS10M                 MERRA-2 Wind Speed at 10 Meters (m/s) \n"
        "-END HEADER-\n"
        "YEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN,T2M,RH2M,PRECTOTCORR,WS10M\n"
        "2013,1,1,0,0,-999,70,0,2\n",
        encoding="utf-8",
    )
    cfg = load_dataset_build_config("configs/dataset_build.yaml")

    weather, meta = process_nasa_power(path, cfg)

    assert "timestamp_utc" in weather
    assert meta["missing_count_per_parameter"]["T2M"] == 1
    assert meta["units"]["ALLSKY_SFC_SW_DWN"] == "Wh/m^2"
