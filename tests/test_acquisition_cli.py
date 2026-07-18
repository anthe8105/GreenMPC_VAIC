from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from greenmpc.data import acquisition
from greenmpc.data.acquisition import acquire_sources, status_table
from greenmpc.data.download import DownloadResult, sha256_file


CONFIG_PATH = Path("configs/data_sources.yaml")


def _raw_config(tmp_path: Path) -> dict:
    data = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    data["storage"]["raw_root"] = "data/raw"
    data["storage"]["provenance_root"] = "data/provenance"
    for source in data["sources"].values():
        source["destination_directory"] = f"data/raw/{source['source_id']}"
    return data


def _write_config(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "configs"
    path.mkdir()
    config_path = path / "data_sources.yaml"
    config_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return config_path


def _patch_project(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "data/raw").mkdir(parents=True)
    (tmp_path / "data/provenance").mkdir(parents=True)
    monkeypatch.setattr(acquisition, "PROJECT_ROOT", tmp_path)


def test_offline_missing_cache_fails_clearly(monkeypatch, tmp_path: Path) -> None:
    _patch_project(monkeypatch, tmp_path)
    config_path = _write_config(tmp_path, _raw_config(tmp_path))

    result = acquire_sources(
        source_names=["uci-load"],
        offline=True,
        config_path=config_path,
    )

    assert result == 1


def test_offline_makes_no_network_call(monkeypatch, tmp_path: Path) -> None:
    _patch_project(monkeypatch, tmp_path)
    data = _raw_config(tmp_path)
    config_path = _write_config(tmp_path, data)
    source = data["sources"]["vietnam_tariff_reference"]
    target_dir = tmp_path / source["destination_directory"]
    target_dir.mkdir(parents=True)
    target = target_dir / source["file_name"]
    target.write_text(
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

    def fail_download(*args, **kwargs):
        raise AssertionError("network should not be called")

    monkeypatch.setattr(acquisition, "download_file", fail_download)
    result = acquire_sources(
        source_names=["tariff"],
        offline=True,
        config_path=config_path,
    )

    assert result == 0


def test_offline_missing_tariff_cache_fails(monkeypatch, tmp_path: Path) -> None:
    _patch_project(monkeypatch, tmp_path)
    config_path = _write_config(tmp_path, _raw_config(tmp_path))

    result = acquire_sources(
        source_names=["tariff"],
        offline=True,
        config_path=config_path,
    )

    assert result == 1


def test_force_reacquires(monkeypatch, tmp_path: Path) -> None:
    _patch_project(monkeypatch, tmp_path)
    data = _raw_config(tmp_path)
    config_path = _write_config(tmp_path, data)
    calls = {"count": 0}

    def fake_download(url, destination, **kwargs):
        calls["count"] += 1
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("html", encoding="utf-8")
        return DownloadResult(
            url=url,
            final_url=url,
            local_path=destination,
            byte_size=destination.stat().st_size,
            sha256=sha256_file(destination),
            content_type="text/html",
            content_length=str(destination.stat().st_size),
            etag=None,
            last_modified=None,
            from_cache=False,
        )

    monkeypatch.setattr(acquisition, "download_file", fake_download)
    result = acquire_sources(
        source_names=["tariff"],
        force=True,
        config_path=config_path,
    )

    assert result == 0
    assert calls["count"] == 1


def test_status_displays_cached_state(monkeypatch, tmp_path: Path) -> None:
    _patch_project(monkeypatch, tmp_path)
    data = _raw_config(tmp_path)
    config_path = _write_config(tmp_path, data)

    statuses = status_table(config_path)

    assert {status.source_id for status in statuses} == {
        "uci_electricity_load_diagrams",
        "uci_steel_industry",
        "nasa_power_hourly",
        "vietnam_tariff_reference",
    }
