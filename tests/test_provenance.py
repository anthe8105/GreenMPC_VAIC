from __future__ import annotations

from pathlib import Path

from greenmpc.data.provenance import (
    AcquisitionRecord,
    read_acquisition_records,
    write_acquisition_records,
)


def test_provenance_serialization_and_reload(tmp_path: Path) -> None:
    record = AcquisitionRecord(
        source_id="uci_steel_industry",
        source_name="Steel",
        publisher="UCI",
        source_type="measured industrial electricity consumption",
        landing_page="https://example.test",
        retrieval_url="https://example.test/file.zip",
        retrieved_at_utc="2026-01-01T00:00:00+00:00",
        local_path="data/raw/file.zip",
        file_name="file.zip",
        byte_size=3,
        sha256="abc",
        content_type="application/zip",
        license_name="review",
        license_url=None,
        citation_text="citation",
        retrieval_status="downloaded",
        validation_status="passed",
        validation_level="structural",
        warnings=[],
        source_notes="notes",
        is_measured_data=True,
        is_derived_data=False,
        is_synthetic_data=False,
        is_rescaled_data=False,
        is_actual_vrg_data=False,
    )
    path = tmp_path / "acquisitions.json"

    write_acquisition_records(path, [record])
    loaded = read_acquisition_records(path)

    assert loaded == [record]
    assert not loaded[0].is_actual_vrg_data
