"""Stage 1 public-source acquisition orchestration."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode

import yaml

from greenmpc.data.download import DownloadResult, download_file, sha256_file
from greenmpc.data.provenance import (
    AcquisitionRecord,
    read_acquisition_records,
    utc_now_iso,
    write_acquisition_records,
    write_schema_report,
    write_sources_manifest,
)
from greenmpc.data.raw_validation import (
    extract_steel_csv,
    inspect_nasa_csv,
    inspect_steel_csv,
    inspect_tariff_reference,
    inspect_uci_electricity_zip,
    validate_no_zip_path_traversal,
    validate_zip,
)
from greenmpc.data.source_config import (
    DataSourceRegistryConfig,
    NASAPowerSourceConfig,
    TariffSourceConfig,
    UCISourceConfig,
    load_data_source_config,
)


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_ALIASES = {
    "uci-load": "uci_electricity_load_diagrams",
    "uci-steel": "uci_steel_industry",
    "nasa-power": "nasa_power_hourly",
    "tariff": "vietnam_tariff_reference",
}


@dataclass(frozen=True)
class SourceStatus:
    source_id: str
    enabled: bool
    required: bool
    cached: bool
    validated: bool
    local_path: str
    file_size: int | None
    sha256_prefix: str | None
    retrieval_timestamp: str | None
    warnings: list[str]


def load_default_registry() -> DataSourceRegistryConfig:
    return load_data_source_config(PROJECT_ROOT / "configs" / "data_sources.yaml")


def acquire_sources(
    *,
    source_names: list[str] | None = None,
    all_sources: bool = False,
    offline: bool = False,
    force: bool = False,
    extract_large: bool = False,
    config_path: Path | str | None = None,
) -> int:
    config = load_data_source_config(config_path or PROJECT_ROOT / "configs" / "data_sources.yaml")
    selected_ids = _selected_source_ids(config, source_names, all_sources)
    records = _load_existing_records(config)
    schema_report = _load_existing_schema_report(config)
    failures: list[str] = []

    write_sources_manifest(_provenance_root(config) / "sources.yaml", config)
    _write_provenance_readme(_provenance_root(config) / "README.md")

    for source_id in selected_ids:
        source = _source_by_id(config, source_id)
        try:
            if isinstance(source, UCISourceConfig) and source.source_id == "uci_electricity_load_diagrams":
                record, report = _acquire_uci_electricity(config, source, offline, force, extract_large)
            elif isinstance(source, UCISourceConfig) and source.source_id == "uci_steel_industry":
                record, report = _acquire_uci_steel(config, source, offline, force)
            elif isinstance(source, NASAPowerSourceConfig):
                record, report = _acquire_nasa(config, source, offline, force)
            elif isinstance(source, TariffSourceConfig):
                record, report = _acquire_tariff(config, source, offline, force)
            else:
                raise ValueError(f"unsupported source: {source_id}")
            records[source.source_id] = record
            schema_report[source.source_id] = report
            LOGGER.info("Acquired %s: %s", source.source_id, record.validation_status)
        except Exception as exc:
            failures.append(f"{source_id}: {exc}")
            LOGGER.error("Source failed: %s", failures[-1])

    write_acquisition_records(_provenance_root(config) / "acquisitions.json", list(records.values()))
    write_schema_report(_provenance_root(config) / "raw_schema_report.json", schema_report)
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    return 0


def status_table(config_path: Path | str | None = None) -> list[SourceStatus]:
    config = load_data_source_config(config_path or PROJECT_ROOT / "configs" / "data_sources.yaml")
    records = _load_existing_records(config)
    statuses: list[SourceStatus] = []
    for source in config.sources.values():
        path = _local_path(source)
        record = records.get(source.source_id)
        cached = path.exists()
        statuses.append(
            SourceStatus(
                source_id=source.source_id,
                enabled=source.enabled,
                required=source.required_for_stage,
                cached=cached,
                validated=bool(record and record.validation_status == "passed"),
                local_path=str(path),
                file_size=path.stat().st_size if cached else None,
                sha256_prefix=record.sha256[:12] if record and record.sha256 else None,
                retrieval_timestamp=record.retrieved_at_utc if record else None,
                warnings=record.warnings if record else [],
            )
        )
    return statuses


def print_status_table(config_path: Path | str | None = None) -> None:
    rows = status_table(config_path)
    headers = ["source_id", "enabled", "required", "cached", "validated", "size", "sha256", "retrieved", "warnings"]
    print(" | ".join(headers))
    print(" | ".join("-" * len(header) for header in headers))
    for row in rows:
        print(
            " | ".join(
                [
                    row.source_id,
                    str(row.enabled),
                    str(row.required),
                    str(row.cached),
                    str(row.validated),
                    str(row.file_size or ""),
                    row.sha256_prefix or "",
                    row.retrieval_timestamp or "",
                    "; ".join(row.warnings),
                ]
            )
        )


def validate_offline(config_path: Path | str | None = None) -> int:
    return acquire_sources(all_sources=True, offline=True, config_path=config_path)


def _acquire_uci_electricity(
    config: DataSourceRegistryConfig,
    source: UCISourceConfig,
    offline: bool,
    force: bool,
    extract_large: bool,
) -> tuple[AcquisitionRecord, dict]:
    path = _local_path(source)
    result = _download_or_cache(config, source.download_url, path, source.expected_format, offline, force)
    report = inspect_uci_electricity_zip(path, extract_large=extract_large)
    warnings = ["Only structural sample validation was performed; full statistical validation is deferred."]
    if extract_large:
        _extract_large_uci_file(path, Path(source.destination_directory))
    return _record(source, source.download_url, result, "passed", "structural", warnings, True), report


def _acquire_uci_steel(
    config: DataSourceRegistryConfig,
    source: UCISourceConfig,
    offline: bool,
    force: bool,
) -> tuple[AcquisitionRecord, dict]:
    path = _local_path(source)
    result = _download_or_cache(config, source.download_url, path, source.expected_format, offline, force)
    validate_no_zip_path_traversal(path)
    validate_zip(path)
    csv_path = extract_steel_csv(path, path.parent)
    report = inspect_steel_csv(csv_path)
    return _record(source, source.download_url, result, "passed", "structural", [], True), report


def _acquire_nasa(
    config: DataSourceRegistryConfig,
    source: NASAPowerSourceConfig,
    offline: bool,
    force: bool,
) -> tuple[AcquisitionRecord, dict]:
    path = _local_path(source)
    request_record = _nasa_request_record(source)
    request_path = path.parent / "nasa_power_request.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(request_record, indent=2, sort_keys=True), encoding="utf-8")
    result = _download_or_cache(config, request_record["generated_request_url"], path, "csv", offline, force)
    report = inspect_nasa_csv(path, source.parameters, source.start_date, source.end_date)
    warnings = ["NASA POWER is satellite/model-based and is not an on-site weather sensor."]
    return _record(source, request_record["generated_request_url"], result, "passed", "structural", warnings, False), report


def _acquire_tariff(
    config: DataSourceRegistryConfig,
    source: TariffSourceConfig,
    offline: bool,
    force: bool,
) -> tuple[AcquisitionRecord, dict]:
    path = _local_path(source)
    path.parent.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    if offline:
        if not path.exists():
            raise FileNotFoundError(f"offline cache missing: {path}")
        existing = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if existing.get("official_source_error"):
            warnings.append(f"Official tariff page retrieval failed: {existing['official_source_error']}")
        result = DownloadResult(
            url=source.government_source_url,
            final_url=source.government_source_url,
            local_path=path,
            byte_size=path.stat().st_size,
            sha256=sha256_file(path),
            content_type="application/x-yaml",
            content_length=str(path.stat().st_size),
            etag=None,
            last_modified=None,
            from_cache=True,
        )
        report = inspect_tariff_reference(path)
        return _record(source, source.government_source_url, result, "passed", "metadata", warnings, False), report

    official_status: dict[str, object] = {"official_source_reachable": None}
    html_path = path.parent / "government_source.html"
    try:
        result = _download_or_cache(
            config,
            source.government_source_url,
            html_path,
            "html",
            offline=False,
            force=force,
        )
        official_status = {
            "official_source_reachable": True,
            "downloaded_source": {
                "local_path": str(html_path),
                "byte_size": result.byte_size,
                "sha256": result.sha256,
                "content_type": result.content_type,
            },
        }
    except Exception as exc:
        official_status = {"official_source_reachable": False, "official_source_error": str(exc)}
        warnings.append(f"Official tariff page retrieval failed: {exc}")

    tariff_record = {
        "source_type": source.source_type,
        "country": "Vietnam",
        "publisher": source.publisher,
        "decision_number": source.decision_number,
        "issue_date": source.issue_date,
        "effective_date": None,
        "government_source_url": source.government_source_url,
        "evn_source_url": source.evn_source_url,
        "retrieved_at_utc": utc_now_iso(),
        "selected_customer_category": None,
        "selected_voltage_level": None,
        "operational_values_imported": False,
        "manual_review_required": True,
        "notes": source.notes,
        **official_status,
    }
    path.write_text(yaml.safe_dump(tariff_record, sort_keys=False), encoding="utf-8")
    result = DownloadResult(
        url=source.government_source_url,
        final_url=source.government_source_url,
        local_path=path,
        byte_size=path.stat().st_size,
        sha256=sha256_file(path),
        content_type="application/x-yaml",
        content_length=str(path.stat().st_size),
        etag=None,
        last_modified=None,
        from_cache=offline,
    )
    report = inspect_tariff_reference(path)
    return _record(source, source.government_source_url, result, "passed", "metadata", warnings, False), report


def _download_or_cache(
    config: DataSourceRegistryConfig,
    url: str,
    path: Path,
    expected_format: str,
    offline: bool,
    force: bool,
) -> DownloadResult:
    if offline:
        if not path.exists():
            raise FileNotFoundError(f"offline cache missing: {path}")
        return DownloadResult(
            url=url,
            final_url=url,
            local_path=path,
            byte_size=path.stat().st_size,
            sha256=sha256_file(path),
            content_type=None,
            content_length=None,
            etag=None,
            last_modified=None,
            from_cache=True,
        )
    return download_file(
        url,
        path,
        user_agent=config.network.user_agent,
        timeout_seconds=config.network.read_timeout_seconds,
        retries=config.network.maximum_retries,
        retry_backoff_seconds=config.network.retry_backoff_seconds,
        temporary_suffix=config.storage.temporary_suffix,
        force=force,
        expected_format=expected_format if expected_format in {"zip", "csv"} else None,
    )


def _record(
    source,
    retrieval_url: str,
    result: DownloadResult,
    validation_status: str,
    validation_level: str,
    warnings: list[str],
    measured: bool,
) -> AcquisitionRecord:
    return AcquisitionRecord(
        source_id=source.source_id,
        source_name=source.display_name,
        publisher=source.publisher,
        source_type=source.source_type,
        landing_page=source.official_landing_page,
        retrieval_url=retrieval_url,
        retrieved_at_utc=utc_now_iso(),
        local_path=str(result.local_path),
        file_name=result.local_path.name,
        byte_size=result.byte_size,
        sha256=result.sha256,
        content_type=result.content_type,
        license_name=source.license_name,
        license_url=source.license_url,
        citation_text=source.citation_text,
        retrieval_status="cached" if result.from_cache else "downloaded",
        validation_status=validation_status,
        validation_level=validation_level,
        warnings=warnings,
        source_notes=source.notes,
        is_measured_data=measured,
        is_derived_data=False,
        is_synthetic_data=False,
        is_rescaled_data=False,
        is_actual_vrg_data=False,
    )


def _nasa_request_record(source: NASAPowerSourceConfig) -> dict:
    params = {
        "parameters": ",".join(source.parameters),
        "community": source.community,
        "longitude": source.longitude,
        "latitude": source.latitude,
        "start": source.start_date.replace("-", ""),
        "end": source.end_date.replace("-", ""),
        "format": source.format,
        "time-standard": source.time_standard,
    }
    return {
        "endpoint": source.endpoint,
        "query_parameters": params,
        "generated_request_url": f"{source.endpoint}?{urlencode(params)}",
        "retrieval_timestamp": utc_now_iso(),
        "location_label": source.location_label,
        "coordinate_disclaimer": "Coordinates are configurable demonstration assumptions and are not an actual VRG facility.",
    }


def _extract_large_uci_file(zip_path: Path, destination_directory: Path) -> None:
    validate_no_zip_path_traversal(zip_path)
    import zipfile

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            if member.lower().endswith((".txt", ".csv")):
                archive.extract(member, destination_directory)
                return


def _selected_source_ids(
    config: DataSourceRegistryConfig,
    source_names: list[str] | None,
    all_sources: bool,
) -> list[str]:
    if all_sources:
        return [source.source_id for source in config.sources.values() if source.enabled]
    if not source_names:
        raise ValueError("select --all or at least one --source")
    selected: list[str] = []
    for name in source_names:
        source_id = SOURCE_ALIASES.get(name, name)
        _source_by_id(config, source_id)
        selected.append(source_id)
    return selected


def _source_by_id(config: DataSourceRegistryConfig, source_id: str):
    for source in config.sources.values():
        if source.source_id == source_id:
            return source
    raise ValueError(f"unknown source: {source_id}")


def _local_path(source) -> Path:
    return PROJECT_ROOT / source.destination_directory / source.file_name


def _provenance_root(config: DataSourceRegistryConfig) -> Path:
    return PROJECT_ROOT / config.storage.provenance_root


def _load_existing_records(config: DataSourceRegistryConfig) -> dict[str, AcquisitionRecord]:
    path = _provenance_root(config) / "acquisitions.json"
    if not path.exists():
        return {}
    return {record.source_id: record for record in read_acquisition_records(path)}


def _load_existing_schema_report(config: DataSourceRegistryConfig) -> dict:
    path = _provenance_root(config) / "raw_schema_report.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_provenance_readme(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """# Raw Data Provenance

Stage 1 caches public raw inputs and stores reviewable provenance metadata.

- UCI electricity profiles are measured anonymous client-consumption profiles with Portuguese local timestamps. They are not industry-labeled, not Vietnamese, and not VRG records.
- UCI steel data is a measured South Korean steel-industry source. It is not a proxy for all future scenario tenant industries.
- NASA POWER data is satellite/model-based meteorological and solar-resource data for configurable demonstration coordinates. Raw data is retained in UTC.
- Vietnam tariff records are curated regulatory/reference metadata. Customer category and voltage level are not selected in Stage 1.

Raw archives and CSV files are excluded from Git because they are externally sourced and may be large. Reacquire them with `python scripts/acquire_public_data.py --all`; validate cached files without network calls using `python scripts/acquire_public_data.py --all --offline`.

Citation text and retrieval fingerprints are recorded in `sources.yaml` and `acquisitions.json`. The SHA-256 values are local retrieval fingerprints unless a publisher-provided checksum is separately documented.

No Stage 1 source is actual VRG operational data, actual VRG tenant data, a confidential DPPA contract, an actual VRG battery specification, or actual VRG transformer topology.
""",
        encoding="utf-8",
    )
