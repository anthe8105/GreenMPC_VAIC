"""Typed data-source configuration for Stage 1 acquisition."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlparse

import yaml


REQUIRED_SOURCE_IDS = {
    "uci_electricity_load_diagrams",
    "uci_steel_industry",
    "nasa_power_hourly",
    "vietnam_tariff_reference",
}


@dataclass(frozen=True)
class StorageConfig:
    raw_root: str
    provenance_root: str
    temporary_suffix: str
    overwrite_existing: bool
    keep_compressed_archives: bool
    extract_large_archives_by_default: bool


@dataclass(frozen=True)
class NetworkConfig:
    connect_timeout_seconds: int
    read_timeout_seconds: int
    maximum_retries: int
    retry_backoff_seconds: int
    user_agent: str


@dataclass(frozen=True)
class BaseSourceConfig:
    source_id: str
    display_name: str
    enabled: bool
    source_type: str
    publisher: str
    official_landing_page: str
    expected_format: str
    destination_directory: str
    file_name: str
    license_name: str
    license_url: str | None
    citation_text: str
    required_for_stage: bool
    notes: str


@dataclass(frozen=True)
class UCISourceConfig(BaseSourceConfig):
    download_url: str


@dataclass(frozen=True)
class NASAPowerSourceConfig(BaseSourceConfig):
    endpoint: str
    latitude: float
    longitude: float
    location_label: str
    is_actual_vrg_location: bool
    community: str
    parameters: list[str]
    start_date: str
    end_date: str
    format: str
    time_standard: str


@dataclass(frozen=True)
class TariffSourceConfig(BaseSourceConfig):
    government_source_url: str
    evn_source_url: str
    decision_number: str
    issue_date: str
    selected_category: str
    manual_review_required: bool


@dataclass(frozen=True)
class DataSourceRegistryConfig:
    schema_version: int
    storage: StorageConfig
    network: NetworkConfig
    sources: dict[str, BaseSourceConfig]


def load_data_source_config(path: str | Path) -> DataSourceRegistryConfig:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        raise ValueError("data source configuration root must be a mapping")

    for section in ("schema_version", "storage", "network", "sources"):
        if section not in raw:
            raise ValueError(f"missing required section: {section}")

    storage = _build(StorageConfig, raw["storage"], "storage")
    network = _build(NetworkConfig, raw["network"], "network")
    raw_sources = raw["sources"]
    if not isinstance(raw_sources, dict):
        raise ValueError("sources must be a mapping")

    sources: dict[str, BaseSourceConfig] = {}
    for key, source_data in raw_sources.items():
        if not isinstance(source_data, dict):
            raise ValueError(f"sources.{key} must be a mapping")
        source_id = source_data.get("source_id")
        if source_id in {"uci_electricity_load_diagrams", "uci_steel_industry"}:
            source = _build(UCISourceConfig, source_data, f"sources.{key}")
        elif source_id == "nasa_power_hourly":
            source = _build(NASAPowerSourceConfig, source_data, f"sources.{key}")
        elif source_id == "vietnam_tariff_reference":
            source = _build(TariffSourceConfig, source_data, f"sources.{key}")
        else:
            raise ValueError(f"sources.{key}.source_id is not an approved Stage 1 source")
        sources[key] = source

    config = DataSourceRegistryConfig(
        schema_version=raw["schema_version"],
        storage=storage,
        network=network,
        sources=sources,
    )
    _validate(config)
    return config


def _build(cls: type[Any], data: dict[str, Any], section: str) -> Any:
    field_names = {field.name for field in cls.__dataclass_fields__.values()}
    missing = sorted(field_names.difference(data))
    if missing:
        raise ValueError(f"{section} missing required field(s): {', '.join(missing)}")
    return cls(**{field: data[field] for field in field_names})


def _validate(config: DataSourceRegistryConfig) -> None:
    if config.schema_version != 1:
        raise ValueError("schema_version must be 1")
    if config.storage.extract_large_archives_by_default:
        raise ValueError("storage.extract_large_archives_by_default must be false")
    _validate_network(config.network)

    source_ids = [source.source_id for source in config.sources.values()]
    if len(set(source_ids)) != len(source_ids):
        raise ValueError("sources.source_id values must be unique")
    missing = REQUIRED_SOURCE_IDS.difference(source_ids)
    if missing:
        raise ValueError(f"required sources missing: {', '.join(sorted(missing))}")

    for source in config.sources.values():
        _validate_base_source(source)
        if isinstance(source, UCISourceConfig):
            _require_https(source.download_url, f"{source.source_id}.download_url")
        elif isinstance(source, NASAPowerSourceConfig):
            _validate_nasa(source)
        elif isinstance(source, TariffSourceConfig):
            _validate_tariff(source)


def _validate_network(network: NetworkConfig) -> None:
    if network.connect_timeout_seconds <= 0:
        raise ValueError("network.connect_timeout_seconds must be positive")
    if network.read_timeout_seconds <= 0:
        raise ValueError("network.read_timeout_seconds must be positive")
    if network.maximum_retries < 0:
        raise ValueError("network.maximum_retries must be nonnegative")
    if network.retry_backoff_seconds < 0:
        raise ValueError("network.retry_backoff_seconds must be nonnegative")


def _validate_base_source(source: BaseSourceConfig) -> None:
    _require_https(source.official_landing_page, f"{source.source_id}.official_landing_page")
    if source.license_url is not None:
        _require_https(source.license_url, f"{source.source_id}.license_url")
    _require_relative_path(
        source.destination_directory,
        f"{source.source_id}.destination_directory",
    )
    _require_relative_path(source.file_name, f"{source.source_id}.file_name")
    if "actual vrg" in source.source_type.lower():
        raise ValueError(f"{source.source_id}.source_type must not claim actual VRG data")


def _validate_nasa(source: NASAPowerSourceConfig) -> None:
    _require_https(source.endpoint, "nasa_power_hourly.endpoint")
    if not -90 <= float(source.latitude) <= 90:
        raise ValueError("nasa_power_hourly.latitude must be between -90 and 90")
    if not -180 <= float(source.longitude) <= 180:
        raise ValueError("nasa_power_hourly.longitude must be between -180 and 180")
    if not source.parameters:
        raise ValueError("nasa_power_hourly.parameters must not be empty")
    if source.time_standard != "UTC":
        raise ValueError("nasa_power_hourly.time_standard must be UTC")
    if source.format != "CSV":
        raise ValueError("nasa_power_hourly.format must be CSV")
    if source.is_actual_vrg_location:
        raise ValueError("nasa_power_hourly.is_actual_vrg_location must be false")
    start = date.fromisoformat(source.start_date)
    end = date.fromisoformat(source.end_date)
    if start >= end:
        raise ValueError("nasa_power_hourly.start_date must precede end_date")


def _validate_tariff(source: TariffSourceConfig) -> None:
    _require_https(source.government_source_url, "vietnam_tariff_reference.government_source_url")
    _require_https(source.evn_source_url, "vietnam_tariff_reference.evn_source_url")
    if source.selected_category != "not_selected":
        raise ValueError("vietnam_tariff_reference.selected_category must remain not_selected")
    if not source.manual_review_required:
        raise ValueError("vietnam_tariff_reference.manual_review_required must be true")


def _require_https(url: str, field: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{field} must be an HTTPS URL")


def _require_relative_path(path_value: str, field: str) -> None:
    path = PurePosixPath(path_value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{field} must be a relative project path")
