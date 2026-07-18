from __future__ import annotations

import zipfile
from pathlib import Path

from greenmpc.data.dataset_builder import load_dataset_build_config
from greenmpc.data.raw_load_reader import load_hourly_profiles


def test_reads_zip_decimal_comma_and_filters_year(tmp_path: Path) -> None:
    text = '"";"MT_001"\n"2012-01-01 00:15:00";9,0\n"2013-01-01 00:15:00";1,5\n"2013-01-01 00:30:00";2,5\n'
    path = tmp_path / "load.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("LD2011_2014.txt", text)
    cfg = load_dataset_build_config("configs/dataset_build.yaml")

    hourly, report = load_hourly_profiles(path, cfg)

    assert hourly["MT_001"].dropna().iloc[0] == 2.0
    assert report["source_year_rows"] == 2
