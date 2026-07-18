from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from greenmpc.data.acquisition import PROJECT_ROOT, validate_offline
from greenmpc.data.provenance import read_acquisition_records, read_schema_report
from greenmpc.data.raw_validation import (
    inspect_nasa_csv,
    inspect_steel_csv,
    inspect_tariff_reference,
    inspect_uci_electricity_zip,
    validate_zip,
)
from greenmpc.data.source_config import NASAPowerSourceConfig, load_data_source_config


def _git_ignored(path: Path) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(path)],
        cwd=PROJECT_ROOT,
        check=False,
    )
    return result.returncode == 0


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    stage0 = subprocess.run(
        [sys.executable, "scripts/verify_stage0.py"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    checks.append(("Stage 0 verification", stage0.returncode == 0, stage0.stdout.strip() or stage0.stderr.strip()))

    try:
        config = load_data_source_config(PROJECT_ROOT / "configs" / "data_sources.yaml")
        checks.append(("data-source config loads", True, "loaded"))
    except Exception as exc:
        print(f"FAIL data-source config loads: {exc}")
        return 1

    records_path = PROJECT_ROOT / config.storage.provenance_root / "acquisitions.json"
    schema_path = PROJECT_ROOT / config.storage.provenance_root / "raw_schema_report.json"
    records = read_acquisition_records(records_path) if records_path.exists() else []
    schema = read_schema_report(schema_path) if schema_path.exists() else {}
    record_map = {record.source_id: record for record in records}
    checks.append(("provenance records exist", bool(records), str(records_path)))

    for source in config.sources.values():
        raw_path = PROJECT_ROOT / source.destination_directory / source.file_name
        checks.append((f"{source.source_id} raw path exists", raw_path.exists(), str(raw_path)))
        record = record_map.get(source.source_id)
        checks.append((f"{source.source_id} not actual VRG", bool(record and not record.is_actual_vrg_data), "is_actual_vrg_data=false"))
        if raw_path.exists() and source.source_id != "vietnam_tariff_reference":
            checks.append((f"{source.source_id} raw ignored by Git", _git_ignored(raw_path), str(raw_path)))

    try:
        load_zip = PROJECT_ROOT / "data/raw/uci_electricity_load_diagrams/electricityloaddiagrams20112014.zip"
        load_report = inspect_uci_electricity_zip(load_zip)
        checks.append(("UCI load ZIP and sample valid", True, load_report["primary_member"]))
        extracted_candidates = list(load_zip.parent.glob("*.txt")) + list(load_zip.parent.glob("*.csv"))
        checks.append(("large UCI load not extracted", not extracted_candidates, str(extracted_candidates)))
    except Exception as exc:
        checks.append(("UCI load ZIP and sample valid", False, str(exc)))

    try:
        steel_zip = PROJECT_ROOT / "data/raw/uci_steel_industry/steel_industry_energy_consumption.zip"
        validate_zip(steel_zip)
        steel_csvs = [path for path in steel_zip.parent.glob("*.csv")]
        steel_report = inspect_steel_csv(steel_csvs[0]) if steel_csvs else {}
        checks.append(("UCI steel valid", bool(steel_report), str(steel_report.get("columns"))))
    except Exception as exc:
        checks.append(("UCI steel valid", False, str(exc)))

    try:
        nasa_source = next(source for source in config.sources.values() if source.source_id == "nasa_power_hourly")
        assert isinstance(nasa_source, NASAPowerSourceConfig)
        nasa_report = inspect_nasa_csv(
            PROJECT_ROOT / nasa_source.destination_directory / nasa_source.file_name,
            nasa_source.parameters,
            nasa_source.start_date,
            nasa_source.end_date,
        )
        checks.append(("NASA data valid", nasa_report["expected_parameters_present"], str(nasa_report["time_columns"])))
        checks.append(("NASA raw remains UTC", nasa_report["time_standard"] == "UTC", "UTC"))
    except Exception as exc:
        checks.append(("NASA data valid", False, str(exc)))

    try:
        tariff_report = inspect_tariff_reference(PROJECT_ROOT / "data/raw/vietnam_tariff/tariff_reference.yaml")
        checks.append(("tariff metadata valid", True, str(tariff_report["decision_number"])))
    except Exception as exc:
        checks.append(("tariff metadata valid", False, str(exc)))

    offline_status = validate_offline(PROJECT_ROOT / "configs" / "data_sources.yaml")
    checks.append(("offline source validation", offline_status == 0, f"exit={offline_status}"))
    checks.append(("schema report exists", bool(schema), str(schema_path)))

    print("check | result | detail")
    print("----- | ------ | ------")
    failed = False
    for name, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        print(f"{name} | {status} | {detail}")
        failed = failed or not passed
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
