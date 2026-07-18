"""Stage 1 provenance records and serialization."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class AcquisitionRecord:
    source_id: str
    source_name: str
    publisher: str
    source_type: str
    landing_page: str
    retrieval_url: str
    retrieved_at_utc: str
    local_path: str
    file_name: str
    byte_size: int
    sha256: str
    content_type: str | None
    license_name: str
    license_url: str | None
    citation_text: str
    retrieval_status: str
    validation_status: str
    validation_level: str
    warnings: list[str]
    source_notes: str
    is_measured_data: bool
    is_derived_data: bool
    is_synthetic_data: bool
    is_rescaled_data: bool
    is_actual_vrg_data: bool


def write_acquisition_records(path: Path, records: list[AcquisitionRecord]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(record) for record in records], indent=2, sort_keys=True),
        encoding="utf-8",
    )


def read_acquisition_records(path: Path) -> list[AcquisitionRecord]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [AcquisitionRecord(**record) for record in raw]


def write_sources_manifest(path: Path, config: Any) -> None:
    manifest = {
        "schema_version": config.schema_version,
        "generated_at_utc": utc_now_iso(),
        "sources": [
            {
                "source_id": source.source_id,
                "display_name": source.display_name,
                "publisher": source.publisher,
                "source_type": source.source_type,
                "official_landing_page": source.official_landing_page,
                "destination_directory": source.destination_directory,
                "license_name": source.license_name,
                "license_url": source.license_url,
                "citation_text": source.citation_text,
                "required_for_stage": source.required_for_stage,
                "notes": source.notes,
            }
            for source in config.sources.values()
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def write_schema_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def read_schema_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
