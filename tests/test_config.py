from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from greenmpc.config import GreenMPCConfig, load_config


CONFIG_PATH = Path("configs/demo.yaml")


def _load_raw() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _write_config(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "demo.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def _mutated_config(tmp_path: Path, mutate) -> Path:
    data = deepcopy(_load_raw())
    mutate(data)
    return _write_config(tmp_path, data)


def test_valid_configuration_loads() -> None:
    config = load_config(CONFIG_PATH)

    assert isinstance(config, GreenMPCConfig)
    assert len(config.tenants) == 5
    assert config.mpc.solver == "HIGHS"


def test_duplicate_tenant_ids_fail(tmp_path: Path) -> None:
    path = _mutated_config(
        tmp_path,
        lambda data: data["tenants"][1].update(
            {"tenant_id": data["tenants"][0]["tenant_id"]}
        ),
    )

    with pytest.raises(ValueError, match="tenants.tenant_id"):
        load_config(path)


def test_invalid_renewable_target_fails(tmp_path: Path) -> None:
    path = _mutated_config(
        tmp_path,
        lambda data: data["tenants"][0].update({"renewable_target_fraction": 1.2}),
    )

    with pytest.raises(ValueError, match="renewable_target_fraction"):
        load_config(path)


def test_invalid_soc_ordering_fails(tmp_path: Path) -> None:
    path = _mutated_config(
        tmp_path,
        lambda data: data["battery"].update(
            {"minimum_soc_fraction": 0.95, "maximum_soc_fraction": 0.90}
        ),
    )

    with pytest.raises(ValueError, match="minimum_soc_fraction"):
        load_config(path)


def test_invalid_initial_soc_fails(tmp_path: Path) -> None:
    path = _mutated_config(
        tmp_path,
        lambda data: data["battery"].update({"initial_soc_fraction": 0.95}),
    )

    with pytest.raises(ValueError, match="initial_soc_fraction"):
        load_config(path)


def test_invalid_efficiency_fails(tmp_path: Path) -> None:
    path = _mutated_config(
        tmp_path,
        lambda data: data["battery"].update({"charge_efficiency": 0.0}),
    )

    with pytest.raises(ValueError, match="charge_efficiency"):
        load_config(path)


def test_invalid_data_split_fails(tmp_path: Path) -> None:
    path = _mutated_config(
        tmp_path,
        lambda data: data["forecasting"].update({"test_fraction": 0.2}),
    )

    with pytest.raises(ValueError, match="split fractions"):
        load_config(path)


def test_wrong_solver_fails(tmp_path: Path) -> None:
    path = _mutated_config(
        tmp_path,
        lambda data: data["mpc"].update({"solver": "CBC"}),
    )

    with pytest.raises(ValueError, match="mpc.solver"):
        load_config(path)


def test_enabled_certificate_flag_fails(tmp_path: Path) -> None:
    path = _mutated_config(
        tmp_path,
        lambda data: data["reporting"].update(
            {"official_certificate_claim_allowed": True}
        ),
    )

    with pytest.raises(ValueError, match="official_certificate_claim_allowed"):
        load_config(path)


def test_missing_required_section_fails(tmp_path: Path) -> None:
    path = _mutated_config(tmp_path, lambda data: data.pop("grid"))

    with pytest.raises(ValueError, match="missing required section"):
        load_config(path)
