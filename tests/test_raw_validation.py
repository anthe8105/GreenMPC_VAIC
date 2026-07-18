from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import yaml

from greenmpc.data.raw_validation import (
    extract_steel_csv,
    inspect_nasa_csv,
    inspect_steel_csv,
    inspect_tariff_reference,
    inspect_uci_electricity_zip,
    validate_no_zip_path_traversal,
    validate_zip,
)


def _zip(path: Path, files: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return path


def test_valid_zip_passes(tmp_path: Path) -> None:
    path = _zip(tmp_path / "valid.zip", {"file.csv": b"a,b\n1,2\n"})

    report = validate_zip(path)

    assert report["zip_valid"]


def test_corrupt_zip_fails(tmp_path: Path) -> None:
    path = tmp_path / "bad.zip"
    path.write_bytes(b"not zip")

    with pytest.raises(ValueError, match="valid ZIP"):
        validate_zip(path)


def test_zip_path_traversal_is_rejected(tmp_path: Path) -> None:
    path = _zip(tmp_path / "bad.zip", {"../evil.csv": b"a,b\n"})

    with pytest.raises(ValueError, match="path traversal"):
        validate_no_zip_path_traversal(path)


def test_large_uci_archive_not_extracted_by_default_and_sample_works(tmp_path: Path) -> None:
    body = "date;client_a;client_b\n2011-01-01 00:00:00;1,2;3,4\n".encode("latin-1")
    path = _zip(tmp_path / "load.zip", {"LD2011_2014.txt": body})

    report = inspect_uci_electricity_zip(path)

    assert not report["large_file_extracted"]
    assert report["sample_client_column_count"] == 2
    assert report["numeric_client_values_in_first_20"] >= 1


def test_steel_extract_and_inspect(tmp_path: Path) -> None:
    csv_body = b"date,Usage_kWh,Lagging_Current_Reactive.Power_kVarh,WeekStatus\n2018-01-01 00:15:00,10.1,2.0,Weekday\n"
    zip_path = _zip(tmp_path / "steel.zip", {"Steel_industry_data.csv": csv_body})

    csv_path = extract_steel_csv(zip_path, tmp_path)
    report = inspect_steel_csv(csv_path)

    assert report["row_count"] == 1
    assert "Usage_kWh" in report["numeric_fields"]


def test_nasa_error_html_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "nasa.csv"
    path.write_text("<html>error</html>", encoding="utf-8")

    with pytest.raises(ValueError, match="HTML"):
        inspect_nasa_csv(path, ["T2M"], "2013-01-01", "2013-12-31")


def test_nasa_expected_parameters_checked(tmp_path: Path) -> None:
    path = tmp_path / "nasa.csv"
    path.write_text(
        "NASA header\nYEAR,MO,DY,HR,T2M,RH2M,ALLSKY_SFC_SW_DWN,PRECTOTCORR,WS10M\n"
        "2013,1,1,0,25,70,0,0,2\n",
        encoding="utf-8",
    )

    report = inspect_nasa_csv(
        path,
        ["ALLSKY_SFC_SW_DWN", "T2M", "RH2M", "PRECTOTCORR", "WS10M"],
        "2013-01-01",
        "2013-12-31",
    )

    assert report["expected_parameters_present"]
    assert report["time_standard"] == "UTC"


def test_nasa_missing_parameter_fails(tmp_path: Path) -> None:
    path = tmp_path / "nasa.csv"
    path.write_text("YEAR,MO,DY,HR,T2M\n2013,1,1,0,25\n", encoding="utf-8")

    with pytest.raises(ValueError, match="expected parameter"):
        inspect_nasa_csv(path, ["T2M", "WS10M"], "2013-01-01", "2013-12-31")


def test_tariff_reference_guards_unselected_category(tmp_path: Path) -> None:
    path = tmp_path / "tariff_reference.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "decision_number": "Decision No. 1279/QD-BCT",
                "issue_date": "2025-05-09",
                "effective_date": None,
                "selected_customer_category": None,
                "selected_voltage_level": None,
                "operational_values_imported": False,
                "manual_review_required": True,
            }
        ),
        encoding="utf-8",
    )

    report = inspect_tariff_reference(path)

    assert report["selected_customer_category"] is None
