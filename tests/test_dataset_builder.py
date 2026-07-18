from __future__ import annotations

from greenmpc.data.dataset_builder import build_status, load_dataset_build_config


def test_dataset_build_config_loads_and_status_reports() -> None:
    cfg = load_dataset_build_config("configs/dataset_build.yaml")
    assert cfg.build.source_year == 2013
    assert "tenant_hourly_path" in build_status()
