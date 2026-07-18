from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from greenmpc.data.source_config import load_data_source_config


CONFIG_PATH = Path("configs/data_sources.yaml")


def _raw_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _write(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "data_sources.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _mutated(tmp_path: Path, mutate) -> Path:
    data = deepcopy(_raw_config())
    mutate(data)
    return _write(tmp_path, data)


def test_valid_source_configuration_loads() -> None:
    config = load_data_source_config(CONFIG_PATH)

    assert config.schema_version == 1
    assert set(source.source_id for source in config.sources.values()) == {
        "uci_electricity_load_diagrams",
        "uci_steel_industry",
        "nasa_power_hourly",
        "vietnam_tariff_reference",
    }


def test_invalid_url_scheme_fails(tmp_path: Path) -> None:
    path = _mutated(
        tmp_path,
        lambda data: data["sources"]["uci_steel_industry"].update(
            {"download_url": "http://example.test/file.zip"}
        ),
    )

    with pytest.raises(ValueError, match="download_url"):
        load_data_source_config(path)


def test_invalid_nasa_coordinates_fail(tmp_path: Path) -> None:
    path = _mutated(
        tmp_path,
        lambda data: data["sources"]["nasa_power_hourly"].update({"latitude": 100.0}),
    )

    with pytest.raises(ValueError, match="latitude"):
        load_data_source_config(path)


def test_invalid_nasa_dates_fail(tmp_path: Path) -> None:
    path = _mutated(
        tmp_path,
        lambda data: data["sources"]["nasa_power_hourly"].update(
            {"start_date": "2013-12-31", "end_date": "2013-01-01"}
        ),
    )

    with pytest.raises(ValueError, match="start_date"):
        load_data_source_config(path)


def test_nasa_time_standard_must_be_utc(tmp_path: Path) -> None:
    path = _mutated(
        tmp_path,
        lambda data: data["sources"]["nasa_power_hourly"].update(
            {"time_standard": "LST"}
        ),
    )

    with pytest.raises(ValueError, match="time_standard"):
        load_data_source_config(path)


def test_duplicate_source_ids_fail(tmp_path: Path) -> None:
    path = _mutated(
        tmp_path,
        lambda data: data["sources"]["uci_steel_industry"].update(
            {"source_id": "uci_electricity_load_diagrams"}
        ),
    )

    with pytest.raises(ValueError, match="unique"):
        load_data_source_config(path)


def test_large_archive_extraction_disabled_by_default() -> None:
    config = load_data_source_config(CONFIG_PATH)

    assert not config.storage.extract_large_archives_by_default


def test_tariff_category_unselected() -> None:
    config = load_data_source_config(CONFIG_PATH)
    source = config.sources["vietnam_tariff_reference"]

    assert getattr(source, "selected_category") == "not_selected"
