"""Structural validation for cached Stage 1 raw source files."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import yaml


def validate_zip(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"ZIP file is missing: {path}")
    if not zipfile.is_zipfile(path):
        raise ValueError(f"not a valid ZIP file: {path}")
    with zipfile.ZipFile(path) as archive:
        corrupt_member = archive.testzip()
        if corrupt_member is not None:
            raise ValueError(f"ZIP CRC validation failed for member: {corrupt_member}")
        members = archive.namelist()
    return {
        "path": str(path),
        "validation_level": "structural",
        "zip_valid": True,
        "member_count": len(members),
        "members": members,
    }


def inspect_uci_electricity_zip(path: Path, *, extract_large: bool = False) -> dict[str, Any]:
    zip_report = validate_zip(path)
    with zipfile.ZipFile(path) as archive:
        primary = _primary_member(archive.namelist(), [".txt", ".csv"])
        with archive.open(primary) as handle:
            sample_bytes = handle.read(128 * 1024)

    text, encoding = _decode_sample(sample_bytes)
    sample_lines = [line for line in text.splitlines() if line.strip()]
    if not sample_lines:
        raise ValueError("uci_electricity sample is empty")
    delimiter = _detect_delimiter(sample_lines[0])
    header = next(csv.reader([sample_lines[0]], delimiter=delimiter))
    data_line = sample_lines[1] if len(sample_lines) > 1 else ""
    values = next(csv.reader([data_line], delimiter=delimiter)) if data_line else []
    client_values = values[1:] if len(values) > 1 else []
    numeric_count = sum(_is_number(value.replace(",", ".")) for value in client_values[:20])
    if numeric_count == 0:
        raise ValueError("uci_electricity sample does not contain numeric client values")

    return {
        **zip_report,
        "primary_member": primary,
        "large_file_extracted": bool(extract_large),
        "delimiter": delimiter,
        "encoding": encoding,
        "timestamp_column": header[0] if header else "column_0",
        "timestamp_example": values[0] if values else None,
        "sample_line_count": len(sample_lines),
        "sample_column_count": len(header),
        "sample_client_column_count": max(len(header) - 1, 0),
        "numeric_client_values_in_first_20": numeric_count,
        "decimal_separator_behavior": "comma decimal values observed or accepted",
        "timezone_caveat": "Source timestamps use Portuguese local hour; daylight-saving handling is preserved for later stages.",
        "complete_statistical_validation": False,
    }


def extract_steel_csv(zip_path: Path, destination_dir: Path) -> Path:
    validate_zip(zip_path)
    destination_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        csv_members = [member for member in archive.namelist() if member.lower().endswith(".csv")]
        if not csv_members:
            raise ValueError("steel ZIP does not contain a CSV file")
        member = csv_members[0]
        target = destination_dir / Path(member).name
        resolved_dir = destination_dir.resolve()
        resolved_target = target.resolve()
        if not resolved_target.is_relative_to(resolved_dir):
            raise ValueError("steel ZIP member path traversal rejected")
        with archive.open(member) as source, target.open("wb") as output:
            output.write(source.read())
    return target


def inspect_steel_csv(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"steel CSV is missing: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        rows = list(reader)
    timestamp_examples = [row.get(columns[0], "") for row in rows[:3]] if columns else []
    numeric_fields = [
        column
        for column in columns
        if rows and all(_is_number(row.get(column, "")) for row in rows if row.get(column, "") != "")
    ]
    categorical_fields = [column for column in columns if column not in numeric_fields]
    missing_value_count = sum(
        1 for row in rows for column in columns if row.get(column, "") in {"", "NA", "NaN", "nan"}
    )
    return {
        "path": str(path),
        "validation_level": "structural",
        "columns": columns,
        "row_count": int(len(rows)),
        "timestamp_column_candidate": columns[0] if columns else None,
        "timestamp_examples": timestamp_examples,
        "numeric_fields": numeric_fields,
        "categorical_fields": categorical_fields,
        "missing_value_count": int(missing_value_count),
        "raw_columns_preserved": True,
        "units_as_reported_by_source": "as published in raw source columns",
    }


def validate_no_zip_path_traversal(zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.namelist():
            member_path = Path(member)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"ZIP path traversal rejected: {member}")


def inspect_nasa_csv(path: Path, expected_parameters: list[str], start_date: str, end_date: str) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"NASA CSV is missing: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise ValueError("NASA CSV is empty")
    if text.lstrip().lower().startswith("<!doctype html") or text.lstrip().lower().startswith("<html"):
        raise ValueError("NASA response appears to be HTML")
    for parameter in expected_parameters:
        if parameter not in text:
            raise ValueError(f"NASA expected parameter missing: {parameter}")

    data_start_index = _find_nasa_data_start(text)
    data_text = "\n".join(text.splitlines()[data_start_index:])
    reader = csv.DictReader(io.StringIO(data_text))
    columns = reader.fieldnames or []
    rows = list(reader)
    sentinel_counts = {
        column: sum(1 for row in rows if row.get(column) in {"-999", "-999.0"})
        for column in columns
        if rows and all(_is_number(row.get(column, "")) for row in rows if row.get(column, "") != "")
    }
    year_values = [row.get("YEAR", "") for row in rows] if "YEAR" in columns else []
    coverage_includes_period = bool(year_values) and start_date[:4] in year_values and end_date[:4] in year_values
    return {
        "path": str(path),
        "validation_level": "structural",
        "columns": columns,
        "row_count": int(len(rows)),
        "expected_parameters_present": all(parameter in columns for parameter in expected_parameters),
        "time_columns": [column for column in ["YEAR", "MO", "DY", "HR"] if column in columns],
        "coverage_includes_requested_period": coverage_includes_period,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "missing_value_sentinel_counts": sentinel_counts,
        "time_standard": "UTC",
        "raw_header_preserved": data_start_index > 0,
    }


def inspect_tariff_reference(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"tariff reference is missing: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data.get("selected_customer_category") is not None:
        raise ValueError("tariff selected_customer_category must remain null")
    if data.get("selected_voltage_level") is not None:
        raise ValueError("tariff selected_voltage_level must remain null")
    if data.get("operational_values_imported") is not False:
        raise ValueError("tariff operational_values_imported must be false")
    if data.get("manual_review_required") is not True:
        raise ValueError("tariff manual_review_required must be true")
    return {
        "path": str(path),
        "validation_level": "metadata",
        "decision_number": data.get("decision_number"),
        "issue_date": data.get("issue_date"),
        "effective_date": data.get("effective_date"),
        "selected_customer_category": data.get("selected_customer_category"),
        "selected_voltage_level": data.get("selected_voltage_level"),
        "operational_values_imported": data.get("operational_values_imported"),
        "manual_review_required": data.get("manual_review_required"),
        "official_source_reachable": data.get("official_source_reachable"),
    }


def _primary_member(members: list[str], suffixes: list[str]) -> str:
    candidates = [
        member for member in members
        if not member.endswith("/")
        and "__MACOSX" not in Path(member).parts
        and not Path(member).name.startswith("._")
        and any(member.lower().endswith(suffix) for suffix in suffixes)
    ]
    if not candidates:
        raise ValueError("ZIP archive does not contain an expected primary data file")
    return max(candidates, key=len)


def _decode_sample(sample: bytes) -> tuple[str, str]:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return sample.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return sample.decode("utf-8", errors="replace"), "utf-8-replace"


def _detect_delimiter(header_line: str) -> str:
    candidates = [";", ",", "\t"]
    return max(candidates, key=header_line.count)


def _is_number(value: str) -> bool:
    if value is None:
        return False
    try:
        float(value)
        return True
    except ValueError:
        return False


def _find_nasa_data_start(text: str) -> int:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("YEAR,") or line.startswith("YEAR;"):
            return index
    raise ValueError("NASA CSV data header with YEAR column was not found")
