from __future__ import annotations

from pathlib import Path

from greenmpc.data.processed_provenance import build_lineage, file_sha256, write_json


def test_lineage_and_fingerprint(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    lineage = build_lineage()
    write_json(path, lineage)
    assert "load_kw" in lineage
    assert len(file_sha256(path)) == 64
