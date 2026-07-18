from __future__ import annotations

from pathlib import Path

from greenmpc.data.dataset_builder import load_dataset_build_config
from greenmpc.data.weather_processing import process_nasa_power


def test_weather_parses_utc_and_missing_sentinel(tmp_path: Path) -> None:
    path = tmp_path / "nasa.csv"
    path.write_text("header\nYEAR,MO,DY,HR,ALLSKY_SFC_SW_DWN,T2M,RH2M,PRECTOTCORR,WS10M\n2013,1,1,0,0,-999,70,0,2\n", encoding="utf-8")
    cfg = load_dataset_build_config("configs/dataset_build.yaml")

    weather, meta = process_nasa_power(path, cfg)

    assert "timestamp_utc" in weather
    assert meta["missing_count_per_parameter"]["T2M"] == 1
