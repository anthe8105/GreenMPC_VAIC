from __future__ import annotations

from pathlib import Path

from greenmpc.forecasting.artifacts import file_sha256, write_json


def test_json_and_hash(tmp_path: Path) -> None:
    path = tmp_path / "x.json"
    write_json(path, {"a": 1})
    assert len(file_sha256(path)) == 64
